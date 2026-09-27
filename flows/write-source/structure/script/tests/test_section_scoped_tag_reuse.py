# -*- coding: utf-8 -*-
"""Regression: per-section restart equation numbers must all be harvested.

Strogatz《Nonlinear Dynamics and Chaos》3e (2026-09-27 实测): 本书公式号**逐节重置**
(verify_config `formula.scope == 3`, 右缘裸整数带括号)，§13.1 有 (1)(2)，§13.2 又
从 (1) 起，§13.3 再来 (1)(2)……。而 `attach_content._attach_formula_tags` 的去重集
`claimed` 存的是**全书唯一**的数字串（当时的理由写着「同一编号全书只应出现一次」），
于是每个整数只有**第一个**用到它的公式挂得上号：ch13 契约最终只剩 1..14 连续 14 个
tag，§13.2 的 (1)、§13.3 的 (1)(2)、§13.4 的 (1)(2)、§13.5 的 (1)-(4) 整片消失。
契约/manifest 的 `tags` 是 `gate_units` 判据 12 的对账真值，漏收即反过来**要求**写手
把印面带号公式写成无编号展示式——违反 V-K「带编号公式 1:1 跟书」（写手只能拒绝编造，
遂报告主会话）。

Fix under test: :func:`attach_content._claim_key` — scope==3 时按「编号@页」作键，
只挡同页重复识别的 OCR 碎片；scope 1/2（书级/章级唯一编号）维持旧的全书单键，
Koopman p166 `(6.7)` 截断碎片那条既有护栏逐字节不变。

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_section_scoped_tag_reuse.py
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
import lib.boot as _boot
_boot.setup()

from attach_content import _attach_formula_tags, _claim_key  # noqa: E402

SEC = dict(ncomp=1, bare=True, scope=3)
CHAP = dict(ncomp=1, bare=True, scope=2)


def _text(raw, page, y=100.0, x=900.0):
    return {"kind": "text", "text": raw, "page": page, "y": y,
            "bottom": y + 12.0, "x": x, "x1": x + 30.0}


def _formula(page, y=100.0):
    return {"kind": "formula", "formula": "a = b", "display": True,
            "page": page, "y": y, "bottom": y + 14.0, "x": 60.0, "x1": 960.0}


def _tags(out):
    return [str(b["tag"]) for b in out
            if b.get("kind") == "formula" and "tag" in b]


class TestClaimKey(unittest.TestCase):
    def test_section_scope_keyed_by_number_and_page(self):
        self.assertEqual(_claim_key("1", 516, 3), "1@516")
        self.assertNotEqual(_claim_key("1", 516, 3), _claim_key("1", 521, 3))

    def test_other_scopes_keep_book_wide_key(self):
        for scope in (None, 1, 2):
            self.assertEqual(_claim_key("6.7", 153, scope), "6.7")
            self.assertEqual(_claim_key("6.7", 166, scope), "6.7")


class TestSectionScopedReuse(unittest.TestCase):
    def test_same_number_in_later_section_still_attaches(self):
        claimed = set()
        a = _attach_formula_tags([_text("(1)", 513), _formula(513)],
                                claimed=claimed, **SEC)
        b = _attach_formula_tags([_text("(1)", 516), _formula(516)],
                                claimed=claimed, **SEC)
        self.assertEqual(_tags(a), ["1"])
        self.assertEqual(_tags(b), ["1"],
                         "§13.2 的 (1) 被 §13.1 的 (1) 吃掉（漏收）")

    def test_duplicate_on_same_page_attaches_once(self):
        claimed = set()
        first = _attach_formula_tags([_text("(2)", 521), _formula(521)],
                                     claimed=claimed, **SEC)
        again = _attach_formula_tags([_text("(2)", 521), _formula(521)],
                                     claimed=claimed, **SEC)
        self.assertEqual(_tags(first), ["2"])
        self.assertEqual(_tags(again), [], "同页重复识别的碎片必须只认一次")
        self.assertIn("(2)", [b.get("text") for b in again if b["kind"] == "text"],
                      "被拒的碎片不得离开正文流")


class TestChapterScopeUnchanged(unittest.TestCase):
    def test_koopman_truncated_fragment_still_dropped(self):
        # (6.7) 真身在 p153；p166 的 `…=01.1.(6.7)` 是 (6.70) 的截断 → 不得再挂
        claimed = set()
        _attach_formula_tags([_text("(6.7)", 153), _formula(153)],
                             claimed=claimed, **CHAP)
        out = _attach_formula_tags([_text("(6.7)", 166), _formula(166)],
                                   claimed=claimed, **CHAP)
        self.assertEqual(_tags(out), [], "章级编号书的重号护栏被改动")


if __name__ == "__main__":
    unittest.main(verbosity=2)
