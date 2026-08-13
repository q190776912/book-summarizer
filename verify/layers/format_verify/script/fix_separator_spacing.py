"""fix_separator_spacing.py — L-LAYER (code 'L', fix_order 9) auto-fix.

Separation of concerns: DETECTION logic (check_separator_blank_lines) lives in
separator_spacing.py; this module holds ONLY the auto-fix logic
(fix_separator_blank_lines).  The fix uses only inline `---` matching (no
shared constants).  Self-registers via register_fixer('L', 9, apply_fix).

Fix-dict key: {l}.
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

from verify.layers.script.base import LayerFixResult, register_fixer


def fix_separator_blank_lines(md_file):
    """L-LAYER auto-fix: insert blank lines above/below every `---` that is
    missing them. Returns number of separators changed.

    Required format: ``正文\\n\\n---\\n\\n正文`` — a blank line immediately
    before AND after each `---`. Builds a fresh line list (instead of fragile
    in-place inserts) so both sides are handled in a single pass.
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    out = []
    n = len(lines)
    changes = 0
    for i, line in enumerate(lines):
        if line.strip() == '---':
            # Ensure a blank line ABOVE the separator.
            if out and out[-1].strip() != '':
                out.append('')
                changes += 1
            out.append(line)
            # Ensure a blank line BELOW the separator (skip if it is the last line).
            nxt = lines[i + 1] if i + 1 < n else ''
            if nxt.strip() != '':
                out.append('')
                changes += 1
        else:
            out.append(line)
    if changes > 0:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(out))
    return changes


def apply_fix(ctx) -> LayerFixResult:
    """Run the L auto-fix and return the byte-compatible fix dict {l}."""
    return LayerFixResult(fix_dict={'l': fix_separator_blank_lines(ctx.md_file)})


register_fixer('L', 9, apply_fix)
