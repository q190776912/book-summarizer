#!/usr/bin/env python3
"""Empirical probe of a book's formula-label shapes.

Reads every chapter's page_*.json `text[]` blocks and classifies the
parenthesis-wrapped number tokens (genuine formula labels) by component count.
Also checks whether the first component of a 3-component label equals the
current chapter (→ scope=2 chapter-prefix guard) or whether 2-component labels
dominate (→ scope=2 with depth=2) etc.

Usage:
    python tools/_scan_formula_shapes.py <book_dir> [--all | <ch> ...]
Prints a per-chapter summary plus a whole-book tally.
"""
import json
import os
import re
import sys

PAREN_3 = re.compile(r'[（(]\s*(\d+)[.\-·,]\s*(\d+)[.\-·,]\s*(\d+)(?:[a-zA-Z])?\s*[）)]')
PAREN_2 = re.compile(r'[（(]\s*(\d+)[.\-·,]\s*(\d+)(?:[a-zA-Z])?\s*[）)]')
PAREN_1 = re.compile(r'[（(]\s*(\d+)(?:[a-zA-Z])?\s*[）)]')


def load_map(book_dir):
    p = os.path.join(book_dir, '_extract', 'chapter_map.json')
    with open(p, encoding='utf-8') as f:
        data = json.load(f)
    if 'chapters' in data:
        return data['chapters']
    # flat {"1": {...}}
    return [{'ch': int(k), **v} for k, v in data.items()]


def scan_chapter(ext_dir, ch, start, end):
    counts = {'p3': 0, 'p2': 0, 'p1': 0}
    p3_ch_match = 0
    p3_total = 0
    for pg in range(int(start), int(end) + 1):
        fp = os.path.join(ext_dir, f'page_{pg:03d}.json')
        if not os.path.exists(fp):
            continue
        try:
            with open(fp, encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            continue
        for b in data.get('text', []) or []:
            t = b.get('text', '') if isinstance(b, dict) else ''
            if not t:
                continue
            for m in PAREN_3.finditer(t):
                counts['p3'] += 1
                p3_total += 1
                if int(m.group(1)) == ch:
                    p3_ch_match += 1
            for _ in PAREN_2.finditer(t):
                counts['p2'] += 1
            for _ in PAREN_1.finditer(t):
                counts['p1'] += 1
    return counts, p3_ch_match, p3_total


def main():
    if len(sys.argv) < 2:
        print('usage: _scan_formula_shapes.py <book_dir> [--all | <ch> ...]')
        sys.exit(1)
    book_dir = sys.argv[1]
    ext_dir = os.path.join(book_dir, '_extract')
    chapters = load_map(book_dir)
    sel = set()
    if '--all' in sys.argv:
        sel = {c['ch'] for c in chapters}
    else:
        for a in sys.argv[2:]:
            try:
                sel.add(int(a))
            except ValueError:
                pass
    tot = {'p3': 0, 'p2': 0, 'p1': 0}
    tot_mat = 0
    tot_p3 = 0
    for c in sorted(chapters, key=lambda x: x['ch']):
        if c['ch'] not in sel:
            continue
        ch = c['ch']
        start = c.get('start')
        end = c.get('end')
        cc, mat, tp3 = scan_chapter(ext_dir, ch, start, end)
        for k in tot:
            tot[k] += cc[k]
        tot_mat += mat
        tot_p3 += tp3
        print(f"ch{ch:>2} (pdf {start:>3}-{end:<3}): "
              f"3-comp={cc['p3']:>4}  2-comp={cc['p2']:>4}  1-comp={cc['p1']:>4}"
              f"  | 3-comp第一章匹配 {mat}/{tp3}"
              if tp3 else f"ch{ch:>2}: 3-comp={cc['p3']:>4} 2-comp={cc['p2']:>4} 1-comp={cc['p1']:>4}")
    print('-' * 64)
    print(f"WHOLE-BOOK: 3-comp={tot['p3']:>5}  2-comp={tot['p2']:>5}  "
          f"1-comp={tot['p1']:>5}")
    if tot_p3:
        print(f"3-comp 标签中第一章前缀匹配: {tot_mat}/{tot_p3} "
              f"({100.0*tot_mat/tot_p3:.1f}%)")


if __name__ == '__main__':
    main()
