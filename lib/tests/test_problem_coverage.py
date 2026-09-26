"""Tests for lib/problem_coverage.py — 节末编号内容（Problems）覆盖对账.

Run:  python lib/tests/test_problem_coverage.py

负向用例守的是本轮实测缺陷：Kreyszig 抽取期把节末题面灌进前一编号项子树，
门控全绿却有约 51 节习题整块没进笔记——本闸必须把这种缺失判成 FAIL。
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

from problem_coverage import (consolidated_cut, coverage_problems,
                              longest_run_from_one,
                              page_floor_problems, page_problem_floors,
                              unit_run_length)


def txt(t, line_start=True):
    return {"text": t, "line_start": line_start}


def node(ntype, key, blocks, children=()):
    return {"type": ntype, "key": key, "name": key, "page_start": 1,
            "page_end": 9, "sub_sec": list(blocks) + list(children)}


def chapter(*sections):
    return {"type": "chapter", "key": "4", "name": "4", "page_start": 1,
            "page_end": 9, "consolidated": False, "sub_sec": list(sections)}


def unit(key, body):
    return {"id": "0001", "key": key, "type": "item", "file": key + ".md"}


def _read(bodies):
    return lambda u: bodies.get(u["key"], "")


PROBLEMS = [txt("1. Show that $p(0)=0$."), txt("2. Show that a norm is"),
            txt("3. Prove the converse."), txt("4. Give an example."),
            txt("5. Finish the proof.")]


class TestRuns(unittest.TestCase):
    def test_restart_after_in_text_list(self):
        # 正文列举 1..3 之后是节末习题 1..5：必须取最长链 5，不是第一条链 3
        self.assertEqual(longest_run_from_one([1, 2, 3, 1, 2, 3, 4, 5]), 5)

    def test_broken_numbering_is_conservative(self):
        self.assertEqual(longest_run_from_one([1, 2, 4, 5]), 2)

    def test_markdown_forms_counted(self):
        md = "\n".join(["> **Proof.**", "> 1. step", "> 2. step", "",
                        "**Problem Set 4.2**", "", "1. first", "2. second",
                        "3. third", "4. fourth", "5. fifth"])
        self.assertEqual(unit_run_length([md]), 5)


class TestGluedNumberHead(unittest.TestCase):
    """负向：编号后**紧跟**内容（无空格）必须计入——中文括注/题干与 OCR 粘连形态。

    旧判据只认 ``[.)\\]]`` + 空白 + 内容，于是 ``1.（提示）``、``2)证明``、
    OCR 粘连的 ``1.The`` 整行不被计数：契约侧链长被压低 → 「该节 12 题」的对账
    下限跟着塌，整块漏写的习题反而绿灯（Kreyszig 补齐期实测）。
    同时锁反向：``**1.5-4 …**`` 这类**行首更深层编号**不得冒充本节第 1 项。
    """

    def test_cjk_paren_glued_to_number_counts(self):
        md = "\n".join(["**习题集 4.2**", "", "1.（提示）证明…", "2.(a) 证明…",
                        "3) 第三个", "4. 第四个", "5. 第五个"])
        self.assertEqual(unit_run_length([md]), 5)

    def test_glued_ocr_english_counts(self):
        md = "\n".join(["1.The first", "2. second", "3. third", "4. fourth"])
        self.assertEqual(unit_run_length([md]), 4)

    def test_deeper_numpath_at_line_start_is_not_an_item(self):
        # 「1.5-4 …」必须**不**被计成第 1 项，否则 4 条正文引用就能凑出一条假链。
        md = "\n".join(["**1.5-4 波利亚定理**", "**2.7-9 有界性**",
                        "**3.6-1 例子**", "**4.13-3 判据**"])
        self.assertEqual(unit_run_length([md]), 0)

    def test_decimal_is_not_an_item(self):
        self.assertEqual(unit_run_length(["1.75 是收敛因子", "2.5 是发散因子"]), 0)


class TestCoverage(unittest.TestCase):
    def test_all_problems_present_passes(self):
        sec = node("section", "4.2", [], [node("theorem", "4.2-1", PROBLEMS)])
        root = chapter(sec)
        bodies = {"4.2-1": "text\n\n1. a\n2. b\n3. c\n4. d\n5. e"}
        units = [unit("4.2-1", "")]
        self.assertEqual(coverage_problems(root, units, _read(bodies)), [])

    def test_missing_problem_set_fails(self):
        """负向：题面整块没写 → 必须报缺失（本轮 Kreyszig 实测缺陷）。"""
        sec = node("section", "4.2", [], [node("theorem", "4.2-1", PROBLEMS)])
        root = chapter(sec)
        bodies = {"4.2-1": "only the theorem statement, no list at all"}
        probs = coverage_problems(root, [unit("4.2-1", "")], _read(bodies))
        self.assertEqual(len(probs), 1)
        self.assertIn("4.2", probs[0])
        self.assertIn("缺 5 项", probs[0])

    def test_partial_problem_set_fails(self):
        sec = node("section", "4.2", [], [node("theorem", "4.2-1", PROBLEMS)])
        root = chapter(sec)
        bodies = {"4.2-1": "**Problem Set 4.2**\n\n1. a\n2. b\n3. c\n4. d"}
        probs = coverage_problems(root, [unit("4.2-1", "")], _read(bodies))
        self.assertEqual(len(probs), 1)
        self.assertIn("缺 1 项", probs[0])

    def test_run_continues_across_units(self):
        sec = node("section", "4.2", [], [node("theorem", "4.2-1", PROBLEMS[:3]),
                                          node("theorem", "4.2-2", PROBLEMS[3:])])
        root = chapter(sec)
        bodies = {"4.2-1": "1. a\n2. b\n3. c", "4.2-2": "4. d\n5. e"}
        units = [unit("4.2-1", ""), unit("4.2-2", "")]
        self.assertEqual(coverage_problems(root, units, _read(bodies)), [])

    def test_consolidated_exercise_skipped(self):
        ex = node("exercise", "4.2", PROBLEMS)
        ex["consolidated"] = True
        sec = node("section", "4.2", [], [ex])
        root = chapter(sec)
        self.assertEqual(coverage_problems(root, [unit("4.2", "")],
                                           _read({})), [])

    def test_short_run_below_threshold_ignored(self):
        sec = node("section", "4.2", [],
                   [node("theorem", "4.2-1", [txt("1. a"), txt("2. b")])])
        root = chapter(sec)
        self.assertEqual(coverage_problems(root, [unit("4.2-1", "")],
                                           _read({})), [])


class TestPageFloors(unittest.TestCase):
    """闸 ⑬：契约瞎了（整页习题没进契约）时，页侧下限必须把缺口判出来。"""

    PAGE6 = {"Problems", "1. first", "2. second", "3. third", "4. fourth",
             "5. fifth", "6. sixth"}

    def _root(self, blocks):
        sec = node("section", "4.2", blocks, [])
        sec["page_start"] = sec["page_end"] = 50
        return chapter(sec)

    def test_page_floor_catches_contract_blind_gap(self):
        # 契约里只残下 1..3（⑫ 判据下「单元写满 3 题」即绿灯），页面却有 6 题
        root = self._root([txt("1. first"), txt("2. second"), txt("3. third")])
        units = [unit("4.2", "")]
        bodies = {"4.2": "**Problem Set 4.2**\n\n1. a\n2. b\n3. c"}
        self.assertEqual(coverage_problems(root, units, _read(bodies)), [])
        probs = page_floor_problems(root, units, _read(bodies),
                                    lambda pg: sorted(self.PAGE6), (50, 60))
        self.assertEqual(len(probs), 1)
        self.assertIn("4.2", probs[0])
        self.assertIn("页侧下限", probs[0])

    def test_page_floor_satisfied_passes(self):
        root = self._root([txt("1. a")])
        bodies = {"4.2": "\n".join("%d. p" % i for i in range(1, 7))}
        self.assertEqual(
            page_floor_problems(root, [unit("4.2", "")], _read(bodies),
                                lambda pg: sorted(self.PAGE6), (50, 60)), [])

    def test_page_floor_stops_at_next_section_heading(self):
        # 下一条节标题之后的 7./8. 属于下一节，不能灌进本节的下限
        root = self._root([txt("1. a")])
        blocks = ["Problems", "1. a", "2. b", "3. c", "4. d",
                  "4.3 Some New Section", "5. e", "6. f", "7. g", "8. h"]
        floors = page_problem_floors(root, lambda pg: blocks, (50, 60))
        self.assertEqual(floors, {"4.2": 4})

    def test_page_floor_ignores_repeated_running_header(self):
        # 跨页习题：每页页顶的**本节**页眉（同号 "4.2 …"）不得当成「本节结束」
        root = self._root([txt("1. a")])
        blocks = ["Problems", "1. a", "2. b", "4.2 Compact Linear Operators",
                  "3. c", "4. d", "4.3 Next Section Title", "5. e"]
        self.assertEqual(page_problem_floors(root, lambda pg: blocks, (50, 60)),
                         {"4.2": 4})

    def test_page_floor_window_includes_next_section_start_page(self):
        # 一套题的尾巴常落在下一条节起始页上：窗必须含该页（由停判据防越界）
        sec = node("section", "4.2", [txt("1. a")], [])
        sec["page_start"], sec["page_end"] = 50, 50
        other = node("section", "4.3", [txt("1. z")], [])
        other["page_start"], other["page_end"] = 51, 55
        root = chapter(sec, other)
        pages = {50: ["Problems", "1. a", "2. b"],
                 51: ["3. c", "4. d", "4.3 New Section", "9. zzz"],
                 52: ["Problems", "5. e", "6. f"]}
        self.assertEqual(page_problem_floors(root, pages.get, (50, 55)),
                         {"4.2": 4, "4.3": 6})

    def test_page_floor_ignored_without_page_json(self):
        root = self._root([txt("1. a")])
        self.assertEqual(
            page_floor_problems(root, [unit("4.2", "")], _read({}),
                                lambda pg: None, (50, 60)), [])

    def test_page_floor_ignores_big_noise_numbers(self):
        root = self._root([txt("1. a")])
        blocks = ["Problems", "1. a", "2. b", "1906 was the year", "3. c"]
        self.assertEqual(page_problem_floors(root, lambda pg: blocks, (50, 60)),
                         {"4.2": 3})


class TestConsolidatedCut(unittest.TestCase):
    """V-I 成堆习题块的契约侧切断点（Fraleigh 实测：块被灌进 description 文本流）。

    正向 = 印刷块标题 / 引言行（含 OCR 粘连与项目符号残渣）必须开切；
    负向 = 正文里的散文引用不得开切（否则把该写的编号内容判成不必写）。
    """

    def cut(self, *blocks):
        return consolidated_cut(list(blocks))

    def test_printed_title_forms(self):
        for head in ("EXERCISES 23", "■EXERCISES23", "Exercises 4", "习题 3",
                     "Exercises for Section 12", "Section 5 Exercises"):
            self.assertEqual(self.cut("1. body list", head, "1. a"), 1, head)

    def test_glued_ocr_intro(self):
        # ch2 D1 实测：OCR 把引言行粘成无空格整句，题号从 21 起
        self.assertEqual(self.cut("18", "InExercises21through6,determine", "21.On"), 1)

    def test_ocr_digit_read_as_letter(self):
        # ch0 §0.20 实测：EXERCISES 0 → 「EXERCISESO」，In Exercises 1 → 「InExercisesI」
        self.assertEqual(self.cut("body prose", "EXERCISESO",
                                  "InExercisesI through4,describe", "1.(x∈R"), 1)

    def test_spaced_intro_line(self):
        self.assertEqual(self.cut("Some body prose.",
                                  "In Exercises 1 through 9, determine whether",
                                  "1. Let $*$ be"), 1)
        self.assertEqual(self.cut("Exercises 14 through 19 deal with uniqueness.",
                                  "1. Suppose $T$ is"), 0)

    def test_prose_reference_does_not_cut(self):
        for line in ("We have demonstrated the toughest part (see Exercises 14 through 22).",
                     "A series of exercises shows that every $G$-set is isomorphic",
                     "Exercises reveal where the axiom is used.",
                     "Many exercises in this section ask for a counterexample."):
            self.assertIsNone(self.cut("body", line, "1. a"), line)

    def test_body_list_alone_is_not_a_block_head(self):
        # 正文列举（公理/情形清单）里没有 Exercises 字样 → 不得开切，
        # 否则「该写的编号内容」被误判成可省略的习题块。
        self.assertIsNone(self.cut("axioms are satisfied:", "1. closure",
                                   "2. identity", "3. inverses"))

    def test_no_header_returns_none(self):
        self.assertIsNone(self.cut("axioms are satisfied:", "1. closure", "2. identity"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
