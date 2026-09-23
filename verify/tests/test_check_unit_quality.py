"""Regression tests for check_unit_quality + gate_units render mapping.

门控曾经放行「未审阅改好」的单元（2026-09-09 用户复核发现）：质量校验异常被
静默吞掉（fail-open）、内容审阅类残留无检测、无真实 KaTeX 渲染。本文件锁定
修复后的行为：
  1. QED 结尾框「口/□」独立行 / OCR 乱码重复片段 / 编码损坏字符 /
     单元内私造标题行 → 必须判不通过；
  2. 干净单元（合法 KaTeX + 粗体标签）→ 通过；
  3. section 单元不做质量校验（只确认 DONE）；
  4. gate_units._render_check_chapter 把真渲染错误按行号映射回所属单元，
     渲染执行失败 fail-closed。
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
import lib.boot as _boot  # noqa: E402
_boot.setup()

import check_unit_quality as cq  # noqa: E402
import gate_units as gu  # noqa: E402


def _item(body):
    return cq.check_body("item", "定理 1.1", body)


class ContentReviewChecksTest(unittest.TestCase):
    def test_clean_item_ok(self):
        body = ("**定理 1.1**：设 $f$ 在 $[0,1]$ 上连续，则 "
                "$\\int_{0}^{1} f(x)\\,dx > 0$。\n\n"
                "> **证明**：由连续性，$f(x) \\ge 0$ 且不恒为零，故积分非负。\n")
        ok, probs = _item(body)
        self.assertTrue(ok, probs)

    def test_qed_box_flagged(self):
        body = "**定理 1.1**：设 $f$ 连续。\n\n> **证明**：显然。\n>\n口\n"
        ok, probs = _item(body)
        self.assertFalse(ok, probs)
        self.assertTrue(any("QED" in p for p in probs), probs)

    def test_qed_box_in_blockquote_flagged(self):
        body = "**定理 1.1**：设 $f$ 连续。\n\n> **证明**：显然。\n>\n> □\n"
        ok, probs = _item(body)
        self.assertFalse(ok, probs)
        self.assertTrue(any("QED" in p for p in probs), probs)

    def test_repeated_fragment_flagged(self):
        frag = "这是一段重复出现的乱码文字内容"  # 14 字符
        body = "**定义 1.2**：设 " + frag * 3 + " 为开集。\n"
        ok, probs = cq.check_body("item", "定义 1.2", body)
        self.assertFalse(ok, probs)
        self.assertTrue(any("重复" in p for p in probs), probs)

    def test_replacement_char_flagged(self):
        body = "**定义 1.2**：设 $X$ 为\ufffd集合。\n"
        ok, probs = _item(body)
        self.assertFalse(ok, probs)
        self.assertTrue(any("编码损坏" in p for p in probs), probs)

    def test_heading_inside_item_flagged(self):
        body = "## §1.2 自造标题\n\n**定义 1.2**：设 $G$ 为群。\n"
        ok, probs = cq.check_body("item", "定义 1.2", body)
        self.assertFalse(ok, probs)
        self.assertTrue(any("标题行" in p for p in probs), probs)

    def test_section_unit_not_quality_checked(self):
        ok, probs = cq.check_body("section", "§1.1", "## §1.1 标题\n")
        self.assertTrue(ok, probs)

    def test_odd_dollar_flagged(self):
        body = "**定理 1.3**：设 $x 为实数。\n"
        ok, probs = _item(body)
        self.assertFalse(ok, probs)


class FenceFormChecksTest(unittest.TestCase):
    """F7 围栏形态：单行 $$ 块 / 缺空 > 行 / 块外 \\tag（ch4 事故回归）。"""

    def test_single_line_display_flagged(self):
        body = ("**定理 4.1**：设 $a_{ij}$ 有界，则\n\n"
                "$$ a_{ij}(x)\\xi_i\\xi_j \\ge \\lambda|\\xi|^2, $$\n")
        ok, probs = _item(body)
        self.assertFalse(ok, probs)
        self.assertTrue(any("single-line display math" in p for p in probs), probs)

    def test_multiline_display_ok(self):
        body = ("**定理 4.1**：设 $a_{ij}$ 有界，则\n\n$$\n"
                "a_{ij}(x)\\xi_i\\xi_j \\ge \\lambda|\\xi|^2\n$$\n\n"
                "> **证明**：显然。\n>\n> $$\n> \\lambda > 0\n> $$\n")
        ok, probs = _item(body)
        self.assertTrue(ok, probs)

    def test_missing_empty_bq_line_flagged(self):
        body = ("**定理 4.1**：设 $a_{ij}$ 有界。\n\n"
                "> **证明**：由估计\n> $$\n> \\lambda > 0\n> $$\n")
        ok, probs = _item(body)
        self.assertFalse(ok, probs)
        self.assertTrue(any("missing empty > line" in p for p in probs), probs)

    def test_missing_blank_line_before_dollar_flagged(self):
        body = "**定义 4.2**：称 $X$ 可分，若\n$$\nX = \\overline{D}\n$$\n"
        ok, probs = cq.check_body("item", "定义 4.2", body)
        self.assertFalse(ok, probs)
        self.assertTrue(any("missing blank line before opening $$" in p
                            for p in probs), probs)

    def test_tag_outside_math_flagged(self):
        body = ("**定理 4.3**：结论如下 \\tag{4.7}\n\n$$\n\\lambda > 0\n$$\n")
        ok, probs = _item(body)
        self.assertFalse(ok, probs)
        self.assertTrue(any("块外" in p or "$$ 块内" in p for p in probs), probs)


class TagReconcileTest(unittest.TestCase):
    """12) 单元级公式序标对账：契约 tag 为真值，缺失/编造均不通过。"""

    BODY = ("**定理 4.1**：设 $a_{ij}$ 有界，则\n\n$$\n"
            "a_{ij}(x)\\xi_i\\xi_j \\ge \\lambda|\\xi|^2 \\tag{4.1}\n$$\n")

    def test_missing_tag_flagged(self):
        ok, probs = cq.check_body("item", "定理 4.1", self.BODY,
                                  expected_tags=["4.1", "4.2"])
        self.assertFalse(ok, probs)
        self.assertTrue(any("缺编号公式" in p and "4.2" in p for p in probs), probs)

    def test_fabricated_tag_flagged(self):
        ok, probs = cq.check_body("item", "定理 4.1", self.BODY,
                                  expected_tags=["4.2"])
        self.assertFalse(ok, probs)
        self.assertTrue(any("编造编号" in p and "4.1" in p for p in probs), probs)

    def test_matching_tags_ok(self):
        ok, probs = cq.check_body("item", "定理 4.1", self.BODY,
                                  expected_tags=["4.1"])
        self.assertTrue(ok, probs)

    def test_no_expected_tags_skips(self):
        ok, probs = cq.check_body("item", "定理 4.1", self.BODY)
        self.assertTrue(ok, probs)


class FalseOmissionClaimTest(unittest.TestCase):
    """15) 假省略声明闸：有单元的习题节点必为 consolidated=false，写「省略」即虚假。

    回归来源：Katok ch20 的 22 道逐节习题（20.1.1-20.4.4）被一句
    「Exercises for §20.4 are collected as a consolidated problem set and omitted
    here.」整体抹掉，门控当时全绿——措辞掩盖缺失，必须机械拦下。
    """

    def test_en_placeholder_flagged(self):
        body = ("**20.4.1.** Exercises for §20.4 are collected as a consolidated "
                "problem set and omitted here.\n")
        ok, probs = cq.check_body("exercise", "20.4.1", body)
        self.assertFalse(ok, probs)
        self.assertTrue(any("假省略声明" in p for p in probs), probs)

    def test_cn_placeholder_flagged(self):
        body = "**习题 20.1.3**：§20.1 的习题收集为综合习题集，此处省略。\n"
        ok, probs = cq.check_body("exercise", "20.1.3", body)
        self.assertFalse(ok, probs)
        self.assertTrue(any("假省略声明" in p for p in probs), probs)

    def test_placeholder_in_desc_flagged(self):
        body = "本节习题不再收录。\n"
        ok, probs = cq.check_body("desc", "D1", body)
        self.assertFalse(ok, probs)

    def test_real_exercise_ok(self):
        body = ("**20.4.1.** Prove the counterpart of Theorem 20.4.1 for Anosov "
                "flows $\\varphi^{t}$ on a compact manifold $M$.\n")
        ok, probs = cq.check_body("exercise", "20.4.1", body)
        self.assertTrue(ok, probs)

    def test_faithful_book_quote_exempted(self):
        """契约原文豁免：命中措辞原样见于书源原文 = Tier 1 忠实保留，不判假省略。

        回归来源：Leinster BCT Example 6.3.11 原书即写 "a little cardinal
        arithmetic, omitted here"，被闸误杀（2026-09-23）。"""
        body = ("> **Example 6.3.11**: ... the comma category $(A \\Rightarrow U)$ "
                "has a weakly initial set. This requires a little cardinal "
                "arithmetic, omitted here; see Exercise 6.3.24.\n")
        src = ("has a weakly initial set. This requires a little cardinal "
               "arithmetic, omitted here; see Exercise 6.3.24.")
        ok, probs = cq.check_body("item", "6.3-11", body,
                                  source_text=src)
        self.assertTrue(ok, probs)

    def test_faithful_quote_without_source_ctx_still_flagged(self):
        """fail-closed：无 source_text / source_text 不含该措辞 → 照常判 FAIL。"""
        body = "**6.3.11** ... cardinal arithmetic, omitted here.\n"
        ok1, _ = cq.check_body("item", "6.3-11", body)
        ok2, _ = cq.check_body("item", "6.3-11", body,
                               source_text="unrelated contract text")
        ok3, _ = cq.check_body("exercise", "6.3.24",
                               "**习题 6.3.24**：此处省略。\n",
                               source_text="... omitted here ...")
        self.assertFalse(ok1)
        self.assertFalse(ok2)
        self.assertFalse(ok3)

    def test_benign_math_omission_in_prose_passes(self):
        """散文单元的「omit」数学用法不构成省略声明（Katok ch5 D21 回归）。

        原句说的是第一张坐标卡不覆盖竖直向下向量、需第二张卡——这是正文内容本身，
        不是「总结把内容省掉了」。措辞处局部上下文无内容指向词 → 放行。"""
        body = ("Then $\\Phi:(t,u,v)\\mapsto p$ is locally a diffeomorphism; "
                "a second chart starting from $-q$ covers the vertically "
                "downward vectors omitted here.\n")
        ok, probs = cq.check_body("desc", "D21", body)
        self.assertTrue(ok, probs)

    def test_long_prose_with_faraway_proof_word_still_flagged(self):
        """豁免只在声明**局部**判内容指向：正文别处出现 proof 不影响判定。"""
        body = ("The exercises for \\S 5.2 are collected as a consolidated "
                "problem set and omitted here.\n\n"
                + "Some later paragraph mentions the proof of a lemma. " * 8)
        ok, probs = cq.check_body("desc", "D7", body)
        self.assertFalse(ok, probs)
        self.assertTrue(any("假省略声明" in p for p in probs), probs)

    def test_exercise_unit_never_gets_prose_exemption(self):
        """习题单元不适用散文豁免：即便措辞处无「习题」字样也 FAIL（fail-closed）。"""
        body = "This follows from the discussion, omitted here.\n"
        ok, probs = cq.check_body("exercise", "5.1.3", body)
        self.assertFalse(ok, probs)
        self.assertTrue(any("假省略声明" in p for p in probs), probs)


