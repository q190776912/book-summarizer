# -*- coding: utf-8 -*-
"""test_item_numbering_orphan_ex_window.py — B 层「Problem 窗其实是条目计数器」并回主窗。

Background (Iwaniec–Kowalski《Analytic Number Theory》ch7 merge_source, 2026-09-28)
----------------------------------------------------------------------------------
该书章内只有一条 1..35 计数器，Problem 就在其中：印作 Theorem 7.18 → **Problem
7.19** → Theorem 7.20 … Corollary 7.24 → **Problem 7.25** … Conjecture 7.32。
B 层按 label 把 Problem 一律切进 `gi:ex:7` 独立窗，于是**同一批号被两头误报**：
主窗 1..35 报「缺号 19 / 25 / 29」，ex 窗（只有 19,25,29）报「缺号 1..18、20..28」
—— 一章 29 条 BLOCKING，而 md 与契约其实一字不差。

`exercise_shared_numbering` 是「练习与条目共享计数器」的开关，而本书**章末
Exercise 1..5 用的是另一条独立计数器**，所以该开关必须为 False，Etingof 的
形态判据（点号同形留主窗）也就无从生效（它挂在 `_shared` 上）。

根治 = 窗算术第二步 `_merge_orphan_ex_windows`：只在「并回去正好把主窗补平」
时改路由（① ex 窗最小号 > 1；② 窗内每个号都是主窗的洞；③ 并入后主窗连续）。

Run:  python verify/tests/test_item_numbering_orphan_ex_window.py
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
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from verify_config import BookConfig, GroupConfig          # noqa: E402
from item_numbering_integrity import _md_gap_blocking      # noqa: E402
from verify.script.base import VerifyContext               # noqa: E402


def _ctx(md_text):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "chapter7.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(md_text)
    cfg = BookConfig(
        ordinal=[GroupConfig(type=2, name=["Theorem", "Lemma", "Corollary",
                                           "Problem", "Exercise"], scope=2)],
        exercise_shared_numbering=False,   # 🔴 本书章末 Exercise 另持独立计数器
        strict=True,
    )
    return VerifyContext(ch=7, start=1, end=1, md_file=p, ext_dir=d, config=cfg)


def _head(n, label="Theorem"):
    return "**%s 7.%d.** item %d.\n\n" % (label, n, n)


def _md(nums, problems=(), exercises=()):
    """按阅读顺序生成条目；nums/problems/exercises 是章内序标。"""
    body = ["# Chapter 7\n\n"]
    seq = sorted(set(nums) | set(problems))
    for n in seq:
        lab = "Problem" if n in problems else "Theorem"
        body.append(_head(n, lab))
    for n in sorted(exercises):
        body.append(_head(n, "Exercise"))
    return "".join(body)


class OrphanProblemWindow(unittest.TestCase):
    def test_problems_filling_main_holes_are_merged_back(self):
        """主窗 1..7 的洞恰为 3/6，Problem 就是这两个号 → 并回，零 BLOCKING。"""
        md = _md([1, 2, 4, 5, 7], problems=[3, 6])
        blocking, _w, _p, _t, _g = _md_gap_blocking(_ctx(md))
        self.assertEqual(blocking, [], "false gaps: %s" % blocking)

    def test_independent_exercise_window_untouched(self):
        """真独立习题窗（并不平主窗）必须保持原样，不得被误并。

        主窗 1..5 连续无洞，习题窗 {3,9} 与主窗洞集无涉 → 维持 `:ex:` 窗，
        其对 4..8 的缺号照旧上报（这是独立窗自己的序列问题，与本判据无关）。
        """
        md = _md([1, 2, 3, 4, 5], exercises=[3, 9])
        blocking, _w, _p, _t, _g = _md_gap_blocking(_ctx(md))
        text = "\n".join(blocking)
        self.assertIn(":ex:", text, "独立习题窗不应被并回主窗：%s" % text)

    def test_real_hole_still_blocks_when_merge_cannot_close_it(self):
        """收紧后不得失去检出力：4 号真缺（Problem 只补了 3）→ 仍须 BLOCKING。"""
        md = _md([1, 2, 5], problems=[3])
        blocking, _w, _p, _t, _g = _md_gap_blocking(_ctx(md))
        text = "\n".join(blocking)
        self.assertIn("缺号 4", text, "真缺号被豁免了：%s" % text)

    def test_exercise_window_starting_at_one_untouched(self):
        """按节重排的习题窗一定从 1 起号（Katok/Lee 体例）→ 判据① 直接不触发。"""
        md = _md([1, 2, 3], exercises=[1, 2])
        blocking, _w, _p, _t, _g = _md_gap_blocking(_ctx(md))
        self.assertEqual(blocking, [], "独立 1 起号窗不该报缺号：%s" % blocking)


if __name__ == "__main__":
    unittest.main(verbosity=2)
