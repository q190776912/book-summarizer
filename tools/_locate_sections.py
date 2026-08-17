"""Locate the PDF page(s) where target section headings appear, by scanning
page_*.json text[] blocks for a heading line matching `<sec> <CapWord...>`.

Usage: python _locate_sections.py <book_dir> <chapter> <sec_csv>
e.g.    python _locate_sections.py <book> 2 2.9
"""
import json
import os
import re
import sys


def locate(book_dir, ch, secs):
    ext = os.path.join(book_dir, '_extract')
    cmap = json.load(open(os.path.join(ext, 'chapter_map.json'), encoding='utf-8'))
    rng = cmap[str(ch)]
    start, end = int(rng['start']), int(rng['end'])
    sec_re = {s: re.compile(r'^\s*' + re.escape(s) + r'\b\s*[A-Z\(]') for s in secs}
    found = {s: [] for s in secs}
    for pg in range(start, end + 1):
        fp = os.path.join(ext, f'page_{pg:03d}.json')
        if not os.path.exists(fp):
            continue
        try:
            data = json.load(open(fp, encoding='utf-8'))
        except Exception:
            continue
        for b in data.get('text', []) or []:
            t = b.get('text', '') if isinstance(b, dict) else ''
            if not t:
                continue
            for s in secs:
                if sec_re[s].match(t.strip()) and len(t.strip()) < 120:
                    found[s].append((pg, t.strip()))
    for s in secs:
        print(f"  §{s}: " + (", ".join(f"p{pg} {t!r}" for pg, t in found[s][:4])
                              or "NOT FOUND"))
    return found


def main():
    book_dir = sys.argv[1]
    ch = sys.argv[2]
    secs = [s.strip() for s in sys.argv[3].split(',') if s.strip()]
    locate(book_dir, int(ch), secs)


if __name__ == '__main__':
    main()
