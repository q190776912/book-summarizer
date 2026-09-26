"""Regression tests: E 层「浮动图误挂」的**紧贴**判据（Kreyszig 2026-09-26 实测）。

旧实现只看「往前第一个带条号的块是不是 `>` 块」，于是**夹在散文/公式之后**的图
（节末 Problem Set 里的图、公式后面紧跟的插图）一律被判成「本该在那个 `>` 块里」——
而往前找到的那个块常常属于**上一个单元**。实测误伤：ch3 Fig. 24（习题 2 题面之后）、
ch4 Fig. 41/42（公式 (11)/(17) 之后）、ch4 Fig. 44（习题 15 之后）、ch6 Fig. 57/58。

根治后行为（本文件锁定）：
  1. 图块**紧贴** `>` 条目块（中间只有空行）→ 仍然报（原盲区不放松）。
  2. 图块与 `>` 条目块之间夹着散文或公式行 → 不报（图属于那段散文）。
  3. 图已经在 `>` 块内 → 不报。
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
sys.path.insert(0, _ROOT)
from lib.boot import setup  # noqa: E402
setup()

from verify.figure_completeness.script.figure_completeness import (  # noqa: E402
    check_figure_attribution)

_IMG = ('<div style="display:flex">\n'
        '  <img src="figure/ch03_fig24.png" alt="Fig. 24. Pythagorean theorem"'
        ' width="63.4%" height="auto">\n'
        '</div>')


def _verify(md):
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "ch.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write(md)
        return check_figure_attribution(p)


class TestFloatingFigureImmediacy(unittest.TestCase):
    def test_directly_after_blockquote_item_still_flagged(self):
        md = "\n".join([
            "> **3.1-8 Example (Space $C[a,b]$).** text",
            ">",
            "> $$ x = y $$",
            "",
            _IMG,
            "",
        ])
        got = _verify(md)
        self.assertEqual(len(got), 1, got)
        self.assertIn("ch03_fig24.png", got[0])

    def test_after_intervening_prose_not_flagged(self):
        """图属于习题题面：条目块之后还夹着散文/列表 → 不再误判。"""
        md = "\n".join([
            "> **3.1-8 Example (Space $C[a,b]$).** text",
            "",
            "**Problem Set 3.1**",
            "",
            "2. (Pythagorean theorem) If $x \\perp y$, show that",
            "",
            "   $$ \\|x + y\\|^2 = \\|x\\|^2 + \\|y\\|^2 . $$",
            "",
            "   Extend the formula to $m$ vectors.",
            "",
            _IMG,
            "",
        ])
        self.assertEqual(_verify(md), [])

    def test_after_display_formula_not_flagged(self):
        md = "\n".join([
            "> **4.5-3 Theorem (Adjoint of a product).** text",
            "",
            "$$ (ST)^\\times = T^\\times S^\\times . $$",
            "",
            _IMG,
            "",
        ])
        self.assertEqual(_verify(md), [])

    def test_figure_inside_blockquote_not_flagged(self):
        md = "\n".join([
            "> **1.1-3 Example (Euclidean space).** text",
            ">",
            "> " + _IMG.replace("\n", "\n> "),
            "",
        ])
        self.assertEqual(_verify(md), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
