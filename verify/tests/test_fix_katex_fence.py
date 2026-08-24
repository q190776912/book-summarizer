"""Regression tests for the C-layer KaTeX fixer's Pattern 2-3
(`fix_wrapping_dollars`): $$-unwrapping must NEVER strip genuine display
math — including CJK \\text{...} formulas and blocks whose first line does
not start with a backslash command.  2026-08 Kreyszig incident: the old
has_chinese/is_math heuristic mass-deleted top-level fence pairs on CN
chapter files (Ch4 -12 fences, Ch9 -14, Ch8 -6, Ch3 -2)."""
import io
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

from verify.format_verify.script.fix_katex import fix_file  # noqa: E402


class FencePreserveTest(unittest.TestCase):
    def _run(self, text):
        fd, fp = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        try:
            with io.open(fp, "w", encoding="utf-8") as f:
                f.write(text)
            fix_file(fp)
            with io.open(fp, encoding="utf-8") as f:
                return f.read()
        finally:
            os.remove(fp)

    def _fences(self, text):
        return sum(1 for l in text.split("\n") if l.strip() == "$$")

    def test_cjk_text_display_kept(self):
        src = "$$\np(\\alpha x)=\\alpha p(x) \\qquad \\text{对所有 }\\alpha\\ge 0 \\text{ 成立}\n$$\n"
        out = self._run(src)
        self.assertEqual(self._fences(out), 2)
        self.assertIn("\\alpha p(x)", out)

    def test_letterled_display_kept(self):
        src = "$$\nf_{n}(x_{j}) = f(x_{j}) \\tag{8}\n$$\n"
        out = self._run(src)
        self.assertEqual(self._fences(out), 2)

    def test_aligned_cjk_display_kept(self):
        src = ("$$\n\\begin{aligned}\nh(x_{1}+x_{2}, y) &= h(x_{1}, y), \\\\\n"
               "h(x, \\beta y) &= \\bar{\\beta} h(x, y) \\quad \\text{对一切 } x,y.\n"
               "\\end{aligned}\n$$\n")
        out = self._run(src)
        self.assertEqual(self._fences(out), 2)
        self.assertIn("\\begin{aligned}", out)

    def test_plain_relational_display_kept(self):
        # plain relational display without backslash commands: benefit of
        # doubt goes to the fences (2026-08 Ch9 regression: `x=y+z.` blocks
        # were unwrapped by the first tightened heuristic)
        src = "$$\nx=y+z.\n$$\n"
        out = self._run(src)
        self.assertEqual(self._fences(out), 2)

    def test_cjk_inside_text_payload_kept(self):
        # CJK inside \text{} of a command-heavy line must NOT trigger unwrap
        src = ("$$\n\\|T_n x\\| \\le c_x \\qquad \\text{对所有 } n=1,2,\\dots.\n"
               "$$\n")
        out = self._run(src)
        self.assertEqual(self._fences(out), 2)

    def test_prose_with_inline_math_unwrapped(self):
        src = "$$\n设 $f(x)$ 有界，则结论成立。\n$$\n"
        out = self._run(src)
        self.assertEqual(self._fences(out), 0)
        self.assertIn("$f(x)$", out)

    def test_heading_wrapped_unwrapped(self):
        src = "$$ ## 2.3 标题 $$\n"
        out = self._run(src)
        self.assertEqual(self._fences(out), 0)
        self.assertIn("## 2.3 标题", out)

    def test_english_display_no_commands_kept(self):
        # plain relational display without backslash commands: ambiguous, but
        # braces/scripts count as math structure -> kept
        src = "$$\na_{n+1} = {a_n + b_n \\over 2}\n$$\n"
        out = self._run(src)
        self.assertEqual(self._fences(out), 2)


if __name__ == "__main__":
    unittest.main()
