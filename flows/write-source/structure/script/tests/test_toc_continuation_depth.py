# -*- coding: utf-8 -*-
"""Regression: chapter-TOC continuation page must only be treated as TOC when the
next page's first-hit keys share the opener's ordinal depth
(build_structure._opener_continuation_pages; Rosen 8e ch1 §1.1.2, 2026-09-26).

Row layout of `first_hit` values, as produced by build_chapter from scan_skeleton
SEC rows:  (page, kind, key, title, y).

Shapes under test:
  * Ross ch9 — opener page lists 9.1/9.2/9.3 (depth 2), the tail entry `9.4`
    continues at the very top of the next page (y=103) -> that page IS a TOC
    continuation (must stay poisoned, otherwise §9.4 anchors on the opener page);
  * Rosen ch1 — opener page (24) lists 1.1..1.8 (depth 2) *and* carries the body
    heading `1.1.1 Introduction` deep in the page; page 25 tops out with
    `1.1.2 Propositions` at y=175, which is the **body** heading of §1.1.2
    (its prose follows immediately). The old rule keyed on "all first hits hug
    the top" alone and poisoned p25, so the re-scan's strict `min_y` excluded the
    heading itself and §1.1.2 anchored to p61 — the §1.3 exercise region — with no
    sibling inversion for the order gate to see. Depth agreement is what tells the
    two shapes apart.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_toc_continuation_depth.py
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
import lib.boot as _boot  # noqa: E402
_boot.setup()

from build_structure import _opener_continuation_pages  # noqa: E402


def _row(page, key, y, title="T"):
    return (page, "SEC", key, title, y)


def _fh(rows):
    fh = {}
    for r in rows:
        fh.setdefault(r[2], r)
    return fh


class TestTocContinuationDepth(unittest.TestCase):
    # ---- Ross ch9 shape: same-depth tail entry continues on the next page ----
    ROSS = _fh([
        _row(301, "9.1", 420.0), _row(301, "9.2", 470.0), _row(301, "9.3", 520.0),
        _row(302, "9.4", 103.0),
    ])

    def test_same_depth_tail_page_is_poisoned(self):
        self.assertEqual(_opener_continuation_pages(self.ROSS, {301}), {302})

    # ---- Rosen ch1 shape: deeper key on the next page is a BODY heading ----
    ROSEN = _fh([
        _row(24, "1.1", 387.0), _row(24, "1.2", 471.0), _row(24, "1.3", 587.0),
        _row(24, "1.4", 672.0), _row(24, "1.5", 751.0), _row(24, "1.6", 834.0),
        _row(24, "1.7", 921.0), _row(24, "1.8", 1005.0),
        _row(24, "1.1.1", 1525.0),      # body heading, below the TOC band
        _row(25, "1.1.2", 175.0),       # body heading hugging the page top
    ])

    def test_deeper_key_page_is_not_poisoned(self):
        self.assertEqual(_opener_continuation_pages(self.ROSEN, {24}), set())

    def test_body_heading_below_band_does_not_count_as_opener_row(self):
        # 扉页深度众数仍取目录带（深度 2）——正文的 1.1.1 只是少数行。
        self.assertEqual(_opener_continuation_pages(self.ROSEN, {24, 25}), set())

    # ---- guards ----
    def test_page_without_first_hits_not_added(self):
        fh = _fh([_row(10, "2.1", 400.0), _row(10, "2.2", 450.0),
                  _row(10, "2.3", 500.0)])
        self.assertEqual(_opener_continuation_pages(fh, {10}), set())

    def test_low_continuation_row_is_body_not_toc(self):
        # 次页的同号行在正文区（y>350）=> 不可能是目录续排。
        fh = _fh([_row(10, "2.1", 400.0), _row(10, "2.2", 450.0),
                  _row(10, "2.3", 500.0), _row(11, "2.4", 900.0)])
        self.assertEqual(_opener_continuation_pages(fh, {10}), set())

    def test_toc_listing_subsections_still_poisons_deeper_tail(self):
        # 目录本身就列 §N.M.K 的书（扉页众数深度 3）：次页的 1.2.3 续排仍应免疫。
        fh = _fh([_row(5, "1.1.1", 300.0), _row(5, "1.1.2", 340.0),
                  _row(5, "1.1.3", 380.0), _row(6, "1.2.3", 110.0)])
        self.assertEqual(_opener_continuation_pages(fh, {5}), {6})

    def test_no_opener_pages_returns_empty(self):
        self.assertEqual(_opener_continuation_pages(self.ROSEN, set()), set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
