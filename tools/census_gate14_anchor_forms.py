# -*- coding: utf-8 -*-
r"""只读普查 + A/B：⑭ 的锚点形态折平（`lib.tag_attestation._label_forms`）会不会
**造出**印面上并不存在的 `(N)` 括号锚点（2026-10-30）。

动因（基础\数学分析 ch16 实测，任务 #49/#53）：旧折平用 `\\[a-zA-Z]+` **无差别删掉所有
宏名**，于是 `\left(\frac{1}{n\pi}\right)` 被折成 `(1n)`、`n \pi` 被折成 `n\pi`→`n`+`pi`。
`_PAREN_LABEL_RE` 的口径是「块内任意位置」，`1n` 这种**幻影 tag** 因此在页窗里拿到
「括号锚点」→ ⑭ 判不出毒；更糟的是 `tools/deregister_formula_tags.py --false-anchor`
看见「有括号锚点」就机械拒绝，把真幻影分流到 `--mispaired`（处方指向一个不存在的宿主）。

本工具**不出判据**，只做两件事：
  ① **快照**（`--dump`）：每章一行账，全部走 ⑭ 的出厂入口——tag 侧
     `collect_contract_tags` + `attested_numbers` 豁免、读页 `dir_page_loader(
     node_page_dir(...), ext)`、锚点 `anchor_locations`（唯一一趟匹配）、裁决
     `_condemned`。快照记「号 → 页 → 原块」全量 + 该章判毒理由码，A/B 才可比。
  ② **A/B**（`--ab A.jsonl B.jsonl`）：两份快照的差集，按三档报：
     - `锚点站点` 增减（哪个（号,页,块）没了）；
     - 🔴 **裁决变化**：`新增判毒` / `减少判毒`（按理由码分档）——这是唯一能区分
       「削掉幻影」与「误伤真编号」的量；
     - 比例腿的**连带**变化：`bare-only` / `lettered` 两条腿的分母由锚点集与
       `_standalone_labels` 决定，折平一收口就会顺带动到它们，必须单列。

口径纪律（与 `census_gate14_bare_blindness.py` 同一铁律）：
* 不自算等价口径，不改任何书目录/配置/判据；
* 「零命中」不算证据——A/B 必须同时证明**已知为真**的形态仍被认成锚点
  （`( 7 \\mathbf { c } ^ { \\prime } )` / `( 7 ^ { * } )` / 带空格分隔点的 `(2. 7. 5)` /
  字体命令直接包数字 `\\mathbf { 29 }` / 老式字体开关紧跟数字 `({\\it20.60})`），
  故快照另记 `known_true` 档：按章统计这五种形态的命中数，两遍快照该档**逐本相等**
  才算「只削假阳」。（`({\\it20.60})` 这一档就是它抓出了第一版白名单的 `\\b` 边界 bug。）

用法：
    python tools/census_gate14_anchor_forms.py --dump OUT.jsonl [--corpus DIR] [--filter 子串] [--limit N]
    python tools/census_gate14_anchor_forms.py --ab OLD.jsonl NEW.jsonl
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot  # noqa: E402
_boot.setup()

from data.book_structure.book_structure import (prime_chapter_kinds,  # noqa: E402
                                               resolve_chapter_json_path)
from census_gate14_bare_blindness import (_books, _ch_key,  # noqa: E402
                                         _contract_files)
import lib.tag_attestation as _lta  # noqa: E402
from lib.page_dir import node_page_dir as _node_page_dir  # noqa: E402
from lib.user_config import get as _uc_get  # noqa: E402

# 🔴 「已知为真」的形态（A/B 两侧命中数必须逐条相等，否则折平收紧误伤了真锚点）。
# 前三档 = 判据测试里逐条锁住的历史事故形态；后两档是**语料里真实存在**的壳包编号形态
# （`mathbf_bare` 那档原本是合成夹具 `\mathbf { 29 }`，全语料 0 命中 = 不是证据，故改成
# 按真实 OCR 形分档：字体命令直接包数字 / 老式字体开关后**紧跟**数字）。
_KNOWN_TRUE = {
    "bold_prime": r"[（(]\s*7\s*\\mathbf\s*\{?\s*c\s*\}?\s*\^?\s*\{?\s*\\prime",
    "caret_star": r"[（(]\s*7\s*\^\s*\{?\s*\*",
    "spaced_dots": r"[（(]\s*2\.\s*7\.\s*5\s*[)）]",
    "font_macro_num": r"\\(?:mathbf|boldsymbol|mathrm|mathsf|mathbb|mathtt|text)\s*\{?\s*[0-9]",
    "font_switch_num": r"\\(?:it|bf|rm|mit|sl)\s*[0-9]",
}
_KNOWN_TRUE_RE = {k: re.compile(v) for k, v in _KNOWN_TRUE.items()}


def _sites(locs):
    """anchor_locations 输出 → 可序列化的 ``{kind: {号: {页: [块]}}}``。"""
    return {"paren": {n: {str(p): b for p, b in d["paren"].items()}
                      for n, d in locs.items() if d["paren"]},
            "bare": {n: {str(p): b for p, b in d["bare"].items()}
                     for n, d in locs.items() if d["bare"]}}


def _known_true(loader, lo, hi):
    """页窗内五条「已知为真」形态各自 ``[块数, 仍产锚点的块数]``（按原块去重）。

    🔴 两档都要：**块数** = 语料里到底有没有这种形态（0 就是空枪，不能当证据）；
    **锚点数** = 「当前 `_label_forms` 还认不认它」——只有这一档随判据代码变化，
    A/B 比的是它。第一版白名单的 `\\b` 边界 bug 正是被 `font_switch_num` 的锚点档
    （A=有 / B=0）抓出来的。
    """
    n_blk = {k: 0 for k in _KNOWN_TRUE_RE}
    n_anch = {k: 0 for k in _KNOWN_TRUE_RE}
    seen = {k: set() for k in _KNOWN_TRUE_RE}
    for pg in range(int(lo), int(hi) + 1):
        for raw in (loader(pg) or []):
            s = str(raw or "").strip()
            if not s:
                continue
            for k, rx in _KNOWN_TRUE_RE.items():
                if s in seen[k] or not rx.search(s):
                    continue
                seen[k].add(s)
                n_blk[k] += 1
                for t in _lta._label_forms(s):
                    tt = t.replace("．", ".")
                    if (_lta._BARE_LABEL_RE.fullmatch(tt)
                            or _lta._PAREN_LABEL_RE.search(tt)
                            or _lta._SYMBOL_LABEL_RE.search(tt)):
                        n_anch[k] += 1
                        break
    return {k: [n_blk[k], n_anch[k]] for k in _KNOWN_TRUE_RE}


def chapter_row(ext, book_name, ch_key, known):
    tree = json.load(open(resolve_chapter_json_path(ext, ch_key), encoding="utf-8"))
    tags = [n for _k, n in _lta.collect_contract_tags(tree) if n not in known]
    try:
        lo, hi = int(tree.get("page_start")), int(tree.get("page_end"))
    except (TypeError, ValueError):
        return {"book": book_name, "ch": ch_key, "skip": "no-page-window"}
    loader = _lta.dir_page_loader(_node_page_dir(ext, tree, ch_key), ext)
    if not any(loader(p) for p in range(lo, hi + 1)):
        return {"book": book_name, "ch": ch_key, "skip": "no-page-json",
                "tags": len(tags)}
    locs = _lta.anchor_locations(loader, lo, hi)
    _tags2, kinds = _lta._condemned(tree, loader, known)
    return {"book": book_name, "ch": ch_key, "pages": "%d..%d" % (lo, hi),
            "tags": len(tags), "tag_list": sorted(set(tags)),
            "kinds": {n: r for n, r in sorted(kinds.items())},
            "n_paren_sites": sum(len(v) for d in locs.values()
                                 for v in d["paren"].values()),
            "n_bare_sites": sum(len(v) for d in locs.values()
                                for v in d["bare"].values()),
            "known_true": _known_true(loader, lo, hi),
            "anchors": _sites(locs)}


def dump(books, out_path, limit=0):
    rows = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for i, bk in enumerate(books):
            if limit and i >= limit:
                break
            ext = os.path.join(bk, "_extract")
            bs = os.path.join(ext, "book_structure")
            prime_chapter_kinds(ext)
            known = _lta.attested_numbers(ext)
            name = os.path.basename(bk)
            for fn in _contract_files(bs):
                ck = _ch_key(fn)
                if not ck:
                    continue
                try:
                    r = chapter_row(ext, name, ck, known)
                except Exception as e:
                    r = {"book": name, "ch": ck, "skip": "ERR:%s" % type(e).__name__}
                f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")
                rows += 1
    print("快照 %d 行 → %s" % (rows, out_path))


def _load(path):
    out = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            out["%s|%s" % (r["book"], r["ch"])] = r
    return out


def _site_set(row, kind):
    s = set()
    for n, pages in (row.get("anchors") or {}).get(kind, {}).items():
        for pg, blocks in pages.items():
            for b in blocks:
                s.add((n, pg, b))
    return s


def ab(path_a, path_b):
    """A=改前快照，B=改后快照。报锚点站点差集 + 裁决变化 + known_true 回归。"""
    A, B = _load(path_a), _load(path_b)
    keys = sorted(set(A) | set(B))
    print("# A/B：A=%s ｜ B=%s ｜ 章行 %d/%d" % (path_a, path_b, len(A), len(B)))
    only = set(A) ^ set(B)
    if only:
        print("!! 章集合不一致（快照口径漂移，先修这个）：%s" % sorted(only)[:10])
        return 1

    removed_paren, added_paren = {}, {}
    removed_bare, added_bare = {}, {}
    verdict_gains, verdict_freed, verdict_swapped = [], [], []
    kt_diff = {}
    tot = {"paren_removed": 0, "paren_added": 0, "bare_removed": 0,
           "bare_added": 0, "ch_sites_changed": 0}
    kt_tot_a = {k: [0, 0] for k in _KNOWN_TRUE}
    kt_tot_b = {k: [0, 0] for k in _KNOWN_TRUE}
    collateral = []          # 消失站点里「块内命令全是白名单壳」的 = 反向误伤，必须为 0

    for k in keys:
        a, b = A[k], B[k]
        kt_a, kt_b = a.get("known_true") or {}, b.get("known_true") or {}
        for kk in _KNOWN_TRUE:
            va, vb = list(kt_a.get(kk) or [0, 0]), list(kt_b.get(kk) or [0, 0])
            for i in (0, 1):
                kt_tot_a[kk][i] += va[i]
                kt_tot_b[kk][i] += vb[i]
            if va != vb:
                kt_diff.setdefault(k, {})[kk] = (va, vb)
        for kind, rm, ad in (("paren", removed_paren, added_paren),
                             ("bare", removed_bare, added_bare)):
            sa, sb = _site_set(a, kind), _site_set(b, kind)
            for n, pg, blk in sorted(sa - sb):
                rm.setdefault(k, []).append((n, pg, blk))
                cmds = re.findall(r"\\([a-zA-Z]+)", blk)
                if cmds and all(c in _lta._LATEX_STYLE_MACROS for c in cmds):
                    collateral.append((k, kind, n, pg, blk))
            for n, pg, blk in sorted(sb - sa):
                ad.setdefault(k, []).append((n, pg, blk))
        if (sa - sb) or (sb - sa):
            tot["ch_sites_changed"] += 1
        ka, kb = a.get("kinds") or {}, b.get("kinds") or {}
        for n in sorted(set(kb) - set(ka)):
            verdict_gains.append((k, n, kb[n]))
        for n in sorted(set(ka) - set(kb)):
            verdict_freed.append((k, n, ka[n]))
        for n in sorted(set(ka) & set(kb)):
            if ka[n] != kb[n]:
                verdict_swapped.append((k, n, ka[n], kb[n]))

    for nm, d in (("paren 锚点站点**消失**", removed_paren),
                  ("paren 锚点站点**新增**", added_paren),
                  ("bare 锚点站点**消失**", removed_bare),
                  ("bare 锚点站点**新增**", added_bare)):
        cnt = sum(len(v) for v in d.values())
        print("\n## %s：站点 %d 处 ｜ 涉及章 %d" % (nm, cnt, len(d)))
        if nm.startswith("paren 锚点站点**消失**"):
            tot["paren_removed"] = cnt
        elif nm.startswith("paren 锚点站点**新增**"):
            tot["paren_added"] = cnt
        elif nm.startswith("bare 锚点站点**消失**"):
            tot["bare_removed"] = cnt
        else:
            tot["bare_added"] = cnt
        for k in sorted(d)[:40]:
            for n, pg, blk in d[k][:8]:
                print("   %-42s %-12s 号%-8s p%-6s %s" % (k[:42], n, pg, "", blk[:70]))
            if len(d[k]) > 8:
                print("      … 该章另 %d 处" % (len(d[k]) - 8))

    print("\n## 裁决变化（唯一能区分「削幻影」与「误伤真编号」的量）")
    print("   新增判毒 %d ｜ 解除判毒 %d ｜ 理由码改变 %d"
          % (len(verdict_gains), len(verdict_freed), len(verdict_swapped)))
    for k, n, r in verdict_gains[:60]:
        print("   + %-10s %-42s 号%-8s %s" % (r, k, n, ""))
    for k, n, r in verdict_freed[:60]:
        print("   - %-10s %-42s 号%-8s %s" % (r, k, n, ""))
    for k, n, r1, r2 in verdict_swapped[:60]:
        print("   ~ %-10s→%-10s %-42s 号%s" % (r1, r2, k, n))

    print("\n## 反向误伤核（消失站点里，块内命令**全部**是白名单壳的）——必须为 0")
    print("   命中 %d 处" % len(collateral))
    for t in collateral[:25]:
        print("   %-46s %s 号%-8s p%-6s %s" % (t[0][:46], t[1], t[2], t[3], t[4][:70]))

    print("\n## known_true 形态（🔴 锚点档两侧必须相等；块数档证明这条腿不是空枪）")
    for kk in _KNOWN_TRUE:
        flag = "OK " if kt_tot_a[kk] == kt_tot_b[kk] else "DIFF"
        print("   %s %-16s 块数 A=%d B=%d ｜ 仍产锚点 A=%d B=%d"
              % (flag, kk, kt_tot_a[kk][0], kt_tot_b[kk][0],
                 kt_tot_a[kk][1], kt_tot_b[kk][1]))
    for k, d in sorted(kt_diff.items())[:30]:
        print("   !! %s %s" % (k, d))

    print("\n- 合计：paren 消失 %d ｜ paren 新增 %d ｜ bare 消失 %d ｜ bare 新增 %d ｜ "
          "站点有变的章 %d" % (tot["paren_removed"], tot["paren_added"],
                               tot["bare_removed"], tot["bare_added"],
                               tot["ch_sites_changed"]))
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--filter", default=None)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--dump", default=None)
    ap.add_argument("--ab", nargs=2, default=None, metavar=("OLD", "NEW"))
    args = ap.parse_args()
    if args.ab:
        return ab(args.ab[0], args.ab[1])
    corpus = args.corpus or _uc_get("corpus_root")
    books = _books(corpus)
    if args.filter:
        books = [b for b in books if args.filter in os.path.basename(b)]
    if not args.dump:
        print("需 --dump OUT.jsonl 或 --ab OLD NEW（只读，不落任何书目录）")
        return 2
    return dump(books, args.dump, args.limit) or 0


if __name__ == "__main__":
    sys.exit(main())
