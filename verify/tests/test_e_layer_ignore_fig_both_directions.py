r"""E 层：`ignore_fig_ch{N}.json` 必须**双向**豁免（Apostol IANT 无号引言章 2026-09-29 根治）。

背景：无章号的引言章（Historical Introduction）印面图题用**罗马章位**
`Figure I.1 / I.2 / I.3`（fitz 300dpi 目视确证），OCR 把字母 I 读成数字 1，
于是 `figure_index.json` 的标签归一为 `1.1`/`1.2`；而题面 harvest 侧要求
`int(parts[0]) == ch`（此处 ch=0），该式对任何带数字前缀的标签恒不成立 →
两张**真实存在、且总结 md 已正确引用**的裁剪图必然落进 `fig_extra`。

判据本身只能人工核，核完却**没有正规通道**消掉这条 WARN：本层子流程文档
（figure_completeness.md 人工对账第 5 条）明写「必要时加 `ignore_figure`」，
旧实现却只在 `missing` 一侧减项。后果是把人推向「改书侧 figure_index 数据
迁就判据」——正是收官抽检禁止的动作。

断言：
  1. 登记后 extra 与 missing 同时豁免（本闸修复目标）；
  2. **未登记**的 extra 照旧上报（放宽只针对登记的号，不得变成盲区）；
  3. 未登记时 extra 仍报（正向：判据假阳须靠登记消，不靠默认沉默）；
  4. missing 侧原有豁免语义不回归。
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


# Apostol ch0 实测形态：章键 0，标签 1.1/1.2（罗马 I 被 OCR 读成 1），
# 页 14 的题面 OCR 同样写作 "Figure 1.1"。
_CH0_INDEX = [
    {"chapter": 0, "page": 14, "fig_idx": 1, "label": "1.1",
     "file": "figure/ch00_fig1.1.png", "caption": "Figure 1.1"},
    {"chapter": 0, "page": 15, "fig_idx": 2, "label": "1.2",
     "file": "figure/ch00_fig1.2.png", "caption": "Figure 1.2"},
]


class TestIgnoreFigSilencesBothDirections(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.ext = self._d.name
        self.addCleanup(self._d.cleanup)
        _write_cfg(self.ext, 2)
        _write_index(self.ext, _CH0_INDEX)
        _write_page(self.ext, 14, ["Figure 1.1", "as shown in Figure I.1."])
        _write_page(self.ext, 15, ["Figure 1.2"])

    def test_unregistered_extra_is_still_reported(self):
        res = check_figure(0, 14, 15, self.ext)
        self.assertEqual(sorted(res["extra"]), ["1.1", "1.2"],
                         "罗马章位被 OCR 读成数字时两张真图都落进 extra（判据假阳形态）")

    def test_registered_keys_clear_extra_and_missing(self):
        res = check_figure(0, 14, 15, self.ext, ignore_fig={"1.1", "1.2"})
        self.assertEqual(res["extra"], [], "登记的号必须能从 extra 中豁免")
        self.assertEqual(res["missing"], [])

    def test_registration_is_per_number(self):
        res = check_figure(0, 14, 15, self.ext, ignore_fig={"1.1"})
        self.assertEqual(res["extra"], ["1.2"],
                         "豁免只作用于登记的号：未登记的 extra 照旧上报")


class TestMissingSemanticsUnchanged(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.ext = self._d.name
        self.addCleanup(self._d.cleanup)

    def test_registered_key_still_silences_missing(self):
        _write_cfg(self.ext, 2)
        _write_index(self.ext, [
            {"chapter": 9, "page": 60, "fig_idx": 1, "label": "9.1",
             "file": "figure/ch09_fig9_1.png", "caption": "图9.1"}])
        _write_page(self.ext, 60, ["见图 9.1 的构造", "另见 图 9.7"])
        res = check_figure(9, 60, 60, self.ext)
        self.assertEqual(res["missing"], ["9.7"])
        res = check_figure(9, 60, 60, self.ext, ignore_fig={"9.7"})
        self.assertEqual(res["missing"], [], "missing 侧豁免语义不得回归")


if __name__ == "__main__":
    unittest.main(verbosity=2)
