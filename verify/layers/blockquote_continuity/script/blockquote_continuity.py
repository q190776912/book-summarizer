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

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 verify/layers/blockquote_continuity/blockquote_continuity.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""
blockquote_continuity.py — G-LAYER (order 7, fix_order 5): quote-block continuity (structural).

Self-contained implementation of the three G-checks (bodies relocated from the deleted structure_layers.py). Auto-fix converts bare
blank lines inside blockquotes to `> ` and removes orphan bare `>` lines.
"""

from verify.layers.script.base import VerifyLayer, LayerResult

import re

from verify.common.struct_labels import G_EX_RE, G_PF_RE, G_TOPLEVEL_BREAK_RE

from lib.regexlib import G_HEAD

# <div> figure blocks cannot live inside a blockquote (CommonMark); they
# naturally exit it, so treat a <div> as a block terminator. This avoids a
# false conflict with the C-layer, which requires a truly blank line before
# a <div> (a `> ` empty-quote line would itself fail C).
G_TERM = re.compile(r'^(?:---+\s*$|##\s|\*\*[^*]+\*\*|\$\$\s*$|<div)')

NESTED_BQ = re.compile(r'^>\s*>\s*\S')

def check_g_quote_continuity(md_file):
    """G-LAYER: quote-block continuity.

    Returns a list of violation strings (with line numbers). Empty = pass.
    Flagged: a bare blank line (strip()=='') occurring while inside a
    `> **证明/证/例` block, whose next non-blank line is block CONTENT
    (a `>` line or any line that is neither a new block start nor a block
    terminator). Allowed bare blanks: those immediately preceding a new
    block start (`> **证明/例`) or a terminator (`---` / `## ` / top-level
    `**label**`) — these are inter-block separators.
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    n = len(lines)
    out = []
    in_block = False
    for i in range(n):
        ln = lines[i]
        if G_HEAD.match(ln):
            in_block = True
            continue
        if G_TERM.match(ln) and not ln.lstrip().startswith('>'):
            in_block = False
            continue
        # Only flag truly bare blank lines (no `>` prefix), not empty blockquote
        # lines (`> ` or `>`) which keep the blockquote contiguous.
        if in_block and ln.strip() == '' and not ln.startswith('>'):
            j = i + 1
            while j < n and lines[j].strip() == '':
                j += 1
            if j >= n:
                continue  # trailing blank at EOF — nothing after to split, harmless
            nx = lines[j]
            is_newblock = bool(G_HEAD.match(nx))
            is_term = bool(G_TERM.match(nx) and not nx.lstrip().startswith('>'))
            if is_newblock or is_term:
                continue  # legitimate inter-block separator
            out.append(f"  x L{i+1}: bare blank line breaks the `> **证明/例` block "
                       f"(next content L{j+1}: {nx.strip()[:40]})")
        # A top-level (non->) non-blank line closes the blockquote
        if in_block and ln.strip() and not ln.startswith('>'):
            in_block = False
    return out

def check_nested_blockquotes(md_file):
    """Detect nested blockquotes (> > **证明** or > > **例**) — the OLD format.
    Examples and their proofs must use the SAME single `>` level."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    for i, ln in enumerate(lines):
        if NESTED_BQ.match(ln):
            out.append(f"  x L{i+1}: nested blockquote `> > **` (use single `>` level): "
                       f"{ln.strip()[:60]}")
    return out

def check_example_proof_gap(md_file):
    """G-LAYER: detect gap between example (> **例**) and its proof (> **证明思路**).

    A bare empty line or non-blockquote content between them breaks
    the single blockquote — example and proof must be in the same
    contiguous `>` block. Also flags blank `>` lines (visual spacing
    within blockquote is allowed, but warnings are emitted).

    Also detects SAME-LINE example+proof: `> **例**：...**证明梗概**：...`
    which should be split onto two separate `>` lines.
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return [], []
    errors = []   # blocking — empty lines or non-bq content
    warns = []    # non-blocking — `>` gap lines
    # --- Same-line example+proof detection ---
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith('> **例') and '**证明' in s:
            # A `> **例` line containing `**证明` — they should be separate lines
            errors.append(f"  x L{i+1}: example and proof on same line — split into\n"
                          f"             `> **例…**` and `> **证明…**` on separate lines")
    # --- Gap detection (original logic) ---
    for i, ln in enumerate(lines):
        if not G_EX_RE.match(ln):
            continue
        for j in range(i + 1, min(i + 25, len(lines))):
            if not G_PF_RE.match(lines[j]):
                continue
            # Another example between → not the same pair
            if any(G_EX_RE.match(lines[k]) for k in range(i + 1, j)):
                break
            # Section header or structural interrupt → not the same pair
            if any(re.match(r'^#{1,6}\s', lines[k]) for k in range(i + 1, j)):
                break
            if any(re.match(r'^---\s*$', lines[k]) for k in range(i + 1, j)):
                break
            if any(G_TOPLEVEL_BREAK_RE.match(lines[k]) for k in range(i + 1, j)):
                break
            # Inspect gap lines
            for k in range(i + 1, j):
                t = lines[k].strip()
                if t == '':
                    errors.append(f"  x L{i+1}: empty line between example and proof (L{j+1})")
                    break
                elif not lines[k].startswith('>'):
                    errors.append(f"  x L{i+1}: non-blockquote content between example and proof "
                                  f"L{k+1}: {t[:60]}")
                    break
            break
    return errors, warns


class GLayer(VerifyLayer):
    code = 'G'
    name = 'blockquote-continuity'
    order = 7
    fix_order = 5
    auto_fixable = True

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={
            'quote_gaps': check_g_quote_continuity(ctx.md_file),
            'nested_bq': check_nested_blockquotes(ctx.md_file),
            'ex_proof_gaps': check_example_proof_gap(ctx.md_file),
        })
