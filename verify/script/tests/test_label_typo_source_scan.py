"""Regression test: 类型词 OCR 形近补救（_label_typo_normalize）。

形态（Apostol《Introduction to Analytic Number Theory》ch2 实测 2026-09-28）：
印刷「Theorem 2.7 For all f we have I * f = f * I = f.」被 OCR 读成
「Theorerm 2.7 …」，抽取器与源侧扫描的类型词正则同时失配 → 该条既不入契约、
也不在源侧候选集，差集为空，闸门只剩 B 层「序列 1..27 缺号 7」死锁。

判据四重（宁缺毋滥）：块首 ≥5 字母纯字母词 / 非词表正字也非正字复数形 /
与词表**恰好一个**类型词编辑距离恰为 1 / 其后紧跟条目序标数字。

断言：
  1. 正例：「Theorerm 2.7 …」归一为「Theorem 2.7 …」，scan_raw_items 产出该候选，
     端到端 dry-run 里 status=readable（回填通道打开）。
  2. 负例：复数形（"Theorems 2.7 and 2.8 …"）、无序标散文（"These 2.7 …"、
     "Definition of the …"）、非近似词（"Chapter 2.7 …"）、以及**已是正字**的行
     一律不改写；正字候选集的条数不因本机制改变（零回徒）。
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
ROOT = os.path.dirname(os.path.dirname(SCRIPT_DIR))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import check_structure_completeness as csc
from verify_config import BookConfig

CH = 2
START, END = 42, 44

VERIFY_CONFIG = {
    "ordinal": [{"type": 2, "name": ["Theorem"], "scope": 2}],
    "strict": True,
    "language": "en",
    "chapter_first": True,
}
CHAPTER_MAP = {"chapters": [{"chapter": CH, "start": START, "end": END}]}

PAGES = {
    42: [
        "Theorem 2.1 The function 1 is completely multiplicative.",
        "Theorem 2.2 The function mu is multiplicative.",
        "Theorem 2.3 If f is multiplicative so is its divisor sum.",
        "Theorem 2.4 A convolution identity for phi.",
        "Theorem 2.5 The Möbius inversion formula.",
        "Theorem 2.6 Uniqueness of the inverse under convolution.",
        "Theorerm 2.7 For all f we have I * f = f * I = f.",
        "Theorem 2.8 If f is an arithmetical function with f(1) not 0.",
        "Theorems 2.7 and 2.8 are stated in section 2.12.",
        "These 2.7 lines of prose are not an item head at all.",
        "Chapter 2.7 never names a theorem type.",
        "Definition of the Dirichlet convolution comes first here.",
    ],
    43: ["2.12 Applications of the convolution theorems of section 2."],
    44: ["Theorem 2.9 A third real theorem head, printed correctly."],
}

CHAPTER = {
    "key": str(CH), "type": "chapter", "name": "2 Multiplicative functions",
    "page_start": START, "page_end": END,
    "sub_sec": [
        {"key": "定理2.%d" % i, "type": "theorem", "name": "Theorem 2.%d" % i,
         "page_start": 42, "page_end": 42, "sub_sec": []}
        for i in range(1, 7)
    ] + [
        {"key": "定理2.8", "type": "theorem", "name": "Theorem 2.8",
         "page_start": 42, "page_end": 42, "sub_sec": []},
        {"key": "定理2.9", "type": "theorem", "name": "Theorem 2.9",
         "page_start": 44, "page_end": 44, "sub_sec": []},
    ],
}


def _fixture(tmp):
    ext = os.path.join(tmp, "_extract")
    os.makedirs(os.path.join(ext, "book_structure"), exist_ok=True)
    for name, obj in (("verify_config.json", VERIFY_CONFIG),
                      ("chapter_map.json", CHAPTER_MAP),
                      (os.path.join("book_structure", "ch%d.json" % CH), CHAPTER)):
        with open(os.path.join(ext, name), "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
    for p, blocks in PAGES.items():
        with open(os.path.join(ext, "page_%03d.json" % p), "w",
                  encoding="utf-8") as f:
            json.dump({"text": [{"text": b} for b in blocks]}, f)
    return ext


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("  ok: " + msg)


def test_helper():
    n = csc._label_typo_normalize
    _assert(n("Theorerm 2.7 For all f we have I * f = f * I = f.").startswith("Theorem 2.7"),
            "mangled label 'Theorerm 2.7' normalized to 'Theorem 2.7'")
    _assert(n("Lerma 5.1 The additive group of integers").startswith("Lemma 5.1"),
            "one-letter-substitution label 'Lerma 5.1' normalized to 'Lemma 5.1'")
    _assert(n("Theorems 2.7 and 2.8 are stated in section 2.12.") is None,
            "plural label form (cross-reference / running head) never rewritten")
    _assert(n("These 2.7 lines of prose are not an item head at all.") is None,
            "prose word near an ordinal but distant from every label not rewritten")
    _assert(n("Chapter 2.7 never names a theorem type.") is None,
            "non-label word not rewritten")
    _assert(n("Definition of the Dirichlet convolution comes first here.") is None,
            "label word without an ordinal right after it not rewritten")
    _assert(n("Theorem 2.8 If f is an arithmetical function") is None,
            "already-correct label left untouched (zero regression on clean books)")
    _assert(n("2.7 For all f we have I * f") is None,
            "number-first text has no leading word to fix")
    _assert(n("") is None and n(None) is None,
            "empty input returns None (fail-open)")


def test_scan_and_gate():
    tmp = tempfile.mkdtemp(prefix="csc_label_typo_")
    try:
        ext = _fixture(tmp)
        cfg = BookConfig.from_dict(VERIFY_CONFIG)
        raw = csc.scan_raw_items(ext, CH, START, END, cfg.primary_type,
                                cfg.chapter_first, cfg.language,
                                groups=getattr(cfg, "ordinal", None))
        keys = sorted(str(it["key"]) for it in raw)
        print("  raw keys:", keys)
        _assert("Theorem 2.7" in keys,
                "typo'd head surfaces as source candidate 'Theorem 2.7'")
        _assert("Theorems 2.7" not in keys and not any(
            k.startswith("Theorem 2.7") and k != "Theorem 2.7" for k in keys),
            "no plural/prose impostor candidate collected")
        _assert(keys.count("Theorem 2.8") == 1 and keys.count("Theorem 2.9") == 1,
                "correctly printed heads collected exactly once each")

        rdir = os.path.join(ext, "completeness_reports")
        rep = csc.check_chapter(ext, CH, START, END, cfg, backfill=False,
                                report_dir=rdir)
        st = {m["key"]: m["status"] for m in rep["missing_items"]}
        _assert(st.get("Theorem 2.7") == "readable",
                "end-to-end: typo'd head is a readable missing item, "
                "opening the backfill channel (got %s)" % st.get("Theorem 2.7"))
        _assert(rep["gate"]["passed"] is False,
                "dry-run gate still FAILS while 定理2.7 is absent from the contract")

        rep2 = csc.check_chapter(ext, CH, START, END, cfg, backfill=True,
                                 report_dir=rdir)
        with open(os.path.join(ext, "book_structure", "ch%d.json" % CH),
                  encoding="utf-8") as f:
            keys2 = {str(n["key"]) for n in json.load(f)["sub_sec"]}
        _assert("定理2.7" in keys2,
                "backfill writes 定理2.7 into the contract (keys=%s)" % sorted(keys2))
        _assert(rep2["gate"]["passed"] is True,
                "post-backfill gate PASSES (residual=%s)" % rep2["gate"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    test_helper()
    test_scan_and_gate()
    print("\nALL LABEL-TYPO SOURCE-SCAN CHECKS PASSED")
