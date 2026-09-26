"""Arnold-ODE third structural level: bare per-§ restarting numeric subsections.

The book prints single-number GLOBAL § heads (``§ 1. Phase Spaces``) and, inside
each §, bare ``N. Title`` sub-heads that RESTART at 1 per section
(``1. Examples of Evolutionary Processes`` … ``18. Example: Small Oscillations``).
The pipeline previously collapsed this to a flat 2-level tree, so the summary TOC
did not match the book level-by-level.

Feature under test (scan_skeleton, ``local_num_sec`` + post-filter exemption +
``numeric_local_subsection_probe``): a candidate is promoted to a REAL level-2
SEC row keyed ``<§>.<local>`` ONLY when

  * it is a bare number immediately followed by a separator ``./．/:/：/、/。``
    (kills footnote markers ``1 Isac…`` and running heads ``16  Chapter 1…``),
  * the title starts upper-case, is 2..61 chars, has no math-operator and is not
    a running head (kills prose / math residue / headers),
  * the per-§ +1 CONTINUITY LATCH accepts it (number == prev+1, seeded at 1),
  * and the ``global_sec`` dotted-SEC *prose* post-filter EXEMPTS exactly the
    keys we intentionally emitted (``local_sec_keys``), while still dropping the
    ``谷超豪``-style ``7.7 所示`` false positives.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_numeric_local_sections.py
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

import scan_skeleton as S


def _mk_pages(d, pages):
    """pages = [[block_text, ...], ...] -> page_001.json (one file per entry)."""
    for i, blocks in enumerate(pages, start=1):
        fp = os.path.join(d, f"page_{i:03d}.json")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"text": [{"text": b} for b in blocks], "formulas": []}, f)


def _sec_keys(rows):
    return {str(r[2]) for r in rows if r[1] == 'SEC'}


class TestLocalNumSecDetection(unittest.TestCase):
    MODE = 'two-level'

    def _scan(self, d, n, local=True):
        return S.scan(d, 1, 1, n, self.MODE, chapter_first=True,
                      sections_global=True, local_num_sec=local)

    def test_contiguous_runs_promoted(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["§ 1. Phase Spaces",
                 "1. Examples of Evolutionary Processes",
                 "some prose body that is long enough to be ignored here",
                 "2. Phase Spaces",
                 "3.The Integral Curves of a Direction Field"],
                ["§ 2. Vector Fields on the Line",
                 "1. Existence and Uniqueness of Solutions",
                 "2. A Counterexample"],
            ])
            keys = _sec_keys(self._scan(d, 2))
            self.assertIn('1', keys)            # § head
            self.assertIn('2', keys)            # § head
            self.assertIn('1.1', keys)          # subsection (local 1)
            self.assertIn('1.2', keys)          # subsection (local 2)
            self.assertIn('1.3', keys)          # subsection (no-space after dot)
            self.assertIn('2.1', keys)          # restart under §2
            self.assertIn('2.2', keys)
            self.assertTrue(all(k.count('.') <= 1 for k in keys),
                            "only single-level dotted children, no deepening")

    def test_no_local_num_sec_is_byte_identical(self):
        # local_num_sec=False (every non-Arnold book) => NO dotted subsection SEC.
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["§ 1. Phase Spaces",
                 "1. Examples of Evolutionary Processes",
                 "2. Phase Spaces"],
            ])
            keys = _sec_keys(self._scan(d, 1, local=False))
            self.assertNotIn('1.1', keys)
            self.assertNotIn('1.2', keys)
            self.assertIn('1', keys)            # § head still found

    def test_latch_rejects_out_of_order_restart(self):
        # A bare "5." when the run expects 3 must be rejected (not next number).
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["§ 1. Phase Spaces",
                 "1. First Sub",
                 "2. Second Sub",
                 "5. Jumped A Head",   # gap -> rejected
                 "3. Third Sub"],      # resumes correctly
            ])
            keys = _sec_keys(self._scan(d, 1))
            self.assertNotIn('1.5', keys)
            self.assertIn('1.3', keys)

    def test_running_head_and_footnote_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["§ 1. Phase Spaces",
                 "1. Examples of Evolutionary Processes",
                 "16  Chapter 1. Basic Concepts",   # running head: no sep after num
                 "1 Isac Barrow proved the claim",   # footnote: number + space only
                 "1 = 2 and 3 = 0 are the eigenvalues"],  # math residue
            ])
            keys = _sec_keys(self._scan(d, 1))
            self.assertEqual(keys & {'1.16', '1.1'}, {'1.1'})  # only the real sub 1
            self.assertNotIn('1.2', keys)

    def test_lowercase_or_overlong_rejected(self):
        # lowercase-initial candidate never matches the [A-Z] anchor; an
        # over-61-char title is rejected by the {1,60} length cap.
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["§ 1. Phase Spaces",
                 "1. Examples here",
                 "2. lowercase start is not a title case head and never matches",
                 "3. " + ("x" * 200)],   # far beyond the 60-char title cap
            ])
            keys = _sec_keys(self._scan(d, 1))
            self.assertIn('1.1', keys)
            self.assertNotIn('1.2', keys)   # lowercase 'l' -> no [A-Z] match
            self.assertNotIn('1.3', keys)   # over-long title rejected

    def test_global_sec_prose_dotted_still_dropped(self):
        # The post-filter drops "7.7 所示"-style dotted SEC false positives, but
        # KEEPS the keys we intentionally emitted via local_num_sec.
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["§ 7. Dynamics",
                 "1. First Real Subsection",
                 "7.7 所示 is only prose reference here"],
            ])
            keys = _sec_keys(self._scan(d, 1))
            self.assertIn('7.1', keys)          # emitted local survives the filter
            self.assertNotIn('7.7', keys)       # stray dotted prose dropped


class TestProbe(unittest.TestCase):
    MODE = 'two-level'

    def _probe(self, d, ranges, **kw):
        return S.numeric_local_subsection_probe(
            ranges, mode=self.MODE, default_dir=d, chapter_first=True, **kw)

    def test_fires_on_arnold_shape(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["§ 1. Phase Spaces", "1. One Sub", "2. Two Sub", "3. Three Sub"],
                ["§ 2. Vector Fields", "1. Alpha Sub", "2. Beta Sub", "3. Gamma Sub"],
            ])
            fire, info = self._probe(d, [(1, 1, 2)])
            self.assertTrue(fire)
            self.assertGreaterEqual(info["total_children"], 6)
            self.assertIn('1', info["good_parents"])
            self.assertIn('2', info["good_parents"])

    def test_no_fire_without_subsections(self):
        # A global-§ book whose sections have NO numeric sub-blocks.
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["§ 1. Phase Spaces", "plain body prose continues for a while"],
                ["§ 2. Vector Fields", "more body prose with no numbered heads"],
            ])
            fire, info = self._probe(d, [(1, 1, 2)])
            self.assertFalse(fire)

    def test_no_fire_for_dotted_heading_book(self):
        # No literal "§ N" single-number heads -> sec_parents empty -> no fire.
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["1.1 Sparse Polynomial", "1.2 Eigenfunctions body"],
                ["2.1 Deep Section", "2.2 More body text"],
            ])
            fire, info = self._probe(d, [(1, 1, 2)])
            self.assertFalse(fire)

    def test_no_fire_when_only_one_good_parent(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["§ 1. Phase Spaces", "1. One Sub", "2. Two Sub", "3. Three Sub",
                 "4. Four Sub", "5. Five Sub", "6. Six Sub"],
                ["§ 2. Vector Fields", "body prose only no numbers"],
            ])
            fire, info = self._probe(d, [(1, 1, 2)])
            self.assertFalse(fire)   # min_parents=2 not met


if __name__ == "__main__":
    unittest.main(verbosity=2)
