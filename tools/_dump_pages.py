"""Dump formulas[] latex + surrounding text for given pages."""
import json
import os
import sys

BOOK = sys.argv[1]
PAGES = [int(x) for x in sys.argv[2].split(',')]
EXT = os.path.join(BOOK, '_extract')
for pg in PAGES:
    fp = os.path.join(EXT, f'page_{pg:03d}.json')
    data = json.load(open(fp, encoding='utf-8'))
    print(f"\n===== page {pg} =====")
    for f in data.get('formulas', []) or []:
        latex = f.get('latex', '')
        if latex:
            print(f"  FORMULA latex: {latex!r}")
    print("  --- text blocks ---")
    for b in data.get('text', []) or []:
        t = b.get('text', '')
        if t and len(t) < 200:
            print(f"  [t] {t!r}")
