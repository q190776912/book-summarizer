"""test_cleanup_scratch_guard.py — 主代理有限清理权的四条机械边界。

成因（用户裁定 2026-10-20）：Lehmann 收官轮主会话清理自己写的一次性探针脚本，
手写守卫脚本只判了「存在 + 是普通文件 + 在目录内」。本轮把该做法固化为
`tools/cleanup_scratch.py`，判据写进 `flows/_flow_gate.md` 禁止清单「主代理的有限清理权」。
负向必须成立的四类：通配 / 上跳子路径 / 保护名单文件（交付 md、OCR、契约、台账、回执）/
缺项 => **整批不删**（all-or-nothing），且删除后目标目录只剩留证回执。

Run with stdlib unittest:
    python tools/tests/test_cleanup_scratch_guard.py
"""
import os
import shutil
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import cleanup_scratch as cs

SCRATCH = ["_tmp_probe.py", "_tmp_probe_out.txt"]
PROTECTED = ["page_105.json", "Chapter1_1.1_x.md", "第1章_1.1_x.md", "manifest.json",
             "verify_config.json", "chapter_map.json", "repairs.json",
             "ignore_ch1.json", "_extraction_done.json", "_verify_all_round2.log",
             "_audit_after_errata.log", "_flow_status_final.txt"]


class CleanupScratchGuard(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="bks_cleanup_")
        for n in SCRATCH + PROTECTED:
            with open(os.path.join(self.dir, n), "w", encoding="utf-8") as f:
                f.write("x")
        os.mkdir(os.path.join(self.dir, "_tmp_sub"))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_happy_path_removes_only_whitelist_and_leaves_receipt(self):
        rc = cs.cleanup(self.dir, SCRATCH)
        self.assertEqual(rc, 0)
        for n in SCRATCH:
            self.assertFalse(os.path.exists(os.path.join(self.dir, n)), n)
        for n in PROTECTED:
            self.assertTrue(os.path.exists(os.path.join(self.dir, n)), n)
        receipts = [f for f in os.listdir(self.dir) if f.startswith("_cleanup_")]
        self.assertEqual(len(receipts), 1, receipts)
        text = open(os.path.join(self.dir, receipts[0]), encoding="utf-8").read()
        self.assertIn("removed=2 still_present=0", text)

    def test_missing_name_refuses_whole_batch(self):
        rc = cs.cleanup(self.dir, SCRATCH + ["_tmp_never_written.py"])
        self.assertEqual(rc, 2)
        for n in SCRATCH:
            self.assertTrue(os.path.exists(os.path.join(self.dir, n)),
                            "缺项必须导致整批不删：" + n)

    def test_wildcard_and_traversal_refused(self):
        for bad in ["_tmp_*.py", "..\\..\\x.py", "sub/_tmp_probe.py", "_tmp_sub"]:
            rc = cs.cleanup(self.dir, SCRATCH + [bad])
            self.assertEqual(rc, 2, bad)
            self.assertTrue(os.path.exists(os.path.join(self.dir, SCRATCH[0])), bad)

    def test_protected_names_refused_even_when_present(self):
        for bad in PROTECTED + ["_tmp_sub"]:
            rc = cs.cleanup(self.dir, [bad])
            self.assertEqual(rc, 2, bad)
            self.assertTrue(os.path.exists(os.path.join(self.dir, bad)), bad)

    def test_dry_run_touches_nothing(self):
        rc = cs.cleanup(self.dir, SCRATCH, dry_run=True)
        self.assertEqual(rc, 0)
        for n in SCRATCH:
            self.assertTrue(os.path.exists(os.path.join(self.dir, n)), n)
        self.assertEqual([f for f in os.listdir(self.dir) if f.startswith("_cleanup_")], [])

    def test_non_plain_file_refused(self):
        link_target = os.path.join(self.dir, SCRATCH[0])
        weird = os.path.join(self.dir, "_tmp_dir_like")
        os.mkdir(weird)
        ok, bad = cs.plan(self.dir, ["_tmp_dir_like"])
        self.assertEqual(ok, [])
        self.assertTrue(any("directory" in w for _, w in bad))
        self.assertTrue(os.path.exists(link_target))


if __name__ == "__main__":
    unittest.main(verbosity=2)
