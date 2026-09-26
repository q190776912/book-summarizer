"""lib/problem_coverage.py — 契约「连续编号内容块」在总结单元里的覆盖对账（纯函数）。

背景（2026-09-26 Kreyszig 实测）
------------------------------
抽取期把**节末「Problems」题面灌进了前一编号项（或证明）节点的子树**，只有部分节生成
了 ``exercise`` 节点。于是：

* 拆分后**没有**习题单元 → 写手看不到「该写 12 道题」这件事；
* ``gate_units`` 的既有闸门全部看不见：tag / 图片 / 正文非空 / 反向覆盖对账都按
  **节点**比较，题面挂在别的节点子树里照样绿灯。

结果：Kreyszig 11 章 572 单元**门控全绿**，却有约 51 节 / 500+ 道习题整块没进笔记
（ch2、ch3 写全了，其余章普遍只剩正文）。

判据（不依赖任何标签措辞，源语与译文通用）
----------------------------------------
以「**同一节内连续编号的列表项**」为对账单位：

1. 契约侧：按节收集其子树全部文本块，取行首编号 ``1. / 1) / (1)``，求**从 1 起连续**
   的最长链长 ``n_contract``；
2. 单元侧：同节全部单元（按 manifest 顺序拼接，允许题面跨单元续写）用同一判据求
   ``n_unit``；
3. ``n_unit < n_contract`` → 该节有编号内容被整块漏写，报缺失题数；
4. ``n_contract < min_run``（默认 3）跳过——个别 ``1. 2.`` 是正文里的普通列举，
   不足以断定漏了东西；
5. 契约里被标 ``consolidated=true`` 的章末成堆习题是流水线**认可的省略**，跳过。

两侧用**同一**判据，故「正文里本就有的 1./2./3. 列举」不会造成假阳（单元里同样数得到）；
契约侧 OCR 断号只会让 ``n_contract`` 偏小 = 偏保守（宁可漏报不误报）。
唯一按侧取的细节：**行末收尾括号**——单元侧（我们写的 md）额外认全角 `（1）`（中文排版
惯例，微分遍历论 ch2），契约侧仍只认半角（OCR 的全角收尾多是被切成行首的散文碎片，
计入会凭空造链，微分遍历论 ch4 D16 实测）。放宽只作用于单元链 = 只可能少报不会多报。

假阴提示：若原书的题面被写成 ``Problem 1. …`` 之类的**行内**段落而非列表，单元侧数不到
即误报——按本书体例（题面一律列表项）不存在此形态；如遇到，改的是单元的排版，不是本闸。
"""
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

__all__ = ["contract_run_lengths", "unit_run_length", "coverage_problems",
           "consolidated_cut", "is_consolidated_head",
           "page_problem_floors", "page_floor_problems",
           "exercise_item_numbers", "exercise_runs", "exercise_run_gaps",
           "chapter_exercise_problems", "exercise_statements",
           "duplicate_exercise_statement_problems",
           "EXER_SET_HEAD_RE", "EXER_ITEM_BARE_RE", "EXER_ITEM_LABEL_RE"]

# 行首编号项：`1. ` / `12) ` / `(1) `，允许 blockquote 前缀 `>` 与粗体 `**1.**`
#
# 🔴 「编号之后必须有内容」的判据分两支（`_AFTER_NUM`）：
#   * `[ \t]+\S` —— 正常排版 `1. 证明…`；
#   * 紧跟一个内容字符 —— **中文括注/题干直接粘在编号后**（`1.（提示）…`、
#     `2)证明…`）以及 OCR 粘连的英文（`1.The`）。此前只认第一支，于是这类行
#     整行不被计数：契约侧题号粘连时「该节应有 12 题」的下限被压低，页侧对账
#     跟着偏低，整块漏写的习题反而通过（Kreyszig 补齐期实测）。
#   第二支**必须排除数字与 `.` `-` `)`**：否则 `**1.5-4 波利亚定理**` 这类
#   行首的更深层编号会被当成本节第 1 项，把对账彻底污染。
_AFTER_NUM = r"(?:[ \t]+\S|[^\s\d.\-)\])）])"


def _build_num_re(open_p: str, close: str) -> "re.Pattern":
    """`open_p` / `close` = 前后括号字符类；骨架同一，按侧选形态（见下）。"""
    return re.compile(
        r"^[ \t]*(?:>[ \t]*)*(?:\*\*)?[ \t]*" + open_p + r"[ \t]*(?P<n>\d{1,2})"
        r"[ \t]*(?:\*\*)?" + close + _AFTER_NUM)


