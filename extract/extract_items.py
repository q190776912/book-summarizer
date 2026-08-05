
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

import json, re, os, sys

from extract.b_layer import recover_missing_items
from extract.extract_items_en import extract_items_en

# Tail gap (pages after a section's last detected item, up to the next section
# or chapter end) considered "suspicious" rather than silently "resolved" once
# it exceeds this many pages. Mirrors D-layer's SUSPECT>5 threshold.
TAIL_GAP_THRESHOLD = 5

def _add_match(m, txt, p, i, all_blocks, raw_matches, active_section_label, chapter, label_re, cite_re, num_re):
    """Helper: process a regex match and append to raw_matches if valid."""
    ch_num = int(m.group(1))
    if ch_num != chapter:
        return
    sec = int(m.group(2))
    num = int(m.group(3))
    if sec > 15 or num > 50:
        return
    key = f"{ch_num}.{sec}-{num}"
    before = txt[max(0, m.start()-25):m.start()]
    after = txt[m.end():m.end()+50]

    key_esc = re.escape(m.group())

    # 0. Citation words directly before the number (same OCR block)
    if cite_re.search(before):
        return
    # 0b. Citation words at the END of the PREVIOUS OCR block. OCR often splits a
    #     sentence such as "因此，据" | "9.5-1知P是一个投影" into two blocks, so the
    #     cite word ("据") sits at the tail of the prior block, one block away.
    if i > 0:
        prev_tail = all_blocks[i-1][2][-15:].strip()
        if cite_re.search(prev_tail):
            return

    # 1. A FULL label word (定理/定义/引理/推论/命题/例) immediately before the number,
    #    optionally separated by whitespace or parens (e.g. 定理4.3-1 / 定理(3.3-1) /
    #    （谱定理）9.9-1 / 定义2.1-7). It is a real item ONLY when the number starts the
    #    block or the block is a standalone label heading; otherwise it is a
    #    cross-reference. Forward direction only — a "NUMBER 标签" real header
    #    (e.g. "4.3-1 汉恩-巴拿赫定理") is left untouched so genuine items are never
    #    dropped. (Must match the full 2-char label word, not just 例/定/引/推/命,
    #    otherwise 定理4.3-1 slips through because 理 sits between 定 and the number.)
    local = txt[max(0, m.start()-8):m.end()+4]
    if re.search(r'(?:定理|定义|引理|推论|命题|例)[\s（）()]*' + key_esc, local):
        prefix = txt[:m.start()].strip()
        if re.match(r'^(?:定义|定理|引理|推论|命题|例)$', prefix) or prefix.startswith(m.group()):
            pass
        else:
            return

    # 2. Number sits inside a parenthetical span that lists TWO OR MORE numbered
    #    items -> it is an enumeration of references, not an item definition.
    #    e.g. "（4.5，4.6)"  "（变形4.3-1，4.3-2）"  "（7.5-3，7.5-4，7：5-5）"
    op = txt.rfind('（', 0, m.start());  op = op if op != -1 else txt.rfind('(', 0, m.start())
    cl = txt.find('）', m.end());        cl = cl if cl != -1 else txt.find(')', m.end())
    if op != -1 and cl != -1 and op < m.start() < cl:
        if len(num_re.findall(txt[op:cl+1])) >= 2:
            return

    # 3. Range marker with another number nearby (e.g. "例子（1.1-2到1.2-3）")
    after_ctx = txt[m.end():m.end()+40]
    if re.search(r'[例定引推]', before):
        if num_re.search(before) or num_re.search(after_ctx) or re.search(r'[到至～]', before + after_ctx):
            return

    label = 'uncat'
    ctx_self = (before[-60:] if len(before) > 60 else before) + after[:40]
    lm = label_re.search(ctx_self)
    if lm:
        raw = lm.group()
        if re.search(r'例|Example', raw):
            label = '例'
        elif re.search(r'定义|Definition', raw):
            label = '定义'
        elif re.search(r'定理|Theorem', raw):
            label = '定理'
        elif re.search(r'引理|Lemma', raw):
            label = '引理'
        elif re.search(r'推论|Corollary', raw):
            label = '推论'
        elif re.search(r'命题|Proposition', raw):
            label = '命题'

    if label == 'uncat' and active_section_label:
        label = active_section_label

    if label == 'uncat':
        if i > 0:
            prev_txt = all_blocks[i-1][2]
            prev_label = label_re.search(prev_txt[-40:])
            if prev_label:
                raw = prev_label.group()
                if re.search(r'例|Example|定义|Definition', raw):
                    label = '例' if re.search(r'例|Example', raw) else '定义'
        if label == 'uncat' and i < len(all_blocks) - 1:
            next_txt = all_blocks[i+1][2]
            next_label = label_re.search(next_txt[:40])
            if next_label:
                raw = next_label.group()
                if re.search(r'例|Example|定义|Definition|定理|Theorem', raw):
                    label = '例' if re.search(r'例|Example', raw) else ('定义' if re.search(r'定义|Definition', raw) else '定理')

    text_preview = txt[max(0, m.start()-5):m.end()+80].replace('\n', ' ')
    raw_matches.append({'key': key, 'page': p, 'label': label, 'text': text_preview})

