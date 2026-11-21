#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""check_mathjax.py — 检测 MathJax/Obsidian/Typora 不兼容的公式写法。

背景（2026-11-21）：skill 的公式校验链只跑 KaTeX（`check_katex.py` →
`katex_validate.js` → `require('katex')`），而 KaTeX **容忍** `\tag{}` 出现在
`aligned`/`gathered`/`split`/`array`/... 等**内容环境内部**；但 MathJax（Obsidian
与 Typora 默认引擎）明确禁止，直接报 `\tag not allowed in aligned environment`，
公式渲染成红色错误。于是出现「check_katex 绿 / 用户端红」的覆盖盲区。

本检测是**纯行形态扫描**（不依赖 node / KaTeX / MathJax 运行时），判定规则：

  在一个 `$$...$$` display 块内维护环境栈（`\begin{X}` 入栈 / `\end{X}` 出栈）；
  `\tag{...}` 出现时若栈顶属于「内容环境」（aligned / gathered / split /
  cases / array / matrix 族 / smallmatrix / subarray / eqnarray / CD ...）——
  即 MathJax 禁止的位置——即报一条问题。栈顶为 display 顶层环境（equation /
  align / gather / multline 等）时不报（MathJax 允许）。

🔴 与 check_katex 的分工：check_katex 负责 KaTeX 真实渲染（非法命令 / 括号不匹配 /
定界符等），本脚本专门补 MathJax 与 KaTeX 的**行为差异**（tag 位置），二者互补。
format_verify 的 check_katex() 会调用本脚本并把结果并入 katex_errors，
因此 `verify --all` 自动覆盖；也可独立运行：

    python verify/format_verify/script/check_mathjax.py <file.md> [<file2.md> ...]
    python verify/format_verify/script/check_mathjax.py --dir <book_dir>

退出码 0 = 无问题，1 = 发现问题，2 = 用法/读取错误。
"""
import os
import re
import sys

# MathJax: \tag only allowed at display top level; forbidden inside these envs.
BAD_ENVS = frozenset({
    'aligned', 'alignedat', 'gathered', 'split', 'cases',
    'array', 'matrix', 'pmatrix', 'bmatrix', 'vmatrix', 'Vmatrix',
    'smallmatrix', 'subarray', 'eqnarray', 'eqnarray*', 'CD',
})
ENV_RE = re.compile(r'\\(begin|end)\{([^}]+)\}')
TAG_RE = re.compile(r'\\tag\{')


def _strip_prefix(line):
    """去掉 blockquote 前缀与首尾空白，保留 LaTeX 源码。"""
    s = line.strip()
    while s.startswith('>'):
        s = s.lstrip('>').strip()
    return s


def scan_text(text):
    """返回 [(行号1基, 环境名, 源码片段)]，每个 MathJax 不兼容的 \tag 一条。"""
    lines = text.splitlines()
    problems = []
    i = 0
    n = len(lines)
    while i < n:
        first = lines[i].strip()
        if not (first.startswith('$$') or first == '> $$'):
            i += 1
            continue
        # 收集 display 块（直到下一个 $$ / > $$）
        j = i
        stack = []
        while j < n:
            code = _strip_prefix(lines[j])
            is_close = (j > i and (code == '$$' or code.endswith('$$')))
            if is_close:
                break
            # 环境栈
            for m in ENV_RE.finditer(code):
                kind, env = m.group(1), m.group(2)
                if kind == 'begin':
                    stack.append(env)
                elif stack and stack[-1] == env:
                    stack.pop()
            # \tag 判定
            for _ in TAG_RE.finditer(code):
                if stack and stack[-1] in BAD_ENVS:
                    problems.append((j + 1, stack[-1], code[:80]))
            j += 1
        i = j + 1
    return problems


def scan_file(path):
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return scan_text(fh.read())


def format_problems(path, problems):
    out = []
    for ln, env, code in problems:
        out.append('[mathjax] %s:%d \\tag 不允许在 %s 环境内（MathJax/Obsidian/Typora '
                   '报 "tag not allowed in %s environment"）；移到 \\end{%s} 之后: %s'
                   % (path, ln, env, env, env, code))
    return out


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print(__doc__)
        return 2
    files = []
    if argv[0] == '--dir':
        if len(argv) < 2:
            print('ERROR: --dir requires a directory path')
            return 2
        directory = argv[1]
        for root, _dirs, fnames in os.walk(directory):
            for fn in sorted(fnames):
                if fn.endswith('.md'):
                    files.append(os.path.join(root, fn))
    else:
        files = [p for p in argv if p != '--fix']
    total = 0
    for p in files:
        try:
            problems = scan_file(p)
        except OSError as exc:
            print('[mathjax] 读取失败 %s: %r' % (p, exc))
            return 2
        for line in format_problems(p, problems):
            print(line)
        total += len(problems)
    if total:
        print('[mathjax] 共 %d 处 MathJax 不兼容写法' % total)
    return 1 if total else 0


if __name__ == '__main__':
    sys.exit(main())
