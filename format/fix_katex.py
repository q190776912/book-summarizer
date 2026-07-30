r"""Comprehensive KaTeX fix script — handles all known patterns from the
Chaos-Fractals-Noise book project.

Usage:
    python format/fix_katex.py <book_dir>               # fix all .md files
    python format/fix_katex.py <book_dir> --dry-run      # preview only

This script fixes the following patterns. (check_katex --fix is NOT used;
the cascade bug that motivated this script was actually in
_extract/fix_cn_files.py's fix_dollar_count function.)

Pattern 1 — Unclosed $ before Chinese/English punctuation
  Before:  ...$mu=\delta_{x_0},
           [blank line]
           $$...
  After:   ...$mu=\delta_{x_0}$，
           [blank line]
           $$...

Pattern 2 — $$ blocks wrapping $...$ inline math
  Before:  $$ text $formula$ more text $$
  After:   text $formula$ more text

Pattern 3 — $$ blocks wrapping ## headings
  Before:  $$ ## \S N.S 标题 $$
  After:   ## \S N.S 标题

Pattern 4 — Broken commands (spacing corruption from auto-fix scripts)
  \in t  ->  \int
  \in fty  ->  \infty
  \in f  ->  \inf
  \qquad[a-zA-Z]  ->  \qquad [a-zA-Z]
  \quad[a-zA-Z]  ->  \quad [a-zA-Z]
  \widetildeP  ->  \widetilde P

Pattern 5 — CD arrow direction/label errors
  @A\int A cannot work in KaTeX; use @V\int VV for down-arrow
  @VV\text{RN} A  ->  @VV\text{RN}V
  Unmatched $$ after \end{CD} removed

Pattern 6 — (removed, superseded by Pattern 9)

Pattern 7 — Blank lines inside $$...$$ blocks (removed)

Pattern 8 — $$4pt] -> \[4pt] (alignment parameter)

Pattern 9 — Fix brace escaping in math mode (3 sub-cases)
  (a) Group delimiters: _\{FP\} -> _{FP}, \frac\{1\}\{n\} -> \frac{1}{n}
  (b) Set notation: \{P^n f} -> \{P^n f\} (missing closing \)
  (c) Literal braces: \sqrt{1-x\}} kept as-is (NOT unescaped to }})
"""
import os, re, sys, glob


def count_bare_dollars(line: str) -> int:
    """Count bare $ tokens outside $$ blocks, ignoring $-escaped ones."""
    count = 0
    in_dd = False
    i = 0
    while i < len(line):
        if line[i] == '\\' and i + 1 < len(line):
            i += 2
            continue
        if line[i:i+2] == '$$':
            in_dd = not in_dd
            i += 2
            continue
        if line[i] == '$' and not in_dd:
            count += 1
        i += 1
    return count


def get_lines(fp: str):
    with open(fp, 'r', encoding='utf-8') as f:
        return f.readlines()


def put_lines(fp: str, lines):
    with open(fp, 'w', encoding='utf-8') as f:
        f.writelines(lines)


# --- Pattern-specific fixers ---

def fix_unclosed_dollars(lines: list) -> tuple:
    """Pattern 1: lines ending with $formula, followed by blank+$$."""
    changed = False
    i = 0
    while i < len(lines):
        stripped = lines[i].rstrip('\n\r')
        # Skip lines inside $$ blocks
        count = count_bare_dollars(stripped)
        if count > 0 and count % 2 == 1:
            # This line has an unclosed $. Check if next line(s) after blank is $$
            j = i + 1
            while j < len(lines) and lines[j].strip() == '':
                j += 1
            if j < len(lines) and lines[j].strip().startswith('$$'):
                # The unclosed $ will swallow the $$. Add closing $
                # Find the last $... segment that has no closing
                idx = len(stripped)
                # Common trailing punctuation
                for punct in ',;:，；：。、?？)）':
                    if stripped.rstrip().endswith(punct):
                        pos = stripped.rstrip().rfind(punct)
                        # Insert $ before the last punctuation
                        new_line = stripped[:pos] + '$' + stripped[pos:] + '\n'
                        lines[i] = new_line
                        changed = True
                        break
        i += 1
    return changed


