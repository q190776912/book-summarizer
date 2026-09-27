"""Regression tests for verbose_gates.FIGURE_MARKUP_RE / check_verbose_proofs.

2026-09-27 Rosen 8e 补图轮：往一个 640 字的 `> **Solution.**` 解答块里补印一张
原书图（`> <div>` / `> <img>` / `> </div>` + `> **Figure 2.** …` 共 5 行、约 250
字排版标记），块文本被顶到 805 字，门控把「合规嵌图」当成「逐段翻译原书 proof」
报 FAIL（ch4 0053_item_例10）。插图标记不是散文，计量前必须剔除；真正的散文墙
仍须照报。
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "verify", "verbose_gates", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from verbose_gates import FIGURE_MARKUP_RE, check_verbose_proofs  # noqa: E402

_FIG = [
    ">",
    "> <div style=\"display:flex; gap:6px; flex-wrap:wrap; justify-content:center\">",
    ">   <img src=\"figure/ch04_p289_F002.png\" alt=\"FIGURE 2 Multiplying (110)2 and (101)2.\" width=\"7.9%\" height=\"auto\">",
    "> </div>",
    "> **Figure 2.** Multiplying $(110)_2$ and $(101)_2$.",
]


class TestFigureMarkupRe(unittest.TestCase):
    def test_div_img_close_are_markup(self):
        self.assertTrue(FIGURE_MARKUP_RE.match(
            '<div style="display:flex; gap:6px">'))
        self.assertTrue(FIGURE_MARKUP_RE.match('<img src="figure/x.png" alt="x">'))
        self.assertTrue(FIGURE_MARKUP_RE.match("</div>"))

    def test_caption_heads_are_markup(self):
        self.assertTrue(FIGURE_MARKUP_RE.match("**Figure 2.** Multiplying …"))
        self.assertTrue(FIGURE_MARKUP_RE.match("**图 2.** 乘法竖式。"))
        self.assertTrue(FIGURE_MARKUP_RE.match("FIGURE 2 Multiplying …"))

    def test_ordinary_prose_not_markup(self):
        self.assertFalse(FIGURE_MARKUP_RE.match("**Solution.** First note that"))
        self.assertFalse(FIGURE_MARKUP_RE.match("$$ab_{0} \\cdot 2^{0} = (110)_2$$"))
        self.assertFalse(FIGURE_MARKUP_RE.match("We now add the three partial products"))


class TestVerboseProofsIgnoresFigureMarkup(unittest.TestCase):
    def test_figure_inside_solution_not_counted(self):
        prose = ("First note that the partial products are obtained by shifting, "
                 "and each bit of b selects either the all-zero row or a copy of a. ")
        lines = ["> **Solution.** " + prose * 5] + _FIG + [">"]
        self.assertEqual(check_verbose_proofs(lines), [])

    def test_prose_wall_still_reported_with_figure(self):
        prose = ("First note that the partial products are obtained by shifting, "
                 "and each bit of b selects either the all-zero row or a copy of a. ")
        lines = ["> **Solution.** " + prose * 12] + _FIG + [">"]
        out = check_verbose_proofs(lines)
        self.assertEqual(len(out), 1)
        self.assertIn("未分条", out[0])


if __name__ == "__main__":
    unittest.main()
