"""build_structure.py — 统一结构骨架生成器：按章产出分章骨架 ch{N}.json

设计
----
每章一个文件：``<extract_dir>/book_structure/ch{N}.json``（附录 ``appendix{X}.json``），
顶层即该章 ``chapter`` 节点（无书根包装）。本脚本**一步产出含内容的完整契约**
（骨架 + description / proof / 内容块同进程挂入后写回同一文件，幂等可重跑）——
分章文件是结构契约唯一真源；整书单文件 ``book_structure.json`` 不是合法产物、不读取。
``attach_content.py`` 的 attach CLI 仅保留为全章重挂的手动维护入口。
节点 schema 见 ``flows/write-source/structure/structure.md`` 与
``data/book_structure/book_structure.py``（BookStructure / StructureNode）。

增量：每章文件独立，``build_structure <ext> [ch ...]`` 只重建指定章（附录章传
字母章号，如 ``build_structure <ext> A``）；不传 <ch> 即全量重建。


为什么需要它
------------
本脚本把 `scan_skeleton` 的 `SEC`/`EXER` 扫描 与 `extract_items*` 的编号项抽取**内部调用**，
按章产出**分章契约**（`book_structure/ch{N}.json` / `appendix{X}.json`，含内容完整契约），
一次产出同时满足两类需求：
  · write-source 写作契约：章节顺序、条目/练习齐全、印刷标题（name 带序标）。
  · verify 编号项基准：展平树、filter type not in ("exercise","problem") 即得本书编号项集合
    （data_provider 经 BookStructure.load 聚合读取分章文件为编号项基准）。

设计要点（与 verify/data_provider 对齐）
--------------------------------------
  · 编号模式（three-level / two-level / en / vakil / ross / hum …）
    由 `<extract_dir>/verify_config.json` 的 `ordinal` 自动判定，与 verify/data_provider
    同一套分派逻辑。**build_structure 是抽取器的唯一调用方**（verify 读 JSON，不再重跑抽取器）。
  · **条目权威来自抽取器**（带类型）：skeleton 的 ITEM 行对 dash 编号书
    （如 Kreyszig `1.1-1`）匹配不到 `1.1.1.` 正则，故不可靠；en two-level 的
    skeleton 整块乱匹配，同样不可靠。所以 ITEM 节点一律用抽取器结果。
  · **章节骨架来自 skeleton SEC**（含印刷标题）；当某方案 skeleton SEC 捕获
    不全（en two-level / vakil），用「条目键派生章节号」补齐。
  · **练习来自 skeleton EXER**（统一来源），抽取器里的 练习/习题 类键被排除，
    避免与 EXER 重复计数。
  · 条目/练习挂到章节：优先「派生章节号命中」→ 否则「按页码归最近 SEC」。

节点字段
--------
    key        书原生编号（语言无关，如 "1.1-1" / "定义 1.2" / "1.2.A" / "1"）
    type       chapter|section|definition|theorem|lemma|corollary|proposition|
               example|exercise|remark|uncat
    name       带序标的纯标题（不含正文内容）；叶子即 key
    page_start 起始页（叶子 == page_end）
    page_end   容器取末代子孙页；叶子 == page_start
    sub_sec    递归子节点；仅 chapter/section 含此键（叶子省略）

顶层为数组，按章顺序；每章一个 chapter 节点。

用法
----
    python build_structure.py <extract_dir> [ch ...]
    # 全书：不传 <ch> 即扫全部章
    # 编号模式由 verify_config.json 的 ordinal 自动判定，无需 --scheme
"""
import glob
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()
from lib.util import blk_text
from lib.unit_order import check_contract_anchors, check_section_key_page_order

import json
import functools
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

import scan_skeleton
from extract_items import extract_items, extract_items_two_level
from extract_items_cn_single import extract_items_cn_single
from extract_items_en import extract_items_en
from extract_items_en3 import extract_items_en3
from extract_items_vakil import extract_items_vakil
from extract_items_hum import extract_items_hum
from extract_items_gm import extract_items_gm, scan_gm
from verify_config import (ORDINAL_TWO_LEVEL,
                              ORDINAL_SINGLE, ORDINAL_VAKIL,
                              ORDINAL_THREE_LEVEL,
                              ORDINAL_HUM, ORDINAL_APP, ORDINAL_APP2,
                              LABEL_TO_TYPE as _SHARED_LABEL_TO_TYPE,
                              ConfigLoader, ConfigError, BookConfig)
import chapter_map
from key_parse import _canon_label, normkey
from data.book_structure.book_structure import (BookStructure, StructureNode,
                                                chapter_json_path,
                                                norm_chapter_key,
                                                chapter_label, chapter_ordinal,
                                                is_numbered_chapter)


# ---------------------------------------------------------------------------
# 类型映射：抽取器 label（中文 canon 或英文原文） -> 树 type
# 单源：LABEL_TO_TYPE 派生自 config/verify_config 的 _LABEL_CANON ×
# TYPE_TO_LABEL_CN（类型词表单一来源，新增标签只改 config）。本地仅合并
# Table/Figure 两个图表注记类型——图表管线管辖，不属内容类型词表：
# section-scoped 书（Fraleigh 体例）中 Table/Figure 与正文条目共享节内计数器，
# 须自成节点（type=table/figure）而非 uncat——否则 group_for_label() 把它们
# 归入 uncat 组、text counter 在图表槽位（1.20 / 1.21 …）看到假「缺号」。
# 与 make_config 把 "Table"/"Figure" 折叠进合并 ordinal name 的分支配套。
# ---------------------------------------------------------------------------
_LABEL_TO_TYPE = {
    **_SHARED_LABEL_TO_TYPE,
    "Table": "table", "Figure": "figure",
}
# Exercise 族（Lee 2e 节内点式编号，与定理/例共享章计数器）经 3a 转入 EXER
# 行 → exercise 节点。
_EXERCISE_LABELS = {"练习", "习题", "Exercise", "练习.", "Problem"}
# 🔴 Problem 是独立节点类型 problem（用户 2026-09-12 拍板）：语义身份=问题
# （正名 _LABEL_CANON['Problem']='问题'；章末独立计数器、发展性结果、会被
# 正文证明引用，如 Lee ch21 引 Problem 20-11），与节内练习不同类。3a 按
# _PROBLEM_LABELS 打 PROB 行标记，节点构造落 type='problem'；通道机制
# （B 层豁免 / DONE-only 门控 / 单元类型 exercise）与 exercise 同族。
_PROBLEM_LABELS = {"Problem"}

# Case-insensitive view of `_LABEL_TO_TYPE` so OCR-mangled UPPERCASE labels
# (do Carmo prints `DEFINITION` / `THEOREM` in all caps; OCR may also mangle
# them to `DEFINrTION`) still resolve to the correct node type instead of
# falling through to "uncat".  CN keys are unchanged by lowercasing.
_LABEL_TO_TYPE_LC = {k.lower(): v for k, v in _LABEL_TO_TYPE.items()}


def _type_of(label):
    l = (label or "").strip().lower()
    return _LABEL_TO_TYPE_LC.get(l, "uncat")


# ---------------------------------------------------------------------------
# 章节号推导
# ---------------------------------------------------------------------------
_STRIP_LABEL = re.compile(
    r'^(定义|定理|引理|推论|命题|例|评注|注|算法|假设|断言|猜想|'
    r'Definition|Theorem|Lemma|Corollary|Proposition|Example|Remark|'
    r'Assertion|Conjecture|Algorithm|Assumption)\b\s*', re.IGNORECASE)
_STRIP_LABEL_CN = re.compile(r'^(定义|定理|引理|推论|命题|例|评注|注)')


def _nat_key(k):
    """自然序键：数字段按数值比较（'例9' < '例10'）。

    同页条目以 key 作次级排序时，纯字符串序会把 '例10' 排在 '例9' 前
    （'1' < '9'），B 层顺序校验随即报「顺序错乱」。数字按值比较对既有书
    亦严格更正确（同页 'Theorem 9' / 'Theorem 10' 同理）。
    """
    return tuple(int(x) if x.isdigit() else x
                 for x in re.split(r"(\d+)", str(k)))


def _nat_key_digits(k):
    """数字优先自然序键：主键 = key 内全部数字段（按值），次键 = _nat_key。

    同一计数器内条目号在阅读序中单调递增（B 层连续性的前提），而
    _nat_key 把标签词放在元组首位，CJK 标签按码位比较（'命'<'定'<'引'）
    会颠倒同页条目（Brin & Stuck 实测：命题4.2.2 排到 定理4.2.1 前，
    引理9.5.3 排到 定理9.5.4 后，B 层整章报「顺序错乱」）。数字段为主键
    后，同页条目恢复真实阅读序；字母位（Vakil '7.2.A'）由次键消解。
    """
    return (tuple(int(x) for x in re.findall(r"\d+", str(k))), _nat_key(k))


def _section_of_key(key, ordinal, chapter_first=True, chapter_local=False,
                    chapter_scoped=False, sections_global=False):
    """从带类型的条目 key 推导其所属『章节号』（用于挂到 section 节点）。

    ``chapter_scoped``：章内计数器编号书（编著集如 Springer《Koopman Operator》，
    "Theorem 2.6" = 第 2 章第 6 个定理，**不是** §2.6 的条目——各标签编号贯穿
    全章）。此类书条目号末段与节号无对应关系，按数字派生节号必然错位
    （Example 2.6 印在第 71 页却被挂进 "§2.6 Conclusion"，B 层报乱序）。
    故直接返回 None，让条目走 ``_place`` 的页码就近归节。语义与
    ``chapter_local`` 相同，只是编号体例不同（后者节号 §N 每章重置）。

    ``chapter_local``：章内局部编号书（如 Karlin，节 `§N` 每章重置）。此类书
    条目编号（``Theorem 1.5`` 的末位 5）是「章内条目序标」而非「节号」，与
    `§N` 节号无对应关系，按数字派生节号必然错位。故直接返回 None，让条目走
    ``_place`` 的页码就近归节（忠实还原条目在哪一节页面上），而非错挂到某个
    数字巧合的节。

    返回 "C.S"（字符串）或 None（交由页码归并）。

    ``chapter_first``：EN 两级编号下，key 首数究竟是章还是节。
      * True（默认，英文两级 ORDINAL_TWO_LEVEL / 标签前置英文三级 ORDINAL_THREE_LEVEL）："Definition 6.1" = 第 6 章第 1 条，
        段号取 "C.S" = "6.1"。
      * False（节基书，如 Fraleigh："Definition 8.1" = §8 第 1 条，首数即『节号』）：
        段号取 "S" = "8"。

    注（Bug #20）：EN 两级编号下，key 形如 "Example 2.7" 会被派生为章节号 "2.7"。
    真实存在的小节（§2.1–§2.6）由条目与小结共同确立；而 Example 2.7/2.8/2.9 这类
    「仅示例、无对应小结标题」的派生号属于幽灵小节，由 ``build_chapter`` 借助章节
    小结 markdown 的二级标题（``## §N.M``）统一剔除，而非在此短路返回 None——因为
    短路会让所有 EN 条目失去派生小节能力，致使 scan_skeleton 两级模式本就漏扫的
    真实小节（如 §2.1–§2.6）也一并丢失（回归）。故此处按通用规则返回段号。
    """
    if chapter_scoped or chapter_local:
        return None
    if ordinal == ORDINAL_TWO_LEVEL:
        # 中文两级：key 形如 "定义1.1"（标签自有计数器），无章节分量 -> 页码归并
        return None
    if chapter_local:
        # 章内局部书：条目序标与节号解耦，不派生节号（见函数 docstring）。
        return None
    k = _STRIP_LABEL.sub("", key)
    k = _STRIP_LABEL_CN.sub("", k)
    # 🔴 字母前缀附录编号（Weibel "A.1.4" → §A.1）：先判字母首分量，digit-first /
    # CN 书键（"1.2-3" / "定义1.2-1"）首字符非字母，自然落回原逻辑，零回归。
    _lm = re.match(r'^([A-Za-z])\s*[.\-]\s*(\d+)', k)
    if _lm:
        return f"{_lm.group(1).upper()}.{_lm.group(2)}"
    nums = re.findall(r"\d+", k)
    if len(nums) >= 2:
        if chapter_first:
            # 章基两级：首数是章，段号 "C.S"
            return f"{nums[0]}.{nums[1]}"
        # 节基两级（如 Fraleigh）：首数是节，段号取 "S"
        return nums[0]
    if len(nums) == 1:
        # 🔴 全局单号节书（sections_global，如 Arnold《常微分方程》：§N 全书连续
        # 单序标，条目 Theorem/Corollary/Example 用**章级全局**计数器）：条目裸号
        # "8" 是「第 8 个推论」这一条目序标，绝非节号——只是恰好撞上真实存在的
        # §8（§7 的 Corollary 8..12 会被错挂进 §8..§12，再经 min(child_start) 把
        # 各节页区间拖成 105/106/107 乱桩，B/Q/E 三层连带崩）。故此类书单分量
        # key 一律返回 None，交由 `_place` 的 (页码, y) 就近归节；多分量 key
        # （len>=2）走原逻辑，其余书零回归。
        if sections_global:
            return None
        return nums[0]
    return None


def _section_of_exer(num):
    """练习序标（如 "1.2.A" / "1.2" / "1.A" / "A.4-1"）推导章节号；不足两级归章级。"""
    # 🔴 字母前缀附录练习（Weibel "Exercise A.4.1" → key "A.4-1" → §A.4）
    _lm = re.match(r'^([A-Za-z])\s*[.\-]\s*(\d+)', num or "")
    if _lm:
        return f"{_lm.group(1).upper()}.{_lm.group(2)}"
    nums = re.findall(r"\d+", num)
    if len(nums) >= 2:
        return f"{nums[0]}.{nums[1]}"
    return None


_NUM_KEY_RE = re.compile(r'^[\dA-Z]+(?:\.[\dA-Z]+)+$')


def _numbered_heading_y(ext, key, page, page_dir=None):
    """编号小节头在自身页上的 y：块文本以节号开头（含 OCR 粘连变体）才算命中。

    2026-08-29 Koopman 书实测：仅按标题词搜（_find_title_pos）会把上一节折行
    标题的尾巴（§1.2.1 "…Discrete-Time and" / 次行 "Continuous-Time Systems"）
    误当 §1.2.1.2 的节头（y=199 vs 真值 1490），锚点提前吞掉整节内容块。
    编号锚定：`1.2.1.2 Continuous-Time…` / 粘连 `1.2.1.2Continuous…` 两种形态。
    找不到返回 None（调用方回退标题词搜索）。attach_content 同页锚点/排序
    复用本函数（attach_content 以 `_bs._numbered_heading_y` 引用）。
    """
    if not _NUM_KEY_RE.match(str(key)):
        return None
    pat = re.compile(
        r'^[\*§8Ss$]?\s*' + re.escape(str(key))
        + r'(?:[.:\uff1a\s\u00a0]+(?=[A-Za-z\u4e00-\u9fff])|(?=[A-Za-z\u4e00-\u9fff])|(?![\dA-Za-z\u4e00-\u9fff]))')
    _dir = page_dir or ext
    fp = os.path.join(_dir, 'page_%03d.json' % int(page))
    if not os.path.exists(fp):
        return None
    try:
        d = scan_skeleton.PageJson.load(fp).data
    except Exception:
        return None
    ys = []
    for b in d.get("text", []) if isinstance(d, dict) else []:
        if not isinstance(b, dict):
            continue
        s = (b.get("text") or "").strip()
        if not s:
            continue
        for ln in s.split("\n"):
            if pat.match(ln.strip()):
                poly = b.get("poly") or []
                ys.append(poly[1] if len(poly) >= 8 else 0)
                break
    return min(ys) if ys else None


