# -*- coding: utf-8 -*-
"""裸字母子块标题词形闸：数学名词复合词开头的块题必须放行。

Arnold《经典力学的数学方法》§32 实测（2026-09-28）：印刷字母块题就是
「B.2-形式」「C.k-形式」这种**首字符不是汉字**的数学名词，旧判据（标题必须以
汉字起始）把 B/C 两块整块丢弃 → §32 只登记 D/E 两块窗口，B/C 两块的 例1..例3
挤进同一个计数器桶，跨块重号被吞，`ANCHOR-SANITY`（契约页码单调）直接 FAIL。

放行的形态必须**极窄**，否则散文/公式噪声会涌进来（同一实测里出现过的假阳性）：
  「R上的每一个k-形式…」  大写拉丁开头 + 句读
  「SDiffD上的右不变黎曼度量」 大写拉丁开头
  「m-1 个向量满足…」     数字-数字 + 空格
  「U=-#,」/「E=」          纯公式
Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_sub_global_math_noun_title.py
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

from scan_skeleton import _sub_global_title_ok as ok  # noqa: E402


class TestMathNounCompoundTitle(unittest.TestCase):
    def test_digit_leading_math_noun_accepted(self):
        self.assertTrue(ok("2-形式"), "「B.2-形式」的标题部分是数字开头的数学名词")

    def test_letter_leading_math_noun_accepted(self):
        self.assertTrue(ok("k-形式"), "「C.k-形式」同上")

    def test_han_leading_title_still_accepted(self):
        self.assertTrue(ok("两个1-形式的外乘积"))
        self.assertTrue(ok("变分"))


class TestNoiseStillRejected(unittest.TestCase):
    def test_uppercase_latin_leading_rejected(self):
        self.assertFalse(ok("R上的每一个k-形式"))
        self.assertFalse(ok("SDiffD上的右不变黎曼度量"))

    def test_space_or_punctuation_rejected(self):
        self.assertFalse(ok("m-1 个向量满足"))
        self.assertFalse(ok("k-形式，以及外微分"))
        self.assertFalse(ok("k-形式。"))

    def test_pure_formula_or_empty_rejected(self):
        self.assertFalse(ok("U=-#,"))
        self.assertFalse(ok("E="))
        self.assertFalse(ok("n-1"))
        self.assertFalse(ok(""))

    def test_overlong_math_noun_rejected(self):
        # 连字符后的汉字限长：散文里的「k-形式的全体构成…」不是块题。
        self.assertFalse(ok("k-形式的全体构成一个模"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
