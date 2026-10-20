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
    the exemption is **narrowed by node type** (Lehmann ch4): a dash key whose node type is
    a numbered result (``example`` / ``theorem`` / …) is an ordinary body item and is NOT
    exempt, while unknown / ``uncat`` / exercise types keep the old exemption;
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
                            check_unit_order, dash_exempt, inherited_desc_anchor_keys,
                            is_dash_problem,
                            iter_unit_nodes, resolve_unit_anchors, _anchor_tables)


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
    multi, anytype, exact = _anchor_tables(_contract([("11.1", 20), ("11.1", 30)]))
    # 锚点 = (page_start, 契约前序号, 归一键, 节点type, 契约原始键)；前序号让「页码相同但
    # 登记序倒退」也能被抓到，尾两项让修复类工具（tools/sync_manifest_order.py）拿到节点本体
    assert [a[:2] for a in multi[("item", "11.1")]] == [(20, 0), (30, 1)]
    assert [a[:2] for a in anytype["11.1"]] == [(20, 0), (30, 1)]
    assert [a[:2] for a in exact["11.1"]] == [(20, 0), (30, 1)]
    assert multi[("item", "11.1")][1] == (30, 1, "11.1", "item", "11.1")
    assert [(d["page"], d["key"]) for d in iter_unit_nodes(
        _contract([("11.1", 20), ("11.1", 30)]))] == [(20, "11.1"), (30, "11.1")]


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


# --------------------------- 续接单元：一个契约节点拆成多条单元（2026-09-29 阿诺尔德）
def _cu(t, ntype, key, cont=False):
    u = _u(t, ntype, key)
    if cont:
        u["continuation"] = True
    return u


def test_continuation_unit_reuses_parent_anchor_and_earns_no_regression():
    # 印刷字母小节材料化：父单元留前缀，字母正文单元沿用父键（节级编号覆盖对账按 key
    # 取正文，换合成键就会被当成漏写）。一个节点可切出**多个**字母正文单元，而未标记的
    # 第二条会落到该键锚点列表的第 2 项 = 另一节同键条目的页码，此后整章消费错位；
    # 带 continuation 标记则复用父单元锚点且不动游标 ⇒ 0 问题。
    c = _sec_contract([("section", "1.1", 24), ("example", "例4", 25),
                       ("section", "1.2", 40), ("example", "例4", 41)])
    units = [_u("section", "section", "1.1"),
             _cu("item", "example", "例4"),
             _cu("desc", "description", "例4", True),
             _cu("desc", "description", "例4", True),
             _u("section", "section", "1.2"),
             _cu("item", "example", "例4"),
             _cu("desc", "description", "例4", True)]
    assert check_unit_order(c, units) == []


def test_unmarked_duplicate_key_still_desyncs():
    # 负向：continuation 标记不是装饰——同一条清单去掉标记，第二个字母正文单元会消费
    # 该键的第 2 个锚点（下一节的 例4，p41），于是紧随其后的 §1.2（p40）被误判成倒退。
    c = _sec_contract([("section", "1.1", 24), ("example", "例4", 25),
                       ("section", "1.2", 40), ("example", "例4", 41)])
    units = [_u("section", "section", "1.1"),
             _u("item", "example", "例4"),
             _u("desc", "description", "例4"),
             _u("desc", "description", "例4"),
             _u("section", "section", "1.2"),
             _u("item", "example", "例4")]
    probs = check_unit_order(c, units)
    assert probs, "无标记的同键重复单元应消费到第 2 个锚点而错位"
    assert "1.2" in probs[0]


def test_contract_extras_do_not_lose_anchor():
    # 契约重数 > 单元重数（同键的节节点 + 习题块节点、V-I 省略块）：桶耗尽后退回首见页，
    # 不得因锚点缺失而让后续真错位漏检。
    c = _sec_contract([("section", "10.2", 708), ("exercise", "10.2", 712),
                       ("section", "10.3", 720), ("exercise", "10.3", 730)])
    multi, _any, _exact = _anchor_tables(c)
    assert [an[0] for an in multi[("section", "10.2")]] == [708]
    assert [an[0] for an in multi[("exercise", "10.2")]] == [712]
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




