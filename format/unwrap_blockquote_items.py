#!/usr/bin/env python3
"""
unwrap_blockquote_items.py -- Fix a formatting defect where standalone lemma /
corollary / theorem / proposition / definition STATEMENT headings got swallowed
into a preceding proof blockquote by fmt_proofs.py (which merges consecutive
'>' lines).

Per the book-summarizer convention, 引理/推论/定理/命题/定义 are TOP-LEVEL items;
only proof sketches ("证明/Proof") belong inside '>'. This script:
  1. Unwraps a '> **Lemma/Corollary/Theorem/...**' heading line to top level
     (a proof line containing 证明/Proof is left untouched).
  2. Normalizes empty-quote separators ('> ') that end up between two top-level
     blocks into bare blanks (the only legitimate inter-block separator per the
     verifier's G-layer rule), while keeping '> ' lines that are genuinely
     inside a still-open blockquote.

Idempotent: re-running on already-fixed files is a no-op.
"""

import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir)))

import re, os, glob

HEAD_RE = re.compile(
    r'^> \*\*(定理|命题|定义|引理|推论|断言|公理|Theorem|Proposition|Definition|Lemma|Corollary|Axiom)'
)

def is_unwrap_target(line: str) -> bool:
    # Any bold structural-label heading inside a blockquote must be top-level
    # (verifier H-layer), even when it is a proof heading like
    # `**定理 4.10 证明概要**` / `**引理证明**` / `**定理 4.2 证明收尾**`.
    # Lines such as `> **证明思路 (Proof sketch)**` have no structural label and
    # are left untouched (they are genuine proof sketches).
    return bool(HEAD_RE.match(line))

def process(text: str) -> str:
    lines = text.split('\n')
    unwrapped = set()
    out = []
    for i, line in enumerate(lines):
        if is_unwrap_target(line):
            out.append(line[2:])          # strip leading '> '
            unwrapped.add(i)
        else:
            out.append(line)
    n = len(out)
    res = list(out)
    for i in range(n):
        if out[i].rstrip() == '>' and (i in unwrapped or (i - 1) in unwrapped or (i + 1) in unwrapped):
            prev_is_q = (i > 0) and out[i - 1].startswith('>')
            nxt_is_q = (i < n - 1) and out[i + 1].startswith('>')
            if not (prev_is_q and nxt_is_q):
                res[i] = ''
    return '\n'.join(res)

def main():
    base = r'D:/study/book/basic-algebraic-geometry-1'
    files = sorted(glob.glob(os.path.join(base, '第*.md')) +
                   glob.glob(os.path.join(base, 'Chapter*.md')))
    changed = 0
    for f in files:
        with open(f, encoding='utf-8') as fh:
            src = fh.read()
        new = process(src)
        if new != src:
            with open(f, 'w', encoding='utf-8') as fh:
                fh.write(new)
            changed += 1
            print('CHANGED', os.path.basename(f))
    print('total changed:', changed)

if __name__ == '__main__':
    main()