class PhantomExerciseEntryTest(unittest.TestCase):
    """16) 幻影习题条目闸（单元级）+ ⑨ 章级习题重号闸。

    回归来源：Katok 全书 24 处「OCR 续行碎片被切成独立习题条目」——碎片标题起于
    句中（`) the smoothness of…` / `for fows.`）、节点零内容块、或整段吞并后续小节
    正文（ch9 的 9.1.5 吞了 §9.2 全节 684 块 4 张图）。ch2 事故链：重号条目 →
    空单元 → 假省略措辞，一路绿灯到拼接。
    """

    def _p(self, *a, **kw):
        return cq.check_body(*a, **kw)[1]

    def test_mid_sentence_title_flagged(self):
        probs = self._p("exercise", ") the smoothness of Ws(c) and Wu(c) implies",
                        "**6.4.5.** Construct an example of a locally maximal "
                        "hyperbolic set $\\Lambda$.\n",
                        key="6.4.5", content_blocks=5)
        self.assertTrue(any("起于句中" in p for p in probs), probs)

    def test_zero_block_node_flagged(self):
        probs = self._p("exercise", "for fows.",
                        "**20.1.5.** Find a counterpart of Theorem 20.1.6.\n",
                        key="20.1.5", content_blocks=0)
        self.assertTrue(any("零内容" in p for p in probs), probs)

    def test_cross_section_tag_flagged(self):
        probs = self._p("exercise", "9.1.5. Construct a function",
                        "**Exercise 9.1.5**: Construct a $C^\\infty$ function.\n",
                        key="9.1.5", content_blocks=684,
                        expected_tags=["9.2.1", "9.2.2"])
        self.assertTrue(any("吞并" in p and "9.2" in p for p in probs), probs)

    def test_cross_section_image_flagged(self):
        probs = self._p("exercise", "9.1.5. Construct a function",
                        "**Exercise 9.1.5**: Construct a $C^\\infty$ function.\n",
                        key="9.1.5", content_blocks=684,
                        expected_images=["figure/ch09_fig9.2.1.png"])
        self.assertTrue(any("插图" in p for p in probs), probs)

    def test_same_section_tag_not_flagged(self):
        body = ("**12.2.2\\***. Modify the construction so that $|f'(x) - f'(y)| "
                "< |x - y| |\\log|x - y||^{1+\\beta}$. \\tag{12.2.2}\n")
        probs = self._p("exercise", "12.2.2. Modify the construction", body,
                        key="12.2.2", content_blocks=44,
                        expected_tags=["12.2.2"])
        self.assertFalse(any("吞并" in p for p in probs), probs)

    def test_clean_exercise_not_flagged(self):
        ok, probs = cq.check_body(
            "exercise", "20.1.3. Let B_k be the set defined in Exercise 1.9.10",
            "**20.1.3.** Let $B_{k}\\subset\\Omega_{2}$ be the set defined in "
            "Exercise 1.9.10. Prove that $S_k$ has a unique measure of maximal "
            "entropy.\n",
            key="20.1.3", content_blocks=8, expected_tags=[], expected_images=[])
        self.assertTrue(ok, probs)

    def test_chapter_duplicate_exercise_key_flagged(self):
        units = [{"type": "exercise", "key": "2.1.7", "file": "0020_exercise.md"},
                 {"type": "exercise", "key": "2.1.7", "file": "0021_exercise.md"},
                 {"type": "exercise", "key": "2.1.8", "file": "0022_exercise.md"},
                 {"type": "item", "key": "定理2.1.1", "file": "0003_item.md"}]
        probs = gu._check_exercise_key_uniqueness(units)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("重号", probs[0])
        self.assertIn("2.1.7", probs[0])
        self.assertNotIn("2.1.8", probs[0])

    def test_chapter_unique_exercise_keys_pass(self):
        units = [{"type": "exercise", "key": "2.1.%d" % i, "file": "f%d.md" % i}
                 for i in range(1, 4)]
        self.assertEqual(gu._check_exercise_key_uniqueness(units), [])


