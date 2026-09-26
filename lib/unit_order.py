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

1. 以 ``norm_secnum`` 归一键 → 该键在契约中**首次出现节点**的 ``page_start``（阅读顺序
   首见页），建锚点表；同键多节点取首见（保守，宁可漏不可误）。
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


def build_page_anchor(contract: Optional[Dict[str, Any]]) -> Dict[str, int]:
    """遍历分章契约树，返回 ``{归一键 -> page_start}``（同键取**首次出现**节点的页）。

    树的前序遍历（父先于子、子按 ``sub_sec`` 顺序）即契约登记的阅读顺序，故「首见」=
    阅读顺序里的第一次出现。仅收录带 ``page_start`` 且键可归一为非空的节点；内容块
    （无 type / text/formula/image）不带有效键，自然跳过。
    """
    anchor: Dict[str, int] = {}

    def _walk(node: Any) -> None:
        if not isinstance(node, dict):
            return
        key = node.get("key")
        ps = node.get("page_start")
        if key is not None and ps is not None:
            nk = norm_secnum(key)
            if nk and nk not in anchor:
                try:
                    anchor[nk] = int(ps)
                except (TypeError, ValueError):
                    pass
        for sub in (node.get("sub_sec") or []):
            _walk(sub)

    if isinstance(contract, dict):
        _walk(contract)
    return anchor


def _resolve_page(key: Any, anchor: Dict[str, int]) -> Optional[int]:
    """把单元键解析为契约页码：先整体归一键，再退回尾部点分序标（``例5.1``→``5.1``）。"""
    nk = norm_secnum(key)
    if nk in anchor:
        return anchor[nk]
    m = re.search(r"(\d+(?:\.\d+)+)$", nk)  # 带标签键的尾号
    if m and m.group(1) in anchor:
        return anchor[m.group(1)]
    return None


def check_unit_order(
    contract: Optional[Dict[str, Any]],
    units: List[Dict[str, Any]],
) -> List[str]:
    """检查 ``units``（**合并/manifest 顺序**）是否按契约页码单调不减。

    返回问题字符串列表（空 = 通过）。契约缺失（``None``）→ 直接返回 ``[]``（无从判
    真值，不误报，与其它门控的「契约缺失即跳过」一致）。

    每条问题含：出问题的单元（type / key / 页码）+ 被其「插队」的参照单元（key / 页码），
    便于定位「谁不该出现在这里」。
    """
    if not isinstance(contract, dict) or not units:
        return []
    anchor = build_page_anchor(contract)
    if not anchor:
        return []

    problems: List[str] = []
    max_page = -1
    max_ref: Tuple[str, int] = ("", -1)
    for u in units:
        if not isinstance(u, dict):
            continue
        if u.get("type") in _SKIP_TYPES:
            continue
        raw_key = u.get("key")
        if is_dash_problem(raw_key):        # 章末习题：豁免，不推进游标
            continue
        page = _resolve_page(raw_key, anchor)
        if page is None:                     # 锚点缺失：跳过，不重置游标
            continue
        if page < max_page:
            problems.append(
                "%s「%s」（原书 p%d）排在「%s」（原书 p%d）之后——早页内容出现在晚页"
                "内容之后，单元跨节/跨页错位（合并 md 阅读顺序倒退）" % (
                    u.get("type") or "单元", raw_key, page, max_ref[0], max_page))
        else:
            max_page = page
            max_ref = (str(raw_key), page)
    return problems
