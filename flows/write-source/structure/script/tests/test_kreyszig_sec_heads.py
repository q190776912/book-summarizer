# -*- coding: utf-8 -*-
"""Regression: universal section detector vs Kreyszig 2e section heads
(2026-09-26).

Two complementary defects in `scan_skeleton._section_header_info._validate`:

1) FALSE REJECT — Kreyszig prints section titles as two noun phrases joined
   by an internal period ("1.5 Examples. Completeness Proofs", "2.2 Normed
   Space. Banach Space", "11.2 Momentum Operator. Heisenberg Uncertainty
   Principle"). The blanket mid-sentence guard `[.;；]\\s+[A-Z]` killed 5 real
   heads (1.5/2.2/2.10/3.1/11.2) -> whole sections vanished from the skeleton.
   Now the guard only fires when prose markers co-occur (>=3 consecutive
   lowercase words, or length > 56).

2) FALSE ACCEPT — chapter-opener numbered prose ("1.6. Another concept of
   theoretical and practical interest is separability", "8.4. The
   Riesz-Schauder theory is based on Secs. 8.3 and 8.4, and the") matched the
   detector and anchored §N.M to the preamble page ahead of the real head
   (section-ORDER blocking + real head suppressed by first-hit dedup).
   Lowercase copula verbs (is/are/was/were/been/being) now veto any section
   title — Title-Case headings never carry a lowercase copula.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_kreyszig_sec_heads.py
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
    "scan_skeleton_kz",
    os.path.join(_ROOT, "flows/write-source/structure/script/scan_skeleton.py"))
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)


def _info(ln, ch=None):
    return ss._section_header_info(ln, ch=ch, depths={2})


class TestRealHeadsAccepted(unittest.TestCase):
    """Kreyszig internal-period titles must produce SEC rows (were killed)."""

    def test_examples_completeness_proofs(self):
        self.assertIsNotNone(_info("1.5 Examples. Completeness Proofs", ch=1))

    def test_normed_space_banach_space(self):
        self.assertIsNotNone(_info("2.2 Normed Space. Banach Space", ch=2))

    def test_normed_spaces_of_operators_dual(self):
        self.assertIsNotNone(
            _info("2.10 Normed Spaces of Operators. Dual Space", ch=2))

    def test_inner_product_hilbert(self):
        self.assertIsNotNone(
            _info("3.1 Inner Product Space. Hilbert Space", ch=3))

    def test_momentum_head_long_title(self):
        # 52 chars, every word Title-Case, no copula -> real head (was killed)
        self.assertIsNotNone(
            _info("11.2 Momentum Operator. Heisenberg Uncertainty Principle",
                  ch=11))


class TestProsePhantomsRejected(unittest.TestCase):
    """Numbered preamble sentences must NOT anchor a section."""

    def test_ch1_preamble_is_separability(self):
        self.assertIsNone(_info(
            "1.6. Another concept of theoretical and practical interest "
            "is separability", ch=1))

    def test_ch8_preamble_riesz_schauder(self):
        self.assertIsNone(_info(
            "8.4. The Riesz-Schauder theory is based on Secs. 8.3 and "
            "8.4, and the", ch=8))

    def test_mid_sentence_prose_still_rejected(self):
        # original negative case: lowercase run "built up the kernel of"
        self.assertIsNone(_info(
            "8.3.21 The UIT built up the kernel of T. This shows", ch=8))

    def test_long_mid_sentence_line_rejected(self):
        self.assertIsNone(_info(
            "2.5 Summary of the Main Results Obtained in This Chapter. "
            "Further Details Are Deferred to Appendix", ch=2))


class TestNoRegressionsOnPlainTitles(unittest.TestCase):
    def test_plain_title_case_heads_still_ok(self):
        for ln, ch in (("1.1 Metric Space", 1),
                       ("9.10 Extension of the Spectral Theorem to", 9),
                       ("7.3 Spectral Properties of Bounded", 7)):
            self.assertIsNotNone(_info(ln, ch=ch), ln)

    def test_capitalized_copula_title_not_vetoed(self):
        # Title-Case "Is" must not trip the lowercase-copula veto
        self.assertIsNotNone(_info("4.9 What Is a Compact Operator", ch=4))

    def test_chapter_filter_intact(self):
        self.assertIsNone(_info("1.1 Metric Space", ch=2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