class PhantomExerciseExemptionTest(unittest.TestCase):
    """16) 幻影闸两条形态豁免（Leinster 37 处误伤回归）：子题标号起头 / name
    自带完整题面且正文非空——Katok 残渣（两三词碎片、空正文）照旧拦。"""

    def _p(self, *a, **kw):
        return cq.check_body(*a, **kw)[1]

    def test_part_label_title_exempted(self):
        probs = self._p("exercise", "(b) Prove that the composite of two adjunctions",
                        "**6.2.8(b)** Prove that the composite of two "
                        "adjunctions is an adjunction.\n",
                        key="6.2-8", content_blocks=3)
        self.assertFalse(any("起于句中" in p for p in probs), probs)

    def test_statement_in_name_zero_blocks_exempted(self):
        probs = self._p(
            "exercise",
            "Exercises 1.4.1 What is the coproduct of two objects of Set, "
            "and of Cat?",
            "**1.4.1** What is the coproduct of two objects of "
            "$\\mathbf{Set}$, and of $\\mathbf{Cat}$?\n",
            key="1.4-1", content_blocks=0)
        self.assertFalse(any("零内容" in p for p in probs), probs)

    def test_numberless_group_heading_exempted(self):
        probs = self._p(
            "exercise", "Interactions between adjoint functors and limits",
            "**Interactions between adjoint functors and limits**: right "
            "adjoints preserve limits.\n",
            key="6_3", content_blocks=0)
        self.assertFalse(any("零内容" in p for p in probs), probs)

    def test_empty_body_not_exempted(self):
        probs = self._p(
            "exercise",
            "Exercises 1.4.1 What is the coproduct of two objects of Set, "
            "and of Cat?",
            "", key="1.4-1", content_blocks=0)
        self.assertTrue(any("零内容" in p for p in probs), probs)

    def test_short_fragment_zero_blocks_still_flagged(self):
        probs = self._p("exercise", "for fows.",
                        "**20.1.5.** Find a counterpart of Theorem 20.1.6.\n",
                        key="20.1.5", content_blocks=0)
        self.assertTrue(any("零内容" in p for p in probs), probs)

    def test_short_statement_exempted_via_bold_ordinal(self):
        probs = self._p("exercise", "Exercises 4.3.15 Prove Lemma 4.3.8",
                        "**Exercise 4.3.15.** Prove Lemma 4.3.8.\n",
                        key="4.3-15", content_blocks=0)
        self.assertFalse(any("零内容" in p for p in probs), probs)

    def test_mid_sentence_name_blocks_ordinal_exemption(self):
        probs = self._p("exercise", "for fows. Find a counterpart of Theorem",
                        "**20.1.5.** Find a counterpart of Theorem 20.1.6.\n",
                        key="20.1.5", content_blocks=0)
        self.assertTrue(any("零内容" in p for p in probs), probs)

    def test_mid_sentence_continuation_zero_blocks_still_flagged(self):
        probs = self._p(
            "exercise", "and the Digression on arithmetic on page 69.",
            "**6.3.12** and the Digression on arithmetic on page 69, and "
            "comment on it.\n",
            key="6.3-12", content_blocks=0)
        self.assertTrue(any("零内容" in p or "起于句中" in p for p in probs), probs)


