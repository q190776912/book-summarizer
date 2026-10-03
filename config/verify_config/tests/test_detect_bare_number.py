# -*- coding: utf-8 -*-
"""test_detect_bare_number.py — `make_config.detect_bare_number` 探测器回归
（2026-10-02，用户裁定：bare_number 无默认值，改由**书页证据探测**代替硬编码 true 播种）。

探测器契约（三态，绝不静默兜底）：
  * True  —— 确有裸排公式号落点（`build_formula_patterns` 会 emit 裸变体、且关掉即漏收）；
  * False —— 公式号一律带括号/标签（开裸只把页码/表值/交叉引用收成幻影 MISSING，Lee/Apostol 型）；
  * None  —— 证据不足 / 落点混叠无明确优势 → 调用方**留空**，交 require_complete 挡下、
             agent 依书补定。
另有 **inert** 短路：单级书（ncomp=1）/ 字母·罗马章位书 / 未开 Q 层——`build_formula_patterns`
根本不 emit 裸变体，`bare_number` 对本抽取无作用，直接给可复核的显式起点 `True`（不改任何结果，
故不算静默默认）。

运行：
  python -m pytest config/verify_config/tests/test_detect_bare_number.py -q
"""
import os
import sys
import json
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

from make_config import detect_bare_number  # noqa: E402


def _mk_ext(blocks):
    """Fresh temp extract dir with the MM-repair marker + page_001.json holding
    `blocks` (list of {"text":..., "poly":...}). Returns (extract_dir, [page_path])."""
    ext = tempfile.mkdtemp(prefix="dbn_")
    with open(os.path.join(ext, "_extraction_done.json"), "w", encoding="utf-8") as f:
        json.dump({"done": True}, f)
    page = {"text": [{"text": t, "poly": [0, 0, 100, 0, 100, 20, 0, 20]} for t in blocks]}
    p = os.path.join(ext, "page_001.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(page, f)
    return ext, [p]


# ncomp>=2 digit-led two-component scheme (where the bare variant is actually on).
_T2 = {"type": 2}


class TestDetectorDecisions(unittest.TestCase):
    def test_bracket_only_returns_false(self):
        # Every formula-number slot is bracketed `(C.N)` with a clean tail; no bare
        # trailing numbers.  Enabling bare would only harvest prose noise -> False.
        ext, pages = _mk_ext(
            ["推导可得下述估计式 (%d.%d)." % (i // 10 + 1, i % 10 + 1)
             for i in range(40)])
        self.assertIs(detect_bare_number(ext, _T2, pages=pages), False)

    def test_bare_tagged_returns_true(self):
        # Every slot is a standalone bare `C.N` (no brackets) with a clean tail ->
        # True (disabling bare would drop real equation numbers).
        ext, pages = _mk_ext(
            ["两端同乘该算子后整理 %d.%d" % (i // 10 + 1, i % 10 + 1)
             for i in range(40)])
        self.assertIs(detect_bare_number(ext, _T2, pages=pages), True)

    def test_too_few_slots_returns_none(self):
        # Under _BARE_NUMBER_MIN_SLOT (20) -> indeterminate -> None (leave blank).
        ext, pages = _mk_ext(
            ["化简得结果 (%d.%d)." % (1, k) for k in range(1, 6)])
        self.assertIsNone(detect_bare_number(ext, _T2, pages=pages))

    def test_mixed_slots_no_clear_winner_returns_none(self):
        # 20 bracketed + 10 bare -> bare_frac ~= 0.33, between LO(0.1) and HI(0.5)
        # -> no confident call -> None (agent decides from the book).
        blocks = ["由引理可得 (%d.%d)." % (1, k) for k in range(1, 21)]
        blocks += ["整理上述结果后得到 %d.%d" % (2, k) for k in range(1, 11)]
        ext, pages = _mk_ext(blocks)
        self.assertIsNone(detect_bare_number(ext, _T2, pages=pages))


class TestDetectorInertShapes(unittest.TestCase):
    """Single-level / alpha-led / no-Q-layer shapes never emit the bare variant,
    so bare_number is inert -> a fixed reviewed True (not a silent default)."""

    def test_single_level_returns_true(self):
        # ncomp == 1 (type 1): bare variant never emitted -> inert True regardless
        # of page content.
        ext, pages = _mk_ext(["(7)", "(12) 单独整数号"] * 30)
        self.assertIs(detect_bare_number(ext, {"type": 1}, pages=pages), True)

    def test_letter_chapter_returns_true(self):
        # letter-led (type 2 + letter_ch True): bare `(A.3)` indistinguishable from
        # Fig./section headings -> never emitted -> inert True.
        ext, pages = _mk_ext(["引理给出界 (A.%d)" % k for k in range(1, 40)])
        self.assertIs(
            detect_bare_number(ext, {"type": 2, "letter_ch": True}, pages=pages),
            True)

    def test_no_formula_block_returns_true(self):
        self.assertIs(detect_bare_number("x", {"ignore": []}, pages=[]), True)

    def test_none_formula_cfg_returns_true(self):
        self.assertIs(detect_bare_number("x", None, pages=[]), True)


class TestDetectorGuard(unittest.TestCase):
    def test_missing_marker_returns_none(self):
        # MM-repair marker absent for a ncomp>=2 book -> unreliable scan -> None.
        ext = tempfile.mkdtemp(prefix="dbn_nomarker_")
        blocks = ["结果 (%d.%d)." % (1, k) for k in range(1, 40)]
        page = {"text": [{"text": t, "poly": [0, 0, 1, 0, 1, 1, 0, 1]} for t in blocks]}
        with open(os.path.join(ext, "page_001.json"), "w", encoding="utf-8") as f:
            json.dump(page, f)
        # NOTE: deliberately no _extraction_done.json marker.
        self.assertIsNone(
            detect_bare_number(ext, _T2, pages=[os.path.join(ext, "page_001.json")]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
