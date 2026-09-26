"""lib/unit_order.py — 总结单元「结构阅读顺序」核心校验（纯函数，无副作用）。

背景（2026-09-26 用户裁定）
------------------------
一本书的所有门控 / verify 层可以**全绿**，但合并 md 里的总结单元**次序仍然错乱**
（读者看到晚页内容出现在早页之前），原因是**没有任何闸门断言 merge 顺序 == 结构阅读
顺序**：

* B 层「编号单调」只在**同一节前缀**内比较，对以 U/D 结构锚为节、条目本身无统一
  数字前缀的书（如 Lee《光滑流形》）完全看不见跨节错乱；
* 反向覆盖闸 ``_check_contract_unit_coverage`` 是**集合**比较（分桶 + 序标归一），
  同一集合的任意**排列**都放行；
* ``subsection_order_problems`` 只查**契约里**小节数字键是否递增，跑在拆分之前，
  且只看逆序不看跨页。

本模块补上这块空白：以**源书页码（契约节点的 ``page_start``）为结构阅读顺序的真值**，
检查单元清单（manifest / 合并顺序）是否**页码单调不减**。页码是原书物理顺序，比契约
节点的**列表顺序**更可靠（契约列表可能被陈旧/错误的拆分排乱，但每个节点自带的
``page_start`` 始终指向它在原书里的真实页），因此即便契约本身排序有误，本判据仍能给出
正确的阅读顺序。

判据（与 ``_extract/_bks_order_probe.py`` 原型一致，实测 Lee 全书 24/26 章零误报，
仅 ch2 / appendixB 两处真实待修结构错位被精确命中）：

1. 以 ``norm_secnum`` 归一键 → 该键在契约中的**全部** ``page_start``（按前序 = 阅读顺序）。
   单元按「同一锚点列表的第 k 次出现」消费第 k 个页；列表耗尽才退回首见页。
   （2026-09-26 Rosen 8e 实测：**条目号逐节重启**的书里 ``例1`` 一章可出现 8 次，旧的
   「同键取首见」单值表会把晚节的 ``例1`` 解析成早节页码，一次性假报 118 处；
   按出现序消费后，逐节重启号书与全书唯一号书都得到正确锚点。）
2. 按传入的单元**顺序**遍历，维护「迄今最大页码」；某单元的页码**严格小于**迄今最大
   页码 → 该单元内容在原书更靠后，却排在更靠后页码内容之后 = 跨页错位，报告之。
3. 页码**相等允许**（同页多单元的正常形态，交由 B 层管同页内序标单调）。
4. **章末 dashes 习题豁免**：原书把 Problems 汇总到章末，但每道题的 ``page_start`` 指向
   其在正文中的**首次出现页**（早于章末内容），必然被页码单调判据误伤——键形 ``N-M``
   （原始键含连字符，归一前判定）一律跳过，不推进也不受限于页码游标。
5. 解析不到页码的单元（契约无该键 / 幻影 / 老键形对不上）→ **跳过**（既不当问题也不
   重置游标），避免因锚点缺失产生连锁误报。

调用方（gate_units 合并前 / verify 层合并后）负责取到 ``contract``（分章契约 dict）与
**有序** ``units``（manifest 的 ``units`` 数组，或合并 md 反推出的单元序），两者共用本
实现，杜绝双份逻辑漂移。

同模块另提供 ``check_contract_anchors(contract)``：不看单元、只看契约**自己**的前序页码
是否单调，供 ``build_structure`` 在**落盘前**拦下「锚点/位置自相矛盾」的节点（缺陷在源头，
事后由门控 ⑪ 反推代价大得多）。以及 ``check_section_key_page_order(contract)``：印刷
**小节号**的先后必须与页码先后一致，补上前序单调闸的盲区（错锚节点恰在前序末尾时无人
报错，Rosen 8e ch9 ``§9.1.1`` 实测）。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

try:  # 裸名（lib 在 sys.path）优先，退回包路径
    from util import norm_secnum
except ImportError:  # pragma: no cover - 取决于入口 bootstrap
    from lib.util import norm_secnum

# 章末 dash 习题键（**原始**、未归一）：如 "5-10" / "22-1" / "16.4-3"。
# 关键：必须在 norm_secnum 之前判定——归一会把 '-' 折成 '.'，与真点分序标（习题 5.10）
# 撞车，届时无法区分「章末 problem」与「点分 exercise」。
_DASH_PROBLEM_RE = re.compile(r"\d+(?:\.\d+)*-\d+")

# 单元类型里不参与页码单调判定的（章头本身只有一条、恒在最前，无意义）。
_SKIP_TYPES = frozenset({"chapter"})


def is_dash_problem(raw_key: Any) -> bool:
    """该键（原始、未归一）是否为「章末 dash 习题」（``N-M`` 体例）？

    这些单元的 ``page_start`` 指向正文首现页（早于章末正文），按设计汇总排到章末，
    故从页码单调判定中**整体豁免**。
    """
    return bool(_DASH_PROBLEM_RE.fullmatch(str(raw_key).strip()))


def _iter_anchor_entries(contract: Optional[Dict[str, Any]]):
    """前序遍历契约树，产出 ``(归一键, 节点 type, page_start, 前序序号)``。

    跳过无 ``key`` / 无 ``page_start`` / 键归一后为空的节点，以及 ``proof`` 子节点
    （``例3.P1`` 这类证明块按设计**不单独成单元**，若计入会与真单元的重数错位）。

    前序序号（父先于子、子按 ``sub_sec`` 列表序）是**契约自己的登记序**：页码只能证明
    「谁在原书更靠后」，序号才能证明「契约把这条内容排在前面」——两者一起用才分得开
    「契约排序错」与「单元次序跟丢了契约」（见模块头判据 2/2b）。
    """
    order = [0]

    def _walk(node: Any):
        if not isinstance(node, dict):
            return
        key = node.get("key")
        ps = node.get("page_start")
        ntype = node.get("type")
        if key is not None and ps is not None and ntype != "proof":
            nk = norm_secnum(key)
            if nk:
                try:
                    yield nk, ntype, int(ps), order[0]
                except (TypeError, ValueError):
                    pass
                else:
                    order[0] += 1
        for sub in (node.get("sub_sec") or []):
            for got in _walk(sub):
                yield got

    if isinstance(contract, dict):
        for got in _walk(contract):
            yield got


def check_unit_order(
    contract: Optional[Dict[str, Any]],
    units: List[Dict[str, Any]],
) -> List[str]:
    """检查 ``units``（**合并/manifest 顺序**）是否与原书页码、契约登记前序同时单调。

    返回问题字符串列表（空 = 通过）。契约缺失（``None``）→ 直接返回 ``[]``（无从判
    真值，不误报，与其它门控的「契约缺失即跳过」一致）。

    每条问题含：出问题的单元（type / key / 页码）+ 被其「插队」的参照单元（key / 页码），
    便于定位「谁不该出现在这里」。
    """
    if not isinstance(contract, dict) or not units:
        return []
    multi, anytype = _anchor_tables(contract)
    if not multi:
        return []

    consumed: Dict[int, int] = {}
    problems: List[str] = []
    max_page = -1
    max_order = -1
    max_ref: Tuple[str, int] = ("", -1)
    for u in units:
        if not isinstance(u, dict):
            continue
        if u.get("type") in _SKIP_TYPES:
            continue
        raw_key = u.get("key")
        if is_dash_problem(raw_key):        # 章末习题：豁免，不推进游标
            continue
        anchor = _unit_page(raw_key, u, multi, anytype, consumed)
        if anchor is None:                   # 锚点缺失：跳过，不重置游标
            continue
        page, order = anchor
        label = u.get("type") or "单元"
        if page < max_page:
            problems.append(
                "%s「%s」（原书 p%d）排在「%s」（原书 p%d）之后——早页内容出现在晚页"
                "内容之后，单元跨节/跨页错位（合并 md 阅读顺序倒退）" % (
                    label, raw_key, page, max_ref[0], max_page))
        elif order < max_order:
            # 页码没倒退但契约登记序倒退：单元**跨过了它在契约里的位置**（改约未改清单，
            # 或拆分后契约被重排）。同页互换不触发此支（序号仍须按前序）。
            problems.append(
                "%s「%s」（原书 p%d）在契约里登记在第 %d 位，却排在第 %d 位内容之后——"
                "单元次序与契约前序不一致（合并 md 阅读顺序倒退，须同步清单次序）" % (
                    label, raw_key, page, order, max_order))
        else:
            max_page = max(max_page, page)
            max_order = max(max_order, order)
            max_ref = (str(raw_key), page)
    return problems


# 契约自身锚点自查（build_structure 落盘前的结构闸，判据 2c）
# ---------------------------------------------------------------------------
_EXERCISE_TYPES = frozenset({"exercise", "problem"})


def _iter_anchor_nodes(contract: Optional[Dict[str, Any]]):
    """前序遍历契约，产出 ``(节点 dict, 归一键, page_start, 父键)``。

    过滤规则与 ``_iter_anchor_entries`` 一致（无键 / 无页 / ``proof`` 子节点不参与），
    但保留节点本体，便于报告点名。
    """
    def _walk(node, parent_key):
        if not isinstance(node, dict):
            return
        key = node.get("key")
        ps = node.get("page_start")
        ntype = node.get("type")
        nk = norm_secnum(key) if key is not None else None
        anchored = bool(nk) and ps is not None and ntype != "proof"
        if anchored:
            try:
                yield node, nk, int(ps), parent_key
            except (TypeError, ValueError):
                anchored = False
        for sub in (node.get("sub_sec") or []):
            for got in _walk(sub, str(key) if key is not None else parent_key):
                yield got

    if isinstance(contract, dict):
        for got in _walk(contract, None):
            yield got


def check_contract_anchors(contract: Optional[Dict[str, Any]]) -> List[str]:
    """契约**自身**的锚点-树序一致性自查（生成契约时就该拦住，别留给门控 ⑪ 事后报错）。

    返回问题字符串列表（空 = 通过）。判据：把契约节点按前序摊平，页码必须单调不减
    （相等允许，与判据 3 同）。出现「锚点早于其前序内容」的连续一段时，只报**段首**
    一条并给出该段长度——段首就是需要动手的那个节点。

    为什么需要这道闸（Rosen 8e ch6/ch8 实测教训）：由抽取器 ``Exercise`` 标签条目
    派生的「节习题块」节点，其 ``page_start`` 取的是**命中的那一行页眉/散文**所在页，
    而不是印刷标题 ``Exercises``（= 习题块真实页）；同时它按「键与节同号」被排在父节点
    子列表**最前**。两者叠加 → ch8 一次性 49 处、ch6 14 处门控 ⑪ 报错，而且合并 md 会
    把整节习题集插到节正文中间。检测点必须在**写契约之前**：
    ``subsection_order_problems`` 只比小节数字键、``_scan_anchor_sanity`` 是只读旁证，
    两者都看不见「同号习题块锚点跑到节末之后」这一形态。

    章末 dash 习题（判据 4）一律豁免：它们的 ``page_start`` 按设计指向正文首现页，
    排到章末必然「页码倒退」，不是缺陷。
    """
    if not isinstance(contract, dict):
        return []
    problems: List[str] = []
    max_page = -1
    max_ref: Tuple[str, Any, int, str] = ("", None, -1, "")
    pending_ref = None
    pending_tail = 0

    def _flush():
        nonlocal pending_ref, pending_tail
        if pending_ref is not None and pending_tail > 1:
            problems[-1] += "（同类共 %d 处）" % pending_tail
        pending_ref, pending_tail = None, 0

    def _hint(ntype):
        return ("（节习题块的常见形态：锚点须取本节末印刷标题 ``Exercises`` 所在页，"
                "且节点须移到父节点 ``sub_sec`` **末尾**）"
                if ntype in _EXERCISE_TYPES else "")

    for node, nk, page, pkey in _iter_anchor_nodes(contract):
        if is_dash_problem(node.get("key")):
            continue
        if page < max_page:
            if pending_ref == max_ref:
                pending_tail += 1
                continue
            ntype = node.get("type") or "?"
            msg = ("契约节点 %s「%s」（原书 p%d，父节点「%s」）排在其前序内容 %s"
                   "（原书 p%d）之后：锚点与树序矛盾——参照节点 %s 最可疑"
                   "（它的页码晚于其后的兄弟/子节），其次是本节点的挂接位置" % (
                       ntype, nk, page, pkey, max_ref[0], max_page, max_ref[0]))
            problems.append(msg + _hint(max_ref[3]) + _hint(ntype))
            pending_ref, pending_tail = max_ref, 1
        else:
            _flush()
            max_page = page
            max_ref = ("%s「%s」" % (node.get("type") or "?", nk), nk, page,
                       node.get("type") or "")
    _flush()
    return problems


# ---------------------------------------------------------------------------
# 小节号 ↔ 页码交叉一致性（build_structure 落盘前的第二道结构闸，判据 2d）
# ---------------------------------------------------------------------------
_DOTTED_NUM_RE = re.compile(r"^\d+(?:\.\d+)+$")


def _key_tuple(nk):
    return tuple(int(p) for p in nk.split("."))


def check_section_key_page_order(contract: Optional[Dict[str, Any]]) -> List[str]:
    """印刷**小节号**的先后必须与**页码**先后一致（Rosen 8e ch9 实测教训）。

    ``check_contract_anchors`` 查的是「前序页码单调」，它有一个天然盲区：错锚的节点
    恰好落在前序**末尾**（最后一个节点、或其后所有节点页码都更大）时，前序没有任何
    倒退可看，闸门静默放行，而单元顺序检查（门控 ⑪）要等到拆分后才可能撞上——
    Rosen 8e ch9 ``§9.1.1 Introduction`` 正是这一形态：``build_structure`` 按标题文本
    找锚点行，而 ``Introduction`` 这个词在本章后面（``§9.6.1`` 那页）又出现一次，于是
    该节点的 ``page_start`` 被写成 673（真值 622），且被排到 ``§9.1`` 子列表**末尾**；
    门控 ⑪ 因此一次报出 153 处「阅读顺序倒退」。

    判据：取本章所有带**点分数字键**的 ``section`` 节点，按小节号元组升序排（与印刷
    阅读顺序同），要求 ``page_start`` **单调不减**（同页允许：``§9.5`` 与 ``§9.5.1``
    印在同一页是常态）。逆序即报告——被跨过去的**前**节点就是可疑锚点。非数字键
    （``D7`` / ``例3`` / ``A.2`` 之类）、无页码节点一律不参与。
    """
    if not isinstance(contract, dict):
        return []
    secs = []
    for node, nk, page, _pkey in _iter_anchor_nodes(contract):
        if node.get("type") != "section" or not _DOTTED_NUM_RE.match(nk):
            continue
        secs.append((_key_tuple(nk), nk, page))
    secs.sort()
    problems: List[str] = []
    # 按小节号升序的相邻对：页码必须不减（同页允许，如 §9.5 与其 §9.5.1 印在同一页）；
    # 页码变小 → 前一个节点（号更早、页码却更晚）的锚点抓错了页。
    for (t1, k1, p1), (t2, k2, p2) in zip(secs, secs[1:]):
        if p2 >= p1:
            continue
        problems.append(
            "小节 §%s（原书 p%d）的小节号晚于 §%s（原书 p%d），页码却更早——印刷小节号"
            "顺序与页码矛盾，须核对 §%s 的锚点行（同名标题在别处重现时最容易抓错页，"
            "如 ``Introduction``）" % (k2, p2, k1, p1, k1))
    return problems


# manifest 记录 type → 契约节点 type 的等价写法（记录没有 ntype 时退回用它）。
# 'item' 故意不给别名：条目在契约里按体例分为 example/theorem/definition/…，
# 让 _unit_page 走「不分类型」兜底表，行为与旧的单值首见锚点一致。
_TYPE_ALIAS = {"desc": "description", "exercise": "exercise",
               "problem": "exercise", "section": "section", "chapter": "chapter"}


def _anchor_tables(contract):
    """一次遍历建两张出现序表：``{(节点type, 键): [(页, 前序号)…]}`` 与 ``{键: [(页, 前序号)…]}``。

    两表的页都按契约**前序**（= 阅读顺序）排列，故「第 k 次出现」在两种查法下一致。

    为什么按 ``(type, key)`` 分桶而不是只按 ``key``（Rosen 8e 实测教训）：同一归一键会
    合法重复——``例1`` 是**逐节重启**的条目号（一章可出现 8 次），``10.2`` 既是节节点
    也是该节习题块节点。早先版本只建「键 → 首见页」单值表，于是晚节的 ``例1`` 全被
    解析成早节的页，页码单调判据在 Rosen 8e ch1 一次假报 118 处（真错位的单元被淹没，
    闸门等于失效）。按 (类型, 键) 桶 + 出现序消费后，重启号书与键全书唯一的书都得到
    正确锚点（后者桶长恒为 1，行为与旧表一致）。
    """
    multi: Dict[Tuple[Any, str], List[Tuple[int, int]]] = {}
    anytype: Dict[str, List[Tuple[int, int]]] = {}
    for nk, ntype, page, order in _iter_anchor_entries(contract):
        multi.setdefault((ntype, nk), []).append((page, order))
        anytype.setdefault(nk, []).append((page, order))
    return multi, anytype


def _consume(entries, consumed):
    """取该锚点列表的下一个 ``(页, 前序号)``；列表耗尽后**退回首见条目**。

    退回而非返回 None：契约重数 > 单元重数（同键的节/习题块节点、V-I 省略的块）时，
    多出来的单元不该失去锚点，宁可保守沿用首见页（= 旧单值表行为）。
    """
    i = consumed.get(id(entries), 0)
    consumed[id(entries)] = i + 1
    return entries[i] if i < len(entries) else entries[0]


def _unit_page(raw_key, unit, multi, anytype, consumed):
    """该单元的 ``(契约页, 契约前序号)``；先按 ``(节点类型, 归一键)`` 桶，再退回不分类型。"""
    nk = norm_secnum(raw_key)
    tail = re.search(r"(\d+(?:\.\d+)+)$", nk)   # 带标签键的尾号（例5.1 -> 5.1）
    keys = [nk] + ([tail.group(1)] if tail else [])
    for t in (unit.get("ntype"), _TYPE_ALIAS.get(str(unit.get("type")))):
        if not t:
            continue
        for k in keys:
            entries = multi.get((t, k))
            if entries:
                return _consume(entries, consumed)
    for k in keys:
        entries = anytype.get(k)
        if entries:
            return _consume(entries, consumed)
    return None
