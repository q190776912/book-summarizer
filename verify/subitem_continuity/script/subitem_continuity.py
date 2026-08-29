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

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 verify/subitem_continuity/subitem_continuity.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""
subitem_continuity.py — O-LAYER (order 15): ordinal sub-item gap detection (warning-only).

Non-blocking: emits '~' (tail/OCR cross-ref) and 'x' (head/internal) lines but is
NEVER auto-fixed and never forces a FAIL by itself. check_ordinal_subitem_gaps is
Self-contained implementation of check_ordinal_subitem_gaps, forwarding the OCR cross-reference args.
"""

from verify.script.base import VerifyLayer, LayerResult, LayerFixResult

import re

import os

# Inline math must never contribute ordinal labels: notation like $f(x)$ or
# $g(t)$ contains parenthesized letters that are NOT sub-item markers
# ((x) would be read as roman 10, (t) as alpha 20, producing phantom
# INTERNAL gaps in theorem statements). Strip before matching.
_INLINE_MATH_RE = re.compile(r'\$[^$]*\$')

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
    """Try to extract ordinal label(s) from a line. Returns a LIST of raw
    label strings (e.g. ['3'], ['ii'], ['b']) or [] if the line is not a
    numbered item.

    A line is treated as a sub-item sequence when it BEGINS with a sub-item
    marker (paren / bold-dot / plain-dot). On such lines we capture EVERY
    `(n)` / `**n.**` marker in the line, not just the first — this correctly
    handles inline sequences like `引理 (1) a；(2) b；(3) c；` where the
    numbers share one physical line (previously only the leading number was
    seen, producing a false "missing (2)(3)" warning).

    Excludes blockquote lines (`>` prefix) from plain-dot matching to avoid
    false positives on proof steps (1. 2. 3. inside > **证明思路**).
    Parenthesized and bold patterns are allowed inside blockquotes since
    `> **(1)**` is a valid sub-item inside an example block.
    """
    # Strip inline math BEFORE matching: $f(x)$ / $g(t)$ contain
    # parenthesized letters that are function arguments, not ordinals.
    line = _INLINE_MATH_RE.sub(' MATH ', line)
    # Pattern A: parenthesized (works anywhere, including inside blockquotes)
    m = _O_PAREN_RE.match(line)
    if m:
        labels = [mm.group(1) for mm in
                  re.finditer(r'[（(]([0-9]+|[a-z]+)[)）]', line)]
        if labels:
            return labels
        return [m.group(1)]
    # Pattern B: bold with dot (works anywhere)
    m = _O_BOLD_DOT_RE.match(line)
    if m:
        labels = [mm.group(1) for mm in
                  re.finditer(r'\*\*([0-9]+|[a-z]+)[.)]\*\*', line)]
        if labels:
            return labels
        return [m.group(1)]
    # Pattern C: plain with dot (top-level only, exclude blockquotes)
    if not line.lstrip().startswith('>'):
        m = _O_PLAIN_DOT_RE.match(line)
        if m:
            return [m.group(2)]
    return []

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

def _split_roman_suffix(lb):
    """'iia' -> 'ii' when the leading part is valid roman and the tail is a short
    alpha suffix; 'ii' -> 'ii'. Returns None if the label is not of that shape."""
    lb = lb.lower()
    for cut in range(len(lb), 0, -1):
        head, tail = lb[:cut], lb[cut:]
        if len(tail) <= 2 and _ROMAN_VALID.match(head):
            return head
    return None

def _alpha_to_int(lb):
    """Spreadsheet-style alpha ordinal: a=1 .. z=26, aa=27, ab=28 ...
    Tolerates multi-char labels (previously `ord()` crashed on them)."""
    n = 0
    for ch in lb.lower():
        if 'a' <= ch <= 'z':
            n = n * 26 + (ord(ch) - ord('a') + 1)
        else:
            return 0
    return n

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
            # Roman with an alpha sub-suffix, e.g. (i) (iia) (iib) — textbooks use
            # this for sub-cases. Rank by the roman prefix; duplicates collapse.
            split = [_split_roman_suffix(lb) for lb in labels]
            if all(s is not None for s in split):
                return 'roman', [(li, _roman_to_int(s)) for (li, _), s in zip(items, split)]
            # Heterogeneous labelling we cannot rank — skip rather than emit noise.
            return 'mixed', []
        else:
            # All single-char: check if they're all roman chars
            roman_chars = set('ivxlcdm')
            if all(lb.lower() in roman_chars for lb in labels):
                return 'roman', [(li, _roman_to_int(lb)) for li, lb in items]
            else:
                return 'alpha', [(li, _alpha_to_int(lb)) for li, lb in items]

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
    in_math = False
    for i, ln in enumerate(lines):
        # Skip display-math ($$) blocks entirely: formula content lines may
        # begin with `(x-a)^2...` etc. and are never ordinal sequences.
        n_fence = ln.count('$$')
        if n_fence % 2 == 1:
            in_math = not in_math
            continue
        if in_math or n_fence:
            continue
        labels = _o_match_line(ln)
        for lb in labels:
            item_lines.append((i, lb))

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

    # Precompute per-block ordinal sets + line spans for cross-block
    # continuation detection (e.g. 定理1.7 的 (5)(6)(7) 承接 定理1.6 的 (1)–(4)):
    # a gap is NOT a real omission when the missing leading/internal numbers
    # already appear in a NEARBY preceding block (same item sequence).
    block_meta = []
    for blk in blocks:
        st, oi = _classify_block(blk)
        ords = set() if st == 'mixed' else {v for _, v in oi if v > 0}
        block_meta.append({'ords': ords,
                           'first': blk[0][0], 'last': blk[-1][0]})

    # Phase 2: check each block for gaps
    for bi, block in enumerate(blocks):
        if len(block) < 3:
            continue  # too few items — likely cross-references, not a sequence

        seq_type, ordinal_items = _classify_block(block)
        if seq_type == 'mixed':
            continue  # unrankable labelling — no reliable gap signal
        # Filter out any items with ordinal 0 (failed conversion)
        ordinal_items = [(li, ord_val) for li, ord_val in ordinal_items if ord_val > 0]
        if len(ordinal_items) < 3:
            continue

        ordinals = sorted(set(val for _, val in ordinal_items))
        first_line = ordinal_items[0][0] + 1  # 1-indexed for display
        min_ord, max_ord = ordinals[0], ordinals[-1]
        ord_set = set(ordinals)

        # Cross-block continuation: gather ordinals from nearby preceding blocks
        # (within 120 lines). If the "missing" numbers already appear there, the
        # current block is a legitimate continuation, not an omission.
        prev_ords = set()
        for pj in range(bi - 1, -1, -1):
            if block_meta[pj]['last'] < block_meta[bi]['first'] - 120:
                break
            prev_ords |= block_meta[pj]['ords']

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

        # HEAD gap: sequence starts above 1 — suppress if the leading numbers
        # already appear in a nearby preceding block (cross-theorem continuation)
        if min_ord > 1:
            if not set(range(1, min_ord)).issubset(prev_ords):
                head_missing = [_fmt(v) for v in range(1, min_ord)]
                out.append(
                    f"  x L{first_line}: [{ctx_label}] HEAD gap ({type_tag}) — "
                    f"sequence starts at ({_fmt(min_ord)}), "
                    f"missing ({', '.join(head_missing)}) before first item"
                )

        # INTERNAL gaps: missing ordinals between min and max — suppress if the
        # missing numbers already appear in a nearby preceding block
        expected = set(range(min_ord, max_ord + 1))
        internal_missing = sorted(expected - ord_set)
        if internal_missing:
            if not set(internal_missing).issubset(prev_ords):
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
                data = PageJson.load(os.path.join(ext_dir, f'page_{p:03d}.json')).data
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
    name = 'subitem-continuity'
    order = 15
    auto_fixable = False

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={
            'o_subitem_gaps': check_ordinal_subitem_gaps(
                ctx.md_file, ext_dir=ctx.ext_dir, ch=ctx.ch,
                start=ctx.start, end=ctx.end),
        })
