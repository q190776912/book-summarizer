"""verify_hom.py — completeness checker for Hilton & Stammbach summaries.

Compares labeled items extracted from the OCR JSON (see extract_items_hom.py)
against the bold entries written in the chapter markdown. Reports missing /
extra keys so the agent can confirm no item was dropped or invented.

Usage:
  python verify_hom.py <start_page> <end_page> <extract_dir> <md_file> [--examples]
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
from page_json import PageJson

import json, re, os, sys

# Shared H&S two-level ("section.item") numbering constants live in lib/numbering
# to avoid drift between verify_hom.py and extract_items_hom.py.
from lib.numbering import (
    HOM_ITEM_RE as ITEM_RE,
    HOM_EX_RE as EX_RE,
    HOM_CITE_RE as CITE_RE,
    HOM_LABEL_MAP as LABEL_MAP,
    HOM_MD_ENTRY_RE as MD_ENTRY_RE,
)


def extract_keys(extract_dir, start, end, with_examples):
    blocks = []
    for p in range(start, end + 1):
        fp = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        with open(fp, encoding='utf-8') as f:
            data = PageJson.load(os.path.join(extract_dir, f"page_{p:03d}.json")).data
        for t in data.get('text', []):
            txt = t.get('text', '').strip()
            if not txt:
                continue
            poly = t.get('poly', [])
            y = poly[1] if poly and len(poly) >= 8 else 0
            blocks.append((p, y, txt))
    blocks.sort(key=lambda x: (x[0], x[1]))
    keys = set()
    for p, y, txt in blocks:
        for m in ITEM_RE.finditer(txt):
            sec, num = int(m.group(2)), int(m.group(3))
            if sec > 20 or num > 80:
                continue
            before = txt[max(0, m.start() - 25):m.start()].strip()
            if CITE_RE.search(before):
                continue
            keys.add(f"{LABEL_MAP[m.group(1)]}{sec}.{num}")
        if with_examples:
            for m in EX_RE.finditer(txt):
                sec = int(m.group(2)); num = m.group(3)
                if sec > 20:
                    continue
                keys.add(f"例{sec}.{num}" if num else f"例{sec}")
    return keys


def md_keys(path):
    keys = set()
    with open(path, encoding='utf-8') as f:
        for line in f:
            for m in MD_ENTRY_RE.finditer(line):
                keys.add(f"{m.group(1)}{m.group(2)}.{m.group(3)}")
    return keys


if __name__ == '__main__':
    args = sys.argv[1:]
    with_ex = '--examples' in args
    pos = [a for a in args if not a.startswith('--')]
    start, end, extract_dir, md = int(pos[0]), int(pos[1]), pos[2], pos[3]
    expected = extract_keys(extract_dir, start, end, with_ex)
    # definitions are unnumbered -> not tracked by number; we just note count
    got = md_keys(md)
    missing = sorted(expected - got, key=lambda k: (int(re.findall(r'\d+', k)[0]), int(re.findall(r'\d+', k)[1])))
    extra = sorted(got - expected, key=lambda k: (int(re.findall(r'\d+', k)[0]), int(re.findall(r'\d+', k)[1])))
    print(f"Expected labeled items (from JSON): {len(expected)}")
    print(f"Found in md: {len(got)}")
    if missing:
        print(f"\nMISSING ({len(missing)}):")
        for k in missing:
            print("  ", k)
    else:
        print("\nMISSING: none")
    if extra:
        print(f"\nEXTRA in md (review; usually filtered cross-refs): {len(extra)}")
        for k in extra:
            print("  ", k)
    else:
        print("EXTRA: none")
    sys.exit(1 if missing else 0)
