"""Insert the 24 missing numbered book formulas (writing-rules rule 7: 1:1
reproduction with \\tag{}) into BOTH the CN and EN chapter summaries, placing
each at the END of its target `## §C.S` section (before the next heading / EOF).

Idempotent: skips any (section, number) whose \\tag{n} already exists there.

Usage: python _insert_missing_formulas.py <book_dir>
"""
import glob
import os
import re
import sys

BOOK = sys.argv[1] if len(sys.argv) > 1 else \
    "D:/study/book/Kreyszig-Introductory-Functional-Analysis-with-Applications"

# (chapter) -> { section -> [(number, latex), ...] }  (order = book order)
FORMULAS = {
    2: {
        '2.9': [
            ('1', r'x = \xi_1 e_1 + \cdots + \xi_n e_n'),
            ('2', r'y = Tx = T\Bigl(\sum_{k=1}^{n} \xi_k e_k\Bigr) '
                  r'= \sum_{k=1}^{n} \xi_k\, T e_k'),
            ('3', r'y = \sum_{j=1}^{n} \eta_j b_j'),
            ('3b', r'T e_j = \sum_{k=1}^{n} T_{kj}\, b_k'),
            ('4', r'\eta_i = \sum_{k=1}^{n} T_{ik}\, \xi_k'),
            ('5a', r'f(x) = f\Bigl(\sum_{j=1}^{n} \xi_j e_j\Bigr) '
                   r'= \sum_{j=1}^{n} \xi_j\, f(e_j) '
                   r'= \sum_{j=1}^{n} \xi_j \alpha_j'),
            ('5b', r'\alpha_j = f(e_j)'),
            ('6', r'e_j^*(e_k) = \delta_{jk}'),
        ],
    },
    4: {
        '4.11': [
            ('2', r'a \le t_1 < \cdots < t_n \le b'),
            ('4', r'|f_n(x)| \le |\alpha_k|\, |x(t_k)| '
                  r'\le |\alpha_k|\, \|x\|'),
            ('5', r'\|f_n\| = \sum_{k=0}^{n} |\alpha_k|'),
        ],
        '4.12': [
            ('16', r'\int_{-h}^{h} x(t)\,dt = 2h\Bigl( x(0) '
                   r'+ x^{\prime\prime}(0)\,\frac{h^{2}}{3!} '
                   r'+ x^{(4)}(0)\,\frac{h^{4}}{5!} + \cdots \Bigr)'),
        ],
    },
    5: {
        '5.2': [
            ('1', r'd(x, z) = \max_{1\le j\le n} |\xi_j - \zeta_j|'),
            ('2', r'y = Tx = Cx + b'),
        ],
        '5.3': [
            ('1a', r"x' = f(t, x)"),
            ('1b', r'x(t_0) = x_0'),
        ],
    },
    6: {
        '6.2': [
            ('3', r'\sum_{k=1}^{n} \beta_k\, y_k(t) = v(t)'),
        ],
        '6.5': [
            ('1b', r'x = y + z'),
        ],
    },
    7: {
        '7.5': [
            ('2', r'\begin{array}{c} \Lambda \longrightarrow X \\[2pt] '
                   r'\lambda \longmapsto S_\lambda x. \end{array}'),
        ],
        '7.6': [
            ('2a', r'x(y+z) = xy + xz'),
            ('2b', r'(x+y)z = xz + yz'),
            ('4', r'xy = yx'),
            ('5', r'ex = xe = x'),
        ],
    },
    10: {
        '10.7': [
            ('2', r'\int_{-\infty}^{+\infty} t^2 |x(t)|^2 \,dt < \infty'),
        ],
    },
}

SEC_RE = re.compile(r'^##\s*§?\s*(\d+\.\d+)\s', re.M)
TAG_RE = re.compile(r'\\tag\{')


def sort_key(num):
    suf = num[-1].lower() if num[-1].isalpha() else ''
    core = num[:-1] if suf else num
    return (int(core) if core.isdigit() else 9999, suf)


def find_files(ch):
    cn = glob.glob(os.path.join(BOOK, f'第{ch}章*.md'))
    en = glob.glob(os.path.join(BOOK, f'Chapter{ch}_*.md'))
    return (cn[0] if cn else None, en[0] if en else None)


def insert_into_file(path, chapter_formulas):
    text = open(path, encoding='utf-8').read()
    # locate headings with their byte/char positions
    headings = [(m.start(), m.group(1)) for m in SEC_RE.finditer(text)]
    if not headings:
        print(f"  [WARN] no sections in {path}")
        return 0
    # sort target sections to insert bottom-up
    targets = sorted(chapter_formulas.keys(),
                     key=lambda s: [int(x) for x in s.split('.')])
    # map section -> position where to insert (end of section)
    inserts = []  # (pos, block)
    for sec in targets:
        sec_pos = None
        next_pos = len(text)
        for i, (hp, hsec) in enumerate(headings):
            if hsec == sec:
                sec_pos = hp
                if i + 1 < len(headings):
                    next_pos = headings[i + 1][0]
                break
        if sec_pos is None:
            print(f"  [WARN] section §{sec} not found in {os.path.basename(path)}")
            continue
        # already has the tags? guard
        seg = text[sec_pos:next_pos]
        existing = {m.group(1) for m in re.finditer(r'\\tag\{([^}]*)\}', seg)}
        items = [(n, latex) for (n, latex) in chapter_formulas[sec]
                 if n not in existing]
        if not items:
            continue
        items.sort(key=lambda t: sort_key(t[0]))
        # Blank line BETWEEN consecutive formula blocks (F-layer requires a
        # blank line before every opening $$), and one trailing blank line.
        block = '\n\n'.join(
            f'$$\n{latex} \\tag{{{n}}}\n$$' for (n, latex) in items)
        # Record the splice point on the ORIGINAL text (before any insert).
        # Apply bottom-up so lower inserts don't shift higher positions.
        inserts.append((next_pos, block, sec, [n for n, _ in items]))
    # apply bottom-up; guarantee one blank line before the block group and one
    # blank line before the following heading / EOF.
    for insert_at, block, sec, ns in sorted(inserts, key=lambda x: -x[0]):
        text = (text[:insert_at].rstrip('\n')
                + '\n\n' + block + '\n\n'
                + text[insert_at:].lstrip('\n'))
    open(path, 'w', encoding='utf-8').write(text)
    total = sum(len(ns) for *_, ns in inserts)
    if total:
        tags = ', '.join(f'§{s}({n})' for *_, s, ns in inserts for n in ns)
        print(f"  + {os.path.basename(path)}: inserted {total} -> {tags}")
    return total


def main():
    grand = 0
    for ch in sorted(FORMULAS):
        cn, en = find_files(ch)
        print(f"=== Chapter {ch} ===")
        for path in (cn, en):
            if not path:
                print(f"  [WARN] file missing for chapter {ch}")
                continue
            grand += insert_into_file(path, FORMULAS[ch])
    print(f"\nTOTAL inserted across CN+EN: {grand}")


if __name__ == '__main__':
    main()
