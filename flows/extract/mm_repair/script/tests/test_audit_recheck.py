# -*- coding: utf-8 -*-
"""Regression tests for the `--recheck` channel of ``mm_repair_audit.py``.

Background
----------
The audit only flags entries by **confidence** (score < text_thresh, formula
conf < threshold, garbled markers).  A block that OCR reads *confidently but
wrongly* is therefore invisible to the whole repair loop, and once it has fed a
contract item head the failure only surfaces far downstream — Shafarevich
《Basic Algebraic Geometry 1》p209: the printed head is
``Proposition 3.1 Ω is generated as an A-module…`` but PaddleOCR glued it into
``Proposition3.12isgenerated…`` at **score 0.97**.  The contract gained the
phantom item 命题3.12, and the structure completeness gate failed chapter 3 on
「缺号」+「阅读序倒挂」.  There was no sanctioned way to route that
already-confirmed defect back through repairs.json + apply (hand-editing
page_*.json would bypass the mm_repaired/mm_reviewed provenance markers).

`--recheck` is that channel: the agent names the entries, the audit crops and
registers them as unresolved regardless of score / prev_resolved.  These tests
guard the two pure helpers behind it, in particular the **fail-closed** half —
a silently dropped nomination is indistinguishable from "reviewed and fine".

Run:
    python flows/extract/mm_repair/script/tests/test_audit_recheck.py
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
import lib.boot as _boot
_boot.setup()

import mm_repair_audit as ma  # noqa: E402

PAGE = {
    "page": 209,
    "text": [
        {"poly": [1, 2, 3, 4], "text": "5 Differential Forms", "score": 0.98},
        {"poly": [1, 5, 3, 7], "text": "Proposition3.12isgenerated …",
         "score": 0.97, "mm_reviewed": True},
    ],
    "formulas": [
        {"bbox": [0, 0, 10, 10], "latex": "\\omega", "conf": 0.9},
    ],
}


class TestParseRecheckSpec(unittest.TestCase):
    def test_string_form(self):
        self.assertEqual(ma.parse_recheck_spec('["209:text:35"]'),
                         [(209, "text:35", "")])

    def test_dict_form_carries_why(self):
        spec = '[{"page": 209, "key": "text:1", "why": "印面 3.1 Ω"}]'
        self.assertEqual(ma.parse_recheck_spec(spec),
                         [(209, "text:1", "印面 3.1 Ω")])

    def test_entries_object(self):
        spec = '{"entries": ["209:formula:0"]}'
        self.assertEqual(ma.parse_recheck_spec(spec), [(209, "formula:0", "")])

    def test_malformed_all_raise(self):
        for bad in ('not json', '[123]', '["209"]', '["209:bogus:1"]',
                    '{"page": 209, "key": "text:1"}', '[]',
                    '[{"key": "text:1"}]', '[{"page": "x", "key": "text:1"}]'):
            with self.assertRaises(ValueError, msg=bad):
                ma.parse_recheck_spec(bad)


class TestCollectRecheckFlags(unittest.TestCase):
    def test_text_flag_shape_and_no_score_gate(self):
        out = ma.collect_recheck_flags(PAGE, {"text:1": "why"})
        self.assertEqual(len(out), 1)
        key, kind, region, current, score = out[0]
        self.assertEqual((key, kind), ("text:1", "text"))
        self.assertEqual(current, "Proposition3.12isgenerated …")
        self.assertEqual(region, [1, 5, 3, 7])
        self.assertEqual(score, 0.97, "高分条目正是本通路的靶子，不得按阈值过滤")

    def test_already_reviewed_block_can_be_reflagged(self):
        # PAGE text:1 carries mm_reviewed=True — re-audit must still accept it
        self.assertEqual(len(ma.collect_recheck_flags(PAGE, {"text:1": ""})), 1)

    def test_formula_flag_carries_reason(self):
        key, kind, region, current, conf, reason = \
            ma.collect_recheck_flags(PAGE, {"formula:0": ""})[0]
        self.assertEqual((key, kind, reason), ("formula:0", "formula", "recheck"))
        self.assertEqual(current, "\\omega")

    def test_out_of_range_fails_closed(self):
        for bad in ("text:9", "formula:3"):
            with self.assertRaises(ValueError, msg=bad):
                ma.collect_recheck_flags(PAGE, {bad: ""})


class TestBlockAlreadyHandled(unittest.TestCase):
    """幂等：终态标记（repaired / reviewed / converted / unavailable）一律跳过。

    旧 text 侧漏认 `mm_converted` / `mm_unavailable`，令已修完的书重跑 audit 时
    把处理过的条目重新标成待修（Shafarevich p308 七条 mm_converted 实测复活），
    manifest 由全绿假回退成 pending。
    """

    def test_all_terminal_flags_skip(self):
        for fl in ("mm_repaired", "mm_reviewed", "mm_converted", "mm_unavailable"):
            self.assertTrue(ma.block_already_handled({fl: True}), fl)

    def test_unmarked_block_still_scanned(self):
        self.assertFalse(ma.block_already_handled({"text": "x", "score": 0.1}))

    def test_empty_dict_safe(self):
        self.assertFalse(ma.block_already_handled({}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
