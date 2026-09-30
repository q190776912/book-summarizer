# -*- coding: utf-8 -*-
"""Regression tests for ``mm_repair_apply.route_misfiled_segments``.

Background
----------
Fan-out agents write four verdict sections; the segment list
(``[{"type":"text",...},{"type":"formula",...}]``) belongs to ``to_structured``,
which is the only path that splits a line into new ``text[]`` / ``formulas[]``
entries.  An agent that files the same list under ``corrections`` used to have it
written **verbatim** into the page JSON, so ``text`` became a list — and every
consumer that reads page lines as strings crashed.  Evans《Partial Differential
Equations》p274 ``text:7`` / p276 ``text:16`` killed ``build_chapter_map.py``
with ``AttributeError: 'list' object has no attribute 'strip'``.

The guard reroutes such a value instead of dropping it (the agent's content is
fine, only the mailbox was wrong), and leaves genuine string corrections alone.

Run:
    python flows/extract/mm_repair/script/tests/test_apply_segment_routing.py
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "flows", "extract", "mm_repair", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mm_repair_apply import route_misfiled_segments  # noqa: E402

SEGS = [{"type": "text", "text": "= {"},
        {"type": "formula", "latex": "\\sum_{|\\alpha|\\le k}|D^{\\alpha}u|"}]


class TestRouting(unittest.TestCase):
    def test_string_correction_is_left_alone(self):
        corr = {"text:3": "$u \\in H^1(U)$"}
        tf, log = {}, []
        self.assertFalse(route_misfiled_segments(corr, tf, "text:3", log))
        self.assertEqual(corr, {"text:3": "$u \\in H^1(U)$"})
        self.assertEqual(tf, {})
        self.assertEqual(log, [])

    def test_segment_list_is_rerouted_not_dropped(self):
        corr = {"text:7": SEGS}
        tf, log = {}, []
        self.assertTrue(route_misfiled_segments(corr, tf, "text:7", log))
        self.assertEqual(corr, {})                      # 不再被当字符串写回
        self.assertEqual(tf["text:7"], SEGS)            # 内容原样进 to_structured
        self.assertTrue(any("[FORMAT]" in m for m in log))  # 且如实报告

    def test_absent_key_is_noop(self):
        corr, tf, log = {"text:1": "a"}, {}, []
        self.assertFalse(route_misfiled_segments(corr, tf, "text:9", log))
        self.assertEqual(corr, {"text:1": "a"})
        self.assertEqual(tf, {})

    def test_reroute_survives_missing_log_argument(self):
        corr, tf = {"formula:2": SEGS}, {}
        self.assertTrue(route_misfiled_segments(corr, tf, "formula:2"))
        self.assertEqual(tf["formula:2"], SEGS)


if __name__ == "__main__":
    unittest.main(verbosity=2)
