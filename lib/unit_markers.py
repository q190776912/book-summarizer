"""lib/unit_markers.py — 单元首行标记 ↔ 本侧 manifest 记录 的对账判据。

被两处消费，判据只此一份：
- ``flows/write-source/script/check_translate_parity.py``（步骤 7 判据 12，源/译两侧）
- ``flows/write-source/script/gate_units.py``（步骤 5 单元门控，源侧与译侧同规则）

另提供 `outside_marker()`：整文件格式重写工具（`tools/normalize_math_cli.py`、
`tools/_wrap_raw_math.py`）用它跳过首行标记 —— 标记是登记处的抄本，不归格式工具管。

为什么必须有机械闸（2026-09-28 Shafarevich BAG1 ch1/0073 教训）：写源阶段人工改单元
首行时把 ``name=`` 截断（``…the element Zd+1 is`` 丢了 `` separable over the``），
`gate_units` 照旧 PASS——它只判「标记在不在 / 是不是 DRAFT / 有无泄漏」，从不把首行
与本侧 manifest 记录逐字段比。于是缺陷一路带到步骤 7 才由 parity 判据 12 抓出，
而此时该章已 merge/verify，返工面扩大。同源判据前置到写源门控 = 缺陷当步即暴露。
"""
import re

MARKER_RE = re.compile(
    r"^<!--\s*book-summarizer\s+(?:DONE|DRAFT)\s+unit:\s*"
    r"id=(\S*)\s+type=(\S*)\s+key=(.*?)\s+name=(.*?)\s*-->$")

MARKER_FIELDS = ("id", "type", "key", "name")


def is_unit_marker_line(line):
    return bool(MARKER_RE.match(line.rstrip("\r\n")))


def outside_marker(text, fn):
    """对**除首行单元标记之外**的文本跑 `fn`，再把原首行原样接回。

    🔴 首行 `<!-- book-summarizer DONE unit: … name=… -->` 是登记处（本侧 `manifest.json`）
    在文件里的抄本，判据 12 要求与之**逐字**一致。任何整文件正则重写（KaTeX 定界符归一、
    裸 Unicode 字形包 `$…$`）扫到它，就会把题名改成契约与 manifest 里都不存在的形态，
    一章单元集体脱账 —— 实测 Fraleigh《A First Course in Abstract Algebra》一本 550 处、
    全库 1129 处全是这一类首行被顺手改过（正文一字节未变）。所以格式工具一律只许动标记以外
    的部分；已经造成的债用 `tools/sync_translate_markers.py` 复位。
    """
    head, sep, rest = text.partition("\n")
    if not is_unit_marker_line(head):
        return fn(text)
    return head + sep + fn(rest)


def marker_manifest_mismatch(path, rec, side):
    """单元**首行标记**的 `id/type/key/name` 必须与「该单元在**自己那侧**
    `manifest.json` 里的记录」逐字相同；不一致返回说明串，一致返回 None。

    为什么对 manifest 而非对「另一侧的文件首行」：两侧首行历史上**互相**被回填/改写过
    （Robinson 动力学 16 个单元里，有的是译文代理补全截断标题、有的是**源**文件首行存着
    UTF-8 被二次解码成的三字符乱码，而 manifest 里是正确的箭头），文件↔文件比无法判定
    权威侧；manifest 才是登记处，且 parity 第 1 项已保证两侧 manifest 互相 1:1。
    跨书实测命中：real-analysis 2 文件（`type=desc` vs manifest `description`）、
    Robinson 动力学 18、do Carmo 曲线曲面 0、Etingof 0（首尾行被代理改过、当场手工复位的
    ch1/0063/0064 即属本类）。复位工具 `tools/sync_translate_markers.py`（只写首行；
    首行不进最终 md，故复位不需重 merge/verify）。

    2026-10-21 全库普查收口：脱账 1129 处集中在 4 本已收官书（Fraleigh 550 / Rosen 244 /
    数学分析 323 / 黎曼几何 12），逐条按契约裁决后**全部**是「manifest 站在契约那侧、首行被
    顺手改过」（把裸 Unicode 包成 `$≥$`、自撰干净题名、截断题名三类），已全部复位归零；
    同轮给复位工具补上 `name` 双侧裁定（首行在契约账上而 manifest 不在时禁止复位）。
    """
    try:
        with open(path, encoding="utf-8") as f:
            line = f.readline().rstrip("\r\n")
    except OSError as e:
        return "%s侧首行读取失败：%s" % (side, e)
    m = MARKER_RE.match(line)
    if not m:
        return "%s侧首行不可解析（不是 `<!-- book-summarizer DONE unit: ... -->`）：%r" % (
            side, line[:80])
    got = m.groups()
    want = tuple(str(rec.get(k) or "") for k in MARKER_FIELDS)
    if got != want:
        diff = ["%s: 标记 %r / manifest %r" % (k, a, b)
                for k, a, b in zip(MARKER_FIELDS, got, want) if a != b]
        return ("%s侧首行与本侧 manifest 记录脱账 —— %s"
                "（首行是登记处的抄本：改单元只许把 DRAFT 翻成 DONE，题名要 KaTeX 化请改正文；"
                "复位用 tools/sync_translate_markers.py）" % (side, "；".join(diff)))
    return None
