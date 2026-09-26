"""Regression test: 字母后缀序标 OCR 形近豁免（suffix_confusion）。

形态（do Carmo《Differential Geometry of Curves and Surfaces》ch5 §5-2 实测，
2026-09-26）：印刷「THEOREM 1b」的尾字母被抽取器按形近折成数字（b→8），源侧扫描
产出伪候选 canon=(18,) 键「定理18」；而契约真身「定理1b」因 `_canon_key` 不接受
尾字母必然缺席 contract_items → 假 readable 缺项、闸门死锁，--backfill 还会把
幽灵「定理18」写进契约。豁免判据三重（snippet 印着 数字+尾字母 / 候选编号恰等于
形近折叠值 / 契约裸键有同号同尾字母项）。

断言：
  1. dry-run：伪候选「定理18」status=suffix_confusion（不拦闸）；真缺项「定理3」
     仍 status=readable（豁免不得吞真缺项）。
  2. backfill：只回填「定理3」；「定理18」绝不入契约；再跑 gate PASS。
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

import check_structure_completeness as csc
from verify_config import BookConfig

CH = 1
START, END = 1, 4

VERIFY_CONFIG = {
    "ordinal": [{"type": 1, "name": ["Theorem"], "scope": 3}],
    "strict": True,
    "language": "en",
    "chapter_first": True,
}
CHAPTER_MAP = {"chapters": [{"chapter": CH, "start": START, "end": END}]}

# 印刷真值：定理1 / 定理2 / 定理3 / 定理1b（后缀）。契约缺定理3、且真身以
# 尾字母键「定理1b」登记（_canon_key 无 int canon → contract_items 必然缺席）。
# 🔴 1b 必须排在递增数字之后：抽取器把 1b 折成 18 后，比 18 小的后续号会被
# 「编号倒退」规则丢弃（en_single 章级单调计数器），真缺项将不被扫出。
PAGES = {
    1: ["THEOREM 1. First statement about curves."],
    2: ["THEOREM 2. Second statement."],
    3: ["THEOREM 3. Third statement, genuinely absent from the contract."],
    4: ["THEOREM 1b. Let S be a regular, compact, and connected surface"],
}

CHAPTER = {
    "key": str(CH), "type": "chapter", "name": "1 Test Chapter",
    "page_start": START, "page_end": END,
    "sub_sec": [
        {"key": "定理1", "type": "theorem", "name": "定理1 1. First statement",
         "page_start": 1, "page_end": 1, "sub_sec": []},
        {"key": "定理2", "type": "theorem", "name": "定理2 2. Second statement",
         "page_start": 2, "page_end": 2, "sub_sec": []},
        {"key": "定理1b", "type": "theorem", "name": "定理1b 1b. Let S be",
         "page_start": 4, "page_end": 4, "sub_sec": []},
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
        with open(os.path.join(ext, "page_%03d.json" % p), "w",
                  encoding="utf-8") as f:
            json.dump({"text": [{"text": b} for b in blocks]}, f)
    return ext


def _assert(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("  ok: " + msg)


def main():
    tmp = tempfile.mkdtemp(prefix="csc_suffix_confusion_")
    try:
        ext = _fixture(tmp)
        cfg = BookConfig.from_dict(VERIFY_CONFIG)
        rdir = os.path.join(ext, "completeness_reports")

        rep = csc.check_chapter(ext, CH, START, END, cfg, backfill=False,
                                report_dir=rdir)
        st = {m["key"]: m["status"] for m in rep["missing_items"]}
        print("  missing statuses:", st)
        # 伪候选（1b 折成 18）——前提：源侧确实以形近号出现，否则本测试失去意义
        _assert(st.get("定理18") == "suffix_confusion",
                "mangled candidate 定理18 exempted as suffix_confusion (got %s)"
                % st.get("定理18"))
        _assert(st.get("定理3") == "readable",
                "genuinely missing 定理3 still flagged readable (got %s)"
                % st.get("定理3"))
        _assert("定理18" not in rep["gate"]["residual_readable_items"],
                "exempted item does not block the gate")
        _assert(rep["gate"]["passed"] is False,
                "dry-run gate still FAILS due to real missing 定理3")

        rep2 = csc.check_chapter(ext, CH, START, END, cfg, backfill=True,
                                 report_dir=rdir)
        bf = {str(x) for x in rep2.get("backfilled_items") or []}
        _assert(not any("18" in x for x in bf),
                "phantom 定理18 must NEVER be backfilled (got %s)" % bf)
        with open(os.path.join(ext, "book_structure", "ch%d.json" % CH),
                  encoding="utf-8") as f:
            keys = {n["key"] for n in json.load(f)["sub_sec"]}
        _assert("定理18" not in keys, "contract has no phantom 定理18 (keys=%s)" % keys)
        _assert("定理3" in keys, "real missing 定理3 was backfilled")
        _assert(rep2["gate"]["passed"] is True,
                "post-backfill gate PASSES (residual=%s)" % rep2["gate"])
        print("\nALL SUFFIX-CONFUSION EXEMPTION CHECKS PASSED")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
