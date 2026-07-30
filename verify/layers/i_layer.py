"""i_layer.py — I-LAYER (order 9, fix_order 6): item separator (---) completeness.

Self-contained implementation (bodies relocated from the deleted structure_layers.py during the per-layer split)."""

from verify.registry import VerifyLayer, LayerResult, LayerFixResult

import re

_I_ITEM_RE_STRUCT = re.compile(
    r'^\*\*(?:定义|定理|引理|推论|命题|断言|公理'
    r'|Definition|Theorem|Lemma|Corollary|Proposition|Axiom)'
)

_I_ITEM_RE_EXAMPLE = re.compile(r'^> \*\*(?:例|Example)')

def check_i_separators(md_file):
    """I-LAYER: check that consecutive items are separated by `---`.

    Items checked: definition, theorem, lemma, corollary, proposition,
    axiom, example. Internal blocks (proof, note) are NOT items and
    don't need separators. Section boundaries (##) reset the requirement.
    """
    try:
        lines = open(md_file, encoding='utf-8').read().split('\n')
    except Exception:
        return []
    out = []
    # Collect all item-starting line numbers
    item_lines = []
    for i, ln in enumerate(lines):
        if _I_ITEM_RE_STRUCT.match(ln) or _I_ITEM_RE_EXAMPLE.match(ln):
            item_lines.append(i)
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
        lines = open(md_file, encoding='utf-8').read().split('\n')
    except Exception:
        return 0
    changes = 0

    _I_STRUCT = re.compile(
        r'^\*\*(?:定义|定理|引理|推论|命题|断言|公理'
        r'|Definition|Theorem|Lemma|Corollary|Proposition|Axiom)'
    )
    _I_EXAMPLE = re.compile(r'^> \*\*(?:例|Example)')

    item_lines = []
    for i, ln in enumerate(lines):
        if _I_STRUCT.match(ln) or _I_EXAMPLE.match(ln):
            item_lines.append(i)

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
    order = 9
    fix_order = 6
    auto_fixable = True

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={
            'i_sep_gaps': check_i_separators(ctx.md_file),
        })

    def fix(self, ctx):
        return LayerFixResult(fix_dict={'i': fix_i_separators(ctx.md_file)})
