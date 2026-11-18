# -*- coding: utf-8 -*-
"""check_section_leak.py — 节界泄漏闸（verify/script 公用能力）

目的
----
契约把 §S 的尾部编号条目挂进了**下一节**（LEAK-A：上一节尾部内容出现在下一节
文件开头），或把下一节头之后的内容留在本节名下（LEAK-B）。

成因（Lee《Introduction to Smooth Manifolds》2026-11-16 全书普查实测 65 处）：
``build_structure`` 的 ``_place`` 对 ``_item_pos`` 定位不到条头块的条目按
「位置未知 → 视为页末 → 归入本页已开节的最后一节」回退；当 §N 的尾部条目与
§N+1 的节头**同页**（§N+1 节头印在该页下部）时，这批条目整批挂进 §N+1。
Lee ISM 的节头是**裸标题**（无编号），页眉复本与真标题**同文本、同左缘**
（页眉顶行左缘起排），``_band_split_y`` 的「右移 >25%」与「前缀重复」判据都不
触发 → ``_find_title_pos`` 取到页眉 y（页顶），同页 y 比较随之全部失真。
B 层（同标签序号单调）对跨节错挂结构性失明：推论 13.30 是 §13.2 的最后一条，
挂到 §13.3 名下后各标签序号依然单调，门控一路放绿——直到交付 md 按节拆分，
「上一节尾部出现在下一节文件开头」才肉眼可见。

判据（保守、无证据不报）：对每个 section 节点 S 取**印刷节头锚点** (page, y)：
  * 数字键 → ``build_structure._numbered_heading_y``（自带页眉带让位）；
  * 裸标题键（U* 等）→ 本模块 ``_title_heading_anchor``：先收「整块归一化 ==
    标题」的**独立命中**；同页 ≥2 个且最顶者在页眉带内 → 取带下最小 y（真节头，
    页眉复本让位——``_band_split_y`` 同文本同左缘形态失明，故此处自判）；
    无独立命中回退 ``_find_title_pos``（原让位行为）；本页无 → 试 page_start-1
    （节锚点偏晚形态，与 check_section_attribution 的「锚点晚于最早节头」互补）。
对 S 的每个子节点 C 取锚点 (page, y)：
  * 编号条目 → ``_item_pos``（±1 页回退，与 ``attach_content._item_anchor`` 同源；
    仍找不到 = 无证据，跳过）；
  * description → 首个 ≥20 字符 text 块归一化前缀，在 page_start ±1 页内行首命中。
仅当满足其一才报 BLOCKING：
  * **LEAK-A** ``anchor_C < anchor_S``（页更早，或同页 y 更小）——§S 的尾部内容
    被挂进 §S。修复 = 归位到「节头锚点 ≤ anchor_C 的最后一个 section」
    （没有 → 章级前言），manifest 记录同步移动。
  * **LEAK-B** ``anchor_C > anchor_N``（N = S **子树之后**的下一个 section 的
    节头锚点）——下一节头之后仍挂在 §S 名下。S 自己子树内的节头**不算**边界：
    父节条目印在自己子节标题之后是合法形态（Lee ISM §7.4「Semidirect Products」
    子节后的 §7.4 习题实测）。
豁免：``consolidated`` 节的子节点（章末集中习题块）；type=section 的子节点
（小节由递归覆盖）；锚点无证据的节点一律跳过（防误报，宁漏勿错）。

用法
----
    python verify/script/check_section_leak.py <extract_dir> [ch ...]   # 全书普查
供 ``check_structure_completeness``（步骤 3 完整性闸门）与修书驱动脚本消费：
结构化结果走 :func:`section_leak_findings`（含建议归位目标），字符串报告走
:func:`section_leak_problems`。
"""
import difflib
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

import json

from lib.util import blk_text
from lib.page_dir import resolve_page_dir
from data.book_structure.book_structure import unit_dir_name
import build_structure as _bs

# 编号结构条目类型（与 check_section_attribution._ITEM_TYPES 同集合 + 习题）。
_ITEM_TYPES = {"definition", "theorem", "lemma", "corollary",
               "proposition", "example", "remark", "conjecture",
               "assertion", "assumption", "condition", "axiom", "property",
               "exercise", "problem", "notation", "convention", "terminology"}

# 同页 y 比较容差（OCR bbox 抖动）。
_EPS = 3.0
# description 前缀锚定的最小归一化长度（短前缀撞正文风险大）。
_DESC_MIN_NORM = 20
_DESC_SNIPPET = 40


