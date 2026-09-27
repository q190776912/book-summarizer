# -*- coding: utf-8 -*-
"""Regression: same-page item order when the contract key carries NO label word.

Strogatz《Nonlinear Dynamics and Chaos》3e (2026-09-27 实测, ch6 §6.8 / ch7 §7.2):
键形是裸号 `6.8-1` / `7.2-3`，条目的计数器身份只住在节点的 ``type``
（theorem / example）上。``_sort_doc_order`` 的旧实现用 **key 的数字前缀** 判
「同标签 / 异标签」——两个裸号前缀同为空串，于是被当成同一条计数器而走数字序，
跨计数器的 y 裁决分支**永远进不去**：

    p211  Example 6.8.4 (y=474)  →  Theorem 6.8.1 (y=581)   [印面顺序]
    契约  Theorem 6.8.1 (1<4)    →  Example 6.8.4           [旧输出，反了]
    p238  Theorem 7.2.3 (y=716)  →  Example 7.2.1 (y=1272)  [印面顺序]
    契约  Example 7.2.1          →  Theorem 7.2.3 (3>1)     [旧输出，反了]

merge 按 manifest（= 契约文档序）拼接，于是最终 md 与书不同序，读者按题号回查跳页。

Fix under test: ``_item_counter_label``（键前缀为空时回退到 ``type``）+
``_item_order_cmp``（提为模块级纯函数，可脱离 build_chapter 闭包单测）。
共享计数器语义（test_shared_counter_doc_order.py）不变：显式组内仍走数字序。

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_item_order_cross_counter.py
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

from build_structure import _item_counter_label, _item_order_cmp  # noqa: E402
from key_parse import _canon_label  # noqa: E402


def ymap(**ys):
    """→ ``y_of(node)``：按 `type-key` 查预置 y（模拟源页锚定）。"""
    def _f(node):
        return ys.get("%s-%s" % (node.get("type"), node.get("key")))
    return _f


def node(typ, key, page):
    return {"type": typ, "key": key, "page_start": page, "page_end": page}


# 显式共享计数器组（canon 后的标签 → 组下标），等价于 _label_group_index 的输出
SHARED = {_canon_label(k): 0 for k in ("theorem", "example", "definition")}


class TestCounterLabelOfBareKey(unittest.TestCase):
    def test_key_prefix_wins(self):
        self.assertEqual(_item_counter_label({"key": "Remark 5.5-1", "type": "example"}),
                         "Remark ")

    def test_bare_key_falls_back_to_type(self):
        self.assertEqual(_item_counter_label({"key": "6.8-1", "type": "theorem"}),
                         "theorem")


class TestStrogatzCrossCounter(unittest.TestCase):
    """裸号键 + 各自起号（无显式组）→ 异计数器对按锚定 y。"""

    def test_theorem_after_later_numbered_example(self):
        thm = node("theorem", "6.8-1", 211)
        ex = node("example", "6.8-4", 211)
        y = ymap(**{"theorem-6.8-1": 581.0, "example-6.8-4": 474.0})
        self.assertEqual(_item_order_cmp(thm, ex, y), 1,
                         "Theorem 6.8.1 印面在 Example 6.8.4 之后，不得按数字抢前")
        self.assertEqual(_item_order_cmp(ex, thm, y), -1)

    def test_theorem_before_example_its_number_is_larger(self):
        thm = node("theorem", "7.2-3", 238)
        ex = node("example", "7.2-1", 238)
        y = ymap(**{"theorem-7.2-3": 716.0, "example-7.2-1": 1272.0})
        self.assertEqual(_item_order_cmp(thm, ex, y), -1,
                         "Theorem 7.2.3 印面在 Example 7.2.1 之前")

    def test_same_counter_still_numeric_when_y_is_crossed(self):
        # 同计数器（两个 example）：交叉引用误锚的 y 不得翻案（Kreyszig 语义）
        a = node("example", "6.8-4", 211)
        b = node("example", "6.8-5", 211)
        y = ymap(**{"example-6.8-4": 900.0, "example-6.8-5": 300.0})
        self.assertEqual(_item_order_cmp(a, b, y), -1)

    def test_page_wins_over_y(self):
        a = node("theorem", "6.8-2", 212)
        b = node("example", "6.8-3", 209)
        self.assertEqual(_item_order_cmp(a, b, ymap()), 1)

    def test_missing_y_both_falls_back_to_numeric(self):
        thm = node("theorem", "6.8-1", 211)
        ex = node("example", "6.8-4", 211)
        self.assertEqual(_item_order_cmp(thm, ex, ymap()), -1,
                         "两条都锚不到 y 时退回旧数字序（保守，不赌随机序）")


class TestSharedCounterPreserved(unittest.TestCase):
    def test_explicit_group_number_order_beats_y(self):
        thm = node("theorem", "2.1", 401)
        ex = node("example", "2.6", 401)
        y = ymap(**{"theorem-2.1": 900.0, "example-2.6": 100.0})
        self.assertEqual(_item_order_cmp(thm, ex, y, SHARED), -1,
                         "共享一条计数器（do Carmo 黎曼几何）：数字序即阅读序")

    def test_dedup_of_equal_keys_is_tie(self):
        a = node("example", "6.8-4", 211)
        b = node("example", "6.8-4", 211)
        self.assertEqual(_item_order_cmp(a, b, ymap()), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
