"""Vakil lettered-exercise OCR glyph garbles must not corrupt the contract
(2026-09-24 Rising Sea incident).

Root causes:
  * OCR reads letter exercise heads "C.S.O" / "C.S.I" as digits 0/1 (58 heads
    book-wide). The digit form then either (a) enters the ITEM contract as a
    fake numeric item (5.5-0) later typed as an exercise, or (b) collides with
    the real item "C.S.1" and is silently dropped (10.1.I content loss).
  * Page-split prose leaves phantom exercise heads ("4.5.L. If you prefer
    that, by all means do so.)" / bare "8.2.F." closing a reference
    "…in Exercises 8.2.A and 8.2.F.") that duplicate a real letter.
  * Decorative item titles starting with "Exercise <ref>" (24.5.11
    "Exercise 24.5.M can be improved:") get an exercise label and are routed
    out of the ITEM contract by build_structure 3a — the numbered item
    vanishes.

Fixes under test (SSOT `lib.numbering.is_exercise_head_text`):
  * scan_skeleton: digit-0/1 head + exercise-HEAD form → lettered EXER row
    (O / I); lettered head WITHOUT keyword that is empty or ")"-terminated →
    dropped; everything else untouched (1360/1362 real heads carry the keyword).
  * extract_items_vakil: skips garbled exercise heads; blanks decorative
    "Exercise <ref>" labels so the item stays uncat.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_vakil_exer_heads.py
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

import importlib.util


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(_ROOT, *rel.split('/')))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ss = _load("flows/write-source/structure/script/scan_skeleton.py", "scan_skeleton")
ev = _load("flows/write-source/structure/script/extract_items_vakil.py",
           "extract_items_vakil")
from lib.numbering import is_exercise_head_text, has_exercise_word


def _dir(lines):
    d = tempfile.mkdtemp()
    blocks = [{"text": ln, "poly": [0, 500, 1200, 520, 0, 0, 0, 0]} for ln in lines]
    with open(os.path.join(d, "page_001.json"), "w", encoding="utf-8") as fh:
        json.dump({"text": blocks}, fh)
    return d


LINES = [
    "5.5 Proper morphisms",
    "5.5.1. Definition. A morphism is proper.",
    "5.5.A. UNIMPORTANT EXERCISE. trivial one.",
    "5.5.0. ExERCISE. Show that those subsets of Spec A are supports.",
    "5.5.II. not a thing",
    "10.1.1. ExERCISE.  Prove that the condition of being quasiseparated is local.",
    "4.5.L. If you prefer that, by all means do so.)",
    "8.2.F.",
    "24.5.11. Exercise 24.5.M can be improved:",
    "3.4.7. Exercise 3.5.B shows this.",
]


def _rows(ch):
    return {(r[1], r[2]): r for r in
            ss.scan(_dir(LINES), ch, 1, 1, 'three-level', section_depths=[1, 2])}


class TestVakilExerHeads(unittest.TestCase):
    def test_predicate(self):
        self.assertTrue(is_exercise_head_text("ExERCISE. Show that"))
        self.assertTrue(is_exercise_head_text("EASY EXERCISE (GENERIC FLATNESS). Suppose"))
        self.assertTrue(is_exercise_head_text("EXERCISE (CF. EXERCISE 3.5.B). Fix"))
        self.assertTrue(is_exercise_head_text("EXERCISE: EPk-P gives"))
        self.assertTrue(is_exercise_head_text("ExERCISE/DEFINITION. Suppose"))
        self.assertTrue(is_exercise_head_text("EXERCISE."))
        self.assertFalse(is_exercise_head_text("Exercise 24.5.M can be improved:"))
        self.assertFalse(is_exercise_head_text("Definition. A morphism"))
        self.assertFalse(is_exercise_head_text("Motivation. Let's review"))
        self.assertTrue(has_exercise_word("EASY ExERCISE. Show"))
        self.assertFalse(has_exercise_word("If you prefer that"))

    def test_scan_garble_and_phantoms(self):
        r5 = _rows(5)
        self.assertIn(('EXER', '5.5.O'), r5)          # O-garble recovered
        self.assertNotIn(('ITEM', '5.5-0'), r5)
        self.assertIn(('ITEM', '5.5.1'), r5)          # real item untouched
        self.assertIn(('EXER', '5.5.A'), r5)
        r10 = _rows(10)
        self.assertIn(('EXER', '10.1.I'), r10)         # I-garble recovered
        self.assertNotIn(('ITEM', '10.1.1'), r10)
        r4 = _rows(4)
        self.assertNotIn(('EXER', '4.5.L'), r4)        # paren-terminated prose phantom
        r8 = _rows(8)
        self.assertNotIn(('EXER', '8.2.F'), r8)        # empty-text reference phantom
        r24 = _rows(24)
        self.assertIn(('ITEM', '24.5.11'), r24)        # decorative Exercise title = item
        self.assertNotIn(('EXER', '24.5.11'), r24)

    def test_extractor_skips_garbles_and_blanks_ref_labels(self):
        d = _dir(LINES)
        for ch in (5, 10, 24):
            items, _, _ = ev.extract_items_vakil(d, ch, 1, 1)
            keys = {it['key']: it for it in items}
            self.assertNotIn('5.5-0', keys)
            if ch == 5:
                self.assertIn('5.5-1', keys)
            if ch == 10:
                self.assertNotIn('10.1-1', keys)      # I-garble not an item
            if ch == 24:
                self.assertIn('24.5-11', keys)         # real item kept…
                self.assertEqual(keys['24.5-11']['label'], '')  # …exercise label blanked


if __name__ == "__main__":
    unittest.main(verbosity=2)
