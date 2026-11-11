# -*- coding: utf-8 -*-
r"""Q 层页眉守卫回归（Cover & Thomas《信息论基础》2nd ed 实测 2026-11-11）。

扫描书的书眉把「本页起始的新节名」以**无空格大写词**紧排、并把**页码粘在词尾**
（p107 页眉 ``4.4SECONDLAWOFTHERMODYNAMICS81``，同页真节标题在页中 y=555 带
空格）。该形态撞不过任何既有守卫（无空格粘连不违规、大写尾不违规、尾粘页码
无碍），而「书眉命名的节恰好真实起始于本页」使 ``_track_heading`` 的 ±2 契约
锚核必然放行 → 游标在页首即被推进到新节，印在页首（上一节在交界页的延续部分）
的公式整批错归 → 假 MISPLACED（本书 ch4 (4.43) / ch12 (12.40)(12.41) /
ch13 (13.30) 三组实测）。

守卫只拒「无空格大写尾巴 + 紧贴尾数字前 ≥4 连续大写」的书眉形态；真节标题
（带空格 / OCR 丢空格但结尾是字母 / 中文 / 短大写词收尾）照旧识别。
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
import lib.boot as _boot  # noqa: E402
_boot.setup()

from verify.formula_tag.script.formula_tag import (  # noqa: E402
    _heading_num, SourceFormulaIndex)


class RunningHeadGluedPageNoTest(unittest.TestCase):
    def test_running_heads_rejected(self):
        """书眉：大写节名紧排 + 页码粘尾（本书三处实测原串）。"""
        for s in ("4.4SECONDLAWOFTHERMODYNAMICS81",
                  "12.6BURG'SMAXIMUMENTROPYTHEOREM417",
                  "13.2UNIVERSALCODINGFORBINARYSEQUENCES433"):
            self.assertIsNone(_heading_num(s), s)

    def test_real_titles_still_recognised(self):
        """真节标题四种形态不受伤：带空格 / 丢空格结尾是字母 / 短大写词
        收尾 / 中文与字母标题既有形态。

        注意「带空格 + 页码粘尾」（如 ``4.4SECOND LAW OFTHERMODYNAMICS81``）
        不在此列：它与 p459 书眉 ``13.2UNIVERSAL CODINGFOR BINARY
        SEQUENCES433`` 形状不可区分（无 y 坐标纯文本无法分辨页眉/页中），
        而语料 27,588 页全量扫描证明该形状的命中 90/90 全部位于页顶书眉
        （y≤149），页中真标题无一此形态——故按设计拒绝（见
        test_running_heads_rejected）。
        """
        for s, want in (
                ("4.4SECOND LAW OFTHERMODYNAMICS", "4.4"),
                ("4.4SECONDLAWOFTHERMODYNAMICS", "4.4"),
                ("2.3.2 Preliminaries", "2.3.2"),
                ("23.2. A partition of A(9)().", "23.2"),
                ("5.3. e-Orbits", "5.3"),
                ("4.4图变换原理", "4.4"),
        ):
            self.assertEqual(_heading_num(s), want, s)

    def test_short_glued_titles_not_swept(self):
        """短大写词/混合大小写收尾的真节题（<4 连续大写）不受守卫波及。

        ``4.4B5`` 单字母尾在改前即被既有「≥2 连续字母」接受规则拒绝
        （与本守卫无关），一并锁定防回归。
        """
        for s, want in (
                ("4.4UTF8", "4.4"),
                ("4.4IPv6", "4.4"),
                ("4.4CO2", "4.4"),
                ("4.4B5", None),
        ):
            self.assertEqual(_heading_num(s), want, s)

    def test_cursor_never_advances_on_running_head(self):
        """端到端语义：页眉不得推进游标（从无节出发也不认）；块序在后的
        真节标题照常接管。"""
        idx = SourceFormulaIndex.__new__(SourceFormulaIndex)
        idx._cur_heading = None
        idx._sec_keys = None
        idx._tail_exer_page = None
        idx._tail_exer_anchor_y = None
        idx._sec_ranges = {}
        idx._track_heading("4.4SECONDLAWOFTHERMODYNAMICS81", pg=107)
        self.assertIsNone(idx._cur_heading, "书眉不得作为首个节头")
        idx._cur_heading = "4.3"
        idx._track_heading("4.4SECONDLAWOFTHERMODYNAMICS81", pg=107)
        self.assertEqual(idx._cur_heading, "4.3", "书眉不得推进游标")
        idx._track_heading("4.4SECOND LAW OFTHERMODYNAMICS", pg=107)
        self.assertEqual(idx._cur_heading, "4.4", "真节标题照常接管")


if __name__ == "__main__":
    unittest.main()
