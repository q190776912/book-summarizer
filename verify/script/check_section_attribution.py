"""check_section_attribution.py — 条目↔节归属闸（verify/script 公用能力）

目的
----
契约把某节 §K 的**锚点页**定得**晚于**该节标题在原书里最早出现的页，导致落在
「最早节标题页 ~ 锚点页」之间的编号条目被甩到 §K 之外（通常漂到章前言）。

成因（real-analysis-for-graduate-students ch2 实测 2026-10-10）：真节头在 p29 以
「裸节号块 + 标题块」**两行**形态出现（`2.1` 独占一块，`Algebras and σ-algebras`
下一块），抽取器只认单行 `N.M 标题`，于是把 p31 的全大写**页眉复本**
`2.1. ALGEBRAS AND σ-ALGEBRAS` 当成了 §2.1 锚点 → 定义2.1～引理2.7（p29–30）被归到
章级、漂在 §2.1 之前，只有命题2.8 留在 §2.1 名下。内容不缺，**归属**错了。

为什么必须由本闸兜住：D 层（section_continuity）只比对节号存在/连续（§2.1 在、无
洞）；`check_contract_anchors` 只查前序页码单调（29→31 不倒退）；
`subsection_order_problems` 只比小节键递增（2.1<2.2<2.3）——三者对「锚点晚于最早
节头」这一形态全部结构性失明，门控因此一路放绿。

判据（保守、低误报）：仅当同时满足才报 BLOCKING：
  (1) 该节键是**点分数字**且首段 == 章号（自动排除无序号/字母附录/全局单号书）；
  (2) 源中存在一个**正文页** H（该页含 ≥1 个「标签+编号」条头，排除纯目录/扉页），
      其上 §K 的节头以**两行**形态出现——一个**独立成块的裸节号**（整块恰为点分号）
      紧跟一个标题块，且 H **严格早于**契约锚点页 A；
  (3) 契约里存在**编号结构条目**（definition/theorem/…）其 page_start ∈ [H, A) 且
      其父节点不是 §K。

**只认两行形态，不认单行**（ch4 §4.2 实测教训 2026-10-10）：单行「节号 + 后随文本」
会撞上以节号起头的**交叉引用句**（`4.2 shows that μ* is an outer measure, …`），那是
正文散文、不是节头 → 假报。而「整块恰为裸节号」的独立块几乎只可能由 OCR 把真节头
拆成「号块 + 标题块」两行而来，交叉引用永远内联在句子里、不会独占一块。故本闸只以
两行形态作为「最早真节头」的证据，恰好补上 build_structure 单行检测器漏掉的那一类。

合法「节前言定义先于首节标题」**不**被误报：那种情况下 §K 最早节头 H 就等于锚点 A
（标题确实排在条目之后），[H, A) 为空 → 不触发。本闸只打「锚点晚于最早节头」的误锚
形态，正是回归要防的类。
"""
import os
import re
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import page_json
from lib.util import blk_text
from lib.page_dir import resolve_page_dir

# 编号结构条目类型（与 check_structure_completeness._ITEM_TYPES 同集合）。
_ITEM_TYPES = {"definition", "theorem", "lemma", "corollary",
               "proposition", "example", "remark", "conjecture",
               "assertion", "assumption", "condition", "axiom", "property"}

# 点分数字节号（≥2 段），分隔符与 lib.regexlib.SEP_TIGHT 家族保持一致。
_DOTTED = r'\d{1,2}(?:[.\-·．]\d{1,2})+'
# 裸号块：整块恰为点分号（可带尾随一个分隔符/空白）。两行节头的第一块。
_BARE_NUM = re.compile(r'^(' + _DOTTED + r')[.\s·．]?$')
# 条头：标签词 + 编号（正文页判据）。中英标签词皆纳。
_ITEM_HEAD = re.compile(
    r'^\s*(?:Definition|Theorem|Lemma|Proposition|Corollary|Example|Remark|'
    r'Axiom|Exercise|定义|定理|引理|命题|推论|例|评注|注|公理|练习|猜想)'
    r'\s*[\*\uff1a:]?\s*\d{1,2}[.\-·．]\d{1,2}')
_SEP_SPLIT = re.compile(r'[.\-·．]')


