"""Build per-chapter writing bundles for Vakil (Rising Sea).

For each chapter, emit `<extract_dir>/chN_bundle.txt` containing:
  # SECTIONS   (from scan_skeleton three-level contract)
  # ITEMS      (numbered items N.M.K that must all land in the .md)
  # FIGURES    (figures belonging to this chapter, from figure_index.json)
  # RAW TEXT   (cleaned OCR text of the chapter pages, page-header noise stripped)

Subagents consume the bundle + the gold Chapter 1 template to produce a
faithful EN draft. Run:  python build_vakil_bundle.py <extract_dir> [ch ...]
"""
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
import figure_index
import chapter_map

import os, sys, re, json

from scan_skeleton import scan

# Known page-header / footer noise in the Vakil draft PDF.
NOISE_EXACT = {
    "november 18, 2017 draft",
    "the rising sea: foundations of algebraic geometry",
    "early (out-of-date) version of the rising sea: foundations of algebraic geometry",
    "foundations of algebraic geometry",
    "ravi vakil",
    "published by princeton university press",
    "(c) 2024 ravi vakil. published by princeton university press",
}
NOISE_SUBSTR = [
    "early (out-of-date) version of the rising sea",
    "published by princeton university press",
    "(c) 2024 ravi vakil",
]


def is_noise(s):
    t = s.strip().lower()
    if t in NOISE_EXACT:
        return True
    for sub in NOISE_SUBSTR:
        if sub in t:
            return True
    # isolated page number on its own line
    if re.fullmatch(r'\d{1,4}', t):
        return True
    return False


def main():
    extract_dir = sys.argv[1]
    want = [int(x) for x in sys.argv[2:]]
    cm = chapter_map.load_chapter_map_raw(os.path.join(extract_dir, 'chapter_map.json'))
    chapters = cm['chapters']
    rng = {c['ch']: (c['start'], c['end']) for c in chapters}
    fig_idx = None
    fp = os.path.join(extract_dir, 'figure_index.json')
    if os.path.exists(fp):
        try:
            fig_idx = figure_index.FigureIndex.load(fp).to_dict()
        except Exception:
            fig_idx = None

    for ch in (want or sorted(rng)):
        if ch not in rng:
            print('ch%d SKIP' % ch); continue
        start, end = rng[ch]
        # raw text, cleaned
        chunks = []
        for p in range(start, end + 1):
            fn = os.path.join(extract_dir, 'page_%03d.json' % p)
            if not os.path.exists(fn):
                continue
            d = page_json.PageJson.load(fn).data
            lines = []
            for t in d.get('text', []):
                s = (t.get('text') or '').strip()
                if not s or is_noise(s):
                    continue
                lines.append(s)
            if lines:
                chunks.append('=== PAGE %d ===' % p)
                chunks.extend(lines)
        raw = '\n'.join(chunks)

        # skeleton
        skel = scan(extract_dir, ch, start, end, 'three-level')

        # figures for this chapter
        figs = []
        if fig_idx:
            for fig in fig_idx:
                fp_ = fig.get('page') or fig.get('pdf_page')
                if isinstance(fp_, int) and start <= fp_ <= end:
                    figs.append(fig)

        # Dedupe ITEM/EXER rows by number (keep first occurrence) so the
        # writing contract lists each numbered item exactly once.
        seen_item, seen_exer = set(), set()
        items_dedup, exers_dedup = [], []
        for p, kind, num, title in skel:
            if kind == 'ITEM':
                if num in seen_item:
                    continue
                seen_item.add(num); items_dedup.append((p, num, title))
            elif kind == 'EXER':
                if num in seen_exer:
                    continue
                seen_exer.add(num); exers_dedup.append((p, num, title))

        out_path = os.path.join(extract_dir, 'ch%d_bundle.txt' % ch)
        with open(out_path, 'w', encoding='utf-8') as out:
            out.write('# Chapter %d bundle (pages %d-%d)\n' % (ch, start, end))
            out.write('# %s\n' % (next((c.get('title') for c in chapters if c['ch'] == ch), '')))
            out.write('\n# SECTIONS (%d)\n' % sum(1 for r in skel if r[1] == 'SEC'))
            for p, kind, num, title in skel:
                if kind == 'SEC':
                    out.write('SEC  %s  %s\n' % (num, title))
            out.write('\n# ITEMS (%d) — every one must land in the .md\n' % len(items_dedup))
            for p, num, title in items_dedup:
                out.write('ITEM %s  p%d  %s\n' % (num, p, title))
            out.write('\n# EXERCISES (lettered, %d) — kept inline in .md, not counted\n' % len(exers_dedup))
            for p, num, title in exers_dedup:
                out.write('EXER %s  p%d  %s\n' % (num, p, title))
            out.write('\n# FIGURES (%d)\n' % len(figs))
            for fig in figs:
                out.write('FIG  %s  page %s  %s\n' % (fig.get('file', fig.get('name', '')),
                                                     fig.get('page', fig.get('pdf_page', '')),
                                                     (fig.get('caption') or '')[:120]))
            out.write('\n# RAW TEXT\n')
            out.write(raw)
        print('ch%d -> %s (%d items, %d figs, %d raw chars)' % (
            ch, os.path.basename(out_path), len(items_dedup), len(figs), len(raw)))


if __name__ == '__main__':
    main()
