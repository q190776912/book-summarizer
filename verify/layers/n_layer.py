# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 references/layers/n.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""n_layer.py — N-LAYER (order 14, fix_order 11): excessive empty `>` lines in blockquotes.

Self-contained implementation (bodies relocated from the deleted structure_layers.py during the per-layer split)."""

from verify.layers.base import VerifyLayer, LayerResult, LayerFixResult

import re

from verify.layers._struct_labels import N_ITEM_RE

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

def fix_excessive_bq_empty_lines(md_file):
    """N-LAYER auto-fix: collapse excessive consecutive empty `>` lines in
    blockquotes to max 1. Returns number of lines removed."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    n = len(lines)
    changes = 0
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
                    # Keep the first `> ` line, DELETE the rest so we never
                    # create bare blank lines that the G-layer would flag.
                    for idx in range(j - 1, i, -1):
                        del lines[idx]
                    changes += count - 1
                    n = len(lines)
                    # Do NOT advance i — the next line to check is still at i
                    continue
                i = j
                continue
            if s == '':
                i += 1
                continue
        i += 1
    if changes > 0:
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return changes

class NLayer(VerifyLayer):
    code = 'N'
    order = 14
    fix_order = 11
    auto_fixable = True

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={
            'n_bq_empty': check_excessive_bq_empty_lines(ctx.md_file),
        })

    def fix(self, ctx):
        return LayerFixResult(fix_dict={'n': fix_excessive_bq_empty_lines(ctx.md_file)})
