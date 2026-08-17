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
    ORDINAL_TWO_LEVEL, ORDINAL_EN, ORDINAL_ROMAN, ORDINAL_GM, ORDINAL_FRALEIGH,
    ORDINAL_EN3, ORDINAL_THREE_LEVEL, GroupConfig, _LABEL_CANON, EN_LABEL_KINDS,
    _canon_label,
)

# GM (Gelfand-Manin) section/entry separators: the shared wildcard set
# (SEP_TIGHT) plus the ideographic comma "、" that GM book headings
# occasionally use ("## 1、 Triangulated …"). Derived from SEP_TIGHT so the
# GM separator stays in lockstep with the rest of the pipeline's policy
# (single source of truth in lib.regexlib).
GM_SEP = SEP_TIGHT[:-1] + r'、]'

# --- Fraleigh (ordinal=ORDINAL_FRALEIGH): section-based two-level ---
# Unlike 周民强-type two-level (where first number == CHAPTER and label counters
# are independent/shared), Fraleigh numbers items per global SECTION, and the
# Chinese translation groups sections into chapters (ch1 = secs 1-7, ch2 = secs
# 8-11, ...). Item keys are 标签S.N where S is the SECTION number: 定义8.1,
# 例1.2, 表1.20, 图3.6, 定理8.5. Labels include 例/表/图 (extractor emits them).
FR_COMBINED_LABELS = '|'.join(
    ['定义', '定理', '引理', '推论', '命题', '例', '表', '图',
     'Definition', 'Theorem', 'Lemma', 'Corollary', 'Proposition',
     'Example', 'Table', 'Figure'])
FR_ENTRY_RE = re.compile(
    r'\*\*(' + FR_COMBINED_LABELS + r')\s*(\d+)' + SEP_TIGHT + r'(\d+)[^\n*]*\*+')
FR_PROSE_RE = re.compile(
    r'(' + FR_COMBINED_LABELS + r')\s*(\d+)' + SEP_TIGHT + r'(\d+)')

# --- three-level (default) key parsing ---
# KEY_RE / ENTRY_RE are imported from lib.regexlib (label-FREE, built from
# SEP_TIGHT). They match both dash (N.S-N) and dot (N.S.N) numbering — the
# extractor canonicalizes everything to dash, but the .md may keep the book's
# dot style.

# --- two-level key parsing (e.g. 周民强《实变函数论》) ---
# Bold entries:  **定义1.1**： / **定理1.1**：
# NOTE: labels MUST be an alternation, not a char class. A char class
# [定义定理...] matches a SINGLE cjk char, so `**定义1.1**` (label is 2 chars)
# would never match — every entry then silently degrades to "mentioned-only".
ENTRY_RE_2 = re.compile(
    r'\*\*(定义|定理|引理|推论|命题'
    r'|Definition|Theorem|Lemma|Corollary|Proposition)\s*(\d+)' + SEP_TIGHT + r'(\d+)\s*(?:' + SEP_TIGHT + r')?\s*\*+')
# Prose / cross-reference mentions:  定义1.3, 由定理5.2 / by Theorem 5.2 ...
PROSE_RE_2 = re.compile(
    r'(定义|定理|引理|推论|命题'
    r'|Definition|Theorem|Lemma|Corollary|Proposition)\s*(\d+)' + SEP_TIGHT + r'(\d+)')

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
                  '注', '注记', '公理', '断言', '猜想', '条件', '假设', '算法']
