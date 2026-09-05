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
  3. 写出 {"ordinal": [<组>, ...], "language": <en if 候选 in (4,5,6,8,9) else cn>}：
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
from verify_config import (ORDINAL_DEPTH, ORDINAL_LANGUAGE_DEFAULT,
                           ORDINAL_HUM, ORDINAL_APP)


def _is_fig_kw(name):
    """True iff `name` is a figure-label keyword (Fig / Figure / 图).

    Mirrors lib.figure_io._is_fig_kw so make_config and the runtime figure
    pipeline agree on which `ordinal` group is the Figure group."""
    s = str(name)
    if "图" in s:
        return True
    low = "".join(ch for ch in s.lower() if ch.isalpha())
    return low in ("fig", "figure")


def _load_old_ordinal(cfg_path):
    """Return the `ordinal` array from an existing verify_config.json, or []."""
    try:
        with open(cfg_path, encoding="utf-8") as f:
            return (json.load(f) or {}).get("ordinal", []) or []
    except Exception:
        return []

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
# 重建分章契约出现「大量遗漏」的根因。
EN_THREE_RE = re.compile(
    r'(?:\b(?:Theorem|Lemma|Definition|Proposition|Corollary)\s+\d+\.\d+[\.\-]\d+'
    r'|\b\d+\.\d+[\.\-]\d+\s+(?:Theorem|Lemma|Definition|Proposition|Corollary)\b)')

# CN 条目标签：定义|定义|引理|推论|命题 ... N.M（两级）或 N.M.K（三级）
CN_TWO_RE = re.compile(r'(定理|定义|引理|推论|命题)\s*\d+\.\d+(?!\.\d)')
CN_THREE_RE = re.compile(r'(定理|定义|引理|推论|命题)\s*\d+\.\d+\.\d+')

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


def detect_formula(extract_dir, pages=None):
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
    single_nums = []  # ints in page order, for per-section-reset fallback
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
            dotted_count += len(_F_DOT_RE.findall(text))
            dotted_count += len(_F_EQ_RE.findall(text))
            dotted_count += len(_F_CN_EQ_RE.findall(text))

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
        # numbers don't fabricate a type-4 formula scheme.
        if dotted_count >= _FORMULA_MIN_COUNT:
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
    chapter entry carries ``"ordinal": 4`` and ``"chapter_first": false`` — the
    first numeric component of an item key is the SECTION, not the chapter
    (``"Theorem 8.1"`` = §8 item 1).  The page-text scan in
    `_detect_ordinal_from_pages` CANNOT tell a section-based two-level scheme
    (type 4 + chapter_first=False) apart from a plain chapter-based EN two-level
    (type 4 + chapter_first=True) — both look like "Label N.M" — so the scan
    always votes 4 and cannot know chapter_first.  We therefore trust
    chapter_map's declaration for ``chapter_first`` when present and consistent.

    For the scan-ambiguous ORDINAL *codes* (6=gm, 8=vakil, 9=en3) we additionally
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


def _contract_counter_evidence(extract_dir):
    """结构契约（book_structure/ch{N}.json）已存在时，用契约条目本身作为
    计数器分组证据 —— 比 ordinal 探测阶段的 OCR 标题扫描干净得多（OCR 漏识
    / 字符混淆会让 _shares_main_counter 的证据稀疏化，Weibel 实测被误判成
    5 个独立计数组）。

    返回 ``[(form, comps)]``（仅数字章；附录字母章走 letter_chapter 专属
    生成器，不在此列）或 None（无契约 / 无可用条目）。**练习条目不纳入**
    证据（exercise 不在 _CONTRACT_TYPE_TO_FORM）：练习计数器由
    `_detect_exercise_counter` / `_detect_appendix_exercise` 专属检测并
    单列组，与 LABEL_FORMS 刻意不含 Exercise 的口径一致。
    """
    from data.book_structure.book_structure import BookStructure
    try:
        bs = BookStructure.load(extract_dir)
    except Exception:
        return None
    if bs is None:
        return None
    out = []

    def walk(n):
        if n.type in ("chapter", "section"):
            for k in n.sub_sec:
                walk(k)
            return
        form = _CONTRACT_TYPE_TO_FORM.get(str(n.type))
        if not form:
            return
        nums = re.findall(r"\d+", str(n.key))
        if len(nums) < 2:
            return
        out.append((form, tuple(int(x) for x in nums)))

    for c in bs.chapters:
        if not str(c.key)[:1].isdigit():
            continue  # 附录字母章键的窗口语义不同，交 letter_chapter 生成器
        walk(c)
    # 同号去重：深层书的子项（如 Weibel ch9 的 `Corollary 9.3.3.1`）被抽取器
    # 展平成三段键后与宿主条目（Theorem 9.3-3）同号不同族——这属书的层级
    # 深度问题，不是「平行计数器」证据；按窗口首次出现保留，其余丢弃，
    # 否则重复号会让 _shares_main_counter 把正文族误拆成多组。
    seen = set()
    deduped = []
    for form, comps in out:
        if comps in seen:
            continue
        seen.add(comps)
        deduped.append((form, comps))
    return deduped or None


