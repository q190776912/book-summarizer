# -*- coding: utf-8 -*-
"""Regression: punctuation-tail guard vs semicolon-ended section heads
(do Carmo《Differential Geometry of Curves and Surfaces》, 2026-09-26).

The book prints long section titles across two lines and ends the first line
with a semicolon ("2-2. Regular Surfaces;" + "and Differentiable Structures").
The 2026-09 trailing-punctuation guard (short fragment < 40 chars ending in
", ; :") vetoed all six real heads (2-2/2-3/2-4/4-7/5-6/5-10) -> whole sections
vanished from the skeleton and their items were misfiled into neighbouring
sections by page proximity.

Fix: exempt a trailing ';' when the title is >= 2 words and every word starts
non-lowercase (Title-Case noun phrase).  Prose fragments keep failing:
- "1.5.3. First,"          single short word, comma        -> still rejected
- "2-2. and Differentiable" leading lowercase word          -> still rejected
- "5-6. Covering Spaces;"  Title-Case 2 words               -> now accepted

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_semicolon_sec_heads.py
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
    "scan_skeleton_sc",
    os.path.join(_ROOT, "flows/write-source/structure/script/scan_skeleton.py"))
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)


def _info(ln, ch=None):
    return ss._section_header_info(ln, ch=ch, depths={2})


class TestSemicolonHeadsAccepted(unittest.TestCase):
    """do Carmo's six semicolon-ended heads must produce SEC rows."""

    def test_regular_surfaces(self):
        self.assertIsNotNone(_info("2-2. Regular Surfaces;", ch=2))

    def test_change_of_parameters(self):
        self.assertIsNotNone(_info("2-3. Change of Parameters;", ch=2))

    def test_tangent_plane(self):
        self.assertIsNotNone(_info("2-4. The Tangent Plane;", ch=2))

    def test_further_properties_geodesics(self):
        self.assertIsNotNone(
            _info("4-7. Further Properties of Geodesics;", ch=4))

    def test_covering_spaces(self):
        self.assertIsNotNone(_info("5-6. Covering Spaces;", ch=5))

    def test_abstract_surfaces(self):
        self.assertIsNotNone(_info("5-10. Abstract Surfaces;", ch=5))


class TestProseFragmentsStillRejected(unittest.TestCase):
    """The exemption must not widen the hole the guard was built for."""

    def test_comma_fragment_single_word(self):
        self.assertIsNone(_info("1.5.3. First,", ch=1))

    def test_semicolon_lowercase_continuation(self):
        # continuation line of a split title is lowercase-led -> no exemption
        self.assertIsNone(_info("2-2. and Differentiable Structures;", ch=2))

    def test_semicolon_prose_with_function_words(self):
        self.assertIsNone(_info("2-5. In the following we shall;", ch=2))

    def test_semicolon_single_word(self):
        self.assertIsNone(_info("3-1. Areas;", ch=3))

    def test_colon_short_still_rejected(self):
        self.assertIsNone(_info("2-2. See also:", ch=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
