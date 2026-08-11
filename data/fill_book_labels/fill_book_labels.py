#!/usr/bin/env python3
"""fill_book_labels.py — model + constructor for ``*_filled.json``.

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

Model (subclass of :class:`JsonData`):
    FormulaFill — the *_filled.json document (summary manifest enriched in place)

Usage:
    python fill_book_labels.py summary_formulas.json book_chN_formulas.json -o filled.json
"""
import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

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
from json_data import JsonData


@dataclass
class FormulaFill(JsonData):
    """The ``*_filled.json`` document — a JSON subclass (summary manifest enriched)."""
    chapter_file: Optional[str]
    formulas: List[dict] = field(default_factory=list)

    # ---- constructor ----
    @classmethod
    def run(cls, summary_path: str, book_path: str) -> "FormulaFill":
        sm = json.load(open(summary_path, encoding='utf-8'))
        bm = json.load(open(book_path, encoding='utf-8'))
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

        return cls(chapter_file=sm.get('chapter_file'), formulas=sm['formulas'])

    @classmethod
    def from_dict(cls, d: dict) -> "FormulaFill":
        return cls(chapter_file=d.get("chapter_file"),
                   formulas=d.get("formulas", []))

    # ---- export ----
    def to_dict(self) -> dict:
        d = {"formulas": self.formulas}
        if self.chapter_file is not None:
            d["chapter_file"] = self.chapter_file
        return d

    def counts(self) -> dict:
        return {
            "ok": sum(1 for r in self.formulas if r.get('status') == 'ok'),
            "label_not_in_book": sum(1 for r in self.formulas if r.get('status') == 'label_not_in_book'),
            "unlabeled_summary": sum(1 for r in self.formulas if r.get('status') == 'unlabeled_summary'),
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('summary')
    ap.add_argument('book')
    ap.add_argument('-o', '--out', required=True)
    args = ap.parse_args()

    filled = FormulaFill.run(args.summary, args.book)
    filled.dump(args.out)
    c = filled.counts()
    print(f'wrote {args.out}: ok={c["ok"]} label_not_in_book={c["label_not_in_book"]} '
          f'unlabeled_summary={c["unlabeled_summary"]}')


if __name__ == '__main__':
    main()
