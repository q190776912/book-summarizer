# -*- coding: utf-8 -*-
"""跨库校准工具：统计各书 `units/` 里第 25 项「松散 OCR 数学形态」的命中分布。

用途 = 给门控判据的**收紧/放宽**提供跨书证据（判据本体只有一份，在
`flows/write-source/script/check_unit_quality.py` 的 `loose_math_problems`；
本工具只是消费者，**不写任何文件**）。

    python tools/scan_math_form.py <corpus_root> [--books N] [--sample N] [--quiet]

输出：每书命中文件数/行数，以及抽样行（供人工判定是否误报）。
"""
import argparse
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[1])
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "flows", "write-source", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot  # noqa: E402
_boot.setup()

import io  # noqa: E402
import glob  # noqa: E402
import check_unit_quality as cq  # noqa: E402


def book_units_roots(corpus_root):
    for dirpath, dirnames, filenames in os.walk(corpus_root):
        if os.path.basename(dirpath) == "book_structure":
            u = os.path.join(dirpath, "units")
            if os.path.isdir(u):
                yield u
                dirnames[:] = []


def scan(root, sample_lines):
    files = lines = 0
    per_book = []
    for units in book_units_roots(root):
        book = units.split(os.sep + "_extract" + os.sep)[0]
        bf = bl = 0
        samples = []
        for p in sorted(glob.glob(os.path.join(units, "*", "*.md"))):
            probs = cq.loose_math_problems(io.open(p, encoding="utf-8").read())
            if not probs:
                continue
            n = probs[0].count("\n  L")
            bf += 1
            bl += n
            if len(samples) < sample_lines:
                for ln in probs[0].splitlines()[1:3]:
                    samples.append("%s %s" % (os.path.basename(p), ln.strip()))
        per_book.append((os.path.relpath(book, root), bf, bl, samples))
        files += bf
        lines += bl
    return per_book, files, lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus_root")
    ap.add_argument("--top", type=int, default=15, help="按命中行数详列前 N 本书")
    ap.add_argument("--sample", type=int, default=4, help="每本详列书打印的抽样行数")
    ap.add_argument("--all", action="store_true", help="所有书都打印（含 0 命中）")
    a = ap.parse_args()
    per_book, files, lines = scan(a.corpus_root, a.sample)
    per_book.sort(key=lambda t: -t[2])
    print("books=%d  files_with_loose=%d  loose_lines=%d" % (len(per_book), files, lines))
    for idx, (book, bf, bl, samples) in enumerate(per_book):
        if bl == 0:
            if a.all:
                print("%-70s files=%4d lines=%6d" % (book[-70:], bf, bl))
            continue
        if idx < a.top:
            print("%-70s files=%4d lines=%6d" % (book[-70:], bf, bl))
            for s in samples:
                print("      | %s" % s[:150])
    return 0


if __name__ == "__main__":
    sys.exit(main())
