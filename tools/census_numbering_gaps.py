# -*- coding: utf-8 -*-
"""跨书普查（**只读**）：编号完整性三条腿的现状与接闸 backlog 依据。

三条腿的判据都在 :mod:`lib.tag_attestation`，本工具只调用、不改盘：
1. ``numbering_gaps`` —— 逐章连续编号序列的**空洞**（纯契约树，不依赖几何）；
2. ``margin_anchor_audit(glued=False)`` —— 页池编号列双向对账（既往形态）；
3. ``margin_anchor_audit(glued=True)`` + ``column_separable`` —— 粘连锚点形态，
   以及「编号列与正文区是否可分」这一**前置条件**（不可分 → 本审计无权出结论）。

用途：把 ⑱ 的粘连方向 / 空洞判据 / 页池审计拼进 `gate_units` 之前，先看各书的
gaps / lost / unsupported 计数与**列可分率**——收紧判据会让并行在跑的书的旧 PASS
作废，没有这份普查不许接闸。

跑法（Windows 控制台 GBK 会乱码，重定向到 UTF-8 文件再读）::

    python tools/census_numbering_gaps.py > <书>/_extract/_census_numbering.txt 2>&1
    python tools/census_numbering_gaps.py --book "Introduction to Analytic"
"""
import argparse
import io
import json
import os
import sys
from pathlib import Path

_ROOT = None
for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = _c
        break
sys.path.insert(0, str(_ROOT))
import lib.boot  # noqa: E402
lib.boot.setup()  # noqa: E402

from lib.tag_attestation import (collect_contract_tags, margin_anchor_audit,  # noqa: E402
                                 numbering_gaps, page_anchor_index,
                                 page_geom_loader, number_column,
                                 column_separable)
from lib.user_config import get as _cfg_get  # noqa: E402


def _load(path):
    with io.open(str(path), encoding="utf-8") as f:
        return json.load(f)


def contract_files(bs_dir):
    return [p for p in sorted(bs_dir.iterdir())
            if p.is_file() and p.suffix == ".json"
            and (p.name.startswith("ch") or p.name.startswith("appendix"))]


def _page_dirs(ex_dir):
    """含 page_*.json 的目录（extract 根 + 按册分的子目录）。"""
    out = []
    for d in [ex_dir] + sorted(p for p in ex_dir.iterdir()
                               if p.is_dir() and not p.name.startswith("_")):
        try:
            if any(f.startswith("page_") and f.endswith(".json")
                   for f in os.listdir(str(d))):
                out.append(d)
        except OSError:
            continue
    return out


def census_book(book_dir, stats):
    ex = book_dir / "_extract"
    printed = False
    # 备份 / 临时目录（`_` 前缀）里也有 book_structure 副本，必须排除——否则同一章
    # 会被旧契约重复计数（实测把已回填的号又报成空洞）。
    sub = [p for p in sorted(ex.iterdir()) if p.is_dir() and not p.name.startswith("_")]
    for bs in [ex / "book_structure"] + [p / "book_structure" for p in sub]:
        if not bs.is_dir():
            continue
        loader = page_geom_loader(*[str(p) for p in _page_dirs(ex)])
        for cj in contract_files(bs):
            try:
                tree = _load(cj)
            except Exception as e:
                print("  %-14s LOAD-ERROR %s" % (cj.stem, e))
                continue
            tags = {str(n) for _k, n in collect_contract_tags(tree)}
            gaps = [g[0] for g in numbering_gaps(tree)]
            line = "  %-14s tags=%-4d gaps=%s" % (cj.stem, len(tags),
                                                 gaps if gaps else "-")
            stats["chapters"] += 1
            stats["gaps"] += len(gaps)
            if loader and tags:
                try:
                    lo, hi = int(tree["page_start"]), int(tree["page_end"])
                    col = number_column(page_anchor_index(loader, lo, hi), tags)
                    sep = column_separable(loader, lo, hi, col)
                    _l0, u0 = margin_anchor_audit(tree, loader, cj.stem)
                    l1, u1 = margin_anchor_audit(tree, loader, cj.stem, glued=True)
                    line += "  sep=%-1s lost(on)=%-2d unsup(off/on)=%d/%d" % (
                        "Y" if sep else "n", len(l1), len(u0), len(u1))
                    stats["sep" if sep else "overlap"] += 1
                    stats["lost"] += len(l1)
                    stats["unsup_off"] += len(u0)
                    stats["unsup_on"] += len(u1)
                except Exception as e:
                    line += "  AUDIT-ERROR %s" % e
            if not printed:
                print("\n### %s" % book_dir.relative_to(stats["_corpus"]))
                printed = True
            print(line)
    return printed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--book", default=None, help="substring filter on book dir name")
    args = ap.parse_args()
    corpus = Path(args.corpus or _cfg_get("corpus_root"))
    books = []
    for d in sorted(corpus.rglob("*")):
        if not d.is_dir() or not (d / "_extract" / "book_structure").is_dir():
            continue
        if args.book and args.book.lower() not in d.name.lower():
            continue
        if any(p.name == "_extract" for p in d.parents):
            continue                                    # 册目录不单独计
        books.append(d)
    print("corpus=%s  books=%d" % (corpus, len(books)))
    stats = {"_corpus": corpus, "chapters": 0, "gaps": 0, "sep": 0, "overlap": 0,
             "lost": 0, "unsup_off": 0, "unsup_on": 0}
    for b in books:
        census_book(b, stats)
    print("\nTOTALS chapters=%d  gaps=%d  column-separable=%d  overlapping=%d"
          "  lost(glued)=%d  unsup off/on=%d/%d"
          % (stats["chapters"], stats["gaps"], stats["sep"], stats["overlap"],
             stats["lost"], stats["unsup_off"], stats["unsup_on"]))


if __name__ == "__main__":
    main()
