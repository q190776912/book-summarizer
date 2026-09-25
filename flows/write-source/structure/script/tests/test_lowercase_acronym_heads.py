# -*- coding: utf-8 -*-
"""Regression: technical-term / acronym section heads must survive the
lowercase-first + short-title vetoes (Rosen《Discrete Mathematics》8e,
2026-09-25).

Root cause: three real heads were killed by scan_skeleton._validate —
  * "9.2 n-ary Relations and Their Applications" (parent §9.2 + its restart
    window vanished; orphaned 9.2.x hoisted to chapter level),
  * "9.2.2 n-ary Relations" and "4.3.8 gcds as Linear Combinations"
    (lowercase first word = technical noun, not prose),
  * "9.2.5 SQL" (3-letter acronym hit the <4-char junk veto).

Fixes under test:
  * acronym exemption: rest is exactly 3 uppercase letters (+ optional
    punctuation) -> accepted; 'A'/'B' junk unchanged;
  * technical-first-word exemption: lowercase head word NOT in the function
    word list AND a Title-Case continuation word later -> accepted;
    "and it is stated…" / "and W911NF…" / all-lowercase prose rejected;
  * Brin & Stuck 'e-Orbits' hyphen form unaffected.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_lowercase_acronym_heads.py
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
    "scan_skeleton_lc",
    os.path.join(_ROOT, "flows/write-source/structure/script/scan_skeleton.py"))
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)


class TestTechnicalHeads(unittest.TestCase):
    def test_lowercase_technical_first_word_accepted(self):
        for ln, num in (
            ("9.2 n-ary Relations", "9.2"),
            ("9.2 n-ary Relations and Their Applications 611", "9.2"),
            ("9.2.2 n-ary Relations", "9.2.2"),
            ("4.3.8 gcds as Linear Combinations", "4.3.8"),
        ):
            ch = int(num.split(".")[0])
            got = ss._section_header_info(ln, ch=ch,
                                          depths={2 if ln.count('.') == 1 else 3})
            self.assertIsNotNone(got, ln)
            self.assertEqual(got[0], num)

    def test_prose_lowercase_continuations_rejected(self):
        for ln, ch in (
            ("20.6 and it is stated that", 20),
            ("14-1-0359 and W911NF research", 14),
            ("12.7 + valuative criteria for separatedness and prop", 12),
            ("9.2 a note on history", 9),
        ):
            self.assertIsNone(ss._section_header_info(ln, ch=ch,
                                                      depths={2, 3}), ln)

    def test_hyphen_symbol_head_still_accepted(self):
        got = ss._section_header_info("5.3 e-Orbits", ch=5, depths={2})
        self.assertIsNotNone(got)


class TestAcronymHeads(unittest.TestCase):
    def test_three_letter_acronym_accepted(self):
        got = ss._section_header_info("9.2.5 SQL", ch=9, depths={3})
        self.assertIsNotNone(got)
        self.assertEqual(got[0], "9.2.5")

    def test_single_letter_junk_still_rejected(self):
        self.assertIsNone(ss._section_header_info("5-6.A A", ch=5, depths={2}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
