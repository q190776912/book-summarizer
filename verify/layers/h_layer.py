"""
h_layer.py — H-LAYER (order 8, fix_order 1): structural label / blockquote audit.

H is a single layer code with four sub-checks and four sub-fixes:
  h        -> structural label inside blockquote (定义/定理/... must be top-level)
  h_stmt   -> statement content wrongly wrapped in `>`
  h_ul     -> unlabeled blockquote (free-standing `>` with no recognized label)
  h_mbq    -> labels that MUST be inside `>` but are at top level

Auto-fix internal order (HARD CONSTRAINT): h -> h_stmt -> h_ul -> h_mbq. The fix
dict is built in exactly this order so the merged fix result preserves the legacy
fix_all_layers key order.

Self-contained implementation (bodies relocated from the deleted structure_layers.py during the per-layer split).

Self-contained implementation (bodies relocated from the deleted structure_layers.py during the per-layer split).
"""

from verify.registry import VerifyLayer, LayerResult, LayerFixResult

import re

from verify.layers._struct_labels import (
    H_STRUCT_BQ_RE,
    H_STRUCT_BQ_FIX_RE,
    TOP_LEVEL_HEADER_RE,
    H_INLINE_STRUCT_BQ_RE,
)

_H_UL_OPENERS = re.compile(
    r'^\s*>\s*\*\*(?:'
    r'(?:证明|证|例|注|说明'
    r'|Proof|Example|Note|Remark)'
    r')'
)

_H_UL_FOOTNOTE = re.compile(r'^\s*>\s*\^\{')

_H_MISSING_BQ = re.compile(
    r'^\s*\*\*(?:'
    r'(?:证明|证|证明思路|证明概要|注记|说明'
    r'|Proof|Example|Note|Remark)'
    r'|例(?:\s*\d[\d.]*)?'
    r'|注(?:\s*\d[\d.]*)?'
    r')\*\*'
)

_H_MISSING_BQ_FOOTNOTE = re.compile(r'^\s*\{')

def _h_ext_is_legit_bq(s):
    """A blockquote line that is LEGIT (proof/example/note/footnote) -> stop."""
    t = s.lstrip()
    if not t.startswith('>'):
        return False
    inner = t[1:].lstrip()
    return (inner.startswith('**证明') or inner.startswith('**例')
            or inner.startswith('**注') or inner.startswith('^{'))

def _h_ext_is_structural_bq(s):
    """A blockquote line that is WRAPPED STATEMENT content (sub-point/formula)."""
    t = s.lstrip()
    if not t.startswith('>'):
        return False
    inner = t[1:].lstrip()
    if inner.startswith('$$'):
        return True
    if re.match(r'^（([0-9a-zA-Z]+)）', inner):
        return True
    if re.match(r'^\*\*\(([0-9a-zA-Z]+)\)\*\*', inner):
        return True
    if re.match(r'^- （([0-9a-zA-Z]+)）', inner):
        return True
    if re.match(r'^- \(([0-9a-zA-Z]+)\)', inner):
        return True
    return False

def _h_ext_items(md_file):
    """Yield (lines, h_idx, pen_idx) for each structural item in the file."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return
    n = len(lines)
    heads = [i for i in range(n) if TOP_LEVEL_HEADER_RE.match(lines[i])]
    for idx, h in enumerate(heads):
        nxt = heads[idx + 1] if idx + 1 < len(heads) else n
        pen_idx = nxt
        for k in range(h + 1, nxt):
            if _h_ext_is_legit_bq(lines[k]):
                pen_idx = k
                break
        yield lines, h, pen_idx

def check_h_structural_blockquote(md_file):
    """H-LAYER: scan the file for structural labels inside blockquotes.

    Returns a list of violation strings (with line numbers). Empty = pass.
    Each violation is a line matching `> **LABEL...` where LABEL is a
    structural label (definition/theorem/lemma/etc.)."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    for i, ln in enumerate(lines):
        if H_STRUCT_BQ_RE.match(ln):
            rest = ln.lstrip()
            label_end = rest.find('**', 2)
            label = rest[4:label_end] if label_end > 4 else rest[4:].split()[0]
            out.append(f"  x L{i+1}: structural label `{label.strip()}` inside blockquote "
                       f"(must be top-level): {ln.strip()[:70]}")
    # Sub-check: orphan bare `>` lines (empty blockquote not attached to content).
    # A bare `>` line is orphan only if it has no blockquote content either before or after.
    n = len(lines)
    for i, ln in enumerate(lines):
        if re.match(r'^\s*>\s*$', ln):
            # Check if preceded by blockquote content
            prev_bq = False
            for k in range(i - 1, -1, -1):
                s = lines[k].strip()
                if s:
                    prev_bq = lines[k].lstrip().startswith('>')
                    break
            # Check if followed by blockquote content
            next_bq = False
            for k in range(i + 1, n):
                s = lines[k].strip()
                if s:
                    next_bq = lines[k].lstrip().startswith('>')
                    break
            if not (prev_bq or next_bq):
                out.append(f"  x L{i+1}: bare `>` line not attached to any blockquote content "
                           f"(orphan empty blockquote — remove or merge)")
    return out

