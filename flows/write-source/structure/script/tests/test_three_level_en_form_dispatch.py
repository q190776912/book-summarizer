"""EN three-level dispatch must follow the PRINTED heading form
(Kreyszig incident, 2026-09-25).

Root cause: build_structure._extract_items routed ORDINAL_THREE_LEVEL +
language=en unconditionally to extract_items_en3, which requires LABEL-FIRST
heads ("Definition 1.1.1").  Kreyszig prints NUMBER-FIRST heads
("1.1-1 Definition (Metric space, metric).") — the whole book nearly vanished
from the contract (ch1: 3 items captured vs 50 candidates by the generic
three-level extractor, which explicitly supports "N.S-N Lemma" English heads).

Fix under test (build_structure._three_level_en_number_first + dispatch):
  * probe counts block-start heads of both forms per chapter; number-first
    wins only when nf >= 5 AND nf > lf -> generic extract_items path;
  * label-first books (Strogatz / Lasota) and mixed-noise pages keep the
    exact prior en3 behavior (nf < 5 or lf >= nf).

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_three_level_en_form_dispatch.py
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

import build_structure as bs


def _mk_pages(d, lines):
    """Write page_001..NNN.json whose single text block carries `lines`."""
    for i, ln in enumerate(lines, start=1):
        fp = os.path.join(d, f"page_{i:03d}.json")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"text": [{"text": ln}], "formulas": []}, f)


NF_HEADS = [
    "1.1-1 Definition (Metric space, metric). A metric space is a set X.",
    "1.1-2 Examples  Real line R.",
    "1.2-3 Definition (Space l). The set of all bounded sequences.",
    "1.3-4 Theorem (Banach space). The space l is complete.",
    "1.3-5 Lemma (Triangle inequality). We have d(x,y) <= d(x,z)+d(z,y).",
    "1.4-6 Corollary. Every convergent sequence is bounded.",
]
LF_HEADS = [
    "Definition 1.1.1 (Metric space). A metric space is a set X.",
    "Theorem 1.2.3 (Banach). The space is complete.",
    "Example 1.2.4  Real line R.",
    "Lemma 1.3.1 Triangle inequality.",
    "Corollary 1.3.2 Every convergent sequence is bounded.",
]


class TestProbe(unittest.TestCase):
    def test_number_first_detected(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, NF_HEADS)
            self.assertTrue(bs._three_level_en_number_first(d, 1, len(NF_HEADS)))

    def test_label_first_not_swallowed(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, LF_HEADS)
            self.assertFalse(bs._three_level_en_number_first(d, 1, len(LF_HEADS)))

    def test_minority_noise_keeps_en3(self):
        # 4 number-first refs (< threshold 5) must NOT flip the route.
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, NF_HEADS[:4] + LF_HEADS)
            self.assertFalse(bs._three_level_en_number_first(d, 1, 9))

    def test_tie_breaks_to_en3(self):
        # equal counts => conservative default (existing en3 behavior).
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, NF_HEADS + LF_HEADS[:6])
            self.assertFalse(bs._three_level_en_number_first(d, 1, 12))

    def test_inline_prose_refs_not_counted(self):
        # "…see 1.2-1 and…" mid-line / "we can obtain" after number: not a head.
        prose = [
            "1. Show that in 1.2-1 we can obtain another metric by replacing.",
            "It follows from 1.3-4 that the space is complete, see also 2.1-1.",
            "(1.1-1) Definition of metric is in section 1.1.",
        ]
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, prose)
            self.assertFalse(bs._three_level_en_number_first(d, 1, len(prose)))

    def test_missing_pages_no_crash(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(bs._three_level_en_number_first(d, 1, 5))


class TestDispatch(unittest.TestCase):
    class _Book:
        primary_type = bs.ORDINAL_THREE_LEVEL
        language = "en"
        chapter_first = True
        section_scoped = False
        gm_bare_numbered = False
        ordinal = []

    def test_number_first_routes_to_generic(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, NF_HEADS)
            items = bs._extract_items(d, 1, 1, len(NF_HEADS), self._Book())
            keys = {it["key"] for it in items}
            self.assertIn("1.1-1", keys)   # generic bare-numeric key
            self.assertIn("1.2-3", keys)
            # the en3 route captured nothing of these number-first heads
            self.assertEqual(bs.extract_items_en3(d, 1, 1, len(NF_HEADS)), [])

    def test_label_first_still_routes_to_en3(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, LF_HEADS)
            items = bs._extract_items(d, 1, 1, len(LF_HEADS), self._Book())
            keys = {it["key"] for it in items}
            self.assertIn("1.1-1", keys)
            self.assertIn("1.2-3", keys)
            self.assertIn("1.3-1", keys)


if __name__ == "__main__":
    unittest.main(verbosity=2)
