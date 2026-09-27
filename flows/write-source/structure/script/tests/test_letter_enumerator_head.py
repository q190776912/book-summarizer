# -*- coding: utf-8 -*-
"""Regression: a printed LETTER enumerator must never be laundered into a numeric
item key by the OCR digit↔letter confusion table.

Print (Shafarevich《Basic Algebraic Geometry 1》I, p202, §"Quotient Groups and
Chevalley's Theorem", 2026-09-28 实测):

    Theorem A The abstract group G/N
    Theorem B An affine algebraic group is isomorphic to an algebraic subgroup of
    Theorem C (Chevalley's theorem) Every algebraic group G has a normal sub-

The book says so itself: "Theorems are labelled with letters (Theorem A, etc.) to
indicate that proofs are [omitted]".  ``EN_OCR_NUM`` treats B/D as look-alikes of
8/0, so the old extractor emitted ONE phantom numeric head — key ``Theorem 8``,
name "定理8 B An affine algebraic group …" — while A and C (no confusion entry)
vanished entirely.  Four sibling heads, three different outcomes, none of them the
print.

Fix under test: the pure-letter-enumerator guard — a match whose number tokens
carry NO digit at all is not a numeric entry.  Letter enumerators do not consume
the numeric counter (no gap), so the statement stays prose (or goes through
``manual_overrides`` / the ORDINAL_HUM family when the whole book uses letters).
Letter-CHAPTER-position forms (``Theorem A.1``, APP/APP2 ordinals) keep their
digit in the second component and must be unaffected.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_letter_enumerator_head.py
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

from extract_items_en import extract_items_en  # noqa: E402

POLY = [149, 432, 1074, 432, 1074, 464, 149, 464]


def _blk(txt):
    return {"text": txt, "poly": list(POLY), "score": 0.98}


def _keys(pages, **kw):
    """pages: [text_block_list] → 抽取到的条目 key 集合（小写归一）。"""
    with tempfile.TemporaryDirectory() as d:
        for i, texts in enumerate(pages, start=1):
            with open(os.path.join(d, "page_%03d.json" % i), "w", encoding="utf-8") as f:
                json.dump({"text": texts, "formulas": []}, f)
        return {it["key"].lower() for it in extract_items_en(d, 1, len(pages), **kw)}


class TestLetterEnumeratorDropped(unittest.TestCase):
    def test_theorem_B_does_not_become_numeric_8(self):
        got = _keys([[
            _blk("Theorem B An affine algebraic group is isomorphic to an algebraic "
                 "subgroup of"),
        ]])
        self.assertNotIn("theorem 8", got)
        self.assertNotIn("theorem b", got)

    def test_letter_heads_dropped_not_paired_with_real_items(self):
        got = _keys([[
            _blk("Theorem A The abstract group G/N"),
            _blk("Theorem B An affine algebraic group is isomorphic to an"),
            _blk("Theorem C (Chevalley's theorem) Every algebraic group G has a"),
            _blk("Theorem 3.14 Any algebraic group is a quasiprojective variety."),
        ]])
        self.assertEqual(got, {"theorem 3.14"})

    def test_corollary_lemma_letter_heads_dropped(self):
        got = _keys([[
            _blk("Corollary A Theorem 3.15 is false"),
            _blk("Lemma B Let H be a subgroup"),
            _blk("Remark C This is the end"),
        ]])
        self.assertEqual(got, set())

    def test_chapter_first_digital_two_level_shape(self):
        # 本章体例：章号.序号（chapter_first），字母序标不得混进同一计数器。
        got = _keys([[
            _blk("Theorem B An affine algebraic group is isomorphic to an algebraic subgroup of"),
            _blk("Theorem 3.15 An Abelian variety is an Abelian group."),
        ]], section_scoped=True)
        self.assertEqual(got, {"theorem 3.15"})


class TestDigitCarryingFormsUnaffected(unittest.TestCase):
    def test_ocr_confused_digit_still_kept(self):
        # "Theorem 8.1" 被 OCR 读成 "Theorem B.1"：第二分量有数字 → 整条含数字，
        # 不在本守卫射程，照旧经形近表归一回 8.1（字母章位 `Theorem A.1` 同理不被
        # 本守卫拦截，它本来就在 _ocr_int_glue 处失败——那是 APP 体例的抽取器职责）。
        got = _keys([[_blk("Theorem B.1 Let X be a variety")]])
        self.assertIn("theorem 8.1", got)

    def test_normal_two_level_head_kept(self):
        got = _keys([[_blk("Proposition 3.1 Ω is generated as an A-module by the elements")]])
        self.assertIn("proposition 3.1", got)


if __name__ == "__main__":
    unittest.main(verbosity=2)
