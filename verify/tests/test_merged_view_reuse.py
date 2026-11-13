# -*- coding: utf-8 -*-
"""2026-11-12：临时章视图按语言复用 + 退出统一清理（safe-delete 闸门根治）。

旧实现每组新建并删除 `._verify_merged_ch{N}_{lang}.md`；52 章的书在单条命令内
累计 ~100 次删除，触发宿主 50 次批量删除确认墙，verify 中途退出、日志无 PASS 行。
"""
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
import lib.boot as _boot  # noqa: E402
_boot.setup()

from verify.script import verify_chapter as vc  # noqa: E402


class TestMergedViewReuse(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.files = []
        for name, body in (("第10章_10.1_a.md", "第一节正文\n"),
                           ("第10章_10.2_b.md", "第二节正文\n")):
            p = os.path.join(self.d.name, name)
            with open(p, "w", encoding="utf-8") as f:
                f.write(body)
            self.files.append(p)

    def tearDown(self):
        vc._TMP_VIEWS.clear()
        self.d.cleanup()

    def test_same_lang_reuses_one_path(self):
        a = vc._merged_temp_path(self.d.name, 10, self.files)
        b = vc._merged_temp_path(self.d.name, 11, self.files)
        self.assertEqual(a, b)
        self.assertEqual(len(vc._TMP_VIEWS), 1)

    def test_kind_separates_main_and_pair_views(self):
        main = vc._merged_temp_path(self.d.name, 10, self.files)
        pair = vc._merged_temp_path(self.d.name, 10, self.files, kind="pair")
        self.assertNotEqual(main, pair)
        self.assertEqual(len(vc._TMP_VIEWS), 2)

    def test_name_round_trips_language(self):
        view = vc._merged_temp_path(self.d.name, 10, self.files)
        self.assertEqual(vc._group_lang([view]), "cn")

    def test_cleanup_removes_all_registered_views(self):
        paths = [vc._merged_temp_path(self.d.name, 10, self.files),
                 vc._merged_temp_path(self.d.name, 10, self.files, kind="pair")]
        self.assertTrue(all(os.path.isfile(p) for p in paths))
        vc._cleanup_tmp_views()
        self.assertFalse(any(os.path.isfile(p) for p in paths))
        self.assertEqual(vc._TMP_VIEWS, set())
        # 幂等：再清一次不抛
        vc._cleanup_tmp_views()


if __name__ == "__main__":
    unittest.main()
