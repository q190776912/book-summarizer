"""config/verify_config/make_config.py — 存量书「书级配置」best-effort 引导脚本

为还没有 / 想快速重建 `_extract/verify_config.json` 的书生成一份**起始**配置。
这是 BEST-EFFORT 检测，明确标注「需人工核对」，不声称自动正确。

用法：
    python config/verify_config/make_config.py <extract_dir> [--force]

行为：
  1. 若 <extract_dir>/verify_config.json 已存在且非 --force：打印跳过并 exit 0。
  2. best-effort 检测 ordinal 与 formula（两者都**全量**扫描整本书，整书聚合后
     确认全局配置，**禁止抽样前 N 页**）：
     - **全量**扫描整本书所有 page_*.json（sorted(glob)，不切片前 N 页），用带
       位置护栏 + 交叉引用过滤的标签扫描收集『作为编号标题出现』的条头串，再交给
       `OrdinalStyle.detect_style`（lib/ordinal_styles.py，与 md 侧抽键**同一套判定
       标准**）按特异性优先投票出编号族：
         * 单级 `定理2` → 1；两级 `定义1.1` → 2；三级 `定理1.1.1` → 3；
           附录字母章位三级 `Definition A.1.1` → 13、两段 `Theorem B.2` → 14。
         * 🔴 只产出 ordinal_styles 实现的码 {1,2,3,8,12,13,14}；旧码 4/9/10/11 已于
           2026-09-21 彻底退役并折入就近规范码（4→2、9/10→3、11→1），加载期不再有任何映射。
         * 8（vakil，序标在前 + 第三维字母）与 12（hum，裸标签 / 纯字母序标）无法被
           数字锚定的页扫投票命中，改由 chapter_map 显式声明采纳。
         * 一条编号条头都检不到 → family=None，**不回退默认 3**，调用方省略 ordinal 组。
     - formula：detect_formula() **全量**扫描所有 page_*.json 的 text[]，统计
       standalone (N)/（N）与 (C.N)/Eq. C.N/式（C.N）的数量，整书聚合并确认全局
       公式配置（type/depth/scope）。单分量 ≫ 多分量 → type1/depth1（scope 由
       是否「全书数值回落」判定：回落→scope3 节级重排，否则→scope1 全书）；多分量
       多 → type2/depth2，scope 由**首分量重置行为**派生（逐章重启→2 / 全书连续→1），
       首分量证据不足（仅见单一前缀）时**不写 scope**——scope 无默认值，交 agent 依
       书确定；都抽不到返回 None（不写 formula 键）。
  3. 写出 {"ordinal": [<组>, ...], "language": <按实际检出的标签词形判 en / cn>}：
     - 在同一遍整书扫描中，按 LABEL_FORMS 收集『作为编号标题出现』的全部条目类型
       标签词（含 Remark/评注/注、Exercise/习题/练习/问题/Problem、Axiom/公理 等，
       不再刻意排除），**并按下文规则分组**：
       * 同一遍扫描同时记录每条目标签词及其相邻编号组件；
       * `_group_headings_by_counter` 判定哪些标签词**同升序（共享一个计数器）**——
         即在同一个 scope 重置窗口内彼此不独立归 1 的，归入同一个 group 的 name；
       * 各自有独立编号序列（在同样窗内独立从 1 重排）的标签词，各自成独立 group。
       * 这正是 `ordinal` 数组的设计意图：一同升序的进同一对象，不升序的新增对象。
       * 未检出任何条目类型时回退为单个 [["uncat"]] 兜底组。
     - 若 detect_formula 非 None 再写入 "formula": {...}。
     并打印醒目提示：四级子小节书（1.1.1.1）需手动补 `section_types`；
     检出的分组若与实际不符请手动合并/拆分后再跑 verify。
4. 同时显式写出 `section_types`（D 层要校验的**小节层级**，深度由 `SECTION_TYPE_DEPTH`
   派生、**不单独输出字段**；即书里实际有 `## §N` / `## §N.M` / `## §N.M.K` /
   `## §N.M.K.L` 几级标题——与条目编号深度正交，不能由 ordinal 类型直接推定）。判定口径见
   `_detect_section_hierarchy`：扫描整书 OCR，识别**任意深度**（目前封顶 4 级：
   2/3/4 级）的"带标题、非条目标签"真小节头（如 `20.5` / `20.5.1` / `1.2.1.3`），
   据此给出正确层级 `[1, 2, ...]`。该书既有二级小节（20.5）也有三级小节（20.5.1）
   这类**混合深度**书，以及四级（1.1.1.1）的书，都能被正确识别——不再被旧逻辑一律
   强锁 `[1, 2]` 而漏掉三级小节、也不再由条目号派生幽灵小节。

⚠️ 相位护栏：ordinal/formula 探测均要求 MM Repair 已完成（完成标记 _extraction_done.json
   存在；该标记仅在 MM Repair 模式 A+B 全部 apply 回 page_*.json 后由主 Agent 写出，不等同
   后台文本流水线"文本 100%"中间信号），否则跳过探测、打印提示并返回默认值——**禁止**在
   MM Repair 未完成（尤其模式 A 视觉审读未做）时对前若干页抽样降级。判定不清时以
   `verify/verify.md` 与各层 `ref/*.md` 的语义为准，人工核对后再跑校验。

⚠️ 本脚本只生成「起始」配置，不覆盖任何已有文件（除非 --force），也不声称正确。
"""
import os
import sys
import time
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
from lib.util import blk_text  # noqa: E402

import os
import sys
import json
import re
import glob

sys.stdout.reconfigure(encoding='utf-8')
from typing import List
from lib.numbering import ordinal_depth
from lib.numbering import is_fig_label_name as _is_fig_kw  # SSOT（与 figure_io / primary_group 同源）
from lib.ordinal_styles import OrdinalStyle
from verify_config import (ORDINAL_LANGUAGE_DEFAULT,
                           ORDINAL_APP, ORDINAL_APP2, ORDINAL_HUM,
                           SCOPE_BOOK, APPENDIX_NAME_RE, SUPPLEMENT_NAME_RE,
                           MAP_KEY_SPECIAL_SAME_STYLE)
from data.chapter_map.chapter_map import KIND_APPENDIX, KIND_SUPPLEMENT


def _load_old_section_cfg(cfg_path, section_key="ch"):
    """旧 verify_config.json 里**本段**的配置字典（map / 旧扁平两种格式都吃）。

    map 格式取 ``data[section_key]``；旧扁平格式（顶层就是字段）取顶层——
    当年扁平配置的顶层声明对附录/补篇同样生效（无 appendix 子配置时
    ConfigLoader 整章回退主配置），所以回贴扁平顶层 = 零回归而非跨段污染。
    读不到 / 解析失败 → ``{}``（调用方据此保持探测默认值，绝不静默放松）。
    """
    try:
        with open(cfg_path, encoding="utf-8-sig") as f:
            data = json.load(f) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    if any(k in data for k in ("ch", "appendix", "supplement")):
        sub = data.get(section_key)
        return sub if isinstance(sub, dict) else {}
    return data


def _load_old_ordinal(cfg_path, section_key="ch"):
    """Return the `ordinal` array from an existing verify_config.json, or [].

    🔴 map-aware（2026-09-08 修复）: 最新 schema 把每个子配置嵌套在外层键
    ``"ch"`` / ``"appendix"`` / ``"supplement"`` 下, ``ordinal`` 不再位于顶层。
    若事后对「已转 map 格式」的书重跑 ``make_config.py --force``, 旧顶层
    ``ordinal`` 读取会落空、Figure 组丢失 —— 这是转格式引入的回归。改读
    ``data[section_key]["ordinal"]`` 即可按子配置保真回贴; section_key 由
    ``_build_config_dict`` 透传（正文="ch", 附录/补篇=各自键）。

    旧扁平格式（顶层有 ``ordinal``）仍走原分支, 零回归。
    """
    try:
        with open(cfg_path, encoding="utf-8") as f:
            data = json.load(f) or {}
    except Exception:
        return []
    # map-format: 读匹配子配置的 ordinal
    if isinstance(data, dict) and any(k in data for k in ("ch", "appendix", "supplement")):
        sub = data.get(section_key)
        if isinstance(sub, dict):
            return sub.get("ordinal", []) or []
        return []
    # legacy flat format: 顶层 ordinal
    return data.get("ordinal", []) or []


def _load_old_formula(cfg_path, section_key="ch"):
    """旧配置同段 `formula` 中 operator 登记的键（`ignore` / `bare_number`）。

    `detect_formula` 只能从书源**探测** `type`/`scope`/`letter_ch`；而
    `ignore`（噪声账本，如 Lee 正文的 `"7.35"`）与 `bare_number`（裸排编号
    开关，Lee 散文 `1-11` Problem 标签须关）是**人工判断**，探测层无法重建。
    重生成配置若不回贴，登记过的噪声会静默复活 → 假 MISSING。与
    `_load_old_ordinal` 同构：map 格式读 ``data[section_key]["formula"]``，
    扁平格式读顶层 ``formula``。无旧配置 / 无 formula / 无登记键 → ``None``。
    """
    try:
        with open(cfg_path, encoding="utf-8-sig") as f:
            data = json.load(f) or {}
    except Exception:
        return None
    if isinstance(data, dict) and any(k in data for k in ("ch", "appendix", "supplement")):
        sub = data.get(section_key)
        fc = sub.get("formula") if isinstance(sub, dict) else None
    else:
        fc = data.get("formula")
    if not isinstance(fc, dict):
        return None
    out = {}
    if "ignore" in fc:
        out["ignore"] = fc["ignore"]
    if "bare_number" in fc:
        out["bare_number"] = fc["bare_number"]
    # 🔴 `known_book` 同样是**人工判断**（印面目视确证「书源确有、抽取器漏挂」的
    # 编号，见 flows/write-source/write-source.md 闸门 ⑭ 的登记纪律），没有探测器
    # 能重建它。`--force` 重生成若不回贴，登记即静默消失 → Q 层重新把写手照印面写对
    # 的 `\tag` 判成 FABRICATED（两头堵）。`known_book_audit` 是它的证据账本
    # （编号 / 章 / 理由 / 时间），必须同号同迁，否则审计线索断裂。
    # 由 `config/verify_config/register_formula.py` 写入，禁止手改本文件。
    if "known_book" in fc:
        out["known_book"] = fc["known_book"]
    if "known_book_audit" in fc:
        out["known_book_audit"] = fc["known_book_audit"]
    return out or None

# --- section hierarchy (D-layer) -------------------------------------------
# `section_types` (ORDINAL-DEPTH codes, NOT "chapter/section" role names) MUST
# NOT be inferred from the ordinal type alone — it is a PER-LEVEL list ordered
# from the CHAPTER level (element 0) down to the deepest `## §` level; its k-th
# element is the number of numeric components that level's `## §` token carries
# (1 -> `## §N`, 2 -> `## §N.M`, 3 -> `## §N.M.K`, 0 -> that level is
# UNNUMBERED — e.g. `## § <标题>`, OR the chapter is the file `# 第N章` with no
# `## §` number).  This is ORTHOGONAL to the item-numbering depth.  Each code's
# depth is FIXED and resolved via SECTION_TYPE_DEPTH in verify_config.py — it is
# NOT a separate stored `section_depths` field.  The LIST LENGTH must equal the
# number of section hierarchy levels (chapter INCLUSIVE): a chapter + unnumbered
# subsection book is `[0, 0]` (two levels), NOT `[0]` (which would describe a
# single level with no subsections).  A type-3 book can legitimately be either:
#   * a genuine 3-level-section book  (md has `#### §1.1.1`; items like
#     `1.1.2 定义`)                                  -> section_types = [1, 2, 3]
#   * a Kreyszig-shaped book (md only `## §1.3`; items like `1.3-4 Theorem`,
#     deepest component IS the item counter, NOT a subsection)
#                                                          -> section_types = [1, 2]
# ⚠️ make_config always PREPENDS the chapter prefix `1` (it assumes the chapter
# is represented by a `## §` number), so it CANNOT emit `[0, 0]` for an
# unnumbered-chapter book whose chapter is the file (`# 第N章`, no `## §`
# number) — those books (e.g. Silverman) require a hand-written `[0, 0]`
# override.  `_detect_section_hierarchy` is for NUMBERED books only.  The only
# reliable way to tell a genuine 3-level-section book from a Kreyszig-shaped one
# is to scan the raw OCR: does the deepest level k (= item depth) contain any
# k-component numbered line that is a GENUINE section header (a number followed
# by a non-label TITLE) rather than a LABELED ITEM?  See
# `_detect_section_hierarchy` for the implementation.
_SEP_RE = re.compile(r'[.\-–·/．－〜]')
# Capture ONLY the leading number (optionally prefaced by OCR-glued §/8).  The
# trailing title is inspected separately via `rest` so a label keyword's first
# letter is never stripped off (the old `\s+\S` suffix ate the 'T' of 'Theorem'
# and turned labeled items into phantom section headers).
# 🔴 节标题分隔符只接受「点族」(`.`/`．`/`·`/`–`/`－`/`〜`)，**刻意排除分数斜杠
# `/` 与 ASCII 连字符 `-`**——二者是数学表达式/范围运算符，不是章节号分隔符。
# 否则 `1/1 and 2/1.`、`3-2i`、`1-6i— 37` 这类 OCR 数学/页码碎片会被误判为
# 「二级序标节标题」，凭空给 `section_types` 加层级（Silverman 实测中了 3 个，
# 导致 make_config 误生成 [1,2] 覆盖正确的手写 [0]）。OCR 点号变体（en-dash /
# fullwidth-hyphen / fullwidth-dot / middle-dot / wave-dash）保留为合法分隔符。
_SEC_HEAD_RE = re.compile(r'^(?:§|8)?\s*(\d+(?:[.–·．－〜]\d+)*)')
# 附录字母章号节标题：`A.1 Categories` / `A.6 Adjoint Functors`（章位为单字母）。
_SEC_HEAD_APP_RE = re.compile(r'^\s*([A-Za-z])\s*[.–·．－〜]\s*(\d+(?:[.–·．－〜]\d+)*)')
# 附录节标题的长度上限：超过即判为「编号条目」（`A.1.5 A morphism …`）而非标题。
# 实测最长真标题 `A.5 Limits and Colimits (see Chapter 2, section 6)` = 50 字符。
APPENDIX_HEAD_MAX = 60
_LABEL_KW_RE = re.compile(
    r'(定义|定理|引理|命题|推论|例|公理|练习|评注|准则|图|表|'
    r'Definition|Theorem|Lemma|Proposition|Corollary|Example|Axiom|Exercise|'
    r'Remark|Figure|Fig|Table)')


def _section_header_depth(txt, max_depth=4, letter_chapter=False):
    """If `txt` is a GENUINE section header, return its component-count depth
    (>= 2); otherwise None.

    `letter_chapter=True` switches to the APPENDIX shape, where the chapter slot
    is a LETTER: ``A.1 Categories`` / ``A.6 Adjoint Functors`` (2 components).
    Such a heading is also required to be SHORT (<= `APPENDIX_HEAD_MAX` chars) —
    in an appendix the bare ITEM lines (``A.1.5 A morphism f: B -> C is called
    monic if…``) carry the very same 3-component letter shape, and only length
    separates a title from a numbered entry.

    A genuine section header is a dotted number (>= 2 components) followed by a
    non-label TITLE — e.g. ``20.5 Sparse Polynomial``, ``20.5.1 Eigenfunctions``,
    ``1.2.1.3 Deep``, but NOT a labeled item (``Theorem 20.4``), a formula
    number (``(20.53)``), a figure/table label (``Figure 20.1``), nor a bare
    number without a title.  The chapter-level number (a single component, e.g.
    ``20``) is the chapter ITSELF, not a section, so it is excluded (depth < 2).

    This detector is deliberately INDEPENDENT of the item-numbering style —
    a book may number its items one way (e.g. EN two-level ``Theorem 20.4``)
    yet nest its sections to ANY depth.  ``max_depth`` caps the search at a sane
    upper bound (default 4 = chapter + 3 nested levels, matching the
    SECTION_ROLE_CODES cap in verify_config.py) so a runaway OCR artifact can
    never produce an absurd hierarchy; roles 5/6 were never observed in any
    book and were dropped.
    """
    if letter_chapter:
        m = _SEC_HEAD_APP_RE.match(txt)
        if not m:
            return None
        if len(txt) > APPENDIX_HEAD_MAX:
            return None          # 长行 = 编号条目（A.1.5 …）而非节标题
        comps: List[str] = [m.group(1).upper()]
        comps += [x for x in _SEP_RE.split(m.group(2)) if x]
    else:
        m = _SEC_HEAD_RE.match(txt)
        if not m:
            return None
        comps = [x for x in _SEP_RE.split(m.group(1)) if x]
    return _header_depth_from_comps(txt, m, comps, max_depth)