def _norm(s):
    return re.sub(r"\s+", "", s or "")


def _norm_md(s):
    """单元行 → OCR 可比形态：去空白与 Markdown 装饰（* _ `）。"""
    return re.sub(r"[\s*_`]+", "", s or "")


def _node_f(n, k, default=None):
    return n.get(k, default) if isinstance(n, dict) else getattr(n, k, default)


def _page_blocks(ext, ch, p):
    """页 p 的文本块 [(x, y, 归一化文本)]；缺页/坏页返回 []。"""
    if not p or int(p) < 1:
        return []
    fp = os.path.join(resolve_page_dir(ext, ch), "page_%03d.json" % int(p))
    if not os.path.exists(fp):
        return []
    try:
        d = json.load(open(fp, encoding="utf-8"))
    except Exception:
        return []
    out = []
    for b in d.get("text", []) or []:
        if not isinstance(b, dict):
            continue
        t = _norm(blk_text(b))
        if not t:
            continue
        xy = _bs.scan_skeleton.block_xy(b.get("poly") or [])
        out.append((xy[0], xy[1], t))
    return out


def _title_heading_anchor(ext, ch, node):
    """裸标题节头锚点 (page, y, how)；无证据返回 None。

    独立命中优先：整块归一化 == 标题的块。同页 ≥2 个且最顶者在页眉带内 →
    取带下最小 y（Lee ISM p356 实测：页眉复本与真标题同文本同左缘，
    _band_split_y 两判据皆不触发，必须在此自判）。无独立命中回退
    ``_find_title_pos``；本页无 → 试 page_start-1（锚点偏晚）。"""
    page = int(_node_f(node, "page_start") or 0)
    name = (_node_f(node, "name") or "").strip()
    if not page:
        return None
    m = re.match(r"^[\dA-Z]+(?:\.[\dA-Z]+)*\s+(.*)$", name, re.DOTALL)
    title = (m.group(1) if m else name).strip()
    if not title:
        return None
    for p in (page, page - 1):
        if p < 1:
            continue
        blocks = _page_blocks(ext, ch, p)
        if not blocks:
            continue
        tn = _norm(title)
        standalone = [(x, y) for (x, y, t) in blocks if t == tn]
        if standalone:
            top = min(y for (_x, y, _t) in blocks)
            below = [(x, y) for (x, y) in standalone
                     if y > top + _bs.scan_skeleton._HEAD_TOP_TOL]
            pick = (min(below, key=lambda t: t[1])
                    if (below and len(standalone) > 1)
                    else min(standalone, key=lambda t: t[1]))
            return (p, float(pick[1]), "title-standalone")
        pos = _bs._find_title_pos(ext, title, p, p)
        if pos:
            return (pos[0], float(pos[1]), "title")
    return None


def _numbered_band_yield(ext, ch, node):
    """数字节头的页眉复本让位：带下独立命中的最小 y；无让位证据返回 None。

    Brin–Stuck《Introduction to Dynamical Systems》p17 实测 2026-11-17（该书
    普查 143 处 LEAK-B 全假阳的根因）：页眉 running head 印 `1.2. Circle
    Rotations`（带句点、**正文左缘起排** x=77、y=62=本页最顶块），真节头
    `1.2 Circle Rotations` 在同页 y=1416——`_band_split_y` 的「右移 >25%」
    （左缘起排不触发）与「前缀重复」（左缘判据先行否决）两判据皆不触发，
    `_numbered_heading_y` 取到页眉 y=62，LEAK-B 的下一节边界被提到页顶，
    整页正文全部「越过」假边界。裸标题路径在 `_title_heading_anchor` 已自判
    同形态；此处对数字节头补同款判据：整块归一化（去标点/页码尾，跨句点变体
    `1.2.` ≡ `1.2`）等于节头全名的**独立命中** ≥2 且最顶者贴住本页最顶块
    （±`_HEAD_TOP_TOL`，运行头位置）→ 取带下最小 y。判据只看同文本独立命中，
    无该形态的书零改动（只把锚点从页顶复本**下移**，绝不反向）。"""
    page = int(_node_f(node, "page_start") or 0)
    name = (_node_f(node, "name") or "").strip()
    if not page or not name:
        return None
    blocks = _page_blocks(ext, ch, page)
    if len(blocks) < 2:
        return None
    nn = _bs._norm_head(_bs._HEAD_TRAIL_NUM.sub("", name))
    if len(nn) < 8:
        return None
    hits = []
    for x, y, t in blocks:
        tn = _bs._norm_head(_bs._HEAD_TRAIL_NUM.sub("", t))
        if tn == nn:
            hits.append(y)
    if len(hits) < 2:
        return None
    tol = _bs.scan_skeleton._HEAD_TOP_TOL
    top = min(y for (_x, y, _t) in blocks)
    top_hit = min(hits)
    if top_hit > top + tol:
        return None  # 最顶命中不在页顶 = 页眉复本形态不成立，让位无据
    below = [y for y in hits if y > top_hit + tol]
    if not below:
        return None
    return float(min(below))


