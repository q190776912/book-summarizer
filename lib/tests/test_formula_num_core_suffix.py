# -*- coding: utf-8 -*-
"""单段编号（ncomp<=1）不收字母后缀（Apostol《Introduction to Analytic Number
Theory》ch11 实测 2026-09-28）。

根因：`formula_num_core` 无差别给所有段数挂上 `_FORMULA_SUFFIX`，于是印刷把
ζ(2s) 一类公式**截断成独立块**的 `(2s)`/`(6s)`（p243 [301,1504,347]、p253
[797,1506,849]、p259 [220,1164,282] / [606,1253,661]，同行还有
`k(n) _ (s)(2s)x(3s)`、`1-p-2s`、`²(s)`）被当成公式序标真值收下 → 内容完整性
闸门报「公式编号丢失 ['6s']」（176 条幻影同类）。契约 tag 是 `gate_units` 的
对账真值，收下它们等于逼写手凭空写 `\tag{2s}`。

实测语料里子式后缀编号（`(8.11a)`）**只出现在多段体例**（ncomp>=2：Evans
SDE/PDE、Koopman、Ross、A First Course in Numerical Methods、Chaos/Fractals/
Noise）；《数学分析》type=1 的 `['0x','1D','2M','3w','4m','9x']` 与本书同病。
故判据：ncomp<=1 时后缀一律不收；ncomp=None（未配置，走
`formula_tag_shape_ok` 的 ≥2 段形态闸）与 `letter=True`（字母章位）分支不变。

运行：
  python lib/tests/test_formula_num_core_suffix.py
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

from lib.numbering import (formula_num_core, formula_tag_number, formula_tag_re,
                           formula_trailing_tag)


class SingleSegmentRejectsSuffix(unittest.TestCase):
    def test_plain_single_segment_still_accepted(self):
        for t in ("(1)", "(26)", "（7）", "(1)"):
            self.assertEqual(formula_tag_number(t, ncomp=1), t.strip("()（）"),
                             "单段纯数字编号是本书真形态，不许受影响")

    def test_bare_single_segment_still_accepted(self):
        self.assertEqual(formula_tag_number("12", ncomp=1, bare=True), "12")

    def test_fragment_with_letter_suffix_rejected(self):
        for t in ("(2s)", "(6s)", "(9x)", "(0j)", "（1D）", "2s", "6s"):
            self.assertIsNone(formula_tag_number(t, ncomp=1),
                              "%r 是公式碎片截断块，不是序标" % t)

    def test_regex_source_has_no_suffix_group(self):
        self.assertNotIn("[a-zA-Z]", formula_num_core(1))
        self.assertNotIn("[a-zA-Z]", formula_num_core(0))
        self.assertIn("[a-zA-Z]", formula_num_core(2), "多段须继续接受子式后缀")
        self.assertIn("[a-zA-Z]", formula_num_core(None), "未配置分支不变")

    def test_letter_chapter_branch_unchanged(self):
        self.assertEqual(formula_tag_number("(B.4)", ncomp=2, letter=True), "B.4")
        self.assertIsNone(formula_tag_number("(A)", ncomp=1, letter=True),
                          "纯单字母不是序标")

    def test_trailing_tag_same_semantics(self):
        # 行尾编号：单段仍收纯数字、不收字母后缀
        got = formula_trailing_tag("\\zeta(2) = \\pi^2/6  (3)", ncomp=1)
        self.assertEqual((got[0] if isinstance(got, tuple) else got), "3")
        self.assertIsNone(formula_trailing_tag("k(n) (s)(2s)x(3s) (2s)", ncomp=1))

    def test_trailing_tag_adjacent_label_rejected(self):
        # Silverman《数论之美》ch15 实测 2026-10-03：σ(800000) 展示式分母
        # `(2-1)(5-1)` 被 OCR 读成独立块，尾 `(5-1)` 紧挨另一完整数字形标签
        # ——是公式内容，不是印刷编号（旧白名单 `)` 放行 → 幻影 tag `5-1`）。
        self.assertIsNone(formula_trailing_tag("(2-1)(5-1)", ncomp=None))
        self.assertIsNone(formula_trailing_tag("(2-1)(5-1)", ncomp=2))
        # 嵌套括号收尾的真例：前缀 `(x)` 非数字形标签，不受影响
        got = formula_trailing_tag("f(x))(3.5)", ncomp=2)
        self.assertEqual((got[0] if isinstance(got, tuple) else got), "3.5")


class MultiSegmentKeepsSuffix(unittest.TestCase):
    """子式后缀是真体例的书（ncomp>=2）零回归。"""

    def test_measured_suffix_forms(self):
        for txt, ncomp, want in (("(8.11a)", 2, "8.11a"),
                                 ("(18.10a)", 2, "18.10a"),
                                 ("(5.1.3b)", 3, "5.1.3b"),
                                 ("(11.1-1)", 3, "11.1-1"),
                                 ("(2.17)", 2, "2.17")):
            got = formula_tag_number(txt, ncomp=ncomp)
            self.assertEqual(got, want, "%s (ncomp=%s) 应配 %s，实得 %s"
                             % (txt, ncomp, want, got))

    def test_unconfigured_still_matches_suffix_form(self):
        self.assertEqual(formula_tag_number("(8.11a)", ncomp=None), "8.11a")


class CompiledRegexCachesStayConsistent(unittest.TestCase):
    def test_paren_only_variant(self):
        rx = formula_tag_re(1, bare=False)
        self.assertTrue(rx.match("(5)"))
        self.assertFalse(rx.match("5"))
        self.assertFalse(rx.match("(5s)"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
