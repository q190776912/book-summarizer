# -*- coding: utf-8 -*-
"""Regression: number-first printed heads in `_item_pos`.

do Carmo《黎曼几何》(Riemannian Geometry, 2026-09-27 实测): headings print
NUMBER-FIRST ("2.1 DEFINITION. …").  Contract keys are CN-canonical
("定义2.1"); the existing head variants (CN / "definition 2.1" EN alias) and
the contain probe (prefix still carries the CN key) all miss, so every item
returned y=-1 → attach_content anchors degenerate to (page, 0.0) → each
page's content piles onto the LAST node and 120/263 items attach empty.

Fix under test: `_nf_specs` — for a CN label + numeric rest, also accept a
block whose line starts "<number> <label-word>" where the word is
OCR-similar (ratio ≥ 0.75) to an EN alias of the label.  Negative guards:
prose after the number ("2.1 shows that") must NOT anchor, and a longer
number must not be captured by a shorter key ("2.10" vs key 2.1).

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_numberfirst_item_anchor.py
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

from build_structure import _item_pos  # noqa: E402


def _blk(text, y):
    return {"text": text, "poly": [40, y, 500, y, 500, y + 14, 40, y + 14]}


class TestNumberFirstItemAnchor(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.ext = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def _page(self, num, blocks):
        fp = os.path.join(self.ext, "page_%03d.json" % num)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"text": blocks, "formulas": []}, f, ensure_ascii=False)

    def _pos(self, key, page, name, blocks, ptype="definition"):
        self._page(page, blocks)
        return _item_pos(self.ext, {"key": key, "page": page,
                                    "text": name, "type": ptype})

    def test_numberfirst_head_anchors(self):
        got = self._pos(
            "定义2.1", 64,
            "定义2.1 2.1 DEFINITION. An affne connection V on a differentiable man-",
            [_blk("50", 173), _blk(" Afne and Riemannian connections", 176),
             _blk("2.1 DEFINITION. An affne connection V on a differentiable man-", 279),
             _blk("ifold M is a mapping", 326)])
        self.assertEqual(got, (64, 279))

    def test_numberfirst_head_ocr_garbled_label(self):
        got = self._pos(
            "定义2.5", 66,
            "定义2.5 2.5 DEFINrTION. Let M be a differentiable manifold with an affine",
            [_blk("2.5 DEFINrTION. Let M be a differentiable manifold with an affine", 400),
             _blk("connection V. A vector field V along a curve", 450)])
        self.assertEqual(got, (66, 400))

    def test_numberfirst_theorem_mixed_case(self):
        got = self._pos(
            "定理3.6", 69,
            "定理3.6 3.6 Theorem. (Levi-Civita). Given a Riemannian manifold M,",
            [_blk("3.6 Theorem. (Levi-Civita). Given a Riemannian manifold M,", 300)],
            ptype="theorem")
        self.assertEqual(got, (69, 300))

    def test_negative_prose_after_number_not_anchored(self):
        # "2.1 shows that …" is a cross-reference/continuation, not a head.
        got = self._pos(
            "定义2.1", 64, "定义2.1 2.1 DEFINITION. An affne connection V",
            [_blk("2.1 shows that the metric is complete", 279)])
        self.assertEqual(got[1], -1)

    def test_negative_longer_number_not_captured(self):
        # key 2.1 must not anchor onto "2.10 DEFINITION".
        got = self._pos(
            "定义2.1", 64, "定义2.1 2.1 DEFINITION. An affne connection V",
            [_blk("2.10 DEFINITION. Another manifold entirely", 279)])
        self.assertEqual(got[1], -1)

    def test_label_first_books_unchanged(self):
        # Existing exact head path (EN alias "definition 2.1") still wins.
        got = self._pos(
            "定义2.1", 64, "定义2.1 Definition 2.1 (Norm) blah",
            [_blk("Definition 2.1 A norm on a vector space", 350),
             _blk("2.1 definition of a fake head", 100)])
        self.assertEqual(got, (64, 350))


if __name__ == "__main__":
    unittest.main(verbosity=2)
