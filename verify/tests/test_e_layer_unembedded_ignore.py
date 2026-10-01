r"""E 层：`fig_unembedded`（PARTIAL COVERAGE）的 `ignore_fig` 登记豁免通道。

背景（Ross《A First Course in Probability》2026-10-01 实测）：全书 7 张未嵌图
逐张 fitz 目视核验后确认**全是真实书图、且全是章末习题配图**（图2.6=习题2.56
转盘、图3.5+无名桥式电路=习题3.70、无名阶梯密度=Self-Test 5.1、无名圆弦图=
习题6.16、无名靶盘=Self-Test 6.12、图3.6 配对圈=章末习题区）。章末习题按
writing-rules 习题收录规则不收录 → 宿主条目不存在 → 无法非孤儿式嵌入 →
按「图被正文引用才嵌入」规则**合法不嵌**，但旧实现没有任何正规通道登记这一
事实，WARN 永远挂在收官报告上。

断言：
  1. label 登记（normfig 比对，与 missing/extra 同命名空间）豁免该图；
  2. 无名检测块（无 label）按**文件名 / stem** 登记同样豁免；
  3. **未登记**的未嵌图照旧上报（负向控制：豁免只作用于登记键）；
  4. 豁免不动 `embedded` 集（阻断闸 `fig_zero_embed` 的事实基础不变）。
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

from verify.figure_completeness.script.figure_completeness import check_figure_coverage  # noqa: E402


_MD_IMG = '<img src="figure/ch02_fig2.1.png" alt="图 2.1" width="45%">'

_INDEX = [
    # 嵌入了的图（md 引用了）
    {"chapter": 2, "page": 60, "fig_idx": 1, "label": "2.1",
     "file": "figure/ch02_fig2.1.png", "caption": "图 2.1"},
    # 带 label、但按规则有意不嵌（习题配图）
    {"chapter": 2, "page": 94, "fig_idx": 2, "label": "2.6",
     "file": "figure/ch02_fig2.6.png", "caption": "Figure 2.6 Spinners"},
    # 无名检测块（习题配图，caption 抽取失败）
    {"chapter": 2, "page": 95, "fig_idx": 3, "label": None,
     "file": "figure/ch02_unnamed_07.png", "caption": ""},
]


def _write_md(path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("# ch2\n\ntext\n\n" + _MD_IMG + "\n")


class TestUnembeddedIgnoreExemption(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.md = os.path.join(self._d.name, "Chapter2_x.md")
        _write_md(self.md)
        self.addCleanup(self._d.cleanup)

    def _cov(self, ignore=None):
        return check_figure_coverage(self.md, _INDEX, ignore)

    def test_unregistered_unembedded_still_reported(self):
        embedded, unembedded = self._cov()
        self.assertEqual(embedded, {"ch02_fig2.1.png"})
        self.assertEqual(sorted(unembedded),
                         ["ch02_fig2.6.png", "ch02_unnamed_07.png"],
                         "未登记时两张未嵌图都必须照旧上报（负向控制）")

    def test_label_registration_exempts(self):
        _, unembedded = self._cov(ignore={"2.6"})
        self.assertEqual(unembedded, ["ch02_unnamed_07.png"],
                         "label 登记只豁免该图，未登记的无名块照旧上报")

    def test_filename_registration_exempts_unnamed_crop(self):
        _, unembedded = self._cov(ignore={"ch02_unnamed_07.png"})
        self.assertEqual(unembedded, ["ch02_fig2.6.png"])

    def test_stem_registration_exempts_too(self):
        _, unembedded = self._cov(ignore={"ch02_unnamed_07"})
        self.assertEqual(unembedded, ["ch02_fig2.6.png"],
                         "stem（去扩展名）形式同样有效——登记侧手写常省扩展名")

    def test_full_registration_clears_unembedded(self):
        _, unembedded = self._cov(ignore={"2.6", "ch02_unnamed_07.png"})
        self.assertEqual(unembedded, [])

    def test_embedded_set_never_shrinks(self):
        embedded, _ = self._cov(ignore={"2.1", "2.6", "ch02_unnamed_07.png"})
        self.assertEqual(embedded, {"ch02_fig2.1.png"},
                         "豁免不得缩减 embedded 集——fig_zero_embed 阻断闸的事实基础必须不变")


if __name__ == "__main__":
    unittest.main(verbosity=2)
