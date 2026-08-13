"""fix_structural_label_guard.py — H-LAYER (code 'H', fix_order 1) auto-fix.

Separation of concerns: the DETECTION logic (check_h_*) lives in
structural_label_guard.py; this module holds ONLY the auto-fix logic
(fix_h_*).  The two modules share regex constants / helpers by importing
them from structural_label_guard (single source of truth — no duplicated
patterns).  This module self-registers via register_fixer('H', 1, apply_fix)
so VerifyManager.fix prefers it over the (now removed) Layer.fix.

Fix-dict keys are emitted in the HARD-CONSTRAINT order
h -> h_stmt -> h_ul -> h_mbq (matches the legacy fix_all_layers key order).
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

import re

from verify.layers.script.base import LayerFixResult, register_fixer
from verify.common.struct_labels import (
    H_STRUCT_BQ_FIX_RE, H_INLINE_STRUCT_BQ_RE, TOP_LEVEL_HEADER_RE,
)

# Shared regex constants + helpers used by BOTH detection and fix (single source).
from format_verify import (
    _H_UL_OPENERS, _H_UL_FOOTNOTE, _H_MISSING_BQ, _H_MISSING_BQ_FOOTNOTE,
    _h_ext_is_legit_bq, _h_ext_is_structural_bq, _h_ext_items,
)


def fix_h_structural_blockquote(md_file):
    """H-LAYER auto-fix: remove `> ` prefix from structural labels inside blockquotes.
    Also removes orphan bare `>` lines. Returns number of lines changed."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    changes = 0

    # Fix structural labels inside blockquotes: un-indent them
    for i in range(len(lines)):
        ln = lines[i]
        if H_STRUCT_BQ_FIX_RE.match(ln):
            new_ln = re.sub(r'^\s*>\s+', '', ln)
            if new_ln != ln:
                lines[i] = new_ln
                changes += 1

    # Also remove orphan bare `>` lines (H-layer sub-check).
    # Remove both `>` (no space) and `> ` (with space) when not between real
    # blockquote content.  We DELETE the line entirely (rather than blanking it
    # to '') so the surrounding lines stay adjacent — blanking left a stray empty
    # line that tripped the G-layer quote-gap check (e.g. an orphan `>` sitting
    # between a top-level header and the next header).  Backward iteration makes
    # `del` safe.
    orphan_changes = 0
    for i in range(len(lines) - 1, -1, -1):
        ln = lines[i]
        is_bare = ln.strip() == '>' or ln.strip() == ''
        if not (ln.startswith('>') and is_bare):
            continue  # not a bare > line
        prev_has = i > 0 and lines[i-1].startswith('>') and lines[i-1].strip() not in ('', '>')
        next_has = i < len(lines)-1 and lines[i+1].startswith('>') and lines[i+1].strip() not in ('', '>')
        if not (prev_has and next_has):
            del lines[i]
            orphan_changes += 1
    changes += orphan_changes

    if changes > 0:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return changes


