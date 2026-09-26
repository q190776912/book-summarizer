# -*- coding: utf-8 -*-
"""章级闸 ⑯「同一题面重复出现在两个单元」+ 单元级判据 21/22 的回归测试。

真值来源：Rosen 8e ch5 §5.4（习题单元只有 4 行「契约节点所以题面未写」的元话语）与
ch8 §8.4（单元里抄的是 §8.3 的 29–37 题，号段自身连续 → ⑮/判据 20 全绿）。
"""
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve()
if len(_HERE.parents) < 2:  # pragma: no cover
    raise SystemExit("run from the skill root")
for _p in (str(_HERE.parents[1]),):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as boot  # noqa: E402
boot.setup()

from lib.problem_coverage import (  # noqa: E402
    exercise_statements, duplicate_exercise_statement_problems)

_LONG = "Show that if $a = b^d$ and $n$ is a power of $b$ then the function satisfies " \
        "the stated recurrence and the claimed closed form holds for every such $n$."
_OTHER = "Give a big-O estimate for the function $f$ described in the previous item, " \
         "assuming throughout that $f$ is an increasing function of $n$."


class TestStatementFingerprint(unittest.TestCase):
    def test_latex_spacing_difference_still_matches(self):
        """同一题写成 `$cn^d$` 与 `$c n ^ { d }$` 必须同一指纹（实测形态）。"""
        a = exercise_statements("**Exercise 31.** " + _LONG)
        b = exercise_statements("31. Show that if $a = b ^ { d }$ and $n$ is a power of "
                                "$b$ then the function satisfies the stated recurrence "
                                "and the claimed closed form holds for every such $n$.")
        self.assertEqual(len(a), 1)
        self.assertEqual(len(b), 1)
        self.assertEqual(a[0][1], b[0][1])

    def test_short_reference_sentence_not_fingerprinted(self):
        """「Use Exercise 29 to show…」式引用太短，不得当成可配对的题面。"""
        self.assertEqual(exercise_statements("30. Use Exercise 29 to show the bound."), [])

    def test_year_like_large_number_ignored(self):
        self.assertEqual(exercise_statements("1976. " + _LONG), [])


class TestDuplicateGate(unittest.TestCase):
    def test_same_statement_in_two_exercise_units_flagged(self):
        units = [("a.md", "**Exercise Set 8.3**\n\n**Exercise 31.** " + _LONG, True),
                 ("b.md", "**Exercise Set 8.4**\n\n**Exercise 31.** " + _LONG, True)]
        probs = duplicate_exercise_statement_problems(units)
        self.assertEqual(len(probs), 1)
        self.assertIn("a.md", probs[0])
        self.assertIn("b.md", probs[0])
        self.assertIn("1 道题", probs[0])

    def test_collision_count_reported(self):
        units = [("a.md", "**Exercise 31.** " + _LONG + "\n\n**Exercise 32.** " + _OTHER, True),
                 ("b.md", "**Exercise 31.** " + _LONG + "\n\n**Exercise 32.** " + _OTHER, True)]
        probs = duplicate_exercise_statement_problems(units)
        self.assertEqual(len(probs), 1)
        self.assertIn("2 道题", probs[0])

    def test_distinct_statements_pass(self):
        units = [("a.md", "**Exercise 29.** " + _LONG, True),
                 ("b.md", "**Exercise 60.** " + _OTHER, True)]
        self.assertEqual(duplicate_exercise_statement_problems(units), [])

    def test_prose_units_never_judged(self):
        """desc/item 里重复的散文表述不是「重复题面」（判据只对契约登记的习题单元）。"""
        units = [("a.md", "Paragraph.\n\n" + _LONG, False),
                 ("b.md", "Other.\n\n" + _LONG, False)]
        self.assertEqual(duplicate_exercise_statement_problems(units), [])

    def test_mixed_registration_still_caught(self):
        """真值形态：§8.3 登记单元里的裸号题面 == §8.4 登记单元里的粗体题面。"""
        units = [("0049_exercise_8_3.md", "**Exercises for 8.3.**\n\n31. " + _LONG, True),
                 ("0069_exercise_8_4.md", "30. x\n\n**Exercise 31.** " + _LONG, True)]
        probs = duplicate_exercise_statement_problems(units)
        self.assertEqual(len(probs), 1)
        self.assertIn("0049_exercise_8_3.md", probs[0])

    def test_remedy_text_forbids_shortening(self):
        units = [("a.md", "**Exercise 31.** " + _LONG, True),
                 ("b.md", "**Exercise 31.** " + _LONG, True)]
        msg = duplicate_exercise_statement_problems(units)[0]
        self.assertIn("禁止用「凑连续」的删改掩盖", msg)


if __name__ == "__main__":
    unittest.main(verbosity=2)
