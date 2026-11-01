# -*- coding: utf-8 -*-
"""只读普查：闸门 ⑭ 的 `lettered` 合取闸在跨语料上**何时不生效**（2026-10-30）。

动因（数学分析 ch6–ch9 实测）：抽取器把公式残渣当编号收割，契约里出现 `2x` / `2M` / `12x`
/ `0x` 这类**字母尾幻影**。⑭ 唯一会拦它们的是形态启发式 `lettered` 腿
（`lib.tag_attestation.lettered_leg_enabled`），它有**两条体例证据腿，任一成立即开**：

    印面侧 ⇔ 页窗里「整块就是 `(号)`」的独立印刷编号 ≥5 且其中字母尾 ≤10%
    契约侧 ⇔ 本章纯整数 tag ≥5 且字母尾 tag ≤10%

🔴 「字母尾」的口径是 `_lettered_tail`（**数字后紧跟字母**：`2n` / `12x` / `18.10a`），不是
「含字母」：Gelfand–Manin《methods-of-homological-algebra》ch5 印面编号是 `V.1`..`V.29`
（罗马章前缀），30 块独立编号里 29 块「含字母」，用「含字母」数分母时印面腿被**前缀**挤死，
该章契约里的 `9x` / `9y` 两个公式残渣就永远量不到体例矛盾（2026-10-31 实测；改口径后该章
腿开、两个号都被点名并已摘账）。前缀字母是另一种编号体例，该由判据①管。本工具的所有
字母尾计数（`lettered` / `exempt` / `p_lettered`）都走这个谓词。

和 :mod:`tools.census_gate14_bare_blindness` 量过的那条腿**同一种方向性缺陷**：
比例判据里**幻影越多 → 字母尾越大 → 越容易越过 10% 门槛**，字母尾最扎眼的章恰好失明
（旧口径只有契约侧，跨 58 书 / 477 章实测**全语料点名 0 处＝死代码**，16 个失明号里
`ratio-drowned` 占 0 章——卡的全是 `n_numeric >= 5` 那道门：章本身 tag 稀疏 + 登记处
`known_book: 1..30` 把样本掏空。本工具改版前后各 dump 一次，`--ab` 量出半径）。
本工具量四件事（🔴 全程只读，不改任何书目录/配置/判据）：

  ① 每章 `numeric` / `lettered` / `standalone` 豁免，**按出厂入口算**：tag 侧走
     `collect_contract_tags`（含 `attested_numbers(ext)` 人工确证豁免剔除），锚点侧走
     `_label_index_by_page` + `_standalone_labels`，读页走
     `dir_page_loader(node_page_dir(...), ext)`；**裁决直接调 `condemned_map`**，
     腿的算术调 `lettered_leg_enabled` / `bare_only_leg_enabled` 且喂**判据自己的输入**
     （全量样本 + 页窗 `standalone`），普查不复制一份 `setdefault` 链；
  ② 腿**是否生效**、关的原因**分侧**记（两腿任一成立即开，所以只报「合并原因」会藏掉
     证据到底缺在哪一侧）：印面侧 `printed-unmeasurable`（整块编号 <5，页窗量不到体例）
     / `printed-lettered`（印面字母尾 >10% —— 本章**真用**字母编号，门关得对）；
     契约侧 `few-numeric`（纯整数 tag <5，不可证）/ `ratio-drowned`（整数 ≥5 却被自己的
     幻影挤过 10% —— 这才是方向性缺陷的靶子）；
  ③ **真失明量** = 腿关时「本来会被这条腿**新点名**」的字母尾号，即三趟裁决后**一个理由码
     都没拿到**的那些（`unattested` / `bare-only` 先赢的号不算，`setdefault` 语义）——
     这样报的才是「失明导致的漏网」，不是字母尾号总数；
  ④ 失明子集的**嫌疑分档**（都是线索不是判据，取证按此排序）：
     `异地`/`far` = 该号的锚点页不落在挂着它的那个节点的页窗里（`far` 再要求连 ±1 页都不沾，
     是首要嫌疑；±1 档的必要性由 2026-10-30 measure-integration ch9 实测坐实——印面裸排编号
     打在续页右缘，节点页窗只写到条目起始页）；`自证` = 号的字母数字串出现在**自己那条公式**
     的折叠文本里（宽松包含，会高估）；`量不到` = 节点没有页窗，不猜。

known_true 通道（证明本工具不是「零命中即安全」）：③ 只统计字母尾号中**没拿到**「整块即
`(号)`」强证据的那些，所以另报 `豁免` = 拿到强证据的字母尾号（Koopman ch18 的 `18.10a`/
`18.10b` 印作独立块，必须落在这里而不是失明集），以及 `点名` = 腿**开着**时确实被判毒的
字母尾号（证明这条腿本身在语料上是活着的）。这两档任一为零都要停下来查工具，不能当「书很干净」。

改版后**仍然失明**的站点是「按设计量不到/字母体例」，照实报出来、交印面取证裁定，
**不得**批量豁免静音（`--dump` 里逐章留 `why_printed` / `why_contract` / `printed` 三列账）。

另报 `partial` 章（页窗可读页少于全部页）：⑭ 在这种章上照判不误，但锚点证据偏薄，
读它的失明数时要留一分。

🔴 2026-10-31 复跑（字母尾口径 + 16 处幻影已销账之后）的实测基线，供下次读数对照：
书 58 ｜ 章 472 ｜ 契约里余下字母尾号 93（**豁免 91 / 失明 2**）｜ 点名 **0** ｜
`printed-lettered`（本章真用字母编号，门关得对）**0 章** ｜ 失明 2 号 =
数学分析 ch8 `2M`、LawrenceEvans-SDE chC `2k`，两章关因都是
`printed-unmeasurable / few-numeric`（页窗独立编号 4 块 / 0 块，整数 tag <5）＝按设计量不到。
「点名 0」**不等于**腿死：用各书 `_bak_deregister_tags/<ts>/book_structure+chN.json`
（摘除**前**的契约）喂今天的判据即可复现点名（核脚本
`D:/study/_scratch/shelf_gate_20261028/_p766_known_true.py`：数学分析 ch18 `1D`+`2p`、
ch9 `2g`+`9x`+`3w`、Gelfand–Manin ch5 `9x`+`9y` 全部判 `lettered`）。语料干净时要这样自证，
不要停在「零命中」。

用法：
    python tools/census_gate14_lettered_blindness.py [--corpus DIR] [--filter 子串]
        [--limit N] [--show-blind] [--min-blind 1] [--ratio-only] [--samples]
    # 判据改版校准（改前后各 dump 一次，再对照；见 :func:`ab`）：
    python tools/census_gate14_lettered_blindness.py --dump OLD.jsonl
    python tools/census_gate14_lettered_blindness.py --dump NEW.jsonl
    python tools/census_gate14_lettered_blindness.py --ab OLD.jsonl NEW.jsonl
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


_ALNUM = re.compile(r"[0-9A-Za-z]")


def _fold(s):
    return "".join(_ALNUM.findall(str(s)))


def _tag_sites(tree):
    """tag → [(挂着它的节点页窗, 该块公式折叠串), …]（同号多块全留；局部性与自证线索用）。"""
    out = {}

    def walk(node, win):
        if isinstance(node, dict):
            lo, hi = node.get("page_start"), node.get("page_end")
            w = (int(lo), int(hi)) if isinstance(lo, int) and isinstance(hi, int) else win
            if node.get("formula") is not None:
                seq = []
                t = _lta._norm(node.get("tag"))
                if t:
                    seq.append(t)
                for x in (node.get("tags") or []):
                    s = _lta._norm(x)
                    if s and s not in seq:
                        seq.append(s)
                fd = _fold(node.get("formula"))
                for s in seq:
                    out.setdefault(s, []).append((w, fd))
            for c in node.get("sub_sec") or []:
                walk(c, w)
        elif isinstance(node, list):
            for c in node:
                walk(c, win)

    walk(tree, None)
    return out


def _local(sites, by_paren, by_bare, num, pad=0):
    """该号的锚点页**是否**落在挂着它自己的节点页窗里。None = 节点无页窗（量不到，不猜）。"""
    ws = [w for w, _f in sites.get(num, []) if w]
    if not ws:
        return None
    anch = set(by_paren.get(num, ())) | set(by_bare.get(num, ()))
    return any(int(w[0]) - pad <= a <= int(w[1]) + pad for w in ws for a in anch)


def chapter_row(ext, ch_key, known, show=False):
    """一章一行账。**裁决直接调判据**（`_lta.condemned_map`），诊断列喂判据自己的输入。

    🔴 这里过去逐句镜像 `_condemned` 的 `setdefault` 链，于是判据一改版普查就悄悄分叉
    （`blind` 会按旧算术算，报出判据根本不可能点名的站点）。改版后 `blind` / `caught`
    都从**真裁决**倒推：`caught` = 拿到 `lettered` 码的号（腿开时这条腿的新点名），
    `blind` = 腿关时**三个理由码一个都没拿到**的字母尾号（前两条腿先赢的不算漏网）。
    """
    tree = json.load(open(resolve_chapter_json_path(ext, ch_key), encoding="utf-8"))
    skip = {_lta._norm(x) for x in known}
    all_tags = list(_lta.collect_contract_tags(tree))
    tags = [(k, n) for k, n in all_tags if n not in skip]
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
    verdicts = dict(_lta.condemned_map(tree, loader, known))
    by_paren, by_bare = _lta._label_index_by_page(loader, lo, hi)
    paren, bare = set(by_paren), set(by_bare)
    standalone = _lta._standalone_labels(loader, lo, hi)
    p_le = sorted(n for n in standalone if _lta._lettered_tail(n))
    # ↓ 三个计数就是 _condemned 递给 lettered_leg_enabled 的那三个（全量、含已登记号）
    numeric_full = [n for _k, n in all_tags if not _lta._lettered_tail(n)]
    lettered_full = [n for _k, n in all_tags
                     if _lta._lettered_tail(n) and n not in standalone]
    leg = _lta.lettered_leg_enabled(len(numeric_full), len(lettered_full),
                                    len(standalone), len(p_le))
    # 两条证据腿各自开否：印面侧把契约侧喂成「必然不成立」，契约侧不传页窗参数（默认 0）
    leg_printed = _lta.lettered_leg_enabled(0, 1, len(standalone), len(p_le))
    leg_contract = _lta.lettered_leg_enabled(len(numeric_full), len(lettered_full))
    lettered = [n for _k, n in tags
                if _lta._lettered_tail(n) and n not in standalone]
    exempt = sorted({n for _k, n in tags
                     if _lta._lettered_tail(n) and n in standalone})
    caught = sorted({n for n in lettered if verdicts.get(n) == "lettered"})
    blind = [] if leg else sorted({n for n in lettered if n not in verdicts})
    why_printed = why_contract = None
    if not leg and lettered_full:
        why_printed = (None if leg_printed else
                       ("printed-unmeasurable"
                        if len(standalone) < _lta._PRINTED_CONVENTION_MIN
                        else "printed-lettered"))
        why_contract = (None if leg_contract else
                        ("few-numeric" if len(numeric_full) < 5 else "ratio-drowned"))
    sites = _tag_sites(tree)
    offpage = [n for n in blind if _local(sites, by_paren, by_bare, n) is False]
    far = [n for n in blind if _local(sites, by_paren, by_bare, n, pad=1) is False]
    unmeas = [n for n in blind if _local(sites, by_paren, by_bare, n) is None]
    self_anch = [n for n in blind
                 if _fold(n) and any(_fold(n) in f for _w, f in sites.get(n, []))]
    bare_leg = _lta.bare_only_leg_enabled(
        len([n for _k, n in all_tags if n in paren]),
        len([n for _k, n in all_tags if n not in paren and n in bare]))
    row = {"ch": ch_key, "pages": "%d..%d" % (lo, hi),
           "tags": len(tags),
           "numeric": len([n for _k, n in tags
                           if not _lta._lettered_tail(n)]),
           "lettered": len(lettered),
           "numeric_full": len(numeric_full), "lettered_full": len(lettered_full),
           "leg": leg, "leg_printed": leg_printed, "leg_contract": leg_contract,
           "why_printed": why_printed, "why_contract": why_contract,
           "blind": blind, "exempt": exempt,
           "caught": caught, "offpage": offpage, "far": far, "unmeas": unmeas,
           "self_anchored": self_anch,
           "no_paren": [n for n in blind if n not in paren],
           "bare_leg_off": (not bare_leg),
           "partial": len(avail) < (hi - lo + 1),
           "have": "%d/%d" % (len(avail), hi - lo + 1)}
    # 登记处对「体例样本」的削减（🔴 旧口径把体例样本读成**摘掉 attested 之后**的 tag 集：
    # 一本把 `known_book` 写成 `1..30` 的书，纯整数 tag 会塌到个位数，两条比例腿同时关死。
    # 现在样本读全量，登记号只豁免裁决 —— 这两列留着，是为了继续看得见「登记了多少、是谁」）
    dropped = sorted({n for _k, n in all_tags if n in skip})
    row["printed"] = {"standalone": len(standalone), "lettered": len(p_le),
                      "lettered_eg": p_le[:8],
                      "numeric_full": len(numeric_full),
                      "lettered_full": len(lettered_full),
                      "registered": len(dropped), "registered_eg": dropped[:12]}
    row["registered_all"] = dropped
    row["standalone_all"] = sorted(standalone)
    row["verdicts"] = verdicts
    if show and blind:
        locs = _lta.anchor_locations(loader, lo, hi)
        row["samples"] = {n: {"paren": locs.get(n, {}).get("paren", {}),
                              "bare": locs.get(n, {}).get("bare", {})}
                          for n in blind}
    return row



def _read_dump(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rec = json.loads(line)
                out["%s|%s" % (rec["book"], rec["ch"])] = rec
    return out


def _cnt(d):
    out = {}
    for rec in d.values():
        for c in rec["verdicts"].values():
            out[c] = out.get(c, 0) + 1
    return out


def ab(old_path, new_path):
    """两份 ``--dump`` 的裁决差集（判据改版**前后各 dump 一次**；这里只对照，不重跑判据）。

    同屏四档，缺任一档都不算证完：
      ① 按理由码给 旧/新 总数；
      ② **新增判毒**站点逐条列出（书名｜章｜号｜码｜印面独立括号号数｜其中字母尾数），
         每一条都要回印面核过才能落账；
      ③ **新增放行**站点（收紧方向却放行 = 判据被削，必须逐条解释，不许只报总数）；
      ④ known_true 两核：(a) 章内「整块即 `(号)`」的字母尾号在 NEW 里**不得**判毒；
         (b) 已登记（``known_book``）的号在 NEW 里**不得**判毒 —— 把体例样本从「摘掉
         attested 的 tag 集」换成全量之后，「登记即豁免」必须原样成立，否则这次改动
         把人工确证通道一起削掉了（那是反向误伤，不是收紧）。
    """
    old, new = _read_dump(old_path), _read_dump(new_path)
    only_old = sorted(set(old) - set(new))
    only_new = sorted(set(new) - set(old))
    print("# ⑭ lettered 腿 A/B（旧 dump=%d 章 ｜ 新 dump=%d 章）" % (len(old), len(new)))
    if only_old or only_new:
        print("⚠️ 章集合不齐：只在旧 %d ｜ 只在新 %d（多半是读页/异常路径变了，先解释再看差集）"
              % (len(only_old), len(only_new)))
        for k in (only_old + only_new)[:20]:
            print("      %s" % k)
    print("① 理由码总数  旧 %s ｜ 新 %s" % (_cnt(old), _cnt(new)))
    adds, rems, chg, blind = [], [], [], {"old": 0, "new": 0}
    for k in sorted(set(old) & set(new)):
        blind["old"] += len(old[k]["blind"])
        blind["new"] += len(new[k]["blind"])
        vo, vn = old[k]["verdicts"], new[k]["verdicts"]
        for n in sorted(set(vo) | set(vn)):
            co, cn = vo.get(n), vn.get(n)
            if co == cn:
                continue
            if co and not cn:
                rems.append((k, n, co))
            elif cn and not co:
                adds.append((k, n, cn, new[k]))
            else:
                chg.append((k, n, co, cn))
    print("② 新增判毒 %d 处 ｜ ③ 新增放行 %d 处 ｜ 理由码改写 %d 处"
          % (len(adds), len(rems), len(chg)))
    print("   失明量（腿关时本该点名的字母尾号）旧 %d → 新 %d" % (blind["old"], blind["new"]))
    for k, n, c, rec in adds:
        pr = rec["printed"]
        print("      +%-11s %-34s ch%-8s 号%-9s 印面独立括号号%-4d 其中字母尾%-3d %s"
              % (c, k.split("|")[0][:34], k.split("|")[1], n,
                 pr["standalone"], pr["lettered"],
                 "页窗%s" % rec["have"] if rec["partial"] else ""))
    for k, n, c in rems:
        print("      -%-11s %-34s ch%-8s 号%-9s（旧判 %s，新放行）"
              % (c, k.split("|")[0][:34], k.split("|")[1], n, c))
    for k, n, co, cn in chg:
        print("      ~%-11s %-34s ch%-8s 号%-9s %s → %s"
              % (cn, k.split("|")[0][:34], k.split("|")[1], n, co, cn))
    bad_a = [(k, n) for k, rec in new.items() for n in rec["exempt"]
             if n in rec["verdicts"]]
    bad_b = [(k, n) for k, rec in new.items() for n in rec["registered_all"]
             if n in rec["verdicts"]]
    print("④ known_true 核：(a) 有「整块即 `(号)`」强证据却仍判毒 %d 处 ｜ "
          "(b) 已登记 known_book 却判毒 %d 处" % (len(bad_a), len(bad_b)))
    for k, n in (bad_a + bad_b)[:20]:
        print("      🔴 %s 号 %s" % (k, n))
    return 0 if not (bad_a or bad_b) else 3


def _why_key(r):
    """关因合写：`印面侧/契约侧`（腿开的那侧记 `开`）。"""
    if r["leg"]:
        return "开"
    return "%s/%s" % (r["why_printed"] or "开", r["why_contract"] or "开")


def _on_path(r):
    """腿开时是哪条证据证的：`printed` / `contract` / `both`。"""
    if r["leg_printed"] and r["leg_contract"]:
        return "both"
    return "printed" if r["leg_printed"] else "contract"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--filter", default=None, help="只跑书名含该子串的书")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--show-blind", action="store_true", help="列出失明章的号")
    ap.add_argument("--min-blind", type=int, default=1)
    ap.add_argument("--ratio-only", action="store_true",
                    help="只报「契约整数 ≥5 却被字母尾挤过 10%」的章（旧口径的方向性缺陷靶子）；"
                         "默认全报有失明号的章，因为改版后剩下的多是印面量不到")
    ap.add_argument("--samples", action="store_true",
                    help="对入报章再跑一趟锚点，打印每个失明号的锚点页与原块样本（取证用）")
    ap.add_argument("--dump", metavar="FILE", default=None,
                    help="把逐章裁决/诊断写成 JSONL（判据改版**前后各跑一次**，再 --ab 对比）")
    ap.add_argument("--ab", nargs=2, metavar=("OLD", "NEW"), default=None,
                    help="对比两份 --dump：按理由码给差集（新增判毒/新增放行）+ known_true 核")
    args = ap.parse_args()

    corpus = args.corpus or _uc_get("corpus_root")
    books = _books(corpus)
    if args.filter:
        books = [b for b in books if args.filter in os.path.basename(b)]
    if args.limit:
        books = books[:args.limit]
    if args.ab:
        return ab(*args.ab)

    print("# ⑭ lettered 失明普查（只读）")
    print("# 失明 = 腿关时「本该被这条腿点名、三趟裁决后却一个理由码都没拿到」的字母尾号；"
          "已被 unattested / bare-only 判毒的不算（setdefault 语义）")
    print("# 关因分侧记：printed-unmeasurable（页窗独立编号块<%d）｜ printed-lettered"
          "（印面字母尾>10%%，门关得对）｜ few-numeric（整数 tag<5）｜ ratio-drowned（靶子）"
          % _lta._PRINTED_CONVENTION_MIN)
    st = {"books": 0, "seen": 0, "ch": 0, "unread": 0, "partial": 0, "errs": 0,
          "blind": 0, "offpage": 0, "far": 0, "self": 0, "unmeas": 0,
          "exempt": 0, "caught": 0, "caught_ch": 0, "bare_off_ch": 0,
          "blind_ch": 0, "closed_ch": 0, "ratio_ch": 0}
    why_st = {}
    on_st = {}
    dumpf = open(args.dump, "w", encoding="utf-8") if args.dump else None
    for bk in books:
        ext = os.path.join(bk, "_extract")
        bs = os.path.join(ext, "book_structure")
        prime_chapter_kinds(ext)
        known = _lta.attested_numbers(ext)
        st["seen"] += 1
        rows = []
        for fn in _contract_files(bs):
            ck = _ch_key(fn)
            if not ck:
                continue
            try:
                r = chapter_row(ext, ck, known, show=args.samples)
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
            st["ch"] += 1
            st["exempt"] += len(r["exempt"])
            st["caught"] += len(r["caught"])
            st["caught_ch"] += 1 if r["caught"] else 0
            st["bare_off_ch"] += 1 if r["bare_leg_off"] else 0
            if r["leg"]:
                on_st[_on_path(r)] = on_st.get(_on_path(r), 0) + 1
            elif r["lettered_full"]:
                st["closed_ch"] += 1
            if r["why_contract"] == "ratio-drowned":
                st["ratio_ch"] += 1
            if r["blind"]:
                st["blind_ch"] += 1
                why_st[_why_key(r)] = why_st.get(_why_key(r), 0) + len(r["blind"])
        st["partial"] += sum(1 for r in rows if r["partial"])
        if dumpf is not None:
            rel = os.path.relpath(bk, corpus).replace("\\", "/")
            for r in rows:
                rec = dict(r)
                rec["book"] = rel
                dumpf.write(json.dumps(rec, ensure_ascii=False, sort_keys=True) + "\n")
        sel = [r for r in rows if r["blind"]]
        if args.ratio_only:
            sel = [r for r in sel if r["why_contract"] == "ratio-drowned"]
        risk = sum(len(r["blind"]) for r in sel)
        if risk < args.min_blind:
            continue
        st["books"] += 1
        st["blind"] += risk
        st["offpage"] += sum(len(r["offpage"]) for r in sel)
        st["far"] += sum(len(r["far"]) for r in sel)
        st["self"] += sum(len(r["self_anchored"]) for r in sel)
        st["unmeas"] += sum(len(r["unmeas"]) for r in sel)
        print("%-46s 失明%4d ｜ ±1外%4d 异地%4d 自证%4d 量不到%4d ｜ "
              "腿开%d/%d 章 独立块%d 字母%d 豁免%4d 点名%3d ｜ %s"
              % (os.path.basename(bk)[:46], risk,
                 sum(len(r["far"]) for r in sel),
                 sum(len(r["offpage"]) for r in sel),
                 sum(len(r["self_anchored"]) for r in sel),
                 sum(len(r["unmeas"]) for r in sel),
                 sum(1 for r in rows if r["leg"]), len(rows),
                 sum(r["printed"]["standalone"] for r in sel),
                 sum(r["printed"]["lettered"] for r in sel),
                 sum(len(r["exempt"]) for r in rows),
                 sum(len(r["caught"]) for r in rows),
                 " ".join(sorted({_why_key(r) for r in sel}))))
        if args.show_blind:
            for r in sel:
                print("      %-8s p%-12s tag%-4d 整数全%-4d 字母全%-4d 独立块%-4d 其中字母%-4d "
                      "腿%-3s(%s)%s ｜ 无括号锚点%-3s ±1外%-3s 自证%-3s → %s"
                      % (r["ch"], r["pages"], r["tags"], r["numeric_full"],
                         r["lettered_full"], r["printed"]["standalone"],
                         r["printed"]["lettered"],
                         "开" if r["leg"] else "关", _why_key(r),
                         " 页窗%s" % r["have"] if r["partial"] else "",
                         " ".join(r["no_paren"]), " ".join(r["far"]),
                         " ".join(r["self_anchored"]), " ".join(r["blind"][:60])))
        if args.samples:
            for r in sel:
                for n in r["blind"]:
                    loc = r["samples"].get(n, {})
                    for kind in ("paren", "bare"):
                        for pg, samples in sorted(loc.get(kind, {}).items()):
                            print("      dump %-8s %-7s %s p%-6d %s"
                                  % (r["ch"], n, kind, pg, " ⫽ ".join(samples)))
    if dumpf is not None:
        dumpf.close()
        print("dump（逐章裁决 + 印面体例）→ %s" % args.dump)
    print("-" * 78)
    print("语料 %s ｜ 书 %d ｜ 章 %d（读不到页窗 %d，页窗不全 %d）｜ 判据异常 %d"
          % (corpus, st["seen"], st["ch"], st["unread"], st["partial"], st["errs"]))
    print("lettered 腿：%d 章有字母尾号候选，其中门关 %d 章 ｜ 门开靠哪条证据 %s ｜ "
          "契约比例压死（旧口径靶子）%d 章"
          % (st["ch"], st["closed_ch"], on_st, st["ratio_ch"]))
    print("失明按关因（印面侧/契约侧）%s ｜ 有失明的章 %d" % (why_st, st["blind_ch"]))
    print("入报口径（--ratio-only=%s，min-blind>=%d）：书 %d ｜ 失明号 %d ｜ "
          "其中 ±1 外 %d ｜ 异地 %d ｜ 自证线索 %d ｜ 局部性量不到 %d"
          % (args.ratio_only, args.min_blind, st["books"], st["blind"],
             st["far"], st["offpage"], st["self"], st["unmeas"]))
    print("known_true 两档：字母尾号拿到「整块即编号」强证据（豁免）%d ｜ "
          "腿开时确实被这条腿点名的字母尾号 %d（%d 章）｜ bare-only 腿关的章 %d"
          % (st["exempt"], st["caught"], st["caught_ch"], st["bare_off_ch"]))


if __name__ == "__main__":
    main()
