# -*- coding: utf-8 -*-
"""extract_items_cn_single.py — CN 单级编号项抽取（ORDINAL_SINGLE + language=cn）。

规则5（config_setting）增量扩展：李庆扬《数值分析》第5版等中文单级编号书，
条目为「标签+单一数字」且无章/节分量（定理1 / 定义3 / 例12 / 算法2 / 性质4），
既有抽取器均不覆盖：
  * extract_items(_two_level/_three_level) 只认 N.S-N / N.S.K 多级号；
  * extract_items_en(single=True) 的 EN_LABELS 无中文标签词。
本抽取器按 BookConfig.ordinal 各组的 name（经 _canon_label 规范化）取标签词表，
只收「块首 标签+数字」标题形态（与 extract_items_en 的 heading-vs-prose 守卫
同型），块中引用（如「由定理5可知」「利用算法2的结果」）天然被起点锚排除。

key 形态：f"{规范中文标签}{n}"（如 "定理1"），与 keys_in_md 的 ORDINAL_SINGLE
分支（ENTRY_RE_EN_SINGLE_C，COMBINED_LABEL_KINDS 含中文）输出的 md 侧键
1:1 对齐；label 字段携带原始标签供 group_for_label 分组。
"""
import bisect
import os
import re

from lib.boot import setup

setup()

from page_json import PageJson
from lib.regexlib import strip_head_noise
from verify_config import _canon_label
from scan_skeleton import block_xy


def _labels_from_groups(groups):
    """从 ordinal 组收集要抽取的标签词（规范化后），排除练习族与图族。"""
    skip = {"练习", "习题", "图", "Figure", "Fig", "Table", "表"}
    labels = []
    seen = set()
    for g in groups or []:
        for nm in g.name or []:
            c = _canon_label(nm)
            if not c or c in skip or c in seen:
                continue
            seen.add(c)
            labels.append(c)
    # 长标签优先（避免"注"抢在"注记"前匹配）
    labels.sort(key=len, reverse=True)
    return labels


