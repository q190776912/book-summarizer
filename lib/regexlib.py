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
``verify/script/key_parse.py``.

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
# (num_re / lab_re / fr_re / EN_LAB_RE / fallback_re).  Like
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
# GM_LABELED_RE …) live in verify/script/key_parse.py, which imports SEP_TIGHT from
# here and rebuilds them with the wildcard separator.
KEY_RE = re.compile(r'(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)')
ENTRY_RE = re.compile(r'\*\*[^*]*?(\d+' + SEP_TIGHT + r'\d+' + SEP_TIGHT + r'\d+)[^*]*\*+')
ROMAN_KEY_RE = re.compile(r'([IVXLCDM]+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)')


# --- shared label-bearing / domain regexes (centralised 2026-08-09) --------
# Only BYTE-IDENTICAL, same-semantics duplicates across packages are merged
# here.  Semantically divergent duplicates (e.g. g_layer.G_TERM vs
# fmt_extras.G_TERM, or the #{1,6} vs #{2,6} SEC_RE in wrap_examples_bq) are
# intentionally left local — blind merging would change behaviour.
# Consumers import with `as` aliases to keep local call-sites untouched.

# Chinese-scheme section-heading detectors (extract.scan_skeleton +
# verify.script.audit_counts).  OCR noise: §→8, glue of §/number, no space before title.
SEC_CN = re.compile(
    r'^[§Ss8*+x$\u00d7\u2605\u2606\s]*[.．·]?(\d{1,2})[\.\．·](\d{1,2})'
    r'[\.\．·。]?(?!\s+[\u4e00-\u9fff])(?=[^\d.．·。]*[\u4e00-\u9fff]).{0,24}$')
SECBARE_CN = re.compile(
    r'^[§Ss8*+x$\u00d7\u2605\u2606\s]*[.．·]?(\d{1,2})[\.\．·](\d{1,2})$')
SECGLUE_CN = re.compile(
    r'^[§Ss8*+x$\u00d7\u2605\u2606\s]*[Ss8§](\d{1,2})[\.\．·]?(\d{1,2})'
    r'[^\s\d](?=[^\d.．·。]*[\u4e00-\u9fff]).{0,24}$')

# Blockquote head line (verify.g_layer + format.fmt_extras).
G_HEAD = re.compile(r'^\s*>+\s*\*?(?:\*{0,2})(?:证明|证|例)')

# Figure OCR markers (figure.build_figure_index + figure.build_precise_anchors).
FIG_ITEM_SEC_RE = re.compile(r'^\s*(\d{1,2})\.(\d{1,2})\b\s*[:.]?\s*[A-Za-z]')
FIG_PAGE_RE = re.compile(r'=====\s*PAGE\s*(\d+)\s*=====')

# Format-package section heading / horizontal rule (#{2,6} variant; the
# #{1,6} variant in wrap_examples_bq is kept local on purpose).
FMT_SEC_RE = re.compile(r'^#{2,6}\s')
FMT_HR_RE = re.compile(r'^\s*---\s*$')

# Formula-number detectors (make_config + config/verify_config/tests +
# verify.formula_tag via FMT_* names).  Half/full-width parens both matched;
# negative lookbehind rejects function-call parens like x(0)/f(0).
F_SINGLE_RE = re.compile(r'(?<![\w\u4e00-\u9fff])[（(]\s*(\d+)\s*[）)]')
F_DOT_RE = re.compile(r'(?<![\w\u4e00-\u9fff])[（(]\s*(\d+\.\d+)\s*[）)]')
F_EQ_RE = re.compile(r'\b(?:Eq\.?|Equation)\s+(\d+\.\d+)')
F_CN_EQ_RE = re.compile(r'式\s*[（(]?\s*(\d+\.\d+)')
