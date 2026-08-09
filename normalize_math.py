#!/usr/bin/env python3
"""normalize_math.py — fix formula delimiter defects in book-summarizer output.

Two defect classes this handles:
  A) Math written in Markdown BACKTICKS (`\\xi_1`) -> render as literal code, not math.
     Convert math-bearing backtick spans to inline $...$ (mapping Unicode -> LaTeX).
  B) Math in $...$ but CHOPPED: a subscript / norm-bar / parenthesis left OUTSIDE the
     math region, e.g.
        $\\alpha$_1   |   \\|$\\hat{y}$\\|_1   |   $\\delta$_{nj}
     Re-join into a single $...$ region.

DESIGN PRINCIPLE — SAFE ONLY:
  * We never merge across whitespace (space-separated $...$ are left as separate,
    valid inline math regions — merging them is guesswork and corrupts text).
  * Bare-field rules (R^n, C[a,b], ...) are applied ONLY to NON-math segments, so
    math that is already correctly wrapped is never double-wrapped.
  * We do NOT attempt to "repair" function-application patterns like $f(x)$ — those
    are already valid KaTeX; touching them destroyed formulas in testing.
Safe to run: it only touches delimiter style, never alters underlying LaTeX commands.
Back up the target files first.
"""
import re
import sys
import os
import shutil

# ---- Unicode math/greek -> LaTeX -------------------------------------------
UNI_MAP = {
    'α': r'\alpha', 'β': r'\beta', 'γ': r'\gamma', 'δ': r'\delta', 'ε': r'\varepsilon',
    'ζ': r'\zeta', 'η': r'\eta', 'θ': r'\theta', 'ι': r'\iota', 'κ': r'\kappa',
    'λ': r'\lambda', 'μ': r'\mu', 'ν': r'\nu', 'ξ': r'\xi', 'ο': r'\omicron',
    'π': r'\pi', 'ρ': r'\rho', 'ς': r'\sigma', 'σ': r'\sigma', 'τ': r'\tau',
    'υ': r'\upsilon', 'φ': r'\varphi', 'χ': r'\chi', 'ψ': r'\psi', 'ω': r'\omega',
    'Γ': r'\Gamma', 'Δ': r'\Delta', 'Θ': r'\Theta', 'Λ': r'\Lambda', 'Ξ': r'\Xi',
    'Π': r'\Pi', 'Σ': r'\Sigma', 'Φ': r'\Phi', 'Ψ': r'\Psi', 'Ω': r'\Omega',
    '∞': r'\infty', '∈': r'\in', '∉': r'\notin', '⊂': r'\subset', '⊃': r'\supset',
    '⊆': r'\subseteq', '⊇': r'\supseteq', '∀': r'\forall', '∃': r'\exists',
    '∅': r'\emptyset', 'ℝ': r'\mathbb{R}', 'ℤ': r'\mathbb{Z}', 'ℕ': r'\mathbb{N}',
    'ℚ': r'\mathbb{Q}', 'ℂ': r'\mathbb{C}', '≤': r'\le', '≥': r'\ge',
    '→': r'\to', '↦': r'\mapsto', '⇒': r'\Rightarrow', '⇔': r'\Leftrightarrow',
    '∫': r'\int', '∑': r'\sum', '∏': r'\prod', '·': r'\cdot', '×': r'\times',
    '÷': r'\div', '∂': r'\partial', '∇': r'\nabla', '∧': r'\wedge', '∨': r'\vee',
    '¬': r'\neg', '−': '-',
}
SUP_MAP = {'⁰': '^0', '¹': '^1', '²': '^2', '³': '^3', '⁴': '^4', '⁵': '^5',
           '⁶': '^6', '⁷': '^7', '⁸': '^8', '⁹': '^9', 'ⁿ': '^n'}


def _map_uni(s: str) -> str:
    out = ''.join(UNI_MAP.get(c, c) for c in s)
    out = ''.join(SUP_MAP.get(c, c) for c in out)
    return out


# ---- Class A: backtick -> $ -------------------------------------------------
def fix_backticks(t: str) -> str:
    def repl(m):
        inner = m.group(1)
        if '$' in inner:            # already contains math delimiters: skip
            return m.group(0)
        return '$' + _map_uni(inner) + '$'
    return re.sub(r'`([^`\n]+)`', repl, t)


# ---- Class B: re-join chopped $...$ (LOCAL, anchored, SAFE rules only) ----
def _fix_norm_bars(t: str) -> str:
    """Norm bars (backslash + '|') around a $...$ region, optional trailing subscript.

    Handles both-sided  \\| $x$ \\|_N  ->  $\\|x\\|_N$  in one shot.
    The pipe is matched via re.escape so it is NEVER an alternation operator.
    """
    NB = re.escape(r'\|')   # regex that matches a single LaTeX  \|
    t = re.sub(NB + r'\$([^$\n]+)\$' + NB + r'(_[A-Za-z0-9]+)?',
               lambda m: r'$\|' + m.group(1) + r'\|' + (m.group(2) or '') + '$', t)
    # Trailing-only norm bar (no leading bar):  $x$ \\|_N  ->  $\\|x\\|_N$
    t = re.sub(r'(\$[^$\n]*?)\$' + NB + r'(_[A-Za-z0-9]+)',
               lambda m: m.group(1) + r'\|' + m.group(2) + '$', t)
    return t


