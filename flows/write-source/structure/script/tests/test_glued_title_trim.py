# -*- coding: utf-8 -*-
"""Regression: OCR-glued title tail must not eat the item number
(extract_items_en single mode; Rosen 8e §1.3/§1.5 Example 9, 2026-09-25).

"EXAMPLE 9Determine whether …" / "EXAMPLE 9Translate the statement" — the
EN_OCR_NUM confusable-letter class swallowed the title's first word
("9Dete" / "9T"), the lowercase-tail prose guard then rejected the whole
heading and the example vanished (B-layer 缺号 9, REAL gaps).

Fix under test: post-match trim back to the leading digits (syncing the match
end so the title tail resumes at "Determine"/"Translate"); legit OCR forms
("EXAMPLE 1o" = Example 10 followed by a space, "EXAMPLE3") unchanged.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_glued_title_trim.py
"""
import json
import os
import sys
import tempfile
import unittest
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

from extract_items_en import extract_items_en  # noqa: E402


def _mk_pages(d, lines):
    for i, ln in enumerate(lines, start=1):
        with open(os.path.join(d, f"page_{i:03d}.json"), "w", encoding="utf-8") as f:
            json.dump({"text": [{"text": ln}], "formulas": []}, f)


def _keys(d, n):
    return {it["key"].lower(): it for it in
            extract_items_en(d, 1, n, single=True)}


class TestGluedTitleTrim(unittest.TestCase):
    def test_glued_uppercase_title_kept_with_clean_number(self):
        lines = [
            "EXAMPLE 9Determine whether each of the compound propositions (pV-q) is satisfiable",
            "EXAMPLE 10 Show that the two quantified statements are equivalent",
        ]
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, lines)
            got = _keys(d, len(lines))
            self.assertIn("example 9", got)
            self.assertIn("example 10", got)
            self.assertIn("Determine", got["example 9"]["text"])

    def test_glued_single_letter_tail_with_continuation_trimmed(self):
        lines = ["EXAMPLE 9Translate the statement into English"]
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, lines)
            got = _keys(d, len(lines))
            self.assertIn("example 9", got)
            self.assertIn("Translate", got["example 9"]["text"])

    def test_subpart_marker_after_number_kept(self):
        # printed "EXAMPLE 7" whose sub-question marker glued onto the number:
        # "EXAMPLE 7a) How many cards must be selected …" — the lowercase 'a'
        # is a part marker, not a prose connective.
        lines = [
            "EXAMPLE 7a) How many cards must be selected from a standard deck of 52 cards to guarantee",
            "EXAMPLE 8 What is the least number of area codes needed to guarantee the plan",
        ]
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, lines)
            got = _keys(d, len(lines))
            self.assertIn("example 7", got)
            self.assertIn("example 8", got)
            self.assertIn("How many cards", got["example 7"]["text"])

    def test_prose_lowercase_connective_still_rejected(self):
        lines = [
            "Definition 15 is ambiguous in this context so we refine it below",
            "Example 3 shows that the converse of Theorem 2 fails badly here",
        ]
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, lines)
            got = _keys(d, len(lines))
            self.assertNotIn("definition 15", got)
            self.assertNotIn("example 3", got)

    def test_ocr_digit_letter_tail_before_space_unchanged(self):
        # "1o" == 10: single trailing confusable letter + whitespace => keep
        lines = ["EXAMPLE 1o  The n-Queens Problem asks for a placement of n queens"]
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, lines)
            got = _keys(d, len(lines))
            self.assertIn("example 10", got)

    def test_merged_label_number_unchanged(self):
        lines = ["EXAMPLE3 Show the equivalence"]
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, lines)
            self.assertIn("example 3", _keys(d, len(lines)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
