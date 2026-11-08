"""`resync_figure_refs.main()` 跨书章型隔离的判据回归（2026-11-08）。

根因：`_PRIMED_KINDS` 是进程级全局，`prime_chapter_kinds` 只灌不清；同一
进程里另一本书把章 `14` 灌成 `KIND_APPENDIX` 后，`unit_dir_name("14")` 会
算出 `appendix14`，本 CLI 对该章 0 job → 图引用旧名残留。实证：pytest 全量
跑 `test_two_digit_chapter_label_is_not_blind` 失败、单跑通过；直接注入
`bs._PRIMED_KINDS['14'] = 2` 可稳定复现完全相同的断言。

本文件锁住：① 注入污染后 `main()` 仍以当前书为准；② **关掉 reset 必须复现
原失败**（负向锁，防止把「碰巧通过」当修好）；③ 注册表在用例间不被污染。
"""
import io
import os
import shutil
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "tools"),
           os.path.join(_ROOT, "tools", "tests")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot  # noqa: E402
lib.boot.setup()

import resync_figure_refs as R  # noqa: E402
import test_resync_figure_refs as base  # noqa: E402
from data.book_structure import book_structure as bs  # noqa: E402


class T(unittest.TestCase):
    def setUp(self):
        self._saved = dict(bs._PRIMED_KINDS)
        self.tmp = tempfile.mkdtemp(prefix="rfr_iso_")
        self.book = os.path.join(self.tmp, "B")
        os.makedirs(self.book)

    def tearDown(self):
        bs._PRIMED_KINDS.clear()
        bs._PRIMED_KINDS.update(self._saved)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _unit_src(self, ch="14"):
        p = os.path.join(self.book, "_extract", "book_structure", "units",
                         "ch%s" % ch, "0001_desc_D1.md")
        return io.open(p, encoding="utf-8").read().split('src="')[1].split('"')[0]

    def test_foreign_kind_is_reset_before_priming(self):
        real, _stale = base.build(self.book, "14")
        bs._PRIMED_KINDS["14"] = 2          # 模拟另一本书残留的附录章型
        base.run(self.book, "14", commit=True)
        self.assertEqual(self._unit_src(), "figure/" + real)
        self.assertNotIn("14", bs._PRIMED_KINDS)

    def test_negative_without_reset_reproduces_failure(self):
        """负向锁：把 reset 变成 no-op，必须复现 ch14 旧名残留。"""
        _real, stale = base.build(self.book, "14")
        bs._PRIMED_KINDS["14"] = 2
        with mock.patch.object(R, "reset_chapter_kinds", lambda: None):
            base.run(self.book, "14", commit=True)
        self.assertEqual(self._unit_src(), "figure/" + stale)

    def test_primed_kinds_do_not_leak_between_cases(self):
        self.assertEqual(bs._PRIMED_KINDS.get("14"), self._saved.get("14"))
