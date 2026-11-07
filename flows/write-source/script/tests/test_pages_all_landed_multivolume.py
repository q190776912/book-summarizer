"""`pages_all_landed` 必须认得**多册书**的册目录（数学分析实测 2026-11-06）。

缺陷现场：`flow_runner audit D:/study/book/基础/数学分析` 报
    ❌ extract.extract_text: 无 page_*.json
而磁盘上有 971 个 `page_*.json`——只是按 SKILL.md「上下册 / 多册书」条落在
`_extract/上册/`、`_extract/下册/`，根目录恒为空。旧实现只在根目录 glob，
于是**所有多册书**的 extract_text 证据永久假缺页：`audit` 红、`mark` 会被拒，
而唯一能"通过"它的动作是重跑提取流水线——对已收官的书是毁灭性的。

根治 = 读页口径与判据同源：册目录走 `lib.page_dir.volume_dirs`
（判据是「目录里真有 page 文件」，不硬编码「上册/下册」，且 `_`/`.` 前缀的
备份·演练区**不算**分册——Apostol `_rehearsal/` 那类整区拷贝曾把 Q 层读页带偏）。
每册各自须 1..N 连续。

负向（必须仍然成立，否则放行等于拆闸）：
  * 任一册内部断号 ⇒ 仍 FAIL（假绿的最坏形态是"册存在但少页"）；
  * 根目录与册目录都没有 page 文件 ⇒ FAIL；
  * 只有 `_bak_*` 之类的下划线目录里有 page 文件 ⇒ FAIL（不得被当成册）；
  * 首页非 1 ⇒ FAIL。

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_pages_all_landed_multivolume.py
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
    _ROOT = str(Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

from flows._flow_contract import physical_evidence  # noqa: E402


def _touch_pages(d, nums):
    os.makedirs(d, exist_ok=True)
    for n in nums:
        with open(os.path.join(d, "page_%03d.json" % n), "w", encoding="utf-8") as fh:
            fh.write("{}")


class PagesAllLanded(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.book = self._tmp.name
        self.ex = os.path.join(self.book, "_extract")
        os.makedirs(self.ex)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self):
        return physical_evidence.pages_all_landed(self.book, self.ex)

    def test_single_volume_root_ok(self):
        _touch_pages(self.ex, range(1, 12))
        ok, detail = self._run()
        self.assertTrue(ok, detail)
        self.assertIn("11 页", detail)

    def test_multivolume_subdirs_ok(self):
        """根目录空 + 两册各自连续 = 已收官多册书的真实形态。"""
        _touch_pages(os.path.join(self.ex, "上册"), range(1, 8))
        _touch_pages(os.path.join(self.ex, "下册"), range(1, 6))
        ok, detail = self._run()
        self.assertTrue(ok, detail)
        self.assertIn("上册", detail)
        self.assertIn("下册", detail)

    def test_hole_in_one_volume_still_fails(self):
        _touch_pages(os.path.join(self.ex, "上册"), range(1, 8))
        _touch_pages(os.path.join(self.ex, "下册"), [1, 2, 3, 5])
        ok, detail = self._run()
        self.assertFalse(ok, "册内断号被放行 = 假绿")
        self.assertIn("断裂", detail)
        self.assertIn("下册", detail)

    def test_no_page_files_anywhere_fails(self):
        ok, detail = self._run()
        self.assertFalse(ok)
        self.assertIn("page_*.json", detail)

    def test_underscore_backup_dir_is_not_a_volume(self):
        _touch_pages(os.path.join(self.ex, "_bak_20261022"), range(1, 6))
        ok, detail = self._run()
        self.assertFalse(ok, "备份区整区拷贝不得充当册目录")

    def test_first_page_not_one_fails(self):
        _touch_pages(os.path.join(self.ex, "上册"), range(1, 6))
        _touch_pages(os.path.join(self.ex, "下册"), range(3, 9))
        ok, detail = self._run()
        self.assertFalse(ok)
        self.assertIn("首页非 1", detail)


if __name__ == "__main__":
    unittest.main(verbosity=2)
