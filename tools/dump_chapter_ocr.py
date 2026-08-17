#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
dump_chapter_ocr.py — authoring aid for book-summarizer.

Dumps the readable OCR text + formula LaTeX for a chapter's page range,
in reading order (sorted by poly Y then X). This is the ground-truth source
for faithful chapter authoring (do NOT copy OCR formula LaTeX — rewrite it).

Usage:
    python tools/dump_chapter_ocr.py <book_dir> <chapter_number> [--pages 16-23]
    python tools/dump_chapter_ocr.py <book_dir> --pages 16-23

If chapter_number is given, the page range is read from _extract/chapter_map.json.
Output goes to stdout (pipe to a file if you like).
"""
import json
import os
import sys
import glob


def sort_key(block):
    poly = block.get("poly") or block.get("bbox") or [0, 0, 0, 0, 0, 0, 0, 0]
    # poly = [x0, y0, x1, y1, x2, y2, x3, y3] (4 corners). Use top-left y, then x.
    y = poly[1] if len(poly) >= 2 else 0
    x = poly[0] if len(poly) >= 1 else 0
    return (y, x)


def load_pages(book_dir, chapter):
    extract_dir = os.path.join(book_dir, "_extract")
    cmap_path = os.path.join(extract_dir, "chapter_map.json")
    with open(cmap_path, encoding="utf-8") as f:
        cmap = json.load(f)
    ch = None
    for c in cmap.get("chapters", []):
        if str(c.get("ch")) == str(chapter):
            ch = c
            break
    if ch is None:
        raise SystemExit(f"chapter {chapter} not found in chapter_map.json")
    return ch.get("start"), ch.get("end")


def dump_range(book_dir, start, end):
    extract_dir = os.path.join(book_dir, "_extract")
    lines = []
    for pno in range(int(start), int(end) + 1):
        pf = os.path.join(extract_dir, f"page_{pno:03d}.json")
        if not os.path.exists(pf):
            lines.append(f"\n===== PAGE {pno:03d} (MISSING) =====\n")
            continue
        with open(pf, encoding="utf-8") as f:
            d = json.load(f)
        lines.append(f"\n===== PAGE {pno:03d} =====")
        # formulas first (so we can cross-check math)
        formulas = d.get("formulas", [])
        if formulas:
            flines = []
            for fo in formulas:
                bbox = fo.get("bbox")
                latex = fo.get("latex", "")
                flines.append(f"    [F] bbox={bbox} :: {latex}")
            lines.append("  --- formulas ---")
            lines.extend(flines)
        texts = d.get("text", [])
        texts_sorted = sorted(texts, key=sort_key)
        lines.append("  --- text ---")
        for t in texts_sorted:
            txt = t.get("text", "")
            lines.append(f"    {txt}")
    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    if len(args) < 2:
        raise SystemExit(__doc__)
    book_dir = args[0]
    chapter = None
    pages_arg = None
    i = 1
    while i < len(args):
        if args[i] == "--pages":
            pages_arg = args[i + 1]
            i += 2
        else:
            if chapter is None:
                chapter = args[i]
            i += 1
    if pages_arg:
        a, b = pages_arg.split("-")
        start, end = int(a), int(b)
    else:
        start, end = load_pages(book_dir, chapter)
    out = dump_range(book_dir, start, end)
    print(out)


if __name__ == "__main__":
    main()
