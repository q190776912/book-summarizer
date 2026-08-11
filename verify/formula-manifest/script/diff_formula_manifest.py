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
import build_book_manifest
import fill_book_labels

# -*- coding: utf-8 -*-
"""
diff_formula_manifest.py
========================
Verify a (backfilled) summary formula manifest against the book manifest.

Checks (display formulas only):
  * label_not_in_book  : summary_label absent from the book set
                         -> FABRICATED / wrong reference (fix the summary)
  * label_mismatch     : LLM-asserted book_label != summary_label
                         -> summary mislabeled / misplaced (fix the summary)
  * missing_in_summary : a book label never referenced by any summary formula
                         -> summary omitted that equation (fix the summary)
  * unlabeled_summary  : summary display with no label -- LLM should confirm
                         the book also leaves it unnumbered (else it is an
                         OMITTED label)

Inline formulas are ignored.

Exit code 0 when no label_not_in_book / label_mismatch / missing errors;
1 otherwise (so it can gate CI / the verify pipeline).

Usage:
    python diff_formula_manifest.py filled_formulas.json book_chN_formulas.json
"""
import argparse
import json
import sys


def sec_ok(s_sum, s_book):
    """Tolerant section comparison: mismatch only when the C.N (first two
    components) differ.  Deeper sub-section granularity is ignored so a
    summary that omits a sub-heading is not falsely flagged."""
    if not s_sum or not s_book:
        return True
    a = s_sum.split('.'); b = s_book.split('.')
    if len(a) >= 2 and len(b) >= 2:
        return a[:2] == b[:2]
    return a[0] == b[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('filled')
    ap.add_argument('book')
    args = ap.parse_args()

    sm = fill_book_labels.FormulaFill.load(args.filled).to_dict()
    bm = build_book_manifest.BookFormulaIndex.load(args.book).to_dict()
    book_labels = {f['label'] for f in bm['formulas']}

    errors = []
    warns = []
    referenced = set()

    for r in sm['formulas']:
        if r['kind'] != 'display':
            continue
        sl = r.get('summary_label')
        bl = r.get('book_label')
        st = r.get('status')

        if st == 'label_not_in_book':
            errors.append(f"  FABRICATED  ord={r['ord']} L{r['line']} "
                          f"summary_label={sl} (not in book)")
            continue
        if sl is not None:
            referenced.add(sl)
        if st == 'ok':
            # auto-matched: book_label == summary_label by construction.
            # Sanity-check page range and SECTION placement.
            pr = bm.get('page_range', [0, 10**9])
            if r.get('page') is not None and not (pr[0] <= r['page'] <= pr[1]):
                errors.append(f"  PAGE_RANGE ord={r['ord']} L{r['line']} "
                              f"label={sl} page={r['page']} not in {pr}")
            if not sec_ok(r.get('section'), r.get('book_section')):
                errors.append(f"  MISPLACED ord={r['ord']} L{r['line']} "
                              f"label={sl} summary_section={r.get('section')} "
                              f"book_section={r.get('book_section')}")
        elif st == 'unlabeled_summary':
            warns.append(f"  UNLABELED  ord={r['ord']} L{r['line']} "
                         f"section={r.get('section')} "
                         f"content={r['content_summary'][:50]}")
        else:
            # LLM set an explicit book_label differing from summary_label
            if bl is not None and sl is not None and bl != sl:
                errors.append(f"  MISMATCH   ord={r['ord']} L{r['line']} "
                              f"summary={sl} book={bl} "
                              f"(summary mislabeled -> fix)")
            elif bl is not None and sl is None:
                errors.append(f"  OMITTED    ord={r['ord']} L{r['line']} "
                              f"book={bl} (summary missing label -> fix)")
            elif bl is None and sl is not None:
                # book_label null but summary has a label not in 'ok' -> already
                # covered by label_not_in_book; ignore here
                pass

    # --- sequence (reading-order) alignment: catches MISPLACEMENT ---------
    # Summary labeled formulas in document order vs book labels in reading
    # order (page, pos_y).  A divergence means a formula was mislabeled or
    # moved (e.g. a spurious tag in an earlier section shifts the sequence).
    sum_seq = [r['summary_label'] for r in sm['formulas']
               if r['kind'] == 'display' and r.get('summary_label')]
    book_seq = sorted(bm['formulas'], key=lambda f: (f['page'], f['pos_y'] or 0))
    book_labels_seq = [f['label'] for f in book_seq]
    if sum_seq != book_labels_seq:
        errors.append("  ORDER_MISMATCH  summary sequence != book reading "
                      f"sequence ({len(sum_seq)} vs {len(book_labels_seq)})")
        errors.append("    summary: " + " ".join(sum_seq))
        errors.append("    book   : " + " ".join(book_labels_seq))

    missing = sorted(book_labels - referenced,
                     key=lambda s: [int(x) for x in
                                    ''.join(c if c.isdigit() else ' '
                                            for c in s).split()][:2]
                                     if any(c.isdigit() for c in s) else [999, 0])
    for m in missing:
        errors.append(f"  MISSING    book label {m} not present in summary")

    print(f"=== diff chapter {sm.get('chapter_file')} vs book "
          f"(pages {bm.get('page_range')}) ===")
    if errors:
        print("ERRORS:")
        print('\n'.join(errors))
    if warns:
        print(f"\nWARNINGS (review {len(warns)} unlabeled displays):")
        print('\n'.join(warns))
    if not errors and not warns:
        print("  clean: all display formulas verified.")
    elif not errors:
        print(f"  no hard errors; {len(warns)} unlabeled displays to review.")

    sys.exit(1 if errors else 0)


if __name__ == '__main__':
    main()
