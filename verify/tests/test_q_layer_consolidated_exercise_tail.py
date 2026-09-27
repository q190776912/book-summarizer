# -*- coding: utf-8 -*-
"""Regression: chapter-end CONSOLIDATED exercise pages must not enter S.

Strogatz《Nonlinear Dynamics and Chaos》3e ch13 (2026-09-27 实测): 题 13.6.5
(Ott-Antonsen ansatz) 的显示公式在印面上确实带右缘编号 `(13)`(p553 y=250)、
`(14)`(p553 y=507)。但该章章末习题区整块是**集中习题块**——契约节点
``consolidated: true``，writing-rules「有专门习题小标题的集中习题块一律省略」，
`unit_node_entries` 也据此**不给它出单元**。于是 Q 层的书源集合 S 收了 (14)，
总结按设计没有它 → `verify_chapter --all` 报
``Q-LAYER FORMULA MISSING (1) [FAIL, blocking]: ! 14  (14)``，
硬闸反过来**要求**写手把习题解答写成正文公式（违反省略规则，且只能靠编造
上下文满足）。

Fix under test: :meth:`formula_tag.SourceFormulaIndex._in_exercise_tail` —
`_load_sec_keys` 读契约时一并记下 consolidated 节点的最小叶号，plain
(`build`) 与节级 (`build_sectioned`) 两条抽取路径都跳过该页及其后。
无 consolidated 标记的书（契约无该字段）行为逐字节不变。

Runs under stdlib unittest:
  python verify/tests/test_q_layer_consolidated_exercise_tail.py
"""
import json
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

from formula_tag import SourceFormulaIndex, build_formula_patterns  # noqa: E402


def _write_pages(ext, texts):
    """`texts` = per-page list of block texts (or a plain string per page)."""
    os.makedirs(ext, exist_ok=True)
    for i, t in enumerate(texts, start=1):
        blocks = t if isinstance(t, (list, tuple)) else [t]
        with open(os.path.join(ext, "page_%03d.json" % i), "w",
                  encoding="utf-8") as f:
            json.dump({"text": [{"text": b, "poly": [[0, 10 * j], [10, 10 * j]]}
                                for j, b in enumerate(blocks)]},
                      f, ensure_ascii=False)


def _write_contract(ext, ch, nodes):
    d = os.path.join(ext, "book_structure")
    os.makedirs(d, exist_ok=True)
    tree = {"key": str(ch), "type": "chapter", "sub_sec": nodes}
    with open(os.path.join(d, "ch%d.json" % ch), "w", encoding="utf-8") as f:
        json.dump(tree, f, ensure_ascii=False)


def _section(key, page, name="§"):
    return {"key": key, "type": "section", "name": name, "page_start": page,
            "page_end": page, "sub_sec": []}


def _exercise(key, page, consolidated):
    node = {"key": key, "type": "exercise", "name": "题", "page_start": page,
            "page_end": page, "sub_sec": []}
    if consolidated:
        node["consolidated"] = True
    return node


class TestTailPageDerivation(unittest.TestCase):
    def test_min_consolidated_page_wins(self):
        with tempfile.TemporaryDirectory() as d:
            ext = os.path.join(d, "_extract")
            _write_contract(ext, 13, [
                _section("13.6", 534),
                _exercise("13.6.1", 535, True),
                _exercise("13.6.5", 537, True),
            ])
            src = SourceFormulaIndex(ext, build_formula_patterns(1), True)
            src._load_sec_keys(13)
            self.assertEqual(src._tail_exer_page, 535)
            self.assertTrue(src._in_exercise_tail(535))
            self.assertFalse(src._in_exercise_tail(534))

    def test_no_consolidated_flag_means_no_exclusion(self):
        with tempfile.TemporaryDirectory() as d:
            ext = os.path.join(d, "_extract")
            _write_contract(ext, 3, [
                _section("3.1", 20),
                _exercise("3.1.1", 24, False),
            ])
            src = SourceFormulaIndex(ext, build_formula_patterns(1), True)
            src._load_sec_keys(3)
            self.assertIsNone(src._tail_exer_page)
            self.assertFalse(src._in_exercise_tail(24))

    def test_missing_contract_is_neutral(self):
        src = SourceFormulaIndex("/none", build_formula_patterns(1), True)
        src._load_sec_keys(9)
        self.assertIsNone(src._tail_exer_page)
        self.assertFalse(src._in_exercise_tail(1))


class TestPlainPathTailExcluded(unittest.TestCase):
    def test_tail_numbers_absent_from_s_body_numbers_kept(self):
        with tempfile.TemporaryDirectory() as d:
            ext = os.path.join(d, "_extract")
            # pages 1..4: body carries (1)(2); exercise tail (page 3 onward)
            # carries (3)(4) which the summary legitimately omits.
            _write_pages(ext, ["body (1)", "body (2)", "exer (3)", "exer (4)"])
            _write_contract(ext, 1, [
                _section("1.1", 1),
                _exercise("1.1.1", 3, True),
            ])
            src = SourceFormulaIndex(ext, build_formula_patterns(1), True)
            src.build(1, 1, 4)
            self.assertEqual(src.numbers_for_chapter(1), {"1", "2"})

    def test_without_consolidated_flag_tail_still_collected(self):
        with tempfile.TemporaryDirectory() as d:
            ext = os.path.join(d, "_extract")
            _write_pages(ext, ["body (1)", "body (2)", "exer (3)", "exer (4)"])
            _write_contract(ext, 1, [
                _section("1.1", 1),
                _exercise("1.1.1", 3, False),
            ])
            src = SourceFormulaIndex(ext, build_formula_patterns(1), True)
            src.build(1, 1, 4)
            self.assertEqual(src.numbers_for_chapter(1),
                             {"1", "2", "3", "4"})


class TestSectionedPathTailExcluded(unittest.TestCase):
    # 节级重置书（ncomp==1 / scope 3）只认**独立成块**的裸标签 `(N)`，
    # 所以页面写成块列表而非散文行。
    PAGES = [["1.1 Governing Equations", "(1)"], ["(2)"], ["(3)"]]

    def test_sectioned_buckets_skip_tail_pages(self):
        with tempfile.TemporaryDirectory() as d:
            ext = os.path.join(d, "_extract")
            _write_pages(ext, self.PAGES)
            _write_contract(ext, 1, [
                _section("1.1", 1),
                _exercise("1.1.1", 3, True),
            ])
            src = SourceFormulaIndex(ext, build_formula_patterns(1), True)
            out = src.build_sectioned(1, 1, 3, ["1.1"], ncomp=1)
            sec = out["_sectioned"]
            self.assertEqual(sec.get("1.1"), {"1", "2"})
            self.assertNotIn("3", out["_union"])
            self.assertNotIn("3", src.all_numbers())

    def test_sectioned_keeps_tail_when_not_consolidated(self):
        with tempfile.TemporaryDirectory() as d:
            ext = os.path.join(d, "_extract")
            _write_pages(ext, self.PAGES)
            _write_contract(ext, 1, [
                _section("1.1", 1),
                _exercise("1.1.1", 3, False),
            ])
            src = SourceFormulaIndex(ext, build_formula_patterns(1), True)
            out = src.build_sectioned(1, 1, 3, ["1.1"], ncomp=1)
            self.assertEqual(out["_sectioned"].get("1.1"), {"1", "2", "3"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
