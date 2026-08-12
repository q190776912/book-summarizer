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

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 verify/layers/math_blockquote_leak/math_blockquote_leak.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""math_blockquote_leak.py — M-LAYER (order 13, fix_order 10): `>` lines inside display math blocks.

Self-contained implementation (bodies relocated from the deleted structure_layers.py during the per-layer split)."""

from verify.layers.script.base import VerifyLayer, LayerResult

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


class MLayer(VerifyLayer):
    code = 'M'
    name = 'math-blockquote-leak'
    order = 13
    fix_order = 10
    auto_fixable = True

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={
            'm_dm_gt': check_displaymath_gt(ctx.md_file),
        })
