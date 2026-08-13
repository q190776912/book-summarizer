"""fix_item_separator.py — I-LAYER (code 'I', fix_order 6) auto-fix.

Separation of concerns: DETECTION logic (check_i_separators) lives in
item_separator.py; this module holds ONLY the auto-fix logic
(fix_i_separators).  Shared item-label regexes are imported from
verify.common.struct_labels.  Self-registers via register_fixer('I', 6, apply_fix).

Fix-dict key: {i}.
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
from verify.common.struct_labels import (
    I_ITEM_STRUCT_RE, I_ITEM_EXAMPLE_RE, I_ITEM_NUMFIRST_RE,
)


def fix_i_separators(md_file):
    """I-LAYER auto-fix: insert `---` between consecutive items without separator.
    Returns number of separators inserted."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    changes = 0

    item_lines = []
    for i, ln in enumerate(lines):
        if (I_ITEM_STRUCT_RE.match(ln) or I_ITEM_EXAMPLE_RE.match(ln)
                or I_ITEM_NUMFIRST_RE.match(ln)):
            item_lines.append(i)
    item_lines = sorted(set(item_lines))

    insertions = []
    for idx in range(len(item_lines) - 1):
        i = item_lines[idx]
        j = item_lines[idx + 1]
        if j - i > 100:
            continue
        has_sep = False
        section_between = False
        for k in range(i + 1, j):
            t = lines[k].strip()
            if t == '---':
                has_sep = True
                break
            if re.match(r'^#{1,6}\s', lines[k]):
                section_between = True
                break
        if not has_sep and not section_between:
            insertions.append(j)

    for pos in sorted(set(insertions), reverse=True):
        lines.insert(pos, '---')
        changes += 1

    if changes > 0:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return changes


def apply_fix(ctx) -> LayerFixResult:
    """Run the I auto-fix and return the byte-compatible fix dict {i}."""
    return LayerFixResult(fix_dict={'i': fix_i_separators(ctx.md_file)})


register_fixer('I', 6, apply_fix)
