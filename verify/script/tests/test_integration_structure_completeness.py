"""Integration regression test for check_structure_completeness.py.

Builds a temporary three-level (ORDINAL_THREE_LEVEL, single uncat group) fixture
book that deliberately OMITS:
  * section 1.3 (tail leak -> detected by section_continuity / D-layer), and
  * items 1.1-2 (interior gap -> detected by item_numbering_integrity / B-layer
    blocking + set-difference), 1.2-2 and 1.3-1 (readable leaks -> set-difference).

Then runs the dry-run and --backfill paths and asserts:
  1. dry-run: D-layer finds missing section 1.3; B-layer blocks on the 1.1-2
     interior gap; set-difference finds the 3 readable missing items; gate FAILS.
  2. backfill: book_structure.json gains section 1.3 + items 1.1-2 / 1.2-2 /
     1.3-1; re-run gate PASSES (zero residual sections / readable items /
     B-layer blocking) -> completeness + continuity guaranteed.

Run:
    python verify/script/tests/test_integration_structure_completeness.py
"""
import json
import os
import sys
import tempfile
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
# Make the verify/script package importable (check_structure_completeness lives there).
SCRIPT_DIR = os.path.dirname(HERE)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import check_structure_completeness as csc
from verify_config import BookConfig
from data.book_structure.book_structure import BookStructure, StructureNode

# ---- fixture configuration -------------------------------------------------
CH = 1
START, END = 1, 8

VERIFY_CONFIG = {
    "ordinal": [{"type": 3, "name": ["uncat"], "depth": 3, "scope": 3}],
    "strict": True,
    "language": "en",
}

CHAPTER_MAP = {"chapters": [{"chapter": CH, "start": START, "end": END}]}

# Source (book truth). Every section has >=1 labeled three-level item so the
# D-layer treats it as "present". EN labels so en3_nf captures has_label.
# (1.1-1, 1.1-2, 1.1-3, 1.2-1, 1.2-2, 1.3-1 are ALL present in source.)
PAGES = {
    1: ["1.1 Metric Spaces", "1.1-1 Definition (Metric space.)"],
    2: ["1.1-2 Theorem (Banach fixed point.)"],
    3: ["1.1-3 Example (Open ball.)"],
    4: ["1.2 Completeness", "1.2-1 Definition (Cauchy sequence.)"],
    5: ["1.2-2 Theorem (Completeness of R^n.)"],
    6: ["1.3 Compactness", "1.3-1 Lemma (Compactness lemma.)"],
    7: ["Proof. Let (x_n) be a Cauchy sequence."],
    8: ["Hence the space is complete."],
}

# Contract = book_structure.json deliberately MISSING section 1.3 and items
# 1.1-2 / 1.2-2 / 1.3-1.
BOOK_STRUCTURE = {
    "key": -1, "type": -1, "name": "Test Book", "page_start": 1, "page_end": 8,
    "sub_sec": [
        {
            "key": str(CH), "type": "chapter", "name": "1 First Chapter",
            "page_start": 1, "page_end": 8, "sub_sec": [
                {"key": "1.1", "type": "section", "name": "1.1 Metric Spaces",
                 "page_start": 1, "page_end": 3, "sub_sec": [
                    {"key": "1.1-1", "type": "definition",
                     "name": "1.1-1 Definition (Metric space.)",
                     "page_start": 1, "page_end": 1, "sub_sec": []},
                    {"key": "1.1-3", "type": "example",
                     "name": "1.1-3 Example (Open ball.)",
                     "page_start": 3, "page_end": 3, "sub_sec": []},
                ]},
                {"key": "1.2", "type": "section", "name": "1.2 Completeness",
                 "page_start": 4, "page_end": 5, "sub_sec": [
                    {"key": "1.2-1", "type": "definition",
                     "name": "1.2-1 Definition (Cauchy sequence.)",
                     "page_start": 4, "page_end": 4, "sub_sec": []},
                ]},
                # section 1.3 intentionally absent
            ],
        }
    ],
}


