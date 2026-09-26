"""Tests for lib/problem_coverage.py — 章级「习题集题号跨单元连续」闸。

Run:  python lib/tests/test_chapter_exercise_gate.py

负向用例守的是 Rosen 8e 实测缺陷：整节习题被灌进一个 desc 节点后契约没有逐题条目，
「§10.1 抄了 1,2 就跳到 10–38」在契约覆盖对账、页侧下限、单元级判据 20 里全是绿灯
（缺的 3..9 分散在不同单元），只在合并后 verify B/O 层才成片暴露、且被分块噪声淹没。
本闸按合并顺序把全章题号串成号流，必须在门控就报出跨单元的洞。
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

from problem_coverage import (chapter_exercise_problems, exercise_item_numbers,
                              exercise_run_gaps, exercise_runs)


class TestNumberHelpers(unittest.TestCase):
    def test_both_item_forms_counted_in_order(self):
        self.assertEqual(
            exercise_item_numbers("1. a\n**Exercise 3.** b\n"), [1, 3])

    def test_set_heading_is_not_an_item(self):
        self.assertEqual(
            exercise_item_numbers("**Exercise Set 1.8**\n\n1. a\n"), [1])

    def test_runs_split_on_restart(self):
        self.assertEqual(exercise_runs([1, 2, 3, 1, 2]), [[1, 2, 3], [1, 2]])

    def test_duplicate_numbers_folded(self):
        self.assertEqual(exercise_runs([1, 1, 2, 3]), [[1, 2, 3]])

    def test_range_label_expands(self):
        self.assertEqual(
            exercise_item_numbers("**Exercises 2-4.** q\n"), [2, 3, 4])
        self.assertEqual(exercise_item_numbers("12-14) a\n"), [12, 13, 14])

    def test_absurd_range_span_not_expanded(self):
        # 两个不相干数字被 OCR 粘成「Exercise 3-1906」→ 只认首号，不凭空造 1900 个号
        self.assertEqual(exercise_item_numbers("**Exercise 3-1906.** x\n"), [3])

    def test_gaps_reported_per_run(self):
        self.assertEqual(exercise_run_gaps([1, 2, 3, 1, 2, 5]), [(1, 5, [3, 4])])

    def test_short_run_exempt(self):
        self.assertEqual(exercise_run_gaps([1, 9]), [])


class TestChapterExerciseGate(unittest.TestCase):
    def test_cross_unit_hole_caught(self):
        units = [("0100_exercise_10_1.md", "**Exercise Set 10.1**\n\n1. p\n2. q\n", True),
                 ("0101_desc_D10.md", "10. r\n11. s\n12. t\n", False)]
        probs = chapter_exercise_problems(units)
        self.assertEqual(len(probs), 1)
        self.assertIn("Exercise Set 10.1", probs[0])
        self.assertIn("缺号 7 处", probs[0])
        self.assertIn("1..12", probs[0])
        # 补写位置 = 洞之后第一题所在的单元文件
        self.assertIn("0101_desc_D10.md", probs[0])

    def test_contiguous_handoff_across_units_passes(self):
        units = [("a.md", "**Exercise Set 1.1**\n\n1. p\n2. q\n", True),
                 ("b.md", "3. r\n4. s\n5. t\n")]
        self.assertEqual(chapter_exercise_problems(units), [])

    def test_second_set_restarts_cleanly(self):
        units = [("a.md", "**Exercise Set 6.4**\n\n1. p\n2. q\n3. r\n"
                          "**Exercise Set 6.5**\n\n1. s\n2. t\n3. u\n", True)]
        self.assertEqual(chapter_exercise_problems(units), [])

    def test_hole_reported_under_its_own_heading(self):
        units = [("a.md", "**Exercise Set 6.4**\n\n1. p\n2. q\n3. r\n"
                          "**Exercise Set 6.5**\n\n1. s\n9. t\n10. u\n11. v\n", True)]
        probs = chapter_exercise_problems(units)
        self.assertEqual(len(probs), 1)
        self.assertIn("Exercise Set 6.5", probs[0])
        self.assertNotIn("6.4", probs[0])

    def test_prose_lists_before_any_set_never_judged(self):
        # 边界①：全章既无习题集标题也无 exercise 单元 → 正文枚举不构成「集」
        units = [("a.md", "Steps:\n1. p\n2. q\n3. r\n"),
                 ("b.md", "Cases:\n1. s\n2. t\n8. u\n")]
        self.assertEqual(chapter_exercise_problems(units), [])

    def test_unregistered_desc_block_never_opens_a_set(self):
        # V-I：契约没登记习题节点的单元里顺带抄到的集中习题块 = 认可的省略，不报缺号
        #（Rosen 8e ch10 §10.6 实测假阳：desc 节点里一句「**Exercises for Section 10.6**」
        #  之后抄了两道题，被当成集标题开段 → 报「缺 3、4」）
        units = [("a.md", "正文散文……\n\n**Exercises for Section 10.6**\n\n"
                          "1. p\n2. q\n9. r\n10. s\n")]
        self.assertEqual(chapter_exercise_problems(units), [])

    def test_prose_lists_between_two_sets_not_appended(self):
        # 第一集之后的散文枚举不得混进该集号流
        units = [("a.md", "**Exercise Set 2.1**\n\n1. p\n2. q\n3. r\n", True),
                 ("b.md", "Three cases arise:\n1. x\n2. y\n"),
                 ("c.md", "**Exercise Set 2.2**\n\n1. z\n2. w\n3. v\n", True)]
        self.assertEqual(chapter_exercise_problems(units), [])

    def test_section_boundary_closes_the_open_set(self):
        # 边界②：新的 `##` 小节 = 上一集到此为止；后面散文里的 1./2./9. 不得再喂给号流
        units = [("a.md", "**Exercise Set 4.1**\n\n1. p\n2. q\n3. r\n", True),
                 ("b.md", "## §4.2 More Stuff\n\nSteps:\n1. x\n2. y\n9. z\n")]
        self.assertEqual(chapter_exercise_problems(units), [])

    def test_label_form_exercise_numbers_counted(self):
        units = [("a.md", "**Exercise Set 1.1**\n\n**Exercise 1.** p\n"
                          "**Exercise 2.** q\n**Exercise 9.** r\n", True),
                 ("b.md", "**Exercise 10.** s\n")]
        probs = chapter_exercise_problems(units)
        self.assertEqual(len(probs), 1)
        self.assertIn("缺号 6 处", probs[0])

    def test_range_label_covers_every_number_it_names(self):
        # 原书把同型几题合并成一条题干（Rosen「**Exercises 2-4.** Find …」），
        # 区间覆盖的每一号都算写了 —— 否则 3、4 被报成缺号（ch10 §10.6 实测假阳）
        units = [("a.md", "**Exercise Set 10.6**\n\n**Exercise 1.** p\n"
                          "**Exercises 2-4.** q\n**Exercise 5.** r\n"
                          "**Exercises 6-8.** s\n**Exercise 9.** t\n", True)]
        self.assertEqual(chapter_exercise_problems(units), [])

    def test_range_label_does_not_hide_real_hole(self):
        units = [("a.md", "**Exercise Set 10.6**\n\n**Exercise 1.** p\n"
                          "**Exercises 2-4.** q\n**Exercise 9.** r\n"
                          "**Exercise 10.** s\n**Exercise 11.** t\n", True)]
        probs = chapter_exercise_problems(units)
        self.assertEqual(len(probs), 1)
        self.assertIn("缺号 4 处", probs[0])

    def test_exercise_flag_without_heading_is_own_segment(self):
        units = [("a.md", "**Exercise Set 3.1**\n\n1. p\n2. q\n3. r\n", True),
                 ("b.md", "1. p\n2. q\n9. r\n10. s\n", True)]
        probs = chapter_exercise_problems(units)
        self.assertEqual(len(probs), 1)
        self.assertIn("b.md", probs[0])
        self.assertIn("缺号 6 处", probs[0])

    def test_supplementary_exercises_restart_not_a_hole(self):
        units = [("a.md", "**Exercise Set 12.1**\n\n1. p\n2. q\n3. r\n"
                          "**Supplementary Exercises**\n\n1. s\n2. t\n3. u\n", True)]
        self.assertEqual(chapter_exercise_problems(units), [])

    def test_short_set_exempt(self):
        units = [("a.md", "**Exercise Set 2.1**\n\n1. p\n7. q\n", True)]
        self.assertEqual(chapter_exercise_problems(units), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
