#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mm_repair_decide.py — merge agent batch decisions into _mm_repair/repairs.json

Usage:
    python tools/mm_repair_decide.py <extract_dir> <decisions.json>

Decisions JSON format (corrections / ok / to_structured):
{
  "corrections": {
    "004": {"text:11": "correct text", "formula:1": "latex"},
    ...
  },
  "ok": {
    "004": ["text:3", "formula:0"],
    ...
  },
  "to_structured": {
    "004": {"text:9": "x^2+y^2", "formula:2": "plain text"},
    ...
  }
}

This tool merges into the existing repairs.json (from mode B / prior batches),
never clobbering whole pages.
"""
import argparse
import json
import os
import sys


def _deep_update_page(dst_page, src_page):
    """Merge per-page dict-of-key decisions into existing page block."""
    for key, val in src_page.items():
        dst_page[key] = val


def merge_repairs(repairs_path, decisions):
    if os.path.exists(repairs_path):
        rep = json.load(open(repairs_path, encoding="utf-8"))
    else:
        rep = {}
    for section in ("corrections", "ok", "to_structured"):
        src = decisions.get(section, {})
        if not src:
            continue
        dst = rep.setdefault(section, {})
        for page, page_block in src.items():
            dst_page = dst.setdefault(page, {} if section != "ok" else [])
            if section == "ok":
                existing = set(dst_page)
                for k in page_block:
                    existing.add(k)
                dst[page] = sorted(existing)
            else:
                _deep_update_page(dst_page, page_block)
    json.dump(rep, open(repairs_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return rep


def main():
    ap = argparse.ArgumentParser(description="Merge MM Repair decisions into repairs.json")
    ap.add_argument("extract_dir", help="path to book _extract dir")
    ap.add_argument("decisions", help="path to JSON decisions file")
    args = ap.parse_args()

    repairs_path = os.path.join(args.extract_dir, "_mm_repair", "repairs.json")
    if not os.path.isfile(repairs_path):
        print(f"[mm_repair_decide] repairs.json not found at {repairs_path}; starting fresh.")
    decisions = json.load(open(args.decisions, encoding="utf-8"))
    if not any(decisions.get(k) for k in ("corrections", "ok", "to_structured")):
        print("[mm_repair_decide] warning: empty decisions")
    merge_repairs(repairs_path, decisions)
    # report counts per section
    rep = json.load(open(repairs_path, encoding="utf-8"))
    for section in ("corrections", "ok", "to_structured"):
        total = sum(len(v) for v in rep.get(section, {}).values())
        print(f"[mm_repair_decide] {section}: {total} decisions now stored")
    return 0


if __name__ == "__main__":
    sys.exit(main())
