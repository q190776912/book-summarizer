"""fix_blockquote_spacing.py — N-LAYER (code 'N', fix_order 11) auto-fix.

Separation of concerns: DETECTION logic (check_excessive_bq_empty_lines) lives in
blockquote_spacing.py; this module holds ONLY the auto-fix logic
(fix_excessive_bq_empty_lines).  Shared regex N_ITEM_RE is imported from
verify.script.struct_labels.  Self-registers via register_fixer('N', 11, apply_fix).

Fix-dict key: {n}.
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
from verify.script.struct_labels import N_ITEM_RE


def fix_excessive_bq_empty_lines(md_file):
    """N-LAYER auto-fix: collapse excessive consecutive empty `>` lines in
    blockquotes to max 1. Returns number of lines removed."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    n = len(lines)
    changes = 0
    in_bq = False
    i = 0
    while i < n:
        s = lines[i].strip()
        if s.startswith('> **') and ('证明' in s or '例' in s or '注' in s
                or re.search(r'\*\*(?:Proof|Example|Note|Remark)\b', s)):
            in_bq = True
            i += 1
            continue
        if in_bq:
            if (re.match(r'^---\s*$', s) or re.match(r'^#{1,6}\s', s) or
                N_ITEM_RE.match(s)):
                in_bq = False
                i += 1
                continue
            if s in ('>', '> '):
                j = i
                while j < n and lines[j].strip() in ('>', '> '):
                    j += 1
                count = j - i
                if count > 1:
                    # Keep the first `> ` line, DELETE the rest so we never
                    # create bare blank lines that the G-layer would flag.
                    for idx in range(j - 1, i, -1):
                        del lines[idx]
                    changes += count - 1
                    n = len(lines)
                    # Do NOT advance i — the next line to check is still at i
                    continue
                i = j
                continue
            if s == '':
                i += 1
                continue
        i += 1
    if changes > 0:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return changes


def apply_fix(ctx) -> LayerFixResult:
    """Run the N auto-fix and return the byte-compatible fix dict {n}."""
    return LayerFixResult(fix_dict={'n': fix_excessive_bq_empty_lines(ctx.md_file)})


register_fixer('N', 11, apply_fix)
