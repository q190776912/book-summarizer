# -*- coding: utf-8 -*-
"""2026-11-12：规则15 接线 + U 层「无证据不得静音」+ V-F 根因 的判据测试。

背景：
  * `heading_sep` 由 F 层 emit，但 report.py / verify_chapter.py 从未读取 →
    规则15（标题下紧跟 `---` 永不合法）形同虚设，全库 336 个交付 md 违规。
  * U 层在契约/单元/manifest 缺失或 md 读失败时返回 `{}`，report.py 的
    `if md_st:` 把覆盖率整段静音 → 「没测」显示成「没问题」。
  * `merge_units` 的 V-F 状态机在父节标题后紧跟子节标题时仍插 `---`，
    自己生成的产物违反自己的规则15（根因）。
"""
import contextlib
import importlib.util
import io
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
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if os.path.join(_ROOT, "lib") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "lib"))
import lib.boot as _boot
_boot.setup()

from verify.script.base import DEFAULT_RESULT  # noqa: E402
from verify.script.report import print_result  # noqa: E402


def _load_module(alias, rel):
    """按显式路径加载，避开 `unit_order` 裸名撞 `lib/unit_order.py`。"""
    path = os.path.join(_ROOT, rel)
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


uo = _load_module("_test_u_layer", "verify/unit_order/script/unit_order.py")
mu = _load_module("_test_merge_units", "flows/write-source/script/merge_units.py")
fix = _load_module("_test_fix_sep", "verify/format_verify/script/fix_separator_spacing.py")


_OK_STATS = {
    "units": 3, "expected": 3, "located": 3, "coverage": 100.0,
    "units_dir": "units", "unmeasurable": 0, "um_keys": [],
    "ambiguous": 0, "amb_keys": [], "unlocated": [],
}


def _run_report(**overrides):
    r = dict(DEFAULT_RESULT)
    # DEFAULT_RESULT 的 md_order_stats 是 {}；U 层无证据闸现在是阻断的，
    # 故测试基线须显式给一份「测过且全覆盖」的正常账本。
    r["md_order_stats"] = dict(_OK_STATS)
    r.update(overrides)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        status = print_result(r)
    return status, buf.getvalue()


class TestHeadingSepIsLive(unittest.TestCase):
    def test_heading_sep_blocks(self):
        status, out = _run_report(heading_sep=["  x L9: `---` under heading"])
        self.assertEqual(status, "FAIL")
        self.assertIn("Heading separator", out)
        self.assertIn("F:1 F-layer-format", out)

    def test_no_heading_sep_stays_pass(self):
        status, out = _run_report(heading_sep=[])
        self.assertEqual(status, "PASS")
        self.assertNotIn("Heading separator", out)

    def test_fixer_rule_is_idempotent_and_spares_legal_separators(self):
        lines = ["## §1.1 A", "", "---", "", "### §1.1.1 B", "",
                 "Some prose.", "", "---", "", "## §1.2 C"]
        out1, n1 = fix._remove_heading_seps(lines)
        self.assertEqual(n1, 1)
        out2, n2 = fix._remove_heading_seps(out1)
        self.assertEqual(n2, 0)
        self.assertEqual(out1, out2)
        # 合法分隔线（散文与下一节标题之间）必须保留
        self.assertEqual(sum(1 for l in out1 if l.strip() == "---"), 1)


class TestUnitOrderNoEvidence(unittest.TestCase):
    def test_unmeasured_stats_shape(self):
        s = uo._unmeasured_stats("contract-or-units-missing")
        self.assertTrue(s["unmeasured"])
        self.assertEqual(s["coverage"], 0.0)
        self.assertEqual(s["expected"], 0)

    def test_unmeasured_blocks(self):
        status, out = _run_report(
            md_order_stats=uo._unmeasured_stats("units-manifest-empty"))
        self.assertEqual(status, "FAIL")
        self.assertIn("无证据", out)
        self.assertIn("1 u-layer-no-evidence", out)

    def test_empty_stats_also_blocks(self):
        """老结果 / 异常返回 {} 同样不得静音。"""
        status, out = _run_report(md_order_stats={})
        self.assertEqual(status, "FAIL")
        self.assertIn("无证据", out)

    def test_normal_stats_stays_pass(self):
        status, out = _run_report(md_order_stats=dict(_OK_STATS))
        self.assertEqual(status, "PASS")
        self.assertNotIn("无证据", out)
        self.assertIn("U-LAYER DELIVERED ORDER COVERAGE", out)

    def test_md_read_failure_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError) as cm:
                uo._delivered_order(d, 1, os.path.join(d, "missing.md"), {})
        self.assertIn("U 层读取交付 md 失败", str(cm.exception))


class TestVfStateMachine(unittest.TestCase):
    def test_no_sep_after_heading(self):
        self.assertFalse(mu._vf_section_sep_needed("heading", ["## §1 A", ""]))

    def test_sep_after_item_or_desc(self):
        self.assertTrue(mu._vf_section_sep_needed("item", ["body", ""]))
        self.assertTrue(mu._vf_section_sep_needed("desc", ["body", ""]))

    def test_no_sep_when_empty(self):
        self.assertFalse(mu._vf_section_sep_needed(None, []))

    def test_first_section_after_chapter_heading_needs_no_sep(self):
        # 章标题单元后紧跟第一个节标题：prev == "heading" → 不插
        self.assertFalse(mu._vf_section_sep_needed("heading", ["# Chapter 1", ""]))


if __name__ == "__main__":
    unittest.main()
