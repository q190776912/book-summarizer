import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json, re
from collections import defaultdict

# (Grouping is now driven by the BookConfig.ordinal GroupConfig array; the old
# SEP_COMBINED/SEP_PER_TYPE constants are gone — see lib/config.py GroupConfig.)
from lib.regexlib import SEP_NUMERIC

# ---------------------------------------------------------------------------
# B-LAYER ("extraction blocking") recovery logic.
# Raw re-scan + auto-recovery of missing items in boundary / internal-gap /
# tail-gap regions. Pure functions: all state (extract_dir, chapter, label_re,
# existing_keys, TAIL_GAP_THRESHOLD) is passed in by the caller in
# extract_items.py. No import back into extract_items (no circular import).
# ---------------------------------------------------------------------------

def _rescan_gap(extract_dir, chapter, sec, p_start, p_end):
    """Raw re-scan of pages [p_start, p_end] for C.sec-N patterns, WITHOUT the
    cross-reference filter, to surface any item the strict pass may have dropped
    in a boundary/gap region (e.g. an item whose label was garbled into a
    cross-reference-like form). Returns list of (page, key, snippet)."""
    found = []
    if p_end < p_start:
        return found
    num_re = re.compile(r'(\d+)\s*' + SEP_NUMERIC + r'\s*(\d+)\s*' + SEP_NUMERIC + r'\s*(\d+)')
    fb = re.compile(r'(\d)(\d)' + SEP_NUMERIC + r'\s*(\d+)')
    for p in range(max(1, p_start), p_end + 1):
        fp = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        with open(fp, 'r', encoding='utf-8') as f:
            data = json.load(f)
        for t in data.get("text", []):
            txt = t.get("text", "").strip()
            if not txt:
                continue
            for m in num_re.finditer(txt):
                if int(m.group(1)) == chapter and int(m.group(2)) == sec:
                    found.append((p, f"{chapter}.{sec}-{m.group(3)}", txt[max(0, m.start()-5):m.end()+30]))
            m2 = fb.search(txt)
            if m2 and int(m2.group(1)) == chapter and int(m2.group(2)) == sec:
                found.append((p, f"{chapter}.{sec}-{m2.group(3)}", txt[max(0, m2.start()-5):m2.end()+30]))
    return found


def _try_label_rescan(snippet, active_section_label, label_re):
    lm = label_re.search(snippet)
    if lm:
        raw = lm.group()
        if re.search(r'例|Example', raw):
            return '例'
        elif re.search(r'练习|习题|Exercise', raw):
            return '练习'
        elif re.search(r'定义|Definition', raw):
            return '定义'
        elif re.search(r'定理|Theorem', raw):
            return '定理'
        elif re.search(r'引理|Lemma', raw):
            return '引理'
        elif re.search(r'推论|Corollary', raw):
            return '推论'
        elif re.search(r'命题|Proposition', raw):
            return '命题'
    return active_section_label if active_section_label else 'uncat'


def _scan_and_recover(p_start, p_end, sec_num, section_label, extract_dir, chapter, existing_keys, label_re):
    """Re-scan gap pages and auto-recover items with plausible labels."""
    recovered = []
    keys_found = set()
    found = _rescan_gap(extract_dir, chapter, sec_num, p_start, p_end)
    for page, key, snippet in found:
        if key in existing_keys or key in keys_found:
            continue
        label = _try_label_rescan(snippet, section_label, label_re)
        # Language-agnostic content check (replaces the old CJK-only test,
        # which wrongly dropped English/other-language books). Recover when we
        # can determine a label (not 裸) OR the snippet carries real alphabetic
        # content in ANY script (≥2 Unicode letters) or a LaTeX command. A bare
        # "3.2-1" OCR fragment with no letters is rejected, not hallucinated.
        has_alpha = (len(re.findall(r'[^\W\d_]', snippet)) >= 2) or ('\\' in snippet)
        if label != 'uncat' or has_alpha:
            recovered.append({'key': key, 'page': page, 'label': label, 'text': snippet[:120]})
            keys_found.add(key)
            existing_keys.add(key)
    return recovered


