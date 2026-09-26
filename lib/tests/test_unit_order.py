"""tests for lib.unit_order.check_unit_order

This module is the SSOT behind gate ⑪ (pre-merge, gate_units) and the U verify layer
(post-merge): it asserts the merge/manifest unit order is page-monotonic against the
per-chapter contract's ``page_start`` anchors — the one structural reading-order check
that B-layer (same-section-prefix ordinal), the set-based coverage gate, and
subsection_order (numeric section keys, pre-split) all miss.

Regression guardrails encoded here (all learned calibrating Lee《Smooth Manifolds》):
  * page regression is flagged (true positive) and correct order is clean;
  * ties (same page) are ALLOWED;
  * chapter-head units are skipped;
  * chapter-end dash Problems (raw key ``N-M``) are EXEMPT and must not touch the cursor;
  * an unresolvable key is skipped WITHOUT resetting the running max (so a later genuine
    scramble is still caught);
  * the dash-vs-dotted distinction is decided on the RAW key BEFORE norm_secnum collapses
    '-' into '.' (the exact bug that produced 110 false flags in the prototype).
"""
import lib.boot as b
b.setup()

from lib.unit_order import check_unit_order, is_dash_problem, build_page_anchor


def _contract(nodes):
    """Build a minimal chapter contract: root chapter node + flat item children.

    ``nodes`` = list of (key, page_start) tuples in CONTRACT-REGISTRATION order.
    """
    return {
        "key": "11",
        "type": "chapter",
        "name": "Ch",
        "sub_sec": [
            {"key": k, "type": "item", "name": k, "page_start": p, "page_end": p}
            for (k, p) in nodes
        ],
    }


def _units(keys):
    return [{"key": k, "type": "item"} for k in keys]


# --------------------------------------------------------------------------- true positive
def test_page_regression_is_flagged():
    c = _contract([("11.1", 11), ("11.2", 12), ("11.3", 13)])
    # 11.1(p11) -> 11.3(p13) -> 11.2(p12): the p12 unit is out of order (page < running max 13)
    probs = check_unit_order(c, _units(["11.1", "11.3", "11.2"]))
    assert len(probs) == 1
    assert "11.2" in probs[0] and "11.3" in probs[0]
    assert "p12" in probs[0] and "p13" in probs[0]


def test_correct_monotonic_order_is_clean():
    c = _contract([("11.1", 11), ("11.2", 12), ("11.3", 13)])
    assert check_unit_order(c, _units(["11.1", "11.2", "11.3"])) == []


# --------------------------------------------------------------------------- tie allowed
def test_same_page_ties_are_allowed():
    c = _contract([("11.1", 11), ("11.2", 11), ("11.3", 11)])
    assert check_unit_order(c, _units(["11.1", "11.2", "11.3"])) == []


# --------------------------------------------------------------------------- chapter skip
def test_chapter_head_unit_skipped():
    c = _contract([("11", 10), ("11.1", 11), ("11.2", 12)])
    units = [{"key": "11", "type": "chapter"}, {"key": "11.1", "type": "item"},
             {"key": "11.2", "type": "item"}]
    assert check_unit_order(c, units) == []


# --------------------------------------------------------------------------- dash exemption
def test_dash_problem_exempt_does_not_flag_or_advance_cursor():
    # A chapter-end Problem (raw dash key) whose page_start points at its FIRST mention
    # in the body (early page) must be exempt: here 11.1/11.2/11.3 are in order, then the
    # problem "11-5" sits on an early page AFTER later content — normally flagged, exempted.
    c = _contract([("11.1", 11), ("11.2", 12), ("11.3", 13), ("11-5", 11)])
    units = _units(["11.1", "11.2", "11.3", "11-5"])
    assert check_unit_order(c, units) == []


def test_dash_exempt_then_real_regression_still_caught():
    # After the exempt dash (cursor must stay at 13, not drop to the dash's early page),
    # a genuine p10 unit is still flagged.
    c = _contract([("11.1", 11), ("11.3", 13), ("11-5", 11), ("11.4", 10)])
    units = _units(["11.1", "11.3", "11-5", "11.4"])
    probs = check_unit_order(c, units)
    assert len(probs) == 1 and "11.4" in probs[0]


# --------------------------------------------------------------------------- unknown-page skip
def test_unknown_key_skipped_without_resetting_cursor():
    # "ghost" is absent from the contract -> skipped, and the running max (12) must persist
    # so the subsequent p10 item is still flagged.
    c = _contract([("11.1", 11), ("11.2", 12), ("11.3", 10)])
    units = _units(["11.1", "11.2", "ghost", "11.3"])
    probs = check_unit_order(c, units)
    assert len(probs) == 1 and "11.3" in probs[0]


# --------------------------------------------------------------------------- degenerate inputs
def test_no_contract_returns_empty():
    assert check_unit_order(None, _units(["11.1", "11.2"])) == []


def test_no_units_returns_empty():
    c = _contract([("11.1", 11), ("11.2", 12)])
    assert check_unit_order(c, []) == []


def test_empty_anchor_returns_empty():
    # contract without any page_start keys -> cannot derive truth -> silent, no false flags
    c = {"key": "11", "type": "chapter", "sub_sec": [{"key": "x", "type": "item"}]}
    assert check_unit_order(c, _units(["x", "y"])) == []


# --------------------------------------------------------------------------- raw-key dash detection
def test_is_dash_problem_raw_before_normalization():
    assert is_dash_problem("5-10") is True
    assert is_dash_problem("22-1") is True
    assert is_dash_problem(" 16-3 ") is True
    assert is_dash_problem("16.4-3") is True      # dotted prefix + trailing dash problem
    # dotted exercise / item must NOT be exempted
    assert is_dash_problem("5.10") is False
    assert is_dash_problem("Proposition 5.1") is False
    assert is_dash_problem("U1") is False
    assert is_dash_problem(None) is False


def test_build_page_anchor_first_occurrence_wins():
    # same normalized key appears twice; anchor must keep the FIRST page (conservative)
    c = {
        "key": "11", "type": "chapter",
        "sub_sec": [
            {"key": "11.1", "type": "item", "page_start": 20},
            {"key": "11.1", "type": "item", "page_start": 30},
        ],
    }
    assert build_page_anchor(c)["11.1"] == 20