# 契约侧（OCR）与页侧：与历史判据逐字一致（只认半角）。全角收尾在 OCR 里多是
# **行首截断的散文碎片**——微分遍历论 ch4 D16 的 `(4）成立．由第一步` 其实是正文里
# 的条件引用「（3）（4）成立」被切成行首；一旦计入就凭空造出 1..4 链，把写全了
# (1)–(3) 的节判成「缺 1 项」。契约侧链偏短 = 少报 = 保守，正是本闸声明的设计取向。
_NUM_LINE_RE = _build_num_re(r"\(?", r"[.)\]]")
# 单元侧（我们写的 md）：中文排版惯例写 `（1）`（微分遍历论 ch2 定理2.1.9 的
# (1)–(4) 条）。只认半角时单元侧数不到 → 「契约 1..4 / 单元没有任何编号项」的假
# 「整块漏写」FAIL，闸 ⑫ 误杀全绿章节；放宽只让单元链变长 = 只可能少报不会多报。
_NUM_LINE_RE_UNIT = _build_num_re(r"[(（]?", r"[.)\]）]")

_CONTAINER_TYPES = ("chapter", "section", "subsection")

# 抽取期 OCR 里节末习题块的标志（只用于**页侧**对账，见 page_problem_floors）
_PAGE_HEAD_RE = re.compile(r"^\s*(?:Problems?|Problem\s*Set\s*[\d.]+)\s*$", re.I)
_PAGE_NUM_RE = re.compile(r"^\s*\(?(\d{1,2})[.)\]]" + _AFTER_NUM)
# 页眉/节标题：`9.11 Some Title`。**同节号 = 页眉重复，不算「本节结束」**（Kreyszig 实测：
# 习题跨页时每一页页顶都印当前节号，若一律当结束，下限会停在第一页 = 严重偏低）。
_PAGE_SEC_HEAD_RE = re.compile(r"^\s*(\d{1,2}\.\d{1,2})\s+[A-Z]")


def _num(text: Any, rex: "re.Pattern" = None) -> Optional[int]:
    if not isinstance(text, str):
        return None
    m = (rex or _NUM_LINE_RE).match(text)
    if not m:
        return None
    n = int(m.group("n"))
    return n if 1 <= n <= 99 else None


def longest_run_from_one(nums: Iterable[int]) -> int:
    """序列中「从 1 起、步长 1」连续链的**最长**长度（可在中途重新开始计数）。

    🔴 必须取最长而非「第一条」：一节里常既有正文列举 ``1. 2. 3.`` 又有节末习题
    ``1. … 12.``；贪心只走第一条链会在 3 处停住，之后习题的 1 再不能被接受，
    于是「整块漏写的 12 道题」被误判成「3 项都在」。
    """
    best = want = 0
    for n in nums:
        if n == want + 1:
            want += 1
        elif n == 1:
            want = 1
        else:
            want = 0
        if want > best:
            best = want
    return best


def _leaf_texts(node: Dict[str, Any]) -> List[Any]:
    out: List[Any] = []

    def walk(n):
        for b in n.get("sub_sec") or []:
            if not isinstance(b, dict):
                continue
            if "type" in b:
                walk(b)
            else:
                out.append(b.get("text"))
    walk(node)
    return out


def _section_nodes(root: Dict[str, Any]) -> List[Dict[str, Any]]:
    """章下所有**节级**容器（含节内再分节），习题按节对账。"""
    out = []

    def walk(n):
        for c in n.get("sub_sec") or []:
            if not isinstance(c, dict):
                continue
            if c.get("type") in ("section", "subsection"):
                out.append(c)
                walk(c)
    walk(root)
    return out


def _descendant_keys(node: Dict[str, Any]) -> Tuple[str, ...]:
    keys = []
    if node.get("key") is not None:
        keys.append(str(node["key"]))

    def walk(n):
        for c in n.get("sub_sec") or []:
            if isinstance(c, dict) and "type" in c:
                if c.get("key") is not None:
                    keys.append(str(c["key"]))
                walk(c)
    walk(node)
    return tuple(keys)


def _skip_consolidated(node: Dict[str, Any]) -> bool:
    """该节的习题是否契约明示省略（章末成堆 ``consolidated=true``）。"""
    hit = [False]

    def walk(n):
        for c in n.get("sub_sec") or []:
            if not isinstance(c, dict) or "type" not in c:
                continue
            if c.get("type") in ("exercise", "problem") and c.get("consolidated"):
                hit[0] = True
            walk(c)
    walk(node)
    return hit[0]


