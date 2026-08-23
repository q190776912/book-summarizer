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
from page_json import PageJson

import os, sys

import json, re
from lib.regexlib import SEP_TIGHT
from item_dedup import dedup_items

# ---------------------------------------------------------------------------
# ENGLISH-aware extraction (two-level English numbering)
# For English textbooks with two-level numbering (Theorem 1.1, Definition 1.1,
# Example 1.25, ...). Returns items shaped like the CN path: {key, label, page, text}.
# ---------------------------------------------------------------------------
# NOTE: "Assertion" is intentionally EXCLUDED. It is semantically a Proposition
# claim and is never a tracked ordinal group in any verify_config (the config
# groups are Theorem/Algorithm/Lemma/Conjecture/Proposition/Example/Question/
# Figure). Treating it as a contract item fabricates phantom "Assertion N"
# entries that can never match the md's "Assertion N" / "断言 N" (which the
# config does not require) — surfacing as false truly-missing. Per the user's
# ignore_ch7.json intent, Assertion items are non-blocking noise, so they must
# not enter the contract at all.
EN_LABELS = ["Definition", "Theorem", "Lemma", "Proposition", "Corollary", "Example",
             "Conjecture", "Remark"]
# Extended to ALSO capture single-number EN headings ("Theorem 1", used per
# chapter by Silverman's "A Friendly Introduction to Number Theory" 4th ed).
# The second numeric component is optional; single-number keys become
# "Theorem 1", two-level remain "Theorem 1.2".
#
# OCR-digit tolerance: mirror verbatim the OCR_DIGIT map used by
# verify/script/check_structure_completeness.py so the extractor recovers items
# the cross-scanner finds but a strict \d+ would miss — e.g. OCR reads
# "Theorem 7.l" (letter l instead of digit 1).  Without this, those items are
# silently dropped from the contract while scan_raw_items still catches them,
# which surfaces as false "missing_items" in the completeness gate.
OCR_DIGIT = {'O': 0, 'o': 0, 'Q': 0, 'D': 0, '0': 0,
             'I': 1, 'l': 1, 'i': 1, '1': 1,
             'Z': 2, 'z': 2, '2': 2,
             'E': 3, 'e': 3, '3': 3,
             'S': 5, 's': 5, '5': 5,
             'G': 6, 'g': 6, '6': 6,
             'T': 7, 't': 7, '7': 7,
             'B': 8, 'b': 8, '8': 8,
             'g': 9, '9': 9}

def _ocr_int(tok):
    """Normalize an OCR-tolerant numeric token to int (letters mapped via
    OCR_DIGIT). Returns None if any char cannot resolve to a digit."""
    s = ''.join(str(OCR_DIGIT.get(c, c)) for c in tok)
    return int(s) if s.isdigit() else None


