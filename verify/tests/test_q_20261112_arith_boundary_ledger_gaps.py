# -*- coding: utf-8 -*-
r"""Q 层三条 fail-open 守卫回归（2026-11-12 全库 62 本复核实测）。

三处都属「页级/账本级证据不足以证明放错」的假阳，修法一律是**单调放宽**
（只可能少报，绝不新增告警），故每条都带反向锁：真缺陷照判。

A. 算术残行守卫：convex optimization ch9 p484 散文行
   ``10-8/20 ~ 0.4 each iteration. This reasonably rapid convergence is
   predicted by``（长 79 < 80 绕过长度闸）被 ``_HEAD_RE`` 读成节号 10.8；
   尾部含 ``each`` 又过了「标题词」判定，于是游标从 §9.3.2 跳到跨章 10.8，
   「只进不退」随后锁死 §9.4~§9.7 全部真节头 → ch9 四枚忠实 ``\tag`` 的
   book_section 全错（4 条假 MISPLACED）。节号后紧跟 ``/数字`` 是分数，
   真节标题不会这样写。

B. 交界页无证据不判：convex optimization ch1/ch5 的 (1.7)/(5.15)/(5.44)
   印在「下一节契约首页」的页顶（页顶书眉已是下一节号，正文节题却在页中
   更下方，属上一节尾部）。页级契约页窗无法分辨归属 → 不判。

C. 局部账本空洞：Cover & Thomas《信息论基础》ch16 p666 密集标签页，
   Voronoi 把标签与展示式整体错配一格，留下「有编号无账身」的空洞
   (16.152=None)，于是 16.150 的正文被算到隔三格的 16.153 上。空洞即
   账本错配的物理证据 → 「b 像 (m)」不构成「b 属于 (m)」的证据。

反向锁：A 的真节标题、B 的真错位、C 的真移位一格（Lee 9.25->9.26）与
三段号（Katok 9.3.2->9.4.2）一律不受影响。
"""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

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
    _heading_num, _compute_order_and_section, SourceFormulaIndex)
from verify.formula_tag.script.tag_formula_pairing import (  # noqa: E402
    _ledger_gap_between)


def _tag(n, latex="$$\nx\n$$\n"):
    return SimpleNamespace(normalized=n, latex=latex)


class _PlainSrc:
    """plain 路径（scope==2）最小替身：只暴露判据实际读取的账本。"""

    def __init__(self, union, book_section, pos, sec_ranges, strong=True):
        self._u = set(union)
        self._book_section = dict(book_section)
        self._book_section_sec = {}
        self._p = dict(pos)
        self._sec_ranges = dict(sec_ranges)
        self._pos_strong = {n: strong for n in union}
        self._full_keys = set()
        self._pos_sec = {}
        self._pos_sec_standalone = {}

    def source_numbers(self):
        return set(self._u)

    def primary_pos(self, n):
        return self._p.get(n)

    def book_section(self, n):
        return self._book_section.get(n)


class ArithResidualHeadingGuard(unittest.TestCase):
    """守卫 A：算术残行不得当节头。"""

    ARITH = ("10-8/20 ~ 0.4 each iteration. This reasonably rapid "
             "convergence is predicted by")

    def test_arithmetic_residual_rejected(self):
        self.assertEqual(len(self.ARITH), 79)
        self.assertIsNone(_heading_num(self.ARITH))

    def test_other_slash_forms_rejected(self):
        for s in ("5.2/3 Some prose line about the ratio here",
                  "9.4/ 20 the error decays as expected in this case"):
            self.assertIsNone(_heading_num(s), s)

    def test_real_titles_still_recognised(self):
        """反向锁：真节标题（含带斜杠的合法标题文字）不受伤。"""
        for s, want in (
                ("9.4 Newton's method", "9.4"),
                ("9.3.2 Examples", "9.3.2"),
                ("5.2 The Lagrange dual problem", "5.2"),
                ("1.3 Convex optimization", "1.3"),
                ("23.2. A partition of A(9)().", "23.2"),
                ("2.3.2 Preliminaries", "2.3.2"),
        ):
            self.assertEqual(_heading_num(s), want, s)

    def test_cursor_not_poisoned_by_cross_chapter_heading(self):
        """反向锁：污染行被拒后，真节头仍能把游标从 9.3.2 推到 9.7。"""
        idx = SourceFormulaIndex.__new__(SourceFormulaIndex)
        idx._cur_heading = "9.3.2"
        idx._sec_keys = {"9.3.2", "9.4", "9.5", "9.6", "9.7"}
        idx._tail_exer_page = None
        idx._tail_exer_anchor_y = None
        idx._sec_ranges = {"9.3.2": (483, 484), "9.4": (488, 495),
                           "9.5": (496, 509), "9.6": (510, 520),
                           "9.7": (522, 525)}
        idx._track_heading(self.ARITH)
        self.assertEqual(idx._cur_heading, "9.3.2", "算术残行不得推进游标")
        idx._track_heading("9.4 Newton's method")
        self.assertEqual(idx._cur_heading, "9.4", "真节头必须能继续推进")


