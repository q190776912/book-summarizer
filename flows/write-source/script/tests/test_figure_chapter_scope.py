"""Regression test: 插图跨「节」误判根治（Rising Sea ch5/ch7 2026-09-25）。

章级图号书（ordinal type2 scope2，如 Vakil/Katok/Weibel 的 ``Figure 5.2`` = 第 5 章
第 2 图）里，图号第二段是章内序号、与所属小节无关。旧判据用 ``_FIG_SECTION_RE`` 把
``fig5.2`` 反推成「§5.2 的图」，于是 §5.5 里 Exercise 5.5.G 正常携带的 Figure 5.2 被误
判为跨节吞并，卡死门控。锁死：同章插图（含别小节）一律放行；只有跨「章」插图才判。
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, str(Path(_ROOT) / "flows" / "write-source" / "script"))

import check_unit_quality as cuq  # noqa: E402


def _probs(key, images, tags=None):
    return cuq.phantom_exercise_problems(
        "EXERCISE (CF. (5.5.3.1)).", 3, tags or [], images, key, body="x")


class TestFigureChapterScope(unittest.TestCase):
    def test_same_chapter_other_section_ok(self):
        # Figure 5.2 (2nd fig of ch5) legitimately embedded in Exercise 5.5.G (§5.5)
        self.assertEqual(_probs("5.5.G", ["figure/ch05_fig5.2.png"]), [])

    def test_multi_figures_same_chapter_ok(self):
        self.assertEqual(_probs("7.3.G", [
            "figure/ch07_fig7.2.png", "figure/ch07_fig7.4.png",
            "figure/ch07_fig7.5.png"]), [])

    def test_cross_chapter_still_flagged(self):
        probs = _probs("5.5.G", ["figure/ch06_fig6.1.png"])
        self.assertTrue(any("别章插图" in p for p in probs), probs)

    def test_leading_zero_chapter_ok(self):
        # ch05 vs key 5.x — zero padding must not create a false cross-chapter hit
        self.assertEqual(_probs("5.5.G", ["figure/ch05_fig5.12.png"]), [])

    def test_appendix_letter_chapter_ok(self):
        self.assertEqual(_probs("A.3.B", ["figure/appendixA_figA.2.png"]), [])

    def test_appendix_cross_letter_flagged(self):
        probs = _probs("A.3.B", ["figure/appendixB_figB.1.png"])
        self.assertTrue(any("别章插图" in p for p in probs), probs)


if __name__ == "__main__":
    unittest.main()
