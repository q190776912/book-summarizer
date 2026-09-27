"""lib/unit_markers.py — 单元首行标记 ↔ 本侧 manifest 记录 的对账判据。

被两处消费，判据只此一份：
- ``flows/write-source/script/check_translate_parity.py``（步骤 7 判据 12，源/译两侧）
- ``flows/write-source/script/gate_units.py``（步骤 5 单元门控，源侧与译侧同规则）

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
        return "%s侧首行与本侧 manifest 记录脱账 —— %s" % (side, "；".join(diff))
    return None
