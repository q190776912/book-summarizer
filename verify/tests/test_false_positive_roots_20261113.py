# -*- coding: utf-8 -*-
"""2026-11-13：两个仍活着的判据假阳根因，修复 + 反向锁。

B 层：m3 回退的引用动词是封闭白名单，`> **（2）利用引理3.89 过渡．**`
      这类表外动词会把交叉参照复活成条目 → 假「幽灵重复节点」。
Q 层：MISPLACED plain 支缺 ORDER 支已有的 `_reprint` 重述豁免；
      `_section_prefix_compatible` 遇字母/罗马章位节号退化成全等比较。
"""
import importlib.util
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

from item_numbering_integrity import _parse_entry  # noqa: E402


def _load(alias, rel):
    path = os.path.join(_ROOT, rel)
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


ft = _load("_test_formula_tag_fp", "verify/formula_tag/script/formula_tag.py")


class TestBCiteVerbGuard(unittest.TestCase):
    """扩词表 + 结构守卫必须挡住表外动词，且绝不吞真归因条头。"""

    def test_out_of_vocabulary_verb_is_rejected(self):
        """before/after 差分实测：这三条旧代码复活成条目，新代码拒绝。"""
        self.assertIsNone(_parse_entry('（2）利用引理2.5-4 过渡．', 3))
        self.assertIsNone(_parse_entry('（2）结合定理2.1.3 可知．', 3))
        self.assertIsNone(_parse_entry('（3）借助引理1.4.2 得证．', 3))

    def test_original_whitelist_verb_still_rejected(self):
        """负向锁：历史标本（由/见…）改前改后都必须拒绝。"""
        self.assertIsNone(_parse_entry('（2）由引理2.5-4 过渡．', 3))

    def test_real_attribution_header_is_kept(self):
        """最重要的反向锁：真条头「黎斯 (Riesz) 引理2.5-4」不得被吞。"""
        got = _parse_entry('黎斯 (Riesz) 引理2.5-4', 3)
        self.assertIsNotNone(got, '带归因括号的真实条头必须仍被解析')
        self.assertEqual(got[0], [2, 5, 4])

    def test_cn_attribution_paren_header_unchanged(self):
        """「（由 Banach）引理2.5-4」在改前就被括号深度守卫拒绝；
        锁定它不由本次改动引入任何新行为（既非误伤也非误放行）。"""
        self.assertIsNone(_parse_entry('（由 Banach）引理2.5-4', 3))

    def test_normal_numbered_header_is_kept(self):
        self.assertIsNotNone(_parse_entry('定理2.3.1', 3))


class TestSectionPrefixCompatible(unittest.TestCase):
    def test_numeric_ancestor_still_compatible(self):
        """纯数字路径逐字节等价（旧行为）。"""
        self.assertTrue(ft._section_prefix_compatible('1.3', '1.3.1'))
        self.assertTrue(ft._section_prefix_compatible('1.3.2', '1.3'))

    def test_numeric_real_misplacement_still_flagged(self):
        self.assertFalse(ft._section_prefix_compatible('1.4', '1.3'))
        self.assertFalse(ft._section_prefix_compatible('1.3.5', '1.3.2'))

    def test_letter_chapter_ancestor_now_compatible(self):
        """type 15/17：A.2 与 A.2.1 是祖孙，旧实现 ValueError → 全等 → 假 MISPLACED。"""
        self.assertTrue(ft._section_prefix_compatible('A.2', 'A.2.1'))
        self.assertTrue(ft._section_prefix_compatible('A.2.1', 'A.2'))

    def test_roman_chapter_ancestor_now_compatible(self):
        """type 16/18：II.1 与 II.1.3 同理。"""
        self.assertTrue(ft._section_prefix_compatible('II.1', 'II.1.3'))

    def test_non_numeric_real_misplacement_still_flagged(self):
        """反向锁：字母/罗马段不同节仍须照判，不能一律放行。"""
        self.assertFalse(ft._section_prefix_compatible('A.2', 'A.3'))
        self.assertFalse(ft._section_prefix_compatible('II.1', 'II.2'))
        self.assertFalse(ft._section_prefix_compatible('A.2', 'B.2'))

    def test_numeric_normalization_preserved(self):
        self.assertTrue(ft._seg_equal('1', '01'))
        self.assertFalse(ft._seg_equal('A', 'a'))


if __name__ == "__main__":
    unittest.main()
