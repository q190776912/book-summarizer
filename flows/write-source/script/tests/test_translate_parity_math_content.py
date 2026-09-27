"""test_translate_parity_math_content.py — 判据 9/10「译文公式内容对账」回归。

Etingof《Introduction to representation theory》步骤6 实测（2026-09-28）：
ch1/0014 的源单元完整印着
`$f(xy) = f(x)f(y)$ for all $x, y \\in A$, and $f(1) = 1$`，翻译代理却凭「读到的」
内容写成半截 `**定义 1.8**：… 使得 $f(xy) = $`——整条定义丢了一半。
既有 parity 判据（`\\tag` / 图片 / 条目编号 / 节号）**全是集合对账**，公式**内容**
不在账上，未翻译哈希判据又因译文哈希一变即逃逸，`english_residues` 只认英文 →
一路全绿到 merge。根治 = `_math_content_problems`（显示式多重集 + 行内式悬空收尾）。

本测试锁三件事：
1. **真实事故样本必须被抓**（截断的行内式、丢失/改写的显示式）；
2. **不得误报正常译文差异**：中文把代词显化成行内公式（译文多出 `$P$`）、
   `$$` 块被包进 `>` 或换行位置不同（版式差异）都必须放行；
3. 完整照抄 / 纯公式 / 纯图单元干净通过。
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

from check_translate_parity import _math_content_problems, _norm_display_blocks

SRC_0014 = (
    "**Definition 1.8**: A homomorphism of algebras $f : A \\to B$ is a linear map "
    "such that $f(xy) = f(x)f(y)$ for all $x, y \\in A$, and $f(1) = 1$.\n"
)


def _hits(src, tr):
    return _math_content_problems(src, tr, "0014_item_x.md")


# ── 负向：真实事故样本必须被抓 ────────────────────────────────────────────

def test_truncated_inline_math_flagged():
    tr = "**定义 1.8**：代数同态 $f : A \\to B$ 是一个线性映射，使得 $f(xy) = $\n"
    probs = _hits(SRC_0014, tr)
    assert any("行内公式被截断" in p for p in probs), probs


def test_missing_inline_operands_flagged():
    # 行内式没有悬空收尾（`$f(xy)$` 是完整式），但整段条件被删 → 靠显示式判据抓不到，
    # 这里用带显示式的源验证「内容丢失」分支本身生效
    src = "**Proposition 1.1**: Let $V$ be finite.\n\n$$\n\\dim V = \\sum_i n_i \\dim V_i.\n$$\n"
    tr = "**命题 1.1**：设 $V$ 有限。\n\n$$\n\\dim V = \\sum_i n_i.\n$$\n"
    probs = _hits(src, tr)
    assert any("显示公式在译文里丢失" in p for p in probs), probs


def test_dropped_display_block_flagged():
    src = ("**Example 1.2**: We have\n\n$$\n\\operatorname{Hom}_A(V_1, V_2) \\ne 0.\n$$\n"
           "More generally\n\n$$\n\\chi_{V \\oplus W} = \\chi_V + \\chi_W.\n$$\n")
    tr = "**例 1.2**：我们有\n\n$$\n\\operatorname{Hom}_A(V_1, V_2) \\ne 0.\n$$\n更一般地。\n"
    probs = _hits(src, tr)
    assert any("显示公式在译文里丢失" in p for p in probs), probs
    assert any("chi_V" in p for p in probs), probs


def test_dangling_relation_variants_flagged():
    for tr in ("设 $\\phi \\to$\n", "于是 $a \\in$\n", "即 $U \\subseteq$\n", "且 $x =$\n"):
        assert _hits("", tr), tr


# ── 正向：正常译文差异不得误报 ────────────────────────────────────────────

def test_clean_copy_passes():
    tr = ("**定义 1.8**：一个代数同态 $f : A \\to B$ 是一个线性映射，"
          "使得对所有 $x, y \\in A$ 都有 $f(xy) = f(x)f(y)$，并且 $f(1) = 1$。\n")
    assert _hits(SRC_0014, tr) == []


def test_extra_inline_math_not_flagged():
    """中文把代词显化为行内公式（译文多出 `$P$` / `$n$ 阶`）属正常，不报。"""
    src = "**Proposition 2.2**: It is clear that this holds.\n\n$$\n\\phi_i \\circ \\phi_j = \\delta_{ij} \\phi_i.\n$$\n"
    tr = "**命题 2.2**：$P$ 显然满足该性质。\n\n$$\n\\phi_i \\circ \\phi_j = \\delta_{ij} \\phi_i.\n$$\n"
    assert _hits(src, tr) == []


def test_blockquote_wrapping_and_linebreaks_exempt():
    """`$$` 包进 `>`（CN 版必包标签表所致）与换行位置差异 = 版式差异，不报。"""
    src = "**Example 6.11**：\n\n$$\n\\operatorname{Ext}^{1}(Z, X) = \\mathrm{Hom}(X, Z)/G.\n$$\n"
    tr = ("**例 6.11**\n\n> **评注 6.12**\n>\n> $$\n> \\operatorname{Ext}^{1}(Z, X)\n>\n"
          "> = \\mathrm{Hom}(X, Z)/G.\n> $$\n")
    assert _norm_display_blocks(src) == _norm_display_blocks(tr)
    assert _hits(src, tr) == []


def test_pure_math_and_image_units_pass():
    assert _hits("$$\n\\int f\\,d\\mu = \\lim_{n\\to\\infty} \\int s_n\\,d\\mu.\n$$\n",
                 "$$\n\\int f\\,d\\mu = \\lim_{n\\to\\infty} \\int s_n\\,d\\mu.\n$$\n") == []
    img = '<img src="ch5_fig1.png" width="60%">\n'
    assert _hits(img, img) == []


def test_legit_complete_inline_forms_not_flagged():
    """`$X^*$` / `$A/B$` / `$n-1$` 都是完整式的合法收尾——判据只列关系/二元运算符。"""
    tr = "记 $X^*$ 为对偶，$G/H$ 为商，$n-1$ 为余数，$V^{\\otimes 2}$ 为张量平方。\n"
    assert _hits("", tr) == []


def test_ellipsis_ending_not_flagged():
    r"""省略号收尾本身即「以下省略」的完整式（本书实测两处误报：
    `$b(t) = 1 + b_1 t + b_2 t^2 + \cdots$`、`$s_n \alpha, \ldots$`）。"""
    tr = ("写 $b(t) = 1 + b_1 t + b_2 t^2 + \\cdots$，则序列 $s_n \\alpha, s_{n-1} s_n \\alpha, "
          "\\ldots$ 生成之。\n")
    assert _hits("", tr) == []


def test_source_attested_dangling_form_exempt():
    """源书本就用悬空式指代一个概念 → 译文照抄不是截断（本书实测两处：
    ch6/0027 函子 `$V \\otimes$`、ch2/0033 「包含关系 `$\\subseteq$`」）。"""
    src = "the functor $V \\otimes$ has a right adjoint, and the inclusion $\\subseteq$ is clear.\n"
    tr = "函子 $V \\otimes$ 有右伴随，且包含关系 $\\subseteq$ 是显然的。\n"
    assert _hits(src, tr) == []


def test_attestation_does_not_mask_real_truncation():
    """豁免只在「源文有此式」时生效：源文写全式、译文砍半截仍须被抓。"""
    src = "$f(xy) = f(x)f(y)$ for all $x, y \\in A$.\n"
    tr = "使得 $f(xy) = $ 对所有。\n"
    probs = _hits(src, tr)
    assert any("行内公式被截断" in p for p in probs), probs


# ── 正向：跨书实测的三类**表述/排版**差异（real-analysis 等已收官书不得翻案）────
# 判据 9 逐字严格版在 real-analysis（已收官）假报 19 个单元、Robinson 动力学 1、
# do Carmo 曲线曲面 2 —— 全是下面三类，故归一时删 `\text{}` 体、剥尾部标点，
# 并允许「整块搬进行内」兜底。

def test_translated_text_body_inside_formula_exempt():
    r"""公式内 `\text{and}` → `\text{和}` 是**正确**译法，不是内容差异。"""
    src = "$$\nx\\vee y=\\max(x,y)\\qquad\\text{and}\\qquadx\\wedge y=\\min(x,y).\n$$\n"
    tr = "$$\nx\\vee y=\\max(x,y)\\qquad\\text{和}\\qquadx\\wedge y=\\min(x,y)。\n$$\n"
    assert _hits(src, tr) == []


def test_translated_case_condition_exempt():
    src = ("$$\na_{n}=\\begin{cases}1,&n\\text{even};\\\\ 0,&n\\text{odd}.\\end{cases}\n$$\n")
    tr = ("$$\na_{n}=\\begin{cases}1,&n\\text{偶数};\\\\ 0,&n\\text{奇数}.\\end{cases}\n$$\n")
    assert _hits(src, tr) == []


def test_operatorname_not_exempt():
    r"""`\mathrm` / `\operatorname` 是算子名，被改动仍须报（区别于 `\text{}` 散文）。"""
    src = "$$\n\\operatorname{Hom}_A(V_1, V_2) \\ne 0.\n$$\n"
    tr = "$$\n\\operatorname{Hom}_B(V_1, V_2) \\ne 0.\n$$\n"
    probs = _hits(src, tr)
    assert any("显示公式在译文里丢失" in p for p in probs), probs


def test_trailing_punctuation_exempt():
    """中英句末标点习惯差异（`.` vs `。`、`$$…0.` vs `$$…0`）不报。"""
    src = "$$\n\\lim_{j\\to\\infty}r_{j}=0.\n$$\n\n$$\nM<\\infty.\n$$\n"
    tr = "$$\n\\lim_{j\\to\\infty}r_{j}=0\n$$\n\n$$\nM<\\infty,\n$$\n"
    assert _hits(src, tr) == []


def test_display_relocated_inline_exempt():
    """EN 版独立成块、CN 版把同一条式子并进展望句子里写成行内式 = 排版搬迁，内容一字
    未丢 → 放行（real-analysis ch5/0009 等 7 单元实测）。"""
    src = ("**Proposition 5.5**: Suppose $f$ is real-valued.\n\n"
           "$$\n\\{x : f(x) \\geq a\\} = \\bigcap_{n=1}^{\\infty} \\{x : f(x) > a - 1/n\\}\n$$\n")
    tr = ("**命题 5.5**：假设 $f$ 是实值函数。\n\n"
          "> 2. 如果 $f$ 是可测的，那么 $\\{x : f(x) \\geq a\\} = "
          "\\bigcap_{n=1}^{\\infty} \\{x : f(x) > a - 1/n\\}$ 表明 (1) 成立则 (4) 成立。\n")
    assert _hits(src, tr) == []


def test_relocation_fallback_does_not_mask_truncation():
    """兜底只认**完整**内核作为子串：搬进行内同时被砍半截仍须被抓。"""
    src = ("$$\n\\{x : f(x) \\geq a\\} = \\bigcap_{n=1}^{\\infty} \\{x : f(x) > a - 1/n\\}\n$$\n")
    tr = "于是 $\\{x : f(x) \\geq a\\}$ 成立。\n"
    probs = _hits(src, tr)
    assert any("显示公式在译文里丢失" in p for p in probs), probs


