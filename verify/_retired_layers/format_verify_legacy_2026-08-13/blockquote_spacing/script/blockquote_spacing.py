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

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 verify/layers/blockquote_spacing/blockquote_spacing.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""blockquote_spacing.py — N-LAYER (order 14, fix_order 11): excessive empty `>` lines in blockquotes.

Self-contained implementation (bodies relocated from the deleted structure_layers.py during the per-layer split)."""

from verify.layers.script.base import VerifyLayer, LayerResult

import re

from verify.common.struct_labels import N_ITEM_RE

def check_excessive_bq_empty_lines(md_file):
    """N-LAYER: detect excessive consecutive empty `>` lines inside blockquotes.

    Within a blockquote (> **证明** / > **例** ...), consecutive empty `>` lines
    should be limited to at most 1 between content-bearing lines."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    n = len(lines)
    in_bq = False
    i = 0
    while i < n:
        s = lines[i].strip()
        if s.startswith('> **') and ('证明' in s or '例' in s or '注' in s
                or re.search(r'\*\*(?:Proof|Example|Note|Remark)\b', s)):
            in_bq = True
            i += 1
            continue
        if in_bq:
            if (re.match(r'^---\s*$', s) or re.match(r'^#{1,6}\s', s) or
                N_ITEM_RE.match(s)):
                in_bq = False
                i += 1
                continue
            if s in ('>', '> '):
                j = i
                while j < n and lines[j].strip() in ('>', '> '):
                    j += 1
                count = j - i
                if count > 1:
                    out.append(f"  x L{i+1}–L{j}: {count} consecutive empty `>` lines "
                               f"in blockquote (max 1 allowed)")
                i = j
                continue
            # Skip regular blank lines (not >)
            if s == '':
                i += 1
                continue
        i += 1
    return out


class NLayer(VerifyLayer):
    code = 'N'
    name = 'blockquote-spacing'
    order = 14
    fix_order = 11
    auto_fixable = True

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={
            'n_bq_empty': check_excessive_bq_empty_lines(ctx.md_file),
        })
