#!/usr/bin/env python3
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

# -*- coding: utf-8 -*-
"""
proof_steps.py — 证明步骤编号（从 fmt_proofs.py 迁移，逻辑不变）。

提供：number_proof / stage2（证明步骤编号渲染为块引用内有序列表）。
"""
import os, sys

import re
from bq_core import MARKER_RE, PROF_LINE_RE


def number_proof(text):
    matches = list(MARKER_RE.finditer(text))
    if len(matches) < 2:
        return None
    segs = []
    pos = 0
    for m in matches:
        segs.append(text[pos:m.start()])
        pos = m.start()
    segs.append(text[pos:])
    items = []
    if segs[0].strip():
        items.append(segs[0])
    items.extend(segs[1:])
    if len(items) < 2:
        return None
    return [f'{k}. {it.strip()}' for k, it in enumerate(items, 1)]


def stage2(text):
    lines = text.split('\n')
    out = []
    i = 0
    N = len(lines)
    while i < N:
        line = lines[i]
        m = PROF_LINE_RE.match(line)          # > **证明(思路|梗概|概要)**：<正文>
        if m:
            variant = m.group(1)              # 思路 / 梗概 / 概要
            body = m.group(2)                 # 行内证明正文（可能为空）
            if body.strip():
                numbered = number_proof(body)
                if numbered:
                    out.append('> **证明%s**：' % variant)
                    for seg in numbered:
                        out.append('> ' + seg)
                    i += 1
                    continue
                out.append(line)              # 单步证明，不编号
                i += 1
                continue
            # 正文为空：证明在后续行
            j = i + 1
            if j < N and re.match(r'^>\s+\d+\.\s', lines[j]):
                out.append(line)              # 已是编号块，保持（幂等）
                i += 1
                continue
            # 其余情况（手工编号/多行证明）保持 header，后续行原样透传
            out.append(line)
            i += 1
            continue
        out.append(line)
        i += 1
    return '\n'.join(out)
