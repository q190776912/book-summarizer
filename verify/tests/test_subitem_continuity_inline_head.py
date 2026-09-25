"""
test_subitem_continuity_inline_head.py — O 层「行内子项标记」HEAD 缺号假报回归
（Gelfand–Manin《Methods of Homological Algebra》ch1 / ch2 / ch4 习题实测）。

三类同一个盲点：三条检测正则全是**行首锚定**，因此写在 item header 同一行里的
`a)` 对本层完全不可见，后一条独占一行的 `b)` 就被当成序列开头 → 报「HEAD gap，
缺 (a)」，而 (a) 其实就印在上一行 header 后面。

    ch2  **1. Limits in Abelian Categories**: a) Prove that the kernel …
    ch1  3. Affine Schemes. a) Let $A$ be a commutative unitary ring …
    ch4  **3. Massey 积 (Massey product)。** a) 设 $\\mathcal{D}$ 是三角范畴 …

ch1 另叠加第二个盲点：`['3','b','c','d','e']` 是异质块，`_classify_block` 把字母项
归零丢弃（`mixed` 时整块丢弃），于是 a)…e) 从「前文已见」集合里消失；中间的公式块
把行距撑到 >4 使 `f)` 另起一块，该块便凭空「缺 a、b、c、d、e」。

修复（两处，**都只作用于抑制路径，结构上不可能新增告警**）：
* `_label_ordinals` —— 块内每个标签按数字/字母/罗马全部合理解读补进 `block_meta['ords']`；
* `_o_inline_ordinals` —— 行内 `a)` / `(a)` 标记单独收集，按 120 行窗口并入 HEAD 抑制集合。

负向（必须仍然报错，否则本层失去意义）：真正的缺项（(a) 从未以任何形态出现、
附着回指 `2.1.3(a)` 不算标记）依旧报 HEAD gap；INTERNAL 缺号不受行内标记影响。
"""
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
import lib.boot as _boot
_boot.setup()

from subitem_continuity import (
    _o_inline_ordinals, _label_ordinals, check_ordinal_subitem_gaps,
)


def _gaps(md_text):
    d = tempfile.mkdtemp()
    p = os.path.join(d, 'ch1.md')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(md_text)
    return check_ordinal_subitem_gaps(p)


class InlineOrdinalTest(unittest.TestCase):
    def test_bare_marker_after_header_seen(self):
        self.assertIn(1, _o_inline_ordinals(
            "**1. Limits in Abelian Categories**: a) Prove that the kernel of "
            "morphisms $f, g : X \\to Y$ is an equalizer."))

    def test_cn_fullwidth_and_plain_numbered_header(self):
        self.assertIn(1, _o_inline_ordinals(
            "**3. Massey 积 (Massey product)。** a) 设 $\\mathcal{D}$ 是三角范畴。"))
        self.assertIn(1, _o_inline_ordinals(
            "3. Affine Schemes. a) Let $A$ be a commutative unitary ring."))

    def test_glued_crossref_not_counted(self):
        # 附着回指（紧贴字母/数字）与句读收尾的行文回指都不算子项标记。
        self.assertEqual(_o_inline_ordinals(
            "one proves exactness (see II.6.18a)."), set())
        self.assertEqual(_o_inline_ordinals(
            "Prove that $r _ { U V }$ depends only on $U$ (compare a), (i))."),
            set())


class LabelOrdinalsTest(unittest.TestCase):
    def test_multi_interpretation_union(self):
        self.assertEqual(_label_ordinals('3'), {3})
        self.assertEqual(_label_ordinals('c'), {3, 100})   # alpha 3 / roman 100
        self.assertEqual(_label_ordinals('ii'), {2, 243})  # roman 2 / alpha 'ii' 243


class HeadGapBookCasesTest(unittest.TestCase):
    def test_bold_header_inline_a_no_gap(self):
        md = ("# Chapter 2\n\n"
              "**Exercises**:\n\n"
              "**1. Limits in Abelian Categories**: a) Prove that the kernel of "
              "morphisms $f, g : X \\to Y$ coincides with the equalizer.\n\n"
              "The existence of infinite limits imposes additional restrictions.\n\n"
              "b) Let $I$ be some set of indices. Define the category $\\mathcal{A}^{I}$.\n\n"
              "c) Formulate dual axioms.\n\n"
              "d) Prove that the category $\\mathcal{A}b$ satisfies AB4.\n")
        self.assertEqual(_gaps(md), [])

    def test_heterogeneous_block_ords_suppress_later_head(self):
        # a) 与数字 header 同行；b)…e) 同块（异质，曾被整块作废）；公式块撑开行距，
        # 使 f) 起新块 —— 旧实现在这里报「缺 a、b、c、d、e」。
        md = ("# Chapter 1\n\n"
              "3. Affine Schemes. a) Let $A$ be a commutative unitary ring.\n\n"
              "b) Let $S \\subseteq A$ be a multiplicatively closed subset.\n\n"
              "c) Prove that $A _ { f }$ depends only on $D ( f )$.\n\n"
              "d) Let $V = D ( g ) \\subset U = D ( f )$. Define $r _ { U V }$.\n\n"
              "$$\nr _ { V W } \\circ r _ { U V } = r _ { U W }\n$$\n\n"
              "e) Prove that there exists a unique sheaf of rings.\n\n"
              "$$\n\\left\\{ s _ { i } \\in A _ { f _ { i } } \\mid x = y \\right\\}\n$$\n\n"
              "f) Prove that the stalk of $\\mathcal{O}$ at $p$ is $A _ { p }$.\n\n"
              "g) Let $M$ be an $A$-module.\n\n"
              "h) Prove that there exists a unique sheaf of modules.\n\n"
              "i) Let $\\tilde{M} _ { 1 }, \\tilde{M} _ { 2 }$ be quasicoherent.\n")
        self.assertEqual(_gaps(md), [])


class StillReportedTest(unittest.TestCase):
    """负向：真缺号不许被这次放宽吃掉。"""

    def test_real_head_gap_still_reported(self):
        md = ("### Remarks\n\n"
              "b) This one is present.\n\n"
              "c) And this one.\n\n"
              "d) And this one.\n")
        got = _gaps(md)
        self.assertEqual(len(got), 1)
        self.assertTrue(got[0].strip().startswith('x'))
        self.assertIn('HEAD gap', got[0])
        self.assertIn('missing (a)', got[0])

    def test_inline_marker_elsewhere_does_not_hide_internal_gap(self):
        # 行内标记只进 HEAD 抑制窗口；INTERNAL 缺号（此处 c)）照旧要报。
        md = ("### Remarks\n\n"
              "1. Setup, cf. a) below.\n\n"
              "prose\n\nprose\n\nprose\n\n"
              "a) first.\n\n"
              "b) second.\n\n"
              "d) fourth — c) is genuinely missing.\n")
        got = _gaps(md)
        self.assertTrue(any('INTERNAL gap' in g for g in got), got)


if __name__ == '__main__':
    unittest.main()
