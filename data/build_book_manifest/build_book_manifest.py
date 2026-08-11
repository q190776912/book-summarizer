#!/usr/bin/env python3
"""build_book_manifest.py — model + constructor for ``book_chN_formulas.json``.

Derive a per-chapter *book-side* formula manifest from the OCR ``page_*.json``
files produced during extraction.

For every chapter page we scan ``text[]`` blocks for formula sequence labels
``(C.N)`` / ``Eq. C.N`` / ``Equation C.N`` / ``式（C.N）`` (depth = 2 by
default; override with ``--depth``), **scoped to the chapter number C** so
cross-chapter references are ignored.  For each label we keep:

  * label    : canonical "C.N" (+ optional letter suffix, e.g. "8.11a")
  * page     : PDF page number
  * pos_y    : top y-coordinate (PDF points) of the OCR block == "页中位置"
  * context  : the OCR text line containing the label (prose for LLM mapping)
  * poly     : raw bounding box
  * occ      : all (page, pos_y) occurrences of that label in the chapter

The PRIMARY position is the earliest occurrence (lowest page, then lowest y) --
i.e. where the formula is *defined*, not later references.

NOTE: ``page_*.json`` ``formulas[].latex`` is LaTeX-OCR output (noisy) and is
NOT used for content matching; book-formula *content* is verified by the LLM
reading the book during backfill.  This manifest therefore carries labels +
positions + prose context only.

Models (subclass of :class:`JsonData`):
    BookFormulaRecord — one book-side formula entry (leaf record)
    BookFormulaIndex  — the book_chN_formulas.json document

Usage:
    python build_book_manifest.py --extract-dir _extract --chapter-map chapter_map.json --chapter 2
"""
import argparse
import glob
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

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

GROUP2 = r'(\d+[.\-·,]\d+([a-zA-Z])?)'
PATS = [
    r'[（(]\s*' + GROUP2 + r'\s*[）)]',
    r'\bEq\.?\s+' + GROUP2,
    r'\bEquation\s+' + GROUP2,
    r'式\s*[（(]?\s*' + GROUP2,
]

# OCR heading like "2.3.2 Preliminaries" / "§2.2 Stability ..." (short -> heading)
HEAD_RE = re.compile(r'^\s*(?:§\s*)?(\d+(?:\.\d+)+)\b')


def norm_label(raw: str) -> str:
    raw = raw.replace('·', '.').replace(',', '.').replace('-', '.')
    return raw


def extract_labels(text: str, chapter: int):
    """Yield (label, suffix_char) for labels whose chapter component == chapter."""
    out = []
    for pat in PATS:
        for m in re.finditer(pat, text):
            raw = m.group(1)
            lab = norm_label(raw)
            parts = re.split(r'[.\-·,]', lab)
            if len(parts) >= 2 and parts[0] == str(chapter):
                letter = m.group(2) or ''
                out.append((lab + letter, letter))
    return out


