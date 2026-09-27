# -*- coding: utf-8 -*-
"""冒号收尾条头不得被「无字母即拒」吃掉（Strogatz 3e，2026-09-27）。

根因：本书条头印刷形态是 `Example 2.2.1:`，标题/正文在**下一个 OCR 块**——抽取器
`_EN3_REST_OK` 看到编号后的 rest 只剩一个冒号，被「rest 无字母即拒」（本行原为拦
断行引用尾 `Example 1.2.8.`）整书拒绝 → 全书 141 条例题全漏，且因源侧真值集同样
失明（见 verify 侧同名修复）闸门一路假绿。

判据：冒号与句点同为条头终止符，剥掉后按「空尾」放行；但断行引用尾
（`…see Example 1.2.8.` 之后只剩标点/括号）仍须被拒。

运行：
  python flows/write-source/structure/script/tests/test_colon_terminated_item_head.py
"""
import json
import os
import re
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

_SCRIPT = os.path.join(_ROOT, "flows", "write-source", "structure", "script")
if _SCRIPT not in sys.path:
    sys.path.insert(0, _SCRIPT)
import extract_items_en3 as ee       # noqa: E402


def _ok(line):
    """按抽取器主条头正则匹配一次，再跑判别函数。"""
    m = re.search(r'\b(' + ee.EN3_LABEL_ALT + r')s?(?![A-Za-z])\s*([0-9]+\.[0-9]+\.[0-9]+)',
                  line, re.IGNORECASE)
    return bool(m) and ee._EN3_REST_OK(line, m)


class TestColonHead(unittest.TestCase):
    def test_colon_terminated_head_accepted(self):
        for line in ("Example 2.2.1:", "Definition 2.1.3:", "Theorem 6.8.6:",
                     "Example 2.2.1\uff1a"):
            self.assertTrue(_ok(line), "%r 是印刷条头，必须放行" % line)

    def test_full_width_colon_with_title(self):
        self.assertTrue(_ok("Example 3.1.1\uff1a Bifurcation in the logistic equation"))

    def test_head_with_title_after_colon(self):
        self.assertTrue(_ok("Example 2.2.1: The overdamped harmonic oscillator"))

    def test_wrapped_paren_ref_tail_still_rejected(self):
        # 回归护栏：修复只针对冒号尾，下列引用尾形态不得放行。
        self.assertFalse(_ok("Example 1.2.8."))          # 断行引用尾（纯标点）
        self.assertFalse(_ok("Definition 5.1.1)"))       # 括号包裹引用
        self.assertFalse(_ok("Remark 5.1.2(a) that they"))


class TestExtractorEndToEnd(unittest.TestCase):
    def test_colon_heads_captured(self):
        pages = [
            ["Example 2.1.1:", "Investigate the flow determined by the sign of f."],
            ["Example 2.2.2:", "The overdamped harmonic oscillator has no fixed point."],
        ]
        with tempfile.TemporaryDirectory() as d:
            for i, blocks in enumerate(pages, start=1):
                json.dump({"text": [{"text": t,
                                     "poly": [60, 100 + 60 * j, 1100, 140 + 60 * j,
                                              60, 140 + 60 * j, 60, 100 + 60 * j]}
                                    for j, t in enumerate(blocks)],
                           "formulas": []},
                          open(os.path.join(d, "page_%03d.json" % i), "w",
                               encoding="utf-8"))
            items = ee.extract_items_en3(d, 2, 1, 2, want_examples=True)
        keys = {it["key"] for it in items}
        self.assertIn("Example 2.1.1", keys)
        self.assertIn("Example 2.2.2", keys)


if __name__ == "__main__":
    unittest.main(verbosity=2)
