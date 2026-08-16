"""fix_item_separator.py — I-LAYER (code 'I', fix_order 6) auto-fix.

Separation of concerns: DETECTION logic (check_i_separators) lives in
item_separator.py; this module holds ONLY the auto-fix logic
(fix_i_separators).  Shared item-label regexes are imported from
verify.script.struct_labels.  Self-registers via register_fixer('I', 6, apply_fix).

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
from verify.script.struct_labels import (
    I_ITEM_RE, I_ITEM_EXAMPLE_RE,
)


def fix_i_separators(md_file):
    """I-LAYER auto-fix: insert `---` between consecutive items without separator.
    Returns number of separators inserted.

    Uses the robust item detector (I_ITEM_RE) so name-prefixed theorems
    (e.g. `**Hahn-Banach Theorem 4.3-1**`, `**Polya Convergence Theorem 4.11-3**`)
    and number-first non-keyword items (`**4.11-2 Requirement.**`) are correctly
    recognized — the OLD narrow regexes silently skipped them, producing
    false-green PASS on missing separators.

    Each inserted `---` gets a blank line above AND below (rule 12 / l_sep_blanks);
    an existing blank line is not duplicated.
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    changes = 0

    item_lines = []
    for i, ln in enumerate(lines):
        if (I_ITEM_RE.match(ln) or I_ITEM_EXAMPLE_RE.match(ln)):
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

    insert_set = set(insertions)
    if not insert_set:
        return 0
    new_lines = []
    for idx, ln in enumerate(lines):
        if idx in insert_set:
            # blank line above (unless previous line already blank)
            if new_lines and new_lines[-1].strip() != '':
                new_lines.append('')
            new_lines.append('---')
            new_lines.append('')  # blank line below
        new_lines.append(ln)

    if len(new_lines) != len(lines):
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        changes = len(insert_set)
    return changes


def apply_fix(ctx) -> LayerFixResult:
    """Run the I auto-fix and return the byte-compatible fix dict {i}."""
    return LayerFixResult(fix_dict={'i': fix_i_separators(ctx.md_file)})


register_fixer('I', 6, apply_fix)
