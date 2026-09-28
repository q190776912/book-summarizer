# -*- coding: utf-8 -*-
"""字母子块重启计数器的抽取判据（2026-09-28 Arnold《经典力学的数学方法》实测）。

现场（中文扫描版，`sections_global` + ordinal 组 `scope==3`）：书里 §N 内还印有一层
**大写字母子块**（`A.` / `B.` / `D.` …），而 例 / 问题 一类计数器**在每个字母块内
从 1 起重**：
  · §8 D 块 问题1..6（p42-43）→ E 块 问题1..3（p47）；
  · §14 B 块 例1..4（p64）→ D 块 例1..2（p65）。
同时**另有**计数器跨字母块**连续**：§36 问题1..14 横跨 C/D/E 三块、附录B 定理1..15
横跨 D/F/H/J/K 五块。抽取器必须同时守住这两种形态。

旧实现两处缺陷（本测试的负向部分）：
  ① 分桶边界判据把尾部非数字的窗口号（"14.D"）当作父节 "14" 的**嵌套号**并回同
     一桶 ⇒ 后一字母块的起重条被 `buckets.setdefault` 按最早页吃掉，**整条从契约
     里静默消失**（正文只作为节描述残留），B 层却报出无法解释的缺号；
  ② 放行判据只认「同桶内已有该号的**直接后继**」⇒ 每桶**最后**一条（无后继）永远
     不放行，跨块连续计数器（问题1..14 分成 1..5 / 6..14 两段）被腰斩。
现判据：字母窗口开新桶（`_tail.isdigit()` 才判嵌套）+ 放行三种形态——章级首见、
同桶连续（`n == 桶内已放行最大值+1`）、**同父节连续**（`n == 父节已放行最大值+1`，
跨字母块的连续计数器）、同桶存在直接后继（回指链）。

同日追加的三条收紧（各自有实测案，见下方对应测试类）：
  ③「后继」必须**同标签词**且**文档序在后**——本书各类型计数器并行（引理1/引理2、
    系1..9），跨类型的号不是重起证据；已用过的号往回看也不是；
  ④ 候选排序与判据一律用 **seq（页内块序 = 文档序）**，不再用 `(页, 号)`：同页
    「前节尾条 问题6 + 本节起重 问题1..3」按号重排会把尾条整条丢掉；
  ⑤ 号后助词判据的空白写在**负向前查内部**，否则量词回溯让出空格、环视停在
    空白上，「定理2 的证明…」这类回指照样入账。

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_letterblock_restart_cn_single.py
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

from extract_items_cn_single import extract_items_cn_single   # noqa: E402
from verify_config import GroupConfig                          # noqa: E402


def _groups():
    return [GroupConfig(type=1, name=["例"], scope=3),
            GroupConfig(type=1, name=["问题"], scope=3)]


GROUPS = _groups()
RST = ({"例", "问题"},)
# 本书各类型计数器**并行**（引理1/引理2、系1..系9），跨类型判据测试要用到的标签。
GROUPS_ALL = [GroupConfig(type=1, name=[n], scope=3)
              for n in ("定理", "引理", "系", "例", "问题", "注", "定义")]
RST_ALL = {"定理", "引理", "系", "例", "问题", "注", "定义"}


def _mk_pages(d, pages):
    """pages = [[line, ...], ...] -> page_001.json ...（每页一个 text 块列表）"""
    for i, lines in enumerate(pages, start=1):
        with open(os.path.join(d, "page_%03d.json" % i), "w", encoding="utf-8") as f:
            json.dump({"text": [{"text": t} for t in lines], "formulas": []}, f)


def _keys(pages, windows, groups=None, rst=None):
    with tempfile.TemporaryDirectory() as d:
        _mk_pages(d, pages)
        rst = ({c for c in (rst or RST[0])}, list(windows))
        return [it["key"] for it in extract_items_cn_single(
            d, 1, len(pages), groups=groups or GROUPS, restart_per_section=rst)]


def _items(pages, windows, groups=None, rst=None):
    with tempfile.TemporaryDirectory() as d:
        _mk_pages(d, pages)
        rst = ({c for c in (rst or RST[0])}, list(windows))
        return extract_items_cn_single(
            d, 1, len(pages), groups=groups or GROUPS, restart_per_section=rst)

class TestLetterBlockRestart(unittest.TestCase):
    """字母块 = 真重启边界：同键跨块是两条，不是引用回指。"""

    def test_letters_open_new_bucket(self):
        # §14：B 块 例1..4（p64），D 块 例1..2（p65）——旧判据丢 D 块两条。
        pages = [
            ["§14 辛空间上的线性代数与辛群", "例1 设 A 是…"],
            ["例2 例2 任一辛基的矩阵…", "例3 例3 辛群是…", "例4 例4 命题…"],
            ["D. 辛群的局部结构", "例1 例1 辛群的维数…", "例2 例2 考察…"],
        ]
        win = [(1, "14"), (1, "14.B"), (3, "14.D")]
        got = _keys(pages, win)
        self.assertEqual(got.count("例1"), 2, "跨字母块的 例1 是两条真条目")
        self.assertEqual(got.count("例2"), 2, "跨字母块的 例2 是两条真条目")
        self.assertEqual(sorted(set(got)), ["例1", "例2", "例3", "例4"])

    def test_tail_of_bucket_is_kept(self):
        # §8：D 块 问题1..6 与 E 块 问题1..3。旧「只认直接后继」判据把每桶
        # **最后**一条（问题6 / 问题3）判成无后继而丢弃。
        pages = [
            ["§8 在有心力场中的运动的研究", "问题1 证明近心点…", "问题2 求接近于…"],
            ["问题3 对U 的哪些值…", "问题4 设当 r 趋于无穷…",
             "问题5 令 U 等于…", "问题6 求出有界轨道…"],
            ["E. 用复数表示的平面有心力场", "问题1 证明胡克椭圆…",
             "问题2 证明点在幂场…", "问题3 设引力与幂成正比…"],
        ]
        win = [(1, "8"), (1, "8.D"), (3, "8.E")]
        got = _keys(pages, win)
        self.assertEqual(got.count("问题6"), 1, "桶尾条目不得因「无后继」被丢")
        self.assertEqual(got.count("问题3"), 2, "两块各有一条 问题3")
        self.assertEqual(len(got), 9)

    def test_continuous_counter_across_letters_kept(self):
        # §36 形态：问题1..14 **跨** C/D/E 三块连续计数（每块首不是起重）。
        pages = [
            ["§36 哈密顿方程的正则极小化", "C. 作用量变量", "问题1 …", "问题2 …"],
            ["D. 平均化", "问题3 …", "问题4 …"],
            ["E. 多自由度情形", "问题5 …", "问题6 …"],
        ]
        win = [(1, "36"), (1, "36.C"), (2, "36.D"), (3, "36.E")]
        got = _keys(pages, win)
        self.assertEqual(got, ["问题%d" % n for n in range(1, 7)],
                         "同父节内连续的计数器须全数放行，且不重排")


class TestLetterBlockStillGuardsBackReferences(unittest.TestCase):
    """负向：同一字母块内的同号再现（引用回指）仍须压掉。"""

    def test_same_bucket_duplicate_dropped(self):
        pages = [
            ["§14 B. 辛空间", "例1 设 A 是辛矩阵…", "例2 由例1 可见…"],
            ["例3 例3 辛群是李群…"],
        ]
        win = [(1, "14"), (1, "14.B")]
        got = _keys(pages, win)
        self.assertEqual(got.count("例1"), 1)
        self.assertEqual(got.count("例2"), 1)

    def test_reference_line_before_head_does_not_reorder(self):
        """引用行（'见例2 …'）不放开新条目，也不打乱页序输出。"""
        pages = [
            ["§9 三维空间中质点的运动", "A. 角动量", "问题1 证明…"],
            ["B. 守恒律", "问题1 由问题1 的结论…", "问题2 设…"],
        ]
        win = [(1, "9"), (1, "9.A"), (2, "9.B")]
        got = _keys(pages, win)
        self.assertEqual(got, ["问题1", "问题1", "问题2"])


class TestSuccessorMustMatchLabelAndReadingOrder(unittest.TestCase):
    """放行判据 ③ 的三维：同桶、**同标签**、文档序在后（2026-09-28 实测三案）。"""

    def test_other_label_successor_does_not_release(self):
        """§39.F 案：p183 印的是回指句「引理1 说明…李括弧」，同桶里在它之后
        只有 §40 的 **系2**——跨类型号不构成「引理计数器在此重起」的证据。"""
        pages = [
            ["§39 F. 附录：李群的李代数", "引理1 在0处混合偏导数等于交换子…",
             "引理2 算子 LBLA-LALB 是一阶线性微分算子."],
            ["§40 哈密顿函数的李代数", "A. 两个函数的泊松括弧",
             "引理1 说明矢量场的泊松括弧可以定义为李群之李括弧",
             "系1 函数F是哈密顿函数为H的相流之首次积分",
             "系2 函数F和H的泊松括弧等于1-形式dF在IdH上之值."],
        ]
        win = [(1, "39"), (1, "39.F"), (2, "40"), (2, "40.A")]
        got = _keys(pages, win, groups=GROUPS_ALL, rst=RST_ALL)
        self.assertEqual(got.count("引理1"), 1,
                         "跨类型后继（系2）放开了回指句 → 假 引理1")
        self.assertEqual(got.count("引理2"), 1)
        self.assertEqual(got.count("系2"), 1, "真条目不得受影响")

    def test_already_consumed_successor_does_not_release(self):
        """§16 案：p73 的回指句「例1 到例3 中的变换…」在后，而 §16 的真 例1/例2
        早在 p72 入账——「后继」只在其**后面**才算重起证据，不能往回看。"""
        pages = [
            ["§16 正则变换", "例1 设 S 是…", "例2 取生成函数…", "例3 令…"],
            ["例1 到例3 中的变换都与力学有密切关系"],
        ]
        win = [(1, "16"), (2, "17")]
        got = _keys(pages, win)
        self.assertEqual(got.count("例1"), 1, "已用过的后继不是本页重起的证据")

    def test_same_page_restart_keeps_both_in_reading_order(self):
        """§34 案（文档序）：前一节尾条 问题6 与后一节起重 问题1..3 **印在同一页**。
        旧实现按 `(页, 号)` 排序，起重条被排到尾条**前面**，尾条于是既不成续接又
        无后继 → 从契约里消失（内容整条丢）。按文档序：尾条先入账（父桶续接），
        起重条再由后继放行，两条都在。"""
        pages = [
            ["§33 节前一页", "问题1 …", "问题2 …", "问题3 …", "问题4 …", "问题5 …"],
            ["问题6 这是§33印在§34起页上的尾条", "问题1 §34起重真头",
             "问题2 §34真头", "问题3 §34真头"],
        ]
        win = [(1, "33"), (2, "34")]
        items = _items(pages, win)
        got = [it["key"] for it in items]
        self.assertEqual(got.count("问题6"), 1, "同页尾条不得因按号重排而丢失")
        self.assertEqual(got.count("问题1"), 2, "§33 / §34 各有一条 问题1")
        six = [it for it in items if it["key"] == "问题6"][0]
        self.assertEqual((six["page"], six["text"][:6]), (2, "问题6 这是"))


class TestParticleLookoutCrossesOcrSpace(unittest.TestCase):
    """号后助词判据须**跨空白**生效（Arnold §24 实测 2026-09-28）。

    「定理2 的证明里面的椭球的任一k 维截面…」不是条目而是「定理2 的证明」的
    回指。旧写法 `\\s*(?!['的…'])` 里吞空白的量词可回溯让出那个空格，环视看到
    的是空格（永不是助词）→ 假条头入账。空白必须在环视**内部**。
    """

    def test_particle_after_space_is_not_a_head(self):
        pages = [
            ["§24 E. 椭球坐标", "定理1 若…则…"],
            ["定理2 的证明里面的椭球的任一k 维截面之最小主半轴不大于 b"],
        ]
        got = _keys(pages, [(1, "24")],
                    groups=[GroupConfig(type=1, name=["定理"], scope=3)],
                    rst={"定理"})
        self.assertNotIn("定理2", got, "「定理2 的证明…」是回指，不是条目")
        self.assertIn("定理1", got)

    def test_statement_after_space_is_a_head(self):
        """正向对照：号后空白 + 陈述句仍须入账（本书大量真条头就是这个形状）。"""
        pages = [
            ["§24 E. 椭球坐标", "定理1 若…则…"],
            ["定理2 若主半轴为 a1 ≥ a2 ≥… 的椭球包含…"],
        ]
        got = _keys(pages, [(1, "24")],
                    groups=[GroupConfig(type=1, name=["定理"], scope=3)],
                    rst={"定理"})
        self.assertEqual(sorted(got), ["定理1", "定理2"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
