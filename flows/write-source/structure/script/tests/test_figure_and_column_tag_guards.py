# -*- coding: utf-8 -*-
r"""Regression: figure-area numbers and cross-column bundles must not become tags.

Strogatz《Nonlinear Dynamics and Chaos》3e (2026-09-27 实测) 里收割流造出两类**印面
并不存在**的编号，两者都让契约（= `gate_units` 判据 12 的真值）把写手逼成
「照写 = 编造编号，不写 = 漏写」两头堵：

1. **图区坐标轴刻度被当编号**——p407（印面 392）分岔图下方的 ``10 20 30 40 50``
   在 OCR 通道里就是独立成行的裸数字块，被挂到同页一个展示式上；写手照契约补写了
   ``\\tag{40}`` / ``\\tag{50}``（PDF 出版方文字层核对该页右缘**无**这些号）。
2. **跨列捆绑**——p262 的 `\begin{array}`  averages 式右缘只印 ``(54)``，而 array 内
   `3/8` 分数的分子分母（``3``/``8``）与 `\cos^{2n}` 的指数（``2n``）横向落在公式
   bbox 的右半侧，旧「一块可挂多号」把它们一并收进 `tags` → 契约要求同一块写四个
   ``\\tag``（KaTeX 亦判 ``Multiple \\tag`` 渲染失败）。

Fix under test: :func:`attach_content._in_figure`（按 ``figure_index`` 图 bbox 排除
图内数字）与 :func:`attach_content._same_column_cluster`（多号只信**同列**、且取离
版心中点最远的一簇——逐行编号必贴在编号列上，碎片不会）。

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_figure_and_column_tag_guards.py
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

from attach_content import (  # noqa: E402
    _attach_formula_tags,
    _in_figure,
    _same_column_cluster,
)

SEC = dict(ncomp=1, bare=True, scope=3)


def _num(raw, page, x, y, w=30.0, h=27.0):
    return {"kind": "text", "text": raw, "page": page,
            "x": x, "x1": x + w, "y": y, "bottom": y + h}


def _formula(page, x=60.0, x1=960.0, y=100.0, bottom=300.0):
    return {"kind": "formula", "formula": "\\begin{array}{l}a=b\\\\c=d\\end{array}",
            "display": True, "page": page,
            "x": x, "x1": x1, "y": y, "bottom": bottom}


def _image(page, x, y, x1, bottom):
    return {"kind": "image", "page": page, "x": x, "x1": x1,
            "y": y, "bottom": bottom, "file": "figure/x.png"}


def _attached(out):
    return [(str(b["tag"]), [str(t) for t in (b.get("tags") or [])])
            for b in out if b.get("kind") == "formula" and "tag" in b]


class TestFigureAreaNumbers(unittest.TestCase):
    def test_axis_ticks_inside_figure_are_not_tags(self):
        # p407 形态：展示式与 10..50 一并落在图 bbox 内
        blocks = [_image(407, 295, 711, 931, 1113),
                  _formula(407, x=460, x1=940, y=980, bottom=1040),
                  _num("40", 407, 789, 1000), _num("50", 407, 900, 1002)]
        out = _attach_formula_tags(blocks, claimed=set(), **SEC)
        self.assertEqual(_attached(out), [],
                         "图区内的轴刻度被挂成公式编号")
        left = [b.get("text") for b in out if b.get("kind") == "text"]
        self.assertIn("40", left, "被拒的数字块应留在正文流")

    def _in(self, blk, boxes):
        return _in_figure(blk, boxes)

    def test_margin_number_outside_figure_still_attaches(self):
        blocks = [_image(407, 295, 711, 931, 1113),
                  _formula(407, x=60, x1=960, y=200, bottom=320),
                  _num("3", 407, 900, 250)]
        out = _attach_formula_tags(blocks, claimed=set(), **SEC)
        self.assertEqual([t for t, _ in _attached(out)], ["3"])

    def test_helper_geometry(self):
        box = [(295.0, 711.0, 931.0, 1113.0)]
        self.assertTrue(_in_figure({"x": 789, "x1": 821, "y": 1000,
                                    "bottom": 1027}, box))
        self.assertFalse(_in_figure({"x": 900, "x1": 930, "y": 250,
                                     "bottom": 277}, box))


class TestSameColumnBundle(unittest.TestCase):
    def test_cross_column_fragments_dropped_margin_column_kept(self):
        # p262 形态：真编号 (54) 在最右列，3 / 8 / 2n 是 array 内部碎片
        hits = [(_num("3", 262, 520, 150), "3", 520.0),
                (_num("8", 262, 540, 210), "8", 540.0),
                (_num("54", 262, 900, 260), "54", 900.0)]
        kept = _same_column_cluster(hits, 60.0, 960.0)
        self.assertEqual([n for _, n, _tx in kept], ["54"])

    def test_legit_consecutive_column_bundle_survives(self):
        hits = [(_num("1", 300, 900, 120), "1", 900.0),
                (_num("2", 300, 902, 240), "2", 902.0)]
        kept = _same_column_cluster(hits, 60.0, 960.0)
        self.assertEqual([n for _, n, _tx in kept], ["1", "2"],
                         "同列逐行编号的多号捆绑被误杀")

    def test_left_margin_book_anchors_on_left_column(self):
        hits = [(_num("7", 100, 10, 150), "7", 10.0),
                (_num("2", 100, 600, 200), "2", 600.0)]
        kept = _same_column_cluster(hits, 100.0, 960.0)
        self.assertEqual([n for _, n, _tx in kept], ["7"],
                         "左缘编号书的左列应胜出（离版心中点更远）")

    def test_end_to_end_bundle_is_pruned(self):
        blocks = [_formula(262, x=60, x1=960, y=100, bottom=320),
                  _num("3", 262, 520, 150), _num("8", 262, 540, 210),
                  _num("54", 262, 900, 260)]
        out = _attach_formula_tags(blocks, claimed=set(), **SEC)
        self.assertEqual(_attached(out), [("54", [])],
                         "跨列碎片仍被捆进 tags")

    def test_parenthesized_wins_over_bare_in_same_column(self):
        # 实测 p262：(52)(53)(54) 与 array 内 3/8 的分子分母**同在右缘一列**，
        # 列聚类分不开——delimiter 是唯一与本书版式一致的证据。
        blocks = [_formula(262, x=135, x1=1059, y=807, bottom=1011),
                  _num("3", 262, 1034, 869, w=10), _num("8", 262, 1032, 900, w=18),
                  _num("(54)", 262, 1028, 1005, w=52)]
        out = _attach_formula_tags(blocks, claimed=set(), **SEC)
        self.assertEqual(_attached(out), [("54", [])],
                         "同列裸排碎片压过了带括号真编号")

    def test_bare_only_book_unaffected(self):
        blocks = [_formula(120, x=60, x1=960, y=100, bottom=140),
                  _num("12", 120, 900, 108)]
        out = _attach_formula_tags(blocks, claimed=set(), **SEC)
        self.assertEqual([t for t, _ in _attached(out)], ["12"],
                         "全书裸排编号的书被 delimiter 规则误伤")


if __name__ == "__main__":
    unittest.main(verbosity=2)