# Combined (used when ordinal == ORDINAL_EN so either language matches).
COMBINED_LABEL_KINDS = EN_LABEL_KINDS + CN_LABEL_KINDS
ENTRY_RE_EN = re.compile(
    r'\*\*(?:' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*(\d+)' + SEP_TIGHT + r'(\d+)\s*\*+')
PROSE_RE_EN = re.compile(
    r'\b(?:' + '|'.join(COMBINED_LABEL_KINDS) + r')\b\s*(\d+)' + SEP_TIGHT + r'(\d+)')

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
PROSE_RE_EN_C = re.compile(
    r'\b(' + '|'.join(COMBINED_LABEL_KINDS) + r')\b\s*(\d+)' + SEP_TIGHT + r'(\d+)',
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

# EN3 (ORDINAL_EN3 / type 9): English three-level, LABEL-FIRST dots (Label C.S.N),
# e.g. Lasota & Mackey《Chaos, Fractals, and Noise》.  Items are numbered three
# deep (Remark 1.1.1 / Definition 2.3.4 / Theorem 3.2.1).  IDENTICAL in spirit to
# ORDINAL_EN but with a THIRD numeric component.  The label is captured (group 1)
# so keys_in_md can canonize it to the Chinese structure key (Remark -> 评注,
# Example -> 例, Definition -> 定义, ...) aligning with book_structure.json.  The
# bold `**` prefix naturally excludes FIGURE 1.1.1 / (1.1.1) figure/formula numbers
# (no label word), avoiding key collisions with the item set.
ENTRY_RE_EN3_C = re.compile(
    r'\*\*(' + '|'.join(COMBINED_LABEL_KINDS) + r')'
    r'\s*(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)',
    re.IGNORECASE)
PROSE_RE_EN3_C = re.compile(
    r'\b(' + '|'.join(COMBINED_LABEL_KINDS) + r')\b'
    r'\s*(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)',
    re.IGNORECASE)

# --- roman three-level (e.g. Gelfand-Manin "Methods of Homological Algebra") ---
# Item numbers are Chapter.Section.Item with a ROMAN chapter: I.2.13, II.3.5.
# The chapter prefix is a roman numeral; section/item are arabic.
ENTRY_RE_ROMAN = re.compile(
    r'\*\*((' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*([IVXLCDM]+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+))')
PROSE_RE_ROMAN = re.compile(
    r'\b(' + '|'.join(COMBINED_LABEL_KINDS) + r')\b\s*([IVXLCDM]+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)')

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

def keys_in_md(path, ordinal=ORDINAL_THREE_LEVEL, chapter_roman=None, groups=None):
    """Entries/all_keys from an .md file.

    `groups` is the BookConfig.ordinal GroupConfig array (new v2 form).  When
    given, EVERY group contributes its branch's keys so a multi-group config
    (e.g. 定理/定义 + 练习) parses BOTH numbering styles and unions them —
    the exercise group's two-level keys are captured alongside the theorem
    group's three-level keys.  When only `ordinal` (int) is supplied it is
    treated as a single group (back-compat shortcut).  `chapter_roman` is
    required for any GM/ROMAN group.
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
                    allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}-{m.group(4)}")
            elif t == ORDINAL_TWO_LEVEL:
                for m in ENTRY_RE_2.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}"
                    entries.add(key); allk.add(key)
                for m in PROSE_RE_2.finditer(line):
                    allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
            elif t == ORDINAL_EN:
                for m in ENTRY_RE_EN_C.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}"
                    entries.add(key); allk.add(key)
                for m in ENTRY_RE_EN_SINGLE_C.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}"
                    entries.add(key); allk.add(key)
                for m in PROSE_RE_EN_C.finditer(line):
                    allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
            elif t == ORDINAL_EN3:
                for m in ENTRY_RE_EN3_C.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}.{m.group(4)}"
                    entries.add(key); allk.add(key)
                for m in PROSE_RE_EN3_C.finditer(line):
                    allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}.{m.group(4)}")
            elif t == ORDINAL_FRALEIGH:
                for m in FR_ENTRY_RE.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}"
                    entries.add(key); allk.add(key)
                for m in FR_PROSE_RE.finditer(line):
                    allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
            elif t == ORDINAL_ROMAN:
                for m in ENTRY_RE_ROMAN.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}-{m.group(4)}"
                    entries.add(key); allk.add(key)
                for m in PROSE_RE_ROMAN.finditer(line):
                    allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}-{m.group(4)}")
            else:
                for m in ENTRY_RE.finditer(line):
                    entries.add(normkey(m.group(1)))
                for m in KEY_RE.finditer(line):
                    allk.add(normkey(f'{m.group(1)}.{m.group(2)}-{m.group(3)}'))
    return entries, allk

def sortkey(k):
    return tuple(int(x) for x in re.findall(r'\d+', k))
