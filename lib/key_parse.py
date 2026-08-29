"""
key_parse.py — key/label regexes + canon maps + parsing/canonization helpers.

Single home for ALL key/label parsing logic used across the skill (extract
flows, verify layers, and config tools): the three-level / two-level / English
key regexes, the label canonicalization maps (_LABEL_CANON etc.), `normkey`,
`keys_in_md`, `sortkey` and `_first_num`. It has NO heavy dependencies (no
cv2 / torch) so it can be imported standalone in a bare environment.

This module is a shared `lib/` primitive (not owned by any single flow or the
verify engine), so it is importable anywhere via the bare name `key_parse`
(boot injects `lib/` into sys.path). It must NOT import anything from
`flows.*` or `verify.*` (other than the already-shared `lib.regexlib` and the
`config/verify_config` model), to keep the extract/verify boundary clean.

The inter-component separator policy lives in `lib/regexlib`
(SEP_TIGHT / SEP_WIDE / canon helpers).  This module imports SEP_TIGHT and
rebuilds every label-embedded regex with it, and re-exports the label-FREE
shared regexes (KEY_RE / ENTRY_RE / ROMAN_KEY_RE) so all callers stay unchanged.
"""
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

import re, sys, os


from lib.regexlib import (
    SEP_TIGHT, SEP_SPLIT_RE, KEY_RE, ENTRY_RE, ROMAN_KEY_RE,
)
from verify_config import (
    ORDINAL_TWO_LEVEL, ORDINAL_EN, ORDINAL_ROMAN, ORDINAL_GM,
    ORDINAL_EN3, ORDINAL_THREE_LEVEL, ORDINAL_SINGLE, ORDINAL_CN3LAB,
    ORDINAL_ROSS, ORDINAL_HUM,
    GroupConfig, _LABEL_CANON, EN_LABEL_KINDS,
    _canon_label,
)

# GM (Gelfand-Manin) section/entry separators: the shared wildcard set
# (SEP_TIGHT) plus the ideographic comma "、" that GM book headings
# occasionally use ("## 1、 Triangulated …"). Derived from SEP_TIGHT so the
# GM separator stays in lockstep with the rest of the pipeline's policy
# (single source of truth in lib.regexlib).
GM_SEP = SEP_TIGHT[:-1] + r'、]'

# --- three-level (default) key parsing ---
# KEY_RE / ENTRY_RE are imported from lib.regexlib (label-FREE, built from
# SEP_TIGHT). They match both dash (N.S-N) and dot (N.S.N) numbering — the
# extractor canonicalizes everything to dash, but the .md may keep the book's
# dot style.

# --- two-level key parsing (中文二级标签) ---
# Bold entries:  **定义1.1**： / **定理1.1**：
# NOTE: labels MUST be an alternation, not a char class. A char class
# [定义定理...] matches a SINGLE cjk char, so `**定义1.1**` (label is 2 chars)
# would never match — every entry then silently degrades to "mentioned-only".
ENTRY_RE_2 = re.compile(
    r'\*\*(定义|定理|引理|推论|命题|例|示例'
    r'|Definition|Theorem|Lemma|Corollary|Proposition|Example'
    r'|公理|Axiom'
    r'|问题|Problem'
    r'|注记|评注|注|Remark)\s*(\d+)' + SEP_TIGHT + r'(\d+)\s*(?:' + SEP_TIGHT + r')?\s*\*+')
# Prose / cross-reference mentions:  定义1.3, 由定理5.2 / by Theorem 5.2 ...
# 2026-08-27 补齐 例/Example/公理/Axiom/问题/Problem/示例 的 ENTRY_RE_2+PROSE_RE_2 覆盖
# （之前仅含 定义|定理|引理|推论|命题|注记|评注|注|Remark，中文书籍的
# 例1.X 等条目长期被静默略过成 missing，与 verify_config 里已配置的
# type=example/example ordinal group 完全脱节）。
PROSE_RE_2 = re.compile(
    r'(定义|定理|引理|推论|命题|例|示例'
    r'|Definition|Theorem|Lemma|Corollary|Proposition|Example'
    r'|公理|Axiom'
    r'|问题|Problem'
    r'|注记|评注|注|Remark)\s*(\d+)' + SEP_TIGHT + r'(\d+)')

