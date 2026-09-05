"""build_structure.py — 统一结构骨架生成器：按章产出分章骨架 ch{N}.json

设计（2026-08-29 用户最终确认，替代全书单文件方案）
------------------------------
每章一个文件：``<extract_dir>/book_structure/ch{N}.json``（附录 ``appendix{X}.json``），
顶层即该章 ``chapter`` 节点（无书根包装）。本脚本**一步产出含内容的完整契约**
（骨架 + description / proof / 内容块同进程挂入后写回同一文件，幂等可重跑）——
分章文件是结构契约唯一真源；全书单文件 ``book_structure.json`` 已废弃、不读取。
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
  · verify 编号项基准：展平树、filter type!="exercise" 即得本书编号项集合
    （data_provider 经 BookStructure.load 聚合读取分章文件为编号项基准）。

设计要点（与 verify/data_provider 对齐）
--------------------------------------
  · 编号模式（three-level / two-level / en / vakil / gm / roman）
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

import json
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

import scan_skeleton
from extract_items import extract_items, extract_items_two_level
from extract_items_cn_single import extract_items_cn_single
from extract_items_cn3lab import extract_items_cn3lab
from extract_items_en import extract_items_en
from extract_items_en3 import extract_items_en3
from extract_items_vakil import extract_items_vakil
from extract_items_gm import extract_items_gm
from extract_items_ross import extract_items_ross
from extract_items_hum import extract_items_hum
from verify_config import (ORDINAL_EN, ORDINAL_EN3, ORDINAL_TWO_LEVEL,
                              ORDINAL_SINGLE, ORDINAL_GM, ORDINAL_ROMAN, ORDINAL_VAKIL,
                              ORDINAL_THREE_LEVEL, ORDINAL_CN3LAB, ORDINAL_ROSS,
                              ORDINAL_HUM, ORDINAL_APP,
                              ConfigLoader, ConfigError, BookConfig)
import chapter_map
from key_parse import _canon_label, normkey
from data.book_structure.book_structure import (BookStructure, StructureNode,
                                                chapter_json_path,
                                                norm_chapter_key,
                                                chapter_label)


# ---------------------------------------------------------------------------
# 类型映射：抽取器 label（中文 canon 或英文原文） -> 树 type
# ---------------------------------------------------------------------------
_LABEL_TO_TYPE = {
    "定义": "definition", "Definition": "definition",
    "定理": "theorem", "Theorem": "theorem",
    "引理": "lemma", "Lemma": "lemma",
    "推论": "corollary", "Corollary": "corollary",
    "命题": "proposition", "Proposition": "proposition",
    "例": "example", "Example": "example",
    # Section-scoped EN books (Fraleigh-style) number Tables / Figures in the
    # SAME shared per-section counter as the text items, so they must be typed
    # as their own nodes (not "uncat") — otherwise group_for_label() sends them
    # to the uncat group and the text counter still sees false "missing item"
    # gaps at the graphic slots (1.20 / 1.21 …).  Coupled with the make_config
    # collapse branch that folds "Table"/"Figure" into the merged ordinal name.
    "Table": "table", "Figure": "figure",
    "评注": "remark", "Remark": "remark",
    "注": "remark",
    # Ross 体例（ORDINAL_ROSS）：Axiom 1..4（§2.3 三公理 / §9.2 Markov 链公理）
    # 是真实印刷条目头，type 用独立 "axiom"（structure_io TYPE_TO_LABEL 同步
    # 映射 公理），避免误归 definition/uncat 破坏键空间对齐。
    "公理": "axiom", "Axiom": "axiom",
    "断言": "proposition", "Assertion": "proposition",  # 近似归入命题
    "猜想": "uncat", "Conjecture": "uncat",
    "算法": "algorithm", "Algorithm": "uncat",
    "性质": "property",
    "假设": "uncat", "Assumption": "uncat",
    "uncat": "uncat",
}
_EXERCISE_LABELS = {"练习", "习题", "Exercise", "练习."}

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
                    chapter_scoped=False):
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
      * True（默认，ORDINAL_EN / ORDINAL_EN3）："Definition 6.1" = 第 6 章第 1 条，
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


def _numbered_heading_y(ext, key, page):
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
        + r'(?:[.:：\s\u00a0]+(?=[A-Za-z\u4e00-\u9fff])|(?=[A-Za-z]))')
    fp = os.path.join(ext, 'page_%03d.json' % int(page))
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


def _find_title_pos(ext, title, start, end):
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
    for p in range(start, end + 1):
        fp = os.path.join(ext, "page_%03d.json" % p)
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
        fp = os.path.join(ext, "page_%03d.json" % p)
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
        fp = os.path.join(ext, "page_%03d.json" % p)
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


def _item_pos(ext, it):
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
    fp = os.path.join(ext, "page_%03d.json" % p)
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
    ys_head, ys_contain = [], []
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
        if key_variants and any(k and re.match(r'^' + re.escape(k) + r'(?!\d)', sl)
                                for k in key_variants):
            ys_head.append(y)
        if probe and probe[:24] in sl:
            ys_contain.append(y)
    if ys_head:
        return (p, min(ys_head))
    if ys_contain:
        return (p, min(ys_contain))
    return (p, -1)


def _find_title_page(ext, title, start, end):
    """无序号标小节：返回标题首次出现的页码（兼容旧签名）。

    实现委托给 :func:`_find_title_pos`（三段式锚定匹配，见其 docstring），
    仅丢弃 y 分量。"""
    pos = _find_title_pos(ext, title, start, end)
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
    if str(ch)[:1].isdigit():
        pats = (f"Chapter{ch}_*.md", f"chapter{ch}_*.md", f"第{ch}章_*.md")
    else:
        pats = (f"Appendix{ch}_*.md", f"appendix{ch}_*.md", f"附录{ch}_*.md")
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


def _find_chapter_local_section_page(ext, ch, n, start, end):
    """First source page where chapter-local section `n` appears as a "N. Title"
    heading (Karlin-style).  Gives chapter-local sections a real page so items
    place to the correct section by page proximity.  Returns ``start`` if not
    found; the first occurrence (not later running-header repeats) is the real
    heading, so the early return is correct."""
    from lib.regexlib import SEC_LOCAL
    for p in range(start, end + 1):
        fp = os.path.join(ext, f"page_{p:03d}.json")
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


def _recognized_sections(ext, ch, start, end):
    """无序号标书（section_types 含 0）：读取「agent 校验识别」步骤产物
    ``_recognized_sections.json`` 中本章的小节标题清单，返回 ``[(title, page, y), ...]``
    （按文档顺序），``(page, y)`` 为该标题块的锚定位置（用于排序与条目归并）。

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
        pos = _find_title_pos(ext, t, start, end)
        if pos is None:
            # OCR 漏识的标题（如被 PaddleOCR 吞掉的小节标题）：按文档索引在
            # [start, end] 线性插值保序，避免错排到章首（否则会破坏小节顺序
            # 与条目页码归并）。插值仅影响页排序，不编造内容。
            pg = start if n <= 1 else round(start + (end - start) * i / (n - 1))
            pos = (pg, 0)
        out.append((t, pos[0], pos[1]))
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
    if str(ch)[:1].isdigit():
        cands.extend(glob.glob(os.path.join(book_dir, f"第{ch}章_*.md")))
    else:
        # 附录章小结 md 命名同 merge_units._final_md_name（Appendix{X}_*.md / 附录X_*.md）
        cands.extend(glob.glob(os.path.join(book_dir, f"Appendix{ch}_*.md")))
        cands.extend(glob.glob(os.path.join(book_dir, f"附录{ch}_*.md")))
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


