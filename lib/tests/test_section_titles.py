"""Tests for lib/section_titles.py — 章级闸 ⑰「节标题折行截短」。

Run:  python lib/tests/test_section_titles.py

负向用例锁的是 Rosen《离散数学》8e 实测缺陷（全书 623 节点里 34 个中招，此前所有闸门
全绿）：原书节题排两行时抽取器只取第一行 → 契约 name 残缺（`6.1 The Basics of`），
顺着拆分灌进单元 H2、首行 name=、manifest 与最终 md 文件名。两种半修形态都要拦：
(a) 写手只补了单元 H2、契约照旧残缺（SSOT 与成品分叉，重拆即回退）；
(b) 契约/单元双双残缺（成品直接是残题，如 `8.5 Inclusion-`）。
正向用例锁零假阳：单个词的合法节题、并列同义词、粘连页码残渣、撇号异形、
译文标题（CJK 虚词结尾合法，「……是如何陈述的」）。
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

from section_titles import (clean_title, dangling_reason,  # noqa: E402
                            norm_title, title_problems)


def _contract(pairs):
    """[(key, name)] -> 形如分章契约的嵌套 dict。"""
    return {"key": "6", "type": "chapter", "name": "6 Counting",
            "sub_sec": [{"key": k, "type": "section", "name": n,
                         "sub_sec": []} for k, n in pairs]}


def _units(rows):
    return [{"type": "section", "key": k, "file": "%s.md" % k, "name": k + " " + t}
            for k, t in rows]


def _read(bodies):
    return lambda u: bodies[u["file"]]


class TestDangling(unittest.TestCase):
    def test_dangling_preposition(self):
        self.assertTrue(dangling_reason("## §1.2 Applications of", "1.2"))

    def test_trailing_hyphen(self):
        self.assertTrue(dangling_reason("## §8.5 Inclusion-", "8.5"))
        self.assertTrue(dangling_reason("## §10.2 Graph Termi-", "10.2"))

    def test_legit_single_word_title(self):
        for t in ("## §2.1 Sets", "## §3.1 Algorithms", "## §10.4 Connectivity",
                  "## §4.6 Cryptography", "### §6.3.3 Combinations"):
            self.assertIsNone(dangling_reason(t, "x"), t)

    def test_hyphenated_compound_not_dangling(self):
        # 末词整体是连字符复合词（含 and 词素）——整词比较才不会被误杀
        self.assertIsNone(
            dangling_reason("## §8.3 Divide-and-Conquer Algorithms and Recurrence "
                            "Relations", "8.3"))
        self.assertIsNone(dangling_reason("## §10.6 Shortest-Path Problems", "10.6"))

    def test_clean_title_strips_glued_page_number(self):
        self.assertEqual(clean_title("## §2 Phase Flows 57", "2"), "Phase Flows")
        self.assertEqual(norm_title("Phase Flows 57", ""), norm_title("Phase Flows", ""))


class TestContractUnitReconciliation(unittest.TestCase):
    def test_contract_truncated_unit_complete_fails(self):
        """Rosen ch6 §6.1 实测形态：契约残缺、写手已把单元 H2 补全。"""
        c = _contract([("6.1", "6.1 The Basics of")])
        u = _units([("6.1", "The Basics of Counting")])
        probs = title_problems(c, u, _read({"6.1.md": "## §6.1 The Basics of Counting\n\n正文"}))
        self.assertEqual(len(probs), 1, probs)
        # 契约侧悬空 → 报「SSOT 残缺」（比泛化的「前缀」更准），须回填契约而非削短单元
        self.assertIn("契约", probs[0])
        self.assertIn("SSOT", probs[0])

    def test_both_truncated_fails(self):
        """Rosen ch8 §8.5 实测形态：契约与单元双双残题。"""
        c = _contract([("8.5", "8.5 Inclusion-")])
        probs = title_problems(c, _units([("8.5", "Inclusion-")]),
                               _read({"8.5.md": "## §8.5 Inclusion-\n\n正文"}))
        self.assertTrue(any("折行截短" in p for p in probs), probs)

    def test_aligned_passes(self):
        c = _contract([("6.1", "6.1 The Basics of Counting")])
        probs = title_problems(c, _units([("6.1", "The Basics of Counting")]),
                               _read({"6.1.md": "## §6.1 The Basics of Counting\n\n正文"}))
        self.assertEqual(probs, [])

    def test_apostrophe_variant_passes(self):
        """ch7 §7.3.2：契约弯引号 / 单元直引号，同一标题的异形不算分叉。"""
        c = _contract([("7.3.2", "7.3.2 Bayes’ Theorem")])
        probs = title_problems(c, _units([("7.3.2", "Bayes' Theorem")]),
                               _read({"7.3.2.md": "### §7.3.2 Bayes' Theorem\n\n正文"}))
        self.assertEqual(probs, [])

    def test_glued_words_normalized(self):
        """ch1 §1.4.8：契约粘连成 LogicalEquivalencesInvolvingQuantifiers。"""
        c = _contract([("1.4.8", "1.4.8 LogicalEquivalencesInvolvingQuantifiers")])
        probs = title_problems(
            c, _units([("1.4.8", "Logical Equivalences Involving Quantifiers")]),
            _read({"1.4.8.md": "### §1.4.8 Logical Equivalences Involving Quantifiers\n\n正文"}))
        self.assertEqual(probs, [])

    def test_unit_shorter_than_contract_fails(self):
        c = _contract([("9.1", "9.1 Relations and Their Properties")])
        probs = title_problems(c, _units([("9.1", "Relations and")]),
                               _read({"9.1.md": "## §9.1 Relations and\n\n正文"}))
        self.assertTrue(any("缺词" in p or "折行截短" in p for p in probs), probs)

    def test_translation_dir_skips_name_comparison(self):
        """units-translate：H2 是中文译文，只查悬空，绝不与英文契约名对账。"""
        c = _contract([("2.4", "2.4 Sequences and Summations")])
        bodies = {"2.4.md": "## §2.4 序列与求和\n\n正文",
                  "1.7.3.md": "### §1.7.3 理解定理是如何陈述的\n\n正文"}
        u = _units([("2.4", "序列与求和")])
        u.append({"type": "section", "key": "1.7.3", "file": "1.7.3.md", "name": "1.7.3"})
        probs = title_problems(c, u, _read(bodies), compare_names=False)
        self.assertEqual(probs, [])

    def test_no_contract_only_dangling(self):
        probs = title_problems(None, _units([("1.1", "Introduction to")]),
                               _read({"1.1.md": "## §1.1 Introduction to\n\n正文"}))
        self.assertEqual(len(probs), 1, probs)

    def test_unit_without_heading_is_skipped(self):
        c = _contract([("6.1", "6.1 The Basics of")])
        probs = title_problems(c, _units([("6.1", "The Basics of Counting")]),
                               _read({"6.1.md": "没有标题行的正文"}))
        self.assertEqual(probs, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
