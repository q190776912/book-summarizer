# -*- coding: utf-8 -*-
"""Regression: a statement whose SUBJECT is a lifted-out inline formula must not
be thrown away as a cross-reference (``extract_items_en`` MENTION_VERBS guard;
Shafarevich《Basic Algebraic Geometry 1》Theorem 3.6, p180, 2026-09-28 实测).

Print:  Theorem 3.6  $\\widetilde{\\mathcal O}$ is a principal ideal domain with a
        finite number of prime ideals.
MFD carves $\\widetilde{\\mathcal O}$ into its own formula item, so the OCR TEXT
line degenerates to "Theorem 3.6  is a principal ideal domain…" — number + a
two-space HOLE + lowercase "is".  The old guard saw "is" in MENTION_VERBS and
dropped the head: the contract lost 定理3.6, the B layer blocked the chapter with
「缺号 6」, and the source-side backfill could never repair it (same predicate).

Fix under test: ``_formula_slot_subject`` — keep the head only when BOTH
① the number is followed by ≥2 spaces (the formula slot), and ② a formula sits
on that line at the estimated x of the slot.  Genuine prose mentions
("Theorem 3.5 follows from two results.") and mentions whose line ends with an
unrelated inline formula keep the old (drop) behaviour.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_formula_slot_subject.py
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

from extract_items_en import extract_items_en, _formula_slot_subject  # noqa: E402

# 行带（y）取 600..625；块 x 100..700，文本 78 字符 → 平均字符宽 ≈7.7，
# 「Theorem 3.6」+双空格 的槽位估计 x ≈ 200（容差 2 字符 ≈15）。
POLY = [100, 600, 700, 600, 700, 625, 100, 625]
HEAD = ("Theorem 3.6  is a principal ideal domain with a finite number of "
        "prime ideals.")


def _blk(txt, poly=None):
    return {"text": txt, "poly": poly if poly is not None else POLY, "score": 0.99}


def _f(x0, x1, y0=598, y1=632, latex="\\widetilde { \\mathcal { O } }"):
    return {"bbox": [x0, y0, x1, y1], "latex": latex, "conf": 0.81}


def _keys(pages):
    """pages: [(text_block_list, formula_list)] → 抽取到的条目 key 集合。"""
    with tempfile.TemporaryDirectory() as d:
        for i, (texts, formulas) in enumerate(pages, start=1):
            with open(os.path.join(d, "page_%03d.json" % i), "w", encoding="utf-8") as f:
                json.dump({"text": texts, "formulas": formulas}, f)
        return {it["key"].lower() for it in extract_items_en(d, 1, len(pages))}


class TestFormulaSlotSubjectPredicate(unittest.TestCase):
    def test_slot_formula_keeps_head(self):
        blk = _blk(HEAD)
        self.assertTrue(_formula_slot_subject(
            HEAD, HEAD.index("is") - 2, blk, [_f(205, 235)]))

    def test_no_gap_rejected(self):
        txt = "Theorem 3.5 follows from two results. To state these, we introduce"
        self.assertFalse(_formula_slot_subject(
            txt, txt.index("follows") - 1, _blk(txt), [_f(205, 235)]))

    def test_gap_without_formula_rejected(self):
        blk = _blk(HEAD)
        self.assertFalse(_formula_slot_subject(HEAD, 13, blk, []))

    def test_formula_elsewhere_on_line_rejected(self):
        # 行尾的行内式（在谓语之后）不构成「主语槽位」证据。
        blk = _blk(HEAD)
        self.assertFalse(_formula_slot_subject(HEAD, 13, blk, [_f(600, 640)]))

    def test_formula_on_other_line_rejected(self):
        blk = _blk(HEAD)
        self.assertFalse(_formula_slot_subject(
            HEAD, 13, blk, [_f(205, 235, y0=900, y1=930)]))

    def test_missing_poly_degrades_to_old_behaviour(self):
        blk = _blk(HEAD, poly=None)
        blk.pop("poly")
        self.assertFalse(_formula_slot_subject(HEAD, 13, blk, [_f(205, 235)]))


class TestExtractItemsEndToEnd(unittest.TestCase):
    def test_theorem_with_formula_subject_is_extracted(self):
        got = _keys([([_blk(HEAD)], [_f(205, 235)])])
        self.assertIn("theorem 3.6", got)

    def test_plain_mention_still_dropped(self):
        txt = "Theorem 3.5 follows from two results. To state these, we introduce"
        got = _keys([([_blk(txt)], [_f(600, 640)])])
        self.assertNotIn("theorem 3.5", got)

    def test_real_head_unaffected(self):
        txt = "Theorem 3.7 If {x1, ..., xr} = f-1(y) then  is a free Oy-module of rank n"
        got = _keys([([_blk(txt)], [_f(205, 235)])])
        self.assertIn("theorem 3.7", got)


if __name__ == "__main__":
    unittest.main(verbosity=2)
