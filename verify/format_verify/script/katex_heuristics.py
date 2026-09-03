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

import os, sys

import re

BAD_MACRO_PATTERNS = [
    (r'\\bigl\(\s*\\(sup|inf)\s*\\\{', r'\bigl(\sup\{ / \bigl(\inf\{ — KaTeX 不支持，改用 \sup\{ 或 \bigl(\sup_{…}'),
    (r'\\left\.\\frac', r'\left.\frac{}{}\right|_{} — KaTeX 级联失败，改用 \dfrac{}{}\bigr|_{}'),
]


# Characters that only appear inside commutative diagrams / math rendered as
# ASCII/Unicode art (never in real source code). Used to detect the
# anti-pattern of wrapping formulas/diagrams in ``` code fences.
_FENCE_MATH_SIGNS = ('→', '↓', '←', '↑', '⇒', '↘', '↗', '↔', '⟶', '⟹',
                      '─', '│', '╲', '╳', '┼', '├', '┤', '┐', '└', '┌', '┘')
_FENCE_MATH_TOKENS = ('\\begin', '@>', '@V', '@|', '@AAA', '@<<', '@=',
                      '-->', '<--', '---->', '<----', '-|->', '--|>',
                      '=|>')


# Pass 1c: raw Unicode math arrows / relation glyphs are FORBIDDEN outside
# math mode (writing-rules.md rule #8). They must be written as KaTeX commands:
#   ↪ \hookrightarrow   ↠ \twoheadrightarrow   ↦/↣ \mapsto   → \to
#   ⇒ \implies / \Rightarrow   ⇔ \iff   ≅ \cong
RAW_MATH_ARROWS = ('↪', '↠', '↦', '↣', '→', '⇒', '⇔', '⇐', '⇎', '⇏',
                   '⇉', '↤', '↥', '↮', '↝', '↺', '↻', '⟶', '⟼', '⟻',
                   '⤇', '⤊', '≅')


def _strip_math_and_code(line, in_fence, in_display):
    """Remove $...$ / $$...$$ spans and code from a line so remaining text can
    be scanned for raw Unicode arrows. Returns (stripped_text, in_fence,
    in_display). Lines inside code fences or display math return ''.

    IMPORTANT: inline $...$ spans are stripped BEFORE display-math detection.
    Otherwise two adjacent inline spans such as  $\\mathrm{RP}$$^{24}$  form a
    spurious `$$` substring that corrupts the multi-line display-math parity
    tracker (every following `$$` block gets mis-classified and its content
    wrongly scanned for naked LaTeX commands). Standalone `$$` display
    delimiters (on their own line, possibly blockquote-prefixed) are protected
    from inline stripping so they still toggle the display-math state.
    """
    ls = line.strip()
    if ls.startswith('```'):
        return '', (not in_fence), in_display
    if in_fence:
        return '', in_fence, in_display
    # --- Normalise LaTeX \(...\) / \[...\] math delimiters (valid math mode) ---
    # These ARE math and must not be scanned for "naked commands" / raw arrows.
    # Single-line \[...\] is stripped directly. Remaining standalone \[ / \]
    # (one per line, possibly multiline display math) are rewritten to $$ so the
    # display-math state machine below handles them. Inline \(...\) is stripped
    # directly. Without this, every \command inside \(...\)/\[...\] is falsely
    # flagged as a "naked LaTeX command outside math mode".
    line = re.sub(r'\\\[.*?\\\]', ' ', line)
    line = line.replace('\\[', '$$').replace('\\]', '$$')
    line = re.sub(r'\\\(.*?\\\)', ' ', line)
    # Protect standalone display-math delimiters (strict convention: `$$` alone
    # on the line, optionally `> `-prefixed) from inline-$ stripping, so they
    # keep toggling the display-math state and are not consumed as inline math.
    is_standalone_disp = bool(
        re.match(r'^\s*>\s*\$\$\s*$', line) or re.match(r'^\s*\$\$\s*$', line))
    if is_standalone_disp:
        line = line.replace('$$', '\x00D\x00', 1)
    # Also protect single-line $$...$$ display math from inline-$ stripping
    # Pattern: $$...$$ on the same line (not standalone)
    line = re.sub(r'\$\$[^$]+\$\$', lambda m: '\x00D\x00' + m.group()[2:-2] + '\x00D\x00', line)
    # Strip inline $...$ and `...` FIRST so the subsequent display-math
    # detection only sees genuine `$$` delimiters (not adjacent-inline `$$`).
    line = re.sub(r'\$[^$]*\$', ' ', line)
    line = re.sub(r'`[^`]*`', ' ', line)
    # Restore protected display delimiters.
    # \x00D\x00 is a 3-char marker: NUL + 'D' + NUL
    line = line.replace('\x00D\x00', '$$')
    # handle $$ display math (possibly multi-line)
    # Use chr(36)+chr(36) to avoid Python escape interpretation of $$
    dd = chr(36) + chr(36)
    n = line.count(dd)
    if in_display:
        if n % 2 == 1:
            in_display = False
            line = line.split(dd, 1)[1] if dd in line else ''
        else:
            return '', in_fence, in_display
    else:
        if n % 2 == 1:
            in_display = True
            line = line.split(dd, 1)[0]
        elif n >= 2:
            line = re.sub(r'\$\$.*?\$\$', ' ', line)
    return line, in_fence, in_display