def build(extract_dir, chapter_map_path, chapter, depth=2):
    cm = json.load(open(chapter_map_path, encoding='utf-8'))
    info = cm.get(str(chapter)) or cm.get(chapter)
    start, end = info['start'], info['end']
    name = info.get('name_en') or info.get('name')

    by_label = {}  # label -> {page,pos_y,context,poly,occ:[(page,y)]}
    headings = []  # (page, y, section_num)
    for pg in range(start, end + 1):
        f = os.path.join(extract_dir, f'page_{pg:03d}.json')
        if not os.path.exists(f):
            f = os.path.join(extract_dir, f'page_{pg}.json')
        if not os.path.exists(f):
            continue
        d = json.load(open(f, encoding='utf-8'))
        for blk in d.get('text', []):
            txt = blk.get('text', '')
            poly = blk.get('poly') or []
            y = poly[1] if len(poly) >= 2 else None
            for lab, letter in extract_labels(txt, chapter):
                rec = by_label.setdefault(lab, {
                    'label': lab, 'page': None, 'pos_y': None,
                    'context': txt, 'poly': poly, 'occ': [],
                })
                rec['occ'].append((pg, y))
                # keep earliest (lowest page, then lowest y) as primary
                if rec['page'] is None or (pg, y) < (rec['page'], rec['pos_y']):
                    rec['page'], rec['pos_y'] = pg, y
                    rec['context'] = txt
                    rec['poly'] = poly
            # heading detection (short numbered line)
            hm = HEAD_RE.match(txt.strip())
            if hm and len(txt.strip()) < 80:
                headings.append((pg, y, hm.group(1)))

    # assign each label the nearest preceding heading (book section)
    headings.sort()
    for lab, rec in by_label.items():
        sec = None
        for hpg, hy, hsec in headings:
            if (hpg, hy) <= (rec['page'], rec['pos_y'] or 0):
                sec = hsec
            else:
                break
        rec['book_section'] = sec

    formulas = []
    for lab in sorted(by_label.keys(), key=lambda s: [int(x) for x in re.split(r'[.\-·,a-zA-Z]+', s) if x.isdigit()][:2]):
        rec = by_label[lab]
        formulas.append({
            'label': rec['label'],
            'page': rec['page'],
            'pos_y': rec['pos_y'],
            'book_section': rec['book_section'],
            'context': rec['context'],
            'occ': rec['occ'],
        })
    return {
        'chapter': chapter,
        'chapter_name': name,
        'page_range': [start, end],
        'depth': depth,
        'formulas': formulas,
    }


@dataclass
class BookFormulaRecord:
    """One book-side formula entry of ``book_chN_formulas.json``."""
    label: str
    context: str
    page: Optional[int] = None
    pos_y: Optional[float] = None
    book_section: Optional[str] = None
    occ: List[Tuple[int, Optional[float]]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "page": self.page,
            "pos_y": self.pos_y,
            "book_section": self.book_section,
            "context": self.context,
            "occ": self.occ,
        }


@dataclass
class BookFormulaIndex(JsonData):
    """The ``book_chN_formulas.json`` document — a JSON subclass."""
    chapter: int
    chapter_name: Optional[str]
    page_range: List[int]
    depth: int
    formulas: List[BookFormulaRecord] = field(default_factory=list)

    @classmethod
    def build(cls, extract_dir, chapter_map_path, chapter, depth=2) -> "BookFormulaIndex":
        d = build(extract_dir, chapter_map_path, chapter, depth)
        formulas = [BookFormulaRecord(**f) for f in d['formulas']]
        return cls(chapter=d['chapter'], chapter_name=d['chapter_name'],
                   page_range=d['page_range'], depth=d['depth'], formulas=formulas)

    @classmethod
    def from_dict(cls, d: dict) -> "BookFormulaIndex":
        formulas = [BookFormulaRecord(**f) for f in d.get("formulas", [])]
        return cls(chapter=d.get("chapter"),
                   chapter_name=d.get("chapter_name"),
                   page_range=d.get("page_range"),
                   depth=d.get("depth", 2),
                   formulas=formulas)

    def to_dict(self) -> dict:
        return {
            "chapter": self.chapter,
            "chapter_name": self.chapter_name,
            "page_range": self.page_range,
            "depth": self.depth,
            "formulas": [f.to_dict() for f in self.formulas],
        }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--extract-dir', required=True)
    ap.add_argument('--chapter-map', required=True)
    ap.add_argument('--chapter', type=int, required=True)
    ap.add_argument('--depth', type=int, default=2)
    ap.add_argument('-o', '--out', default=None)
    args = ap.parse_args()

    idx = BookFormulaIndex.build(args.extract_dir, args.chapter_map, args.chapter, args.depth)
    out = args.out or os.path.join(
        args.extract_dir, f'book_ch{args.chapter}_formulas.json')
    idx.dump(out)
    print(f'wrote {out}: {len(idx.formulas)} book labels '
          f'(pages {idx.page_range})')


if __name__ == '__main__':
    main()
