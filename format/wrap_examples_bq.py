#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
wrap_examples_bq.py — 把顶层的 **例/Example** 条目整体包进 `>` 块引用（幂等可重跑）。

SKILL.md 约定：只有「证明」与「例/Example」进 `>` 块引用；结构性标签（定义/定理/…）
必须顶层。生成阶段常见缺陷是例子写在顶层——本工具将其（连同条目内全部行，含 $$、
列表、图 div、既有 > 说明块）统一收进同一连续 blockquote。

区域边界（遇到即结束包裹）：
  - 分隔线 `---`
  - 任意标题 `#...`
  - 顶层结构性标签 **定义/定理/引理/推论/命题/断言/公理/注/注记/评注/Definition/...**
  - 下一个顶层 **例/Example**（各自独立成块）

区域内规则：
  - 空行 → `>`（保持 blockquote 连续，不被空行打断）
  - 已带 `>` 的行保持
  - 其余行加 `> ` 前缀
  - 区域末尾的 `>` 空行剥掉（避免 `>` 紧邻 `---` 的 stray-empty-quote）

用法: python wrap_examples_bq.py <book_dir>
处理 <book_dir> 下所有 第*.md / Chapter*.md。改动后建议依次跑
fmt_proofs.py 与 check_katex.py --fix 复验。
"""

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

import re
import sys
import glob
import os

# 注意：不能用 \b —— Python re 中汉字与数字都算 word 字符，「例2.1-2」中
# 例与 2 之间没有词边界，\b 会漏掉全部中文编号例。
EX_RE = re.compile(r'^\*\*(例(?![外如])|Example\b)')
STRUCT_RE = re.compile(
    r'^\*\*(定义|定理|引理|推论|命题|断言|公理|注记|注|评注|假设|习题|问题'
    r'|Definition|Theorem|Lemma|Proposition|Corollary|Claim|Axiom|Remark'
    r'|Assumption|Exercise|Problem|Conjecture)\b')
HR_RE = re.compile(r'^\s*---\s*$')
SEC_RE = re.compile(r'^#{1,6}\s')


def wrap_file(path):
    raw = open(path, encoding='utf-8').read()
    lines = raw.split('\n')
    out = []
    i, n, changed = 0, len(lines), 0
    while i < n:
        line = lines[i]
        if not EX_RE.match(line):
            out.append(line)
            i += 1
            continue
        # 进入例区域
        changed += 1
        region = ['> ' + line]
        i += 1
        while i < n:
            l = lines[i]
            if HR_RE.match(l) or SEC_RE.match(l) or STRUCT_RE.match(l) or EX_RE.match(l):
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
    text = '\n'.join(out)
    text = re.sub(r'\n{3,}', '\n\n', text)
    if text != raw:
        open(path, 'w', encoding='utf-8', newline='\n').write(text)
        return changed
    return 0


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
