# -*- coding: utf-8 -*-
"""Regression: same-parent subsection keys must ascend in contract order
(check_structure_completeness.subsection_order_problems; Rosen 8e ch2, 2026-09-25).

`build_structure` re-scans section anchors when a chapter opener prints a section
TOC. Rosen's TOC lists only §N.M, and the re-scan matched the bare word
"Introduction" belonging to §2.6.1 as §2.1.1's heading -> §2.1.1 anchored on
p211, the contract listed §2.1's children as 2.1.2 … 2.1.8, 2.1.1, §2.1's window
stretched to 144-211 and p211's content got attached to BOTH §2.1.1 and §2.6.1.

Nothing caught it: the D layer (section_continuity) only compares §N.M because the
contract has no subsection containers, and B/Q layers do not look at section
order. So the step-3 completeness gate now blocks on an inverted same-parent
subsection sequence — before any unit is split, i.e. while a rebuild is free.

Note the gate flags *inversions* only: a section whose first subsection is
unnumbered in the source (children start at .2) is legitimate and must pass.

Runs under stdlib unittest:
  python verify/tests/test_subsection_order_gate.py
"""
import os
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[1])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from check_structure_completeness import (  # noqa: E402
    subsection_order_problems, _sec_key_nums)


def _sec(key, page, kids=None):
    return {"key": key, "type": "section", "name": key, "page_start": page,
            "sub_sec": list(kids or [])}


def _ch(kids):
    return {"key": "2", "type": "chapter", "name": "ch2", "page_start": 144,
            "sub_sec": kids}


class TestSubsectionOrderGate(unittest.TestCase):
    def test_inverted_subsection_anchored_late_is_blocked(self):
        # Rosen ch2 shape: 2.1.1 last, anchored on 211 (after 2.1.8 on 154).
        ch = _ch([_sec("2.1", 144, [
            _sec("2.1.2", 147), _sec("2.1.3", 148), _sec("2.1.8", 154),
            _sec("2.1.1", 211),
        ])])
        probs = subsection_order_problems(ch)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("2.1.1", probs[0])
        self.assertIn("逆序", probs[0])

    def test_ascending_subsections_pass(self):
        ch = _ch([_sec("2.1", 144, [
            _sec("2.1.1", 144), _sec("2.1.2", 147), _sec("2.1.8", 154),
        ])])
        self.assertEqual(subsection_order_problems(ch), [])

    def test_first_subsection_unnumbered_passes(self):
        # Source starts subsections at .2 (the .1 head carries no printed number):
        # a gap is NOT an inversion, must not block.
        ch = _ch([_sec("2.5", 202, [_sec("2.5.2", 203), _sec("2.5.3", 206)])])
        self.assertEqual(subsection_order_problems(ch), [])

    def test_letter_and_descriptive_keys_skipped(self):
        ch = _ch([_sec("A", 10), _sec("B", 12), _sec("intro", 5)])
        self.assertEqual(subsection_order_problems(ch), [])
        self.assertIsNone(_sec_key_nums("A.2"))
        self.assertEqual(_sec_key_nums("2.1.3"), (2, 1, 3))

    def test_nested_chapters_scan_all_levels(self):
        # Deep inversion (chapter -> section -> subsection) is found by recursion.
        ch = _ch([_sec("2.2", 156, [
            _sec("2.2.3", 162), _sec("2.2.1", 170),
        ])])
        self.assertEqual(len(subsection_order_problems(ch)), 1)

    def test_item_children_do_not_count(self):
        # Entries (type=item) share the numbering namespace but are not sections.
        ch = _ch([_sec("2.1", 144, [
            {"key": "2.1.8", "type": "item", "name": "x", "page_start": 154},
            {"key": "2.1.1", "type": "item", "name": "y", "page_start": 211},
        ])])
        self.assertEqual(subsection_order_problems(ch), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
