# -*- coding: utf-8 -*-
"""Regression: Title-Case 「Proof …」 section headings must survive the
sentence-start veto (Rosen《Discrete Mathematics》8e, 2026-09-25).

Root cause: `_SEC_TITLE_SENTENCE_STARTS` carried `Proof\b(?! of\b)` (tuned for
Rising Sea), so Rosen's real subsection heads
  "1.7.6  Proof by Contraposition" / "1.8.5 Proof Strategies" /
  "1.8.7 Proof Strategy in Action"
were killed and the whole subsections vanished from the skeleton.

Fix under test (scan_skeleton._proof_title_is_prose): reject a Proof-led title
only when NO capitalized non-stopword follows the stem — prose stubs
("Proof." / "Proof by induction is …" / "Proof: see above") stay rejected,
Rising Sea's `Proof of Krull's …` carve-out is a special case (unchanged).

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_proof_title_heads.py
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
    "scan_skeleton_proof",
    os.path.join(_ROOT, "flows/write-source/structure/script/scan_skeleton.py"))
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)


class TestProofTitleHeads(unittest.TestCase):
    def test_rosen_title_case_proof_heads_accepted(self):
        for ln, num in (
            ("1.7.6  Proof by Contraposition", "1.7.6"),
            ("1.8.5 Proof Strategies", "1.8.5"),
            ("1.8.7 Proof Strategy in Action", "1.8.7"),
            ("1.7.7 Proofs by Contradiction", "1.7.7"),
        ):
            got = ss._section_header_info(ln, ch=1, depths={3})
            self.assertIsNotNone(got, ln)
            self.assertEqual(got[0], num)

    def test_prose_proof_stubs_still_rejected(self):
        for ln in (
            "7.2 Proof by induction is the standard trick here",
            "7.2 Proof.",
            "7.2 Proof: see above",
            "7.2 Proof by contradiction shows the claim",
        ):
            self.assertIsNone(ss._section_header_info(ln, ch=7, depths={2}), ln)

    def test_rising_sea_proof_of_carve_out_unchanged(self):
        got = ss._section_header_info(
            "11.5 Proof of Krull Principal Ideal and Height Theorems",
            ch=11, depths={2})
        self.assertIsNotNone(got)
        self.assertEqual(got[0], "11.5")


if __name__ == "__main__":
    unittest.main(verbosity=2)