class BoundaryPageNoEvidenceGuard(unittest.TestCase):
    """守卫 B：标签印面页恰为书侧判定节契约首页 -> 不判。"""

    def setUp(self):
        # convex ch5 (5.15): 总结挂 §5.1，书侧判 §5.2；契约 5.1=(229,235)、
        # 5.2=(237,244)，标签印面页 237 == 5.2 首页。
        self.src = _PlainSrc(
            {"5.15"}, {"5.15": "5.2"}, {"5.15": (237, 832.0)},
            {"5.1": (229, 235), "5.2": (237, 244)})
        self.tags = [("5.1", _tag("5.15"))]

    def test_boundary_page_not_flagged(self):
        om, mp = _compute_order_and_section(
            self.tags, self.src, reset_on_section=False)
        self.assertEqual(mp, [], "交界页页级证据不足，不得判 MISPLACED")
        self.assertEqual(om, [])

    def test_real_misplacement_still_flagged(self):
        """反向锁：标签印面页远离契约首页（真错位）照判不误。"""
        self.src._p["5.15"] = (241, 300.0)
        om, mp = _compute_order_and_section(
            self.tags, self.src, reset_on_section=False)
        self.assertEqual([r["number"] for r in mp], ["5.15"])

    def test_no_contract_range_still_flagged(self):
        """反向锁：书侧判定节无契约页窗时守卫不生效，仍照旧判。"""
        self.src._sec_ranges.pop("5.2")
        om, mp = _compute_order_and_section(
            self.tags, self.src, reset_on_section=False)
        self.assertEqual([r["number"] for r in mp], ["5.15"])

    def test_own_section_page_window_guard_unchanged(self):
        """既有契约页窗核（标签落在总结所在节页窗内）行为不变。"""
        self.src._p["5.15"] = (232, 300.0)
        om, mp = _compute_order_and_section(
            self.tags, self.src, reset_on_section=False)
        self.assertEqual(mp, [])


class LedgerGapGuard(unittest.TestCase):
    """守卫 C：印面账本空洞 -> 无证据不判。"""

    def test_gap_between_detected(self):
        printed = {"16.150": ["aaa"], "16.151": ["bbb"],
                   "16.153": ["ccc"]}          # 16.152 空洞
        self.assertTrue(_ledger_gap_between(printed, "16.150", "16.153"))

    def test_true_shift_one_slot_not_exempt(self):
        """反向锁：真移位一格（Lee 9.25 -> 9.26）不得被豁免。"""
        printed = {"9.25": ["aaa"], "9.26": ["bbb"]}
        self.assertFalse(_ledger_gap_between(printed, "9.25", "9.26"))

    def test_full_ledger_not_exempt(self):
        printed = {"16.150": ["a"], "16.151": ["b"],
                   "16.152": ["c"], "16.153": ["d"]}
        self.assertFalse(_ledger_gap_between(printed, "16.150", "16.153"))

    def test_three_component_and_cross_prefix_not_exempt(self):
        """反向锁：Katok 9.3.2 -> 9.4.2 三段号、跨前缀号不走本守卫。"""
        self.assertFalse(_ledger_gap_between({}, "9.3.2", "9.4.2"))
        self.assertFalse(_ledger_gap_between({}, "16.150", "17.153"))

    def test_empty_body_counts_as_gap(self):
        printed = {"16.150": ["a"], "16.151": [],
                   "16.152": ["c"], "16.153": ["d"]}
        self.assertTrue(_ledger_gap_between(printed, "16.150", "16.153"))

    def test_sparse_ledger_not_exempt(self):
        """反向锁：区间内多处无载体 = 正常稀疏账本，不是错配一格。

        全量 pytest 反向钉实测：Koopman (5.32)->(5.17) 之间仅登记 3 个号，
        旧版「任一无载体即空洞」会吞掉原假阳复现，故收紧为恰好一个空洞。
        """
        printed = {"5.17": ["a"], "5.18": ["b"], "5.32": ["c"]}
        self.assertFalse(_ledger_gap_between(printed, "5.17", "5.32"))


if __name__ == "__main__":
    unittest.main()
