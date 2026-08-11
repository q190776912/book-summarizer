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

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 verify/layers/item_separator/item_separator.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""item_separator.py — I-LAYER (order 9, fix_order 6): item separator (---) completeness.

Self-contained implementation (bodies relocated from the deleted structure_layers.py during the per-layer split)."""

from verify.layers.script.base import VerifyLayer, LayerResult, LayerFixResult

import re

from verify.layers.script._struct_labels import (
    I_ITEM_STRUCT_RE, I_ITEM_EXAMPLE_RE, I_ITEM_NUMFIRST_RE,
)

def check_i_separators(md_file):
    """I-LAYER: check that consecutive items are separated by `---`.

    Items checked: definition, theorem, lemma, corollary, proposition,
    axiom, example. Internal blocks (proof, note) are NOT items and
    don't need separators. Section boundaries (##) reset the requirement.
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    # Collect all item-starting line numbers
    item_lines = []
    for i, ln in enumerate(lines):
        if (I_ITEM_STRUCT_RE.match(ln) or I_ITEM_EXAMPLE_RE.match(ln)
                or I_ITEM_NUMFIRST_RE.match(ln)):
            item_lines.append(i)
    item_lines = sorted(set(item_lines))
    # Check consecutive pairs
    for idx in range(len(item_lines) - 1):
        i = item_lines[idx]
        j = item_lines[idx + 1]
        # Skip if too far apart (likely across a section boundary with no ## mark)
        if j - i > 100:
            continue
        # Look for --- or section heading between i and j
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
            si = lines[i].strip()[:70]
            sj = lines[j].strip()[:70]
            out.append(f"  x L{i+1}→L{j+1}: missing `---` between items: [{si}]...[{sj}]")
    return out

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

class ILayer(VerifyLayer):
    code = 'I'
    name = 'item-separator'
    order = 9
    fix_order = 6
    auto_fixable = True

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={
            'i_sep_gaps': check_i_separators(ctx.md_file),
        })

    def fix(self, ctx):
        return LayerFixResult(fix_dict={'i': fix_i_separators(ctx.md_file)})
