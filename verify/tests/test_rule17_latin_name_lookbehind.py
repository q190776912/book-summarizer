"""Judgement test for rule #17's `_FUNC_CALL_RE` lookbehind (Latin names).

`Cramér (1946)` / `Erdős (1968)` put an accented LATIN letter right in front of the
paren, so the old ASCII-only lookbehind saw a bare call `r (1946)` and writers
corrupted the printed name into "Cramer" to get past the gate (Lehmann ch5/0058,
ch6/0022, ch7/0002 + Rosen ch10/0113, 2026-10-17).

🔴 The relaxation is deliberately LATIN-ONLY: CJK / Greek letters must keep being
flagged (`设f(x)` / `则T(x)` / `πf(x)` are genuine bare calls in prose and the
corpus scan found 200+ such lines), and the ordinary prose/label skips must stay.
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
import lib.boot as _boot  # noqa: E402
_boot.setup()

from verify.format_verify.script.katex_heuristics import (  # noqa: E402
    find_bare_math_errors,
)


def bare_call_hits(line):
    return [e for e in find_bare_math_errors([line]) if "bare function call" in e]


class LatinNameLookbehind(unittest.TestCase):
    def test_accented_latin_name_year_is_not_a_call(self):
        for line in (
            "For a rigorous treatment see Cramér (1946).",
            "See, for example, Cramér (1946, Section 22.2).",
            "This is due to Erdős (1968).",
            "The bound is from Skorohod (1965).",
        ):
            self.assertEqual([], bare_call_hits(line), line)

    def test_cjk_and_greek_before_a_call_still_flagged(self):
        # 汉字 / 希腊字母紧跟裸调用 = 真缺陷，放过就等于给每一本中文书开洞。
        for line in (
            "设f(x) 在区间上连续。",
            "则T(x) 是线性算子。",
            "其中πf(x) 为投影。",
        ):
            self.assertTrue(bare_call_hits(line), line)

    def test_plain_bare_call_still_flagged(self):
        self.assertTrue(bare_call_hits("we compute f(x) for all x"))

    def test_label_and_prose_skips_unchanged(self):
        for line in (
            "See Figure 3(b) for the case.",
            "This holds in 2(a) but not elsewhere.",
            "The argument x_1 works.",
        ):
            self.assertEqual([], bare_call_hits(line), line)

    def test_multiplication_sign_does_not_silence_a_call(self):
        # U+00D7 (×) / U+00F7 (÷) 从拉丁区间里**剔掉**正是为了这条：
        # `a×f(x)` 里的 f(x) 仍是裸调用，不能被当成「词尾字母」。
        self.assertTrue(bare_call_hits("hence a×f(x) is bounded."))


if __name__ == "__main__":
    unittest.main()
