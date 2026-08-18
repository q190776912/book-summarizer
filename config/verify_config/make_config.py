"""config/verify_config/make_config.py — 存量书「书级配置」best-effort 引导脚本

为还没有 / 想快速重建 `_extract/verify_config.json` 的书生成一份**起始**配置。
这是 BEST-EFFORT 检测，明确标注「需人工核对」，不声称自动正确。

用法：
    python config/verify_config/make_config.py <extract_dir> [--force]

行为：
  1. 若 <extract_dir>/verify_config.json 已存在且非 --force：打印跳过并 exit 0。
  2. best-effort 检测 ordinal 与 formula（两者都**全量**扫描整本书，整书聚合后
     确认全局配置，**禁止抽样前 N 页**）：
     - chapter_map.json 章号全是罗马数字（I/II/III…）→ 候选 5（roman）
     - 否则**全量**扫描整本书所有 page_*.json（sorted(glob)，不切片前 N 页），
       用轻量正则判断条目标签形态：
         * EN 两级（Theorem/Lemma/Definition/Proposition/Corollary N.M）→ 候选 4（en）
         * CN 三级（定义|定义|引理|推论|命题 N.M.K）→ 候选 3
         * CN 两级（定义|定义|引理|推论|命题 N.M）→ 候选 2
       - 按特异性优先（CN 三级 > EN > CN 两级），都无命中则默认 3（three_level）。
     - formula：detect_formula() **全量**扫描所有 page_*.json 的 text[]，统计
       standalone (N)/（N）与 (C.N)/Eq. C.N/式（C.N）的数量，整书聚合并确认全局
       公式配置（type/depth/scope）。单分量 ≫ 多分量 → type1/depth1（scope 由
       是否「全书数值回落」判定：回落→scope3 节级重排，否则→scope1 全书）；多分量
       多 → type4/depth2/scope2；都抽不到返回 None（不写 formula 键）。
  3. 写出 {"ordinal": [<组>, ...], "language": <en if 候选 in (4,5,6,7) else cn>}：
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

import os
import sys
import json
import re
import glob

sys.stdout.reconfigure(encoding='utf-8')
from verify_config import ORDINAL_DEPTH, ORDINAL_LANGUAGE_DEFAULT

# --- section hierarchy (D-layer) -------------------------------------------
# `section_types` (role codes) MUST NOT be inferred from the ordinal type
# alone — it describes how many NESTED SECTION levels the book's markdown /
# source actually has (## §N / ## §N.M / ## §N.M.K), which is ORTHOGONAL to
# the item-numbering depth.  Each role's nesting depth is FIXED and resolved
# via SECTION_TYPE_DEPTH in verify_config.py — it is NOT a separate stored
# `section_depths` field (that would drift out of sync and wrongly equate
# `depth == role_code`).  A type-3 book can legitimately be either:
#   * a genuine 3-level-section book  (md has `#### §1.1.1`; items like
#     `1.1.2 定义`)                                  -> section_types = [1, 2, 3]
#   * a Kreyszig-shaped book (md only `## §1.3`; items like `1.3-4 Theorem`,
#     deepest component IS the item counter, NOT a subsection)
#                                                          -> section_types = [1, 2]
# The only reliable way to tell them apart is to scan the raw OCR: does the
# deepest level k (= item depth) contain any k-component numbered line that is a
# GENUINE section header (a number followed by a non-label TITLE) rather than a
# LABELED ITEM?  See `_detect_section_hierarchy` for the implementation.
_SEP_RE = re.compile(r'[.\-–·/．－〜]')
# Capture ONLY the leading number (optionally prefaced by OCR-glued §/8).  The
# trailing title is inspected separately via `rest` so a label keyword's first
# letter is never stripped off (the old `\s+\S` suffix ate the 'T' of 'Theorem'
# and turned labeled items into phantom section headers).
_SEC_HEAD_RE = re.compile(r'^(?:§|8)?\s*(\d+(?:[.\-–·/．－〜]\d+)*)')
_LABEL_KW_RE = re.compile(
    r'(定义|定理|引理|命题|推论|例|公理|练习|评注|准则|图|表|'
    r'Definition|Theorem|Lemma|Proposition|Corollary|Example|Axiom|Exercise|'
    r'Remark|Figure|Fig|Table)')


def _section_header_depth(txt, max_depth=4):
    """If `txt` is a GENUINE section header, return its component-count depth
    (>= 2); otherwise None.

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
    m = _SEC_HEAD_RE.match(txt)
    if not m:
        return None
    comps = [x for x in _SEP_RE.split(m.group(1)) if x]
    if len(comps) < 2 or len(comps) > max_depth:
        return None
    rest = txt[m.end():].lstrip()
    if not rest or not rest[0].isalnum():
        return None  # number with no following title -> not a header line
    title = rest[:12]
    if _LABEL_KW_RE.search(title):
        return None  # labeled item / figure / table, not a section header
    if not re.search(r'[A-Za-z一-鿿]', title):
        return None
    return len(comps)