def _header_depth_from_comps(txt, m, comps, max_depth):
    """Shared tail of `_section_header_depth`: validate the parsed components.

    `comps[0]` may be a LETTER when the caller parsed an appendix heading
    (`A.1 Categories` -> ``['A', '1']``); every LATER segment must be numeric.
    """
    if not m:
        return None
    if not comps:
        return None
    # 🔴 防御：除可能的字母章位外，每个序标段必须是纯数字（挡掉 `6i`、`2x` 这类
    # 带字母的数学碎片，即便它们绕过了上面的分隔符限制）。
    tail_digits = comps[1:] if not comps[0].isdigit() else comps
    if not all(c.isdigit() for c in tail_digits):
        return None
    if not (comps[0].isdigit() or (len(comps[0]) == 1 and comps[0].isalpha())):
        return None
    if len(comps) < 2 or len(comps) > max_depth:
        return None
    rest = txt[m.end():].lstrip()
    # 🔴 容忍序标后的点号（AMS 体例「1.1. Guide」/ do Carmo「1-2. Parametrized
    # Curves」）：数字段后紧跟句点再接标题。此处必须与消费方
    # ``scan_skeleton._section_header_info`` 的 lstrip('.．。') 口径一致——
    # 两边不一致时（本函数严格、scan_skeleton 宽松）会产生「节头能抓但
    # section_types 只给 [1]」，下游按 depths 过滤后整本书的小节全漏
    # （Han-Lin《Elliptic PDEs》实测：1.1. Guide / 1.2. Mean Value Properties
    # 全部漏检，契约退化为一个页码页眉冒充的伪节）。
    rest = rest.lstrip('.．。').lstrip()
    if not rest or not rest[0].isalnum():
        return None  # number with no following title -> not a header line
    title = rest[:12]
    if _LABEL_KW_RE.search(title):
        return None  # labeled item / figure / table, not a section header
    if not re.search(r'[A-Za-z一-鿿]', title):
        return None
    return len(comps)


