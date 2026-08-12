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

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 verify/layers/separator_spacing/separator_spacing.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""separator_spacing.py — L-LAYER (order 12, fix_order 9): blank lines around `---` separators.

Self-contained implementation (bodies relocated from the deleted structure_layers.py during the per-layer split)."""

from verify.layers.script.base import VerifyLayer, LayerResult

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


class LLayer(VerifyLayer):
    code = 'L'
    name = 'separator-spacing'
    order = 12
    fix_order = 9
    auto_fixable = True

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={
            'l_sep_blanks': check_separator_blank_lines(ctx.md_file),
        })