def _section_anchor(ext, ch, node):
    """节头锚点 (page, y, how)；无证据返回 None。"""
    key = str(_node_f(node, "key") or "")
    page = int(_node_f(node, "page_start") or 0)
    if page and re.match(r"^[\dA-Z]+(?:\.[\dA-Z]+)+$", key):
        # 数字键优先（含页眉带让位）；失败再按标题词回退。
        y = _bs._numbered_heading_y(ext, key, page)
        if y is not None:
            # 🔴 同文本页眉复本让位（`_band_split_y` 两判据失明的形态，见
            # `_numbered_band_yield`）：只把锚点从页顶复本移到带下真节头。
            y2 = _numbered_band_yield(ext, ch, node)
            if y2 is not None and y2 > float(y):
                return (page, y2, "numkey-band-yield")
            # 🔴 页顶命中嫌疑（Katok p92 实测 2026-11-17：真节头行被 OCR 吃掉
            # 章号 `2.4`→`4.`，同文本独立命中只剩页眉一处，让位判据无 below
            # 可取；该书 101 处 LEAK-B 全由此假阳）。锚点贴住本页最顶块时退回
            # 标题词搜索，**只接受带下（y > 页顶+TOL）命中**——`_find_title_pos`
            # 的包含匹配会取到页眉复本自身（min-y），不能直接用；这里在检查器
            # 本地做同页带下包含命中，锚点只下移不上移。
            blocks = _page_blocks(ext, ch, page)
            if blocks:
                tol = _bs.scan_skeleton._HEAD_TOP_TOL
                top = min(y_ for (_x, y_, _t) in blocks)
                if float(y) <= top + tol:
                    name2 = (_node_f(node, "name") or "").strip()
                    m2 = re.match(r"^[\dA-Z]+(?:\.[\dA-Z]+)*\s+(.*)$",
                                  name2, re.DOTALL)
                    title2 = (m2.group(1) if m2 else name2).strip()
                    tn2 = _bs._norm_head(title2)
                    if len(tn2) >= 8:
                        below = []
                        for (_x, y_, t) in blocks:
                            if y_ <= top + tol:
                                continue
                            # 🔴 模糊可比（Katok p478 实测：真节头行被 OCR 吞章号
                            # `14.2`→`2.` 且 flows→fows，精确/包含全失灵）：
                            # 归一化（去标点转小写）后序列相似度 ≥0.8 即算命中。
                            bn = _bs._norm_head(t)
                            if not bn:
                                continue
                            sm = difflib.SequenceMatcher(None, tn2, bn)
                            if tn2 in bn or sm.ratio() >= 0.8:
                                below.append(y_)
                        if below:
                            return (page, float(min(below)),
                                    "numkey-topband-title")
            return (page, float(y), "numkey")
    return _title_heading_anchor(ext, ch, node)


def _item_band_guard(ext, ch, node, cand, y):
    """条目锚点的页顶带守卫（Weibel 3.6-2 实测 2026-11-17：`_item_pos` 的
    包含匹配探针截断到 24 字符，页眉 running head `3.6 Universal Coefficient
    Theorems` 含「universal coefficient theorem」前缀即命中，min-y 让页眉压过
    页底真位置 y1617 → 假 LEAK-A）。条目真身**永远不会印在页眉带里**，故：
    命中落在页顶带（y ≤ 本页最顶块 + `_HEAD_TOP_TOL`）时不可信——用**全名**
    归一化探针在带下重找 body 命中；找到 → 让位给带下最小 y；找不到 → 返回
    None（调用方对整条锚点放弃 = 无证据不报，宁漏勿错）。非页顶命中原样放行。"""
    blocks = _page_blocks(ext, ch, cand)
    if not blocks:
        return None, False
    tol = _bs.scan_skeleton._HEAD_TOP_TOL
    top = min(y_ for (_x, y_, _t) in blocks)
    if float(y) > top + tol:
        return None, False  # 不在页顶带 = 可信 body 命中，原样放行
    name = (_node_f(node, "name") or "").strip()
    tn = _norm(re.sub(r"^(?:[\dA-Z]+(?:[.\-][\dA-Z]+)*\s+){1,2}", "", name)).lower()
    if len(tn) >= 8:
        below = [y_ for (_x, y_, t) in blocks
                 if y_ > top + tol and tn in t.lower()]
        if below:
            return float(min(below)), False  # 带下真身 → 让位
    return None, True  # 页顶命中且无 body 证据 → 整条放弃


