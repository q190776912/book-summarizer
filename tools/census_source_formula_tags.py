# -*- coding: utf-8 -*-
"""只读普查：内容完整性闸门 ②b「编号列几何闸 + 噪声形态」的跨语料影响（2026-09-30）。

动因：`check_content_completeness._source_formula_tags` 新增两条与**契约侧同源**的
剔除（列外裸排块 = 公式内部残渣；`(0)`/前导零/节内重置书 ≥3 位纯数字 = 噪声），
判据是**收紧源真值集**——风险方向不是误报而是**漏报**：某个**真印**编号若被新判据
踢出源真值集、而契约里又恰好没有它，闸门就对它失明（内容丢失看不见）。

本工具对语料里每本书的每份分章契约，用**同一份页窗证据**跑两遍：
  old = 关掉两条新判据（`number_column`→None、`formula_tag_noise`→False）
  new = 现网判据
并只统计 `dropped = old - new`，其中 **`blind = dropped - 契约在账 tag`** 是必须
人工过目的子集（契约没有、源真值又不再声称 = 潜在失明）。

🔴 只读：不写任何书目录、不改配置、不跑流水线。

用法：
    python tools/census_source_formula_tags.py [--filter 子串] [--limit N]
        [--corpus DIR] [--show-blind]
"""
import argparse
import json
import os
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
import lib.boot as _boot
_boot.setup()

import lib.numbering as _ln                      # noqa: E402
import lib.tag_attestation as _lta               # noqa: E402
import attach_content as ac                      # noqa: E402
import check_content_completeness as ccc         # noqa: E402
from lib.user_config import get as _uc_get       # noqa: E402


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


def _tags_of(node):
    got = set()
    for b in ac._iter_blocks(node):
        if b.get("tag"):
            got.add(str(b["tag"]))
        for t in (b.get("tags") or []):
            got.add(str(t))
    return got


def _both(ext, node, key, ncomp, scope, letter, bare, page_dir):
    prefix = ""
    if scope == 2:
        if key.isdigit():
            prefix = key
        elif letter and len(key) == 1 and key.isalpha():
            prefix = key
    kw = dict(letter=letter, bare=bare, page_dir=page_dir,
              section_scoped=(scope == 3))
    new = ccc._source_formula_tags(ext, node.get("page_start"),
                                   node.get("page_end"), prefix, ncomp, **kw)
    _nc, _nz = _lta.number_column, _ln.formula_tag_noise
    _lta.number_column = lambda *a, **k: None
    _ln.formula_tag_noise = lambda *a, **k: False
    try:
        old = ccc._source_formula_tags(ext, node.get("page_start"),
                                       node.get("page_end"), prefix, ncomp, **kw)
    finally:
        _lta.number_column, _ln.formula_tag_noise = _nc, _nz
    return old, new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--filter", default=None, help="只跑书名含该子串的书")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--show-blind", action="store_true")
    args = ap.parse_args()

    corpus = args.corpus or _uc_get("corpus_root")
    books = _books(corpus)
    if args.filter:
        books = [b for b in books if args.filter in os.path.basename(b)]
    if args.limit:
        books = books[:args.limit]

    n_ch = n_drop = n_blind = 0
    print("# census: 编号列几何闸 + 噪声形态（old=关掉新判据 / new=现网）")
    for bk in books:
        ext = os.path.join(bk, "_extract")
        bs = os.path.join(ext, "book_structure")
        rows = []
        for f in _contract_files(bs):
            try:
                node = json.load(open(os.path.join(bs, f), encoding="utf-8"))
            except Exception as e:
                print("  !! %s/%s 读约失败：%r" % (os.path.basename(bk), f, e))
                continue
            key = str(node.get("key") or "")
            ncomp, scope, letter, bare = ac.formula_cfg(ext, key)
            if ncomp is None:
                continue                       # 未配 formula（Q 层 opt-in）→ 闸门不比对
            old, new = _both(ext, node, key, ncomp, scope, letter, bare,
                             ccc._node_page_dir(ext, node))
            n_ch += 1
            dropped = old - new
            if not dropped:
                continue
            got = _tags_of(node)
            blind = dropped - got
            rows.append((f, sorted(old), sorted(new), sorted(dropped),
                         sorted(blind)))
            n_drop += len(dropped)
            n_blind += len(blind)
        if rows:
            print("== %s" % os.path.basename(bk))
            for f, old, new, dropped, blind in rows:
                print("   %-18s old=%-3d new=%-3d dropped=%s  blind(契约无档)=%s"
                      % (f, len(old), len(new), dropped[:10],
                         blind[:10] if (blind or args.show_blind) else "[]"))
    print("--- 汇总：章 %d / 被剔除候选 %d / 其中契约无档（须人工过目）%d"
          % (n_ch, n_drop, n_blind))


if __name__ == "__main__":
    main()
