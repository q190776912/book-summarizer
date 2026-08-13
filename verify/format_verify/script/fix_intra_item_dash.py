"""fix_intra_item_dash.py — J-LAYER (code 'J', fix_order 7) auto-fix.

Separation of concerns: DETECTION logic (check_item_header_dash) lives in
intra_item_dash.py; this module holds ONLY the auto-fix logic
(fix_item_header_dash).  Shared regexes are imported from the detection
module (_J_SUBPOINT_RE, _J_DASH_RE) and from verify.script.struct_labels
(TOP_LEVEL_HEADER_RE).  Self-registers via register_fixer('J', 7, apply_fix).

Fix-dict key: {j}.
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
from verify.script.struct_labels import TOP_LEVEL_HEADER_RE
from format_verify import _J_SUBPOINT_RE, _J_DASH_RE


def fix_item_header_dash(md_file):
    """J-LAYER auto-fix: remove every `---` that sits INSIDE an item block.

    Uses the same `in_item` span-tracker as check_item_header_dash, so it
    catches a `---` between a header and its first `**(N)**` sub-point AND a
    `---` between two `**(i)**`/`**(i+1)**` sub-points, even when a sub-point
    spans multiple lines (continuation text / `$$` formula directly above the
    `---`). Also collapses the single blank immediately after the `---` so the
    parts stay tight (matching the no-`---` style of `**引理3.3**`).
    Returns number of lines removed."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    n = len(lines)
    remove = set()
    in_item = False
    for i in range(n):
        s = lines[i]
        st = s.strip()
        if st == '':
            continue
        if st.startswith('>'):
            in_item = False
            continue
        if re.match(r'^#{1,6}\s', s):
            in_item = False
            continue
        if TOP_LEVEL_HEADER_RE.match(s) or _J_SUBPOINT_RE.match(s):
            in_item = True
            continue
        if _J_DASH_RE.match(s):
            ni = i + 1
            while ni < n and lines[ni].strip() == '':
                ni += 1
            if ni < n and not lines[ni].lstrip().startswith('>'):
                nxt = lines[ni]
                if in_item and _J_SUBPOINT_RE.match(nxt):
                    remove.add(i)  # the `---`
                    if i + 1 < n and lines[i + 1].strip() == '':
                        remove.add(i + 1)  # the blank line right after the `---`
            continue
    if remove:
        new = [ln for idx, ln in enumerate(lines) if idx not in remove]
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new))
        return len(remove)
    return 0


def apply_fix(ctx) -> LayerFixResult:
    """Run the J auto-fix and return the byte-compatible fix dict {j}."""
    return LayerFixResult(fix_dict={'j': fix_item_header_dash(ctx.md_file)})


register_fixer('J', 7, apply_fix)
