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
    'Remark': '评注', '评注': '评注', '注释': '评注', '注': '评注',
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
                  'Assumption', 'Algorithm']
# Chinese label synonyms that appear in bilingual-book .md files.
CN_LABEL_KINDS = ['定义', '定理', '引理', '推论', '命题', '例', '示例', '评注', '注释',
                  '注', '公理', '断言', '猜想', '条件', '假设', '算法']
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

def _canon_label(lbl):
    return _LABEL_CANON.get(lbl, lbl)

def _first_num(key):
    """Return the first integer found in a key string (e.g. leading chapter
    number of '定义1.1' -> 1). Returns -1 if none."""
    m = re.search(r'\d+', key)
    return int(m.group()) if m else -1

def keys_in_md(path, scheme='three-level'):
    entries, allk = set(), set()
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            if scheme == 'two-level':
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
            else:
                for m in ENTRY_RE.finditer(line):
                    entries.add(normkey(m.group(1)))
                for m in KEY_RE.finditer(line):
                    allk.add(normkey(f'{m.group(1)}.{m.group(2)}-{m.group(3)}'))
    return entries, allk

def sortkey(k):
    return tuple(int(x) for x in re.findall(r'\d+', k))
