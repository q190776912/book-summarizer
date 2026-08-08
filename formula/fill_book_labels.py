#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fill_book_labels.py
====================
Backfill step: attach the *book-side* truth to a summary formula manifest.

For each DISPLAY formula in the summary manifest:
  * summary_label present AND found in the book manifest
        -> book_label = summary_label, page/pos_y/context copied from book.
           status = "ok"  (auto-matched; LLM still reviews for misplacement)
  * summary_label present but NOT in the book manifest
        -> book_label = "__UNMATCHED__", status = "label_not_in_book"
           (fabricated / wrong-chapter reference -- must be fixed in summary)
  * summary_label absent (unlabeled display)
        -> book_label = null, status = "unlabeled_summary"
           (auxiliary derivation OR an omitted book number -- LLM reviews)

INLINE formulas are left untouched (status = "inline"); they are notation,
not book equations, and are excluded from label fidelity checks.

The resulting JSON is the persistent manifest.  During backfill the LLM
inspects each record and, where the summary mislabeled a formula, corrects
``book_label`` to the TRUE book label (differing from ``summary_label``);
``diff_formula_manifest.py`` then flags the mismatch so the SUMMARY can be
fixed.

Usage:
    python fill_book_labels.py summary_formulas.json book_chN_formulas.json -o filled.json
"""
import argparse
import json


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('summary')
    ap.add_argument('book')
    ap.add_argument('-o', '--out', required=True)
    args = ap.parse_args()

    sm = json.load(open(args.summary, encoding='utf-8'))
    bm = json.load(open(args.book, encoding='utf-8'))
    lookup = {f['label']: f for f in bm['formulas']}

    for r in sm['formulas']:
        if r['kind'] != 'display':
            r['status'] = 'inline'
            continue
        sl = r.get('summary_label')
        if sl:
            b = lookup.get(sl)
            if b:
                r['book_label'] = sl
                r['page'] = b['page']
                r['pos_y'] = b['pos_y']
                r['book_section'] = b.get('book_section')
                r['context'] = b['context']
                r['book_occ'] = b['occ']
                r['status'] = 'ok'
            else:
                r['book_label'] = '__UNMATCHED__'
                r['status'] = 'label_not_in_book'
        else:
            r['book_label'] = None
            r['status'] = 'unlabeled_summary'

    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(sm, f, ensure_ascii=False, indent=2)

    n_ok = sum(1 for r in sm['formulas'] if r.get('status') == 'ok')
    n_un = sum(1 for r in sm['formulas'] if r.get('status') == 'label_not_in_book')
    n_unl = sum(1 for r in sm['formulas']
                if r.get('status') == 'unlabeled_summary')
    print(f'wrote {args.out}: ok={n_ok} label_not_in_book={n_un} '
          f'unlabeled_summary={n_unl}')


if __name__ == '__main__':
    main()
