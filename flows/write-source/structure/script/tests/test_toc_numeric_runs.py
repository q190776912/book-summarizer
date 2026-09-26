# -*- coding: utf-8 -*-
"""Regression: chapter-TOC numeric run must not anchor a section head
(do Carmo《Differential Geometry of Curves and Surfaces》ch5 实测 2026-09-26).

Page 325 opens chapter 5 with a dependency/TOC line OCR-merged into one row,
"5-2 5-3 5-4 5-5 5-6,A5-6,B 5-7 5-8 5-9 5-10 5-11". The universal detector
captured num "5-2" and treated the remaining numeric run as its "title",
anchoring §5-2 to the TOC page (real head "5-2. The Rigidity of the Sphere"
was then suppressed by first-hit dedup). New guard in
`scan_skeleton._section_header_info._validate`: reject when the rest starts
with a section-number token AND the line carries >= 3 such bare tokens.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_toc_numeric_runs.py
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
    "scan_skeleton_toc",
    os.path.join(_ROOT, "flows/write-source/structure/script/scan_skeleton.py"))
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)


def _info(ln, ch=None):
    return ss._section_header_info(ln, ch=ch, depths={2})


class TestTocNumericRunsRejected(unittest.TestCase):
    def test_do_carmo_ch5_toc_line(self):
        self.assertIsNone(_info(
            "5-2 5-3 5-4 5-5 5-6,A5-6,B 5-7 5-8 5-9 5-10 5-11", ch=5))

    def test_dot_separated_toc_run(self):
        self.assertIsNone(_info("2.1 2.2 2.3 2.4 2.5", ch=2))

    def test_secs_cross_reference_still_rejected(self):
        self.assertIsNone(_info(
            "8.4. The Riesz-Schauder theory is based on Secs. 8.3 and 8.4,"
            " and the", ch=8))


class TestRealHeadsUntouched(unittest.TestCase):
    def test_real_5_2_head(self):
        self.assertIsNotNone(_info("5-2. The Rigidity of the Sphere", ch=5))

    def test_semicolon_title_heads_still_ok(self):
        for ln, ch in (("2-2. Regular Surfaces;", 2),
                       ("4-7. Further Properties of Geodesics;", 4),
                       ("5-10. Abstract Surfaces;", 5)):
            self.assertIsNotNone(_info(ln, ch=ch), ln)

    def test_plain_heads_still_ok(self):
        self.assertIsNotNone(_info("1-1 Introduction", 1))
        self.assertIsNotNone(_info("1.5 Examples. Completeness Proofs", 1))

    def test_title_with_one_trailing_number_ok(self):
        # a genuine title containing a single number token (< 3) is kept
        self.assertIsNotNone(_info("3.5 The Case n = 2 of Curves", 3))


if __name__ == "__main__":
    unittest.main(verbosity=2)
