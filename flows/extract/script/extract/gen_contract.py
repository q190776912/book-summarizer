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

# -*- coding: utf-8 -*-
"""Robust item-contract generator for the dash-numbered CN book
《泛函分析导论及应用》(Kreyszig). Outputs every numbered item header
`N.M-K` found in the chapter's OCR pages, with a best-guess label and a
short text preview, plus a WARNING for any `§N.M` section heading that
yielded zero detected items (so the writer knows to eyeball the OCR).

The built-in extract_items.py drops whole sections (e.g. §2.3) and
comma-form numbers (e.g. `2,5-5`); this tool is deliberately permissive
to catch them. It is NOT used by verify — it only produces a contract
backbone for the writer. verify's A-layer uses extract_items keys, so the
writer must ALSO include any items this tool finds that extract_items
missed (verify won't flag them, but completeness against the book matters).

Usage:
  python gen_contract.py <extract_dir> <ch> <start> <end>
Prints to stdout.
"""
import json, os, re, sys

LABEL_WORDS = ('定理', '定义', '引理', '推论', '命题', '例')
LABEL_RE = re.compile(r'(定理|定义|引理|推论|命题|例(?:子)?)')
CITE_RE = re.compile(r'(见|由|根据|参考|参见|据|Cf\.|例\d|定理\d)')

# number-first:  2.3-1 / 2,3-1 / 2.3,1 / 2·3-1
NUM_FIRST = re.compile(r'(\d+)\s*[\.\uff0e\·\，\s]\s*(\d+)\s*[\-\.\uff0e\·\，\s]\s*(\d+)')
# label-first:   定理 2.3-1 / 例2,3-1
LABEL_FIRST = re.compile(r'(定理|定义|引理|推论|命题|例)\s*(\d+)\s*[\.\uff0e\·\，\s]\s*(\d+)\s*[\-\.\uff0e\·\，\s]\s*(\d+)')
# comma form 2,5-5  (two-group then dash)
COMMA_FORM = re.compile(r'(\d+)\s*,\s*(\d+)\s*-\s*(\d+)')
SEC_HEADING = re.compile(r'^(?:§\s*)?(\d+)\.(\d+)(?:\s{2,}|\s+[^\d\-])')


def load_blocks(ed, start, end):
    blocks = []
    for p in range(start, end + 1):
        fp = os.path.join(ed, 'page_%03d.json' % p)
        if not os.path.exists(fp):
            continue
        try:
            d = page_json.PageJson.load(fp).data
        except Exception:
            continue
        for t in d.get('text', []):
            txt = (t.get('text') or '').strip()
            if not txt:
                continue
            poly = t.get('poly', [])
            y = poly[1] if poly and len(poly) >= 8 else 0
            blocks.append((p, y, txt))
    blocks.sort(key=lambda x: (x[0], x[1]))
    return blocks


def guess_label(txt, pos):
    before = txt[max(0, pos - 12):pos]
    after = txt[pos:pos + 12]
    ctx = before + after
    lm = LABEL_RE.search(ctx)
    if lm:
        w = lm.group()
        if w.startswith('例'):
            return '例'
        return w
    return 'uncat'


def main():
    ed, ch, start, end = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
    blocks = load_blocks(ed, start, end)

    found = {}          # key -> dict
    sections_present = set()
    for p, y, txt in blocks:
        stripped = txt.strip().rstrip('：:．。，, ')
        sm = SEC_HEADING.match(stripped)
        if sm and int(sm.group(1)) == ch:
            sections_present.add(int(sm.group(2)))

    def add(key, label, p, pos, txt):
        if key in found:
            # upgrade label if we learn it
            if found[key]['label'] == 'uncat' and label != 'uncat':
                found[key]['label'] = label
            return
        found[key] = {'key': key, 'label': label, 'page': p,
                      'text': txt[max(0, pos - 6):pos + 80].replace('\n', ' ')}

    for i, (p, y, txt) in enumerate(blocks):
        # label-first
        for m in LABEL_FIRST.finditer(txt):
            c, s, n = int(m.group(2)), int(m.group(3)), int(m.group(4))
            if c != ch or s > 15 or n > 60:
                continue
            key = f"{c}.{s}-{n}"
            before = txt[max(0, m.start() - 25):m.start()]
            if CITE_RE.search(before):
                continue
            add(key, m.group(1) if not m.group(1).startswith('例') or True else '例', p, m.start(), txt)
        # num-first (dot/·/space separators)
        for m in NUM_FIRST.finditer(txt):
            c, s, n = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if c != ch or s > 15 or n > 60:
                continue
            key = f"{c}.{s}-{n}"
            before = txt[max(0, m.start() - 25):m.start()]
            after = txt[m.end():m.end() + 50]
            if CITE_RE.search(before):
                continue
            # skip if it's inside a parenthetical enumeration of 2+ refs
            op = txt.rfind('（', 0, m.start()); op = op if op != -1 else txt.rfind('(', 0, m.start())
            cl = txt.find('）', m.end()); cl = cl if cl != -1 else txt.find(')', m.end())
            if op != -1 and cl != -1 and op < m.start() < cl:
                if len(NUM_FIRST.findall(txt[op:cl + 1])) >= 2:
                    continue
            label = guess_label(txt, m.start())
            add(key, label, p, m.start(), txt)
        # comma form 2,5-5
        for m in COMMA_FORM.finditer(txt):
            c, s, n = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if c != ch or s > 15 or n > 60:
                continue
            key = f"{c}.{s}-{n}"
            before = txt[max(0, m.start() - 25):m.start()]
            if CITE_RE.search(before):
                continue
            label = guess_label(txt, m.start())
            add(key, label, p, m.start(), txt)

    items = sorted(found.values(), key=lambda x: (x['page'],
              tuple(int(p) for p in x['key'].split('.')[1].split('-'))))
    # group by section
    by_sec = {}
    for it in items:
        sec = it['key'].split('.')[1].split('-')[0]
        by_sec.setdefault(sec, []).append(it)

    print(f"=== Ch{ch} CONTRACT ({len(items)} items) p{start}-{end} ===\n")
    for sec in sorted(by_sec, key=lambda s: int(s)):
        print(f"\n----- §{ch}.{sec} ({len(by_sec[sec])} items) -----")
        for it in by_sec[sec]:
            print(f"{it['key']:8s} [{it['label']}] p{it['page']:3d}  {it['text']}")

    # warnings for sections present but with no items
    missing_secs = sorted([s for s in sections_present if s not in by_sec], key=lambda s: int(s))
    if missing_secs:
        print("\n=== WARNING: section headings found but ZERO items detected (eyeball OCR!) ===")
        for s in missing_secs:
            print(f"  §{ch}.{s}")

    # also warn for detected items whose label is uncat
    uncat = [it['key'] for it in items if it['label'] == 'uncat']
    if uncat:
        print(f"\n=== NOTE: {len(uncat)} items have no label word near them (use book's printed label) ===")
        print("  " + " ".join(uncat))

    print(f"\nTotal: {len(items)}")


if __name__ == '__main__':
    main()
