"""fix_math_blockquote_leak.py — M-LAYER (code 'M', fix_order 10) auto-fix.

Separation of concerns: DETECTION logic (check_displaymath_gt) lives in
math_blockquote_leak.py; this module holds ONLY the auto-fix logic
(fix_displaymath_gt).  The fix uses only inline `$$` matching (no shared
constants).  Self-registers via register_fixer('M', 10, apply_fix).

Fix-dict key: {m}.
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


def fix_displaymath_gt(md_file):
    """M-LAYER auto-fix: strip `>` prefix from lines inside `$$...$$` blocks.
    Returns number of lines changed."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    changes = 0
    n = len(lines)
    i = 0
    while i < n:
        s = lines[i].strip()
        if s == '$$':
            j = i + 1
            while j < n and lines[j].strip() != '$$':
                j += 1
            if j < n:
                for k in range(i + 1, j):
                    ln = lines[k]
                    stripped = ln.lstrip()
                    if stripped.startswith('>'):
                        new_ln = ln.replace('>', '', 1)
                        if new_ln.startswith(' '):
                            new_ln = new_ln[1:]
                        if new_ln != ln:
                            lines[k] = new_ln
                            changes += 1
                i = j
        i += 1
    if changes > 0:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return changes


def apply_fix(ctx) -> LayerFixResult:
    """Run the M auto-fix and return the byte-compatible fix dict {m}."""
    return LayerFixResult(fix_dict={'m': fix_displaymath_gt(ctx.md_file)})


register_fixer('M', 10, apply_fix)