# 块首允许 OCR 的项目符号残渣（Fraleigh 印的是「■ EXERCISES 23」，■ 被 OCR 粘进行首）
_OCR_BULLET = r"[■□•·◦○●▪▸\-*›»]*"
# 🔴 OCR 还会把**题号**认成字母：`EXERCISES 0` → `EXERCISESO`、`In Exercises 1 through 4`
# → `InExercisesI through4`（Fraleigh ch0 §0.20 实测：块标题与引言行双双损坏 → 本闸看不见
# 块首，把题号 1..4 当成「正文该写却漏写」的编号内容，逼写手抄整块题面）。
# 只放行**粘连**形态（数字位置换成 O/o/I/l/L）；带空格的散文（``Exercises in this
# section``）里 "in" 前有空格，仍不匹配。
_OCR_DIGIT = r"0-9OoIlL"
_CONSOLIDATED_HEAD_RE = re.compile(
    r"^\s*(?:>\s*)?" + _OCR_BULLET + r"\s*(?:EXERCISES?|Exercises?|习题|练习)"
    r"\s*(?:for\s*)?(?:Section\s*)?[" + _OCR_DIGIT + r".。]*\s*$"
    r"|^\s*(?:>\s*)?" + _OCR_BULLET + r"\s*Section\s*\d+\s+Exercises?\s*$"
    # 块首**引言行**（题号紧跟其后）：OCR 常把它粘成 `InExercises21through6,determine…`
    # 或 `■EXERCISES23`。要求「Exercises」后**立刻**出现编号，散文里的裸词
    # （``Exercises show that…`` / ``see Exercises 22`` 不在行首）不会被误判。
    # 行首即可切：习题块恒在一节末尾，早切只会压低契约侧下限 = 少报 = 保守。
    r"|^\s*(?:>\s*)?" + _OCR_BULLET + r"\s*(?:(?:In|For|The|Consider|See)\s*)?"
    r"(?:EXERCISES?|Exercises?|习题|练习|Problems?)(?:\s*\d|[" + _OCR_DIGIT + r"])",
    re.IGNORECASE)


def is_consolidated_head(text: Any) -> bool:
    """单块/单行是否「集中习题块」的块首（标题行或引言行）。

    与 `consolidated_cut` 同一判据，暴露给配置探测侧复用：`make_config` 的
    `_detect_exercise_counter` 要按页标记习题区，而 OCR 常把 Fraleigh 这类书的
    块标题粘成 `EXERCISESO` / `InExercises21through6,…`，词边界正则看不见它，
    于是习题页被当成正文页、题号 1..N 被当成「保留习题计数器」→ 配置里凭空多出
    一个 type:1 组，verify B 层随即为每个被省略的题号报「缺号」。
    """
    return isinstance(text, str) and bool(_CONSOLIDATED_HEAD_RE.match(text))


def consolidated_cut(texts: List[Any]) -> Optional[int]:
    """契约文本块里「章末集中习题块」起始块的下标（无则 None）。

    writing-rules V-I：带专用标题（``Exercises`` / ``EXERCISES 20`` / ``Section 2
    Exercises`` / ``习题``）的习题块属**整块省略**形态，既不写也不校验。抽取期把
    这种块灌进了本节 description/section 的文本流（Fraleigh 全书如此），于是本闸的
    契约侧下限把题号 ``1..N`` 当成了「应补全的编号内容」，逼写手把受版权保护的整节
    习题逐题抄进笔记（实测：删掉抄来的习题后，ch20/21/23/25/35 各报一条「缺 N 项」）。
    判据按体例而不是按措辞：①**整行只有块标题**（可带题号）；②行首**引言行**，即
    ``Exercises``/``习题`` 之后**紧跟数字**（``In Exercises 1 through 9, …``、
    OCR 粘连的 ``InExercises21through6,determine…``、``■EXERCISES23``）。
    散文引用不算：句中/行中的 ``see Exercises 22 through 25`` 不在行首，
    ``Exercises show that…``（数字不紧邻）也不匹配。
    """
    for i, t in enumerate(texts):
        if isinstance(t, str) and _CONSOLIDATED_HEAD_RE.match(t):
            return i
    return None


