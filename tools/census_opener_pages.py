"""census_opener_pages.py — 章首目录页免疫判据的跨书回归普查（只读，不写契约）。

为什么需要：`build_structure._compute_opener_pages` 决定「这一页是章扉页目录」，
被误判的页会让**该页上所有节号**改走回扫（正文节头重锚），是节锚点最上游的开关。
判据放宽（由「全部首现命中在带内」改成「带内首现 ≥K 条」）必须在全书目上校准，
否则 Evans 修好了、别的书静默改锚。

做法：对语料里每一本书、每一个章，跑到「扫完 SEC 行、算目录页」这一步即中止
（抛哨兵异常，条目抽取/内容挂载/落盘全部不执行），用**同一份 first_hit 证据**
分别按旧判据（带覆盖全部命中）与新判据（带内命中 ≥K）算目录页集合，凡新增的
「扉页」就逐节报告旧锚点（该页）vs 新锚点（`_find_numbered_heading_page` 回扫结果）。

用法：
    python tools/census_opener_pages.py                  # 全书目
    python tools/census_opener_pages.py --filter Evans   # 只跑路径含该子串的书
    python tools/census_opener_pages.py --limit 8

退出码：0 = 跑完（漂移内容由 agent 判读）；1 = 有书跑失败。
🔴 本工具不改任何文件：只 import 扫描链、只读 page_*.json / chapter_map.json /
verify_config.json，绝不写 book_structure 契约。
"""
import argparse
import glob
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "lib"))
import lib.boot as _boot  # noqa: E402
_boot.setup()

import build_structure as bs  # noqa: E402
from lib.user_config import get  # noqa: E402


class _Abort(Exception):
    """哨兵：SEC 扫描 + 目录页判据一旦算完就中断本章（不做条目抽取、不落盘）。"""


def _old_compute(first_hit, opener_k=3):
    """改动前的判据：同页首现 ≥K **且**目录带覆盖**全部**命中 y。"""
    cnt = {}
    for _num, row in first_hit.items():
        cnt[row[0]] = cnt.get(row[0], 0) + 1
    out = set()
    for p, c in cnt.items():
        if c < opener_k:
            continue
        ys = sorted(float(r[4]) for r in first_hit.values()
                    if r[0] == p and r[4] is not None)
        if not ys or bs._toc_band_bottom(ys) >= ys[-1] - 1e-6:
            out.add(p)
    return out


RESULTS = {"books": 0, "chapters": 0, "flip_pages": 0, "drift": 0, "skipped": []}


def census_one(ex, book_by_ch, rng, cm):
    """逐章跑到目录页判据处，返回 [(ch, page, [(num, old_pg, new_pg, title)])]。"""
    real = bs._compute_opener_pages
    hits = []

    def probe(first_hit, opener_k=3):
        new = real(first_hit, opener_k)
        old = _old_compute(first_hit, opener_k)
        for p in sorted(new - old):
            ys = sorted(float(r[4]) for r in first_hit.values()
                        if r[0] == p and r[4] is not None)
            band = bs._toc_band_bottom(ys)
            rows = []
            for num, row in first_hit.items():
                if row[0] != p or row[4] is None:
                    continue
                if float(row[4]) > band:
                    continue          # 带下命中 = 真节头，原位采用，不受影响
                end = rng[probe._ch][1]
                page_dir = probe._pd
                npg = bs._find_numbered_heading_page(
                    ex, num, p, end, min_y=row[4], page_dir=page_dir,
                    title_text=row[3]) or p
                if npg != p:
                    rows.append((num, p, npg, (row[3] or "")[:34]))
            hits.append((probe._ch, p, band, rows))
        raise _Abort()

    probe._ch = None
    probe._pd = None
    bs._compute_opener_pages = probe
    try:
        for ch, (start, end) in sorted(rng.items(), key=lambda kv: bs._chapter_sort_key(kv[0])):
            probe._ch = ch
            probe._pd = bs._resolve_page_dir(ex, ch)
            book = book_by_ch(ch)
            manual = None
            try:
                bs.build_chapter(ex, ch, start, end, book, cm, manual=manual)
            except _Abort:
                pass
            except Exception as exc:            # 本章扫描失败：记录后继续（不阻断普查）
                print("        ch%s 扫描失败: %r" % (bs.chapter_label(ch), exc))
    finally:
        bs._compute_opener_pages = real
    return hits


