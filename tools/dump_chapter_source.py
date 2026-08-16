#!/usr/bin/env python3
"""dump_chapter_source.py — one-file source dump per chapter for the
book-summarizer skill.

Concatenates the OCR text + formula LaTeX of every page in a chapter's PDF
page range (from chapter_map.json) into a single readable .md-ish file under
<book_dir>/_extract/_src_dump/. This is a convenience for the chapter author
(subagent or main agent) so they read ONE file instead of ~40 page_*.json.

The dump is intentionally raw OCR (noisy text, garbled formula LaTeX) — the
author must still "understand -> correct -> rewrite" per writing-rules.md.

Usage:
    python tools/dump_chapter_source.py <book_dir> <ch> [<ch> ...]
    python tools/dump_chapter_source.py <book_dir> --all
"""
import json
import os
import sys
import glob

for _c in [os.path.abspath(__file__), *[p for p in os.path.abspath(__file__).split(os.sep)]]:
    pass
# boot
_ROOT = None
for _c in [os.path.dirname(__file__), os.path.dirname(os.path.dirname(__file__))]:
    if os.path.exists(os.path.join(_c, "SKILL.md")):
        _ROOT = _c
        break
if _ROOT is None:
    _ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

from data.chapter_map.chapter_map import load_chapter_map_raw


def _sorted_pages(ext):
    return sorted(glob.glob(os.path.join(ext, "page_*.json")),
                  key=lambda p: int(os.path.basename(p)[5:-5]))


def dump_chapter(book_dir, ch):
    ext = os.path.join(book_dir, "_extract")
    cm = load_chapter_map_raw(os.path.join(ext, "chapter_map.json"))
    # normalize to {"chapters":[...]} or flat dict
    if isinstance(cm, dict) and "chapters" in cm:
        entries = cm["chapters"]
        e = next((x for x in entries if str(x.get("ch", x.get("num", x.get("chapter")))) == str(ch)), None)
    else:
        e = cm.get(str(ch))
    if e is None:
        print(f"ch{ch}: not in chapter_map, skip")
        return
    start, end = int(e["start"]), int(e["end"])
    name = e.get("name_en") or e.get("name") or ""
    print(f"ch{ch} '{name}': PDF pages {start}..{end}")

    out_dir = os.path.join(ext, "_src_dump")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"ch{ch:02d}_source.md")
    pages = _sorted_pages(ext)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Chapter {ch}: {name}\n")
        f.write(f"# PDF page range: {start}..{end} (offset +15 from printed page)\n\n")
        for pgf in pages:
            pg = int(os.path.basename(pgf)[5:-5])
            if pg < start or pg > end:
                continue
            d = json.load(open(pgf, encoding="utf-8"))
            # sort text blocks by vertical position (poly y0)
            blocks = d.get("text", [])
            blocks = sorted(blocks, key=lambda b: (b.get("poly", [0, 0, 0, 0, 0, 0, 0, 0])[1] if b.get("poly") else 0))
            text = "\n".join(b.get("text", "") for b in blocks)
            formulas = d.get("formulas", [])
            f.write(f"\n===== PDF PAGE {pg} (printed ~{pg-15}) =====\n")
            f.write(text.strip() + "\n")
            if formulas:
                f.write("\n-- formulas (OCR LaTeX, MUST be corrected) --\n")
                for i, fm in enumerate(formulas):
                    latex = fm.get("latex", "")
                    f.write(f"  [{i}] {latex}\n")
    print(f"  -> wrote {out_path}")


def main():
    if len(sys.argv) < 3:
        print("Usage: dump_chapter_source.py <book_dir> <ch> [<ch> ...] | --all")
        sys.exit(1)
    book_dir = sys.argv[1]
    if sys.argv[2] == "--all":
        cm = load_chapter_map_raw(os.path.join(book_dir, "_extract", "chapter_map.json"))
        if isinstance(cm, dict) and "chapters" in cm:
            chs = [str(x.get("ch", x.get("num", x.get("chapter")))) for x in cm["chapters"]]
        else:
            chs = list(cm.keys())
    else:
        chs = sys.argv[2:]
    for ch in chs:
        dump_chapter(book_dir, ch)


if __name__ == "__main__":
    main()
