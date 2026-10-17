# -*- coding: utf-8 -*-
"""Regression: the in-page anchor used to order item nodes must lock onto the
PRINTED item head, not onto a page header or a prose cross-reference.

Print (Lehmann《Elements of Large-Sample Theory》ch2, p79, 2026-10-15 实测) --
the block list of the page in y order::

    y=88    662. Convergence in Probability and in Law      <- running head
    y=156   Definition 2.3.2 A sequence of distributions …   <- real head
    y=531   2.3.2 only states that for large n, the …        <- prose回指
    y=1187  Example 2.3.4 Normal. If Yn is normally …
    y=1505  Example 2.3.5 Convergence in probability. If …

``_doc_y_of`` (the anchor behind `_sort_doc_order`) called ``_item_pos`` with
key/page/text only -- no ``type``.  ``_item_pos`` builds its "printed head"
variants from `it["type"]`, so without it:

* Example ``2.3-5`` never matched the HEAD layer (the printed head is
  label-first, ``Example 2.3.5 …``) and fell through to the CONTAIN layer, whose
  policy is ``min(y)`` -- the running head at y=88 shares the first 24 probe
  characters ("convergence in probabi") and won.
* Definition ``2.3-2`` matched the HEAD layer on the prose回指 line
  ("2.3.2 only states that …"), which the bare-ordinal variant accepts.

Those two wrong anchors plus the correct y=1187 of Example 2.3.4 make a
comparison cycle (5 < 定义2 < 4 < 5) for `_item_order_cmp`, and Timsort -- which
assumes a transitive comparator -- emitted `2.3-5, 2.3-2, 2.3-4`.  The B layer
then reported 顺序错乱 @2.3 seq=[1,2,3,5,4,…], i.e. the structure gate could not
pass.

Fix under test: pass the node ``type`` (the same convention
`attach_content._item_anchor` already uses), which registers the
"<label> <number>" head variant and makes the head layer win over contain.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_item_pos_label_head_anchor.py
"""
import functools
import json
import os
import re
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

import build_structure as B                                    # noqa: E402

P79 = [
    (88.0, "662. Convergence in Probability and in Law"),
    (156.0, "Definition 2.3.2 A sequence of distributions with cdf's Hn is "
            "said to con-"),
    (399.0, "(2.3.4)"),
    (531.0, "2.3.2 only states that for large n, the distribution of Yn is "
            "close to that of"),
    (1187.0, "Example 2.3.4 Normal. If Yn is normally distributed as N(&n, "
             "o2) and"),
    (1505.0, "Example 2.3.5 Convergence in probability. If Yn -> c and Y is "
             "a ran-"),
]


def _write_page(dirpath):
    blocks = [{"text": t, "poly": [120, y, 1080, y, 1080, y + 30, 120, y + 30],
               "score": 0.98} for y, t in P79]
    with open(os.path.join(dirpath, "page_079.json"), "w", encoding="utf-8") as f:
        json.dump({"text": blocks, "formulas": []}, f)
    return dirpath


class TestLabelHeadAnchor(unittest.TestCase):
    def _pos(self, key, text, typ=None):
        it = {"key": key, "page": 79, "text": text}
        if typ:
            it["type"] = typ
        with tempfile.TemporaryDirectory() as d:
            _write_page(d)
            return B._item_pos(d, it, page_dir=d)

    def test_example_head_not_stolen_by_running_head(self):
        got = self._pos("2.3-5", "2.3-5 2.3.5 Convergence in probability. "
                                 "If Yn -> c and Y is a ran-", typ="example")
        self.assertEqual(got, (79, 1505.0))

    def test_definition_head_not_stolen_by_prose_reference(self):
        got = self._pos("2.3-2", "2.3-2 2.3.2 A sequence of distributions "
                                 "with cdf's Hn is sai", typ="definition")
        self.assertEqual(got, (79, 156.0))

    def test_without_type_reproduces_the_wrong_anchor(self):
        # 负向：不传 type 时旧缺陷仍在（页眉抢先）——本条锁定「传 type」正是
        # 修复本身，而不是碰巧的其他改动。
        got = self._pos("2.3-5", "2.3-5 2.3.5 Convergence in probability. "
                                 "If Yn -> c and Y is a ran-")
        self.assertEqual(got, (79, 88.0))

    def test_anchor_order_matches_print(self):
        ys = [self._pos("2.3-2", "2.3-2 2.3.2 A sequence of distributions "
                                 "with cdf's Hn is sai", "definition")[1],
              self._pos("2.3-4", "2.3-4 2.3.4 Normal. If Yn is normally "
                                 "distributed as", "example")[1],
              self._pos("2.3-5", "2.3-5 2.3.5 Convergence in probability. "
                                 "If Yn", "example")[1]]
        self.assertEqual(ys, sorted(ys))

    def test_comparator_is_transitive_on_the_repaired_anchors(self):
        nodes = {
            "2.3-4|example": {"key": "2.3-4", "type": "example", "page_start": 79},
            "2.3-5|example": {"key": "2.3-5", "type": "example", "page_start": 79},
            "2.3-2|definition": {"key": "2.3-2", "type": "definition",
                                 "page_start": 79},
        }
        y_of = {"2.3-4": 1187.0, "2.3-5": 1505.0, "2.3-2": 156.0}

        def _y(node):
            return y_of[str(node["key"])]

        order = sorted(nodes.values(),
                       key=functools.cmp_to_key(
                           lambda a, b: B._item_order_cmp(a, b, _y)))
        self.assertEqual([n["key"] for n in order], ["2.3-2", "2.3-4", "2.3-5"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