# --------------------------------------------------- resolve_unit_anchors（修复类工具用的同源解析）
def test_resolve_returns_contract_node_body():
    """解析结果须交出**契约节点本体**（原始键 + 名），修复工具据此复位陈旧键。"""
    c = {"key": "6", "type": "chapter", "name": "6", "page_start": 260, "page_end": 290,
         "sub_sec": [{"key": "推论6.2.5", "type": "corollary",
                      "name": "推论6.2.5 6.2.5", "page_start": 262, "page_end": 262},
                     {"key": "引理6.2.6", "type": "lemma",
                      "name": "引理6.2.6 6.2.6", "page_start": 263, "page_end": 263}]}
    got = resolve_unit_anchors(c, [{"type": "item", "key": "6.2-5"},
                                   {"type": "item", "key": "引理6.2.6"}])
    assert [g["node"]["key"] for g in got] == ["推论6.2.5", "引理6.2.6"]
    assert [g["order"] for g in got] == [1, 2]   # 0 = 章根本身也入前序表
    assert got[0]["dash"] is True          # 旧连字符键形：判据照样解析（豁免的是页码倒退）
    assert got[0]["node"]["name"] == "推论6.2.5 6.2.5"


def test_resolve_chapter_record_skipped_and_unresolvable_is_none():
    c = _sec_contract([("section", "1.1", 24), ("example", "例1", 25)])
    got = resolve_unit_anchors(c, [{"type": "chapter", "key": "1"},
                                   {"type": "item", "key": "例1"},
                                   {"type": "desc", "key": "D9"}])
    assert got[0]["skip"] == "chapter" and got[0]["node"] is None
    assert got[1]["node"]["key"] == "例1"
    assert got[2]["node"] is None          # 契约查无此内容：交调用方按邻域取证


# ---------------- 裸号键与带前缀键同章混用（2026-09-30 高等代数 ch3/7/9 普查命中）
def _mixed_key_chapter():
    """高等代数 ch7 §7.7 实测形态：契约里 ``定理/定义/引理7.7.1`` 带体例前缀，
    ``例7.7.1`` 的节点键却是裸号 ``7.7.1``；manifest 记录键与契约键**逐字相同**。"""
    return _ch([_node("section", "7.7", 342),
                _node("theorem", "定理7.7.1", 343),
                _node("definition", "定义7.7.1", 344),
                _node("example", "7.7.1", 345),
                _node("theorem", "定理7.7.2", 345),
                _node("lemma", "引理7.7.1", 346)])


def test_bare_and_prefixed_keys_in_one_chapter_do_not_cross_steal():
    c = _mixed_key_chapter()
    units = [{"type": "section", "key": "7.7"},
             {"type": "item", "key": "定理7.7.1"},
             {"type": "item", "key": "定义7.7.1"},
             {"type": "item", "key": "7.7.1"},
             {"type": "item", "key": "定理7.7.2"},
             {"type": "item", "key": "引理7.7.1"}]
    # 契约侧尾号回退一旦把 ``定理7.7.1`` 也登记进裸号桶，裸号记录就从桶首吃到 p343，
    # 于是假报「item「7.7.1」(p343) 排在「定义7.7.1」(p344) 之后」。原始键全等档在前 ⇒ 0。
    assert check_unit_order(c, units) == []
    got = resolve_unit_anchors(c, units)
    assert [g["node"]["key"] for g in got] == ["7.7", "定理7.7.1", "定义7.7.1",
                                               "7.7.1", "定理7.7.2", "引理7.7.1"]
    assert [g["page"] for g in got] == [342, 343, 344, 345, 345, 346]


def test_bare_key_record_real_regression_still_flagged():
    # 负向：上一条的修法不得把真错位一起放过——把裸号 例7.7.1（p345）整条挪到章末。
    c = _mixed_key_chapter()
    units = [{"type": "section", "key": "7.7"},
             {"type": "item", "key": "定理7.7.1"},
             {"type": "item", "key": "定义7.7.1"},
             {"type": "item", "key": "定理7.7.2"},
             {"type": "item", "key": "引理7.7.1"},
             {"type": "item", "key": "7.7.1"}]
    probs = check_unit_order(c, units)
    assert len(probs) == 1 and "7.7.1" in probs[0] and "p345" in probs[0]


