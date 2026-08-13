#!/usr/bin/env python3
"""fmt_extras.py — display-math post-processing helpers (production stage).

Subcommands (idempotent unless noted):

  dedent    <file.md> [--fix] | --dir <dir> [--fix]
            Strip list-indentation from non-blockquote `$$` blocks so they
            render as top-level display math instead of a code block.

  normalize <file.md> [--fix] | --dir <dir> [--fix]
            Rebuild every `$$ ... $$` block cleanly (plain or blockquote):
            dedent + blank lines + restore `>` on blockquote closers.

Blockquote continuity / nested-blockquote flattening / intra-block bare `$$`
prefixing are handled by verify (fixers G / M via `verify --fix`), not here.
Single-line `$$ ... $$` splitting is also handled by `verify --fix` (fixer C,
verify/format_verify/script/fix_katex.py).  This tool therefore only does
display-math *shape* post-processing that verify does not auto-fix.
"""
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


import sys, os, glob, argparse


# --------------------------------------------------------------------------
# dedent_display_math
# --------------------------------------------------------------------------
def dedent(lines):
    out = list(lines)
    changed = False
    in_block = False
    stack = []  # indices of indented open `$$` lines
    for idx, line in enumerate(out):
        s = line.strip()
        if s != '$$':
            continue
        is_bq = line.lstrip().startswith('>')
        lead = len(line) - len(line.lstrip(' '))
        if not in_block:
            in_block = True
            if not is_bq and lead > 0:
                stack.append(idx)
        else:
            in_block = False
            if stack:
                oi = stack.pop()
                g = len(out[oi]) - len(out[oi].lstrip(' '))
                if g > 0:
                    for j in range(oi, idx + 1):
                        if out[j].strip() == '':
                            continue
                        ls = len(out[j]) - len(out[j].lstrip(' '))
                        remove = min(g, ls)
                        out[j] = out[j][remove:]
                    changed = True
    return out, changed


# --------------------------------------------------------------------------
# normalize_display_math
# --------------------------------------------------------------------------
def normalize(lines):
    out = list(lines)
    res = []
    i = 0
    n = len(out)
    while i < n:
        line = out[i]
        s = line.strip()
        if s == '$$':
            is_bq = line.lstrip().startswith('>')
            # collect interior lines until the closing $$ (exclusive)
            j = i + 1
            interior = []
            while j < n and out[j].strip() != '$$':
                interior.append(out[j])
                j += 1
            close_idx = j  # index of the closing $$ line
            formulas = []
            for bl in interior:
                st = bl.lstrip()
                if st.startswith('>'):
                    st = st[1:].lstrip()
                formulas.append(st.rstrip('\n'))
            # blank line BEFORE the block
            if res:
                pv = res[-1]
                if pv.strip() != '':
                    if pv.lstrip().startswith('>'):
                        if pv.strip() != '>':
                            res.append('> \n')
                    else:
                        res.append('\n')
            # emit the clean block
            if is_bq:
                res.append('> $$\n')
                for f in formulas:
                    if f.strip() != '':
                        res.append('> ' + f + '\n')
                res.append('> $$\n')
            else:
                res.append('$$\n')
                for f in formulas:
                    if f.strip() != '':
                        res.append(f + '\n')
                res.append('$$\n')
            # blank line AFTER the block
            nxt = out[close_idx + 1] if close_idx + 1 < n else ''
            if nxt.strip() != '':
                if nxt.lstrip().startswith('>'):
                    res.append('> \n')
                else:
                    res.append('\n')
            i = close_idx + 1
        else:
            res.append(line)
            i += 1
    return res


# --------------------------------------------------------------------------
# file drivers + CLI
# --------------------------------------------------------------------------
def _process_file_dedent(path, fix):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    new, changed = dedent(lines)
    if fix and changed:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(new)
        print(f"[DEDENT] rewrote {os.path.basename(path)} (dedented)")
    else:
        print(f"[DEDENT] {os.path.basename(path)}: "
              f"{'WOULD dedent (run with --fix to apply)' if changed else 'nothing to dedent'}")
    return changed


def _process_file_normalize(path, fix):
    with open(path, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    new = normalize(lines)
    changed = new != lines
    if fix and changed:
        with open(path, 'w', encoding='utf-8') as f:
            f.writelines(new)
        print(f"[NORM] rewrote {os.path.basename(path)} (rebuilt $$ blocks)")
    else:
        print(f"[NORM] {os.path.basename(path)}: "
              f"{'WOULD rebuild (run with --fix to apply)' if changed else 'nothing to rebuild'}")
    return changed


def main():
    ap = argparse.ArgumentParser(
        description="Display-math post-processing helpers.")
    sub = ap.add_subparsers(dest='cmd', required=True)

    p_d = sub.add_parser('dedent', help='dedent non-blockquote $$ blocks')
    p_d.add_argument('path', nargs='?')
    p_d.add_argument('--dir', help='process all *.md in this dir')
    p_d.add_argument('--fix', action='store_true')

    p_n = sub.add_parser('normalize', help='rebuild every $$ block cleanly')
    p_n.add_argument('path', nargs='?')
    p_n.add_argument('--dir', help='process all *.md in this dir')
    p_n.add_argument('--fix', action='store_true')

    args = ap.parse_args()

    if args.cmd == 'dedent':
        if args.dir:
            for fp in sorted(glob.glob(os.path.join(args.dir, '*.md'))):
                _process_file_dedent(fp, args.fix)
        elif args.path:
            _process_file_dedent(args.path, args.fix)
        else:
            ap.error('dedent needs <path> or --dir')
    elif args.cmd == 'normalize':
        if args.dir:
            for fp in sorted(glob.glob(os.path.join(args.dir, '*.md'))):
                _process_file_normalize(fp, args.fix)
        elif args.path:
            _process_file_normalize(args.path, args.fix)
        else:
            ap.error('normalize needs <path> or --dir')


if __name__ == '__main__':
    main()
