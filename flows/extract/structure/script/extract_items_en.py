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

# ---------------------------------------------------------------------------
# ENGLISH-aware extraction (two-level English numbering)
# For English textbooks with two-level numbering (Theorem 1.1, Definition 1.1,
# Example 1.25, ...). Returns items shaped like the CN path: {key, label, page, text}.
# ---------------------------------------------------------------------------
EN_LABELS = ["Definition", "Theorem", "Lemma", "Proposition", "Corollary", "Example",
             "Assertion", "Conjecture", "Remark"]
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

def extract_items_en(extract_dir, start, end, want_examples=True):
    items = []
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
            for m in EN_LAB_RE.finditer(txt):
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
                # Normalize OCR-tolerant numeric tokens (letter↔digit confusions
                # like l→1, O→0) so the contract carries the canonical number.
                n1 = _ocr_int(m.group(2))
                if n1 is None:
                    continue
                if m.group(3) is not None:
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
                # Let...") are kept.
                if m.group(3) is None:
                    after = txt[m.end():].lstrip()
                    if after and after[0].isascii() and after[0].islower():
                        continue
                snippet = txt[max(0, m.start() - 5):m.end() + 90].replace("\n", " ")
                items.append({"key": key, "label": label,
                              "page": p, "text": snippet})
    seen = {}
    for it in items:
        if it["key"] not in seen:
            seen[it["key"]] = it
    out = sorted(seen.values(), key=lambda x: (x["page"], x["key"]))
    return out
