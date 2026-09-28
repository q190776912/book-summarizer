"""Tests for lib/page_dir.py — 分册目录判据不得被暂存/备份区劫持.

Run:  python lib/tests/test_page_dir.py

动因（Apostol IANT 2026-09-28 实测）：``_extract/_rehearsal/``（一次演练留下的
整区副本：60 个 ``page_*.json`` + 自己的 ``chapter_map.json``）被
:func:`volume_dirs` 认成分册目录，:func:`resolve_page_dir` 的第一判据「分册自带
chapter_map 含本章」于是命中它，Q 层对账只读到副本里的 64–79 页，80 页起
``FileNotFoundError`` 被 ``except`` 静默吞掉 —— 真实印刷编号 (23)/(24) 从未进入
书源集 S，总结忠实的 ``\\tag{23}`` 被误判 FABRICATED。

守住两条：
  * ``_`` / ``.`` 前缀目录（``_mm_repair`` / ``_bak_*`` / ``_rehearsal`` …）
    一律不是分册；
  * 顶层自己放着 ``page_*.json`` = 单册契约，页池就是顶层。
并守住多册书的原行为（上册/下册按各自 chapter_map 精确路由）不被改坏。
"""
import json
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
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from page_dir import resolve_page_dir, volume_dirs


def _page(path, pg):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"page": pg, "text": [{"text": "(%d)" % pg}], "formulas": []}, f)


def _chapter_map(d, chapters):
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump({"chapters": [{"ch": c, "start": s, "end": e}
                                for c, s, e in chapters]}, f)


class PageDirTestCase(unittest.TestCase):
    def setUp(self):
        self.ext = tempfile.mkdtemp(prefix="pd_")

    def tearDown(self):
        shutil.rmtree(self.ext, ignore_errors=True)


class TestScratchDirsIgnored(PageDirTestCase):
    def test_underscore_dir_is_not_a_volume(self):
        _page(os.path.join(self.ext, "page_001.json"), 1)
        _page(os.path.join(self.ext, "_rehearsal", "page_001.json"), 1)
        _page(os.path.join(self.ext, ".cache", "page_002.json"), 2)
        self.assertEqual(volume_dirs(self.ext), [])

    def test_underscore_dir_is_not_a_volume_even_when_only_source_of_pages(self):
        # 顶层无页、只有 `_bak/` 有页：仍不得把备份区当分册（宁可退回顶层）。
        _page(os.path.join(self.ext, "_bak_tag_backfill", "page_010.json"), 10)
        self.assertEqual(volume_dirs(self.ext), [])
        self.assertEqual(resolve_page_dir(self.ext, 3), self.ext)

    def test_single_volume_with_scratch_copy_resolves_to_top_level(self):
        """The exact apostol shape: top level has ALL pages, `_rehearsal` has a
        partial copy carrying its own chapter_map (the first-priority evidence
        that used to win)."""
        for pg in range(64, 86):
            _page(os.path.join(self.ext, "page_%03d.json" % pg), pg)
        for pg in range(64, 80):                     # stale rehearsal copy
            _page(os.path.join(self.ext, "_rehearsal", "page_%03d.json" % pg), pg)
        _chapter_map(os.path.join(self.ext, "_rehearsal"), [(3, 64, 79)])
        _chapter_map(self.ext, [(3, 64, 85)])
        self.assertEqual(resolve_page_dir(self.ext, 3), self.ext)
        with open(os.path.join(resolve_page_dir(self.ext, 3), "page_080.json"),
                  encoding="utf-8") as f:
            got = json.load(f)
        self.assertEqual(got["page"], 80)            # the chapter's tail pages ARE read


class TestMultiVolumeUnchanged(PageDirTestCase):
    def _build(self):
        for pg in range(1, 6):                       # 上册 pages 1..5, ch 1..2
            _page(os.path.join(self.ext, "上册", "page_%03d.json" % pg), pg)
        for pg in range(1, 6):                       # 下册 renumbers from 1, ch 3..4
            _page(os.path.join(self.ext, "下册", "page_%03d.json" % pg), pg)
        _chapter_map(os.path.join(self.ext, "上册"), [(1, 1, 3), (2, 3, 5)])
        _chapter_map(os.path.join(self.ext, "下册"), [(3, 1, 3), (4, 3, 5)])
        _chapter_map(self.ext, [(1, 1, 5), (2, 1, 5), (3, 1, 5), (4, 1, 5)])

    def test_per_volume_chapter_map_routes_each_chapter(self):
        self._build()
        up = os.path.join(self.ext, "上册")
        down = os.path.join(self.ext, "下册")
        self.assertEqual(sorted(os.path.basename(v) for v in volume_dirs(self.ext)),
                         ["上册", "下册"])
        self.assertEqual(resolve_page_dir(self.ext, 1), up)
        self.assertEqual(resolve_page_dir(self.ext, 3), down)

    def test_scratch_copy_does_not_steal_a_volume(self):
        self._build()
        for pg in range(1, 6):
            _page(os.path.join(self.ext, "_rehearsal", "page_%03d.json" % pg), pg)
        _chapter_map(os.path.join(self.ext, "_rehearsal"), [(1, 1, 5), (3, 1, 5)])
        self.assertEqual(resolve_page_dir(self.ext, 1), os.path.join(self.ext, "上册"))
        self.assertEqual(resolve_page_dir(self.ext, 3), os.path.join(self.ext, "下册"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
