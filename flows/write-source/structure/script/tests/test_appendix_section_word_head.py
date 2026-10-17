# -*- coding: utf-8 -*-
"""Regression: an appendix whose sections print `Section A.1. <Title>` and whose
items print `Theorem A.1.1` must reach the contract at all.

Print (Lehmann《Elements of Large-Sample Theory》, Appendix, pp. 584-603,
2026-10-15 实测).  The chapter_map key is the BARE word `appendix` (the printed
appendix carries no ordinal, so the 附录命名总则 forbids inventing one).  Two
independent defects made that appendix empty:

1. `extract_items_en3` derived the letter-position filter as
   ``_ch_s.upper()`` -- for a bare word key that is ``"APPENDIX"``, so the
   single-letter test `m.group(2).upper() != _app_letter` is ALWAYS true and
   every letter-position head died.  The contract came out items=0 while the
   printed appendix has 10 heads (`Theorem A.1.1`, `Corollary A.1.1`,
   `Lemma A.2.1`, `Example A.2.1/A.2.2/A.3.1/A.4.1/A.6.1/A.6.2`,
   `Theorem A.4.1`).
2. No section detector saw `Section A.1. The Lindeberg Condition …`:
   `_SEC_HEAD_RE` requires a DIGIT at line start (the leading `S` of the word
   is eaten by its own optional-decoration class and the match then fails), and
   `SUB_GLOBAL` requires a BARE capital letter.  sections=0 made the
   completeness gate vacuously green.

Fixes under test: `SEC_APP_WORD` + the `(letter, number)` monotone first-seen
latch in `scan()` (only for non-digit chapter keys), and `_app_letter = None`
("any letter") for multi-character word keys -- the chapter's own page window
already scopes which appendix an item belongs to, and page windows are
disjoint.  Single-letter keys (`A`, `B`) and numeric chapters keep their
historic filtering.

The false-positive families the guards must still reject are the printed
problem-group heads at pp. 601-603 (`Section A.1` .. `Section A.6` -- bare, no
title, repeats of already-emitted keys) and prose cross-references.

Corpus calibration (14 books with a non-digit chapter, every appendix page
window scanned): 7 accepted matches, all 7 in THIS book and all 7 real printed
section heads; zero matches anywhere else -> zero regression.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_appendix_section_word_head.py
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

import scan_skeleton as S                                     # noqa: E402
from extract_items_en3 import extract_items_en3               # noqa: E402

POLY = [149, 432, 1074, 432, 1074, 464, 149, 464]


def _blk(txt):
    return {"text": txt, "poly": list(POLY), "score": 0.98}


def _write_pages(dirpath, pages):
    for i, texts in enumerate(pages, start=1):
        with open(os.path.join(dirpath, "page_%03d.json" % i), "w",
                  encoding="utf-8") as f:
            json.dump({"text": texts, "formulas": []}, f)


def _secs(pages, ch="appendix"):
    with tempfile.TemporaryDirectory() as d:
        _write_pages(d, pages)
        rows = S.scan(d, ch, 1, len(pages), "three-level",
                      section_depths=[1], chapter_first=True, language="en")
    return [(r[0], r[2], r[3]) for r in rows if r[1] == "SEC"]


def _items(pages, ch="appendix"):
    # 抽取器不保证跨标签顺序（按正则通道分趟），断言一律按集合比较。
    with tempfile.TemporaryDirectory() as d:
        _write_pages(d, pages)
        return [it["key"] for it in extract_items_en3(d, ch, 1, len(pages),
                                                      want_examples=True)]


# ---------------------------------------------------------------------------
# 1) the `Section A.N. Title` channel
# ---------------------------------------------------------------------------
class TestAppendixSectionWordHead(unittest.TestCase):
    def test_real_heads_emitted_in_order(self):
        got = _secs([[
            _blk("Appendix"),
            _blk("Section A.1. The Lindeberg Condition for the central limit "
                 "theo-"),
            _blk("Theorem A.1.1. Let Xnj form a triangular array"),
        ], [
            _blk("Section A.2. Hajek's projection method"),
            _blk("Lemma A.2.1. For any statistics S, T, and T*"),
        ]])
        self.assertEqual([(k, t) for _p, k, t in got],
                         [("A.1", "The Lindeberg Condition for the central "
                                  "limit theo-"),
                          ("A.2", "Hajek's projection method")])

    def test_long_title_not_vetoed_by_exercise_length_cap(self):
        # 46 chars: `_sec_like_title` (an exercise-latch prose judgement with a
        # ~40-char cap) used to kill the three longest real heads.
        got = _secs([[_blk("Section A.6. Refinements of first-order, "
                           "large-sample theory")]])
        self.assertEqual([k for _p, k, _t in got], ["A.6"])

    def test_bare_group_head_without_title_rejected(self):
        # pp. 601-603 print `Section A.1` .. `Section A.6` as problem-group
        # heads under `Section A.7. Problems` -- bare, and repeats.
        got = _secs([[
            _blk("Section A.1. The Lindeberg Condition"),
            _blk("Section A.2. Hajek's projection method"),
            _blk("Section A.7. Problems"),
            _blk("Section A.1"),
            _blk("Section A.2"),
        ]])
        self.assertEqual([k for _p, k, _t in got], ["A.1", "A.2", "A.7"])

    def test_backnumbered_repeat_rejected(self):
        got = _secs([[
            _blk("Section A.1. The Lindeberg Condition"),
            _blk("Section A.3. Almost sure convergence"),
            _blk("Section A.2. Hajek's projection method"),
        ]])
        self.assertEqual([k for _p, k, _t in got], ["A.1", "A.3"])

    def test_prose_sentence_tail_rejected(self):
        got = _secs([[
            _blk("Section A.1. The Lindeberg Condition"),
            _blk("Section A.4. The result follows. Indeed the proof is long"),
        ]])
        self.assertEqual([k for _p, k, _t in got], ["A.1"])

    def test_running_head_words_rejected(self):
        got = _secs([[_blk("Section A.9. Appendix to the main theorem")]])
        self.assertEqual(got, [])

    def test_lowercase_letter_and_numeric_forms_not_matched(self):
        # `Section 6.3 to be` (numeric cross-ref, printed p588) and a lowercase
        # prose reference must never enter this channel.
        self.assertIsNone(S.SEC_APP_WORD.match("Section 6.3 to be"))
        self.assertIsNone(S.SEC_APP_WORD.match("section A.1 shows the result"))

    def test_channel_off_for_numeric_chapter(self):
        got = _secs([[_blk("Section A.1. The Lindeberg Condition")]], ch=3)
        self.assertEqual(got, [])


# ---------------------------------------------------------------------------
# 2) the letter-position filter for a bare word key
# ---------------------------------------------------------------------------
class TestAppendixLetterFilterForWordKey(unittest.TestCase):
    def test_bare_word_key_harvests_letters(self):
        got = _items([[
            _blk("Theorem A.1.1. Let Xnj form a triangular array of variables"),
            _blk("Example A.2.1 Determining the minimizing sum of squares"),
            _blk("Lemma B.1.2. For any statistics S and T"),
        ]])
        self.assertEqual(set(got), {"Theorem A.1.1", "Example A.2.1",
                                    "Lemma B.1.2"})

    def test_letter_key_still_filters_other_letters(self):
        got = _items([[
            _blk("Theorem A.1.1. Let Xnj form a triangular array of variables"),
            _blk("Lemma B.1.2. For any statistics S and T"),
        ]], ch="A")
        self.assertEqual(got, ["Theorem A.1.1"])

    def test_numeric_chapter_keeps_legacy_A_only(self):
        got = _items([[
            _blk("Theorem A.1.1. Let Xnj form a triangular array of variables"),
            _blk("Lemma B.1.2. For any statistics S and T"),
        ]], ch=1)
        self.assertEqual(got, ["Theorem A.1.1"])

    def test_cross_reference_not_harvested(self):
        got = _items([[
            _blk("Theorem A.1.1. Let Xnj form a triangular array"),
            _blk("under the assumptions of Example A.4.1, compare the "
                 "approximation"),
            _blk("(A.1.2)"),
        ]])
        self.assertEqual(got, ["Theorem A.1.1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