def _book_config(ex):
    """与 build_structure.main 同源的配置取法（ConfigLoader 失败则退读 verify_config）。"""
    cfg_path = os.path.join(ex, "verify_config.json")
    try:
        loader = bs.ConfigLoader(ex, os.path.dirname(ex.rstrip("/")) or ex)
        loader.require_complete()
        return loader.book, (lambda ch: loader.config_for_chapter(ch))
    except Exception:
        pass
    if not os.path.exists(cfg_path):
        return None, None
    import json
    with open(cfg_path, encoding="utf-8-sig") as fh:
        vcfg = json.load(fh)
    b = bs.BookConfig.from_dict(vcfg)
    return b, (lambda ch: b)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--filter", action="append", default=[])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--ch", default=None, help="调试用：只跑该章键")
    args = ap.parse_args()

    corpus = args.corpus or get("corpus_root")
    maps = sorted(set(
        glob.glob(os.path.join(corpus, "*", "*", "_extract", "chapter_map.json"))
        + glob.glob(os.path.join(corpus, "*", "*", "_extract", "*",
                                 "chapter_map.json"))))
    for needle in args.filter:
        maps = [m for m in maps if needle in m]
    if args.limit:
        maps = maps[:args.limit]

    failed = []
    for i, mp in enumerate(maps, 1):
        ex = os.path.dirname(mp)
        label = os.path.basename(os.path.dirname(ex))[:52]
        try:
            if not os.path.exists(os.path.join(ex, "_extraction_done.json")):
                print("[%d/%d] %-52s 无 _extraction_done，跳过" % (i, len(maps), label))
                RESULTS["skipped"].append(label)
                continue
            book, book_by_ch = _book_config(ex)
            if book is None:
                print("[%d/%d] %-52s 无 verify_config，跳过" % (i, len(maps), label))
                RESULTS["skipped"].append(label)
                continue
            try:
                from book_structure import prime_chapter_kinds
                prime_chapter_kinds(ex)
            except Exception:
                pass
            cm = bs.chapter_map.load_chapter_map_raw(mp)
            rng = bs._build_rng(cm)
            if args.ch:
                k = bs.norm_chapter_key(args.ch)
                rng = {k: rng[k]} if k in rng else {}
            hits = census_one(ex, book_by_ch, rng, cm)
            RESULTS["books"] += 1
            RESULTS["chapters"] += len(rng)
            nflip = sum(1 for _c, _p, _b, rows in hits)
            ndrift = sum(len(rows) for _c, _p, _b, rows in hits)
            RESULTS["flip_pages"] += nflip
            RESULTS["drift"] += ndrift
            tag = "扉页新增 %d 页 / 改锚 %d 节" % (nflip, ndrift) if hits else "无变化"
            print("[%d/%d] %-52s %2d章 %s" % (i, len(maps), label, len(rng), tag))
            for ch, p, band, rows in hits:
                if not rows:
                    print("        %-6s p%-4s band_bottom=%s → 无节改锚" %
                          (bs.chapter_label(ch), p, band))
                    continue
                for num, o, n, t in rows:
                    print("        %-6s §%-8s p%-4s → p%-4s  %r" %
                          (bs.chapter_label(ch), num, o, n, t))
        except Exception as exc:
            print("[%d/%d] %-52s FAILED: %r" % (i, len(maps), label, exc))
            failed.append(ex)

    print("\n共 %d 本 / %d 章；新增扉页 %d 处，改锚 %d 节；跳过 %d 本；失败 %d 本"
          % (RESULTS["books"], RESULTS["chapters"], RESULTS["flip_pages"],
             RESULTS["drift"], len(RESULTS["skipped"]), len(failed)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