def _key_prefix_num(key, depth):
    """Parse a key like 'C.S-N' / 'C.S' / 'C-N' into (prefix_str, num).

    `prefix_str` is the first ``depth-1`` numeric components joined by '.'
    (the counter reset-prefix for this group); `num` is the component at
    index ``depth-1`` (the item number within the group).  Returns
    ('', 0) for an unparseable key (no digits)."""
    nums = [int(x) for x in re.findall(r'\d+', key)]
    if not nums:
        return '', 0
    if len(nums) >= depth:
        prefix = nums[:depth - 1]
        num = nums[depth - 1]
        return '.'.join(str(x) for x in prefix), num
    # Key has fewer components than `depth` (heading-only or two-level form):
    # treat all components as the prefix, num = last component.
    return '.'.join(str(x) for x in nums), (nums[-1] if nums else 0)


def _group_key(it, cfg):
    """Section-grouping key for the missing-number scan, NAMESPACED BY GROUP.

    Different BookConfig groups (GroupConfig) share a merged counter; the group
    index ``gi`` is prepended so counters of different groups NEVER merge.  The
    prefix length is driven by the matched group's ``depth`` (per the v2 schema).
    """
    label = it.get('label') or 'uncat'
    g = cfg.group_for_label(label)
    gi = cfg.ordinal.index(g)
    prefix_str, _num = _key_prefix_num(it['key'], g.depth)
    return f"{gi}:{prefix_str}" if prefix_str else f"{gi}:file"


