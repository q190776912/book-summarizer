# -*- coding: utf-8 -*-
"""B 层「缺号」的序标占用豁免（共享计数器 / 序标被节标题占用，2026-09-28）。

根因（Apostol《Introduction to Analytic Number Theory》实测，两章两种形态）：
  1. ch7 同章 **Theorem 与 Lemma 共用一条章内计数器**：印刷 定理7.1/7.2/7.3、
     引理7.4…7.8、定理7.9/7.10。B 层按标签分桶 → Theorem 桶报「缺号 4..8」、
     Lemma 桶报「缺号 1..3」，全是假缺号（该序标在契约另有节点）。
  2. ch12 印 §12.11「Evaluation of …」，条目序列 12.10 → 12.12：序标 12.11 被
     **节标题**占用，书中本无 Theorem 12.11。
旧实现只能靠 `ignore_ch7.json` / `ignore_ch12.json` 手工登记（人说了算）。现由
`ordinal_occupancy_sets` + `occupied_ordinal` 依契约账目机械判定，并一律登记进
`gate.b_gap_ordinal_occupancy` 留痕。

安全网（本测试负向部分）：源侧差集若在该序标报出 `readable` 遗漏（= 印刷条头存在
而契约无账），**绝不豁免**，闸门照拦。

运行：
  python verify/script/tests/test_ordinal_occupancy_gap.py
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "verify", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import check_structure_completeness as csc  # noqa: E402
from data.book_structure.book_structure import StructureNode  # noqa: E402

_BLOCK_FMT = "  WARN (BLOCKING): %s:%d 缺号 %d（序列 1..10 不连续 — 严格模式）"


def _node(key, ntype, *kids):
    return StructureNode(key=key, type=ntype, name=key, sub_sec=list(kids))


def _ch7_tree():
    """定理7.1-7.3 + 引理7.4-7.8 + 定理7.9-7.10，节 7.1/7.9。"""
    items = [_node("定理7.%d" % n, "theorem") for n in (1, 2, 3, 9, 10)]
    items += [_node("引理7.%d" % n, "lemma") for n in (4, 5, 6, 7, 8)]
    return _node("7", "chapter",
                 _node("7.1", "section"), _node("7.9", "section"), *items)


def _ch12_tree():
    """条目 12.10 → 12.12，序标 12.11 由节标题占用。"""
    return _node("12", "chapter",
                 _node("12.10", "section"), _node("12.11", "section"),
                 _node("定理12.10", "theorem"), _node("定理12.12", "theorem"))


def _sets(tree, miss=None):
    tree.type = "chapter"          # _PRIMARY 需按方案归一
    return csc.ordinal_occupancy_sets(tree, miss or [])


class TestSharedCounterItemAlias(unittest.TestCase):
    """形态①：异标签条目在账 = 共享计数器，不是缺号。"""

    def test_theorem_gap_occupied_by_lemma(self):
        csc._PRIMARY = csc.ORDINAL_TWO_LEVEL
        occ_items, occ_secs, gap_left = _sets(_ch7_tree())
        for n in (4, 5, 6, 7, 8):
            msg = _BLOCK_FMT % (0, 7, n)
            self.assertEqual(
                csc.occupied_ordinal(msg, occ_items, occ_secs, gap_left), "item",
                "定理桶的缺号 %d 由引理 %d.%d 在账，须豁免" % (n, 7, n))

    def test_lemma_gap_occupied_by_theorem(self):
        csc._PRIMARY = csc.ORDINAL_TWO_LEVEL
        occ_items, occ_secs, gap_left = _sets(_ch7_tree())
        for n in (1, 2, 3):
            msg = _BLOCK_FMT % (2, 7, n)
            self.assertEqual(
                csc.occupied_ordinal(msg, occ_items, occ_secs, gap_left), "item")


class TestSectionAlias(unittest.TestCase):
    """形态②：序标被节标题占用。"""

    def test_section_head_occupies_ordinal(self):
        csc._PRIMARY = csc.ORDINAL_TWO_LEVEL
        occ_items, occ_secs, gap_left = _sets(_ch12_tree())
        self.assertIn("12.11", occ_secs)
        self.assertEqual(
            csc.occupied_ordinal(_BLOCK_FMT % (0, 12, 11),
                                 occ_items, occ_secs, gap_left), "section")


class TestGenuineGapStillBlocks(unittest.TestCase):
    """负向：账上无此序标 / 源侧报出可读遗漏 / 非缺号消息 → 一律不豁免。"""

    def test_unoccupied_number_is_not_exempt(self):
        csc._PRIMARY = csc.ORDINAL_TWO_LEVEL
        occ_items, occ_secs, gap_left = _sets(_ch7_tree())
        self.assertIsNone(
            csc.occupied_ordinal(_BLOCK_FMT % (0, 7, 12),
                                 occ_items, occ_secs, gap_left),
            "7.12 在契约无任何账（该章只到 7.10），须照拦")

    def test_readable_source_gap_wins_over_occupancy(self):
        """印刷条头存在而契约无账：差集报 readable → 序标虽被他节点占用也不豁免。"""
        csc._PRIMARY = csc.ORDINAL_TWO_LEVEL
        tree = _node("12", "chapter", _node("12.11", "section"))
        miss = [{"canon": [12, 11], "status": "readable", "key": "Theorem 12.11"}]
        occ_items, occ_secs, gap_left = _sets(tree, miss)
        self.assertEqual(gap_left, {(12, 11)})
        self.assertIsNone(
            csc.occupied_ordinal(_BLOCK_FMT % (0, 12, 11),
                                 occ_items, occ_secs, gap_left),
            "源侧看得见、契约没有 = 真漏抽，不得借节号豁免")

    def test_non_string_and_other_messages_pass_through(self):
        csc._PRIMARY = csc.ORDINAL_TWO_LEVEL
        occ_items, occ_secs, gap_left = _sets(_ch7_tree())
        self.assertIsNone(csc.occupied_ordinal(
            {"exercise_block_only": True}, occ_items, occ_secs, gap_left))
        self.assertIsNone(csc.occupied_ordinal(
            "ORDERING BLOCKING: 条目 7.5 顺序错乱", occ_items, occ_secs, gap_left))
        self.assertIsNone(csc.occupied_ordinal(
            "0:7 缺号 x（数字畸形）", occ_items, occ_secs, gap_left))


class TestThreeLevelShapeUnaffected(unittest.TestCase):
    """三级书（C.S-N）的缺号消息按完整 canon 比对，不得被同号节/条目误豁免。"""

    def test_three_level_canon_match(self):
        csc._PRIMARY = csc.ORDINAL_THREE_LEVEL
        tree = _node("4", "chapter",
                     _node("4.1.2", "theorem"), _node("4.1", "section"))
        occ_items, occ_secs, gap_left = _sets(tree)
        self.assertEqual(
            csc.occupied_ordinal("  WARN (BLOCKING): 4.1 缺号 2（序列不连续）",
                                 occ_items, occ_secs, gap_left), "item")
        self.assertIsNone(
            csc.occupied_ordinal("  WARN (BLOCKING): 4.1 缺号 9（序列不连续）",
                                 occ_items, occ_secs, gap_left))


if __name__ == "__main__":
    unittest.main(verbosity=2)
