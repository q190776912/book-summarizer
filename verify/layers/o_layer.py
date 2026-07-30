"""
o_layer.py — O-LAYER (order 15): ordinal sub-item gap detection (warning-only).

Non-blocking: emits '~' (tail/OCR cross-ref) and 'x' (head/internal) lines but is
NEVER auto-fixed and never forces a FAIL by itself. check_ordinal_subitem_gaps is
Self-contained implementation of check_ordinal_subitem_gaps (bodies relocated from the deleted structure_layers.py), forwarding the OCR cross-reference args.
"""

from verify.registry import VerifyLayer, LayerResult, LayerFixResult

import re

import os

_O_PAREN_RE = re.compile(
    r'^\s*(?:[-*–]\s+)?'          # optional list marker (-, *, –)
    r'(?:\*\*)?'                  # optional bold open
    r'[（(]([0-9]+|[a-z]+)[)）]'   # (content) — digits or lowercase letters
    r'(?:\*\*)?'                  # optional bold close
)

_O_BOLD_DOT_RE = re.compile(
    r'^\s*(?:[-*–]\s+)?'          # optional list marker
    r'\*\*([0-9]+|[a-z]+)[.)]\*\*'  # **N.** or **a)**
)

_O_PLAIN_DOT_RE = re.compile(
    r'^(\s{0,3})'                 # 0-3 spaces indent (top-level only)
    r'([0-9]+|[a-z]+)[.)]\s+\S'   # N. or a) followed by space + content
)

_O_CONTEXT_RE = re.compile(
    r'(注解|注释|注[：:]|备注|说明|Remarks?|Notes?|Comments?)', re.IGNORECASE
)

_ROMAN_VALID = re.compile(
    r'^(m{0,3})(cm|cd|d?c{0,3})(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$', re.I
)

_ROMAN_VALUES = {'i': 1, 'v': 5, 'x': 10, 'l': 50, 'c': 100, 'd': 500, 'm': 1000}

def _o_match_line(line):
    """Try to extract an ordinal label from a line. Returns the raw label
    string (e.g. '3', 'ii', 'b') or None if the line is not a numbered item.
    
    Excludes blockquote lines (`>` prefix) from plain-dot matching to avoid
    false positives on proof steps (1. 2. 3. inside > **证明思路**).
    Parenthesized and bold patterns are allowed inside blockquotes since
    `> **(1)**` is a valid sub-item inside an example block.
    """
    # Pattern A: parenthesized (works anywhere, including inside blockquotes)
    m = _O_PAREN_RE.match(line)
    if m:
        return m.group(1)
    # Pattern B: bold with dot (works anywhere)
    m = _O_BOLD_DOT_RE.match(line)
    if m:
        return m.group(1)
    # Pattern C: plain with dot (top-level only, exclude blockquotes)
    if not line.lstrip().startswith('>'):
        m = _O_PLAIN_DOT_RE.match(line)
        if m:
            return m.group(2)
    return None

def _roman_to_int(s):
    """Convert a roman numeral string to integer. Returns 0 if invalid."""
    s = s.lower()
    if not _ROMAN_VALID.match(s):
        return 0
    total = 0
    prev = 0
    for ch in reversed(s):
        val = _ROMAN_VALUES.get(ch, 0)
        if val < prev:
            total -= val
        else:
            total += val
        prev = val
    return total

def _int_to_roman(n):
    """Convert integer 1-3999 to lowercase roman numeral string."""
    if n <= 0 or n > 3999:
        return str(n)
    table = [
        (1000, 'm'), (900, 'cm'), (500, 'd'), (400, 'cd'),
        (100, 'c'), (90, 'xc'), (50, 'l'), (40, 'xl'),
        (10, 'x'), (9, 'ix'), (5, 'v'), (4, 'iv'), (1, 'i'),
    ]
    result = []
    for val, sym in table:
        while n >= val:
            result.append(sym)
            n -= val
    return ''.join(result)

