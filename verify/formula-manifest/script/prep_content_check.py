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
import fill_book_labels

# -*- coding: utf-8 -*-
"""Render every formula-bearing page for all chapters and emit per-chapter
checklists so sub-agents can do visual content fidelity checks.

Reads each EN `*_filled.json` under the extract dir, collects labeled display
formulas (summary_label not None), renders the corresponding PDF pages, and
writes `checklist_chN.txt` listing each label with its page / section /
book_section / summary content.
"""
import json
import glob
import os
import fitz  # PyMuPDF


def main():
    import argparse
    import re
    ap = argparse.ArgumentParser()
    ap.add_argument('--book-root', required=True)
    ap.add_argument('--extract-dir', default='_extract')
    ap.add_argument('--dpi', type=int, default=110)
    args = ap.parse_args()

    root = args.book_root
    extract = os.path.join(root, args.extract_dir)
    pdf = os.path.join(root, 'Koopman Operator.pdf')
    out = os.path.join(extract, '_contentcheck')
    os.makedirs(out, exist_ok=True)

    doc = fitz.open(pdf)
    pages_to_render = set()
    checklists = {}

    ch_re = re.compile(r'Chapter(\d+)_.*_filled\.json$')
    for fp in sorted(glob.glob(os.path.join(extract, 'Chapter*_filled.json'))):
        m = ch_re.search(os.path.basename(fp))
        if not m:
            continue  # skip CN (第*章) and non-standard names
        ch = int(m.group(1))
        if ch in checklists:
            continue  # de-dupe stray duplicate md
        d = fill_book_labels.FormulaFill.load(fp).to_dict()
        formulas = d.get('formulas', [])
        labeled = [r for r in formulas
                   if r.get('kind') == 'display' and r.get('summary_label')]
        lines = []
        for r in labeled:
            pg = r.get('page')
            if pg:
                pages_to_render.add(int(pg))
            lines.append(
                f"{r['summary_label']}  page={pg}  "
                f"section={r.get('section')}  "
                f"book_section={r.get('book_section')}\n"
                f"    summary: {r.get('content_summary', '')}"
            )
        checklists[ch] = len(labeled)
        with open(os.path.join(out, f'checklist_ch{ch}.txt'),
                  'w', encoding='utf-8') as f:
            f.write(f'Chapter {ch}\n')
            f.write(f'Labeled formulas: {len(labeled)}\n')
            f.write(f'Source md: {os.path.basename(fp)}\n\n')
            f.write('\n'.join(lines) if lines else '(none)')

    # render pages
    rendered = 0
    for pg in sorted(pages_to_render):
        try:
            pix = doc[pg - 1].get_pixmap(dpi=args.dpi)
            pix.save(os.path.join(out, f'p{pg:03d}.png'))
            rendered += 1
        except Exception as e:
            print(f'  WARN cannot render page {pg}: {e}')

    print(f'rendered {rendered} unique pages')
    print(f'chapters ({len(checklists)}): {sorted(checklists.keys())}')
    print('labeled-per-chapter:',
          {k: checklists[k] for k in sorted(checklists)})


if __name__ == '__main__':
    main()
