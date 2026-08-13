"""fix_blockquote_continuity.py — G-LAYER (code 'G', fix_order 5) auto-fix.

Separation of concerns: DETECTION logic (check_g_*) lives in
blockquote_continuity.py; this module holds ONLY the auto-fix logic
(fix_g_quote_continuity).  Shared regex constants are imported from the
detection module (G_TERM) and from lib.regexlib (G_HEAD) — single source of
truth, no duplicated patterns.  Self-registers via register_fixer('G', 5, apply_fix).

Fix-dict key: {g}.
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

from verify.script.base import LayerFixResult, register_fixer
from lib.regexlib import G_HEAD
from format_verify import G_TERM


def fix_g_quote_continuity(md_file):
    """G-LAYER auto-fix: convert bare blank lines inside blockquotes to `> `.
    Returns number of lines changed."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    n = len(lines)
    changes = 0

    # PASS 1: convert blank lines inside blockquotes to `> `
    in_block = False
    for i in range(n):
        ln = lines[i]
        if G_HEAD.match(ln):
            in_block = True
            continue
        elif G_TERM.match(ln) and not ln.lstrip().startswith('>'):
            in_block = False
            continue
        if in_block and ln.strip() == '' and not ln.startswith('>'):
            # Mirror check_g_quote_continuity: a bare blank is a LEGITIMATE
            # inter-block separator when its next non-blank line is a new
            # block head (`> **证明/例`) or a terminator (`---` / `## ` /
            # top-level `**label**`) — leave it as-is, do NOT convert to `> `.
            j = i + 1
            while j < n and lines[j].strip() == '':
                j += 1
            if j < n:
                nx = lines[j]
                is_newblock = bool(G_HEAD.match(nx))
                is_term = bool(G_TERM.match(nx) and not nx.lstrip().startswith('>'))
                if is_newblock or is_term:
                    continue
            lines[i] = '> '
            changes += 1
        # A top-level (non->) non-blank line closes the blockquote
        if in_block and ln.strip() and not ln.startswith('>'):
            in_block = False

    # PASS 2: remove orphan bare `>` lines (exactly `>`, not `> ` with space)
    for i in range(n - 1, -1, -1):
        if lines[i].rstrip() == '>' and lines[i] != '> ':
            prev_has = i > 0 and lines[i-1].startswith('>') and lines[i-1].rstrip() != '>'
            next_has = i < n-1 and lines[i+1].startswith('>') and lines[i+1].rstrip() != '>'
            if not (prev_has and next_has):
                lines[i] = ''
                changes += 1

    if changes > 0:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return changes


def apply_fix(ctx) -> LayerFixResult:
    """Run the G auto-fix and return the byte-compatible fix dict {g}."""
    return LayerFixResult(fix_dict={'g': fix_g_quote_continuity(ctx.md_file)})


register_fixer('G', 5, apply_fix)
