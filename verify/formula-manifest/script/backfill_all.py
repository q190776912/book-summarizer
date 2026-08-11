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
import chapter_map

# -*- coding: utf-8 -*-
"""
backfill_all.py
===============
Bulk backfill driver for an already-summarized book.

For every chapter in chapter_map.json it runs, in the book root directory:
    formula_manifest.py  <ChapterN_*.md>  ->  _extract/<base>_formulas.json
    build_book_manifest.py --chapter N    ->  _extract/book_chN_formulas.json
    fill_book_labels.py   summary book     ->  _extract/<base>_filled.json
    diff_formula_manifest.py filled book    (capture hard errors)

Both EN and CN chapter files are processed.  A summary report lists, per
chapter, any HARD diff errors (FABRICATED / MISSING / ORDER_MISMATCH /
PAGE_RANGE) so the LLM can review only the flagged chapters.

Usage:
    python backfill_all.py --book-root "D:/.../Koopman Operator" --extract-dir _extract
"""
import argparse
import glob
import json
import os
import subprocess
import sys

PY = r'D:/anaconda3/envs/pdfextract/python.exe'
# Constructors live in their own per-JSON dirs under data/ (chapter_map-style):
#   data/formula_manifest/formula_manifest.py
#   data/build_book_manifest/build_book_manifest.py
#   data/fill_book_labels/fill_book_labels.py
# The diff verifier is a flow script in verify/formula-manifest/script/.
FM = os.path.join(_ROOT, 'data', 'formula_manifest', 'formula_manifest.py')
BM = os.path.join(_ROOT, 'data', 'build_book_manifest', 'build_book_manifest.py')
FL = os.path.join(_ROOT, 'data', 'fill_book_labels', 'fill_book_labels.py')
DIFF = os.path.join(_ROOT, 'verify', 'formula-manifest', 'script', 'diff_formula_manifest.py')


def run(cmd, cwd):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--book-root', required=True)
    ap.add_argument('--extract-dir', default='_extract')
    args = ap.parse_args()
    root = args.book_root
    ex = args.extract_dir
    cm_path = os.path.join(root, ex, 'chapter_map.json')
    cm = chapter_map.load_chapter_map_raw(cm_path)

    report = []
    for key in sorted(cm.keys(), key=lambda k: int(k)):
        n = int(key)
        en = glob.glob(os.path.join(root, f'Chapter{n}_*.md'))
        cn = glob.glob(os.path.join(root, f'第{n}章_*.md'))
        en = [os.path.basename(x) for x in en if 'formulas' not in x]
        cn = [os.path.basename(x) for x in cn if 'formulas' not in x]
        chapter_errors = []

        # book manifest (once per chapter)
        book_json = os.path.join(ex, f'book_ch{n}_formulas.json')
        rc, out = run([PY, BM,
                       '--extract-dir', ex, '--chapter-map', cm_path,
                       '--chapter', str(n), '-o', book_json], root)
        if rc != 0:
            chapter_errors.append(f'BUILD_FAIL: {out[-300:]}')

        for md in en + cn:
            base = os.path.splitext(md)[0]
            ext = os.path.join(ex, f'{base}_formulas.json')
            fill = os.path.join(ex, f'{base}_filled.json')
            rc1, _ = run([PY, FM, md,
                          '-o', ext, '--chapter-map', cm_path, '--chapter', str(n)], root)
            rc2, _ = run([PY, FL, ext,
                          book_json, '-o', fill], root)
            rc3, dout = run([PY, DIFF,
                             fill, book_json], root)
            hard = [l for l in dout.splitlines()
                    if l.strip().startswith(('  FABRICATED', '  MISSING',
                                             '  ORDER_MISMATCH', '  PAGE_RANGE',
                                             '  MISPLACED', '  MISMATCH',
                                             '  OMITTED'))]
            if hard:
                chapter_errors.append(f'[{md}] ' + ' | '.join(hard))

        status = 'OK' if not chapter_errors else 'REVIEW'
        report.append((n, status, chapter_errors))
        print(f'ch{n:>2} {status}  ' + ('' if status == 'OK'
              else '\n        '.join(chapter_errors)))

    with open(os.path.join(root, ex, 'backfill_report.txt'), 'w', encoding='utf-8') as f:
        for n, status, errs in report:
            f.write(f'ch{n:>2} {status}\n')
            for e in errs:
                f.write('   ' + e + '\n')
    n_ok = sum(1 for _, s, _ in report if s == 'OK')
    print(f'\n=== {n_ok}/{len(report)} chapters clean; '
          f'{len(report)-n_ok} need review ===')
    print('report -> _extract/backfill_report.txt')


if __name__ == '__main__':
    main()
