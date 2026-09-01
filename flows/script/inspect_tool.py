#!/usr/bin/env python3
import os
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
import page_json
from page_json import PageJson

# -*- coding: utf-8 -*-
"""inspect_tool.py — consolidated inspection / raw-dump utilities for book-summarizer.

Subcommands:
  page <raw_dir> <page|start-end> [--formulas] [--raw]
        View one page (or a page range) of OCR JSON under <raw_dir>.
        <raw_dir> is typically the book's _extract/raw/ folder.

  raw  <extract_dir> <start> <end> [<out_file>]
        Merge OCR text for pages [start, end] into one y-sorted plaintext file.
        Writes <out_file>, or <extract_dir>/ch<start>_<end>_raw.txt by default.

  find <ch> <start> <end> <extract_dir>
        Scan pages [start, end] for N.S-N numbered items of chapter <ch>,
        with label / cross-reference detection (debug helper).
"""

import os, sys

import sys, os, json, re, argparse
from lib.regexlib import SEP_NUMERIC


def _ykey(t):
    poly = t.get("poly")
    if isinstance(poly, list) and poly and isinstance(poly[0], list) and len(poly[0]) >= 2:
        return poly[0][1]
    if isinstance(poly, list) and len(poly) >= 2 and isinstance(poly[1], (int, float)):
        return poly[1]
    return 1e9


# --------------------------------------------------------------------------
# page
# --------------------------------------------------------------------------
def dump_page(raw_dir, page_num, show_formulas=False, raw=False):
    path = os.path.join(raw_dir, f"page_{page_num:03d}.json")
    if not os.path.exists(path):
        print(f"[p{page_num}] NOT FOUND: {path}")
        return
    data = page_json.PageJson.load(path).data
    if raw:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return
    print(f"{'='*60}")
    print(f" PAGE {data['page']}  |  {len(data['formulas'])} formulas  {len(data['text'])} text blocks")
    print(f"{'='*60}")
    for t in data["text"]:
        txt = t.get("text", "").strip()
        if txt:
            print(txt)
    if show_formulas and data["formulas"]:
        print(f"\n--- Formulas ---")
        for i, f in enumerate(data["formulas"]):
            print(f"  [{i}] {f['latex']}")


# --------------------------------------------------------------------------
# raw
# --------------------------------------------------------------------------
def dump_raw(extract_dir, start, end, out_file=None):
    if out_file is None:
        out_file = os.path.join(extract_dir, f"ch{start}_{end}_raw.txt")
    blocks = []
    for p in range(start, end + 1):
        fp = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        with open(fp, "r", encoding="utf-8") as f:
            data = page_json.PageJson.load(os.path.join(extract_dir, f"page_{p:03d}.json")).data
        for t in data.get("text", []):
            txt = t.get("text", "").strip()
            if not txt:
                continue
            y = _ykey(t)
            blocks.append((p, y, txt))
    blocks.sort(key=lambda x: (x[0], x[1]))
    lines = []
    cur_page = None
    for p, y, txt in blocks:
        if p != cur_page:
            lines.append(f"\n===== PAGE {p} =====\n")
            cur_page = p
        lines.append(txt)
    text = "\n".join(lines) + "\n"
    with open(out_file, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"[OK] wrote {len(blocks)} blocks -> {out_file}")


# --------------------------------------------------------------------------
# find
# --------------------------------------------------------------------------
def find_items(ch, start, end, extract_dir):
    all_blocks = []
    for p in range(start, end + 1):
        fpath = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fpath):
            continue
        data = page_json.PageJson.load(fpath).data
        for t in data.get("text", []):
            txt = t.get("text", "").strip()
            if not txt:
                continue
            y = _ykey(t)
            all_blocks.append((p, y, txt))
    all_blocks.sort(key=lambda x: (x[0], x[1]))

    num_re = re.compile(r'(\d+)' + SEP_NUMERIC + r'\s*(\d+)' + SEP_NUMERIC + r'\s*(\d+)')
    cite_re = re.compile(r'见|由|根据|参考|参见|Cf\.')
    label_re = re.compile(r'定义|定理|引理|命题|推论|例|Example|Definition|Theorem|Lemma|Proposition|Corollary')

    all_matches = []
    for i, (p, y, txt) in enumerate(all_blocks):
        for m in num_re.finditer(txt):
            ch_num = int(m.group(1))
            if ch_num != ch:
                continue
            sec = int(m.group(2))
            num = int(m.group(3))
            key = f"{ch}.{sec}-{num}"
            before = txt[max(0, m.start()-15):m.start()]
            after = txt[m.end():m.end()+20]
            label = ''
            contexts = [before + after]
            if i > 0:
                contexts.append(all_blocks[i-1][2][-20:] + txt[:20])
            if i < len(all_blocks) - 1:
                contexts.append(txt[-20:] + all_blocks[i+1][2][:20])
            for ctx in contexts:
                lm = label_re.search(ctx)
                if lm:
                    label = lm.group()
                    break
            is_cite = bool(cite_re.search(before))
            tag = 'REF' if is_cite else label if label else 'NUM'
            snip = txt[max(0, m.start()-5):m.end()+30].replace('\n', ' ')
            all_matches.append((key, p, tag, m.group(), snip))

    seen = set()
    for key, p, tag, num_text, snippet in all_matches:
        if key not in seen:
            seen.add(key)
            print(f"{key:8s} p{p:3d} [{tag:4s}] {num_text:12s}  {snippet[:80]}")
    print(f"\nTotal unique: {len(seen)}")


def main():
    ap = argparse.ArgumentParser(
        description="Inspection / raw-dump utilities for book-summarizer.")
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_page = sub.add_parser('page', help='view OCR page(s)')
    p_page.add_argument('raw_dir')
    p_page.add_argument('page', help='page number or range start-end')
    p_page.add_argument('--formulas', '-f', action='store_true')
    p_page.add_argument('--raw', '-r', action='store_true')

    p_raw = sub.add_parser('raw', help='merge pages into y-sorted plaintext')
    p_raw.add_argument('extract_dir')
    p_raw.add_argument('start', type=int)
    p_raw.add_argument('end', type=int)
    p_raw.add_argument('out_file', nargs='?', default=None)

    p_find = sub.add_parser('find', help='scan numbered items (debug)')
    p_find.add_argument('ch', type=int)
    p_find.add_argument('start', type=int)
    p_find.add_argument('end', type=int)
    p_find.add_argument('extract_dir')

    args = ap.parse_args()

    if args.cmd == 'page':
        raw_dir = args.raw_dir
        if not os.path.isdir(raw_dir):
            raw_dir = os.path.join(os.getcwd(), args.raw_dir)
            if not os.path.isdir(raw_dir):
                print(f"ERROR: not found: {args.raw_dir}")
                sys.exit(1)
        if '-' in args.page:
            s, e = args.page.split('-')
            for p in range(int(s), int(e) + 1):
                dump_page(raw_dir, p, args.formulas, args.raw)
        else:
            dump_page(raw_dir, int(args.page), args.formulas, args.raw)
    elif args.cmd == 'raw':
        dump_raw(args.extract_dir, args.start, args.end, args.out_file)
    elif args.cmd == 'find':
        find_items(args.ch, args.start, args.end, args.extract_dir)


if __name__ == '__main__':
    main()