def _levenshtein(a, b):
    """Standard Levenshtein edit distance (case-insensitive already applied
    by callers). Small, dependency-free; only used on short label words."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


# Tolerance for OCR-garbled label words in the NUMBER-FIRST (section-scoped)
# path.  do Carmo prints entries as `2.1 DEFINITION` but OCR mangles the label
# (`DEFINrTION`, `DEFINrrION`, `BxAMPLE`, `PROPosrTION`, …) while the `N.M`
# number stays intact.  The number alone is enough to know it IS an entry, but
# we still need the canonical label to key/type it correctly, so we fuzzy-match
# the garbled word against the known label set.  Threshold 2 recovers every
# observed do Carmo garble (all are <= 2 substitutions) without false-positive
# matches against ordinary prose words like `Let`/`Then` (distance >= 3).
_LABEL_FUZZY_THRESHOLD = 2


def _resolve_label(word, labels):
    """Resolve a (possibly OCR-garbled) heading word to its canonical label.

    Tries, in order: exact case-insensitive match, then Levenshtein-fuzzy
    match within `_LABEL_FUZZY_THRESHOLD`, then (fallback) scanning the first
    ~40 chars of the line for any exact label word — this last one catches
    named theorems where the label is NOT the first word, e.g. do Carmo's
    `2.2 Index Theorem.` (label = Theorem, not `Index`).
    Returns the canonical label string (e.g. ``"Definition"``) or None.
    """
    w = (word or "").strip()
    if not w:
        return None
    wl = w.lower()
    # 1) exact
    for lab in labels:
        if lab.lower() == wl:
            return lab
    # 2) fuzzy
    best, best_d = None, 99
    for lab in labels:
        d = _levenshtein(wl, lab.lower())
        if d <= _LABEL_FUZZY_THRESHOLD and d < best_d:
            best, best_d = lab, d
    if best is not None:
        return best
    return None


def _scan_inline_label(text, labels, window=40):
    """Fallback: return the first exact (case-insensitive) label word found in
    the first `window` chars of `text` (so a named theorem's label that appears
    after the entry name is still caught)."""
    head = text[:window]
    toks = re.findall(r"[A-Za-z][A-Za-z]{2,}", head)
    for t in toks:
        for lab in labels:
            if lab.lower() == t.lower():
                return lab
    return None

# Character class: any digit OR any OCR-confusable letter from OCR_DIGIT keys.
# NOTE: must include \d (all 0-9).  OCR_DIGIT only lists the letters it maps
# plus the literal digits that appear as map *values*; the digit "4" (and any
# digit with no letter-confusable) is NOT a key, so a bare key-set class would
# silently drop every item whose number contains such a digit (e.g.
# "Theorem 4.1").  Hence \d + the confusable letters.
_EN_OCR_LETTERS = ''.join(sorted(k for k in set(OCR_DIGIT.keys()) if not k.isdigit()))
EN_OCR_NUM = r'[\d' + _EN_OCR_LETTERS + r']+'

EN_LAB_RE = re.compile(
    r'\b(' + '|'.join(EN_LABELS) + r')\b\s*(?:\([^)]*\))?\s*'
    r'(' + EN_OCR_NUM + r')(?:\s*' + SEP_TIGHT + r'\s*(' + EN_OCR_NUM + r'))?',
    re.IGNORECASE,
)

# Section-scoped EN books (e.g. Fraleigh): the FIRST number is the SECTION, not
# the chapter, and the source additionally prints NUMBER-FIRST headings
# ("26.4 Lemma", "24.2 Corollary") alongside label-first ones, plus numbered
# graphics ("Table 1.20", "Figure 3.6"). The shared EN extractor handles these
# ONLY when `section_scoped=True`, so normal chapter-first EN books (Silverman,
# stochastic-processes, ...) keep their exact prior behavior untouched.
SECTION_LABELS = EN_LABELS + ["Table", "Figure", "表", "图"]
# Number-first headings ("2.1 DEFINITION", "24.2 Corollary") — the label word
# is captured RAW (may be OCR-garbled) and resolved to its canonical form by
# `_resolve_label` in the loop below.  We intentionally do NOT require the label
# to exactly match SECTION_LABELS here, because OCR mangles it
# (`DEFINrTION`, `BxAMPLE`, …); the number `N.M` is the reliable signal that
# this is an entry.  The captured word must be >= 3 letters so we don't grab a
# stray single letter.
EN_LAB_RE_NF = re.compile(
    r'(' + EN_OCR_NUM + r')\s*' + SEP_TIGHT + r'\s*(' + EN_OCR_NUM + r')\s+'
    r'(?:\([^)]*\)\s+)?([A-Za-z][A-Za-z]{2,})',
    re.IGNORECASE,
)


def extract_items_en(extract_dir, start, end, want_examples=True, section_scoped=False,
                     single=False):
    """Extract English item headings from OCR pages.

    ``single``: when True (single-level EN books, e.g. Silverman's "A Friendly
    Introduction to Number Theory" 4th ed — ORDINAL_SINGLE / type 1), items carry
    ONE numeric component ("Theorem 1", "Lemma 1"). The regex then MUST NOT
    capture a second component: OCR line-merge noise ("Assertion 1. The number..."
    glued to a later "7") would otherwise fabricate "Assertion 1.7". With
    ``single=False`` (default; two-level EN books like Kreyszig) the optional
    second component is kept ("Theorem 1.1").
    """
    items = []
    # Section-scoped books also accept numbered graphics (Table/Figure) as items.
    lab_labels = SECTION_LABELS if section_scoped else EN_LABELS
    if single:
        lab_re = re.compile(
            r'\b(' + '|'.join(lab_labels) + r')\b\s*(?:\([^)]*\))?\s*'
            r'(' + EN_OCR_NUM + r')',
            re.IGNORECASE,
        )
    else:
        lab_re = re.compile(
            r'\b(' + '|'.join(lab_labels) + r')\b\s*(?:\([^)]*\))?\s*'
            # 🔴 TIGHT second component (NO whitespace between SEP_TIGHT and the
            # digit).  Two-level EN numbering is ALWAYS printed tight
            # ("Theorem 1.1", "Lemma 2.3") with no space after the separator.
            # Allowing a trailing `\s*` here is catastrophic: a single-number
            # heading like "Example 2. Queueing" / "Example 3. Some Genetic"
            # ends with a SENTENCE period followed by a space and the TITLE
            # word.  EN_OCR_NUM includes OCR-0/5-confusable letters
            # (Q/O/o/D->0, S/s->5, ...), so the greedy `[\d...]+` then swallows
            # the title word's first letters as a phantom sub-number:
            #   "Example 2. Queueing" -> "Example 2.0"  (Q->0)
            #   "Example 3. Some"      -> "Example 3.50" (S->5,o->0)
            #   "Example 1. Suppose"   -> "Example 1.5"  (S->5)
            #   "Example 1. Our"       -> "Example 1.0"  (O->0)
            # Those fabricated keys never match the md's "例2"/"例3"/"例1",
            # surfacing as false TRULY-MISSING (A-layer M failures).  Requiring
            # the digit to be TIGHT against the separator kills the capture for
            # sentence-period+title (space present) while keeping every genuine
            # "1.1" intact.  (The leading `\s*` is kept so "Theorem 1.1" with a
            # separator that may follow the first number without a space still
            # matches — it does; the trailing one is what enabled the bug.)
            r'(' + EN_OCR_NUM + r')(?:\s*' + SEP_TIGHT + r'(' + EN_OCR_NUM + r'))?',
            re.IGNORECASE,
        )
    for p in range(start, end + 1):
        fp = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        with open(fp, "r", encoding="utf-8") as f:
            data = PageJson.load(os.path.join(extract_dir, f"page_{p:03d}.json")).data
        for t in data.get("text", []):
            txt = t.get("text", "")
            if not txt:
                continue
            for m in lab_re.finditer(txt):
                label = m.group(1)
                if label == "Example" and not want_examples:
                    continue
                # Heading vs prose reference: a real entry heading starts the
                # text block (e.g. "THEOREM 8.4. Let k >= 2."); a cross-reference
                # like "by Lemma 11.26" / "satisfy Theorem 11.1" sits mid-block.
                # Skip mid-block matches to avoid false-positive phantom items
                # (Apostol prints headings in UPPERCASE / OCR-mangled case, so
                # IGNORECASE is needed above, but it also widens prose capture).
                if txt[:m.start()].strip():
                    continue
                # Reject cross-reference headings: a genuine entry heading is
                # followed by a sentence period / space + title, never a closing
                # delimiter.  do Carmo prints entries NUMBER-FIRST, so a label-
                # first "Example 4.8)" is a reference, not a heading; without this
                # guard it fabricates a phantom item.
                _after = txt[m.end():m.end() + 1]
                if _after and _after in ")]},;:":
                    continue
                # Normalize OCR-tolerant numeric tokens (letter↔digit confusions
                # like l→1, O→0) so the contract carries the canonical number.
                n1 = _ocr_int(m.group(2))
                if n1 is None:
                    continue
                # single-mode regex has only 2 groups (label + number); the
                # optional second component (group 3) exists ONLY in two-level
                # mode. Guard every group(3) access with `not single`.
                if (not single) and m.group(3) is not None:
                    n2 = _ocr_int(m.group(3))
                    if n2 is None:
                        continue
                    key = f"{label} {n1}.{n2}"
                else:
                    key = f"{label} {n1}"
                # Reject single-level "Label N" matches that are actually prose
                # sentences (e.g. "Definition 15 is ambiguous..." / "Definition 0
                # of Markov time...") rather than numbered headings.  Genuine
                # two-level EN headings are always "Label N.M"; a bare "Label N"
                # immediately followed by a lowercase word is prose, not a
                # heading, and would otherwise pollute the contract (the B-layer
                # then flags a phantom 0..N gap).  Single-level headings that
                # start the next word with an uppercase letter (e.g. "Theorem 1
                # Let...") are kept.  Applies only to single-component keys
                # (single mode, or a two-level key whose n2 half was absent).
                if single or m.group(3) is None:
                    after = txt[m.end():].lstrip()
                    if after and after[0].isascii() and after[0].islower():
                        continue
                snippet = txt[max(0, m.start() - 5):m.end() + 90].replace("\n", " ")
                items.append({"key": key, "label": label,
                              "page": p, "text": snippet})
            # Section-scoped EN source also prints NUMBER-FIRST headings
            # ("2.1 DEFINITION", "24.2 Corollary") — always two-level, so no
            # single-level prose ambiguity to guard against.  The label word is
            # OCR-garbled in practice; resolve it to the canonical label via
            # exact/fuzzy/inline scan so the entry is keyed and typed correctly.
            if section_scoped:
                for m in EN_LAB_RE_NF.finditer(txt):
                    raw = m.group(3)
                    if txt[:m.start()].strip():
                        continue
                    n1 = _ocr_int(m.group(1))
                    n2 = _ocr_int(m.group(2))
                    if n1 is None or n2 is None:
                        continue
                    label = _resolve_label(raw, SECTION_LABELS)
                    if label is None:
                        # tertiary: the label may appear just after the entry
                        # name (e.g. "2.2 Index Theorem." -> Theorem).
                        label = _scan_inline_label(
                            txt[m.start():m.start() + 50], SECTION_LABELS)
                    if label is None:
                        continue
                    if label == "Example" and not want_examples:
                        continue
                    key = f"{label} {n1}.{n2}"
                    snippet = txt[max(0, m.start() - 5):m.end() + 90].replace("\n", " ")
                    items.append({"key": key, "label": label,
                                  "page": p, "text": snippet})
    # Collapse reference mentions but KEEP two genuinely different items that
    # share a (label, number) — e.g. a source book printing the same number
    # twice (a printing off-by-one).  Genuine headings are already pre-filtered
    # above (only block-start matches survive), so any same-key collision with a
    # different heading text is a distinct item.
    out = dedup_items(items)
    return out
