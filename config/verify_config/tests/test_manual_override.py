# -*- coding: utf-8 -*-
"""`verify_chapter.py --manual` 运行时覆盖的判据回归（2026-11-09 审计）。

旧版 `_main_impl` 取了 `--manual` 的值却从不消费，help / config_schema.md /
writing-rules.md 都宣称可用 ⇒ 用户按文档传参静默无效。现在值经
`verify_one` / `verify_all` / `_make_loader` 透传到 `ConfigLoader.__init__`
的 `manual_override`，覆盖 `BookConfig.manual`，由 `manual_for_chapter()` 读取。

判据：① 传覆盖 → 书级人工补漏条目可见；② 不传（负向锁）→ 读不到；
③ 覆盖不写回 verify_config.json（只作用于本次进程）。
"""
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

import config.verify_config.verify_config as VC  # noqa: E402


class TestManualOverride(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.ext = os.path.join(self.td.name, "_extract")
        os.makedirs(self.ext)
        self.target = os.path.join(self.td.name, "manual_overrides.json")
        with open(self.target, "w", encoding="utf-8") as fh:
            json.dump([{"key": "9.9", "label": "定理", "page": 1}], fh,
                      ensure_ascii=False)
        self.cfg = os.path.join(self.ext, "verify_config.json")

    def tearDown(self):
        self.td.cleanup()

    def _fake_load(self):
        def _inner(loader):
            loader.book = types.SimpleNamespace(manual=None)
        return _inner

    def _make(self, **kw):
        with mock.patch.object(VC, "prime_chapter_kinds"), \
             mock.patch.object(VC.ConfigLoader, "_load_verify_config",
                               self._fake_load()), \
             mock.patch.object(VC.ConfigLoader, "_load_chapter_map",
                               return_value={}), \
             mock.patch.object(VC.ConfigLoader, "_load_figure_index",
                               return_value=[]):
            return VC.ConfigLoader(self.ext, self.td.name, **kw)

    def test_override_reaches_manual_for_chapter(self):
        loader = self._make(manual_override=self.target)
        self.assertEqual(loader.book.manual, VC._norm_win(self.target))
        rows = loader.manual_for_chapter(1)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["key"], "9.9")

    def test_without_override_is_empty(self):
        loader = self._make()
        self.assertIsNone(loader.book.manual)
        self.assertEqual(loader.manual_for_chapter(1), [])

    def test_override_does_not_write_config(self):
        self._make(manual_override=self.target)
        self.assertFalse(os.path.exists(self.cfg))


if __name__ == "__main__":
    unittest.main(verbosity=2)
