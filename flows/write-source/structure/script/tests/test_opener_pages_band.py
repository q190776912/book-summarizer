# -*- coding: utf-8 -*-
"""Regression: 章扉页「目录带」判据数**带内**命中，不是要求全部命中在带内
（build_structure._compute_opener_pages；Evans《PDE》2ed ch6，2026-09-30）。

Evans 每章扉页把本章小节列成目录带，而**正文就从同一页开始**：

    p325: '6.1 Definitions'(889) '6.2 Existence…'(942) … '6.7 References'(1171)
          '6.1. DEFINITIONS'(1439)   <- 真节头，同页带下
          '6.1.1. Elliptic equations.'(1508)

旧判据「全部首现命中都落在带内」被带下这两条真节头打破 → p325 不被认作扉页 →
§6.2…§6.7 的 sec_pages 全锚扉页，而其子节（§6.1.2 p327 / §6.2.3 p334 …）锚点正确
→ ANCHOR-SANITY「小节号更晚而页码更早」10 处矛盾，ch6 拒绝落盘。

新判据：目录带 = 行距 ≤ _TOC_LINE_GAP 的最长连续前缀，**前缀内**首现 ≥K 条即扉页；
带下的命中交给 `_hit_below_toc_band` 原位采用（本就是该机制的设计场景）。
负向（茆诗松 ch8 p395，2026-09-29 实测）必须继续不免疫：带内只有 628/774 两条。

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_opener_pages_band.py
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

from build_structure import (_compute_opener_pages, _hit_below_toc_band,  # noqa: E402
                             _toc_band_bottom)


def _fh(rows):
    """rows: [(page, num, y)] → first_hit（num -> (page,'SEC',num,title,y)）。"""
    return {n: (p, "SEC", n, "t%s" % n, y) for p, n, y in rows}


EVANS_CH6 = _fh([
    (325, "6.1", 889.0), (325, "6.2", 942.0), (325, "6.3", 985.0),
    (325, "6.4", 1029.0), (325, "6.5", 1077.0), (325, "6.6", 1125.0),
    (325, "6.7", 1171.0), (325, "6.1.1", 1439.0 + 69.0), (327, "6.1.2", 1510.0),
])


class TestOpenerBand(unittest.TestCase):
    def test_evans_opener_with_body_heading_below_band_is_still_toc_page(self):
        self.assertIn(325, _compute_opener_pages(EVANS_CH6))

    def test_old_all_hits_in_band_criterion_would_reject_it(self):
        ys = sorted(r[4] for r in EVANS_CH6.values() if r[0] == 325)
        self.assertLess(_toc_band_bottom(ys), ys[-1])   # 带未覆盖全部 → 旧判据弃页

    def test_hit_below_band_is_used_in_place(self):
        band = _toc_band_bottom(
            sorted(r[4] for r in EVANS_CH6.values() if r[0] == 325))
        self.assertEqual(band, 1171.0)
        self.assertTrue(_hit_below_toc_band(1508.0, band))    # §6.1.1 真节头
        self.assertFalse(_hit_below_toc_band(942.0, band))    # §6.2 目录行 → 回扫

    def test_mao_ch8_body_page_stays_not_opener(self):
        # 茆书 p395：§8.1(628)/§8.1.1(774) 间距 146 成带，§8.1.2(1833) 远在带外
        mao = _fh([(395, "8.1", 628.0), (395, "8.1.1", 774.0),
                   (395, "8.1.2", 1833.0), (407, "8.2", 300.0)])
        self.assertNotIn(395, _compute_opener_pages(mao))

    def test_pure_toc_page_still_opener(self):
        toc = _fh([(100, "3.1", 400.0), (100, "3.2", 452.0), (100, "3.3", 505.0),
                   (101, "3.4", 300.0)])
        self.assertIn(100, _compute_opener_pages(toc))

    def test_two_hits_below_k_never_opener(self):
        few = _fh([(50, "2.1", 400.0), (50, "2.2", 450.0), (60, "2.3", 300.0)])
        self.assertNotIn(50, _compute_opener_pages(few))

    def test_no_y_rows_fail_open(self):
        md = {  # md 派生行 y=None：无法核带 → 维持旧行为（认作目录页）
            "2.1": (7, "SEC", "2.1", "A", None),
            "2.2": (7, "SEC", "2.2", "B", None),
            "2.3": (7, "SEC", "2.3", "C", None),
        }
        self.assertIn(7, _compute_opener_pages(md))


if __name__ == "__main__":
    unittest.main(verbosity=2)