def contract_run_lengths(root: Dict[str, Any]) -> List[Tuple[str, int, Tuple[str, ...]]]:
    """→ [(节键, 契约侧最长编号链, 该节子树的键集合)]（只含链长 ≥ 阈值的节）。"""
    out = []
    for s in _section_nodes(root):
        if _skip_consolidated(s):
            continue
        texts = _leaf_texts(s)
        cut = consolidated_cut(texts)
        if cut is not None:
            texts = texts[:cut]
        n = longest_run_from_one([x for x in (_num(t) for t in texts) if x])
        if n:
            out.append((str(s.get("key") or ""), n, _descendant_keys(s)))
    return out


def unit_run_length(texts: Iterable[str]) -> int:
    """把该节的单元正文（按阅读顺序）拼起来求单元侧最长编号链。

    单元侧用 ``_NUM_LINE_RE_UNIT``：我们写的 md 按中文排版惯例写 `（1）`，
    与契约侧 OCR 的 `(1)` 是同一编号项的不同排版形态。
    """
    nums = []
    for t in texts:
        for line in t.splitlines():
            n = _num(line, _NUM_LINE_RE_UNIT)
            if n:
                nums.append(n)
    return longest_run_from_one(nums)


def coverage_problems(root: Optional[Dict[str, Any]], units: List[Dict[str, Any]],
                      read_body, min_run: int = 3) -> List[str]:
    """节级编号内容覆盖对账 → 问题列表（空 = 通过）。

    ``read_body(unit)`` 返回该单元的正文（去掉首行 DONE 注释后的 md）。
    """
    if not root:
        return []
    problems = []
    for sec_key, n_contract, keys in contract_run_lengths(root):
        if n_contract < min_run:
            continue
        keyset = set(keys)
        bodies = [read_body(u) for u in units if str(u.get("key")) in keyset]
        n_unit = unit_run_length(b for b in bodies if b)
        if n_unit < n_contract:
            problems.append(
                "节 %s 的编号内容有缺失：契约里编号 %s 连成一条（题面/条目通常整块被"
                "抽进本章节点子树），单元里只写到 %s——缺 %s 项，须按契约把剩余各项补全"
                "（习题写成 ``**Problem Set %s**`` + 列表项，题面完整，不得以「见原书」搪塞）"
                % (sec_key, "1..%d" % n_contract, "%d" % n_unit if n_unit else "没有任何编号项",
                   n_contract - n_unit, sec_key))
    return problems


# ---------------------------------------------------------------------------
# 页侧下限（page floor）
# ---------------------------------------------------------------------------
# 为什么还需要它：``coverage_problems`` 拿**契约**当下限，可契约本身就会瞎——抽取期
# 有的节末「Problems」整页根本没进契约（跨页题块被丢/被灌进别节子树），于是
# 「契约 4 题、印刷 10 题、单元只写了 5 题」这种真缺口，契约侧完全看不出来，门控
# 照样绿灯。这里直接从 ``_extract/page_NNN.json``（该节的页窗内）读题号，取
# 「Problems 标题之后出现过的最大题号」为**下限**。
#
# 只作下限、且刻意保守：
#   * 必须在该节页窗内**看见** "Problems"/"Problem Set N.M" 标题块才成立；
#   * 一遇到下一条节标题（``9.9 Section Title``）立即停止，避免把下一节的正文列举算进来；
#   * 上限 30 挡掉 OCR 噪声式的大数；不足 ``min_floor`` 的忽略。
# 因此它**永远不会高于**印刷实际题数（题号在页面上就是 1..N），只会因 OCR 丢块偏低。


def _section_windows(root: Dict[str, Any],
                     chapter_span: Tuple[int, int]) -> List[Tuple[str, int, int]]:
    """[(节键, 页窗起, 页窗止)]：窗 = 本节 page_start 到**下一条节标题**之前。"""
    secs = []
    for c in root.get("sub_sec") or []:
        if isinstance(c, dict) and c.get("type") in ("section", "subsection"):
            ps, pe = c.get("page_start"), c.get("page_end")
            if ps is None:
                continue
            secs.append((str(c.get("key") or ""), int(ps),
                         int(pe) if pe else int(ps)))
    starts = sorted({p for _, p, _ in secs})
    out = []
    for key, ps, pe in secs:
        nxt = [s for s in starts if s > ps]
        # 页窗**含**下一条节的起始页：一套题常结束于下节开始的那一页（题号排在页上半部），
        # 越界风险由扫描时「遇到**别的**节号标题或下一个 Problems 即停」兜住。
        hi = nxt[0] if nxt else max(pe, chapter_span[1])
        out.append((key, ps, max(hi, ps)))
    return out