def find_raw_arrow_errors(lines):
    """Pass 1c: flag raw Unicode math arrows outside math mode."""
    errs = []
    in_fence = False
    in_display = False
    for i, line in enumerate(lines, 1):
        text, in_fence, in_display = _strip_math_and_code(
            line, in_fence, in_display)
        if not text:
            continue
        bad = [ch for ch in RAW_MATH_ARROWS if ch in text]
        if bad:
            errs.append(
                f'line {i}: raw Unicode math arrow(s) {"".join(bad)} outside '
                f'math mode — use KaTeX ($\\hookrightarrow$, $\\to$, '
                f'$\\cong$, ...) per writing-rules.md rule #8')
    return errs


_NAKED_CMD_RE = re.compile(r'\\[A-Za-z]{2,}')


def find_naked_command_errors(lines):
    """Pass 1d: flag LaTeX commands (\\mathrm, \\operatorname, \\mathbb, ...)
    appearing OUTSIDE math mode — they render as literal code, not formulas.
    Fix: wrap the whole math run in $...$."""
    errs = []
    in_fence = False
    in_display = False
    for i, line in enumerate(lines, 1):
        text, in_fence, in_display = _strip_math_and_code(
            line, in_fence, in_display)
        if not text:
            continue
        m = _NAKED_CMD_RE.search(text)
        if m:
            errs.append(
                f'line {i}: naked LaTeX command "{m.group(0)}" outside math '
                f'mode — wrap the formula in $...$ (it will not render '
                f'otherwise)')
    return errs


# Pass 1e: a `$` at line start that swallowed a structural prefix, e.g.
#   `$> - \mu_*$ ...`  or  `$> (b) \mathbb Z_n$ ...`  or  `$- \mu:A\to B$ ...`
# This destroys the blockquote `>` marker / list bullet / item numbering
# (they get rendered INSIDE the formula). The prefix must stay outside `$`.
_SWALLOWED_PREFIX_RE = re.compile(
    r'^\$\s*(?:>\s*)?(?:[-*]\s+|\([A-Za-z0-9]\)\s+|\d+[.)]\s+)')


# ============================================================================
# Pass 1f (NEW, 2026-08-04): "character-type" formulas outside math mode
#   (writing-rules.md rule #17). ALL mathematical content MUST be rendered via
#   KaTeX ($...$ / $$...$$); it must NEVER appear as bare characters in the
#   running text. Two sub-cases:
#     (A) Raw Unicode math glyphs (Greek letters, operators, relations, sets,
#         ...). These are never legitimate prose in these summaries and must be
#         rewritten as KaTeX (e.g. σ -> $\sigma$, √ -> $\sqrt{}$, ∑ -> $\sum$).
#     (B) ASCII math written as plain text: probability/expectation operators
#         (Pr{ Pr( E[ Var( Cov( ...), single-letter function calls with a
#         math-like argument (X(t) p_k(n) f(x+y)), and variable+digit tokens
#         (x0 t1 y2) meaning a subscripted variable.
#   NOTE: superscript digits ² ³ are intentionally NOT enforced here (physical
#   units like km² would false-positive); they remain a documentation request.
# ============================================================================

# (A) Unicode math glyphs — high precision: essentially never prose.
BARE_MATH_GLYPHS = (
    # Greek (math variables / constants)
    'α', 'β', 'γ', 'δ', 'ε', 'ζ', 'η', 'θ', 'κ', 'λ', 'μ', 'ν', 'ξ',
    'π', 'ρ', 'σ', 'τ', 'φ', 'χ', 'ψ', 'ω',
    'Γ', 'Δ', 'Θ', 'Λ', 'Ξ', 'Σ', 'Φ', 'Ψ', 'Ω',
    # operators / relations
    '√', '∑', '∞', '≤', '≥', '≠', '≈', '≡', '×', '÷', '±', '∓',
    '∂', '∇', '∏', '∓',
    # set theory / logic / number sets
    '∪', '∩', '∈', '∉', '⊂', '⊆', '∀', '∃', '∅',
    'ℝ', 'ℕ', 'ℤ', 'ℂ',
)

# (B) probability / expectation / variance operators written bare.
# Lookbehind (?<![.\w]) excludes citation contexts like "1.7.E (...)" /
# "Exercise ... E (...)" where E is a label, not the expectation operator.
_PROB_OP_RE = re.compile(r'(?<![.\w])(?:Pr|E|Var|Cov)\s*[\(\[\{]')

# (B) single-letter function call: name is ONE letter, arg is math-like.
# Lookbehind (?<![A-Za-z$0-9.]) excludes citation sub-refs like "1.7.H(c)",
# "2(a)", "Figure 3(b)" — these are label references, not math calls.
_FUNC_CALL_RE = re.compile(r'(?<![A-Za-z$0-9.])([A-Za-z])\s*\(([^)]{0,25})\)')

