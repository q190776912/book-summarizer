#!/usr/bin/env python3
"""repairs.py — model + constructor for ``repairs.json``.

Merge per-part ``repairs_part_*.json`` fragments into ``repairs.json``.

Usage:
    python repairs.py <mm_repair_dir> [<extract_dir>]

- <mm_repair_dir>: directory containing repairs_part_*.json + manifest.json
- <extract_dir>:   directory containing page_*.json (only needed for validation against manifest)

Merges the top-level maps (corrections / ok / to_structured / deferred /
unavailable) across all repairs_part_NN.json files. Pages are scoped to disjoint
ranges by the fan-out
tool, so collisions should not occur — but we detect and report any.

Validation (if manifest.json present):
- every page key in parts exists in manifest["pages"]
- every "text:I" / "formula:I" key referenced exists as an entry key in that
  manifest page (so apply.py won't silently drop it)

Model (subclass of :class:`JsonData`):
    Repairs — the repairs.json document (corrections / ok / to_structured)
"""
import glob
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

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
from json_data import JsonData


def load(p):
    with open(p, encoding="utf-8") as f:
        return json.load(f)


@dataclass
class Repairs(JsonData):
    """The ``repairs.json`` document — a JSON subclass with a merge constructor.

    Top-level maps: corrections / ok / to_structured / deferred / unavailable.
    The first three come from the merge path (``repairs_part_*.json``);
    ``deferred`` is emitted by the text-compare path (``mm_repair_text_compare.py``)
    for entries left unresolved for the visual agent; ``unavailable`` holds
    entries judged unrecoverable after multiple visual review rounds (pure OCR
    noise / severe garble) — apply marks them ``mm_unavailable`` and lets the
    gate pass without polluting content.
    """
    corrections: Dict[str, dict] = field(default_factory=dict)
    ok: Dict[str, list] = field(default_factory=dict)
    to_structured: Dict[str, dict] = field(default_factory=dict)
    deferred: Dict[str, list] = field(default_factory=dict)
    unavailable: Dict[str, list] = field(default_factory=dict)

    # ---- constructor ----
    @classmethod
    def merge(cls, mm_dir: str, extract_dir: str = None):
        """Merge repairs_part_*.json fragments. Returns (Repairs, collisions, warnings)."""
        parts = sorted(glob.glob(os.path.join(mm_dir, "repairs_part_*.json")))
        if not parts:
            raise FileNotFoundError(f"MERGE: no repairs_part_*.json found in {mm_dir}")

        merged = {"corrections": {}, "ok": {}, "to_structured": {}, "deferred": {}, "unavailable": {}}
        collisions = []
        part_counts = {}

        for pf in parts:
            data = load(pf)
            tag = os.path.basename(pf)
            c = sum(len(v) for v in data.get("corrections", {}).values())
            o = sum(len(v) for v in data.get("ok", {}).values())
            t = sum(len(v) for v in data.get("to_structured", {}).values())
            dd = sum(len(v) for v in data.get("deferred", {}).values())
            part_counts[tag] = (c, o, t, dd)

            for sec in ("corrections", "ok", "to_structured", "deferred", "unavailable"):
                src = data.get(sec, {})
                dst = merged[sec]
                for page, val in src.items():
                    if page not in dst:
                        dst[page] = val
                    else:
                        # collision handling
                        if sec in ("ok", "deferred", "unavailable"):
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

        warnings = []
        manifest_path = os.path.join(mm_dir, "manifest.json")
        if os.path.isfile(manifest_path):
            manifest = load(manifest_path)
            man_pages = manifest.get("pages", {})
            for sec in ("corrections", "ok", "to_structured", "deferred", "unavailable"):
                for page, val in merged[sec].items():
                    mp = man_pages.get(page)
                    if mp is None:
                        warnings.append(f"[{sec}] page {page} not in manifest")
                        continue
                    man_keys = {e["key"] for e in mp.get("entries", [])}
                    keys = val if sec in ("ok", "deferred", "unavailable") else val.keys()
                    for k in keys:
                        if k not in man_keys:
                            warnings.append(f"[{sec}] page {page} key {k} not in manifest")

        inst = cls(corrections=merged["corrections"], ok=merged["ok"],
                   to_structured=merged["to_structured"], deferred=merged["deferred"],
                   unavailable=merged["unavailable"])
        return inst, collisions, warnings, part_counts

    # ---- export ----
    def to_dict(self) -> dict:
        return {
            "corrections": self.corrections,
            "ok": self.ok,
            "to_structured": self.to_structured,
            "deferred": self.deferred,
            "unavailable": self.unavailable,
        }

    @classmethod
    def from_sections(cls, corrections=None, ok=None, to_structured=None,
                      deferred=None) -> "Repairs":
        """Build a Repairs document directly from the four section maps.

        Used by ``mm_repair_text_compare.py`` (text-layer compensation) which
        produces the four maps inline and delegates the JSON write here, per
        the one-JSON-one-directory rule.
        """
        return cls(corrections=corrections or {}, ok=ok or {},
                   to_structured=to_structured or {}, deferred=deferred or {})

    @classmethod
    def from_dict(cls, d: dict) -> "Repairs":
        return cls(
            corrections=d.get("corrections", {}) or {},
            ok=d.get("ok", {}) or {},
            to_structured=d.get("to_structured", {}) or {},
            deferred=d.get("deferred", {}) or {},
            unavailable=d.get("unavailable", {}) or {},
        )


def main() -> int:
    mm_dir = sys.argv[1]
    extract_dir = sys.argv[2] if len(sys.argv) > 2 else None

    try:
        repairs, collisions, warnings, part_counts = Repairs.merge(mm_dir, extract_dir)
    except FileNotFoundError as e:
        print(str(e))
        return 1

    out = os.path.join(mm_dir, "repairs.json")
    repairs.dump(out)

    tot_c = sum(len(v) for v in repairs.corrections.values())
    tot_o = sum(len(v) for v in repairs.ok.values())
    tot_t = sum(len(v) for v in repairs.to_structured.values())
    print(f"MERGE: {len(part_counts)} part files merged -> {out}")
    print(f"  corrections={tot_c}  ok={tot_o}  to_structured={tot_t}  total={tot_c+tot_o+tot_t}")
    for tag in sorted(part_counts):
        c, o, t, dd = part_counts[tag]
        print(f"    {tag}: corrections={c} ok={o} to_structured={t} deferred={dd}")
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
