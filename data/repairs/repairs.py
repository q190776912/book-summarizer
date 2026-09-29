#!/usr/bin/env python3
"""repairs.py — model + constructor for ``repairs.json``.

Merge the per-batch agent fragments (``repairs_part_*.json`` / ``_frag_*.json``)
into ``repairs.json``, optionally folding a mode-B base in first.

Usage:
    python repairs.py <mm_repair_dir> [<extract_dir>] [--base <modeB.json>]

- <mm_repair_dir>: directory containing the fragments + manifest.json
- <extract_dir>:   directory containing page_*.json (only needed for validation against manifest)
- --base:          the mode-B text-compare output to fold in underneath the agent
                   verdicts.  Pass a COPY (e.g. ``repairs.modeB.json``), never the
                   output ``repairs.json`` itself — mode B writes its candidates
                   straight into that file, so merging without ``--base`` would
                   drop all of them.

Merges the top-level maps (corrections / ok / to_structured / deferred /
unavailable) across all fragment files. Pages are scoped to disjoint ranges by the fan-out
tool, so collisions should not occur — but we detect and report any.

Validation (if manifest.json present):
- every page key in parts exists in manifest["pages"]
- every "text:I" / "formula:I" key referenced exists as an entry key in that
  manifest page (so apply.py won't silently drop it)
- 🔴 coverage: every manifest entry carries a ruling (``deferred`` does not count —
  apply ignores it); any gap exits 1 instead of letting apply mark the book partial
- 🔴 mode-B candidates on a page a visual agent re-reviewed but never ruled on are
  listed for settlement (text-layer corrections are candidates, not verdicts)

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
    SECTIONS = ("corrections", "ok", "to_structured", "deferred", "unavailable")
    LIST_SECTIONS = ("ok", "deferred", "unavailable")
    PART_GLOBS = ("repairs_part_*.json", "_frag_*.json")

    @classmethod
    def _iter_keys(cls, data: dict):
        """Yield (section, page, key) for every entry a document rules on."""
        for sec in cls.SECTIONS:
            for page, val in (data.get(sec) or {}).items():
                for key in val:
                    yield sec, page, key

    @classmethod
    def _drop(cls, merged: dict, page: str, key: str, keep_sec: str = None):
        """Remove `page`/`key` from every section (optionally keeping one)."""
        for sec in cls.SECTIONS:
            if sec == keep_sec:
                continue
            blk = merged[sec].get(page)
            if not blk:
                continue
            if sec in cls.LIST_SECTIONS:
                if key in blk:
                    merged[sec][page] = [k for k in blk if k != key]
                    if not merged[sec][page]:
                        del merged[sec][page]
            elif key in blk:
                del blk[key]
                if not blk:
                    del merged[sec][page]

    @classmethod
    def merge(cls, mm_dir: str, extract_dir: str = None, base_path: str = None):
        """Merge agent fragments (and optionally a mode-B base) into one document.

        Fragments are `repairs_part_*.json` / `_frag_*.json`; pages are scoped to
        disjoint ranges by the fan-out plan, so collisions should not occur — we
        still detect and report them.

        🔴 `base_path` (the mode-B text-compare output) is folded in FIRST, then
        every fragment ruling **wins across sections**: a key the agent re-judged
        is stripped from all other sections before the agent's verdict is written.
        Without that, `mm_repair_apply.py` — which reads a fixed
        corrections > ok > to_structured > unavailable precedence — would let a
        stale text-layer candidate silently outrank the newer visual verdict.
        """
        parts = sorted({p for g in cls.PART_GLOBS
                        for p in glob.glob(os.path.join(mm_dir, g))})
        if not parts:
            raise FileNotFoundError(f"MERGE: no {'/'.join(cls.PART_GLOBS)} found in {mm_dir}")

        merged = {sec: {} for sec in cls.SECTIONS}
        owner = {}           # (page, key) -> tag that currently rules it
        collisions = []
        overrides = []
        part_counts = {}
        base_open = set()    # (page, key) mode-B verdicts awaiting visual settlement
        frag_pages = set()   # pages a visual agent re-reviewed
        frag_ruled = set()   # (page, key) the agents actually ruled

        docs = []
        if base_path:
            docs.append(("base:" + os.path.basename(base_path), load(base_path), False))
        docs += [(os.path.basename(pf), load(pf), True) for pf in parts]

        for tag, data, arbitrate in docs:
            part_counts[tag] = {sec: sum(len(v) for v in (data.get(sec) or {}).values())
                                for sec in cls.SECTIONS}
            for sec, page, key in cls._iter_keys(data):
                if not arbitrate:
                    if sec in ("corrections", "ok"):
                        base_open.add((page, key, sec))
                    continue
                frag_pages.add(page)
                if sec != "deferred":
                    frag_ruled.add((page, key))
            if arbitrate:
                claim = {}
                for sec, page, key in cls._iter_keys(data):
                    claim.setdefault((page, key), []).append(sec)
                for (page, key), secs in claim.items():
                    cur = owner.get((page, key))
                    if cur is None:
                        continue
                    if cur.startswith("base:"):
                        cls._drop(merged, page, key)
                        owner.pop((page, key), None)
                        overrides.append((page, key, cur, "/".join(secs)))
                    else:
                        # part vs part = same tier; let the absorb below overwrite
                        # it and report the duplicate ruling as a collision.
                        collisions.append((tag, "/".join(secs), page, key,
                                          f"already ruled by {cur}"))
            for sec in cls.SECTIONS:
                src = data.get(sec, {})
                dst = merged[sec]
                for page, val in src.items():
                    if page not in dst:
                        dst[page] = val
                    else:
                        # collision handling
                        if sec in cls.LIST_SECTIONS:
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
            for sec, page, key in cls._iter_keys(data):
                owner[(page, key)] = tag

        warnings = []
        missing = []
        # 🔴 mode-B trust review (mm_repair doc rule: text-layer `corrections`
        # are CANDIDATES — a legacy OCR layer can be confidently wrong).  A
        # candidate on a page a visual agent re-reviewed but that the agent
        # never ruled on is an OPEN question, not a verdict: report it so the
        # caller settles it instead of letting apply write it back unexamined.
        # 🔴 mode-B verdicts are CANDIDATES, not facts: `corrections` can be a
        # mis-extracted text layer, and `ok` only means "text layer agrees with our
        # OCR" — which proves nothing when the embedded layer is itself legacy OCR
        # (same source, same error).  A base verdict on a page a visual agent
        # re-reviewed but never ruled on is an OPEN question: report it so the caller
        # settles it instead of letting apply stamp it mm_reviewed.
        unreviewed = sorted((page, key, sec) for (page, key, sec) in base_open
                            if page in frag_pages and (page, key) not in frag_ruled)
        manifest_path = os.path.join(mm_dir, "manifest.json")
        if os.path.isfile(manifest_path):
            manifest = load(manifest_path)
            man_pages = manifest.get("pages", {})
            for sec in cls.SECTIONS:
                for page, val in merged[sec].items():
                    mp = man_pages.get(page)
                    if mp is None:
                        warnings.append(f"[{sec}] page {page} not in manifest")
                        continue
                    man_keys = {e["key"] for e in mp.get("entries", [])}
                    keys = val if sec in cls.LIST_SECTIONS else val.keys()
                    for k in keys:
                        if k not in man_keys:
                            warnings.append(f"[{sec}] page {page} key {k} not in manifest")
            # 🔴 coverage: an entry with no ruling stays unresolved in the manifest,
            # so apply marks the book only "partial" — find it here instead.
            # `deferred` is NOT a ruling (apply ignores that section), so it never counts.
            ruled = {(page, key) for sec, page, key in cls._iter_keys(merged)
                     if sec != "deferred"}
            for page, mp in man_pages.items():
                for e in mp.get("entries", []):
                    if (page, e["key"]) not in ruled:
                        missing.append((page, e["key"]))

        inst = cls(corrections=merged["corrections"], ok=merged["ok"],
                   to_structured=merged["to_structured"], deferred=merged["deferred"],
                   unavailable=merged["unavailable"])
        unrevisited = sorted((page, key, sec) for (page, key, sec) in base_open
                             if page not in frag_pages)
        report = {"overrides": overrides, "missing": missing,
                  "base_unreviewed": unreviewed, "base_unrevisited": unrevisited,
                  "base": bool(base_path)}
        return inst, collisions, warnings, part_counts, report

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
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    base_path = None
    for a in sys.argv[1:]:
        if a.startswith("--base"):
            base_path = a.split("=", 1)[1] if "=" in a else None
    if "--base" in sys.argv:
        i = sys.argv.index("--base")
        if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith("--"):
            base_path = sys.argv[i + 1]
    if not argv:
        print(__doc__)
        return 1
    mm_dir = argv[0]
    extract_dir = argv[1] if len(argv) > 2 else None

    try:
        repairs, collisions, warnings, part_counts, report = Repairs.merge(
            mm_dir, extract_dir, base_path=base_path)
    except FileNotFoundError as e:
        print(str(e))
        return 1

    out = os.path.join(mm_dir, "repairs.json")
    if base_path and os.path.abspath(base_path) == os.path.abspath(out):
        print("MERGE: --base must not be the output repairs.json "
              "(fold a copy, e.g. repairs.modeB.json, so the base survives a failed write)")
        return 1

    # 🔴 machine-readable full report (stdout truncates at 40) so the caller can
    # build visual waves straight from it instead of reading the console.
    open(os.path.join(mm_dir, "_merge_report.json"), "w",
         encoding="utf-8").write(json.dumps(
             {"overrides": report["overrides"], "missing": report["missing"],
              "base_unreviewed": report["base_unreviewed"],
              "base_unrevisited": report["base_unrevisited"],
              "collisions": collisions, "warnings": warnings,
              "part_counts": part_counts, "totals": {
                  sec: sum(len(v) for v in getattr(repairs, sec).values())
                  for sec in Repairs.SECTIONS}},
             ensure_ascii=False, indent=1))

    tot = {sec: sum(len(v) for v in getattr(repairs, sec).values()) for sec in Repairs.SECTIONS}
    print(f"MERGE: {len(part_counts)} source(s) merged -> {out}"
          + ("  [base folded: %s]" % os.path.basename(base_path) if base_path else ""))
    print("  " + "  ".join(f"{sec}={tot[sec]}" for sec in Repairs.SECTIONS)
          + f"  ruled_total={sum(tot.values())}")
    for tag in sorted(part_counts):
        print(f"    {tag}: " + " ".join(f"{sec}={part_counts[tag][sec]}" for sec in Repairs.SECTIONS))
    if collisions:
        print(f"  COLLISIONS ({len(collisions)}) — same entry ruled twice by two fragments, resolve before apply:")
        for col in collisions[:40]:
            print("    ", col)
    else:
        print("  no collisions across parts")
    if report["overrides"]:
        print(f"  base overridden by fragment verdicts: {len(report['overrides'])} "
              "(cross-section stale candidates removed — apply would otherwise let "
              "corrections>ok>to_structured outrank the newer ruling)")
        for ov in report["overrides"][:40]:
            print("    ", ov)
    if report["base_unreviewed"]:
        print(f"  ⚠️ MODE-B VERDICTS ON RE-REVIEWED PAGES, NEVER RULED "
              f"({len(report['base_unreviewed'])}): the visual agent covered the page "
              "but left these text-layer verdicts untouched — settle each one "
              "(confirm / rewrite from print / ok / unavailable) before apply.")
        for p, k, sec in report["base_unreviewed"][:40]:
            print(f"     page {p}: {k} [{sec}]")
    if report["base_unrevisited"]:
        print(f"  ⚠️ MODE-B VERDICTS ON PAGES NO AGENT VISITED "
              f"({len(report['base_unrevisited'])}) — `ok` there only proves the "
              "embedded text layer matches our own OCR; if that layer is legacy OCR "
              "it is the SAME SOURCE with the SAME errors. Send a visual wave.")
        for p, k, sec in report["base_unrevisited"][:40]:
            print(f"     page {p}: {k} [{sec}]")
    if warnings:
        print(f"  VALIDATION WARNINGS ({len(warnings)}):")
        for w in warnings[:40]:
            print("    ", w)
    else:
        print("  validation: all keys present in manifest")
    if report["missing"]:
        pages = sorted({p for p, _ in report["missing"]})
        print(f"  ❌ COVERAGE GAP: {len(report['missing'])} manifest entries have no ruling "
              f"across {len(pages)} pages (apply would mark the book PARTIAL).")
        for p in pages[:30]:
            keys = [k for pp, k in report["missing"] if pp == p]
            print(f"     page {p}: {keys}")
        return 1
    # 🔴 fail-closed: an unruled mode-B claim is still a claim.  `ok` from the text
    # layer only means "the embedded layer matches our own OCR" — when that layer is
    # legacy OCR it is the same source with the same errors, and apply would stamp it
    # mm_reviewed anyway.  Do not hand apply a repairs.json containing such a verdict.
    if collisions:
        print(f"  ❌ COLLISIONS: {len(collisions)} entr(ies) ruled by two fragments — "
              "apply would pick one by section precedence, i.e. arbitrarily.")
        return 1
    open_q = len(report["base_unreviewed"]) + len(report["base_unrevisited"])
    if open_q:
        print(f"  ❌ OPEN MODE-B VERDICTS: {open_q} text-layer claim(s) (ok/corrections) "
              "got no visual ruling. Full list: _mm_repair/_merge_report.json. "
              "Send a visual wave over those pages and re-merge; repairs.json NOT written.")
        return 1
    repairs.dump(out)
    print("  coverage: every manifest entry has exactly one ruling")
    print(f"  wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
