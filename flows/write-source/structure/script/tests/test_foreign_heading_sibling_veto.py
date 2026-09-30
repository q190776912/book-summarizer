# -*- coding: utf-8 -*-
"""Regression: a generic word heading must not anchor a section onto ANOTHER
section's page, and a body heading already below the chapter-TOC band must be
used in place (build_structure; Rosen 8e ch2 §2.1.1, 2026-09-25).

Rosen prints one chapter opener TOC listing only §N.M, and OCR slices every body
subsection heading into TWO blocks — bare number + title:

    page 211:  "2.6.1"(y=295) "Introduction"(y=293)     <- §2.6.1 really starts here
    page 144:  "2.1.1 Introduction"(y=1635)             <- §2.1.1 really starts here
    page 156:  "2.2.1"(y=1113) "Introduction"(y=1110)

Two independent defects followed from that:

1. `_find_numbered_heading_page` re-scan for §2.1.1 (whose first hit sits on the
   opener page) found no `title`/`bare` candidate — the opener-page heading is
   excluded by `min_y` — and fell through to the loose `text` candidate, i.e. the
   bare word "Introduction" belonging to §2.2.1/§2.6.1 → §2.1.1 anchored at 211,
   duplicating §2.6.1's content and stretching §2.1's window across the chapter.
   Guard: a `text` candidate with an *alien* bare-number block in the same line
   band (|Δy| ≤ 80) on the same page belongs to that other number → reject.
   Rosen ch11's genuinely unnumbered headings (no alien block) keep working.

2. The caller treated EVERY opener-page hit as a TOC line and re-scanned, but for
   §N.M.K the first hit *is* the body heading (TOC lists only §N.M), and
   `min_y` strictly excludes that row itself → anchor is whatever the re-scan
   happens to hit. Guard: `_hit_below_toc_band` — a hit below the page's TOC band
   (= max y over that page's first hits) is the real heading; use it, no re-scan.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_foreign_heading_sibling_veto.py
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

from build_structure import (_find_numbered_heading_page,  # noqa: E402
                             _has_foreign_sibling, _hit_below_toc_band)


def _blk(text, y):
    return {"text": text, "poly": [60, y, 900, y + 30, 900, y + 60, 60, y + 60]}


def _mk(d, pages):
    for p, blks in pages.items():
        with open(os.path.join(d, "page_%03d.json" % p), "w",
                  encoding="utf-8") as fh:
            json.dump({"text": [_blk(t, y) for t, y in blks],
                       "formulas": []}, fh)


# Rosen ch2 shape: opener TOC (2.1..2.6), body head "2.1.1 Introduction" below
# the band on the SAME page, and numbered "Introduction" headings later.
PAGES = {
    144: [("2.1 Sets", 385), ("2.2 Set Operations", 431),
          ("2.3 Functions", 481), ("2.6 Matrices", 693),
          ("2.1", 1524), ("Sets", 1544),
          ("2.1.1 Introduction", 1635),
          ("In this section we study the fundamental discrete structure", 1711)],
    156: [("2.2 Set Operations 133", 95), ("2.2.1", 1113),
          ("Introduction", 1110), ("Unions and Intersections", 1180)],
    211: [("188 2 / Basic Structures", 94), ("Matrices", 196),
          ("2.6.1", 295), ("Introduction", 293),
          ("Matrices are used throughout discrete mathematics", 361)],
}
LO, HI = 144, 223


class TestForeignHeadingSiblingVeto(unittest.TestCase):
    def test_generic_word_heading_does_not_steal_another_section(self):
        with tempfile.TemporaryDirectory() as d:
            _mk(d, PAGES)
            # §2.1.1 must NOT anchor on 156/211 (§2.2.1 / §2.6.1 pages): the
            # "Introduction" blocks there each sit beside an alien bare number.
            self.assertIsNone(
                _find_numbered_heading_page(d, "2.1.1", LO, HI, min_y=1635.0,
                                            page_dir=d,
                                            title_text="Introduction"))

    def test_own_numbered_heading_still_wins_over_veto(self):
        # Same fixture, but the real heading survives as a numbered line below
        # the opener page -> title candidate is untouched by the sibling veto.
        pages = {k: list(v) for k, v in PAGES.items()}
        pages[144] = [b for b in pages[144] if b[0] != "2.1.1 Introduction"]
        pages[150] = [("2.1.1 Introduction", 800), ("prose", 900)]
        with tempfile.TemporaryDirectory() as d:
            _mk(d, pages)
            self.assertEqual(
                _find_numbered_heading_page(d, "2.1.1", LO, HI, min_y=1635.0,
                                            page_dir=d,
                                            title_text="Introduction"), 150)

    def test_unnumbered_heading_without_alien_number_still_matches(self):
        # Rosen ch11 shape: bare title block, no number block on the page at all.
        pages = {k: list(v) for k, v in PAGES.items()}
        pages[144] = [b for b in pages[144] if b[0] != "2.1.1 Introduction"]
        pages[150] = [("Applications of Trees", 800), ("prose here", 900)]
        with tempfile.TemporaryDirectory() as d:
            _mk(d, pages)
            self.assertEqual(
                _find_numbered_heading_page(d, "2.1.1", LO, HI, min_y=1635.0,
                                            page_dir=d,
                                            title_text="Applications of Trees"),
                150)

    def test_helper_flags_only_same_band(self):
        foreign = [(156, 1113.0, "2.2.1")]
        self.assertTrue(_has_foreign_sibling(156, 1110.0, foreign))
        self.assertFalse(_has_foreign_sibling(156, 1400.0, foreign))
        self.assertFalse(_has_foreign_sibling(157, 1110.0, foreign))


class TestOpenerBandHit(unittest.TestCase):
    def test_hit_below_band_is_the_real_heading(self):
        self.assertTrue(_hit_below_toc_band(1635.0, 693.0))

    def test_toc_line_inside_band_still_rescans(self):
        self.assertFalse(_hit_below_toc_band(385.0, 693.0))

    def test_band_bottom_row_itself_rescans(self):
        # Ross ch5: §5.1's TOC line is the band's last entry and the body
        # heading follows below it -> conservative (old) behaviour.
        self.assertFalse(_hit_below_toc_band(693.0, 693.0))

    def test_no_band_information_rescans(self):
        self.assertFalse(_hit_below_toc_band(1635.0, None))
        self.assertFalse(_hit_below_toc_band(None, 693.0))


class TestRunningHeadOnlyBook(unittest.TestCase):
    """Evans《PDE》2ed 体例（2026-09-30 实测）：章首印目录带（`1.3 Strategies for
    studying PDE`），真节头是**大写带号**行（p24 `1.3. STRATEGIES FOR STUDYING PDE`），
    而该书把节标题逐字印成后续各页的**页眉**（p25/p27 同文）。旧「同文 ≥2 页 = 页眉，
    弃」把唯一的真节头一起否掉 → 回扫 None → 锚点退回章首目录页 p19 → 12 章全部
    ANCHOR-SANITY 拒绝落盘。判据：候选全为重复文时取**最早**那页（页眉不可能早于本节）。
    """

    EVANS = {
        19: [("Chapter 1", 120), ("INTRODUCTION", 160),
             ("1.1  Partial differential equations", 220),
             ("1.2 Examples", 250), ("1.3 Strategies for studying PDE", 280),
             ("1.4 Overview", 310), ("1.5 Problems", 340),
             ("1.1. PARTIAL DIFFERENTIAL EQUATIONS", 700),
             ("A partial differential equation (PDE) is an equation", 760)],
        21: [("1.2. EXAMPLES", 95), ("1.2. EXAMPLES", 640),
             ("Consider the initial-value problem", 700)],
        24: [("6", 90), ("1.2.2. Systems of partial differential equations.", 400),
             ("1.3. STRATEGIES FOR STUDYING PDE", 1500),
             ("We discuss here some general strategies", 1560)],
        25: [("1.3. STRATEGIES FOR STUDYING PDE", 90),
             ("1.3.1. Well-posed problems, classical solutions.", 400)],
        27: [("1.4. OVERVIEW", 90), ("1.3.3. Typical difficulties.", 400),
             ("1.4. OVERVIEW", 900)],
    }

    def _find(self, num, lo, min_y=None, title_text=None):
        with tempfile.TemporaryDirectory() as d:
            _mk(d, self.EVANS)
            return _find_numbered_heading_page(d, num, lo, 32, min_y=min_y,
                                               page_dir=d, title_text=title_text)

    def test_heading_that_also_runs_as_header_anchors_its_own_page(self):
        self.assertEqual(self._find("1.3", 19, min_y=280.0), 24)

    def test_heading_on_the_opener_page_itself(self):
        """§1.1 真在扉页起始：min_y 挡住目录行后，仍取扉页下方那条。"""
        self.assertEqual(self._find("1.1", 19, min_y=220.0), 19)

    def test_section_starting_on_its_header_page(self):
        """§1.2 的真节头与页眉同页（p21 两条），最早页即正确页。"""
        self.assertEqual(self._find("1.2", 19, min_y=250.0), 21)

    def test_no_candidate_still_returns_none(self):
        """负向：区间里根本没有该节号（不得凭目录带里的行编造锚点）。"""
        self.assertIsNone(self._find("1.9", 19, min_y=340.0))

    def test_foreign_numbered_line_is_not_claimed(self):
        """负向：§1.5 的行只在 p30 之后出现（本夹具里没有）→ None；
        而 §1.4 必须取 p27（真节头），不得取 p24/p25 的 §1.3 页眉。"""
        self.assertEqual(self._find("1.4", 19, min_y=310.0), 27)
        self.assertIsNone(self._find("1.5", 19, min_y=340.0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