def _detect_ordinal_from_pages(extract_dir, pages=None, letter_chapter=False):
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

    `pages` restricts the scan to an explicit list of `page_*.json` paths (the
    APPENDIX generator passes the appendix range only).  `letter_chapter=True`
    enables the appendix letter-slot numbering detection (``Definition A.1.1``)
    and lets the family vote elect ``ORDINAL_APP`` (13).

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
    counts = {'cn_three': 0, 'en_three': 0, 'en': 0, 'cn_two': 0}
    label_res = _build_label_heading_regexes(letter_chapter=letter_chapter)
    headings = []   # (canon_idx, raw_form, comps_tuple)
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
            counts['cn_three'] += len(CN_THREE_RE.findall(block))
            counts['en_three'] += len(EN_THREE_RE.findall(block))
            counts['en'] += len(EN_TWO_RE.findall(block))
            counts['cn_two'] += len(CN_TWO_RE.findall(block))
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
                    if form[0].isascii() and form[0].isalpha():
                        seen_en = True
                    else:
                        seen_cn = True

    # family vote — derived from the ACTUAL detected headings (position-guarded,
    # cross-ref-filtered), which is far more robust than the raw regex counts
    # (those also catch body cross-references).  Specificity-first:
    # three-level > two-level > single-level.  A PURE single-level book (every
    # detected entry is "Label N", e.g. Silverman) must NOT fall through to the
    # default type 3 — it votes type 1 here.
    # 附录字母章号（`A.1.1`）——首分量是 str 而非 int，独立成族 ORDINAL_APP(13)。
    n_app = sum(1 for h in headings
                if len(h[2]) >= 2 and isinstance(h[2][0], str))
    n_single = sum(1 for h in headings
                   if len(h[2]) == 1 and not isinstance(h[2][0], str))
    n_two = sum(1 for h in headings
                if len(h[2]) == 2 and not isinstance(h[2][0], str))
    n_three = sum(1 for h in headings
                  if len(h[2]) >= 3 and not isinstance(h[2][0], str))
    if n_app > 0 and n_app >= n_single and n_app >= n_two and n_app >= n_three:
        family = ORDINAL_APP
    elif n_three > 0 and n_three >= n_two and n_three >= n_single:
        family = 3
    elif n_two > 0 and n_two >= n_single:
        # CN two-level (type 2) vs EN two-level (type 4)
        family = 2 if (seen_cn and not seen_en) else 4
    elif n_single > 0:
        family = 1
    else:
        # No position-guarded headings were detected.  Per the strict
        # "no-default" rule there is NO fallback to the raw regex counts
        # (those also catch cross-references / prose mentions) and NO default
        # type.  The book simply has no detectable ordinal numbering — signal
        # this with family=None so the caller omits the ordinal group entirely
        # instead of fabricating a `{"type": 3}` uncat entry.
        family = None
    # Prefer a per-chapter `ordinal` declared in chapter_map.json for the
    # scan-ambiguous ORDINAL codes (6=gm, 8=vakil, 9=en3).  The page scan can
    # only ever vote {1,2,3,4,5}; gm/vakil/en3 carry numbering shapes the scan
    # cannot distinguish from plain two/three-level, so we adopt chapter_map's
    # declared code when present and consistent.  (A section-based two-level
    # book like Fraleigh is plain type 4 on both axes — the scan already votes
    # 4 — but we still pull its `chapter_first` flag from chapter_map below.)
    cm = _ordinal_from_chapter_map(extract_dir)
    cm_ord = cm[0] if cm else None
    cm_chapter_first = cm[1] if cm else True
    if cm_ord is not None and cm_ord in (6, 8, 9, ORDINAL_HUM):
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
    depth = ORDINAL_DEPTH.get(family, 3)
    if depth >= 2:
        headings = [h for h in headings if len(h[2]) >= 2]
    # 计数器分组的证据优先级：结构契约（若已生成）> OCR 标题扫描。契约条目
    # 是去噪后的权威样本（键 + 类型俱全），共享/平行计数器的判别不再受 OCR
    # 漏识干扰；无契约（首次 config，先于 structure）时保持原 OCR 路径零回归。
    # 仅主配置走此通路；附录 letter_chapter 配置由专属生成器处理。
    _contract_evidence = None
    if not letter_chapter and depth >= 2:
        _contract_evidence = _contract_counter_evidence(extract_dir)
        if _contract_evidence:
            headings = [(0, f, comps) for (f, comps) in _contract_evidence]
    # group by shared counter.  Single-level (type 1) books reset their
    # counter per chapter, so the page scan has NO chapter window to separate
    # shared vs independent counters (the window logic in _shares_main_counter
    # needs >=2 components) — use the domain convention (_group_single_level).
    if family == 1:
        groups = _group_single_level(headings)
    else:
        # 契约证据是完备样本：min==1 的 reset 判据关闭（共享计数器书各标签
        # 轮流当节首，见 _shares_main_counter 注释）。
        groups = _group_headings_by_counter(
            headings, depth, strict_reset=not _contract_evidence)
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

    This returns True ONLY when it finds a run of >=3 consecutive bare
    first-level ordinals that is NOT inside a consolidated-exercise zone (i.e.
    not on/near a page that carries an "Exercises/练习" header).  That
    correctly returns False for Fraleigh (every exercise ordinal there lives on
    a consolidated-block page) while still letting books with genuine preserved
    exercises get a type:1 group.

    It deliberately does NOT scan "Exercise N" / "N Exercise" surface forms,
    because those are overwhelmingly body cross-references, not headings.
    """
    EXER_HEAD_RE = re.compile(
        r'\b(?:Exercises?|Problems?|习题|练习|问题)\b', re.IGNORECASE)
    # bare "N. <text>" — a number, a dot, then an alphabetic / Han start.
    BARE_RE = re.compile(r'(?:^|(?<=[)\]}\s])|[\s])(\d+)\.\s*[A-Za-z一-鿿]')
    pages = pages if pages is not None else sorted(
        glob.glob(os.path.join(extract_dir, 'page_*.json')))
    # Pass 1: mark consolidated-exercise zone pages (header page +/- 2).
    zone = set()
    for pg in pages:
        try:
            with open(pg, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        pno = int(re.search(r'(\d+)', os.path.basename(pg)).group(1))
        for b in data.get('text', []):
            if isinstance(b, dict) and blk_text(b) and EXER_HEAD_RE.search(blk_text(b)):
                zone.update(range(pno - 2, pno + 3))
                break
    # Pass 2: look for bare consecutive ordinal runs on NON-zone pages.
    run = [1, None]   # [当前连续长度, 上一序号]（跨页/跨块延续）
    for pg in pages:
        try:
            with open(pg, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        pno = int(re.search(r'(\d+)', os.path.basename(pg)).group(1))
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
            for i, nnum in enumerate(nums):
                if i > 0 and nnum == nums[i - 1] + 1:
                    run[0] += 1
                elif i == 0 and run[1] is not None and nnum == run[1] + 1:
                    run[0] += 1
                else:
                    run[0] = 1
                run[1] = nnum
                if run[0] >= 3:
                    return True
    return False


# Appendix exercises print a LETTER chapter slot (`Exercise A.1.1`) and are NOT
# part of LABEL_FORMS (which deliberately omits Exercise to avoid cross-reference
# fabrication).  Detect them separately so the appendix config can carry an
# Exercise group — a preserved/interleaved appendix exercise counter is a real
# verified sequence, exactly like a body one.
_APP_EX_RE = re.compile(
    r'(?i)\bexercise\b\s*[A-Z]\.\d+\.\d+|\b[A-Z]\.\d+\.\d+\s+exercise\b')


def _detect_appendix_exercise(extract_dir, pages):
    """True iff the appendix page range contains preserved `Exercise A.S.N`
    headings (letter chapter slot).  Only consulted for the appendix config."""
    for pg in (pages or []):
        try:
            with open(pg, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        for b in data.get('text', []):
            text = blk_text(b) if isinstance(b, dict) else ''
            if _APP_EX_RE.search(text or ''):
                return True
    return False


def detect_ordinal(extract_dir):
    """Best-effort ordinal (numbering-family) detection for a book's _extract dir."""
    is_roman, _ = _chapter_keys_are_roman(extract_dir)
    if is_roman:
        return 5
    family, _, _, _ = _detect_ordinal_from_pages(extract_dir)
    return family


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


