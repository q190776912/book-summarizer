#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fix display math that sits *inside a block quote* but is missing the `> ` prefix
on its `$$` fences and content lines.

Two problems this handles:
  1. Multi-line block inside a block quote written as:
         > **证明**：...于是
         $$
         (aI_n-[b_{ij}])...=0,
         $$
     should become (every line of the display math prefixed with `> `):
         > **证明**：...于是
         >
         > $$
         > (aI_n-[b_{ij}])...=0,
         > $$

  2. Single-line block quote display math written as:
         > $$x\longrightarrow y$$
     should be split into three prefixed lines.

Rule for deciding "inside a block quote": the most recent non-empty, non-display-math
line before the `$$` block begins with `>`.  In that case the whole display block is
prefixed with `> `.  Top-level display math (preceded by a non-`>` line) is left untouched.
"""
import sys
import re

SINGLE_RE = re.compile(r'^(?P<prefix>>\s*)?\$\$(?P<content>.+?)\$\$\s*$')
FENCE_RE = re.compile(r'^(?P<lead>\s*>+\s*)?\$\$\s*$')


def _bq_prefix_of_line(line):
    """Return the `> ` prefix (including any nesting) if line starts with blockquote, else ''."""
    m = re.match(r'^(\s*>+\s*)', line)
    return m.group(1) if m else ''


def _preceding_is_bq(out):
    for k in range(len(out) - 1, -1, -1):
        if out[k].strip() == '':
            continue
        return _bq_prefix_of_line(out[k]) != ''
    return False


def fix_file(path, dry_run=False):
    with open(path, encoding='utf-8') as f:
        lines = f.read().split('\n')
    out = []
    i = 0
    n = len(lines)
    changed = 0
    while i < n:
        line = lines[i]

        # --- Case 2: single-line block quote display math `> $$...$$` ---
        ms = SINGLE_RE.match(line)
        if ms and ms.group('content').strip():
            content = ms.group('content').strip()
            prefix = ms.group('prefix') or ('> ' if _preceding_is_bq(out) else '')
            out.append(prefix + '$$')
            out.append(prefix + content)
            out.append(prefix + '$$')
            changed += 1
            i += 1
            continue

        # --- Case 1: multi-line display math block (a bare `$$` fence) ---
        mo = FENCE_RE.match(line)
        if mo:
            lead = mo.group('lead') or ''
            if lead.strip():
                prefix = lead
            elif _preceding_is_bq(out):
                prefix = '> '
            else:
                prefix = ''
            out.append(prefix + '$$')
            i += 1
            while i < n:
                cl = lines[i]
                if FENCE_RE.match(cl):
                    out.append(prefix + '$$')
                    i += 1
                    changed += 1
                    break
                cs = cl.strip()
                if cs == '':
                    out.append('' if prefix == '' else prefix.rstrip())
                else:
                    stripped = re.sub(r'^\s*>+\s*', '', cl)
                    out.append(prefix + stripped)
                i += 1
            continue

        out.append(line)
        i += 1

    if dry_run:
        print(f"{path}: {changed} block(s) would change")
        return changed
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(out))
    print(f"{path}: {changed} display-math block(s) fixed")
    return changed


def main():
    dry = '--dry' in sys.argv
    for p in sys.argv[1:]:
        if p == '--dry':
            continue
        fix_file(p, dry_run=dry)


if __name__ == '__main__':
    main()