# ---------------- 旧连字符键 + 同号章末习题（2026-09-29 Katok ch6 实测）
def _katok_like_chapter():
    """Katok ch6 形态：条目节点键带前缀（``推论6.2.5``），章末习题块里另有一个
    **裸号同号**节点 ``6.2.5``（type=exercise，p280）；拆分当时的清单写成 ``6.2-5``。"""
    return _ch([_node("section", "6.2", 260),
                _node("corollary", "推论6.2.5", 262),
                _node("lemma", "引理6.2.6", 263),
                _node("exercise", "6.2.5", 280)])


def test_legacy_dash_item_key_resolves_to_prefixed_item_not_same_number_exercise():
    c = _katok_like_chapter()
    units = [{"type": "section", "key": "6.2"},
             {"type": "item", "key": "6.2-5"},          # 陈旧连字符键：无原始键全等档
             {"type": "item", "key": "引理6.2.6"},
             {"type": "exercise", "key": "6.2.5"}]
    got = resolve_unit_anchors(c, units)
    # 尾号别名把 ``推论6.2.5`` 也放进裸号桶，按前序消费：条目单元拿条目节点，
    # 单元类型在前的习题单元拿同号习题节点。旧契约侧无别名表时第 2 条会拿到 p280。
    assert [g["node"]["key"] for g in got] == ["6.2", "推论6.2.5", "引理6.2.6", "6.2.5"]
    assert [g["page"] for g in got] == [260, 262, 263, 280]
    assert check_unit_order(c, units) == []


def test_legacy_dash_item_key_after_exercise_sibling_keeps_item_anchor():
    # 负向兜底：同号裸号**习题**节点排在前面时，陈旧连字符条目记录仍须拿条目节点
    # （习题记录走 (类型,键) 桶、不动别名桶游标），且真跨页错位的记录仍要报错。
    c = _katok_like_chapter()
    swapped = [{"type": "section", "key": "6.2"},
               {"type": "exercise", "key": "6.2.5"},
               {"type": "item", "key": "6.2-5"},
               {"type": "item", "key": "引理6.2.6"}]
    got = resolve_unit_anchors(c, swapped)
    assert [g["page"] for g in got] == [260, 280, 262, 263]
    # 连字符键按设计豁免页码单调（章末习题体例），但习题块插到条目之前仍被其它记录暴露
    probs = check_unit_order(c, swapped)
    assert len(probs) == 1 and "引理6.2.6" in probs[0] and "p263" in probs[0]


# ------------------------------------------------ dash exemption narrowed by node type
def _typed_ch(kids, start=1):
    """``_ch`` 的章头页码写死 550，会让契约锚点自查先把「章头晚于其内容」报一轮——
    与本题无关。这里给一个页码自洽的章头，使 ``check_contract_anchors`` 的断言只反映
    被测形态。"""
    return {"key": "4", "type": "chapter", "name": "Ch", "page_start": start,
            "page_end": start + 100, "sub_sec": kids}


def test_dash_keyed_numbered_item_is_not_exempt():
    # Lehmann ch4 实测形态：条目按节起号写成 ``4.2-2``，契约把 p250 那条登记在 p249
    # 那条之前。旧判据把 dash 键**整族**豁免 ⇒ 门控 ⑪ 与契约锚点自查同时报 0，
    # 合并 md 阅读顺序倒退无人看见。收窄后两侧都必须点名。
    kids = [_node("theorem", "4.2-1", 248),
            _node("example", "4.2-2", 250),
            _node("example", "4.2-3", 249),
            _node("example", "4.2-4", 251)]
    c = _typed_ch(kids, start=245)
    units = [{"type": "item", "ntype": "theorem", "key": "4.2-1"},
             {"type": "item", "ntype": "example", "key": "4.2-2"},
             {"type": "item", "ntype": "example", "key": "4.2-3"},
             {"type": "item", "ntype": "example", "key": "4.2-4"}]
    probs = check_unit_order(c, units)
    assert len(probs) == 1, probs
    assert "4.2-3" in probs[0] and "p249" in probs[0] and "p250" in probs[0]
    anchors = check_contract_anchors(c)
    assert len(anchors) == 1, anchors
    assert "4.2.3" in anchors[0], anchors[0]