# ---------------------------------------------------------------------------
# TWO-LEVEL numbering scheme (e.g. 周民强《实变函数论》）
#   · 定义 has its OWN per-chapter counter (定义1.1, 定义1.2, ...)
#   · 定理/引理/推论/命题 SHARE one continuous counter (1.1, 1.2, ...)
#   · 例 are renumbered PER SECTION (例1, 例2 ...) — not emitted here; use
#     scan_items.py for example completeness.
# Produces keys like '定义1.1' / '定理1.1' that match the .md bold entries
# (**定义1.1**：, **定理1.1**：). The three-level N.S-N regex is deliberately
# NOT used here (it manufactures false-positive phantom keys for this scheme).
# ---------------------------------------------------------------------------
def extract_items_two_level(extract_dir, chapter, start_page, end_page):
    all_blocks = []
    for p in range(start_page, end_page + 1):
        fpath = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fpath):
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        for t in data.get("text", []):
            txt = t.get("text", "").strip()
            if not txt:
                continue
            poly = t.get("poly", [])
            y = poly[1] if poly and len(poly) >= 8 else 0
            all_blocks.append((p, y, txt))
    all_blocks.sort(key=lambda x: (x[0], x[1]))

    lab_re = re.compile(r'(定义|定理|引理|推论|命题)\s*(\d+)\s*[\.\·]\s*(\d+)')
    raw = []
    for p, y, txt in all_blocks:
        for m in lab_re.finditer(txt):
            c = int(m.group(2)); num = int(m.group(3))
            if c != chapter:
                continue
            label = m.group(1)
            key = f"{label}{c}.{num}"
            text_preview = txt[max(0, m.start()-5):m.end()+80].replace('\n', ' ')
            raw.append({'key': key, 'page': p, 'label': label, 'text': text_preview})

    seen = {}
    for it in raw:
        if it['key'] not in seen:
            seen[it['key']] = it
    items = sorted(seen.values(), key=lambda x: (x['page'], x['key']))
    # Continuity is independently verified by scan_items.py; no B-layer gap
    # re-scan here (the three-level re-scan logic is N.S-N specific).
    return items, [], []


