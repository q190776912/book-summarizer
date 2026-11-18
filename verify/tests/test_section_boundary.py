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
        self.assertIsNotNone(second, fs)
        self.assertIn("heading_late", second["kinds"])

    def test_tail_snippet_detects_welded_desc_block(self):
        old = ("Old section body text that is printed before the heading and "
               "continues for a while so its head can be matched reliably. ")
        old = old * 2
        tail = ("new section opening text that is welded onto the old paragraph "
                "by a description unit and is printed only after the heading ")
        tail = tail * 3
        prev_block = old + tail
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

    def test_no_page_geometry_still_runs(self):
        lines = [
            "## § A",
            "",
            "First body.",
            "",
            "## § B",
            "",
            "second body starts lowercase.",
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