def _exercise_block_pos(ext, ch, start, end, headings):
    """Ross 体例章末习题块头位置：返回首个锚定标题行的 (page, y)，无则 None。

    与 scan_skeleton._exercise_headings_re 同一匹配器（单一真源），供
    build_chapter 把章末习题区内的条目从 ITEM 合同剔除（y 感知：同页条目须
    位于块头上方才保留）。"""
    rx = scan_skeleton._exercise_headings_re(headings)
    if rx is None:
        return None
    for p in range(int(start), int(end) + 1):
        fp = os.path.join(ext, 'page_%03d.json' % p)
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


def _exercise_region_start(ext, ch, start, end):
    """Return the page where 'EXERCISES FOR CHAPTER <ch>' begins, else None.

    Used to exclude exercise-region pages from the ITEM contract so that
    exercise problems (e.g. Strogatz `3.1.1`) are not mistaken for chapter
    items (examples/theorems).  Case-insensitive, space-optional to survive
    OCR like `EXERCISESFORCHAPTER3`.
    """
    head = re.compile(r'EXERCISES\s*FOR\s*CHAPTER\s*(\d+)', re.IGNORECASE)
    pat = str(ch)
    for p in range(start, end + 1):
        fp = os.path.join(ext, 'page_%03d.json' % p)
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
def _single_en_items(ext, start, end, book):
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
    items = extract_items_en(ext, start, end, want_examples=True,
                             section_scoped=book.section_scoped, single=True,
                             extra_labels=extra)
    kept = []
    for it in items:
        lab, _, num = it["key"].partition(" ")
        it = dict(it)
        it["key"] = f"{_canon_label(lab)}{num}"
        kept.append(it)
    return kept