def fix_wrapping_dollars(lines: list) -> tuple:
    """Pattern 2-3: remove $$ that wrap $...$ or ## headings."""
    changed = False
    i = 0
    while i < len(lines):
        if lines[i].strip() == '$$':
            open_idx = i
            j = i + 1
            while j < len(lines) and lines[j].strip() != '$$':
                j += 1
            if j < len(lines):
                close_idx = j
                inner = [l for l in lines[open_idx+1:close_idx] if l.strip()]
                inner_text = '\n'.join(l.rstrip('\n\r') for l in inner)

                has_inline = '$' in inner_text
                has_display = '\\begin{' in inner_text
                has_heading = bool(re.search(r'^##? ', inner_text, re.MULTILINE))
                has_chinese = bool(re.search(r'[\u4e00-\u9fff]', inner_text))
                is_math = bool(re.search(r'^\\[a-zA-Z]', inner_text))

                # Determine if this $$ should be removed
                should_remove = False
                if has_heading:
                    should_remove = True
                elif has_chinese and not has_display and (has_inline or not is_math):
                    should_remove = True
                elif has_inline and not has_display and not is_math:
                    should_remove = True

                if should_remove:
                    # Keep the inner content, remove the $$ wrappers
                    content_lines = lines[open_idx+1:close_idx]
                    # Dedent blockquote if needed
                    result = []
                    for cl in content_lines:
                        result.append(cl)
                    lines[open_idx:close_idx+1] = result
                    changed = True
                    i = open_idx + len(result)
                    continue
                i = close_idx + 1
            else:
                i += 1
        else:
            i += 1
    return changed


def fix_broken_commands(content: str) -> tuple:
    """Pattern 4: fix command-level spacing corruption."""
    original = content
    # Standard broken commands from auto-fix scripts
    fixes = [
        (r'\\in\s+t(?![a-zA-Z])', r'\\int'),
        (r'\\in\s+fty', r'\\infty'),
        (r'\\in\s+f(?![a-zA-Z])', r'\\inf'),
        (r'\\qquad\s*([a-zA-Z])', r'\\qquad \1'),
        (r'\\quad\s*([a-zA-Z])', r'\\quad \1'),
        (r'\\widetilde\s+P', r'\\widetilde P'),
        (r'\\frac(\d)(?=[a-zA-Z]\{)', r'\\frac{\1}'),
    ]
    for pattern, replacement in fixes:
        content = re.sub(pattern, replacement, content)
    return content != original, content


def fix_cd_blocks(lines: list) -> tuple:
    """Pattern 5: remove stray unmatched $$ after \\end{CD}."""
    import re
    changed = False
    i = 0
    while i < len(lines):
        if '\\begin{CD}' in lines[i]:
            # Find \end{CD}
            j = i + 1
            while j < len(lines) and '\\end{CD}' not in lines[j]:
                j += 1
            if j < len(lines):
                end_line = j
                # If the \end{CD} line has a closing $$ on it (e.g. \end{CD}$$)
                # that is not paired with an opening $$, remove the trailing $$
                m = re.match(r'(.*\\\\end\{CD\})\s*\$\$\s*$', lines[end_line])
                if m:
                    lines[end_line] = m.group(1) + '\n'
                    changed = True
                # Look for stray single $$ line immediately after \end{CD}
                if end_line + 1 < len(lines):
                    next_line = lines[end_line + 1].strip()
                    if next_line == '$$':
                        # Check if it forms a balanced pair later — if not, it's stray
                        k = end_line + 2
                        while k < len(lines) and lines[k].strip() != '$$':
                            k += 1
                        if k >= len(lines) or k == end_line + 2:
                            # No matching $$ found — remove the stray one
                            del lines[end_line + 1]
                            changed = True
                            continue
            i = end_line + 1 if j < len(lines) else j + 1
        else:
            i += 1
    return changed