def _item_anchor(ext, ch, node):
    """编号条目锚点 (page, y, how)；无证据返回 None。

    与 attach_content._item_anchor 同源（page_start 本页 → ±1 页回退），
    区别仅在「找不到」返回 None 而非 (page, 0.0) 哨兵——校验必须无证据不报。
    页顶带守卫见 `_item_band_guard`（条目真身不印在页眉带，页顶命中不可信）。"""
    page = int(_node_f(node, "page_start") or 0)
    if not page:
        return None
    it = {"key": _node_f(node, "key") or "",
          "text": _node_f(node, "name") or "",
          "type": _node_f(node, "type") or ""}
    for cand in (page, page - 1, page + 1):
        if cand < 1:
            continue
        pos = _bs._item_pos(ext, dict(it, page=cand), page_dir=resolve_page_dir(ext, ch))
        if pos and pos[0] == cand and pos[1] is not None and pos[1] >= 0:
            y2, discard = _item_band_guard(ext, ch, node, cand, float(pos[1]))
            if discard:
                return None
            if y2 is not None:
                return (cand, y2, "item-band-yield")
            return (cand, float(pos[1]), "item" if cand == page else "item+1")
    return None


_UNIT_MANIFEST_CACHE = {}


def _chapter_units(ext, ch):
    """章的全部单元表 {key: (file_path, body_lines)}；无 units 目录返回 {}。

    契约 description 节点普遍是空壳（text 块不落盘），正文在单元文件里——
    锚定 desc 必须回退单元首行；部分泄漏的重复检测也要扫全部单元。
    步骤 3 闸门运行时 units 尚未拆出 → 空表，判据自然退化为「无证据跳过」
    （拆分前的书不报 desc 泄漏）。"""
    ck = str(ch)
    # 🔴 缓存键必须含 ext：一次进程审计多本书时 ch1/ch2 会互相串单元，
    # 把 A 书 desc 锚点算到 B 书的单元上（2026-11-18 代数几何七书联审实测）。
    ckey = (os.path.abspath(str(ext)), ck)
    if ckey in _UNIT_MANIFEST_CACHE:
        return _UNIT_MANIFEST_CACHE[ckey]
    out = {}
    udir = os.path.join(ext, "book_structure", "units", unit_dir_name(ck))
    mfp = os.path.join(udir, "manifest.json")
    if os.path.exists(mfp):
        try:
            man = json.load(open(mfp, encoding="utf-8"))
        except Exception:
            man = {}
        for u in (man.get("units") or []):
            if not u.get("file"):
                continue
            fp = os.path.join(udir, u["file"])
            if not os.path.exists(fp):
                continue
            try:
                lines = open(fp, encoding="utf-8").read().split("\n")[1:]
            except Exception:
                continue
            out[str(u.get("key"))] = (fp, lines)
    _UNIT_MANIFEST_CACHE[ckey] = out
    return out


def _line_page_hit(ext, ch, tn, pages):
    """归一化行 tn 在 pages（有序页列表）内的首命中 (page, y)；梯前缀 40→32→24。

    同页多个命中时优先「体带」块（页顶行 + _HEAD_TOP_TOL 之下）——运行头/页眉
    复本与正文行共享前缀时（Lee ISM 节头即 run-in 标题，p356 实测）取体带命中。
    🔴 页顶带命中**一律不采信**：目录行、页眉跑马行、页脚水印都可能与描述首行
    共享前缀（methods p124「5.Additive and Abelian Categories109」、rising-sea
    "November 18, 2017 draft"、a-course 页眉章名实测），而这些标记可能属于
    **另一章**，拿它们当锚点会做跨章误判。带下无命中 = 无证据，跳过不报。"""
    tol = _bs.scan_skeleton._HEAD_TOP_TOL
    for L in (40, 32, 24):
        probe = tn[:L]
        if not probe:
            continue
        for p in pages:
            if p < 1:
                continue
            blocks = _page_blocks(ext, ch, p)
            if not blocks:
                continue
            hits = [(y, t) for (_x, y, t) in blocks if t.startswith(probe)]
            if not hits:
                continue
            top = min(y for (_x, y, _t) in blocks)
            body = [y for y, _t in hits if y > top + tol]
            if body:
                return (p, float(min(body)))
    return None


