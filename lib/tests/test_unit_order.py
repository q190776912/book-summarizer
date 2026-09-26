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

``check_contract_anchors`` (the build-time contract self-check wired into
``build_structure``) is covered by the last group: the Rosen 8e ch8 shape where a
section's exercise-block node carries the page of the header/prose line that triggered
it (p585 > next section p563) must be named at build time, while the same node re-anchored
to the printed ``Exercises`` heading page at the end of its section must stay silent.

``check_section_key_page_order`` is the second build-time guard (Rosen 8e ch9): printed
section numbers must order the same way pages do, which still catches a mis-anchored
``§9.1.1 Introduction`` (its heading text repeats on a much later page) when that node
happens to sit at the **end** of the contract preorder and so leaves page-monotonicity
silent.
"""
import lib.boot as b
b.setup()

from lib.unit_order import (check_contract_anchors, check_section_key_page_order,
                            check_unit_order, is_dash_problem, _anchor_tables)


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
    # 旧「键 → 首见页」单值表已删（逐节重启号的书会批量假报），改为按类型分桶 +
    # 按出现序消费；_anchor_tables 的桶表是本判据的真值来源。
    multi, anytype = _anchor_tables(_contract([("11.1", 20), ("11.1", 30)]))
    # 条目 = (page_start, 契约前序号)，前序号让「页码相同但登记序倒退」也能被抓到
    assert multi[("item", "11.1")] == [(20, 0), (30, 1)]
    assert anytype["11.1"] == [(20, 0), (30, 1)]


# ------------------------------------------------- 逐节重启条目号（2026-09-26 Rosen 8e）
def _sec_contract(rows):
    """契约：``rows`` = [(node_type, key, page_start)]，按契约登记（前序）顺序。"""
    return {
        "key": "1", "type": "chapter", "name": "Ch", "page_start": 1, "page_end": 99,
        "sub_sec": [{"key": k, "type": t, "name": k, "page_start": p, "page_end": p}
                    for (t, k, p) in rows],
    }


def _u(t, ntype, key):
    return {"type": t, "ntype": ntype, "key": key}


# 原书每节都重印自己的 Example 1：同一归一键在契约里合法出现多次。
RESTART = [("section", "1.1", 24), ("example", "例1", 25), ("example", "例2", 26),
           ("section", "1.2", 40), ("example", "例1", 40),
           ("section", "1.3", 49), ("example", "例1", 49)]


def test_restart_numbered_items_in_reading_order_are_clean():
    # 旧「同键取首见」锚点会把 3 个 例1 都解析成 p25 ⇒ 2 处假报；按出现序消费后必须 0。
    c = _sec_contract(RESTART)
    units = [_u("section", "section", "1.1"), _u("item", "example", "例1"),
             _u("item", "example", "例2"), _u("section", "section", "1.2"),
             _u("item", "example", "例1"), _u("section", "section", "1.3"),
             _u("item", "example", "例1")]
    assert check_unit_order(c, units) == []


def test_restart_numbered_misplaced_block_still_flagged():
    # 真缺陷形态（Rosen ch1 §1.1.2 手术后的实测残留）：早节的条目单元排在晚节内容之后。
    # 契约同键重数与单元一致时，第 k 次出现仍锚到第 k 个页 ⇒ 倒退必须被命中。
    c = _sec_contract(RESTART)
    units = [_u("section", "section", "1.1"), _u("section", "section", "1.2"),
             _u("item", "example", "例1"), _u("item", "example", "例2"),
             _u("section", "section", "1.3"), _u("item", "example", "例1")]
    probs = check_unit_order(c, units)
    assert probs, "早节条目单元排到晚节之后必须被命中"
    assert "例1" in probs[0] and "p25" in probs[0] and "p40" in probs[0]


def test_contract_extras_do_not_lose_anchor():
    # 契约重数 > 单元重数（同键的节节点 + 习题块节点、V-I 省略块）：桶耗尽后退回首见页，
    # 不得因锚点缺失而让后续真错位漏检。
    c = _sec_contract([("section", "10.2", 708), ("exercise", "10.2", 712),
                       ("section", "10.3", 720), ("exercise", "10.3", 730)])
    multi, _any = _anchor_tables(c)
    assert [p for p, _o in multi[("section", "10.2")]] == [708]
    assert [p for p, _o in multi[("exercise", "10.2")]] == [712]
    assert check_unit_order(c, [_u("section", "section", "10.2"),
                                _u("exercise", "exercise", "10.2"),
                                _u("section", "section", "10.3"),
                                _u("exercise", "exercise", "10.3")]) == []
    # 单元键多于契约出现次数时退回首见页（708），后面的晚页单元仍不会被误报，
    # 但把晚页单元插到最前时必须仍能抓到。
    probs = check_unit_order(c, [_u("exercise", "exercise", "10.3"),
                                 _u("section", "section", "10.2")])
    assert len(probs) == 1 and "10.2" in probs[0]


def test_same_page_contract_order_regression_is_flagged():
    # 页码全等（旧判据按设计放行），但单元次序跨过了契约登记序 ⇒ 仍须命中。
    # 这正是「改了契约没同步 manifest」的形态（Rosen ch1 §1.1.2 手术后残留）。
    c = _sec_contract([("example", "例1", 40), ("example", "例2", 40)])
    probs = check_unit_order(c, [_u("item", "example", "例2"),
                                _u("item", "example", "例1")])
    assert len(probs) == 1 and "契约前序" in probs[0]


def test_contract_order_regression_across_blocks_is_flagged():
    # 早节整块内容被排到晚节之后：页码与登记序双双倒退，只报一条（页码优先）。
    c = _sec_contract([("example", "例1", 25), ("section", "1.2", 40),
                       ("example", "例1", 40)])
    probs = check_unit_order(c, [_u("section", "section", "1.2"),
                                _u("item", "example", "例1"),
                                _u("item", "example", "例1")])
    assert len(probs) == 1 and "跨节/跨页错位" in probs[0]


# ------------------------------------------------- 契约自身锚点自查（build_structure 闸）
def _ch(sub_sec):
    return {"key": "8", "type": "chapter", "name": "Ch", "page_start": 550,
            "page_end": 621, "sub_sec": sub_sec}


def _node(ntype, key, page, children=None):
    return {"key": key, "type": ntype, "name": key, "page_start": page,
            "page_end": page, "sub_sec": children or []}


def _ch8(exercise_page, exercise_first):
    """Rosen 8e ch8 形态：节 8.1 的习题块节点要么排在子节前（错），要么在末尾（对）。"""
    kids = [_node("exercise", "8.1", exercise_page)] if exercise_first else []
    kids += [_node("description", "D2", 550),
             _node("section", "8.1.1", 550),
             _node("section", "8.1.2", 551),
             _node("example", "例6", 557),
             _node("proof", "例6.P1", 557)]
    if not exercise_first:
        kids.append(_node("exercise", "8.1", exercise_page))
    return _ch([_node("section", "8.1", 550, kids),
                _node("section", "8.2", 563),
                _node("section", "8.3", 576)])


def test_contract_exercise_block_anchored_past_its_section_is_flagged():
    # 实测缺陷（Rosen 8e ch8 修补前）：习题块节点的页码取自「命中的页眉/散文行」（p585），
    # 晚于其后的 §8.2（p563）⇒ 契约自己就自相矛盾，必须在落盘前被点名。
    probs = check_contract_anchors(_ch8(585, exercise_first=True))
    assert len(probs) == 1
    assert "exercise「8.1」" in probs[0] and "p585" in probs[0]
    assert "Exercises" in probs[0]          # 给出「节习题块」修法提示


def test_contract_exercise_block_anchored_at_section_end_is_clean():
    # 同一节点改成真实页（习题块标题页 559）并移到父节点末尾 ⇒ 无告警。
    assert check_contract_anchors(_ch8(559, exercise_first=False)) == []


def test_contract_anchor_check_reports_run_once_with_count():
    # 整棵早节子树被挂到晚节之后：只报段首一条，并给出该段规模。
    c = _ch([_node("section", "8.1", 550),
             _node("section", "8.2", 563, [_node("example", "例1", 563)]),
             _node("section", "8.1.1", 551, [_node("example", "例1", 551),
                                             _node("example", "例2", 552)])])
    probs = check_contract_anchors(c)
    assert len(probs) == 1 and "同类共 3 处" in probs[0]


def test_contract_anchor_check_exempts_dash_problems():
    # 章末 dash 习题的 page_start 指向正文首现页（早页），按设计排在章末 ⇒ 不是缺陷。
    c = _ch([_node("section", "8.1", 550, [_node("example", "例1", 551)]),
             _node("section", "8.2", 563),
             _node("exercise", "8-3", 551),
             _node("exercise", "8-9", 552)])
    assert check_contract_anchors(c) == []


def test_contract_anchor_check_no_contract_returns_empty():
    assert check_contract_anchors(None) == []
    assert check_contract_anchors({"key": "8", "type": "chapter"}) == []


# ---------------------------------- 小节号 ↔ 页码交叉一致（前序单调闸的盲区，第二道闸）
def _ch9(section_911_page, where):
    """Rosen 8e ch9 实测形态：``§9.1.1 Introduction`` 的锚点抓到了后面那页重名的
    ``Introduction``（p673），真值是 p622。``where`` = 该节点挂在树里的位置。"""
    n911 = _node("section", "9.1.1", section_911_page)
    kids91 = [_node("description", "D2", 622),
              _node("section", "9.1.2", 623),
              _node("section", "9.1.3", 624)]
    root_kids = [_node("section", "9.1", 622, kids91),
                 _node("section", "9.2", 634),
                 _node("section", "9.6", 673, [_node("section", "9.6.1", 673)])]
    if where == "in-91":
        kids91.append(n911)
    elif where == "in-91-first":
        kids91.insert(0, n911)
    else:                                  # "tail"：整棵树的最后一个节点
        root_kids.append(n911)
    return {"key": "9", "type": "chapter", "name": "Relations", "page_start": 622,
            "page_end": 695, "sub_sec": root_kids}


def test_section_key_page_order_flags_intro_heading_collision_at_tree_tail():
    # 盲区证明：错锚节点恰在**前序末尾**（页码 673 = 全章最大），前序单调闸静默放行，
    # 而按印刷小节号排序立刻露馅（§9.1.1 p673 早于 §9.1.2 p623 却页码更晚）。
    c = _ch9(673, "tail")
    assert check_contract_anchors(c) == []
    probs = check_section_key_page_order(c)
    assert len(probs) == 1
    assert "§9.1.2" in probs[0] and "§9.1.1" in probs[0] and "p673" in probs[0]


def test_section_key_page_order_flags_same_defect_inside_parent():
    # 同一节点挂在 §9.1 子列表末尾时两道闸都响（互为兜底，报告口径不同）。
    c = _ch9(673, "in-91")
    assert check_contract_anchors(c), "前序闸应同时命中"
    assert len(check_section_key_page_order(c)) == 1


def test_section_key_page_order_clean_after_reanchor():
    # 修好（回到 p622 并排在 §9.1.2 之前）⇒ 静默。
    assert check_section_key_page_order(_ch9(622, "in-91-first")) == []


def test_section_key_page_order_ignores_non_dotted_keys():
    # 单段键（章级小节 "1"/"2"）与字母附录键（"A.2"）都不参与——它们不构成
    # 「同一点分编号体系内的先后关系」，按元组排序会假报。
    c = _ch([_node("section", "1", 300), _node("section", "2", 250),
             _node("section", "A.2", 900), _node("section", "A.1", 100)])
    assert check_section_key_page_order(c) == []


def test_section_key_page_order_no_contract_returns_empty():
    assert check_section_key_page_order(None) == []
    assert check_section_key_page_order({"key": "9", "type": "chapter"}) == []