def page_problem_floors(root: Optional[Dict[str, Any]], page_loader,
                        chapter_span: Tuple[int, int],
                        min_floor: int = 3) -> Dict[str, int]:
    """{节键: 页侧题号下限}（下限，检测不到即不出现在结果里）。

    ``page_loader(page)`` → 该页文本块内容的**阅读序**字符串列表（或 None）。
    """
    floors: Dict[str, int] = {}
    if not root:
        return floors
    for key, lo, hi in _section_windows(root, chapter_span):
        m_cur = re.match(r"\d{1,2}\.\d{1,2}", key)
        cur_no = m_cur.group(0) if m_cur else key
        seen_head = False
        n = 0
        abandoned = False
        for pg in range(lo, hi + 1):
            blocks = page_loader(pg)
            if not blocks:
                continue
            for t in blocks:
                s = (t or "").strip()
                if not s:
                    continue
                m = _PAGE_SEC_HEAD_RE.match(s)
                if not seen_head:
                    # 🔴 还没见到本节的「Problems」标题就先冒出**别的**节号 → 本节页窗里
                    # 根本没有自己的题集（该标题属于下一条节）。Kreyszig 实测假阳：3.6 无
                    # 独立题集，其页窗尾巴（=3.7 起始页）上印着「3.7 …/Problems/1. …10.」，
                    # 不 abandon 就会把 3.7 的 10 道题算成 3.6 的下限。
                    if m and m.group(1) != cur_no:
                        abandoned = True
                        break
                    if _PAGE_HEAD_RE.match(s):
                        seen_head = True
                    continue
                if m and m.group(1) != cur_no:     # 进入**下一条**节 → 本套题结束
                    seen_head = False
                    break
                if _PAGE_HEAD_RE.match(s):         # 下一套题的标题 → 本套结束
                    seen_head = False
                    break
                mm = _PAGE_NUM_RE.match(s)
                if mm:
                    v = int(mm.group(1))
                    if v <= 30:
                        n = max(n, v)
            if abandoned:
                break
        if n >= min_floor:
            floors[key] = max(floors.get(key, 0), n)
    return floors


def page_floor_problems(root: Optional[Dict[str, Any]], units: List[Dict[str, Any]],
                        read_body, page_loader, chapter_span: Tuple[int, int],
                        min_floor: int = 3) -> List[str]:
    """页侧下限对账 → 问题列表（空 = 通过）。判据与 ``coverage_problems`` 同侧（单元）。"""
    if not root:
        return []
    floors = page_problem_floors(root, page_loader, chapter_span, min_floor)
    if not floors:
        return []
    problems = []
    for sec_key, n_floor in sorted(floors.items()):
        keys = set()
        for s in _section_nodes(root):
            if str(s.get("key") or "") == sec_key:
                keys = set(_descendant_keys(s))
        if not keys:
            continue
        n_unit = unit_run_length(
            [b for b in (read_body(u) for u in units if str(u.get("key")) in keys) if b])
        if n_unit < n_floor:
            problems.append(
                "节 %s 的习题比**原书页面**少：该节页窗里「Problems」之后出现过题号 %d"
                "（页侧下限，契约可能根本没抽到这批题块），单元里只写到 %s——请把该节页窗"
                "内印刷的 Problem Set %s 逐题抄全（``**Problem Set %s**`` + 顶格 ``1. 2. …`` "
                "列表项），不得只按契约抄、也不得以「见原书」搪塞"
                % (sec_key, n_floor, "%d" % n_unit if n_unit else "没有任何编号项",
                   sec_key, sec_key))
    return problems