def _detect_appendix_chapters(extract_dir):
    """返回本书附录章列表（含章号/名称/页区间）。无附录返回 []。"""
    out = _chapter_map_appendix_chapters(extract_dir)
    if not out:
        out = _ocr_appendix_chapters(extract_dir)
    return out


def _appendix_page_files(extract_dir, app_chapters):
    """附录章覆盖的 page_*.json 文件列表（按 start..end 区间并集）。"""
    nums = set()
    for c in app_chapters:
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
                      is_appendix=False, pages=None):
    """Detection + assembly for ONE book-config (main or appendix).

    Shared by `main()` (the mandatory `verify_config.json`) and the optional
    `appendix_verify_config.json` so the two can never drift in schema.  Returns
    ``(config_dict, family, groups, ordinal, depth)``; the caller writes/presents.

    `pages` restricts the scan to an explicit page range (appendix generator
    passes ONLY the appendix pages); `letter_chapter` enables the appendix
    letter-slot numbering detection (`Definition A.1.1`).
    """
    family, groups, lang, cm_chapter_first = _detect_ordinal_from_pages(
        extract_dir, pages=pages, letter_chapter=letter_chapter)
    ordinal = family
    language = (lang if lang
                else (ORDINAL_LANGUAGE_DEFAULT.get(ordinal, 'cn')
                      if ordinal is not None else 'cn'))
    depth = ORDINAL_DEPTH.get(ordinal, 3) if ordinal is not None else 3
    formula_cfg = detect_formula(extract_dir, pages=pages)
    # scope: 三级（type 3/5/13）按「节」重置计数器 → scope=3；其余按章重置 → 2。
    SCOPE_BY_TYPE = {1: 2, 2: 2, 3: 3, 4: 2, 5: 3, 6: 2, 13: 3}
    ordinal_arr = []
    if ordinal is not None:
        if is_appendix:
            # 🔴 附录：所有标签共享「按节(A.S)重置」的计数器（Weibel Appendix A：
            # A.1.1, A.1.2 … 然后 A.2.1 重置），合并为单个 group、scope=3，
            # 避免字母章位窗口把每个 (A.S) 拆成独立 group。
            all_labels = []
            for g in groups:
                for nm in g:
                    if nm and nm not in all_labels:
                        all_labels.append(nm)
            scope = 3
            ordinal_arr.append({"type": ORDINAL_APP,
                                "name": all_labels or ["uncat"], "scope": 3})
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
        for g in _load_old_ordinal(cfg_path):
            if any(_is_fig_kw(nm) for nm in g.get("name", [])):
                if ordinal is not None:
                    ordinal_arr.append({
                        "type": ordinal,
                        "name": g.get("name") or ["Figure"],
                        "scope": SCOPE_BY_TYPE.get(ordinal, 2),
                    })
                else:
                    ordinal_arr.append(g)
                break
    config = {
        "ordinal": ordinal_arr,
        "strict": True,
        "language": language,
    }
    config["chapter_first"] = bool(cm_chapter_first)
    config["section_scoped"] = bool(not cm_chapter_first)
    if formula_cfg is not None:
        config["formula"] = formula_cfg
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
    config["section_types"] = sd
    if ordinal == ORDINAL_HUM:
        config["sections_global"] = True
    return config, family, groups, ordinal, depth