def test_dash_keyed_exercise_stays_exempt():
    # 章末习题：dash 键 + 习题类型 → 维持豁免（page_start 指正文首现页，按设计排章末）
    c = _typed_ch([_node("theorem", "11.1", 11), _node("theorem", "11.2", 12),
                   _node("exercise", "11-5", 11)], start=10)
    units = [{"type": "item", "ntype": "theorem", "key": "11.1"},
             {"type": "item", "ntype": "theorem", "key": "11.2"},
             {"type": "item", "ntype": "exercise", "key": "11-5"}]
    assert check_unit_order(c, units) == []
    assert check_contract_anchors(c) == []


def test_dash_type_lookup_falls_back_to_contract_but_stays_conservative():
    # 清单不带 ``ntype``（老清单 / 合并 md 反推）→ 退回契约**原始键全等**查类型
    c = _ch([_node("example", "4.2-2", 250), _node("example", "4.2-3", 249)])
    units = [{"type": "item", "key": "4.2-2"}, {"type": "item", "key": "4.2-3"}]
    assert len(check_unit_order(c, units)) == 1
    # 类型取不到（契约里没有这个原始键，如 Katok 的旧连字符键对带前缀节点）
    # → 维持旧豁免，绝不给这类书新增误报
    legacy = [{"type": "item", "key": "6.2-5"}, {"type": "item", "key": "6.2-6"}]
    assert check_unit_order(
        _ch([_node("corollary", "推论6.2.5", 262), _node("lemma", "引理6.2.6", 263)]),
        legacy) == []


def test_dash_exempt_helper():
    assert dash_exempt("11-5", "exercise") is True
    assert dash_exempt("11-5", "problem") is True
    assert dash_exempt("11-5", None) is True          # 类型取不到 = 保守豁免
    assert dash_exempt("11-5", "uncat") is True       # 形状不明 = 保守豁免
    assert dash_exempt("4.2-2", "example") is False   # 编号结果条目 = 不再豁免
    assert dash_exempt("4.2-2", "Theorem") is False   # 大小写无关
    assert dash_exempt("4.2.2", "example") is False   # 非 dash 键本来就不豁免



# ---------------------------------- 判据 7：继承锚点的导语容器（2026-10-20 Kreyszig ch4 实测）
def _desc_chapter(desc_pages, own_pages=False):
    """三节各带一个 ``description`` 导语节点的章契约。

    ``own_pages=False`` = 真实形态：容器 ``page_start`` 从所在**节**继承（与节起始页相同），
    它对「这段散文印在哪一页」没有证据。``own_pages=True`` = 反事实兜底：容器自己有独立
    页码（≠ 节起始页），此时页码单调判定必须照常生效。
    """
    secs = []
    for i, (sec_key, sec_page, dkey, dpage) in enumerate(desc_pages):
        kids = [_node("description", dkey, dpage if own_pages else sec_page),
                _node("item", sec_key + "-1", sec_page + 1),
                _node("item", sec_key + "-2", sec_page + 2)]
        # own_pages 形态下把容器页写成该节**末后**一页，制造可判定的锚点
        if own_pages:
            kids[0]["page_start"] = kids[0]["page_end"] = dpage
        secs.append(_node("section", sec_key, sec_page, kids))
    return {"key": "4", "type": "chapter", "name": "Ch", "page_start": 225,
            "page_end": 320, "sub_sec": secs}


_DESC3 = [("4.1", 225, "D1", 225), ("4.2", 228, "D2", 240), ("4.3", 233, "D3", 250)]


def _units_after_desc(key_pos):
    """按 ``(type, key)`` 列表造单元序。"""
    return [{"type": t, "ntype": {"desc": "description", "item": "item",
                                  "section": "section"}[t], "key": k}
            for (t, k) in key_pos]


def test_inherited_desc_anchor_helper():
    c = _desc_chapter(_DESC3)
    got = inherited_desc_anchor_keys(c)
    assert got == {"D1", "D2", "D3"}, got          # 三容器页 == 各自节起始页 = 继承
    own = _desc_chapter(_DESC3, own_pages=True)
    # D1 的容器页仍 == 节页（225），D2/D3 的容器页被写成独立页 → 只有 D1 算继承
    assert inherited_desc_anchor_keys(own) == {"D1"}, inherited_desc_anchor_keys(own)


