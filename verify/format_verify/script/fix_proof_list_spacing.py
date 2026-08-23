"""fix_proof_list_spacing.py — K-LAYER (code 'K', fix_order 8) auto-fix.

Separation of concerns: DETECTION logic (check_proof_after_list) lives in
proof_list_spacing.py; this module holds ONLY the auto-fix logic
(fix_proof_after_list).  The fix uses only inline regexes (no shared
constants).  Self-registers via register_fixer('K', 8, apply_fix).

Inserts the missing blank line between a list's last item and a following
new block (blockquote / `$$` / top-level `**label**` / `<div`) at any list
indentation.  Mirrors check_proof_after_list's `_k_next_is_new_block`.
Fix-dict key: {k}.
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

from verify.script.base import LayerFixResult, register_fixer

_K_LIST_RE = re.compile(r'^\s*(?:\d+[.)]|\(\d+\)|[-+*])\s')

_K_LABEL_RE = re.compile(r'^\*\*[^*]+\*\*')


def _k_next_is_new_block(item_line, nx):
    """Inline mirror of format_verify.check_proof_after_list's helper."""
    if nx.strip() == '':
        return False
    if len(nx) - len(nx.lstrip()) > len(item_line) - len(item_line.lstrip()):
        return False
    if _K_LIST_RE.match(nx):
        return False
    t = nx.strip()
    if re.match(r'^#{1,6}\s', t):
        return False
    if t.startswith('>') or t.startswith('$$') or t.startswith('<div'):
        return True
    if _K_LABEL_RE.match(t):
        return True
    return False


def fix_proof_after_list(md_file):
    """K-LAYER auto-fix: insert a blank line between a list's last item and a
    following new block (blockquote / `$$` / `**label**` / `<div`).
    Returns number of lines changed."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    changes = 0
    n = len(lines)
    i = 0
    while i < n - 1:
        if _K_LIST_RE.match(lines[i]) and _k_next_is_new_block(lines[i], lines[i + 1]):
            # Insert blank line after the list item
            lines.insert(i + 1, '')
            changes += 1
            n += 1
            i += 1  # skip the newly inserted blank line
        i += 1
    if changes > 0:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return changes


def apply_fix(ctx) -> LayerFixResult:
    """Run the K auto-fix and return the byte-compatible fix dict {k}."""
    return LayerFixResult(fix_dict={'k': fix_proof_after_list(ctx.md_file)})


register_fixer('K', 8, apply_fix)