# ---------------------------------------------------------------------------
# 习题集题号**连续性**（章级；题号可跨单元续写，故按合并顺序串成全章号流）
# ---------------------------------------------------------------------------
# 与上面的「契约 ↔ 单元覆盖对账」互补：那道闸以**契约**为真值，而抽取器把整节习题
# 灌进一个 desc 节点时契约**没有逐题条目**（Rosen 8e ch6/ch9/ch10 实测），对账只能
# 看到「该节有 1 个内容块」。本闸改以**「原书每节习题集恒为连续编号」**这条体例事实
# 为真值：把全章单元正文按合并顺序串起来，遇习题集标题切段，段内号流必须连续。
#
# 于是「§10.1 习题只写了 1,2,10,11,…,38」（缺 3..9，且这 7 题分散在不同单元）这种
# **单元级看不见**的跨单元洞，会在步骤 5 门控就报出来，而不是等步骤 7 合并后的
# verify B/O 层（那两层按行距 ≤4 分块，长题面/插图把一集撑成多块，HEAD 缺号误报
# 成片、真洞反而埋在一堆噪声里，Rosen 8e ch10 一次 16 条里只有部分是真题）。
#
# 🔴 **适用范围 = 契约登记的习题单元**（manifest ``type == exercise``）。写作规则
# V-I（docs/writing-rules.md）规定「**有专门小标题的集中习题块一律省略**」，是否收录
# 由契约节点的 ``consolidated`` 承载：Rosen 每节末的 ``Exercise Set N.M`` 是集中块，
# 抽取期把题面挂在**相邻 desc/item 节点**子树里（契约无 exercise 条目、未标
# consolidated），因此这些散落题面**不是**「应写而漏写」的欠账——对它们报缺号等于逼
# 写手恢复 V-I 认可的省略内容（Rosen 8e ch10 §10.6 实测：闸把 desc 节点里的一句
# 「**Exercises for Section 10.6**」当成集标题开段，报出两个假洞）。故号流**只由
# exercise 单元开段**（含隐式：exercise 单元没印集标题也算开段），其后紧接的单元即便
# 是 desc/item 也照常接力（一集 68 题分散在 20 个单元里是常态），直到下一个集标题 /
# 下一个 exercise 单元 / 新的 ``##`` 小节边界把号段结算。
EXER_SET_HEAD_RE = re.compile(
    r"\*\*[^*\n]{0,60}?(?:exercises?\b|problems?\b|习题|练习)(?!\s*\d)", re.I)
_SECTION_HEAD_RE = re.compile(r"^\s*#{1,3}\s", re.M)
# 题号两体：① 裸号 ``1.`` / ``2)`` / ``**12.**``；② 标签号 ``**Exercise 3.**`` /
# ``**习题 17**``（Rosen 8e ch6 单元用后者，只认①会让整块缺号隐身）。
# 🔴 两体都吃**区间号** ``Exercises 2-4.`` / ``12-15)``：原书把同型的几道题合并成一条
# 题干（Rosen 8e ch10 §10.6 印「Exercises 2–4. Find the length of a shortest path…」），
# 区间**覆盖**的每一号都算写了。只认首号会让 3、4 被报成缺号（实测假阳）。
_EXER_RANGE = r"(\d{1,3})(?:\s*[.\u2013\u2014-]\s*(\d{1,3}))?"
EXER_ITEM_BARE_RE = re.compile(
    r"^\s*(?:>\s*)?\*{0,2}" + _EXER_RANGE + r"[.)]\*{0,2}\s", re.M)
EXER_ITEM_LABEL_RE = re.compile(
    r"^\s*(?:>\s*)?\*{1,2}\s*(?:exercises?|problems?|习题|练习|Exercises?)\s*"
    + _EXER_RANGE + r"\b", re.M | re.I)
_RANGE_SPAN_MAX = 30      # 区间跨度上限：超过它多半是两个不相干数字被粘住


def exercise_item_numbers(text: str) -> List[int]:
    """按出现顺序摊平一段文本里的习题题号（两体各匹配一次，同一位置不重复计数）。

    区间号 ``2-4`` 摊成 ``2, 3, 4``（顺序与首号一致，不影响切段判定）。
    """
    got = []
    for rx in (EXER_ITEM_BARE_RE, EXER_ITEM_LABEL_RE):
        for m in rx.finditer(text):
            lo = int(m.group(1))
            hi = int(m.group(2)) if m.group(2) else lo
            vals = [lo]
            if hi > lo and hi - lo <= _RANGE_SPAN_MAX:
                vals = list(range(lo, hi + 1))
            got.append((m.start(), vals))
    seen: set = set()
    out: List[int] = []
    for pos, vals in sorted(got):
        if pos in seen:
            continue
        seen.add(pos)
        out.extend(vals)
    return out


def exercise_runs(nums: Iterable[int]) -> List[List[int]]:
    """题号流切成**递增号段**：号回退 = 新习题集 restart → 切段；相邻重号折叠。"""
    runs: List[List[int]] = []
    cur: List[int] = []
    for v in nums:
        if not cur:
            cur = [v]
        elif v == cur[-1]:
            continue
        elif v < cur[-1]:
            runs.append(cur)
            cur = [v]
        else:
            cur.append(v)
    if cur:
        runs.append(cur)
    return runs


def exercise_run_gaps(nums: Iterable[int], min_run: int = 3
                      ) -> List[Tuple[int, int, List[int]]]:
    """→ [(段首号, 段末号, 段内缺号列表)]；长度 < ``min_run`` 的短段不判。

    短段（一两条枚举）在原书正文/证明里极常见，不构成「习题集」，判缺号必误伤。
    """
    out = []
    for run in exercise_runs(nums):
        if len(run) < min_run:
            continue
        have = set(run)
        missing = [k for k in range(run[0], run[-1] + 1) if k not in have]
        if missing:
            out.append((run[0], run[-1], missing))
    return out