def _generate_appendix_verify_config(extract_dir):
    """Generate `<extract_dir>/appendix_verify_config.json` for appendix chapters.

    Only runs when the book has appendix chapter(s) — located via
    `_detect_appendix_chapters` (chapter_map registration OR OCR fallback).  The
    scan is RESTRICTED to the appendix page range so an appendix that prints a
    DIFFERENT numbering convention than the body (letter chapter slot `A.1.1`
    vs digit `10.9.13`, different label sets, different counter-reset scope) is
    detected on its own terms.  When no appendix numbering is detected the file
    is NOT written (the body config stays authoritative — zero regression).
    """
    app_chapters = _detect_appendix_chapters(extract_dir)
    if not app_chapters:
        print("[make_config] 未检出附录章，跳过 appendix_verify_config.json"
              "（回退主配置，零回归）。")
        return
    app_pages = _appendix_page_files(extract_dir, app_chapters)
    if not app_pages:
        print("[make_config] 检出附录章但无可用页区间，跳过"
              " appendix_verify_config.json。")
        return
    app_cfg_path = os.path.join(extract_dir, 'appendix_verify_config.json')
    app_config, app_family, app_groups, app_ordinal, app_depth = _build_config_dict(
        extract_dir, app_cfg_path, letter_chapter=True, is_appendix=True,
        pages=app_pages)
    if not app_ordinal or app_ordinal != ORDINAL_APP:
        # 附录页区间未检出字母章位体例（可能本书附录与正文同体例）→ 不写文件，
        # 避免生成一份与主配置等价的冗余配置。
        print(f"[make_config] 附录页区间检出编号族={app_ordinal}（非字母章位 type 13），"
              f"视为与正文同体例，跳过 appendix_verify_config.json。")
        return
    # 附录保留式练习计数器（`Exercise A.1.1`，字母章位）不在 LABEL_FORMS 中，
    # 单独探测后并入附录配置，确保附录练习序列也被校验。
    if _detect_appendix_exercise(extract_dir, app_pages):
        app_config["ordinal"].append(
            {"type": ORDINAL_APP, "name": ["Exercise"], "scope": 3})
    with open(app_cfg_path, 'w', encoding='utf-8') as f:
        json.dump(app_config, f, ensure_ascii=False, indent=2)
    labels = [nm for g in app_config.get('ordinal', []) for nm in g.get('name', [])]
    print(f"⚠️ 已生成附录配置（letter-chapter 体例 ordinal={app_ordinal}，"
          f"depth={app_depth}）:")
    print(f"   附录章: {[c['ch'] for c in app_chapters]}  "
          f"页区间: {app_pages[0]!r}..{app_pages[-1]!r}")
    print(f"   标签组名: {labels}")
    print(f"   文件路径: {app_cfg_path}")
    print(f"   文件内容: {json.dumps(app_config, ensure_ascii=False)}")


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

    # 🔒 硬闸：config 子流程的契约是「先建 chapter_map.json，再生成
    # verify_config.json」（extract/config_setting 步骤 1）。缺章节映射时
    # 生成的配置没有章界可依（下游 ConfigLoader 也读不到章列表）——
    # 拒绝生成，防止对半成品书伪造配置。
    if not os.path.exists(os.path.join(extract_dir, 'chapter_map.json')):
        print('[make_config] BLOCKED: 缺 chapter_map.json（章节映射未建立）。')
        print('  config 子流程须先产出章节映射，再运行本脚本生成 verify_config.json。')
        print('  ❌ 禁止跳过章节映射直接生成配置。')
        return 2

    # One full scan yields the numbering family, the set of entry-type labels
    # actually present as numbered headings, their GROUPING by shared counter,
    # AND the book's language (derived from which label forms were seen).
    # Labels that ascend together share ONE group; labels with an independent
    # counter get their OWN group — that is what the `ordinal` ARRAY is for.
    config, family, groups, ordinal, depth = _build_config_dict(extract_dir, cfg_path)

    with open(cfg_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    # 🔴 附录专用配置（appendix_verify_config.json）：仅扫附录页区间，体例与正文
    # 不一致时独立生成（字母章位 `A.1.1` / 不同的标签集 / 不同的计数器重置边界）。
    # 缺附录章 → 不生成（回退主配置，零回归）。生成同样打 _provenance 戳 + 同样
    # 走 ConfigLoader 的 _extraction_done.json 上游闸（无手写侧门）。
    _generate_appendix_verify_config(extract_dir)

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
