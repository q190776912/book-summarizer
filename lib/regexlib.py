"""book-summarizer shared separator / numbering regex library.

Single source of truth for the inter-component separator policy used across the
verify pipeline and the extractors.  Previously every module hardcoded its own
``[.\\-]`` / ``[.．]`` / ``.`` separator set, which broke on books that use a
slightly different punctuation between numbering components.  Here the
separator is WILDCARDED:

  * ``SEP_TIGHT`` — used by *matching* regexes (character-class, no space, no
    comma) so an unanchored ``finditer`` never swallows prose like "1, 2, 3"
    or "Eq. 2.3".
  * ``SEP_WIDE``  — used ONLY by ``re.split`` / ``canon_sep`` where the input is
    already anchor-bounded, so a broader set (spaces, fullwidth commas …) is
    safe and makes any separator style normalize to one canonical form before
    comparison.

This module depends only on ``re`` / ``functools`` (standalone, no cv2/torch),
and contains NO label knowledge — label-embedded regexes stay in
``verify/key_parse.py``.

Imported as ``from lib.regexlib import ...`` (the skill root is on sys.path).
"""

import re
import functools

# --- separator policy -------------------------------------------------------
# Matching-class separator: real digit-to-digit separators only (no whitespace,
# no comma) so unanchored scans stay precise.
SEP_TIGHT = r'[.\-–·/．－〜]'

# Wide separator: any punctuation/whitespace that can separate numeric
# components in a *bounded* context (re.split / canon). Includes the fullwidth
# comma "，" and ASCII comma so Chinese/English prose separators normalize too.
SEP_WIDE = r'[\s._\-–·/：:／~～_＋+，,;；、．－〜]+'
SEP_SPLIT_RE = re.compile(SEP_WIDE)

# Numeric separator: used by the *number matchers* in the extractors
# (num_re / lab_re / fr_re / EN_LAB_RE / fallback_re / scan_items).  Like
# SEP_WIDE it tolerates whitespace + fullwidth comma, but deliberately EXCLUDES
# the more dangerous colon / plus / semicolon / ideographic-comma / slash so a
# decimal "3.14", a formula "a:b" or a date "4/7/2001" is never misread as a
# numbering path.  Adds the fullwidth period/hyphen (．/－) that OCR frequently
# emits — the gap the original hardcoded ``[\.\-\·\，\s]`` set left open.
SEP_NUMERIC = r'[\s.\-–·．－〜，,]'


def canon_sep(s):
    """Normalize any run of separators in ``s`` to a single '.' and strip ends."""
    parts = [p for p in SEP_SPLIT_RE.split(s) if p]
    return '.'.join(parts)


def canon_token_numeric(s):
    """Canonicalize a numbering token's numeric part to '.'-separated form,
    preserving an optional leading label word.

    'Theorem 12-3' -> 'Theorem 12.3'
    '定理 4。11-5'  -> '定理 4.11.5'
    '4·11·5'       -> '4.11.5'
    """
    s = s.strip()
    m = re.match(r'^([A-Za-z\u4e00-\u9fff]+)\s*(.*)$', s)
    if m:
        label = m.group(1)
        num = canon_sep(m.group(2))
        return f"{label} {num}" if num else label
    return canon_sep(s)


def split_numpath(s, levels):
    """Split a bare key into ``levels`` ints using the wide separator (robust to
    runs like '4..5' / '4--5'); return None if component count != levels."""
    parts = [p for p in SEP_SPLIT_RE.split(s.strip()) if p]
    if len(parts) != levels:
        return None
    try:
        return [int(p) for p in parts]
    except ValueError:
        return None


# --- shared label-FREE compiled regexes (all built from SEP_TIGHT) ----------
# Label-embedded regexes (ENTRY_RE_ROMAN, FR_*, ENTRY_RE_2, ENTRY_RE_EN*,
# GM_LABELED_RE …) live in verify/key_parse.py, which imports SEP_TIGHT from
# here and rebuilds them with the wildcard separator.
KEY_RE = re.compile(r'(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)')
ENTRY_RE = re.compile(r'\*\*[^*]*?(\d+' + SEP_TIGHT + r'\d+' + SEP_TIGHT + r'\d+)[^*]*\*+')
ROMAN_KEY_RE = re.compile(r'([IVXLCDM]+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)')
