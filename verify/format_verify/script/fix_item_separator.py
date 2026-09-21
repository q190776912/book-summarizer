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
    insert_item_separators, _find_deficient_item_inserts,
)


def fix_i_separators(md_file):
    """I-LAYER auto-fix: insert `---` between consecutive items without separator.
    Returns number of separators inserted.

    Detection + insertion are delegated to the SHARED helper in
    ``verify.script.struct_labels`` (``_find_deficient_item_inserts`` /
    ``insert_item_separators``) so this fixer, ``check_i_separators`` and
    ``merge_units`` all agree on exactly what counts as an item and when a
    separator is missing — a divergence here would make merge fix a spot verify
    still flags (or vice versa). Uses the robust item detector (I_ITEM_RE) so
    name-prefixed theorems (e.g. ``**Hahn-Banach Theorem 4.3-1**``,
    ``**Polya Convergence Theorem 4.11-3**``) and number-first non-keyword items
    (``**4.11-2 Requirement.**``) are correctly recognized — the OLD narrow
    regexes silently skipped them, producing false-green PASS on missing
    separators.

    Each inserted `---` gets a blank line above AND below (rule 12 / l_sep_blanks);
    an existing blank line is not duplicated.
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    insert_set = _find_deficient_item_inserts(lines)
    if not insert_set:
        return 0
    new_lines = insert_item_separators(lines)
    if len(new_lines) != len(lines):
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new_lines))
        return len(insert_set)
    return 0


def apply_fix(ctx) -> LayerFixResult:
    """Run the I auto-fix and return the byte-compatible fix dict {i}."""
    return LayerFixResult(fix_dict={'i': fix_i_separators(ctx.md_file)})


register_fixer('I', 6, apply_fix)