def _classify_block(items):
    """Classify a block of (line_idx, raw_label) pairs as 'numeric', 'roman',
    or 'alpha'. Returns (type, [(line_idx, ordinal_int), ...]) where ordinal_int
    is the position in the sequence (1-based)."""
    labels = [raw for _, raw in items]

    # If all labels are purely digits → numeric
    if all(lb.isdigit() for lb in labels):
        return 'numeric', [(li, int(lb)) for li, lb in items]

    # If all labels are purely alpha
    if all(lb.isalpha() for lb in labels):
        # Disambiguate roman vs alpha:
        # - If ANY label is multi-char and valid roman (ii, iii, iv, vi, etc.) → roman
        # - If all single-char and all in {i, v, x, l, c, d, m} → roman
        # - Otherwise → alpha
        multi_char = [lb for lb in labels if len(lb) > 1]
        if multi_char:
            if all(_ROMAN_VALID.match(lb) for lb in multi_char):
                return 'roman', [(li, _roman_to_int(lb)) for li, lb in items]
            else:
                return 'alpha', [(li, ord(lb) - ord('a') + 1) for li, lb in items]
        else:
            # All single-char: check if they're all roman chars
            roman_chars = set('ivxlcdm')
            if all(lb.lower() in roman_chars for lb in labels):
                return 'roman', [(li, _roman_to_int(lb)) for li, lb in items]
            else:
                return 'alpha', [(li, ord(lb.lower()) - ord('a') + 1) for li, lb in items]

    # Mixed (shouldn't happen with the regex, but fallback)
    return 'numeric', [(li, int(lb) if lb.isdigit() else 0) for li, lb in items]

