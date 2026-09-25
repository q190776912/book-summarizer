"""Per-section-restart single EN books must not be collapsed (Rosen, 2026-09-25).

Root cause: Rosen numbers "Example 1..16" inside §1.1 and *again* "Example 1..11"
inside §1.2 (config ordinal groups with scope==3, single component).  The
chapter-wide monotonic guard and the seen-key continuation guard
(added for Han-Lin's chapter-wide counters) treated every section restart as a
stale cross-reference: ch1 collapsed 138 examples -> 28.

Fix under test (extract_items_en `restart_per_section`): for labels whose
counter resets per section, both guards bucket by the current section window
(nested numbers like 1.1.1 sharing anchor 1.1's bucket), while cross-references
*within* the same section still die and non-restart labels keep the exact
chapter-wide behavior (passing None = byte-identical old path).

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_restart_per_section_single_en.py
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

from extract_items_en import extract_items_en


def _mk_pages(d, pages):
    """pages = [[block1, block2, ...], ...] -> page_001.json, one block each."""
    for i, blocks in enumerate(pages, start=1):
        fp = os.path.join(d, f"page_{i:03d}.json")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"text": [{"text": b} for b in blocks],
                       "formulas": []}, f)


class TestRestartPerSection(unittest.TestCase):
    def _run(self, d, n, windows, labels):
        return extract_items_en(d, 1, n, want_examples=True, single=True,
                                restart_per_section=(labels, windows)
                                if labels else None)

    def test_restart_across_sections_kept(self):
        # §1.1: Example 1,2,5 ; §1.2: Example 1,2 again — all five are real.
        with tempfile.TemporaryDirectory() as d:
            pages = [
                ["Example 1 Solve the congruence."],
                ["Example 2 Show that p divides a."],
                ["Example 5 Harder problem."],
                ["Example 1 Cryptography application."],   # §1.2 restart
                ["Example 2 RSA system."],                 # §1.2
            ]
            _mk_pages(d, pages)
            items = self._run(d, 5, [(1, "1.1"), (4, "1.2")], {"example"})
            e1 = [it for it in items if it["key"] == "Example 1"]
            self.assertEqual(len(e1), 2, "section restart must survive")
            self.assertEqual({it["page"] for it in e1}, {1, 4})
            self.assertEqual(len(items), 5)

    def test_monotonic_guard_still_applies_within_section(self):
        # Inside §1.2 (pages 4-6) the stale "Example 2" after Example 7 is the
        # Han-Lin wrapped cross-reference shape and must STILL die.
        with tempfile.TemporaryDirectory() as d:
            pages = [
                ["Example 1 First."],
                ["Example 2 Second."],
                ["Example 3 Third."],
                ["Example 7 New section item."],
                ["Example 2 Let us recall the claim."],   # <= max(7), same bucket
                ["Example 8 Next real item."],
            ]
            _mk_pages(d, pages)
            items = self._run(d, 6, [(1, "1.1"), (4, "1.2")], {"example"})
            keys = [(it["key"], it["page"]) for it in items]
            self.assertNotIn(("Example 2", 5), keys)
            self.assertIn(("Example 8", 6), keys)
            self.assertIn(("Example 2", 2), keys)  # first section keeps its own

    def test_nested_subsection_shares_bucket(self):
        # "1.1.1" is NOT a reset boundary: a stale reference landing there dies.
        with tempfile.TemporaryDirectory() as d:
            pages = [
                ["Example 1 First."],
                ["Example 9 Deep item."],
                ["Example 3 Stale wrapped reference here."],  # under 1.1.1 bucket
                ["Example 1 Fresh section restart."],          # under 1.2
            ]
            _mk_pages(d, pages)
            items = self._run(d, 4, [(1, "1.1"), (3, "1.1.1"), (4, "1.2")],
                              {"example"})
            keys = [(it["key"], it["page"]) for it in items]
            self.assertNotIn(("Example 3", 3), keys)
            self.assertIn(("Example 1", 4), keys)

    def test_non_restart_labels_keep_chapter_wide(self):
        # Definition is not in the restart set -> its §1.2 "Definition 1" is
        # still collapsed by the chapter-wide guard (Evans/Silverman shape).
        with tempfile.TemporaryDirectory() as d:
            pages = [
                ["Definition 5 Modular arithmetic."],
                ["Example 1 Solve."],
                ["Example 1 Restart example."],
                ["Definition 1 Modular again."],   # chapter-wide stale -> dies
            ]
            _mk_pages(d, pages)
            items = self._run(d, 4, [(1, "1.1"), (3, "1.2")], {"example"})
            keys = [(it["key"], it["page"]) for it in items]
            self.assertIn(("Example 1", 3), keys)
            self.assertNotIn(("Definition 1", 4), keys)

    def test_no_parameter_is_byte_identical_old_behavior(self):
        # Regression pin: without restart_per_section the collapse persists.
        with tempfile.TemporaryDirectory() as d:
            pages = [
                ["Example 1 First."],
                ["Example 9 High."],
                ["Example 2 Restart in next section."],  # would die chapter-wide
            ]
            _mk_pages(d, pages)
            items = self._run(d, 3, None, None)
            keys = [it["key"] for it in items]
            self.assertEqual(keys.count("Example 2"), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