def normkey(s):
    """Canonicalize a key to N.S-N dash form (N.S.N -> N.S-N, N·S·N -> N.S-N).
    Wildcard-aware: any separator run normalizes via SEP_SPLIT_RE."""
    parts = [p for p in SEP_SPLIT_RE.split(s) if p]
    if len(parts) == 3:
        return f'{parts[0]}.{parts[1]}-{parts[2]}'
    return s

# _LABEL_CANON / EN_LABEL_KINDS / _canon_label are imported from config
# (single source of truth) so the md-side parser and the extractor agree on
# bilingual label canonicalization (e.g. Example -> 练习, matching the
# 练习/习题/Example exercise group).  Do NOT redefine them here.

# Chinese label synonyms that appear in bilingual-book .md files.
CN_LABEL_KINDS = ['定义', '定理', '引理', '推论', '命题', '例', '示例', '评注', '注释',
                  '注', '注记', '公理', '断言', '猜想', '条件', '假设', '算法', '性质']
# Combined (used when ordinal == ORDINAL_EN so either language matches).
COMBINED_LABEL_KINDS = EN_LABEL_KINDS + CN_LABEL_KINDS
ENTRY_RE_EN = re.compile(
    r'\*\*(?:' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*(\d+)' + SEP_TIGHT + r'(\d+)\s*\*+')
PROSE_RE_EN = re.compile(
    # CJK-aware boundaries: \b never fires after a CJK char (由定理X.Y / 见命题X.Y
    # are all \w on both sides), which hid every Chinese cross-reference that
    # directly followed CJK text and surfaced them as false "truly missing".
    # (?<![A-Za-z0-9]) keeps the old protection against matches inside Latin
    # words (reTheorem); (?![A-Za-z]) still rejects the plural "Theorems" while
    # ALLOWING a digit right after the label (CN no-space form 定理14.15).
    r'(?<![A-Za-z0-9])(?:' + '|'.join(COMBINED_LABEL_KINDS) + r')(?![A-Za-z])\s*(\d+)' + SEP_TIGHT + r'(\d+)')

# Capturing variants of the EN regexes (label as group(1)) — used by
# keys_in_md('en'), which needs the label to canonicalize (Definition->定义...).
# PREFIX match only: real entries look like `**Definition 1.1 (Title)**：` or
# `**定义 5.1（级联系统）**：` — the number is immediately after the label but a
# parenthetical + closing `**` follows, so we must NOT require `*` right after
# the number. The label IS captured (group 1) so we can canonicalize it.
# re.IGNORECASE: English books (e.g. Apostol) print headings in UPPERCASE
# (THEOREM 8.16. / COROLLARY 8.3.) or OCR-mangled mixed case (THEoREM /
# CoROLLARY); without it the md-side parser misses those entries and they
# surface as false "truly missing". Mirrors extract_items_en (EN_LAB_RE).
ENTRY_RE_EN_C = re.compile(
    r'\*\*(' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*(\d+)' + SEP_TIGHT + r'(\d+)',
    re.IGNORECASE)
# Number-FIRST English entries (Fraleigh《A First Course in Abstract Algebra》
# prints "0.12 Definition", "0.20 Example" — number before label). The label-FIRST
# regexes above never match these, so an entire number-first English book extracts
# ZERO md items and every contract item surfaces as falsely "truly missing".
# Mirror of ENTRY_RE_EN_C with the number/label swapped; emits the SAME canonical
# key (`定义0.12`) so the md side and the OCR truth set (extract_items_en's
# EN_LAB_RE_NF) compare apples-to-apples. "Figure"/"Table" are NOT in
# COMBINED_LABEL_KINDS, so `**0.15 Figure**` is correctly excluded (figures are an
# E-layer concern, not B-layer items).
ENTRY_RE_EN_NF_C = re.compile(
    r'\*\*(\d+)' + SEP_TIGHT + r'(\d+)\s*(' + '|'.join(COMBINED_LABEL_KINDS) + r')',
    re.IGNORECASE)

# ORDINAL_HUM (Humphreys GTM 9): bold entries without section numbers.
# Matches **Theorem**, **Corollary A**, **Corollary A (Lie's Theorem)**,
# **Lemma A**, **Definition**, **Example 1**, etc.
_HUM_LABELS = (r'Theorem|Proposition|Corollary|Lemma|Example|Remark|Definition'
               r'|定理|命题|推论|引理|例|评注|注|定义')
ENTRY_RE_HUM = re.compile(
    r'\*\*(' + _HUM_LABELS + r')'
    r'(?:\s+([A-Z]))?'   # optional letter suffix (A, B, C)
    r'(?:\s+(\d+))?'      # optional number (for Example 1, Example 2)
    r'(?:\.?)'            # optional trailing period
    r'(?:\s*\([^)]*\))?'  # optional parenthetical
    r'\s*\*\*')
PROSE_RE_EN_C = re.compile(
    # Same CJK-aware boundaries as PROSE_RE_EN (see note there): \b fails after
    # CJK chars (「由命题 14.17」) and before digits in no-space form (命题14.17).
    r'(?<![A-Za-z0-9])(' + '|'.join(COMBINED_LABEL_KINDS) + r')(?![A-Za-z])\s*(\d+)' + SEP_TIGHT + r'(\d+)',
    re.IGNORECASE)
# Single-level English entries (e.g. `**Example 1**`, `**Remark 2**`) where the
# item carries ONE numeric component only (no section/item split).  This is the
# ORDINAL_EN counterpart of ENTRY_RE_EN_C for books that number some entry kinds
# chapter-wide with a single digit (Karlin & Taylor numbers its Examples 1, 2,
# … within the chapter).  The negative lookahead rejects a genuine two-level
# `**Label N.N**` (already captured by ENTRY_RE_EN_C) so it is NOT also emitted
# as a spurious single-level key `Label N`.
ENTRY_RE_EN_SINGLE_C = re.compile(
    r'\*\*(' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*(\d+)(?!\s*' + SEP_TIGHT + r'\s*\d+)',
    re.IGNORECASE)

# --- Ross（ORDINAL_ROSS = 11）：节内作用域编号，例题带字母位 ----------------
# S. Ross《A First Course in Probability》：`**Example 2a**` / `**Axiom 1**` /
# `**Proposition 4.1**`。点分两段形态由 ENTRY_RE_EN_C 覆盖；此处补两类：
#   * 字母位键 `Label N<letter>`——必须先于单数字形态匹配，否则
#     ENTRY_RE_EN_SINGLE_C 会把 "**Example 2a**" 截成 幻影键 "例2"；
#   * 单数字键 `Label N`——负向断言同时拒绝 后随字母（那是字母键）与
#     后随分隔符+数字（那是点分键），避免同一物理条目被重复/错形收录。
ROSS_LAB = '|'.join(COMBINED_LABEL_KINDS)
_SEP_CHARS = SEP_TIGHT[1:-1]      # 类内字符集（已转义）：.\-–·/．－〜
ENTRY_RE_ROSS_LETTER_C = re.compile(
    r'\*\*(' + ROSS_LAB + r')\s*(\d{1,2})\s*([A-Za-z])\b', re.IGNORECASE)
ENTRY_RE_ROSS_SINGLE_C = re.compile(
    r'\*\*(' + ROSS_LAB + r')\s*(\d{1,2})(?![\d' + _SEP_CHARS + r'A-Za-z])',
    re.IGNORECASE)
PROSE_RE_ROSS_LETTER = re.compile(
    r'(?<![A-Za-z0-9])(' + ROSS_LAB + r')(?![A-Za-z])\s*(\d{1,2})\s*([A-Za-z])(?![A-Za-z0-9])')
PROSE_RE_ROSS_SINGLE = re.compile(
    r'(?<![A-Za-z0-9])(' + ROSS_LAB + r')(?![A-Za-z])\s*(\d{1,2})(?![' + _SEP_CHARS + r'\dA-Za-z])')


def _ross_canon(label, num, suffix=''):
    """Ross 规范键：规范中文标签 + 原编号（例2a / 公理1 / 命题4.1）。"""
    return f"{_canon_label(label)}{num}{suffix}"

# EN3 (ORDINAL_EN3 / type 9): English three-level, LABEL-FIRST dots (Label C.S.N),
# e.g. Lasota & Mackey《Chaos, Fractals, and Noise》.  Items are numbered three
# deep (Remark 1.1.1 / Definition 2.3.4 / Theorem 3.2.1).  IDENTICAL in spirit to
# ORDINAL_EN but with a THIRD numeric component.  The label is captured (group 1)
# so keys_in_md can canonize it to the Chinese structure key (Remark -> 评注,
# Example -> 例, Definition -> 定义, ...) aligning with the per-chapter contract.  The
# bold `**` prefix naturally excludes FIGURE 1.1.1 / (1.1.1) figure/formula numbers
# (no label word), avoiding key collisions with the item set.
ENTRY_RE_EN3_C = re.compile(
    r'\*\*(' + '|'.join(COMBINED_LABEL_KINDS) + r')'
    r'\s*(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)',
    re.IGNORECASE)
PROSE_RE_EN3_C = re.compile(
    r'(?<![A-Za-z0-9])(' + '|'.join(COMBINED_LABEL_KINDS) + r')(?![A-Za-z])'
    r'\s*(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)',
    re.IGNORECASE)

# --- roman three-level (e.g. Gelfand-Manin "Methods of Homological Algebra") ---
# Item numbers are Chapter.Section.Item with a ROMAN chapter: I.2.13, II.3.5.
# The chapter prefix is a roman numeral; section/item are arabic.
ENTRY_RE_ROMAN = re.compile(
    r'\*\*((' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*([IVXLCDM]+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+))')
# re.IGNORECASE: 与 PROSE_RE_EN_C 同理——OCR 常把标签打成全大写/混合大小写
# ("THEOREM I.2.3")，无 IGNORECASE 时整条散文引用被漏抽、浮为假「真缺失」。
PROSE_RE_ROMAN = re.compile(
    r'(?<![A-Za-z0-9])(' + '|'.join(COMBINED_LABEL_KINDS) + r')(?![a-z])\s*([IVXLCDM]+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)',
    re.IGNORECASE)

# --- GM (ordinal=ORDINAL_GM): BOOK-printed forms, roman machine keys ---
# Gelfand-Manin style books print sections per chapter ("## §1. Triangulated
# Spaces") and item titles as per-section headings; the .md renders them as
# ATX sub-headings ("### 1. Main Definitions", "### 3. Proposition." — book
# typography, 2026-08 user directive).  Legacy "**N. Title**" inline bold is
# still accepted for backward compatibility.  Full "Proposition I.2.11" labels
# appear only in prose cross-references.  Machine keys stay `标签I.S-N`
# (labelled) / `I.S-N` (heading with no label word — mirror of the PDF-side
# rule in extract_items_gm.py).
GM_SEC_RE = re.compile(r'^##\s*[§$]?\s*(\d{1,2})(?:' + GM_SEP + r')?\s+\S')
GM_ENTRY_RE = re.compile(
    r'^\s*(?:>\s*)?(?:###\s+|\*\*)(\d{1,3})(?:' + GM_SEP + r')\s*([^*\n]{0,80})')
GM_LABELED_RE = re.compile(
    r'\b(' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*([IVXLCDM]+)\s*(?:' + GM_SEP + r')?\s*(\d+)\s*(?:' + GM_SEP + r')?\s*(\d+)',
    re.IGNORECASE)
# First label keyword inside an item heading ("3. Proposition." -> 'Proposition'), or None
# when the heading carries no label word ("14. Skeleton and Dimension").
GM_HEAD_LABEL_RE = re.compile(
    r'\b(' + '|'.join(COMBINED_LABEL_KINDS) + r')s?\b', re.IGNORECASE)


def gm_head_label(title):
    """Label of an item heading ("3. Proposition." -> 'Proposition'), or None
    when the heading carries no label word ("14. Skeleton and Dimension")."""
    m = GM_HEAD_LABEL_RE.search(title)
    if not m:
        return None
    raw = m.group(1)
    if raw.lower().endswith('s') and len(raw) > 1 and \
            raw[:-1].lower() in (k.lower() for k in EN_LABEL_KINDS):
        raw = raw[:-1]
    return raw[:1].upper() + raw[1:]

# _canon_label is imported from config (see import above) — single source
# of truth for bilingual label canonicalization.  The local copy was removed to
# avoid divergence (e.g. Example must canonize to 练习 on BOTH the md side and
# the extractor side so the exercise group routes correctly).

def _first_num(key):
    """Return the first integer found in a key string (e.g. leading chapter
    number of '定义1.1' -> 1). Returns -1 if none."""
    m = re.search(r'\d+', key)
    return int(m.group()) if m else -1

# --- 显式异章限定词（cross-chapter qualifier）---
# 正文交叉引用常带显式章限定："Proposition 5.4 of Chap. 0" / "第9章的引理 3.8" /
# "（第9章，推论 3.10）"。这类 mention 指向**别的章**的条目，不属于本章契约，
# 若进入 all_keys 会在 A 层 EXTRA（仅参考）中反复刷屏。keys_in_md 收到
# `chapter` 参数时，把「限定词章号 != 本章」的正文提及剔除；条目（加粗标签）
# 永不过滤。限定词识别：AFTER 型 "… of Chap.(ter) X"（匹配点后 20 字符内）、
# BEFORE 型 "第X章[的，、：:；]" 与 "Chap.(ter) X[,，]"（紧贴匹配点之前）。
_CHAP_QUAL_AFTER_RE = re.compile(r'[Cc]hap(?:ter|\.)?\s*(\d{1,3})')
_CHAP_QUAL_BEFORE_CN_RE = re.compile(r'第\s*(\d{1,3})\s*章\s*[的，、：:；]?\s*$')
_CHAP_QUAL_BEFORE_EN_RE = re.compile(r'[Cc]hap(?:ter|\.)\s*(\d{1,3})\s*[,，]\s*$')


def _is_foreign_chapter_ref(line, start, end, chapter):
    """该正文提及是否带「指向异章」的显式章限定词（chapter=None 时恒 False）。"""
    if chapter is None:
        return False
    m = _CHAP_QUAL_AFTER_RE.search(line, end, min(len(line), end + 20))
    if m and int(m.group(1)) != chapter:
        return True
    before = line[max(0, start - 16):start]
    mb = _CHAP_QUAL_BEFORE_CN_RE.search(before)
    if mb and int(mb.group(1)) != chapter:
        return True
    mb = _CHAP_QUAL_BEFORE_EN_RE.search(before)
    if mb and int(mb.group(1)) != chapter:
        return True
    return False


def keys_in_md(path, ordinal=ORDINAL_THREE_LEVEL, chapter_roman=None, groups=None,
               chapter=None):
    """Entries/all_keys from an .md file.

    `groups` is the BookConfig.ordinal GroupConfig array (new v2 form).  When
    given, EVERY group contributes its branch's keys so a multi-group config
    (e.g. 定理/定义 + 练习) parses BOTH numbering styles and unions them —
    the exercise group's two-level keys are captured alongside the theorem
    group's three-level keys.  When only `ordinal` (int) is supplied it is
    treated as a single group (back-compat shortcut).  `chapter_roman` is
    required for any GM/ROMAN group.  `chapter`（可选）为该 md 所属章号：给出时，
    带显式异章限定词（of Chap. X / 第X章…，X != chapter）的正文提及不进入
    all_keys（条目标签不受影响）；缺省 None 保持旧行为。
    """
    if groups is None:
        groups = [GroupConfig(type=int(ordinal) if ordinal is not None else ORDINAL_THREE_LEVEL)]
    # Any group needing a roman chapter prefix?
    needs_roman = any(g.type in (ORDINAL_GM, ORDINAL_ROMAN) for g in groups)
    if needs_roman and chapter_roman is None:
        raise ValueError("keys_in_md(group with type=ORDINAL_GM/ORDINAL_ROMAN) requires chapter_roman")
    entries, allk = set(), set()
    try:
        lines = open(path, 'r', encoding='utf-8').readlines()
    except Exception:
        return entries, allk
    for g in groups:
        t = g.type
        cur_sec = None
        for line in lines:
            if t == ORDINAL_GM:
                if chapter_roman is None:
                    raise ValueError("keys_in_md(ordinal=ORDINAL_GM) requires chapter_roman")
                sm = GM_SEC_RE.match(line.strip())
                if sm:
                    cur_sec = int(sm.group(1))
                    continue
                if cur_sec is None:
                    continue
                for m in GM_ENTRY_RE.finditer(line):
                    n = int(m.group(1))
                    if n > 40:
                        continue
                    lbl = gm_head_label(m.group(2))
                    key = (f"{_canon_label(lbl)}{chapter_roman}.{cur_sec}-{n}"
                           if lbl else f"{chapter_roman}.{cur_sec}-{n}")
                    entries.add(key); allk.add(key)
                for m in GM_LABELED_RE.finditer(line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}-{m.group(4)}")
            elif t == ORDINAL_TWO_LEVEL:
                for m in ENTRY_RE_2.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}"
                    entries.add(key); allk.add(key)
                for m in PROSE_RE_2.finditer(line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
            elif t == ORDINAL_EN:
                for m in ENTRY_RE_EN_C.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}"
                    entries.add(key); allk.add(key)
                for m in ENTRY_RE_EN_SINGLE_C.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}"
                    entries.add(key); allk.add(key)
                for m in ENTRY_RE_EN_NF_C.finditer(line):
                    key = f"{_canon_label(m.group(3))}{m.group(1)}.{m.group(2)}"
                    entries.add(key); allk.add(key)
                for m in PROSE_RE_EN_C.finditer(line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
            elif t in (ORDINAL_EN3, ORDINAL_CN3LAB):
                # EN3（Label C.S.N，如 Lasota & Mackey）与 CN3LAB（标签C.S.N，如
                # 孙文祥《遍历论》`定理1.1.1`）共用同一 md 侧解析：键 = 规范标签
                # （_canon_label 双语归一，Theorem/定理 → 定理）+ 点分三段。
                # COMBINED_LABEL_KINDS 同时含中英标签词，两侧天然对齐。
                for m in ENTRY_RE_EN3_C.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}.{m.group(4)}"
                    entries.add(key); allk.add(key)
                for m in PROSE_RE_EN3_C.finditer(line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}.{m.group(4)}")
            elif t == ORDINAL_SINGLE:
                # Single-level EN book (e.g. Silverman "A Friendly Introduction to
                # Number Theory" 4th ed — ordinal type 1): items carry ONE
                # numeric component ("Theorem 1", "Lemma 1"); there is no
                # section/item split.  Previously this ordinal fell through to
                # the three-level `else` branch (ENTRY_RE / KEY_RE expecting a
                # "C.S-N" form), so NOTHING was extracted from the md and every
                # contract item surfaced as falsely truly-missing.  Reuse the
                # single-number EN regex (ENTRY_RE_EN_SINGLE_C, already applied by
                # the ORDINAL_EN branch for chapter-wide single-digit entries);
                # COMBINED_LABEL_KINDS makes it match both EN ("Theorem 2") and
                # CN ("定理2") bold heads, canonicalized to the Chinese key
                # ("定理2") that read_structure_items emits, so EN+CN both match.
                for m in ENTRY_RE_EN_SINGLE_C.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}"
                    entries.add(key); allk.add(key)
            elif t == ORDINAL_ROSS:
                # Ross 体例（ORDINAL_ROSS = 11）：**Example 2a** / **Axiom 1** /
                # **Proposition 4.1**。字母位键必须先于单数字形态（SINGLE 的负向
                # 断言已拒字母尾，二者互斥，但顺序仍按特异度排）；点分两段形态由
                # ENTRY_RE_EN_C 覆盖。规范键 = 规范中文标签 + 原编号
                # （例2a / 公理1 / 命题4.1），与 read_structure_items 对齐。
                for m in ENTRY_RE_ROSS_LETTER_C.finditer(line):
                    key = _ross_canon(m.group(1), m.group(2), m.group(3).lower())
                    entries.add(key); allk.add(key)
                for m in ENTRY_RE_EN_C.finditer(line):
                    entries.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
                    allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
                for m in ENTRY_RE_ROSS_SINGLE_C.finditer(line):
                    entries.add(_ross_canon(m.group(1), m.group(2)))
                    allk.add(_ross_canon(m.group(1), m.group(2)))
                for m in PROSE_RE_ROSS_LETTER.finditer(line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(_ross_canon(m.group(1), m.group(2), m.group(3).lower()))
                for m in PROSE_RE_EN_C.finditer(line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
                for m in PROSE_RE_ROSS_SINGLE.finditer(line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(_ross_canon(m.group(1), m.group(2)))
            elif t == ORDINAL_ROMAN:
                for m in ENTRY_RE_ROMAN.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}-{m.group(4)}"
                    entries.add(key); allk.add(key)
                for m in PROSE_RE_ROMAN.finditer(line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}-{m.group(4)}")
            elif t == ORDINAL_HUM:
                for m in ENTRY_RE_HUM.finditer(line):
                    label = _canon_label(m.group(1))
                    letter = m.group(2) or ''
                    number = m.group(3) or ''
                    if letter:
                        key = f"{label} {letter.upper()}"
                    elif number:
                        key = f"{label}{number}"
                    else:
                        key = label
                    entries.add(key); allk.add(key)
                for m in PROSE_RE_2.finditer(line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
            else:
                for m in ENTRY_RE.finditer(line):
                    entries.add(normkey(m.group(1)))
                for m in KEY_RE.finditer(line):
                    allk.add(normkey(f'{m.group(1)}.{m.group(2)}-{m.group(3)}'))
    return entries, allk

def sortkey(k):
    return tuple(int(x) for x in re.findall(r'\d+', k))
