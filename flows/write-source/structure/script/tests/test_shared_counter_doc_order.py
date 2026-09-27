# -*- coding: utf-8 -*-
"""Regression: same-page CROSS-label item order for shared-counter books.

do Carmo《黎曼几何》(Riemannian Geometry, 2026-09-27 实测): every section
prints ONE ascending counter shared by all labels, number-first
("2.1 DEFINITION", "2.2 PROPOSITION", "2.6 PROPOSITION", "3.3 COROLLARY",
"3.4 DEFINITION").  `_sort_doc_order._item_order_cmp` compared cross-label
same-page pairs by anchored y, which mis-anchors on dense mixed pages (a
cross-reference block beats the real head), producing adjacent swaps
([2, 1, ...], [2.6, 2.5], [3.4, 3.3]) that the B-layer gate rejects as
ORDERING BLOCKING in 13/14 chapters.

Fix under test: `_label_group_index` (explicit ordinal group membership,
uncat skipped) + `_cross_label_order` — labels in the SAME explicit group
share one counter, so number order IS reading order; different groups
(parallel per-label counters, e.g. do Carmo《曲线曲面》) keep the y order.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_shared_counter_doc_order.py
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

from build_structure import _cross_label_order, _label_group_index  # noqa: E402
from verify_config import GroupConfig  # noqa: E402


def _g(labels, uncat=False, typ=2, scope=3):
    return GroupConfig(type=typ, name=(["uncat"] if uncat else labels),
                       scope=scope)


class TestLabelGroupIndex(unittest.TestCase):
    def test_explicit_groups_and_uncat_skip(self):
        groups = _label_group_index([
            _g(["Definition", "Proposition", "Theorem"]),
            _g(["Figure", "Fig"], typ=1, scope=1),
            _g([], uncat=True),
        ])
        self.assertEqual(groups[_canon("Definition")], 0)
        self.assertEqual(groups[_canon("Proposition")], 0)
        self.assertEqual(groups[_canon("Figure")], 1)
        self.assertNotIn(_canon("Axiom"), groups)

    def test_bilingual_canon(self):
        groups = _label_group_index([_g(["Definition", "Theorem"])])
        # 契约键用中文 canon 标签（定义2.1），组名是英文——必须同组命中
        self.assertEqual(groups[_canon("定义")], groups[_canon("Theorem")])


def _canon(lbl):
    from key_parse import _canon_label
    return _canon_label(lbl)


class TestCrossLabelOrder(unittest.TestCase):
    SHARED = _label_group_index([
        _g(["Definition", "Proposition", "Theorem", "Corollary",
            "Remark", "Example", "Lemma"]),
        _g(["Figure", "Fig"], typ=1, scope=1),
    ])
    PARALLEL = _label_group_index([
        _g(["Definition"]), _g(["Proposition"]), _g(["Example"]),
    ])

    def test_shared_counter_number_order_beats_bad_y(self):
        # 2.2 误锚到更小的 y（交叉引用块）：共享计数器书仍按号序 2.1 < 2.2
        r = _cross_label_order("Definition", "Proposition",
                               (2, 1), (2, 2), 500.0, 300.0, self.SHARED)
        self.assertEqual(r, -1)

    def test_shared_counter_negative_no_inversion(self):
        # 真头 y 序与号序一致时结论不变（不引入反向错误）
        r = _cross_label_order("Proposition", "Definition",
                               (2, 6), (2, 5), 100.0, 600.0, self.SHARED)
        self.assertEqual(r, 1, "2.6 不得排到 2.5 之前，即使其 y 更小")

    def test_parallel_groups_keep_y_order(self):
        # 不同组 = 各自独立计数器：数字不可比，y 说 3.4 在 3.3 前先出现
        r = _cross_label_order("Definition", "Corollary",
                               (3, 4), (3, 3), 100.0, 600.0, self.PARALLEL)
        self.assertEqual(r, -1, "并行计数器书必须维持 y 锚序")

    def test_unknown_label_falls_back_to_y(self):
        # 未入显式组（落 uncat）→ 旧 y 行为，不赌数字序
        r = _cross_label_order("Axiom", "Definition",
                               (1, 9), (2, 1), 700.0, 100.0, self.SHARED)
        self.assertEqual(r, 1)

    def test_missing_y_goes_last(self):
        r = _cross_label_order("Axiom", "Definition",
                               (1, 1), (1, 2), None, 100.0, self.SHARED)
        self.assertEqual(r, 1, "y 缺失按页末（+inf）排后")

    def test_shared_equal_number_is_tie(self):
        r = _cross_label_order("Definition", "Proposition",
                               (2, 2), (2, 2), None, None, self.SHARED)
        self.assertEqual(r, 0)

    def test_cn_canon_labels_match_en_groups(self):
        # 契约中文 canon 键（定义/命题）经共享组判定为数字序
        r = _cross_label_order("定义", "命题", (2, 1), (2, 2),
                               500.0, 300.0, self.SHARED)
        self.assertEqual(r, -1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