def _desc_anchor(ext, ch, node):
    """description 锚点 (page, y, how)：契约 text 块优先，空壳回退单元首行。

    取首个足够长的实质行（归一化 ≥%d 字符）在 page_start ±1 页内行首命中；
    无证据返回 None。""" % _DESC_MIN_NORM
    page = int(_node_f(node, "page_start") or 0)
    if not page:
        return None
    # 候选 snippet：契约 text 块（若有）优先，其次单元首行——两者都可能因
    # LaTeX/OCR 字符差异（$X x^{i}$ vs Xx^i）单源失配，多候选互为备份。
    # 🔴 契约 OCR 块按页几何挂载，desc 节点的 page_start 落在**新节首页**时
    # 常把上一节页尾残文挂进来（an-intro ch3 D6 的「is the cokernel of the
    # difference map」、leinster ch6 D5 的「defined as in Lemma 6.1.3(a)」）。
    # 这些残文不在单元正文里，拿它们当锚点会报假跨节泄漏。故契约候选必须
    # 与单元正文逐字相交才采信；无单元可核时宁可无证据，不猜。
    units = _chapter_units(ext, ch)
    info = units.get(str(_node_f(node, "key") or ""))
    unit_norm = _norm_md("\n".join(info[1])) if info else ""
    raw = []
    for blk in (_node_f(node, "text") or []):
        t = blk.get("text") if isinstance(blk, dict) else blk
        tn = _norm(t)
        if len(tn) >= _DESC_MIN_NORM:
            raw.append(tn[:_DESC_SNIPPET])
    for b in (_node_f(node, "sub_sec") or []):
        if isinstance(b, dict) and b.get("text"):
            tn = _norm(str(b.get("text")))
            if len(tn) >= _DESC_MIN_NORM:
                raw.append(tn[:_DESC_SNIPPET])
        if len(raw) >= 5:
            break
    # 无单元目录（拆分前的早期章节 / 契约-only 测试）无从交叉核对，沿用原候选；
    # 有单元时只采信单元正文确实包含的片段。
    cands = [s for s in raw if not unit_norm or s[:24] in unit_norm]
    if info:
        for ln in info[1]:
            tn = _norm_md(ln)
            if len(tn) >= _DESC_MIN_NORM:
                cands.append(tn[:_DESC_SNIPPET])
            if len(cands) >= 8:
                break
    for snip in cands:
        hit = _line_page_hit(ext, ch, snip, (page, page - 1, page + 1))
        if hit:
            return (hit[0], hit[1], "desc-text")
    return None


def _node_anchor(ext, ch, node):
    t = str(_node_f(node, "type") or "")
    if t in _ITEM_TYPES:
        return _item_anchor(ext, ch, node)
    if t == "description":
        return _desc_anchor(ext, ch, node)
    return None


def _is_block_el(el):
    """sub_sec 元素是否为内容块（与 attach_content._is_block 同判据）。"""
    return isinstance(el, dict) and ("text" in el or "formula" in el or "image" in el) \
        and "key" not in el and "type" not in el