def _find_title_pos(ext, title, start, end, page_dir=None):
    """无序号标小节：在章节 OCR 区间 [start, end] 内查找标题块，返回 ``(page, y)``。

    y 为命中块的 poly 顶边（同页多个命中取最小 y），供「同页条目 vs 节头」
    的先后判定（_place 的字典序 (page, y) 归并）；找不到返回 None。

    三段式匹配（2026-08-24 Evans SDE 案例，增量无回归）：
      Pass 1a —— 锚定体例头（大小写敏感）。存储标题两种形态：
        * 字母节头 ``X. TITLE``（原书印 ``A. BASIC DEFINITIONS``）→ 锚
          ``^X[.:．]?\\s*TITLE``；
        * 大写 run-in 主题头 ``TITLE``（原书正文内嵌 ``RANDOM VARIABLES. We …``）
          → 锚 ``^TITLE``。
        原书章首自带 mini-TOC（title-case 列出全部小节）而正文节头为 ALL-CAPS
        的书（Evans SDE 实测），旧的小写包含匹配会让所有小节都命中 TOC 页；
        正文还有与节名同词的前置散文/子块标题（如 ``EXAMPLES OF LINEAR …``
        先于 ``D. LINEAR …``），包含匹配同样误命中。
      Pass 1b —— 大小写敏感包含：保留给正文头不带上述形态的书。
      Pass 2 —— 旧行为（lowercase 包含 / 前缀相等）：任何书在 Pass 1 无命中时
        结果与改动前完全一致（零回归）。
    """
    t_raw = (title or "").strip()
    if not t_raw:
        return None
    t_norm = t_raw.lower()
    m0 = re.match(r'^([A-Z])\.\s+(.*)$', t_raw)
    if m0:
        anchor_re = re.compile(r'^' + m0.group(1) + r'[.:．]?\s*' + re.escape(m0.group(2)))
    else:
        anchor_re = re.compile(r'^' + re.escape(t_raw))
    # --- Pass 1a: anchored, case-sensitive (page, min-y) ---
    _dir = page_dir or ext
    for p in range(start, end + 1):
        fp = os.path.join(_dir, "page_%03d.json" % p)
        if not os.path.exists(fp):
            continue
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        ys = []
        for b in d.get("text", []):
            if not isinstance(b, dict):
                continue
            s = blk_text(b).strip()
            if s and anchor_re.match(s):
                poly = b.get("poly") or []
                ys.append(poly[1] if len(poly) >= 8 else 0)
        if ys:
            return (p, min(ys))
    # --- Pass 1b: exact-case containment ---
    for p in range(start, end + 1):
        fp = os.path.join(_dir, "page_%03d.json" % p)
        if not os.path.exists(fp):
            continue
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        for b in d.get("text", []):
            if not isinstance(b, dict):
                continue
            s_raw = blk_text(b).strip()
            if t_raw in s_raw:
                poly = b.get("poly") or []
                return (p, poly[1] if len(poly) >= 8 else 0)
    # --- Pass 2: legacy case-insensitive (y=0) ---
    for p in range(start, end + 1):
        fp = os.path.join(_dir, "page_%03d.json" % p)
        if not os.path.exists(fp):
            continue
        try:
            d = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        for b in d.get("text", []):
            if not isinstance(b, dict):
                continue
            s = blk_text(b).strip().lower()
            if not s:
                continue
            head = s.split(". ")[0].strip()
            if t_norm == head or t_norm in s:
                return (p, 0)
    return None


# 多册书（上下册）分册解析：单一真源在 lib.page_dir（structure / verify / extract
# 共用）。契约顶层 `page_dir` 字段由 build_chapter 经 rel_page_dir 写入，下游按
# 章还原目录，避免歧义读页（各册页码重复，读 extract_dir 会静默命中某一册）。
from lib.page_dir import (rel_page_dir as _rel_page_dir,
                          resolve_page_dir as _resolve_page_dir)


# OCR 数字↔形近字母映射（与 extract_items_en.OCR_DIGIT 同源，反向：数字→可混淆字母集）。
# 用于 _item_pos 的「OCR 容错条头」兜底：抽取器已能把 "Corollary 1l" 归一为
# 序标 11（key 携带规范号），但 _item_pos 用 re.escape 的字面号去锚定源页块文本
# 时，"corollary 11" 匹配不到印成 "Corollary 1l" 的真条头 → y=-1 → 同页误排最前
# （Arnold《ODE》ch3 §27 实测：推论11 '1l' 排到 9、10 之前，B 层顺序错乱 BLOCKING）。
_OCR_LETTERS_FOR_DIGIT = {
    '0': 'OoQD', '1': 'Ili', '2': 'Zz', '3': 'Ee', '4': '',
    '5': 'Ss', '6': 'G', '7': 'Tt', '8': 'Bb', '9': 'g',
}


def _ocr_tolerant_head_re(k):
    """把条头 key 变体（如 "corollary 11"）编译成 OCR 容错条头正则。

    数字段逐位展开为 [该数字|其 OCR 形近字母] 字符类；大小写不敏感；保留
    「序标后不接数字」边界守卫（(?![\\d])），避免 "corollary 1" 误命中
    "corollary 11"。仅在严格头/包含匹配全部失配后作为最后兜底调用。"""
    if not k:
        return None
    out = []
    for ch in k:
        if ch.isdigit():
            cls = ch + _OCR_LETTERS_FOR_DIGIT.get(ch, '')
            out.append('[' + ''.join(sorted(set(cls))) + ']')
        else:
            out.append(re.escape(ch))
    try:
        return re.compile('^' + ''.join(out) + r'(?![\d])', re.IGNORECASE)
    except re.error:
        return None


def _item_pos(ext, it, page_dir=None):
    """编号项在源页上的 (page, y)：取其 key/片段首个匹配块的 poly 顶边。

    找不到时 y 取 -1（同页排序时排在任何节头之前——OCR 整块丢失的条目
    通常位于该页节头之前的阅读流里；跨节归并不受影响）。

    CN 规范键的 EN 别名重试（2026-08-29 Koopman 书实测）：契约 key 是 CN
    规范标签（"定义1.1"），EN 书源文印 "Definition 1.1"——直接 startswith
    永不命中 → y=-1 → attach 锚点错位、条目 0 内容块。此处把 CN 前缀译回
    EN 别名（Definition/Theorem/…）再试 startswith。"""
    p = it.get("page")
    if not p:
        return None
    _dir = page_dir or ext
    fp = os.path.join(_dir, "page_%03d.json" % p)
    if not os.path.exists(fp):
        return None
    try:
        d = json.load(open(fp, encoding="utf-8"))
    except Exception:
        return None
    key = (it.get("key") or "").strip().lower()
    snip = (it.get("text") or "").strip()
    # 契约 name 形如 "1.2-1 1.2.1 <正文>"（前两段为契约序标 + 书源序标，书源块里
    # 没有），或 "Definition 1.2.1 <正文>"。剥离前导数字序标段（最多两段）以保留
    # <正文> 供子串回退匹配——否则 "1.2-1 1.2.1" 前缀导致书源 "Definition 1.2.1
    # <正文>" 块永远匹配不到（Weibel《同调代数》实测：序标印在标签词之后，非行首）。
    snip_body = re.sub(r'^(?:[\dA-Z]+(?:[.\-][\dA-Z]+)*\s+){1,2}', '', snip)
    if not snip_body:
        snip_body = snip
    probe = re.sub(r"\s+", " ", snip_body[:48]).lower()
    key_variants = [key] if key else []
    m_cn = re.match(r'^([\u4e00-\u9fff]+)', key)
    if m_cn:
        from verify_config import _LABEL_CANON as _LC
        cn = m_cn.group(1)
        rest = key[m_cn.end():]
        # CN 键无分隔符（"定义1.1"）；EN 源文印 "Definition 1.1"（号前有空格）
        key_variants += [(en.lower() + ' ' + rest.lstrip('.')) for en, c in _LC.items() if c == cn]
        key_variants += [(en.lower() + rest) for en, c in _LC.items() if c == cn]
    # 三级点分 scheme（scheme three-level）：契约键用连字符（"1.2-1"），书源多印
    # 点分（"1.2.1"），反之亦然。追加对方分隔变体，否则 startswith 永不命中 →
    # y=-1 → _item_anchor 回退 (page, 0.0) → 同页多 item 内容全错归该页最后一个
    # item（Weibel《同调代数》实测 1.2-1/1.2-2、1.4-3/4/5 错位空心）。
    # 仅对「纯数字+分隔符」键追加反向变体，避免正文数学（如 "1-1=0"）被误当序标。
    if key:
        if '-' in key:
            _v = key.replace('-', '.')
            if _v not in key_variants:
                key_variants.append(_v)
        if '.' in key and re.match(r'^[\d.]+$', key):
            _v = key.replace('.', '-')
            if _v not in key_variants:
                key_variants.append(_v)
    # 裸头条目的 label 头变体（attach_content._item_anchor 传 node.type；构建期
    # 调用无 type 时缺省空串，行为不变）：印刷头仅 "<Label> <号>" 独占一行、
    # 无题文的条目（Casella & Berger p251 Theorem 5.3.8 实测），契约 name 为裸键
    # 时 startswith 永不命中 → y=-1；且同页存在 "(Theorem 5.3.8.) Similar..."
    # 散文引用行时 contain 会抢先命中引用行。追加 "<type> <号>" 头变体后真头
    # 可命中；配合下方「裸头优先」决胜排除同前缀引用行。
    _typ = str(it.get("type") or "").strip().lower()
    if (_typ and _typ not in ("uncat", "description", "proof")
            and key and re.match(r'^[\dA-Z]+[.\-][\dA-Z]', key)):
        for _v in (_typ + ' ' + key.replace('-', '.'),
                   _typ + ' ' + key):
            if _v not in key_variants:
                key_variants.append(_v)
    ys_head, ys_head_bare, ys_contain = [], [], []
    for b in d.get("text", []):
        if not isinstance(b, dict):
            continue
        s = blk_text(b).strip()
        if not s:
            continue
        sl = re.sub(r"\s+", " ", s.lower())
        poly = b.get("poly") or []
        y = poly[1] if len(poly) >= 8 else 0
        # 边界感知：序标后必须跟非数字（空格/字母/标点），避免 "1.2.1" 误命中
        # "1.2.10" 等同前缀序标块（ch6 含 1.6-1…1.6-14）。
        _hit_bare = False
        if key_variants:
            for k in key_variants:
                if k and re.match(r'^' + re.escape(k) + r'(?!\d)', sl):
                    ys_head.append(y)
                    # 裸头判定：匹配号后仅剩标点/空白（印刷头独占一行）。
                    # 同页若有以此为前缀、后接散文的引用行（"(Theorem 5.3.8.)
                    # Similar..."），y 更小会被 min(y) 抢先——裸头必须优先。
                    if not sl[len(k):].strip(" .:：．，,;；)）-–—*"):
                        _hit_bare = True
                    break
        if _hit_bare:
            ys_head_bare.append(y)
        if probe and probe[:24] in sl:
            ys_contain.append(y)
        else:
            # 空格归一的去空格包含兜底（2026-09-15《高等代数学》实测）：OCR 粘连
            # 号（`推论2.4.33类…` 实为 2.4.3+「3类…」）使 head 的 (?!\d) 守卫
            # 拒配、普通 contain 又因契约名含空格而失配 → y=-1 误排最前（同节
            # 条目顺序错乱、B 层 BLOCKING）。去空格包含仅作 fallback 层追加，
            # 不动 head 语义与既有命中。
            _probe_ns = probe.replace(" ", "")
            if len(_probe_ns) >= 8 and _probe_ns[:24] in sl.replace(" ", ""):
                ys_contain.append(y)
    if ys_head_bare:
        return (p, min(ys_head_bare))
    if ys_head:
        return (p, min(ys_head))
    if ys_contain:
        return (p, min(ys_contain))
    # 最后兜底：OCR 数字↔形近字母容错条头（严格头/裸头/包含均未命中时才启用）。
    # 覆盖印刷序标被读成形近字母（"Corollary 1l"↔号 11）导致锚定失败、y=-1 误排
    # 最前的场景；仅追加匹配、不改动上面既有命中，零回归。
    _tol = [r for r in (_ocr_tolerant_head_re(k) for k in key_variants) if r]
    if _tol:
        ys_tol = []
        for b in d.get("text", []):
            if not isinstance(b, dict):
                continue
            s = blk_text(b).strip()
            if not s:
                continue
            if any(r.match(s) for r in _tol):
                poly = b.get("poly") or []
                ys_tol.append(poly[1] if len(poly) >= 8 else 0)
        if ys_tol:
            return (p, min(ys_tol))
    return (p, -1)


def _find_title_page(ext, title, start, end, page_dir=None):
    """无序号标小节：返回标题首次出现的页码（兼容旧签名）。

    实现委托给 :func:`_find_title_pos`（三段式锚定匹配，见其 docstring），
    仅丢弃 y 分量。``page_dir`` 见 :func:`_find_title_pos`（多册书须传分册目录）。"""
    pos = _find_title_pos(ext, title, start, end, page_dir=page_dir)
    if pos is None:
        return None
    return pos[0]


def _chapter_local_sections_from_markdown(ext, ch):
    """Chapter-local books (Karlin-style: sections reset per chapter, written as
    ``## §N`` in the md) — return the authoritative section list
    ``[(local_num_str, title), ...]`` parsed from the chapter's md
    ``## §N Title`` headers.  Source ``"N. Title"`` is ambiguous with numbered
    PROBLEMS and REFERENCES, so the md transcription (faithful to the book) is
    the single source of truth for the section contract (the D-layer later
    cross-checks these against the source)."""
    book_dir = os.path.dirname(ext.rstrip("/")) or ext
    cands = []
    # 小结 md 命名随章型：数字章 Chapter{N}_*.md / 第N章_*.md，
    # 附录章 Appendix{X}_*.md / 附录X_*.md（merge_units._final_md_name 同源）。
    _ord = chapter_ordinal(ch)
    if is_numbered_chapter(ch) and _ord:
        pats = (f"Chapter{_ord}_*.md", f"chapter{_ord}_*.md", f"第{_ord}章_*.md")
    elif _ord:
        pats = (f"Appendix{_ord}_*.md", f"appendix{_ord}_*.md", f"附录{_ord}_*.md")
    else:
        # 无编号附录：裸名 附录.md / Appendix.md（或带标题 附录_*.md）
        pats = ("附录.md", "附录_*.md", "Appendix.md", "appendix_*.md")
    for pat in pats:
        cands.extend(glob.glob(os.path.join(book_dir, pat)))
    out = []
    if not cands:
        return out
    sec_re = re.compile(r'^#{2}\s*§\s*(\d+)\s*(.*)$')
    for path in cands:
        try:
            with open(path, encoding="utf-8-sig") as fh:
                for line in fh:
                    m = sec_re.match(line.rstrip("\n"))
                    if m:
                        out.append((m.group(1), m.group(2).strip()))
        except OSError:
            continue
    return out


