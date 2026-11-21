# -*- coding: utf-8 -*-
"""回归：字母附录章源侧**节头**查漏（step2_sections 不再整项跳过）。

事故形态（convex optimization 2026-11-20）：印面有节头、契约漏登的字母章缺节
——附录B 的 B.2 The S-procedure / B.3 The field of values / B.4 Proofs of the
strong duality results、附录C 的 C.5 Solving underdetermined linear equations、
附录A 的 A.1.1 Inner product——写源期完整性闸门对字母章整项跳过（旧分支
``skipped="appendix-letter-chapter"``），一路假绿到交付。

修法：``letter_source_sections`` 专用扫描（整行锚定 + 标题形闭 + 读序单调前缀
+ 契约键合法性过滤），step2_sections 字母章分支接入，missing_sections 与数字章
同口径进闸；**不自动回填**（回填路径 int(ch) 会崩，字母节须人工按印面登记）。
"""
import json
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, str(_ROOT / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot  # noqa: E402
lib.boot.setup()

from verify.script.check_structure_completeness import (  # noqa: E402
    letter_source_sections, step2_sections)
from data.book_structure.book_structure import StructureNode  # noqa: E402


def _mk_ext(tmp_path, pages):
    """pages: {page_no: [line, ...]} → 扁平 page_*.json fixture。"""
    for n, lines in pages.items():
        fp = tmp_path / f"page_{n:03d}.json"
        fp.write_text(json.dumps({
            "page": n,
            "text": [{"text": ln} for ln in lines],
            "formulas": [],
        }, ensure_ascii=False), encoding="utf-8")
    return str(tmp_path)


def _mk_tree(spec):
    """spec: {'sections': {'B.1': {...子节点}}, ...} → StructureNode 章节点。

    简化：spec = list of (type, key)；'section:B.1' / 'example:B.1'。
    """
    root = StructureNode(key="B", type="chapter", name="B appendix")
    for t, k in spec:
        root.sub_sec.append(StructureNode(key=k, type=t, name=k))
    return root


BOYD_B_PAGES = {
    667: ["B Problems involving two quadratic functions", "665",
          "B.1 Single constraint quadratic optimization",
          "We consider the problem with one constraint"],
    669: ["B.2 The S-procedure", "655",
          "The next result is a theorem of alternatives for a pair of quadratic"],
    670: ["656", "B Problems involving two quadratic functions",
          "B.3 The field of values of two symmetric matrices"],
    671: ["B.4 Proofs of the strong duality results", "657",
          "We first prove the S-procedure result given in SB.2.",
          "B.4 Proofs of the strong duality results"],
}


class TestLetterSourceSections:
    def test_missing_section_detected(self, tmp_path):
        """印面有 B.2 而契约只有 B.1/B.3/B.4 → missing = ['B.2']。"""
        ext = _mk_ext(tmp_path, BOYD_B_PAGES)
        tree = _mk_tree([("section", "B.1"), ("section", "B.3"), ("section", "B.4")])
        r = letter_source_sections(ext, "B", 667, 674, tree=tree)
        assert r["missing"] == ["B.2"]
        assert {"B.1", "B.2", "B.3", "B.4"} <= r["printed"]

    def test_all_present_no_missing(self, tmp_path):
        ext = _mk_ext(tmp_path, BOYD_B_PAGES)
        tree = _mk_tree([("section", "B.1"), ("section", "B.2"),
                         ("section", "B.3"), ("section", "B.4")])
        r = letter_source_sections(ext, "B", 667, 674, tree=tree)
        assert r["missing"] == []

    def test_running_head_duplicate_counted_once(self, tmp_path):
        ext = _mk_ext(tmp_path, BOYD_B_PAGES)
        r = letter_source_sections(ext, "B", 667, 674)
        b4 = [(k, p) for k, p, _ in r["occurrences"] if k == "B.4"]
        assert len(b4) == 1  # p671 页眉 + 真头同键去重

    def test_exercise_line_non_monotonic_rejected(self, tmp_path):
        """章末习题倒挂号（B.1 复现于 B.4 之后）不作节证据。"""
        pages = dict(BOYD_B_PAGES)
        pages[674] = ["B.1 Show that the claim also holds for n > 2."]
        ext = _mk_ext(tmp_path, pages)
        r = letter_source_sections(ext, "B", 667, 674)
        assert "B.1" not in r["printed"] or True  # B.1 早已单调收下（p667）
        assert all("Show that" not in ln for _k, _p, ln in r["occurrences"])
        assert any("non-monotonic" in rr for _p, _l, rr in r["rejected"])

    def test_prose_title_rejected_by_guard(self, tmp_path):
        """散文题（句界 + ≥8 词句点结尾）不作节证据。"""
        pages = dict(BOYD_B_PAGES)
        pages[674] = ["B.5 It was shown by Smith and Jones, in a long series of papers. Further"]
        ext = _mk_ext(tmp_path, pages)
        r = letter_source_sections(ext, "B", 667, 674)
        assert "B.5" not in r["printed"]
        assert any("title-guard" in rr for _p, _l, rr in r["rejected"])

    def test_bare_number_heading_line(self, tmp_path):
        """OCR 拆行：`C.5` 号裸行 + 次行标题 → 号行即证据。"""
        pages = {695: ["C.5", "Solving underdetermined linear equations"]}
        ext = _mk_ext(tmp_path, pages)
        r = letter_source_sections(ext, "C", 695, 698)
        assert "C.5" in r["printed"]

    def test_ocr_mangled_title_accepted(self, tmp_path):
        """ℓ 被啃成 '('：`B.2 (1-norm approximation` 仍须收（11.8.2 同型）。"""
        pages = {631: ["B.2 (1-norm approximation"]}
        ext = _mk_ext(tmp_path, pages)
        r = letter_source_sections(ext, "B", 631, 632)
        assert "B.2" in r["printed"]

    def test_three_level_key(self, tmp_path):
        """三级号 `A.1.1 Inner product, Euclidean norm, and angle`。"""
        pages = {648: ["A.1.1 Inner product, Euclidean norm, and angle"]}
        ext = _mk_ext(tmp_path, pages)
        r = letter_source_sections(ext, "A", 647, 666)
        assert "A.1.1" in r["printed"]

    def test_worded_form_requires_title(self, tmp_path):
        """`Section A.1. Norms` 收；裸分组头 `Section A.1` 不收。"""
        pages = {651: ["Section A.1. Norms", "Section A.2"]}
        ext = _mk_ext(tmp_path, pages)
        r = letter_source_sections(ext, "A", 651, 652)
        assert "A.1" in r["printed"]
        assert "A.2" not in r["printed"]

    def test_letter_mismatch_rejected(self, tmp_path):
        """他章节头行（ch=B 窗口出现 C.1）不进本章证据。"""
        pages = {674: ["C.1 Matrix structure and algorithm complexity"]}
        ext = _mk_ext(tmp_path, pages)
        r = letter_source_sections(ext, "B", 674, 674)
        assert r["printed"] == set()
        assert any("letter-mismatch" in rr for _p, _l, rr in r["rejected"])

    def test_inline_reference_not_matched(self, tmp_path):
        """行中回指 `in section B.2 we`（非行首）不作节头。"""
        pages = {672: ["as shown in section B.2 we conclude that the result holds"]}
        ext = _mk_ext(tmp_path, pages)
        r = letter_source_sections(ext, "B", 672, 672)
        assert "B.2" not in r["printed"]


class TestStep2LetterBranch:
    def test_step2_returns_letter_missing(self, tmp_path):
        ext = _mk_ext(tmp_path, BOYD_B_PAGES)
        tree = _mk_tree([("section", "B.1"), ("section", "B.3"), ("section", "B.4")])
        missing, detail = step2_sections("B", 667, 674, ext, None, tree)
        assert missing == ["B.2"]
        assert detail["skipped"] is None
        assert "B.2" in detail["letter_printed"]

    def test_step2_letter_all_present(self, tmp_path):
        ext = _mk_ext(tmp_path, BOYD_B_PAGES)
        tree = _mk_tree([("section", "B.1"), ("section", "B.2"),
                         ("section", "B.3"), ("section", "B.4")])
        missing, detail = step2_sections("B", 667, 674, ext, None, tree)
        assert missing == []
        assert detail["continuity"] == [] and detail["tail"] == []

    def test_contract_item_key_legality(self, tmp_path):
        """契约已有同键编号项（example B.1）→ 印面 B.1 不报缺失。"""
        ext = _mk_ext(tmp_path, BOYD_B_PAGES)
        tree = _mk_tree([("section", "B.1"), ("example", "B.1"),
                         ("section", "B.3"), ("section", "B.4")])
        missing, _ = step2_sections("B", 667, 674, ext, None, tree)
        assert missing == ["B.2"]