def _desc_leak_shape(ext, ch, node, a_s):
    """desc 泄漏形态：
      whole   整单元内容都在节头之前 → 搬节点（走 LEAK-A）
      partial 头部 k 个段落在节头之前、其余在后 → 修剪前导块（LEAK-D）
    返回 (kind, k, frag_line, duplicate_in)。无法定位的行即停（保守）。"""
    units = _chapter_units(ext, ch)
    info = units.get(str(_node_f(node, "key") or ""))
    if not info:
        return ("whole", 0, "", "")
    self_file = info[0]
    _fp, lines = info
    ps = int(_node_f(node, "page_start") or 0)
    k = 0
    frag = ""
    below_after = False
    for ln in lines:
        tn = _norm_md(ln)
        if len(tn) < _DESC_MIN_NORM:
            continue
        if tn.startswith("$$"):
            break                      # 公式围栏：不可行首锚定，停（保守）
        if tn.startswith("<div") or tn.startswith("<img"):
            break                      # 图容器/图块：不在文字层行首锚定，停
        hit = None
        if not tn.startswith("$$") and not tn.startswith("<div") and not tn.startswith("<img"):
            hit = _line_page_hit(ext, ch, tn, (ps, ps - 1, ps + 1))
        if hit is None:
            continue                   # 无命中行：中性跳过（多块/公式跨块形态）
        if hit[0] < a_s[0] or (hit[0] == a_s[0] and hit[1] < a_s[1] - _EPS):
            k += 1
            if not frag:
                frag = ln.strip()
        elif hit[0] > a_s[0] or (hit[0] == a_s[0] and hit[1] > a_s[1] + _EPS):
            below_after = True
    kind = "partial" if (k and below_after) else "whole"
    dup = ""
    if kind == "partial" and frag:
        probe = _norm_md(frag)[:48]
        for ukey, (fp2, lines2) in units.items():
            if fp2 == self_file:
                continue
            for ln2 in lines2:
                if probe and probe in _norm_md(ln2):
                    dup = os.path.basename(fp2)
                    break
            if dup:
                break
    return (kind, k, frag, dup)


