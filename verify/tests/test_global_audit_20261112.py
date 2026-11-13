# -*- coding: utf-8 -*-
"""2026-11-12 skill 全局审计回归：fail-closed / 状态不可洗白 / 无重复定义。

覆盖本轮修复中可纯函数化的判据（其余为 CLI 级改动，由全库 A/B 兜底）：
  * mm_repair_audit.load_prev_manifest：manifest 读失败不得静默降级为「无历史」
  * mm_repair_audit.next_audit_status：并回的 unresolved 历史不得沿用 applied
  * make_summary.parse_pass：损坏值不得洗成「未校验」
  * preflight.print_preflight：tags_outside 必须让 all_ok=False
  * audit_counts.main：空 md + 空书侧必须 BLOCKED(2)，不得 PASS(0)
  * 静态不变量：非 tests 模块不得有同作用域重复顶层定义；9 层注册必须齐全
"""
import ast
import collections
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

import mm_repair_audit as ma  # noqa: E402
import make_summary  # noqa: E402
import audit_counts  # noqa: E402
import preflight  # noqa: E402


class TestLoadPrevManifest(unittest.TestCase):
    def test_missing_file_is_no_history(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(ma.load_prev_manifest(os.path.join(d, "nope.json")),
                             (set(), None))

    def test_bom_manifest_loads(self):
        doc = {"status": "applied", "pages": {"003": {"entries": [
            {"key": "text:1", "resolved": True},
            {"key": "text:2", "resolved": False}]}}}
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "manifest.json")
            with open(p, "wb") as f:
                f.write(b"\xef\xbb\xbf" + json.dumps(doc).encode("utf-8"))
            resolved, prev = ma.load_prev_manifest(p)
        self.assertEqual(resolved, {"003:text:1"})
        self.assertEqual(prev["status"], "applied")

    def test_corrupt_manifest_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "manifest.json")
            with open(p, "w", encoding="utf-8") as f:
                f.write("{ not json")
            with self.assertRaises(RuntimeError) as cm:
                ma.load_prev_manifest(p)
        self.assertIn("拒绝从零重建", str(cm.exception))


class TestNextAuditStatus(unittest.TestCase):
    def test_new_flag_pending(self):
        self.assertEqual(ma.next_audit_status(1, "applied"), "pending")

    def test_clean_history_keeps_applied(self):
        pages = {"003": {"entries": [{"key": "text:1", "resolved": True}]}}
        self.assertEqual(ma.next_audit_status(0, "applied", pages), "applied")

    def test_unresolved_history_is_partial_not_applied(self):
        pages = {"003": {"entries": [{"key": "text:1", "resolved": True},
                                     {"key": "text:2", "resolved": False}]}}
        self.assertEqual(ma.next_audit_status(0, "applied", pages), "partial")

    def test_fresh_book_no_prev(self):
        self.assertEqual(ma.next_audit_status(0, None, {}), "none")


class TestParsePass(unittest.TestCase):
    def test_normal_and_unknown(self):
        self.assertEqual(make_summary.parse_pass("12/12"), (12, 12))
        self.assertEqual(make_summary.parse_pass("?"), (None, None))
        self.assertEqual(make_summary.parse_pass(None), (None, None))

    def test_corrupt_is_invalid_not_unverified(self):
        self.assertEqual(make_summary.parse_pass("12/abc"), ("INVALID", "INVALID"))
        self.assertEqual(make_summary.parse_pass("junk"), ("INVALID", "INVALID"))


class TestPreflightGate(unittest.TestCase):
    def test_tags_outside_blocks(self):
        pf = {"balanced": True, "tags_outside": ["1.1"], "fences": 2,
              "blocks": 1, "tags_total": 1, "tags_in": 0,
              "escaped": 0, "collapsed": 0}
        with mock.patch.object(preflight, "preflight_md", return_value=pf):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertFalse(preflight.print_preflight(["x.md"]))

    def test_balanced_without_outside_stays_ok(self):
        pf = {"balanced": True, "tags_outside": [], "fences": 2,
              "blocks": 1, "tags_total": 1, "tags_in": 1,
              "escaped": 0, "collapsed": 0}
        with mock.patch.object(preflight, "preflight_md", return_value=pf):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertTrue(preflight.print_preflight(["x.md"]))


class TestAuditCountsNoEvidence(unittest.TestCase):
    def test_empty_both_sides_is_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            md = os.path.join(d, "empty.md")
            open(md, "w", encoding="utf-8").write("")
            ext = os.path.join(d, "ext")
            os.makedirs(ext)
            argv = ["audit_counts.py", "1", "1", "2", md, ext]
            with mock.patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaises(SystemExit) as cm:
                        audit_counts.main()
        self.assertEqual(cm.exception.code, 2)


class TestStaticInvariants(unittest.TestCase):
    def test_no_duplicate_top_level_definitions(self):
        """后者静默覆盖前者是 F811 类真缺陷，2026-11-12 已清零两处。"""
        root = Path(_ROOT)
        dups = []
        skip = {"__pycache__", ".git", "node_modules", ".pytest_cache", ".ruff_cache"}
        for p in root.rglob("*.py"):
            if any(part in skip or part == "tests" for part in p.parts):
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8-sig"))
            except (SyntaxError, UnicodeDecodeError):
                continue

            def walk(node, where):
                names = collections.defaultdict(list)
                for ch in ast.iter_child_nodes(node):
                    if isinstance(ch, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        names[ch.name].append(ch.lineno)
                    elif isinstance(ch, (ast.If, ast.Try, ast.For, ast.While, ast.With)):
                        walk(ch, where)
                for n, lines in names.items():
                    if len(lines) > 1:
                        dups.append((str(p.relative_to(root)), n, lines))
            walk(tree, "module")
        self.assertEqual(dups, [], "同作用域重复定义: %s" % (dups[:5],))

    def test_all_nine_layers_registered(self):
        import register_all
        codes = set(register_all.LAYER_REGISTRY.by_code())
        self.assertEqual(codes, {"EXTRACT", "D", "B", "E", "F", "O", "P", "Q", "U"})


if __name__ == "__main__":
    unittest.main()
