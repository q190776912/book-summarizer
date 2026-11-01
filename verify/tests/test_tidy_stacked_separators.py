# -*- coding: utf-8 -*-
r"""``render_draft._tidy_separators`` 堆叠分割线合并的判据回归。

成因（周民强《实变函数论》第 1 章交付物实测，2026-10-30）：合并稿里出现
``---`` / 空行 / ``---`` 的**假分隔**（无正文夹在中间，读者看到两条紧挨的横线）。
根因是第一遍合并把「串」的距离写成了上限——判定式
``lines[k] == "---" and k - last <= 2``，即只被空行隔开的两个 ``---`` 之间
最多允许 2 个空行。零内容契约节点（description 单元正文为空）在拼接状态机里
仍会吐出一个空行，于是间距变成 3，第二个 ``---`` 逃出合并；紧接着第二遍把每个
保留的 ``---`` 上下规整成恰一个空行，就把「两个各自带空行的分隔线」原样写进了交付。
⇒ 距离守卫本身没有意义：内层循环只跳过**空行**，能走到的下一个 ``---`` 必然是
「只被空行隔开」的堆叠，无论如何都该合并。修法 = 去掉 ``k - last <= 2``。

负向：被正文隔开的两个 ``---``（= 真单元边界）**不得**被合并；``owners`` 并行列表
在整理后仍与 ``lines`` 等长且逐个 ``---`` 继承串首行的归属（回填定位序标缺口靠它）。
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

import render_draft as rd


def tidy(lines):
    return rd._tidy_separators(list(lines))


class StackedSeparatorCollapseTest(unittest.TestCase):
    def test_adjacent_and_blank_split_runs_collapse(self):
        for src in (
            ["A", "---", "", "---", "B"],                 # 1 空行（老写法已覆盖）
            ["A", "---", "---", "B"],                     # 紧挨
            ["A", "---", "", "", "---", "B"],              # 🔴 2 空行：零内容单元吐出的形态
            ["A", "---", "", "", "", "---", "B"],          # 3 空行：逃出旧守卫的那一档
            ["A", "", "---", "", "", "", "", "", "---", "", "B"],
        ):
            self.assertEqual(["A", "", "---", "", "B"], tidy(src), src)

    def test_idempotent(self):
        once = tidy(["A", "---", "", "", "---", "B", "---", "---", "C"])
        self.assertEqual(once, tidy(once))
        self.assertEqual(["A", "", "---", "", "B", "", "---", "", "C"], once)

    def test_leading_separator_survives(self):
        self.assertEqual(["---", "", "A"], tidy(["---", "", "A"]))
        self.assertEqual(["---", "", "A"], tidy(["---", "", "", "", "---", "A"]))

    def test_content_between_separators_is_never_swallowed(self):
        # 负向：两个 --- 之间有正文 = 真单元边界，必须原样保留两处分隔
        src = ["A", "---", "", "正文", "", "---", "B"]
        self.assertEqual(["A", "", "---", "", "正文", "", "---", "", "B"], tidy(src))
        self.assertEqual(2, tidy(src).count("---"))
        # 只跳过空行的串才合并：正文之后的 --- 属于下一串
        self.assertEqual(2, tidy(["A", "---", "", "", "正文", "---", "", "", "---", "B"]).count("---"))


class OwnerAlignmentTest(unittest.TestCase):
    def test_owners_stay_row_aligned_and_seps_keep_run_head(self):
        lines = ["A", "---", "", "", "---", "B", "---", "C"]
        owners = ["u1.md", "u2.md", None, None, "u3.md", "u4.md", "u5.md", "u6.md"]
        res, res_ow = rd._tidy_separators(lines, owners)
        self.assertEqual(len(res), len(res_ow))
        self.assertEqual(["A", "", "---", "", "B", "", "---", "", "C"], res)
        # 合并串继承串首行的归属；第二遍插入的空行归属为 None
        self.assertEqual(["u1.md", None, "u2.md", None, "u4.md",
                          None, "u5.md", None, "u6.md"], res_ow)

    def test_none_owners_keeps_single_list_return(self):
        got = rd._tidy_separators(["A", "---", "---", "B"])
        self.assertIsInstance(got, list)


if __name__ == "__main__":
    unittest.main(verbosity=2)
