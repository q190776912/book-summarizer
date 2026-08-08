#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
merge_repairs.py — merge per-part repairs_part_*.json fragments into repairs.json.

Usage:
    python merge_repairs.py <mm_repair_dir> [<extract_dir>]

- <mm_repair_dir>: directory containing repairs_part_*.json + manifest.json
- <extract_dir>:   directory containing page_*.json (only needed for validation against manifest)

Merges the three top-level maps (corrections / ok / to_formula) across all
repairs_part_NN.json files. Pages are scoped to disjoint ranges by the fan-out
tool, so collisions should not occur — but we detect and report any.

Validation (if manifest.json present):
- every page key in parts exists in manifest["pages"]
- every "text:I" / "formula:I" key referenced exists as an entry key in that
  manifest page (so apply.py won't silently drop it)
"""
import json
import os
import glob
import sys


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def main():
    mm_dir = sys.argv[1]
    extract_dir = sys.argv[2] if len(sys.argv) > 2 else None

    parts = sorted(glob.glob(os.path.join(mm_dir, "repairs_part_*.json")))
    if not parts:
        print("MERGE: no repairs_part_*.json found in", mm_dir)
        return 1

    merged = {"corrections": {}, "ok": {}, "to_formula": {}}
    collisions = []
    part_counts = {}

    for pf in parts:
        data = load(pf)
        tag = os.path.basename(pf)
        c = sum(len(v) for v in data.get("corrections", {}).values())
        o = sum(len(v) for v in data.get("ok", {}).values())
        t = sum(len(v) for v in data.get("to_formula", {}).values())
        part_counts[tag] = (c, o, t)

        for sec in ("corrections", "ok", "to_formula"):
            src = data.get(sec, {})
            dst = merged[sec]
            for page, val in src.items():
                if page not in dst:
                    dst[page] = val
                else:
                    # collision handling
                    if sec == "ok":
                        existing = set(dst[page])
                        incoming = set(val)
                        dup = existing & incoming
                        if dup:
                            collisions.append((tag, sec, page, sorted(dup)))
                        dst[page] = sorted(existing | incoming)
                    else:
                        for k, v in val.items():
                            if k in dst[page] and dst[page][k] != v:
                                collisions.append((tag, sec, page, k))
                            dst[page][k] = v

    # validation against manifest
    manifest_path = os.path.join(mm_dir, "manifest.json")
    warnings = []
    if os.path.isfile(manifest_path):
        manifest = load(manifest_path)
        man_pages = manifest.get("pages", {})
        for sec in ("corrections", "ok", "to_formula"):
            for page, val in merged[sec].items():
                mp = man_pages.get(page)
                if mp is None:
                    warnings.append(f"[{sec}] page {page} not in manifest")
                    continue
                man_keys = {e["key"] for e in mp.get("entries", [])}
                if sec == "ok":
                    for k in val:
                        if k not in man_keys:
                            warnings.append(f"[{sec}] page {page} key {k} not in manifest")
                else:
                    for k in val.keys():
                        if k not in man_keys:
                            warnings.append(f"[{sec}] page {page} key {k} not in manifest")

    out = os.path.join(mm_dir, "repairs.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)

    # summary
    tot_c = sum(len(v) for v in merged["corrections"].values())
    tot_o = sum(len(v) for v in merged["ok"].values())
    tot_t = sum(len(v) for v in merged["to_formula"].values())
    print(f"MERGE: {len(parts)} part files merged -> {out}")
    print(f"  corrections={tot_c}  ok={tot_o}  to_formula={tot_t}  total={tot_c+tot_o+tot_t}")
    for tag in sorted(part_counts):
        c, o, t = part_counts[tag]
        print(f"    {tag}: corrections={c} ok={o} to_formula={t}")
    if collisions:
        print("  COLLISIONS (resolve before apply):")
        for col in collisions:
            print("    ", col)
    else:
        print("  no collisions across parts")
    if warnings:
        print("  VALIDATION WARNINGS:")
        for w in warnings:
            print("    ", w)
    else:
        print("  validation: all keys present in manifest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
