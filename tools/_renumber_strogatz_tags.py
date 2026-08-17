"""_renumber_strogatz_tags.py — one-off normalizer for Strogatz EN chapter summaries.

Strogatz numbers displayed equations PER SECTION with bare (1),(2),... that reset
to (1) at each new `## §N.M` section. Some writers emitted chapter-wide sequential
numbers (1..57), dotted `N.M` (3.1..3.27), lettered (1a,1b) or ranged (46,47) tags.
This script rewrites EVERY `\tag{...}` inside a `$$...$$` block to a strict per-section
bare integer sequence (1,2,3,...) starting at 1 for each `## §N.M` section, so the
tags match the book and pass the Q-layer FABRICATED check (book-source set S).

Idempotent: running twice yields the same result.
"""
import re, glob, os

BOOK = "D:/study/book/nonlinear-dynamics-and-chaos-3nbsped"
os.chdir(BOOK)

# exactly `## §...` (NOT `### §...`) marks a section boundary -> counter resets
SEC_RE = re.compile(r'(?m)^(##(?!#)\s*§[^\n]*)')
BLOCK_RE = re.compile(r'\$\$(.*?)\$\$', re.S)


def renumber_segment(seg: str) -> str:
    counter = 0

    def blockrepl(m):
        nonlocal counter
        block = m.group(0)

        def tagrepl(_tm):
            nonlocal counter
            counter += 1
            return '\\tag{' + str(counter) + '}'

        return re.sub(r'\\tag\{[^}]*\}', tagrepl, block)

    return BLOCK_RE.sub(blockrepl, seg)


def process_file(fn: str):
    text = open(fn, encoding='utf-8').read()
    parts = SEC_RE.split(text)
    out = []
    if parts:
        out.append(renumber_segment(parts[0]))  # preamble before first section
        for i in range(1, len(parts), 2):
            out.append(parts[i])  # heading line, unchanged
            body = parts[i + 1] if i + 1 < len(parts) else ''
            out.append(renumber_segment(body))
    newtext = ''.join(out)
    if newtext != text:
        open(fn, 'w', encoding='utf-8').write(newtext)
        return True
    return False


if __name__ == '__main__':
    changed = 0
    for fn in sorted(glob.glob('Chapter*.md')):
        if process_file(fn):
            changed += 1
            print('renumbered', fn)
        else:
            print('unchanged ', fn)
    print(f"done: {changed} file(s) changed")