def fix_escaped_braces_in_math(content: str) -> tuple:
    """Pattern 9: fix brace escaping in math mode (3 sub-cases).

    (a) \\_\\{FP\\} -> _{FP} (group delimiters after _/^/cmd)
    (b) \\{...} -> \\{...\\} (set notation missing closing \\)
    (c) do NOT unescape \\}\\} -> }} (literal braces like \\sqrt{1-x\\}})
    """
    original = content
    out = []
    i = 0
    # Use two flags to robustly track math mode:
    # in_dd: inside $$...$$ display math
    # in_single: inside $...$ inline math
    # Math is active when either is True.
    # $ inside $$ is treated as literal (not a toggle).
    in_dd = False
    in_single = False
    depth = 0
    # flag: True if the last depth-raising char was \{ (escaped open)
    # i.e., we are inside a \{...  group whose closing \} may be missing
    seen_esc_open = False

    def in_math():
        return in_dd or in_single

    ARG_CMDS = frozenset({
        'mathcal', 'operatorname', 'mathbf', 'mathrm', 'mathbb',
        'mathscr', 'mathsf', 'mathtt',
        'frac', 'binom', 'stackrel',
        'begin', 'end',
        'tilde', 'hat', 'dot', 'ddot', 'bar', 'vec',
        'overline', 'widetilde', 'widehat',
        'text', 'textnormal', 'textbf', 'textit',
        'boxed', 'cases', 'array', 'matrix',
    })
    _CMD_RE = re.compile(r'\\[a-zA-Z*]+$')

    while i < len(content):
        if content[i:i+2] == '$$':
            out.append('$$')
            in_dd = not in_dd
            if not in_dd:
                in_single = False  # leaving display math resets inline too
            depth = 0
            seen_esc_open = False
            i += 2
            continue
        if content[i] == '$' and not in_dd:
            out.append('$')
            in_single = not in_single
            depth = 0
            seen_esc_open = False
            i += 1
            continue

        if not in_math():
            out.append(content[i])
            i += 1
            continue

        # ---------- inside math mode ----------
        c = content[i]

        # --- escaped \{ or \} ---
        if c == '\\' and i + 1 < len(content):
            nxt = content[i + 1]

            if nxt == '{':
                before = ''.join(out[-20:]).rstrip()
                unescape = False
                if before.endswith('_') or before.endswith('^'):
                    unescape = True
                elif before.endswith('}'):
                    if depth <= 2:
                        unescape = True
                else:
                    m = _CMD_RE.search(before)
                    if m and m.group(0)[1:] in ARG_CMDS:
                        unescape = True

                if unescape:
                    out.append('{')
                    depth += 1
                else:
                    out.append('\\{')
                    seen_esc_open = True   # we are in \{... zone
                i += 2
                continue

            if nxt == '}':
                if depth > 0:
                    # Only unescape \} if NOT immediately followed by }
                    # (literal brace like \sqrt{1-x\}})
                    if i + 2 < len(content) and content[i + 2] == '}':
                        out.append('\\}')
                    else:
                        out.append('}')
                        depth -= 1
                else:
                    out.append('\\}')
                    seen_esc_open = False  # set notation properly closed
                i += 2
                continue

        # --- unescaped { ---
        if c == '{':
            depth += 1
            out.append(c)
            i += 1
            continue

        # --- unescaped } at depth 0: maybe missing \ from set notation ---
        if c == '}':
            if depth > 0:
                depth -= 1
                out.append(c)
            else:
                if seen_esc_open:
                    out.append('\\}')
                    seen_esc_open = False
                else:
                    out.append(c)
            i += 1
            continue

        # ---- regular character ----
        out.append(c)
        i += 1

    return ''.join(out) != original, ''.join(out)





def fix_blank_in_dollar(lines: list) -> tuple:
    """Pattern 7: remove blank lines inside $$...$$ blocks."""
    changed = False
    in_dd = False
    new_lines = []
    for line in lines:
        if line.strip() == '$$':
            in_dd = not in_dd
            new_lines.append(line)
        elif in_dd and line.strip() == '':
            changed = True
            continue
        else:
            new_lines.append(line)
    if changed:
        lines[:] = new_lines
    return changed


def fix_align_param(content: str) -> tuple:
    """Pattern 8: fix $$4pt] → \\[4pt]."""
    original = content
    content = re.sub(r'\$\$(\d+)pt\]', r'\\\\[\1pt]', content)
    return content != original, content


def fix_file(fp: str, dry_run: bool = False) -> int:
    """Apply all fixes to a single file. Returns count of changes made."""
    with open(fp, 'r', encoding='utf-8') as f:
        content = f.read()
    lines = content.splitlines(keepends=True)
    changes = 0

    # Pattern 1 — lines-based
    if fix_unclosed_dollars(lines):
        changes += 1
        content = ''.join(lines)

    # Pattern 2-3 — lines-based
    if fix_wrapping_dollars(lines):
        changes += 1
        content = ''.join(lines)

    # Pattern 4 — content-based; re-sync lines after
    changed, content = fix_broken_commands(content)
    if changed:
        changes += 1
        lines = content.splitlines(keepends=True)

    # Pattern 5 — lines-based; no content-sync needed since we write once at end
    if fix_cd_blocks(lines):
        changes += 1
        content = ''.join(lines)

    # Pattern 9 — content-based (replaces old Pattern 6)
    changed, content = fix_escaped_braces_in_math(content)
    if changed:
        changes += 1
        lines = content.splitlines(keepends=True)

    # Pattern 7 — lines-based
    if fix_blank_in_dollar(lines):
        changes += 1
        content = ''.join(lines)

    # Pattern 8 — content-based
    changed, content = fix_align_param(content)
    if changed:
        changes += 1

    # Write once at end
    if changes and not dry_run:
        with open(fp, 'w', encoding='utf-8') as f:
            f.write(content)

    return changes


def main():
    dry_run = '--dry-run' in sys.argv
    # Determine target directory
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    if args:
        target = args[0]
    else:
        target = os.getcwd()

    if os.path.isdir(target):
        files = sorted(glob.glob(os.path.join(target, '*.md')))
    elif os.path.isfile(target):
        files = [target]
    else:
        print(f'Error: {target} is not a file or directory')
        sys.exit(1)

    total_changes = 0
    for fp in files:
        fname = os.path.basename(fp)
        n = fix_file(fp, dry_run=dry_run)
        if n:
            status = f'{n} fix(es)'
        else:
            status = 'OK'
        print(f'{fname:50s} {status}')
        total_changes += n

    mode = 'Dry-run' if dry_run else 'Fixed'
    print(f'\n{mode} {len(files)} files, {total_changes} total changes.')


if __name__ == '__main__':
    main()
