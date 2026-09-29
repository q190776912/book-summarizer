# -*- coding: utf-8 -*-
"""Regression: `formula.known_book` 注入必须落在**登记时确证的那一章**。

丘维声《解析几何》(2026-09-29 实测): 本书公式编号按**节**排且逐章重启 (ch1 §3 的
(3.11) 与 ch3 §3 的 (3.3) 是两个不同的号)，而 `register_formula.py` 登记时写的
`--chapter` 才是「这个号印在哪一章」的真值（账本 `known_book_audit` 逐条记着）。
旧注入判据只看「号的首段 == 章号」，对这类书必然注错章：ch1 登记的真号 (3.11)
被当成 **ch3** 的真编号要求总结写出 → 20 条假 `Q-LAYER FORMULA MISSING`，运维只
能把它们塞进 `ignore`（跨章污染，且掩盖真漏写）。

修法（被测）: :func:`formula_tag.known_book_scopes` 把 `known_book` + 账本合成
`{号: 登记章集合}`，注入判据优先按登记章；**无账本的存量配置**（含以裸 set 传入
的调用方）退回「首段 == 章号」旧行为，逐条不变。

Runs under stdlib unittest:
  python verify/tests/test_q_layer_known_book_chapter_scope.py
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

from formula_tag import (SourceFormulaIndex, build_formula_patterns,  # noqa: E402
                         known_book_scopes)

PATTERNS = build_formula_patterns(2)


def _write_pages(ext, n):
    """n 页**不含任何可收割编号**的正文页（页 1–2 = ch1 页窗，3–4 = ch3 页窗）。"""
    os.makedirs(ext, exist_ok=True)
    for i in range(1, n + 1):
        with open(os.path.join(ext, "page_%03d.json" % i), "w",
                  encoding="utf-8") as f:
            json.dump({"text": [{"text": "正文若干，无右缘编号",
                                 "poly": [0, 10 * i, 10, 10 * i + 12]}]},
                      f, ensure_ascii=False)


def _cfg(nums, audit):
    return {"known_book": list(nums), "known_book_audit": audit}


class TestScopesMapping(unittest.TestCase):
    def test_audit_chapter_wins_and_merges(self):
        scopes = known_book_scopes(_cfg(["3.11"], [
            {"number": "3.11", "chapter": 1},
            {"number": "3.11", "chapter": 3},
        ]))
        self.assertEqual(scopes, {"3.11": {1, 3}})

    def test_number_without_audit_is_legacy_none(self):
        scopes = known_book_scopes(_cfg(["3.11"], []))
        self.assertEqual(scopes, {"3.11": None})

    def test_audit_entry_for_unlisted_number_still_counts(self):
        scopes = known_book_scopes(_cfg([], [{"number": "2.7", "chapter": 2}]))
        self.assertEqual(scopes, {"2.7": {2}})


class TestPlainPathScope(unittest.TestCase):
    def test_registered_chapter_gets_it_other_chapter_does_not(self):
        with tempfile.TemporaryDirectory() as d:
            ext = os.path.join(d, "_extract")
            _write_pages(ext, 4)
            kb = known_book_scopes(_cfg(["3.11"], [{"number": "3.11",
                                                    "chapter": 1}]))
            first = SourceFormulaIndex(ext, PATTERNS, False, known_book=kb)
            first.build(1, 1, 2)
            self.assertIn("3.11", first.numbers_for_chapter(1))

            third = SourceFormulaIndex(ext, PATTERNS, False, known_book=kb)
            third.build(3, 3, 4)
            self.assertNotIn("3.11", third.numbers_for_chapter(3))

    def test_legacy_set_argument_keeps_first_component_rule(self):
        with tempfile.TemporaryDirectory() as d:
            ext = os.path.join(d, "_extract")
            _write_pages(ext, 4)
            third = SourceFormulaIndex(ext, PATTERNS, False,
                                       known_book={"3.11"})
            third.build(3, 3, 4)
            self.assertIn("3.11", third.numbers_for_chapter(3))
            first = SourceFormulaIndex(ext, PATTERNS, False,
                                       known_book={"3.11"})
            first.build(1, 1, 2)
            self.assertNotIn("3.11", first.numbers_for_chapter(1))


class TestSectionedPathScope(unittest.TestCase):
    def test_union_follows_registered_chapter(self):
        with tempfile.TemporaryDirectory() as d:
            ext = os.path.join(d, "_extract")
            _write_pages(ext, 4)
            kb = known_book_scopes(_cfg(["3.11"], [{"number": "3.11",
                                                    "chapter": 3}]))
            third = SourceFormulaIndex(ext, PATTERNS, False, known_book=kb)
            out3 = third.build_sectioned(3, 3, 4, ["3.1"], ncomp=2)
            self.assertIn("3.11", out3["_union"])

            first = SourceFormulaIndex(ext, PATTERNS, False, known_book=kb)
            out1 = first.build_sectioned(1, 1, 2, ["1.1"], ncomp=2)
            self.assertNotIn("3.11", out1["_union"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
