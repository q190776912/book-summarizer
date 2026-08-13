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

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 verify/layers/proof_list_spacing/proof_list_spacing.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""proof_list_spacing.py — K-LAYER (order 11, fix_order 8): blank line between list and proof.

Self-contained implementation (bodies relocated from the deleted structure_layers.py during the per-layer split)."""

from verify.layers.script.base import VerifyLayer, LayerResult

import re

def check_proof_after_list(md_file):
    """K-LAYER: ensure a blank line separates a numbered list from the proof
    blockquote that follows it.

    A `> **证明`/`> **证明思路**` blockquote that directly follows the last
    item of a 4-space-indented numbered list (without a blank line) will render
    the proof at the list's indentation rather than the theorem's outer level.
    Returns a list of violation strings (with line numbers). Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    n = len(lines)
    for i in range(n - 1):
        # A candidate list line: starts with 4 spaces + digit + `.`
        if re.match(r'^    \d+\.\s', lines[i]) or re.match(r'^    \(\d+\)\s', lines[i]):
            nx = lines[i + 1].strip()
            if (nx.startswith('> **证明') or nx.startswith('> **证明思路**')
                    or re.search(r'\*\*(?:Proof|Proof sketch|Proof outline|Example|Note|Remark)\b', nx)):
                out.append(f"  x L{i+2}: `{nx[:50]}` directly follows list item "
                           f"L{i+1} without blank line — add blank line between")
    return out


class KLayer(VerifyLayer):
    code = 'K'
    name = 'proof-list-spacing'
    order = 11
    fix_order = 8
    auto_fixable = True

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={
            'k_proof_list': check_proof_after_list(ctx.md_file),
        })
