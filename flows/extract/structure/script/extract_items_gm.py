"""
extract_items_gm.py — item extractor for "Chapter.Section.Item" books whose
PAGES and .md headings both use the BOOK's printed forms, e.g. Gelfand & Manin,
"Methods of Homological Algebra":

    ## §1. Triangulated Spaces          (sections numbered per chapter)
    ### 1. Main Definitions             (items numbered per section, bare
    ### 3. Proposition. ...              ordinal, written as ATX headings to
    ...                                  match the book's printed titles)
    ...  "by Proposition I.2.11", "see Lemma I.2.11"   (full refs in prose)

Machine keys stay Chapter.Section-Item with a ROMAN chapter numeral:
    `命题I.2-11` (labelled heading / labelled reference)
    `I.2-14`     (heading WITHOUT a label word, e.g. "14. Skeleton and
                  Dimension" — the book prints no label there, so the key
                  carries none; the .md parser applies the same rule)

Strategy
--------
(a) Bare ordinal headings in the PDF OCR blocks: `^N. Word` at the START of a
    text block with y >= HEAD_Y_MIN.  Running heads ("1. Simplicial Sets",
    "7. Complexes", page numbers) always sit at the very top of a page
    (y <= ~105) and are filtered by the y threshold.  A block starting with
    "Exercises" switches on an exercises flag (reset at the next section
    heading) so exercise ordinals are never counted as items.
(b) The current section is tracked from "§N. Title" heading blocks
    (`^[§$](\\d+)\\. Title`); the chapter_map page ranges are the fallback before
    the first section heading is seen (and for pages whose heading OCR fails).
(c) Explicit labelled cross-references ("Proposition I.2.11") are captured so
    items cited ONLY by full reference are still known to exist.

Items reached by neither (a) nor (c) must be supplied via `manual_overrides`
(the same mechanism used for OCR-garbled recovery elsewhere).

The heading scan (scan_gm_blocks) is shared with the D-layer, which checks
section coverage and per-section tail ordinals INDEPENDENTLY of this module's
key output.
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
import manual_overrides_chN
import page_json
import chapter_map

import os
import re
import json

from key_parse import (
    _canon_label, EN_LABEL_KINDS, GM_HEAD_LABEL_RE, GM_LABELED_RE, gm_head_label,
)

# Roman chapter numerals (uppercase in this book; accept lower too).
_ROMAN_VALUES = {'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000}


def roman_to_int(s):
    s = s.lower().strip()
    if not s or not all(ch in _ROMAN_VALUES for ch in s):
        return 0
    total = 0
    prev = 0
    for ch in reversed(s):
        val = _ROMAN_VALUES[ch]
        total += -val if val < prev else val
        prev = max(prev, val)
    return total


def int_to_roman(n):
    vals = [(1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'),
            (90, 'XC'), (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'),
            (4, 'IV'), (1, 'I')]
    out = ''
    for v, sym in vals:
        while n >= v:
            out += sym
            n -= v
    return out


# ---------------------------------------------------------------------------
# OCR regexes (extractor/D-layer side).  The .md-side counterparts live in
# lib/key_parse.py; GM_HEAD_LABEL_RE / GM_LABELED_RE are shared there.
# ---------------------------------------------------------------------------

# Section heading in the OCR: "§1. Triangulated Spaces" / "$2. Simplicial Sets" /
# "S3. Structures and Categories. Representable Functors" — the OCR often reads
# the section glyph as a capital S (Gelfand-Manin ch.2+ alternates "$"/"S").
# NOT matching "§2 = x0 + x1," (no dot), NOT matching "§I.1" (roman digit).
GM_OCR_SEC_RE = re.compile(r'^[§S$]\s*(\d{1,2})\.\s+[A-Z]')

# Item heading in the OCR: "1. Main Definitions", "3. Proposition. ...",
# "8.Theorem.In the setup..." / "4.Remarks" / "3.Presheaves ..." (glued OCR,
# hence the optional space).  Anchored at block start; a following digit
# ("1.5.1.", "2.8)") or lower-case letter ("1. a) ...") never matches.  The
# leading [A-Z] is a LOOKAHEAD so the heading word is not consumed (the title
# for label detection must keep its first letter).
GM_OCR_ITEM_RE = re.compile(r'^(\d{1,3})\.\s*(?=[A-Z])')

# Exercises block heading in the OCR.
GM_OCR_EX_RE = re.compile(r'^Exercises')

# Running heads / page numbers all sit above this y on a text page.
HEAD_Y_MIN = 120
# Item ordinals never exceed this in this book (guards vs formula garbage).
MAX_ITEM = 40


def _norm_label(raw):
    """Normalize a GM_LABELED_RE label match: 'Cor.'/'Def.' and plurals."""
    raw = raw.strip()
    low = raw.lower()
    if low == 'cor.':
        return 'Corollary'
    if low == 'def.':
        return 'Definition'
    if low.endswith('s') and len(raw) > 1 and \
            raw[:-1] in EN_LABEL_KINDS:
        return raw[:-1]
    if raw in EN_LABEL_KINDS:
        return raw
    return raw.capitalize()


def _load_sections(ext_dir, chapter):
    cm_path = os.path.join(ext_dir, 'chapter_map.json')
    sections = []
    if os.path.exists(cm_path):
        cm = chapter_map.load_chapter_map_raw(cm_path)
        for e in cm.get('chapters', []):
            num = e.get('num', e.get('ch'))
            if num is None:
                num = e.get('chapter', e.get('number'))
            try:
                if int(num) == chapter:
                    sections = e.get('sections', [])
                    break
            except (TypeError, ValueError):
                continue
    return sections


def _section_of_page(page, sections):
    for s in sections:
        if s['start'] <= page <= s['end']:
            return s['sec']
    return None


def _read_blocks(ext_dir, start, end):
    """All text blocks in reading order: (page, y, text)."""
    all_blocks = []
    for p in range(start, end + 1):
        fp = os.path.join(ext_dir, f'page_{p:03d}.json')
        if not os.path.exists(fp):
            continue
        data = page_json.PageJson.load(fp).data
        for t in data.get('text', []):
            txt = t.get('text', '').strip()
            if not txt:
                continue
            poly = t.get('poly', [])
            y = poly[1] if poly and len(poly) >= 8 else 0
            all_blocks.append((p, y, txt))
    all_blocks.sort(key=lambda x: (x[0], x[1]))
    return all_blocks


def scan_gm_blocks(ext_dir, start, end, sections=None):
    """Heading scan shared by the extractor and the D-layer.

    Returns list of dicts {page, sec, num, label, text} — one per DISTINCT
    item heading of the chapter's page range (running heads, exercise ordinals
    and duplicate pages already removed).  label is None for label-less
    headings ("14. Skeleton and Dimension").
    """
    all_blocks = _read_blocks(ext_dir, start, end)
    first_page = all_blocks[0][0] if all_blocks else start
    cur_sec = _section_of_page(first_page, sections) if sections else None
    exercise = False
    found = []
    for p, y, txt in all_blocks:
        sm = GM_OCR_SEC_RE.match(txt)
        if sm:
            cur_sec = int(sm.group(1))
            exercise = False
            continue
        if GM_OCR_EX_RE.match(txt):
            exercise = True
            continue
        if cur_sec is None or exercise or y < HEAD_Y_MIN:
            continue
        im = GM_OCR_ITEM_RE.match(txt)
        if not im:
            continue
        num = int(im.group(1))
        if num > MAX_ITEM:
            continue
        if any(f['sec'] == cur_sec and f['num'] == num for f in found):
            continue  # duplicate page
        title = txt[im.end():].lstrip()[:80]
        found.append({'page': p, 'sec': cur_sec, 'num': num,
                      'label': gm_head_label(title), 'text': txt[:120]})
    return found


def extract_items_gm(extract_dir, chapter, start_page, end_page,
                     manual_overrides=None):
    sections = _load_sections(extract_dir, chapter)
    rch = int_to_roman(chapter)
    rch_low = rch.lower()

    raw = []
    for h in scan_gm_blocks(extract_dir, start_page, end_page, sections):
        key = (f"{_canon_label(h['label'])}{rch}.{h['sec']}-{h['num']}"
               if h['label'] else f"{rch}.{h['sec']}-{h['num']}")
        raw.append({'key': key, 'page': h['page'],
                    'label': h['label'] or '', 'text': h['text']})

    # (c) explicit labelled cross-references (items cited only by full ref).
    for p, y, txt in _read_blocks(extract_dir, start_page, end_page):
        for m in GM_LABELED_RE.finditer(txt):
            r, s, n = m.group(2), int(m.group(3)), int(m.group(4))
            if r.lower() != rch_low:
                continue
            if s > 40 or n > MAX_ITEM:
                continue
            label = _norm_label(m.group(1))
            key = f"{_canon_label(label)}{r}.{s}-{n}"
            raw.append({'key': key, 'page': p, 'label': label,
                        'text': txt[max(0, m.start() - 5):m.end() + 60]})

    seen = {}
    for it in raw:
        if it['key'] not in seen:
            seen[it['key']] = it
    items = list(seen.values())
    items.sort(key=lambda x: (x['page'], x['key']))

    if manual_overrides:
        existing = {it['key']: i for i, it in enumerate(items)}
        for mo in manual_overrides:
            if mo['key'] in existing:
                items[existing[mo['key']]] = {**items[existing[mo['key']]], **mo}
            else:
                items.append(mo)
        items.sort(key=lambda x: (x['page'], x['key']))

    return items, [], []


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("pos", nargs="*", help="<ch> <start> <end> <extract_dir>")
    ap.add_argument("--manual", default=None)
    ns = ap.parse_args()
    ch = int(ns.pos[0]); start = int(ns.pos[1]); end = int(ns.pos[2])
    ext = ns.pos[3]
    manual = None
    if ns.manual and os.path.exists(ns.manual):
        manual = manual_overrides_chN.load_manual_overrides(ns.manual)
    items, w, b = extract_items_gm(ext, ch, start, end, manual_overrides=manual)
    cur = None
    for it in items:
        sec = '.'.join(it['key'].split('.')[:2])
        if sec != cur:
            cur = sec
            print()
        print(f"{it['key']:14s} p{it['page']:3d}  {it['text'][:70]}")
    print(f"\nTotal: {len(items)}")
