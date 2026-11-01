# -*- coding: utf-8 -*-
"""只读普查：闸门 ⑭ 的 `bare-only` 合取闸在跨语料上**何时不生效**（2026-10-30）。

动因（数值分析 ch5 例9 实测）：抽取器把展示式**数组元素**当公式编号收割，于是契约里出现
`1.83 / 1.08 / 0.783` 这类幻影 tag；而 ⑭ 判「无印刷锚点」用的裸排锚点集恰好把这些元素
**自己**认成锚点（OCR 把列向量元素切成独占整块），幻影因此自证清白。唯一还能拦它的是
`bare-only` 合取闸（`lib.tag_attestation.bare_only_leg_enabled`）：

    生效 ⇔ paren_hits ≥ 5 且 paren_hits ≥ 0.9 × (paren_hits + bare_only)

它是一条**比例**判据，于是方向反了：**一章里幻影越多，`bare_only` 越大，分母越大，
这条腿越不生效**——ch5 摘掉 5 个幻影前 57:10 不生效，摘掉后 57:5 才生效并立刻点名剩下
5 个。也就是说该闸只在「幻影已经很少」的书上工作，正是要查的书反而失明。

本工具量三件事（🔴 全程只读，不改任何书目录/配置/判据）：
  ① 每章 `paren_hits` / `bare_only`，**按出厂入口算**：tag 侧走 `collect_contract_tags`
     （含 `attested_numbers(ext)` 人工确证豁免剔除），锚点侧走 `_label_index`，读页走
     `dir_page_loader(node_page_dir(...), ext)`，腿的算术走 `bare_only_leg_enabled` ——
     全部是 `_condemned` 用的同一批函数、同一处算术，**不自算等价口径**；
  ② `bare-only` 腿**是否生效**，以及「若生效会新点名几个」= 当前失明量（`失明`）。
     腿关时再分两种原因：`无paren证据`（paren_hits<5，本书根本不以 `(N)`  numbering，
     这条腿**本就不该**生效）与 `比例压死`（paren_hits≥5 但被自己的幻影挤掉，这才是
     方向性缺陷的靶子）；
  ③ 失明子集里「tag 的数字串出现在**自己那条公式文本**里」的**线索**数（数组元素自证的形态）。
     ③ 是宽松包含（两侧都折成纯数字再判子串），会高估：只用来排序该先核哪本书，**不是结论**。
  ④ **局部性**（2026-10-30 Rising Sea ch21 实测后加的更硬的线索）：章级锚点集是整页窗的并集，
     所以 p587 上一个孤立裸块 ``0`` 就能给 p590 证明里那条展示式的 tag ``0`` 当锚点 ——
     幻影自证的真根子不是「数组元素」，而是**裸块锚点没有位置约束**。本工具按 tag 所在节点的
     页窗查裸锚页码：``异地`` = 裸锚只出现在别的页（首要嫌疑），``量不到`` = 节点没有页窗。
     同样是**线索不是判据**：⑭ 自己没用局部性，改成判据前要先看这两档在全语料的假阳率
     （合法裸排编号书里，页边号块与展示式同页 ⇒ 落进「同页」，不受影响）。
     🔴 已实测的假阳形态（measure-integration ch9，2026-10-30）：印面编号是**裸排** `9.46`…`9.50`
     打在续页 p296 右缘，而契约节点页窗只写到条目起始页 p295 ⇒ 严格「异地」全中；故另报
     `far`（锚点连 ±1 页都不沾）作为首要嫌疑档 —— 取证应按 `far` 排序，`异地` 只是上限。
     同时坐实一条**反向**结论：同页裸块可以是**真编号**（这本书的编号就没有括号），
     所以「裸块 = 数组元素/页码」的嫌疑只成立于**异地**或**自证**，不能只凭「是裸块」。

另报 `partial` 章（页窗可读页少于全部页）：⑭ 在这种章上照判不误，但锚点证据偏薄，
读它的失明数时要留一分。

用法：
    python tools/census_gate14_bare_blindness.py [--corpus DIR] [--filter 子串]
        [--limit N] [--show-at-risk] [--min-risk 1] [--include-no-paren-evidence]
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[1])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot  # noqa: E402
_boot.setup()

from data.book_structure.book_structure import (prime_chapter_kinds,  # noqa: E402
                                               resolve_chapter_json_path)
import lib.tag_attestation as _lta  # noqa: E402
from lib.page_dir import node_page_dir as _node_page_dir  # noqa: E402
from lib.user_config import get as _uc_get  # noqa: E402


def _books(corpus):
    """语料下的书目录（含 `_extract/book_structure` 者，不含册内/备份嵌套）。"""
    out = []
    for sub in sorted(os.scandir(corpus), key=lambda e: e.name):
        if not sub.is_dir():
            continue
        for bk in sorted(os.scandir(sub.path), key=lambda e: e.name):
            if not bk.is_dir():
                continue
            if os.path.isdir(os.path.join(bk.path, "_extract", "book_structure")):
                out.append(bk.path)
    return out


def _contract_files(bs_dir):
    return sorted(f for f in os.listdir(bs_dir)
                  if f.endswith(".json")
                  and (f.startswith("ch") or f.startswith("appendix")
                       or f.startswith("supplement")))


def _ch_key(fname):
    for pre in ("ch", "appendix", "supplement"):
        if fname.startswith(pre):
            return fname[len(pre):-5]
    return None


_DIGITS = re.compile(r"[0-9]")


def _digits(s):
    return "".join(_DIGITS.findall(str(s)))


def _formula_of_block(node):
    """块 → 其公式串（`tag` 与 `tags` 里的号都归到这个块上，供 ③ 的线索用）。"""
    seq = []
    t = _lta._norm(node.get("tag"))
    if t:
        seq.append(t)
    for x in (node.get("tags") or []):
        s = _lta._norm(x)
        if s and s not in seq:
            seq.append(s)
    return seq, _digits(node.get("formula"))


def _tag_formula_index(tree):
    """tag → 该 tag 所在块的公式纯数字串（同号多块时拼起来，只作线索用）。"""
    out = {}

    def walk(node):
        if isinstance(node, dict):
            if node.get("formula") is not None:
                seq, fd = _formula_of_block(node)
                for s in seq:
                    out[s] = out.get(s, "") + fd
            for c in node.get("sub_sec") or []:
                walk(c)
        elif isinstance(node, list):
            for c in node:
                walk(c)

    walk(tree)
    return out


def _tag_window(tree):
    """tag → 挂着它的那个**最近带页窗的祖先节点**页窗 [(lo, hi), …]（局部性判据用）。"""
    out = {}

    def walk(node, win):
        if isinstance(node, dict):
            lo, hi = node.get("page_start"), node.get("page_end")
            w = (int(lo), int(hi)) if isinstance(lo, int) and isinstance(hi, int) else win
            if node.get("formula") is not None:
                seq, _fd = _formula_of_block(node)
                for s in seq:
                    out.setdefault(s, []).append(w)
            for c in node.get("sub_sec") or []:
                walk(c, w)
        elif isinstance(node, list):
            for c in node:
                walk(c, win)

    walk(tree, None)
    return out


def chapter_row(ext, ch_key, known):
    """一章一行账。**逐句镜像 `lib.tag_attestation._condemned`**（同一批函数、同顺序）。"""
    tree = json.load(open(resolve_chapter_json_path(ext, ch_key), encoding="utf-8"))
    skip = {_lta._norm(x) for x in known}
    tags = [(k, n) for k, n in _lta.collect_contract_tags(tree) if n not in skip]
    if not tags:
        return None
    try:
        lo, hi = int(tree.get("page_start")), int(tree.get("page_end"))
    except (TypeError, ValueError):
        return {"ch": ch_key, "unreadable": "no-page-window"}
    loader = _lta.dir_page_loader(_node_page_dir(ext, tree, ch_key), ext)
    avail = [p for p in range(lo, hi + 1) if loader(p)]
    if not avail:
        return {"ch": ch_key, "unreadable": "no-page-json",
                "pages": "%d..%d" % (lo, hi)}
    by_paren, by_bare = _lta._label_index_by_page(loader, lo, hi)
    paren, bare = set(by_paren), set(by_bare)
    # ↓ 与 _condemned 同一套过滤：paren_hits 先摘掉「有括号锚点」的，剩下的才谈裸排
    paren_hits = [n for _k, n in tags if n in paren]
    bare_only = [n for _k, n in tags if n not in paren and n in bare]
    unattested = [n for _k, n in tags if n not in paren and n not in bare]
    leg = _lta.bare_only_leg_enabled(len(paren_hits), len(bare_only))
    if leg:
        reason = None
    elif len(paren_hits) < 5:
        reason = "no-paren-evidence"
    else:
        reason = "ratio-drowned"
    blind = [] if leg else sorted(set(bare_only))
    win = _tag_window(tree)
    fd = _tag_formula_index(tree)
    self_anch = [t for t in blind if _digits(t) and _digits(t) in fd.get(t, "")]
    # ④ 局部性：裸块锚点**是否落在该 tag 自己所在节点的页窗里**。不在 = 锚点是章内别处的
    #    孤立数字块（Rising Sea ch21 实测：p587 的裸块 `0` 给 p590 的 tag `0` 当锚点）。
    def _local(t, pad=0):
        wins = [w for w in (win.get(t) or []) if w]
        if not wins:
            return None                      # 节点无页窗 ⇒ 局部性量不到，不猜
        anchors = by_bare.get(t, ())
        return any(int(w[0]) - pad <= a <= int(w[1]) + pad
                   for w in wins for a in anchors)

    offpage = [t for t in blind if _local(t) is False]
    unmeas = [t for t in blind if _local(t) is None]
    # 🔴 校准（2026-10-30 measure-integration ch9 实测）：节点页窗是**条目**的起点页，
    # 一条证明/展示式可以续到下页，印面编号就落在下页 —— 严格「异地」会把这类真号判成嫌疑
    # （本书 9.46..9.50 五个连号全中）。所以再分一档 `far`：锚点连 ±1 页都不沾，才是首要嫌疑。
    far = [t for t in blind if _local(t, pad=1) is False]
    return {"ch": ch_key, "pages": "%d..%d" % (lo, hi),
            "tags": len(tags), "paren_hits": len(paren_hits),
            "bare_only": len(set(bare_only)), "unattested": len(set(unattested)),
            "leg": leg, "reason": reason, "blind": blind,
            "self_anchored": self_anch, "offpage": offpage, "far": far,
            "unmeas": unmeas,
            "partial": len(avail) < (hi - lo + 1),
            "have": "%d/%d" % (len(avail), hi - lo + 1)}


def loader_diff(books):
    """⑭ 的**读页口径**差集：`dir_page_loader(ext)`（闸门旧口径）vs 含册目录的正确口径。

    分册书（``_extract/上册|下册/page_*.json``，顶层无页）在旧口径下**一页也读不到** →
    「缺页文件不判」把整章判成空 → ⑭ 静默失效。本模式量该失效在语料上的爆炸半径：
    新点名章数 = 把闸接回正确读页后会新增几个 FAIL（2026-10-30 修 `gate_units._page_label_loader`
    前的校准；实测全语料只有 数学分析 一本受影响，新增 2 个**真**幻影 ch3 ``0x`` / ch16 ``1n``）。
    """
    print("# ⑭ 读页口径差集（只读）：flat=dir_page_loader(ext) ｜ node=含册目录")
    st = {"ch": 0, "flat_ch": 0, "node_ch": 0, "dead_node": 0, "gain_ch": 0, "gain_n": 0}
    for bk in books:
        ext = os.path.join(bk, "_extract")
        bs = os.path.join(ext, "book_structure")
        prime_chapter_kinds(ext)
        known = {str(x) for x in _lta.attested_numbers(ext)}
        for fn in _contract_files(bs):
            ck = _ch_key(fn)
            if not ck:
                continue
            try:
                tree = json.load(open(resolve_chapter_json_path(ext, ck), encoding="utf-8"))
            except Exception:
                continue
            tags = {str(n) for _k, n in _lta.collect_contract_tags(tree)} - known
            if not tags:
                continue
            st["ch"] += 1
            node_ld = _lta.dir_page_loader(_node_page_dir(ext, tree, ck), ext)
            flat = {str(x) for x in _lta.unattested_tags(
                tree, _lta.dir_page_loader(ext), _lta.attested_numbers(ext))}
            node = {str(x) for x in _lta.unattested_tags(
                tree, node_ld, _lta.attested_numbers(ext))}
            if flat:
                st["flat_ch"] += 1
            if node:
                st["node_ch"] += 1
            try:
                lo, hi = int(tree.get("page_start")), int(tree.get("page_end"))
                if not any(node_ld(p) for p in range(lo, hi + 1)):
                    st["dead_node"] += 1
            except (TypeError, ValueError):
                pass
            gain = node - flat
            if gain:
                st["gain_ch"] += 1
                st["gain_n"] += len(gain)
                print("  %-44s %-10s 旧口径漏点名 %s"
                      % (os.path.basename(bk)[:44], ck, " ".join(sorted(gain)[:12])))
    print("-" * 78)
    print("有契约 tag 的章 %d ｜ flat 点名章 %d ｜ node 点名章 %d ｜ 正确口径也读不到页的章 %d"
          % (st["ch"], st["flat_ch"], st["node_ch"], st["dead_node"]))
    print("接回正确读页 → 新增 FAIL 章 %d ｜ 新增判毒号 %d（免费修复的判据 = 这两个数只含真毒）"
          % (st["gain_ch"], st["gain_n"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--filter", default=None, help="只跑书名含该子串的书")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--show-at-risk", action="store_true")
    ap.add_argument("--min-risk", type=int, default=1)
    ap.add_argument("--include-no-paren-evidence", action="store_true",
                    help="把「paren_hits<5」的章也算进失明（默认单列，不算靶子）")
    ap.add_argument("--loader-diff", action="store_true",
                    help="改量 ⑭ 的读页口径差集（flat vs 含册目录），见 :func:`loader_diff`")
    args = ap.parse_args()

    corpus = args.corpus or _uc_get("corpus_root")
    books = _books(corpus)
    if args.filter:
        books = [b for b in books if args.filter in os.path.basename(b)]
    if args.limit:
        books = books[:args.limit]
    if args.loader_diff:
        return loader_diff(books)

    print("# ⑭ bare-only 失明普查（只读）")
    print("# 失明 = 腿关时「只有裸排锚点」的契约 tag；腿开 = 它们本就被判毒，失明 0")
    st = {"books": 0, "ch": 0, "blind": 0, "ratio_ch": 0, "ratio_blind": 0,
          "noparen_ch": 0, "noparen_blind": 0, "self": 0, "unread": 0,
          "partial": 0, "errs": 0, "catch": 0, "offpage": 0, "far": 0, "unmeas": 0}
    for bk in books:
        ext = os.path.join(bk, "_extract")
        bs = os.path.join(ext, "book_structure")
        prime_chapter_kinds(ext)
        known = _lta.attested_numbers(ext)
        st["catch"] += 1
        rows = []
        for fn in _contract_files(bs):
            ck = _ch_key(fn)
            if not ck:
                continue
            try:
                r = chapter_row(ext, ck, known)
            except Exception as e:
                print("!! %s %s：%s %s" % (os.path.basename(bk), fn,
                                          type(e).__name__, e))
                st["errs"] += 1
                continue
            if not r:
                continue
            if r.get("unreadable"):
                st["unread"] += 1
                continue
            rows.append(r)
        ratio = [r for r in rows if r["reason"] == "ratio-drowned"]
        nop = [r for r in rows if r["reason"] == "no-paren-evidence"]
        sel = (ratio if not args.include_no_paren_evidence else ratio + nop)
        sel = [r for r in sel if r["blind"]]
        st["ch"] += len(rows)
        st["partial"] += sum(1 for r in rows if r["partial"])
        st["ratio_ch"] += len(ratio)
        st["ratio_blind"] += sum(len(r["blind"]) for r in ratio)
        st["noparen_ch"] += len(nop)
        st["noparen_blind"] += sum(len(r["blind"]) for r in nop)
        risk = sum(len(r["blind"]) for r in sel)
        if risk < args.min_risk:
            continue
        st["books"] += 1
        st["blind"] += risk
        st["self"] += sum(len(r["self_anchored"]) for r in sel)
        st["offpage"] += sum(len(r["offpage"]) for r in sel)
        st["far"] += sum(len(r["far"]) for r in sel)
        st["unmeas"] += sum(len(r["unmeas"]) for r in sel)
        print("%-46s 失明%4d ｜ 比例压死%3d 无paren证据%3d ｜ 异地%3d 其中±1外%3d "
              "自证%3d 量不到%3d ｜ 章数%d"
              % (os.path.basename(bk)[:46], risk,
                 sum(len(r["blind"]) for r in ratio if r["blind"]),
                 sum(len(r["blind"]) for r in nop if r["blind"]),
                 sum(len(r["offpage"]) for r in sel),
                 sum(len(r["far"]) for r in sel),
                 sum(len(r["self_anchored"]) for r in sel),
                 sum(len(r["unmeas"]) for r in sel), len(rows)))
        if args.show_at_risk:
            for r in sel:
                print("      %-8s p%-12s tag%-4d paren%-4d bare%-4d 无锚点%-4d "
                      "腿%-3s %s%s ｜ 异地%-3s 自证%-3s → %s"
                      % (r["ch"], r["pages"], r["tags"], r["paren_hits"],
                         r["bare_only"], r["unattested"],
                         "开" if r["leg"] else "关", r["reason"] or "",
                         " 页窗%s" % r["have"] if r["partial"] else "",
                         " ".join(r["far"]), " ".join(r["self_anchored"]),
                         " ".join(r["blind"][:40])))
    print("-" * 78)
    print("语料 %s ｜ 书 %d ｜ 章 %d（读不到页窗 %d，页窗不全 %d）｜ 判据异常 %d"
          % (corpus, st["catch"], st["ch"], st["unread"], st["partial"], st["errs"]))
    print("失明章/号：比例压死 %d 章 %d 号 ｜ 无paren证据 %d 章 %d 号"
          % (st["ratio_ch"], st["ratio_blind"], st["noparen_ch"], st["noparen_blind"]))
    print("入报口径（--include-no-paren-evidence=%s）：书 %d ｜ 失明号 %d ｜ "
          "其中异地 %d（±1 外 %d）｜ 自证线索 %d ｜ 局部性量不到 %d"
          % (args.include_no_paren_evidence, st["books"], st["blind"],
             st["offpage"], st["far"], st["self"], st["unmeas"]))


if __name__ == "__main__":
    main()
