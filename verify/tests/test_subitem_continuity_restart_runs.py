"""
test_subitem_continuity_restart_runs.py — O 层「重启段」INTERNAL 假报回归
（Rosen《Discrete Mathematics》8e ch9 章末补章习题实测，2026-09-26）。

盲点：章末一个块里**并着多条各自从 1 重启的独立清单**——

    ... 48. Show that ...      ← Supplementary Exercises 的尾巴
    49. Show that ...
    50. Show that ...
    **Computer Projects**
    1. Given the matrix ...    ← 新清单，从 1 重启
    ...
    15. Given a partial ordering ...
    **Computations and Explorations**
    1. Display all ...
    ... 9. ...

题与题行距 ≤4（标题行只撑开 2 行），于是四张清单被并成**一个块**。旧实现按整块
min–max 求缺 → 报 `present: (1..15, 42..50), missing: (16, ..., 41)`，
26 个**幽灵缺号**（那些号属于另一条清单，本就不该出现在这条里）。

修复：`_o_split_restarts` 按阅读顺序在**数值下降处**切段，INTERNAL 只在段内求缺；
缺号只要在「前一窗口块」**或同块其他段**出现过即抑制。两处都只减少告警。

负向（必须仍然报错，否则本层失去意义）：
* 单条单调清单中间真缺一个号 → 照旧报 INTERNAL；
* 段内真缺号、但该号只是**同块别段**也没有 → 照旧报（`prev_ords | block_union`
  抑制不吃掉它）；
* HEAD 判定口径不变（仍按整块 min）。
"""
import os
import re
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

from subitem_continuity import (  # noqa: E402
    _o_split_restarts, check_ordinal_subitem_gaps,
)


def _gaps(md_text):
    d = tempfile.mkdtemp()
    p = os.path.join(d, 'ch9.md')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(md_text)
    return check_ordinal_subitem_gaps(p)


class SplitRestartsTest(unittest.TestCase):
    def test_splits_at_each_decrease(self):
        items = [(41, 48), (43, 49), (45, 50), (49, 1), (51, 2), (53, 3)]
        runs = _o_split_restarts(items)
        self.assertEqual([[v for _, v in r] for r in runs],
                         [[48, 49, 50], [1, 2, 3]])

    def test_monotone_list_is_one_run(self):
        items = [(10, 28), (12, 29), (14, 30), (16, 31)]
        self.assertEqual(len(_o_split_restarts(items)), 1)


class FusedRestartListsTest(unittest.TestCase):
    """章末多清单并块：不得凭空造出 16..41 一串幽灵号。"""

    MD = ("# Chapter 9\n\n"
          "**Supplementary Exercises**\n\n"
          "46. Give an example of a finite lattice.\n\n"
          "47. Show that the lattice is complemented.\n\n"
          "48. Show that if L is a finite distributive lattice.\n\n"
          "49. Show that the game of Chomp has a winning strategy.\n\n"
          "50. Show that if S has a greatest element b.\n\n"
          "**Computer Projects** Write programs with these input and output.\n\n"
          "1. Given the matrix representing a relation, determine reflexivity.\n\n"
          "2. Given the matrix representing a relation, determine symmetry.\n\n"
          "3. Given the matrix representing a relation, determine transitivity.\n\n"
          "4. Given a positive integer n, display all the relations.\n\n"
          "**Computations and Explorations** Use a computational program.\n\n"
          "1. Display all the different relations on a set with four elements.\n\n"
          "2. Display all the different reflexive and symmetric relations.\n\n"
          "3. Display all the reflexive and transitive relations.\n")

    def test_no_phantom_internal_gap(self):
        self.assertEqual(_gaps(self.MD), [])