def chapter_exercise_problems(ordered_units, min_run: int = 3) -> List[str]:
    """章级习题集题号连续闸。``ordered_units`` = **按合并顺序**的
    ``[(单元文件名, 正文, 是否契约登记的习题单元)]``（第三项可省略 = 否）。

    返回问题字符串列表（空 = 通过）。每条报：习题集标题、缺号数、号段、缺失题号 +
    **洞之后第一题所在的单元文件**（补写就打开那个文件，把缺的各题插在它前面）。

    判据边界（四条都是为「少误伤」设计）：
    ① 号流**只由习题单元开段**（manifest ``type == exercise``，即契约在账的习题条目；
      该单元没印集标题时也开，段名退回文件名）——散文/条目单元里的 ``1. 2. 3.`` 列举与
      它们顺带抄到的集中习题块（V-I 认可省略）都不开段；
    ② 段一旦开开，后续单元（含 desc/item 接力单元）的题号继续累积，直到下一个集标题 /
      下一个习题单元 / 新的 ``##``–``###`` 小节边界结算——一集 68 题分散在 20 个单元里
      是 Rosen 这类书的常态，这正是本闸相对单元级判据 20 的**唯一增量**；
    ③ 号回退也切段（章末「Supplementary Exercises」等重新起号不算前一集缺号）；
    ④ 短段（< ``min_run``）不判。
    合起来仍拦得住「同一集内部跳号」——那正是写手只抄代表性题目的形态。
    """
    problems: List[str] = []
    head = ""
    seg: List[Tuple[int, str]] = []
    opened = False          # 是否已进入某个（契约在账的）习题集

    def flush():
        if not seg:
            return
        for lo, hi, missing in exercise_run_gaps([n for n, _ in seg], min_run):
            first_after = missing[0]
            nxt = min((n for n, _ in seg if n > first_after), default=None)
            where = next((f for n, f in seg if n == nxt), "?")
            problems.append(
                "习题集「%s」题号缺号 %d 处（号段 %d..%d，缺 %s）——原书该节习题集是"
                "连续编号，跳号即题面被漏写；须按 page_*.json 把缺的各题题面补全"
                "（插在单元 %s 之前），禁止用措辞搪塞，也禁止删短已有各题来「凑连续」" % (
                    head, len(missing), lo, hi,
                    ", ".join(str(m) for m in missing[:12])
                    + ("…" if len(missing) > 12 else ""), where))
        del seg[:]

    def take(text, fname):
        if opened:
            for v in exercise_item_numbers(text):
                seg.append((v, fname))

    def open_at(title):
        nonlocal opened, head
        flush()
        head, opened = title, True

    for item in ordered_units:
        fname, body = item[0], item[1]
        is_exercise = bool(item[2]) if len(item) > 2 else False
        if opened and _SECTION_HEAD_RE.search(body):
            flush()                      # 进入新的小节 = 上一集到此为止
            opened = False
        if not is_exercise:
            # 非习题单元：只可能是在**接力**上一集（V-I 认可的集中块散抄不开新段）
            take(body, fname)
            continue
        cuts = [m.start() for m in EXER_SET_HEAD_RE.finditer(body)]
        if not cuts:
            open_at("（%s：单元内无习题集标题）" % fname)
            take(body, fname)
            continue
        bounds = [0] + cuts + [len(body)]
        for k in range(1, len(bounds) - 1):
            take(body[bounds[k - 1]:bounds[k]], fname)   # 标题之前 = 上一集续段
            open_at(body[bounds[k]:bounds[k] + 70].splitlines()[0].strip().strip("*"))
        take(body[bounds[-2]:], fname)
    flush()
    return problems


# ── 章级「同一题面重复出现在两个单元」闸 ────────────────────────────────
# 🔴 题目标题行的两种印刷形态：``**Exercise 31.** Show that…`` 与裸号 ``31. Show that…``
#    （中文随文「习题 31.」同形）。
_EXER_STMT_HEAD_RE = re.compile(
    r"^ {0,3}(?:>\s*)?\*{0,2}\s*(?:Exercise[s]?|习题|练习)\s*(\d{1,3})\s*[.)]"
    r"\s*\*{0,2}\s*(.*)$"
    r"|^ {0,3}(?:>\s*)?\*{0,2}(\d{1,3})\s*[.)]\s*\*{0,2}\s*(.*)$",
    re.I)
