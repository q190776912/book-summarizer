"""Shared numbering regexes and label maps for book-summarizer.

Centralizes constants that were duplicated across extractors/verifiers — most
notably the Hilton & Stammbach two-level "section.item" scheme, which was
copied verbatim in both ``extract_items_hom.py`` and ``verify_hom.py``.
Importing from here keeps the two scripts in sync (one source of truth).
"""

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

import re

# --- H&S two-level "section.item" scheme (NO chapter digit) ---
# Chapters are ROMAN (I..IX) and are not part of item numbers; items are
# numbered per section: "Theorem 2.1", "Proposition 3.1", "Definition 1.1" ...
HOM_ITEM_RE = re.compile(
    r'(定义|定理|引理|推论|命题|Definition|Theorem|Lemma|Corollary|Proposition)'
    r'\s*[（(]?\s*(\d{1,2})\.(\d{1,3})[）)]?')
HOM_EX_RE = re.compile(r'(例|Example)\s*\(?(\d{1,2})(?:\.(\d{1,3}))?\)?')

# citation words that mark a cross-reference rather than a definition
HOM_CITE_RE = re.compile(r'(见|由|根据|参考|参见|据|cf\.|see|by|from|in)\s*$', re.I)

HOM_LABEL_MAP = {'定义': '定义', '定理': '定理', '引理': '引理', '推论': '推论',
                 '命题': '命题', 'Definition': '定义', 'Theorem': '定理',
                 'Lemma': '引理', 'Corollary': '推论', 'Proposition': '命题'}

HOM_MD_ENTRY_RE = re.compile(r'\*\*(定义|定理|引理|推论|命题)\s*(\d{1,2})\.(\d{1,3})')
