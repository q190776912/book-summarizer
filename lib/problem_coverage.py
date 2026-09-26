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

假阴提示：若原书的题面被写成 ``Problem 1. …`` 之类的**行内**段落而非列表，单元侧数不到
即误报——按本书体例（题面一律列表项）不存在此形态；如遇到，改的是单元的排版，不是本闸。
"""
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

__all__ = ["contract_run_lengths", "unit_run_length", "coverage_problems",
           "page_problem_floors", "page_floor_problems"]

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
_AFTER_NUM = r"(?:[ \t]+\S|[^\s\d.\-)\]])"
_NUM_LINE_RE = re.compile(
    r"^[ \t]*(?:>[ \t]*)*(?:\*\*)?[ \t]*\(?(?P<n>\d{1,2})[ \t]*(?:\*\*)?[.)\]]"
    + _AFTER_NUM)

_CONTAINER_TYPES = ("chapter", "section", "subsection")

# 抽取期 OCR 里节末习题块的标志（只用于**页侧**对账，见 page_problem_floors）
_PAGE_HEAD_RE = re.compile(r"^\s*(?:Problems?|Problem\s*Set\s*[\d.]+)\s*$", re.I)
_PAGE_NUM_RE = re.compile(r"^\s*\(?(\d{1,2})[.)\]]" + _AFTER_NUM)
# 页眉/节标题：`9.11 Some Title`。**同节号 = 页眉重复，不算「本节结束」**（Kreyszig 实测：
# 习题跨页时每一页页顶都印当前节号，若一律当结束，下限会停在第一页 = 严重偏低）。
_PAGE_SEC_HEAD_RE = re.compile(r"^\s*(\d{1,2}\.\d{1,2})\s+[A-Z]")


def _num(text: Any) -> Optional[int]:
    if not isinstance(text, str):
        return None
    m = _NUM_LINE_RE.match(text)
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


def contract_run_lengths(root: Dict[str, Any]) -> List[Tuple[str, int, Tuple[str, ...]]]:
    """→ [(节键, 契约侧最长编号链, 该节子树的键集合)]（只含链长 ≥ 阈值的节）。"""
    out = []
    for s in _section_nodes(root):
        if _skip_consolidated(s):
            continue
        n = longest_run_from_one([x for x in (_num(t) for t in _leaf_texts(s)) if x])
        if n:
            out.append((str(s.get("key") or ""), n, _descendant_keys(s)))
    return out


def unit_run_length(texts: Iterable[str]) -> int:
    """把该节的单元正文（按阅读顺序）拼起来求单元侧最长编号链。"""
    nums = []
    for t in texts:
        for line in t.splitlines():
            n = _num(line)
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

