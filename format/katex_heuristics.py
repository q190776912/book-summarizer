import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
# math mode (formatting.md rule #8). They must be written as KaTeX commands:
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
    # Strip inline $...$ and `...` FIRST so the subsequent display-math
    # detection only sees genuine `$$` delimiters (not adjacent-inline `$$`).
    line = re.sub(r'\$[^$]*\$', ' ', line)
    line = re.sub(r'`[^`]*`', ' ', line)
    # Restore protected display delimiters.
    line = line.replace('\x00D\x00', '$$')
    # handle $$ display math (possibly multi-line)
    n = line.count('$$')
    if in_display:
        if n % 2 == 1:
            in_display = False
            line = line.split('$$', 1)[1] if '$$' in line else ''
        else:
            return '', in_fence, in_display
    else:
        if n % 2 == 1:
            in_display = True
            line = line.split('$$', 1)[0]
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
                f'$\\cong$, ...) per formatting.md rule #8')
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
