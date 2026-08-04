"""
key_parse.py — key/label regexes + canon maps + parsing/canonization helpers.

This module is the single home for ALL key/label parsing logic used across the
verify package: the three-level / two-level / English key regexes, the label
canonicalization maps (_LABEL_CANON etc.), `normkey`, `keys_in_md`, `sortkey`
and `_first_num`. It has NO heavy dependencies (no cv2 / torch) so it can be
imported standalone in a bare environment.
"""
import re, sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# --- fraleigh scheme: section-based two-level (Fraleigh《抽象代数基础教程》) ---
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
    r'\*\*(' + FR_COMBINED_LABELS + r')\s*(\d+)\.(\d+)[^\n*]*\*+')
FR_PROSE_RE = re.compile(
    r'(' + FR_COMBINED_LABELS + r')\s*(\d+)\.(\d+)')

# --- three-level (default) key parsing ---
# Matches both dash (N.S-N) and dot (N.S.N) numbering — the extractor
# canonicalizes everything to dash, but the .md may keep the book's dot style.
KEY_RE = re.compile(r'(\d+)\.(\d+)[\.\-](\d+)')
# A bold entry looks like  **标签N.S-N**  or  **N.S-N 名称**  or  > **例N.S-N**
ENTRY_RE = re.compile(r'\*\*[^*]*?(\d+\.\d+[\.\-]\d+)[^*]*\*+')

# --- two-level key parsing (e.g. 周民强《实变函数论》) ---
# Bold entries:  **定义1.1**： / **定理1.1**：
# NOTE: labels MUST be an alternation, not a char class. A char class
# [定义定理...] matches a SINGLE cjk char, so `**定义1.1**` (label is 2 chars)
# would never match — every entry then silently degrades to "mentioned-only".
ENTRY_RE_2 = re.compile(
    r'\*\*(定义|定理|引理|推论|命题'
    r'|Definition|Theorem|Lemma|Corollary|Proposition)\s*(\d+)\.(\d+)\s*[.．]?\s*\*+')
# Prose / cross-reference mentions:  定义1.3, 由定理5.2 / by Theorem 5.2 ...
PROSE_RE_2 = re.compile(
    r'(定义|定理|引理|推论|命题'
    r'|Definition|Theorem|Lemma|Corollary|Proposition)\s*(\d+)\.(\d+)')

def normkey(s):
    """Canonicalize a key to N.S-N dash form (N.S.N -> N.S-N)."""
    parts = s.split('.')
    if len(parts) == 3:
        return f'{parts[0]}.{parts[1]}-{parts[2]}'
    return s

# Label -> canonical Chinese label. Bilingual EN books sometimes write item
# entries in ENGLISH (`**Definition 1.1**`) and sometimes in CHINESE
# (`**定义 1.1**` / `**注释 5.1**`) even within the same book, so the verifier
# must canonicalize BOTH forms to one key. EN->CN pairs keep EN/CN aligned;
# CN synonyms (注释/评注/注 -> 评注) unify the Chinese variants the extractor
# would emit as Remark->评注.
_LABEL_CANON = {
    'Definition': '定义', '定理': '定理', '定义': '定义',
    'Theorem': '定理',
    'Lemma': '引理', '引理': '引理',
    'Corollary': '推论', '推论': '推论',
    'Proposition': '命题', '命题': '命题',
    'Example': '例', '例': '例', '示例': '例',
    'Remark': '评注', '评注': '评注', '注释': '评注', '注': '评注', '注记': '评注',
    'Commentary': '评注',
    'Axiom': '公理', '公理': '公理',
    'Assertion': '断言', '断言': '断言',
    'Conjecture': '猜想', '猜想': '猜想',
    'Condition': '条件', '条件': '条件',
    'Assumption': '假设', '假设': '假设', '假定': '假设',
    'Algorithm': '算法', '算法': '算法',
}

# English two-level book item regexes (for scheme='en'). Mirror ENTRY_RE_2 /
# PROSE_RE_2 but include English label kinds AND Example (English summaries
# write **Example N.M** as a full entry, unlike the CN two-level scheme).
EN_LABEL_KINDS = ['Definition', 'Theorem', 'Lemma', 'Corollary', 'Proposition',
                  'Example', 'Remark', 'Axiom', 'Assertion', 'Conjecture',
                  'Assumption', 'Algorithm', 'Commentary']
# Chinese label synonyms that appear in bilingual-book .md files.
CN_LABEL_KINDS = ['定义', '定理', '引理', '推论', '命题', '例', '示例', '评注', '注释',
                  '注', '注记', '公理', '断言', '猜想', '条件', '假设', '算法']