def recover_missing_items(extract_dir, chapter, start_page, end_page, items, label_re, TAIL_GAP_THRESHOLD, cfg=None):
    """Step 5-6: boundary & density checks with auto-recovery (B-LAYER).

    Detection 宗旨 (the part that flags missing numbers for the agent to fill):
      1. 首项检验  — a section/type sequence must start at its first number (usually 1).
      2. 连续性     — every number in [first, last] must be present (middle gaps = dropped).
      3. 尾部校验   — after the last found number, re-scan following pages for
                     max+1, max+2, ...; any such item the strict pass dropped is recovered.

    When a gap (head/internal) is detected and the OCR re-scan cannot recover it,
    it is reported as BLOCKING so the agent verifies/fills it — NOT silently
    resolved as "likely absent" (that hid real drops swallowed by OCR, e.g. 4.11-4).
    Returns (items, warnings, blocking)."""
    by_sec = defaultdict(list)
    for it in items:
        sec_key = _group_key(it, cfg)
        num = int(re.findall(r'\d+', it['key'])[-1])
        by_sec[sec_key].append((num, it))

    warnings = []
    blocking = []

    # Track keys we've auto-recovered to avoid re-adding
    existing_keys = {it['key'] for it in items}
    auto_recovered = []

    def _sec_sort_key(k):
        # New key format is "gi:prefix" (group index : numeric prefix).
        gi_str, prefix = k.split(':', 1)
        return (int(gi_str), tuple(int(x) for x in re.findall(r'\d+', prefix)))
    sec_order = sorted(by_sec.keys(), key=_sec_sort_key)

    # First pass: collect all auto-recoverable items
    for idx, sec_key in enumerate(sec_order):
        nums = by_sec[sec_key]
        nums_sorted = sorted(nums, key=lambda x: x[0])
        first_num = nums_sorted[0][0]
        last_num = nums_sorted[-1][0]
        first_page = nums_sorted[0][1]['page']
        last_page = nums_sorted[-1][1]['page']
        prefix_part = sec_key.split(':', 1)[1]
        comps = [int(x) for x in re.findall(r'\d+', prefix_part)]
        sec_num = comps[1] if len(comps) >= 2 else (comps[0] if comps else 0)
        detected = {n for n, _ in nums_sorted}

        # Get active section label (例/定义/etc.) from items in this section
        sec_labels = [it['label'] for _, it in nums_sorted if it['label'] != 'uncat']
        section_label = sec_labels[0] if sec_labels else None

        # --- Boundary check: head (首项检验, items before first_num) ---
        # NOTE: this extraction-side pass is SECONDARY. Its role is to surface
        # gaps the strict OCR pass dropped; it must NOT hard-block on its own
        # because OCR phantom matches (a stray "8.6-15" citation) inflate
        # last_num and fabricate gaps. The authoritative missing-number
        # detection runs on the written .md in verify/layers/b_layer.py.
        if first_num > 1:
            recovered = _scan_and_recover(start_page, first_page - 1, sec_num, section_label, extract_dir, chapter, existing_keys, label_re)
            auto_recovered.extend(recovered)
            still_missing = [n for n in range(1, first_num)
                           if f"{chapter}.{sec_num}-{n}" not in existing_keys]
            if recovered and still_missing:
                msg = (f"  WARN (BLOCKING): {sec_key} starts at -{first_num}, items "
                       f"{', '.join(f'-{n}' for n in still_missing)} still missing after auto-recovery")
                warnings.append(msg); blocking.append(msg)
            elif not recovered and still_missing:
                warnings.append(f"  WARN (resolved): {sec_key} starts at -{first_num}; re-scan "
                                f"p{start_page}-{first_page-1} found nothing → likely starts at -{first_num}")
            else:
                warnings.append(f"  WARN (resolved): {sec_key} starts at -{first_num}; auto-recovered all gaps")

        # --- Internal gap check (连续性, missing items within [first, last]) ---
        expected = set(range(first_num, last_num + 1))
        actual = {n for n, _ in nums_sorted}
        missing = sorted(expected - actual)
        if missing and not (len(missing) == 1 and first_num == 1 and missing == [last_num]):
            recovered = _scan_and_recover(first_page, last_page, sec_num, section_label, extract_dir, chapter, existing_keys, label_re)
            auto_recovered.extend(recovered)
            still_missing = [n for n in missing
                           if f"{chapter}.{sec_num}-{n}" not in existing_keys]
            if recovered and still_missing:
                msg = (f"  WARN (BLOCKING): {sec_key} missing items "
                       f"{', '.join(f'-{m}' for m in still_missing)}; still missing after auto-recovery")
                warnings.append(msg); blocking.append(msg)
            elif not recovered and still_missing:
                # Found nothing in re-scan → likely cross-refs/absent (or an OCR
                # swallow). The .md-side B-layer check is what ultimately decides.
                warnings.append(f"  WARN (resolved): {sec_key} missing items "
                                f"{', '.join(f'-{m}' for m in missing)}; re-scan found nothing → likely cross-refs/absent")
            else:
                warnings.append(f"  WARN (resolved): {sec_key} internal gaps auto-recovered")

        # --- Tail gap check (items after last_num, up to next section OR chapter end) ---
        if idx + 1 < len(sec_order):
            next_key = sec_order[idx + 1]
            next_first_page = min(it['page'] for _, it in by_sec[next_key])
            gap_end = next_first_page - 1
            next_desc = f"next section p{next_first_page}"
        else:
            # Last section: no following section. Scan its tail up to the chapter
            # end instead of skipping it — the old behaviour left the last
            # section's tail completely unchecked (B-layer blind spot #1).
            gap_end = end_page
            next_desc = f"chapter end p{end_page}"
        gap = gap_end - last_page
        if gap >= 1:
            recovered = _scan_and_recover(last_page + 1, gap_end, sec_num, section_label, extract_dir, chapter, existing_keys, label_re)
            auto_recovered.extend(recovered)
            if not recovered:
                if gap > TAIL_GAP_THRESHOLD:
                    # Large tail gap with no recoverable item: don't silently call
                    # it "resolved". Flag it so a human verifies the chapter/section
                    # genuinely ends here (vs. an OCR-unreadable tail item we missed).
                    warnings.append(f"  WARN (suspicious): {sec_key} last -{last_num} on p{last_page}, "
                                    f"{next_desc} ({gap}pp gap > {TAIL_GAP_THRESHOLD}); large tail gap with "
                                    f"no recoverable item — verify the chapter/section actually ends here")
                else:
                    warnings.append(f"  WARN (resolved): {sec_key} last -{last_num} on p{last_page}, "
                                    f"{next_desc} ({gap}pp gap); re-scan gap found nothing → likely ends at -{last_num}")

    # Merge auto-recovered items into main items list
    if auto_recovered:
        item_keys = {it['key'] for it in items}
        for rec in auto_recovered:
            if rec['key'] not in item_keys:
                items.append(rec)
                item_keys.add(rec['key'])
        items.sort(key=lambda x: (x['page'], x['key']))
        if '--verbose' in sys.argv:
            print(f"[AUTO-RECOVER] Added {len(auto_recovered)} item(s) from boundary re-scans: "
                  f"{[r['key'] for r in auto_recovered]}")

    return items, warnings, blocking
