# -*- coding: utf-8 -*-
"""页眉带复本（running head）判据与「窗口左界降级」的判据测试。

立项缺陷（2026-09-28 Arnold《经典力学的数学方法》中文扫描版 p162 实测）：印刷把
**当前节标题**重印在每页页首右侧作页眉，本书页幅大 → 页眉 y≈119，而绝对页首阈值
是 100，旧判据整条漏网。p162 的块序（OCR `page_162.json`）：

    idx 0   y=119   '$36．外微分'      ← 页眉复本（右移）
    idx 7   y=604   '问题 13 …'        ← §35 的尾条
    idx 10  y=745   '问题 14 …'        ← §35 的尾条
    idx 15  y=1053  '$36．外微分'      ← §36 真节头（左边界）

骨架里同一 (页, 键) 于是有两行；窗口左界按「(页, 块首 y)」先到者，页眉把 §36 的左界
推到 y=119 ⇒ 同页其后的两条 §35 尾题整条判给 §36（契约挂错节，B 层只能报出无法解释
的缺号）。修法两条，都在本文件锁死：
  ① 带下界**按本页自己的最顶文本行**放宽：`max(_HEAD_BAND_Y, page_top_y + 容差)`
     ——既有书（页眉恒 <100）行为逐字不变，只是把带下界推到「本页第一行印刷」；
  ② `demote_head_band_rows` 只删「同号在本页还有更靠下的一行」的页眉带 SEC/SUB 行。

负向锁死三件事：
  · 左对齐的正文行永不算页眉（右移量判据不放松，否则整栏正文首行全被吞）；
  · 本页只有页眉一行时**照旧保留**（那是该节在这一页的唯一锚点，删了会丢 sec_pages）；
  · 降级只管 SEC/SUB，条目行/其它键的行一律不动；缺几何信息 fail-open。

同一谓词的第三个消费者（锚点 y 的正文带优先）见
`test_anchor_band_preference.py`；本文件末类 `TestScanWiring` 直接跑 `scan()`，钉住
「带线记录 → 降级」这条**接线**（纯函数测试证明不了接线）。

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_running_head_band.py
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

from scan_skeleton import (              # noqa: E402
    demote_head_band_rows, is_running_head, page_top_y, page_x_extent)


def _blk(text, x, y, right=1133.0, h=38.0):
    """OCR 文本块：单栏排版，右边界恒等于 `right`（页宽跨度因此可信）。

    poly = [左上x, 左上y, 右上x, 右上y, 右下x, 右下y, 左下x, 左下y]。给块编造
    `x+900` 这种假右界会把页宽跨度撑大、把 1/4 页宽的右移阈值推到真页眉之外，
    页眉就不再被 `is_running_head` 命中——测试会「因为写错而通过」。
    """
    return {"text": text,
            "poly": [x, y, right, y, right, y + h, x, y + h]}


# 实测 p162 的页幅几何：文本左边界 ≈122、右边界 ≈1133（跨度 ≈1011）、最顶行 y≈117。
LEFT, SPAN, TOP = 122.0, 1011.0, 117.0


class TestPageRelativeHeadBand(unittest.TestCase):
    def test_absolute_band_when_top_missing(self):
        """不带 `top` = 旧行为（绝对 100）：零回归面。"""
        self.assertTrue(is_running_head(721, 59, 71, 650))
        self.assertFalse(is_running_head(721, 119, 71, 650))

    def test_page_relative_band_catches_arnold_header(self):
        """Arnold 案：页眉 y=119 > 绝对阈值，但本页最顶行 y=117 → 带下界 129 命中。"""
        self.assertTrue(is_running_head(572, 119, LEFT, SPAN, TOP))

    def test_body_row_below_band_is_not_a_head(self):
        """负向：真节头（左边界 + 带下）不得算页眉。"""
        self.assertFalse(is_running_head(126, 1053, LEFT, SPAN, TOP))

    def test_left_aligned_row_in_band_is_not_a_head(self):
        """负向：带内但**左对齐**的行是正文（页眉判据两条件缺一不可）。

        只按 y 判会把整页第一栏正文首行当页眉降级 → 条目/节头被整片吞掉。
        """
        self.assertFalse(is_running_head(124, 119, LEFT, SPAN, TOP))

    def test_dominates_absolute_floor_on_tall_pages(self):
        """取大者：短页（最顶行 y=40）仍用绝对 100，不因相对带缩窄而漏判旧书。"""
        self.assertTrue(is_running_head(700, 90, LEFT, SPAN, 40.0))

    def test_fail_open_without_geometry(self):
        self.assertFalse(is_running_head(None, 50, LEFT, SPAN, TOP))
        self.assertFalse(is_running_head(700, None, LEFT, SPAN, TOP))
        self.assertFalse(is_running_head(700, 50, None, SPAN, TOP))
        self.assertFalse(is_running_head(700, 50, LEFT, 0.0, TOP))

    def test_geometry_helpers(self):
        blocks = [_blk("a", 122, 117), _blk("b", 130, 604)]
        self.assertEqual(page_top_y(blocks), 117.0)
        self.assertEqual(page_x_extent(blocks), (122.0, 1011.0))
        self.assertIsNone(page_top_y([{"text": "no poly"}]))
        self.assertEqual(page_x_extent([{"text": "no poly"}]), (None, None))


class TestDemoteHeadBandRows(unittest.TestCase):
    """`rows` 元组 = (页, 类型, 键, 标题, 块首 y)。"""

    def test_header_demoted_when_lower_same_key_row_exists(self):
        rows = [(162, "SEC", "36", "36 外微分", 119.0),
                (162, "SEC", "35", "35 泊松括弧", 300.0),
                (162, "SEC", "36", "36 外微分", 1053.0)]
        out, n = demote_head_band_rows(rows, {(162, 119.0)})
        self.assertEqual(n, 1)
        self.assertEqual([r[4] for r in out], [300.0, 1053.0])
        self.assertNotIn(119.0, [r[4] for r in out])

    def test_sole_header_row_is_kept(self):
        """负向：本页只印了页眉（该节在这一页无真节头）→ 保留，节起始页不丢。"""
        rows = [(163, "SEC", "36", "36 外微分", 119.0)]
        out, n = demote_head_band_rows(rows, {(163, 119.0)})
        self.assertEqual((n, out), (0, rows))

    def test_lower_row_of_other_key_does_not_demote(self):
        """负向：更靠下的行必须是**同号**行（另一节的节头不是本页眉的复本）。"""
        rows = [(162, "SEC", "36", "36 外微分", 119.0),
                (162, "SEC", "35", "35 泊松括弧", 1053.0)]
        out, n = demote_head_band_rows(rows, {(162, 119.0)})
        self.assertEqual((n, out), (0, rows))

    def test_item_rows_never_demoted(self):
        """负向：降级只作用于节/子块窗口行，条目行一律不动。"""
        rows = [(162, "ITEM", "问题13", "问题13 …", 119.0),
                (162, "ITEM", "问题13", "问题13 …", 604.0)]
        out, n = demote_head_band_rows(rows, {(162, 119.0)})
        self.assertEqual((n, out), (0, rows))

    def test_sub_rows_are_demoted_too(self):
        rows = [(162, "SUB", "36.A", "A. 例子", 119.0),
                (162, "SUB", "36.A", "A. 例子", 1053.0)]
        out, n = demote_head_band_rows(rows, {(162, 119.0)})
        self.assertEqual((n, [r[4] for r in out]), (1, [1053.0]))

    def test_empty_head_band_is_identity(self):
        rows = [(162, "SEC", "36", "36 外微分", 119.0)]
        self.assertEqual(demote_head_band_rows(rows, set()), (rows, 0))

    def test_short_rows_and_missing_y_survive(self):
        rows = [(162, "SEC", "36"), (162, "SEC", "36", "t", None),
                (162, "SEC", "36", "t", 119.0), (162, "SEC", "36", "t", 1053.0)]
        out, n = demote_head_band_rows(rows, {(162, 119.0)})
        self.assertEqual(n, 1)
        self.assertEqual(len(out), 3)


class TestScanWiring(unittest.TestCase):
    """接线：`scan()` 真的把 `is_running_head` 记的带线喂给降级（合成 p162 双行）。

    单测 `demote_head_band_rows` 只证明纯函数正确；本类证明扫描循环**确实**按页记录
    了页眉带线并应用降级——漏接线时页眉行照样进 `rows`，窗口左界照样被推到 y=119。
    """

    @staticmethod
    def _rows(pages, start, end):
        with tempfile.TemporaryDirectory() as d:
            for p, blocks in pages.items():
                with open(os.path.join(d, "page_%03d.json" % p), "w",
                          encoding="utf-8") as f:
                    json.dump({"text": blocks, "formulas": []}, f)
            import scan_skeleton
            return scan_skeleton.scan(d, 7, start, end, "cn",
                                      chapter_first=True, sections_global=True,
                                      language="cn")

    def test_arnold_p162_shape_keeps_body_head_only(self):
        pages = {
            161: [_blk("§35．泊松括弧", 126, 200), _blk("问题12 求…", 180, 400)],
            162: [_blk("$36．外微分", 572, 119),        # 页眉复本（右移）
                  _blk("·147·", 1087, 119),
                  _blk("问题 13 求矢量场 A 在球面上的通量", 180, 604),
                  _blk("问题 14 设在 2n 维空间中有一个二维链", 180, 745),
                  _blk("$36．外微分", 126, 1053),       # 真节头（左边界）
                  _blk("我们在这里定义k-形式的外微分", 130, 1135)],
        }
        secs = [(p, k, y) for p, kind, k, _t, y in self._rows(pages, 161, 162)
                if kind == "SEC"]
        self.assertEqual(secs, [(161, "35", 200.0), (162, "36", 1053.0)],
                         "§36 的窗口左界必须是真节头 y，不是页眉 y")

    def test_page_with_only_header_still_emits_section(self):
        """负向：本页没有真节头（跨页节的续页）时页眉行照旧发出，节不丢锚点。"""
        pages = {
            163: [_blk("$36．外微分", 572, 119),
                  _blk("由此得到斯托克斯定理的推论", 130, 300)],
        }
        secs = [(p, k, y) for p, kind, k, _t, y in self._rows(pages, 163, 163)
                if kind == "SEC"]
        self.assertEqual(secs, [(163, "36", 119.0)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