# Combined (used by the 'en' scheme so either language matches).
COMBINED_LABEL_KINDS = EN_LABEL_KINDS + CN_LABEL_KINDS
ENTRY_RE_EN = re.compile(
    r'\*\*(?:' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*(\d+)\.(\d+)\s*\*+')
PROSE_RE_EN = re.compile(
    r'\b(?:' + '|'.join(COMBINED_LABEL_KINDS) + r')\b\s*(\d+)\.(\d+)')

# Capturing variants of the EN regexes (label as group(1)) — used by
# keys_in_md('en'), which needs the label to canonicalize (Definition->定义...).
# PREFIX match only: real entries look like `**Definition 1.1 (Title)**：` or
# `**定义 5.1（级联系统）**：` — the number is immediately after the label but a
# parenthetical + closing `**` follows, so we must NOT require `*` right after
# the number. The label IS captured (group 1) so we can canonicalize it.
ENTRY_RE_EN_C = re.compile(
    r'\*\*(' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*(\d+)\.(\d+)')
PROSE_RE_EN_C = re.compile(
    r'\b(' + '|'.join(COMBINED_LABEL_KINDS) + r')\b\s*(\d+)\.(\d+)')

# --- roman three-level (e.g. Gelfand-Manin "Methods of Homological Algebra") ---
# Item numbers are Chapter.Section.Item with a ROMAN chapter: I.2.13, II.3.5.
# The chapter prefix is a roman numeral; section/item are arabic.
ROMAN_KEY_RE = re.compile(r'([IVXLCDM]+)\.(\d+)[\.\-](\d+)')
ENTRY_RE_ROMAN = re.compile(
    r'\*\*((' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*([IVXLCDM]+)\.(\d+)[\.\-](\d+))')
PROSE_RE_ROMAN = re.compile(
    r'\b(' + '|'.join(COMBINED_LABEL_KINDS) + r')\b\s*([IVXLCDM]+)\.(\d+)[\.\-](\d+)')

# --- gm scheme: BOOK-printed forms, roman machine keys ---
# Gelfand-Manin style books print sections per chapter ("## §1. Triangulated
# Spaces") and item titles as per-section headings; the .md renders them as
# ATX sub-headings ("### 1. Main Definitions", "### 3. Proposition." — book
# typography, 2026-08 user directive).  Legacy "**N. Title**" inline bold is
# still accepted for backward compatibility.  Full "Proposition I.2.11" labels
# appear only in prose cross-references.  Machine keys stay `标签I.S-N`
# (labelled) / `I.S-N` (heading with no label word — mirror of the PDF-side
# rule in extract/extract_items_gm.py).
GM_SEC_RE = re.compile(r'^##\s*[§$]?\s*(\d{1,2})[.．、]?\s+\S')
GM_ENTRY_RE = re.compile(
    r'^\s*(?:>\s*)?(?:###\s+|\*\*)(\d{1,3})[.．]\s*([^*\n]{0,80})')
GM_LABELED_RE = re.compile(
    r'\b(' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*([IVXLCDM]+)\s*\.?\s*(\d+)\s*\.?\s*(\d+)',
    re.IGNORECASE)
# First label keyword inside an item heading ("3. Proposition. ...",
# "6. Definition (- Lemma). ...", "9. Remarks and Examples", or the CN
# translations "3. 命题.", "6. 定义（-引理）.").  BOTH EN and CN label words
# are accepted so the gm scheme verifies the derived CN chapter too (extract
# keys are already Chinese-canonical via _canon_label).  The optional plural
# 's' lets "Examples"/"Remarks" match ("1. Main Definitions" matches as
# Definition+s too) — SAME rule as extract/extract_items_gm.py so both sides
# build identical keys.
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

def _canon_label(lbl):
    if lbl in _LABEL_CANON:
        return _LABEL_CANON[lbl]
    # Case-insensitive English labels: prose cross-references are written in
    # the .md as "proposition II.5.15" (lowercase) while the extractor
    # normalizes them via _norm_label before _canon_label; both sides must
    # produce the same canonical Chinese label.  Handles 'cor.'/'def.'
    # abbreviations and plurals ("propositions") the same way.
    low = lbl.lower()
    if low in ('cor.', 'def.'):
        low = {'cor.': 'corollary', 'def.': 'definition'}[low]
    if low.endswith('s') and len(low) > 1 and \
            low[:-1] in (k.lower() for k in EN_LABEL_KINDS):
        low = low[:-1]
    for k in EN_LABEL_KINDS:
        if k.lower() == low:
            return _LABEL_CANON[k]
    return lbl

def _first_num(key):
    """Return the first integer found in a key string (e.g. leading chapter
    number of '定义1.1' -> 1). Returns -1 if none."""
    m = re.search(r'\d+', key)
    return int(m.group()) if m else -1

def keys_in_md(path, scheme='three-level', chapter_roman=None):
    """Entries/all_keys from an .md file.

    For scheme='gm', `chapter_roman` (e.g. 'I') is REQUIRED: the .md headings
    are bare per-section ordinals with no chapter prefix, so the chapter is
    known only at the call site (the verify context).
    """
    entries, allk = set(), set()
    cur_sec = None
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if scheme == 'gm':
                if chapter_roman is None:
                    raise ValueError("keys_in_md(scheme='gm') requires chapter_roman")
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
            elif scheme == 'two-level':
                for m in ENTRY_RE_2.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}"
                    entries.add(key); allk.add(key)
                for m in PROSE_RE_2.finditer(line):
                    allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
            elif scheme == 'en':
                for m in ENTRY_RE_EN_C.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}"
                    entries.add(key); allk.add(key)
                for m in PROSE_RE_EN_C.finditer(line):
                    allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
            elif scheme == 'fraleigh':
                for m in FR_ENTRY_RE.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}"
                    entries.add(key); allk.add(key)
                for m in FR_PROSE_RE.finditer(line):
                    allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
            elif scheme == 'roman':
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