def section_leak_findings(ext, ch, start, end, ch_node):
    """结构化泄漏清单（修书驱动消费）。

    返回 dict 列表：
      {code, node_key, node_type, node_page, anchor, parent_key, parent_name,
       sec_anchor, bound_label, bound_anchor, home_key, home_name,
       home_is_chapter}
    ``home_*`` = 建议归位目标：节头锚点 ≤ 节点锚点的最后一个 section
    （无 → '#chapter' 章级前言）。LEAK-B 不给 home（须回源判读）。
    """
    if ch_node is None:
        return []
    # 带父链的文档序平铺（sec = [node, parent_node, subtree_last_idx]）
    secs = []

    def walk(n, parent):
        for c in (_node_f(n, "sub_sec") or []):
            if str(_node_f(c, "type") or "") != "section":
                continue
            if _node_f(c, "consolidated"):
                continue
            secs.append([c, parent, None])
            idx = len(secs) - 1
            walk(c, c)
            # 子树末下标 = 进入子树后更新到当前最后下标
            secs[idx][2] = len(secs) - 1

    walk(ch_node, None)
    anchors = {}
    for node, _parent, _e in secs:
        anchors[id(node)] = _section_anchor(ext, ch, node)

    def _usable(a):
        """(page, y) 锚点带 y<=0 是几何缺失哨兵（OCR 无 poly / 标题未命中），
        不得当真值参与跨节/跨章比较——否则 intro-ca 的 y=0 会把整页条目
        误判成越过下一节节头。"""
        return a is not None and float(a[1]) > 0

    findings = []
    for i, (node, _parent, sub_end) in enumerate(secs):
        a_s = anchors[id(node)] if _usable(anchors[id(node)]) else None
        # LEAK-B 边界 = 子树之后的第一个 section（S 自己子树内的节头不算边界）
        j = (sub_end + 1) if sub_end is not None else (i + 1)
        a_next = (anchors[id(secs[j][0])]
                  if j < len(secs) and _usable(anchors[id(secs[j][0])]) else None)
        next_label = (str(_node_f(secs[j][0], "key")) if j < len(secs) else "")
        # SECORDER：节自身与下一结构兄弟的锚序（节头印得晚却排在兄弟之前）
        kids_struct = [c for c in (_node_f(node, "sub_sec") or [])
                       if not _is_block_el(c)]
        for si, sc in enumerate(kids_struct):
            if str(_node_f(sc, "type") or "") != "section" or _node_f(sc, "consolidated"):
                continue
            a_sc = anchors[id(sc)]
            if not _usable(a_sc) or si + 1 >= len(kids_struct):
                continue
            nxt = kids_struct[si + 1]
            a_nx = (_section_anchor(ext, ch, nxt)
                    if str(_node_f(nxt, "type") or "") == "section"
                    else _node_anchor(ext, ch, nxt))
            if not _usable(a_nx):
                continue
            if (a_sc[0], a_sc[1]) > (a_nx[0], a_nx[1] + _EPS):
                findings.append({
                    "code": "SECORDER", "node_key": str(_node_f(sc, "key") or ""),
                    "node_type": "section",
                    "node_page": _node_f(sc, "page_start"),
                    "anchor": (a_sc[0], a_sc[1]),
                    "parent_key": str(_node_f(node, "key") or ""),
                    "parent_name": str(_node_f(node, "name") or ""),
                    "sec_anchor": (a_sc[0], a_sc[1]),
                    "bound_label": str(_node_f(nxt, "key") or ""),
                    "bound_anchor": (a_nx[0], a_nx[1]),
                    "home_key": "", "home_name": "", "home_is_chapter": False,
                    "leak_blocks": 0, "frag": "", "duplicate_in": "",
                })
        for c in (_node_f(node, "sub_sec") or []):
            t = str(_node_f(c, "type") or "")
            if t == "section" or _node_f(c, "consolidated"):
                continue
            # 弱锚（标题回退 y=0）：同页 y 比较无意义，desc 形态判定跳过（防误报）
            if t == "description" and a_s is not None and a_s[1] <= 0:
                continue
            a_c = _node_anchor(ext, ch, c)
            if not _usable(a_c):
                continue
            ck = str(_node_f(c, "key") or "")
            ct = str(_node_f(c, "type") or "")
            if a_s is not None and (a_c[0] < a_s[0]
                                    or (a_c[0] == a_s[0] and a_c[1] < a_s[1] - _EPS)):
                # desc 单元头部残片形态：只有前 k 个段落在节头之前 → 修剪而非搬节点
                if ct == "description":
                    kind, k, frag, dup = _desc_leak_shape(ext, ch, c, a_s)
                    if kind == "partial":
                        findings.append({
                            "code": "LEAK-D", "node_key": ck, "node_type": ct,
                            "node_page": _node_f(c, "page_start"),
                            "anchor": (a_c[0], a_c[1]),
                            "parent_key": str(_node_f(node, "key") or ""),
                            "parent_name": str(_node_f(node, "name") or ""),
                            "sec_anchor": (a_s[0], a_s[1]),
                            "leak_blocks": k, "frag": frag, "duplicate_in": dup,
                            "home_key": "", "home_name": "", "home_is_chapter": False,
                            "bound_label": "", "bound_anchor": None,
                        })
                        continue
                # LEAK-A：建议归位目标 = 节头锚点 ≤ 节点锚点的最后一个 section
                home_key, home_name = "#chapter", ""
                best = None
                for (s2, _p2, _e2) in secs:
                    a2 = anchors[id(s2)]
                    if a2 is None:
                        continue
                    if (a2[0], a2[1]) <= (a_c[0], a_c[1]):
                        if best is None or (a2[0], a2[1]) > best[0]:
                            best = ((a2[0], a2[1]), s2)
                if best is not None:
                    home_key = str(_node_f(best[1], "key") or "")
                    home_name = str(_node_f(best[1], "name") or "")
                findings.append({
                    "code": "LEAK-A", "node_key": ck, "node_type": ct,
                    "node_page": _node_f(c, "page_start"),
                    "anchor": (a_c[0], a_c[1]),
                    "parent_key": str(_node_f(node, "key") or ""),
                    "parent_name": str(_node_f(node, "name") or ""),
                    "sec_anchor": (a_s[0], a_s[1]),
                    "bound_label": "", "bound_anchor": None,
                    "home_key": home_key, "home_name": home_name,
                    "home_is_chapter": home_key == "#chapter",
                })
                continue
            if a_next is not None and (a_c[0] > a_next[0]
                                       or (a_c[0] == a_next[0]
                                           and a_c[1] > a_next[1] + _EPS)):
                # LEAK-B：建议归位目标与 LEAK-A 同规则（节头锚点 ≤ 节点锚点的
                # 最后一个 section）——Lee ISM ch7 实测：Ex 7.31/例 7.32 越过
                # 「Semidirect Products」节头，该规则正好把它们归回 U6。
                home_key, home_name = "", ""
                best = None
                for (s2, _p2, _e2) in secs:
                    a2 = anchors[id(s2)]
                    if a2 is None:
                        continue
                    if (a2[0], a2[1]) <= (a_c[0], a_c[1]):
                        if best is None or (a2[0], a2[1]) > best[0]:
                            best = ((a2[0], a2[1]), s2)
                if best is not None:
                    home_key = str(_node_f(best[1], "key") or "")
                    home_name = str(_node_f(best[1], "name") or "")
                findings.append({
                    "code": "LEAK-B", "node_key": ck, "node_type": ct,
                    "node_page": _node_f(c, "page_start"),
                    "anchor": (a_c[0], a_c[1]),
                    "parent_key": str(_node_f(node, "key") or ""),
                    "parent_name": str(_node_f(node, "name") or ""),
                    "sec_anchor": (a_s[0], a_s[1]) if a_s else None,
                    "bound_label": next_label,
                    "bound_anchor": (a_next[0], a_next[1]),
                    "home_key": home_key, "home_name": home_name,
                    "home_is_chapter": False,
                })
    return findings