class StillReportedTest(unittest.TestCase):
    """负向：真缺号不被重启切段吃掉。"""

    def test_real_hole_in_monotone_run_still_reported(self):
        md = ("**Supplementary Exercises**\n\n"
              "28. Find all chains in the posets.\n\n"
              "29. Find all antichains in the posets.\n\n"
              "30. Find an antichain with the greatest number of elements.\n\n"
              "31. Show that every maximal chain contains a minimal element.\n\n"
              "32. Show that every finite poset can be partitioned.\n\n"
              "33. Show that in any group of mn + 1 people there is either.\n\n"
              "35. Show that the principle of well-founded induction is valid.\n\n"
              "36. Let R be the relation on the set of all functions.\n\n"
              "37. Let R be a quasi-ordering on a set A.\n")
        got = _gaps(md)
        internal = [g for g in got if 'INTERNAL gap' in g]
        # （清单从 28 起、前文无同类编号 → 另有一条 HEAD，属既有口径，本例不关心）
        self.assertEqual(len(internal), 1, got)
        # 只列未抑制的缺号（旧版会把 min..max 区间内的号全列一遍）
        self.assertIn('missing: (34)', internal[0])
        self.assertNotIn('missing: (34, 35', internal[0])

    def test_gap_not_in_other_runs_still_reported(self):
        # 42..50 段真缺 45；后面 Computer Projects 1..3 不含 45 → 必须照报。
        md = ("**Supplementary Exercises**\n\n"
              "42. Show that every finite lattice is bounded.\n\n"
              "43. Give an example of a lattice that is not distributive.\n\n"
              "44. Show that the lattice of power set is distributive.\n\n"
              "46. Give an example of a finite lattice with complements.\n\n"
              "47. Show that the lattice of power set is complemented.\n\n"
              "48. Show that if L is a finite distributive lattice.\n\n"
              "49. Show that the game of Chomp has a winning strategy.\n\n"
              "50. Show that if S has a greatest element b.\n\n"
              "**Computer Projects**\n\n"
              "1. Given the matrix representing a relation, determine reflexivity.\n\n"
              "2. Given the matrix representing a relation, determine symmetry.\n\n"
              "3. Given the matrix representing a relation, determine transitivity.\n")
        got = _gaps(md)
        self.assertTrue(any('INTERNAL gap' in g and 'missing: (45)' in g
                            for g in got), got)

    def test_head_reporting_lists_only_unsuppressed(self):
        # 数字清单从 12 起，1..9 在更早的块里已有（宽抑制），只有 10、11 真缺
        # → HEAD 仍报（判定不变），但显示里不得再列 1..9。
        md = ("# Chapter 10\n\n"
              "**Exercises**\n\n"
              "1. Show that the graph is simple.\n\n"
              "2. What kind of graph can be used to model a highway system.\n\n"
              "3. Determine whether the graph shown has directed edges.\n\n"
              "4. Determine whether the graph shown has multiple edges.\n\n"
              "5. Determine whether the graph shown has loops.\n\n"
              "6. Determine whether the graph is a simple graph.\n\n"
              "7. Determine whether the graph model is directed.\n\n"
              "8. Determine whether the graph has a loop at every vertex.\n\n"
              "9. Determine whether the multigraph is finite.\n\n"
              "<div>\n  <img src=\"figure/a.png\" alt=\"Graphs\">\n</div>\n\n"
              "12. Let G be a simple graph. Show that the relation R is reflexive.\n\n"
              "13. Let G be an undirected graph with a loop at every vertex.\n\n"
              "14. The intersection graph of a collection of sets is a graph.\n\n"
              "15. Use the niche overlap graph to determine the species.\n")
        got = _gaps(md)
        self.assertEqual(len(got), 1, got)
        m = re.search(r'missing \(([^)]*)\)', got[0])
        self.assertIsNotNone(m, got[0])
        listed = [x.strip() for x in m.group(1).split(',')]
        self.assertIn('10', listed)
        self.assertIn('11', listed)
        self.assertNotIn('3', listed)


if __name__ == '__main__':
    unittest.main()
