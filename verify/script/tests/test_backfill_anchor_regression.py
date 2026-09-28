"""Negative regression test — backfill anchor self-consistency (contract pre-order pages).

Defect reproduced (Iwaniec-Kowalski《Analytic Number Theory》, chapter-shared counter
= ORDINAL_TWO_LEVEL + chapter_first, 2026-09-28): ch3 §3.6/§3.7/§3.8 span pages
60/62/63 and hold items 定理3.6(p61) … 定理3.8(p67). The missed item 命题3.7 (p65) has
canon (3,7), so the canon-adjacency backfill branch happily hung it after 定理3.6 —
i.e. a page-65 item *before* the page-62/63 sections. `build_structure` runs
`check_contract_anchors` before writing, but backfill lands afterwards, so the
contradiction only surfaced much later as write-source gate ⑪ ("单元跨节/跨页错位"),
by which time the whole chapter was already split into units.

Asserts:
  1. guarded  — insert_item vetoes the canon-adjacency spot that regresses the
     anchor pages (it re-tries the canon successor instead), so the item ends up
     inside §3.8 before 定理3.8 and the contract passes check_contract_anchors;
  2. control  — with the veto stubbed out, the same fixture DOES regress through
     canon-adjacency and DOES produce anchor problems (so assertion 1 is meaningful).

Run:
    python verify/script/tests/test_backfill_anchor_regression.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.dirname(HERE)          # verify/script
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import check_structure_completeness as csc
from data.book_structure.book_structure import StructureNode
from lib.unit_order import check_contract_anchors
from verify_config import ORDINAL_TWO_LEVEL


def _n(key, ntype, page, kids=()):
    return StructureNode(key=key, type=ntype, name=str(key), page_start=page,
                         page_end=page, sub_sec=list(kids))


def fixture():
    """chapter 3 — sections 3.6(p60)/3.7(p62)/3.8(p63), items 3.6(p61)/3.8(p67)."""
    return _n("3", "chapter", 60, [
        _n("3.6", "section", 60, [_n("D9", "description", 60),
                                  _n("定理3.6", "theorem", 61)]),
        _n("3.7", "section", 62, [_n("D10", "description", 62)]),
        _n("3.8", "section", 63, [_n("D11", "description", 63),
                                  _n("定理3.8", "theorem", 67)]),
    ])


def parent_of(tree, key):
    for s in tree.sub_sec:
        for c in s.sub_sec:
            if str(c.key) == key:
                return str(s.key), [str(x.key) for x in s.sub_sec]
    raise AssertionError(key)


def main():
    csc._PRIMARY = ORDINAL_TWO_LEVEL
    real = csc._anchor_problem_count

    # --- control: veto stubbed out -> the historical bad placement happens ----
    csc._anchor_problem_count = lambda tree: -1
    try:
        t = fixture()
        ok, where = csc.insert_item(t, "命题3.7", "Proposition", 65, (3, 7),
                                    "Proposition 3.7. Some statement.")
    finally:
        csc._anchor_problem_count = real
    assert ok, "backfill reported failure"
    assert where == "(canon-adjacency)", "fixture no longer reproduces: %s" % where
    assert parent_of(t, "命题3.7")[0] == "3.6", parent_of(t, "命题3.7")
    regressions = check_contract_anchors(t.to_dict())
    assert regressions, "fixture produces no anchor regression -> test is vacuous"
    print("[1] control reproduced: canon-adjacency put 命题3.7(p65) into §3.6 ->"
          " %d anchor regression(s): %s" % (len(regressions), regressions[0][:60]))

    # --- guarded: veto rejects that spot, the item lands page-consistently ----
    t = fixture()
    ok, where = csc.insert_item(t, "命题3.7", "Proposition", 65, (3, 7),
                                "Proposition 3.7. Some statement.")
    assert ok
    sec, order = parent_of(t, "命题3.7")
    assert sec == "3.8", (sec, order)
    assert order.index("命题3.7") < order.index("定理3.8"), order
    problems = check_contract_anchors(t.to_dict())
    assert not problems, "guarded tree still regresses: %s" % problems
    print("[2] guarded: rejected §3.6, placed via %s into §%s at %s"
          " -> contract anchor-clean" % (where, sec, order))

    # --- the veto helper itself measures regressions --------------------------
    assert real(fixture()) == 0, "clean fixture must measure 0"
    bad = fixture()
    bad.sub_sec[0].sub_sec.append(_n("命题3.7", "proposition", 65))
    csc._fix_pages(bad)
    assert real(bad) > 0, "veto helper blind to a hand-made regression"
    print("[3] _anchor_problem_count = 0 clean / >0 regressing")

    print("OK: backfill anchor veto works (canon-adjacency can no longer"
          " place a late-page item before earlier-page sections)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
