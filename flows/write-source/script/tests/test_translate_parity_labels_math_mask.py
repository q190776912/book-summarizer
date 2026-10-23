"""test_translate_parity_labels_math_mask.py — 判据 5「条目编号集合」的数学掩码回归。

2026-10-22 real-analysis（Teschl《Topics in Real and Functional Analysis》）实测两处假 FAIL：
  - ch4/0031_item_引理4_15.md：源 ['4.13','4.15'] / 译 ['4.10','4.13','4.15']
  - ch8/0005 早期同类（后被确认为真差异，另案修单元）
根因：`_labels` 直接在**原始正文**上跑 `_BOLD_RE = **...**`。泛函分析里 `$X^{**}$` /
`j_{**}` 双对偶记号自带字面 `**`，两段杂散 `**` 跨数学配对后，把夹在中间的**普通散文**
交叉引用编号（"由推论 4.10" 里没粗体）提成伪条目号。且 EN/CN **语序不同**（"by Corollary
4.10" 在句末、中文在 `j_{**}` 之前）→ 源译两侧抓到的杂散编号不同 → 假 FAIL。

真正的粗体标签（`**定理 4.15**`）从不落在 `$…$` / `$$…$$` 内部。故 `_labels` 先按与
`_has_prose` 相同的口径掩掉全部数学，再取粗体段——只消除假阳，不可能藏真缺陷。

本测试锁两件事：
1. **双对偶 `**` 不得被提成伪条目号**（真实事故样本必须转绿）；
2. **真粗体标签照常提取**（掩码不得吃掉数学外的合法条目编号）。
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "flows", "write-source", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from check_translate_parity import _labels


# ── 负向：双对偶 `**` 不得被提成伪条目号 ──────────────────────────────────

def test_double_adjoint_stars_do_not_create_phantom_label():
    """真实样本：`**引理 4.15.**` 头 + 正文散文交叉引用「由推论 4.10」+ 数学 `j_{**}`。
    掩码前，两个 `{**}` 之间的 `**` 配对会把 4.10 提成伪号；掩码后只应剩头标签 4.15。"""
    body = (
        "**引理 4.15.** 设 $X$ 是一个 Banach 空间。\n"
        "\n"
        "> 1. (i) 记 $j_{**} : Y^{**} \\to X^{**}$。注意由推论 4.10，$j_{**}$ 是等距的。"
        "于是 $x \\in \\overline{Y}$ 由推论 4.13。\n"
    )
    assert _labels(body) == ["4.15"], _labels(body)


def test_display_math_with_adjoints_stars_clean():
    r"""显示式里的 `\xrightarrow` 表格里满是 `**`/`*`，不得泄漏条目号。"""
    body = (
        "**定理 9.16.** 见下。\n"
        "\n"
        "> $$\n"
        "> \\begin{array}{ccc} X & \\xrightarrow{J_X} & X^{**}\\end{array}\n"
        "> $$\n"
        "\n"
        "> 由引理 9.10 得证。\n"
    )
    assert _labels(body) == ["9.16"], _labels(body)


def test_word_order_difference_does_not_diverge_source_vs_translation():
    """源/译语序不同导致杂散 `**` 配对位置变化，也不得改变抓到的条目号集合。"""
    en = (
        "**Lemma 4.15.** Let $Y$ be closed and $j_{**}$ is isometric "
        "by Corollary 4.10 for $Y^{**}$.\n"
    )
    cn = (
        "**引理 4.15.** 记 $j_{**}$ 由推论 4.10 是等距的，对 $Y^{**}$。\n"
    )
    assert _labels(en) == _labels(cn) == ["4.15"], (_labels(en), _labels(cn))


# ── 正向：掩码数学不得吃掉合法粗体标签 ────────────────────────────────────

def test_real_bold_labels_still_extracted_after_masking():
    """真粗体条目头（在数学之外）必须照常被抓，证明掩码是单调安全的。"""
    body = (
        "**定义 8.1.** 设 $f \\in L^p(X, d\\mu)$。\n"
        "\n"
        "**习题 8.2.** 证明 $L^\\infty(X) \\subseteq L^p(X)$。\n"
    )
    assert _labels(body) == ["8.1", "8.2"], _labels(body)


def test_bold_label_adjacent_to_inline_math_survives():
    r"""粗体标签紧贴行内数学（`**推论 4.13（$X^*$ 可分）**`）：标签号在 `$` 之外，仍须提取。"""
    body = "**推论 4.13.** 若 $X^*$ 可分则 $X$ 可分，见 $X^{**}$。\n"
    assert _labels(body) == ["4.13"], _labels(body)
