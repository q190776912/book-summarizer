# -*- coding: utf-8 -*-
"""回归：sanitize_name 60 字符封顶不得把中英括号段名的尾 `)` 截丢。

Koopman Operator 实测（2026-10-02）：`5.3 Koopman算子与主特征函数
(TheKoopmanOperatorandPrincipalEigenfunctions)` 超 60 → 落盘文件名成
`…Eigenfunctions.md`（括号悬空），`6.5 …(Data-DrivenAlgorithmsfortheStochasticKoopma.md`
同理——纯外观但产出破损名。修后截断点回退一格补 `)`，保持括号闭合。
"""
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from split_chapters import sanitize_name


def test_long_paren_name_keeps_closing_paren():
    name = "5.3Koopman算子与主特征函数(TheKoopmanOperatorandPrincipalEigenfunctions)"
    out = sanitize_name(name)
    assert len(out) <= 61
    assert out.endswith(")")
    assert out.count("(") == out.count(")")


def test_truncation_before_open_paren_drops_dangling_open():
    # 截断点恰在 `(` 处：不得留下悬空 `(`，也不得凭空补 `)`
    stem = "甲" * 59
    out = sanitize_name(stem + "(Tail)")
    assert "(" not in out and ")" not in out


def test_short_name_untouched():
    assert sanitize_name("7.2Preliminaries(Preliminaries)") == \
        "7.2Preliminaries(Preliminaries)"
