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
bq_core.py — 块引用引擎（生产期变换）。

提供：emit_block / stage1，以及支撑这些函数的模块级正则与常量。

注：块引用的「修复」逻辑（引用连续性、嵌套折叠、例-证空隙合并、标题下分隔线清理等）
已统一收归 verify 的 fixer（fix_blockquote_continuity.py 代码 G、fix_separator_spacing.py
代码 L），本模块只保留写作期（wrap_examples / fmt_proofs 调用）所需的变换。
"""
import os, sys

import re

# 编号条目或描述性粗体块（**标签...**： 形式，标签后可能紧跟 (...) 括注）
ITEM_RE = re.compile(r'^\*\*(定义|定理|引理|推论|命题|注|注记|评注)\b')
BLOCK_RE = re.compile(r'^\*\*[^*]+\*\*[^\n]*?[:：]')
# 引用项开头：以块引用承载的 **条目（Example/Remark/Theorem/Definition/...）**
# 仅匹配「标准定理类标签」（中英文），用于区分「独立条目」与「条目内的加粗续句」
# （如 "Polynomial expansion of H^{-1}" 这类非标准标签仍视为所属条目的内容）。
_ITEM_LABELS = (r'定义|定理|引理|推论|命题|注|注记|评注|例|假设|证明(?:思路|梗概|概要)?'
                r'|习题|问题|断言|公理'
                r'|Definition|Theorem|Lemma|Proposition|Corollary|Conjecture|Claim|'
                r'Example|Remark|Assumption|Proof|Axiom|Exercise|Problem|'
                r'Hypothesis|Algorithm')
ITEM_OPEN = re.compile(r'^>\s+\*\*(?:' + _ITEM_LABELS + r')\b')
# 独立成行的结构性条目（无 > 前缀）：在新旧两种版式下都视作硬边界，
# 收束上一个引用块但【不】把本行/后续内容包进上一块引用（修复吞并定理陈述的 bug）。
ITEM_STANDALONE = re.compile(r'^\*\*(?:定义|定理|引理|推论|命题|断言)')
from lib.regexlib import FMT_SEC_RE as SEC_RE      # 匹配 '## ' '### ' '#### ' 等任意层级节标题；其下首个 item 前均不插 '---'
# 证明梗概 / 证明思路 / 证明概要 / 英文 Proof / Proof sketch / Proof outline / Proof of <...>
PROOF_RE = re.compile(
    r'\*\*(?:证明(?:思路|梗概|概要)?'
    r'|Proof(?:\s+(?:sketch|outline|of\s+[^*\n]+?))?)\b[*.:：]?\*\*'
)
PROF_LINE_RE = re.compile(
    r'^>\s+\*\*(证明(?:思路|梗概|概要)?'
    r'|Proof(?:\s+(?:sketch|outline|of\s+[^*\n]+?))?)\b[*.:：]?\*\*[:：]?\s*(.*)$'
)
from lib.regexlib import FMT_HR_RE as HR_RE    # 水平分隔线

STRONG = (r'首先|其次|再次|然后|接着|最后|先证|再证|次证|又证|后证|'
          r'另一方面|其一|其二|其三|情形一|情形二|情形三|'
          r'（一）|（二）|（三）|第一步|第二步|第三步|'
          r'（必要性）|（充分性）|（i）|（ii）|（iii）|（iv）|'
          r'\(i\)|\(ii\)|\(iii\)|\(iv\)')
BARE = r'先|再|又|一般|反之|同理'
# 强标记前可接 任意断句标点/空格/行首；弱标记(先/再/又/一般/反之/同理)前只接
# 行首 或 ：；。\n （避免 "先在…、再…" 这类单步描述被误拆）。
MARKER_RE = re.compile(
    r'(?:(?<=^)|(?<=[:：；。\n\s]))(' + STRONG + r')'
    r'|(?:(?<=^)|(?<=[:：；。\n]))(' + BARE + r')'
)


def is_block_start(line):
    return bool(BLOCK_RE.match(line))


def emit_block(out, line, state):
    if not state['first']:
        # 清掉尾部空白与可能存在的旧分隔线，避免重复
        while out and out[-1].strip() == '':
            out.pop()
        if out and out[-1].strip() == '---':
            out.pop()
        while out and out[-1].strip() == '':
            out.pop()
        # 若上一行已是块引用行(> 或 > **)，不再补前导空行，
        # 避免「> 空行 ---」与 repair 的空行折叠互相拉锯导致非幂等
        if not (out and out[-1].lstrip().startswith('>')):
            out.append('')
        out.append('---')
        out.append('')
    out.append(line)
    state['first'] = False


def _close_block_below(out):
    """若当前处于某条目块内，确保块下方有一行 '---' 分隔（在标题或文件末尾之前）。

    幂等：折叠末尾空行后，若最后非空行已是 '---' 则不重复添加。
    """
    while out and out[-1].strip() == '':
        out.pop()
    if out and not HR_RE.match(out[-1]):
        # 上一行已是块引用行(> 或 > **)时不再补前导空行，避免与 repair 空行折叠拉锯
        if not out[-1].lstrip().startswith('>'):
            out.append('')
        out.append('---')


NESTED_BQ_RE = re.compile(r'^>\s+>\s+\*\*(?:证明|证|例|证明思路|证明梗概|证明概要|Proof|定理|引理|推论|命题|定义)\b')


def stage1(text):
    lines = text.split('\n')
    out = []
    in_block = False
    i = 0
    N = len(lines)
    while i < N:
        line = lines[i]
        # ---- flatten nested blockquotes: > > ** --> > ** ----
        if NESTED_BQ_RE.match(line):
            line = re.sub(r'^>\s+>\s+', '> ', line)
        # ---- 证明梗概/思路 提取 / 包块引用 ----
        pm = PROOF_RE.search(line)
        if pm:
            if line.startswith('> '):
                out.append(line)          # 已在块引用内（如例内证明），保持
                in_block = True
                i += 1
                continue
            idx = pm.start()
            if idx == 0:
                out.append('> ' + line)   # 独立证明行
                in_block = True
                i += 1
                continue
            # 行内（定理句末 / 续句）-> 拆开
            before = line[:idx].rstrip()
            after = line[idx:]
            if before.strip():
                if is_block_start(before):
                    emit_block(out, before, {'first': not in_block})
                    in_block = True
                else:
                    out.append(before)    # 续句（如"其中…"），不插分隔线
            out.append('> ' + after)
            in_block = True
            i += 1
            continue
        if SEC_RE.match(line):
            if in_block:
                _close_block_below(out)   # 条目块下方补分隔线，再接标题
                in_block = False
            out.append(line)
            i += 1
            continue
        if is_block_start(line):
            emit_block(out, line, {'first': not in_block})  # 非首个条目上方补 '---'
            in_block = True
            i += 1
            continue
        out.append(line)
        i += 1
    if in_block:
        _close_block_below(out)          # 文件末尾前补分隔线
    return '\n'.join(out)