def extract_items_cn_single(extract_dir, start, end, groups=None,
                            manual_overrides=None, restart_per_section=None):
    """从 page_*.json 抽取中文单级编号项（块首「标签+数字」形态）。

    返回 [{'key': '定理1', 'label': '定理', 'page': p, 'text': snippet}, ...]。

    ``restart_per_section``: ``(标签集合, [(page, 节号[, 块首 y]), ...])``——按节重置
    计数器（config ordinal 组 ``scope == 3``，如 Arnold《经典力学的数学方法》每节各起
    「例1」）的书，把下方「同 key 收敛到最早页」按**节窗口分桶**。否则后一节起重
    号的真条头会被前一节同号条目当作引用压掉（实测 §13 例1（p62）吞掉 §14 例1
    （p64），B 层报 4:14 缺号 1 阻断）。第 3 元是块头在该页上的阅读位置（页内
    y），桶边界按 ``(页, y)`` 比较——同页相邻两个字母块因此各归各桶；不传该元
    时退化为按页归桶。语义与 extract_items_en 的同名参数一致（EN 侧仍按页）；
    集合里的标签按 _canon_label 规范化后比较。不传该参数行为逐字不变。
    """
    labels = _labels_from_groups(groups)
    if not labels:
        return []
    # 仅拒绝「助词/连词」紧随数字的行首形态（如"定理1的证明""例2和例3"）。
    # 动词/介词开头（对于/给定/在线性方程组中/说明…）可能是真标题陈述句，
    # 不拒绝——行首真引用大多带前导词（由/见/利用/注意），被起点锚排除；
    # 漏网的行首引用由下方「按 key 保留最早页」兜底，不影响契约正确性。
    # 句点不拒：本书排版存在「定义5.若…」（号后带点再接正文）的标题形态，
    # 两级号仍由 (?!\d) 拦截。
    # 🔴 助词判据**跨空格**生效（Arnold 实测 2026-09-28）：扫描版 OCR 常在号与
    # 正文间插入空格，「定理2 的证明里面的椭球…」（= 定理2 的证明，不是条目）与
    # 「定理1 至3可直接由上证得出」（= 定理1~3 的回指）因此从「紧邻」判据下漏网，
    # 被抽成假条目。号后允许空白再判助词，两种 OCR 形态给出同一结论。
    ref_next = '的之中即与和或及时前后都均也是'
    # 🔴 助词判据**不得写成「先吞空白再 lookahead」**（Arnold §24 实测 2026-09-28）：
    # 「定理2 的证明里面的椭球…」的块首在旧式 `[ \u3000　]*(?![''的…''])` 下**仍然
    # 匹配**——吞空白的那个量词可以回溯让出那个空格，于是负向前查看到的字符是空格
    # 本身（空格永远不是助词），假条头照样入账。改成把空白放进**前查内部**
    # `(?![ \u3000　]*[助词])`：量词在环视里不参与主式回溯，无论停在哪个空白上，
    # 环视自己都会跨过空白去看真正的下一个字符。
    lab_re = re.compile(
        r'^[\s>]*(' + '|'.join(re.escape(l) for l in labels) + r')\s*'
        r'(\d{1,3})(?!\d)(?![ \u3000　]*[' + ref_next + r'])')
    # restart_per_section：把 (page, 节号) 窗口折成「重置边界」——**纯数字**号子嵌套
    # 于上一节号（"1.1.1" 接 "1.1"）不开新桶，其余一律开新桶（与
    # extract_items_en 同型）。页在首个边界之前 → 无桶，退回章级收敛。
    # 🔴 字母子块窗口（Arnold《经典力学的数学方法》体例）必须**开新桶**：节内印刷
    # 字母子块「A. 定义 / B. 例子 / D. 杨氏不等式」各自起一条计数器，实测 §14.B 例1-4
    # （p64）与 §14.D 例1-2（p65）同键不同条——旧判据把 "14.D" 当作 "14" 的嵌套号
    # 并回同一桶，`buckets.setdefault` 取最早页，于是 D 块的两条例从契约里**静默消失**
    # （正文只作为节描述散文残留，无条头）。尾部非数字（字母）= 真重启边界。
    # 🔴 边界还须精确到**页内位置**（Arnold §32 实测 2026-09-28）：B 块尾条 例2/例3
    # 与 C 块起重 例1 印在同一页（p144），而 C 的 例2 印在 D 块头上（p145）。按页
    # 归桶时 C 的 例1 被排到 B 尾巴之后（其后继不在本桶），三条续接判据全落空 →
    # 真条目又被当成回指吞掉。故 boundaries 按 (页, y) 排序，条目按块首 y 归桶。
    rst_labels, boundaries = set(), []
    if restart_per_section:
        _rl, _rws = restart_per_section
        rst_labels = {_canon_label(str(x).strip())
                      for x in (_rl or []) if str(x).strip()}
        _anchor = None
        for _w in sorted(_rws or [], key=lambda t: (t[0], str(t[1]))):
            _pg, _num = _w[0], _w[1]
            _y = _w[2] if len(_w) > 2 else None
            _s = str(_num)
            _tail = _s[len(_anchor) + 1:] if _anchor and _s.startswith(_anchor + '.') else None
            if _anchor is None or not (_tail and _tail.isdigit()):
                boundaries.append([int(_pg),
                                   float(_y) if _y is not None else float("-inf"),
                                   _s])
                _anchor = _s
        # 🔴 边界按**阅读位置** (页, 页内 y) 排序，桶号 = 排序后的下标（只是分组
        # 键，无外部含义）。同页相邻两个字母块由此各归各桶；y 缺失 = -inf（页顶），
        # 与旧「按页归桶」逐字一致。
        boundaries.sort(key=lambda t: (t[0], t[1]))
        # 项布局 = (页, 页内 y, 桶号, 窗口号)——`_bucket` 取 [2]、`_bucket_parent`
        # 取 [3]，改形状时两处都要跟着改。
        boundaries = [(pg, y, i, s) for i, (pg, y, s) in enumerate(boundaries)]
    _b_keys = [(pg, y) for pg, y, _, _ in boundaries]

    def _bucket(p, y=None):
        """条目所属窗口桶 = 阅读位置 (页, 块首 y) 之前最近的那个边界。

        y 未知 → 视为页末（+inf）：取本页最后一个边界，与旧的纯页码归桶同结果
        （页内没有任何其它边界时两者给出同一个桶）。"""
        if not _b_keys:
            return None
        key = (int(p), float(y) if y is not None else float("inf"))
        i = bisect.bisect_right(_b_keys, key) - 1
        return boundaries[i][2] if i >= 0 else None

    def _bucket_parent(b):
        """窗口号的父节分量：「14.D」→「14」，「14」→「14」。计数**跨字母子块
        连续**的书（§35 问题1..14 横跨 E/F/G、块首那条号不是 1）据此放行。
        （boundaries 项 = (页, 页内 y, 桶号, 窗口号)，窗口号在**第 4 位**。）"""
        if b is None or not (0 <= b < len(boundaries)):
            return None
        return str(boundaries[b][3]).split('.')[0]
    rows = []
    for p in range(int(start), int(end) + 1):
        fp = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        data = PageJson.load(fp).data
        for t in data.get("text", []) or []:
            txt = (t.get("text") or "").strip()
            if not txt:
                continue
            # 条头是块**首行**（lab_re 锚 `^`），故块首 y 即条头阅读位置。
            _blk_y = block_xy(t.get("poly") or [])[1]
            # 🔴 行首粘连标点（'．例9…'）不是「不是条头」的证据：检测前一律
            # strip_head_noise（判据在 lib/regexlib，抽取侧与查漏侧共用一份）。
            # 正文快照仍取原始行 txt，绝不写回净化后的文本。
            m = lab_re.match(strip_head_noise(txt))
            if not m:
                continue
            label = m.group(1)
            n = int(m.group(2))
            if n <= 0:
                continue
            key = f"{_canon_label(label)}{n}"
            snippet = txt[:100]
            # 🔴 第 4 元 `seq` = **文档序**（rows 按页内块序追加，故 len(rows) 即
            # 阅读顺序号）。旧实现用 `(page, n)` 当文档序：同一页内「前一节尾条
            # 问题4..6 + 本节起重问题1..3」（Arnold §34 起页 p151 实测）会被按**号**
            # 重排成 问题1,2,3,4,5,6，于是计数器续接判据看到的是印刷上**在后**的
            # 尾条、放行判据的「后继」也往回看——同桶同号两条同时入账。判据一律
            # 用 seq，页只是 seq 的主导分量。
            rows.append(({"key": key, "label": _canon_label(label),
                          "page": p, "text": snippet},
                         n, _bucket(p, _blk_y), len(rows)))
    # 按 key 收敛到最早页出现（真标题在前，行首引用/证明复述在后）。
    # 本书的同号再现均为引用或证明回指（如 p20「定理1 说明…」、
    # 「定理N 的证明」），不存在 Lasota-Mackey 式同号异条排版，
    # 故不做 dedup_items 的跨页异名保留。
    # restart_per_section 生效时，scope==3 标签改按「节 / 字母子块桶」收敛（各桶
    # 独立取最早页）。跨桶重号的放行判据 = 「这条号是某条**已入账计数器**的下一条」，
    # 三种续接形态任一成立即放行（一律要求 run>0，见下）：
    #   ① 本桶计数器续接（`run_bucket`）：同一节/子块内连号（例1→例2→例3）；
    #   ② 父节计数器续接（`run_parent`）：计数**跨字母子块连续**的书（§35/§36
    #      问题1..18 横跨 A..H 八块），块边界只是排版分段，不是重起；
    #   ③ 父节已有该号的直接后继（旧「同桶后继」，现已放宽到父节，见下）：号首被
    #      OCR 漏掉时后继仍能把该条放回来，**新块从 1 起重**也靠它确认（§8.E 问题1
    #      后继问题2 在账）。
    # 三条都不成立 → 孤立出现在新窗里的同号 = 回指，丢弃。
    # 🔴 ①②必须要求 `run > 0`：run=0 时 `n == run+1` 就是「n==1」，等于**无条件
    #   放过每个新窗的第一条**——实测 §39.F「引理1 说明矢量场的泊松括弧可以定义
    #   为…李括弧」正是回指前文引理1 的散文（§39 的引理只有 p180 那一条），旧
    #   写法把它抽成了第二个 引理1。「起重」的直接证据是后继（判据 ③），不是
    #   「号恰好等于 1」。
    # 🔴 旧实现只有判据 ③，于是**每个桶的最后一条**永远进不来：实测 §8.E 问题3
    #   （p47，其后继问题4 不存在）、§36.F 问题9 同理被吞——「后继」只是「计数器
    #   确实走到这里」的代理证据，续接判据（①②）才是直接证据。
    first, buckets = {}, {}
    for it, n, b, seq in sorted(rows, key=lambda t: t[3]):
        if b is None or it["label"] not in rst_labels:
            first.setdefault(it["key"], it)
        else:
            buckets.setdefault((b, it["key"]), []).append((it, n, seq))
    seen = set(first)
    out = list(first.values())
    run_bucket, run_parent = {}, {}
    # 🔴 槽位登记**全部**候选（旧实现 `setdefault((b,key), (it,n))` 只留最早那条，
    # 于是「前节尾条被归进后节窗口」时（Arnold §33 的 问题6..11 印在 §34 起页
    # p151），本节的同号真条头在入桶阶段就被**整批静默吞掉**（契约里只剩 问题5
    # 正文中的裸文本块，且练习族 B 层豁免 → 永不见天日）。现在候选全留，**去重
    # 完全交给下面的计数器判据**：同一 (桶,号) 的两条不可能都续接（第二条 n 不等
    # 于 run+1，也无后继），所以重复条头照旧被压掉，而真正的跨节重号照旧放行。
    # 🔴 候选一律带 `seq`（文档序），排序与「后继在后」都以 seq 为准：用
    # `(page, n)` 顶替文档序时，同页「尾条 问题4..6 + 起重条 问题1..3」会被按号
    # 重排，同号两条反而都放行。
    pending = [(it["page"], n, b, it, seq)
               for (b, key), lst in buckets.items() for (it, n, seq) in lst]
    # 🔴 判据 ③「后继在账」的后继必须是**文档序在后**的那条（Arnold §16 实测
    # 2026-09-28）：p73 印的是回指句「例 1 到例 3 中的变换都与力学有密切关系」，
    # 而 §16 的真 例1/例2 早在 p72 入账。旧写法 `(b, "例2") in buckets` 只看集合，
    # 于是「已用过的后继」被当成「计数器在此重起」的证据，把回指句放成了第二个
    # 例1（B 层随即报「16 例 缺号 2」——假号吃掉真号的位置）。后继只在其**后面**
    # 才算重起证据：连号要能往下走，不是往回看。
    # 🔴 后继还必须**同标签词**（Arnold §39.F 实测 2026-09-28）：本书一个窗口里
    # 各类型计数器并行（引理1/引理2、系1/系2/…），旧改写把 `lab` 形参留下了却
    # 没参与比较，于是「同桶任意 n+1」都算重起证据——p183 的回指句「引理1 说明
    # 矢量场的泊松括弧可以定义为…李括弧」被 §40 的 **系2**（号 2、页在后）放开，
    # 凭空多出第二个 引理1。原集合式判据 `(b, "%s%d" % (lab, n+1))` 是按
    # 标签+号 命中的，这一维在改写中丢了。
    # 🔴 搜索范围是**父节**而非单个字母块（Arnold §33 实测 2026-09-28）：桶边界
    # 精确到块首 y 之后，同页相邻字母块各归各桶，于是「本节重起的 问题1」与它的
    # 后继「问题2」可能被字母块头劈在两个桶里（§33 问题1@p148y1380 在 A 块、问题2
    # @p150y522 在 B 块），同桶判据看不到后继 → 重起的第一条被吞（契约 问题2..11
    # 而 问题1 无）。重起证据本就该在**整节**范围内找：本书的计数器要么每块起重、
    # 要么跨块连续，两种体例的号都落在同一条 §N 计数器上。标签维与「文档序在后」
    # 两维照旧保留（§39.F 案：跨节的 系2 仍不构成 §40 内 引理 的重起证据）。
    def _has_later_successor(b, lab, n, seq):
        """同父节、同标签内是否存在号 = n+1 且文档序严格在 `seq` 之后的候选。"""
        par = _bucket_parent(b)
        for pg, nn, bb, cand, s in pending:
            if (_bucket_parent(bb) == par and cand["label"] == lab
                    and nn == n + 1 and s > seq):
                return True
        return False

    for page, n, b, it, seq in sorted(pending, key=lambda t: t[4]):
        lab = it["label"]
        key = it["key"]
        if key in seen:
            rb, rp = (run_bucket.get((b, lab), 0),
                      run_parent.get((_bucket_parent(b), lab), 0))
            if not ((rb and n == rb + 1) or (rp and n == rp + 1)
                    or _has_later_successor(b, lab, n, seq)):
                continue
        seen.add(key)
        out.append(it)
        # run 记「本桶/父节**文档序**最后放行的号」，不是历史最大值：一个窗口里
        # 计数器可以被前一同号项占过一次后从 1 重起（§34 问题6..11 先被 §33 尾条
        # 借道），取 max 会把重起点之后的连号全判成回指。
        run_bucket[(b, lab)] = n
        run_parent[(_bucket_parent(b), lab)] = n
    out.sort(key=lambda x: (x["page"], x["key"]))
    # manual_overrides_ch{N}.json：恢复 OCR 错字/漏识的真实条目
    # （如「个圆寇理5(（格什戈林圆盘定理）」→ 定理5），语义与 extract_items 一致：
    # 已有同 key 条目则原位替换，否则追加，最后按 (page, key) 稳定排序。
    if manual_overrides:
        def _slot(key, page):
            """同 key 原位替换的目标：先按 (key, page) 精确命中，退回首个同 key。
            （按节重置的书里同 key 可在多节各存一条，只按 key 会替错那条。）"""
            for i, it in enumerate(out):
                if it['key'] == key and it.get('page') == page:
                    return i
            for i, it in enumerate(out):
                if it['key'] == key:
                    return i
            return None
        for mo in manual_overrides:
            entry = {'key': mo['key'], 'page': mo['page'],
                     'label': mo.get('label') or mo['key'].rstrip('0123456789'),
                     'text': mo.get('text') or '', 'agent_recovered': True}
            idx = _slot(mo['key'], mo['page'])
            if idx is None:
                out.append(entry)
            else:
                out[idx] = entry
        out.sort(key=lambda x: (x['page'], x['key']))
    return out


if __name__ == "__main__":
    import sys
    import json
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    ext, s, e = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    rows = extract_items_cn_single(ext, s, e)
    for r in rows:
        print(f"p{r['page']:03d} {r['key']}: {r['text'][:60]}")
    print(f"[total] {len(rows)} items")
