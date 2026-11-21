# -*- coding: utf-8 -*-
r"""tests for check_mathjax：MathJax/Obsidian/Typora 不兼容写法检测。

钉住行为：
  * \tag 在 aligned/gathered/split/array 等内容环境内 → 报（MathJax 禁止）
  * \tag 在 $$ 顶层（不在任何环境内）→ 不报（合法）
  * blockquote（> $$ / > \begin{aligned}）前缀不影响判定
  * 环境闭合后（\end{aligned} 之后的 \tag）→ 不报
  * 非数学正文里的 \tag 文本 → 不报（只扫 $$ 块内）
  * KaTeX 容忍而 MathJax 禁止 → 本检测与 check_katex 互补，不重复其职责
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'verify', 'format_verify', 'script'))
from check_mathjax import scan_text  # noqa: E402


def test_tag_inside_aligned_flagged():
    text = r"""
$$
\begin{aligned}
a &= b \\
c &= d
\tag{21.6}
\end{aligned}
$$
"""
    p = scan_text(text)
    assert len(p) == 1, p
    assert p[0][1] == 'aligned'


def test_tag_after_aligned_ok():
    text = r"""
$$
\begin{aligned}
a &= b \\
c &= d
\end{aligned}
\tag{21.6}
$$
"""
    assert scan_text(text) == []


def test_tag_top_level_ok():
    text = "$$\n\\frac{1}{2}=\\frac{2}{4}. \\tag{3.1}\n$$"
    assert scan_text(text) == []


def test_blockquote_prefix_handled():
    text = r"""
> $$
> \begin{aligned}
> a &= b \tag{5.1}
> \end{aligned}
> $$
"""
    p = scan_text(text)
    assert len(p) == 1 and p[0][1] == 'aligned', p


def test_gathered_and_split_flagged():
    for env in ('gathered', 'split', 'cases', 'array', 'pmatrix'):
        text = "$$\\begin{%s}\na\n\\tag{1}\n\\end{%s}$$" % (env, env)
        p = scan_text(text)
        assert len(p) == 1 and p[0][1] == env, (env, p)


def test_prose_tag_ignored():
    # \tag 出现在非 $$ 块的普通文本里不算
    assert scan_text("正文里写 \tag{1} 只是文字，不是公式。\n") == []


def test_two_display_blocks():
    text = r"""
$$
\begin{aligned}
a \tag{1}
\end{aligned}
$$
正常段落。
$$
b \tag{2}
$$
"""
    p = scan_text(text)
    assert len(p) == 1 and p[0][1] == 'aligned', p
