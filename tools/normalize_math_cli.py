#!/usr/bin/env python3
"""tools/normalize_math_cli.py — CLI entry point for formula delimiter repair.

The actual normalization logic lives in `lib/normalize_math.py` (importable as
`from lib.normalize_math import normalize, stats`). This file is only the
file-rewriting command-line front end.

Usage:
    python tools/normalize_math_cli.py <file.md> [<file2.md> ...]

For each file it prints before/after defect counts (backtick spans, math-bearing
backtick spans, chopped-$ signals). If the content changes, a backup
`<file>.bak_mathfix` is written once and the file is rewritten in place.
"""
import os
import shutil
import sys

# Make the skill root importable when this file is run directly
# (e.g. `python tools/normalize_math_cli.py ...`): the script's own directory is
# what ends up on sys.path, not the skill root, so `lib` would be unresolvable.
SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if SKILL_ROOT not in sys.path:
    sys.path.insert(0, SKILL_ROOT)

from lib.normalize_math import normalize, stats


def main():
    files = sys.argv[1:]
    if not files:
        print("usage: python tools/normalize_math_cli.py <file.md> [<file2.md> ...]")
        return 1
    for f in files:
        t = open(f, encoding='utf-8').read()
        sb, bb, ch = stats(t)
        t2 = normalize(t)
        sb2, bb2, ch2 = stats(t2)
        if t2 != t:
            bak = f + '.bak_mathfix'
            if not os.path.exists(bak):
                shutil.copy(f, bak)
            open(f, 'w', encoding='utf-8').write(t2)
            print(f"{os.path.basename(f):50s} backtick={sb}->{sb2}  math_bearing={bb}->{bb2}  chopped={ch}->{ch2}")
        else:
            print(f"{os.path.basename(f):50s} (unchanged)")
    return 0


if __name__ == '__main__':
    sys.exit(main())
