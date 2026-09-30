"""Regression test: `_canon_key` 的 THREE_LEVEL 分支必须剥内嵌类型标签（2026-09-29 Katok 实测）。

形态：build_structure 把类型词内嵌进契约键（`命题1.1.2` / `定义1.1.1` / `例1.2.1`），
而 `_canon_key(ORDINAL_THREE_LEVEL, ...)` 旧实现只认**裸**三段数字，于是这些契约条目
在 contract_items 里整体蒸发，源侧扫到的同一真身全部判成 readable 假缺项：
Katok《Introduction to the Modern Theory of Dynamical Systems》9 章闸门永 FAIL
（217 条假缺项，逐条对过全部已在 units/*/manifest.json 以同键登记），
点集拓扑讲义 458 键 / 高等代数 513 键同形（点集拓扑 old=0，契约对闸门完全隐形）。
跨 15 本 THREE_LEVEL 书普查：本修复 gained>=0 且 **lost=0**（不会让任何原本可解析
的键失效）。

断言：
  1. 单元：标签前缀键可解析；裸键行为不变；尾缀杂质/两段/纯标签仍返回 None。
  2. 复合键不因剥标签而把不同类型折叠（定义1.1.1 与 命题1.1.1 必须两把键）。
  3. 集成：契约以标签键登记的两条**不得**出现在 readable 残差里；真缺项仍要出现，
     闸门据真缺项 FAIL；--backfill 只回填真缺项，回填后闸门 PASS。
"""
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT_DIR = os.path.dirname(HERE)
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

_ROOT = HERE
while _ROOT != os.path.dirname(_ROOT) and not os.path.exists(os.path.join(_ROOT, "SKILL.md")):
    _ROOT = os.path.dirname(_ROOT)
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "lib"))
import lib.boot as boot
boot.setup()

import check_structure_completeness as csc
from verify_config import BookConfig, ORDINAL_THREE_LEVEL, ORDINAL_TWO_LEVEL

CH = 1
START, END = 1, 4

VERIFY_CONFIG = {
    "ordinal": [{"type": 3, "name": ["Proposition", "Definition"], "scope": 3}],
    "strict": True,
    "language": "en",
    "chapter_first": True,
}
CHAPTER_MAP = {"chapters": [{"chapter": CH, "start": START, "end": END}]}

# 印刷真值：1.1.1 / 1.1.2 已在契约（以内嵌标签键登记），1.1.3 是真缺项。
PAGES = {
    1: ["Proposition 1.1.1. Every hyperbolic toral automorphism has a dense "
        "set of periodic points."],
    2: ["Definition 1.1.2. A compact set S is locally maximal if S equals the "
        "intersection of its local stable and unstable manifolds."],
    3: ["Proposition 1.1.3. Shadowing holds for the shift on two symbols."],
}

CHAPTER = {
    "key": str(CH), "type": "chapter", "name": "1 First Examples",
    "page_start": START, "page_end": END,
    "sub_sec": [
        {"key": "命题1.1.1", "type": "proposition",
         "name": "命题1.1.1 1.1.1. Every hyperbolic toral automorphism",
         "page_start": 1, "page_end": 1, "sub_sec": []},
        {"key": "定义1.1.2", "type": "definition",
         "name": "定义1.1.2 1.1.2. A compact set S is locally maximal",
         "page_start": 2, "page_end": 2, "sub_sec": []},
    ],
}


def _fixture(tmp):
    ext = os.path.join(tmp, "_extract")
    os.makedirs(os.path.join(ext, "book_structure"), exist_ok=True)
    with open(os.path.join(ext, "verify_config.json"), "w", encoding="utf-8") as f:
        json.dump(VERIFY_CONFIG, f, ensure_ascii=False)
    with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump(CHAPTER_MAP, f, ensure_ascii=False)
    with open(os.path.join(ext, "book_structure", "ch%d.json" % CH),
              "w", encoding="utf-8") as f:
        json.dump(CHAPTER, f, ensure_ascii=False)
    for p, blocks in PAGES.items():
        with open(os.path.join(ext, "page_%03d.json" % p), "w", encoding="utf-8") as f:
            json.dump({"text": [{"text": b} for b in blocks]}, f)
    return ext


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("  ok: " + msg)