def section_leak_problems(ext, ch, start, end, ch_node):
    """字符串报告（空 = 通过）。见模块 docstring。"""
    out = []
    for f in section_leak_findings(ext, ch, start, end, ch_node):
        sec = "§%s(%s)" % (f["parent_key"], (f["parent_name"] or "")[:40])
        pos = (f["anchor"][0], round(f["anchor"][1]))
        if f["code"] == "LEAK-D":
            dup = ("；片段与 %s 内容重复（OCR 残渣），修剪后无需归位"
                   % f["duplicate_in"]) if f.get("duplicate_in") else \
                "；片段须归位到前节末尾（新建尾部 desc，双语单元与 manifest 同步）"
            out.append(
                "节界泄漏 LEAK-D：%s 名下的 desc %s 单元头部 %d 个段落在节头锚点 p%s 之前"
                "（上一节尾部残片粘进本节开头）——修剪单元前导块（EN/CN 同步），%s"
                % (sec, f["node_key"], f["leak_blocks"],
                   (f["sec_anchor"][0], round(f["sec_anchor"][1])), dup))
            continue
        if f["code"] == "SECORDER":
            bp = (f["bound_anchor"][0], round(f["bound_anchor"][1]))
            out.append(
                "节序倒置 SECORDER：§%s 节头锚点 p%s 晚于后兄弟 %s 的锚点 p%s"
                "——节点排在印刷序之前（多半原先无子单元所以页码单调门看不见），"
                "须把该节移到锚序正确的兄弟位置"
                % (f["node_key"], pos, f["bound_label"], bp))
            continue
        if f["code"] == "LEAK-A":
            sp = (f["sec_anchor"][0], round(f["sec_anchor"][1]))
            home = ("章级前言" if f["home_is_chapter"]
                    else "§%s(%s)" % (f["home_key"], (f["home_name"] or "")[:40]))
            out.append(
                "节界泄漏 LEAK-A：%s 名下的 [%s] %s 印刷锚点 p%s 在节头锚点 p%s 之前"
                "——上一节尾部内容被挂进本节（同页跨节头形态）；建议归位 → %s，"
                "契约与双语 manifest 记录须同步移动"
                % (sec, f["node_type"], f["node_key"], pos, sp, home))
        else:
            bp = (f["bound_anchor"][0], round(f["bound_anchor"][1]))
            out.append(
                "节界泄漏 LEAK-B：%s 名下的 [%s] %s 印刷锚点 p%s 已越过下一节 "
                "§%s 的节头锚点 p%s——下一节头之后的内容仍挂在本节名下；"
                "建议归位 → §%s(%s)，契约与双语 manifest 记录须同步移动"
                "（父节条目印在自己子节标题之后不算泄漏，已按子树边界豁免）"
                % (sec, f["node_type"], f["node_key"], pos,
                   f["bound_label"], bp, f["home_key"], (f["home_name"] or "")[:40]))
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")
    ext = argv[0]
    want = argv[1:] or None
    from data.book_structure.book_structure import BookStructure
    bs = BookStructure.load(ext)
    if bs is None:
        print("[check_section_leak] BLOCKED: 分章契约缺失（%s/book_structure/）" % ext)
        return 2
    total = 0
    for chapter in bs.chapters:
        ck = str(chapter.key)
        if want and ck not in want:
            continue
        node = bs.find_chapter(ck)
        if node is None:
            continue
        node = node.to_dict() if hasattr(node, "to_dict") else node
        fnd = section_leak_findings(ext, ck, None, None, node)
        print("== ch%s leaks=%d" % (ck, len(fnd)))
        for line in section_leak_problems(ext, ck, None, None, node):
            print("   " + line)
        total += len(fnd)
    print("TOTAL:", total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
