# -*- coding: utf-8 -*-
"""`_load_sec_keys` 的账本必须**真的绑到 self**（2026-10-04 nonlinear ch13 根治）。

事故实测：并行改动在节键趟里写了一行裸名 `_ranges[str(key)] = (p0, p1)`，而账本
是 `self._sec_ranges`（函数开头刚初始化、`except` 里同样复位）。裸名 = 未定义名 →
`NameError` → 被本函数末尾的 `except Exception` **整段吞掉** → `_sec_keys` /
`_tail_exer_page` / `_tail_exer_anchor_y` 全部退回 `None`。🔴 后果是 fail-open 而非
报错：Q 层「章末集中习题页剔除」判据静默失效，Strogatz 第三版 ch13 的习题块
13.6.5 内印 `z(t)=α*(-iγ,t) (13)` / `r(K)=√(1-2γ/K) (14)` 被当成书真相集，而正文
忠实 `\tag` 止于 (13) → 双版各报 `Q-LAYER FORMULA MISSING (14)` 阻断（该书架此前
26/26 PASS，回归即由这一行造成）。

因此本测试只测一件事：**给定一份结构正常的契约，三个属性必须按契约取值**；
任何在节键趟里抛出的异常都会把它们打回 `None`，测试随即失败。
"""
import io
import json
import os
import sys
import tempfile
import unittest

_ROOT = os.environ.get("SKILL_ROOT") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "lib"))
import lib.boot as _boot
_boot.setup()

from formula_tag import SourceFormulaIndex  # noqa: E402


def _mk_book(pages=(50, 60)):
    """契约：§7.1(50-54) / §7.2(55-59)，章末 consolidated **习题节点**起于 p60。

    🔴 习题节点必须是 `type:'exercise'` 而非 `section`（与真实契约同形，见
    nonlinear ch13 的 `13.6.x`）：`last_sec_end` 只从 section 节点取，写成 section
    会让「习题页在最后一个正文节之后」的判据自己把它否掉。
    """
    d = tempfile.mkdtemp()
    bs = os.path.join(d, 'book_structure')
    os.makedirs(bs, exist_ok=True)
    tree = {'key': '7', 'type': 'chapter', 'name': 'Chapter 7', 'sub_sec': [
        {'key': '7.1', 'type': 'section', 'name': 'Introduction',
         'page_start': 50, 'page_end': 54, 'sub_sec': []},
        {'key': '7.2', 'type': 'section', 'name': 'Examples',
         'page_start': 55, 'page_end': 59, 'sub_sec': [
             {'key': '7.2.1', 'type': 'exercise', 'consolidated': True,
              'name': '(Ott-Antonsen ansatz) Equation (9) is an infinite-'
                      'dimensional nonlinear system that can be solved exactly.',
              'page_start': pages[1], 'sub_sec': []},
         ]},
    ]}
    with io.open(os.path.join(bs, 'ch7.json'), 'w', encoding='utf-8') as f:
        json.dump(tree, f, ensure_ascii=False)
    return d


def _index(d):
    return SourceFormulaIndex(d, [], chapter_prefix=True, ignore=set(), ncomp=3)


class SecLedgerBindingTest(unittest.TestCase):
    def test_sec_keys_are_populated_not_swallowed(self):
        """契约可读 ⇒ `_sec_keys` 必须是该章节键集合（None = 判据失明）。"""
        idx = _index(_mk_book())
        idx._load_sec_keys(7)
        self.assertIsNotNone(idx._sec_keys,
                             "_sec_keys=None：_load_sec_keys 内异常被吞，节判据已失效")
        self.assertTrue({'7.1', '7.2'} <= set(idx._sec_keys))

    def test_sec_ranges_ledger_bound_to_self(self):
        """🔴 本行即回归锁：section 节点带 int page_start ⇒ `self._sec_ranges` 在册。

        裸名 `_ranges[...]` 写法会在这里抛 `NameError` 并把三个属性一并打回 None。
        """
        idx = _index(_mk_book())
        idx._load_sec_keys(7)
        self.assertTrue(idx._sec_ranges,
                        "_sec_ranges 为空：节起始页账本没绑上 self")
        self.assertEqual(idx._sec_ranges.get('7.1'), (50, 54))
        self.assertEqual(idx._sec_ranges.get('7.2'), (55, 59))

    def test_tail_exercise_page_is_registered(self):
        """章末 consolidated 习题页 ⇒ `_tail_exer_page` 必须是那页（剔除判据的锚）。"""
        idx = _index(_mk_book())
        idx._load_sec_keys(7)
        self.assertEqual(idx._tail_exer_page, 60,
                         "_tail_exer_page 未登记 ⇒ 习题号列会进书真相集")

    def test_missing_contract_degrades_cleanly(self):
        """无契约 = 合法的降级路径（与改前一致），不得抛。"""
        idx = _index(tempfile.mkdtemp())
        idx._load_sec_keys(7)
        self.assertIsNone(idx._sec_keys)
        self.assertIsNone(idx._tail_exer_page)
        self.assertEqual(idx._sec_ranges, {})


if __name__ == '__main__':
    unittest.main()
