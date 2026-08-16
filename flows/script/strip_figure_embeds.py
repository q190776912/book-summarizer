"""strip_figure_embeds.py — remove all existing figure embeds (flex <div> + <img>)
from every *.md in the book so embed_figures can re-insert them at new positions.

Idempotent-safe: only removes lines that are (in core, after stripping a leading
'> ' blockquote prefix) a figure flex <div>, an <img ...>, or a closing </div>.
All other content (including blank lines, which may be REQUIRED before $$ math
blocks) is preserved.
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

import os, sys

FLEX_OPEN = '<div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:center">'


def core(ln):
    return ln.strip().lstrip('>').lstrip()


def is_embed_line(ln):
    c = core(ln)
    if c.startswith('<div style="display:flex'):
        return True
    if c.startswith('<img'):
        return True
    if c == '</div>':
        return True
    return False


def strip_file(path):
    lines = open(path, encoding='utf-8').read().splitlines()
    out = [ln for ln in lines if not is_embed_line(ln)]
    removed = len(lines) - len(out)
    if removed:
        open(path, "w", encoding='utf-8').write("\n".join(out) + "\n")
    return removed


def main():
    book_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    n = 0
    for fn in sorted(os.listdir(book_dir)):
        if not fn.endswith(".md"):
            continue
        p = os.path.join(book_dir, fn)
        r = strip_file(p)
        if r:
            n += 1
            print(f"  stripped {r} line(s) from {fn}")
    print(f"Done. {n} file(s) had figure embeds removed.")


if __name__ == "__main__":
    main()
