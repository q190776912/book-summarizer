"""primary_group must never be hijacked by the Figure group (2026-09-24 Rising Sea incident).

Root cause: Vakil-shaped books declare the shared text counter as the
`uncat` fallback group ({"type":8,"name":["uncat"],"scope":3}) AND carry a
separate Figure group ({"type":2,"name":["Fig","Figure"]}).  The old
`primary_group` = "first non-uncat group" returned the FIGURE group, so
`primary_type` became 2 (EN two-level) and build_structure dispatched the
wrong extractor: ch1's 76 extracted items were silently dropped (items=0),
sections were misbuilt, and the completeness gate could never pass.

Fix under test (SSOT `lib.numbering.is_fig_group`):
  * figure-only groups are skipped when choosing `primary_group`;
  * fallback order preserved: labeled group > uncat/[0];
  * books whose ONLY non-uncat group is Figure fall back to [0] (unchanged).

Runs under stdlib unittest:
  python config/verify_config/tests/test_primary_fig_hijack.py
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
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from verify_config import BookConfig
from lib.numbering import is_fig_label_name, is_fig_group


class TestPrimaryFigHijack(unittest.TestCase):
    def test_vakil_uncat_plus_figure(self):
        book = BookConfig.from_dict({
            "ordinal": [
                {"type": 8, "name": ["uncat"], "scope": 3},
                {"type": 2, "name": ["Fig", "Figure"], "scope": 2},
            ],
            "language": "en",
        })
        self.assertEqual(book.primary_type, 8)

    def test_labeled_group_still_wins(self):
        book = BookConfig.from_dict({
            "ordinal": [
                {"type": 3, "name": ["定理"], "scope": 2},
                {"type": 2, "name": ["图"], "scope": 2},
                {"type": 3, "name": ["uncat"], "scope": 2},
            ],
        })
        self.assertEqual(book.primary_group.name, ["定理"])

    def test_figure_only_falls_back_to_first(self):
        book = BookConfig.from_dict({
            "ordinal": [
                {"type": 2, "name": ["Fig", "Figure"], "scope": 2},
            ],
        })
        self.assertEqual(book.primary_type, 2)

    def test_mixed_label_group_not_skipped(self):
        # A group that carries Figure AND text labels is NOT figure-only.
        book = BookConfig.from_dict({
            "ordinal": [
                {"type": 3, "name": ["Theorem", "Figure"], "scope": 2},
                {"type": 2, "name": ["Fig"], "scope": 2},
            ],
        })
        self.assertEqual(book.primary_group.name, ["Theorem", "Figure"])

    def test_predicates(self):
        self.assertTrue(is_fig_label_name("Figure"))
        self.assertTrue(is_fig_label_name("Fig."))
        self.assertTrue(is_fig_label_name("图"))
        self.assertFalse(is_fig_label_name("Theorem"))
        self.assertFalse(is_fig_label_name("uncat"))
        self.assertTrue(is_fig_group({"name": ["Fig", "Figure"]}))
        self.assertFalse(is_fig_group({"name": ["Theorem", "Figure"]}))
        self.assertFalse(is_fig_group({"name": []}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