def test_inherited_desc_unit_out_of_page_order_is_not_flagged():
    # 交付/印面次序：节头 → 该节条目 → **下一节**的导语（Kreyszig ch4 全部 12 个 desc
    # 单元都是这个形态：容器继承页比它自己的散文早若干页）。旧判据一次假报 11 处。
    c = _desc_chapter(_DESC3)
    units = _units_after_desc([
        ("section", "4.1"), ("desc", "D1"), ("item", "4.1-1"), ("item", "4.1-2"),
        ("section", "4.2"), ("item", "4.2-1"), ("item", "4.2-2"),
        ("desc", "D2"), ("section", "4.3"), ("item", "4.3-1"), ("item", "4.3-2"),
        ("desc", "D3")])
    assert check_unit_order(c, units) == []


def test_inherited_desc_skip_does_not_blind_later_real_regression():
    # 负向兜底：跳过的导语不得「顺手」把游标放宽——其后一条真实跨页倒退（§4.3 的条目
    # 排到 §4.2 之前）仍须点名，且参照页码不受 desc 豁免影响。
    c = _desc_chapter(_DESC3)
    units = _units_after_desc([
        ("section", "4.1"), ("desc", "D1"), ("item", "4.1-1"),
        ("section", "4.3"), ("item", "4.3-1"),          # 晚节先出现 = 真倒退
        ("section", "4.2"), ("item", "4.2-1")])
    probs = check_unit_order(c, units)
    assert len(probs) == 1, probs
    assert "4.2" in probs[0] and "p228" in probs[0]


def test_own_page_desc_unit_is_still_flagged():
    # 反事实：容器有**独立**页码证据（≠ 节起始页）时判据 7 不适用，倒退照常报。
    c = _desc_chapter(_DESC3, own_pages=True)
    units = _units_after_desc([
        ("section", "4.1"), ("desc", "D1"), ("item", "4.1-1"), ("item", "4.1-2"),
        ("section", "4.2"), ("item", "4.2-1"), ("item", "4.2-2"),
        ("section", "4.3"), ("item", "4.3-1"), ("item", "4.3-2"),
        ("desc", "D3")])                                # D3 独立页 250 > 其后无内容，OK
    assert check_unit_order(c, units) == []
    late_first = _units_after_desc([
        ("section", "4.1"), ("item", "4.1-1"),
        ("section", "4.2"), ("item", "4.2-1"),
        ("section", "4.3"), ("item", "4.3-1"),
        ("desc", "D2")])                                # D2 独立页 240，排在 p234 之后
    probs = check_unit_order(c, late_first)
    assert any("D2" in p for p in probs), probs


def test_desc_unit_consuming_item_anchor_stays_checked():
    # 豁免口径按**锚点节点类型**收窄，不按单元 ``type``：一条 ``desc`` 记录若把键解析到
    # **条目**节点（该键在契约里没有 description 节点），继承页判据不适用，真倒退
    # 仍要点名。键形取**点分**而非 dash——dash 键先被判据 4 的 ``dash_exempt`` 处理，
    # 到不了这里（实测 遍历论_孙文祥 ch4 ``4.3-1`` / ch6 ``6.2-2`` 就是 dash 键的
    # **item** 记录，ntype 属编号结果 ⇒ 不豁免、照常判定，形态与判据 7 无关）。
    c = {"key": "6", "type": "chapter", "name": "Ch", "page_start": 100, "page_end": 160,
         "sub_sec": [_node("section", "6.1", 100, [_node("item", "6.1.1", 101),
                                                   _node("item", "6.1.2", 102)]),
                     _node("section", "6.2", 110, [_node("item", "6.2.1", 111),
                                                   _node("item", "6.2.2", 112)])]}
    units = _units_after_desc([
        ("section", "6.1"), ("item", "6.1.1"), ("item", "6.1.2"),
        ("section", "6.2"), ("item", "6.2.1"),
        ("desc", "6.2.2")])                             # desc 记录吃了 p112 的条目锚点
    assert check_unit_order(c, units) == []
    back = _units_after_desc([
        ("section", "6.1"), ("item", "6.1.1"),
        ("section", "6.2"), ("item", "6.2.1"), ("item", "6.2.2"),
        ("desc", "6.1.2")])                             # 但排在 p112 之后 → 真倒退
    probs = check_unit_order(c, back)
    assert any("6.1.2" in p for p in probs), probs


