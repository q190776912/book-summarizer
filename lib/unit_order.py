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
   🔴 但**豁免按节点类型收窄**（2026-10-17 Lehmann ch4 实测）：``N.M-k`` 这一键形在条目
   按节起号的书里就是普通编号项（``4.2-2`` = Example 4.2.2），整体豁免会让门控对这类书
   **完全失明**（实测 ch4 把 p250 的条目登记在 p249 之前，门控 ⑪ 与契约锚点自查均报 0）。
   故类型属编号结果条目（``definition/theorem/lemma/proposition/corollary/example/remark/
   axiom/property``）的 dash 键**不再豁免**；类型取不到、或属习题族 / ``uncat`` / ``item``
   的一律维持豁免原状（保守侧，不给类型奇怪的书新增误报）。判据只此一份：:func:`dash_exempt`。
5. 解析不到页码的单元（契约无该键 / 幻影 / 老键形对不上）→ **跳过**（既不当问题也不
   重置游标），避免因锚点缺失产生连锁误报。契约节点自带 ``page_start <= 0`` 同属「无页码
   证据」：写源后的降级手术会把节点页码清成 0（2026-10-20 跨库普查全书库仅 6 处，全在
   Weibel《同调代数》：ch7/ch9 两个 ``chapter`` 节点 + ch9/10 三个
   ``definition``「converted from miscast subsection」），故建锚点表时一并剔除，
   契约前序自查（:func:`check_contract_anchors`）同源剔除。
6. **续接单元（manifest 记录带 ``"continuation": true``）**复用「同键最近一次正常消费
   的锚点」，**不推进**该键锚点列表的游标（键也解析不到时退回正常消费）。
   为什么需要：一个契约节点的正文可以被**合法地**拆成多条单元——印刷字母小节
   （``letter_subs``，节内 A./B./C. 子块）材料化时，父单元只留前缀，每个字母生成
   「标题单元 + 正文单元」，而正文单元必须沿用父键，否则节级编号覆盖对账
   （``lib/problem_coverage.coverage_problems`` 按「单元 key ∈ 该节契约子树键集」取正文）
   会把拆出去的那半段看成漏写。沿用父键 ⇒ 该键在 manifest 里出现两次；条目号逐节重启
   的书（``例4`` 一章两次 → 锚点列表长 2）里，第二条会消费第 2 个锚点 = **另一节**那条
   的页码，于是从这一条起整章的锚点消费错位，一次性假报数十处跨页倒退
   （2026-09-29 阿诺尔德《经典力学的数学方法》ch3/4/5/7 实测）。续接标记由拆单元的一方
   写明，判据只在此模块认，别处不必再实现。
7. **继承锚点的导语容器跳过**（:func:`inherited_desc_anchor_keys`，2026-10-20 Kreyszig
   泛函分析 ch4 实测根治）：单元**消费的契约节点**是 ``description`` 且其 ``page_start``
   与所在节起始页相同（= 从节继承来的容器页）时，跳过判定、不推进游标。为什么必须跳：
   印面上节标题常排到页末、它的开场段落换到下一页首，「节头 → 导语」这一**正确**次序
   在页码单调判据下必然「倒退」。实测 Kreyszig ch4 的 12 个 desc 单元逐个是下一节的开场白
   （page_233.json：§4.3 标题 poly y=1286/1332，其开场白 y=1415 在标题**下方**），门控 ⑪
   据此假报 11 处，并把一次返修引到与印面相反的方向（源清单被改成「导语 → 节头」，与中英
   两版交付 md 分叉 ⇒ ``check_translate_parity`` 报「两侧顺序不同」）。
   🔴 口径按**锚点节点类型**收窄（不是按单元 ``type``）：跨书普查 79 → 65 处，消失的 14 处
   逐条核对均为「单元正文不属于其键所指节点」的继承锚点错挂；被豁免的只有「消费的锚点是
   ``description`` **且**该容器页 == 所在节起始页」这一种，其余一处不动——实测两种仍受约束
   的形态：① 遍历论_孙文祥 ch4 ``4.3-1`` / ch6 ``6.2-2`` 是 **item** 记录（ntype 属编号结果，
   连 dash 豁免都不成立），锚点本就是条目节点；② 同书 ch8 ``D4`` 是 desc 记录，但其容器
   页 216 ≠ 所在节起始页 214 = 容器自带页码证据，不属继承。判据测试
   ``lib/tests/test_unit_order.py::test_inherited_desc_*`` +
   ``::test_own_page_desc_unit_is_still_flagged`` + ``::test_desc_unit_consuming_item_anchor_stays_checked`` +
   ``::test_dash_key_item_unit_is_never_desc_exempted``。

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

