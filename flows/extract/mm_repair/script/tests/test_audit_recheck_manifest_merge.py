# -*- coding: utf-8 -*-
"""2026-11-12 回归：已完成书上跑 --recheck 不得清空 manifest 审计轨迹。

背景见 ``test_audit_recheck.py`` 与 audit 源码注释。实测（convex optimization，
573 页 / 1921 条 resolved / status=applied）：为修 p484 的高分错读而重跑
``audit --recheck``，旧实现从零构造 pages_out，只留下 1 条本轮 flagged，
1921 条 resolved 全部消失；且 ``_maybe_write_extraction_done`` 按
``m["pages"]`` 的键取「被 flag 页集合」，缩成 1 页后每页 mm 标记核对形同虚设。

本文件钉死三件纯函数行为：并回历史、同 key 以本轮为准、无新 flag 不打回状态。
"""
import os
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "flows", "extract", "mm_repair", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import mm_repair_audit as ma  # noqa: E402


def _e(key, resolved=True, **kw):
    d = {"key": key, "type": "text", "resolved": resolved,
         "current": "old-" + key}
    d.update(kw)
    return d


class TestMergePrevManifestPages(unittest.TestCase):
    def test_no_prev_is_noop(self):
        cur = {"003": {"entries": [_e("text:1", False)]}}
        self.assertIs(ma.merge_prev_manifest_pages(cur, None), cur)

    def test_resolved_history_preserved_on_unflagged_pages(self):
        prev = {"pages": {
            "003": {"sheet": "page_003_sheet.png", "entries": [_e("text:1")]},
            "007": {"sheet": "page_007_sheet.png", "entries": [_e("formula:2")]},
        }}
        cur = {}
        out = ma.merge_prev_manifest_pages(cur, prev)
        self.assertEqual(sorted(out), ["003", "007"])
        self.assertEqual(out["003"]["entries"][0]["key"], "text:1")
        self.assertTrue(out["003"]["entries"][0]["resolved"])
        self.assertEqual(out["003"]["sheet"], "page_003_sheet.png")
        self.assertEqual(out["003"]["count"], 1)

    def test_same_page_new_flag_wins_no_duplicate(self):
        prev = {"pages": {"484": {
            "sheet": "old_sheet.png",
            "entries": [_e("formula:32"), _e("text:30")],
        }}}
        new = {"484": {"sheet": "new_sheet.png", "count": 1, "entries": [
            {"key": "text:33", "type": "text", "resolved": False,
             "current": "10-8/20 ~ 0.4", "source": "recheck"},
        ]}}
        out = ma.merge_prev_manifest_pages(new, prev)
        keys = [e["key"] for e in out["484"]["entries"]]
        self.assertEqual(sorted(keys), ["formula:32", "text:30", "text:33"])
        self.assertEqual(len(keys), len(set(keys)))
        fresh = [e for e in out["484"]["entries"] if e["key"] == "text:33"][0]
        self.assertFalse(fresh["resolved"])
        self.assertEqual(fresh["current"], "10-8/20 ~ 0.4")
        self.assertEqual(fresh["source"], "recheck")
        self.assertEqual(out["484"]["count"], 3)
        self.assertEqual(out["484"]["sheet"], "new_sheet.png")

    def test_old_unresolved_not_silently_dropped(self):
        prev = {"pages": {"012": {"entries": [_e("text:5", False)]}}}
        out = ma.merge_prev_manifest_pages({}, prev)
        self.assertEqual(len(out["012"]["entries"]), 1)
        self.assertFalse(out["012"]["entries"][0]["resolved"])

    def test_prev_entries_are_copied_not_aliased(self):
        prev = {"pages": {"003": {"entries": [_e("text:1")]}}}
        out = ma.merge_prev_manifest_pages({}, prev)
        out["003"]["entries"][0]["resolved"] = False
        self.assertTrue(prev["pages"]["003"]["entries"][0]["resolved"])


class TestNextAuditStatus(unittest.TestCase):
    def test_idle_rerun_keeps_applied(self):
        self.assertEqual(ma.next_audit_status(0, "applied"), "applied")
        self.assertEqual(ma.next_audit_status(0, "partial"), "partial")

    def test_new_flag_goes_pending(self):
        self.assertEqual(ma.next_audit_status(1, "applied"), "pending")

    def test_fresh_book_without_prev(self):
        self.assertEqual(ma.next_audit_status(0, None), "none")


class TestPreservePrevManifestFields(unittest.TestCase):
    def test_inherits_stats_but_not_computed(self):
        prev = {"text_mode": "hybrid", "hybrid": True, "applied": 900,
                "status": "applied", "total_flagged": 1921,
                "pages": {"003": {"entries": []}}, "pdf": "OLD.pdf"}
        manifest = {"status": "pending", "total_flagged": 1,
                    "pages": {}, "pdf": "NEW.pdf"}
        out = ma.preserve_prev_manifest_fields(manifest, prev)
        self.assertEqual(out["text_mode"], "hybrid")
        self.assertTrue(out["hybrid"])
        self.assertEqual(out["applied"], 900)
        self.assertEqual(out["status"], "pending")
        self.assertEqual(out["total_flagged"], 1)
        self.assertEqual(out["pdf"], "NEW.pdf")


if __name__ == "__main__":
    unittest.main()
