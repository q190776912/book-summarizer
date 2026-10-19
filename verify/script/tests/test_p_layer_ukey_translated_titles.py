"""Regression test: U 键（合成节键）标题兜底对**译版标题**不假阳缺节。

Axler《Measure, Integration & Real Analysis》ch12 小节印面无序标 → 契约键
`U1…U6`（build_structure 合成键），P 层缺节闸走「归一化标题集合精确匹配」兜底。
EN 侧标题即印刷标题（`## § Probability Spaces`）→ 精确命中；CN 侧按写作规则
带 `(English)` 源书标题（`## § 概率空间 (Probability Spaces)`），译名不等于
契约标题 → 旧判据把 6/6 节全报成 `## §U1` 缺失（实测 2026-10-19）。

修复 = `_md_section_titles` 把标题**尾部英文括号段**一并入集（仍为精确匹配，
不放宽为互含）。断言正反两侧：
  1. CN 译名标题满足全部 U 键（0 缺节）；
  2. EN 源标题行为零回归；
  3. 真缺一节仍必须报（修复不得吞真缺）；
  4. 无尾括号的标题不虚构额外键。
"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..")))
from lib import boot  # noqa: E402
boot.setup()

import verify.verbose_gates.script.verbose_gates as vg  # noqa: E402

CFG = types.SimpleNamespace(sections_unnumbered=False)

CH12_SECS = [
    ("U1", "Probability Spaces"),
    ("U2", "Independent Events and Independent Random Variables"),
    ("U3", "Variance and Standard Deviation"),
    ("U4", "Conditional Probability and Bayes' Theorem"),
    ("U5", "Distribution and Density Functions of Random Variables"),
    ("U6", "Weak Law of Large Numbers"),
]

CN_LINES = [
    "# 第 12 章：概率测度 (Chapter 12: Probability Measures)",
    "",
    "## § 概率空间 (Probability Spaces)",
    "text",
    "## § 独立事件与独立随机变量 (Independent Events and Independent Random Variables)",
    "text",
    "## § 方差与标准差 (Variance and Standard Deviation)",
    "text",
    "## § 条件概率与 Bayes 定理 (Conditional Probability and Bayes' Theorem)",
    "text",
    "## § 随机变量的分布函数与密度函数 (Distribution and Density Functions of Random Variables)",
    "text",
    "## § 大数弱定律 (Weak Law of Large Numbers)",
    "text",
]

EN_LINES = [
    "# Chapter 12: Probability Measures",
    "",
    "## § Probability Spaces",
    "text",
    "## § Independent Events and Independent Random Variables",
    "text",
    "## § Variance and Standard Deviation",
    "text",
    "## § Conditional Probability and Bayes' Theorem",
    "text",
    "## § Distribution and Density Functions of Random Variables",
    "text",
    "## § Weak Law of Large Numbers",
    "text",
]


def _run(sections, md_lines, monkey):
    orig = vg._load_contract
    vg._load_contract = lambda ext, ch: (sections, set(), [])
    try:
        return vg.check_missing_sections(md_lines, ext_dir=None, ch=monkey, cfg=CFG)
    finally:
        vg._load_contract = orig


class TestUKeyTranslatedTitles(unittest.TestCase):
    def test_cn_translated_titles_satisfy_u_keys(self):
        out = _run(CH12_SECS, CN_LINES, "12")
        self.assertEqual(out, [], f"译版尾括号英文标题未命中 U 键兜底: {out}")

    def test_en_source_titles_zero_regression(self):
        out = _run(CH12_SECS, EN_LINES, "12")
        self.assertEqual(out, [], f"EN 源标题行为回归: {out}")

    def test_missing_section_still_flagged(self):
        secs = [("U1", "Probability Spaces"), ("U2", "Weak Law of Large Numbers")]
        lines = ["## § 概率空间 (Probability Spaces)"]
        out = _run(secs, lines, "12")
        self.assertEqual(len(out), 1, f"真缺节被吞: {out}")
        self.assertIn("U2", out[0])

    def test_no_paren_title_adds_no_extra_key(self):
        titles = vg._md_section_titles(["## § Weak Law of Large Numbers"])
        self.assertEqual(titles, {"weak law of large numbers"})

    def test_cn_title_indexes_both_forms(self):
        titles = vg._md_section_titles(["## § 概率空间 (Probability Spaces)"])
        self.assertIn("概率空间 (probability spaces)", titles)
        self.assertIn("probability spaces", titles)


if __name__ == "__main__":
    unittest.main(verbosity=2)
