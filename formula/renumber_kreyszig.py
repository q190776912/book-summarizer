#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
renumber_kreyszig.py
====================
For every RENUMBERED match from reconcile_kreyszig, change the summary
``\\tag{summary_label}`` to ``\\tag{book_label}`` within the matching
``## §C.S`` section.  Only display-math tags are rewritten; inline math is left
untouched.  Original markdowns are copied to ``_recon/md_bak/`` before editing.

Usage:
    python renumber_kreyszig.py --md-root D:/study/book/基础/泛函分析导论及应用 \
        --extract-dir _extract --chapter-map _extract/chapter_map.json
"""
import argparse
import glob
import json
import os
import re
import shutil
import sys

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL_ROOT)

from formula.reconcile_kreyszig import build_book_manifest, build_summary_manifest, align_section

SECTION_HEAD_RE = re.compile(r'^(#{1,6})\s+§\s*(\d+\.\d+)')
TAG_RE = re.compile(r'\\tag\{([^}]+)\}')


def compute_renumber_map(chapter, extract_dir, cmap, md_root):
    """Return list of {section, summary_label, book_label} for RENUMBERED matches."""
    # use_position_labels=True: the OCR equation numbers are unreliable
    # (scrambled / mis-attached); relabel each displayed formula by its
    # reading-order position within the section, which equals the true
    # consecutive Kreyszig number.
    bm = build_book_manifest(chapter, cmap, extract_dir, use_position_labels=True)
    md_files = glob.glob(os.path.join(md_root, f'第{chapter}章_*.md'))
    if not md_files:
        return []
    sm = build_summary_manifest(md_files[0])
    renumbers = []
    for sec, bl in bm['sections'].items():
        sl = sm['sections'].get(sec, [])
        matches, _, _ = align_section(bl, sl, 0.28)
        for bk, s, kind, _sc in matches:
            if kind != 'RENUMBERED':
                continue
            renumbers.append({
                'section': sec,
                'summary_label': s['label'],
                'book_label': bk['label'],
            })
    return renumbers


def renumber_md(md_path, renumbers):
    """Apply renumber mapping to a markdown file. Returns count of replacements."""
    with open(md_path, encoding='utf-8') as f:
        text = f.read()
    # split on section headings, keeping the heading line in each chunk
    parts = re.split(r'(?m)^(#{1,6}\s+§\s*\d+\.\d+.*)$', text)
    # parts: [pre-heading, heading, body, heading, body, ...]
    if not parts:
        return 0
    # build lookup: section -> {summary_label: book_label}
    lookup = {}
    for r in renumbers:
        lookup.setdefault(r['section'], {})[str(r['summary_label'])] = str(r['book_label'])

    def replace_in_display_block(block, section):
        mapping = lookup.get(section)
        if not mapping:
            return block
        # find \tag{X} inside display math only (between $$...$$ or > $$...$$)
        def sub_tag(m):
            full = m.group(0)
            label = m.group(1)
            if label in mapping:
                return full.replace(f'\\tag{{{label}}}', f'\\tag{{{mapping[label]}}}')
            return full
        return TAG_RE.sub(sub_tag, block)

    out = [parts[0]]  # pre-heading text
    total = 0
    i = 1
    while i < len(parts):
        heading = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ''
        m = SECTION_HEAD_RE.match(heading)
        sec = m.group(2) if m else None
        if sec and sec in lookup:
            new_body = replace_in_display_block(body, sec)
            count = new_body.count('\\tag{') - body.count('\\tag{')
            total += abs(count)
            out.append(heading + new_body)
        else:
            out.append(heading + body)
        i += 2
    new_text = ''.join(out)
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(new_text)
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--md-root', required=True)
    ap.add_argument('--extract-dir', required=True)
    ap.add_argument('--chapter-map', required=True)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    cmap = json.load(open(args.chapter_map, encoding='utf-8'))
    bk_root = args.md_root
    out_dir = os.path.join(SKILL_ROOT, 'formula', '_recon', 'md_bak')
    os.makedirs(out_dir, exist_ok=True)

    all_maps = {}
    total_replaced = 0
    for ch in sorted(int(k) for k in cmap):
        ren = compute_renumber_map(ch, args.extract_dir, cmap, bk_root)
        all_maps[ch] = ren
        md_files = glob.glob(os.path.join(bk_root, f'第{ch}章_*.md'))
        if not md_files:
            print(f'ch{ch}: no md file')
            continue
        md = md_files[0]
        # backup
        shutil.copy2(md, os.path.join(out_dir, os.path.basename(md) + '.bak'))
        if args.dry_run:
            print(f'ch{ch}: {len(ren)} renumbers (dry-run)')
        else:
            n = renumber_md(md, ren)
            total_replaced += n
            print(f'ch{ch}: {len(ren)} renumbers, {n} tag replacements')

    map_file = os.path.join(SKILL_ROOT, 'formula', '_recon', 'renumber_map.json')
    with open(map_file, 'w', encoding='utf-8') as f:
        json.dump(all_maps, f, ensure_ascii=False, indent=1)
    print(f'wrote {map_file}')
    if not args.dry_run:
        print(f'TOTAL tag replacements: {total_replaced}')


if __name__ == '__main__':
    main()