# (B) variable + subscript-digit token (x0 t1 y2 ...), standalone math variable.
_VAR_DIGIT_RE = re.compile(r'(?<![A-Za-z$\\])([a-z])\d(?![A-Za-z$])')

# words that legitimately precede a '(' in prose — never a math function call.
_LABEL_WORDS = (
    'Example', 'Section', 'Chapter', 'Theorem', 'Definition', 'Corollary',
    'Remark', 'Note', 'Figure', 'Part', 'Lemma', 'Proposition', 'Scholium',
    'Exercise', 'Hint', 'Appendix', 'Equation', 'See', 'If', 'When', 'Since',
    'Then', 'Proof', 'Random', 'Brown', 'Chapman', 'Kolmogorov', 'Schauder',
    'Haar', 'Bessel', 'Cauchy', 'Borel', 'Cantelli', 'Parseval', 'Optional',
    'Martingale', 'Brownian', 'Scholium',
)


def find_bare_math_errors(lines):
    """Pass 1f: flag "character-type" formulas OUTSIDE math mode.

    Math must be rendered with KaTeX, never as bare characters. Detects:
      (A) raw Unicode math glyphs (σ √ ∑ ∞ ≤ ≥ π η Δ μ λ ...),
      (B) ASCII math as plain text (Pr{ X(t) p_k(n) x0 ...).
    Lines inside $...$ / $$...$$ / code fences are already stripped by
    _strip_math_and_code, so anything left is genuinely outside math mode.
    """
    errs = []
    in_fence = False
    in_display = False
    for i, line in enumerate(lines, 1):
        # Skip <img ...> lines entirely: alt-text is a descriptive caption, not
        # rendered markdown, so bare chars there are neither bugs nor renderable.
        if '<img' in line:
            continue
        text, in_fence, in_display = _strip_math_and_code(
            line, in_fence, in_display)
        if not text:
            continue
        # (A) Unicode math glyphs
        bad = [ch for ch in BARE_MATH_GLYPHS if ch in text]
        if bad:
            errs.append(
                f'line {i}: character-type formula — raw Unicode math glyph(s) '
                f'{"".join(bad)} outside math mode — wrap in $...$ / rewrite as '
                f'KaTeX (writing-rules.md rule #17)')
        # (B) probability / expectation / variance operators
        for m in _PROB_OP_RE.finditer(text):
            errs.append(
                f'line {i}: character-type formula — bare operator '
                f'"{m.group(0).strip()}" outside math mode — write as '
                f'$\\Pr{{...}}$, $\\mathbb{{E}}[...]$, $\\operatorname{{Var}}(...)$ '
                f'(rule #17)')
        # (B) single-letter function call with math-like argument
        for m in _FUNC_CALL_RE.finditer(text):
            arg = m.group(2)
            # skip if the argument is a real English phrase (label-like)
            if re.search(r'[a-z]{4,}', arg):
                continue
            # skip if preceded by a label word (e.g. "Example (X(t)...")
            pre = text[max(0, m.start() - 16):m.start()]
            last_tok = pre.split()[-1] if pre.split() else ''
            if last_tok.rstrip('(') in _LABEL_WORDS:
                continue
            # argument must look math-like (digit / _ / , | = < > ; ^ ± or 1-2 letters)
            if (re.search(r'[\d_,|=<>;^±]', arg)
                    or re.fullmatch(r'[A-Za-z]{1,2}', arg)):
                errs.append(
                    f'line {i}: character-type formula — bare function call '
                    f'"{m.group(0)}" outside math mode — wrap as ${m.group(0)}$ '
                    f'(rule #17)')
        # (B) variable + digit subscript token
        for m in _VAR_DIGIT_RE.finditer(text):
            errs.append(
                f'line {i}: character-type formula — bare variable '
                f'"{m.group(0)}" (variable+subscript) outside math mode — '
                f'write as ${m.group(0)[0]}_{m.group(0)[1]}$ (rule #17)')
    return errs



def find_swallowed_prefix_errors(lines):
    """Pass 1e: flag `$` that swallowed a blockquote/list/number prefix."""
    errs = []
    in_fence = False
    for i, line in enumerate(lines, 1):
        s = line.strip()
        if s.startswith('```'):
            in_fence = not in_fence
            continue
        if in_fence or s.startswith('$$'):
            continue
        if _SWALLOWED_PREFIX_RE.match(line):
            errs.append(
                f'line {i}: math `$` swallowed a structural prefix '
                f'(`>` / list bullet / item number) — move the prefix back '
                f'outside and open `$` at the math content: {line[:50]!r}')
    return errs


def _fence_looks_like_math(content):
    """True if a ``` ... ``` block's content is actually a formula/diagram
    that should have been written as $$ ... $$ (use \\begin{CD} for diagrams)."""
    if not content.strip():
        return False
    if any(ch in content for ch in _FENCE_MATH_SIGNS):
        return True
    if any(tok in content for tok in _FENCE_MATH_TOKENS):
        return True
    return False