class RenderMappingTest(unittest.TestCase):
    def _make_fake(self, tmp):
        """构造最小 extract 目录：units/ch1/ 下两个 DONE 单元（一好一坏公式）。"""
        out_dir = os.path.join(tmp, "book_structure", "units", "ch1")
        os.makedirs(out_dir, exist_ok=True)
        good = ("<!-- book-summarizer DONE unit: id=0001 type=item key=1.1-1 "
                "name=1.1-1 Definition. -->\n**定义 1.1**：设 $x$ 为实数。\n")
        bad = ("<!-- book-summarizer DONE unit: id=0002 type=item key=1.1-2 "
                "name=1.1-2 Theorem. -->\n**定理 1.2**：\n\n$$\n\\frac{1}{2\n$$\n")
        with open(os.path.join(out_dir, "0001_item.md"), "w", encoding="utf-8") as f:
            f.write(good)
        with open(os.path.join(out_dir, "0002_item.md"), "w", encoding="utf-8") as f:
            f.write(bad)
        units = [
            {"file": "0001_item.md", "type": "item", "key": "1.1-1", "name": "1.1-1 Definition."},
            {"file": "0002_item.md", "type": "item", "key": "1.1-2", "name": "1.1-2 Theorem."},
        ]
        return out_dir, units

    def test_render_error_mapped_to_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            out_dir, units = self._make_fake(tmp)
            problems = gu._render_check_chapter(tmp, out_dir, units)
            self.assertTrue(problems, "坏公式必须被真渲染抓到")
            self.assertTrue(any("0002_item.md" in p for p in problems), problems)
            self.assertFalse(any("0001_item.md" in p for p in problems), problems)

    def test_render_fail_closed_on_missing_toolchain(self):
        """node 缺失等基础设施问题必须记为问题（fail-closed），不得静默通过。"""
        with tempfile.TemporaryDirectory() as tmp:
            out_dir, units = self._make_fake(tmp)
            import katex_render
            real = katex_render.run_render_check
            katex_render.run_render_check = lambda p: ["[render] node not found — "
                                                       "genuine LaTeX syntax errors NOT checked (heuristic-only fallback)"]
            try:
                problems = gu._render_check_chapter(tmp, out_dir, units)
            finally:
                katex_render.run_render_check = real
            self.assertTrue(problems, "工具链缺失必须 fail-closed")
            self.assertTrue(any("公式渲染检查" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main()