def _detect_section_hierarchy(extract_dir, max_depth=4, pages=None,
                              letter_chapter=False):
    """Return the D-layer `section_types` (role-code) list for this book.

    The returned list enumerates the nested section levels present in the
    book's SOURCE (chapter / section / subsection / sub-subsection) as ROLE
    CODES (1..4).  It is ORTHOGONAL to the item-numbering depth — a book may
    number its items one way (e.g. EN two-level ``Theorem 20.4``) yet nest its
    sections to ANY depth (``20.5``, ``20.5.1``, ...).  We therefore SCAN THE
    RAW OCR
    for genuine section headers of EVERY depth rather than inferring anything
    from the item depth.

    A genuine section header is a dotted number (>= 2 components) followed by a
    non-label TITLE (see ``_section_header_depth``).  The detected depth set
    (>= 2) is combined with the mandatory chapter prefix (depth 1) to form
    ``[1, 2, 3, ...]``.  The previous implementation short-circuited to
    ``[1, 2]`` for two-level item books and only OCR-scanned when the item depth
    was exactly 3 — that wrongly forced every EN-two-level / Kreyszig-shaped
    book to at most two section levels and missed genuine deeper subsections
    (e.g. Koopman's ``20.5.1``), feeding phantom sections derived from item
    numbers into the per-chapter contract (``book_structure/ch{N}.json``).

    `max_depth` bounds the hierarchy (default 4, matching the SECTION_ROLE_CODES
    cap); roles 5/6 are not emitted (never observed in the corpus).

    `pages` restricts the scan to an explicit list of `page_*.json` paths (the
    APPENDIX generator passes only the appendix page range — an appendix
    routinely uses a different section shape than the body, and mixing the two
    ranges would fabricate levels neither part actually has).
    """
    depths = set()
    pages = pages if pages is not None else sorted(
        glob.glob(os.path.join(extract_dir, 'page_*.json')))
    for pg in pages:
        try:
            with open(pg, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        for b in data.get('text', []):
            txt = blk_text(b).strip() if isinstance(b, dict) else ''
            if not txt:
                continue
            d = _section_header_depth(txt, max_depth=max_depth,
                                      letter_chapter=letter_chapter)
            if d is not None:
                depths.add(d)
    if depths:
        return [1] + sorted(d for d in depths if d >= 2)
    # 🔴 探测不到任何「带编号」节头：本段小节很可能是**无编号主题行**
    # （Lee《ISM》正文 `Topological Manifolds` 与附录 `Topological Spaces`
    # 同为无编号），而上面的正则只认点分数字、对此完全失明。此时按「agent
    # 校验识别」产出的权威清单 `_recognized_sections.json` 推导无编号层级数
    # （role 0），而不是返回无信息量的 `[1]`（＝该层级无小节）——后者会让
    # **条目号顶替成 section**（附录小节变成 `## §A.4`）。
    # 🔴 正文与附录走**同一套逻辑**（仅按 letter_chapter 区分取哪半份清单），
    # 不存在「附录单独借用正文配置」的第二条路径。
    _n = _unnumbered_levels_from_recognized(extract_dir, letter_chapter)
    if _n:
        return [0] * _n
    return [1]


def _numeric_local_chapter_ranges(extract_dir):
    """Numeric-chapter page ranges ``[(ch, start, end), ...]`` from chapter_map.json.

    Only chapters whose key is a plain number are returned — appendix/supplement
    letters never carry the global-§ numeric-subsection shape and would only add
    noise to the probe.  Missing file / malformed entries degrade to ``[]``.
    """
    cm_p = os.path.join(extract_dir, 'chapter_map.json')
    if not os.path.exists(cm_p):
        return []
    try:
        cm = json.load(open(cm_p, encoding='utf-8-sig'))
    except Exception:
        return []
    nodes = cm.get('chapters') if isinstance(cm, dict) else cm
    if not isinstance(nodes, list):
        return []
    out = []
    for e in nodes:
        if not isinstance(e, dict):
            continue
        ch = e.get('ch', e.get('num', e.get('chapter')))
        if str(ch)[:1].isdigit():
            out.append((ch, e.get('start'), e.get('end')))
    return out


def _detect_numeric_local_sections(extract_dir, ordinal, language, chapter_first):
    """(fire, info): does this book print single-number global § heads whose
    bodies hold bare ``N. Title`` sub-heads restarting per § (Arnold ODE shape)?

    Delegates to ``scan_skeleton.numeric_local_subsection_probe`` (the SAME
    production scanner used by build_structure) so detection can never drift
    from what the contract will actually contain.  Any import/probe failure
    degrades to ``(False, {})`` — a conservative no-op that leaves every other
    book on its existing 2-level path (zero regression).
    """
    if ordinal is None:
        return False, {}
    try:
        import scan_skeleton as _S
        mode = _S._mode_for_ordinal(ordinal, language)
        ranges = _numeric_local_chapter_ranges(extract_dir)
        if not ranges:
            return False, {}
        return _S.numeric_local_subsection_probe(
            ranges, mode=mode, default_dir=extract_dir,
            chapter_first=bool(chapter_first))
    except Exception as e:                      # pragma: no cover - defensive
        print(f"[make_config] numeric_local_sections 探测异常（保守 False）：{e}")
        return False, {}


def _unnumbered_levels_from_recognized(extract_dir, letter_chapter=False):
    """无编号小节的**层级数**：取 `_recognized_sections.json` 中本段体例
    （正文=数字章 / 附录=字母章）所有章的 level 最大值。

    `_recognized_sections.json` 由「agent 校验识别」步骤产出，是**唯一可靠**
    的无编号小节来源（OCR 正则对无数字标题失明）。元素形如
    ``{"title": ..., "level": 1|2, "page": ...}``；缺 level 或旧格式裸字符串
    视为 level 1。无清单/层级为 0 时返回 None，调用方回退 `[1]`（零回归）。
    """
    fp = os.path.join(extract_dir, "_recognized_sections.json")
    if not os.path.exists(fp):
        return None
    try:
        with open(fp, encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    max_lv = 0
    for k, entries in data.items():
        # 章体例须与本段一致：正文段取数字章，附录/补篇段取字母章
        if bool(not str(k)[:1].isdigit()) != bool(letter_chapter):
            continue
        for e in (entries or []):
            lv = e.get("level") if isinstance(e, dict) else None
            try:
                max_lv = max(max_lv, int(lv or 1))
            except (TypeError, ValueError):
                max_lv = max(max_lv, 1)
    return max_lv or None




# --- entry-type label vocabulary (detected as numbered headings) -----------
# The set of theorem-ish / remark labels that can appear as NUMBERED HEADINGS
# in a math book.  make_config scans the whole book and detects which of these
# actually occur; it then GROUPS them by whether they share ONE ascending
# counter (see `_group_headings_by_counter`) — labels that ascend together go
# in ONE group's `name`, labels with an independent counter get their OWN
# group.  This is what the `ordinal` ARRAY is FOR: it is NOT a fixed "main
# types vs others" split.  Order = stable output order within a group.
# `form_by_lower` maps a matched (possibly OCR-lowercased) surface form back
# to the canonical spelling written into `name`.
#
# ⚠️ Exercise / 习题 / 练习 / 问题 / Problem are EXCLUDED from LABEL_FORMS
# here — but for a NARROWER reason than "exercises are never verified".  Per
# docs/writing-rules.md §习题（练习）收录规则 (corrected), the rule is:
#   有标题归拢即省（集中习题块 → 不写、不校验）；无标题穿插即留（被保留的练习 → 写、且应校验）。
# So *preserved* (interleaved) exercises DO need a verified ordinal group; only
# the consolidated-block exercises must be skipped.
#
# The reason Exercise is kept OUT of LABEL_FORMS is purely to kill the
# "无中生有" bug: in books like Fraleigh the ONLY "Exercise N" surface forms in
# the OCR are BODY CROSS-REFERENCES ("see Exercise 51", "According to Exercise
# 12 of Section 1") — NEVER real exercise headings.  Scanning "Label N" here
# would therefore fabricate a spurious "Exercise" group out of cross-references
# (this was the original bug in Fraleigh's config).  The genuine FIRST-LEVEL
# exercise counter (bare "1." "2." "3." with no label prefix) is detected
# separately by `_detect_exercise_counter`, which fires ONLY for PRESERVED
# exercises that sit outside a consolidated "Exercises/练习" zone — so it
# correctly returns False for Fraleigh (all exercises there are consolidated
# blocks), while still letting a book with genuine preserved exercises get a
# type:1 group.
#
# NOTE on `uncat`: it is the CATCH-ALL fallback for any numbered item whose type
# is not in TYPE_TO_LABEL (`TYPE_TO_LABEL.get(n.type, 'uncat')` in
# structure_io.py) — NOT "reserved for two-level figures/tables".  Any unmatched
# first-level family legitimately becomes the uncat group, so it is perfectly
# fine for an unmatched exercise counter to surface as uncat instead of a named
# group; we only PREFER a named exercise group when `_detect_exercise_counter`
# can establish one.
LABEL_FORMS = [
    ("Definition",  ["Definition", "定义"]),
    ("Theorem",     ["Theorem", "定理"]),
    ("Lemma",       ["Lemma", "引理"]),
    ("Corollary",   ["Corollary", "推论"]),
    ("Proposition", ["Proposition", "命题"]),
    ("Conjecture",  ["Conjecture", "猜想"]),
    ("Algorithm",   ["Algorithm", "算法"]),
    ("Example",     ["Example", "例", "例题", "例子"]),
    ("Remark",      ["Remark", "评注", "注", "注记", "附注", "Note", "Commentary"]),
    ("Axiom",       ["Axiom", "公理"]),
    ("Assumption",  ["Assumption", "假设", "假定"]),
    ("Question",    ["Question", "问题"]),
]


def _build_label_heading_regexes(letter_chapter=False):
    """Build, per canonical label, ONE regex that captures BOTH the label text
    and the adjacent numeric key (so we can later tell which labels share a
    counter).  Longer raw forms are tried first (e.g. 注记 before 注) so the
    matched surface form is the longest one actually present.

    Two arms, both capturing the number:
      * label-first :  ``Label 1.5-3``  -> groups (label, num)
      * number-first: ``1.5-3 Label``  -> groups (num, label)
    CN forms matched literally; EN forms word-boundary + IGNORECASE.  Returns a
    list of ``(canon_idx, regex, form_by_lower)``.

    `letter_chapter=True` (APPENDIX scan) additionally accepts a LETTER chapter
    slot — ``Definition A.1.1`` — plus a plural label (``Examples A.1.3``).
    The letter arm is deliberately anchored with a lookahead
    (``[A-Za-z](?=[sep]\\d)``) so it can NEVER absorb a stray word character:
    without it ``Examples A.1.3`` would match the label ``Example`` and then
    read the leftover ``s`` as the number.  The digit arm is byte-identical to
    the default, so the main-text scan is unaffected.
    """
    out = []
    for ci, (canon, forms) in enumerate(LABEL_FORMS):
        ordered = sorted(forms, key=len, reverse=True)   # longest first
        label_alt = '|'.join(re.escape(f) for f in ordered)
        form_by_lower = {f.lower(): f for f in forms}
        if letter_chapter:
            num = (r'(?:\d[\d.\-–·/．－〜]*'
                   r'|[A-Za-z](?=[.\-–·／/．－〜]\d)[\d.\-–·/．－〜]*)')
            label_alt = r'(?:' + label_alt + r')(?:es|s)?'
        else:
            num = r'\d[\d.\-–·/．－〜]*'
        rx = re.compile(
            r'(' + label_alt + r')\s*(' + num + r')'
            r'|(' + num + r')\s+(' + label_alt + r')',
            re.IGNORECASE)
        out.append((ci, rx, form_by_lower))
    return out


def _is_header_boundary(tail):
    """Decide whether a matched label+number is a real HEADING (return True)
    or a cross-reference embedded in PROSE (return False).

    We ACCEPT by default.  The only thing that flips us to "prose / cross-ref"
    is an explicit continuation particle immediately after the number:
      * CN possessive / locative particle: 的 / 中 / 里 / 上 / 处
        (e.g. '定理 2.1 的证明' is a reference, not a heading).
      * EN prose-continuation word: of / that / which / states / shows /
        implies / is / are / and / but / where / see / given / let / then /
        hence / thus / so …

    A heading NAME must NOT be rejected — even a single latin letter
    ('Definition 1.5-3 X') or a Han name ('定义 1.1.1 有界').  Rejecting those
    was the bug that made the whole-book scan miss entries whose name began
    with a letter / Han char, collapsing the detection back to ['uncat'].
    """
    s = tail.lstrip()
    if not s:
        return True
    c = s[0]
    if c in ':.。():（）)，,；;*':
        return True
    # CN possessive / locative particle => 'X 的…' / 'X 中…' prose, not a heading.
    if re.match(r'^[的是在里上中处]', s):
        return False
    # EN prose-continuation word => cross-reference inside a sentence.
    if re.match(
        r'^(?:of|that|which|this|these|those|states?|shows?|implies?|'
        r'means?|says?|is|are|was|were|and|but|where|see(?: also)?|'
        r'given|let|then|hence|thus|so)\b', s, re.IGNORECASE):
        return False
    return True


def _is_crossref_prefix(pre):
    """The text immediately BEFORE the label must not be a citation particle
    ('见 定义 1.5-3' / 'see Theorem 2.1') — that is a cross-reference, not a
    heading.  We inspect the ~10 chars preceding the label."""
    pre = pre[-10:].lower()
    return bool(re.search(
        r'(见|由|根据|参考|参见|据|依照|按|cf\.|see\b|below\b|viz\.|e\.g\.|i\.e\.)', pre))


def _parse_comps(numstr, letter_chapter=False):
    """Parse a matched numeric key ('1.5-3') into a tuple of ints.

    With `letter_chapter=True` the FIRST component may be an appendix LETTER
    ('A.1.1' -> ``('A', 1, 1)``); every later component must still be numeric
    (otherwise it is an OCR fragment, not a numbering path).  Mixing a str
    chapter slot with int tail components keeps the counter-grouping logic
    (which only reads ``comps[-1]`` / ``comps[:-1]``) working unchanged.
    """
    parts = [p for p in SEP_SPLIT_RE.split(numstr) if p]
    if not parts:
        return None
    if letter_chapter and parts[0][:1].isalpha():
        head, rest = parts[0][0].upper(), parts[0][1:]
        comps: List = [head]
        if rest:
            if not rest.isdigit():
                return None
            comps.append(int(rest))
        try:
            comps.extend(int(x) for x in parts[1:])
        except ValueError:
            return None
        return tuple(comps)
    try:
        return tuple(int(x) for x in parts)
    except ValueError:
        return None

# Heading-position guard for label detection (see `_detect_ordinal_from_pages`).
# A numbered label is treated as a REAL heading only if it sits at (or very
# near) the START of its text block, or the block is short enough that the
# match is its dominant content.  Body cross-references ("… by Theorem 3.2 …")
# live mid-prose and are rejected.  This is the concrete mechanism behind the
# rule "only add to verify_config what the book actually uses as a heading —
# never fabricate a label from a body cross-reference or a copied vocabulary".
HEADING_LEAD_MAX = 3     # max non-label chars allowed before the match
HEADING_SHORT_MAX = 80   # blocks at/under this length are scanned whole

# ---- formula detection (full-book, whole-book aggregation) ----------------
# Reuse q_layer.norm's "（）→()" ASCII-normalisation idea: a standalone formula
# number may appear in either full-width or half-width parens, so we match both.

# Formula-number detectors — patterns shared from lib/regexlib.py
from lib.regexlib import (F_SINGLE_RE as _F_SINGLE_RE, F_DOT_RE as _F_DOT_RE,
                          F_EQ_RE as _F_EQ_RE, F_CN_EQ_RE as _F_CN_EQ_RE,
                          F_LETTER_RE as _F_LETTER_RE,
                          F_ROMAN_RE as _F_ROMAN_RE,
                          SEP_SPLIT_RE)

# --- formula detection confidence gate ------------------------------------
# The loose `(N)` / `（N）` text scan matches MANY non-formula contexts in a
# number-theory / algorithms book: algorithm step numbers ("(1) Set = 1"),
# proof statement references ("verify (1) and (2)"), table row labels
# ("(18) = 39"), square-and-multiply values ("(71)² ="), and OCR garbage
# ("(512823440)").  Those are NOT formula sequence labels, so we only emit a
# formula config when the matched "(N)" numbers form a genuinely ascending
# formula numbering (a meaningful count + a coherent consecutive run).  When
# the evidence is weak we return None and let manual review add the scheme —
# we must NEVER fabricate a formula config (the user's "no-default / must
# match" rule applies to `formula` exactly as it does to `ordinal`).
_FORMULA_MIN_COUNT = 30   # need this many right-aligned "(N)" to be a scheme
_FORMULA_MIN_RUN = 5      # and a consecutive run of at least this length
# 📐 Letter-led series (appendix `(A.N)`) are judged against the **scanned range**:
# the appendix generator calls `detect_formula` with ONLY the appendix page window,
# so a whole-book threshold can never be reachable. Measured on Shafarevich BA1
# "Algebraic Appendix" (pp.299–312, 14 pages): 17 clean `(A.N)` hits, series
# A.1…A.15, dotted_count = 0 → with the fixed threshold 30 detection returned
# None → the appendix sub-config silently had NO `formula` key → `attach_content`
# harvested zero tags → every printed equation number of the appendix disappeared
# from the notes (prose references "(A.3)" then point at unnumbered displays).
_FORMULA_LETTER_MIN = 8       # floor for a letter-led series
_FORMULA_FULL_SCAN_PAGES = 60  # range size at which the whole-book bar applies


def _letter_min_count(n_pages):
    """Threshold for a letter-led equation series, scaled to the scanned range.

    Ranges of `_FORMULA_FULL_SCAN_PAGES` pages or more keep the historical
    whole-book bar exactly (`>= 60` pages ⇒ unchanged behaviour for every
    already-finished book); shorter ranges get `30 * pages / 60` with a floor of
    `_FORMULA_LETTER_MIN`."""
    if n_pages >= _FORMULA_FULL_SCAN_PAGES:
        return _FORMULA_MIN_COUNT
    return max(_FORMULA_LETTER_MIN,
               int(_FORMULA_MIN_COUNT * n_pages / _FORMULA_FULL_SCAN_PAGES))


def _letter_series_confident(hits):
    """True iff `(letter, number)` hits contain a genuine ascending series.

    Same discipline as :func:`_formula_single_confident` (formula numbers run
    1,2,3,…; incidental `(A.12)` mentions are scattered), applied **per letter**
    and on the *deduplicated* numbers — a 14-page appendix only yields ~15 hits,
    so the count alone is weak evidence while a run of 5 is not."""
    by_letter = {}
    for lt, num in hits:
        try:
            by_letter.setdefault(lt.upper(), set()).add(int(num))
        except (TypeError, ValueError):
            continue
    for nums in by_letter.values():
        uniq = sorted(nums)
        longest = cur = 1
        for i in range(1, len(uniq)):
            cur = cur + 1 if uniq[i] == uniq[i - 1] + 1 else 1
            longest = max(longest, cur)
        if longest >= _FORMULA_MIN_RUN:
            return True
    return False



def _formula_single_confident(nums):
    """True iff `nums` (right-aligned / standalone "(N)" values) looks like a
    genuine formula numbering: enough of them, and they ascend together in a
    long consecutive run (formula numbers are 1,2,3,…; incidental
    parenthesised numbers are scattered and non-consecutive)."""
    if len(nums) < _FORMULA_MIN_COUNT:
        return False
    uniq = sorted(set(nums))
    longest = cur = 1
    for i in range(1, len(uniq)):
        if uniq[i] == uniq[i - 1] + 1:
            cur += 1
        else:
            longest = max(longest, cur)
            cur = 1
    longest = max(longest, cur)
    return longest >= _FORMULA_MIN_RUN


def _formula_tail_clean(tail):
    """A genuine formula number is right-aligned at the END of an equation
    line, so the text after `(N)` is only whitespace / punctuation.  Prose
    like "verify (1) and (2)", "(1) Set = 1", "(18) = 39" leave content after
    the paren and are NOT formula numbers."""
    return re.fullmatch(r"[\s\.\,\;\)\]\}\:\'\"\u3002\uff0c\uff1b]*", tail) is not None


def _series_scope(hits):
    """Per-head reset vs one book-wide series, for a ``(head, number)`` scan.

    scope 2 when the first number seen under a later head is SMALLER than the
    previous head's running max (i.e. the number resets after each head —
    ``B.1..B.15`` then ``C.1..``), else scope 1 (a single monotonic series).
    Shared by the letter and roman branches so their scope decision cannot
    drift apart."""
    heads = []
    for h, _n in hits:
        if h not in heads:
            heads.append(h)
    for i in range(1, len(heads)):
        first_of_later = next(n for h2, n in hits if h2 == heads[i])
        prev_max = max(n for h2, n in hits if h2 == heads[i - 1])
        if first_of_later < prev_max:
            return 2
    return 1


def _two_component_scope(pairs):
    """Digit two-component ``(C.N)`` scope — derived from book evidence, NO default.

    ``pairs`` is a page-ordered list of ``(first_component, second_component)``
    ints.  scope 2 (per-chapter reset, cross-chapter guard ON) vs scope 1
    (book-wide, guard off) is decided by the SAME reset test as the alpha-led
    families (``_series_scope``): does the trailing number restart under a new
    leading component?  But that question can only be answered when the book
    actually shows **two or more distinct leading components** — with a single
    leading value there is no boundary to observe a reset against, so the
    evidence is genuinely undeterminable and we return ``None`` (the caller then
    OMITS `scope`, and the load-time validator / agent must settle it from the
    book rather than silently assuming chapter-scope)."""
    if len({h for h, _n in pairs}) < 2:
        return None
    return _series_scope(pairs)


def detect_formula(extract_dir, pages=None):
    """Full-scan EVERY page_*.json and infer the book's formula numbering.

    Counts standalone single-component ``(N)``/``（N）`` vs two-component
    ``(C.N)``/``Eq. C.N``/``式（C.N）`` occurrences across the WHOLE book, then
    decides the global formula config by whole-book aggregation (never by
    sampling the first N pages).  Letter-chapter-led ``(A.3)`` / ``（B.12）``
    (Lee ISM appendices) is counted via ``F_LETTER_RE`` with the same
    tail-clean discipline; when it dominates the range (>= _FORMULA_MIN_COUNT
    and beats the digit form) the returned config carries
    ``"letter_ch": True`` (``{"type": 2, ...}``).  Roman-chapter-led ``(II.5)``
    is counted via ``F_ROMAN_RE`` (multi-character head only, so single-char
    Roman heads stay letter) and returns the formula-only ``{"type": 16}``;
    Roman wins only on positive multi-char Roman evidence with no non-Roman
    letter head, keeping the digit / letter elections byte-identical.  In both
    alpha-led cases the scope is decided by whether the digit component resets
    after each head (per-head reset → scope 2).  The DIGIT two-component branch
    ``(C.N)`` likewise DERIVES its scope (never defaults to 2): via
    ``_two_component_scope`` the trailing number restarting under a new leading
    component → scope 2 (per-chapter), a book-wide monotonic series → scope 1,
    and fewer than two distinct leading components → the reset is unobservable
    so ``scope`` is OMITTED (the load-time validator / agent must settle it from
    the book — there is no default scope anywhere).

    Returns a ``{"type", "ignore", "scope"[, "letter_ch"]}`` dict, where
    ``scope`` is ALWAYS derived from book evidence and may be omitted when it can
    not be determined — it is never silently defaulted.  The token ``depth`` /
    lead is DERIVED from ``type`` via ``resolve_formula_type`` — the formula-only
    Roman type lives in its own namespace, not ORDINAL_DEPTH — so it is not part
    of the config.  ``None`` is returned when no shape is detected (caller then
    simply omits the ``formula`` key).  Operator-registered keys (``ignore`` /
    ``bare_number``) from the previous config are re-attached by
    ``_build_config_dict``.

    Phase guard: requires MM Repair to be finished (``_extraction_done.json``
    present — written only after mode A+B are applied back to ``page_*.json``,
    NOT merely when background text extraction reaches 100%); otherwise returns
    None rather than guessing from a partial / un-repaired extraction.

    `pages` restricts the scan (appendix generator passes the appendix range).
    """
    if not os.path.exists(os.path.join(extract_dir, '_extraction_done.json')):
        print('[make_config] MM Repair 未完成（缺 _extraction_done.json），'
              '跳过 formula 探测；请完成 MM Repair（模式 A+B 写回 page_*.json）后再生成配置。')
        return None

    pages = pages if pages is not None else sorted(
        glob.glob(os.path.join(extract_dir, 'page_*.json')))
    single_count = 0
    dotted_count = 0
    letter_count = 0
    roman_count = 0
    single_nums = []  # ints in page order, for per-section-reset fallback
    dotted_hits = []  # (first_comp, second_comp) in page order, for 2-comp scope
    letter_hits = []  # (letter, num) in page order, for letter-ch scope check
    roman_hits = []   # (roman_head, num) in page order, for roman scope check
    for pg in pages:
        try:
            with open(pg, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        texts = [blk_text(b) for b in data.get('text', [])
                 if isinstance(b, dict)]
        for text in texts:
            if not text:
                continue
            # Only count "(N)" that is a genuine formula number: the LAST paren
            # in the block whose tail is whitespace/punctuation only (a
            # right-aligned equation number).  Prose-embedded "(N)" — algorithm
            # steps, proof statement refs, table row labels, OCR noise — leave
            # content after the paren and are excluded (see _formula_tail_clean).
            matches = list(_F_SINGLE_RE.finditer(text))
            if matches:
                last = matches[-1]
                if _formula_tail_clean(text[last.end():]):
                    single_count += 1
                    try:
                        single_nums.append(int(last.group(1)))
                    except ValueError:
                        pass
            for _rx in (_F_DOT_RE, _F_EQ_RE, _F_CN_EQ_RE):
                for _m in _rx.finditer(text):
                    dotted_count += 1
                    _g = _m.group(1)
                    if '.' in _g:
                        _a, _b = _g.split('.', 1)
                        try:
                            dotted_hits.append((int(_a), int(_b)))
                        except ValueError:
                            pass
            # Letter-chapter-led `(A.3)`: same tail-clean discipline as the
            # single-component scan (the block's LAST letter-led paren must be
            # a right-aligned equation number).  Letter-led books (Lee ISM
            # appendices) score ZERO on _F_DOT_RE — its `\d+\.\d+` core cannot
            # match a letter first component — so without this counter the
            # appendix sub-config silently loses its `formula` key entirely.
            lmatches = list(_F_LETTER_RE.finditer(text))
            if lmatches:
                llast = lmatches[-1]
                if _formula_tail_clean(text[llast.end():]):
                    letter_count += 1
                    letter_hits.append((llast.group(1), int(llast.group(2))))
            # Roman-chapter-led `(II.5)` / `（IV.12）`: POSITIVE multi-character
            # Roman evidence only.  F_ROMAN_RE requires [IVXLCDM]{2,5}, so it is
            # disjoint from the single-letter probe at the regex level —
            # `(II.5)` never matches F_LETTER_RE (after `I` comes `I`, not a
            # separator) and single-char `(I.1)` never matches F_ROMAN_RE (its
            # head needs >=2 chars) and stays with the letter branch.  Same
            # tail-clean discipline as the letter / single scans.
            rmatches = list(_F_ROMAN_RE.finditer(text))
            if rmatches:
                rlast = rmatches[-1]
                if _formula_tail_clean(text[rlast.end():]):
                    roman_count += 1
                    roman_hits.append((rlast.group(1), int(rlast.group(2))))

    # Roman-chapter-led candidate `(II.5)` (formula type 16, lead='roman').
    # Checked BEFORE the letter branch: elect ROMAN only on positive multi-
    # character Roman evidence AND when NO non-Roman letter head was seen (a
    # genuine letter appendix yields A/B/C heads via F_LETTER_RE and must keep
    # winning as letter).  Single-char Roman heads (I/V/X/L/C/D/M) are
    # indistinguishable from letters and are deliberately left to the letter
    # branch below, so this election never mis-fires on a letter book.
    if (roman_count >= _letter_min_count(len(pages))
            and roman_count > dotted_count
            and _letter_series_confident(roman_hits)
            and all(head in 'IVXLCDM' for head, _n in letter_hits)):
        return {"type": 16, "scope": _series_scope(roman_hits), "ignore": []}

    # Letter-chapter-led candidate (checked after Roman — letter-led pages also
    # score a little on single/dotted noise, and letter-led must win when the
    # Roman election above declined).
    if (letter_count >= _letter_min_count(len(pages))
            and letter_count > dotted_count
            and _letter_series_confident(letter_hits)):
        # Scope: per-letter-chapter reset (B.1..B.15 then C.1.. → scope 2) vs
        # one book-wide letter series (scope 1).
        scope = _series_scope(letter_hits)
        return {"type": 2, "scope": scope, "ignore": [], "letter_ch": True}

    if single_count > dotted_count and single_count > 0:
        # Single-component candidate.  Require CONFIDENT evidence of a genuine
        # formula numbering — otherwise these are incidental parenthesised
        # numbers (algorithm steps, proof statement refs, table row labels,
        # OCR noise), NOT formula sequence labels.  e.g. Silverman's source has
        # ~90 such "(N)" hits but ZERO real formula numbers -> we return None.
        if _formula_single_confident(single_nums):
            # Single-component book.  Decide scope by whether the numeric
            # sequence "falls back" (resets to a smaller number) somewhere in
            # the book: reset seen -> per-section (scope 3); monotonic ->
            # book-wide (scope 1).
            scope = 1
            seen_max = 0
            for n in single_nums:
                if n < seen_max:
                    scope = 3
                    break
                seen_max = max(seen_max, n)
            return {"type": 1, "scope": scope, "ignore": []}
    if dotted_count > single_count and dotted_count > 0:
        # Two-component candidate (e.g. "(C.N)", "Eq. C.N", "式（C.N）").
        # Require a comparable minimum count so a handful of incidental dotted
        # numbers don't fabricate a type-2 formula scheme.
        if dotted_count >= _FORMULA_MIN_COUNT:
            # 🔴 NO default scope: derive 1 (book-wide) vs 2 (per-chapter reset)
            # from the observed leading-component reset behaviour.  When the
            # book never shows two distinct leading components the reset can not
            # be observed -> omit `scope` entirely and let the load-time
            # validator / agent decide it from the book (宁缺勿滥).
            out = {"type": 2, "ignore": []}
            _sc = _two_component_scope(dotted_hits)
            if _sc is not None:
                out["scope"] = _sc
            return out
    return None


# canonical NAME (EN) of each surface form — used for grouping decisions.
_FORM_CANON = {}
for _canon, _forms in LABEL_FORMS:
    for _f in _forms:
        _FORM_CANON[_f.lower()] = _canon

def _group_headings_by_counter(headings, depth, strict_reset=True):
    """Group detected ``(canon_idx, raw_form, comps)`` headings into counters.

    Every detected entry-type family (Definition/Theorem/Lemma/Corollary/
    Proposition/Example/Axiom/Remark/Exercise/...) is clustered by whether it
    ACTUALLY shares ONE ascending counter with a reference family — NOT by a
    hard-coded "main types always merge" rule.  Two families that never re-use
    a number nor reset to 1 inside a shared scope window share a counter; a
    family that resets to 1 (or duplicates a number) inside a running window
    runs on its OWN independent sequence and gets a separate group.  This is
    what the ``ordinal`` ARRAY is for: labels that ascend together -> one
    object; separate counters -> a NEW object.

    A family is given its OWN group (the safe, conservative choice) when it
    never co-occurs with the reference counter in a comparable scope window,
    because separate never manufactures false gaps, whereas a wrong merge
    would.
    """
    from collections import defaultdict
    if not headings:
        return [["uncat"]]
    canon_of = lambda f: _FORM_CANON.get(f.lower())
    by_canon = defaultdict(lambda: {"forms": set(), "comps": []})
    for (ci, f, c) in headings:
        canon = canon_of(f)
        if canon is None:
            continue
        by_canon[canon]["forms"].add(f)
        by_canon[canon]["comps"].append(c)
    if not by_canon:
        return [["uncat"]]

    order = {f: (i, j) for i, (_, forms) in enumerate(LABEL_FORMS)
             for j, f in enumerate(forms)}

    def sort_forms(fs):
        return sorted(fs, key=lambda f: order.get(f, (999, 999)))

    def _counter_min_max(comps):
        # (min, max) of the per-item counter numbers across all scope windows.
        nums = [c[-1] for c in comps if len(c) >= 1]
        return (min(nums), max(nums)) if nums else (0, 0)

    # Reference counter selection.
    # Default to the family with the MOST detected headings (the previous
    # behaviour).  That choice is correct for the common case and, crucially,
    # for books where every family is independently numbered (each resets to 1)
    # such as Koopman -> 8 separate single-type groups.  HOWEVER, when that
    # most-frequent family does NOT start at 1 it cannot be the TRUE primary of
    # a shared ascending chain: a sibling that legitimately resets to 1
    # (Definition 1.1 in a Definition 1.1 / Theorem 1.2 / Lemma 1.3 chain) would
    # then be mis-split into its own group.  In that case we fall back to the
    # family that BEGINS at 1 (the true primary) and has the LARGEST span
    # (largest max number) -- the full 1..N primary, not a mid-chain fragment.
    # Independent parallel counters also start at 1, but the true primary spans
    # the full range, so the largest max among from-1 families selects it.
    # We only switch away from "most headings" when that reference itself fails
    # to start at 1: unconditionally preferring a from-1 family would change the
    # reference for normally-numbered books too, which (because
    # _shares_main_counter is reference-dependent) triggers spurious merges such
    # as Koopman's Corollary/Problem.  The hard fallback (no family starts at 1)
    # keeps the most-headings choice.
    ref_canon = max(by_canon, key=lambda cc: len(by_canon[cc]["comps"]))
    if _counter_min_max(by_canon[ref_canon]["comps"])[0] != 1:
        starts_at_1 = [cc for cc in by_canon
                       if _counter_min_max(by_canon[cc]["comps"])[0] == 1]
        if starts_at_1:
            ref_canon = max(starts_at_1,
                            key=lambda cc: _counter_min_max(by_canon[cc]["comps"])[1])
    ref_comps = by_canon[ref_canon]["comps"]
    primary = sort_forms(by_canon[ref_canon]["forms"])
    groups = []
    for canon, data in by_canon.items():
        if canon == ref_canon:
            continue
        forms = sort_forms(data["forms"])
        if _shares_main_counter(data["comps"], ref_comps,
                                strict_reset=strict_reset):
            primary += forms
        else:
            groups.append(forms)
    groups.insert(0, primary)
    return groups


def _shares_main_counter(cand_comps, main_comps, strict_reset=True):
    """True iff the candidate family shares the SAME ascending counter as the
    main types (so it should merge into the primary group).  False (its OWN
    group) when it runs on an INDEPENDENT parallel sequence.

    Two signals prove independence (do NOT merge):
      * DUPLICATE: in a shared scope window the candidate re-uses a number the
        main counter already used (e.g. Problem 6.3-2 AND Definition 6.3-2 both
        exist).  Parallel counters reuse numbers; a single shared sequence
        never does.  This is the definitive discriminator between "same
        counter" and "parallel independent counter" — the old logic that only
        checked for a reset-to-1 falsely merged parallel counters.
      * RESET: the candidate resets to 1 inside a window where the main counter
        is already running — it starts its own sequence there.
    If the candidate never co-occurs with the main counter in a comparable
    window, return False (conservative: own group).
    """
    from collections import defaultdict
    main_by_win = defaultdict(list)
    for c in main_comps:
        if len(c) >= 2:
            main_by_win[c[:-1]].append(c[-1])
    cand_by_win = defaultdict(list)
    for c in cand_comps:
        if len(c) >= 2:
            cand_by_win[c[:-1]].append(c[-1])
    shared = 0
    for w, cnums in cand_by_win.items():
        if w not in main_by_win:
            continue
        shared += 1
        mnums = main_by_win[w]
        # duplicate number in the same window => parallel independent counters
        if any(n in mnums for n in cnums):
            return False
        # resets to 1 within a running window => its own sequence.
        # strict_reset=False（契约证据通路）跳过本规则：共享计数器书
        # （Weibel 正文）不同标签**轮流**当节首条目，候选窗内 min==1 是常态，
        # 按此判据会把 Definition/Theorem 全拆散、制造数百幻影缺号；
        # 「同窗重复号」判据已足以鉴别真正的平行计数器（练习 10.3.1 vs
        # Definition 10.3.1 同窗共存）。
        if strict_reset and min(cnums) == 1:
            return False
    if shared == 0:
        return False
    return True




def _group_single_level(headings):
    """Group headings of a SINGLE-LEVEL (type 1) book.

    Single-level books (e.g. Silverman's ``Theorem 1``, ``Lemma 2``) reset
    their counter per chapter, so the page scan has NO chapter window to tell
    which labels share ONE ascending counter vs run independent sequences (the
    window logic in ``_shares_main_counter`` needs >=2 components).  We
    therefore apply the domain convention valid for essentially every
    single-level math book:

      * STATEMENT labels (Theorem / Lemma / Proposition / Corollary /
        Conjecture / Claim / Fact / Axiom / Algorithm) share ONE ascending
        counter -> the single PRIMARY group.  This is exactly the user's
        "合并升序" for a single-level book.
      * EXPOSITORY labels that always re-start at 1 (Example / Question /
        Problem / Exercise / Remark / Note) each get their OWN group.

    Only labels ACTUALLY detected in the book are emitted (no fabrication).
    """
    STATEMENT = {"Theorem", "Lemma", "Proposition", "Corollary", "Conjecture",
                 "Claim", "Fact", "Axiom", "Algorithm"}
    from collections import defaultdict
    by_canon = defaultdict(set)
    for ci, form, comps in headings:
        canon = _FORM_CANON.get(form.lower())
        if canon:
            by_canon[canon].add(form)
    if not by_canon:
        return [["uncat"]]
    primary = []
    independents = []
    for canon, forms in by_canon.items():
        sorted_forms = sorted(forms, key=str.lower)
        if canon in STATEMENT:
            primary.extend(sorted_forms)
        else:
            independents.append(sorted_forms)
    groups = []
    if primary:
        groups.append(primary)
    groups.extend(independents)
    return groups or [["uncat"]]


def _ordinal_from_chapter_map(extract_dir):
    """Return ``(ordinal_code, chapter_first)`` declared in chapter_map.json
    when it is consistent across every chapter, else None.

    chapter_map.json is the structural source of truth authored from the book's
    own sectioning.  For a section-based two-level book (e.g. Fraleigh) every
    chapter entry carries ``"ordinal": 2`` and ``"chapter_first": false`` — the
    first numeric component of an item key is the SECTION, not the chapter
    (``"Theorem 8.1"`` = §8 item 1).  The page-text scan in
    `_detect_ordinal_from_pages` CANNOT tell a section-based two-level scheme
    (type 2 + chapter_first=False) apart from a plain chapter-based EN two-level
    (type 2 + chapter_first=True) — both look like "Label N.M" — so the scan
    always votes 2 and cannot know chapter_first.  We therefore trust
    chapter_map's declaration for ``chapter_first`` when present and consistent.

    For the scan-ambiguous ORDINAL *codes* (8=vakil, 12=Humphreys) we additionally
    adopt the declared code over the scan's guess.  A book whose chapters disagree
    on the ordinal (or carry none) returns None and falls back to the scan vote.
    """
    cm_path = os.path.join(extract_dir, 'chapter_map.json')
    if not os.path.exists(cm_path):
        return None
    try:
        with open(cm_path, encoding='utf-8-sig') as f:
            cm = json.load(f)
    except Exception:
        return None
    chs = cm.get('chapters', []) if isinstance(cm, dict) else cm
    if not isinstance(chs, list):
        return None
    codes = set()
    cf_set = set()
    for e in chs:
        if isinstance(e, dict) and e.get('ordinal') is not None:
            try:
                codes.add(int(e['ordinal']))
            except (TypeError, ValueError):
                pass
            cf_set.add(bool(e.get('chapter_first', True)))
    if len(codes) == 1:
        chapter_first = True
        if len(cf_set) == 1:
            chapter_first = cf_set.pop()
        return codes.pop(), chapter_first
    return None


_CONTRACT_TYPE_TO_FORM = {
    "definition": "Definition", "theorem": "Theorem", "lemma": "Lemma",
    "corollary": "Corollary", "proposition": "Proposition",
    "example": "Example", "remark": "Remark", "axiom": "Axiom",
}


def _contract_counter_evidence(extract_dir, include_chapter=False,
                               letter_chapter=False):
    """结构契约（book_structure/ch{N}.json）已存在时，用契约条目本身作为
    计数器分组证据 —— 比 ordinal 探测阶段的 OCR 标题扫描干净得多（OCR 漏识
    / 字符混淆会让 _shares_main_counter 的证据稀疏化，Weibel 实测被误判成
    5 个独立计数组）。

    `letter_chapter=True`（附录 / 补篇子配置）：只收**字母章位键**的条目
    （`A.9` → comps=('A',9)，`A.1.3` → ('A',1,3)），窗口分量即字母章（或
    字母章+节），与 OCR 通路 `_parse_comps(letter_chapter=True)` 同形。
    Shafarevich《Basic Algebraic Geometry 1》Algebraic Appendix 实测：OCR 标题
    扫描只捞到 `Proposition A.9-A.14`（漏 A.1-A.8），于是 `Corollary A.1-A.3`
    的号与它**不重号**，被判成共享计数器并进同一组 → 条目阅读序按数字排，
    `Corollary A.1` 压到 `Proposition A.11` 之前，ANCHOR-SANITY 整章拒绝落盘。
    契约里 A.1-A.17 齐全，「同窗重号」判据据此正确拆成两个平行计数器组。

    返回 ``[(form, comps)]``或 None（无契约 / 无可用条目）。**练习条目不纳入**
    证据（exercise 不在 _CONTRACT_TYPE_TO_FORM）：练习计数器由
    `_detect_exercise_counter` / `_detect_appendix_exercise` 专属检测并
    单列组，与 LABEL_FORMS 刻意不含 Exercise 的口径一致。

    `include_chapter=True`（单级 type-1 书专用）：单级书的条目键只含裸序号
    （如 '定理1'），章节边界不在键里，故用**所属章号补成窗口分量**
    comps=(chapter, num)，让 `_shares_main_counter` 的「同窗重复号」判据得以
    区分「共享一条计数器」与「章内各自重起的平行计数器」。Arnold《ODE》实测：
    第 2 章同时存在 Theorem 1-3、Corollary 1-12、Lemma 1-4——三族在窗口 (2,)
    内**重号**，故是各自独立的计数器，必须拆成三个具名组；旧 `_group_single_level`
    的「statement 标签一律合并」硬约定会把它们错误并成一组，使组合并最大号
    （Corollary 12）漏进 Lemma/Theorem 的逐标签 TAIL 比对，制造成片假「源最大 12
    ≫ md 最大 4」BLOCKING。
    """
    from data.book_structure.book_structure import BookStructure
    try:
        bs = BookStructure.load(extract_dir)
    except Exception:
        return None
    if bs is None:
        return None
    out = []

    def walk(n, ch_int):
        if n.type in ("chapter", "section"):
            for k in n.sub_sec:
                walk(k, ch_int)
            return
        form = _CONTRACT_TYPE_TO_FORM.get(str(n.type))
        if not form:
            return
        if letter_chapter:
            m = re.match(r'^([A-Za-z])\s*[.\-·]\s*(\d+)'
                         r'((?:\s*[.\-·]\s*\d+)*)$', str(n.key).strip())
            if not m:
                return   # 非字母章位键（正文书同目录混载时）不参与附录证据
            tail = [int(x) for x in re.findall(r'\d+', m.group(3))]
            out.append((form, tuple([m.group(1).upper(), int(m.group(2))]
                                    + tail)))
            return
        nums = re.findall(r"\d+", str(n.key))
        if include_chapter:
            if not nums:
                return
            out.append((form, (ch_int, int(nums[-1]))))
            return
        if len(nums) < 2:
            return
        # 🔴 窗口分量**必须带上所属章号**。`_shares_main_counter` 以 comps[:-1]
        # 为「同窗」，节级编号书（Fraleigh / do Carmo《黎曼几何》：键 = 节.项，
        # 计数器按节重启）的键里**没有章号**，不加章号时第 5 章的 `2.1` 与第 13
        # 章的 `2.1` 落在同一个窗口 (2,)，被「同窗重号」判据当成平行计数器的决定
        # 性证据 → 一套共享计数器被误拆成 7 个独立组（黎曼几何实测 37 个假重号
        # 窗）。章号前置后窗口 = (章, 节)（章级编号书 = (章, 章)，第二个分量冗余
        # 但无害），跨章同号不再相撞、同章同号照旧是铁证。
        out.append((form, tuple([ch_int] + [int(x) for x in nums])))

    for c in bs.chapters:
        ck = str(c.key)
        if letter_chapter:
            walk(c, None)   # 字母章位证据只看条目键，字母/数字章键一律遍历
            continue
        if not ck[:1].isdigit():
            continue  # 附录字母章键的窗口语义不同，交 letter_chapter 通路
        ch_int = int(re.match(r"\d+", ck).group(0))
        walk(c, ch_int)
    # 🔴 证据去重**必须按 (form, comps) 去重，绝不按 comps 去重**：跨标签同号
    # 共存正是「平行计数器」的决定性证据（同章既有 定理1.3 又有 例1.3 → 两条
    # 独立计数器）。旧实现按 comps 首见保留，把后到的异族同号项全部丢掉，等于
    # **专门销毁拆组证据**——Shafarevich《Basic Algebraic Geometry 1》正文实测：
    # 契约里 定理1.1-1.28 与 例1.1-1.35 各自成串，去重后 Theorem 只剩 (1,1)(1,2)、
    # Example 从 (1,3) 起，窗内「无重号」→ 四族被误并成一条共享计数器 → 条目阅读
    # 序按合并号段排（`Theorem 1.8` 排到 `Example 1.23` 之前，印面相反）→
    # ANCHOR-SANITY 整章拒绝落盘。
    # 保留的深层书顾虑（Weibel ch9 `Corollary 9.3.3.1` 与宿主 `Theorem 9.3-3`
    # 展平后同号）由「同 form 同 comps 只记一次」覆盖，异 form 共存照记。
    seen = set()
    deduped = []
    for form, comps in out:
        sig = (form, comps)
        if sig in seen:
            continue
        seen.add(sig)
        deduped.append((form, comps))
    return deduped or None


# 「全书连续」判据阈值：至少 2 个跨章接续证据，且连续票 ≥ 2×重起票。
_BOOK_SCOPE_MIN_CONT = 2
_BOOK_SCOPE_RATIO = 2


def _book_scope_votes(per_chapter):
    """``{章号: [条目号, …]}`` → ``(连续票数, 重起票数)``（纯函数，不读磁盘）。

    按章号升序逐章扫描：本章**最小编号 > 前面所有章节的最大编号** 说明计数器
    没有随章归零，而是接着上一章往下数 → 一票「连续」；本章出现了前面已经数过
    的号（重起或交叠）→ 一票「重起」。
    """
    chs = sorted(per_chapter)
    if len(chs) < 2:
        return 0, 0
    cont = restart = 0
    running_max = max(per_chapter[chs[0]])
    for c in chs[1:]:
        nums = per_chapter[c]
        if nums and min(nums) > running_max:
            cont += 1
        else:
            restart += 1
        running_max = max(running_max, max(nums))
    return cont, restart


def _refine_book_scope(extract_dir, ordinal_arr):
    """把**跨章连续**的单级计数器组从默认 scope=2（每章重启）改判 scope=1（全书）。

    🔴 `SCOPE_BY_TYPE` 对单级（type 1）一律给 scope=2，于是 Serre《Linear
    Representations of Finite Groups》这类「Theorem / Proposition / Lemma 全书
    连续起号」的书（ch2 印 Theorem 3–8、ch12 印 Theorem 24–28 + Proposition
    32–37 + Lemma 12–19）一经 `make_config --force` 重生成就被判成每章从 1 重起，
    B 层逐章报「缺号 1 … 17」假 BLOCKING（实测 40/40 → 14/40，26 章 FAIL）。
    证据取**结构契约**（`_contract_counter_evidence(include_chapter=True)`，
    已核准的 (章, 号) 事实），不取 OCR 页扫。判不清一律保持 scope=2 —— 只收紧
    漏判方向，不放松既有书的校验力度（fail-closed）。

    只改判 `type == 1` 的组：单级键的「最后一个数字」才等价于条目序号，多级键
    的分量语义不同。组内**每个**标签都必须自己投连续票才改判整组——混进一条按章
    重启的标签就不动整组。返回 ``(ordinal_arr, notes)``。
    """
    ev = _contract_counter_evidence(extract_dir, include_chapter=True)
    if not ev:
        return ordinal_arr, []
    by_form = {}
    for form, comps in ev:
        if len(comps) < 2:
            continue
        by_form.setdefault(form, {}).setdefault(comps[0], []).append(comps[-1])
    notes = []
    for g in ordinal_arr:
        if g.get("type") != 1 or g.get("scope") == SCOPE_BOOK:
            continue
        names = [n for n in (g.get("name") or []) if n]
        if not names:
            continue
        total_cont = total_restart = 0
        for n in names:
            per_ch = {c: v for c, v in (by_form.get(n) or {}).items() if v}
            if len(per_ch) < 3:
                total_cont = -1
                break
            cont, restart = _book_scope_votes(per_ch)
            if cont < _BOOK_SCOPE_MIN_CONT or cont < _BOOK_SCOPE_RATIO * restart:
                total_cont = -1
                break
            total_cont += cont
            total_restart += restart
        if total_cont >= 0:
            g["scope"] = SCOPE_BOOK
            notes.append("%s：跨章连续 %d 票 / 章内重起 %d 票 → scope=1（全书计数器）"
                         % ("/".join(names), total_cont, total_restart))
    return ordinal_arr, notes


def _detect_ordinal_from_pages(extract_dir, pages=None, letter_chapter=False):
    """Full-scan EVERY page_*.json and (a) vote on the numbering FAMILY and
    (b) detect which entry-type labels appear as numbered headings, then GROUP
    them by whether they share ONE ascending counter.

    Family vote: delegated to ``OrdinalStyle.detect_style`` (lib/ordinal_styles.py)
    — the SAME judgment standard the md-side key parser uses — run over the
    position-guarded, cross-ref-filtered heading STRINGS collected below.  It
    votes specificity-first (three-level > two-level > single-level; appendix
    letter-slot forms → 13/14) and returns None when no numbering style matches,
    so the ONLY codes this can emit are the ones ordinal_styles implements
    ({1,2,3,8,12,13,14}) — there is NO default type 3; a book with no detectable
    numbered heading yields family None (ordinal group omitted, not fabricated).

    Label detection + grouping: during the SAME scan we collect every
    (canon_idx, raw_form, comps) heading.  ``_group_headings_by_counter`` then
    puts labels that ascend together (share a counter within a scope window)
    into ONE group and gives labels with an independent reset their OWN group.
    This is what the ``ordinal`` ARRAY is for — NOT a fixed main/other split.

    Returns ``(family_int, groups, lang, chapter_first)`` where ``groups`` is a
    list of raw-form lists (one per counter), primary group first; ``lang`` is
    the detected language or None; ``chapter_first`` is the chapter_map-declared
    flag (True when chapter_map carries no contrary declaration).

    `pages` restricts the scan to an explicit list of `page_*.json` paths (the
    APPENDIX generator passes the appendix range only).  `letter_chapter=True`
    enables the appendix letter-slot numbering detection (``Definition A.1.1`` /
    ``Theorem B.2``) so ``detect_style`` elects ``ORDINAL_APP`` (13, three-level)
    or ``ORDINAL_APP2`` (14, two-level).

    Phase guard: only runs AFTER MM Repair is finished (`_extraction_done.json`
    present).  If MM Repair is incomplete we RAISE — never return a degraded
    default (that was the backdoor that let a half-repaired book get a config).
    """
    if not os.path.exists(os.path.join(extract_dir, '_extraction_done.json')):
        raise RuntimeError(
            '[make_config] BLOCKED: 缺 _extraction_done.json，MM Repair 未完成。'
            '禁止返回退化默认；须先完成 MM Repair（模式 A+B 写回 page_*.json，'
            'apply 真完成写出 _extraction_done.json）再生成配置。'
            '严禁手写/手改 verify_config.json 绕过本护栏。')
    pages = pages if pages is not None else sorted(
        glob.glob(os.path.join(extract_dir, 'page_*.json')))
    label_res = _build_label_heading_regexes(letter_chapter=letter_chapter)
    headings = []   # (canon_idx, raw_form, comps_tuple)
    heading_texts = []   # 原始「标签+编号」条头串，喂给 OrdinalStyle.detect_style 判族
    seen_en = False
    seen_cn = False
    for pg in pages:
        try:
            with open(pg, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        # Scan PER BLOCK (not the whole page joined into one string) so we can
        # tell whether a "Label N.M" sits at a block boundary — the strongest
        # signal that it is a real heading rather than a mid-prose reference.
        blocks = [blk_text(b) for b in data.get('text', [])
                  if isinstance(b, dict)]
        for block in blocks:
            if not block:
                continue
            stripped = block.lstrip()
            lead = len(block) - len(stripped)   # leading whitespace before match
            for ci, rx, form_by_lower in label_res:
                for m in rx.finditer(block):
                    # Only accept a heading that is at (or near) the block start,
                    # OR in a short block where the match dominates the content.
                    # Anything deeper in a long block is body prose / a
                    # cross-reference and must NOT seed a config label.
                    if (m.start() - lead > HEADING_LEAD_MAX
                            and len(stripped) > HEADING_SHORT_MAX):
                        continue
                    # label-first: groups 1=label, 2=num ; number-first: 3=num, 4=label
                    if m.group(1) is not None:
                        lab_txt, numstr = m.group(1), m.group(2)
                    else:
                        numstr, lab_txt = m.group(3), m.group(4)
                    prefix = block[:m.start()]
                    tail = block[m.end():]
                    # skip cross-references ('见 定义 1.5-3') and prose ('定理 2.1 的证明')
                    if _is_crossref_prefix(prefix) or not _is_header_boundary(tail):
                        continue
                    form = form_by_lower.get(lab_txt.lower(), lab_txt)
                    comps = _parse_comps(numstr, letter_chapter=letter_chapter)
                    if not comps:
                        continue
                    headings.append((ci, form, comps))
                    heading_texts.append(m.group(0))
                    if form[0].isascii() and form[0].isalpha():
                        seen_en = True
                    else:
                        seen_cn = True

    # family vote — the numbering FAMILY is elected by ordinal_styles'
    # `OrdinalStyle.detect_style`, the SAME judgment standard the rest of the
    # pipeline uses (lib/ordinal_styles.py).  We feed it the position-guarded,
    # cross-ref-filtered heading STRINGS collected above (e.g. '定理1.1.1',
    # 'Definition A.1.1', 'Theorem B.2'), so the family decision and the md-side
    # key parsing share ONE source of truth.  detect_style votes specificity-first
    # (three-level > two-level > single-level; appendix letter-slot → 13/14) and
    # returns None when no numbering style matches (unnumbered book) — the caller
    # then OMITS the ordinal group rather than fabricating a `{"type": 3}` entry.
    # 🔴 Only the codes ordinal_styles implements can be emitted: {1,2,3,8,12,13,14}
    #    (None = unnumbered).  The legacy codes 4/9/10/11 are DEPRECATED and were
    #    folded into the nearest canonical code (4→2, 9/10→3, 11→1); detection emits
    #    them directly with no load-time remap: an EN two-level book
    #    now elects 2, a cn3lab book elects 3 (bare `C.S-N` key — per-label counters
    #    are no longer distinguished at the family level), exactly as the user-directed
    #    clean migration accepts.
    style = OrdinalStyle.detect_style(heading_texts)
    family = style.code if style is not None else None
    # chapter_map may declare a code the page scan still cannot separate
    # confidently — vakil (8, number-first + letter third dim) and Humphreys
    # (12, bare / LETTER-only headings that the digit-anchored scan never
    # captures).  Trust the explicit declaration for those two.
    cm = _ordinal_from_chapter_map(extract_dir)
    cm_ord = cm[0] if cm else None
    cm_chapter_first = cm[1] if cm else True
    if cm_ord is not None and cm_ord in (8, ORDINAL_HUM):
        family = cm_ord
    # language: derive from the ACTUAL label forms seen
    if seen_en:
        lang = 'en'
    elif seen_cn:
        lang = 'cn'
    else:
        lang = None
    # A numbered entry heading in a multi-level book must carry at least TWO
    # numbering components (chapter.item / chapter.section.item).  A lone
    # number next to a label ("Axiom 211", "Theorem 4", "Problem 135") is a
    # cross-reference, footnote, page-reference or other prose mention — NOT a
    # heading that DEFINES a new entry.  Kreyszig, for example, has 33 prose
    # 'Axiom' mentions but ZERO real Axiom headings; keeping the 1-component
    # noise would fabricate an 'Axiom' group.  Single-component headings are
    # kept only for depth-1 (single global counter) books.
    if family is None:
        # No detectable ordinal numbering — return empty groups; the caller
        # will omit the ordinal key rather than fabricate an `uncat` group.
        return None, [], lang, cm_chapter_first
    depth = ordinal_depth(family)
    if depth >= 2:
        headings = [h for h in headings if len(h[2]) >= 2]
    # 🔴 计数器分组的证据 = **结构契约（按标签）∪ OCR 标题扫描**。契约条目是
    # 去噪后的权威样本（键 + 类型俱全），但**只覆盖它已经抽到的标签**：附录首轮
    # 实测（Shafarevich《Basic Algebraic Geometry 1》）旧契约里没有 `Corollary`
    # 节点，纯契约证据会让该标签整个隐形、探测只给一组，bootstrap 死锁。故
    # **契约没有的标签**沿用其 OCR 标题；同一标签内只用契约一套样本，绝不与
    # OCR 的交叉引用噪声混用（混用会把共享计数器书按假重号拆散——Lee/Rosen 实测
    # 回归）。无契约（首次 config 先于 structure）时保持原 OCR 路径零回归。
    # 正文与附录/补篇（letter_chapter）两条生成都走这条通路——附录键自带字母
    # 章位窗口（`A.N` → ('A',N)），证据形态与 OCR 的 `_parse_comps` 一致。
    _contract_evidence = None
    _single_level_windowed = False
    _ev = None
    if letter_chapter and depth >= 2:
        _ev = _contract_counter_evidence(extract_dir, letter_chapter=True)
    elif not letter_chapter and depth >= 2:
        _ev = _contract_counter_evidence(extract_dir)
    elif not letter_chapter and family == 1:
        # 🔴 单级书：契约条目键只含裸序号（'定理1'），把**所属章号补成窗口分量**
        # comps=(chapter, num) 后即拥有可比较的窗口，`_shares_main_counter` 的
        # 「同窗重号」判据得以区分「共享一条计数器」与「章内各自重起的平行计数
        # 器」，取代 `_group_single_level` 的「statement 标签一律合并」硬约定。
        # Arnold《ODE》实测：第 2 章同时存在 Theorem 1-3、Corollary 1-12、
        # Lemma 1-4——三族在窗口 (2,) 内重号 → 各自独立，拆成三个具名组。
        _ev = _contract_counter_evidence(extract_dir, include_chapter=True)
        if _ev:
            _single_level_windowed = True
    if _ev:
        _contract_evidence = _ev
        _have = {_FORM_CANON.get(str(f).lower()) for f, _c in _ev}
        # 契约覆盖的标签：只取契约样本（干净）；契约没覆盖的标签：补该标签的
        # OCR 标题，避免它在证据里整个隐形。
        headings = ([(0, f, c) for (f, c) in _ev]
                    + [h for h in headings
                       if _FORM_CANON.get(str(h[1]).lower()) not in _have])
    # group by shared counter.  Single-level (type 1) books WITHOUT a structure
    # contract have no chapter window (OCR headings carry only a bare number),
    # so they fall back to the domain convention (_group_single_level).  With a
    # contract, chapter-windowed evidence drives the same duplicate-based split
    # as multi-level books (see above).
    if family == 1 and not _single_level_windowed:
        groups = _group_single_level(headings)
    else:
        # 契约证据是完备样本：min==1 的 reset 判据关闭（共享计数器书各标签
        # 轮流当节首，见 _shares_main_counter 注释）。单级窗口深度按 2 处理
        # （comps = (chapter, num) 两段）。
        groups = _group_headings_by_counter(
            headings, max(2, depth), strict_reset=not _contract_evidence)
    if family == ORDINAL_HUM:
        # config_setting 规则5（ORDINAL_HUM = 12，Humphreys《Intro to Lie Algebras
        # and Representation Theory》GTM 9）：正文条目头只印裸标签（"Lemma." /
        # "Theorem (Cartan's Criterion)."）或节内大写字母号（"Lemma A"），没有
        # 「标签+数字」形态的可分组编号头，上面的计数器分组必然落空/掺引用噪声。
        # 按全书实测固定：每类标签独立一组（各类条目由所在小节隐式定位，
        # 互不共享计数器；Table 同理按节重编）。Figure 单独一组（图号 "Figure 1"
        # 单段、按小节重编 → type 1 全局整数解析）。
        groups = [["Theorem"], ["Proposition"], ["Corollary"], ["Lemma"],
                  ["Example"], ["Remark"], ["Table"]]
    return family, groups, lang, cm_chapter_first


def _detect_exercise_counter(extract_dir, pages=None):
    """Detect a PRESERVED (interleaved) first-level exercise counter.

    Exercises come in two flavors per writing-rules §习题（练习）收录规则:
      * consolidated blocks — a dedicated "Exercises"/"练习"/"Problems" header
        followed by bare "1." "2." "3." ordinals. OMITTED from the summary,
        must NOT be verified (their nodes carry `consolidated:true`).
      * preserved exercises — bare "N. <text>" ordinals appearing inline among
        definitions/theorems with NO such header. Kept in the summary AND
        SHOULD be verified.

    This returns True ONLY when it finds a run of >= MIN_RUN consecutive bare
    first-level ordinals that is NOT inside a consolidated-exercise zone (i.e.
    not near a page that carries an "Exercises/练习" header).  That
    correctly returns False for Fraleigh (every exercise ordinal there lives on
    a consolidated-block page) while still letting books with genuine preserved
    exercises get a type:1 group.

    It deliberately does NOT scan "Exercise N" / "N Exercise" surface forms,
    because those are overwhelmingly body cross-references, not headings.

    🔴 Two blind spots fixed on Fraleigh (2026-09-26, 161 false B-layer 「缺号」):
      * the old zone test used a word-boundary regex only, but OCR glues the
        printed heads (``EXERCISESO`` / ``InExercises21through6,determine…``), so
        whole exercise sections were never marked;
      * ``header page +/- 2`` cannot cover an exercise block that runs 3+ pages.
    Both are fixed below: the block-head judge is shared with the writing gate
    (`lib.problem_coverage.is_consolidated_head`), and a zone is EXTENDED forward
    while the following pages stay ordinal-dominant. Counting also requires the
    ordinal to OPEN its text block, so in-body enumerations ("1. closure 2. identity")
    buried inside a definition block no longer build a run.
    """
    from lib.problem_coverage import is_consolidated_head

    EXER_HEAD_RE = re.compile(
        r'\b(?:Exercises?|Problems?|习题|练习|问题)\b', re.IGNORECASE)
    # bare "N. <text>" — a number, a dot, then an alphabetic / Han start.
    BARE_RE = re.compile(r'(?:^|(?<=[)\]}\s])|[\s])(\d+)\.\s*[A-Za-z一-鿿]')
    # ordinal that OPENS its block (an exercise item, not a sentence-internal list)
    BARE_OPEN_RE = re.compile(r'^\s*(?:>\s*)?(?:[-*+]\s*)?(\d{1,3})[.)]\s*[A-Za-z一-鿿]')
    pages = pages if pages is not None else sorted(
        glob.glob(os.path.join(extract_dir, 'page_*.json')))

    def _load(pg):
        try:
            with open(pg, encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    def _pno(pg):
        return int(re.search(r'(\d+)', os.path.basename(pg)).group(1))

    loaded = [(pg, _pno(pg), _load(pg)) for pg in pages]
    loaded = [(p, n, d) for p, n, d in loaded if d is not None]
    loaded.sort(key=lambda x: x[1])

    def _head(text):
        return bool(EXER_HEAD_RE.search(text)) or is_consolidated_head(text)

    def _opens(texts):
        return [int(m.group(1)) for t in texts
                for m in [BARE_OPEN_RE.match(t)] if m]

    # Pass 1: consolidated-exercise header pages.
    head_pages = set()
    for _p, pno, data in loaded:
        if any(_head(t) for t in map(blk_text, data.get('text', []) or []) if t):
            head_pages.add(pno)
    # Pass 2: mark the zone = header page +/-1, EXTENDED forward while the page
    # still carries an ordinal run (>=3 block-opening items, continuing locally).
    zone = set()
    for pno in head_pages:
        zone.update(range(pno - 2, pno + 2))
    active = 0
    for _p, pno, data in loaded:
        texts = [blk_text(b) for b in (data.get('text', []) or [])]
        texts = [t for t in texts if t]
        nums = _opens(texts)
        if pno in head_pages:
            active = max(2, 0)
            zone.add(pno)
            continue
        if active > 0:
            zone.add(pno)
            active -= 1
            if len(nums) >= 3:
                active = 2
    # Pass 3: look for bare consecutive ordinal runs on NON-zone pages.
    # 🔴 判据（Fraleigh 2026-09-26 实测）：修好习题区标记后，区外只剩 5 条 run，
    # 最长 4，全部是正文里的枚举（定义内「1. closure 2. associativity …」／判断题
    # 分项）。两条放行规则据此分开真/假：**单条长链**（≥ MIN_RUN，一节列 5 题以上）
    # 或**多处短链**（≥ MIN_SPOTS 个不同页各有一链——每节 3~4 题的小计数器）。
    MIN_RUN = 5
    MIN_SPOTS = 6
    run = [1, None]   # [当前连续长度, 上一序号]（跨页/跨块延续）
    spots = set()     # 出现过 ≥3 链的页（短链计数器证据）
    for _p, pno, data in loaded:
        if pno in zone:
            run[0], run[1] = 1, None   # 进入练习区页：run 重置
            continue
        for b in data.get('text', []):
            if not isinstance(b, dict):
                continue
            text = blk_text(b)
            if not text:
                continue
            # 连续序号 run 跨块累计（每条练习通常独占一个块，按块重置会让
            # run 永远到不了 3）：prev_num/run 为函数级状态，块间延续。
            nums = [int(x) for x in BARE_RE.findall(text)]
            head = BARE_OPEN_RE.match(text)
            for i, nnum in enumerate(nums):
                if i == 0 and not head:
                    run[0], run[1] = 1, None
                    break
                if i > 0 and nnum == nums[i - 1] + 1:
                    run[0] += 1
                elif i == 0 and run[1] is not None and nnum == run[1] + 1:
                    run[0] += 1
                else:
                    run[0] = 1
                run[1] = nnum
                if run[0] >= MIN_RUN:
                    return True
                if run[0] >= 3:
                    spots.add(pno)
                    if len(spots) >= MIN_SPOTS:
                        return True
    return False


# 🔴 图编号体例探测（2026-09-24 Atiyah–Macdonald 实测坑）：`lib.figure_io.load_fig_components`
# 已禁止静默默认——`ordinal` 缺 Figure 组直接抛 ConfigError，verify --all 在首个读图配置
# 的章**全局中断**。而旧 make_config 只为 HUM 书或老配置已有组的书产出 Figure 组，普通
# 「图无编号」书生成出的 config 必崩，且 `--force` 重生成同样缺组（唯一 sanctioned 出路被
# 堵死）。修在生成侧：探测印刷图题（≥2 个不同图号的系列，防交叉引用假阳性）产出对应段数
# 组；无系列则显式 `type: 0`（UNNUMBERED，图号零匹配），保证生成器输出恒满足消费者契约。
_FIG_CAP_RE = re.compile(
    r'(?:(?:^|(?<=[\s(]))(?:Figure|Figures|Fig|Figs)\.?\s*'
    r'([0-9]+(?:[.\-．][0-9]+){0,2})\b)'
    r'|(?<![A-Za-z])(?:图|圖)\s*([0-9]+(?:[.\-．][0-9]+){0,2})',
    re.IGNORECASE)


def _detect_fig_numbering(extract_dir, pages=None):
    """Return ``(depth, labels)`` describing the book's printed figure scheme.

    depth：图号**段数众数**（1=全局整数 / 2=章.图 / 3=章.节.图），无图题系列则 0
    （显式无图编号）。labels：观测到的印刷前缀（"Figure"/"Fig"/"图" 子集）。
    判据要求 **≥2 个不同图号**——正文交叉引用（"see Figure 7"）即便高频也只贡献同号，
    不会伪造出一个体例；真图题天然成系列。
    """
    pages = pages if pages is not None else sorted(
        glob.glob(os.path.join(extract_dir, 'page_*.json')))
    seen = set()      # 不同图号（系列判据）
    depths = {}       # 段数 -> 命中数
    labels = set()
    for pg in pages:
        try:
            with open(pg, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        for b in data.get('text', []):
            text = blk_text(b) if isinstance(b, dict) else ''
            if not text:
                continue
            for m in _FIG_CAP_RE.finditer(text):
                num = m.group(1) or m.group(2)
                seen.add(num)
                comps = 1 + num.count('.') + num.count('-') + num.count('．')
                d = max(1, min(3, comps))
                depths[d] = depths.get(d, 0) + 1
                surf = m.group(0)
                if '图' in surf or '圖' in surf:
                    labels.add('图')
                elif re.search(r'(?i)figur', surf):
                    labels.add('Figure')
                else:
                    labels.add('Fig')
    if len(seen) < 2:
        return 0, sorted(labels)
    # 段数取众数；平票取**更大**段数（三级书常混出两级交叉引用，取大不取小）
    best = sorted(depths.items(), key=lambda kv: (-kv[1], -kv[0]))[0][0]
    return best, sorted(labels)


# Appendix exercises print a LETTER chapter slot and are NOT part of
# LABEL_FORMS (which deliberately omits Exercise to avoid cross-reference
# fabrication).  Detect them separately so the appendix config can carry the
# exercise counter — a preserved/interleaved appendix exercise sequence is a
# real verified one, exactly like a body one.  Two shapes exist in the wild:
#   * three-level `Exercise A.1.1`（Weibel 式，条目与练习都带节段）
#   * two-level   `Exercise B.4`（Lee ISM 附录实测 101 次命中：练习编号与
#     条目同为「字母章.序」两段，无节段）——canon 层对两段键本就兼容
#     （check_structure_completeness._canon_key: 'A.1' -> ('A', 1)）。
# The `[A-Z]\.` slot requirement keeps digit-chapter `Exercise 7.35`
# cross-references from the body config's counter out of the appendix probe.
_APP_EX_RE = re.compile(
    r'(?i)\bexercise\b\s*([A-Z]\.\d+(?:\.\d+)?)'
    r'|\b([A-Z]\.\d+(?:\.\d+)?)\s+exercises?\b')


def _detect_appendix_exercise(extract_dir, pages):
    """附录保留式练习计数器探测 → ``(present, shared)``。

    ``present``：附录页区间存在字母章位练习标题（两段/三级均可）。
    ``shared``：练习与条目**共享同一计数器**（一起升序）——判据 = 同前缀组
    （两段按字母、三级按 字母.节）内练习号的跳号率：共享计数器里条目占用
    序列空位 → 练习号大量跳号（Lee A 章 1,2,3,9,11,13,…，A.4-A.8 是
    Example）；独立平行计数器组内近似连续（Weibel A.1.1,A.1.2,A.1.3…）。
    ``shared=True`` 时调用方把 ``Exercise`` 并入主组 name；``False`` 时追加
    独立 Exercise 组。
    """
    nums = []  # (prefix_tuple, last_int)
    for pg in (pages or []):
        try:
            with open(pg, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        for b in data.get('text', []):
            text = blk_text(b) if isinstance(b, dict) else ''
            if not text:
                continue
            for m in _APP_EX_RE.finditer(text):
                raw = m.group(1) or m.group(2)
                parts = raw.split('.')
                if len(parts) == 2:
                    nums.append(((parts[0].upper(),), int(parts[1])))
                else:
                    nums.append(((parts[0].upper(), int(parts[1])), int(parts[2])))
    if not nums:
        return False, False
    # 按前缀分组投票：组内（样本 >=3）跳号率 = 相邻差>1 占比
    groups = {}
    for pre, n in nums:
        groups.setdefault(pre, []).append(n)
    votes = 0
    total = 0
    for pre, seq in groups.items():
        seq = sorted(seq)
        if len(seq) < 3:
            continue
        gaps = sum(1 for i in range(1, len(seq)) if seq[i] > seq[i - 1] + 1)
        votes += 1 if gaps / (len(seq) - 1) >= 0.25 else 0
        total += 1
    shared = total > 0 and votes * 2 > total
    return True, shared


# 正文保留式练习印在**数字章位**（`Exercise 7.35`），与附录的字母章位不同。
# `_detect_exercise_counter` 明确「不扫描 `Exercise N` 表面形态」（那是正文里
# 最典型的交叉引用形态），故这里单独探测。
# 判据 = **共用计数器的真签名**（三者同时成立），而非只看练习号跳号：
#   * 不相交：同一章窗内练习号与条目号**不重号**（共用一条 1..N 序列时两者
#     天然互补；平行独立计数器必然重号，如 Problem 6.3-1 与 Definition 6.3-1）；
#   * 并集稠密：练习号 ∪ 条目号 覆盖 min..max 的 ≥90%（同一条序列被两类瓜分）；
#   * 练习侧跳号：练习号自身大量跳号（相邻差>1 占比 ≥25%），说明空位被条目占用。
# 只按「跳号」单判会把**自身稀疏**的独立练习计数器误判为共享（实测 AoPS/交换
# 代数等书练习号本身就跳号），故必须叠加不相交 + 并集稠密。
_EX_CH_RE = re.compile(
    r'(?i)\bexercise\b\s*(\d+)\.(\d+)'
    r'|\b(\d+)\.(\d+)\s+exercises?\b')
# 条目（非练习）标签头：EN + CN 常用标签，数字章位两段。
_ITEM_CH_RE = re.compile(
    r'(?i)(?:theorem|proposition|lemma|corollary|example|definition|remark'
    r'|定理|命题|引理|推论|例|定义|评注)\s*(\d+)\.(\d+)'
    r'|(\d+)\.(\d+)\s+(?:theorem|proposition|lemma|corollary|example|definition|remark)')


def _detect_chapter_exercise_shared(extract_dir, pages=None):
    """正文保留式练习是否与条目**共享同一章内计数器** → ``bool``。

    见上方判据注记（不相交 + 并集稠密 + 练习侧跳号，按章窗多数投票）。
    ``True`` 时调用方在 config 落 ``exercise_shared_numbering: True``。
    """
    ex_by_ch, item_by_ch = {}, {}
    for pg in (pages if pages is not None else sorted(
            glob.glob(os.path.join(extract_dir, 'page_*.json')))):
        try:
            with open(pg, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        for b in data.get('text', []):
            text = blk_text(b) if isinstance(b, dict) else ''
            if not text:
                continue
            for m in _EX_CH_RE.finditer(text):
                ch, n = ((m.group(1), m.group(2)) if m.group(1)
                         else (m.group(3), m.group(4)))
                try:
                    ex_by_ch.setdefault(int(ch), set()).add(int(n))
                except ValueError:
                    continue
            for m in _ITEM_CH_RE.finditer(text):
                ch, n = ((m.group(1), m.group(2)) if m.group(1)
                         else (m.group(3), m.group(4)))
                try:
                    item_by_ch.setdefault(int(ch), set()).add(int(n))
                except ValueError:
                    continue
    votes = total = 0
    for ch, ex in ex_by_ch.items():
        if len(ex) < 3:
            continue
        items = item_by_ch.get(ch, set())
        if ex & items:                      # 重号 → 平行独立计数器
            total += 1
            continue
        union = sorted(ex | items)
        span = union[-1] - union[0] + 1
        dense = span > 0 and len(union) / span >= 0.9
        seq = sorted(ex)
        gaps = sum(1 for i in range(1, len(seq)) if seq[i] > seq[i - 1] + 1)
        gappy = gaps / (len(seq) - 1) >= 0.25
        total += 1
        votes += 1 if (dense and gappy) else 0
    return total > 0 and votes * 2 > total


def detect_labels(extract_dir):
    """Flat list of ALL entry-type label forms detected as numbered headings
    (across every counter group).  Empty => caller falls back to ``["uncat"]``.
    """
    _, groups, _, _ = _detect_ordinal_from_pages(extract_dir)
    out = []
    for g in groups:
        out.extend(g)
    seen = set()
    res = []
    for x in out:
        if x not in seen:
            seen.add(x)
            res.append(x)
    return res


# --- appendix chapter detection --------------------------------------------
# 附录章定位：与 ConfigLoader.is_appendix_chapter 严格同源（章名含
# Appendix/附录，或章号为字母 A/B/C…）。优先读 chapter_map（已登记的附录），
# 缺失时回退 OCR 扫描 "Appendix X" / "附录X" 标题页。
_APPENDIX_NAME_RE = re.compile(r'(?:^|[^A-Za-z])(?:appendix|appendices)\b|附录',
                               re.IGNORECASE)
_APPENDIX_OCR_RE = re.compile(r'^\s*Appendi(?:x|ces)\s+([A-Z])\b', re.IGNORECASE)


def _chapter_map_appendix_chapters(extract_dir):
    """chapter_map.json 中已登记的附录章（章名或字母章号）。"""
    cm_p = os.path.join(extract_dir, 'chapter_map.json')
    if not os.path.exists(cm_p):
        return []
    try:
        cm = json.load(open(cm_p, encoding='utf-8-sig'))
    except Exception:
        return []
    nodes = cm.get('chapters') if isinstance(cm, dict) else cm
    if not isinstance(nodes, list):
        return []
    out = []
    for e in nodes:
        if not isinstance(e, dict):
            continue
        ch = e.get('ch', e.get('num', e.get('chapter')))
        name = f"{e.get('name','')} {e.get('name_en','')} {e.get('name_cn','')}"
        key = str(ch)
        if _APPENDIX_NAME_RE.search(name) or (key and not key[:1].isdigit()):
            out.append({'ch': ch, 'name': e.get('name') or e.get('name_en') or name,
                        'start': e.get('start'), 'end': e.get('end')})
    out.sort(key=lambda d: (str(d['ch']) if d['ch'] is not None else ''))
    return out


def _ocr_appendix_chapters(extract_dir):
    """chapter_map 未登记附录时，从 OCR 定位 `Appendix X` 标题页（取首个命中页）。"""
    pages = sorted(glob.glob(os.path.join(extract_dir, 'page_*.json')),
                   key=lambda p: int(re.search(r'page_(\d+)\.json', p).group(1)))
    hits = {}
    for p in pages:
        try:
            data = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        for b in data.get('text', []):
            txt = b.get('text', '') if isinstance(b, dict) else ''
            m = _APPENDIX_OCR_RE.match(txt.strip())
            if m:
                letter = m.group(1).upper()
                if letter not in hits:
                    hits[letter] = int(re.search(r'page_(\d+)\.json', p).group(1))
    if not hits:
        return []
    last = int(re.search(r'page_(\d+)\.json', pages[-1]).group(1))
    # 多附录（A、B…）：每个附录的 end = 下一附录起点 - 1（末附录到全书末页）。
    # 旧实现一律给 end=全书末页，会把后面附录的页也算进前面附录的扫描区间。
    letters = sorted(hits.items())
    out = []
    for i, (letter, start) in enumerate(letters):
        end = letters[i + 1][1] - 1 if i + 1 < len(letters) else last
        out.append({'ch': letter, 'name': f'Appendix {letter}',
                    'start': start, 'end': end})
    return out


def _chapter_map_special_chapters(extract_dir, kind):
    """chapter_map.json 中登记为指定 kind 的章（kind=2 附录 / kind=3 补篇）。

    kind 缺失时按章名双信号回退（见下方注释），与 ConfigLoader 的附录判据同源。
    """
    cm_p = os.path.join(extract_dir, 'chapter_map.json')
    if not os.path.exists(cm_p):
        return []
    try:
        cm = json.load(open(cm_p, encoding='utf-8-sig'))
    except Exception:
        return []
    nodes = cm.get('chapters') if isinstance(cm, dict) and 'chapters' in cm else []
    if not nodes and isinstance(cm, dict):
        nodes = [dict(e, **({'ch': k} if ('ch' not in e and 'num' not in e and 'chapter' not in e) else {}))
                 for k, e in cm.items() if isinstance(e, dict)]
    out = []
    for e in nodes:
        if not isinstance(e, dict):
            continue
        _name = str(e.get('name') or e.get('name_en') or e.get('title') or '')
        _raw_kind = e.get('kind', None)
        if _raw_kind is None:
            # 🔴 双信号回退（Shafarevich《Basic Algebraic Geometry 1》实测）：
            # chapter_map 未写 kind 时，**章名**就是附录/补篇判据——与
            # `ConfigLoader.is_appendix_chapter`、`build_structure._is_appendix`
            # 同源（二者都认「章名含 Appendix/附录」）。只认显式 kind 会让本书
            # "Algebraic Appendix" 落回主配置：正文 type 2 的两段号（`3.1`）正则
            # 撞不上附录的字母章位（`Proposition A.1`）→ appendix5 契约 items=0、
            # 17 条 Proposition + 3 条 Corollary 整批从结构里消失。
            if kind == KIND_APPENDIX and _APPENDIX_NAME_RE.search(_name):
                k = KIND_APPENDIX
            elif kind == KIND_SUPPLEMENT and SUPPLEMENT_NAME_RE.search(_name):
                k = KIND_SUPPLEMENT
            else:
                continue
        else:
            k = int(_raw_kind or 1)
        if k != kind:
            continue
        ch = e.get('ch', e.get('num', e.get('chapter')))
        if ch is None:
            continue
        out.append({'ch': ch, 'name': _name,
                    'start': e.get('start'), 'end': e.get('end')})
    out.sort(key=lambda d: str(d['ch']))
    return out


_SUPPLEMENT_OCR_RE = re.compile(r'^\s*Suppleme(?:nt|ntary)\s+([A-Z])\b', re.IGNORECASE)


def _ocr_supplement_chapters(extract_dir):
    """chapter_map 未登记补篇时，从 OCR 定位 `Supplement X` 标题页。"""
    pages = sorted(glob.glob(os.path.join(extract_dir, 'page_*.json')),
                   key=lambda p: int(re.search(r'page_(\d+)\.json', p).group(1)))
    hits = {}
    for p in pages:
        try:
            data = json.load(open(p, encoding='utf-8'))
        except Exception:
            continue
        for b in data.get('text', []):
            txt = b.get('text', '') if isinstance(b, dict) else ''
            m = _SUPPLEMENT_OCR_RE.match(txt.strip())
            if m:
                letter = m.group(1).upper()
                if letter not in hits:
                    hits[letter] = int(re.search(r'page_(\d+)\.json', p).group(1))
    if not hits:
        return []
    last = int(re.search(r'page_(\d+)\.json', pages[-1]).group(1))
    letters = sorted(hits.items())
    out = []
    for i, (letter, start) in enumerate(letters):
        end = letters[i + 1][1] - 1 if i + 1 < len(letters) else last
        out.append({'ch': letter, 'name': f'Supplement {letter}',
                    'start': start, 'end': end})
    return out


def _detect_special_chapters(extract_dir, kind):
    """返回本书指定 kind 的章列表（含章号/名称/页区间）。无则返回 []。

    优先读 chapter_map 显式 kind；缺失时按 kind 选 OCR 回退（附录→"Appendix X"、
    补篇→"Supplement X"）。"""
    out = _chapter_map_special_chapters(extract_dir, kind)
    if not out:
        out = (_ocr_appendix_chapters(extract_dir) if kind == KIND_APPENDIX
               else _ocr_supplement_chapters(extract_dir))
    return out


def _special_page_files(extract_dir, chapters):
    """指定章覆盖的 page_*.json 文件列表（按 start..end 区间并集）。"""
    nums = set()
    for c in chapters:
        s = c.get('start')
        e = c.get('end')
        if isinstance(s, int) and isinstance(e, int):
            for n in range(s, e + 1):
                nums.add(n)
    if not nums:
        return None
    files = []
    for n in sorted(nums):
        fp = os.path.join(extract_dir, f'page_{n:03d}.json')
        if os.path.exists(fp):
            files.append(fp)
    return files or None


def _build_config_dict(extract_dir, cfg_path, *, letter_chapter=False,
                      is_appendix=False, pages=None, section_key="ch"):
    """Detection + assembly for ONE book-config (main / appendix / supplement).

    Shared by `main()` (the mandatory `verify_config.json` "ch" sub-config) and
    the optional `appendix` / `supplement` sub-configs so they never drift in
    schema.  Returns ``(config_dict, family, groups, ordinal, depth)``; the
    caller writes/presents (assembled into the outer map by `main()`).

    `pages` restricts the scan to an explicit page range (special generator
    passes ONLY that kind's pages); `letter_chapter` enables the letter-slot
    letter-slot numbering detection (`Definition A.1.1`).

    `section_key` ("ch" / "appendix" / "supplement") tells `_load_old_ordinal`
    which sub-config's `ordinal` to preserve on a `--force` regenerate — so the
    map-format nesting (latest schema) round-trips zero-regression instead of
    dropping the Figure group.
    """
    family, groups, lang, cm_chapter_first = _detect_ordinal_from_pages(
        extract_dir, pages=pages, letter_chapter=letter_chapter)
    ordinal = family
    language = (lang if lang
                else (ORDINAL_LANGUAGE_DEFAULT.get(ordinal, 'cn')
                      if ordinal is not None else 'cn'))
    depth = ordinal_depth(ordinal)
    formula_cfg = detect_formula(extract_dir, pages=pages)
    # scope: 三级（type 3）与附录字母章位三级（13）按「节」重置 → scope=3；
    # 其余（单级 1 / 两级 2 / vakil 8 / hum 12 / 附录两级 14）按章重置 → 2。
    SCOPE_BY_TYPE = {1: 2, 2: 2, 3: 3, 8: 2, 12: 2, 13: 3, 14: 2}
    ordinal_arr = []
    if ordinal is not None:
        if is_appendix:
            if ordinal == ORDINAL_APP2:
                # 两段附录字母章位（Lee ISM `Label B.N`）：计数器跨全附录连续
                # （Example A.4-A.8 不分节重置）、每字母章从 1 重开 → 章级
                # 计数器（scope=2，首分量=字母与章键 'A'/'B'… 比对，跨章
                # 守卫天然成立）。
                scope = 2
            else:
                # 🔴 三级附录字母章位（Weibel `Label A.S.N`）：所有标签共享
                # 「按节(A.S)重置」的计数器（A.1.1, A.1.2 … 然后 A.2.1 重置），
                # scope=3，避免字母章位窗口把每个 (A.S) 拆成独立 group。
                scope = 3
            # 🔴 **保留探测出的计数器划分**，不得把 groups 压成一个标签列表。
            # 旧实现一律 flatten（Lee ISM 附录「全部标签共享一条计数器」的经验
            # 值），代价实测在 Shafarevich《Basic Algebraic Geometry 1》的
            # Algebraic Appendix：那里 `Proposition A.1-A.17` 与
            # `Corollary A.1-A.3` 是**平行计数器**（探测已正确拆成两组），压成一组
            # 后 `label_group` 认为同组 → 同页异标签按数字序裁决 → `Corollary A.1`
            # 顶到 `Proposition A.11`（印面在其后）之前，ANCHOR-SANITY 拒绝落盘；
            # 且 O/B 层按合并号段判缺号会双向造假阳。探测只给一组时（Lee 式共享）
            # 行为与旧实现逐字相同，零回归。
            for name in (groups or [["uncat"]]):
                ordinal_arr.append({
                    "type": ordinal,
                    "name": [nm for nm in name if nm] or ["uncat"],
                    "scope": scope,
                })
        else:
            scope = SCOPE_BY_TYPE.get(ordinal, 2)
            for name in groups:
                ordinal_arr.append({
                    "type": ordinal,
                    "name": name if name else ["uncat"],
                    "scope": scope,
                })
    if not cm_chapter_first and ordinal_arr:
        if len(ordinal_arr) > 1:
            merged = []
            for g in ordinal_arr:
                for nm in g["name"]:
                    if nm not in merged:
                        merged.append(nm)
            ordinal_arr = [{"type": ordinal, "name": merged, "scope": scope}]
        sole = ordinal_arr[0]
        for extra in ("Table", "Figure"):
            if extra not in sole["name"]:
                sole["name"].append(extra)
    if _detect_exercise_counter(extract_dir, pages=pages):
        ordinal_arr.append({
            "type": 1,
            "name": ["练习", "习题", "Exercise", "Problem"],
            "scope": 3,
        })
    if ordinal == ORDINAL_HUM and not any(
            any(_is_fig_kw(nm) for nm in g.get("name", [])) for g in ordinal_arr):
        ordinal_arr.append({"type": 1, "name": ["Figure"], "scope": 1})
    if not any(any(_is_fig_kw(nm) for nm in g.get("name", [])) for g in ordinal_arr):
        for g in _load_old_ordinal(cfg_path, section_key):
            if any(_is_fig_kw(nm) for nm in g.get("name", [])):
                # 🔴 图号计数器与**条目**计数器正交（Figure 单独成组的全部理由）。
                # 旧实现把继承来的组按正文字段重打 `type=ordinal,
                # scope=SCOPE_BY_TYPE[ordinal]`——Shafarevich《Basic Algebraic
                # Geometry 1》实测：图全局整数编号（`Figure 1…26`，旧账
                # type 1/scope 1），条目两段号（type 2），`--force` 重生成于是
                # 把 Figure 悄悄改成 type 2/scope 2，此后 `load_fig_components`
                # 期待 `N.M` 形态 → 全部印面 `Figure 7` 失配（假缺号/顺序噪声）。
                # 继承即**原样回贴**（账本保真）；只有旧组本身缺 type/scope 时
                # 才退回正文字段（老配置的残缺记录）。
                _keep = dict(g)
                if "type" not in _keep:
                    _keep["type"] = (ordinal if ordinal is not None else 0)
                if "scope" not in _keep:
                    _keep["scope"] = SCOPE_BY_TYPE.get(_keep["type"], 2)
                _keep["name"] = _keep.get("name") or ["Figure"]
                ordinal_arr.append(_keep)
                break
    # 🔴 生成器契约自洽（2026-09-24 AM 实测坑，负向测试
    # config/verify_config/tests/test_fig_group_guarantee.py）：figure_io 的
    # load_fig_components **禁止静默默认**——缺 Figure 组即抛 ConfigError 且中断
    # 整轮 verify。探测/老配置继承两条来源都没有组时，必须显式落组：探到图题系列
    # 按其段数（1/2/3），否则 `type: 0`（UNNUMBERED = 图号零匹配，显式而非默认）。
    if not any(any(_is_fig_kw(nm) for nm in g.get("name", [])) for g in ordinal_arr):
        _fig_depth, _fig_labels = _detect_fig_numbering(extract_dir, pages=pages)
        ordinal_arr.append({
            "type": _fig_depth,
            "name": _fig_labels or ["Figure"],
            "scope": 1 if _fig_depth == 1 else 2,
        })
    # 🔴 计数器边界两补：① 单级探测只有 scope 2/3 两档，先按**结构契约**补判
    # 「跨章连续」= scope 1；② 旧账（含当年人工核准的那份）声明过的 scope 与
    # strict 一律回贴——`--force` 只该重扫体例，不该顺手改写既有书的判定边界。
    # Serre《Linear Representations of Finite Groups》实测：两处都缺时重生成把
    # 全书连续号判成每章重启并打开 strict，B 层对 26 章报假缺号（40/40 → 14/40）。
    if not is_appendix:
        ordinal_arr, _sc_notes = _refine_book_scope(extract_dir, ordinal_arr)
    else:
        ordinal_arr, _sc_notes = ordinal_arr, []
    ordinal_arr, _rp_notes = _repaste_old_scopes(cfg_path, ordinal_arr, section_key)
    ordinal_arr, _pt_notes = _repaste_old_partition(cfg_path, ordinal_arr, section_key)
    for _n in _sc_notes + _rp_notes + _pt_notes:
        print(f"[make_config] 计数器边界：{_n}")
    config = {
        "ordinal": ordinal_arr,
        "strict": True,
        "language": language,
    }
    _old_strict = _load_old_section_cfg(cfg_path, section_key).get("strict")
    if isinstance(_old_strict, bool):
        config["strict"] = _old_strict
    config["chapter_first"] = bool(cm_chapter_first)
    config["section_scoped"] = bool(not cm_chapter_first)
    if not is_appendix and _detect_chapter_exercise_shared(extract_dir, pages=pages):
        # Lee 式体例：正文练习（`Exercise C.N`）与定理/例**共用**章内同一条
        # 1..N 计数器（条目占掉序列空位 → 练习号大量跳号）。B 层
        # （item_numbering_integrity._lab 分窗）据此**不得**给练习另开 ``ex:``
        # 编号窗——否则练习组按 1..max 判缺号、非练习组按 min..max 判缺号，
        # 两侧同时报假 BLOCKING（Lee 2e 实测：全书 22 章 EN 共 42 FAIL）。
        # 附录侧同体例由 `_detect_appendix_exercise` 把 ``Exercise`` 并入主组
        # name 解决，自身不需要本字段，故只在正文段落落。
        config["exercise_shared_numbering"] = True
    if formula_cfg is not None:
        # 回贴 operator 登记（ignore / bare_number 是人工判断，探测层无法重建，
        # 见 _load_old_formula）——缺了这步，重生成即静默清空噪声账本。
        old_f = _load_old_formula(cfg_path, section_key)
        if old_f:
            formula_cfg.update(old_f)
        config["formula"] = formula_cfg
        if formula_cfg.get("type") is not None and "scope" not in formula_cfg:
            print("[make_config] ⚠️ formula 探测到 type=%r 但**无法从书中判定 scope**"
                  "（首分量证据不足，通常仅见单一章前缀）。`scope` 无默认值，加载期会硬"
                  "报错；请 agent 依书实际编号体例显式补 `formula.scope`"
                  "（1=全书连续 / 2=每章重启 / 3=每节重启）后再跑 verify。"
                  % (formula_cfg.get("type"),))
    config["_provenance"] = {
        "generated_by": "make_config.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mm_repair_done": True,
        "appendix": bool(is_appendix),
        "warning": ("手写/手改本文件无效；须由 make_config.py 在 MM Repair 完成后生成，"
                    "且下游 ConfigLoader 会校验 _extraction_done.json 与 _provenance。"),
    }
    sd = _detect_section_hierarchy(extract_dir, pages=pages,
                                  letter_chapter=letter_chapter)
    if ordinal == ORDINAL_HUM:
        sd = [1, 1]
    # 🔴 Arnold ODE 型三级结构（通用探测，非逐书硬编码）：全书用**单号全局 §**
    # 作节头（原书印 "§ 1. Title"），而每个 § 内又有**逐 § 从 1 重启的裸单号
    # 二级小节**（原书印 "1. Title"）。这是可被 production 扫描器稳定复现的
    # 结构指纹（见 scan_skeleton.numeric_local_subsection_probe），因此把它
    # 提升为契约的第三层：sections_global=true + numeric_local_sections=true
    # + section_types 三位 [1,1,1]（章 / 全局 § / 逐 § 数值子块，皆单分量 role 1）。
    # 🔴 探测本身即权威且自限（要求真实单号 § 字形头 + 逐 § 干净 1..k 子块跑），
    # 点分层级书（Koopman「20.5」无单号 §）根本不会命中，故不再用 sd 深度做前置
    # 闸门——_detect_section_hierarchy 对 Arnold 的单号 § 会误检成 [1,2]，用它当
    # 门反而把真结构挡掉。只要 probe 命中即整树改写为三位 [1,1,1]（章/全局 §/
    # 逐 § 数值子块，皆单分量 role 1）并强制 sections_global=true。
    if not is_appendix:
        _nl_fire, _nl_info = _detect_numeric_local_sections(
            extract_dir, ordinal, language, cm_chapter_first)
        if _nl_fire:
            config["sections_global"] = True
            config["numeric_local_sections"] = True
            sd = [1, 1, 1]
            print("[make_config] 检出 Arnold-ODE 型三级结构：全局单号 § + 逐 § "
                  "裸单号子块 → section_types=%s sections_global=true "
                  "numeric_local_sections=true（§父节=%d，子块总数=%d）"
                  % (sd, len(_nl_info.get("good_parents", [])),
                     _nl_info.get("total_children", 0)))
    config["section_types"] = sd
    if ordinal == ORDINAL_HUM:
        config["sections_global"] = True
    # 🔴 人工声明的结构开关回贴（见 _MANUAL_DECLARED_FLAGS 注释）：探测器
    # 本轮没写这些键 → 从旧账取回，`--force` 不再把书的体例声明洗掉。
    for _k, _v in _load_old_manual_flags(cfg_path, section_key).items():
        config.setdefault(_k, _v)
    return config, family, groups, ordinal, depth


# --- manual declared flags (ledger fidelity on --force) --------------------
# 🔴 `make_config --force` 会**整份重扫并覆盖**配置。条目体例（ordinal /
# formula）有 best-effort 探测器，而下面这些开关是**结构体例的人工声明**
# ——探测器刻意不产出（判据依赖「每章是否从 1 重起」这类跨页语义，任何启发式
# 都会在他书上误触发）。旧实现重生成时把它们静默丢掉：Shafarevich《Basic
# Algebraic Geometry 1》实测 `chapter_local_numbering: true` 一丢，scan_skeleton
# 立刻退回通用 `§C.S` 通道 → 全书 sections=0、条目落章级桶，而配置看起来
# 完全正常（假绿）。因此与 `_load_old_ordinal` / `_load_old_formula` 同构：
# 重生成时**回贴**旧账里声明为 True 的这些字段（只回贴 True，绝不注入 False，
# 也不覆盖探测器本轮已经写下的同名键）。
_MANUAL_DECLARED_FLAGS = (
    'chapter_local_numbering',    # 章内三层（节 §N 每章重起 + 小节 N.M）
    'chapter_local_sections',     # 节清单以已写出的 md 为权威
    'chapter_scoped_items',       # 条目按章重启、不带节段
    'gm_bare_numbered',           # 裸单号条目（GM 型）
    'exercise_region_headings',   # 练习区标题词（列表，非布尔）
    # 🔴 两本**印面目视确证账**（列表，非布尔）：探测器无从重建，`--force` 若不回贴
    # 就会静默清空，下游判据随即翻脸——`content_overrides` 一丢，① 复算闸重新把
    # 已按印面剔掉的噪声块报成「契约缺块」（Iwaniec–Kowalski ch1/9/22/23）；
    # `exercise_printed_attested` 一丢，练习覆盖审计把印面确有、OCR 整行漏扫的练习
    # 报成 PHANTOM（同书 ch1 Ex2 / ch4 Ex7 / ch5 Ex6；同批 4 处里的 ch4 Ex4 是**判据漏**
    # ——标题在 OCR 里只读歪一个字母——已改 `printed_label`，不在本账）。写入侧见
    # `lib/content_overrides.py` 与 `flows/write-source/script/check_exercise_coverage.py`。
    'content_overrides',          # 契约内容块的人工裁定（drop 噪声 / retag 挪位）
    'exercise_printed_attested',  # 印面确有、OCR 漏扫的练习号登记
)


def _load_old_manual_flags(cfg_path, section_key="ch"):
    """旧配置里人工声明的开关（True / 非空列表）→ dict（可能为空）。

    与 `_load_old_ordinal` 同构：外层 map 读 ``data[section_key]``，扁平格式读
    顶层。只收「声明为真」的字段——False / 空列表等于没声明，不回贴。

    扁平格式的顶层声明在**当年对附录/补篇章同样生效**（旧书无 appendix 子配置
    时 ConfigLoader 整章回退主配置），所以首次补写 appendix/supplement 子配置
    时照原样继承它们 = 零回归，而非跨段污染。
    """
    try:
        with open(cfg_path, encoding="utf-8-sig") as f:
            data = json.load(f) or {}
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    if any(k in data for k in ("ch", "appendix", "supplement")):
        sub = data.get(section_key)
        cfg = sub if isinstance(sub, dict) else {}
    else:
        cfg = data
    out = {}
    for k in _MANUAL_DECLARED_FLAGS:
        v = cfg.get(k)
        if v is True or (isinstance(v, (list, tuple)) and len(v) > 0):
            out[k] = list(v) if isinstance(v, (list, tuple)) else True
    return out


def _repaste_old_scopes(cfg_path, ordinal_arr, section_key="ch"):
    """旧账里**同名标签组**声明过的 `scope` 原样回贴（账本保真）。

    🔴 与 `_load_old_ordinal` 的 Figure 分支、`_load_old_manual_flags` 同一个
    设计意图：`--force` 是整份**重扫**，探测只有 scope 2/3 两档（见
    `_refine_book_scope` 的 scope=1 补判），人工/历史核准过的计数器边界若不在
    回贴范围内就会被静默洗掉——Serre《Linear Representations of Finite Groups》
    实测：旧账 Theorem/Proposition/Lemma scope=1、Corollary scope=3（按节重启），
    重生成后一律变 scope=2 且 `strict` 打开，B 层对 26 章报假缺号。
    配对口径 = 标签集合有交集（探测常把一族拆/并成不同组名）；旧组声明过 scope
    即沿用旧值并打一行提示，探测值只在旧账没记时生效。返回 ``(arr, notes)``。
    """
    notes = []
    claimed = set()          # 已被某个旧组认领的新组下标，避免一个旧组改多个新组
    for old_g in _load_old_ordinal(cfg_path, section_key):
        onames = {n for n in (old_g.get("name") or []) if n}
        if not onames or old_g.get("scope") is None:
            continue
        target = None
        for i, g in enumerate(ordinal_arr):
            if i in claimed:
                continue
            if onames & {n for n in (g.get("name") or []) if n}:
                target = i
                break
        if target is None:
            continue
        claimed.add(target)
        g = ordinal_arr[target]
        sc = int(old_g["scope"])
        if g.get("scope") != sc:
            notes.append("%s：scope %s → 沿用旧账 %s"
                         % ("/".join(sorted(onames)), g.get("scope"), sc))
            g["scope"] = sc
    return ordinal_arr, notes


def _repaste_old_partition(cfg_path, ordinal_arr, section_key="ch"):
    """旧账的**计数器划分**（哪些标签各自成一条计数器）优先于本轮合并结果。

    🔴 判据不对称：探测说「两条计数器合并」依据的只是**同窗不重号**（缺席
    证据），而旧账把它们分列是当年核对过印面的**正面判断**——缺席证据不能推翻
    正面账本，这与 `_repaste_old_scopes` / `_load_old_manual_flags` 同一口径。
    Serre《Linear Representations of Finite Groups》实测：命题 12–45 与引理 1–25
    是两条**独立的全局**计数器，在任何一章都不会撞号（ch12 = 命题32–37 +
    引理12–19），于是「窗内无重号」把它们并成一组，B 层的 TAIL 比对随即错接
    （「源最大 37 远大于 md 最大 19」），12 章 EN+CN 各报一条假 BLOCKING。

    口径：① 旧账声明过的标签按旧组原样重建（含旧 type / 旧 scope），**本轮没
    检出的也照样留在账上**（漏检 ≠ 书里没有）；② 本轮新检出的标签（旧账没有的，
    如 Definition / Remark / Example / Figure）从各新组里摘掉旧标签后
    **保持探测的分组与 scope**；③ 一个标签只认第一个旧组；④ 旧组**缺** type /
    scope 时（残缺账本，如早期手写的 `[{"name": ["Figure"]}]`）用本轮探测到同
    标签的那组补齐——绝不写出无 type 的组，否则下游 `require_complete`/分组消费
    直接 KeyError（test_fig_group_guarantee 实测）。
    没有旧账（首次配置）时原样返回，零影响。返回 ``(arr, notes)``。
    """
    old_groups = _load_old_ordinal(cfg_path, section_key)
    if not old_groups:
        return ordinal_arr, []

    def _detected(onames):
        """本轮探测里带这些标签的组（用于补齐旧组缺失的 type/scope）。"""
        for g in ordinal_arr:
            if onames & {n for n in (g.get("name") or []) if n}:
                return g
        return ordinal_arr[0] if ordinal_arr else {}

    out, claimed, notes = [], set(), []
    for og in old_groups:
        onames = [n for n in (og.get("name") or []) if n and n not in claimed]
        if not onames:
            continue
        claimed.update(onames)
        fb = _detected(set(onames))
        rebuilt = {}
        for k in ("type", "scope"):
            v = og.get(k)
            if v is None:
                v = fb.get(k)
            if v is not None:
                rebuilt[k] = v
        rebuilt["name"] = onames
        out.append(rebuilt)
        notes.append("旧账划分：%s 各自成组（type=%s scope=%s）"
                     % ("/".join(onames), rebuilt.get("type"), rebuilt.get("scope")))
    for g in ordinal_arr:
        rest = [n for n in (g.get("name") or []) if n and n not in claimed]
        if not rest:
            continue
        claimed.update(rest)
        new_g = dict(g)
        new_g["name"] = rest
        out.append(new_g)
        notes.append("本轮新检出：%s（type=%s scope=%s，按探测值）"
                     % ("/".join(rest), g.get("type"), g.get("scope")))
    # 旧账声明过、本轮没检出的标签在 loop ① 里已原样保留（漏检 ≠ 书里没有）
    return out, notes


def _generate_special_verify_configs(extract_dir):
    """Generate appendix/supplement sub-configs (letter-chapter convention) by
    scanning EACH kind's page range independently.

    🔴 Supplement（kind=3）与 Appendix（kind=2）是不同概念，分别按 chapter_map 的
    kind 检出、分别生成子配置（同走 ``_build_config_dict(letter_chapter=True)`` 的
    字母章位体例检测）；二者在 verify_config.json 外层 map 中分别落键
    ``"appendix"`` / ``"supplement"``，绝不混称。返回
    ``{"appendix": cfg|None, "supplement": cfg|None}``。

    仅当某类页区间检出字母章位体例（ORDINAL_APP=13 三级 / ORDINAL_APP2=14 两段）
    才产出子配置；否则回退主配置。

    🔴 回退分两种，必须可区分（否则下游警告永远消不掉）：
      * **已裁决同体例**——该类章检出、页区间也扫了，结论是编号首段仍是数字章号
        （Serre GTM42 附录实测）→ 记入返回的 ``same_style`` 清单，由 main() 写进
        ``verify_config.json`` 的 ``_special_same_style``；ConfigLoader 见此声明
        即安静回退（此时回退是**正确行为**，不是错配）。
      * **没扫到/没检出**（无该类章、或检出章却没有可用页区间）→ 不进清单，
        下游静默回退警告保留，因为那份配置从没对这个 kind 做过任何结论。
    """
    out = {"appendix": None, "supplement": None, "same_style": []}
    for kind, key, label in ((KIND_APPENDIX, "appendix", "附录"),
                             (KIND_SUPPLEMENT, "supplement", "补篇")):
        chs = _detect_special_chapters(extract_dir, kind)
        if not chs:
            print(f"[make_config] 未检出{label}章，跳过 verify_config.json 的 "
                  f"\"{key}\" 子配置（回退主配置，零回归）。")
            continue
        pages = _special_page_files(extract_dir, chs)
        if not pages:
            print(f"[make_config] 检出{label}章但无可用页区间，跳过 \"{key}\" 子配置。"
                  f"（未做体例裁决 ⇒ 下游回退警告会保留，请核对 chapter_map 页区间。）")
            continue
        cfg, family, groups, ordinal, depth = _build_config_dict(
            extract_dir, os.path.join(extract_dir, 'verify_config.json'),
            letter_chapter=True, is_appendix=True, pages=pages,
            section_key=key)
        if not ordinal or ordinal not in (ORDINAL_APP, ORDINAL_APP2):
            # 该类页区间**已扫描**且未检出字母章位体例 → 本书该类与正文同体例。
            # 不产出与主配置等价的冗余子配置，但必须把这一裁决落账，否则
            # ConfigLoader 的静默回退警告永远无法被补救（它给出的补救命令
            # ——本脚本 --force——对本类书永远只会重复同一结论）。
            out["same_style"].append(key)
            print(f"[make_config] {label}页区间检出编号族={ordinal}"
                  f"（非字母章位 type 13/14），"
                  f"视为与正文同体例，跳过 \"{key}\" 子配置，"
                  f"并记入 {MAP_KEY_SPECIAL_SAME_STYLE} 声明。")
            continue
        # 字母章位保留式练习计数器（`Exercise A.1.1` / `Exercise B.4`，两段/
        # 三级形态见 _APP_EX_RE）不在 LABEL_FORMS 中，单独探测后按计数器
        # 归属落位：与条目**共享**同一计数器（一起升序，Lee ISM 附录实测——
        # 练习号 A.1,A.2,A.3 后跳 A.9，A.4-A.8 是 Example）→ 把 ``Exercise``
        # **并入主组 name**（正文章共享体例同构）；**平行独立**计数器
        # （Weibel 式同号并存）→ 追加独立 Exercise 组。type/scope 均跟随
        # 本书附录的实际体例。
        ex_present, ex_shared = _detect_appendix_exercise(extract_dir, pages)
        if ex_present:
            _main_scope = (cfg["ordinal"][0].get("scope", 3)
                           if cfg.get("ordinal") else 3)
            if ex_shared and cfg.get("ordinal"):
                if "Exercise" not in cfg["ordinal"][0].setdefault("name", []):
                    cfg["ordinal"][0]["name"].append("Exercise")
            else:
                cfg["ordinal"].append({"type": ordinal, "name": ["Exercise"],
                                       "scope": _main_scope})
        out[key] = cfg
        labels = [nm for g in cfg.get('ordinal', []) for nm in g.get('name', [])]
        print(f"⚠️ 已生成{label}配置（letter-chapter 体例 ordinal={ordinal}，"
              f"depth={depth}）：")
        print(f"   {label}章: {[c['ch'] for c in chs]}  "
              f"页区间: {pages[0]!r}..{pages[-1]!r}")
        print(f"   标签组名: {labels}")
        print(f"   子配置内容: {json.dumps(cfg, ensure_ascii=False)}")
    return out


def _upgrade_missing_special_keys(extract_dir, cfg_path):
    """已存在的 verify_config.json 缺 appendix/supplement 子配置时的增量升级。

    🔴 Lee 2e 实测教训：书先由旧版本生成（当时附录分支不存在或未检出），
    此后 skill 升级了 letter-chapter 支持，但「已存在则跳过」硬闸让这份
    缺 ``"appendix"`` 键的配置永远不更新——ConfigLoader 把附录章静默回退到
    数字章号的正文配置，``Theorem A.1`` 全部判为跨章引用，build_structure
    抽出 0 条，整附录被塞进单个 description，而所有下游都无感。

    因此普通（非 --force）运行时做**增量升级**：外层 map 缺哪个 special 键、
    而书的章节映射确实含该 kind 的章，就只补写那个键（整份重扫、保留既有键
    的手动修改原样不动）。补写后打印变更清单。既有键一律不碰——
    ``--force`` 才是整份重生成。
    """
    try:
        with open(cfg_path, encoding='utf-8-sig') as fh:
            data = json.load(fh)
    except Exception as e:
        print(f"[make_config] 已存在 {cfg_path}，跳过（用 --force 覆盖）。读取失败: {e}")
        return 0
    if not isinstance(data, dict):
        print(f"[make_config] 已存在 {cfg_path}（非外层 map 格式），跳过（用 --force 覆盖）。")
        return 0

    missing = [k for k in ('appendix', 'supplement') if k not in data]
    if not missing:
        print(f"[make_config] 已存在 {cfg_path}，跳过（外层 map 完整；用 --force 覆盖）。")
        return 0

    special = _generate_special_verify_configs(extract_dir)
    added = []
    for key in missing:
        if special.get(key) is not None:
            data[key] = special[key]
            added.append(key)
    # 🔴 该类章扫过、结论是「与正文同体例」→ 落账声明（不产出冗余子配置）。
    # 没有它，老配置的 appendix 键缺失会永久触发一条 --force 也消不掉的警告。
    declared = []
    ss = [k for k in (special.get("same_style") or []) if k in missing]
    have = data.get(MAP_KEY_SPECIAL_SAME_STYLE)
    existing = {str(k) for k in have} if isinstance(have, (list, tuple, set)) else set()
    for key in ss:
        if key not in existing:
            declared.append(key)
    if declared:
        data[MAP_KEY_SPECIAL_SAME_STYLE] = sorted(existing | set(declared))
    if not added and not declared:
        print(f"[make_config] 已存在 {cfg_path}，跳过（用 --force 覆盖）。"
              f"缺 {missing} 键但对应 kind 的章未检出或无页区间——若这不符合预期，"
              f"请核对 chapter_map.json 的章名/章号。")
        return 0
    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    if added:
        print(f"[make_config] ⚠ 增量升级 {cfg_path}：补写缺失的 {added} 子配置"
              f"（既有键原样保留）。附录/补篇章自下一次运行起改走自己的编号体例；"
              f"须重跑 build_structure 重建这些章的契约。")
    if declared:
        print(f"[make_config] ⚠ 增量升级 {cfg_path}：{declared} 判明与正文同体例，"
              f"已记入 {MAP_KEY_SPECIAL_SAME_STYLE} 声明（不产出冗余子配置）。"
              f"下游 ConfigLoader 的回退警告自此消音——回退在这里是正确行为。")
    return 0


def main():
    args = sys.argv[1:]
    force = '--force' in args
    pos = [a for a in args if not a.startswith('-')]
    if not pos:
        print(__doc__)
        return 2

    extract_dir = pos[0]
    if not os.path.isdir(extract_dir):
        print(f"[make_config] 目录不存在: {extract_dir}")
        return 2

    cfg_path = os.path.join(extract_dir, 'verify_config.json')
    if os.path.exists(cfg_path) and not force:
        _upgrade_missing_special_keys(extract_dir, cfg_path)
        return 0

    # 🔒 硬闸：MM Repair 未完成（缺 _extraction_done.json）一律拒绝生成配置，
    # 绝不写退化默认文件。这是防"跳步生成 config"的最后一道墙——一旦放行，
    # 下游 build_structure / verify_chapter 会基于未修复页的错配配置跑。
    if not os.path.exists(os.path.join(extract_dir, '_extraction_done.json')):
        print('[make_config] BLOCKED: 缺 _extraction_done.json，MM Repair 未完成。')
        print('  须先完成 MM Repair（模式 A+B 写回 page_*.json，apply 真完成写出')
        print('  _extraction_done.json）后再生成配置。详见')
        print('  flows/extract/mm_repair/mm_repair.md 出口条件。')
        print('  ❌ 禁止手写/手改 verify_config.json 绕过本护栏。')
        return 2

    # 🔒 硬闸：config 子流程的契约是「先建 chapter_map.json，再生成
    # verify_config.json」（extract/config_setting 步骤 1）。缺章节映射时
    # 生成的配置没有章界可依（下游 ConfigLoader 也读不到章列表）——
    # 拒绝生成，防止对半成品书伪造配置。
    if not os.path.exists(os.path.join(extract_dir, 'chapter_map.json')):
        print('[make_config] BLOCKED: 缺 chapter_map.json（章节映射未建立）。')
        print('  config 子流程须先产出章节映射，再运行本脚本生成 verify_config.json。')
        print('  ❌ 禁止跳过章节映射直接生成配置。')
        return 2

    # 🔒 硬闸：附录 / 补篇的**阿拉伯数字序标**必须有印刷证据（lib/appendix_ordinal）。
    # 成因实测（Shafarevich BAG1 2026-09-29）：印面标题就是裸的 "Algebraic Appendix"，
    # 却被顺着正文章号登记成 ch5，于是整条命名链长出伪造序标——契约 appendix5.json、
    # 单元目录 units/appendix5/、成品 附录5_*.md / Appendix5_*.md、H1 "# Chapter 5:"。
    # 判据保守（只判数字序标；字母/罗马一律放过），故可直接 fail-closed。
    from data.chapter_map.chapter_map import load_chapter_records as _load_recs
    from lib.appendix_ordinal import appendix_ordinal_problems as _apx_probs
    _problems = _apx_probs(_load_recs(extract_dir), extract_dir)
    if _problems:
        print('[make_config] BLOCKED: chapter_map 的附录/补篇序标没有印刷证据'
              '（页窗 + 前置目录区均取不到「附录/补篇词 + 该数字」相邻共现）：')
        for _p in _problems:
            print('  - ' + _p)
        print('  修法见 SKILL.md「附录命名总则」：印面无序标 → 该章键直接写裸 '
              '"appendix"（补篇写 "supplement"）；印面有字母序标 → 照抄字母。')
        print('  ❌ 禁止把附录顺着正文章号编号来绕过本闸。')
        return 2

    # One full scan yields the numbering family, the set of entry-type labels
    # actually present as numbered headings, their GROUPING by shared counter,
    # AND the book's language (derived from which label forms were seen).
    # Labels that ascend together share ONE group; labels with an independent
    # counter get their OWN group — that is what the `ordinal` ARRAY is for.
    config, family, groups, ordinal, depth = _build_config_dict(extract_dir, cfg_path)

    # 🔴 附录 / 补篇子配置：分别按 chapter_map 的 kind 扫对应页区间生成（字母章位
    # 体例），Supplement 与 Appendix 分别落键，绝不混称。缺某一类则回退主配置。
    special = _generate_special_verify_configs(extract_dir)

    # ---- 组装外层 map：{"ch": 正文, "appendix": 附录, "supplement": 补篇} ----
    out_map = {"ch": config}
    if special.get("appendix") is not None:
        out_map["appendix"] = special["appendix"]
    if special.get("supplement") is not None:
        out_map["supplement"] = special["supplement"]
    # 🔴 已裁决「与正文同体例」的 kind 落账（见 _generate_special_verify_configs）：
    # 没有这条声明，ConfigLoader 无法区分「扫过、结论是同体例」与「从没扫过」，
    # 于是它对Serre式附录永远打印一条 --force 也消不掉的警告。
    same_style = list(special.get("same_style") or [])
    if same_style:
        out_map[MAP_KEY_SPECIAL_SAME_STYLE] = same_style

    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(out_map, f, ensure_ascii=False, indent=2)

    print(f"⚠️ 已生成起始配置（外层 map：ch/appendix/supplement；"
          f"正文 best-effort 检测 ordinal={ordinal}，depth={depth}）。")
    print(f"   正文小节层级 section_types={config.get('section_types')} "
          f"（角色码即层级深度，depth 由 SECTION_TYPE_DEPTH 派生，避免默认回退过度校验）。")
    print(f"   文件路径: {cfg_path}")
    print(f"   文件内容: {json.dumps(out_map, ensure_ascii=False)}")
    if groups and groups != [["uncat"]]:
        print(f"   · 检出 {sum(len(g) for g in groups)} 个标签词，按『是否同计数器』分为 {len(groups)} 个 group：")
        for gi, g in enumerate(groups):
            print(f"       group[{gi}] name={g}")
        print("     （同升序（共享计数器）的标签进同一 group；独立编号序列的标签")
        print("      各自成 group——这正是 ordinal 数组的设计意图。）")
    else:
        print("   · 未检出任何条目类型标签词，仅生成 [\"uncat\"] 兜底组。")
    print("   请人工核对后再跑 verify：")
    print("     · 若原 verify_config.json 是【整型 ordinal】旧格式，校验会直接报错")
    print("       exit 2；必须用本脚本 --force 重新生成（见")
    print("       config/config_schema.md §配置字段说明）。")
    print("     · 若需公式序标校验（Q 层），formula 键已按书源公式形态 best-effort 写入；")
    print("       多分量书 scope 默认 2（章级跨章守卫），单分量且每节从 1 重排的书")
    print("       应 scope 3（如 Kreyszig 式 (N)），请核对 scope 是否正确。")
    print("     · 所有『作为编号标题出现』的标签词（含 Remark/评注/注、")
    print("       Exercise/习题/练习/问题/Problem、Axiom/公理 等）都已自动检出，")
    print("       并按『是否同升序（共享计数器）』分组：同升序的进同一 group、")
    print("       独立编号序列的各自成 group。该分组由整书扫描的实际编号得出，")
    print("       非硬编码；若某书实际共享而你书里分成多 group（或反之），请手动合并/拆分。")
    print("     · 三级书（type 3/5，编号形如 1.5-3 / I.2.11）现在自动")
    print("       赋 scope=3（每段重置计数器）；此前写死 scope=2 会让")
    print("       item_numbering_integrity 误报跨节断号。EN 三级书（如 Kreyszig，")
    print("       编号 Definition 1.5-3）也会正确判为 type 3，不再误判为英文两级")
    print("       （原 type 4，现并入 type 2）而塌缩三级项。")
    print("     · 小节层级 section_types 现已由 OCR 自动识别（2/3/4 级，上限 4），")
    print("       不再限制为 2 或 3 级；含混合深度（如 20.5 + 20.5.1）的书也会被完整识别；")
    print("       层级深度由 verify_config.py 的 SECTION_TYPE_DEPTH 派生，不单独存储。")
    return 0


if __name__ == '__main__':
    sys.exit(main())
