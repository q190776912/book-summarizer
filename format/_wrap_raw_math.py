"""One-off helper: wrap raw Unicode math glyphs / arrows that appear OUTSIDE
existing math ($...$ / $$...$$) or code (`...` / ```) in $...$ so they pass
book-summarizer's rule #8 / #17 KaTeX heuristic.

WHY: the Kreyszig EN drafts were written with math as plain text
(e.g. "x ∈ X", "f: X → Y", "∑ a_n"). The Unicode glyph/arrow class is
unambiguous and safe to auto-wrap; naked LaTeX commands (\\sum) and bare
function calls (f(x)) are left for hand-fixing (they need context).

The mask logic mirrors format/katex_heuristics._strip_math_and_code so we
never wrap a glyph that is already inside math or code.
"""
import os, re, sys

# --- arrow map ---
ARROW = {
    '↪': r'\hookrightarrow', '↠': r'\twoheadrightarrow', '↦': r'\mapsto',
    '↣': r'\rightarrowtail', '→': r'\to', '⇒': r'\implies', '⇔': r'\iff',
    '⇐': r'\impliedby', '⇎': r'\nLeftrightarrow', '⇏': r'\nRightarrow',
    '⇉': r'\rightrightarrows', '↤': r'\mapsfrom', '↥': r'\uparrow',
    '↮': r'\nleftrightarrow', '↝': r'\rightsquigarrow', '↺': r'\circlearrowleft',
    '↻': r'\circlearrowright', '⟶': r'\longrightarrow', '⟼': r'\longmapsto',
    '⟻': r'\longmapsfrom', '⤇': r'\longrightarrow', '⤊': r'\uparrow',
    '≅': r'\cong',
}
# --- bare Unicode math glyph map (mirrors katex_heuristics.BARE_MATH_GLYPHS) ---
GLYPH = {
    'α': r'\alpha', 'β': r'\beta', 'γ': r'\gamma', 'δ': r'\delta',
    'ε': r'\varepsilon', 'ζ': r'\zeta', 'η': r'\eta', 'θ': r'\theta',
    'κ': r'\kappa', 'λ': r'\lambda', 'μ': r'\mu', 'ν': r'\nu', 'ξ': r'\xi',
    'π': r'\pi', 'ρ': r'\rho', 'σ': r'\sigma', 'τ': r'\tau', 'φ': r'\varphi',
    'χ': r'\chi', 'ψ': r'\psi', 'ω': r'\omega',
    'Γ': r'\Gamma', 'Δ': r'\Delta', 'Θ': r'\Theta', 'Λ': r'\Lambda',
    'Ξ': r'\Xi', 'Σ': r'\Sigma', 'Φ': r'\Phi', 'Ψ': r'\Psi', 'Ω': r'\Omega',
    '√': r'\surd', '∑': r'\sum', '∞': r'\infty', '≤': r'\le', '≥': r'\ge',
    '≠': r'\ne', '≈': r'\approx', '≡': r'\equiv', '×': r'\times',
    '÷': r'\div', '±': r'\pm', '∓': r'\mp', '∂': r'\partial',
    '∇': r'\nabla', '∏': r'\prod', '∪': r'\cup', '∩': r'\cap',
    '∈': r'\in', '∉': r'\notin', '⊂': r'\subset', '⊆': r'\subseteq',
    '∀': r'\forall', '∃': r'\exists', '∅': r'\emptyset',
    'ℝ': r'\mathbb{R}', 'ℕ': r'\mathbb{N}', 'ℤ': r'\mathbb{Z}', 'ℂ': r'\mathbb{C}',
}
ALL = {}
ALL.update(ARROW)
ALL.update(GLYPH)


def compute_protected(lines):
    """Return list (per line) of sets of protected char indices
    (inside $...$ / $$...$$ / `...` / ``` / or a display-math block)."""
    in_fence = False
    in_display = False
    masks = []
    for line in lines:
        prot = set()
        stripped = line.lstrip()
        if stripped.startswith('```'):
            in_fence = not in_fence
            for i in range(len(line)):
                prot.add(i)
            in_display = False
            masks.append(prot)
            continue
        if in_fence:
            for i in range(len(line)):
                prot.add(i)
            masks.append(prot)
            continue
        if in_display:
            for i in range(len(line)):
                prot.add(i)
            idx = line.find('$$')
            if idx != -1:
                in_display = False
                for i in range(idx, min(idx + 2, len(line))):
                    prot.add(i)
            masks.append(prot)
            continue
        # not in fence/display: scan code spans, math, inline $
        i = 0
        n = len(line)
        in_inline = False
        while i < n:
            c = line[i]
            if c == '`':
                j = line.find('`', i + 1)
                if j == -1:
                    for k in range(i, n):
                        prot.add(k)
                    break
                for k in range(i, j + 1):
                    prot.add(k)
                i = j + 1
                continue
            if c == '$':
                if i + 1 < n and line[i + 1] == '$':
                    in_display = True
                    for k in range(i, i + 2):
                        prot.add(k)
                    i += 2
                    continue
                in_inline = not in_inline
                prot.add(i)
                i += 1
                continue
            if in_inline:
                prot.add(i)
            i += 1
        masks.append(prot)
    return masks


def wrap_line(line, prot):
    # Build output; wrap each raw glyph/arrow char not in prot.
    out = []
    for i, c in enumerate(line):
        if i in prot:
            out.append(c)
            continue
        if c in ALL:
            out.append('$' + ALL[c] + '$')
        else:
            out.append(c)
    return ''.join(out)


def process(path):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    masks = compute_protected(lines)
    changed = 0
    new_lines = []
    for line, prot in zip(lines, masks):
        # strip trailing newline for processing
        nl = ''
        if line.endswith('\n'):
            nl = '\n'
            line = line[:-1]
        new = wrap_line(line, prot)
        if new != line:
            changed += 1
        new_lines.append(new + nl)
    if changed:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(new_lines)
    return changed


if __name__ == '__main__':
    files = sys.argv[1:]
    total = 0
    for fp in files:
        c = process(fp)
        total += c
        print(f"  {os.path.basename(fp)}: wrapped glyphs on {c} lines")
    print(f"TOTAL changed lines: {total}")
