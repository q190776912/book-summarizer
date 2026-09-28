"""Regression test: `prune_stale_index`（阿诺尔德《经典力学的数学方法》2026-09-28）。

旧书按数字章 11..26 登记附录，重跑图检测+分配后附录改按字母章 A..P 命名。
`merge_index` 只替换「本次处理到的章」的条目，旧数字章的记录没人管 → figure_index.json
里留下 42 条指向不存在裁图的幽灵条目（章号还在、裁图早已随书目录清理消失），
E 层与「契约 ↔ 图片对账」全部失真。锁死三条：孤儿条目被清除、manual 条目保留、
裁图在盘的条目保留。
"""
import json
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
sys.path.insert(0, os.path.join(_ROOT, "flows", "script"))

import assign_figures  # noqa: E402


class PruneStaleIndexTest(unittest.TestCase):
    def _make(self, entries, crops):
        book = tempfile.TemporaryDirectory()
        extract = os.path.join(book.name, "_extract")
        figdir = os.path.join(book.name, "figure")
        os.makedirs(extract)
        os.makedirs(figdir)
        for c in crops:
            Path(os.path.join(figdir, c)).write_bytes(b"png")
        with open(os.path.join(extract, "figure_index.json"), "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False)
        return book, extract

    def test_orphan_dropped_manual_and_live_kept(self):
        entries = [
            {"chapter": 11, "file": "figure/ch11_fig230.png", "source": "detect"},
            {"chapter": 1, "file": "figure/ch01_fig1.png", "source": "detect"},
            {"chapter": "A", "file": "figure/appendixA_fig1.png", "source": "manual"},
        ]
        book, extract = self._make(entries, ["ch01_fig1.png", "appendixA_fig1.png"])
        with book:
            kept, dropped = assign_figures.prune_stale_index(extract)
            self.assertEqual([str(e["chapter"]) for e in kept], ["1", "A"])
            self.assertEqual([e["chapter"] for e in dropped], [11])
            on_disk = json.load(open(os.path.join(extract, "figure_index.json"), encoding="utf-8"))
            self.assertEqual(len(on_disk), 2)

    def test_no_orphans_leaves_file_untouched(self):
        entries = [{"chapter": 1, "file": "figure/ch01_fig1.png", "source": "detect"}]
        book, extract = self._make(entries, ["ch01_fig1.png"])
        with book:
            path = os.path.join(extract, "figure_index.json")
            before = open(path, encoding="utf-8").read()
            kept, dropped = assign_figures.prune_stale_index(extract)
            self.assertEqual(len(kept), 1)
            self.assertEqual(dropped, [])
            self.assertEqual(open(path, encoding="utf-8").read(), before)


if __name__ == "__main__":
    unittest.main()