def extract_items_fr(extract_dir, chapter, start_page, end_page, manual_overrides=None):
    """Fraleigh-style section-based two-level extractor.

    Fraleigh《抽象代数基础教程》: items are numbered per GLOBAL section —
    定义8.1 / 例1.2 / 表1.20 / 图3.6 — while the Chinese translation groups
    sections into chapters (ch1 = secs 1-7, ch2 = secs 8-11, ...). The first
    number is the SECTION, not the chapter, so the `c == chapter` filter of
    the 周民强 two-level scheme must NOT apply; instead keys are restricted to
    the sections belonging to this chapter (read from chapter_map.json's
    "sections" field). Labels include 例/表/图 which the built-in two-level
    scheme drops.

    chapter_map.json format: {"chapters": [{"num": N, "pdf_start": S,
    "pdf_end": E, "scheme": "fraleigh", "sections": [8, 9, 10, 11], ...}]}
    """
    import json as _json

    sections = None
    cm_path = os.path.join(extract_dir, 'chapter_map.json')
    if os.path.exists(cm_path):
        try:
            with open(cm_path, 'r', encoding='utf-8-sig') as f:
                cm = _json.load(f)
            chs = cm.get('chapters', []) if isinstance(cm, dict) else cm
            for e in chs:
                if e.get('num') == chapter and e.get('sections'):
                    sections = {int(s) for s in e['sections']}
                    break
        except Exception:
            sections = None

    all_blocks = []
    for p in range(start_page, end_page + 1):
        fpath = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fpath):
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            data = _json.load(f)
        for t in data.get("text", []):
            txt = t.get("text", "").strip()
            if not txt:
                continue
            poly = t.get("poly", [])
            y = poly[1] if poly and len(poly) >= 8 else 0
            all_blocks.append((p, y, txt))
    all_blocks.sort(key=lambda x: (x[0], x[1]))

    fr_re = re.compile(
        r'(定义|定理|引理|推论|命题|例|表|图)\s*(\d+)\s*[\.\．·]\s*(\d+)')
    raw = []
    for p, y, txt in all_blocks:
        for m in fr_re.finditer(txt):
            sec = int(m.group(2)); num = int(m.group(3))
            if sec > 80 or num > 120:
                continue
            if sections is not None and sec not in sections:
                continue
            label = m.group(1)
            key = f"{label}{sec}.{num}"
            text_preview = txt[max(0, m.start()-5):m.end()+80].replace('\n', ' ')
            raw.append({'key': key, 'page': p, 'label': label, 'text': text_preview})

    seen = {}
    for it in raw:
        if it['key'] not in seen:
            seen[it['key']] = it
    items = sorted(seen.values(), key=lambda x: (x['page'], x['key']))

    if manual_overrides:
        existing = {it['key']: idx for idx, it in enumerate(items)}
        for mo in manual_overrides:
            if mo['key'] in existing:
                items[existing[mo['key']]] = {'key': mo['key'], 'page': mo['page'],
                                              'label': mo['label'], 'text': mo['text'],
                                              'agent_recovered': True}
            else:
                items.append({'key': mo['key'], 'page': mo['page'],
                              'label': mo['label'], 'text': mo['text'],
                              'agent_recovered': True})
        items.sort(key=lambda x: (x['page'], x['key']))
    return items, [], []


