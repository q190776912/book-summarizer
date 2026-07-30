"""m_layer.py — M-LAYER (order 13, fix_order 10): `>` lines inside display math blocks.

Self-contained implementation (bodies relocated from the deleted structure_layers.py during the per-layer split)."""

from verify.registry import VerifyLayer, LayerResult, LayerFixResult

def check_displaymath_gt(md_file):
    """M-LAYER: detect `>` lines inside `$$...$$` display math blocks.

    When a display math block is wrapped in a blockquote context, empty `>`
    lines can leak inside the `$$` fences. KaTeX rejects bare `>` inside math
    mode. Returns list of violation strings (with line numbers). Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
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
                    if ln.lstrip().startswith('>'):
                        out.append(f"  x L{k+1}: `>` inside display math ($$...$$) — "
                                   f"remove blockquote prefix: {ln.strip()[:60]}")
                i = j
        i += 1
    return out

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

class MLayer(VerifyLayer):
    code = 'M'
    order = 13
    fix_order = 10
    auto_fixable = True

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={
            'm_dm_gt': check_displaymath_gt(ctx.md_file),
        })

    def fix(self, ctx):
        return LayerFixResult(fix_dict={'m': fix_displaymath_gt(ctx.md_file)})
