r"""E 层：全局整数图号书的**跨章图引用**不得算「丢图」（阿诺尔德附录J/O 实测 2026-09-29）。

背景：`components == 1`（全书一条 图1..图N 计数器，如 Kreyszig / 阿诺尔德中译本）时，
正文里的「（图207）」多半是**回指前面章节的图**——裁剪文件早在账
（`figure/ch09_fig207.png`），只是登记在 ch9 名下。旧判据把对照集收窄成
`_chapter_entries(idx, ch)`，于是附录J 引 ch9 的 图207、附录O 引 ch1 的 图2 各造出
一条 blocking `fig_missing`，写手既无图可裁、也无从 ignore。

根治：全局编号在**全书内号唯一**，missing 的对照集改为「本章 ∪ 全书」；
章/节编号书（components 2/3，号带章前缀）不动，仍按本章对照。
`extra` / 有效性（PNG 是否存在、是否过小）检查一律保持本章口径。

断言：
  1. 他章已入库的号被本章引用 → missing 为空（负向：不再假阻断）；
  2. 全书都没有的号被引用 → 仍 FAIL（正向：本闸不得变成盲区）；
  3. components=2 时全书对照**不外溢**——号只在他章入库仍报本章 missing。
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
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from verify.figure_completeness.script.figure_completeness import check_figure  # noqa: E402


def _write_cfg(ext, fig_type):
    with open(os.path.join(ext, "verify_config.json"), "w", encoding="utf-8") as f:
        json.dump({"ordinal": [{"name": ["图", "Figure"], "type": fig_type}],
                   "section_scoped": True}, f, ensure_ascii=False)


def _write_index(ext, entries):
    with open(os.path.join(ext, "figure_index.json"), "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)


def _write_page(ext, pg, blocks):
    with open(os.path.join(ext, f"page_{pg:03d}.json"), "w", encoding="utf-8") as f:
        json.dump({"page": pg, "text": [{"text": t} for t in blocks],
                   "formulas": []}, f, ensure_ascii=False)


class TestCrossChapterFigureRef(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.ext = self._d.name
        self.addCleanup(self._d.cleanup)

    def test_reference_to_other_chapter_crop_is_not_missing(self):
        _write_cfg(self.ext, 1)
        _write_index(self.ext, [
            {"chapter": 9, "page": 221, "fig_idx": 1, "label": "207",
             "file": "figure/ch09_fig207.png", "caption": "图207 测地线"},
            {"chapter": "J", "page": 354, "fig_idx": 1, "label": "243",
             "file": "figure/appendixJ_fig243.png", "caption": "图243 本征频率"}])
        _write_page(self.ext, 354, [
            "球面的测地线的图上清楚地看见（图207)",
            "图243单参数和二参数的一般形式的振动系统族的本征频率"])
        res = check_figure("J", 354, 354, self.ext)
        self.assertEqual(res["missing"], [],
                         "跨章回指（图207 已在 ch9 入库）不得报丢图")

    def test_number_absent_bookwide_still_blocks(self):
        _write_cfg(self.ext, 1)
        _write_index(self.ext, [
            {"chapter": "J", "page": 354, "fig_idx": 1, "label": "243",
             "file": "figure/appendixJ_fig243.png", "caption": "图243 本征频率"}])
        _write_page(self.ext, 354, [
            "见（图301）的构造",
            "图243单参数和二参数的一般形式的振动系统族的本征频率"])
        res = check_figure("J", 354, 354, self.ext)
        self.assertIn("301", res["missing"],
                      "全书都未入库的号仍须 FAIL（真丢图不得被本闸洗白）")

    def test_bookwide_set_does_not_leak_to_chapter_numbering(self):
        _write_cfg(self.ext, 2)
        _write_index(self.ext, [
            {"chapter": 3, "page": 40, "fig_idx": 1, "label": "9.7",
             "file": "figure/ch03_fig9_7.png", "caption": "图9.7"},
            {"chapter": 9, "page": 60, "fig_idx": 1, "label": "9.1",
             "file": "figure/ch09_fig9_1.png", "caption": "图9.1"}])
        _write_page(self.ext, 60, ["见图 9.7 的构造", "图9.1 说明"])
        res = check_figure(9, 60, 60, self.ext)
        self.assertIn("9.7", res["missing"],
                      "components=2 仍按本章对照：号挂在他章 = 本章缺图，照旧报")


if __name__ == "__main__":
    unittest.main(verbosity=2)
