# -*- coding: utf-8 -*-
"""Regression: number/title block-split section heads recovered by
scan_skeleton._merge_bare_num_head (Rosen 8e, 2026-09-25).

OCR split ~15 real heads into two adjacent blocks ("9.6.1" + "Introduction",
"8.4.4" + "Using Generating Functions to Solve", "9.2" + "n-ary Relations…").
The merge pass joins the bare-number line with a title-looking NEXT block and
re-runs full validation; table rows ("3.88 Adams", "0.0817 N", math
continuations "2.3 n(n + 1)") must NOT produce fake sections.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_merge_bare_num_head.py
"""
import importlib.util
import os
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, _ROOT)
import lib.boot as _boot
_boot.setup()

spec = importlib.util.spec_from_file_location(
    "scan_skeleton_merge",
    os.path.join(_ROOT, "flows/write-source/structure/script/scan_skeleton.py"))
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)


def _blk(text, x=100, y=100):
    return {"text": text, "poly": [x, y, x + 300, y, x + 300, y + 40, x, y + 40]}


class TestMergeBareNumHead(unittest.TestCase):
    def _merged_ok(self, num, title, dy=0, dx=10):
        blocks = [_blk(num, 100, 500), _blk(title, 110, 500 + dy)]
        got = ss._merge_bare_num_head(num, 0, blocks)
        self.assertEqual(got, f"{num} {title}", f"dy={dy} dx={dx}")

    def test_same_line_split_merged(self):
        self._merged_ok("9.6.1", "Introduction")

    def test_stacked_split_merged(self):
        self._merged_ok("9.2", "n-ary Relations and Their Applications", dy=60)

    def test_title_with_digits_or_math_not_merged(self):
        for num, title in (("3.88", "Adams 651"), ("9.8.7", "C(9, 6) = C(9, 3)"),
                           ("2.3", "n(n + 1)"), ("7.6", "C(3 + 5 - 1,5)"),
                           ("27.350", "T' := T(n - 2)")):
            blocks = [_blk(num), _blk(title)]
            self.assertIsNone(ss._merge_bare_num_head(num, 0, blocks),
                              f"{num}+{title}")

    def test_lowercase_or_punct_led_next_not_merged(self):
        blocks = [_blk("6.6"), _blk("the following set is countable")]
        got = ss._merge_bare_num_head("6.6", 0, blocks)
        # merge may fire (lowercase lead is decided by the validator), but the
        # function-word first token must veto the section:
        if got is not None:
            self.assertIsNone(ss._section_header_info(got, ch=6, depths={2}))
        blocks = [_blk("2.3"), _blk("(n - 1)n")]
        self.assertIsNone(ss._merge_bare_num_head("2.3", 0, blocks))

    def test_far_away_next_not_merged(self):
        blocks = [_blk("9.2", 100, 200), _blk("Introduction", 100, 900)]
        self.assertIsNone(ss._merge_bare_num_head("9.2", 0, blocks))

    def test_left_side_next_not_merged(self):
        blocks = [_blk("0.0817", 400, 300), _blk("N", 100, 300)]
        self.assertIsNone(ss._merge_bare_num_head("0.0817", 0, blocks))

    def test_non_bare_number_line_not_merged(self):
        blocks = [_blk("9.6.1 Introduction"), _blk("A paragraph")]
        self.assertIsNone(ss._merge_bare_num_head("9.6.1 Introduction", 0, blocks))

    def test_single_letter_junk_next_still_rejected_by_validator(self):
        # even if geometry merged, the validator veto kills "… N"
        blocks = [_blk("9.2"), _blk("N")]
        got = ss._merge_bare_num_head("9.2", 0, blocks)
        if got is not None:
            self.assertIsNone(ss._section_header_info(got, ch=9, depths={2}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
