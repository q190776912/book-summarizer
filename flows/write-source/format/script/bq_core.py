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
bq_core.py — 块引用引擎。

提供：emit_block / remove_heading_seps / repair_leaked_bq / merge_example_block /
stage1，以及支撑这些函数的模块级正则与常量。
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
# 证明梗概 / 证明思路 / 证明概要 均可识别
PROOF_RE = re.compile(r'\*\*证明(思路|梗概|概要)\*\*')
PROF_LINE_RE = re.compile(r'^>\s+\*\*证明(思路|梗概|概要)\*\*[:：]\s*(.*)$')
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


def remove_heading_seps(text):
    """删除紧邻节/子节标题（## / ###）之下的 '---'（标题下不需要分隔符）。

    判定：某 '---' 的「最近上方非空行」若是标题（#{2,3} ），删之。
    节与节之间的 '---'（上方是上个 item 内容、下方才是下一节标题）不受影响。
    幂等；删后顺带把标题下因删线产生的连续空行折叠为单个空行。
    """
    lines = text.split('\n')
    out = []
    for line in lines:
        if HR_RE.match(line):
            j = len(out) - 1
            while j >= 0 and out[j].strip() == '':
                j -= 1
            if j >= 0 and SEC_RE.match(out[j]):
                continue  # 标题下的分隔线，删除
        out.append(line)
    text = '\n'.join(out)
    text = re.sub(r'\n{3,}', '\n\n', text)   # 折叠删线后标题下多余空行
    return text


def detect_heading_seps(text):
    """返回所有「标题下的 '---'」行号（1-based），用于 --check 检测模式。"""
    lines = text.split('\n')
    hits = []
    for i, ln in enumerate(lines):
        if HR_RE.match(ln):
            j = i - 1
            while j >= 0 and lines[j].strip() == '':
                j -= 1
            if j >= 0 and SEC_RE.match(lines[j]):
                hits.append(i + 1)
    return hits


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


def repair_leaked_bq(text):
    """修复「以 > **条目**: 开头的引用项」中漏到引用外的内容，并恢复条目间分隔。

    生成阶段常出现两种缺陷：
      1) 截断：AI 写出 `> **Example 1.2**: ...` 后，紧跟的 $$ 公式块、续句、空行
         没有带 > 前缀，导致条目一部分在引用内、一部分在引用外。
      2) 假合并：原本彼此独立的 `> **Theorem/Remark/...**:` 引用项之间，仅靠漏到
         引用外的 $$ 块（正文）相隔；一旦把 $$ 补回 > 前缀，相邻条目会被误并成
         一个巨型引用块。

    本函数：
      - 将条目内（直到 --- / 标题 / 下一个「标准标签」条目 之前）所有缺失 > 前缀
        的非空行补上 > ，项内空行规范为 `> `，使整条目闭合；
      - 当遇到「标准标签」的新条目且当前已在某条目内时，在其前插入 `---` 分隔
        （与全书「条目间用 --- 分隔」的约定一致），从而恢复独立条目；
      - 非标准标签的加粗续句（如 "Polynomial expansion of H^{-1}"）仍视为所属
        条目的内容，不另起条目、不插 ---。

    幂等：已带 > 的行保持；已存在的 --- 不会重复插入；再次运行无变化。
    """
    lines = text.split('\n')
    out = []
    in_item = False
    for ln in lines:
        if ITEM_OPEN.match(ln):                 # 标准标签引用项开头
            if in_item:
                # 上一个条目结束：插 --- 恢复独立条目（幂等：末尾已是 --- 则不插；
                # 不弹掉末尾的 > 空行，否则会与下面的空行规范互相拉锯导致非幂等）
                if not out or not HR_RE.match(out[-1]):
                    if not (out and out[-1].lstrip().startswith('>')):
                        out.append('')
                    out.append('---')
                    out.append('')
            in_item = True
            out.append(ln)
            continue
        if ITEM_STANDALONE.match(ln):            # 独立成行的结构性条目（无 > 前缀）= 硬边界
            # 收束上一个引用块，但【不】把本行及后续内容包进上一个块引用
            # （这正是旧逻辑吞掉定理/定义陈述的 bug）。条目间 --- 由 stage1 补齐。
            # 顺手清除 repair 把“条目间分隔空行”误规范成的 '> ' 空行（它本不是证明内容）。
            while out and out[-1].rstrip() == '>':
                out.pop()
            in_item = False
            out.append(ln)
            continue
        if in_item:
            if HR_RE.match(ln) or SEC_RE.match(ln):
                in_item = False                 # 遇到分隔线/标题：条目结束
                out.append(ln)
                continue
            if ln.strip() == '':
                # 引用内空行规范为 > ，但避免连续多个 > 空行（防累积/非幂等）
                if out and out[-1].strip() == '>':
                    continue
                out.append('> ')
                continue
            if ln.startswith('>'):              # 已是引用内容，保持
                out.append(ln)
                continue
            out.append('> ' + ln)               # 漏出内容：补 > 前缀
            continue
        out.append(ln)
    return '\n'.join(out)


NESTED_BQ_RE = re.compile(r'^>\s+>\s+\*\*(?:证明|证|例|证明思路|证明梗概|证明概要|定理|引理|推论|命题|定义)\b')

# 例标题行: > **例N.N-N** (后面可接（中文名）或直接）
EX_HEAD_RE = re.compile(r'> \*\*例[\d.]+-[0-9]+')
# 证明行: > **证明思路/证明/证明梗概/证明概要**
PROOF_HEAD_RE = re.compile(r'> \*\*(?:证明思路|证明|证明梗概|证明概要)\*\*')

def merge_example_block(text):
    """把例和它的证明合并到同一个 blockquote 中。

    当 > **例...** 与 > **证明思路...** 之间只有空行、裸 $$、
    或其他非 blockquote 行时，把它们全部收进同一层 `>` 包裹。
    消除完全空行（会打断 blockquote），保留 `>` 空行作为视觉间隔。
    """
    lines = text.split('\n')
    result = list(lines)
    i = 0
    while i < len(result):
        if not EX_HEAD_RE.match(result[i]):
            i += 1
            continue
        # 向后查找证明行（最多 25 行）
        proof_idx = None
        for j in range(i + 1, min(i + 25, len(result))):
            if PROOF_HEAD_RE.match(result[j]):
                # 中间不能有另一个例或结构性中断
                mid = result[i+1:j]
                if any(EX_HEAD_RE.match(l) for l in mid):
                    break
                if any(re.match(r'^#{1,6}\s', l) for l in mid):   # 节标题
                    break
                if any(re.match(r'^\*\*(?:定义|定理|引理|推论|命题|断言)\b', l) for l in mid):
                    break
                if any(re.match(r'^---\s*$', l) for l in mid):
                    break
                proof_idx = j
                break
        if proof_idx is None:
            i += 1
            continue
        # 构建新块：去掉完全空行，非 > 行加上 > 前缀
        new_block = [result[i]]                      # 例标题
        for k in range(i + 1, proof_idx):
            ln = result[k]
            if ln.strip() == '':
                continue                             # 完全空行 → 扔掉
            if ln.startswith('> '):
                new_block.append(ln)                 # 已在 blockquote
            elif ln == '>':
                new_block.append(ln)                 # blockquote 内空行（保留）
            else:
                new_block.append('> ' + ln)          # 加 blockquote 前缀
        new_block.append(result[proof_idx])          # 证明行
        result[i:proof_idx + 1] = new_block
        i += len(new_block)
    return '\n'.join(result)


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