def _detect_section_hierarchy(extract_dir, max_depth=4):
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
    numbers into ``book_structure.json``.

    `max_depth` bounds the hierarchy (default 4, matching the SECTION_ROLE_CODES
    cap); roles 5/6 are not emitted (never observed in the corpus).
    """
    depths = set()
    pages = sorted(glob.glob(os.path.join(extract_dir, 'page_*.json')))
    for pg in pages:
        try:
            with open(pg, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        for b in data.get('text', []):
            txt = b.get('text', '').strip() if isinstance(b, dict) else ''
            if not txt:
                continue
            d = _section_header_depth(txt, max_depth=max_depth)
            if d is not None:
                depths.add(d)
    return [1] + sorted(d for d in depths if d >= 2)

# 罗马数字章号形态（chapter_map 的 key / ch 字段全为罗马字母且无阿拉伯数字）
ROMAN_RE = re.compile(r'^[IVXLCDM]+$')

# EN 两级条目标签（无章号位）：Theorem/Lemma/Definition/Proposition/Corollary N.M
EN_TWO_RE = re.compile(
    r'\b(Theorem|Lemma|Definition|Proposition|Corollary)\s+\d+\.\d+')

# EN 三级条目标签（Kreyszig 型）：标签 + 三段编号，或 三段编号 + 标签，例如
# "Definition 1.5-3" / "1.5-3 Definition" / "Theorem 8.16.3"。
# 必须在 EN_TWO_RE 之前判定：EN_TWO_RE 的 `\d+\.\d+` 会顺带吃掉三级编号的
# 前两段（"Definition 1.5-3" → 匹配到 "Definition 1.5"），从而把 EN 三级书
# 误判为 EN 两级（type 4），导致每个 "C.S-N" 项塌缩成 "Label C.S" 两级 key、
# 丢弃段/项计数器——这正是 Kreyszig 类书被 make_config 错误生成配置后
# 重建 book_structure.json 出现「大量遗漏」的根因。
EN_THREE_RE = re.compile(
    r'(?:\b(?:Theorem|Lemma|Definition|Proposition|Corollary)\s+\d+\.\d+[\.\-]\d+'
    r'|\b\d+\.\d+[\.\-]\d+\s+(?:Theorem|Lemma|Definition|Proposition|Corollary)\b)')

# CN 条目标签：定义|定义|引理|推论|命题 ... N.M（两级）或 N.M.K（三级）
CN_TWO_RE = re.compile(r'(定理|定义|引理|推论|命题)\s*\d+\.\d+(?!\.\d)')
CN_THREE_RE = re.compile(r'(定理|定义|引理|推论|命题)\s*\d+\.\d+\.\d+')

# --- entry-type label vocabulary (detected as numbered headings) -----------
# The FULL set of theorem-ish / remark / exercise labels that can appear as
# NUMBERED HEADINGS in a math book.  make_config scans the whole book and
# detects which of these actually occur; it then GROUPS them by whether they
# share ONE ascending counter (see `_group_headings_by_counter`) — labels that
# ascend together go in ONE group's `name`, labels with an independent counter
# get their OWN group.  This is what the `ordinal` ARRAY is FOR: it is NOT a
# fixed "main types vs others" split.  Order = stable output order within a
# group.  `form_by_lower` maps a matched (possibly OCR-lowercased) surface
# form back to the canonical spelling written into `name`.
LABEL_FORMS = [
    ("Definition",  ["Definition", "定义"]),
    ("Theorem",     ["Theorem", "定理"]),
    ("Lemma",       ["Lemma", "引理"]),
    ("Corollary",   ["Corollary", "推论"]),
    ("Proposition", ["Proposition", "命题"]),
    ("Example",     ["Example", "例", "例题", "例子"]),
    ("Remark",      ["Remark", "评注", "注", "注记", "附注", "Note", "Commentary"]),
    ("Exercise",    ["Exercise", "习题", "练习", "问题", "Problem"]),
    ("Axiom",       ["Axiom", "公理"]),
]


def _build_label_heading_regexes():
    """Build, per canonical label, ONE regex that captures BOTH the label text
    and the adjacent numeric key (so we can later tell which labels share a
    counter).  Longer raw forms are tried first (e.g. 注记 before 注) so the
    matched surface form is the longest one actually present.

    Two arms, both capturing the number:
      * label-first :  ``Label 1.5-3``  -> groups (label, num)
      * number-first: ``1.5-3 Label``  -> groups (num, label)
    CN forms matched literally; EN forms word-boundary + IGNORECASE.  Returns a
    list of ``(canon_idx, regex, form_by_lower)``.
    """
    out = []
    for ci, (canon, forms) in enumerate(LABEL_FORMS):
        ordered = sorted(forms, key=len, reverse=True)   # longest first
        label_alt = '|'.join(re.escape(f) for f in ordered)
        form_by_lower = {f.lower(): f for f in forms}
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


def _parse_comps(numstr):
    """Parse a matched numeric key ('1.5-3') into a tuple of ints."""
    parts = [p for p in SEP_SPLIT_RE.split(numstr) if p]
    if not parts:
        return None
    try:
        return tuple(int(x) for x in parts)
    except ValueError:
        return None

# ---- formula detection (full-book, whole-book aggregation) ----------------
# Reuse q_layer.norm's "（）→()" ASCII-normalisation idea: a standalone formula
# number may appear in either full-width or half-width parens, so we match both.

# Formula-number detectors — patterns shared from lib/regexlib.py
from lib.regexlib import (F_SINGLE_RE as _F_SINGLE_RE, F_DOT_RE as _F_DOT_RE,
                           F_EQ_RE as _F_EQ_RE, F_CN_EQ_RE as _F_CN_EQ_RE,
                           SEP_SPLIT_RE)


def detect_formula(extract_dir):
    """Full-scan EVERY page_*.json and infer the book's formula numbering.

    Counts standalone single-component ``(N)``/``（N）`` vs two-component
    ``(C.N)``/``Eq. C.N``/``式（C.N）`` occurrences across the WHOLE book, then
    decides the global formula config by whole-book aggregation (never by
    sampling the first N pages).

    Returns a ``{"type", "scope", "ignore"}`` dict (``depth`` is DERIVED from
    ``type`` via ORDINAL_DEPTH, so it is not part of the config), or ``None`` when
    neither shape is detected (caller then simply omits the ``formula`` key).

    Phase guard: requires MM Repair to be finished (``_extraction_done.json``
    present — written only after mode A+B are applied back to ``page_*.json``,
    NOT merely when background text extraction reaches 100%); otherwise returns
    None rather than guessing from a partial / un-repaired extraction.
    """
    if not os.path.exists(os.path.join(extract_dir, '_extraction_done.json')):
        print('[make_config] MM Repair 未完成（缺 _extraction_done.json），'
              '跳过 formula 探测；请完成 MM Repair（模式 A+B 写回 page_*.json）后再生成配置。')
        return None

    pages = sorted(glob.glob(os.path.join(extract_dir, 'page_*.json')))
    single_count = 0
    dotted_count = 0
    single_nums = []  # ints in page order, for per-section-reset fallback
    for pg in pages:
        try:
            with open(pg, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        texts = [b.get('text', '') for b in data.get('text', [])
                 if isinstance(b, dict)]
        for text in texts:
            if not text:
                continue
            for m in _F_SINGLE_RE.finditer(text):
                single_count += 1
                try:
                    single_nums.append(int(m.group(1)))
                except ValueError:
                    pass
            dotted_count += len(_F_DOT_RE.findall(text))
            dotted_count += len(_F_EQ_RE.findall(text))
            dotted_count += len(_F_CN_EQ_RE.findall(text))

    if single_count > dotted_count and single_count > 0:
        # Single-component book.  Decide scope by whether the numeric sequence
        # "falls back" (resets to a smaller number) somewhere in the book:
        #   reset seen  -> per-section numbering  -> scope 3
        #   monotonic   -> book-wide numbering      -> scope 1
        scope = 1
        seen_max = 0
        for n in single_nums:
            if n < seen_max:
                scope = 3
                break
            seen_max = max(seen_max, n)
        return {"type": 1, "scope": scope, "ignore": []}
    if dotted_count > single_count and dotted_count > 0:
        # Two-component book -> chapter-level numbering (scope 2).
        return {"type": 4, "scope": 2, "ignore": []}
    return None


def _chapter_keys_are_roman(extract_dir):
    """Return (is_roman, keys) — True if ALL chapter keys are roman-numeral
    shaped and none contain arabic digits (a roman-chapter book)."""
    cm_path = os.path.join(extract_dir, 'chapter_map.json')
    if not os.path.exists(cm_path):
        return False, None
    try:
        with open(cm_path, encoding='utf-8-sig') as f:
            cm = json.load(f)
    except Exception:
        return False, None

    keys = []
    if isinstance(cm, dict) and 'chapters' in cm:
        for e in cm['chapters']:
            ch = e.get('ch', e.get('num', e.get('chapter')))
            if ch is not None:
                keys.append(str(ch))
    elif isinstance(cm, dict):
        keys = [str(k) for k in cm.keys()]
    elif isinstance(cm, list):
        for e in cm:
            ch = e.get('ch', e.get('num', e.get('chapter')))
            if ch is not None:
                keys.append(str(ch))
    else:
        return False, None

    if not keys:
        return False, keys
    arabic = [k for k in keys if re.search(r'\d', k)]
    roman = [k for k in keys if ROMAN_RE.match(k.strip())]
    return bool(roman) and not bool(arabic), keys


# canonical NAME (EN) of each surface form — used for grouping decisions.
_FORM_CANON = {}
for _canon, _forms in LABEL_FORMS:
    for _f in _forms:
        _FORM_CANON[_f.lower()] = _canon

def _group_headings_by_counter(headings, depth):
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
        if _shares_main_counter(data["comps"], ref_comps):
            primary += forms
        else:
            groups.append(forms)
    groups.insert(0, primary)
    return groups


def _shares_main_counter(cand_comps, main_comps):
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
        # resets to 1 within a running window => its own sequence
        if min(cnums) == 1:
            return False
    if shared == 0:
        return False
    return True


def _detect_ordinal_from_pages(extract_dir):
    """Full-scan EVERY page_*.json and (a) vote on the numbering FAMILY and
    (b) detect which entry-type labels appear as numbered headings, then GROUP
    them by whether they share ONE ascending counter.

    Family vote: specificity-first (CN three > EN three > EN two > CN two); no
    hits -> default 3.  The EN-three check precedes EN-two so a three-level EN
    book (Kreyszig) is not mis-detected as EN two-level.

    Label detection + grouping: during the SAME scan we collect every
    (canon_idx, raw_form, comps) heading.  ``_group_headings_by_counter`` then
    puts labels that ascend together (share a counter within a scope window)
    into ONE group and gives labels with an independent reset their OWN group.
    This is what the ``ordinal`` ARRAY is for — NOT a fixed main/other split.

    Returns ``(family_int, groups, lang)`` where ``groups`` is a list of raw-
    form lists (one per counter), primary group first; ``lang`` is the detected
    language or None.

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
    pages = sorted(glob.glob(os.path.join(extract_dir, 'page_*.json')))
    counts = {'cn_three': 0, 'en_three': 0, 'en': 0, 'cn_two': 0}
    label_res = _build_label_heading_regexes()
    headings = []   # (canon_idx, raw_form, comps_tuple)
    seen_en = False
    seen_cn = False
    for pg in pages:
        try:
            with open(pg, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        text = ' '.join(b.get('text', '') for b in data.get('text', []))
        if not text:
            continue
        counts['cn_three'] += len(CN_THREE_RE.findall(text))
        counts['en_three'] += len(EN_THREE_RE.findall(text))
        counts['en'] += len(EN_TWO_RE.findall(text))
        counts['cn_two'] += len(CN_TWO_RE.findall(text))
        for ci, rx, form_by_lower in label_res:
            for m in rx.finditer(text):
                # label-first: groups 1=label, 2=num ; number-first: 3=num, 4=label
                if m.group(1) is not None:
                    lab_txt, numstr = m.group(1), m.group(2)
                else:
                    numstr, lab_txt = m.group(3), m.group(4)
                prefix = text[:m.start()]
                tail = text[m.end():]
                # skip cross-references ('见 定义 1.5-3') and prose ('定理 2.1 的证明')
                if _is_crossref_prefix(prefix) or not _is_header_boundary(tail):
                    continue
                form = form_by_lower.get(lab_txt.lower(), lab_txt)
                comps = _parse_comps(numstr)
                if not comps:
                    continue
                headings.append((ci, form, comps))
                if form[0].isascii() and form[0].isalpha():
                    seen_en = True
                else:
                    seen_cn = True

    # family vote
    if counts['cn_three'] > 0:
        family = 3
    elif counts['en_three'] > 0 and counts['en_three'] >= counts['en']:
        # English three-level (Kreyszig, "Definition 1.5-3") -> type 3.
        # Require three-level to DOMINATE two-level: in a genuine EN-three book
        # every three-level item also yields a two-level prefix match, so
        # en_three ~= en; a predominantly EN-two-level book (e.g. Koopman,
        # "Definition 1.1") has en >> en_three, so it must NOT be flipped to
        # type 3 (which would make the CN three-level extractor misinterpret the
        # book's N.N.N subsections as fake N.N-N items).
        family = 3
    elif counts['en'] > 0:
        family = 4
    elif counts['cn_two'] > 0:
        family = 2
    else:
        family = 3  # default three_level
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
    depth = ORDINAL_DEPTH.get(family, 3)
    if depth >= 2:
        headings = [h for h in headings if len(h[2]) >= 2]
    # group by shared counter
    groups = _group_headings_by_counter(headings, depth)
    return family, groups, lang


def detect_ordinal(extract_dir):
    """Best-effort ordinal (numbering-family) detection for a book's _extract dir."""
    is_roman, _ = _chapter_keys_are_roman(extract_dir)
    if is_roman:
        return 5
    family, _, _ = _detect_ordinal_from_pages(extract_dir)
    return family


def detect_labels(extract_dir):
    """Flat list of ALL entry-type label forms detected as numbered headings
    (across every counter group).  Empty => caller falls back to ``["uncat"]``.
    """
    _, groups, _ = _detect_ordinal_from_pages(extract_dir)
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
        print(f"[make_config] 已存在 {cfg_path}，跳过（用 --force 覆盖）。")
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

    # One full scan yields the numbering family, the set of entry-type labels
    # actually present as numbered headings, their GROUPING by shared counter,
    # AND the book's language (derived from which label forms were seen).
    # Labels that ascend together share ONE group; labels with an independent
    # counter get their OWN group — that is what the `ordinal` ARRAY is for.
    family, groups, lang = _detect_ordinal_from_pages(extract_dir)
    ordinal = family
    # Language: prefer the form-derived language (an EN three-level book like
    # Kreyszig is type 3 but EN); fall back to the type->language default when
    # no label form was detected.
    language = lang if lang else ORDINAL_LANGUAGE_DEFAULT.get(ordinal, 'cn')
    depth = ORDINAL_DEPTH.get(ordinal, 3)
    # best-effort formula detection (full-book, whole-book aggregation; only
    # when the whole extraction is done — see detect_formula's phase guard).
    formula_cfg = detect_formula(extract_dir)
    # v2 schema: `ordinal` is a LIST of GroupConfig dicts — one per counter.
    # `scope` and `depth` are two DISTINCT axes:
    #   * `depth` = number of numbering components (form-driven from ORDINAL_DEPTH).
    #   * `scope` = ascending-range / counter-reset boundary:
    #       1 = book-wide, 2 = chapter-wide reset, 3 = section-wide reset.
    #   Three-level numbering (type 3 / 5) resets the per-item counter PER
    #   SECTION (1.5-1, 1.5-2 … then 1.6-1), so it MUST use scope=3.  Two-level
    #   numbering (type 2 / 4 / 6 / 7) resets PER CHAPTER, so scope=2.
    # Every group shares the book's detected `type`/`depth`/`scope`; only `name`
    # differs (which labels share THIS counter). Different groups NEVER merge.
    # (An earlier version hard-coded scope=2 for every book, which silently
    # broke three-level books like Kreyszig — item_numbering_integrity then
    # expected the item counter to continue across sections instead of
    # restarting at 1, producing false "missing item" gaps.)
    SCOPE_BY_TYPE = {1: 2, 2: 2, 3: 3, 4: 2, 5: 3, 6: 2, 7: 2}
    scope = SCOPE_BY_TYPE.get(ordinal, 2)
    ordinal_arr = []
    for name in groups:
        ordinal_arr.append({
            "type": ordinal,
            "name": name if name else ["uncat"],
            "scope": scope,
        })
    if not ordinal_arr:
        ordinal_arr = [{"type": ordinal, "name": ["uncat"], "scope": scope}]
    config = {
        "ordinal": ordinal_arr,
        "strict": True,
        "language": language,
    }
    if formula_cfg is not None:
        config["formula"] = formula_cfg
    # 🔒 证明戳：声明本文件由 make_config 在 MM Repair 完成后生成。下游
    # ConfigLoader 会校验 _extraction_done.json 与本戳——手写/手改的文件无此戳，
    # 将被拒绝加载（杜绝 Fraleigh 式"agent 手搓 config 当地基"事故）。
    config["_provenance"] = {
        "generated_by": "make_config.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "mm_repair_done": True,
        "warning": ("手写/手改本文件无效；须由 make_config.py 在 MM Repair 完成后生成，"
                    "且下游 ConfigLoader 会校验 _extraction_done.json 与 _provenance。"),
    }
    # Explicit section hierarchy (D-layer).  NOT inferred from the ordinal type
    # (that would wrongly force every type-3/5/8 book to 3 levels); instead we
    # scan the raw OCR to see whether the deepest level k is a genuine section
    # (e.g. `#### §1.1.1`) or just the item counter (Kreyszig `1.3-4`).  This
    # overrides the ORDINAL_SECTION_TYPES fallback so Kreyszig-shaped books get
    # the correct [1, 2] instead of the over-verifying [1, 2, 3].
    sd = _detect_section_hierarchy(extract_dir)
    # The detected depths ARE the built-in role codes (role N == depth N), so
    # write `section_types` directly.  Depth is derived via SECTION_TYPE_DEPTH
    # in verify_config.py and is never stored as a separate `section_depths`.
    config["section_types"] = sd

    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    print(f"⚠️ 已生成起始配置（best-effort 检测 ordinal={ordinal}，depth={depth}）。")
    print(f"   小节层级 section_types={config['section_types']} "
          f"（角色码即层级深度，depth 由 SECTION_TYPE_DEPTH 派生，避免默认回退过度校验）。")
    print(f"   文件路径: {cfg_path}")
    print(f"   文件内容: {json.dumps(config, ensure_ascii=False)}")
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
    print("       编号 Definition 1.5-3）也会正确判为 type 3，不再误判为 EN 两级")
    print("       （type 4）而塌缩三级项。")
    print("     · 小节层级 section_types 现已由 OCR 自动识别（2/3/4 级，上限 4），")
    print("       不再限制为 2 或 3 级；含混合深度（如 20.5 + 20.5.1）的书也会被完整识别；")
    print("       层级深度由 verify_config.py 的 SECTION_TYPE_DEPTH 派生，不单独存储。")
    return 0


if __name__ == '__main__':
    sys.exit(main())