# 🔴 **编号结果条目**的节点类型（2026-10-17 Lehmann ch4 实测根治）：dash 键形
# ``N.M-k`` 在**条目按节起号**的书里就是普通编号项（``4.2-2`` = Example 4.2.2），
# 与「章末习题」毫无关系，此前却被 ``is_dash_problem`` **整体**豁免 ⇒ 门控 ⑪ 与契约
# 锚点自查对这类书完全失明。实测：Lehmann ch4 契约把 Example 4.2.2 (continued)（p250）
# 登记在 Example 4.2.3（p249）之前，合并 md 阅读顺序倒退，两道闸都报 0。
# 跨书普查（corpus 全部契约，dash 键节点 6000+ 条）：definition 905 / theorem 1300 /
# example 1466 / proposition 392 / remark 310 / lemma 371 / corollary 289 / axiom 17 /
# property 47 属编号项，exercise 651 / problem 398 属习题；description 17 / uncat 1077 /
# section 38 形状不明。判据因此**只收回编号结果条目这一族**：类型落在下面集合里的 dash
# 键不再豁免（照常参与页码/前序单调），其余（含 ``uncat``/``item``/类型取不到）
# **维持旧豁免** = 不给类型奇怪的书新增误报。
_NUMBERED_NTYPES = frozenset({
    "definition", "theorem", "lemma", "proposition", "corollary",
    "example", "remark", "axiom", "property",
})


def dash_exempt(raw_key: Any, ntype: Any = None) -> bool:
    """该 dash 键是否享受「章末习题」豁免（= 不参与页码单调判定）。

    键形不是 dash → ``False``（本来就不该豁免）。键形是 dash 而节点类型属**编号结果条目**
    （:data:`_NUMBERED_NTYPES`）→ ``False``（那是正文条目，次序错乱必须被看见）。
    类型未知（``None`` / ``uncat`` / ``item`` / 习题族）→ ``True``（保守，维持豁免原状）。
    """
    if not is_dash_problem(raw_key):
        return False
    return str(ntype or "").strip().lower() not in _NUMBERED_NTYPES


# 单元类型里不参与页码单调判定的（章头本身只有一条、恒在最前，无意义）。
_SKIP_TYPES = frozenset({"chapter"})


def is_dash_problem(raw_key: Any) -> bool:
    """该键（原始、未归一）是否为「章末 dash 习题」（``N-M`` 体例）？

    这些单元的 ``page_start`` 指向正文首现页（早于章末正文），按设计汇总排到章末，
    故从页码单调判定中**整体豁免**。
    """
    return bool(_DASH_PROBLEM_RE.fullmatch(str(raw_key).strip()))