def check_ordinal_subitem_gaps(md_file, ext_dir=None, ch=None, start=None, end=None):
    """O-LAYER: detect gaps in parenthesized numbered/lettered sub-item sequences.

    Supports three sequence types: numeric (1,2,3), roman (i,ii,iii), alpha (a,b,c).

    Returns a list of violation/warning strings. Empty = pass.
    Each entry is prefixed with severity:
      'x' = blocking (head/internal gap with >= 3 items in block)
      '~' = non-blocking warning (tail gap from OCR cross-ref)

    Parameters:
      md_file: path to the chapter .md
      ext_dir: (optional) _extract directory for OCR cross-reference
      ch: (optional) chapter number for OCR cross-ref
      start, end: (optional) page range for OCR cross-ref
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []

    n = len(lines)
    out = []

    # Phase 1: find all numbered/lettered lines
    item_lines = []  # (line_idx, raw_label)
    for i, ln in enumerate(lines):
        label = _o_match_line(ln)
        if label:
            item_lines.append((i, label))

    if not item_lines:
        return []

    # Group into blocks: consecutive items with line gap <= 4
    blocks = []  # list of [(line_idx, raw_label), ...]
    cur_block = [item_lines[0]]
    for k in range(1, len(item_lines)):
        prev_idx = item_lines[k - 1][0]
        cur_idx = item_lines[k][0]
        if cur_idx - prev_idx <= 4:  # allow up to 3 lines gap (continuation text)
            cur_block.append(item_lines[k])
        else:
            blocks.append(cur_block)
            cur_block = [item_lines[k]]
    blocks.append(cur_block)

    # Phase 2: check each block for gaps
    for block in blocks:
        if len(block) < 3:
            continue  # too few items — likely cross-references, not a sequence

        seq_type, ordinal_items = _classify_block(block)
        # Filter out any items with ordinal 0 (failed conversion)
        ordinal_items = [(li, ord_val) for li, ord_val in ordinal_items if ord_val > 0]
        if len(ordinal_items) < 3:
            continue

        ordinals = sorted(set(val for _, val in ordinal_items))
        first_line = ordinal_items[0][0] + 1  # 1-indexed for display
        min_ord, max_ord = ordinals[0], ordinals[-1]
        ord_set = set(ordinals)

        # Find context header (look up to 5 lines above first item)
        ctx_label = ""
        for k in range(max(0, block[0][0] - 5), block[0][0]):
            cm = _O_CONTEXT_RE.search(lines[k])
            if cm:
                ctx_label = cm.group(0).strip()
                break
        if not ctx_label:
            # Use the line just above as context
            for k in range(block[0][0] - 1, max(0, block[0][0] - 4) - 1, -1):
                s = lines[k].strip()
                if s and not s.startswith('-'):
                    ctx_label = s[:30]
                    break

        # Format helper: display ordinal in original notation
        def _fmt(ord_val):
            if seq_type == 'numeric':
                return str(ord_val)
            elif seq_type == 'roman':
                return _int_to_roman(ord_val)
            else:  # alpha
                return chr(ord('a') + ord_val - 1) if 1 <= ord_val <= 26 else str(ord_val)

        type_tag = {'numeric': 'num', 'roman': 'roman', 'alpha': 'alpha'}[seq_type]

        # HEAD gap: sequence starts above 1
        if min_ord > 1:
            head_missing = [_fmt(v) for v in range(1, min_ord)]
            out.append(
                f"  x L{first_line}: [{ctx_label}] HEAD gap ({type_tag}) — "
                f"sequence starts at ({_fmt(min_ord)}), "
                f"missing ({', '.join(head_missing)}) before first item"
            )

        # INTERNAL gaps: missing ordinals between min and max
        expected = set(range(min_ord, max_ord + 1))
        internal_missing = sorted(expected - ord_set)
        if internal_missing:
            present_str = ', '.join(_fmt(v) for v in ordinals)
            missing_str = ', '.join(_fmt(v) for v in internal_missing)
            out.append(
                f"  x L{first_line}: [{ctx_label}] INTERNAL gap ({type_tag}) — "
                f"present: ({present_str}), missing: ({missing_str})"
            )

        # TAIL gap: cross-reference OCR JSON for higher numbers (numeric only)
        if seq_type == 'numeric' and ext_dir and ch is not None and start is not None and end is not None:
            tail_found = _o_tail_ocr_scan(ext_dir, ch, start, end, ordinals, ctx_label)
            if tail_found:
                out.append(
                    f"  ~ L{first_line}: [{ctx_label}] TAIL gap — md max = ({max_ord}), "
                    f"but OCR shows higher number(s): ({', '.join(map(str, tail_found))})"
                )

    return out

def _o_tail_ocr_scan(ext_dir, ch, start, end, md_nums, ctx_label):
    """Scan OCR JSON for parenthesized numbers higher than md max, in the
    vicinity of the same context keyword. Returns sorted list of tail numbers
    found in OCR but absent from md. Empty = no tail gap."""
    import json as _json
    max_num = max(md_nums)
    num_set = set(md_nums)
    # Build a regex to find (N) patterns in OCR text
    ocr_num_re = re.compile(r'[（(](\d{1,3})[)）]')
    # Context keyword for proximity matching
    ctx_kw = ctx_label.rstrip('：:').strip() if ctx_label else ''

    tail_candidates = set()
    for p in range(start, min(end + 1, start + 20)):  # limit scan to first 20 pages
        fp = os.path.join(ext_dir, f'page_{p:03d}.json')
        if not os.path.exists(fp):
            continue
        try:
            with open(fp, encoding='utf-8') as f:
                data = _json.load(f)
        except Exception:
            continue
        full_text = '\n'.join(t.get('text', '') for t in data.get('text', []))
        # Only scan pages that contain the context keyword
        if ctx_kw and ctx_kw not in full_text:
            continue
        for m in ocr_num_re.finditer(full_text):
            num = int(m.group(1))
            if num > max_num and num <= max_num + 10 and num not in num_set:
                # Verify it's in a sequence context (nearby numbers from md_nums)
                # Check +-200 chars for at least one known number
                lo = max(0, m.start() - 200)
                hi = min(len(full_text), m.end() + 200)
                vicinity = full_text[lo:hi]
                has_neighbor = any(
                    re.search(rf'[（(]{n}[)）]', vicinity) for n in md_nums
                )
                if has_neighbor:
                    tail_candidates.add(num)

    return sorted(tail_candidates)

class OLayer(VerifyLayer):
    code = 'O'
    order = 15
    auto_fixable = False

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={
            'o_subitem_gaps': check_ordinal_subitem_gaps(
                ctx.md_file, ext_dir=ctx.ext_dir, ch=ctx.ch,
                start=ctx.start, end=ctx.end),
        })
