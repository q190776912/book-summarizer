"""verify/script/gm_scan.py — Gelfand–Manin / Roman 体例的 OCR 标题扫描（从 flows/write-source/structure/script/extract_items_gm.py 解耦复制）。

D 层（section_continuity）对 GM / ROMAN 书做章节连续性校验时，需复用抽取器的标题扫描
`scan_gm_blocks` / `_load_sections`。本文件为这些纯函数（及依赖的 OCR 正则、roman 互转、label
归一）的**解耦副本**，使校验子流程零 flows 依赖（约束：校验脚本不得依赖 flows 抽取管线）。
`_load_sections` 直接读取 `chapter_map.json`，不依赖 flows 的 `chapter_map` 模块。
`page_json`（data/）为共享数据读取器（非 flows），继续复用。

本文件中的 `scan_gm_blocks` / `_load_sections` 为**解耦副本**，函数实现与源文件 `flows/write-source/structure/script/extract_items_gm.py` **逐字符一致**；**单一真源在 `extract_items_gm.py`，修改须同步两处**（`int_to_roman` 见 `verify/script/ordinal.py`，同源）。
"""
import os
import sys
import re
import json
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
from verify.script.ordinal import int_to_roman
from key_parse import EN_LABEL_KINDS, gm_head_label, GM_LABELED_RE


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


# Section heading in the OCR: "§1. Triangulated Spaces" / "$2. Simplicial Sets" /
# "S3. Structures and Categories. Representable Functors" — the OCR often reads
# the section glyph as a capital S (Gelfand-Manin ch.2+ alternates "$"/"S").
# NOT matching "§2 = x0 + x1," (no dot), NOT matching "§I.1" (roman digit).
GM_OCR_SEC_RE = re.compile(r'^[§S$]\s*(\d{1,2})\.\s+[A-Z]')

# Item heading in the OCR: "1. Main Definitions", "3. Proposition. ...",
# "8.Theorem.In the setup..." / "4.Remarks" / "3.Presheaves ..." (glued OCR,
# hence the optional space).  Anchored at block start; a following digit
# ("1.5.1.", "2.8)") or lower-case letter ("1. a) ...") never matches.  The
# leading [A-Z] is a LOOKAHEAD so the heading word is not consumed.
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
    """读 chapter_map.json，返回该章的 sections 列表（直接读 JSON，不依赖 flows 的 chapter_map 模块）。"""
    cm_path = os.path.join(ext_dir, 'chapter_map.json')
    sections = []
    if os.path.exists(cm_path):
        with open(cm_path, encoding='utf-8') as fh:
            cm = json.load(fh)
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