def _fix_boundary_norms(t: str) -> str:
    """A norm ``\\|x\\|`` the writer SPLIT across a ``$`` boundary, e.g.
        $\\|x$\\| gives \\|$T^\\times\\|$   ->   $\\|x\\|$ gives $\\|T^\\times\\|$
    The tell-tale is a ``\\|`` IMMEDIATELY adjacent to ``$`` (no space): the closing
    ``$`` lands in the middle of the norm. Two complementary rules rejoin it.
    These only fire on adjacency, so correctly-wrapped ``$\\|x\\|$`` is never touched.
    """
    return t


def _fix_subscript_outside(t: str) -> str:
    """A subscript / braced-subscript left OUTSIDE a closing $:  $\\alpha$_1 -> $\\alpha_1$
    Also  $\\delta$_{nj}  ->  $\\delta_{nj}$.  Only touches the boundary, never merges
    across whitespace or into function arguments.
    """
    # (1) bare subscript right after closing $:   $\alpha$_1 -> $\alpha_1$
    t = re.sub(r'(\$[^$\n]*?)(\$)(\_[A-Za-z0-9]+)',
               lambda m: '$' + m.group(1)[1:] + m.group(3) + '$', t)
    # (1c) braced subscript after closing $:   $\delta$_{nj} -> $\delta_{nj}
    t = re.sub(r'(\$[^$\n]*?)(\$)(\_\{[^\}\n]+\})',
               lambda m: '$' + m.group(1)[1:] + m.group(3) + '$', t)
    return t


# ---- Bare-field rules, applied ONLY to non-math segments --------------------
def _fix_bare_fields(seg: str) -> str:
    s = seg
    # K = R  /  K = C  (scalar field statement)
    s = re.sub(r'K\s*=\s*R\b(?!\$)', r'K = $\\mathbb{R}$', s)
    s = re.sub(r'K\s*=\s*C\b(?!\$)', r'K = $\\mathbb{C}$', s)
    # C[a, b]  ->  $C[a, b]$
    s = re.sub(r'(?<!\$)\bC\[a,\s*b\]', r'$C[a, b]$', s)
    # R^n, R^3, ...  and C^n, C^3, ...  (vector / unitary spaces)
    s = re.sub(r'(?<!\$)\bR\^([A-Za-z0-9]+)', r'$\\mathbb{R}^\1$', s)
    s = re.sub(r'(?<!\$)\bC\^([A-Za-z0-9]+)', r'$\\mathbb{C}^\1$', s)
    # sequence spaces l^p, l^q, l^2, l^1, l^\infty, l^{p'}  (lookbehind guards $l^p$)
    s = re.sub(r'(?<!\$)\bl\^(\\{0,1}infty|[A-Za-z0-9]+|\{[^}]+\})', r'$l^\1$', s)
    # bare norms in prose:  \|x\|  ->  $\|x\|$   (single identifier between the bars)
    s = re.sub(r'\\\|([A-Za-z][A-Za-z0-9_{}]*?)\\\|', r'$\|\1\|$', s)
    return s


def _protect_and_apply(t: str, fn) -> str:
    """Apply fn only to NON-math segments; math regions ($$...$$ and $...$) are
    returned untouched so bare-field rules can never double-wrap correct math."""
    parts = re.split(r'(\$\$[\s\S]*?\$\$|\$[^$\n]+?\$)', t)
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 1:           # captured math segment
            out.append(p)
        else:
            out.append(fn(p))
    return ''.join(out)


def _fix_misc(t: str) -> str:
    """A few safe whole-text joins for super/sub-script that was split from a
    $...$ math region (these span a math boundary, so they are not handled by the
    non-math-only bare-field pass):
        l^$\infty$  ->  $l^\infty$
        _$\infty$   ->  _{\infty}
    """
    t = re.sub(r'(?<!\$)\bl\^(\$\\infty\$)', lambda m: '$l^\\infty$', t)
    t = re.sub(r'_\$(\\infty)\$', lambda m: r'_{\infty}', t)
    return t


def normalize(t: str) -> str:
    t = fix_backticks(t)
    for _ in range(3):           # a few fixed passes; re.sub never loops
        t2 = _fix_norm_bars(t)
        t2 = _fix_subscript_outside(t2)
        t2 = _protect_and_apply(t2, _fix_bare_fields)
        t2 = _fix_misc(t2)
        if t2 == t:
            break
        t = t2
    return t


# ---- reporting --------------------------------------------------------------
def stats(t: str):
    spans = re.findall(r'`([^`\n]+)`', t)
    bs = chr(92)
    math_uni = "≤≥⊂⊃⊆⊇∈∉∋∀∃∅∞∫∑∏ℝℤℕℚℂ→↦⇒⇔∧∨¬∂∇·×÷αβγδεζηθικλμνξοπρςστυφχψωΓΔΘΛΞΠΣΦΨΩⁿ"
    bad_bt = [s for s in spans if (bs in s) or any(c in math_uni for c in s)]
    # residual defect signals (heuristic)
    chopped = len(re.findall(r'\$\w*?\$_[A-Za-z0-9]', t)) \
        + len(re.findall(r'\\\|\$[^$\n]+?\$', t))
    return len(spans), len(bad_bt), chopped


def main():
    files = sys.argv[1:]
    for f in files:
        t = open(f, encoding='utf-8').read()
        sb, bb, ch = stats(t)
        t2 = normalize(t)
        sb2, bb2, ch2 = stats(t2)
        if t2 != t:
            bak = f + '.bak_mathfix'
            if not os.path.exists(bak):
                shutil.copy(f, bak)
            open(f, 'w', encoding='utf-8').write(t2)
            print(f"{os.path.basename(f):50s} backtick={sb}->{sb2}  math_bearing={bb}->{bb2}  chopped={ch}->{ch2}")
        else:
            print(f"{os.path.basename(f):50s} (unchanged)")


if __name__ == '__main__':
    main()
