"""scan_items.py — independent completeness scanner for TWO-LEVEL numbering books.

WHY THIS EXISTS
===============
The skill's default extractor (extract_items.py) assumes a THREE-LEVEL
scheme (N.S-N). Some books — most notably 周民强《实变函数论》 — use a
TWO-LEVEL scheme with a DUAL counter:

  (1) 定义 has its OWN per-chapter counter:        定义1.1, 定义1.2, ...
  (2) 定理 / 引理 / 推论 / 命题 SHARE one continuous counter:
                                                    定理1.1, 引理1.2, 推论1.3, ...
  (3) 例 are renumbered PER SECTION:               例1, 例2, ... (within §N.M)

For such books, extract_items' three-level N.S-N regex manufactures
FALSE-POSITIVE phantom keys out of formula/enumeration fragments (e.g. it
reads "1.1-1" out of "((1-1.1+1))"), which then can never be matched in the
.md and produce spurious TRULY-MISSING.

This scanner is the RECOMMENDED completeness check for two-level books. It
directly mirrors the book's numbering and reports:

  * every section §N.M seen in the raw JSON (with page + name)
  * every 定义 (own counter) with page + snippet
  * every 定理/引理/推论/命题 (shared counter) with page + snippet
  * every 例 (per section) with page + snippet
  * CONTINUITY gaps for 定义 / 定理family (missing = [..] means a hole)

Use it AFTER writing a chapter to confirm nothing was dropped, INDEPENDENTLY
of verify_chapter.py (which reads `ordinal` from <extract_dir>/verify_config.json
to pick the numbering mode, but this scanner is the authoritative continuity
check). It is also the basis for
deciding whether a key is genuine or OCR noise when registering --ignore.

OCR QUIRKS HANDLED
==================
  * § misrecognised as 'S'  (e.g. "S2.5"  -> §2.5)  — tolerated via (?:§|S)?
  * § misrecognised as '8'  (e.g. "81.6"  -> §1.6)  — tolerated via (?:§|8)?
  * middle dot '·' accepted as separator alongside '.'

USAGE
=====
  python scan_items.py <ch> <start_page> <end_page> <extract_dir>
  python scan_items.py <ch> <start_page> <end_page> <extract_dir> --verbose

<extract_dir> is the book's _extract folder (page_NNN.json live there).
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
import page_json


import os, sys

import json, os, re, sys
from lib.regexlib import SEP_TIGHT

def ykey(t):
    poly = t.get("poly")
    if isinstance(poly, list) and poly and isinstance(poly[0], list) and len(poly[0]) >= 2:
        return poly[0][1]
    if isinstance(poly, list) and len(poly) >= 2 and isinstance(poly[1], (int, float)):
        return poly[1]
    return 1e9


def scan(ch, start, end, d):
    # Label items: 定义 / 定理 / 引理 / 推论 / 命题, each as 标签 章.号
    lab_re = re.compile(r'(定义|定理|引理|推论|命题)\s*(\d+)\s*' + SEP_TIGHT + r'\s*(\d+)')
    # Section heading: §N.M Name  — tolerate OCR § -> S / 8  (e.g. "S2.5", "81.6")
    sec_re = re.compile(r'^(?:§|S|8)?\s*(' + str(ch) + r')\s*' + SEP_TIGHT + r'\s*(\d+)\s*([^\d.\-–·/．－〜].{0,30})')
    # Examples: 例N (NOT 例N.M) at the start of a block, per-section renumbering.
    ex_re = re.compile(r'^例\s*(\d+)(?![\.\·]?\d)')

    defs = {}        # 定义N.M -> (page, ctx)
    thms = {}        # 定理family N.M -> (label, page, ctx)
    examples = []    # (page, sec, exnum, ctx)
    sections = {}    # N.M -> (page, name)
    cur_sec = None

    for p in range(start, end + 1):
        fp = os.path.join(d, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        data = page_json.PageJson.load(fp).data
        texts = [t for t in data.get("text", []) if t.get("text", "").strip()]
        texts.sort(key=ykey)
        for t in texts:
            txt = t["text"].strip()
            # section heading
            sm = sec_re.match(txt)
            if sm and sm.group(1) == str(ch):
                key = f"{ch}.{sm.group(2)}"
                if key not in sections:
                    sections[key] = (p, sm.group(3).strip())
                cur_sec = key
            # labeled items (定义 / 定理 / 引理 / 推论 / 命题)
            for m in lab_re.finditer(txt):
                lab, c, num = m.group(1), m.group(2), m.group(3)
                if c != str(ch):
                    continue
                ctx = txt[max(0, m.start() - 2):m.start() + 55]
                key = f"{c}.{num}"
                if lab == "定义":
                    if key not in defs:
                        defs[key] = (p, ctx)
                else:
                    if key not in thms:
                        thms[key] = (lab, p, ctx)
            # examples (例N at block start)
            em = ex_re.match(txt)
            if em:
                examples.append((p, cur_sec, int(em.group(1)), txt[:55]))
    return defs, thms, examples, sections


def continuity(keys, label):
    nums = sorted(int(k.split('.')[1]) for k in keys)
    if not nums:
        print(f"  [{label}] NONE FOUND")
        return
    lo, hi = nums[0], nums[-1]
    missing = [n for n in range(lo, hi + 1) if n not in nums]
    print(f"  [{label}] {lo}..{hi}  count={len(nums)}  missing={missing if missing else 'NONE'}")


if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python scan_items.py <ch> <start_page> <end_page> <extract_dir> [--verbose]")
        print("  Two-level numbering scanner (定义 own counter + 定理/引理/推论/命题 shared counter).")
        print("  See module docstring for the numbering scheme and OCR-quirk handling.")
        sys.exit(1)
    ch, start, end, d = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    defs, thms, examples, sections = scan(ch, start, end, d)
    print(f"===== Ch{ch} SECTIONS =====")
    for k in sorted(sections, key=lambda k: int(k.split('.')[1])):
        p, name = sections[k]
        print(f"  §{k} p{p:3d}  {name}")
    print(f"\n===== 定义 (own counter) =====")
    for k in sorted(defs, key=lambda k: int(k.split('.')[1])):
        p, ctx = defs[k]
        print(f"  定义{k:8s} p{p:3d}  {ctx}")
    print(f"\n===== 定理/引理/推论/命题 (shared counter) =====")
    for k in sorted(thms, key=lambda k: int(k.split('.')[1])):
        lab, p, ctx = thms[k]
        print(f"  {lab}{k:8s} p{p:3d}  {ctx}")
    print(f"\n===== 例 (per section) =====")
    for p, sec, exn, ctx in examples:
        print(f"  例{exn} (§{sec}) p{p:3d}  {ctx}")
    print(f"\n===== CONTINUITY =====")
    continuity(defs.keys(), "定义")
    continuity(thms.keys(), "定理family")
    print(f"\nTOTALS: 定义={len(defs)}  定理family={len(thms)}  例={len(examples)}  节={len(sections)}")
    if not sections:
        print("WARNING: no § sections detected — check OCR (§ may be misread as S/8).")
