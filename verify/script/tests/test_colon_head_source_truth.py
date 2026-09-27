# -*- coding: utf-8 -*-
"""源侧真值扫描必须认识「冒号收尾条头」，否则闸门对全漏失明（Strogatz 3e，2026-09-27）。

根因：本书条头印刷成 `Example 2.2.1:`（标题在下一块）。`_S` 的「后继类」字符集
（编号之后允许出现的分隔符）不含 `:` / `：` → `en3_lf` 方案**整书失配** →
`scan_raw_items` 返回空 → B 层「源侧真值集」为空 → `missing_items: []` 恒真，
契约 items=0 也报 `gate.passed=true`（假绿），141 条例题全漏无人拦截。

判据：
  1. 冒号收尾条头须进入源侧真值集（正向）。
  2. 契约漏掉这些条目时闸门必须 FAIL（负向：真值集非空才谈得上拦闸）。
  3. 句点/空白尾形态不得因新增冒号而回归。

运行：
  python verify/script/tests/test_colon_head_source_truth.py
"""
import json
import os
import sys
import tempfile
import unittest
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

SCRIPT_DIR = os.path.join(_ROOT, "verify", "script")
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

import check_structure_completeness as csc   # noqa: E402
from verify_config import (ORDINAL_THREE_LEVEL,  # noqa: E402
                           BookConfig)


VERIFY_CONFIG = {
    "ordinal": [{"type": 3, "name": ["Example", "Definition", "Theorem"],
                 "scope": 1}],
    "strict": True,
    "language": "en",
    "chapter_first": True,
}


def _pages(d, pages):
    for p, lines in pages.items():
        blocks = [{"text": ln,
                   "poly": [60, 100 + 60 * i, 1100, 140 + 60 * i,
                            60, 140 + 60 * i, 60, 100 + 60 * i]}
                  for i, ln in enumerate(lines)]
        with open(os.path.join(d, "page_%03d.json" % p), "w", encoding="utf-8") as fh:
            json.dump({"text": blocks, "formulas": []}, fh)


COLON_PAGES = {1: ["2.1 A Geometric Way of Thinking",
                   "Example 2.1.1:",
                   "Investigate the flow near each fixed point of the equation.",
                   "Example 2.1.2:",
                   "Sketch the nullclines of the competing species model."]}
DOT_PAGES = {1: ["2.1 A Geometric Way of Thinking",
                 "Example 2.1.1. Investigate the flow near each fixed point.",
                 "Example 2.1.2. Sketch the nullclines of the model."]}


class TestColonHeadTruth(unittest.TestCase):
    def test_colon_terminated_heads_enter_truth_set(self):
        with tempfile.TemporaryDirectory() as d:
            _pages(d, COLON_PAGES)
            got = csc.scan_raw_items(d, 2, 1, 1,
                                     primary_type=ORDINAL_THREE_LEVEL,
                                     chapter_first=True, language="en")
        keys = sorted(c["key"] for c in got)
        self.assertEqual(keys, ["2.1-1", "2.1-2"],
                         "冒号收尾条头必须进入源侧真值集（空集 = 闸门失明）")

    def test_dot_terminated_heads_still_scanned(self):
        with tempfile.TemporaryDirectory() as d:
            _pages(d, DOT_PAGES)
            got = csc.scan_raw_items(d, 2, 1, 1,
                                     primary_type=ORDINAL_THREE_LEVEL,
                                     chapter_first=True, language="en")
        self.assertEqual(sorted(c["key"] for c in got), ["2.1-1", "2.1-2"])

    def test_empty_contract_on_colon_pages_does_not_gate_pass(self):
        """负向：契约一条不录时闸门必须拦（修复前真值集为空 → 假绿放行）。"""
        chapter = {"key": "2", "type": "chapter", "name": "2 Flows on the Line",
                   "page_start": 1, "page_end": 1,
                   "sub_sec": [{"key": "2.1", "type": "section",
                                "name": "2.1 A Geometric Way of Thinking",
                                "page_start": 1, "page_end": 1, "sub_sec": []}]}
        cfg = BookConfig.from_dict(VERIFY_CONFIG)
        with tempfile.TemporaryDirectory() as d:
            ext = os.path.join(d, "_extract")
            os.makedirs(os.path.join(ext, "book_structure"))
            with open(os.path.join(ext, "verify_config.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(VERIFY_CONFIG, fh, ensure_ascii=False)
            with open(os.path.join(ext, "book_structure", "ch2.json"), "w",
                      encoding="utf-8") as fh:
                json.dump(chapter, fh, ensure_ascii=False)
            _pages(ext, COLON_PAGES)
            rep = csc.check_chapter(ext, 2, 1, 1, cfg, backfill=False,
                                    report_dir=os.path.join(ext, "reports"))
        st = {str(m["key"]): m["status"] for m in rep["missing_items"]}
        self.assertIn("2.1-1", st)
        self.assertIn("2.1-2", st)
        self.assertFalse(rep["gate"]["passed"],
                         "漏录冒号条头时闸门不得假绿：%s" % rep["gate"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
