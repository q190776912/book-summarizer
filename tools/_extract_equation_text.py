"""Extract the OCR text of a book-source numbered formula.

For each target (chapter, section, number) we scan the given page window,
find the STANDALONE `(N)` / `(Nx)` label block (the canonical Kreyszig formula
tag sitting on its own line), and print that block plus the preceding 1-3 text
blocks (which carry the displayed equation) and the following block.  This is
the raw material for faithfully transcribing the formula into LaTeX.

Windows are hard-coded for the 24 known-missing formulas (see TARGETS).
"""
import json
import os
import re
import sys

BOOK = sys.argv[1] if len(sys.argv) > 1 else \
    "D:/study/book/Kreyszig-Introductory-Functional-Analysis-with-Applications"

EXT = os.path.join(BOOK, '_extract')

# (ch, sec, number) -> [page_start, page_end]
TARGETS = [
    (2, '2.9', '1', 126, 141), (2, '2.9', '2', 126, 141),
    (2, '2.9', '3', 126, 141), (2, '2.9', '3b', 126, 141),
    (2, '2.9', '4', 126, 141), (2, '2.9', '5a', 126, 141),
    (2, '2.9', '5b', 126, 141), (2, '2.9', '6', 126, 141),
    (4, '4.11', '2', 291, 299), (4, '4.11', '4', 291, 299),
    (4, '4.11', '5', 291, 299), (4, '4.12', '16', 300, 313),
    (5, '5.2', '1', 322, 328), (5, '5.2', '2', 322, 328),
    (5, '5.3', '1a', 329, 341), (5, '5.3', '1b', 329, 341),
    (6, '6.2', '3', 345, 366), (6, '6.5', '1b', 367, 377),
    (7, '7.5', '2', 401, 408), (7, '7.6', '4', 409, 419),
    (7, '7.6', '5', 409, 419), (7, '7.6', '2a', 409, 419),
    (7, '7.6', '2b', 409, 419),
    (10, '10.7', '2', 578, 585),
]

_LABEL_RE = re.compile(r'^\s*[（(]\s*(\d+)([a-zA-Z]?)\s*[）)]\s*[.。]?\s*$')


def blocks_in_window(pg_start, pg_end):
    out = []
    for pg in range(pg_start, pg_end + 1):
        fp = os.path.join(EXT, f'page_{pg:03d}.json')
        if not os.path.exists(fp):
            continue
        try:
            data = json.load(open(fp, encoding='utf-8'))
        except Exception:
            continue
        for b in data.get('text', []) or []:
            t = b.get('text', '') if isinstance(b, dict) else ''
            if t:
                out.append((pg, t))
    return out


def main():
    for ch, sec, n, ps, pe in TARGETS:
        blocks = blocks_in_window(ps, pe)
        label_core = n.rstrip('abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ')
        label_suf = n[len(label_core):]
        hits = []
        for i, (pg, t) in enumerate(blocks):
            m = _LABEL_RE.match(t)
            if m and m.group(1) == label_core and m.group(2) == label_suf:
                # collect preceding 3 + this + following 1
                lo = max(0, i - 3)
                hi = min(len(blocks), i + 2)
                ctx = blocks[lo:hi]
                hits.append((i, ctx))
        print(f"\n##### Ch{ch} §{sec}  ({n})  — window p{ps}-{pe}  hits={len(hits)}")
        for hi_i, ctx in hits[:3]:
            for cpg, ct in ctx:
                tag = '  <<LABEL>>' if _LABEL_RE.match(ct) else ''
                print(f"    [p{cpg}] {ct!r}{tag}")


if __name__ == '__main__':
    main()
