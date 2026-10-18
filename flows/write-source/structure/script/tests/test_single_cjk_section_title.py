# -*- coding: utf-8 -*-
"""Regression: a section candidate whose printed "title" is a SINGLE lone CJK
ideograph is OCR debris, never a real section heading.

Print (Rice《Mathematical Statistics and Data Analysis》3e, ch2 "Random
Variables", p70, 2026-10-17 实测):

    Figure 2.11 (gamma densities) carries a y-axis tick labelled "2.5".  PaddleOCR
    glued the tick into one text row together with a stray neighbouring fragment:

        2.5上

The generic section detector matched the number ``2.5`` and — because the short-title
guard deliberately EXEMPTS any title containing CJK (to protect genuine 2-3 character
Chinese titles such as 孙文祥 "熵映射"/"平衡态") — let the one-character "title" ``上``
slip through.  §2.5 was therefore anchored at the figure page p70, which sits BEFORE
the real §2.4 ("Concluding Remarks", p81) and the real §2.5 ("Problems", p81):
ANCHOR-SANITY "小节号晚而页码早" rejected the whole chapter.

Fix under test: reject a title that is exactly one CJK ideograph.  Real Chinese
section titles are always >= 2 characters.  Legit multi-char CJK titles and ASCII
headings must be unaffected; single-latin junk ("3.2A") was already rejected.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_single_cjk_section_title.py
"""
import json
import os
import sys
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

from scan_skeleton import _section_header_info  # noqa: E402


class TestSingleCjkTitleVeto(unittest.TestCase):
    def test_lone_cjk_char_axis_debris_rejected(self):
        self.assertIsNone(_section_header_info("2.5上", ch=2, depths={2, 3, 4}))

    def test_real_ascii_headings_unaffected(self):
        self.assertEqual(
            _section_header_info("2.5 Problems", ch=2, depths={2, 3, 4}),
            ("2.5", 2, "Problems"))
        self.assertIsNotNone(
            _section_header_info("2.4 Concluding Remarks", ch=2, depths={2, 3, 4}))

    def test_multi_char_cjk_title_still_kept(self):
        # 孙文祥《遍历论》真节题——含汉字的 2-3 字标题必须保留。
        self.assertIsNotNone(_section_header_info("2.3熵映射", depths={2, 3, 4}))
        self.assertIsNotNone(_section_header_info("1.5平衡态", depths={2, 3, 4}))

    def test_single_latin_junk_still_rejected(self):
        # 旧短标题守卫已拦的拉丁单/双字母图示残粒，行为不变。
        self.assertIsNone(_section_header_info("3.2A", depths={2, 3, 4}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