def test_unit_canon_key():
    k = csc._canon_key
    t = ORDINAL_THREE_LEVEL
    _assert(k(t, "命题1.1.2") == (1, 1, 2), "label-prefixed key parses (命题1.1.2)")
    _assert(k(t, "Proposition 1.1.2") == (1, 1, 2), "EN label-prefixed key parses")
    _assert(k(t, "1.1.2") == (1, 1, 2), "bare three-level key unchanged")
    _assert(k(t, "1.1-2") == (1, 1, 2), "dash separator still normalises")
    _assert(k(t, "Exercise 13.3.3*") is None,
            "trailing junk still rejected (no silent match)")
    _assert(k(t, "1.1") is None, "two-segment key is not three-level")
    _assert(k(t, "命题") is None, "label-only key yields no canon")
    _assert(k(ORDINAL_TWO_LEVEL, "定理1.2") == (1, 2), "TWO_LEVEL branch untouched")


def test_composite_keys_not_folded():
    a = csc._composite_key(ORDINAL_THREE_LEVEL, "Definition", (1, 1, 1))
    b = csc._composite_key(ORDINAL_THREE_LEVEL, "Proposition", (1, 1, 1))
    _assert(a != b, "stripping labels must not fold distinct types together: %r vs %r" % (a, b))


def main():
    test_unit_canon_key()
    test_composite_keys_not_folded()
    tmp = tempfile.mkdtemp(prefix="csc_label_prefix_")
    try:
        ext = _fixture(tmp)
        cfg = BookConfig.from_dict(VERIFY_CONFIG)
        bs = csc.BookStructure.load(ext)
        tree, contract_items, _secs = csc.load_contract(bs.find_chapter(CH))
        _assert(len(contract_items) == 2,
                "load_contract sees both label-prefixed contract nodes (got %s)"
                % sorted(contract_items))

        rdir = os.path.join(ext, "completeness_reports")
        rep = csc.check_chapter(ext, CH, START, END, cfg, backfill=False,
                                report_dir=rdir)
        st = {m["key"]: m["status"] for m in rep["missing_items"]}
        resid = rep["gate"]["residual_readable_items"]
        print("  statuses:", st, "| residual:", resid)
        _assert("命题1.1.1" not in resid and "定义1.1.2" not in resid,
                "label-prefixed contract items are NOT readable-missing (got %s)" % resid)
        _assert("1.1-3" in st and st["1.1-3"] == "readable",
                "genuinely missing item was scanned as readable (got %s)" % st)
        _assert(resid == ["1.1-3"],
                "exactly one real gap remains in the gate residual (got %s)" % resid)
        _assert(rep["gate"]["passed"] is False,
                "gate still FAILS on the real missing item (no over-relaxation)")

        rep2 = csc.check_chapter(ext, CH, START, END, cfg, backfill=True,
                                 report_dir=rdir)
        with open(os.path.join(ext, "book_structure", "ch%d.json" % CH),
                  encoding="utf-8") as f:
            keys = [n["key"] for n in json.load(f)["sub_sec"]]
        _assert(keys.count("命题1.1.1") == 1 and keys.count("定义1.1.2") == 1,
                "backfill did not duplicate the already-registered items (keys=%s)" % keys)
        _assert(any("1.1.3" in str(x) for x in keys),
                "real missing item was backfilled (keys=%s)" % keys)
        _assert(rep2["gate"]["passed"] is True,
                "post-backfill gate PASSES (residual=%s)" % rep2["gate"])
        print("\nALL THREE-LEVEL LABEL-PREFIX CHECKS PASSED")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
