# -*- coding: utf-8 -*-
"""Regression: INCONSISTENT 重复检测须按「书源真印几次」放行（count-aware）。

Apostol《Introduction to Analytic Number Theory》§3.11 (2026-09-28 fitz 裁剪
目视为准)：原书在印刷页 66、67 **各印一次** `(17)`（同一公式的第二种写法），
总结忠实地在同一个 `## §3.11` 桶里给出两个 `\tag{17}`。旧的重复判据是
「同一桶内 `counts[key] > 1` 即 INCONSISTENT（阻断）」，而节级书源集合 S 是
**set**——同一桶出现两次的证据在收集时就被压掉了，于是忠实继承印刷号的写法
永久无法通过，硬闸反过来要求写手**改掉**印刷编号（=编造）。

Fix under test: `SourceFormulaIndex._count_label` / `label_limit`（与位置证据
同一谓词：非嵌入引用、非节标题、非逗号派生，按**页**去重）+ 单一共享判据
`_dup_beyond_source`，plain 与 sectioned 两条路径同口径。
`label_limit` 在书源无该桶记录时返回 **1**，即维持原严格度——本改动只可能
放宽假阳，不可能收紧，也不会把「凭空多写一个 `\tag`」放过去（负向测试
`test_second_tag_without_source_duplicate_still_flags`）。

Runs under stdlib unittest:
  python verify/tests/test_q_layer_duplicate_label_limit.py
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

from formula_tag import (  # noqa: E402
    SourceFormulaIndex, build_formula_patterns, _compare_sectioned,
    _extract_summary_tags_sectioned, _detect_summary_sections,
)

MD = """# Chapter 3

## §3.11 Some Theorem

$$ \\zeta(s) = \\prod_p (1-p^{-s})^{-1}. \\tag{17}$$

$$ \\log \\zeta(s) = \\sum_p \\sum_m p^{-ms}/m. \\tag{17}$$
"""


def _write_pages(ext, per_page):
    os.makedirs(ext, exist_ok=True)
    for i, blocks in enumerate(per_page, start=1):
        with open(os.path.join(ext, "page_%03d.json" % i), "w",
                  encoding="utf-8") as f:
            json.dump({"text": [{"text": b, "poly": [0, 40, 200, 52]}
                                for b in blocks]}, f, ensure_ascii=False)


def _inc_numbers(tmp, per_page):
    """Run the real sectioned pipeline (source walk + summary bucketing +
    compare) and return the numbers reported INCONSISTENT."""
    ext = os.path.join(tmp, "_extract")
    _write_pages(ext, per_page)
    md_sections, find_re, split_re = _detect_summary_sections(MD)
    src = SourceFormulaIndex(ext, build_formula_patterns(1), False)
    built = src.build_sectioned(3, 1, len(per_page), md_sections, ncomp=1)
    md = os.path.join(tmp, "ch3.md")
    with open(md, "w", encoding="utf-8") as f:
        f.write(MD)
    tags_sec = _extract_summary_tags_sectioned(md, find_re, split_re)
    _fab, inc, _miss, _rows = _compare_sectioned(
        tags_sec, built["_sectioned"], md_sections, built["_union"], set(), src)
    return [r["number"] for r in inc], src


class TestSourceDuplicateExempt(unittest.TestCase):
    def test_two_printed_labels_make_two_tags_legal(self):
        inc, src = _inc_numbers(tempfile.mkdtemp(), [["(17)"], ["(17)"]])
        self.assertEqual(inc, [])
        self.assertEqual(src.label_limit("17", "3.11"), 2)

    def test_same_page_counts_once(self):
        # 同一页的两条通道（text[] 与 formulas[].latex）不得把一次印刷数成两次。
        inc, src = _inc_numbers(tempfile.mkdtemp(), [["(17)", "(17)"]])
        self.assertEqual(src.label_limit("17", "3.11"), 1)
        self.assertEqual(inc, ["17"])


class TestInventedDuplicateStillFlags(unittest.TestCase):
    def test_second_tag_without_source_duplicate_still_flags(self):
        inc, src = _inc_numbers(tempfile.mkdtemp(), [["(17)"], []])
        self.assertEqual(src.label_limit("17", "3.11"), 1)
        self.assertEqual(inc, ["17"])

    def test_unrecorded_number_keeps_old_strictness(self):
        src = SourceFormulaIndex("/none", build_formula_patterns(1), False)
        self.assertEqual(src.label_limit("7"), 1)
        self.assertEqual(src.label_limit("7", "3.1"), 1)

    def test_prose_cross_reference_is_not_a_printed_label(self):
        # 「…in (17) we saw…」是散文回指（_embedded_ref / 块形门禁拦下），
        # 不能替总结的第二个 \tag 作保。
        inc, _src = _inc_numbers(tempfile.mkdtemp(), [
            ["(17)"], ["the bound in (17) is all we need here"]])
        self.assertEqual(inc, ["17"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
