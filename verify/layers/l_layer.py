# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 references/layers/l.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""l_layer.py — L-LAYER (order 12, fix_order 9): blank lines around `---` separators.

Self-contained implementation (bodies relocated from the deleted structure_layers.py during the per-layer split)."""

from verify.registry import VerifyLayer, LayerResult, LayerFixResult

def check_separator_blank_lines(md_file):
    """L-LAYER: every `---` separator line must have a blank line immediately
    above AND below it. Returns list of violation strings (with line numbers).
    Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    n = len(lines)
    for i, ln in enumerate(lines):
        if ln.strip() == '---':
            if i > 0 and lines[i - 1].strip() != '':
                out.append(f"  x L{i+1}: `---` missing blank line BEFORE "
                           f"(prev L{i}: {lines[i-1].strip()[:40]})")
            if i < n - 1 and lines[i + 1].strip() != '':
                out.append(f"  x L{i+1}: `---` missing blank line AFTER "
                           f"(next L{i+2}: {lines[i+1].strip()[:40]})")
    return out

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

class LLayer(VerifyLayer):
    code = 'L'
    order = 12
    fix_order = 9
    auto_fixable = True

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={
            'l_sep_blanks': check_separator_blank_lines(ctx.md_file),
        })

    def fix(self, ctx):
        return LayerFixResult(fix_dict={'l': fix_separator_blank_lines(ctx.md_file)})
