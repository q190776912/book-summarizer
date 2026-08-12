"""fix_proof_list_spacing.py — K-LAYER (code 'K', fix_order 8) auto-fix.

Separation of concerns: DETECTION logic (check_proof_after_list) lives in
proof_list_spacing.py; this module holds ONLY the auto-fix logic
(fix_proof_after_list).  The fix uses only inline regexes (no shared
constants).  Self-registers via register_fixer('K', 8, apply_fix).

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

from verify.layers.script.base import LayerFixResult, register_fixer


def fix_proof_after_list(md_file):
    """K-LAYER auto-fix: insert a blank line between a numbered list and a
    `> **证明` blockquote. Returns number of lines changed."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    changes = 0
    n = len(lines)
    i = 0
    while i < n - 1:
        if re.match(r'^    \d+\.\s', lines[i]) or re.match(r'^    \(\d+\)\s', lines[i]):
            nx = lines[i + 1].strip()
            if (nx.startswith('> **证明') or nx.startswith('> **证明思路**')
                    or re.search(r'\*\*(?:Proof|Proof sketch|Proof outline|Example|Note|Remark)\b', nx)):
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
