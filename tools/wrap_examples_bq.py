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
wrap_examples_bq.py — 把 **例/Example** 条目整体包进 `>` 块引用（幂等可重跑）。

SKILL.md 约定：只有「证明」与「例/Example」进 `>` 块引用；结构性标签（定义/定理/…）
必须顶层。生成阶段常见缺陷是例子写在顶层，或更隐蔽的「半包」——例子头带了 `>`、
但正文（方程组/文字）留在顶层裸奔。本工具两种情况都能修复：

  * 顶层例子头 `**Example 6.1** ...` → 整段收进 `>` 块；
  * 半包例子头 `> **Example 6.1** ...`（头有 `>`、正文无 `>`）→ 先剥掉头上的
    多余 `>`，再整段包进 `>` 块。这是 0.0 版唯一会漏的盲区（头已带 `>` 时正则
    `^\\*\\*` 不匹配，工具整块跳过，正文永远补不上），现已修正。

区域边界（遇到即结束包裹；边界判定同样先剥离行首 `>`，以便正确识别下一个
`>` 开头的例子头，避免把后续例子吞进同一块）：
  - 分隔线 `---`
  - 任意标题 `#...`
  - 顶层结构性标签 **定义/定理/引理/推论/命题/断言/公理/注/注记/评注/Definition/...**
  - 下一个 **例/Example**（各自独立成块）

区域内规则：
  - 空行 → `>`（保持 blockquote 连续，不被空行打断）
  - 已带 `>` 的行保持
  - 其余行加 `> ` 前缀
  - 区域末尾的 `>` 空行剥掉（避免 `>` 紧邻 `---` 的 stray-empty-quote）

对外暴露纯函数 `wrap_text(text) -> (text, changed)`，供 CLI 与 verify `--fix` 的
G 层 fixer（fix_blockquote_continuity.py）复用，避免逻辑重复。

用法: python wrap_examples_bq.py <book_dir>
处理 <book_dir> 下所有 第*.md / Chapter*.md。改动后建议依次跑
fmt_proofs.py 与 check_katex.py --fix 复验。
"""

import os
import re
import sys
import glob

# 注意：不能用 \b —— Python re 中汉字与数字都算 word 字符，「例2.1-2」中
# 例与 2 之间没有词边界，\b 会漏掉全部中文编号例。
EX_RE = re.compile(r'^\*\*(例(?![外如])|Example\b)')
STRUCT_RE = re.compile(
    r'^\*\*(定义|定理|引理|推论|命题|断言|公理|注记|注|评注|假设|习题|问题'
    r'|Definition|Theorem|Lemma|Proposition|Corollary|Claim|Axiom|Remark'
    r'|Assumption|Exercise|Problem|Conjecture)\b')
from lib.regexlib import FMT_HR_RE as HR_RE
SEC_RE = re.compile(r'^#{1,6}\s')


def _strip_leading_bq(line):
    """剥掉行首至多一个 blockquote 标记（`>` 或 `> `）。

    顶层例子头（`**Example**`）原样返回；半包头（`> **Example**`）返回
    `**Example**`。幂等：再剥一次也不会出错。
    """
    if line.startswith('> '):
        return line[2:]
    if line.startswith('>'):
        return line[1:]
    return line


def wrap_text(text):
    """把 text 中所有 **例/Example** 条目（含半包头）整体收进 `>` 块。

    返回 (新文本, 实际变更数)。无变更时返回 (原文本, 0)，保证幂等、可重跑、
    不无谓改写文件。
    """
    lines = text.split('\n')
    out = []
    i, n = 0, len(lines)
    while i < n:
        line = lines[i]
        head = _strip_leading_bq(line)
        if not EX_RE.match(head):
            out.append(line)
            i += 1
            continue
        # 进入例区域：剥掉头上的 `>` 后统一用 `> ` 前缀包裹整段
        region = ['> ' + head]
        i += 1
        while i < n:
            l = lines[i]
            if (HR_RE.match(l) or SEC_RE.match(l) or STRUCT_RE.match(l)
                    or EX_RE.match(_strip_leading_bq(l))):
                break
            if l.strip() == '':
                region.append('>')
            elif l.startswith('>'):
                region.append(l)
            else:
                region.append('> ' + l)
            i += 1
        # 剥掉区域末尾的 '>' 空行
        while region and region[-1].strip() in ('>', ''):
            region.pop()
        out.extend(region)
        out.append('')            # 区域后保留一个空行再接 --- / 下一条目
    new_text = re.sub(r'\n{3,}', '\n\n', '\n'.join(out))
    # preserve trailing-newline parity so the comparison (and the on-disk write
    # under platform newline translation) is a true no-op when nothing changed
    if text.endswith('\n') and not new_text.endswith('\n'):
        new_text += '\n'
    if new_text == text:
        return text, 0
    return new_text, 1


def wrap_file(path):
    raw = open(path, encoding='utf-8').read()
    text, changed = wrap_text(raw)
    if changed:
        open(path, 'w', encoding='utf-8', newline='\n').write(text)
    return changed


def main():
    if len(sys.argv) < 2:
        print('Usage: python wrap_examples_bq.py <book_dir>')
        sys.exit(2)
    d = sys.argv[1]
    files = sorted(glob.glob(os.path.join(d, '第*.md')) +
                   glob.glob(os.path.join(d, 'Chapter*.md')))
    if not files:
        print('No 第*.md / Chapter*.md found in', d)
        sys.exit(1)
    total = 0
    for f in files:
        c = wrap_file(f)
        if c:
            print(f'[OK] {os.path.basename(f)}: wrapped {c} example(s)')
            total += c
    print(f'TOTAL wrapped: {total}')


if __name__ == '__main__':
    main()
