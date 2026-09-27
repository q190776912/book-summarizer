# -*- coding: utf-8 -*-
"""Regression tests for ``_contract_counter_evidence`` (make_config): the
structure-contract counter evidence must carry the CONTRACT CHAPTER in its
window, must keep cross-label same-number samples (dedup by ``(form, comps)``),
and must honour the letter-slot appendix form.

Why (both are print-attested bugs, each with its own book):

* window without chapter — do Carmo《黎曼几何》(section-scoped shared counter,
  keys ``节.项``): the same ``2.1`` legitimately appears in chapter 5 AND chapter
  13.  With comps = (2,1) the window is ``(2,)``, so those are read as
  「同窗重号」— the DEFINITIVE parallel-counter signal — and one shared counter
  was split into 7 groups (37 false collision windows).
* dedup by comps — Shafarevich《Basic Algebraic Geometry 1》正文: 定理1.1-1.28 and
  例1.1-1.35 are two independent chapter-scoped counters that DO re-use numbers.
  First-seen-wins dedup on comps alone destroyed exactly those cross-label
  same-number pairs, so the four independent counters merged into one group and
  ANCHOR-SANITY (document order) refused the chapter.

Run:
    python config/verify_config/tests/test_contract_counter_evidence.py
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

_THIS = Path(__file__).resolve()
_ROOT = None
for _c in _THIS.parents:
    if (_c / "SKILL.md").exists():
        _ROOT = _c
        break
if _ROOT is None:
    _ROOT = _THIS.parents[3]
for _p in (str(_ROOT), os.path.join(str(_ROOT), "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot  # noqa: E402
_boot.setup()

import make_config as mc  # noqa: E402


def _node(key, ntype, name="", ps=1, pe=1, kids=None):
    return {"key": key, "type": ntype, "name": name, "page_start": ps,
            "page_end": pe, "sub_sec": list(kids or [])}


def _mk_ext(items_by_chapter):
    """Write a minimal ``_extract/book_structure/ch{N}.json`` set."""
    d = tempfile.mkdtemp()
    ext = os.path.join(d, "_extract")
    os.makedirs(os.path.join(ext, "book_structure"))
    for ch, items in items_by_chapter.items():
        kids = [_node(k, t, k, i + 1, i + 1)
                for i, (t, k) in enumerate(items)]
        tree = _node(str(ch), "chapter", "Ch%s" % ch, 1, 500, kids)
        with open(os.path.join(ext, "book_structure", "ch%s.json" % ch),
                  "w", encoding="utf-8") as f:
            json.dump(tree, f)
    return ext


def _group(evidence, depth=3):
    headings = [(0, f, c) for (f, c) in evidence]
    return mc._group_headings_by_counter(headings, depth, strict_reset=False)


class TestContractCounterEvidence(unittest.TestCase):

    def test_window_carries_contract_chapter(self):
        """节级编号书：跨章同号不得成为「同窗重号」证据。"""
        ext = _mk_ext({
            5: [("definition", "2.1"), ("theorem", "2.2"), ("corollary", "2.3")],
            13: [("definition", "2.1"), ("theorem", "2.2"), ("corollary", "2.3")],
        })
        ev = mc._contract_counter_evidence(ext)
        self.assertTrue(ev, "契约证据不得为空")
        comps = [c for (_f, c) in ev]
        self.assertIn((5, 2, 1), comps, "comps 必须带所属章号（章, 节, 项）")
        self.assertIn((13, 2, 1), comps, "跨章同号两项都须在证据里（各带自己的章）")
        self.assertNotIn((2, 1), comps, "不得再出现无章号的裸 (节, 项) 窗口")
        groups = _group(ev)
        self.assertEqual(len(groups), 1,
                         "共享计数器（跨章同号）不得被拆散: %s" % groups)
        self.assertEqual(set(groups[0]), {"Definition", "Theorem", "Corollary"})

    def test_same_chapter_cross_label_number_splits(self):
        """同章异标签重号 = 平行计数器的决定性证据，必须拆组。"""
        ext = _mk_ext({
            1: [("theorem", "1.1"), ("theorem", "1.2"),
                ("example", "1.1"), ("example", "1.2"), ("example", "1.3")],
        })
        ev = mc._contract_counter_evidence(ext)
        forms_at = {}
        for f, c in ev:
            forms_at.setdefault(c, set()).add(f)
        self.assertIn({"Theorem", "Example"}, list(forms_at.values()),
                      "(form, comps) 去重必须保留异标签同号样本")
        groups = _group(ev)
        self.assertEqual(len(groups), 2,
                         "两条独立计数器应拆成 2 组: %s" % groups)
        self.assertTrue(all(len(g) == 1 for g in groups), groups)

    def test_letter_appendix_slot_kept(self):
        """附录字母章位：`Proposition A.1` / `Corollary A.1` → ('A',1) 窗内重号。"""
        ext = _mk_ext({
            5: [("proposition", "A.1"), ("proposition", "A.2"),
                ("corollary", "A.1")],
        })
        ev = mc._contract_counter_evidence(ext, letter_chapter=True)
        self.assertTrue(ev, "字母章位证据不得为空")
        self.assertNotIn(5, [c[0] for c in ev],
                         "letter 通路取键自带的字母章位，不掺数字章号")
        groups = _group(ev)
        self.assertEqual(len(groups), 2,
                         "Proposition/Corollary 各自独立计数 → 2 组: %s" % groups)

    def test_single_level_window_is_chapter_then_number(self):
        ext = _mk_ext({2: [("theorem", "1"), ("corollary", "1"),
                           ("corollary", "2")]})
        ev = mc._contract_counter_evidence(ext, include_chapter=True)
        self.assertIn((2, 1), [c for (_f, c) in ev])
        groups = _group(ev, depth=2)
        self.assertEqual(len(groups), 2,
                         "同章重号的单级平行计数器须拆组: %s" % groups)

    def test_no_contract_returns_none(self):
        d = tempfile.mkdtemp()
        self.assertIsNone(mc._contract_counter_evidence(d))


if __name__ == "__main__":
    unittest.main(verbosity=2)
