# -*- coding: utf-8 -*-
"""`_find_split_heading_page` —— 「两行拆分节头」定位（build_structure 补锚净网）。

立项缺陷（2026-10-10 Bass《Real Analysis for Graduate Students》ch2 §2.1 实测）：
OCR 把真节头切成**两块**——一个独立成块的裸节号 `2.1`（p29），紧跟一个标题块
`Algebras and o-algebras`。scan_skeleton 的**单行**节头检测器（要求「号+标题」同行）
看不见它，早期版本遂把后文页顶的**全大写页眉复本** `2.1. ALGEBRAS AND σ-ALGEBRAS`
（p31）当成 §2.1 锚点 → 定义2.1 / 例2.2–2.6 / 引理2.7 整批漂到章级、归属错位。

本函数是 build_structure 补锚 pass 的定位核，与
`verify/script/check_section_attribution.py::_earliest_heading_pages` **逐字同源**
（闸拦什么、build 就修什么）：只认「裸号块紧跟标题块」这一**两行**形态作为最早真
节头的证据。故此处锁死判据的边界，尤其锁死两类**必须不误报**的形态：
  · 交叉引用句内联在正文里（`4.2 shows that …`）——从不独占一块 → 不认；
  · 纯目录/扉页（本页无任何「标签+编号」条头）——即便排了裸号+标题也不认；
  · 全大写单行页眉（号+标题同一块）——非裸号块 → 不认。

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_split_heading_anchor_net.py
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
import lib.boot as _boot                # noqa: E402
_boot.setup()

from build_structure import _find_split_heading_page  # noqa: E402


def _blk(text, y):
    """单栏 OCR 块：poly[1] = 块顶 y。"""
    return {"text": text, "poly": [40.0, float(y), 640.0, float(y),
                                   640.0, float(y) + 24.0, 40.0, float(y) + 24.0]}


def _write_pages(ext, pages):
    """pages: {page_no: [ (text, y), ... ]} → page_%03d.json。"""
    for pg, blocks in pages.items():
        data = {"text": [_blk(t, y) for (t, y) in blocks]}
        with open(os.path.join(ext, "page_%03d.json" % pg), "w",
                  encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)


# 正文页判据用的条头（触发本函数把该页认作正文页）
_ITEM = "Definition 2.1 An algebra is a collection of subsets"


class TestSplitHeadingNet(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ext = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def test_detects_two_line_split_on_body_page(self):
        """p2 裸号块 + 标题块（正文页含条头）→ (2, y_of_bare)。"""
        _write_pages(self.ext, {
            2: [("Chapter 2", 400), ("2.1", 756),
                ("Algebras and o-algebras", 750), (_ITEM, 1065)],
        })
        got = _find_split_heading_page(self.ext, "2.1", 2, 4)
        self.assertIsNotNone(got, "拆分两行节头须被定位")
        self.assertEqual(got[0], 2)
        self.assertAlmostEqual(got[1], 756.0)

    def test_cross_reference_inline_is_not_a_heading(self):
        """交叉引用句内联（`4.2 shows that …`）从不独占裸号块 → 不误判。"""
        _write_pages(self.ext, {
            3: [("Proposition 3.1 statement", 200),
                ("4.2 shows that mu* is an outer measure, but we will see", 300)],
        })
        self.assertIsNone(_find_split_heading_page(self.ext, "4.2", 3, 4),
                          "以节号起头的散文句不是节头，绝不定位")

    def test_toc_page_without_item_head_is_skipped(self):
        """纯目录/扉页：无「标签+编号」条头 → 即便裸号+标题也跳过。"""
        _write_pages(self.ext, {
            1: [("2.1", 300), ("Algebras and o-algebras", 305),
                ("2.2", 400), ("Monotone class theorem", 405)],
        })
        self.assertIsNone(_find_split_heading_page(self.ext, "2.1", 1, 2),
                          "扉页目录无条头 = 非正文页，须跳过")

    def test_all_caps_running_head_single_block_is_not_split(self):
        """全大写页眉（号+标题同一块）非「裸号块」 → 不认（避免撞页眉复本）。"""
        _write_pages(self.ext, {
            4: [("2.1. ALGEBRAS AND o-ALGEBRAS", 126),
                ("Proposition 2.8 If X equals R", 579)],
        })
        self.assertIsNone(_find_split_heading_page(self.ext, "2.1", 4, 5),
                          "单行页眉不是两行拆分节头")

    def test_bare_number_without_adjacent_title_is_skipped(self):
        """裸号块后随的是另一裸号/非标题 → 不认（须紧跟真标题块）。"""
        _write_pages(self.ext, {
            2: [("2.1", 300), ("2.2", 305), (_ITEM, 900)],
        })
        self.assertIsNone(_find_split_heading_page(self.ext, "2.1", 2, 3),
                          "裸号后随裸号不构成两行节头")

    def test_picks_earliest_page_of_recurring_split(self):
        """同一拆分形态跨多页出现 → 取最早页。"""
        _write_pages(self.ext, {
            3: [("Proposition 3.2 recap", 200)],        # 无 3.3 裸号
            5: [("3.3", 600), ("Further results", 604), (_ITEM, 900)],
            6: [("3.3", 600), ("Further results", 604), (_ITEM, 900)],
        })
        got = _find_split_heading_page(self.ext, "3.3", 3, 7)
        self.assertIsNotNone(got)
        self.assertEqual(got[0], 5, "须取最早命中页而非后续复现页")

    def test_cjk_split_heading_detected(self):
        """中文书：裸号块 + CJK 标题块（含条头）→ 定位。"""
        _write_pages(self.ext, {
            40: [("8.1", 500), ("方差分析", 504),
                 ("定义8.1 设随机变量 X 服从正态分布", 800)],
        })
        got = _find_split_heading_page(self.ext, "8.1", 40, 42)
        self.assertIsNotNone(got, "CJK 两行节头须被定位")
        self.assertEqual(got[0], 40)


if __name__ == "__main__":
    unittest.main(verbosity=2)
