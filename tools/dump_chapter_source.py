#!/usr/bin/env python3
"""dump_chapter_source.py — faithful source dump for write-source authoring.

Reads a chapter's page range from ``chapter_map.json`` and prints, per page,
the OCR text blocks in *reading order* (sorted by the top-Y of each block's
poly) plus the extracted formulas (latex). This is the "原文回归" source the
write-source flow requires: authors must write content from this, never from
``book_structure.json``'s ``name`` titles alone.

Usage:
    python tools/dump_chapter_source.py <extract_dir> <chapter> [--out FILE]

    <chapter>  : integer chapter number (1-based) as in chapter_map.json
    --out FILE : optionally write to a file instead of stdout (recommended for
                 large chapters to avoid terminal overflow)

Output layout per page:
    ===== PAGE <n> (chapter <c>) =====
    <text block 1>
    <text block 2>
    ...
    --- formulas on this page ---
    [f0] <latex>
    [f1] <latex>
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lib.boot  # noqa: E402
lib.boot.setup()
from data.page_json.page_json import PageJson  # noqa: E402
from chapter_map import find_chapter  # noqa: E402


def _top_y(poly_str):
    """Return the topmost Y coordinate from a poly string '[x0,y0,...]'."""
    try:
        nums = [float(x) for x in re.findall(r"-?\d+\.?\d*", poly_str)]
    except Exception:
        return 0.0
    if len(nums) < 8:
        # degenerate poly; fall back to whatever numbers we got
        return min(nums) if nums else 0.0
    ys = nums[1::2]  # y0,y1,y2,y3
    return min(ys)


def dump_chapter(extract_dir, chapter, out=None):
    # 归一化读取：兼容 {"chapters":[...]} 与 {"1":{...}} 两种 on-disk 形态
    info = find_chapter(extract_dir, chapter)
    start, end = int(info["start"]), int(info["end"])

    lines = []
    for pg in range(start, end + 1):
        fp = os.path.join(extract_dir, "page_%03d.json" % pg)
        if not os.path.exists(fp):
            lines.append(f"===== PAGE {pg} (MISSING) =====")
            continue
        pj = PageJson.load(fp)
        blocks = pj.text_blocks
        blocks_sorted = sorted(
            blocks, key=lambda b: _top_y(str(b.get("poly", "")))
        )
        lines.append(f"===== PAGE {pg} (chapter {chapter}) =====")
        for b in blocks_sorted:
            txt = (b.get("text") or "").strip()
            if txt:
                lines.append(txt)
        formulas = pj.formulas
        if formulas:
            lines.append("--- formulas on this page ---")
            for i, fo in enumerate(formulas):
                latex = (fo.get("latex") or "").strip()
                conf = fo.get("conf", "")
                if latex:
                    lines.append(f"[{i}] {latex}  (conf={conf})")
        lines.append("")  # blank separator

    text = "\n".join(lines)
    if out:
        with open(out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {len(text)} chars to {out}")
    else:
        print(text)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("extract_dir")
    ap.add_argument("chapter")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    dump_chapter(args.extract_dir, args.chapter, args.out)


if __name__ == "__main__":
    main()
