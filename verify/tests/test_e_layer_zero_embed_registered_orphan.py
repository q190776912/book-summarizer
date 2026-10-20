r"""E 层：阻断闸 `fig_zero_embed` 的「registered orphan」豁免通道。

背景（Lehmann–Casella《Theory of Point Estimation》ch2 实测 2026-10）：本章在
figure_index 里只有**一张带 label 的真图** Figure 8.1，其宿主小节 `§2.8 Notes →
8.4 Geometry of the Information Inequality`（页 171–172）按
`exercise_region_headings=["Problems","Notes"]` 整节省略 → 无宿主锚点、按「图被正文
引用才嵌入」规则**合法不嵌**。旧 `fig_zero_embed = bool(labeled) and not
(labeled∩embedded)` 不认 `ignore_fig` 豁免，于是整章坍缩为 0 嵌、硬阻断，唯一正规
消音通道只清 WARN 侧、清不掉阻断闸——被迫在「孤儿硬塞 `<img>`（触发 fig_misattributed）
」与「永久红」间二选一。

判据 `compute_fig_zero_embed`：should-embed 集 = 带 label 且**未**登记豁免者。
断言：
  1. 未登记时带 label 未嵌图 → 阻断（负向控制：blanket「embed 没跑过」照旧硬 FAIL）；
  2. 唯一带 label 图按 **label** 登记 → 解除阻断（本 bug 的直接复现与修复）；
  3. 按裁剪**文件名 / stem** 登记同样解除；
  4. 多张带 label 图，仅登记其中一张、且都未嵌 → 照旧阻断（安全网不破）；
  5. 带 label 图**已嵌** → 不阻断；
  6. 只有无名检测块、未嵌、无登记 → 不阻断（无名块从不进 should-embed 集）。
"""
import os
import sys
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

from verify.figure_completeness.script.figure_completeness import (  # noqa: E402
    compute_fig_zero_embed,
)


_LAB = {"chapter": 2, "page": 171, "fig_idx": 1, "label": "8.1",
        "file": "figure/ch02_fig8.1.png", "caption": "Figure 8.1"}
_LAB2 = {"chapter": 2, "page": 150, "fig_idx": 2, "label": "5.2",
         "file": "figure/ch02_fig5.2.png", "caption": "Figure 5.2"}
_UNNAMED = {"chapter": 2, "page": 160, "fig_idx": 3, "label": None,
            "file": "figure/ch02_unnamed_01.png", "caption": ""}


class TestFigZeroEmbedRegisteredOrphan(unittest.TestCase):
    def test_unregistered_labeled_unembedded_blocks(self):
        # 负向控制：没跑过 embed → 带 label 未嵌图必须硬阻断。
        self.assertTrue(compute_fig_zero_embed([_LAB], set()))
        self.assertTrue(compute_fig_zero_embed([_LAB], set(), ignore=set()))

    def test_registered_by_label_clears_block(self):
        # 本 bug 的直接复现：唯一带 label 孤儿图登记 label 后解除阻断。
        self.assertFalse(
            compute_fig_zero_embed([_LAB], set(), ignore={"8.1"}))

    def test_registered_by_filename_or_stem_clears_block(self):
        self.assertFalse(compute_fig_zero_embed(
            [_LAB], set(), ignore={"ch02_fig8.1.png"}))
        self.assertFalse(compute_fig_zero_embed(
            [_LAB], set(), ignore={"ch02_fig8.1"}))

    def test_partial_registration_still_blocks_on_the_rest(self):
        # 安全网：只登记一张，另一张带 label 未嵌 → 照旧阻断。
        self.assertTrue(compute_fig_zero_embed(
            [_LAB, _LAB2], set(), ignore={"8.1"}))

    def test_embedded_labeled_does_not_block(self):
        self.assertFalse(compute_fig_zero_embed(
            [_LAB], {"ch02_fig8.1.png"}))

    def test_unnamed_only_never_in_should_embed(self):
        # 无名检测块从不进 should-embed 集：未嵌 + 无登记也不阻断。
        self.assertFalse(compute_fig_zero_embed([_UNNAMED], set()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
