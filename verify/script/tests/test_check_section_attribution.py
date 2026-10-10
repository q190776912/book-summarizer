# -*- coding: utf-8 -*-
"""条目↔节归属闸（check_section_attribution）回归测试。

根因（real-analysis-for-graduate-students ch2 实测 2026-10-10）：真节头在 p29 以
「裸节号块 + 标题块」两行形态出现，build_structure 只认单行 `N.M 标题`，把 p31 的
全大写页眉复本 `2.1. ALGEBRAS AND σ-ALGEBRAS` 当成 §2.1 锚点 → 定义2.1～引理2.7
（p29–30）被甩到 §2.1 之外（漂到章前言）。D 层 / check_contract_anchors /
subsection_order_problems 全部失明，门控放绿。本闸专拦「锚点晚于最早两行节头」。

关键负向（防误报，全部实测过形态）：
  * 单行交叉引用句 `4.2 shows that …`（内联散文、非独立裸号块）→ 不触发；
  * 纯目录/扉页（有裸号+标题但**无条头**）→ 正文页判据挡下，不触发；
  * 正确锚点（节头就在锚点页）→ [H,A) 空，不触发。

运行：
  python verify/script/tests/test_check_section_attribution.py
"""
import os
import sys
import json
import shutil
import tempfile
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "verify", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from check_section_attribution import section_attribution_problems  # noqa: E402
from data.book_structure.book_structure import StructureNode  # noqa: E402


def _node(key, ntype, page=0, *kids):
    return StructureNode(key=key, type=ntype, name=str(key),
                         page_start=page, page_end=page, sub_sec=list(kids))


def _write_pages(ext, pages):
    """pages = {page_no: [block_text, ...]}；写成 page_NNN.json（text 块数组）。"""
    os.makedirs(ext, exist_ok=True)
    for p, blocks in pages.items():
        data = {"text": [{"text": t} for t in blocks]}
        with open(os.path.join(ext, "page_%03d.json" % p), "w",
                  encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)


class TestAttributionGate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="attr_gate_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---- 正向：抓到 ch2 式误锚 --------------------------------------------
    def test_catches_split_two_line_heading_misanchor(self):
        # p29 两行节头（裸 '2.1' + 标题），p31 全大写页眉复本被误当锚点。
        _write_pages(self.tmp, {
            29: ["2.1", "Algebras and sigma-algebras", "Let X be a set.",
                 "Definition 2.1 An algebra is a collection A of subsets"],
            30: ["Example 2.2 Let X = R, the set of real numbers",
                 "Lemma 2.7 If A is a sigma-algebra for each"],
            31: ["2.1. ALGEBRAS AND SIGMA-ALGEBRAS",
                 "Proposition 2.8 If X = R, then the Borel"],
            32: ["2.2 The monotone class theorem",
                 "Definition 2.9 A monotone class is a collection"],
        })
        sec21 = _node("2.1", "section", 31, _node("命题2.8", "proposition", 31))
        sec22 = _node("2.2", "section", 32, _node("定义2.9", "definition", 32))
        chapter = _node("2", "chapter", 29,
                        _node("定义2.1", "definition", 29),
                        _node("例2.2", "example", 30),
                        _node("引理2.7", "lemma", 30),
                        sec21, sec22)
        probs = section_attribution_problems(self.tmp, "2", 29, 32, chapter)
        self.assertEqual(len(probs), 1, "应且仅应报 §2.1 一处误锚")
        self.assertIn("§2.1", probs[0])
        self.assertIn("p29", probs[0])
        # 漂在节外的条目须被点名。
        for k in ("定义2.1", "例2.2", "引理2.7"):
            self.assertIn(k, probs[0])

    # ---- 负向：单行交叉引用句不得触发 ------------------------------------
    def test_cross_reference_sentence_is_not_a_heading(self):
        # §4.2 正确锚在 p46；p43 只有一句以节号起头的交叉引用（内联，非裸号块）。
        _write_pages(self.tmp, {
            43: ["4.2 shows that mu* is an outer measure, but we will see later",
                 "Example 4.3 Let X = R and let C be the collection"],
            44: ["Definition 4.5 Let mu* be an outer measure"],
            46: ["4.2  Lebesgue-Stieltjes measures",
                 "Theorem 4.7 Every Lebesgue-Stieltjes measure"],
        })
        sec41 = _node("4.1", "section", 42,
                      _node("定义4.1", "definition", 42),
                      _node("例4.3", "example", 43),
                      _node("定义4.5", "definition", 44))
        sec42 = _node("4.2", "section", 46, _node("定理4.7", "theorem", 46))
        chapter = _node("4", "chapter", 41, sec41, sec42)
        probs = section_attribution_problems(self.tmp, "4", 41, 46, chapter)
        self.assertEqual(probs, [],
                         "单行交叉引用句不是节头，§4.2 锚点正确，不得误报")

    # ---- 负向：纯目录/扉页（无条头）不得触发 ------------------------------
    def test_toc_page_without_item_head_is_skipped(self):
        # p20 是章首目录：裸号块 + 标题，但整页没有任何条头 → 非正文页 → 跳过。
        _write_pages(self.tmp, {
            20: ["2.1", "Algebras and sigma-algebras",
                 "2.2", "The monotone class theorem"],
            21: ["Definition 2.1 An algebra is a collection A"],
            22: ["2.1. ALGEBRAS AND SIGMA-ALGEBRAS",
                 "Proposition 2.8 If X = R, then the Borel"],
        })
        sec21 = _node("2.1", "section", 22, _node("命题2.8", "proposition", 22))
        chapter = _node("2", "chapter", 21,
                        _node("定义2.1", "definition", 21), sec21)
        probs = section_attribution_problems(self.tmp, "2", 20, 22, chapter)
        # 目录页 p20 无条头被跳过；最早正文节头 = p22 = 锚点 → 不报。
        self.assertEqual(probs, [],
                         "目录页无条头须被正文页判据挡下，不得据其误判锚点过早")

    # ---- 负向：正确锚点（节头就在锚点页）不触发 --------------------------
    def test_correctly_anchored_section_passes(self):
        _write_pages(self.tmp, {
            29: ["2.1 Algebras and sigma-algebras",
                 "Definition 2.1 An algebra is a collection A"],
            30: ["Proposition 2.8 If X = R, then the Borel"],
        })
        sec21 = _node("2.1", "section", 29,
                      _node("定义2.1", "definition", 29),
                      _node("命题2.8", "proposition", 30))
        chapter = _node("2", "chapter", 29, sec21)
        probs = section_attribution_problems(self.tmp, "2", 29, 30, chapter)
        self.assertEqual(probs, [], "节头即锚点页，[H,A) 空 → 通过")

    # ---- 负向：无点分数字节（字母/全局/无序号）不参与 --------------------
    def test_non_dotted_sections_not_considered(self):
        _write_pages(self.tmp, {
            10: ["A  Some Appendix Title", "Definition A.1 Let x be"],
        })
        secA = _node("A", "section", 10, _node("定义A.1", "definition", 10))
        chapter = _node("A", "chapter", 10, secA)
        probs = section_attribution_problems(self.tmp, "A", 10, 10, chapter)
        self.assertEqual(probs, [], "非点分数字节键不参与本闸")


if __name__ == "__main__":
    unittest.main(verbosity=2)