def iter_unit_nodes(contract: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """前序遍历契约里**会成单元**的节点 → 有序 list，下标即门控 ⑪ 的 `order`（契约登记前序号）。

    过滤规则与旧的 :func:`_iter_anchor_entries` 一致：无 ``key`` / 无 ``page_start`` /
    键归一后为空 / ``proof`` 子节点都不入列（证明块按设计不单独成单元，计入会与真单元
    重数错位）。带 ``name`` 一起交出，是为了让**修复类**工具（清单归位、陈旧键复位）拿到
    节点本体而不必再自建一份「键直比索引」——那份自建索引正是 Katok 实测的翻车点：契约
    条目键带体例前缀（``推论6.2.5``），清单里是拆分当时的旧键（``6.2-5``），直比整章拒归位，
    而门控按 (类型,键)+尾号回退照样解析通过，两侧判据从此各说各话。
    """
    out: List[Dict[str, Any]] = []

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
                    page = int(ps)
                except (TypeError, ValueError):
                    pass
                else:
                    # ``page_start <= 0`` = **无页码证据**（不是「原书第 0 页」）：写源后
                    # 的降级手术会把节点页码清成 0（Weibel 同伦代数 ch9/10 实测：3 个
                    # ``definition``「converted from miscast subsection」+ ch7/ch9 两个
                    # ``chapter`` 节点）。这类节点若进锚点表，任何单元吃到它都会被判成
                    # 「早页内容排在晚页之后」——判据 5 对「解析不到页码」一律跳过，
                    # 对「页码为 0」必须同样跳过，否则豁免只覆盖了一半的无证据形态。
                    if page > 0:
                        out.append({"key": str(key), "nk": nk, "type": ntype,
                                    "name": str(node.get("name") or ""), "page": page})
        for sub in (node.get("sub_sec") or []):
            _walk(sub)

    if isinstance(contract, dict):
        _walk(contract)
    return out


def _iter_anchor_entries(contract: Optional[Dict[str, Any]]):
    """前序遍历契约树，产出 ``(归一键, 节点 type, page_start, 前序序号, 原始键)``。

    列与序号都由 :func:`iter_unit_nodes` 单一定义给出（判据只此一份）。
    """
    for i, d in enumerate(iter_unit_nodes(contract)):
        yield d["nk"], d["type"], d["page"], i, d["key"]


# 契约侧「导语容器」节点类型。
_DESC_NODE_TYPE = "description"


def inherited_desc_anchor_keys(contract: Optional[Dict[str, Any]]) -> set:
    """契约里**锚点是继承来的** ``description`` 容器节点，其原始键集合。

    ``build_structure`` 把一节的导语聚成一个无名 ``description`` 节点（``D1``/``D2``…），
    而该节点的 ``page_start`` 写的就是**所在节**的起始页——容器自己没有独立页码证据。
    于是「节点页码」只能回答「这一节从哪页开始」，**回答不了「这段散文印在哪一页」**：
    印刷体里节标题常常落在页末、其导语段落排到下一页首（甚至紧跟着**下一节**的标题），
    写作期把导语单元排在节标题之后或前一节末段之后都是同一页的合法形态。

    实测（2026-10-20 Kreyszig 泛函分析 ch4）：12 个 ``desc`` 单元的正文逐个是**下一节**的
    开场段落（``page_233.json``：§4.3 标题 poly y=1286/1332，而 §4.3 开场白
    「The Hahn-Banach theorem 4.2-1 concerns real vector spaces…」y=1415 在其**下方**），
    交付中英两版都按「节头 → 导语」排 = 与印面一致；门控 ⑪ 却拿容器继承页
    （D2→p228 = §4.2 起始页）判它「排在 §4.3（p233）之后 = 倒退」，一次假报 11 处，
    并把一次「按报错改清单」的返修引到了**与印面相反**的方向。
    跨书普查（corpus 全部 ``units/*/manifest.json`` × 契约）：旧判据 79 处问题，
    豁免「继承锚点的 desc 单元」后 65 处，消失的 14 处逐条核对**单元正文都不属于
    其键指向的契约节点**（导语错挂 / 习题残留），即全部是同一形态；
    倒退一处不动的两类实测：遍历论_孙文祥 ch4/ch6 的 ``4.3-1`` / ``6.2-2`` 是 **item**
    记录（锚点为条目节点），同书 ch8 的 ``D4`` 虽是 desc 记录、容器却自带独立页码
    （216 ≠ 所在节起始页 214）= 有证据，两者都不落在豁免口径里。
    """
    out: set = set()

    def _walk(node: Any, sec_page: Any):
        if not isinstance(node, dict):
            return
        ntype = node.get("type")
        ps = node.get("page_start")
        cur = sec_page
        if ntype == "section":
            cur = ps
        if ntype == _DESC_NODE_TYPE and ps is not None and ps == cur:
            out.add(str(node.get("key")).strip())
        for sub in (node.get("sub_sec") or []):
            _walk(sub, cur)

    if isinstance(contract, dict):
        _walk(contract, contract.get("page_start"))
    return out


def _monotonic_problems(
    seq: List[Tuple[str, Any, int, int]],
    *,
    where_page: str = "合并 md 阅读顺序倒退",
    where_order: str = "合并 md 阅读顺序倒退，须同步清单次序",
    by_preorder: bool = True,
) -> List[str]:
    """对 ``(label, key, page, order)`` 的**阅读顺序**序列跑「页码 + 契约前序」双调判定。

    判据 1–3（页码严格小于迄今最大 = 跨节/跨页错位；页码相等允许；页码没倒退但契约登记
    序倒退 = 单元跨过了它在契约里的位置）。抽成一份实现，是为了让「清单顺序」
    （:func:`check_unit_order`）与「交付 md 实际读到的顺序」（:func:`check_delivered_order`）
    两侧不可能各说各话；两个 ``where_*`` 只改报告括注里的**被测对象**，不改判据。

    ``by_preorder=False`` 关掉第二条支（契约前序 tie-break），只留页码单调 ——
    交付侧口径必须这么收窄，理由不是设计偏好而是实测：
    **同一页之内**的先后，契约的 ``sub_sec`` 列表序**没有印面证据**（页码相等 = 判据 3
    允许，前序只是「拆分当时的登记」）。2026-10-23 茆诗松《概率论与数理统计教程》全书
    实测 6 处「前序倒退」，逐条解剖：4 处是 ``check_contract_anchors`` 文档里那条已知形态
    ——节习题块登记成父节**第一个**子节点（``习题6.1`` 前序 15、``例6.1.6`` 前序 16，
    而印面在 §6.1 末），交付侧才是对的；2 处是同页 subsection 与它的两条定义谁先谁后
    （p324 三个条目 + 一个节头同页，页码给不出答案）。拿它当阻断判据 = 逼着修书方按
    一个没有证据的次序去搬已经正确的交付块。
    """
    problems: List[str] = []
    max_page = -1
    max_order = -1
    max_ref: Tuple[str, int] = ("", -1)
    for label, key, page, order in seq:
        if page < max_page:
            problems.append(
                "%s「%s」（原书 p%d）排在「%s」（原书 p%d）之后——早页内容出现在晚页"
                "内容之后，单元跨节/跨页错位（%s）" % (
                    label, key, page, max_ref[0], max_page, where_page))
        elif by_preorder and order < max_order:
            # 页码没倒退但契约登记序倒退：单元**跨过了它在契约里的位置**（改约未改清单，
            # 或拆分后契约被重排）。同页互换不触发此支（序号仍须按前序）。
            problems.append(
                "%s「%s」（原书 p%d）在契约里登记在第 %d 位，却排在第 %d 位内容之后——"
                "单元次序与契约前序不一致（%s）" % (
                    label, key, page, order, max_order, where_order))
        else:
            max_page = max(max_page, page)
            max_order = max(max_order, order)
            max_ref = (str(key), page)
    return problems


def iter_judged_units(
    contract: Optional[Dict[str, Any]],
    units: List[Dict[str, Any]],
):
    """按**清单顺序**产出「参与页码单调判定」的单元 → ``(index, label, key, page, order)``。

    这是两条被测顺序（清单序 = :func:`check_unit_order`、交付文本序 =
    :func:`check_delivered_order`）**唯一一份**身份解析 + 豁免 + 锚点消费口径。
    抽成生成器不是美化：2026-10-23 跨语料普查里，交付侧口径原先拿「解析到的**节点**
    类型」判 ``dash_exempt``（节点类型必然具体），而清单口径拿「记录自带 ``ntype``，
    缺失时回退**同键类型集**、混用即保守豁免」（判据 4 的旧行为）。同一本书、同一条
    记录，两侧结论相反——Weibel《An Introduction to Homological Algebra》ch5/ch10
    实测 8 条「交付顺序倒退」全是这一分叉造出来的假阳（``5.4-4`` 同键挂着
    ``definition`` + ``exercise`` 两个节点 → 清单侧豁免、游标停在 p143；交付侧不豁免
    → 游标推到 p144，紧接的 ``5.4-5``（契约误登记 p143）就被判成倒退）。
    分叉的根源是「豁免写了两遍」，所以合写成一遍。

    跳过者一律**不消费锚点**（保持 ``check_unit_order`` 旧行为逐字不变）：
      * ``type`` ∈ :data:`_SKIP_TYPES`（章头）
      * dash 键且 :func:`dash_exempt`（章末习题；同键多类型 = 混用 → 保守豁免）
      * 锚点缺失（判据 5）
      * 继承锚点的 ``description`` 容器（判据 7）

    ``continuation`` 记录复用父单元锚点，不消费列表（判据 6）。
    """
    if not isinstance(contract, dict) or not units:
        return
    tables = _anchor_tables(contract)
    if not tables[0]:
        return
    # 单元记录没带 ``ntype`` 时（老清单 / 合并 md 反推），先看记录**自带的 `type`**
    # （结构族经 ``_TYPE_ALIAS`` 映射），再退回契约**原始键全等**查节点类型。
    # 只在唯一类型时采信，混用同键多类型（条目 + 同号习题）宁可维持旧豁免 = 不误报。
    key_types: Dict[str, set] = {}
    for d in iter_unit_nodes(contract):
        key_types.setdefault(str(d["key"]).strip(), set()).add(str(d.get("type") or ""))

    consumed: Dict[int, int] = {}
    follow: Dict[str, Tuple[int, int]] = {}
    inherited_desc = inherited_desc_anchor_keys(contract)
    for i, u in enumerate(units):
        if not isinstance(u, dict):
            continue
        if u.get("type") in _SKIP_TYPES:
            continue
        raw_key = u.get("key")
        if is_dash_problem(raw_key):
            nt = u.get("ntype")
            if not nt:
                # 🔴 清单记录**自带的 `type`** 是拆分当时的身份登记，对「这一条到底
                # 是不是章末习题」比「同键在契约里挂着哪些节点类型」更可信。先吃它，
                # 再落回同键类型集。Weibel《同调代数》ch5/ch10 实测假阳的第二半正是漏了
                # 这一步：习题记录（``type=exercise`` / ``problem``）的**契约习题节点缺位**
                # （同号的 ``Proposition 10.4.1`` 在、``Exercise 10.4.1`` 没登记），旧路径
                # 只查 ``key_types['10.4-1']`` → 拿到唯一的那条**条目**类型（proposition）
                # → 判「编号结果条目、不豁免」→ 习题单元被解析到条目的早页（p397），
                # 紧跟晚页条目（Example 10.4.9, p401）之后就假报「阅读顺序倒退」。
                # 而记录本身早已写明 ``type=exercise`` —— 习题族本就在章末豁免之列
                # （见 :func:`dash_exempt` 对「习题族」维持旧豁免），该用记录自带类型。
                # ``_TYPE_ALIAS`` 只把**结构族**（desc/exercise/problem/section/chapter）
                # 映射成节点类型；编号条目记录 ``type=item`` 不在表内 → 落回 key_types，
                # 逐字节维持旧行为（同号 ``{definition, exercise}`` 混用仍保守豁免）。
                nt = _TYPE_ALIAS.get(str(u.get("type") or "").strip().lower())
            if not nt:
                ts = key_types.get(str(raw_key).strip())
                nt = next(iter(ts)) if ts and len(ts) == 1 else None
            if dash_exempt(raw_key, nt):     # 章末习题：豁免，不推进游标
                continue
        nk = norm_secnum(raw_key)
        if u.get("continuation") and nk in follow:
            anchor = follow[nk]             # 续接单元：复用父单元锚点，不消费列表
        else:
            anchor = _unit_anchor(raw_key, u, tables, consumed)
            if anchor is not None:
                follow[nk] = anchor
        if anchor is None:                   # 锚点缺失：跳过，不重置游标
            continue
        if (anchor[3] == _DESC_NODE_TYPE
                and str(anchor[4] or "").strip() in inherited_desc):
            # 导语容器继承锚点：页码只说明「本节从哪页开始」，对这段散文的真实位置
            # 无证据 → 既不算问题，也不推进/受限游标（判据 7，见
            # :func:`inherited_desc_anchor_keys`）。
            continue
        yield (i, u.get("type") or "单元", raw_key, anchor[0], anchor[1])


def check_unit_order(
    contract: Optional[Dict[str, Any]],
    units: List[Dict[str, Any]],
) -> List[str]:
    """检查 ``units``（**合并/manifest 顺序**）是否与原书页码、契约登记前序同时单调。

    返回问题字符串列表（空 = 通过）。契约缺失（``None``）→ 直接返回 ``[]``（无从判
    真值，不误报，与其它门控的「契约缺失即跳过」一致）。

    被测序列 = :func:`iter_judged_units`（身份/豁免/消费的唯一定义处）按**清单顺序**
    直接喂给 :func:`_monotonic_problems`。

    每条问题含：出问题的单元（type / key / 页码）+ 被其「插队」的参照单元（key / 页码），
    便于定位「谁不该出现在这里」。
    """
    return _monotonic_problems(
        [(label, key, page, order)
         for _i, label, key, page, order in iter_judged_units(contract, units)])


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
                page = int(ps)
            except (TypeError, ValueError):
                anchored = False
            else:
                if page > 0:                  # 同 :func:`iter_unit_nodes`：页码 0 = 无证据
                    yield node, nk, page, parent_key
                else:
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
        if dash_exempt(node.get("key"), node.get("type")):
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
# 让 _unit_anchor 走「不分类型」兜底表，行为与旧的单值首见锚点一致。
_TYPE_ALIAS = {"desc": "description", "exercise": "exercise",
               "problem": "exercise", "section": "section", "chapter": "chapter"}


def _anchor_tables(contract):
    """一次遍历建三张出现序表：``{(节点type, 键): [锚点…]}``、``{归一键: [锚点…]}``、``{契约原始键: [锚点…]}``。

    锚点元组 = ``(页, 前序号, 归一键, 节点type, 契约原始键)``；三表的页都按契约**前序**
    （= 阅读顺序）排列，故「第 k 次出现」在三种查法下一致。

    🔴 契约侧同样做**尾号回退**（``推论6.2.5`` 额外登记在 ``6.2.5`` 名下），与单元侧的尾号
    回退对称（Katok ch6 实测的必要修正）：条目键带体例前缀时只登记全称，于是清单里
    ``6.2-5``（拆分当时的旧键，归一即 ``6.2.5``）会命中**同号的章末习题节点** ``6.2.5``，
    拿到晚 18 页的锚点——门控 ⑪ 由此既看不见这条的真实次序，又把后续一片正常单元误报成
    「早页内容排在晚页之后」。同一列表里多类型按前序共存，靠「第 k 次出现」消费天然分开
    （先出现的条目单元消费条目节点，后出现的习题单元消费习题节点）。

    🔴 但尾号回退会**污染**「裸号键与带前缀键在同一章混用」的书（2026-09-30 跨书普查命中
    高等代数 ch3/ch7/ch9）：ch7 契约里 ``定理7.7.1``(o72,p343)/``定义7.7.1``(o73,p344)/
    ``7.7.1``=例(o74,p345)/``引理7.7.1``(o78,p346) 四节点共存，清单键与契约键**逐字相同**；
    带前缀的三条各按全称消费，裸号那条却从别名桶 ``7.7.1`` 的第 1 项（= ``定理7.7.1``）
    开始吃，锚点早了 2 页 ⇒ 假报「阅读顺序倒退」。判据 = 补第三张**原始键全等**表，
    消费次序改为「类型桶 → 原始键全等 → 归一键（含尾号别名）」：越具体的证据越先用。
    Katok 的 ``6.2-5`` 在原始键表里全等无门（契约只有 ``推论6.2.5`` 与同号习题 ``6.2.5``），
    仍落到别名桶按前序拿到条目节点——两本书同时正确。

    为什么按 ``(type, key)`` 分桶而不是只按 ``key``（Rosen 8e 实测教训）：同一归一键会
    合法重复——``例1`` 是**逐节重启**的条目号（一章可出现 8 次），``10.2`` 既是节节点
    也是该节习题块节点。早先版本只建「键 → 首见页」单值表，于是晚节的 ``例1`` 全被
    解析成早节的页，页码单调判据在 Rosen 8e ch1 一次假报 118 处（真错位的单元被淹没，
    闸门等于失效）。按 (类型, 键) 桶 + 出现序消费后，重启号书与键全书唯一的书都得到
    正确锚点（后者桶长恒为 1，行为与旧表一致）。
    """
    multi: Dict[Tuple[Any, str], List[Tuple]] = {}
    anytype: Dict[str, List[Tuple]] = {}
    exact: Dict[str, List[Tuple]] = {}
    for nk, ntype, page, order, raw in _iter_anchor_entries(contract):
        anchor = (page, order, nk, ntype, raw)
        exact.setdefault(str(raw).strip(), []).append(anchor)
        for k in _key_variants(nk):
            multi.setdefault((ntype, k), []).append(anchor)
            anytype.setdefault(k, []).append(anchor)
    return multi, anytype, exact


def _key_variants(nk: str) -> List[str]:
    """归一键本身 + 尾号（``推论6.2.5`` → ``['推论6.2.5', '6.2.5']``；无尾号只返回本身）。"""
    tail = re.search(r"(\d+(?:\.\d+)+)$", nk or "")
    return [nk] + ([tail.group(1)] if tail and tail.group(1) != nk else [])



def _consume(entries, consumed):
    """取该锚点列表的下一个 ``(页, 前序号)``；列表耗尽后**退回首见条目**。

    退回而非返回 None：契约重数 > 单元重数（同键的节/习题块节点、V-I 省略的块）时，
    多出来的单元不该失去锚点，宁可保守沿用首见页（= 旧单值表行为）。
    """
    i = consumed.get(id(entries), 0)
    consumed[id(entries)] = i + 1
    return entries[i] if i < len(entries) else entries[0]


def _unit_anchor(raw_key, unit, tables, consumed, nodes=None):
    """该单元消费的**锚点元组**（``(页, 前序号, 归一键, 节点type, 契约原始键)``）。

    页码单调闸与修复工具共用这一份查表实现，两侧不可能各说各话。
    传 ``nodes``（:func:`iter_unit_nodes` 的列）时把命中的**契约节点本体**一并附上。

    查表次序 = 证据强度次序：``(节点类型, 键)`` 桶（最具体，能分开 ``10.2`` 的节节点与
    习题块节点）→ **契约原始键全等**（清单键与契约键逐字相同 = 拆分当时的登记，最强）→
    归一键（含尾号别名，兜住 ``6.2-5`` 这类旧键形）。
    """
    multi, anytype, exact = tables
    nk = norm_secnum(raw_key)
    keys = _key_variants(nk)                 # 与契约侧同一份尾号回退
    entry = None
    for t in (unit.get("ntype"), _TYPE_ALIAS.get(str(unit.get("type")))):
        if not t:
            continue
        for k in keys:
            entries = multi.get((t, k))
            if entries:
                entry = _consume(entries, consumed)
                break
        if entry:
            break
    if entry is None:
        entries = exact.get(str(raw_key or "").strip())
        if entries:
            entry = _consume(entries, consumed)
    if entry is None:
        for k in keys:
            entries = anytype.get(k)
            if entries:
                entry = _consume(entries, consumed)
                break
    if entry is None:
        return None
    if nodes is not None:
        node = nodes[entry[1]]
        if node["key"] != entry[4]:            # 列与锚点表同源，不一致即内部错误
            raise AssertionError("锚点序号 %d 指向 %r，与表内原始键 %r 不符"
                                 % (entry[1], node["key"], entry[4]))
        return tuple(list(entry) + [node])
    return entry


def resolve_unit_anchors(
    contract: Optional[Dict[str, Any]],
    units: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """按门控 ⑪ **同源**判据把每条单元记录解析到契约节点（供修复类工具复用）。

    → 与 ``units`` 等长的 dict 列表，字段：
      ``index`` 记录下标、``key`` 记录原始键、``type`` 记录类型、
      ``node`` 命中的契约节点 dict（``key/nk/type/name/page``）或 ``None``、
      ``order`` 契约登记前序、``page`` 原书页码、``dash`` 是否章末连字符习题键、
      ``skip`` 非空 = 该记录本身不参与页码单调判定（目前只有 ``chapter``）。

    与 :func:`check_unit_order` 的差别**只有一点**：这里连 dash 习题也解析（判据要的是
    「这条内容在契约里的位置」，豁免的是页码倒退而非锚点本身），``type=chapter`` 记为
    ``skip`` 供调用方跳过。出现序消费同样按传入顺序进行，故同一清单跑两次结果一致。
    """
    tables = _anchor_tables(contract)
    nodes = iter_unit_nodes(contract)
    consumed: Dict[int, int] = {}
    follow: Dict[str, tuple] = {}
    out: List[Dict[str, Any]] = []
    for i, u in enumerate(units):
        raw_key = u.get("key") if isinstance(u, dict) else None
        rec = {"index": i, "key": raw_key,
               "type": u.get("type") if isinstance(u, dict) else None,
               "node": None, "order": None, "page": None,
               "dash": is_dash_problem(raw_key), "skip": ""}
        if rec["type"] in _SKIP_TYPES:
            rec["skip"] = "chapter"
            out.append(rec)
            continue
        nk = norm_secnum(raw_key)
        anchor = None
        if u.get("continuation") and nk in follow:
            anchor = follow[nk]                # 续接单元复用父锚点，不消费列表
        else:
            anchor = _unit_anchor(raw_key, u, tables, consumed, nodes)
            if anchor:
                follow[nk] = anchor
        if anchor:
            rec["node"] = anchor[5]
            rec["order"] = anchor[1]
            rec["page"] = anchor[0]
        out.append(rec)
    return out


# ---------------------------------------------------------------------------
# 交付 md 自身阅读顺序（缺陷① 根治：清单转绿 ≠ 交付读对）
# ---------------------------------------------------------------------------
#: 唯一化锚点的最小字符数（归一化 = 去全部空白之后）。短于此值的前缀在正文里
#: 极易重复（`**注**`、`---`、图嵌入 `<div …>`），据此决定是否再吃下一行。
_MD_MIN_ANCHOR_CHARS = 12
#: 一个单元最多吃掉多少行来凑唯一；仍不唯一 = 定位失败（跳过，不猜）。
_MD_MAX_ANCHOR_LINES = 14


def norm_text(text: Any) -> str:
    """去掉**全部**空白（含全角空格 / NBSP）——交付文本与单元正文的公共比较空间。

    比较必须在归一化空间里做：交付侧做过 `V-A` 空行整理、`---` 分隔线补齐、
    ``_tidy_separators`` 与 ``clean_cjk``，行切分与单元原文件早已不一致；只剩
    「字符序列」这一层两侧共同可信。单调性只需要相对先后，故偏移取归一化串里的
    下标即可，无需还原成行号。

    ``\\s``（unicode 模式）已含 U+00A0 NBSP 与 U+3000 全角空格，无需再列码位。
    """
    return re.sub(r"\s+", "", str(text or ""))


def _md_line_anchor(lines: List[str], md: str) -> Optional[int]:
    """逐行累加正文前缀，直到该前缀在归一化交付文本里**唯一**出现 → 返回偏移。

    单行锚点会撞车（多个图嵌入单元共用同一行 ``<div style=...>``、多个习题共用
    同一裸 ``> **解**``），取首见位置会把页码很晚的单元排到章首，制造假倒退——
    所以必须唯一化后才可信；吃了 ``_MD_MAX_ANCHOR_LINES`` 行仍不唯一 → ``None``。
    """
    acc = ""
    for ln in lines[:_MD_MAX_ANCHOR_LINES]:
        acc += ln
        if len(acc) < _MD_MIN_ANCHOR_CHARS:
            continue
        if md.count(acc) == 1:
            return md.find(acc)
    return None


def _md_label_anchor(lines: List[str], md: str) -> Optional[int]:
    """兜底定位：交付做过**内容级**修订（同行机械替换、块内加注）的单元，整行前缀
    可能对不上，改用首行的**条头**（``**…**`` 粗体头或 ``#``/``>`` 标题残段）定位。

    只有该条头在交付文本里唯一出现才可用；否则 ``None``（宁可不测，不猜位置）。
    """
    if not lines:
        return None
    first = lines[0]
    m = re.search(r"\*\*[^*]{2,26}\*\*", first)
    cand = m.group(0) if m else (re.sub(r"^>+|^#+", "", first)[:26] or None)
    if not cand or len(cand) < 6 or md.count(cand) != 1:
        return None
    return md.find(cand)


def md_unit_positions(
    bodies: List[List[str]],
    md_text: str,
) -> List[Optional[int]]:
    """每条单元正文在**归一化交付文本**里的偏移（定位不到 = ``None``）。

    ``bodies``：与单元等长的「非空归一化正文行」列表（首行标记注释须已剥掉），
    由调用方读取单元文件给出——本函数只做纯文本定位，不碰磁盘。
    """
    md = norm_text(md_text)
    out: List[Optional[int]] = []
    for lines in bodies:
        if not lines or not md:
            out.append(None)
            continue
        pos = _md_line_anchor(lines, md)
        if pos is None:
            # 🔴 必须是 `is None`，不能写 `or`：章首单元的合法偏移就是 0，
            # 用真值判断会把「定位在文本最开头」当成定位失败丢掉，而章首那块往往
            # 正是唯一能证明倒退的参照 → 整章零问题假绿（两条负向测试互为变异对照）。
            pos = _md_label_anchor(lines, md)
        out.append(pos)
    return out


def check_delivered_order(
    contract: Optional[Dict[str, Any]],
    units: List[Dict[str, Any]],
    positions: List[Optional[int]],
) -> List[str]:
    """断言**交付 md 文本里实际读到的**单元次序与原书**页码**单调不减。

    与 :func:`check_unit_order` 的分工，就是缺陷①的本体：那边的被测顺序是**源
    manifest 的 ``units`` 数组**，隐含「``merge_units`` 之后交付 md 不再被改」这一假设；
    而收官书的交付侧普遍做过内容级修订（整块搬移 / 单元换文件 / 按节拆文件后按节号
    重排），该假设有实证反例（2026-10-23 茆诗松《概率论与数理统计教程》：门控 ⑪ 与 U 层
    全绿的同一章，交付侧顺序是靠**镜像交付 md** 修好的，两道闸对交付文本的实际次序
    完全不可见）。本函数把被测顺序换成**交付 md 自身**：每条单元的身份（契约节点、
    页码、前序）仍按 manifest 顺序解析（``continuation`` / 出现序消费语义不变），
    只有**先后**改成「该单元正文在交付文本里的偏移」。

    ``positions``：:func:`md_unit_positions` 的产出（与 ``units`` 等长，``None`` =
    定位不到 → 跳过，与判据 5/6 同口径 = 宁可不测不误报）。

    🔴 **口径只到页码，不到契约前序**（``by_preorder=False``，理由与实测数字见
    :func:`_monotonic_problems`）：同页之内的先后，印面证据只剩「同一页」这一条，
    而契约 ``sub_sec`` 的列表序在交付侧不是可信真值（实测 6 处「前序倒退」里 4 处是
    节习题块登记成父节第一个子节点的已知契约缺陷，交付侧才对）。所以本判据只报
    **跨页**错位 = 有印面页码证据的那种；同页顺序差异要修的是**契约登记**，
    归 ``check_contract_anchors`` 与各节内序标闸（B 层）管。

    🔴 **``[]`` 不是「通过」的同义词**：定位不到就跳过，所以整章零覆盖也会返回空列表。
    调用方必须把「已定位 / 应定位」覆盖率与问题一起呈现（见 U 层 ``md_order_stats``），
    否则这道闸的绿是假的。

    身份 / 豁免 / 锚点消费与清单侧**同一段代码**（:func:`iter_judged_units`）：章头跳过、
    章末 dash 习题按 ``ntype``→同键类型集 的旧豁免、锚点缺失跳过、继承导语容器跳过
    （判据 7）。交付侧只把「先后」换成正文在交付文本里的偏移，别的什么都不改——
    普查里那 8 条假阳（:func:`iter_judged_units` 文档记了 anatomy）正是「豁免重写第二遍」
    的代价。

    🔴 一条命中 = **「交付文本次序」与「契约页码次序」矛盾**，不等于「交付错了」。
    2026-10-23 全语料普查（58 本 / 892 个 (章,语种) 组 / 49075 条应定位单元，定位率
    99.04%）在豁免口径合流后剩 12 条，逐条印面裁决，两类都是**账错、交付对**：
      * Weibel《An Introduction to Homological Algebra》ch10（6 条，cn+en 各 3）：印面
        p397 那行是 ``Proposition 10.4.1``，与同号 ``Exercise 10.4.1`` **撞键**；节末习题
        块在交付里正确地排在 Example 10.4.9（p401）之后（它的内容引用引理 10.4.6），
        而 manifest 仍把习题记录留在条目中间 = 清单陈旧。
      * Underactuated Robotics 附录 C（6 条）：印面 ``C.1 OPTIMIZATION SOFTWARE`` 在
        **p323**、``C.2 GENERAL CONCEPTS`` 在 p324；交付（C.1 先）对，契约页码
        （C.1=p325 / C.2=p324）与 manifest 次序（C.2 先）都错。
    两类都不该动交付，要动的是账（契约页码 / 清单次序）。所以本判据先以**非阻断
    WARN** 出厂，且每条自带「先按印面定序」的出口指令；升阻断的前提是这两本书的账
    回写完毕（见 ``verify/unit_order/unit_order.md`` 的出口条件）。
    """
    rows = []
    for i, label, key, page, order in iter_judged_units(contract, units):
        if i >= len(positions) or positions[i] is None:
            continue
        rows.append((positions[i], label, key, page, order))
    rows.sort(key=lambda t: t[0])       # 稳定排序：偏移相同者保持 manifest 先后
    return _monotonic_problems(
        [(label, key, page, order) for _pos, label, key, page, order in rows],
        where_page="交付 md 阅读顺序倒退——交付文本与契约页码必有一处不合印面，"
                   "先按印面定序，再决定搬交付块还是回写契约/清单",
        by_preorder=False)

