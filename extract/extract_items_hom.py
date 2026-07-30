"""extract_items_hom.py — custom item extractor for Hilton & Stammbach
"A Course in Homological Algebra".

Numbering convention of THIS book:
  * Chapters are labelled with ROMAN numerals (I..IX); the Roman numeral is
    NOT part of item numbers.
  * Inside a chapter, items are numbered per SECTION: "Theorem 2.1",
    "Proposition 3.1", "Definition 1.1" ... i.e. a TWO-LEVEL "section.item"
    scheme with NO chapter digit. The same ("2.1") recurs in different chapters.
  * Exercises are "2.4." etc. (also section.item) but are NOT labeled items.
  * Examples are "Example 2.1" / "例 2.1" (sometimes "Example" with no number).

The built-in extract_items.py two-level scheme requires the first digit to be
the chapter number, which does NOT hold here, so we use this dedicated
extractor (chapter identity is implicit via the page range passed in).

Usage:
  python extract_items_hom.py <start_page> <end_page> <extract_dir> [--examples]
  -> prints one labeled item per line:  KEY [LABEL] pPAGE  snippet
Keys look like "定理2.1", "命题3.1", "例2.1".
"""
import json, re, os, sys

# Shared H&S two-level ("section.item") numbering constants live in lib/numbering
# to avoid drift between extract_items_hom.py and verify_hom.py.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.numbering import (
    HOM_ITEM_RE as ITEM_RE,
    HOM_EX_RE as EX_RE,
    HOM_CITE_RE as CITE_RE,
)

def scan(extract_dir, start, end, with_examples=False):
    blocks = []
    for p in range(start, end + 1):
        fp = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        with open(fp, encoding='utf-8') as f:
            data = json.load(f)
        for t in data.get('text', []):
            txt = t.get('text', '').strip()
            if not txt:
                continue
            poly = t.get('poly', [])
            y = poly[1] if poly and len(poly) >= 8 else 0
            blocks.append((p, y, txt))
    blocks.sort(key=lambda x: (x[0], x[1]))

    label_map = {'定义': '定义', '定理': '定理', '引理': '引理', '推论': '推论',
                 '命题': '命题', 'Definition': '定义', 'Theorem': '定理',
                 'Lemma': '引理', 'Corollary': '推论', 'Proposition': '命题'}

    items = {}
    for p, y, txt in blocks:
        # labeled items
        for m in ITEM_RE.finditer(txt):
            sec = int(m.group(2)); num = int(m.group(3))
            if sec > 20 or num > 80:
                continue
            before = txt[max(0, m.start() - 25):m.start()].strip()
            if CITE_RE.search(before):
                continue
            key = f"{label_map[m.group(1)]}{sec}.{num}"
            snippet = txt[max(0, m.start() - 5):m.end() + 90].replace('\n', ' ')
            if key not in items:
                items[key] = {'page': p, 'label': label_map[m.group(1)], 'text': snippet}
        if with_examples:
            for m in EX_RE.finditer(txt):
                sec = int(m.group(2))
                num = m.group(3)
                if sec > 20:
                    continue
                key = f"例{sec}.{num}" if num else f"例{sec}"
                snippet = txt[max(0, m.start() - 5):m.end() + 60].replace('\n', ' ')
                if key not in items:
                    items[key] = {'page': p, 'label': '例', 'text': snippet}
    return items

if __name__ == '__main__':
    args = sys.argv[1:]
    with_ex = '--examples' in args
    pos = [a for a in args if not a.startswith('--')]
    start = int(pos[0]); end = int(pos[1]); extract_dir = pos[2]
    items = scan(extract_dir, start, end, with_ex)
    # sort by section then number
    def sk(k):
        body = k.lstrip('例定理论认为推命')
        parts = body.split('.')
        return (int(parts[0]) if parts[0].isdigit() else 0,
                int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0)
    for key in sorted(items, key=sk):
        it = items[key]
        print(f"{key:10s} [{it['label']}] p{it['page']:3d}  {it['text']}")
    print(f"\nTotal: {len(items)}")