def extract_items(extract_dir, chapter, start_page, end_page, manual_overrides=None, scheme='three-level', numbering='combined'):
    if scheme == 'fraleigh':
        return extract_items_fr(extract_dir, chapter, start_page, end_page, manual_overrides)
    if scheme == 'two-level':
        items, warnings, blocking = extract_items_two_level(extract_dir, chapter, start_page, end_page)
        if manual_overrides:
            existing = {it['key']: idx for idx, it in enumerate(items)}
            for mo in manual_overrides:
                if mo['key'] in existing:
                    items[existing[mo['key']]] = {'key': mo['key'], 'page': mo['page'],
                                                  'label': mo['label'], 'text': mo['text'],
                                                  'agent_recovered': True}
                else:
                    items.append({'key': mo['key'], 'page': mo['page'],
                                  'label': mo['label'], 'text': mo['text'],
                                  'agent_recovered': True})
            items.sort(key=lambda x: (x['page'], x['key']))
        return items, warnings, blocking
    # ---- Step 2: read all JSONs, sort by (page, poly_y) ----
    all_blocks = []  # (page, y, text)
    for p in range(start_page, end_page + 1):
        fpath = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fpath):
            continue
        with open(fpath, "r", encoding="utf-8") as f:
            data = json.load(f)
        for t in data.get("text", []):
            txt = t.get("text", "").strip()
            if not txt:
                continue
            poly = t.get("poly", [])
            # poly = [x1,y1, x2,y1, x2,y2, x1,y2] flattened
            y = poly[1] if poly and len(poly) >= 8 else 0
            all_blocks.append((p, y, txt))
    all_blocks.sort(key=lambda x: (x[0], x[1]))

    # ---- regexes (defined BEFORE the section-scan loop below) ----
    # Step 2: broader pattern (also catches 1.3.9 → 1.3-9)
    num_re = re.compile(r'(\d+)\s*[\.\-\·\，\s]\s*(\d+)\s*[\-\.\·\，\s]\s*(\d+)')
    label_re = re.compile(r'(?:定义|定理|引理|推论|命题)\s*（|例(?:子)?|Example|Definition|Theorem|Lemma|Corollary|Proposition')
    cite_re = re.compile(r'(见|由|根据|参考|参见|据|Cf\.)')
    # Step 3: section heading (e.g. "§1.1 Name", "1.1 Name"). NOT matching "1.1-1" (numbered items).
    sec_heading_re = re.compile(r'^(?:§\s*)?(\d+)\.(\d+)(?:\s{2,}|\s+[^\d\-])')
    # Section-level label: a text block that is a standalone "例子" or "Examples" heading
    sec_label_re = re.compile(r'^(例[子]?|Examples?)$')

    # ---- Pass 0: collect the sections actually present in THIS chapter ----
    # Used to constrain the fallback regex (see below) so that stray "37-40"
    # (exercise range) or "1837-1920" (date range) cannot be mis-read as a
    # phantom "3.7" section. A fallback item c.s-N is only kept when s is a
    # real section of this chapter.
    chapter_sections = set()
    for p, y, txt in all_blocks:
        stripped = txt.strip().rstrip('：:．.，, ')
        sm = sec_heading_re.match(stripped)
        if sm and int(sm.group(1)) == chapter:
            chapter_sections.add(int(sm.group(2)))

    # ---- Step 2a: fallback pattern for garbled numbers (e.g. "21_7" → 2.1-7) ----
    fallback_re = re.compile(r'(\d)(\d)[\s_\-\·]\s*(\d+)')

    # ---- Step 2: collect all number matches with context ----
    raw_matches = []
    active_section_label = None   # label inherited from section heading, persists across pages

    for i, (p, y, txt) in enumerate(all_blocks):
        stripped = txt.strip().rstrip('：:．.，, ')  # remove trailing punctuation that OCR may add

        # Detect section heading → reset section-level label
        if sec_heading_re.match(stripped):
            active_section_label = None

        # Detect section-level label heading (e.g. "例子", "Examples")
        if sec_label_re.search(stripped):
            active_section_label = '例'
            continue

        # Step 4: find all number patterns (primary 3-group N.S-i)
        for m in num_re.finditer(txt):
            _add_match(m, txt, p, i, all_blocks, raw_matches,
                       active_section_label, chapter, label_re, cite_re, num_re)

        # Step 4b: fallback 2-group pattern for garbled "21_7" → 2.1-7
        m2 = fallback_re.search(txt)
        if m2:
            c = int(m2.group(1))
            s = int(m2.group(2))
            n = int(m2.group(3))
            # Only accept when s is a section actually present in this chapter,
            # so exercise/date ranges like "37-40" / "1837-1920" cannot be
            # mis-read as a phantom "3.7" section.
            if c == chapter and s <= 15 and n <= 50 and s in chapter_sections:
                key2 = f"{c}.{s}-{n}"
                if key2 not in {rm['key'] for rm in raw_matches}:
                    # Fallback quality filter: require non‑garbage text after the match
                    after_garbled = txt[m2.end():].strip()
                    if len(after_garbled) >= 8 and any('\u4e00' <= ch <= '\u9fff' or ch.isalpha() for ch in after_garbled[:12]):
                        _add_match(m2, txt, p, i, all_blocks, raw_matches,
                                   active_section_label, chapter, label_re, cite_re, num_re)

    # ---- Dedup: prefer non-裸 label ----
    seen = {}
    for it in raw_matches:
        if it['key'] not in seen:
            seen[it['key']] = it
        elif seen[it['key']]['label'] == 'uncat' and it['label'] != 'uncat':
            seen[it['key']] = it

    items = sorted(seen.values(), key=lambda x: (x['page'], x['key']))

    # ---- Merge manual overrides (e.g. OCR-garbled items recovered by agent) ----
    if manual_overrides:
        existing = {it['key']: idx for idx, it in enumerate(items)}
        for mo in manual_overrides:
            if mo['key'] in existing:
                items[existing[mo['key']]] = {'key': mo['key'], 'page': mo['page'],
                                              'label': mo['label'], 'text': mo['text'],
                                              'agent_recovered': True}
            else:
                items.append({'key': mo['key'], 'page': mo['page'],
                              'label': mo['label'], 'text': mo['text'],
                              'agent_recovered': True})
        items.sort(key=lambda x: (x['page'], x['key']))

    # ---- Step 5-6: boundary & density checks with auto-recovery (B-layer) ----
    items, warnings, blocking = recover_missing_items(
        extract_dir, chapter, start_page, end_page, items, label_re, TAIL_GAP_THRESHOLD, numbering
    )
    return items, warnings, blocking


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description="Extract numbered items from book JSON pages.")
    ap.add_argument("pos", nargs="*", help="CN: <ch> <start> <end> <extract_dir> | EN: <start> <end> <extract_dir>")
    ap.add_argument("--lang", choices=["cn", "en"], default="cn")
    ap.add_argument("--scheme", default="three-level", help="two-level|three-level (CN only)")
    ap.add_argument("--manual", default=None, help="path to manual_overrides json (CN only)")
    ap.add_argument("--examples", action="store_true", help="include Example items (EN only)")
    ap.add_argument("--verbose", action="store_true")
    ns = ap.parse_args()

    if ns.lang == "en":
        if len(ns.pos) < 3:
            ap.error("EN mode needs: <start> <end> <extract_dir>")
        start, end, extract_dir = int(ns.pos[0]), int(ns.pos[1]), ns.pos[2]
        items = extract_items_en(extract_dir, start, end, want_examples=ns.examples)
        print(f"=== ITEMS p{start}-{end} ({len(items)}) ===")
        cur_sec = None
        for it in items:
            sec = it["key"].split(".")[0]
            if sec != cur_sec:
                cur_sec = sec
                print()
            print(f"{it['key']:22s} p{it['page']:3d}  {it['text'][:80]}")
        print(f"\nTotal: {len(items)}")
    else:
        if len(ns.pos) < 4:
            ap.error("CN mode needs: <ch> <start> <end> <extract_dir>")
        ch, start, end, extract_dir = int(ns.pos[0]), int(ns.pos[1]), int(ns.pos[2]), ns.pos[3]
        manual = None
        if ns.manual and os.path.exists(ns.manual):
            with open(ns.manual, 'r', encoding='utf-8') as f:
                manual = json.load(f)
            print(f"[INFO] Loaded {len(manual)} manual overrides from {ns.manual}")
        items, warnings, blocking = extract_items(extract_dir, ch, start, end, manual_overrides=manual, scheme=ns.scheme)
        print(f"=== Ch{ch} ITEMS ===")
        cur_sec = ""
        for it in items:
            sec_label = '.'.join(it['key'].split('.')[:2])
            if sec_label != cur_sec:
                cur_sec = sec_label
                print()
            print(f"{it['key']:8s} [{it['label']}] p{it['page']:3d}  {it['text']}")
        if warnings:
            print(f"\n=== WARNINGS (B-layer extraction completeness) ===")
            for w in warnings:
                print(w)
        if blocking:
            print(f"\n=== BLOCKING ({len(blocking)}) — extraction incomplete, must resolve before writing ===")
        else:
            print(f"\n=== B-layer: no blocking issues (all boundary/tail re-scans clean) ===")
        print(f"\nTotal: {len(items)}")
