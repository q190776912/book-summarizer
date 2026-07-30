r"""KaTeX validation/fix script for book-summarizer skill.
Usage:
    python check_katex.py <markdown_file>             # validate only (exit 1 on errors)
    python check_katex.py <markdown_file> --fix       # validate + auto-fix fixable errors
    python check_katex.py --fix <markdown_file>       # same (--fix can come first)
    python check_katex.py --dir <directory> [--fix]   # batch mode: check/fix all .md files

WARNING on --fix with Chinese-language files:
    --fix auto-inserts $ delimiters to fix "naked LaTeX command" warnings.
    On Chinese .md files this can cause CASCADING DAMAGE:
      - It may insert $ inside $$...$$ display math blocks
      - This produces "Can't use function '$' in math mode" errors
      - Each re-run of --fix adds MORE damage (observed: 1 -> 27 errors)
    Use format/fix_katex.py instead for Chinese files — it handles all
    known patterns without the cascading risk.


Two layers of checking:

  [Heuristic layer — always runs, regex-only]
  Checks for:
    1. Escaped display math delimiter (\$\$) — renders as literal $$, not KaTeX.
    2. Single-line display math ($$formula$$ / > $$formula$$) — MUST split $$ onto separate lines.
    3. Missing blank lines before opening $$ display math blocks (plain and > quoted).
    4. Unbalanced inline $...$ (odd number of unescaped $ outside display math).
    5. Known KaTeX-unsupported macros that cause cascade render failure.
    6. Over-indented blockquote display math (`>    $$` / `>    <formula>`): an
       extra indent makes CommonMark treat `$$` as `   $$` content, which KaTeX
       does NOT recognize as a math fence — the formula renders as literal text.
       MUST be single-space (`> $$` / `> <formula>`).
    7. 嵌套列表错位：顶层条目 `(n)` 紧接 `- (i)` 子项 bullet 之后且缺空行，
       渲染会将 `(n)` 误与子项并列；`--fix` 自动在 `(n)` 前补空行。
    8. 结构性条目被吞进块引用（`> **定义/定理/...**`）：结构性条目必须独立成行
       （顶层），`--fix` 自动 unwrap（去掉 `>` 前缀）。
  The naked-LaTeX-command / raw-arrow heuristics strip inline $...$ BEFORE
  display-math detection (protecting standalone `$$` delimiters), so adjacent
  inline spans like  $\mathrm{RP}$$^{24}$  no longer corrupt the multi-line
  display-math parity tracker.
  --fix can auto-correct errors 1-3, 6; errors 4-5 still reported.

  [Real-render layer — runs if node + katex are available]
  Shells out to katex_validate.js (same dir) which renders EVERY display/inline
  math block with KaTeX and reports genuine LaTeX syntax errors (unbalanced
  braces, unsupported commands, bad \\\\ usage, …) that the heuristic CANNOT see.
  If node / katex is missing, it emits a visible WARNING (heuristic-only fallback)
  instead of silently passing — so a missing toolchain is never mistaken for "OK".

NOTE: --fix only fixes the FORMAT errors (1-3). It cannot fix genuine LaTeX
syntax errors found by the real-render layer — those must be hand-edited.
"""
import sys
import os
import re
import glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from format.katex_heuristics import (
    BAD_MACRO_PATTERNS,
    find_raw_arrow_errors,
    find_naked_command_errors,
    find_swallowed_prefix_errors,
    _fence_looks_like_math,
)
from format.katex_render import run_render_check


