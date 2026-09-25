# -*- coding: utf-8 -*-
"""Regression: chapter-TOC opener backfill must not land on running heads
(build_structure._find_numbered_heading_page; Rosen 8e ch10/ch11, 2026-09-25).

Rosen prints each chapter opener page with a section TOC, so every `N.M` first
"SEC" hit sits on that page and the anchor has to be re-found in the body. OCR
then breaks the body headings three ways:
  * ch10 p696 — the number survives as its own block (`10.1`), title in a
    neighbouring block  -> only a BARE-number candidate exists;
  * ch11 p816/p844 — the number is lost entirely, only "Applications of Trees"
    / "Spanning Trees" stand as their own blocks -> only a TITLE-TEXT candidate
    exists (and it must not match the wrapped TOC fragment on the opener page);
  * ch11 p804 (§11.1) — nothing survives -> must return None so the caller
    falls back to the opener page, where §11.1 really starts.
What the old code actually matched in all three cases was the page TOP RUNNING
HEAD (`11.1 Introduction to Trees 783`, printed on every following page), which
pushed the anchor 1-2 pages late and hoisted the section's opening
definitions/theorems/examples out of its window (B-layer 'file' TAIL gaps).

Guards under test:
  * a text repeating (folio stripped) on >=2 pages is a running head -> reject;
  * the first running-head page is the anchor's upper BOUND (a section heading
    never appears after its own header) — without it §11.1's loose word
    "Introduction" would match a block 27 pages later;
  * priority: numbered title > bare number > bare title text.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_heading_page_backfill.py
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

from build_structure import _find_numbered_heading_page  # noqa: E402


def _blk(text, y):
    return {"text": text, "poly": [60, y, 900, y + 30, 900, y + 60, 60, y + 60]}


def _mk(d, pages):
    """pages: {page_no: [(text, y), ...]} — one block per entry."""
    for p, blks in pages.items():
        with open(os.path.join(d, "page_%03d.json" % p), "w",
                  encoding="utf-8") as fh:
            json.dump({"text": [_blk(t, y) for t, y in blks],
                       "formulas": []}, fh)


# ch11-shaped fixture: opener TOC page 1, body heads later, header each page.
PAGES = {
    1: [("2.1 Introduction", 300), ("2.2 Applications", 400),
        ("2.3 Spanning", 500), ("Spanning", 560),
        ("2.1", 1200)],
    2: [("2.1 Introduction to Trees 11", 95), ("Some prose line here", 300)],
    3: [("2.1 Introduction to Trees 12", 95), ("Theorem 1 Let T be a tree", 300)],
    4: [("2.2 Applications of Trees 13", 95), ("Applications of Trees", 900)],
    5: [("2.2 Applications of Trees 14", 95)],
    6: [("2.2 Applications of Trees 15", 95)],
    7: [("2.3 Spanning Trees 16", 95), ("Spanning Trees", 800)],
    8: [("2.3 Spanning Trees 17", 95)],
    9: [("nothing of interest here", 300)],
}


class TestRunningHeadRejected(unittest.TestCase):
    def test_bare_number_on_opener_page_wins(self):
        with tempfile.TemporaryDirectory() as d:
            _mk(d, PAGES)
            self.assertEqual(
                _find_numbered_heading_page(d, "2.1", 1, 9, min_y=300.0,
                                            title_text="Introduction"), 1)

    def test_unnumbered_title_block_used_when_number_lost(self):
        with tempfile.TemporaryDirectory() as d:
            _mk(d, PAGES)
            self.assertEqual(
                _find_numbered_heading_page(d, "2.2", 1, 9, min_y=400.0,
                                            title_text="Applications"), 4)
            self.assertEqual(
                _find_numbered_heading_page(d, "2.3", 1, 9, min_y=500.0,
                                            title_text="Spanning"), 7)

    def test_nothing_survives_falls_back_to_none(self):
        # §11.1 situation: body heading number AND title are gone from OCR.
        pages = {k: list(v) for k, v in PAGES.items()}
        pages[1] = [b for b in PAGES[1] if b[0] != "2.1"]
        with tempfile.TemporaryDirectory() as d:
            _mk(d, pages)
            self.assertIsNone(
                _find_numbered_heading_page(d, "2.1", 1, 9, min_y=300.0,
                                            title_text="Nothing Matching"))

    def test_header_bound_blocks_faraway_title_word(self):
        # "Introduction" recurs as a stand-alone block long after §2.1 began;
        # the running-head bound (first header page) must keep it out.
        pages = {k: list(v) for k, v in PAGES.items()}
        pages[1] = [b for b in PAGES[1] if b[0] != "2.1"]   # drop bare number
        pages[9] = [("Introduction", 300)]                  # late loose match
        with tempfile.TemporaryDirectory() as d:
            _mk(d, pages)
            got = _find_numbered_heading_page(d, "2.1", 1, 9, min_y=300.0,
                                              title_text="Introduction")
            self.assertIsNone(got)

    def test_wrapped_toc_fragment_on_opener_page_not_a_heading(self):
        # TOC entry wraps into its own block ("Spanning" under "2.3 Spanning"):
        # a title-text match on the opener page must never win.
        with tempfile.TemporaryDirectory() as d:
            _mk(d, PAGES)
            got = _find_numbered_heading_page(d, "2.3", 1, 9, min_y=999.0,
                                              title_text="Spanning")
            self.assertEqual(got, 7)

    def test_numbered_body_heading_still_preferred(self):
        # Ross/Strogatz shape: a genuine `2.4 Transport Equation` line exists —
        # it wins over any title-text/bare candidate and the header is ignored.
        pages = dict(PAGES)
        pages[5] = [("2.4 Transport Equation", 700)]
        with tempfile.TemporaryDirectory() as d:
            _mk(d, pages)
            self.assertEqual(
                _find_numbered_heading_page(d, "2.4", 1, 9, min_y=600.0,
                                            title_text="Transport"), 5)


if __name__ == "__main__":
    unittest.main(verbosity=2)
