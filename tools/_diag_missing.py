"""Diagnostic: list per-section MISSING formula numbers for the failing
Kreyszig chapters, with the book-source snippet for each.

Reuses the Q-layer's real `build_sectioned` attribution but augments the
per-section comparison with the section key (which the shipped `_compare_sectioned`
drops from its rows).  Pure read-only; writes nothing.

Usage:
    python _diag_missing.py <book_dir> <chapter_csv>
e.g.
    python _diag_missing.py "D:/study/book/Kreyszig-..." "2,4,5,6,7,10"
"""
import json
import os
import re
import sys

# --- locate skill root (walk up from this file until SKILL.md) -------------
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = None
for _c in [HERE, *[os.path.join(HERE, *(['..'] * i)) for i in range(1, 6)]]:
    if os.path.exists(os.path.join(_c, 'SKILL.md')):
        ROOT = os.path.abspath(_c)
        break
if ROOT is None:
    ROOT = os.path.abspath(os.path.join(HERE, '..'))
for _p in (ROOT, os.path.join(ROOT, 'lib')):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import lib.boot as _boot
_boot.setup()

from verify.formula_tag.script.formula_tag import (
    build_formula_patterns,
    SourceFormulaIndex,
    _extract_summary_tags_sectioned,
)


def md_sections_of(md_file):
    with open(md_file, encoding='utf-8') as f:
        md = f.read()
    return re.findall(r'^##\s*§?\s*(\d+\.\d+)', md, re.M), md


def diag_chapter(book_dir, ch, summary_md):
    ext = os.path.join(book_dir, '_extract')
    cmap = json.load(open(os.path.join(ext, 'chapter_map.json'), encoding='utf-8'))
    rng = cmap[str(ch)]
    start, end = int(rng['start']), int(rng['end'])

    cfg = json.load(open(os.path.join(ext, 'verify_config.json'), encoding='utf-8'))
    fignore = set(cfg.get('formula', {}).get('ignore') or [])

    md_sections, _ = md_sections_of(summary_md)
    if not md_sections:
        print(f"  [WARN] {summary_md} has no ## § sections")
        return

    patterns = build_formula_patterns(1)  # Kreyszig type=1, ncomp=1
    src = SourceFormulaIndex(ext, patterns, False, fignore, ncomp=1)
    built = src.build_sectioned(ch, start, end, md_sections, ncomp=1)
    src_sec = built['_sectioned']

    tags_sec = _extract_summary_tags_sectioned(summary_md)
    covered_by_sec = {}
    for sec, t in tags_sec:
        covered_by_sec.setdefault(sec, set())
        if t.normalized:
            covered_by_sec[sec].add(t.normalized)

    print(f"\n===== Chapter {ch}  ({os.path.basename(summary_md)}) =====")
    print(f"  summary sections: {md_sections}")
    total_missing = 0
    for sec in md_sections:
        S = src_sec.get(sec, set())
        if not S:
            continue
        cov = covered_by_sec.get(sec, set())
        miss = sorted(S - cov - fignore, key=lambda x: (len(x), x))
        if miss:
            total_missing += len(miss)
            for n in miss:
                snip = src.source_text(n)
                print(f"  §{sec}  MISSING ({n})  源片段: {snip!r}")
    print(f"  --> total missing in this file: {total_missing}")


def main():
    book_dir = sys.argv[1]
    chapters = [c.strip() for c in sys.argv[2].split(',') if c.strip()]
    # CN files follow 第N章_*.md ; we diagnose CN (sections match EN)
    for ch in chapters:
        # find CN md
        cand = [f for f in os.listdir(book_dir)
                if f.startswith(f'第{ch}章') and f.endswith('.md')]
        if not cand:
            print(f"[skip] no CN md for chapter {ch}")
            continue
        diag_chapter(book_dir, int(ch), os.path.join(book_dir, cand[0]))


if __name__ == '__main__':
    main()
