"""census_chapter_map.py — chapter_map 检测判据的跨书回归普查（只读，不写盘）。

为什么需要：`build_chapter_map` 的 Mode B 判据（裸标题 / 附录带前缀章头）改动
会影响**全书目**的章起点检出。历史做法是改完只看手上这本书，回归全靠运气；本工具对
语料里每一本已落盘的 chapter_map，用**同一份 OCR 证据**跑「旧判据（关掉新规则）」与
「新判据」两遍，逐章比对 start/end/status，凡有漂移就列出来。

用法：
    python tools/census_chapter_map.py                 # 全书目（慢，建议 --limit/--filter）
    python tools/census_chapter_map.py --filter Evans  # 只跑路径含该子串的书
    python tools/census_chapter_map.py --limit 8

退出码：0 = 零漂移（或只列出预期内的漂移，由 agent 判读）；1 = 有书跑失败。
🔴 本工具不改任何文件：只 import 检测链、只读 page_*.json 与 chapter_map.json。
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

import importlib.util  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "build_chapter_map", os.path.join(_ROOT, "tools", "build_chapter_map.py"))
bcm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bcm)

from data.chapter_map.chapter_map import load_chapter_records  # noqa: E402
from lib.user_config import get  # noqa: E402


def _old_behaviour(on):
    """on=True 时把新规则关掉 → 逐字节回到改动前的判据（附录章只比裸标题）。"""
    if on:
        bcm._real_head = bcm.appendix_head_norm
        bcm.appendix_head_norm = lambda raw: None
    else:
        bcm.appendix_head_norm = bcm._real_head


def census_one(ex, recs):
    ev = bcm.scan_evidence(ex, quiet=True)
    _old_behaviour(True)
    old = bcm.compute_ranges(ex, recs, quiet=True, evidence=ev)
    _old_behaviour(False)
    new = bcm.compute_ranges(ex, recs, quiet=True, evidence=ev)
    diffs = []
    for ch in sorted(set(old[0]) | set(new[0]), key=bcm._ch_sort_key):
        o = (old[0].get(ch), old[1].get(ch), old[2].get(ch))
        n = (new[0].get(ch), new[1].get(ch), new[2].get(ch))
        if o != n:
            diffs.append((ch, o, n))
    return diffs, old[2], new[2]


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--filter", action="append", default=[],
                    help="只跑路径含该子串的书（可多次）")
    ap.add_argument("--limit", type=int, default=0, help="最多跑几本")
    ap.add_argument("--corpus", default=None, help="语料根目录（默认取 user_config）")
    args = ap.parse_args()

    corpus = args.corpus or get("corpus_root")
    maps = sorted(glob.glob(os.path.join(corpus, "*", "*", "_extract",
                                         "chapter_map.json"))
                  + glob.glob(os.path.join(corpus, "*", "*", "_extract", "*",
                                           "chapter_map.json")))
    for needle in args.filter:
        maps = [m for m in maps if needle in m]
    if args.limit:
        maps = maps[:args.limit]

    failed, drifted = [], []
    for i, mp in enumerate(maps, 1):
        ex = os.path.dirname(mp)
        try:
            recs = load_chapter_records(mp)
            if not recs:
                print("[%d/%d] %-60s 无章记录，跳过" % (i, len(maps), ex))
                continue
            diffs, old_st, new_st = census_one(ex, recs)
            sus_old = sum(1 for v in old_st.values() if v == "SUSPECT")
            sus_new = sum(1 for v in new_st.values() if v == "SUSPECT")
            und_old = sum(1 for v in old_st.values() if v == "UNDTECTED")
            und_new = sum(1 for v in new_st.values() if v == "UNDTECTED")
            tag = "漂移 %d 章" % len(diffs) if diffs else "零漂移"
            print("[%d/%d] %-58s %2d章 %-8s SUSPECT %d→%d UNDTECTED %d→%d"
                  % (i, len(maps), os.path.basename(os.path.dirname(ex))[:58],
                     len(recs), tag, sus_old, sus_new, und_old, und_new))
            for ch, o, n in diffs:
                print("        ch%-4s old=%s new=%s" % (ch, o, n))
                drifted.append((ex, ch))
        except Exception as exc:            # 单本失败不阻断普查
            print("[%d/%d] %-58s FAILED: %r" % (i, len(maps), ex, exc))
            failed.append(ex)

    print("\n共 %d 本；有漂移 %d 章；跑失败 %d 本"
          % (len(maps), len(drifted), len(failed)))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
