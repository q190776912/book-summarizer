"""k_layer.py — K-LAYER (order 11, fix_order 8): blank line between list and proof.

Self-contained implementation (bodies relocated from the deleted structure_layers.py during the per-layer split)."""

from verify.registry import VerifyLayer, LayerResult, LayerFixResult

import re

def check_proof_after_list(md_file):
    """K-LAYER: ensure a blank line separates a numbered list from the proof
    blockquote that follows it.

    A `> **证明`/`> **证明思路**` blockquote that directly follows the last
    item of a 4-space-indented numbered list (without a blank line) will render
    the proof at the list's indentation rather than the theorem's outer level.
    Returns a list of violation strings (with line numbers). Empty = pass."""
    try:
        lines = open(md_file, encoding='utf-8').read().split('\n')
    except Exception:
        return []
    out = []
    n = len(lines)
    for i in range(n - 1):
        # A candidate list line: starts with 4 spaces + digit + `.`
        if re.match(r'^    \d+\.\s', lines[i]) or re.match(r'^    \(\d+\)\s', lines[i]):
            nx = lines[i + 1].strip()
            if nx.startswith('> **证明') or nx.startswith('> **证明思路**'):
                out.append(f"  x L{i+2}: `{nx[:50]}` directly follows list item "
                           f"L{i+1} without blank line — add blank line between")
    return out

def fix_proof_after_list(md_file):
    """K-LAYER auto-fix: insert a blank line between a numbered list and a
    `> **证明` blockquote. Returns number of lines changed."""
    try:
        lines = open(md_file, encoding='utf-8').read().split('\n')
    except Exception:
        return 0
    changes = 0
    n = len(lines)
    i = 0
    while i < n - 1:
        if re.match(r'^    \d+\.\s', lines[i]) or re.match(r'^    \(\d+\)\s', lines[i]):
            nx = lines[i + 1].strip()
            if nx.startswith('> **证明') or nx.startswith('> **证明思路**'):
                # Insert blank line after the list item
                lines.insert(i + 1, '')
                changes += 1
                n += 1
                i += 1  # skip the newly inserted blank line
        i += 1
    if changes > 0:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return changes

class KLayer(VerifyLayer):
    code = 'K'
    order = 11
    fix_order = 8
    auto_fixable = True

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={
            'k_proof_list': check_proof_after_list(ctx.md_file),
        })

    def fix(self, ctx):
        return LayerFixResult(fix_dict={'k': fix_proof_after_list(ctx.md_file)})
