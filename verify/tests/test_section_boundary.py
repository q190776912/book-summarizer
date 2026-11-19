# -*- coding: utf-8 -*-
"""S 层判据测试（lib/section_boundary.py）。

运行：
    python -m unittest verify.tests.test_section_boundary -v
    python verify/tests/test_section_boundary.py
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
import lib.boot as _boot
_boot.setup()

from lib.section_boundary import (PageCtx, _title_match, norm_alnum, norm_title,
                                  parse_headings, scan_chapter_files, scan_text)


def _find(findings, section):
    for f in findings:
        if f["section"] == section:
            return f
    return None


class SectionBoundarySignalsTest(unittest.TestCase):
    def test_split_sentence_across_heading(self):
        lines = [
            "# Chapter 1",
            "",
            "## § A",
            "",
            "This paragraph ends with the word",
            "",
            "## § B",
            "",
            "and the sentence continues here.",
        ]
        fs = scan_text(lines)
        b = _find(fs, "B")
        self.assertIsNotNone(b, fs)
        self.assertIn("split_sentence", b["kinds"])

    def test_dup_prev_detected(self):
        para = ("This paragraph belongs entirely to the previous section and it "
                "should never appear again after the next section heading.")
        lines = [
            "# Chapter 1",
            "",
            "## § A",
            "",
            para,
            "",
            "## § B",
            "",
            para,
        ]
        fs = scan_text(lines)
        b = _find(fs, "B")
        self.assertIsNotNone(b, fs)
        self.assertIn("dup_prev", b["kinds"])

    def test_title_match_is_whole_word(self):
        self.assertFalse(_title_match(norm_title("Linear Equations"),
                                      norm_title("Quasilinear Equations")))
        self.assertTrue(_title_match(norm_title("Riemannian Metrics"),
                                     norm_title("Riemannian Metrics")))
        # Whole-word prefix works on raw titles (callers normally pass
        # normalized titles, where only exact equality can match).
        self.assertTrue(_title_match("Smooth Maps",
                                     "Smooth Maps Between Manifolds"))

    def test_parse_headings_skips_chapter_and_item_titles(self):
        lines = [
            "# Chapter 8: Vector Fields",
            "## § First Section",
            "### Theorem 1.2",
            "## Second Section",
        ]
        hs = parse_headings(lines)
        self.assertEqual([h.title for h in hs], ["First Section", "Second Section"])

    def test_heading_late_from_page_geometry(self):
        prev = ("This body text is printed after the second heading even though "
                "it belongs to the first section.")
        nxt = ("The section really starts here with its own introductory body "
               "text and enough characters to match.")
        lines = [
            "## § First Section",
            "",
            prev,
            "",
            "## § Second Section",
            "",
            nxt,
        ]
        blocks = [
            (1, 400, norm_alnum("Second Section"), "Second Section"),
            (1, 600, norm_alnum(prev), prev),
            (1, 700, norm_alnum(nxt), nxt),
        ]
        fs = scan_text(lines, PageCtx(blocks=blocks))
        second = _find(fs, "Second Section")
        # Page geometry alone is weak evidence and must not raise a finding.
        self.assertIsNone(second, "纯页码几何不得单独报 heading_late: %r" % (fs,))

    def test_page_geometry_confirms_runin_heading_late(self):
        """有 run-in 标题文本证据时，页码几何才升级为 heading_late finding。"""
        prev = ("This body text is printed after the second heading even though "
                "it belongs to the first section, and it continues long enough "
                "to clear the body-character threshold of the run-in detector "
                "so the run-in signal fires and confirms the geometry.")
        nxt = ("The section really starts here with its own introductory body "
               "text and enough characters to match.")
        lines = [
            "## § First Section", "",
            "**Second Section.** " + prev, "",
            "## § Second Section", "", nxt,
        ]
        blocks = [
            (1, 400, norm_alnum("Second Section"), "Second Section"),
            (1, 600, norm_alnum(prev), prev),
            (1, 700, norm_alnum(nxt), nxt),
        ]
        fs = scan_text(lines, PageCtx(blocks=blocks))
        second = _find(fs, "Second Section")
        self.assertIsNotNone(second, fs)
        self.assertIn("heading_late", second["kinds"])

    def test_tail_snippet_detects_welded_desc_block(self):
        old = ("Old section body text that is printed before the heading and "
               "continues for a while so its head can be matched reliably. ")
        old = old * 2
        tail = ("new section opening text that is welded onto the old paragraph "
                "by a description unit and is printed only after the heading ")
        tail = tail * 3
        # A run-in with the section's own title is the text evidence that
        # upgrades the page-geometry tail signal to a real finding.
        prev_block = "**Second Section.** " + old + tail
        nxt = ("Body of the new section after the heading with enough text to "
               "avoid being skipped by the scanner.")
        lines = [
            "## § First Section",
            "",
            prev_block,
            "",
            "## § Second Section",
            "",
            nxt,
        ]
        blocks = [
            (1, 400, norm_alnum("Second Section"), "Second Section"),
            (1, 300, norm_alnum(old), old),
            (1, 600, norm_alnum(tail), tail),
        ]
        fs = scan_text(lines, PageCtx(blocks=blocks))
        second = _find(fs, "Second Section")
        self.assertIsNotNone(second, fs)
        self.assertIn("heading_late", second["kinds"])
        self.assertIn("tail of the last body block", second["detail"])

    def test_running_head_never_anchors_section(self):
        """页眉跑马行（含页码）不得充当节头锚点：否则页眉 y197 会把 y600
        的上一节正文判成「印在节头之后」的 heading_late，甚至跨章误判。"""
        prev = ("This body text belongs to the first section and is printed "
                "well before the real second heading on the same page.")
        nxt = ("The second section starts here with its own introductory body "
               "text long enough to be matched against the printed page.")
        lines = [
            "## § First Section", "", prev, "",
            "## § Second Section", "", nxt,
        ]
        header = "Second Section"
        blocks = [
            (1, 197, norm_alnum(header), header),   # 页眉同文
            (1, 199, "49", "49"),                   # 页码
            (1, 600, norm_alnum(prev), prev),
            (1, 900, norm_alnum(header), header),   # 真节头
            (1, 1000, norm_alnum(nxt), nxt),
        ]
        ctx = PageCtx(blocks=blocks)
        self.assertEqual(ctx.find_heading("Second Section"), (1, 900))
        fs = scan_text(lines, ctx)
        second = _find(fs, "Second Section")
        self.assertIsNone(second, "页眉锚点被排除后不得再报 heading_late: %r" % (second,))

    def test_intro_transition_not_late_start(self):
        """节标题后第一段已是正常引言，后面的 'Now we' 是节内过渡，非 late_start。"""
        lines = [
            "# Chapter 7",
            "",
            "## § Lie Subgroups",
            "",
            "Suppose G is a Lie group. A Lie subgroup of G is a subgroup endowed "
            "with a topology and smooth structure making it a Lie group.",
            "",
            "**Proposition 7.11.** Let G be a Lie group and H a subgroup.",
            "",
            "> **Proof.** We check that multiplication and inversion are smooth.",
            "",
            "Now we move beyond the open subgroups to more general Lie subgroups. "
            "The following proposition shows the possibilities are limited.",
        ]
        fs = scan_text(lines)
        sec = _find(fs, "Lie Subgroups")
        self.assertIsNone(sec, "正常引言 + 节内过渡不得报 late_start: %r" % (fs,))

    def test_delayed_intro_after_items_still_detected(self):
        """真错位：节标题后先是 item/proof，节引言被挤到后面，仍须报 late_start。"""
        lines = [
            "# Chapter X",
            "",
            "## § Overdetermined Systems",
            "",
            "**Theorem 19.27.** Let W be an open subset of R^n.",
            "",
            "> **Proof.** Long proof text here that is definitely structural enough "
            "to exceed the character threshold used by the delayed-intro signal "
            "and to make this a genuinely displaced section opening.",
            "",
            "接下来我们把弗罗贝尼乌斯定理应用于一类非线性超定偏微分方程。",
        ]
        fs = scan_text(lines)
        sec = _find(fs, "Overdetermined Systems")
        self.assertIsNotNone(sec, fs)
        self.assertIn("late_start", sec["kinds"])

    def test_discussion_after_theorems_not_late_start(self):
        """定理/证明之后的讨论段（'接下来我们…'）非迟到节引言，不报 late_start。"""
        blocks = ["## § Systems"]
        # several theorem/proof blocks first (discussion follows them)
        for n in range(1, 4):
            blocks += ["**Theorem X.%d.** A statement long enough to be a real item here." % n,
                       "> **Proof.** A proof paragraph with enough structure and text."]
        blocks += ["接下来我们把该定理应用于一类更一般的方程并展开讨论。"]
        fs = scan_text(blocks)
        sec = _find(fs, "Systems")
        self.assertIsNone(sec, "item 后讨论段不得报 late_start: %r" % (fs,))

    def test_no_page_geometry_still_runs(self):
        lines = [
            "## § A",
            "",
            "First body.",
            "",
            "## § B",
            "",
            "second body starts lowercase and then continues with enough extra "
            "words to make it a substantive paragraph beyond the short-tail "
            "threshold used to skip printed-page straddle fragments.",
        ]
        fs = scan_text(lines, None)
        b = _find(fs, "B")
        self.assertIsNotNone(b, fs)
        self.assertIn("lowercase_start", b["kinds"])


class SectionBoundaryFileMappingTest(unittest.TestCase):
    def test_split_files_map_to_real_file_and_line(self):
        para = ("This paragraph belongs entirely to the previous section and it "
                "should never appear again after the next section heading.")
        with tempfile.TemporaryDirectory() as d:
            f1 = os.path.join(d, "Chapter1_1_A.md")
            f2 = os.path.join(d, "Chapter1_2_B.md")
            with open(f1, "w", encoding="utf-8") as fh:
                fh.write("# Chapter 1\n\n## § A\n\n%s\n" % para)
            with open(f2, "w", encoding="utf-8") as fh:
                fh.write("# Chapter 1\n\n## § B\n\n%s\n" % para)
            findings, stats = scan_chapter_files([f1, f2], None)
        b = _find(findings, "B")
        self.assertIsNotNone(b, findings)
        self.assertIn("dup_prev", b["kinds"])
        self.assertEqual(b["file"], "Chapter1_2_B.md")
        self.assertEqual(b["file_line"], 3)  # duplicate chapter title is dropped in merge
        self.assertEqual(stats["files"], ["Chapter1_1_A.md", "Chapter1_2_B.md"])
        self.assertFalse(stats["page_geometry"])


class SectionBoundaryFalsePositiveRegressionTest(unittest.TestCase):
    """编号陈述形态 / 平行命题 / 编号定理标题的误报回归（2026-11 修复）。"""

    def test_orphan_proof_various_statement_formats(self):
        """合法陈述用字母号 / 编号在前 / 人名前缀 / 中英混合时，不得报孤立证明。"""
        statements = [
            "**Lemma A.1**: Let C be a complete locally small category.",
            "**8.3.1 (Lemma/Definition)**: If X is fibrant then the relation is an equivalence.",
            "**Krull's Theorem 6.11.1** The Galois group is the inverse limit of finite groups.",
            "**9.4.9 Barr 引理** 若 u 满足对一切代数都成立的条件则为标量。",
        ]
        for stmt in statements:
            lines = ["## § S", "", stmt, "",
                     "> **Proof.** We check the statement by a long argument that "
                     "is clearly a proof of the preceding item.", ""]
            fs = scan_text(lines)
            self.assertFalse(any("orphan_proof" in f["kinds"] for f in fs),
                             "%s 被误判为孤立证明: %r" % (stmt, fs))

    def test_orphan_proof_still_detected(self):
        """真·孤立证明（标题后直接是证明、无任何陈述）仍须报。"""
        lines = ["## § S", "",
                 "> **Proof.** A proof with no preceding statement at all, "
                 "long enough to be a substantive proof block.", ""]
        fs = scan_text(lines)
        self.assertTrue(any("orphan_proof" in f["kinds"] for f in fs), fs)

    def test_dup_within_parallel_math_statements_not_flagged(self):
        """模板相同但公式变量不同的对偶命题，字符相似度 >0.9 也不是重复。"""
        a = ("**Theorem 2.1.** Let $B' \\xrightarrow{\\mu} B \\xrightarrow{\\varepsilon} B''$ "
             "be an exact sequence of $\\Lambda$-modules. For every $\\Lambda$-module "
             "$A$ the induced sequence")
        b = ("**Theorem 2.2.** Let $A' \\xrightarrow{\\mu} A \\xrightarrow{\\varepsilon} A''$ "
             "be an exact sequence of $\\Lambda$-modules. For every $\\Lambda$-module "
             "$B$ the induced sequence")
        lines = ["## § S", "", a, "", "An intermediate remark.", "", b, "",
                 "A closing remark.", ""]
        fs = scan_text(lines)
        self.assertFalse(any("dup_within" in f["kinds"] for f in fs), fs)

    def test_dup_within_genuine_duplicate_still_flagged(self):
        """真·段内重复（散文或同公式）仍须报。"""
        para = ("This paragraph is genuinely duplicated inside the same section "
                "and it is long enough to clear the one-hundred character floor "
                "used by the intra-section duplicate detector.")
        lines = ["## § S", "", para, "", "Some other text here.", "", para, "",
                 "A final remark.", ""]
        fs = scan_text(lines)
        self.assertTrue(any("dup_within" in f["kinds"] for f in fs), fs)

    def test_dup_within_identical_math_still_flagged(self):
        """带数学的真重复（公式也相同）不得被数学 token 判据压下。"""
        para = ("Let $A \\to B$ be a map of modules and consider its induced "
                "sequence of homology groups in degree two. " * 3).strip()
        lines = ["## § S", "", para, "", "An intermediate remark.", "", para, "",
                 "A final remark.", ""]
        fs = scan_text(lines)
        self.assertTrue(any("dup_within" in f["kinds"] for f in fs), fs)

    def test_numbered_theorem_title_not_heading_early(self):
        """编号定理标题与节标题同名，不是「节 run-in 标题迟到」。"""
        lines = ["## § 12.4 Bertini's Theorem", "",
                 "Introductory body text about Bertini's theorem that is long "
                 "enough to count as substantive content before any item.", "",
                 "**12.4.2 Bertini's Theorem.** Suppose k is algebraically closed.", "",
                 "**12.4.3 Example.** An illustrative example.", ""]
        fs = scan_text(lines)
        self.assertFalse(any("heading_early" in f["kinds"] for f in fs), fs)

    def test_plain_proof_word_in_prose_not_orphan_proof(self):
        """'证明留给读者' / 'Proof of (4.2)' 是散文，不是证明块标题。"""
        for first in ("证明上半连续定理的关键在于如下想法，我们随后给出解释。",
                      "Proof of (4.2). We have to check several cases carefully."):
            lines = ["## § S", "", first, "",
                     "**Lemma A.1**: A genuine statement follows the introduction.", ""]
            fs = scan_text(lines)
            self.assertFalse(any("orphan_proof" in f["kinds"] for f in fs), fs)

    def test_heading_early_still_detected(self):
        """真·节 run-in 标题迟到（非编号条目标题）仍须报。"""
        lines = ["## § Smooth Maps", "",
                 "Considerable body text that belongs to the previous section "
                 "and sits before this section's own run-in title.", "",
                 "**Smooth Maps.** The actual section body starts here with its "
                 "own introductory content.", ""]
        fs = scan_text(lines)
        self.assertTrue(any("heading_early" in f["kinds"] for f in fs), fs)


class SectionBoundaryRegistryTest(unittest.TestCase):
    def test_layer_registered_non_blocking(self):
        from verify.script.register_all import LAYER_REGISTRY
        layer = LAYER_REGISTRY.get("S")
        self.assertIsNotNone(layer, "S layer is not registered")
        self.assertEqual(layer.name, "section-boundary")
        self.assertEqual(layer.order, 2)
        self.assertFalse(layer.auto_fixable)


if __name__ == "__main__":
    unittest.main()