_DUP_MIN_FP = 60           # 指纹短到这个数以下不配对（引用句 / 半句必然重合）
_EXER_MAX_NUM = 200        # 题号上限：超过它多半是年份 / 页码被当成序号


def _statement_fingerprint(text: str) -> str:
    """题面 → 指纹：只留字母数字与汉字。

    必须是**归一化**的：同一道题在两个单元里 LaTeX 写法可以不同
    （``$cn^d$`` vs ``$c n ^ { d }$``、``$f(n)$`` vs ``$f ( n )$``），空格 / 花括号 /
    上下标记号差异不能让它逃过重复检测（Rosen 8e ch8 §8.4 单元照抄 §8.3 的
    29–37 题，正是靠这条指纹才抓出来——题号连续闸 ⑮ 看不见，因为它只比号不比文）。
    """
    return re.sub(r"[^0-9a-z一-鿿]", "", text.lower())


def exercise_statements(text: str) -> List[Tuple[int, str, str]]:
    """一段正文 → ``[(题号, 指纹, 起句)]``；题面 = 标题行余下内容 + 其后续连续行。

    指纹长度 < ``_DUP_MIN_FP`` 的行（「Use Exercise 29 to show…」式引用、只有一
    个词的空题干）不参与配对。
    """
    out: List[Tuple[int, str, str]] = []
    lines = text.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        m = _EXER_STMT_HEAD_RE.match(lines[i])
        if not m:
            i += 1
            continue
        num = m.group(1) or m.group(3)
        stem = m.group(2) if m.group(1) else m.group(4)
        n = int(num)
        if n > _EXER_MAX_NUM:
            i += 1
            continue
        parts = [stem]
        j = i + 1
        while j < len(lines) and lines[j].strip() \
                and not _EXER_STMT_HEAD_RE.match(lines[j]):
            parts.append(lines[j])
            j += 1
        fp = _statement_fingerprint(" ".join(parts))
        if len(fp) >= _DUP_MIN_FP:
            out.append((n, fp, " ".join(stem.split())[:46]))
        i = j
    return out


def duplicate_exercise_statement_problems(ordered_units) -> List[str]:
    """章级重复题面闸。``ordered_units`` = 按合并顺序的
    ``[(文件名, 正文, 是否契约登记的习题单元)]``（同 ``chapter_exercise_problems``）。

    返回问题列表（空 = 通过）。判据：**同一道题面出现在两个不同单元**里。

    🔴 为什么必须有这一闸：OCR 的双栏页会把**上一节习题集的尾巴**灌进下一节的习题
    节点（Rosen 8e ch8：§8.4 的习题单元 0069 里是 §8.3 的 29–37 题，号段自身连续，
    ⑮ 与单元级判据 20 都判 PASS，而 §8.4 自己印 1–60 的题面一条没写）。号流对账
    只看「写出来的号连不连」，**看不出写的是不是本题**——文本指纹是唯一能揭穿的判据。
    只对契约登记的习题单元取指纹：散文单元里的合法重复表述（同一句引文出现在两处
    正文）不得被当成重复题面。
    """
    seen: Dict[str, Tuple[str, int]] = {}
    # (先出现单元, 后出现单元) -> (先出现题号, 后出现题号, 起句, 重复条数)
    pairs: Dict[Tuple[str, str], List[int]] = {}
    for item in ordered_units:
        fname, body = item[0], item[1]
        is_exercise = bool(item[2]) if len(item) > 2 else False
        if not is_exercise:
            continue
        for n, fp, stem in exercise_statements(body):
            prev = seen.get(fp)
            if prev is None:
                seen[fp] = (fname, n)
            elif prev[0] != fname:
                key = (prev[0], fname)
                rec = pairs.setdefault(key, [prev[1], n, stem, 0])
                rec[3] += 1
    return [
        "题面重复：%s 与 %s 有 %d 道题**逐字相同**（首例：%s 的第 %d 题 == %s 的第 %d 题，"
        "起句：%s）——OCR 把相邻小节习题集的条目灌进了本单元；须按印刷页把本题归回它"
        "真正的习题集，并按书源补全本单元欠的各题，禁止用「凑连续」的删改掩盖"
        "（题号对账看不见串文，只有文本指纹能拦）" % (
            a, b, cnt, a, an, b, bn, stem)
        for (a, b), (an, bn, stem, cnt) in sorted(pairs.items())
    ]
