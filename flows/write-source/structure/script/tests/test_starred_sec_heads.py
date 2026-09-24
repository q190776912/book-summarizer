"""Starred section heads lost from the skeleton (2026-09-24 Rising Sea round 3).

Root causes:
  * Printed `12.7 ⋆Valuative criteria…` / `11.5 ⋆⋆Proof of Krull's …` — OCR
    reads the star as '+' between number and title. The universal detector
    rejected the line (`rest[0]` = '+', not alnum) so §12.7/12.8/12.9/11.5/29.8
    never produced SEC rows; build_structure then swallowed their items into
    the previous section and D-layer backfill could only add EMPTY shells.
  * Even undecorated, `_SEC_TITLE_SENTENCE_STARTS` vetoed the word 'Proof',
    killing the genuinely-named sections "Proof of Krull's Principal Ideal and
    Height Theorems" (§11.5) and "Proof of the Theorem on Formal Functions"
    (§29.8).

Fixes under test (scan_skeleton._section_header_info):
  * leading decoration run `[⋆★☆*+×✦ space]` stripped before title validation
    (lowercase-after-decoration still rejected);
  * 'Proof' veto narrowed: prose starts ("Proof." / "Proof by induction")
    still rejected, `Proof of <name>` accepted;
  * greedy SEP capture across a '+' decoration cannot corrupt the number
    ("11.5 + + …" validates as 11.5).

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_starred_sec_heads.py
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
    _ROOT = str(Path(__file__).resolve().parents[3])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import importlib.util


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(_ROOT, *rel.split('/')))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ss = _load("flows/write-source/structure/script/scan_skeleton.py",
           "scan_skeleton")


class TestDecorationStripping(unittest.TestCase):
    def test_plus_star_heads_accepted(self):
        got = ss._section_header_info(
            "12.7 + Valuative criteria for separatedness and properness",
            ch=12, depths={2})
        self.assertIsNotNone(got)
        self.assertEqual(got[0], "12.7")
        self.assertEqual(got[2],
                         "Valuative criteria for separatedness and properness")

    def test_double_plus_proof_of_accepted(self):
        for ln, num in (
            ("11.5 + + Proof of Krull Principal Ideal and Height Theorems", "11.5"),
            ("29.8 ++ Proof of the Theorem on Formal Functions 29.4.2", "29.8"),
            ("11.5 xx Proof of Krull's Principal Ideal and Height Theorems", "11.5"),
            ("29.8 ⋆⋆Proof of the Theorem on Formal Functions", "29.8"),
        ):
            got = ss._section_header_info(ln, ch=int(num.split('.')[0]),
                                          depths={2})
            self.assertIsNotNone(got, ln)
            self.assertEqual(got[0], num)

    def test_lowercase_after_decoration_still_rejected(self):
        self.assertIsNone(ss._section_header_info(
            "12.7 + valuative criteria for separatedness and prop",
            ch=12, depths={2}))

    def test_empty_after_decoration_rejected(self):
        self.assertIsNone(ss._section_header_info("12.7 + .", ch=12,
                                                  depths={2}))

    def test_long_colon_tailed_real_title_accepted(self):
        # printed verbatim: "5.5 The crucial points of a scheme that control
        # everything:" — the punctuation-tail veto must only bite short
        # prose fragments (Casella "1.5.3. First,").
        got = ss._section_header_info(
            "5.5 The crucial points of a scheme that control everything:",
            ch=5, depths={2})
        self.assertIsNotNone(got)
        self.assertEqual(got[0], "5.5")

    def test_short_colon_tailed_fragment_still_rejected(self):
        self.assertIsNone(ss._section_header_info("1.5.3 First,", ch=1,
                                                  depths={3}))

    def test_bracket_titled_head_accepted(self):
        # printed: "18.1 (Desired) properties of cohomology"
        got = ss._section_header_info(
            "18.1 (Desired) properties of cohomology", ch=18, depths={2})
        self.assertIsNotNone(got)
        self.assertEqual(got[0], "18.1")

    def test_lowercase_parenthetical_prose_rejected(self):
        self.assertIsNone(ss._section_header_info(
            "5.3 (see the discussion in Chapter 2) holds too", ch=5,
            depths={2}))


class TestProofVetoNarrowed(unittest.TestCase):
    def test_prose_proof_starts_rejected(self):
        for ln in (
            "7.2 Proof by induction is the standard trick here",
            "7.2 Show that the composition of proper maps is proper",
        ):
            self.assertIsNone(ss._section_header_info(ln, ch=7, depths={2}),
                              ln)

    def test_proof_of_name_accepted(self):
        got = ss._section_header_info(
            "11.5 Proof of Krull Principal Ideal and Height Theorems",
            ch=11, depths={2})
        self.assertIsNotNone(got)


class TestScanEndToEnd(unittest.TestCase):
    def test_starred_sections_produce_sec_rows_with_titles(self):
        lines = [
            "12.7 + Valuative criteria for separatedness and properness",
            "12.7.1. Theorem (Valuative criterion). — Suppose X is a scheme",
            "12.7.A. EXERCISE (THE EASY DIRECTION). Prove the claim.",
            "12.8 + More sophisticated facts about regular local rings",
            "12.8.3. Theorem. — If X is a finite type scheme over a field",
            "12.9 + Filtered rings and modules, and the Artin-Rees Lemma",
            "12.9.2. Proposition. — If A is Noetherian, M is finitely generated",
        ]
        d = tempfile.mkdtemp()
        blocks = [{"text": ln, "poly": [0, 500, 1200, 520, 0, 0, 0, 0]}
                  for ln in lines]
        with open(os.path.join(d, "page_001.json"), "w", encoding="utf-8") as fh:
            json.dump({"text": blocks}, fh)
        rows = ss.scan(d, 12, 1, 1, 'three-level', section_depths=[1, 2])
        secs = {r[2]: r[3] for r in rows if r[1] == 'SEC'}
        self.assertEqual(sorted(secs), ['12.7', '12.8', '12.9'])
        self.assertTrue(secs['12.7'].startswith('Valuative'))
        self.assertTrue(secs['12.8'].startswith('More sophisticated'))
        self.assertTrue(secs['12.9'].startswith('Filtered'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