def fix_h_statement_in_blockquote(md_file):
    """H-LAYER ext auto-fix: unwrap wrapped-statement `>` lines to top-level.
    Mirrors the ch3 repair — structural `>` (>（N）/ >**(N)** / >$$ / >-(a)) in an
    item's statement region are unwrapped; legit proof/example/note `>` kept.
    Returns number of lines changed."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    n = len(lines)
    heads = [i for i in range(n) if TOP_LEVEL_HEADER_RE.match(lines[i])] + [n]
    out, ptr, changes = [], 0, 0
    def _unwrap(t):
        if t == '':
            return ''
        m = re.match(r'^（([0-9a-zA-Z]+)）', t)
        if m:
            return '**(' + m.group(1) + ')**' + t[m.end():]
        m = re.match(r'^\*\*\(([0-9a-zA-Z]+)\)\*\*', t)
        if m:
            return '**(' + m.group(1) + ')**' + t[m.end():]
        m = re.match(r'^- （([0-9a-zA-Z]+)）', t)
        if m:
            return '- (' + m.group(1) + ')' + t[m.end():]
        return t
    for idx in range(len(heads) - 1):
        h, nxt = heads[idx], heads[idx + 1]
        out.extend(lines[ptr:h]); out.append(lines[h])
        pen_idx = nxt
        for k in range(h + 1, nxt):
            if _h_ext_is_legit_bq(lines[k]):
                pen_idx = k; break
        bq = [k for k in range(h + 1, pen_idx) if lines[k].lstrip().startswith('>')]
        wrapped = any(_h_ext_is_structural_bq(lines[k]) for k in bq)
        if wrapped:
            for k in range(h + 1, pen_idx):
                s = lines[k]
                if s.lstrip().startswith('>'):
                    new = _unwrap(s.lstrip()[1:].lstrip())
                    if new != s:
                        changes += 1
                    out.append(new)
                else:
                    out.append(s)
        else:
            out.extend(lines[h + 1:pen_idx])
        out.extend(lines[pen_idx:nxt])
        ptr = nxt
    if changes:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(out))
    return changes


def fix_unlabeled_blockquotes(md_file):
    """H-LAYER ext auto-fix: strip `>` prefix from unlabeled blockquote lines.
    Uses the same block-splitting logic as check_unlabeled_blockquotes.
    Returns number of lines changed."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    n = len(lines)
    changes = 0
    ranges = []
    i = 0
    while i < n:
        if not lines[i].lstrip().startswith('>'):
            i += 1
            continue
        start = i
        i += 1
        while i < n and lines[i].lstrip().startswith('>'):
            if _H_UL_OPENERS.match(lines[i]) or _H_UL_FOOTNOTE.match(lines[i]):
                break
            i += 1
        end = i
        first = None
        for k in range(start, end):
            inner = lines[k].lstrip()
            if inner == '>' or inner == '':
                continue
            first = k
            break
        if first is None:
            continue
        ln = lines[first]
        if _H_UL_OPENERS.match(ln) or _H_UL_FOOTNOTE.match(ln):
            continue
        if H_INLINE_STRUCT_BQ_RE.match(ln):
            continue
        ranges.append((start, end))
    for start, end in ranges:
        for k in range(start, end):
            ln = lines[k]
            if ln.lstrip().startswith('>') and ln.lstrip() not in ('>', '> '):
                new = re.sub(r'^>\s?', '', ln, count=1)
                if new != ln:
                    lines[k] = new
                    changes += 1
    if changes > 0:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return changes


def fix_labels_missing_blockquote(md_file):
    """H-LAYER ext auto-fix: wrap top-level 证明/证/例/注/说明/注记/脚注
    labels with `> `. Returns number of lines changed.

    Display math ($$...$$ fences) is skipped so legitimate CD-diagram rows
    starting with `{` are never wrapped — see check_labels_missing_blockquote."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    changes = 0
    in_math = False
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s == '$$':
            in_math = not in_math
            continue
        if s.startswith('$$') and s.endswith('$$'):
            continue
        if in_math:
            continue
        st = ln.strip()
        if st.startswith('>'):
            continue
        if re.match(r'^#{1,6}\s', ln):
            continue
        if _H_MISSING_BQ.match(st) or _H_MISSING_BQ_FOOTNOTE.match(st):
            lines[i] = '> ' + ln
            changes += 1
    if changes > 0:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return changes


def apply_fix(ctx) -> LayerFixResult:
    """Run all four H sub-fixes in HARD-CONSTRAINT order and return the
    byte-compatible fix dict {h, h_stmt, h_ul, h_mbq}."""
    md = ctx.md_file
    fix_dict = {}
    fix_dict['h'] = fix_h_structural_blockquote(md)
    fix_dict['h_stmt'] = fix_h_statement_in_blockquote(md)
    fix_dict['h_ul'] = fix_unlabeled_blockquotes(md)
    fix_dict['h_mbq'] = fix_labels_missing_blockquote(md)
    return LayerFixResult(fix_dict=fix_dict)


register_fixer('H', 1, apply_fix)
