# -*- coding: utf-8 -*-
"""2026-11-13 二轮审计回归：Q 层未配置阻断 + 三处「读失败不得降级空账本」。

旧行为：
  * Q 层 `formula=None` 且总结含 \\tag{} 时只往 stderr 打 WARN，结论仍 PASS
    （直接违反 verify.md:44「严禁宣称公式校验通过」）。
  * `_summary_has_tags` / `_load_done_index` 读文件失败返回 False / {}，
    后者在 `split_draft_units --force` 下会丢掉全部已 DONE 单元。
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
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from verify.script.base import DEFAULT_RESULT  # noqa: E402
from verify.script.report import print_result  # noqa: E402

_OK_STATS = {
    "units": 1, "expected": 1, "located": 1, "coverage": 100.0,
    "units_dir": "units", "unmeasurable": 0, "um_keys": [],
    "ambiguous": 0, "amb_keys": [], "unlocated": [],
}


def _load(alias, rel):
    path = os.path.join(_ROOT, rel)
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


def _run_report(**overrides):
    r = dict(DEFAULT_RESULT)
    r["md_order_stats"] = dict(_OK_STATS)
    r.update(overrides)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        status = print_result(r)
    return status, buf.getvalue()


class TestQUnconfiguredBlocks(unittest.TestCase):
    def test_unconfigured_blocks(self):
        status, out = _run_report(
            q_unconfigured=["总结含 \\tag{...} 但缺 formula 配置"])
        self.assertEqual(status, "FAIL")
        self.assertIn("Q-LAYER UNCONFIGURED", out)
        self.assertIn("1 q-unconfigured", out)

    def test_configured_stays_pass(self):
        status, out = _run_report(q_checked=True, q_unconfigured=[])
        self.assertEqual(status, "PASS")
        self.assertNotIn("Q-LAYER UNCONFIGURED", out)

    def test_legit_noop_without_formulas_stays_pass(self):
        """没有编号公式时 formula 缺失是正当 no-op，不得误阻断。"""
        status, out = _run_report(q_checked=False, q_unconfigured=[])
        self.assertEqual(status, "PASS")

    def test_default_result_has_the_key(self):
        self.assertIn("q_unconfigured", DEFAULT_RESULT)
        self.assertEqual(DEFAULT_RESULT["q_unconfigured"], [])


class TestReadFailureIsFailClosed(unittest.TestCase):
    def test_summary_has_tags_missing_md_raises(self):
        ft = _load("_test_formula_tag_mod",
                   "verify/formula_tag/script/formula_tag.py")
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(RuntimeError) as cm:
                ft._summary_has_tags(os.path.join(d, "missing.md"))
        self.assertIn("Q 层读取交付 md 失败", str(cm.exception))

    def test_done_index_bad_manifest_raises(self):
        try:
            sdu = _load("_test_split_units_mod",
                        "flows/write-source/script/split_draft_units.py")
        except Exception as e:  # pragma: no cover - optional heavy deps
            self.skipTest("split_draft_units import unavailable: %r" % (e,))
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "manifest.json"), "w",
                      encoding="utf-8") as f:
                f.write("{ broken json")
            with self.assertRaises(RuntimeError) as cm:
                sdu._load_done_index(d)
        self.assertIn("已 DONE 单元", str(cm.exception))

    def test_done_index_missing_file_is_empty(self):
        """文件不存在是合法首跑，仍返回 {}（不是放宽，是区分「不存在」与「读坏」）。"""
        try:
            sdu = _load("_test_split_units_mod2",
                        "flows/write-source/script/split_draft_units.py")
        except Exception as e:  # pragma: no cover
            self.skipTest("split_draft_units import unavailable: %r" % (e,))
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(sdu._load_done_index(d), {})


if __name__ == "__main__":
    unittest.main()
