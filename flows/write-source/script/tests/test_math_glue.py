"""Regression tests: 第 17 项行内公式边界粘连闸（math_glue_problems）。

Weibel ch8 实测场景（2026-09-24）：OCR 原样「maps$C_n \\to C_{n-1}$are」「证明当
$n \\neq 0$时」式粘连逃过全部既有检测流入合并 md。锁死：粘连判 FAIL；合法形态
（`$k$-module`、`$X$;`、`“$n$-胞腔”`、`($i$`、`$$` 围栏）不误伤。
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, str(Path(_ROOT) / "flows" / "write-source" / "script"))

import check_unit_quality as cuq  # noqa: E402


class TestMathGlue(unittest.TestCase):
    def test_en_glue_before_after(self):
        self.assertTrue(cuq.math_glue_problems(
            "the boundary maps$C_n \\to C_{n-1}$are alternating sums"))

    def test_en_hyphenated_forms_pass(self):
        for ok in ["is a $k$-module and an $R$-$R$ bimodule",
                   "the $n$-simplex $\\Delta_n$",
                   "space $X$; elements of $C_n(X)$ are",
                   "equal to $k$) and ($i$ and $j$ not",
                   "See $\\Delta[1]$（8.2.4）"]:
            self.assertEqual(cuq.math_glue_problems(ok), [], ok)

    def test_en_ordinal_and_function_exempt(self):
        for ok in ["the $p$th exterior power of $\\Lambda^p R$",
                   "the $(n-1)$st syzygy of every module",
                   "The $2p$th column gives Tsygan's truncation",
                   "the quotient complex denoted $\\ker(f)$, and coker$(f_n)$ assemble",
                   "The category Sheaves$(X)$ of sheaves forms"]:
            self.assertEqual(cuq.math_glue_problems(ok), [], ok)

    def test_ordinal_exempt_does_not_hide_real_glue(self):
        # 序数豁免只放行 after 侧后缀；before 侧真粘连仍要抓
        self.assertTrue(cuq.math_glue_problems("maps$A_n$th power"))
        self.assertTrue(cuq.math_glue_problems("exact couple$\\varepsilon$ and"))

    def test_cn_han_glue(self):
        self.assertTrue(cuq.math_glue_problems("证明当$n \\neq 0$时$\\Delta[n]$不是纤维化的"))

    def test_cn_han_spaced_pass(self):
        self.assertEqual(cuq.math_glue_problems(
            "证明当 $n \\neq 0$ 时 $\\Delta[n]$ 不是纤维化的。"), [])

    def test_cn_quote_glue_exempt(self):
        # 中文弯引号紧贴公式 = 引号起项，合法（closing-quote 粘连暂不判）
        self.assertEqual(cuq.math_glue_problems("我们需要一个类比于“$\\perp$-投射”的概念"), [])

    def test_display_fence_and_odd_lines_skipped(self):
        self.assertEqual(cuq.math_glue_problems("$$\n\\alpha\\beta\n$$"), [])
        self.assertEqual(cuq.math_glue_problems("cat-$\\mathcal{A}$ unbalanced $x"), [])

    def test_check_body_flags_glue(self):
        ok, probs = cuq.check_body("desc", "d", "maps$C_n \\to C_{n-1}$are sums")
        self.assertFalse(ok)
        self.assertTrue(any("粘连" in p for p in probs))

    def test_check_body_glue_on_exercise(self):
        ok, probs = cuq.check_body("exercise", "ex", "**Exercise 1.1**: show $x$if...")
        self.assertFalse(ok)
        self.assertTrue(any("粘连" in p for p in probs))


if __name__ == "__main__":
    unittest.main()
