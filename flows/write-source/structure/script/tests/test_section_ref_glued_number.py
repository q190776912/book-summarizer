# -*- coding: utf-8 -*-
"""Regression: a two-level EN match whose captured number is immediately glued to a
DEEPER numeric segment (``SEP_TIGHT`` + digit, no space) is a cross-reference to a
sub-section number, never an entry heading.

Print (Rice《Mathematical Statistics and Data Analysis》3e, ch8 p301, 2026-10-17
实测): Rice labels its worked examples with LETTERS (Example A / B / C / D, restart
per chapter — prose-inheritance), and never prints a numeric example id.  OCR glued a
mid-sentence cross-reference "…in Example A of Section 8.5.1…" into one row:

    Example 8.5.1A.)

The two-level ``lab_re`` swallows only "8.5" and leaves ".1A.)" as the "title" — the
character right after the captured number is ``.`` glued to a digit ``1``.  The old
guards rejected ``.)`` / ``.]`` debris and closing-delimiter tails but not ``.digit``,
so a phantom numeric example node ``例8.5`` was minted (the ONLY structured item in the
whole 685-page book) — with a Chinese label and a wrong number bleeding into the unit.

Fix under test: reject a two-level match when ``txt[_mend:`` begins with a separator
immediately followed by a digit (a third numeric segment deeper than the scheme).
Genuine two-level headings ("Example 8.5 Queueing theory") have a space / "(" / sentence
period + title after the number, never a glued deeper digit, and must be kept.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_section_ref_glued_number.py
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

POLY = [149, 432, 1074, 432, 1074, 464, 149, 464]


def _blk(txt):
    return {"text": txt, "poly": list(POLY), "score": 0.98}


def _keys(pages, **kw):
    with tempfile.TemporaryDirectory() as d:
        for i, texts in enumerate(pages, start=1):
            with open(os.path.join(d, "page_%03d.json" % i), "w", encoding="utf-8") as f:
                json.dump({"text": texts, "formulas": []}, f)
        return {it["key"].lower() for it in extract_items_en(d, 1, len(pages), **kw)}


class TestSectionRefGluedNumberDropped(unittest.TestCase):
    def test_example_glued_deeper_segment_rejected(self):
        got = _keys([[_blk("Example 8.5.1A.)")]])
        self.assertNotIn("example 8.5", got)
        self.assertEqual(got, set())

    def test_theorem_glued_deeper_segment_rejected(self):
        # "Theorem 3.4.2" style section cross-ref in a two-level book.
        got = _keys([[_blk("Theorem 3.4.2 shows the claim")]])
        self.assertNotIn("theorem 3.4", got)

    def test_real_two_level_example_head_kept(self):
        # Genuine heading: number, then a space + Title-Case title.
        got = _keys([[_blk("Example 8.5 Queueing models of telephone traffic")]])
        self.assertIn("example 8.5", got)


if __name__ == "__main__":
    unittest.main(verbosity=2)
