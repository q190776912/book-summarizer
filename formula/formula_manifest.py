#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_formula_manifest.py
===========================
Parse a chapter markdown summary and emit a per-formula manifest
(``formulas.json``) used for fidelity verification against the book source.

For every math occurrence (display ``$$...$$`` -- including blockquote
``> $$`` blocks -- and inline ``$...$``) the extractor records:

  * ord            : 1-based occurrence index within the chapter
  * kind           : "display" | "inline"
  * summary_label  : ``\\tag{X}`` value, or null when the formula is unlabeled
  * section        : current heading number (e.g. "2.2"), or null
  * heading        : full current heading text
  * line           : 1-based line number of the formula (for navigation)
  * content_summary: normalized latex (``\\tag`` stripped, whitespace collapsed)

Optional writer annotations (captured during summarization) attach the
*book-side* truth so verification is a trivial equality check instead of a
fragile auto-alignment:

    <!-- book:2.6 p62 y0.33 §2.2 Thm2.2 -->

  book_label : the TRUE label in the book (null if the book formula is unlabeled)
  p62        : page number in the book PDF
  y0.33      : vertical position on the page (0.0 top -> 1.0 bottom)
  §2.2 Thm2.2: free-text context (Theorem/Example name, etc.)

The annotation is attached to the NEXT formula record.

Usage:
    python formula_manifest.py <chapter.md> [-o formulas.json]
                                  [--chapter-map chapter_map.json --chapter N]
"""
import argparse
import json
import os
import re
import sys

HEADING_RE = re.compile(r'^(#{1,6})\s+(.*)$')
NUM_RE = re.compile(r'(\d+(?:\.\d+)*)')  # first number segment anywhere in heading
TAG_RE = re.compile(r'\\tag\{((?:[^{}]|\\[{}])*)\}')
INLINE_RE = re.compile(r'(?<!\\)\$([^$\n]+?)(?<!\\)\$')
BOOKANN_RE = re.compile(
    r'book:\s*([\d.]+)?\s*(?:p(\d+))?\s*(?:y([\d.]+))?\s*(.*?)\s*-->'
)


def strip_bq(line: str) -> str:
    """Remove a single leading blockquote marker (``> `` or ``>``)."""
    return re.sub(r'^>\s?', '', line)


def normalize(content: str) -> str:
    s = TAG_RE.sub('', content)
    s = s.replace('\n', ' ')
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def extract_between_fences(raw: str) -> str:
    """Content between the first and last ``$$`` on a single line."""
    first = raw.find('$$')
    last = raw.rfind('$$')
    if first == last:
        return ''
    return raw[first + 2:last]


def parse(path: str):
    with open(path, encoding='utf-8') as f:
        lines = f.read().split('\n')
    n = len(lines)
    headings = []  # (level, num, text)
    cur_num = None
    cur_heading = None
    records = []
    pending_book = None
    i = 0
    while i < n:
        raw = lines[i]
        stripped = raw.strip()

        # --- heading ---
        m = HEADING_RE.match(raw)
        if m:
            level = len(m.group(1))
            htext = m.group(2).strip()
            num = None
            mm = NUM_RE.search(htext)
            if mm:
                num = mm.group(1)
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, num, htext))
            cur_num, cur_heading = num, htext
            i += 1
            continue

        # --- writer book annotation ---
        if stripped.startswith('<!--'):
            bm = BOOKANN_RE.search(raw)
            if bm:
                pending_book = {
                    'book_label': bm.group(1),
                    'page': int(bm.group(2)) if bm.group(2) else None,
                    'pos_y': float(bm.group(3)) if bm.group(3) else None,
                    'context': (bm.group(4).strip() or None),
                }
                i += 1
                continue

        # --- display math ---
        if '$$' in stripped:
            bq = stripped.startswith('>')
            if stripped.count('$$') >= 2:
                content = extract_between_fences(strip_bq(raw) if bq else raw)
                add_record(records, 'display', content, i + 1,
                           cur_num, cur_heading, pending_book)
                pending_book = None
                i += 1
                continue
            # multi-line block
            opener = strip_bq(raw) if bq else raw
            start_content = opener.split('$$', 1)[1] if '$$' in opener else ''
            buf = []
            j = i + 1
            closing = None
            while j < n:
                l = lines[j]
                if '$$' in l.strip():
                    closing = l
                    break
                buf.append(strip_bq(l) if bq else l)
                j += 1
            end_content = ''
            if closing is not None:
                cl = strip_bq(closing) if bq else closing
                end_content = cl.split('$$', 1)[0]
            parts = [p for p in [start_content] + buf + [end_content] if p]
            content = '\n'.join(parts)
            add_record(records, 'display', content, i + 1,
                       cur_num, cur_heading, pending_book)
            pending_book = None
            i = (j + 1) if closing is not None else j
            continue

        # --- inline math ---
        if '$' in raw and '$$' not in stripped:
            for mm in INLINE_RE.finditer(raw):
                add_record(records, 'inline', mm.group(1), i + 1,
                           cur_num, cur_heading, None)
            i += 1
            continue

        i += 1

    return records


def add_record(records, kind, content, line, num, heading, pending_book):
    tag = TAG_RE.search(content)
    rec = {
        'ord': len(records) + 1,
        'kind': kind,
        'summary_label': tag.group(1) if tag else None,
        'section': num,
        'heading': heading,
        'line': line,
        'content_summary': normalize(content),
    }
    if pending_book:
        rec['book_label'] = pending_book.get('book_label')
        rec['page'] = pending_book.get('page')
        rec['pos_y'] = pending_book.get('pos_y')
        rec['context'] = pending_book.get('context')
    records.append(rec)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('md')
    ap.add_argument('-o', '--out', default=None)
    ap.add_argument('--chapter-map', default=None)
    ap.add_argument('--chapter', default=None, type=int)
    args = ap.parse_args()

    records = parse(args.md)
    manifest = {
        'chapter_file': os.path.basename(args.md),
        'formulas': records,
    }
    if args.chapter_map and args.chapter:
        try:
            cm = json.load(open(args.chapter_map, encoding='utf-8'))
            info = cm.get(str(args.chapter)) or cm.get(args.chapter)
            if info:
                manifest['page_range'] = [info.get('start'), info.get('end')]
                manifest['chapter_name'] = info.get('name_en') or info.get('name')
        except Exception as e:
            sys.stderr.write(f'warn: chapter_map: {e}\n')

    out = args.out or (os.path.splitext(args.md)[0] + '_formulas.json')
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    labeled = sum(1 for r in records if r.get('summary_label'))
    withbook = sum(1 for r in records if r.get('book_label') is not None)
    print(f'wrote {out}: {len(records)} formulas '
          f'({labeled} labeled, {withbook} with book_label)')


if __name__ == '__main__':
    main()
