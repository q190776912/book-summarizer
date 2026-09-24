"""EXER_HEADING latch must not fire on lowercase prose fragments (2026-09-24 Rising Sea incident).

Root cause: OCR splits a sentence so "exercise." sits alone on a line
("…prove this as an / exercise.", Vakil p293).  EXER_HEADING is IGNORECASE and
line-anchored, so the prose fragment latched the exercise region: real items
(10.3.1 Definition — the definition of proper morphisms!) were re-keyed as
numeric EXER rows and lettered exercise heads 10.3.A collapsed to bare "10.3"
(57 corrupted nodes across ch5/10/15/20/30).

Fix under test: a genuine exercises heading is never an all-lowercase word —
`scan()` skips the latch when the matched line is lowercase, while real
headings ("EXERCISES", "Exercises", "EXERCISES FOR CHAPTER 3") still latch.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_exer_latch_prose.py
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
_spec = importlib.util.spec_from_file_location(
    "scan_skeleton",
    os.path.join(_ROOT, "flows", "write-source", "structure", "script", "scan_skeleton.py"))
ss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ss)


def _pages(lines):
    # One text block per line — matches real PP-OCR page JSONs (block ≈ line).
    d = tempfile.mkdtemp()
    blocks = [{"text": ln, "poly": [0, 500, 1200, 520, 0, 0, 0, 0]} for ln in lines]
    with open(os.path.join(d, "page_001.json"), "w", encoding="utf-8") as fh:
        json.dump({"text": blocks}, fh)
    return d


def _scan(lines, mode="three-level", depths=(1, 2)):
    return ss.scan(_pages(lines), 1, 1, 1, mode, section_depths=list(depths))


class TestExerLatchProse(unittest.TestCase):
    def test_lowercase_prose_fragment_does_not_latch(self):
        rows = _scan([
            "1.1 Proper morphisms",
            "You are welcome to prove this as an",
            "exercise.",
            "1.1.1. Definition. A morphism is proper.",
            "1.1.A. EASY EXERCISE. Show that A1 is not proper.",
        ])
        kinds = {r[2]: r[1] for r in rows}
        self.assertEqual(kinds.get("1.1.1"), "ITEM")   # not swallowed as EXER
        self.assertEqual(kinds.get("1.1.A"), "EXER")   # lettered head intact
        self.assertNotIn("1.1", [r[2] for r in rows if r[1] == "EXER"])

    def test_lowercase_prose_in_two_level_does_not_latch(self):
        rows = _scan([
            "See the previous",
            "exercises.",
            "1.3. Show that the sum converges.",
        ], mode="two-level")
        kinds = {r[2]: r[1] for r in rows}
        self.assertEqual(kinds.get("1.3"), "ITEM")

    def test_real_headings_still_latch(self):
        for heading in ("EXERCISES", "EXERCISES.", "Exercises", "EXERCISESFORCHAPTER1"):
            rows = _scan([
                heading,
                "1.1.1. Find the general solution.",
            ])
            got = [(r[1], r[2]) for r in rows if r[2] == "1.1.1"]
            self.assertEqual(got, [("EXER", "1.1.1")], f"heading {heading!r} must latch")


if __name__ == "__main__":
    unittest.main(verbosity=2)
