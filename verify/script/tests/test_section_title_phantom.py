"""Regression test: 节题伪装豁免（section_title）。

形态（Apostol《Introduction to Analytic Number Theory》ch5 §5.1 实测，2026-09-28）：
两级英文书里小节标题行「5.1 Definition and basic properties of …」被**数字前置**
方案 ``en2_nf`` 当成条头（label 从标题首词抓来 → 伪候选 ``Definition 5.1``），
而契约里同一序标**本来就是 section 节点**。旧逻辑判 readable → 闸门死锁，
``--backfill`` 还会在契约里造出幽灵「定义5.1」。

豁免判据：候选来自 ``*_nf`` 方案且带 label，且其 snippet 归一文本与契约里
**同序标小节**的标题互为前缀。

断言：
  1. dry-run：节题伪装「Definition 5.1」status=section_title（不拦闸）；
     同号但文本不符的真条头「Definition 5.3」仍 readable（不得吞真缺项）；
     真缺项「定理5.3」仍 readable。
  2. backfill：只回填真缺项；「Definition 5.1」绝不入契约；再跑 gate PASS。
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

CH = 5
START, END = 118, 120

VERIFY_CONFIG = {
    "ordinal": [
        {"type": 2, "name": ["Theorem"], "scope": 2},
        {"type": 2, "name": ["Definition"], "scope": 2},
    ],
    "strict": True,
    "language": "en",
    "chapter_first": True,
}
CHAPTER_MAP = {"chapters": [{"chapter": CH, "start": START, "end": END}]}

# 印刷真值：§5.1 标题首词恰为 Definition（伪装源），§5.3 标题与 Definition
# 无关（真条头同号不同文，不得被豁免吞掉）；定理5.3 是契约真缺项。
# 🔴 定理5.3 的页码排在 定理5.4（p119）之后（旧夹具放在 p120）会被
# `check_contract_anchors`（回填后锚点自洽闸）与 B 层「顺序错乱」双向夹住——
# 序标 5.3 晚于 5.4 印刷在真实书里不存在（章内共享计数器恒随页码递增），
# 那正是新闸要拦的形态；故夹具把真缺条头挪到它编号应有的页位。
PAGES = {
    118: [
        "5.1 Definition and basic properties of the zeta function",
        "Theorem 5.1. The series for zeta converges.",
        "5.2 Residue classes and complete residue systems",
        "Theorem 5.2. A congruence has a solution iff.",
    ],
    119: [
        "5.3 Linear congruences",
        "Theorem 5.3. Third theorem, genuinely absent from the contract.",
        "5.3 Definition of a reduced residue system, genuinely printed here.",
        "Theorem 5.4. Wilson's theorem.",
    ],
    120: [
        "A closing paragraph without any labelled head.",
    ],
}

CHAPTER = {
    "key": str(CH), "type": "chapter", "name": "5 Elementary theory of congruences",
    "page_start": START, "page_end": END,
    "sub_sec": [
        {"key": "5.1", "type": "section", "name": "5.1 Definition and basic properties of",
         "page_start": 118, "page_end": 120,
         "sub_sec": [
             {"key": "定理5.1", "type": "theorem", "name": "Theorem 5.1",
              "page_start": 118, "page_end": 118, "sub_sec": []},
         ]},
        {"key": "5.2", "type": "section", "name": "5.2 Residue classes and complete residue",
         "page_start": 118, "page_end": 119,
         "sub_sec": [
             {"key": "定理5.2", "type": "theorem", "name": "Theorem 5.2",
              "page_start": 118, "page_end": 118, "sub_sec": []},
         ]},
        {"key": "5.3", "type": "section", "name": "5.3 Linear congruences",
         "page_start": 119, "page_end": 120, "sub_sec": []},
        {"key": "5.4", "type": "section", "name": "5.4 Reduced residue systems and the",
         "page_start": 119, "page_end": 120,
         "sub_sec": [
             {"key": "定理5.4", "type": "theorem", "name": "Theorem 5.4",
              "page_start": 119, "page_end": 119, "sub_sec": []},
         ]},
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


def _all_keys(node):
    ks = set()

    def walk(n):
        ks.add(str(n.get("key")))
        for c in n.get("sub_sec") or []:
            walk(c)
    walk(node)
    return ks


def main():
    tmp = tempfile.mkdtemp(prefix="csc_section_title_")
    try:
        ext = _fixture(tmp)
        cfg = BookConfig.from_dict(VERIFY_CONFIG)
        rdir = os.path.join(ext, "completeness_reports")

        rep = csc.check_chapter(ext, CH, START, END, cfg, backfill=False,
                               report_dir=rdir)
        st = {m["key"]: m["status"] for m in rep["missing_items"]}
        print("  missing statuses:", st)
        # 前提：节题伪装确实以 *_nf 候选出现，否则本测试失去意义
        _assert(st.get("Definition 5.1") == "section_title",
                "section-title impostor 'Definition 5.1' exempted as section_title (got %s)"
                % st.get("Definition 5.1"))
        _assert("Definition 5.1" not in rep["gate"]["residual_readable_items"],
                "exempted impostor does not block the gate")
        _assert(st.get("Definition 5.3") == "readable",
                "same-ordinal real item head with different text stays readable (got %s)"
                % st.get("Definition 5.3"))
        _assert(st.get("Theorem 5.3") == "readable",
                "genuinely missing Theorem 5.3 still flagged readable (got %s)"
                % st.get("Theorem 5.3"))
        _assert(rep["gate"]["passed"] is False,
                "dry-run gate still FAILS due to real missing Theorem 5.3")

        rep2 = csc.check_chapter(ext, CH, START, END, cfg, backfill=True,
                                report_dir=rdir)
        bf = {str(x.get("key") if isinstance(x, dict) else x)
              for x in rep2.get("backfilled_items") or []}
        _assert(not any(k.startswith("Definition 5.1") or k.endswith("定义5.1")
                        for k in bf),
                "phantom 'Definition 5.1' must NEVER be backfilled (got %s)" % bf)
        with open(os.path.join(ext, "book_structure", "ch%d.json" % CH),
                  encoding="utf-8") as f:
            keys = _all_keys(json.load(f))
        _assert(not any("5.1" in k and "定义" in k for k in keys),
                "contract has no phantom 定义5.1 (keys=%s)" % sorted(keys))
        _assert("定理5.3" in keys, "real missing 定理5.3 was backfilled")
        _assert(rep2["gate"]["passed"] is True,
                "post-backfill gate PASSES (residual=%s)" % rep2["gate"])
        print("\nALL SECTION-TITLE PHANTOM CHECKS PASSED")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
