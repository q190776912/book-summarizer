"""test_appendix_letter_tag_chain.py — 附录字母章位公式编号 (A.N) 的**探测→挂载**链判据。

一条缺陷链的两环（Shafarevich BA1 `5 Algebraic Appendix` 实测 2026-09-28：
印面 (A.1)…(A.15) 一个都没进契约 `tags`，成书里所有「见 (A.3)」指向无号展示式）：

① `make_config.detect_formula` 的字母分支用**全书**阈值 `_FORMULA_MIN_COUNT=30`，
   而附录生成器只传附录页窗（14 页 / 17 条干净命中）→ 永远达不到 → `appendix`
   段静默丢掉 `formula` 键；
② `attach_content.formula_cfg` 用「章键是不是数字」判是否附录 → **数字键附录**
   （本书章键 5、kind 2）读不到 `appendix` 段，即使配置里有 `formula`。

正向：短页窗 + 连续段 → 探测出发 `letter_ch`；kind 真值 → 路由到附录段。
负向：命中不足 / 命中散乱无连续段 / 长页窗未达全书阈值 → 一律不伪造配置。
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
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "lib"))
import lib.boot as _boot  # noqa: E402
_boot.setup()

import attach_content as ac  # noqa: E402
import make_config as mc  # noqa: E402
import book_structure as bs  # noqa: E402
from data.book_structure import book_structure as bs_pkg  # noqa: E402

# 🔴 同源文件的**两个模块身份**：`lib.boot` 把 `data/<子目录>` 逐个注入 sys.path，
# 于是 `data/book_structure/book_structure.py` 既能以裸名 `book_structure` 导入，也能
# 以包内名 `data.book_structure.book_structure` 导入，两者是**不同对象、各持一份**
# 进程级 `_PRIMED_KINDS`。`attach_content`（及全部门控）用的是包内那份，只回滚裸名
# 那份等于没回滚——实测把 `{"5": 附录}` 留在全进程，毒死了 verify/tests 的 P 层
# 契约豁免测试（同进程全量跑 2 failed）。本测试因此快照**全部副本**。
_BS_COPIES = [m for m in ({id(bs): bs, id(bs_pkg): bs_pkg}).values()]


def _snapshot_kinds():
    return {id(m): dict(m._PRIMED_KINDS) for m in _BS_COPIES}


def _restore_kinds(snap):
    for m in _BS_COPIES:
        d = m._PRIMED_KINDS
        d.clear()
        d.update(snap.get(id(m), {}))


def _write_pages(ext, per_page, start=1):
    os.makedirs(ext, exist_ok=True)
    paths = []
    for i, blocks in enumerate(per_page, start=start):
        p = os.path.join(ext, "page_%03d.json" % i)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"text": [{"text": t} for t in blocks]}, f,
                      ensure_ascii=False)
        paths.append(p)
    return paths


def _letter_pages(nums):
    """One display line per number, equation number right-aligned at the end."""
    return [[f"the relation reads as follows, (A.{n})"] for n in nums]


class DetectLetterSeriesTest(unittest.TestCase):
    def setUp(self):
        self._done_ok = []

    def _ext(self, per_page, start=1):
        d = tempfile.mkdtemp()
        _write_pages(d, per_page, start=start)
        with open(os.path.join(d, "_extraction_done.json"), "w") as f:
            json.dump({"done": True}, f)
        self.addCleanup(self._rmtree, d)
        return d

    @staticmethod
    def _rmtree(d):
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def test_short_appendix_range_with_a_run_is_detected(self):
        # ① 本书记实：14 页 / 15 个连续号。旧的固定阈值 30 判 None。
        ext = self._ext(_letter_pages(range(1, 16)), start=299)
        pages = sorted(os.path.join(ext, f) for f in os.listdir(ext)
                       if f.startswith("page_"))
        cfg = mc.detect_formula(ext, pages=pages)
        self.assertIsNotNone(cfg)
        self.assertTrue(cfg.get("letter_ch"))
        self.assertEqual(cfg["type"], 2)      # (letter.number) two-component
        self.assertEqual(cfg["scope"], 1)     # one book-wide series inside the appendix

    def test_scattered_letter_hits_are_not_a_series(self):
        # 17 条命中但无连续段（交叉引用 / 巧合括号）→ 绝不伪造配置。
        scattered = [3, 17, 42, 8, 91, 5, 77, 23, 64, 11, 88, 31, 52, 7, 99, 13, 44]
        ext = self._ext(_letter_pages(scattered), start=299)
        pages = sorted(os.path.join(ext, f) for f in os.listdir(ext)
                       if f.startswith("page_"))
        self.assertIsNone(mc.detect_formula(ext, pages=pages))

    def test_too_few_letter_hits_stay_undetected(self):
        ext = self._ext(_letter_pages(range(1, 7)), start=299)
        pages = sorted(os.path.join(ext, f) for f in os.listdir(ext)
                       if f.startswith("page_"))
        self.assertIsNone(mc.detect_formula(ext, pages=pages))

    def test_long_range_keeps_the_whole_book_threshold(self):
        # 70 页 / 20 个连续号：页窗不短，全书判据（30）不得被放宽。
        per_page = (_letter_pages(range(1, 21))
                    + [["a page of prose with no numbered display"]] * 50)
        ext = self._ext(per_page, start=1)
        pages = sorted(os.path.join(ext, f) for f in os.listdir(ext)
                       if f.startswith("page_"))
        self.assertGreaterEqual(len(pages), mc._FORMULA_FULL_SCAN_PAGES)
        self.assertIsNone(mc.detect_formula(ext, pages=pages))

    def test_letter_threshold_scales_only_for_short_ranges(self):
        self.assertEqual(mc._letter_min_count(326), mc._FORMULA_MIN_COUNT)
        self.assertEqual(mc._letter_min_count(60), mc._FORMULA_MIN_COUNT)
        self.assertEqual(mc._letter_min_count(14), mc._FORMULA_LETTER_MIN)
        self.assertEqual(mc._letter_min_count(50), 25)


class FormulaCfgRoutingTest(unittest.TestCase):
    """② 数字键附录必须按 chapter_map 的 kind 路由到 `appendix` 段。"""

    def _ext(self):
        d = tempfile.mkdtemp()
        self.addCleanup(self._rmtree, d)
        with open(os.path.join(d, "chapter_map.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"chapters": [
                {"ch": 1, "name": "Basic Notions", "start": 20, "end": 98},
                {"ch": 4, "name": "Intersection Numbers", "start": 249,
                 "end": 298},
                {"ch": 5, "name": "Algebraic Appendix", "start": 299,
                 "end": 312},
            ]}, f)
        with open(os.path.join(d, "verify_config.json"), "w",
                  encoding="utf-8") as f:
            json.dump({
                "ch": {"ordinal": [], "formula": {"type": 2, "scope": 2}},
                "appendix": {"ordinal": [],
                             "formula": {"type": 2, "scope": 1,
                                         "letter_ch": True}},
            }, f)
        return d

    @staticmethod
    def _rmtree(d):
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def _cfg(self, ext, ch):
        saved = _snapshot_kinds()
        ac._FORMULA_CFG_CACHE.clear()
        try:
            return ac.formula_cfg(ext, ch)
        finally:
            _restore_kinds(saved)
            ac._FORMULA_CFG_CACHE.clear()

    def test_numeric_key_appendix_routes_to_appendix_segment(self):
        ext = self._ext()
        _ncomp, scope, letter, _bare = self._cfg(ext, "5")
        self.assertTrue(letter, "数字键附录必须取到 appendix 段的 letter_ch")
        self.assertEqual(scope, 1)

    def test_numbered_chapters_keep_the_main_segment(self):
        ext = self._ext()
        for ch in ("1", "4"):
            _n, scope, letter, _b = self._cfg(ext, ch)
            self.assertFalse(letter)
            self.assertEqual(scope, 2)

    def test_letter_key_appendix_is_unaffected(self):
        # 旧判据（键非数字）覆盖的形态必须零回归。
        ext = self._ext()
        with open(os.path.join(ext, "chapter_map.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"chapters": [
                {"ch": 1, "name": "Body", "start": 1, "end": 90},
                {"ch": "A", "name": "Appendix", "start": 91, "end": 100},
            ]}, f)
        _n, scope, letter, _b = self._cfg(ext, "A")
        self.assertTrue(letter)
        self.assertEqual(scope, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
