"""Regression tests: 条目类型词解析与习题窗路由（B 层 item_numbering_integrity）。

锁死三类实测场景的根治（Weibel 实测）：

  1. 「Calculation 6.2.1」这类以 Calculation 命名的条头：类型词表缺该词时
     条头解析不出编号 → §6.2 条目窗假「缺号 1」。
  2. 专名内嵌 exercise/Problem 词的条头（Weibel ch6 的
     「Extension Problem 6.6.2」/ CN「6.6.2 扩张问题 (Extension Problem)」）
     解析为降级候选 '~Word'，窗算术两步法（_resolve_demoted_entries）裁决：
       - ch6：习题窗 6.6 的 2 号已有真习题头 → 候选留在内容窗（修「缺号 2」）；
       - ch10「Topology Exercise 10.9.2」：习题窗 10.9 恰缺 2 号 → 回补进习题窗
         （防止把真习题误关内容窗造成假「缺号」）。
  3. 负向保护：真正的 label-first 习题条头（"Exercise 6.7.1" / "习题 6.7.5" /
     "Problem 6.6.2" 开头）必须仍直接解析为习题 label，不经降级。
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, str(Path(_ROOT) / "verify" / "item_numbering_integrity" / "script"))
sys.path.insert(0, str(Path(_ROOT) / "lib"))

import item_numbering_integrity as ini  # noqa: E402


class TestCalculationLabel(unittest.TestCase):
    def test_calculation_parses(self):
        self.assertEqual(ini._parse_entry("Calculation 6.2.1 (Cyclic groups)", 3, "en"),
                         ([6, 2, 1], "Calculation"))


class TestEmbeddedExerciseWordDemotion(unittest.TestCase):
    def test_en_m3_embedded_problem_demoted(self):
        self.assertEqual(ini._parse_entry("Extension Problem 6.6.2", 3, "en"),
                         ([6, 6, 2], "~Problem"))

    def test_en_dash_variant(self):
        self.assertEqual(ini._parse_entry("Extension Problem 6.6-2", 3, "en"),
                         ([6, 6, 2], "~Problem"))

    def test_cn_numberfirst_embedded_wenti_demoted(self):
        self.assertEqual(ini._parse_entry("6.6.2 扩张问题 (Extension Problem)", 3, "cn"),
                         ([6, 6, 2], "~问题"))

    def test_norm_entry_label_strips_marker(self):
        self.assertEqual(ini._norm_entry_label("~Problem"), ("uncat", "Problem"))
        self.assertEqual(ini._norm_entry_label("Exercise"), ("Exercise", None))


class TestLeadingExerciseLabelsKeepBucket(unittest.TestCase):
    def test_en_exercise_first(self):
        self.assertEqual(ini._parse_entry("Exercise 6.7.1", 3, "en"),
                         ([6, 7, 1], "Exercise"))

    def test_en_problem_first_untouched(self):
        self.assertEqual(ini._parse_entry("Problem 6.6.2", 3, "en"),
                         ([6, 6, 2], "Problem"))

    def test_cn_xiti_first(self):
        self.assertEqual(ini._parse_entry("习题 6.7.5", 3, "cn"),
                         ([6, 7, 5], "习题"))

    def test_named_lemma_still_content(self):
        self.assertEqual(ini._parse_entry("Shapiro's Lemma 6.3.2", 3, "en"),
                         ([6, 3, 2], "Lemma"))


class TestWindowArithmeticResolve(unittest.TestCase):
    def test_ch6_candidate_stays_content_when_ex_window_complete(self):
        # ex 窗 6.6 已有 {1,2,3}（真习题头），候选（内容窗 2 号）不回补。
        entries = [
            ("0:ex:6.6", 1, "6.6-1", "Exercise", "6.6"),
            ("0:ex:6.6", 2, "6.6-2", "Exercise", "6.6"),
            ("0:ex:6.6", 3, "6.6-3", "Exercise", "6.6"),
            ("0:6.6", 1, "6.6-1", "uncat", "6.6"),
            ("0:6.6", 2, "6.6-2", "uncat", "6.6"),   # ← 候选 idx=4
        ]
        ini._resolve_demoted_entries(entries, [(4, 0, "6.6", 2)])
        self.assertEqual(entries[4][0], "0:6.6")

    def test_ch10_candidate_restored_when_ex_window_gaps(self):
        # ex 窗 10.9 = {1,3,4} 缺 2 → 候选回补进 ex 窗。
        entries = [
            ("0:ex:10.9", 1, "10.9-1", "Exercise", "10.9"),
            ("0:ex:10.9", 3, "10.9-3", "Exercise", "10.9"),
            ("0:ex:10.9", 4, "10.9-4", "Exercise", "10.9"),
            ("0:10.9", 2, "10.9-2", "uncat", "10.9"),   # ← 候选 idx=3
        ]
        ini._resolve_demoted_entries(entries, [(3, 0, "10.9", 2)])
        self.assertEqual(entries[3][0], "0:ex:10.9")

    def test_no_ex_window_at_all_stays_content(self):
        entries = [("0:6.6", 2, "6.6-2", "uncat", "6.6")]
        ini._resolve_demoted_entries(entries, [(0, 0, "6.6", 2)])
        self.assertEqual(entries[0][0], "0:6.6")


if __name__ == "__main__":
    unittest.main()
