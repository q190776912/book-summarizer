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