def process_file(path, fix):
    """Process a single markdown file. Returns True if OK (no errors after fix)."""
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    errors = []
    fixable = []
    fix_single = []
    fixable_nested = []  # line indices for nested blockquote display math (> > $$)
    in_math = False
    in_bq_math = False
    inline_dollar_count = 0

    # --- Pass 0: detect escaped display math \$\$ (renders as literal $$, not KaTeX) ---
    for i, line in enumerate(lines):
        s = line.strip()
        if s == r'\$\$':
            errors.append(f'line {i + 1}: escaped display math delimiter ' + r'\$\$' + ' — replace with $$')
            fix_single.append((i, False, ''))
        elif s == r'> \$\$':
            errors.append(f'line {i + 1}: escaped blockquote display math delimiter ' + r'\$\$' + ' — replace with $$')
            fix_single.append((i, True, ''))

    # --- Pass 0b: detect nested blockquote display math (> > $$) ---
    # Display math inside nested blockquotes is not recognized by KaTeX
    # because the extra > prefix prevents $$ from being parsed as a math delimiter.
    # Must be flattened to single-level > $$ / > formula / > $$.
    for i, line in enumerate(lines):
        s = line.strip()
        # Match "> > $$" or ">  > $$" etc. — any line with > > before $$
        if re.match(r'^>\s+>', s) and '$$' in s:
            errors.append(f'line {i + 1}: nested blockquote display math (> > $$) — flatten to single-level > $$')
            fixable_nested.append(i)

    # --- Pass 1: detect single-line display math ($$...$$ on one line) ---
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('> $$') and s.endswith('$$') and len(s) > 6:
            formula = s[4:-2].strip()
            fix_single.append((i, True, formula))
            errors.append(f'line {i + 1}: single-line blockquote display math — split > $$ onto separate lines')
        elif s.startswith('$$') and s.endswith('$$') and len(s) > 4 and not s.startswith('>'):
            formula = s[2:-2].strip()
            fix_single.append((i, False, formula))
            errors.append(f'line {i + 1}: single-line display math — split $$ onto separate lines')

    # --- Pass 1f: $$ attached to formula content on ONE side only ---
    # e.g. "$$\begin{aligned}" (open-attached) or "\end{aligned}$$" (close-attached).
    # Markdown renderers fail to recognize these as display math blocks.
    fix_attached = []  # (idx, 'open'|'close', is_bq, rest)
    for i, line in enumerate(lines):
        s = line.strip()
        is_bq = s.startswith('> ')
        core = s[2:].strip() if is_bq else s
        if core.startswith('$$') and not core.endswith('$$') and len(core) > 2:
            fix_attached.append((i, 'open', is_bq, core[2:].strip()))
            errors.append(f'line {i + 1}: opening $$ attached to formula content — split onto its own line')
        elif core.endswith('$$') and not core.startswith('$$') and len(core) > 2 and '$$' not in core[:-2]:
            fix_attached.append((i, 'close', is_bq, core[:-2].strip()))
            errors.append(f'line {i + 1}: closing $$ attached to formula content — split onto its own line')

    # --- Pass 1g: <div>/​</div> blocks need surrounding blank lines ---
    # Without a blank line after </div>, following markdown (including $$ math)
    # is swallowed into the HTML block and never rendered.
    fix_div = []  # (idx, 'before'|'after')
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith('<div') and i > 0 and lines[i - 1].strip() != '':
            fix_div.append((i, 'before'))
            errors.append(f'line {i + 1}: missing blank line before <div> block')
        if s == '</div>' and i + 1 < len(lines) and lines[i + 1].strip() != '':
            fix_div.append((i, 'after'))
            errors.append(f'line {i + 1}: missing blank line after </div> — following content swallowed into HTML block')

    # --- Pass 1h: over-indented blockquote display math (`>    $$`) ---
    # Blockquote display math MUST use a single space (`> $$`); an extra indent
    # (`>    $$`, i.e. `>` + 2+ spaces) becomes `   $$` content under CommonMark,
    # which KaTeX does NOT recognize as a math fence -> the formula renders as
    # literal text. Detect the whole display block and auto-fix to single-space.
    fix_bq_indent = []  # (start_idx, end_idx)
    for i, line in enumerate(lines):
        if re.match(r'^\s*>\s{2,}\$\$', line):
            if line.count('$$') >= 2:
                fix_bq_indent.append((i, i))
            else:
                j = i + 1
                while j < len(lines) and not re.match(r'^\s*>\s{2,}\$\$', lines[j]):
                    j += 1
                end = j if j < len(lines) else len(lines) - 1
                fix_bq_indent.append((i, end))
            errors.append(f'line {i + 1}: over-indented blockquote display math '
                           f'(`>    $$`) — normalize to `> $$`')

    for i, line in enumerate(lines):
        s = line.strip()
        if s == '$$':
            if i > 0 and i < len(lines) - 1:
                next_s = lines[i + 1].strip()
                if not in_math:
                    if next_s != '' and next_s != '$$':
                        prev = lines[i - 1].strip()
                        if prev != '' and not prev.startswith('>'):
                            fixable.append((i, 'plain'))
                            errors.append(f'line {i + 1}: missing blank line before opening $$')
                    in_math = True
                else:
                    in_math = False
            continue
        if s.startswith('> $$'):
            if not in_bq_math:
                in_bq_math = True
                if i > 0:
                    prev = lines[i - 1].strip()
                    if prev != '>' and prev != '':
                        fixable.append((i, 'bq'))
                        errors.append(f'line {i + 1}: missing empty > line before > $$')
            else:
                in_bq_math = False
            continue

        if in_math or in_bq_math:
            continue

        stripped = re.sub(r'\\\$', '', line)
        inline_dollar_count += stripped.count('$')

        for pat, msg in BAD_MACRO_PATTERNS:
            if re.search(pat, line):
                errors.append(f'line {i + 1}: unsupported KaTeX macro — {msg}')

    if inline_dollar_count % 2 != 0:
        errors.append(f'inline $ count is odd ({inline_dollar_count}) — an unpaired $ breaks all following math')

    # --- Pass 1b: detect formulas/diagrams wrapped in code fences (``` ... ```) ---
    # Anti-pattern: commutative diagrams / formulas rendered as ASCII/Unicode
    # art inside a ``` code fence. These MUST be real KaTeX: $$ ... $$ (use
    # \begin{CD}...\end{CD} for commutative diagrams). Code fences are for code only.
    _in_fence = False
    _fence_start = -1
    _fence_buf = []
    for _i, _ln in enumerate(lines):
        _st = _ln.strip()
        if _st.startswith('```'):
            if not _in_fence:
                _in_fence = True
                _fence_start = _i
                _fence_buf = []
            else:
                _content = '\n'.join(_fence_buf)
                if _fence_looks_like_math(_content):
                    errors.append(
                        f'line {_fence_start + 1}: formula/diagram wrapped in a '
                        f'code fence (```) — MUST use $$ ... $$ (commutative '
                        f'diagrams: \\begin{{CD}}...\\end{{CD}}); code fences are '
                        f'for code only, never for math')
                _in_fence = False
                _fence_start = -1
        elif _in_fence:
            _fence_buf.append(_ln)

    # --- Pass 1c: raw Unicode math arrows outside math mode (rule #8) ---
    errors.extend(find_raw_arrow_errors(lines))

    # --- Pass 1d: naked LaTeX commands outside math mode ---
    errors.extend(find_naked_command_errors(lines))

    # --- Pass 1e: `$` swallowed a blockquote/list/number prefix ---
    errors.extend(find_swallowed_prefix_errors(lines))

    # --- Pass 1i: equation number annotation outside $$ block (rule #10) ---
    # Detect lines starting with （式 (N.M)） that follow a $$ closing line.
    # These should use \tag{N.M} inside the formula block instead.
    _eq_ann_re = re.compile(r'^（式\s*\(\d+\.\d+\)）')
    for i, line in enumerate(lines):
        s = line.strip()
        if _eq_ann_re.match(s):
            # Check if preceded by $$ (possibly with a blank line between)
            prev_close = None
            if i >= 1 and lines[i - 1].strip().endswith('$$'):
                prev_close = i - 1
            elif i >= 2 and lines[i - 1].strip() == '' and lines[i - 2].strip().endswith('$$'):
                prev_close = i - 2
            if prev_close is not None:
                errors.append(
                    f'line {i + 1}: 公式编号标注（式 (...)）在 $$ 块外部 — '
                    f'应改用 \\tag{{N.M}} 写入公式行末尾')

    # --- Pass 1j: blockquote-escaped display math (`$$` after `>` without `> $$`) ---
    # When a `$$` opens a display math block after a `>` line but WITHOUT the `>`
    # prefix, it escapes the blockquote. The entire display math block (opening $$,
    # content lines, closing $$) must be prefixed with `> ` to stay inside the quote.
    # Without the fix, the formula renders outside the blockquote, breaking visual
    # grouping (e.g. an example's displayed formula appears after the quote closes).
    fix_bq_escape = []  # list of (start_idx, end_idx)
    for i, line in enumerate(lines):
        s = line.strip()
        if s == '$$' and not line.lstrip().startswith('>'):
            # Check if previous non-blank line starts with > or is > $$
            prev_nonblank = None
            for j in range(i - 1, -1, -1):
                if lines[j].strip():
                    prev_nonblank = j
                    break
            if prev_nonblank is not None and lines[prev_nonblank].strip().startswith('> '):
                # Found escaped display math — locate the full block
                end = i + 1
                while end < len(lines) and lines[end].strip() != '$$':
                    end += 1
                if end < len(lines):
                    fix_bq_escape.append((i, end))
                    errors.append(
                        f'line {i + 1}: blockquote-escaped display math — '
                        f'`$$` after blockquote line lacks `> $$` prefix '
                        f'(entire display math block must stay inside the quote)')

    # --- Pass 2a: 嵌套列表错位（顶层条目紧接子项 bullet 之后，缺空行） ---
    # 当条目含子项（如 `- (i)` / `- (ii)` / `- (iii)`）时，下一个同级顶层条目
    # （如 `(2)`）必须与 `(1)` 并列；若子项列表末尾与 `(2)` 之间无空行，渲染器
    # 会把 `(2)` 误判为子项的并列项。自动修复：在 `(2)` 前插一个空行。
    fix_struct = []  # list of ('list_gap', idx) | ('strip_bq', idx)
    _bullet_re = re.compile(r'^\s*-\s*[\(（][^\)）]+[\)）]')
    _top_item_re = re.compile(r'^[\(（]\d+[\)）]')
    for i, line in enumerate(lines):
        if _bullet_re.match(line):
            j = i + 1
            while j < len(lines) and lines[j].strip() == '':
                j += 1
            if j < len(lines) and _top_item_re.match(lines[j]) and not lines[j].startswith(' '):
                has_blank = any(lines[k].strip() == '' for k in range(i + 1, j))
                if not has_blank:
                    errors.append(
                        f'line {j + 1}: 嵌套列表错位 — 顶层条目 {lines[j].strip()} '
                        f'紧接子项之后缺少空行，将误与子项（而非 (1)）并列；需补空行')
                    fix_struct.append(('list_gap', j))

    # --- Pass 2b: 结构性条目被吞进块引用（> **定义/定理/...） ---
    # 结构性条目（定义/定理/引理/推论/命题/断言/公理）必须独立成行（顶层），
    # 绝不能被 > 包裹。若出现在块引用内，自动 unwrap（去掉 > 前缀）。
    _struct_in_bq_re = re.compile(
        r'^>\s+\*\*(?:定义|定理|引理|推论|命题|断言|公理'
        r'|Definition|Theorem|Lemma|Corollary|Proposition|Axiom)\b')
    for i, line in enumerate(lines):
        if _struct_in_bq_re.match(line):
            errors.append(
                f'line {i + 1}: 结构性条目不应进入块引用（>），应独立成行顶层')
            fix_struct.append(('strip_bq', i))

    # -- Apply fixes (bottom-up so indices stay valid) --
    if fix:
        operations = []
        for fi, is_bq, formula in fix_single:
            # Empty formula means escaped delimiter (\$\$ → $$)
            if formula == '':
                operations.append((fi, -1, ('escaped_delim', is_bq)))
            else:
                operations.append((fi, 0, ('single', is_bq, formula)))
        for fi, kind in fixable:
            operations.append((fi, 1, ('insert', kind)))
        for fi in fixable_nested:
            operations.append((fi, 0, ('nested',)))
        for fi, side, is_bq, rest in fix_attached:
            operations.append((fi, 0, ('attached', side, is_bq, rest)))
        for fi, where in fix_div:
            operations.append((fi, 2, ('div', where)))
        for fi, fi_end in fix_bq_indent:
            operations.append((fi, 0, ('bqindent', fi_end)))
        for fi, end in fix_bq_escape:
            operations.append((fi, 0, ('bq_escape', end)))
        operations.sort(key=lambda x: (-x[0], x[1]))

        for _fi, _priority, op in operations:
            if op[0] == 'escaped_delim':
                fi, is_bq = _fi, op[1]
                old = lines[fi]
                lines[fi] = old.replace(r'\$\$', '$$')
            elif op[0] == 'single':
                fi, is_bq, formula = _fi, op[1], op[2]
                # If formula was from \$\$...\$\$, strip the backslashes first
                formula = formula.replace(r'\$', '$')
                prefix = '> ' if is_bq else ''
                if fi > 0 and lines[fi - 1].strip() not in ('', '>', '$$', '> $$'):
                    lines.insert(fi, prefix + '\n')
                    fi += 1
                new_lines = [prefix + '$$\n', prefix + formula + '\n', prefix + '$$\n']
                lines[fi:fi + 1] = new_lines
            elif op[0] == 'insert':
                fi, kind = _fi, op[1]
                if kind == 'plain':
                    lines.insert(fi, '\n')
                elif kind == 'bq':
                    lines.insert(fi, '>\n')
            elif op[0] == 'attached':
                fi, side, is_bq, rest = _fi, op[1], op[2], op[3]
                prefix = '> ' if is_bq else ''
                if side == 'open':
                    new_lines = [prefix + '$$\n', prefix + rest + '\n']
                    # blank line before opening $$ if needed
                    if fi > 0 and lines[fi - 1].strip() not in ('', '>', '$$', '> $$'):
                        new_lines.insert(0, (prefix.strip() + '\n') if is_bq else '\n')
                else:  # close
                    new_lines = [prefix + rest + '\n', prefix + '$$\n']
                lines[fi:fi + 1] = new_lines
            elif op[0] == 'div':
                fi, where = _fi, op[1]
                if where == 'before':
                    lines.insert(fi, '\n')
                else:  # after
                    lines.insert(fi + 1, '\n')
            elif op[0] == 'nested':
                fi = _fi
                # Flatten nested blockquote display math (> > $$ → > $$)
                # Fix this line and the following formula content/closing lines
                old = lines[fi]
                # Strip one level of blockquote from all lines of this block
                # Opening: > > $$ → > $$
                lines[fi] = old.replace('> > ', '> ', 1)
                # Also fix content/closing lines if they are still nested
                j = fi + 1
                while j < len(lines):
                    l = lines[j]
                    ls = l.strip()
                    if ls.startswith('> > ') or ls == '> >':
                        lines[j] = l.replace('> > ', '> ', 1)
                        j += 1
                    elif ls == '> > $$':
                        lines[j] = l.replace('> > ', '> ', 1)
                        j += 1
                        break
                    elif ls == '> > $$"':
                        lines[j] = l.replace('> > $$"', '> $$')
                        j += 1
                        break
                    else:
                        break
            elif op[0] == 'bqindent':
                fi, fi_end = _fi, op[1]
                # Normalize over-indented blockquote display math to single-space:
                #   `>    $$`  -> `> $$`   and   `>    <formula>` -> `> <formula>`
                # for every `>`-prefixed line in [fi, fi_end].
                for k in range(fi, fi_end + 1):
                    if lines[k].lstrip().startswith('>'):
                        lines[k] = re.sub(r'^(\s*>)\s{2,}', r'\1 ', lines[k], count=1)
            elif op[0] == 'bq_escape':
                fi, end = _fi, op[1]
                # Prepend `> ` to every line of the escaped display math block
                # so it stays inside the blockquote.
                for k in range(fi, end + 1):
                    if not lines[k].lstrip().startswith('>'):
                        lines[k] = '> ' + lines[k]

        # --- 结构性修复（Pass 2）：在其它修复之后、写出之前，自底向上重扫并修正 ---
        # 单独成趟，以避免与其它修复的索引位移相互干扰（保证幂等）。
        struct_fixed = 0
        # Pass 2b：去掉结构性条目的 > 前缀（不位移索引）
        for i in range(len(lines) - 1, -1, -1):
            if _struct_in_bq_re.match(lines[i]):
                l = lines[i]
                if l.startswith('> '):
                    lines[i] = l[2:]
                elif l == '>':
                    lines[i] = ''
                struct_fixed += 1
        # Pass 2a：在错位顶层 (N) 前补空行（自底向上，单次扫描即幂等）
        i = len(lines) - 1
        while i >= 0:
            if _bullet_re.match(lines[i]):
                j = i + 1
                while j < len(lines) and lines[j].strip() == '':
                    j += 1
                if j < len(lines) and _top_item_re.match(lines[j]) and not lines[j].startswith(' '):
                    has_blank = any(lines[k].strip() == '' for k in range(i + 1, j))
                    if not has_blank:
                        lines.insert(j, '\n')
                        struct_fixed += 1
            i -= 1

        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(lines)
        total = (len(fix_single) + len(fixable) + len(fixable_nested) +
                len(fix_attached) + len(fix_div) + len(fix_bq_indent) +
                len(fix_bq_escape) + struct_fixed)
        print(f"[FIX] Applied {total} fix(es) to {path}")

    # -- Real KaTeX render check --
    render_errs = run_render_check(path)
    if render_errs:
        errors.extend(render_errs)

    # -- Report --
    if errors:
        fixable_descs = set()
        if fix:
            for err in errors:
                if ('missing blank line' in err or 'missing empty > line' in err or
                        'single-line' in err or 'escaped' in err or
                        'nested blockquote' in err or 'attached to formula content' in err or
                        'after </div>' in err or 'over-indented' in err or
                        '嵌套列表错位' in err or '结构性条目不应进入块引用' in err):
                    fixable_descs.add(err)
        unfixed = [e for e in errors if e not in fixable_descs]
        if unfixed or not fix:
            print('KATEX ERRORS:')
            for e in (unfixed if fix else errors):
                try:
                    print(' ', e)
                except UnicodeEncodeError:
                    print(' ', e.encode('ascii', errors='replace').decode('ascii'))
            return False
        else:
            print('KATEX CHECK: OK (all fixable errors auto-corrected)')
            return True
    else:
        print('KATEX CHECK: OK')
        return True


def main():
    fix = '--fix' in sys.argv
    args = [a for a in sys.argv[1:] if a != '--fix']

    if not args:
        print("Usage: python check_katex.py <markdown_file> [--fix]")
        print("       python check_katex.py --dir <directory> [--fix]")
        sys.exit(1)

    if args[0] == '--dir':
        if len(args) < 2:
            print("ERROR: --dir requires a directory path")
            sys.exit(2)
        directory = args[1]
        pattern = os.path.join(directory, '*.md')
        md_files = sorted(glob.glob(pattern))
        if not md_files:
            print(f"No .md files found in {directory}")
            sys.exit(0)
        all_ok = True
        for md_file in md_files:
            print(f"\n--- {os.path.basename(md_file)} ---")
            ok = process_file(md_file, fix)
            if not ok:
                all_ok = False
        sys.exit(0 if all_ok else 1)
    else:
        path = args[0]
        ok = process_file(path, fix)
        sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
