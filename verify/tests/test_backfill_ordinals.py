"""Regression tests: 序标回填（backfill_ordinals，完全拼接后校验 + 写回归属单元）。

背景：序标（1:1 保真铁律）原本只在章级 verify 跑。现新增回填工具
``backfill_ordinals.py``：把 B 层（条目缺号）/ O 层（子项缺号）发现的缺口，写回其
归属的总结单元 ``.md``（你在哪个单元找回的序标就放回哪个单元）。本文件锁定回填行为：

  1. B 层缺号（1.1-1 → 1.1-3，缺 1.1-2）：回填到正确单元、正确位置，插入占位条目。
  2. O 层子项缺口（(1)(2)(4) 缺 3）：回填到正确单元、插入 (3) 占位。
  3. 幂等：重复运行不重复插入。
  4. 非编造：占位条目带明确 ``[回填占位]`` 标记，不改写既有正文。
  5. 仅「缺号」回填：「顺序错乱」只报告、不自动改标签。
  6. fail-closed：单元缺失 / 层异常 → 单章跳过并报告，不影响其余章。

🔴 映射纪律：缺口出现在合并 md 第 L 行 → 经 ``merge_chapter_map`` 的 line→unit 映射
定位到归属单元；插入位置取「缺口前序条目」在单元内的行，**不跨单元串味**。
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
# 🔴 backfill_ordinals / gate_units 等入口脚本位于 flows/write-source/script/，
# 显式加入 path 以保证无论 pytest 以何种 rootdir 模式运行都能 import。
_script_dir = os.path.join(_ROOT, "flows", "write-source", "script")
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
import lib.boot as _boot  # noqa: E402
_boot.setup()

import backfill_ordinals as bf  # noqa: E402

_CFG = {"ch": {"ordinal": [{"type": 3, "name": ["uncat"], "scope": 3}],
               "strict": True, "ignore": []}}

_SUBITEMS_GAP = "\n(1) 第一条结论。\n\n(2) 第二条结论。\n\n(4) 第四条结论。\n"
_SUBITEMS_OK = "\n(1) 第一条结论。\n\n(2) 第二条结论。\n\n(3) 第三条结论。\n"


def _ord_body(ordinal, subitems=""):
    """条目单元正文：加粗条头承载三级序标 `1.1-N`（可选追加子项序列）。"""
    return "**%s**\n\n正文内容。\n%s" % (ordinal, subitems)


class _ChapterFixture(unittest.TestCase):
    """搭一个最小可跑章：_extract（含 MM Repair 完成标记 + 配置）+ units/ch1。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bks_bf_")
        self.ext = os.path.join(self.tmp, "_extract")
        self.out_dir = os.path.join(self.ext, "book_structure", "units", "ch1")
        os.makedirs(self.out_dir, exist_ok=True)
        # 🔴 ConfigLoader 硬闸：缺 _extraction_done.json（MM Repair 完成标记）
        # 时拒绝加载 verify_config.json——真实书均已完成 MM Repair，夹具须补。
        with open(os.path.join(self.ext, "_extraction_done.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"status": "done"}, f)
        for d in (self.ext, self.tmp):   # extract_dir / book_dir 两处都放
            with open(os.path.join(d, "verify_config.json"), "w",
                      encoding="utf-8") as f:
                json.dump(_CFG, f)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_unit(self, fname, key, utype, body):
        with open(os.path.join(self.out_dir, fname), "w", encoding="utf-8") as f:
            f.write("<!-- book-summarizer DONE unit: id=%s type=%s key=%s name=x -->\n"
                    % (fname, utype, key))
            f.write(body)

    def _build(self, specs):
        """specs: [(key, utype, body), ...] → 写单元文件，返回 units 列表。"""
        units = []
        for i, (key, utype, body) in enumerate(specs, start=1):
            fname = "%04d_%s.md" % (i, utype)
            self._write_unit(fname, key, utype, body)
            units.append({"file": fname, "type": utype, "key": key})
        with open(os.path.join(self.out_dir, "manifest.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"units": units}, f)
        return units

    def _items(self, ordinals, subitems=""):
        return [(o, "item", _ord_body(o, subitems)) for o in ordinals]


class BackfillBTest(_ChapterFixture):
    """B 层条目缺号：回填到正确单元、正确位置，占位不编造。"""

    def test_missing_number_reported_and_placed(self):
        self._build(self._items(["1.1-1", "1.1-3"]))
        report = []
        planned, _applied = bf._backfill_chapter(self.ext, 1, "units", apply=False,
                                                report=report)
        self.assertEqual(planned, 1, report)
        self.assertTrue(any("1.1-2" in r for r in report), report)

    def test_apply_inserts_placeholder(self):
        self._build(self._items(["1.1-1", "1.1-3"]))
        unit_file = os.path.join(self.out_dir, "0001_item.md")
        unit2_file = os.path.join(self.out_dir, "0002_item.md")
        before = open(unit_file, encoding="utf-8").read()
        self.assertNotIn("回填占位", before)
        r = []
        _p, applied = bf._backfill_chapter(self.ext, 1, "units", apply=True, report=r)
        self.assertEqual(applied, 1, r)
        after = open(unit_file, encoding="utf-8").read()
        self.assertIn("回填占位", after)
        self.assertIn("1.1-2", after)
        # 占位插在 1.1-1 之后（同单元 0001_item.md，紧邻前序条目），
        # 而 1.1-3 在另一单元 0002_item.md（不串味、不被改写）
        self.assertLess(after.index("1.1-1"), after.index("回填占位"))
        self.assertIn("1.1-3", open(unit2_file, encoding="utf-8").read())
        self.assertNotIn("回填占位", open(unit2_file, encoding="utf-8").read())

    def test_placeholder_does_not_clobber_existing(self):
        """占位只追加，不改写既有条目正文。"""
        self._build(self._items(["1.1-1", "1.1-3"]))
        bf._backfill_chapter(self.ext, 1, "units", apply=True, report=[])
        after = open(os.path.join(self.out_dir, "0001_item.md"),
                     encoding="utf-8").read()
        self.assertIn("正文内容。", after, "既有条目正文被改写")
        self.assertEqual(after.count("回填占位"), 1)

    def test_idempotent(self):
        self._build(self._items(["1.1-1", "1.1-3"]))
        bf._backfill_chapter(self.ext, 1, "units", apply=True, report=[])
        r = []
        planned, applied = bf._backfill_chapter(self.ext, 1, "units", apply=True,
                                               report=r)
        self.assertEqual(planned, 0, "重复运行不应再插入：%s" % r)
        self.assertEqual(applied, 0)

    def test_out_of_order_not_backfilled(self):
        """顺序错乱（1.1-3 排 1.1-2 前）只报告、不回填。"""
        self._build(self._items(["1.1-1", "1.1-3", "1.1-2"]))
        r = []
        planned, applied = bf._backfill_chapter(self.ext, 1, "units", apply=True,
                                               report=r)
        self.assertEqual(planned, 0, "顺序错乱不应回填：%s" % r)
        self.assertEqual(applied, 0)


class BackfillOTest(_ChapterFixture):
    """O 层子项缺号：回填到正确单元、插入占位。"""

    def test_subitem_gap_reported_and_placed(self):
        self._build(self._items(["1.1-1"], _SUBITEMS_GAP))
        r = []
        planned, _a = bf._backfill_chapter(self.ext, 1, "units", apply=False, report=r)
        self.assertEqual(planned, 1, r)
        self.assertTrue(any("(3)" in x for x in r), r)

    def test_subitem_apply_inserts(self):
        self._build(self._items(["1.1-1"], _SUBITEMS_GAP))
        unit_file = os.path.join(self.out_dir, "0001_item.md")
        before = open(unit_file, encoding="utf-8").read()
        self.assertNotIn("回填占位", before)
        r = []
        _p, applied = bf._backfill_chapter(self.ext, 1, "units", apply=True, report=r)
        self.assertEqual(applied, 1, r)
        after = open(unit_file, encoding="utf-8").read()
        self.assertIn("回填占位", after)
        self.assertIn("(3)", after)
        # (3) 在 (2) 之后、(4) 之前
        self.assertLess(after.index("(2)"), after.index("回填占位"))
        self.assertLess(after.index("回填占位"), after.index("(4)"))

    def test_subitem_clean_no_backfill(self):
        self._build(self._items(["1.1-1"], _SUBITEMS_OK))
        r = []
        planned, _a = bf._backfill_chapter(self.ext, 1, "units", apply=False, report=r)
        self.assertEqual(planned, 0, r)


class FailClosedTest(_ChapterFixture):
    def test_missing_unit_skips_chapter(self):
        units = [{"file": "9999_missing.md", "type": "item", "key": "1.1-1"}]
        with open(os.path.join(self.out_dir, "manifest.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"units": units}, f)
        r = []
        planned, applied = bf._backfill_chapter(self.ext, 1, "units", apply=True,
                                               report=r)
        self.assertEqual(planned, 0)
        self.assertEqual(applied, 0)


if __name__ == "__main__":
    unittest.main()
