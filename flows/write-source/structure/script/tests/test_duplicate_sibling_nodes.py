# -*- coding: utf-8 -*-
"""Regression: duplicated same-(key,type) structural siblings must be merged
before content is attached (Rosen 8e exercise sets, 2026-09-25).

scan_skeleton reports the *same* exercise set twice for Rosen — the section-end
`EXERCISES` banner and the `Exercise Set 10.2` sub-head beneath it — and
`build_chapter` turns each EXER row into a node.  Two siblings with
`key=10.2 type=exercise` then become two units, and `gate_units` hard-fails the
whole chapter on 「契约本章习题条目重号」(7 groups measured: ch5 §5.4, ch6 §6.5/§6.6,
ch8 §8.3, ch9 §9.2, ch10 §10.2/§10.3), while the empty shell unit merges as a
bare heading.

Fix under test: `attach_content._dedupe_sibling_nodes`, run right after
`_to_skeleton` (nodes are still empty shells there) — keep one representative,
latest `page_start` (so the previous section's tail prose is not sucked into the
exercise node), non-bare `name`, children union.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_duplicate_sibling_nodes.py
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

from attach_content import _dedupe_sibling_nodes   # noqa: E402


def _n(key, ntype, name, ps, pe=None, kids=None):
    return {"key": key, "type": ntype, "name": name,
            "page_start": ps, "page_end": pe if pe is not None else ps,
            "sub_sec": list(kids or [])}


class TestDuplicateSiblingNodes(unittest.TestCase):
    def test_exercise_twins_merge_into_one(self):
        ch = _n("10", "chapter", "Graphs", 680, 760, [
            _n("10.2", "section", "Applications", 700, 720, [
                _n("10.2", "exercise", "Graph Terminology and Special Types", 708),
                _n("10.2", "exercise", "10.2", 708),
            ]),
        ])
        _dedupe_sibling_nodes(ch)
        sec = ch["sub_sec"][0]["sub_sec"]
        self.assertEqual(len(sec), 1, "重号练习节点必须并成一个")
        self.assertEqual(sec[0]["name"], "Graph Terminology and Special Types",
                         "裸号名不得顶掉印刷标题")

    def test_keeps_latest_page_start(self):
        ch = _n("6", "chapter", "Counting", 400, 470, [
            _n("6.6", "exercise", "Exercise Set 6.6 banner", 452, 452,
               [_n("a", "description", "", 452)]),
            _n("6.6", "exercise", "6.6", 455, 456),
        ])
        _dedupe_sibling_nodes(ch)
        ex = ch["sub_sec"]
        self.assertEqual(len(ex), 1)
        self.assertEqual(ex[0]["page_start"], 455, "锚点应贴着题面（组内最晚页）")
        self.assertEqual(ex[0]["page_end"], 456)
        self.assertEqual(len(ex[0]["sub_sec"]), 1, "子节点并集不得丢")

    def test_bare_first_name_replaced_by_printed(self):
        ch = _n("9", "chapter", "Relations", 600, 660, [
            _n("9.2", "exercise", "9.2", 640),
            _n("9.2", "exercise", "Exercises for Section 9.2", 641),
        ])
        _dedupe_sibling_nodes(ch)
        self.assertEqual(ch["sub_sec"][0]["name"], "Exercises for Section 9.2")

    def test_distinct_keys_and_types_untouched(self):
        kids = [_n("9.2", "exercise", "E 9.2", 640),
                _n("9.2", "section", "Relations", 630),
                _n("9.3", "exercise", "E 9.3", 650)]
        ch = _n("9", "chapter", "Relations", 600, 660, list(kids))
        _dedupe_sibling_nodes(ch)
        self.assertEqual(len(ch["sub_sec"]), 3, "key 或 type 不同者不得合并")

    def test_idempotent(self):
        ch = _n("5", "chapter", "Induction", 300, 360, [
            _n("5.4", "exercise", "Exercises 5.4", 350),
            _n("5.4", "exercise", "5.4", 350)])
        _dedupe_sibling_nodes(ch)
        once = str(ch)
        _dedupe_sibling_nodes(ch)
        self.assertEqual(str(ch), once, "重复执行必须幂等")


if __name__ == "__main__":
    unittest.main(verbosity=2)