def check_h_statement_in_blockquote(md_file):
    """H-LAYER ext (BQ): flag statement content wrongly wrapped in `>`.
    Returns a list of violation strings (with line numbers). Empty = pass."""
    out = []
    for lines, h, pen_idx in _h_ext_items(md_file):
        for k in range(h + 1, pen_idx):
            if _h_ext_is_structural_bq(lines[k]):
                out.append(f"  x L{k+1}: statement content wrapped in `>` "
                           f"(unexpected blockquote): {lines[k].strip()[:70]}")
    return out

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

def check_unlabeled_blockquotes(md_file):
    """H-LAYER ext (unlabeled BQ): flag free-standing `>` blocks without a
    recognized label (证明/证/例/注/说明/脚注).

    Grouping: consecutive `>` lines form one "block".  A new legit opener
    (`> **证明**` / `> **例**` etc.) encountered mid-stream SPLITS the block,
    so that:

        > (unlabeled text)
        > **证明**：...   ← splits here, this line starts a fresh block

    Reports each content line within an unlabeled block individually.

    Returns a list of violation strings. Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    n = len(lines)
    out = []
    i = 0
    while i < n:
        if not lines[i].lstrip().startswith('>'):
            i += 1
            continue
        # Collect a blockquote block, splitting at new legit openers
        start = i
        i += 1
        while i < n and lines[i].lstrip().startswith('>'):
            # A legit opener mid-stream breaks the block so it starts fresh
            if _H_UL_OPENERS.match(lines[i]) or _H_UL_FOOTNOTE.match(lines[i]):
                break
            i += 1
        end = i
        # Find first content-bearing line in the block
        first = None
        for k in range(start, end):
            inner = lines[k].lstrip()
            if inner == '>' or inner == '':
                continue
            first = k
            break
        if first is None:
            continue  # block is all empty `>` lines
        ln = lines[first]
        if _H_UL_OPENERS.match(ln) or _H_UL_FOOTNOTE.match(ln):
            continue  # legit blockquote
        # Let H-layer handle structural labels inside blockquotes (double-flag avoidance)
        if H_INLINE_STRUCT_BQ_RE.match(ln):
            continue
        # Unlabeled blockquote — flag each content line
        for k in range(start, end):
            t = lines[k].strip()
            if t.startswith('>') and t != '>':
                inner2 = t[1:].lstrip()
                if inner2:
                    out.append(f"  x L{k+1}: unlabeled blockquote (only 证明/证/例/注/说明/脚注 "
                               f"allowed in `>`): {lines[k].strip()[:70]}")
    return out

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

def check_labels_missing_blockquote(md_file):
    """H-LAYER ext (missing BQ): flag labels (证明/证/例/注/说明/注记/脚注)
    found at TOP LEVEL — they MUST be inside `>`. Returns list of violation
    strings. Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    for i, ln in enumerate(lines):
        st = ln.strip()
        if st.startswith('>'):
            continue
        if re.match(r'^#{1,6}\s', ln):
            continue
        if _H_MISSING_BQ.match(st) or _H_MISSING_BQ_FOOTNOTE.match(st):
            out.append(f"  x L{i+1}: label `{st[:40]}` should be inside `>` "
                       f"(add `> ` prefix)")
    return out

def fix_labels_missing_blockquote(md_file):
    """H-LAYER ext auto-fix: wrap top-level 证明/证/例/注/说明/注记/脚注
    labels with `> `. Returns number of lines changed."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    changes = 0
    for i, ln in enumerate(lines):
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
    # Remove both `>` (no space) and `> ` (with space) when not between real blockquote content.
    orphan_changes = 0
    for i in range(len(lines) - 1, -1, -1):
        ln = lines[i]
        is_bare = ln.strip() == '>' or ln.strip() == ''
        if not (ln.startswith('>') and is_bare):
            continue  # not a bare > line
        prev_has = i > 0 and lines[i-1].startswith('>') and lines[i-1].strip() not in ('', '>')
        next_has = i < len(lines)-1 and lines[i+1].startswith('>') and lines[i+1].strip() not in ('', '>')
        if not (prev_has and next_has):
            lines[i] = ''
            orphan_changes += 1
    changes += orphan_changes

    if changes > 0:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return changes


class HLayer(VerifyLayer):
    code = 'H'
    order = 8
    fix_order = 1
    auto_fixable = True

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={
            'h_structural_bq': check_h_structural_blockquote(ctx.md_file),
            'h_stmt_bq': check_h_statement_in_blockquote(ctx.md_file),
            'h_ul_bq': check_unlabeled_blockquotes(ctx.md_file),
            'h_mbq': check_labels_missing_blockquote(ctx.md_file),
        })

    def fix(self, ctx):
        fix_dict = {}
        fix_dict['h'] = fix_h_structural_blockquote(ctx.md_file)
        fix_dict['h_stmt'] = fix_h_statement_in_blockquote(ctx.md_file)
        fix_dict['h_ul'] = fix_unlabeled_blockquotes(ctx.md_file)
        fix_dict['h_mbq'] = fix_labels_missing_blockquote(ctx.md_file)
        return LayerFixResult(fix_dict=fix_dict)