def _write_fixture(ext):
    os.makedirs(ext, exist_ok=True)
    with open(os.path.join(ext, "verify_config.json"), "w", encoding="utf-8") as f:
        json.dump(VERIFY_CONFIG, f, ensure_ascii=False, indent=2)
    with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump(CHAPTER_MAP, f, ensure_ascii=False, indent=2)
    with open(os.path.join(ext, "book_structure.json"), "w", encoding="utf-8") as f:
        json.dump(BOOK_STRUCTURE, f, ensure_ascii=False, indent=2)
    for p, blocks in PAGES.items():
        data = {"text": [{"text": b} for b in blocks]}
        with open(os.path.join(ext, "page_%03d.json" % p), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    return ext


def _cfg():
    return BookConfig.from_dict(VERIFY_CONFIG)


def _assert(cond, msg):
    if not cond:
        print("  FAIL: " + msg)
        raise AssertionError(msg)
    print("  ok: " + msg)


def main():
    tmp = tempfile.mkdtemp(prefix="csc_integ_")
    try:
        ext = os.path.join(tmp, "_extract")
        _write_fixture(ext)
        cfg = _cfg()
        report_dir = os.path.join(ext, "completeness_reports")

        print("[1] dry-run (no backfill)")
        rep = csc.check_chapter(ext, CH, START, END, cfg, backfill=False,
                                report_dir=report_dir)
        assert rep is not None, "check_chapter returned None"

        # D-layer: missing section 1.3 (tail)
        _assert("1.3" in rep["missing_sections"],
                "D-layer detects missing section 1.3 (got %s)" % rep["missing_sections"])

        # B-layer: interior gap 1.1-2 -> blocking
        _assert(any("1.1" in b and "2" in b for b in rep["b_layer"]["blocking"]),
                "B-layer blocks on interior gap 1.1-2 (got %s)" % rep["b_layer"]["blocking"])

        # set-difference: 3 readable missing items
        readable = [m["key"] for m in rep["missing_items"] if m["status"] == "readable"]
        _assert(set(readable) == {"1.1-2", "1.2-2", "1.3-1"},
                "set-difference finds readable {1.1-2,1.2-2,1.3-1} (got %s)" % readable)

        # dry-run gate must FAIL (nothing backfilled yet)
        _assert(rep["gate"]["passed"] is False,
                "dry-run gate FAILS (got passed=%s)" % rep["gate"]["passed"])

        print("[2] backfill")
        rep2 = csc.check_chapter(ext, CH, START, END, cfg, backfill=True,
                                 report_dir=report_dir)
        _assert(rep2["backfilled_sections"],
                "section 1.3 backfilled (got %s)" % rep2["backfilled_sections"])
        _assert(len(rep2["backfilled_items"]) == 3,
                "3 items backfilled (got %s)" % rep2["backfilled_items"])

        # gate PASSES: zero residual sections / readable items / B-layer blocking
        g = rep2["gate"]
        _assert(g["passed"] is True, "backfill gate PASSES")
        _assert(not g["residual_sections"], "no residual missing sections")
        _assert(not g["residual_readable_items"], "no residual readable items")
        _assert(not g["residual_b_blocking"], "no residual B-layer blocking")

        print("[3] book_structure.json now complete & continuous")
        bs = BookStructure.load(ext)
        ch_node = bs.find_chapter(CH)
        sec_keys = {n.key for n in ch_node.sub_sec if n.type == "section"}
        _assert(sec_keys == {"1.1", "1.2", "1.3"},
                "all 3 sections present (got %s)" % sorted(sec_keys))
        item_keys = {n.key for n in ch_node.iter_items()}
        _assert(item_keys == {"1.1-1", "1.1-2", "1.1-3", "1.2-1", "1.2-2", "1.3-1"},
                "all 6 items present (got %s)" % sorted(item_keys))
        # every backfilled/inserted item lives under its section (continuity)
        sec13 = next(n for n in ch_node.sub_sec if n.key == "1.3")
        _assert(any(n.key == "1.3-1" for n in sec13.sub_sec),
                "1.3-1 correctly nested under section 1.3")

        print("\nALL INTEGRATION CHECKS PASSED")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