def _extract_items(ext, ch, start, end, book, manual=None):
    primary = book.primary_type
    if primary == ORDINAL_HUM:
        # Humphreys GTM 9（config_setting 规则5 增量扩展）：条目头只印裸标签
        # （"Lemma."）或节内字母号（"Lemma A"），编号由所在小节隐式给出。
        # 专用抽取器跟踪当前小节，产出唯一化键 "Lemma §10.2B" / "Lemma §7.2"
        # （注入 § 记号使其不可被 B 层数字解析——引用号继承小节网格、天然稀疏，
        # 可解析会误报海量假断号；与 Ross 字母项同走优雅跳过路径）。
        return extract_items_hum(ext, start, end)
    if primary == ORDINAL_ROSS:
        # Ross 体例（ORDINAL_ROSS = 11，config_setting 规则5 增量扩展）：标签在前 +
        # 节内作用域编号（Example 2a / Proposition 4.1 / Axiom 1）。键保留原书印刷
        # 形态；章末习题区过滤由调用方 build_chapter 按 exercise_region_headings 做。
        return extract_items_ross(ext, start, end)
    if primary == ORDINAL_SINGLE:
        # CN 单级编号书（如李庆扬《数值分析》第5版：定理1 / 定义3 / 例12 /
        # 算法2 / 性质4——「标签+单一数字」、章内连续或节内重置）：既有抽取器
        # 均不覆盖（extract_items 只认多级号，EN 单级抽取器无中文标签词），
        # 按 config_setting 规则5 走增量扩展的中文单级抽取器。
        if getattr(book, "language", "cn") == "cn":
            return extract_items_cn_single(ext, start, end, groups=book.ordinal,
                                           manual_overrides=manual)
        return _single_en_items(ext, start, end, book)
    if primary == ORDINAL_CN3LAB:
        # CN 三级标签前缀书（如孙文祥《遍历论》：定理1.1.1 / 定义2.3.4，每类标签
        # 独立计数、每节重置）：键内嵌规范中文标签（`定理1.1.1`，与 type 9 的
        # `评注1.1.1` 同构），块首锚定天然排除三级小节标题与裸 C.S.N 公式号。
        # 按 config_setting 规则5 走增量扩展的 extract_items_cn3lab。
        return extract_items_cn3lab(ext, ch, start, end, groups=book.ordinal)
    if primary in (ORDINAL_EN, ORDINAL_EN3):
        if primary == ORDINAL_EN:
            items = extract_items_en(ext, start, end, want_examples=True,
                                     section_scoped=book.section_scoped)
        else:
            items = extract_items_en3(ext, ch, start, end, want_examples=True)
        kept = []
        for it in items:
            lab, _, num = it["key"].partition(" ")
            parts = num.split(".")
            # Chapter-scoped EN (book.chapter_first == True, the ORDINAL_EN /
            # ORDINAL_EN3 default): the first numeric component IS the chapter,
            # so drop cross-chapter forward references (first != ch).
            # Section-scoped EN books (book.chapter_first == False — first
            # component is the SECTION, no chapter component; e.g. "Theorem 3.1"
            # = §3 item 1) MUST keep these, so the filter is disabled. Single-
            # number keys are never filtered (they have no chapter/section slot).
            if book.chapter_first and len(parts) >= 2 and parts[0].isdigit() and int(parts[0]) != ch:
                continue
            it = dict(it)
            it["key"] = f"{_canon_label(lab)}{num}"
            kept.append(it)
        # ---- Merge manual overrides（OCR 漏识真实条目的 agent 回填通道）----
        # 与 extract_items 末尾的合并同构：此前 EN 路径没有 overrides 通道，
        # 印刷条目头被 OCR 整行丢失时（如 do Carmo Ch13 "2.7 Corollary …"）
        # 契约永远缺号，A 层 EXTRA 无法消除。override 约定：key=印刷裸编号
        # （如 "2.7"）、label=英文类别词、text=印刷标题。
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
    if (primary == ORDINAL_THREE_LEVEL and getattr(book, "language", None) == "en") \
            or primary == ORDINAL_APP:
        # EN three-level, label-first (e.g. Strogatz, Lasota & Mackey).  The
        # generic three-level extractor is CN-oriented and captures unlabeled
        # exercise numbers (`3.1.1`) as items; route to the label-first EN3
        # extractor, which requires an Example/Definition label and so naturally
        # excludes exercises.  ORDINAL_APP（附录字母章位，type 13）的条目印成
        # `Definition A.1.1` / 裸 `A.1.5`（Weibel Appendix A），同属 label-first
        # 三级形态，由 extract_items_en3 的附录正则（EN3_APP_RE / EN3_APP_BARE_*）
        # 覆盖——键仍走 normkey 裸号（"A.1-1"），类型由节点 type 承载。
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
        items = extract_items_en3(ext, ch, start, end, want_examples=True)
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
    if primary in (ORDINAL_GM, ORDINAL_ROMAN):
        items, _, _ = extract_items_gm(ext, ch, start, end, manual_overrides=manual)
        return items
    if primary == ORDINAL_VAKIL:
        items, _, _ = extract_items_vakil(ext, ch, start, end, manual_overrides=manual)
        return items
    # three_level / two_level 全部走 extract_items（内部按 ordinal 选路）
    items, _, _ = extract_items(ext, ch, start, end, manual_overrides=manual, cfg=book)
    return items


