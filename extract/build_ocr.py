#!/usr/bin/env python3
"""build_ocr.py — 由 page_*.json 拼接出 ch<N>_ocr.txt（写作用 OCR 底本）。

用法:
    python build_ocr.py <extract_dir> <start> <end> <out_file>

输出格式（与已有 ch6_ocr.txt 一致）:
    每个页码一段，形如:
        \n===== PAGE N =====\n\n<该页每行 text>\n
"""
import json
import os
import sys


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        return 2
    extract_dir, start, end, out_file = sys.argv[1], int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    parts = []
    for n in range(start, end + 1):
        p = os.path.join(extract_dir, "page_%03d.json" % n)
        if not os.path.exists(p):
            print("WARNING: missing %s" % p, file=sys.stderr)
            continue
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        lines = []
        for it in d.get("text", []):
            txt = it.get("text") or ""
            for ln in txt.split("\n"):
                lines.append(ln)
        parts.append("\n===== PAGE %d =====\n\n%s\n" % (n, "\n".join(lines)))
    out_path = os.path.join(extract_dir, out_file)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    print("Wrote %s : %d pages (%d-%d)" % (out_file, len(parts), start, end))
    return 0


if __name__ == "__main__":
    sys.exit(main())