def _nums(tok):
    """点分号字符串 → int 元组；非纯数字返回 None。"""
    parts = [p for p in _SEP_SPLIT.split(str(tok or "").strip()) if p != ""]
    if not parts or not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def _node_f(n, k, default=None):
    return n.get(k, default) if isinstance(n, dict) else getattr(n, k, default)


def _collect_sections_and_items(ch_node, ch):
    """遍历契约树：
      sections: [(nums_tuple, anchor_page, section_node)]  —— 点分数字、首段==ch
      items:    [(page_start, key, parent_node)]           —— 编号结构条目
    """
    sections, items = [], []
    ch_i = int(ch) if str(ch).isdigit() else None

    def walk(n, parent):
        t = _node_f(n, "type")
        key = _node_f(n, "key")
        pg = _node_f(n, "page_start")
        if t == "section":
            nums = _nums(key)
            if nums and len(nums) >= 2 and (ch_i is None or nums[0] == ch_i) \
                    and isinstance(pg, int):
                sections.append((nums, pg, n))
        elif t in _ITEM_TYPES and isinstance(pg, int):
            items.append((pg, key, parent))
        for c in (_node_f(n, "sub_sec") or []):
            walk(c, n)

    walk(ch_node, None)
    return sections, items


def _earliest_heading_pages(ext, ch, start, end, want_tuples):
    """扫描源页，为 want_tuples 里每个节号求「最早正文节头页」。

    正文页 = 该页含 ≥1 条头（排除纯目录/扉页）。节头形态：两行（裸号块 + 其下一块
    为标题）或单行且标题非全大写；全大写单行判为页眉复本，不计。返回
    ``{nums_tuple: earliest_page}``（未命中者不入表）。
    """
    first = {}
    remaining = set(want_tuples)
    _pdir = resolve_page_dir(ext, ch)
    for p in range(start, end + 1):
        if not remaining:
            break
        fp = os.path.join(_pdir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        try:
            data = page_json.PageJson.load(fp).data
        except Exception:
            continue
        blocks = [(blk_text(b) or "").strip()
                  for b in data.get("text", [])]
        blocks = [b for b in blocks if b]
        # 正文页判据：本页至少一个条头。
        if not any(_ITEM_HEAD.match(b) for b in blocks):
            continue
        for i, b in enumerate(blocks):
            # 两行形态：独立成块的裸号 + 下一块为标题（大写/CJK 起头、长度适中、非裸号）。
            mb = _BARE_NUM.match(b)
            if mb and i + 1 < len(blocks):
                t = _nums(mb.group(1))
                if t in remaining:
                    nxt = blocks[i + 1]
                    if (3 <= len(nxt) <= 60
                            and re.match(r'^[A-Z一-鿿]', nxt)
                            and not _BARE_NUM.match(nxt)):
                        first[t] = p
                        remaining.discard(t)
                        continue
    return first


def section_attribution_problems(ext, ch, start, end, ch_node):
    """返回归属错误问题串列表（空 = 通过）。见模块 docstring。"""
    if ch_node is None or not str(ch).isdigit():
        return []
    sections, items = _collect_sections_and_items(ch_node, ch)
    if not sections:
        return []
    want = {t for (t, _a, _n) in sections}
    first = _earliest_heading_pages(ext, ch, start, end, want)

    problems = []
    for (nums, anchor, snode) in sections:
        h = first.get(nums)
        if h is None or not (h < anchor):
            continue
        orphans = [(pg, key, par) for (pg, key, par) in items
                   if h <= pg < anchor and par is not snode]
        if not orphans:
            continue
        keys = ", ".join(str(k) for (_p, k, _x) in sorted(orphans))
        sec_label = ".".join(str(x) for x in nums)
        problems.append(
            "§%s 契约锚点=原书 p%d，但源中该节标题最早出现在正文页 p%d；"
            "其间 %d 个编号条目（%s）被归到 §%s 之外（父节点非本节）——"
            "疑为锚点抓到了后现的页眉/复本行，条目↔节归属错位，"
            "须回 build_structure 把 §%s 锚点前移到 p%d 后重跑本闸"
            % (sec_label, anchor, h, len(orphans), keys, sec_label, sec_label, h))
    return problems