# ---------------------------------------------------------------------------
# 单章结构构建
# ---------------------------------------------------------------------------
def _find_numbered_heading_page(ext, num, lo, hi, min_y=None):
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
    """
    pat = re.compile(
        r'^[\*§8Ss$]?\s*' + re.escape(str(num)) + r'(?:[\.．:：]|[\s\u00a0]+)\s*[A-Za-z]')
    pat_glue = re.compile(r'^[\*§8Ss$]?\s*' + re.escape(str(num)) + r'(?=[A-Za-z])')
    for p in range(int(lo), int(hi) + 1):
        fp = os.path.join(ext, 'page_%03d.json' % p)
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
            for ln in blk_text(b).split('\n'):
                ln = ln.rstrip('$').strip()
                if not ln or len(ln) > 70 or ln.endswith((',', ';')):
                    continue
                m = pat.match(ln) or pat_glue.match(ln)
                if m:
                    if (p == int(lo) and min_y is not None
                            and (by is None or by <= float(min_y))):
                        continue    # 目录命中本身 / 其上方的更早行，跳过
                    rest = ln[m.end():]
                    if len(re.findall(r'[A-Za-z\u00c0-\u017f\u4e00-\u9fff]', rest)) >= 2:
                        return p
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

    # 1) skeleton 原始行
    rows = scan_skeleton.scan(ext, ch, start, end, mode,
                              section_depths=section_depths,
                              chapter_first=book.chapter_first,
                              exercise_headings=getattr(book, 'exercise_region_headings', None) or None,
                              plain_sec_heads=(ordinal == ORDINAL_HUM))
    ex_rows = [r for r in rows if r[1] == "EXER"]

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
        sec_rows = [("md", "SEC", n, title) for (n, title) in md_secs]
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

    # 3) 抽取器条目（权威 ITEM，排除练习类 + 练习区页）
    #    习题块（"EXERCISES FOR CHAPTER N" 起至章末）内的页码一律不从抽取器
    #    进入 ITEM 合同，否则习题题号（如 Strogatz `3.1.1`）会被误判为
    #    Example/Definition 条目，造成重复键、错类型、乱序。
    raw_items = _extract_items(ext, ch, start, end, book, manual=manual)
    ex_start = _exercise_region_start(ext, ch, start, end)

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
    _exer_num_re = re.compile(
        r'((?:[A-Za-z][.\-])?\d{1,2}[.\-]\d{1,2}(?:[.\-](?:\d{1,3}|[A-Z]))?)\.?$')
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
        ex_rows.append((it.get("page", 0), 'EXER', num, title, None))

    items = [it for it in raw_items
             if (it.get("label") or "").strip() not in _EXERCISE_LABELS
             and (ex_start is None or it.get("page", 0) < ex_start)]

    # 3a-2) Ross 体例章末习题块（exercise_region_headings 声明）：块头起至章末
    #    的页不再进 ITEM 合同。y 感知：与块头同页的条目，仅当其块顶 y 在块头
    #   （y 较小 = 页面上方）之前才保留；_item_pos 找不到位置时返回 -1 → 保留
    #    （宁缺勿滥的反向：真条目不因 OCR 定位失败而丢失，漏项交源侧回填兜底）。
    _ex_headings = getattr(book, 'exercise_region_headings', None) or None
    if _ex_headings:
        ex_pos = _exercise_block_pos(ext, ch, start, end, _ex_headings)
        if ex_pos is not None:
            _ep, _ey = ex_pos
            _kept = []
            for it in items:
                pos = _item_pos(ext, it)
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
        prev = _by_key.get(k)
        if prev is None:
            _by_key[k] = it
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
            _by_key[k] = it
    items = sorted(_by_key.values(),
                   key=lambda x: ((x.get("page") or 0), _nat_key_digits(x["key"])))

    # 4) 章节骨架：skeleton SEC ∪ 条目/练习派生章节号
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
        for _op in list(_opener_pages):
            _ys = [float(_r[4]) for _r in _first_hit.values()
                   if _r[0] == _op + 1 and _r[4] is not None]
            if _ys and all(y < 350.0 for y in _ys):
                _opener_pages.add(_op + 1)
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
                pg = _find_numbered_heading_page(ext, num, p, end, min_y=y) or p
                y = None
            elif getattr(book, 'chapter_local_sections', False):
                # chapter-local 节来自 md，无源扫描页码；用源 "N. Title"
                # 首现页作为真实页码，供条目按页就近归节。
                pg = _find_chapter_local_section_page(ext, ch, int(num), start, end)
                y = None
            else:
                pg = p
            sec_pages[num] = pg
            # 节头 (page, y) 进 sec_pos：同页「条目在上、节头在下」的 y 感知归并
            # （谷超豪《数学物理方程》实测：ch6 性质4 与 §5 节头同页）。
            sec_pos.setdefault(num, (pg, float(y) if y is not None else 0.0))
            if title and not sec_titles.get(num):
                sec_titles[num] = title

    # 无序号标层（section_types 含 0）：注入「agent 校验识别」步骤产出的权威
    # 小节清单（key 用 "U{n}" 区分于编号小节）。OCR 无数字段，scan_skeleton
    # 的深度检测对无序号标标题完全失明且易编造假小节（违反保真），故此处
    # 直接消费识别产物 _recognized_sections.json，不再走 OCR 正则。
    if getattr(book, "sections_unnumbered", False):
        for _i, (_ut, _up, _uy) in enumerate(
                _recognized_sections(ext, ch, start, end), 1):
            _uk = "U%d" % _i
            sec_pages.setdefault(_uk, _up)
            sec_pos[_uk] = (_up, _uy)
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
                                  chapter_scoped=getattr(book, 'chapter_scoped_items', False)),
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
    if any(re.match(r'^[A-Za-z]', (it.get("key") or "")) for it in items):
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
        node["sub_sec"] = []
        sec_nodes[n] = node

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
                                  chapter_scoped=getattr(book, 'chapter_scoped_items', False))
        title = _clean_title(it.get("text", ""), it["key"])
        name = (f"{it['key']} {title}".strip()) if title else it["key"]
        node = _node(it["key"], _type_of(it.get("label")), name, it["page"])
        pos = _item_pos(ext, it)
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
        node = _node(num, "exercise", name, p)
        _place(node, sec_key, p)

    # 6) 章节内子节点按（页码, 页内 y, 自然序）稳定排序（2026-08-29 升级为
    # y 感知：同页上「条目 vs 嵌套子节头」的先后只看 key 自然序会颠倒——
    # Koopman ch5 实测 Remark 5.5(y=864) 在 §5.4.1 节头(y=1112) 之前，自然序
    # 却把节头排前 → B 层乱序。y 取自源页锚定：条目用 _item_pos，编号节头用
    # _numbered_heading_y；取不到 y 时回退 0（保持旧行为）。
    def _doc_sort_key(child):
        nid = id(child)
        if nid not in _doc_y_cache:
            page = int(child.get("page_start") or 0)
            ckey = str(child.get("key") or "")
            y = None
            if child.get("type") == "section":
                if not ckey.startswith("U"):
                    y = _numbered_heading_y(ext, ckey, page)
                if y is None:
                    t = (child.get("name") or "").strip()
                    t_no = re.sub(r'^[\dA-Z]+(?:\.[\dA-Z]+)*\s*', '', t).strip()
                    pos = _find_title_pos(ext, t_no or t, page, page) if t else None
                    y = pos[1] if pos else None
            else:
                pos = _item_pos(ext, {"key": ckey, "page": page,
                                      "text": child.get("name") or ""})
                y = pos[1] if pos and pos[1] is not None and pos[1] >= 0 else None
            _doc_y_cache[nid] = float(y) if y is not None else 0.0
        return (int(child.get("page_start") or 0), _doc_y_cache[nid],
                _nat_key_digits(child["key"]))

    _doc_y_cache = {}
    for n in all_sec_nums:
        sec_nodes[n]["sub_sec"].sort(key=_doc_sort_key)

    # 6b) 小节按数字层级嵌套（Koopman 书实测，2026-08-29）：契约树必须与原书
    # 标题层级同构——"1.2.1" 是 "1.2" 的子节、挂进其 sub_sec；"1.2.1.1" 再挂进
    # "1.2.1"。此前所有 section 平铺在章下，写作契约与渲染骨架都丢失层级。
    # 父键 = 去掉末段；父不存在（编号洞，如书直接从 1.2 跳 1.2.2）→ 留在顶层，
    # 不编造父节。无序号标节（"U{n}"）与字母子块不参与嵌套。子节在父 sub_sec
    # 内与条目一起按 (page_start, 自然序) 重排，保持文档顺序。
    def _sec_depth(key):
        return len(re.findall(r"\d+", str(key)))

    top_secs = []
    for n in all_sec_nums:
        node = sec_nodes[n]
        if n.startswith("U") or _sec_depth(n) < 2:
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
        node["sub_sec"].sort(key=_doc_sort_key)
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
    # 附录章名归一（命名单点）：契约章名约定 "{key} {title}"，下游
    # render_draft/_final_md_name 据此渲染 "# Appendix A: title" /
    # "AppendixA_title.md"。chapter_map 若登记 "Appendix A: Category Theory
    # Language"（或 "附录A：…"），title 已含序标，直接拼接会得到双前缀
    # "A Appendix A: …" → 渲染 "# Appendix A: Appendix A: …" / 文件名
    # "AppendixA_Appendix_A.md"。故剥离 title 首部的 "Appendix {ch}" / "附录{ch}"
    # （含冒号）；剥后为空（仅登记 "Appendix A"）时保留原样退化，不产生空标题。
    _m_app = re.match(r'^\s*(?:appendi(?:x|ces)\s+%s|附录\s*%s)\b\s*[:：]?\s*(.*)$'
                      % (re.escape(str(ch)), re.escape(str(ch))),
                      ch_title or '', re.IGNORECASE)
    if _m_app and _m_app.group(1).strip():
        ch_title = _m_app.group(1).strip()
    ch_name = (f"{ch} {ch_title}".strip()) if ch_title else str(ch)
    chapter = _node(str(ch), "chapter", ch_name, start)
    chapter["sub_sec"] = sub
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
    # —— 2026-08-29 重构：**一步产出完整契约**——build_structure 生成骨架后立即
    # 调 build_chapter_contract 挂入正文内容（description / proof / text /
    # formula / image 内容块）并写回同一文件，不再有独立的 attach_content 步骤；
    # ch{N}.json 自此即"整章信息的唯一载体"，后续子流程只做校验与回填。
    # 不再产出全书单文件 book_structure.json；分章文件即结构契约唯一真源。
    from attach_content import build_chapter_contract
    out_sub = os.path.join(ext, "book_structure")
    os.makedirs(out_sub, exist_ok=True)
    built = 0
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
        full, stats = build_chapter_contract(ext, node.to_dict())
        with open(out, "w", encoding="utf-8") as f:
            json.dump(full, f, ensure_ascii=False, indent=2)
        built += 1
        n_item = sum(1 for _ in _iter_items(chapter)
                     if _["type"] not in ("exercise", "section", "chapter"))
        n_ex = sum(1 for _ in _iter_items(chapter) if _["type"] == "exercise")
        n_sec = sum(1 for _ in _iter_items(chapter) if _["type"] == "section")
        print("%-9s BUILD | sections=%d items=%d exercises=%d "
              "text=%d formula=%d image=%d proof=%d desc=%d noise=%d -> %s"
              % (chapter_label(ch), n_sec, n_item, n_ex,
                 stats["text"], stats["formula"], stats["image"],
                 stats["proof"], stats["description"], stats["noise_dropped"],
                 os.path.basename(out)))
    print("BOOK -> %s | chapters built=%d" % (out_sub, built))
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