def _find_chapter_local_section_page(ext, ch, n, start, end, page_dir=None):
    """First source page where chapter-local section `n` appears as a "N. Title"
    heading (Karlin-style).  Gives chapter-local sections a real page so items
    place to the correct section by page proximity.  Returns ``start`` if not
    found; the first occurrence (not later running-header repeats) is the real
    heading, so the early return is correct."""
    from lib.regexlib import SEC_LOCAL
    _dir = page_dir or ext
    for p in range(start, end + 1):
        fp = os.path.join(_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        try:
            data = json.load(open(fp, encoding="utf-8"))
        except Exception:
            continue
        for b in data.get("text", []):
            txt = blk_text(b).strip()
            m = SEC_LOCAL.match(txt)
            if m and int(m.group(1)) == n:
                return p
    return start


def _recognized_sections(ext, ch, start, end, page_dir=None):
    """无序号标书（section_types 含 0）：读取「agent 校验识别」步骤产物
    ``_recognized_sections.json`` 中本章的小节标题清单，返回
    ``[(title, page, y, level), ...]``（按文档顺序），``(page, y)`` 为该标题块的
    锚定位置（用于排序与条目归并），``level`` = 标题层级（1=一级小节 / 2=节内
    二级子标题；字符串条目视为 level 1 向后兼容）。

    该清单由识别步骤（agent/LLM 读原书确认「真实无序号标」后给出权威小节列表）
    产出，是**唯一可靠**的无序号标小节来源——OCR 正则靠「≥2 段数字」判节，对
    无数字标题完全失明且易编造假小节（违反保真），故此处直接消费识别产物，
    不再走 scan_skeleton 的深度检测。文件缺失或本章无条目时返回 []。
    """
    fp = os.path.join(ext, "_recognized_sections.json")
    if not os.path.exists(fp):
        return []
    try:
        data = json.load(open(fp, encoding="utf-8"))
    except Exception:
        return []
    titles = data.get(str(ch)) or data.get(ch) or []
    out = []
    n = len(titles)
    for i, t in enumerate(titles):
        if isinstance(t, dict):
            title = str(t.get("title") or "")
            level = int(t.get("level") or 1)
            # 可选锚定页提示：同名短标题（如 Lee 的 "More Examples" 在章内
            # 多节出现）的子串匹配可能命中更晚页——提示页与命中页偏离过大时
            # 以提示页为准（agent 清单的文档序本身即权威）。
            hint_pg = t.get("page")
        else:
            title, level, hint_pg = str(t), 1, None
        pos = _find_title_pos(ext, title, start, end, page_dir=page_dir)
        if pos is not None and hint_pg is not None \
                and abs(int(pos[0]) - int(hint_pg)) > 3:
            pos = (int(hint_pg), 0)
        if pos is None:
            # OCR 漏识的标题（如被 PaddleOCR 吞掉的小节标题）：按文档索引在
            # [start, end] 线性插值保序，避免错排到章首（否则会破坏小节顺序
            # 与条目页码归并）。插值仅影响页排序，不编造内容。
            pg = (int(hint_pg) if hint_pg is not None else
                  (start if n <= 1 else round(start + (end - start) * i / (n - 1))))
            pos = (pg, 0)
        out.append((title, pos[0], pos[1], level))
    return out


def _real_subsections_from_markdown(ext, ch):
    """读取章节小结 markdown（``<book_dir>/Chapter{ch}_*.md``），返回其二级标题
    ``## §N.M`` 对应的小节号集合（如 ``{"2.1", "2.2", ...}``）；集合元素均为恰好
    两段数字（``\\d+\\.\\d+``），不含 ``2.3.1`` 这类子子节。

    返回语义（Bug #20 过滤用）：
      · 返回集合  -> 小结 markdown 存在且含二级小节标题，启用「派生小节校验」；
      · 返回 None  -> 无小结 markdown 或标题为空，不启用过滤，保持原行为
                      （兼容尚未产出小结、或路径命名不同的书，避免误删）。

    典型用法：EN 两级编号下，Example 2.7/2.8/2.9 会被错误派生为幽灵小节
    §2.7/§2.8/§2.9；而小结 markdown 的真实小节只有 §2.1–§2.6，据此剔除幽灵小节，
    使示例就近归并到正确的真实小节下。
    """
    book_dir = os.path.dirname(ext.rstrip("/")) or ext
    cands = []
    for pat in (f"Chapter{ch}_*.md", f"chapter{ch}_*.md"):
        cands.extend(glob.glob(os.path.join(book_dir, pat)))
    if is_numbered_chapter(ch):
        cands.extend(glob.glob(os.path.join(book_dir, f"第{ch}章_*.md")))
    else:
        # 附录/补篇章小结 md 命名同 merge_units._final_md_name
        # （Appendix{X}_*.md / 附录X_*.md；无编号附录 → 裸名 附录.md）
        _ord = chapter_ordinal(ch)
        if _ord:
            cands.extend(glob.glob(os.path.join(book_dir, f"Appendix{_ord}_*.md")))
            cands.extend(glob.glob(os.path.join(book_dir, f"附录{_ord}_*.md")))
        else:
            for _b in ("附录.md", "附录_*.md", "Appendix.md", "appendix_*.md"):
                cands.extend(glob.glob(os.path.join(book_dir, _b)))
    if not cands:
        return None
    nums = set()
    sec_re = re.compile(r'^#{2}\s+.*?(\d+\.\d+)(?:\.\d+)*')
    for path in cands:
        try:
            with open(path, encoding="utf-8-sig") as fh:
                for line in fh:
                    m = sec_re.match(line.rstrip("\n"))
                    if m and re.fullmatch(r'\d+\.\d+', m.group(1)):
                        nums.add(m.group(1))
        except OSError:
            continue
    return nums if nums else None


# ---------------------------------------------------------------------------
# 标题清洗：从抽取器 text snippet 抽取印刷标题（去掉 key / label 前缀，截断）
# ---------------------------------------------------------------------------
def _clean_title(text, key):
    if not text:
        return ""
    t = text.replace(key, "", 1).strip()
    t = _STRIP_LABEL.sub("", t)
    t = _STRIP_LABEL_CN.sub("", t)
    t = t.strip(" .:：．，,()（）\u00a0")
    if not t:
        return ""
    if len(t) > 90:
        cut = t[:90]
        sp = cut.rfind(" ")
        if sp > 40:
            cut = cut[:sp]
        t = cut.rstrip(" .:：．，,") + "\u2026"
    return t


def _node(key, ntype, name, page):
    node = {"key": key, "type": ntype, "name": name,
            "page_start": page, "page_end": page}
    return node


# ---------------------------------------------------------------------------
# 章节图归一（兼容 多套字段名：chapter/start/end 与 num/start_page/end_page）
# ---------------------------------------------------------------------------
def _build_rng(cm):
    def _aint(x):
        try:
            return int(x)
        except (TypeError, ValueError):
            return None

    if isinstance(cm, dict) and "chapters" in cm:
        chs = cm["chapters"]
    elif isinstance(cm, dict):
        out = {}
        for kk, cc in cm.items():
            s = cc.get("start", cc.get("start_page"))
            e = cc.get("end", cc.get("end_page"))
            n = _aint(kk)
            if n is None:
                # 非数字键（附录字母序标 A/B… 或无编号附录/补篇键 "appendix"）
                # 保留为字符串键，与 form-A 分支同处理；否则该章被静默丢弃。
                n = str(kk).strip() or None
            if n is None or s is None or e is None:
                continue
            out[n] = (int(s), int(e))
        return out
    else:
        chs = cm
    out = {}
    for cc in chs:
        raw_n = cc.get("num", cc.get("ch", cc.get("chapter", cc.get("n"))))
        n = _aint(raw_n)
        if n is None and raw_n is not None:
            # 字母章号（附录 A/B…）保留为字符串键，与 _chapter_sort_key 兼容
            sn = str(raw_n).strip()
            n = sn or None
        s = cc.get("start", cc.get("start_page"))
        e = cc.get("end", cc.get("end_page"))
        if n is None or s is None or e is None:
            continue
        out[n] = (int(s), int(e))
    return out


def _chapter_title(cm, ch):
    if isinstance(cm, dict) and "chapters" in cm:
        ent = next((c for c in cm["chapters"] if str(c.get("num", c.get("chapter", c.get("ch")))) == str(ch)), None)
    elif isinstance(cm, dict):
        ent = cm.get(str(ch)) or cm.get(ch)
    else:
        ent = next((c for c in cm if str(c.get("num", c.get("chapter", c.get("ch")))) == str(ch)), None)
    if not ent:
        return ""
    for kk in ("title", "name", "name_en"):
        if ent.get(kk):
            return str(ent[kk])
    return ""


def _exercise_block_pos(ext, ch, start, end, headings, page_dir=None):
    """Ross 体例章末习题块头位置：返回首个锚定标题行的 (page, y)，无则 None。

    与 scan_skeleton._exercise_headings_re 同一匹配器（单一真源），供
    build_chapter 把章末习题区内的条目从 ITEM 合同剔除（y 感知：同页条目须
    位于块头上方才保留）。"""
    rx = scan_skeleton._exercise_headings_re(headings)
    if rx is None:
        return None
    _dir = page_dir or ext
    for p in range(int(start), int(end) + 1):
        fp = os.path.join(_dir, 'page_%03d.json' % p)
        if not os.path.exists(fp):
            continue
        try:
            d = json.load(open(fp, encoding='utf-8'))
        except Exception:
            continue
        for b in d.get('text', []):
            if not isinstance(b, dict):
                continue
            poly = b.get('poly') or []
            y = float(poly[1]) if len(poly) >= 8 else None
            for ln in blk_text(b).split('\n'):
                ln = ln.rstrip('$').strip()
                if ln and rx.match(ln):
                    return (p, y)
    return None


def _exercise_region_start(ext, ch, start, end, page_dir=None):
    """Return the page where 'EXERCISES FOR CHAPTER <ch>' begins, else None.

    Used to exclude exercise-region pages from the ITEM contract so that
    exercise problems (e.g. Strogatz `3.1.1`) are not mistaken for chapter
    items (examples/theorems).  Case-insensitive, space-optional to survive
    OCR like `EXERCISESFORCHAPTER3`.
    """
    head = re.compile(r'EXERCISES\s*FOR\s*CHAPTER\s*(\d+)', re.IGNORECASE)
    pat = str(ch)
    _dir = page_dir or ext
    for p in range(start, end + 1):
        fp = os.path.join(_dir, 'page_%03d.json' % p)
        if not os.path.exists(fp):
            continue
        try:
            d = json.load(open(fp, encoding='utf-8'))
        except Exception:
            continue
        txt = " ".join(blk_text(b) if isinstance(b, dict) else str(b)
                       for b in d.get('text', []))
        m = head.search(txt)
        if m and m.group(1) == pat:
            return p
    return None


# ---------------------------------------------------------------------------
# 抽取器分派：build_structure 是抽取器的唯一调用方（data_provider 现已只读 JSON）。
# 生成分章契约后，verify 与 write-source 均消费该契约（BookStructure.load 聚合），不再重跑抽取器。
# ---------------------------------------------------------------------------
def _single_en_items(ext, start, end, book, sec_windows=None):
    """EN 单级编号书（ORDINAL_SINGLE + language=="en"，如 Evans PDE 2ed /
    Silverman《Friendly Introduction to Number Theory》：`Theorem 1` 单一数字）。

    键与 EN 两级分支同构：`_canon_label(label)+num`（"THEOREM 1" → "定理1"），
    使契约键标签词大小写稳定（OCR 原样大写会让 B 层 `_ENTRY_LABELS`
    大小写敏感解析失败）。单号无章/节位，不做跨章前向引用过滤。

    config_setting 规则5 增量扩展：config `ordinal` 各组 `name` 里 EN_LABELS
    没有的标签词（如 Rosen 的 Algorithm / Axiom 编号块）追加进抽取标签集；
    Figure/Table 是图管线管辖的图表注，uncat 是兜底标记，均不作为文本契约条目。
    """
    _non_text = {"uncat", "Figure", "Fig", "Table", "图", "表"}
    extra = []
    for _g in getattr(book, "ordinal", []) or []:
        for _nm in getattr(_g, "name", []) or []:
            if _nm and _nm not in _non_text and _nm not in extra:
                extra.append(_nm)
    # 🔴 按节重置计数器（config ordinal 组 scope==3，Rosen 实测）：把 scope==3
    # 组的标签词 + 节窗口下传抽取器，令「同标签章级单调守卫 / 续行去重守卫」
    # 按节分桶——否则 §1.2 起重号的 Example 1 被 §1.1 的 Example 16 压掉
    # （ch1 实测 138 例只抽 28）。无 scope==3 组 / 无窗口时行为逐字不变。
    _rst_labels = []
    if sec_windows and not book.section_scoped:
        for _g in getattr(book, "ordinal", []) or []:
            if getattr(_g, "scope", None) == 3:
                for _nm in getattr(_g, "name", []) or []:
                    if _nm and _nm.lower() not in _rst_labels:
                        _rst_labels.append(_nm.lower())
    items = extract_items_en(ext, start, end, want_examples=True,
                             section_scoped=book.section_scoped, single=True,
                             extra_labels=extra,
                             restart_per_section=(
                                 set(_rst_labels), list(sec_windows or []))
                             if _rst_labels else None)
    kept = []
    for it in items:
        lab, _, num = it["key"].partition(" ")
        it = dict(it)
        it["key"] = f"{_canon_label(lab)}{num}"
        kept.append(it)
    return kept


# ---------------------------------------------------------------------------
# 🔴 EN 三级「数字前置」条头探针（Kreyszig 实测 2026-09 根治）。
# ORDINAL_THREE_LEVEL + language=en 此前硬分派到 en3 抽取器（标签前置
# "Definition 1.1.1"），而条头印成「编号在前 + 标签在后」（"1.1-1 Definition
# (Metric space, metric)."）的书会整章近乎漏抽（Kreyszig ch1 仅抓到 3/50）。
# 通用三级抽取器 extract_items 明确支持英文 "N.S-N Lemma" 形态（其源码注释
# 即以 Kreyszig 为范本），但从不被该分派放行。探针按块首统计本章页面两种
# 条头形态的出现次数，数字前置占绝对优势（≥5 且严格多于标签前置）时改走
# 通用抽取器；标签前置书（Strogatz / Lasota & Mackey）探针必然失配，零回归。
_NF_HEAD_RE = re.compile(
    r'^\s*\d{1,2}[.\-–]\d{1,2}[.\-–]\d{1,3}\s+(?:\([^)]{0,60}\)\s*)?'
    r'(?:Definition|Theorem|Lemma|Corollary|Proposition|Example|Remark)'
    r'\b', re.IGNORECASE)
_LF_HEAD_RE = re.compile(
    r'^\s*(?:Definition|Theorem|Lemma|Corollary|Proposition|Example|Remark)'
    r'\s+\d{1,2}[.\-–]\d{1,2}[.\-–]\d{1,3}\b', re.IGNORECASE)


# 条头形态是**全书统一排版惯例**，探针按整书页面判定并缓存——逐章判定会让
# 条目稀疏章（Kreyszig ch11 全书仅 4 条且全部数字前置）达不到阈值而漏章。
_NF_PROBE_CACHE: dict = {}


def _three_level_en_number_first(_dir, start=None, end=None):
    """True iff this BOOK's headings are predominantly NUMBER-FIRST
    (`C.S-N Label`) rather than label-first (`Label C.S.N`).  Scans ALL
    page_*.json in _dir once (memoized per dir)."""
    key = os.path.abspath(_dir)
    cached = _NF_PROBE_CACHE.get(key)
    if cached is not None:
        return cached
    nf = lf = 0
    try:
        names = sorted(os.listdir(_dir))
    except OSError:
        return False
    for name in names:
        if not (name.startswith("page_") and name.endswith(".json")):
            continue
        fp = os.path.join(_dir, name)
        try:
            d = scan_skeleton.PageJson.load(fp).data
        except Exception:
            continue
        for t in d.get('text', []) or []:
            txt = (t.get('text') or '')
            for ln in txt.split('\n'):
                if _NF_HEAD_RE.match(ln):
                    nf += 1
                elif _LF_HEAD_RE.match(ln):
                    lf += 1
    verdict = nf >= 5 and nf > lf
    _NF_PROBE_CACHE[key] = verdict
    return verdict


# 数字前置书的抽取会同时抓到「真条头」和「同编号交叉引用」（OCR 断行使
# "(see 1.2-" + "3 in the next section" 之类引用落在行首）。真条头判据：
# 编号几乎在块首、其后不接 ". , ; )"（引用尾）、首词不是介/连/代词
# （"and|in|below…" 引用续句；真标题可小写如 "n-tuples"，故只列功能词）。
# 仅用于**同键去重**择优——唯一键一律保留（判据错了也不丢内容，B 层缺号
# 闸与步骤 5 人工审阅兜底）。Kreyszig 全书实测：head 键集与 2026-08 审计
# 过的旧契约键集逐章相等。
_NF_NUM_RE = re.compile(r'\d{1,2}[.\-–]\d{1,2}[.\-–]\d{1,3}')
_NF_FUNC_WORDS = {
    'and', 'or', 'the', 'of', 'to', 'in', 'is', 'as', 'by', 'we', 'it', 'so',
    'for', 'be', 'see', 'say', 'says', 'shown', 'shows', 'imply', 'implies',
    'that', 'this', 'these', 'those', 'with', 'follows', 'hold', 'holds',
    'below', 'above', 'used', 'use', 'using', 'given', 'where', 'when',
    'which', 'from', 'can', 'could', 'may', 'must', 'are', 'was', 'were',
    'has', 'have', 'if', 'then', 'but', 'not', 'its', 'their', 'there',
}


def _nf_heading_like(it):
    t = (it.get('text') or '')
    m = _NF_NUM_RE.search(t)
    if not m or m.start() > 2:
        return False
    after = t[m.end():]
    if after[:1] in ('.', ',', ';', ')', '）'):
        return False
    # lettered/numbered reference tail "(a)"/"(c)"/"(2)"（"8.1-4(a) and a sum
    # of compact operators…" 实测）；真条头的括号是标题 "(Title)"，首字符大写。
    if re.match(r'\(\s*[a-z0-9]', after):
        return False
    rest = after.lstrip()
    if not rest:
        return False
    # bare punctuation-tail references ("2.6-4?" / "1.2-3.)") — a printed
    # heading always carries a title sentence after the number.
    if len(re.findall(r'[A-Za-z]{2,}', rest)) < 2:
        return False
    w = re.match(r'[A-Za-z][A-Za-z-]*', rest)
    if w and rest[:1].islower():
        if w.group(0).lower().split('-')[0] in _NF_FUNC_WORDS:
            return False
    return True


def _nf_dedup_items(items):
    """Same-key collisions: keep the most heading-like occurrence (ties →
    longest text).  Unique keys are never dropped.  Output order follows the
    CHOSEN occurrence's position, not the first-seen slot（Kreyszig 实测：
    4.6-8 的引用早于真头出现，若保留首槽会把真条目排到 4.6-7 之前）."""
    def rank(x):
        return (1 if _nf_heading_like(x) else 0, len(x.get('text') or ''))
    best = {}
    for idx, it in enumerate(items):
        k = it['key']
        if k not in best or rank(it) > rank(best[k][1]):
            best[k] = (idx, it)
    return [it for _, it in sorted(best.values(), key=lambda t: t[0])]


def _extract_items(ext, ch, start, end, book, manual=None, page_dir=None,
                   sec_windows=None):
    primary = book.primary_type
    _dir = page_dir or ext
    if getattr(book, "gm_bare_numbered", False):
        # Gelfand-Manin《Methods of Homological Algebra》（config_setting 规则5
        # 增量扩展）：条目是「节内共享一条计数器的裸整数头、数字在前」（"3. Theorem"
        # / "5. Definition." / 描述子块也占同一槽），交叉引用写作 Chapter.Section.N。
        # 既有抽取器无一覆盖（无标签词可锚、节局部重排），专用抽取器按印刷 TOC 节锚
        # + 本节内单调计数器走查，产出标准三级键 "C.S-N" → 下游 B/D/Q/key_parse 全兼容。
        return extract_items_gm(_dir, ch, start, end)
    if primary == ORDINAL_HUM:
        # Humphreys GTM 9（config_setting 规则5 增量扩展）：条目头只印裸标签
        # （"Lemma."）或节内字母号（"Lemma A"），编号由所在小节隐式给出。
        # 专用抽取器跟踪当前小节，产出唯一化键 "Lemma §10.2B" / "Lemma §7.2"
        # （注入 § 记号使其不可被 B 层数字解析——引用号继承小节网格、天然稀疏，
        # 可解析会误报海量假断号；与 Ross 字母项同走优雅跳过路径）。
        return extract_items_hum(_dir, start, end)
    if primary == ORDINAL_SINGLE:
        # CN 单级编号书（如李庆扬《数值分析》第5版：定理1 / 定义3 / 例12 /
        # 算法2 / 性质4——「标签+单一数字」、章内连续或节内重置）：既有抽取器
        # 均不覆盖（extract_items 只认多级号，EN 单级抽取器无中文标签词），
        # 按 config_setting 规则5 走增量扩展的中文单级抽取器。
        if getattr(book, "language", "cn") == "cn":
            return extract_items_cn_single(_dir, start, end, groups=book.ordinal,
                                            manual_overrides=manual)
        return _single_en_items(_dir, start, end, book, sec_windows=sec_windows)
    if primary == ORDINAL_TWO_LEVEL and getattr(book, "language", None) == "en":
        # EN two-level books (former ORDINAL_EN=4, now folded into type 2): label-first /
        # number-first / chapter-wide single-digit forms, all extracted by extract_items_en.
        # Labels not in the base EN_LABELS set (e.g. Lee 2e's Exercise / Problem) are appended
        # to the extractor's label set; Figure/Table/uncat are figure-pipeline concerns, not
        # text-contract items -- strip trailing dots so "Fig." captions are not fake items.
        _non_text = {"uncat", "Figure", "Fig", "Fig.", "Table", "图", "表"}
        _non_text_stripped = {t.rstrip(".") for t in _non_text}
        extra = []
        for _g in getattr(book, "ordinal", []) or []:
            for _nm in getattr(_g, "name", []) or []:
                if _nm and _nm not in extra and \
                        _nm.rstrip(".") not in _non_text_stripped:
                    extra.append(_nm)
        items = extract_items_en(_dir, start, end, want_examples=True,
                                 section_scoped=book.section_scoped,
                                 extra_labels=extra)
        kept = []
        for it in items:
            lab, _, num = it["key"].partition(" ")
            parts = num.split(".")
            if book.chapter_first and len(parts) >= 2 and parts[0].isdigit() and int(parts[0]) != ch:
                continue
            it = dict(it)
            it["key"] = f"{_canon_label(lab)}{num}"
            kept.append(it)
        # ---- Merge manual overrides (OCR-drop agent recovery) ----
        if manual:
            existing = {it["key"]: idx for idx, it in enumerate(kept)}
            for mo in manual:
                k = f"{_canon_label(mo.get('label', ''))}{mo.get('key', '')}"
                item = {"key": k, "page": mo.get("page"),
                        "label": mo.get("label", ""), "text": mo.get("text", ""),
                        "agent_recovered": True}
                if k in existing:
                    kept[existing[k]] = item
                else:
                    kept.append(item)
            kept.sort(key=lambda x: ((x.get("page") or 0), _nat_key(x["key"])))
        return kept

    if primary == ORDINAL_THREE_LEVEL and getattr(book, "language", None) == "en" \
            and _three_level_en_number_first(_dir, start, end):
        # Kreyszig 式「数字前置」三级英文书（探针判定，见上）：en3 标签前置
        # 抽取器整章漏抽，改走通用三级抽取器（其交叉引用守卫明确按
        # "N.S-N Lemma" 英文形态设计）。键为裸号 "C.S-N"，与 en3 分支的
        # normkey 输出同形，下游 B/D/Q 无感。同键的真条头/交叉引用碰撞由
        # _nf_dedup_items 择一（唯一键不丢）。
        items, _, _ = extract_items(_dir, ch, start, end, manual_overrides=manual,
                                    cfg=book)
        return _nf_dedup_items(items)

    if (primary == ORDINAL_THREE_LEVEL and getattr(book, "language", None) == "en") \
            or primary in (ORDINAL_APP, ORDINAL_APP2):
        # EN three-level, label-first (e.g. Strogatz, Lasota & Mackey).  The
        # generic three-level extractor is CN-oriented and captures unlabeled
        # exercise numbers (`3.1.1`) as items; route to the label-first EN3
        # extractor, which requires an Example/Definition label and so naturally
        # excludes exercises.  ORDINAL_APP（附录字母章位，type 13）的条目印成
        # `Definition A.1.1` / 裸 `A.1.5`（Weibel Appendix A）；ORDINAL_APP2
        # （type 14，两段）印成 `Theorem B.2` / 裸 `B.4`（Lee ISM 附录）——
        # 同属 label-first 字母章位形态，由 extract_items_en3 的附录正则
        # （EN3_APP_RE / EN3_APP_BARE_*）覆盖——键仍走 normkey 裸号（"A.1-1" /
        # "B.2"），类型由节点 type 承载。
        # KEY FORMAT (root-cause fix, 2026-08-19): the book's primary_type is
        # ORDINAL_THREE_LEVEL (NOT ORDINAL_EN3), so the completeness checker's
        # _canon_key parses its keys as pure-numeric `C.S-N` tuples — a label
        # word is NOT allowed.  Embedding the CN canon label (`例`) into the key
        # (as the true ORDINAL_EN3 branch does) makes
        # _canon_key(THREE_LEVEL, "例2.2.1") return None, silently dropping the
        # item from the contract (contract_items=0 -> everything "missing", fake
        # block).  The item TYPE is carried by the node `type` field (derived
        # from `it["label"]` via _type_of), so we keep the key bare-numeric and
        # let the checker's _composite_key re-attach the type.  normkey:
        # "2.2.1" -> "2.2-1" (matches scan_raw_items' three-level raw keys).
        items = extract_items_en3(_dir, ch, start, end, want_examples=True)
        kept = []
        for it in items:
            _lab, _, num = it["key"].partition(" ")
            parts = num.split(".")
            if book.chapter_first and len(parts) >= 2 and parts[0].isdigit() and int(parts[0]) != ch:
                continue
            it = dict(it)
            it["key"] = normkey(num)
            kept.append(it)
        # ---- Merge manual overrides（OCR 漏识真实条目的 agent 回填通道）----
        # 与 (ORDINAL_EN, ORDINAL_EN3) 分支的合并同构，但键保持本分支的裸号
        # normkey 形（"6.3.7" → "6.3-7"）：missing_label_policy 的约定是序列洞
        # 经 manual_overrides 恢复；此前本分支不消费 manual，重建契约时手工
        # 恢复的条目会被静默丢弃、洞复现（Weibel ch6/ch10 实测）。
        if manual:
            existing = {it["key"]: idx for idx, it in enumerate(kept)}
            for mo in manual:
                mk = normkey(str(mo.get("key", "")))
                if not mk:
                    continue
                item = {"key": mk, "page": mo.get("page"),
                        "label": mo.get("label", ""), "text": mo.get("text", ""),
                        "agent_recovered": True}
                if mk in existing:
                    kept[existing[mk]] = item
                else:
                    kept.append(item)
            kept.sort(key=lambda x: ((x.get("page") or 0), _nat_key(x["key"])))
        return kept
    if primary == ORDINAL_VAKIL:
        items, _, _ = extract_items_vakil(_dir, ch, start, end, manual_overrides=manual)
        return items
    # three_level / two_level 全部走 extract_items（内部按 ordinal 选路）
    items, _, _ = extract_items(_dir, ch, start, end, manual_overrides=manual, cfg=book)
    return items


# ---------------------------------------------------------------------------
# 单章结构构建
# ---------------------------------------------------------------------------
def _has_foreign_sibling(page, y, foreign, tol=80.0):
    """text 候选是否与**异号**裸节号块同页同行带（= 那是那个号的标题）。

    OCR 常把一个节头切成「裸号块 + 标题块」（Rosen p211: `2.6.1` / `Introduction`），
    于是通用词标题（Introduction/Summary…）会被任意一节的同名标题撞上。裸号与
    标题两块 y 相差仅几磅，用行带容差判相邻。tol 内没有异号裸块 = 真·无号节头
    （Rosen ch11 场景），候选保留。
    """
    if y is None:
        return False
    for fp, fy, _n in foreign:
        if fp == page and abs(float(fy) - float(y)) <= tol:
            return True
    return False


_TOC_LINE_GAP = 250.0   # 目录带内相邻行的最大行距；更大的空隙 = 目录结束


def _toc_band_bottom(ys, gap=_TOC_LINE_GAP):
    """章扉页「目录带」的下界 y（无命中返回 None）。

    从最上方一条节号首现命中起，沿目录行距连续向下延伸，遇到 >gap 的空隙即停
    ——正文区与目录之间隔着一整段引言散文，空隙远大于目录行距（Rosen p144：
    目录 385/431/481/529/610/693，正文节头 1635，间隙 942）。
    不能直接取「该页首现命中的最大 y」：只列 §N.M 的章目录里，§N.M.K 的**正文
    节头**就是它自己的首现命中，会把带界顶到自己头上（严格大于即失效）。
    """
    v = sorted(float(y) for y in (ys or []) if y is not None)
    if not v:
        return None
    bottom = v[0]
    for y in v[1:]:
        if y - bottom > gap:
            break
        bottom = y
    return bottom


def _opener_continuation_pages(first_hit, opener_pages, top_y=350.0):
    """返回应追加进 opener_pages 的「目录续排页」（扉页次页页顶）。

    成因（2026-08-26 Ross ch9 实测）：章扉页目录条目多，末尾一条（`9.4`）续排到
    次页页顶（y≈103），该页本身首现不足 _OPENER_K，逃过扉页判据 → 必须一并免疫。

    🔴 但只有**序标深度与扉页目录带一致**的续排行才认（2026-09-26 Rosen 8e ch1
    §1.1.2 实测缺陷）：扉页目录只列 §N.M（深度 2），次页页顶的 `1.1.2 Propositions`
    是深度 3 的**正文小节头**（Rosen p25 y=175，其下就是命题定义散文）。旧判据只看
    「全部首现贴顶 y<350」，把 p25 误判成目录页 → 回扫的 min_y 严格大于把该节头自己
    排除 → §1.1.2 锚到 p61（§1.3 习题区）；又因 1.1.1 < 1.1.2 序上不倒挂，
    `subsection_order_problems` 检测闸看不见这一形态。
    深度众数取扉页上全部首现命中（Ross：9.1/9.2/9.3 → 2；Rosen ch1 p24：
    1.1..1.8 八个 + 正文 1.1.1 → 众数仍是 2）。
    """
    extra = set()
    for op in list(opener_pages):
        rows = [r for r in first_hit.values()
                if r[0] == op + 1 and r[4] is not None]
        if not rows or not all(float(r[4]) < top_y for r in rows):
            continue
        op_depths = [len(str(r[2]).split(".")) for r in first_hit.values()
                     if r[0] == op]
        if not op_depths:
            continue
        dom = max(set(op_depths), key=op_depths.count)
        if {len(str(r[2]).split(".")) for r in rows} <= {dom}:
            extra.add(op + 1)
    return extra


def _hit_below_toc_band(y, band_bottom):
    """章首目录页上的 SEC 命中是否**已在目录带之下**（= 它就是正文节头）。

    目录只列 §N.M 的书（Rosen 8e）里 §N.M.K 的首现命中是真节头，回扫反而会
    撞上别的小节的同号/同名行；band_bottom = 该页全部首现命中的最大 y。
    等于带底的行按「目录行本身」处理（保守回扫，与旧行为一致）。
    """
    return (y is not None and band_bottom is not None
            and float(y) > float(band_bottom))


def _find_numbered_heading_page(ext, num, lo, hi, min_y=None, page_dir=None,
                                title_text=None):
    """在页码 [lo, hi] 内找首个「以节号 num 开头的标题行」所在页。

    用于章首目录页免疫的回扫：章扉页目录把节号的 SEC 首现页污染成章首页时，
    回扫正文节头（如 `2.1. TRANSPORT EQUIATION` / `2.1 Transport
    equation`）。找不到返回 None（调用方退回原首现页，不比旧行为差）。

    2026-08-26 Ross 体例实测两处误拒修正：
      * OCR 粘连形态 `3.3Bayes'sFormula`（编号与标题间无空格）——补 glue 变体
        （编号后直接跟字母、且不接续数字，"3.1" 不会误吞 "3.11"）；
      * 标题含括号的真节头（`3.5 P(|F) Is a Probability`）——旧全局括号禁令
        整行一票否决，改只要求分隔符后是字母（标题本体），括号不再否决。
        首匹配胜出且自章首向后扫描，习题/解答行的同号行天然排在真节头之后，
        不构成误报源。
      * 🔴 min_y：真节头可能与目录同页（ch5 扉页即 §5.1 起始页）——此时 lo 页
        上只接受块顶 y 严格大于污染行（目录命中）的匹配，否则回扫永远跳过
        真节头所在的首章页、错挂到后文习题/解答行的同号行上。

    2026-09-25 Rosen 体例两处失明修正：
      * 🔴 **页眉（running head）一票否决**：正文节头若被 OCR 掉号（ch11
        "Introduction to Trees" 无 11.1）或裸号成块（ch10 扉页 blk "10.1"），
        回扫会命中后续各页**页顶印刷页眉** `11.1 Introduction to Trees 783`
        → 节锚点晚 1~2 页，章首的定义/定理/例整批漂到 'file' 窗前。判据：
        去掉行尾页码后的同一文本在扫描区间内出现于 ≥2 个不同页 = 页眉，弃。
      * **裸号行可作节头**：OCR 常把节头切成「纯 `N.M`」一块 + 标题另块
        （ch10 p696 y=1197 `10.1`）。标题形态候选全灭时才接受裸号候选，
        且同样受页眉禁令与 min_y 约束。
      * 🔴 **无号正文节头（`title_text`）**：Rosen ch11 的 §11.2/11.4/11.5
        正文节头整块**没有印序号**（"Applications of Trees" 单块，序号被 OCR
        吞掉）→ 前两类候选全灭，只能拿扉页目录行的标题文本回匹配独立成块的
        标题行。三类候选优先级 title > bare > text，全无则返回 None 让调用方
        退回目录页（= 章首页，§N.1 场景正是它）。
      * 🔴 **text 候选的「异号兄弟」否决**（Rosen ch2 §2.1.1 实测）：OCR 把
        节头切成裸号块 + 标题块两半（p211 上是 `2.6.1` / `Introduction`），
        于是**别的小节**的标题块会被本节的通用词标题（`Introduction` 这类每节
        都有的词）撞上 → §2.1.1 锚到 p211，整节内容错挂、§2.1 窗口被拖到
        211 页。判据：text 候选同一页、同一行带（|Δy| ≤ 80）上存在**本节号
        以外**的裸节号块 = 它是那个号的标题，不是本节的 → 弃。真·无号节头
        （ch11 场景）旁边没有别的裸号块，零回归。
    """
    pat = re.compile(
        r'^[\*§8Ss$]?\s*' + re.escape(str(num)) + r'(?:[\.．:：]|[\s\u00a0]+)\s*[A-Za-z]')
    pat_glue = re.compile(r'^[\*§8Ss$]?\s*' + re.escape(str(num)) + r'(?=[A-Za-z])')
    pat_bare = re.compile(r'^[\*§]?\s*' + re.escape(str(num)) + r'\s*[\.．:：]?\s*$')
    pat_foreign_bare = re.compile(r'^[\*§]?\s*(\d+(?:[\.\-·]\d+)+)[\.\-·:：]?\s*$')
    _tq = (title_text or "").strip()
    pat_text = None
    if len(_tq) >= 4:
        pat_text = re.compile(r'^[\*§]?\s*' + re.escape(_tq)
                              + r'(?:[\s\u00a0][^\d]|$)', re.I)
    _dir = page_dir or ext
    cands = []          # (page, y, folio_stripped_text, kind)  kind: 'title' | 'bare' | 'text'
    foreign = []        # [(page, y, num)] 本节的**异号**裸节号块（text 候选兄弟判定）
    for p in range(int(lo), int(hi) + 1):
        fp = os.path.join(_dir, 'page_%03d.json' % p)
        if not os.path.exists(fp):
            continue
        try:
            d = scan_skeleton.PageJson.load(fp).data
        except Exception:
            continue
        blocks = d.get('text', []) if isinstance(d, dict) else []
        for b in blocks:
            if not isinstance(b, dict):
                continue
            poly = b.get('poly') or []
            try:
                by = float(poly[1]) if len(poly) >= 8 else None
            except Exception:
                by = None
            _blines = blk_text(b).split('\n')
            for ln in _blines:
                ln = ln.rstrip('$').strip()
                if not ln or len(ln) > 70 or ln.endswith((',', ';')):
                    continue
                _fo = pat_foreign_bare.match(ln)
                if _fo and _fo.group(1) != str(num):
                    foreign.append((p, by, _fo.group(1)))
                kind = None
                m = pat.match(ln) or pat_glue.match(ln)
                if m:
                    kind = 'title'
                elif pat_bare.match(ln) and len(_blines) == 1:
                    kind = 'bare'
                elif (pat_text is not None and len(_blines) == 1
                        # 目录页（lo）上的标题片段一律不算正文节头——TOC 条目常
                        # 换行成独立块（Rosen ch11 p804 blk21 "Spanning"）；
                        # §N.1 真在扉页起始时调用方 fallback 已给 lo 页。
                        and p > int(lo)
                        and pat_text.match(ln)
                        and not re.search(r'\d', ln)
                        and not ln.endswith('.')):
                    kind = 'text'
                if kind is None:
                    continue
                if (p == int(lo) and min_y is not None
                        and (by is None or by <= float(min_y))):
                    continue    # 目录命中本身 / 其上方的更早行，跳过
                if kind == 'title':
                    rest = ln[m.end():]
                    if len(re.findall(r'[A-Za-z\u00c0-\u017f\u4e00-\u9fff]', rest)) < 2:
                        continue
                cands.append((p, by, re.sub(r'\s+\d{1,4}$', '', ln), kind))
    if not cands:
        return None
    # 页眉禁令：同一文本（去行尾印刷页码后）出现在 ≥2 个不同页 → running head
    _pages_of = {}
    for _p, _y, _t, _k in cands:
        _pages_of.setdefault(_t, set()).add(_p)
    # 🔴 页眉首现页 = 本节锚点的**上界**（节头必然不晚于自己的页眉出现：
    # Rosen p816 页顶印 "11.2 Applications of Trees 793"，正文节头在同页
    # y=1401）。有了这条界，无号标题文本候选就不会在几十页外的散文里
    # 撞见同名单元块（ch11 §11.1 的 "Introduction" 若无上界会挂到 p831）。
    _hdr_pages = [c[0] for c in cands if len(_pages_of.get(c[2], ())) >= 2]
    _hbound = min(_hdr_pages) if _hdr_pages else None
    _kept = [c for c in cands
             if len(_pages_of.get(c[2], ())) < 2
             and (_hbound is None or c[0] <= _hbound)]
    if not _kept:
        return None
    for _kind in ('title', 'bare', 'text'):
        _pk = [c for c in _kept if c[3] == _kind]
        if _kind == 'text':
            _pk = [c for c in _pk if not _has_foreign_sibling(c[0], c[1], foreign)]
        if _pk:
            return _pk[0][0]
    return None


def _seq_filter_letter_blocks(cands):
    """裸字母子块候选的**序列过滤**（Arnold 体例专用）。

    真子块头在每节内按 A,B,C,… 连续出现；残余误报（数学变量起头的散文行如
    "B 之体积成正比"、"V.CU与V'…"）散落在页间、不守字母序。对候选做
    「去重(保留首现页) → 页序上从锚点字母起的最长严格递增子序列」即可保真：
    散点杂讯必被弃，真链即使中间漏检也保持连续。锚点取 'A'（本书体例每节/
    附录都从 A 起）；无 'A' 时退化为最小字母锚定。O(n²) DP，n≤30。
    """
    if not cands:
        return []
    seen = {}
    for pg, L, t in cands:
        if L not in seen:
            seen[L] = (pg, t)
    items = sorted(seen.items(), key=lambda kv: (kv[1][0], kv[0]))
    letters = [k for k, _ in items]
    n = len(items)
    if n == 1:
        keep = {letters[0]}
    else:
        idx = [ord(k) - 64 for k in letters]
        dp = [1] * n
        prev = [-1] * n
        best, best_i = 1, 0
        for i in range(n):
            for j in range(i):
                if idx[j] < idx[i] and dp[j] + 1 > dp[i]:
                    dp[i] = dp[j] + 1
                    prev[i] = j
            if dp[i] > best:
                best, best_i = dp[i], i
        chain = []
        i = best_i
        while i != -1:
            chain.append(letters[i])
            i = prev[i]
        chain.reverse()
        # 尾修剪：链尾若与前一元素字母距 >3（如真节止于 E 而杂讯 P 续尾），
        # 逐个丢弃——真实漏检造成的缺号在链中段不受影响。
        while len(chain) >= 2 and (ord(chain[-1]) - ord(chain[-2])) > 3:
            chain.pop()
        keep = set(chain)
        anchor = 'A' if 'A' in keep else min(keep)
        # 锚点必须入选：从锚点重走一遍链（若锚点不在最优链里则整表存疑，
        # 保守起见仅保留锚点到链尾的稳定段）
        if chain[0] != anchor:
            keep = set(chain[chain.index(anchor):]) if anchor in chain else keep
    return [(seen[k][0], k, seen[k][1]) for k in letters if k in keep]


def build_chapter(ext, ch, start, end, book, cm, manual=None):
    ordinal = book.primary_type
    language = book.language
    mode = scan_skeleton._mode_for_ordinal(ordinal, language)
    section_depths = getattr(book, 'section_depths', None) or None
    # Multi-volume: resolve correct page file directory for this chapter
    page_dir = _resolve_page_dir(ext, ch)

    # 1) skeleton 原始行
    if getattr(book, 'gm_bare_numbered', False):
        # Gelfand-Manin：节头 "§N. Title" 被 OCR 打成 $/S/8 或丢失，且与节内
        # descriptive 子块（"1. Main Definitions"）同形，通用扫描器彻底失明
        # （实测整章塌成 1 个 description 节点）。改由专用抽取器按印刷 TOC 节锚
        # + 本节内单调计数器识别真节界（sec_rows），条目走 _extract_items 的 gm 支。
        gm_sec_rows, _ = scan_gm(page_dir or ext, ch, start, end)
        rows = [(p, "SEC", num, title, y)
                for (p, _k, num, title, y) in gm_sec_rows]
    else:
        rows = scan_skeleton.scan(page_dir, ch, start, end, mode,
                                  section_depths=section_depths,
                                  chapter_first=book.chapter_first,
                                  exercise_headings=getattr(book, 'exercise_region_headings', None) or None,
                                  plain_sec_heads=(ordinal == ORDINAL_HUM),
                                  sections_global=getattr(book, 'sections_global', False),
                                  local_num_sec=getattr(book, 'numeric_local_sections', False))
    ex_rows = [r for r in rows if r[1] in ("EXER", "PROB")]

    # 1b) 裸字母子块头（SUB 行；仅 sections_global 书由 scan_skeleton 产生）。
    # 语境定级：附录章（无数字 § 节头）里字母头**就是节** → 升格为 SEC 行，
    # 键取最后一个点分分量（防 OCR 把别章 "§22．…" 误当父节的粘连）；正文章里
    # 字母头是 §N 内的子块 → 按父节聚合，稍后挂到 section 节点的 letter_subs
    # 元数据上（条目仍平铺 sub_sec，不引入第三层容器）。其余书无 SUB 行，零回归。
    _ch_name = _chapter_title(cm, ch)
    # 附录章判定与 ConfigLoader.is_appendix_chapter 同源（双信号）：章名含
    # Appendix/附录，或章键非数字（字母章位 A/B…）。仅认章名会在 chapter_map
    # 只填裸标题（如 Weibel 附录 name="Category Theory Language"，"Appendix A"
    # 序标由字母键承载）时漏判，附录字母节升格与 §N 免疫全部失效。
    _is_appendix = ('Appendix' in _ch_name) or ('附录' in _ch_name) \
        or (not str(ch)[:1].isdigit())
    letter_sub_blocks = {}   # parent(str) -> [(page, letter, title)]
    _appendix_letter_secs = []   # [(p, 'SEC', L, title)] 附录字母节升格行
    if any(r[1] == "SUB" for r in rows):
        sub_rows = [r for r in rows if r[1] == "SUB"]
        rows = [r for r in rows if r[1] != "SUB"]
        for row in sub_rows:
            p, _kind, num, title = row[0], row[1], row[2], row[3]
            parts = num.split('.')
            L = parts[-1]
            if not (len(L) == 1 and L.isalpha() and L.isupper()):
                continue  # 防御：SUB 键必为单个大写字母（挡 OCR 数字碎片）
            if _is_appendix:
                _appendix_letter_secs.append((p, L, title))
            else:
                letter_sub_blocks.setdefault(parts[0], []).append((p, L, title))
        # 序列过滤：正文按父节、附录按章，剔除不守字母序的散文/公式误报行
        for parent in list(letter_sub_blocks):
            kept = _seq_filter_letter_blocks(letter_sub_blocks[parent])
            if kept:
                letter_sub_blocks[parent] = [
                    (pg, L, t) for (pg, L, t) in kept]
                # 转成 {L: (page,title)} 供 4b 挂载
                letter_sub_blocks[parent] = {
                    L: (pg, t) for pg, L, t in kept}
            else:
                del letter_sub_blocks[parent]
        if _is_appendix:
            kept = _seq_filter_letter_blocks(_appendix_letter_secs)
            _appendix_letter_secs = [(pg, 'SEC', L, t, None) for pg, L, t in kept]

    if getattr(book, 'chapter_local_sections', False):
        # Chapter-local sections (Karlin-style "§1" that RESET per chapter) are
        # authoritative from the md `## §N` transcription — the source "N. Title"
        # form is ambiguous with numbered PROBLEMS and REFERENCES, so scanning
        # the OCR for them fabricates false sections.  We take the section list
        # from the faithfully-written md and resolve each section's source page
        # for item page-proximity placement.
        md_secs = _chapter_local_sections_from_markdown(ext, ch)
        # 🔴 md 行必须携带**真实源页**（下方章首目录页免疫逻辑按 row[0] 做
        # `_op + 1`，要求 int，并统计「同页首现节数」）：占位串 "md" 会在
        # ≥3 节的章上直接 TypeError，在 ≤2 节的章上把该占位当成目录污染页。
        # 用源 "N. Title" 首现页解析（与 1331 分支同一函数，幂等）。
        sec_rows = [(_find_chapter_local_section_page(ext, ch, int(n), start, end,
                                                      page_dir=page_dir),
                     "SEC", n, title)
                    for (n, title) in md_secs]
    else:
        sec_rows = [r for r in rows if r[1] == "SEC"]
        if _is_appendix:
            # 附录章的节只可能是字母头（升格 SUB 行）；数字 "§N" 行是公式/
            # 页眉碎片（OCR "$5．…"），不得混入契约。
            sec_rows = [r for r in sec_rows
                        if not str(r[2]).isdigit()]
    # 附录字母节升格行并入 SEC 去重管线（键=字母，与既有节同型参与后续流程）
    if _appendix_letter_secs:
        sec_rows = list(sec_rows) + _appendix_letter_secs

    # 2) skeleton SEC 去重（优先非空标题，保留最佳标题）。
    #    行统一 5 元组 (p,'SEC',num,title,y)：y 为节头块顶（scan 发射），md 派生
    #    /附录字母升格行 y=None。
    sec_rows = [r if len(r) == 5 else (r[0], r[1], r[2], r[3], None)
                for r in sec_rows]
    # 🔴 同号择优（Hilton & Stammbach ch2 实测）：行内公式残行 "8 F0=8 FG8 FεG'"
    # 可先于真节头命中 SEC_2，把 §8 的标题/起始页污染成公式碎片。含数学运算符
    # 的标题视为碎片，让位给纯词标题；同级取最早页（真节头先于其页眉复本）。
    _SEC_MATH_OP = re.compile(r'[=<>≤≥≠±×÷→←↔⇒∫∑√∂∇∈∋⊂⊃∪∩]')

    def _sec_title_mathy(t):
        return bool(_SEC_MATH_OP.search(str(t or '')))

    sec_best = {}
    for row in sec_rows:
        num, title = row[2], row[3]
        if num not in sec_best:
            sec_best[num] = row
            continue
        cur = sec_best[num]
        cur_mathy, new_mathy = _sec_title_mathy(cur[3]), _sec_title_mathy(title)
        if (cur_mathy and not new_mathy) or (cur[3] == "" and title != ""):
            sec_best[num] = row
    seen = set()
    dedup_sec = []
    for row in sec_rows:
        num = row[2]
        if num in seen:
            continue
        seen.add(num)
        dedup_sec.append(sec_best[num])

    # 2b) 章节骨架页图（skeleton SEC → sec_pages），须在条目抽取**之前**算好：
    # 单级按节重置书（config ordinal scope==3，如 Rosen「§1.1 例1..16 → §1.2
    # 例1..11」）要把节窗口喂给抽取器做「按节分桶」的守卫（否则章级单调守卫把
    # 每一节的起重编号都当陈旧交叉引用丢掉）。sec_pages/sec_titles/sec_pos 在
    # 下方 4) 派生小节管线继续原样使用，语义不变。
    sec_pages = {}   # num -> 最佳候选页（skeleton）
    sec_titles = {}  # num -> 标题
    sec_pos = {}     # num -> (page, y)；仅 sections_unnumbered 路径填充（y 感知归并）
    # 章首目录页免疫（2026-08-25 Evans 实测）：章扉页常印「本章小节目录」，SEC
    # 扫描把每个节号都「首现」在章首页 → 各节 sec_pages 全等于章首页，条目按页
    # 就近归节时全部错挂到最后一个真实节。判据：同一页上「首现」≥_OPENER_K 个
    # 不同节号 → 该页是章首目录页，其上的 SEC 命中不计入 sec_pages（取其后首个
    # 正文命中；若某节只有目录命中则退回原值——与旧行为一致，不比旧差）。
    _OPENER_K = 3
    _first_hit = {}
    for row in dedup_sec:
        _first_hit.setdefault(row[2], row)
    _page_first_cnt = {}
    for _num, _row in _first_hit.items():
        _p = _row[0]
        _page_first_cnt[_p] = _page_first_cnt.get(_p, 0) + 1
    _opener_pages = {p for p, c in _page_first_cnt.items() if c >= _OPENER_K}
    # 🔴 目录跨页续排（2026-08-26 Ross ch9 实测）：章首目录主体在扉页（≥3 个
    # 节号首现），末尾条目（9.4）续排到次页页顶（y≈103）——该首现命中不在
    # 扉页上，逃过上面的判据。补则：紧随某目录页之后的一页，若其全部首现
    # 命中都贴顶（y < 350），同样视为目录污染页（回扫 min_y 会自动跳过续排
    # 行本身；真节头唯一时退回原值，不比旧差）。
    if _opener_pages:
        # 🔴 序标深度一致才认「目录续排」（2026-09-26 Rosen 8e ch1 §1.1.2 实测）：
        # 章扉页目录只列 §N.M（深度 2），而 §N.M.K 的正文节头常常**正好落在扉页
        # 次页的页顶**（Rosen p25 y=175 `1.1.2 Propositions`）。旧规则只看
        # 「全部首现贴顶 y<350」，把该页也判成目录页 → 回扫用 min_y 严格大于
        # 把自己排除 → §1.1.2 锚到 p61（别的小节的习题区），且因为 1.1.1<1.1.2
        # 序上不倒挂，节序检测闸看不见。判据见 _opener_continuation_pages。
        _opener_pages |= _opener_continuation_pages(_first_hit, _opener_pages)
    # 🔴 目录带下界（Rosen 8e ch2 §2.1.1 实测）：章目录通常只列 §N.M，于是
    # §N.M.K 的首现命中**本身就是正文节头**（Rosen p144 目录带 y=385..693，
    # 真节头 "2.1.1 Introduction" 在 y=1635）。旧代码一律按「目录污染行」处理
    # → min_y 严格大于把真节头自己排除，回扫只能撞上别的小节的同号/同名行
    # （见 _find_numbered_heading_page 的兄弟块否决）。判据：命中 y 已落在该页
    # 目录带（= 该页全部首现命中的最大 y）之下 = 真节头，直接采用、不回首扫。
    _toc_band = {}
    for _num, _row in _first_hit.items():
        if _row[0] in _opener_pages:
            _toc_band.setdefault(_row[0], []).append(_row[4])
    _toc_band = {p: _toc_band_bottom(ys) for p, ys in _toc_band.items()}
    if not getattr(book, "sections_unnumbered", False):
        # 无序号标书（section_types 含 0，如 Silverman）：scan_skeleton 对无数字
        # 标题完全失明且易编造假小节（违反保真），故跳过 skeleton SEC，仅用下方
        # 「agent 校验识别」产物 _recognized_sections.json 的权威小节清单注入。
        for row in dedup_sec:
            p, num, title, y = row[0], row[2], row[3], row[4]
            _poisoned = p in _opener_pages
            if num in sec_pages:
                if title and not sec_titles.get(num):
                    sec_titles[num] = title
                continue
            if _poisoned:
                # 章首目录命中：回扫正文节头；扫不到退回原值。min_y = 污染行
                # （目录命中）块顶——真节头与目录同页时（ch5 扉页即 §5.1 起始），
                # 只接受目录行下方的匹配。
                _tb = _toc_band.get(p)
                if _hit_below_toc_band(y, _tb):
                    pg = p          # 命中已在目录带之下 = 真节头，原位采用
                else:
                    pg = _find_numbered_heading_page(
                        ext, num, p, end, min_y=y, page_dir=page_dir,
                        title_text=title) or p
                    y = None
            elif getattr(book, 'chapter_local_sections', False):
                # chapter-local 节来自 md，无源扫描页码；用源 "N. Title"
                # 首现页作为真实页码，供条目按页就近归节。
                pg = _find_chapter_local_section_page(ext, ch, int(num), start, end, page_dir=page_dir)
                y = None
            else:
                pg = p
            sec_pages[num] = pg
            # 节头 (page, y) 进 sec_pos：同页「条目在上、节头在下」的 y 感知归并
            # （谷超豪《数学物理方程》实测：ch6 性质4 与 §5 节头同页）。
            sec_pos.setdefault(num, (pg, float(y) if y is not None else 0.0))
            if title and not sec_titles.get(num):
                sec_titles[num] = title

    # 3) 抽取器条目（权威 ITEM，排除练习类 + 练习区页）
    #    习题块（"EXERCISES FOR CHAPTER N" 起至章末）内的页码一律不从抽取器
    #    进入 ITEM 合同，否则习题题号（如 Strogatz `3.1.1`）会被误判为
    #    Example/Definition 条目，造成重复键、错类型、乱序。
    raw_items = _extract_items(ext, ch, start, end, book, manual=manual,
                               page_dir=page_dir,
                               sec_windows=[(pg, n) for n, pg in sec_pages.items()
                                            if not str(n).startswith("U")])
    ex_start = _exercise_region_start(ext, ch, start, end, page_dir=page_dir)

    # 3a) 标签在前 EN3 书（如 Brin & Stuck）的 "Exercise C.S.N" 条目：抽取器
    #     已把它们作为带标签条目抓出，但练习节点权威来源是 skeleton EXER——
    #     而此类书无 "EXERCISES" 标题块、编号也无字母位，EXER 恒空，直接丢弃
    #     会整书漏练。故把练习类条目转成 EXER 行并入 ex_rows（按练习号去重，
    #     skeleton EXER 优先），非练习类照旧进 ITEM 合同。
    # 🔴 分隔符无关 + 字母前缀附录（2026-09-01 修复 Weibel exercises=0）：
    # raw_items 的 key 经 _extract_items 的 normkey 已转连字符 scheme
    # （"1.1.1"→"1.1-1"，附录 "A.4.1"→"A.4-1"）。原正则只认 digit-first 点分，
    # 对 "1.1-1" 永不命中 → 3a `continue` 漏掉全部 Exercise。改为：可选字母首
    # 分量 + [.\-] 分隔符无关，digit-first（"1.2-3"）与字母前缀（"A.4-1"）均命中，
    # exercise 节点键取 normkey 形态，_section_of_exer 据字母前缀派生 §A.N。
    # 🔴 两级字母号变体（Lee 2e 实测）：附录练习印作 "Exercise A.3"（字母章位 +
    # 单段数字），normkey 后为 "A.3"。旧正则的两段数字核 `\d[.\-]\d` 对它永不
    # 命中 → 3a `continue`，附录练习整章漏收（A 29 条 / B 22 条 / C 7 条）。
    # 增加字母前缀 + 单段数字的变体（字母前缀强制存在，裸单数字仍是散文噪声
    # 不得收）；alternation 放在三级形态之后，三级书行为不变。
    _exer_num_re = re.compile(
        r'((?:[A-Za-z][.\-])?\d{1,2}[.\-]\d{1,2}(?:[.\-](?:\d{1,3}|[A-Z]))?'
        r'|(?:[A-Za-z][.\-])\d{1,3})\.?$')
    _exer_seen = {r[2] for r in ex_rows}
    for it in raw_items:
        if (it.get("label") or "").strip() not in _EXERCISE_LABELS:
            continue
        m = _exer_num_re.search((it.get("key") or "").strip())
        if not m:
            continue
        num = m.group(1).rstrip('.')
        if num in _exer_seen:
            continue
        _exer_seen.add(num)
        title = _clean_title(it.get("text", ""), it["key"])
        _marker = 'PROB' if (it.get("label") or "").strip() in _PROBLEM_LABELS else 'EXER'
        ex_rows.append((it.get("page", 0), _marker, num, title, None))

    items = [it for it in raw_items
             if (it.get("label") or "").strip() not in _EXERCISE_LABELS
             and (ex_start is None or it.get("page", 0) < ex_start)]

    # 3a-1b) Filter out uncat cross-references: bare numbers followed by comma
    # (e.g. "1.5.1,以下两个极限存在：") are prose references, not real items.
    _UNCAT_REF_RE = re.compile(r'^[\d.\-]+\s*[,，]')
    items = [it for it in items
             if (it.get("label") or "").strip() != 'uncat'
             or not _UNCAT_REF_RE.match((it.get("text") or "").strip())]

    # 3a-2) Ross 体例章末习题块（exercise_region_headings 声明）：块头起至章末
    #    的页不再进 ITEM 合同。y 感知：与块头同页的条目，仅当其块顶 y 在块头
    #   （y 较小 = 页面上方）之前才保留；_item_pos 找不到位置时返回 -1 → 保留
    #    （宁缺勿滥的反向：真条目不因 OCR 定位失败而丢失，漏项交源侧回填兜底）。
    _ex_headings = getattr(book, 'exercise_region_headings', None) or None
    if _ex_headings:
        ex_pos = _exercise_block_pos(ext, ch, start, end, _ex_headings, page_dir=page_dir)
        if ex_pos is not None:
            _ep, _ey = ex_pos
            _kept = []
            for it in items:
                pos = _item_pos(ext, it, page_dir=page_dir)
                if pos is None:
                    _kept.append(it)
                    continue
                ip, iy = pos
                if ip < _ep or (ip == _ep and iy < _ey):
                    _kept.append(it)
            items = _kept

    # 3b) 同 key 去重：OCR 断行会把正文引用顶到块首，产生与真条目同号的
    #     假条目（如 §7.3 前言裸号块 "7.3.9."、§5.4 跨块拼接的第二个
    #     5.4.2）。判别：标题非裸者胜（真条目头带印刷标题/正文延续，
    #     引用块常只有裸号或逗号续句）；同态取页码小者（书内编号单调，
    #     真标题先出现）。dedup_items 刻意保留同 key 异文（Lasota-Mackey
    #     双印），故此处按「裸号劣汰」再收一轮。
    #     🔴 仅折叠「同页」重复（2026-08-24 Evans SDE 案例）：节内重置计数器书
    #     （scope 3：Evans 每节 Example 1..N 重排，do Carmo 同型）会合法地在
    #     不同节复用同一 "Label N" 键——跨页（Δpage ≥ 1）的同键项是真实重起，
    #     必须全部保留；只有同页同键才是 OCR 双读/断行伪条目。旧逻辑按章全局
    #     折叠同键项，把合法重起当重复删掉（实测 ch2 丢 §B 的 Example 1/2）。
    #     分组键小写化（OCR 大小写噪声 "EXAMPLE 3"/"ExAMPLE 3" 视为同键）；
    #     跨页保留项挂整数槽位避免覆盖。
    _by_key = {}
    for it in items:
        k = (it["key"] or "").strip().lower()
        # Include label in dedup key so same-numbered items with different labels
        # (e.g. "定义1.3.1" and "定理1.3.1") are kept as distinct entries.
        dk = (k, (it.get("label") or "").strip().lower())
        prev = _by_key.get(dk)
        if prev is None:
            _by_key[dk] = it
            continue
        if abs((it.get("page") or 0) - (prev.get("page") or 0)) > 0:
            _by_key[len(_by_key)] = it
            continue

        def _title_len(x):
            return len(_clean_title(x.get("text", ""), x["key"]))
        # 判优：①裸号劣汰——prev 裸(<8)而 it 带标题(>=8)时替换；
        # ②同态（同裸/同带标题）取页码小者。原写法把「>=8 == 」写成链式
        # 比较（等价于 it 恰为 8 才可能触发），且漏掉页码比较——已按注释
        # 语义重写。
        _lp, _li = _title_len(prev), _title_len(it)
        if (_lp < 8 <= _li) or \
           ((_lp >= 8) == (_li >= 8) and
            it.get("page", 0) < prev.get("page", 0)):
            _by_key[dk] = it
    items = sorted(_by_key.values(),
                   key=lambda x: ((x.get("page") or 0), _nat_key_digits(x["key"])))

    # 4) 章节骨架派生：sec_pages / sec_titles / sec_pos 已在 3) 之前预计算
    #    （单级按节重置书需要节窗口先于条目抽取，见上）。
    # 派生章节号收集（用于补齐 skeleton 缺失的章节）

    # 无序号标层（section_types 含 0）：注入「agent 校验识别」步骤产出的权威
    # 小节清单（key 用 "U{n}" 区分于编号小节）。OCR 无数字段，scan_skeleton
    # 的深度检测对无序号标标题完全失明且易编造假小节（违反保真），故此处
    # 直接消费识别产物，不再走 OCR 正则。条目可带 level（1=一级小节 / 2=节内
    # 二级子标题），_u_level 供 6b) 按层级嵌套（sec2 → 最近 sec1 的 sub_sec）。
    _u_level = {}
    if getattr(book, "sections_unnumbered", False):
        for _i, (_ut, _up, _uy, _ulv) in enumerate(
                _recognized_sections(ext, ch, start, end, page_dir=page_dir), 1):
            _uk = "U%d" % _i
            sec_pages.setdefault(_uk, _up)
            sec_pos[_uk] = (_up, _uy)
            _u_level[_uk] = _ulv
            # 保留空标题（unnumbered 书常有「## §」无标题小节，如 Silverman 后段章
            # 节）。空标题在 P 层 _title_present("") 被判定为「恒存在」，不会误报
            # 缺节；若回退到 "U{n}" 键名，则会因 "u1" 不在 md 标题中而假阳缺节。
            if not sec_titles.get(_uk):
                sec_titles[_uk] = _ut

    # 派生章节号收集（用于补齐 skeleton 缺失的章节）
    derived_sec_firstpage = {}
    def _note_sec(num, page):
        if num is None:
            return
        if num not in sec_pages:  # skeleton 已有则不打扰
            if num not in derived_sec_firstpage or page < derived_sec_firstpage[num]:
                derived_sec_firstpage[num] = page

    for it in items:
        _note_sec(_section_of_key(it["key"], ordinal, book.chapter_first,
                                  chapter_local=getattr(book, 'chapter_local_sections', False),
                                  chapter_scoped=getattr(book, 'chapter_scoped_items', False),
                                  sections_global=getattr(book, 'sections_global', False)),
                  it["page"])
    for row in ex_rows:
        _note_sec(_section_of_exer(row[2]), row[0])

    # 剔除「条目号派生、但 skeleton 并未检出」的幽灵小节（如 EN 两级下
    # "Theorem 20.7" 派生的 §20.7，而 §20.7 并非真小节）。skeleton 扫描现已
    # 深度无关且可靠，凡它没检出的派生小节号必是幽灵；这些条目稍后会按页码
    # 就近归并到最近的真小节（_place），不会丢失。此项取代原先仅靠小结
    # markdown 校验的 Bug#20 守卫——不再依赖尚未写出的小结即可剔除幽灵。
    derived_sec_firstpage = {
        n: pg for n, pg in derived_sec_firstpage.items() if n in sec_pages
    }

    # 🔴 Weibel 附录：条目键为字母前缀（"A.1-4"），scan_skeleton 不检附录字母
    # 小节，上面「须命中 skeleton」过滤器会把派生的 A.1/A.2… 全部清空。附录章直接
    # 以字母前缀条目键派生 A.N 小节注入（标题留空，write-source 阶段据源标题补全
    # §A.N 标题），保证附录条目归入正确的 §A.N 而非堆在章级。仅当本章含字母前缀
    # 键时触发，digit-first 书零回归。
    # 🔴 无编号书（`sections_unnumbered`，section_types 含 0）必须**跳过**这条
    # 派生路径：其小节来自 `_recognized_sections.json` 的权威清单（键 `U{n}`），
    # 而附录条目键恰好也是「字母.数字」（Lee ISM 的 `Example A.4` / `Theorem D.1`），
    # 上面的正则会把**条目号原样派生成 §A.4 / §D.1 伪小节**，与真小节并存
    # （实测 appendixD 产出 `U1, D.1…D.5, U2, U3, D.6`）。Weibel 式附录用的是
    # **有编号** §A.N（section_types 不含 0），不受影响，零回归。
    if (not getattr(book, "sections_unnumbered", False)
            and any(re.match(r'^[A-Za-z]', (it.get("key") or "")) for it in items)):
        for it in items:
            _lm = re.match(r'^([A-Za-z])\s*[.\-]\s*(\d+)',
                           (it.get("key") or ""))
            if not _lm:
                continue
            _an = f"{_lm.group(1).upper()}.{_lm.group(2)}"
            _pg = it.get("page", 0)
            if _an not in sec_pages:
                sec_pages[_an] = _pg
            sec_titles.setdefault(_an, "")
            derived_sec_firstpage.setdefault(_an, _pg)

    all_sec_nums = list(sec_pages.keys()) + [n for n in derived_sec_firstpage if n not in sec_pages]
    # 章节排序：按（skeleton 页 或 派生最小页）
    def _sec_sort_key(n):
        return sec_pages.get(n, derived_sec_firstpage.get(n, start))
    all_sec_nums.sort(key=_sec_sort_key)

    # Bug #20：用章节小结 markdown 的二级小节标题校验「条目派生小节」，剔除幽灵小节
    # （如 EN 两级下 Example 2.7/2.8/2.9 错误派生的 §2.7/§2.8/§2.9）。仅当小结
    # markdown 存在且含二级小节标题时才启用过滤；否则保持原行为（兼容无小结的书）。
    real_sub = _real_subsections_from_markdown(ext, ch)
    if real_sub is not None:
        _kept_derived = {}
        for n, pg in derived_sec_firstpage.items():
            if n in sec_pages or n in real_sub:
                _kept_derived[n] = pg
        derived_sec_firstpage = _kept_derived
        all_sec_nums = list(sec_pages.keys()) + [n for n in derived_sec_firstpage if n not in sec_pages]
        all_sec_nums.sort(key=_sec_sort_key)

    sec_nodes = {}
    for n in all_sec_nums:
        title = sec_titles.get(n, "")
        page = sec_pages.get(n, derived_sec_firstpage.get(n, start))
        # 无序号标小节（"U{n}" 合成键）name 用纯标题，不拼数字前缀；
        # 标题为空时 name 也保持空（P 层对空标题判「恒存在」，避免假阳缺节）。
        if n.startswith("U"):
            name = title
        else:
            name = (f"{n} {title}".strip() if title else n)
        node = _node(n, "section", name, page)
        if n.startswith("U"):
            # 标题层级（1=一级小节 / 2=节内二级子标题）：渲染层据此选择
            # `## §` / `### §`，写作契约与 md 保留原书层级结构。
            node["level"] = int(_u_level.get(n, 1))
        node["sub_sec"] = []
        sec_nodes[n] = node

    # 4a-nums) 数值本地子块（Arnold《ODE》逐 § 重启的裸单号二级小节）：把形如
    #   "<§>.<local>" 的两段号节节点（其单号父 § 存在）标记为**真实 level-2 小节**
    #   —— node["level"]=2（渲染 `###`）+ node["bare_head"]=True（渲染只印裸局部号
    #   "<local>. <标题>"，不带 § 、不投影父号），复用 recognize_sections 的层级
    #   嵌套/渲染/校验管线。仅 numeric_local_sections 书启用，其余书零回归。
    if getattr(book, 'numeric_local_sections', False):
        for _n, _snode in sec_nodes.items():
            _parts = re.findall(r"\d+", str(_n))
            if len(_parts) != 2:
                continue
            _parent = ".".join(_parts[:-1])   # 单号父 §（"1.3" -> "1"）
            if _parent in sec_nodes:
                _snode["level"] = 2
                _snode["bare_head"] = True

    # 4b) 字母子块挂到节节点（letter_subs 元数据；仅正文章的 SUB 聚合结果）。
    # 父节不存在（幽灵）则丢弃；按 (page, letter) 排序保持书中出现顺序。
    if letter_sub_blocks:
        for parent, subs in letter_sub_blocks.items():
            snode = sec_nodes.get(parent)
            if snode is None:
                continue
            entries = []
            for L, (pg, t) in subs.items():
                entries.append((pg, L, {
                    "key": L,
                    "name": (f"{L} {t}".strip() if t else L),
                    "page_start": pg,
                }))
            entries.sort(key=lambda x: (x[0], x[1]))
            snode["letter_subs"] = [e[2] for e in entries]

    # 4c) 🔴 manual_overrides 裁定条目优先于幻影子节：标题前置条目
    # （"Yoneda Embedding 1.6.10 ..."）的号行会被 scan_skeleton 误读为
    # 三段子节头（sec node "1.6.10"），而同号的真条目又经 overrides 回填
    # ——若不清除幻影子节，同号在契约中出现两次（section + item），B 层
    # 查重直接判顺序错乱。凡 overrides 键命中三段子节键且其父节存在
    # （本书小节为两段号）→ 移除幻影子节，让 override 条目归位。
    if manual:
        for mo in manual:
            mk = normkey(str(mo.get("key", "")))
            # 幻影子节的键是点号形（OCR 原样 "1.6.10"），override 键归一为
            # 短横形（"1.6-10"）——两种形态都要查。
            for gk in {mk, mk.replace("-", ".")}:
                if gk not in sec_nodes or len(re.findall(r"\d+", gk)) != 3:
                    continue
                ghost = sec_nodes.pop(gk)
                if gk in all_sec_nums:
                    all_sec_nums.remove(gk)
                derived_sec_firstpage.pop(gk, None)
                sec_pos.pop(gk, None)
                for parent in list(sec_nodes.values()):
                    if ghost in parent.get("sub_sec") or []:
                        parent["sub_sec"].remove(ghost)

    # 5) 条目/练习挂到章节
    chapter_bucket = []  # 无章节可挂时归章级（置于最前）

    def _place(node, sec_key, page, pos=None):
        if sec_key is not None and sec_key in sec_nodes:
            sec_nodes[sec_key]["sub_sec"].append(node)
            return
        # 归并：最近的、起始位置 <= 条目位置的章节。
        # sec_pos 非空（sections_unnumbered 路径）且条目带 (page, y) 时按字典序
        # (page, y) 比较——同页时 y 在节头之前的条目归前一节（2026-08-24 Evans
        # SDE：EXAMPLE 7 与 §B 节头同页但位于其前，页码比较会错归 §B）。
        use_pos = bool(sec_pos) and pos is not None
        cand = None
        for n in all_sec_nums:
            sp = sec_pages.get(n, derived_sec_firstpage.get(n, start))
            if use_pos:
                if sec_pos.get(n, (sp, 0)) <= pos:
                    cand = n
            elif sp <= page:
                cand = n
        if cand is not None:
            sec_nodes[cand]["sub_sec"].append(node)
        else:
            chapter_bucket.append(node)

    _unnumbered_book = getattr(book, "sections_unnumbered", False)
    for it in items:
        sec_key = _section_of_key(it["key"], ordinal, book.chapter_first,
                                  chapter_local=getattr(book, 'chapter_local_sections', False),
                                  chapter_scoped=getattr(book, 'chapter_scoped_items', False),
                                  sections_global=getattr(book, 'sections_global', False))
        title = _clean_title(it.get("text", ""), it["key"])
        name = (f"{it['key']} {title}".strip()) if title else it["key"]
        node = _node(it["key"], _type_of(it.get("label")), name, it["page"])
        pos = _item_pos(ext, it, page_dir=page_dir)
        if (pos is not None and pos[1] < 0 and not _unnumbered_book and sec_pos):
            # OCR 整块丢失的条目（_item_pos 找不到块）：位置未知。-1 的「排在节头
            # 之前」语义只适用于无序号标书（Evans）；编号节书沿用旧「页码就近」
            # 行为——视为页末，归入本页已开节的最后一节。
            pos = (pos[0], float("inf"))
        _place(node, sec_key, it["page"], pos=pos)

    for row in ex_rows:
        p, num, title = row[0], row[2], row[3]
        sec_key = _section_of_exer(num)
        name = (title if title else num)
        node = _node(num, "problem" if row[1] == "PROB" else "exercise", name, p)
        _place(node, sec_key, p)

    # 6) 章节内子节点排序（2026-08-29 y 感知版 → 2026-09-26 Kreyszig 根治）：
    #    「条目 vs 节头/习题块」仍按源页锚定 y 交错（Koopman Remark 5.5 语义
    #    保留），但「条目 vs 条目」改按编号自然序。旧逻辑条目两两也取 y：
    #    ① manual/OCR 丢头条目锚不到（y 回退 0）整页抢跑（2.1-4@67 排到
    #       2.1-2 之前、4.9-3@280 排到 4.9-2 之前）；② 同页交叉引用块误锚
    #       压过小编号真头（4.7-1 误锚 y729 排到 4.7-2(y575) 之后）。
    #    印刷书节内编号单调，同页条目对的真实顺序天然= 自然序，与 y 无关。
    def _doc_y_of(child):
        nid = id(child)
        if nid not in _doc_y_cache:
            page = int(child.get("page_start") or 0)
            ckey = str(child.get("key") or "")
            y = None
            if child.get("type") == "section":
                if not ckey.startswith("U"):
                    y = _numbered_heading_y(ext, ckey, page, page_dir=page_dir)
                if y is None:
                    t = (child.get("name") or "").strip()
                    t_no = re.sub(r'^[\dA-Z]+(?:\.[\dA-Z]+)*\s*', '', t).strip()
                    pos = _find_title_pos(ext, t_no or t, page, page, page_dir=page_dir) if t else None
                    y = pos[1] if pos else None
            else:
                pos = _item_pos(ext, {"key": ckey, "page": page,
                                       "text": child.get("name") or ""}, page_dir=page_dir)
                y = pos[1] if pos and pos[1] is not None and pos[1] >= 0 else None
            _doc_y_cache[nid] = float(y) if y is not None else None
        return _doc_y_cache[nid]

    def _doc_sort_key(child):
        y = _doc_y_of(child)
        return (int(child.get("page_start") or 0),
                y if y is not None else 0.0,
                _nat_key_digits(child["key"]))

    _ANCHOR_TYPES = ("section", "exercise", "problem")

    def _sort_doc_order(children):
        anchors = sorted((c for c in children
                          if c.get("type") in _ANCHOR_TYPES), key=_doc_sort_key)
        def _item_order_cmp(a, b):
            # 🔴 跨计数器比较禁用数字序（do Carmo ch5 实测 2026-09-26）：
            # 节内**每个计数器各自重启**（Definition 1 / Theorem 1 / Example 1
            # 并存），旧键把 key 数字段作为跨条目主序，把 定理1(p401 页中)
            # 排到 例2(p401 页上) 之前 → 前序页码 401→403→401 回退，锚点闸
            # 整章拒绝落盘。数字单调只在**同标签**（同计数器）内成立；
            # 异标签对的真实阅读序 = 源页锚定 y（锚不到取 +inf 排末）。
            # Kreyszig 语义保留：同标签同页交叉引用误锚仍按号序，不看 y。
            pa, pb = int(a.get("page_start") or 0), int(b.get("page_start") or 0)
            if pa != pb:
                return -1 if pa < pb else 1
            ka, kb = str(a.get("key") or "0"), str(b.get("key") or "0")
            la = re.match(r'^([^\d]*)', ka).group(1)
            lb = re.match(r'^([^\d]*)', kb).group(1)
            if la != lb:
                ya = _doc_y_of(a)
                yb = _doc_y_of(b)
                fa = ya if ya is not None else float("inf")
                fb = yb if yb is not None else float("inf")
                if fa != fb:
                    return -1 if fa < fb else 1
                return -1 if _nat_key(ka) < _nat_key(kb) else (
                    0 if ka == kb else 1)
            na = tuple(int(x) for x in re.findall(r"\d+", ka))
            nb = tuple(int(x) for x in re.findall(r"\d+", kb))
            if na != nb:
                return -1 if na < nb else 1
            return -1 if _nat_key(ka) < _nat_key(kb) else (
                0 if ka == kb else 1)

        its = sorted((c for c in children
                      if c.get("type") not in _ANCHOR_TYPES),
                     key=functools.cmp_to_key(_item_order_cmp))
        if not anchors:
            return its
        out, si = [], 0
        for it in its:
            y = _doc_y_of(it)
            # 锚不到的条目（manual 回填/OCR 丢块）按「页末」归位，与 _place
            # 的 inf 约定一致。
            ipos = (int(it.get("page_start") or 0),
                    y if y is not None else float("inf"))
            while si < len(anchors):
                a = anchors[si]
                ay = _doc_y_of(a)
                akey = (int(a.get("page_start") or 0),
                        ay if ay is not None else 0.0)
                if akey <= ipos:
                    out.append(a)
                    si += 1
                else:
                    break
            out.append(it)
        out.extend(anchors[si:])
        return out

    _doc_y_cache = {}
    for n in all_sec_nums:
        sec_nodes[n]["sub_sec"] = _sort_doc_order(sec_nodes[n]["sub_sec"])

    # 6b) 小节按数字层级嵌套（Koopman 书实测，2026-08-29）：契约树必须与原书
    # 标题层级同构——"1.2.1" 是 "1.2" 的子节、挂进其 sub_sec；"1.2.1.1" 再挂进
    # "1.2.1"。此前所有 section 平铺在章下，写作契约与渲染骨架都丢失层级。
    # 父键 = 去掉末段；父不存在（编号洞，如书直接从 1.2 跳 1.2.2）→ 留在顶层，
    # 不编造父节。无序号标节（"U{n}"）与字母子块不参与嵌套。子节在父 sub_sec
    # 内与条目一起按 (page_start, 自然序) 重排，保持文档顺序。
    def _sec_depth(key):
        return len(re.findall(r"\d+", str(key)))

    top_secs = []
    # 无序号标节按 level 嵌套（Lee ISM 实测：sec1=一级小节（TOC 级）、
    # sec2=节内二级子标题——「Coordinate Charts」等只出现在正文、不进 TOC/
    # 页眉）。sec2 挂进**文档序上最近的前一个 sec1** 的 sub_sec；前导 sec2
    #（尚无任何 sec1）保守留在顶层，不编造父节。
    _last_u1 = None
    for n in all_sec_nums:
        node = sec_nodes[n]
        if n.startswith("U"):
            if _u_level.get(n, 1) >= 2 and _last_u1 is not None:
                _last_u1["sub_sec"].append(node)
            else:
                top_secs.append(node)
                if _u_level.get(n, 1) <= 1:
                    _last_u1 = node
            continue
        if _sec_depth(n) < 2:
            top_secs.append(node)
            continue
        parts = re.findall(r"\d+", str(n))
        parent_key = ".".join(parts[:-1])
        parent = sec_nodes.get(parent_key)
        if parent is None or parent is node:
            top_secs.append(node)
        else:
            parent["sub_sec"].append(node)

    def _sort_tree(node):
        node["sub_sec"] = _sort_doc_order(node["sub_sec"])
        for k in node["sub_sec"]:
            if k.get("type") == "section":
                _sort_tree(k)

    for s in top_secs:
        _sort_tree(s)

    # 7) 递归算 page_start / page_end（容器取末代子孙页）
    def _fix_pages(node):
        kids = node.get("sub_sec")
        if not kids:
            return node["page_end"]
        # 容器自身页（节头所在页）参与 page_start：仅有习题块等晚页子项的空节
        # （谷超豪《数学物理方程》ch2 §1 等）若只取子项最小页，会把节头页
        # 推迟到子项页，节区间失真。
        child_starts = [node.get("page_start", 0)] + [k["page_start"] for k in kids]
        child_ends = [_fix_pages(k) for k in kids]
        node["page_start"] = min(child_starts)
        node["page_end"] = max(child_ends)
        return node["page_end"]

    ordered_secs = top_secs
    for s in ordered_secs:
        _fix_pages(s)

    # 章级子节点：章级桶（无章节可挂）置于章节之前，按页码排（同页自然序）
    chapter_bucket.sort(key=lambda x: (x["page_start"], _nat_key_digits(x["key"])))
    sub = chapter_bucket + ordered_secs

    ch_title = _chapter_title(cm, ch)
    # 印刷序标（无编号附录 → 空串）：契约章名约定 "{ordinal} {title}"，下游
    # render_draft/_final_md_name 据此渲染 "# Appendix A: title" / "附录.md"。
    # 🔴 无编号附录（键 "appendix"）ordinal 为空 → 章名只剩标题，绝不伪造 "7 附录"。
    ch_ord = chapter_ordinal(ch)
    # 附录章名归一（命名单点）：chapter_map 若登记 "Appendix A: Category Theory
    # Language"（或 "附录A：…"），title 已含序标，直接拼接会得到双前缀
    # "A Appendix A: …" → 渲染 "# Appendix A: Appendix A: …" / 文件名
    # "AppendixA_Appendix_A.md"。故剥离 title 首部的 "Appendix {ord}" / "附录{ord}"
    # （含冒号）；剥后为空（仅登记 "Appendix A"）时保留原样退化，不产生空标题。
    # 无编号附录（ch_ord 为空）没有可剥离的序标，跳过此归一。
    if ch_ord:
        _m_app = re.match(r'^\s*(?:appendi(?:x|ces)\s+%s|附录\s*%s)\b\s*[:：]?\s*(.*)$'
                          % (re.escape(str(ch_ord)), re.escape(str(ch_ord))),
                          ch_title or '', re.IGNORECASE)
        if _m_app and _m_app.group(1).strip():
            ch_title = _m_app.group(1).strip()
    ch_name = (f"{ch_ord} {ch_title}".strip()) if ch_title else (ch_ord or str(ch))
    chapter = _node(str(ch), "chapter", ch_name, start)
    chapter["sub_sec"] = sub
    # 多册书分册归属写进契约（相对 extract_dir 的子目录名，如 "上册"；单册书为空
    # 串）。下游凡读该章页原文者一律据此还原 page 目录——各册页码重复，直接读
    # extract_dir 会静默命中某一册（实测命中上册），把内容挂错册且不报错。
    chapter["page_dir"] = _rel_page_dir(ext, page_dir)
    _fix_pages(chapter)
    # 章边界以 chapter_map 权威区间 (start, end) 为准，禁止被子节点递归覆盖。
    # 修复：Ch8/14–18 等无编号条目（或 section 无子项）的章，_fix_pages 会把
    # chapter.page_end 塌缩回 page_start（start），致 book_structure 章级页码失真
    # （实测 Ch8: ps=215 pe=215，应为 215–252）。section/item 子区间仍由 _fix_pages
    # 递归决定（取末代子孙页），此处仅锁定章级区间为 chapter_map 真值。
    chapter["page_start"], chapter["page_end"] = start, end
    return chapter


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    ext = args[0]
    # 🔴 灌注 kind 注册表（Chapter/Appendix/Supplement 三分依赖 chapter_map 的显式 kind）
    try:
        from book_structure import prime_chapter_kinds
        prime_chapter_kinds(ext)
    except Exception:
        pass
    # 章号归一：数字章 → int，附录字母章（"A"/"B"…）保留原串。裸 int() 会让
    # `build_structure <ext> A` 直接 ValueError（附录章无法定点重建）。
    want = [norm_chapter_key(x) for x in args[1:]]

    # 🔒 上游闸：structure 依赖已修复的 page_*.json 与 config；MM Repair 未完成
    # （缺 _extraction_done.json）则禁止生成结构契约，否则会基于未修复页抽项，
    # 进而污染 write-source 全部章节（这正是"上一步没做完不能进下一步"的硬纪律）。
    if not os.path.exists(os.path.join(ext, "_extraction_done.json")):
        print("[build_structure] BLOCKED: 缺 _extraction_done.json，MM Repair 未完成。")
        print("  须先完成 MM Repair（模式 A+B 写回 page_*.json，apply 真完成写出")
        print("  _extraction_done.json）后再生成分章契约 book_structure/ch{N}.json。")
        print("  严禁跳步。可先对该书运行 `python tools/flow_runner.py bootstrap <book_dir>`")
        print("  依据物理证据补写完成标记。")
        return 2

    cfg_path = os.path.join(ext, "verify_config.json")
    try:
        loader = ConfigLoader(ext, os.path.dirname(ext.rstrip("/")) or ext)
        loader.require_complete()
        book = loader.book
    except (ConfigError, ValueError) as e:
        # 兼容 chapter_map.json 含字母章号（附录 A/B…）导致 ConfigLoader 崩的
        # 既有书（如 Evans）。直接读 verify_config.json 构造 BookConfig（只解析
        # verify_config，不触发 chapter_map 解析），ordinal / language 不受影响。
        if not os.path.exists(cfg_path):
            print(e)
            return 2
        with open(cfg_path, encoding="utf-8-sig") as fh:
            vcfg = json.load(fh)
        book = BookConfig.from_dict(vcfg)

    cm = chapter_map.load_chapter_map_raw(os.path.join(ext, "chapter_map.json"))
    rng = _build_rng(cm)

    # 解析每章 manual_overrides_ch{N}.json（恢复 OCR 漏识的真实条目，如 4.9-3）。
    # 仅在 ConfigLoader 成功构建时可用（except 分支降级只读 verify_config，无 overrides）。
    _loader_obj = locals().get("loader")

    # 每章独立落盘：<extract_dir>/book_structure/ch{N}.json（附录 appendix{X}.json）
    # —— **一步产出完整契约**：build_structure 生成骨架后立即
    # 调 build_chapter_contract 挂入正文内容（description / proof / text /
    # formula / image 内容块）并写回同一文件；ch{N}.json 即"整章信息的唯一载体"，
    # 后续子流程只做校验与回填。
    # 分章文件即结构契约唯一真源；不产出整书单文件 book_structure.json。
    from attach_content import build_chapter_contract
    out_sub = os.path.join(ext, "book_structure")
    os.makedirs(out_sub, exist_ok=True)
    built = 0
    _anchor_bad = 0
    for ch in (want or sorted(rng, key=_chapter_sort_key)):
        if ch not in rng:
            print("%-9s SKIP (not in chapter_map)" % chapter_label(ch))
            continue
        start, end = rng[ch]
        manual = _loader_obj.manual_for_chapter(ch) if _loader_obj else None
        # 附录章路由：ConfigLoader 在手时按章取配置——附录章（字母键或章名含
        # Appendix/附录）由 config_for_chapter 切到 appendix_verify_config.json
        # 的体例（如 ORDINAL_APP 字母章位），正文章零变化。
        book_ch = _loader_obj.config_for_chapter(ch) if _loader_obj else book
        chapter = build_chapter(ext, ch, start, end, book_ch, cm, manual=manual)
        node = StructureNode.from_dict(chapter)
        node.recompute_pages()
        out = chapter_json_path(ext, str(ch))
        # 骨架 → 完整契约（内容挂载）→ 落盘；一次读写，无中间态文件。
        # 多册书：page_*.json 在分册子目录且各册页码重复，内容挂载必须按章
        # 定位到本册目录，否则下册章会挂成上册页的内容（静默错乱）。
        page_dir = _resolve_page_dir(ext, ch)
        full, stats = build_chapter_contract(ext, node.to_dict(), page_dir=page_dir)
        # 🔴 锚点-树序自相矛盾的契约**不落盘**：这类节点（实测：由抽取器 Exercise
        # 标签条目派生的「节习题块」，页码取自命中的页眉/散文行）会把整节内容
        # 挤到错误的阅读位置上，且只在下游门控 ⑪ 以几十条「单元跨节/跨页错位」
        # 暴露，反推代价高。契约不落盘 = 步骤 3 出口不成立，强制在此修正。
        # 两道闸：① 前序页码单调；② 印刷小节号顺序 ↔ 页码顺序一致（补前序闸盲区：
        # 错锚节点恰在前序末尾时不倒退可看，Rosen 8e ch9 §9.1.1 实测）。
        anchor_problems = (check_contract_anchors(full)
                           + check_section_key_page_order(full))
        for _ap in anchor_problems:
            print("%-9s ANCHOR-SANITY FAIL | %s" % (chapter_label(ch), _ap))
        _anchor_bad += len(anchor_problems)
        if anchor_problems:
            print("%-9s 拒绝落盘（锚点问题 %d 处）" % (chapter_label(ch), len(anchor_problems)))
            continue
        with open(out, "w", encoding="utf-8") as f:
            json.dump(full, f, ensure_ascii=False, indent=2)
        built += 1
        n_item = sum(1 for _ in _iter_items(chapter)
                     if _["type"] not in ("exercise", "problem", "section", "chapter"))
        n_ex = sum(1 for _ in _iter_items(chapter)
                   if _["type"] in ("exercise", "problem"))
        n_sec = sum(1 for _ in _iter_items(chapter) if _["type"] == "section")
        print("%-9s BUILD | sections=%d items=%d exercises=%d "
              "text=%d formula=%d image=%d proof=%d desc=%d noise=%d -> %s"
              % (chapter_label(ch), n_sec, n_item, n_ex,
                 stats["text"], stats["formula"], stats["image"],
                 stats["proof"], stats["description"], stats["noise_dropped"],
                 os.path.basename(out)))
    print("BOOK -> %s | chapters built=%d" % (out_sub, built))
    if _anchor_bad:
        print("[build_structure] BLOCKED: %d 处契约锚点与树序矛盾（ANCHOR-SANITY FAIL）。"
              % _anchor_bad)
        print("  修法：把该节点移到父节点 sub_sec **末尾**，并把 page_start/page_end")
        print("  改成它在原书里的真实页（节习题块 = 本节末印刷标题 ``Exercises`` 所在页）；")
        print("  已拆过单元的书**不得重建契约**（会作废 DONE 单元），改为定点修补契约 +")
        print("  同步 manifest 记录次序（只重排记录，不动 id/文件名），参考实现见")
        print("  书目录 _extract/_fix_exer_anchor.py 与门控 ⑪（lib/unit_order.py）。")
        return 2
    return 0


def _chapter_sort_key(key):
    """章号排序键：数字章号按数值，字母/其它章号（附录 A/B…）排末尾。"""
    try:
        return (0, int(str(key)))
    except (TypeError, ValueError):
        return (1, str(key))


def _iter_items(node):
    """展平树（不含 chapter 自身），供统计/消费使用。"""
    for k in node.get("sub_sec", []):
        yield k
        yield from _iter_items(k)


if __name__ == "__main__":
    sys.exit(main())