def test_dash_key_item_unit_is_never_desc_exempted():
    # 负向兜底（遍历论_孙文祥 ch4/ch6 实测形态）：dash 键 + **编号结果** ntype 的条目
    # 单元不参与任何 desc 豁免；同键的 desc 容器豁免不得顺手把这类记录一起放过。
    c = _desc_chapter([("6.1", 100, "D1", 100), ("6.2", 110, "D2", 110)])
    units = [{"type": "section", "ntype": "section", "key": "6.1"},
             {"type": "item", "ntype": "theorem", "key": "6.1-1"},
             {"type": "desc", "ntype": "description", "key": "D1"},
             {"type": "section", "ntype": "section", "key": "6.2"},
             {"type": "desc", "ntype": "description", "key": "D2"},
             {"type": "item", "ntype": "theorem", "key": "6.2-1"},
             {"type": "item", "ntype": "theorem", "key": "6.1-2"}]
    probs = check_unit_order(c, units)
    assert len(probs) == 1, probs
    assert "6.1-2" in probs[0], probs


# ---------------------------------------------------------------------------
# 判据 5 延伸：契约节点 page_start <= 0 = 无页码证据（Weibel 同调代数实测）
# ---------------------------------------------------------------------------
def _zero_page_chapter():
    """ch9 形态：降级手术把条目页码清成 0（``converted from miscast subsection``）。

    条目节点用 ``theorem``（+ 编号结果类型不享 dash 豁免），否则记录先被判据 4 豁免，
    根本走不到锚点解析，本测试就变成空转。
    """
    return {"key": "9", "type": "chapter", "name": "Ch", "page_start": 330,
            "page_end": 400, "sub_sec": [
                _node("section", "9.5", 338,
                      [_node("theorem", "9.5-5", 339),
                       _node("definition", "9.5-6", 0),
                       _node("theorem", "9.5-7", 340)]),
                _node("section", "9.6", 350, [_node("theorem", "9.6-1", 351)])]}


def test_zero_page_node_is_not_an_anchor():
    c = _zero_page_chapter()
    got = [(n["key"], n["page"]) for n in iter_unit_nodes(c)]
    assert ("9.5-6", 0) not in got, got
    assert sum(1 for k, _ in got if k == "9.5-6") == 0, got


def _zero_units(*pairs):
    """显式记录序（``ntype`` 用契约写法）——Weibel 的 0 页节点是 ``definition``，
    dash 键 + 编号结果类型**不享** dash 豁免，必须让它走到锚点解析才有意义。"""
    return [{"type": t, "ntype": nt, "key": k} for (t, nt, k) in pairs]


def test_zero_page_unit_record_is_skipped_not_flagged():
    c = _zero_page_chapter()
    units = _zero_units(("section", "section", "9.5"), ("item", "theorem", "9.5-5"),
                        ("item", "definition", "9.5-6"), ("item", "theorem", "9.5-7"),
                        ("section", "section", "9.6"), ("item", "theorem", "9.6-1"))
    assert check_unit_order(c, units) == []


def test_zero_page_skip_does_not_reset_cursor():
    # 负向兜底：页码 0 的单元被跳过，但它前面的游标（p340）仍须管住后面的真倒退
    c = _zero_page_chapter()
    units = _zero_units(("section", "section", "9.5"), ("item", "theorem", "9.5-5"),
                        ("item", "theorem", "9.5-7"), ("item", "definition", "9.5-6"),
                        ("item", "theorem", "9.5-5"),                  # p339 再现 = 倒退
                        ("section", "section", "9.6"), ("item", "theorem", "9.6-1"))
    probs = check_unit_order(c, units)
    assert len(probs) == 1, probs
    assert "9.5-5" in probs[0] and "p339" in probs[0], probs


def test_zero_page_node_cleared_from_contract_self_check():
    # 契约前序自查同源剔除：0 页节点排在高页码内容之后不该算「锚点与树序矛盾」
    c = {"key": "9", "type": "chapter", "name": "Ch", "page_start": 330,
         "page_end": 400, "sub_sec": [
             _node("section", "9.5", 338,
                   [_node("theorem", "9.5-5", 339), _node("definition", "9.5-6", 0)]),
             _node("section", "9.6", 350, [_node("theorem", "9.6-1", 351)])]}
    assert check_contract_anchors(c) == []
    c["sub_sec"][0]["sub_sec"][1]["page_start"] = 337        # 真实倒退（早于其前序 339）
    assert any("9.5-6" in p or "9.5.6" in p for p in check_contract_anchors(c))
