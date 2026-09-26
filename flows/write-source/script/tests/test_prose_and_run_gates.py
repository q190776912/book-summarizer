# -*- coding: utf-8 -*-
"""Regression: 第 19 项「P 层散文照抄闸（单元级）」+ 第 20 项「习题块题号缺号闸」。

背景（Rosen 8e 2026-09-26 首跑源版 verify）：16 章单元门控**全绿**，合并 md 的
verify 却报 13 章 222 段「顶层散文整段照抄原书」+ ch6 §6.5/§6.6 共 96 处习题缺号。
两类缺陷都只在步骤 7/8 暴露，写手代理「标 DONE + 门控通过」后整章被打回：

* 照抄散文：判据本来就在 verify 的 ``verbose_gates.check_verbose_paragraphs``，
  单元门控从未调用 → 本闸复用**同一实现**，只在源语言单元上跑；
* 习题缺号：整节习题被 OCR 灌进一个 desc 节点，契约侧无逐条条目可对账，而写手用
  ``Representative exercises follow.`` 之类措辞掩盖 → 扩展「假省略声明」词表 +
  按「原书习题集恒为连续编号」做**段内缺号**机械判定。

锁死方向：两处都必须是「有洞就报、连续/改写后不报」，且不得误伤短枚举、
含公式的段落、非习题单元里的有序列表。

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_prose_and_run_gates.py
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:  # pragma: no cover
    _ROOT = str(Path(__file__).resolve().parents[4])
sys.path.insert(0, _ROOT)
import lib.boot as boot  # noqa: E402
boot.setup()

import check_unit_quality as q  # noqa: E402


class RunGapGate(unittest.TestCase):
    def test_flags_holes_inside_one_exercise_run(self):
        body = "**Exercise Set 6.5.**\n\n1. foo\n\n2. bar\n\n4. baz\n"
        probs = q.exercise_run_gap_problems("exercise", body)
        self.assertEqual(len(probs), 1)
        self.assertIn("缺号 1 处", probs[0])
        self.assertIn("3", probs[0])
        self.assertIn("把缺的各题题面补全", probs[0])

    def test_unregistered_desc_unit_with_headings_exempt(self):
        # 🔴 V-I 适用范围：只有**契约登记的习题单元**欠「题面完整」。desc/item 单元里
        # 顺带抄到的集中习题块（Rosen 每节末的 Exercise Set 被灌进相邻 desc 节点）是
        # 流水线认可的省略，报缺号等于逼写手恢复 V-I 让删的内容。
        body = "**Exercise Set 6.5.**\n\n1. foo\n\n2. bar\n\n4. baz\n"
        self.assertEqual(q.exercise_run_gap_problems("desc", body), [])

    def test_contiguous_run_passes(self):
        body = "**Exercise Set 1.8**\n\n1. a\n\n2. b\n\n3. c\n\n4. d\n"
        self.assertEqual(q.exercise_run_gap_problems("exercise", body), [])

    def test_restart_splits_runs_no_false_positive(self):
        # 一个单元含两个习题集：各自 1..3 连续 → 不得把 3→1 的回退当成缺号
        body = ("**Exercise Set 6.5**\n\n1. a\n\n2. b\n\n3. c\n"
                "\n**Exercise Set 6.6**\n\n1. d\n\n2. e\n\n3. f\n")
        self.assertEqual(q.exercise_run_gap_problems("exercise", body), [])

    def test_second_run_with_holes_still_flagged(self):
        body = ("**Exercise Set 6.5**\n\n1. a\n\n2. b\n\n3. c\n"
                "\n**Exercise Set 6.6**\n\n59. d\n\n61. e\n\n63. f\n")
        probs = q.exercise_run_gap_problems("exercise", body)
        self.assertEqual(len(probs), 1)
        self.assertIn("59..63", probs[0])

    def test_short_run_exempt(self):
        body = "**Exercise Set 6.5**\n\n7. a\n\n12. b\n"
        self.assertEqual(q.exercise_run_gap_problems("exercise", body), [])

    def test_non_exercise_unit_exempt(self):
        # 条目/散文单元里的有序列表（引用了原书第 1、3 条）不是习题块，不得判缺号
        body = "Steps of the argument:\n\n1. assume\n\n3. conclude\n"
        self.assertEqual(q.exercise_run_gap_problems("desc", body), [])

    def test_bold_head_and_blockquote_forms_counted(self):
        body = "**Exercise Set 9.1**\n\n**1.** a\n\n**3.** b\n\n**5.** c\n"
        probs = q.exercise_run_gap_problems("exercise", body)
        self.assertEqual(len(probs), 1)
        self.assertIn("缺号 2 处", probs[0])

    def test_label_head_form_counted(self):
        # Rosen 8e ch6 实测形态：**Exercise N.**（号在粗体标签里，不是行首裸号）
        body = ("**Exercise Set 6.5.**\n\n**Exercise 1.** q\n\n"
                "**Exercise 3.** q\n\n**Exercise 9.** q\n")
        probs = q.exercise_run_gap_problems("exercise", body)
        self.assertEqual(len(probs), 1)
        self.assertIn("1..9", probs[0])
        self.assertIn("缺号 6 处", probs[0])

    def test_range_label_head_covers_its_numbers(self):
        # Rosen「**Exercises 2-4.**」一条题干管三题：区间覆盖的号都算写了，不得报缺
        body = ("**Exercise Set 10.6**\n\n**Exercise 1.** q\n\n"
                "**Exercises 2-4.** q\n\n**Exercise 5.** q\n")
        self.assertEqual(q.exercise_run_gap_problems("exercise", body), [])

    def test_check_body_reports_run_gap(self):
        body = "**Exercise Set 6.5.**\n\n1. foo\n\n3. bar\n\n9. baz\n"
        ok, probs = q.check_body("exercise", "", body)
        self.assertFalse(ok)
        self.assertTrue(any("题号缺号" in p for p in probs))


class OmissionVocabulary(unittest.TestCase):
    def test_representative_exercise_claim_matches(self):
        for text in ("Representative exercises follow.",
                     "Selected exercises are grouped by topic.",
                     "A selection of the exercises illustrates the methods.",
                     "代表性习题如下。"):
            self.assertIsNotNone(q._OMISSION_CLAIM_RE.search(text), text)

    def test_benign_wording_not_matched(self):
        for text in ("a representative sample of a group",
                     "the selection sort algorithm runs in O(n^2)",
                     "we omit the details of the induction step"):
            self.assertIsNone(q._OMISSION_CLAIM_RE.search(text), text)

    def test_check_body_flags_representative_claim_in_exercise_unit(self):
        body = ("**Exercise Set 6.5.**\n\n"
                "The exercises (1-68) are grouped by topic. "
                "Representative exercises follow.\n\n1. a\n\n2. b\n\n3. c\n")
        ok, probs = q.check_body("exercise", "", body)
        self.assertFalse(ok)
        self.assertTrue(any("假省略声明" in p for p in probs))


class ProseOverlapWiring(unittest.TestCase):
    """第 19 项：单元级必须**调用** verify 的同一实现，且只在有 ext/ch 上下文时。"""

    def setUp(self):
        self._orig = q.check_verbose_paragraphs

    def tearDown(self):
        q.check_verbose_paragraphs = self._orig

    def test_called_with_ext_dir_and_ch(self):
        calls = []

        def fake(lines, ext_dir=None, ch=None, label_exempt=True, math_exempt=True):
            calls.append((ext_dir, ch, label_exempt, math_exempt))
            return ["  x L2: 顶层散文段 900 字，与源书字面重合率 95%（整段照抄）"]

        q.check_verbose_paragraphs = fake
        ok, probs = q.check_body("desc", "", "plain prose paragraph here\n",
                                 ext_dir="/tmp/ext", ch="6")
        self.assertEqual(calls, [("/tmp/ext", "6", False, False)])
        self.assertFalse(ok)
        self.assertTrue(any("照抄" in p for p in probs))

    def test_tier1_unit_types_keep_faithful_exemptions(self):
        """item / exercise 不得被收紧——定理陈述与题面按原书忠实保留是 Tier 1。"""
        calls = []

        def fake(lines, ext_dir=None, ch=None, label_exempt=True, math_exempt=True):
            calls.append(label_exempt)
            return []

        q.check_verbose_paragraphs = fake
        q.check_body("item", "定理 2", "**Theorem 2.** faithful statement\n",
                     ext_dir="/tmp/ext", ch="8")
        q.check_body("exercise", "8.3", "**Exercise 1.** faithful statement\n",
                     ext_dir="/tmp/ext", ch="8")
        self.assertEqual(calls, [True, True])

    def test_skipped_without_context(self):
        def boom(lines, ext_dir=None, ch=None, label_exempt=True, math_exempt=True):
            raise AssertionError("无 ext/ch 上下文时不得调用照抄闸")

        q.check_verbose_paragraphs = boom
        ok, _probs = q.check_body("desc", "", "plain prose paragraph here\n")
        self.assertTrue(ok)


class DescLabelAndMathBlindspot(unittest.TestCase):
    """`desc` 单元的 `**段首粗体**` / 单个 `$x$` 不得让整段照抄隐身。

    真值：Rosen 8e 附录 C 单元 `appendix16/0002_desc_D1.md` 八段照抄
    （与源书 8-gram 重合 0.88–1.00）全部躲在 `**A3.2 Assignments and Other
    Types of Statements.**` 这类印刷小标题后面；同一实现默认豁免 `**` 标签区域
    与含公式段，两层门控（单元 + 合并 md）都看不见。
    """

    WALL = ("An assignment statement is used to assign values to variables. "
            "In an assignment statement the left-hand side is the name of the "
            "variable and the right-hand side is an expression that involves "
            "constants, variables that have been assigned values, or functions "
            "defined by procedures, and the right hand side may contain any of "
            "the usual arithmetic operations however in the pseudocode in this "
            "book it may include any well defined operation even if this "
            "operation can be carried out only by using a large number of "
            "statements in an actual programming language so the symbol is "
            "used for assignments thus an assignment statement has the form "
            "variable expression and we could also express this one statement "
            "with several assignment statements but for simplicity we will "
            "often prefer this abbreviated form of pseudocode here, since a "
            "good deal of English description of the steps is permitted and "
            "the formal study of such a notation is not the purpose of this "
            "appendix, which is meant as a reference guide that students "
            "consult while working through the algorithm descriptions in the "
            "text and while writing solutions to the exercises of the book, "
            "and it should be emphasized that a procedure call is written as "
            "the name of the procedure followed by its arguments in "
            "parentheses, that the values returned by such a call may be "
            "assigned to a variable, and that the comments, which are the "
            "statements enclosed between the symbols begin comment and end "
            "comment, are provided solely for the convenience of the reader "
            "and carry no computational meaning at all.")

    def test_bold_label_region_exempt_by_default(self):
        from verbose_gates import check_verbose_paragraphs
        lines = ["**A3.2 Assignments and Other Types of Statements.** " + self.WALL]
        self.assertEqual(check_verbose_paragraphs(lines), [])

    def test_bold_label_region_flagged_for_desc(self):
        from verbose_gates import check_verbose_paragraphs
        lines = ["**A3.2 Assignments and Other Types of Statements.** " + self.WALL]
        hits = check_verbose_paragraphs(lines, label_exempt=False)
        self.assertEqual(len(hits), 1, hits)
        self.assertIn("墙式散文", hits[0])

    def test_inline_math_no_longer_buys_impunity_for_desc(self):
        from verbose_gates import check_verbose_paragraphs
        lines = ["The generating function codes $x$ as " + self.WALL]
        self.assertEqual(check_verbose_paragraphs(lines, math_exempt=True), [])
        hits = check_verbose_paragraphs(lines, label_exempt=False, math_exempt=False)
        self.assertEqual(len(hits), 1, hits)

    def test_tier1_exercise_stem_stays_exempt_under_desc_strict(self):
        """Tier 1 题面即使在 desc 单元里也不得被要求「改写」（改了就是坏题面）。"""
        from verbose_gates import check_verbose_paragraphs
        for head in ("58. ", "**5.** ", "Exercise 62. ", "(a) "):
            lines = [head + self.WALL]
            self.assertEqual(
                check_verbose_paragraphs(lines, label_exempt=False,
                                         math_exempt=False),
                [], head)

    def test_printed_run_in_heading_is_not_an_item_stem(self):
        """`**Remark.**` / `**Historical Note.**` = 印刷小标题，不是条目号，照抄要报。"""
        from verbose_gates import check_verbose_paragraphs
        for head in ("**Remark.** ", "**Historical Note.** ", "**A3.2 Assignments.** "):
            lines = [head + self.WALL]
            hits = check_verbose_paragraphs(lines, label_exempt=False,
                                            math_exempt=False)
            self.assertEqual(len(hits), 1, (head, hits))

    def test_short_labelled_paragraph_still_passes(self):
        """收紧只拦「长段/墙式段」，短粗体段照常放行（不误伤正常导语）。"""
        from verbose_gates import check_verbose_paragraphs
        lines = ["**A3.3 Comments.** Statements in curly braces are not executed."]
        self.assertEqual(
            check_verbose_paragraphs(lines, label_exempt=False, math_exempt=False),
            [])

    def test_unit_metadata_comment_is_not_prose(self):
        """`<!-- book-summarizer DONE … -->` 是机器标记：不得并入正文段落计量。

        真值：Rosen 8e 首跑工作量的 L1 命中几乎全部把该注释行当成散文首行
        （虚增长度 + 报错行号 + 稀释重合率）。
        """
        from verbose_gates import check_verbose_paragraphs, VERBOSE_PARA_HARD_CHARS
        head = "<!-- book-summarizer DONE unit: id=0081 type=desc key=D19 name=x -->"
        lines = [head, "", "Some short lead-in sentence."]
        self.assertEqual(
            check_verbose_paragraphs(lines, label_exempt=False, math_exempt=False),
            [])
        near_wall = self.WALL[:VERBOSE_PARA_HARD_CHARS - 30]
        lines = [head, "", near_wall]
        hits = check_verbose_paragraphs(lines, label_exempt=False, math_exempt=False)
        self.assertEqual(hits, [], "注释行不得把段落顶过可读性硬顶")

    def test_bullet_list_is_not_one_wall_paragraph(self):
        """长列表逐条计量：术语表这类合法条目列表不得被合成一面「散文墙」。"""
        from verbose_gates import check_verbose_paragraphs
        lines = ["- **algorithm**: " + self.WALL]
        self.assertEqual(len(check_verbose_paragraphs(
            lines, label_exempt=False, math_exempt=False)), 1)
        items = ["- **algorithm**: a finite sequence of precise instructions.",
                 "- **integer**: a number without a fractional part.",
                 "- **theorem**: a statement that can be shown to be true."]
        self.assertEqual(check_verbose_paragraphs(
            list(items), label_exempt=False, math_exempt=False), [])

    def test_check_body_wires_desc_strictly_and_degrades_without_context(self):
        """判据 19 端到端：有 ext/ch 才跑照抄闸；无上下文 = 该闸不调用（不误伤）。"""
        from verbose_gates import VERBOSE_PARA_HARD_CHARS
        self.assertGreater(len(self.WALL), VERBOSE_PARA_HARD_CHARS)
        ok, probs = q.check_body(
            "desc", "", "**A3.2 Assignments.** " + self.WALL + "\n")
        self.assertTrue(ok, probs)



class TestMetaExcuseAndHollowExerciseUnit(unittest.TestCase):
    """判据 21（流水线元话语）+ 22（登记习题单元零题面）。

    真值：Rosen 8e ch5 §5.4 的习题单元整单元只有这段说明，一题未写。
    """

    NOTE = ("The contract node for the Section 5.4 exercise set covers only the "
            "printed page 381, where the heading of Section 5.4 appears; the "
            "numbered exercises for Section 5.4 are printed at the end of that "
            "section, outside this page group, so their statements are not "
            "reproduced in this unit.")

    def test_real_hollow_unit_fires_both_gates(self):
        ok, probs = q.check_body("exercise", "Recursive Algorithms 381",
                                 self.NOTE, content_blocks=2)
        self.assertFalse(ok)
        self.assertTrue(any("流水线元话语" in p for p in probs), probs)
        self.assertTrue(any("认不出任何一条习题条目" in p for p in probs), probs)

    def test_bold_ordinal_entry_form_counts_as_statement(self):
        """Katok 8e 形态：习题条目用**契约键序标的粗体头**（无集内序号），不得误判空心。"""
        ok, probs = q.check_body(
            "exercise", "20.1.3. Let B_k be the set defined in Exercise 1.9.10",
            "**20.1.3.** Let $B_{k}\\subset\\Omega_{2}$ be the set defined in Exercise "
            "1.9.10. Prove that $S_k$ has a unique measure of maximal entropy.\n",
            key="20.1.3", content_blocks=8)
        self.assertTrue(ok, probs)

    def test_benign_use_of_word_unit_not_flagged(self):
        ok, probs = q.check_body(
            "desc", "", "One unit of the algebra generates the whole group, "
                        "and every element has finite order in this sense.")
        self.assertTrue(ok, probs)

    def test_faithful_quote_from_source_is_exempt(self):
        """命中措辞原样见于书源原文 = Tier 1 忠实引用，不享「掩盖缺失」的推定。"""
        ok, probs = q.check_body("desc", "", "As the author notes, the proof is "
                                 "not reproduced in this unit of the exposition.",
                                 source_text="the proof is not reproduced in this unit")
        self.assertTrue(ok, probs)

    def test_zero_statement_gate_scoped_to_exercise_units(self):
        """desc 单元没有题号是正常的（判据 22 只管契约登记的习题单元）。"""
        ok, probs = q.check_body("desc", "D4", "Some introductory prose only.",
                                 content_blocks=3)
        self.assertTrue(ok, probs)

    def test_exercise_unit_with_statements_passes_22(self):
        body = "**Exercise Set 5.4**\n\n1. a\n\n2. b\n\n3. c\n"
        ok, probs = q.check_body("exercise", "Recursive Algorithms 381", body,
                                 content_blocks=2)
        self.assertFalse(any("认不出任何一条习题条目" in p for p in probs), probs)

    def test_zero_block_exercise_node_exempt_from_22(self):
        """契约节点本就 0 内容块（幻影节点）时不判零题面——由判据 16 处理。"""
        ok, probs = q.check_body("exercise", "X", "Lead-in sentence only.\n",
                                 content_blocks=0)
        self.assertFalse(any("认不出任何一条习题条目" in p for p in probs), probs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
