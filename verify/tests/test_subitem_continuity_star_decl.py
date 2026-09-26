"""
test_subitem_continuity_star_decl.py — O 层两处「题面存在但看不见」假报回归
（Rosen《Discrete Mathematics》8e ch10 §10.1/§10.5/§10.7/§10.8 习题实测，2026-09-26）。

两处盲点都会让**真实存在于印刷书里**的题号对本层隐形：

1. 难度星号 `**27. Find the crossing numbers …`
   Rosen 用 `*` / `**` 前缀标习题难度（不是粗体）。Pattern B 要求闭合 `**` 紧贴
   编号（`**27.**`），Pattern C 只容许**一个**前导 `*`（do Carmo 的 `*5.`），
   于是整条题面隐形 → `…26, 28…` 凭空 INTERNAL 缺 (27)（实测 ch10 两处）。
   修复 = `_O_STAR_NUM_RE`：仅对**数字**标签放宽到两个前导星号，字母标签的解释
   一字不动 → 不会把 alpha/roman 块重分类。

2. 组题声明 `**Exercises 13-15.** Determine whether the picture shown …`
   声明覆盖的题**只印一张图**、没有以编号打头的题面行，于是清单从 12 跳到 16
   （实测 ch10 §10.5 缺 13-15、§10.6 缺 2-4、§10.1 缺 6-9、§10.2 缺 58-60）。
   修复 = `_o_group_decl_ordinals`：声明号记入抑制集合（`block_meta[..]['decl']`，
   归属规则见 `_O_GROUP_DECL_RE`），**绝不进 item 序列**（进序列会改变 min/max
   与块划分，可能造出新告警）。

负向（必须仍然报错，否则本层失去意义）：
* 无声明时同一条清单的真缺号照旧报 INTERNAL / HEAD；
* 跨度超 `_O_DECL_MAX_SPAN` 的「声明」视为误匹配，不产生任何抑制；
* `**Note 3. …` / `**3.1.4.**` 之类行不得被 Pattern D 当成条目。
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

from subitem_continuity import (  # noqa: E402
    _o_match_line, _o_group_decl_ordinals, check_ordinal_subitem_gaps,
)


def _gaps(md_text):
    d = tempfile.mkdtemp()
    p = os.path.join(d, 'ch10.md')
    with open(p, 'w', encoding='utf-8') as f:
        f.write(md_text)
    return check_ordinal_subitem_gaps(p)


def _internal(got):
    return [g for g in got if 'INTERNAL gap' in g]


def _items(nums):
    """连续题面行（每条一行、空行分隔 → 同属一个块）。"""
    return "".join("%d. Exercise text number %d.\n\n" % (n, n) for n in nums)


class StarNumberedItemTest(unittest.TestCase):
    """难度星号题面必须在场。"""

    def test_double_star_numeric_item_seen(self):
        self.assertEqual(
            _o_match_line("**27. Find the crossing numbers of each of these "
                          "nonplanar graphs. a) $K_5$ b) $K_6$"), ['27'])

    def test_single_star_still_seen(self):
        self.assertEqual(_o_match_line("*28. Find the crossing number of the "
                                       "Petersen graph."), ['28'])

    def test_alpha_bold_forms_unchanged(self):
        # 字母标签不得因这次放宽改判形态
        self.assertEqual(_o_match_line("**i)** Prove the dual statement."), ['i'])
        self.assertEqual(_o_match_line("**Note 3. the star is not a marker.**"), [])
        self.assertEqual(_o_match_line("**3.1.4.** Section heading."), [])

    def test_star_item_closes_real_gap(self):
        md = ("**Exercises**\n\n" + _items([1, 2]) +
              "**3. Find the minimum number of queens controlling an $n \\times n$"
              " chessboard for a) $n = 3$.\n\n"
              "*4. Find the crossing number of the Petersen graph.\n\n" +
              _items([5]))
        self.assertEqual(_gaps(md), [])

    def test_without_the_star_line_the_hole_is_real(self):
        # 负向：删掉带星号的那条题面 → 3 号真的没了，必须报。
        md = ("**Exercises**\n\n" + _items([1, 2]) +
              "*4. Find the crossing number of the Petersen graph.\n\n" +
              _items([5, 6]))
        got = _gaps(md)
        self.assertTrue(any('missing: (3)' in g for g in got), got)


class GroupDeclarationTest(unittest.TestCase):
    """`Exercises A-B` 组题声明 = 那些题只印图，号数算已覆盖。"""

    DECL = ("**Exercises 13-15.** Determine whether the picture shown can be "
            "drawn with a pencil in a continuous motion without lifting it.\n\n")

    def test_decl_ordinals_captured(self):
        self.assertEqual(_o_group_decl_ordinals(
            "**Exercises 13-15.** Determine whether the picture shown can be "
            "drawn with a pencil in a continuous motion."), {13, 14, 15})
        self.assertEqual(_o_group_decl_ordinals(
            "For Exercises 3-9, determine whether the graph shown has directed "
            "or undirected edges."), set(range(3, 10)))
        self.assertEqual(_o_group_decl_ordinals(
            "In Exercises 5-11 find the chromatic number of the given graph."),
            set(range(5, 12)))
        self.assertEqual(_o_group_decl_ordinals(
            "**Exercise 54.** Show that the graph displayed here is "
            "self-complementary."), {54})
        self.assertEqual(_o_group_decl_ordinals(
            "See Exercises 3-5 in the Supplementary Exercises for more."), set())

    def test_internal_figure_only_hole_suppressed(self):
        # ch10 §10.5 实测形态：11,12 →（图题 13-15）→ 16,17,18
        md = ("**Exercises**\n\n" + _items(range(1, 13)) + self.DECL +
              _items(range(16, 19)))
        self.assertEqual(_gaps(md), [])

    def test_without_the_declaration_it_is_a_real_hole(self):
        md = ("**Exercises**\n\n" + _items(range(1, 13)) +
              _items(range(16, 19)))
        got = _gaps(md)
        self.assertTrue(any('missing: (13, 14, 15)' in g for g in got), got)

    def test_head_figure_only_hole_suppressed(self):
        # ch10 §10.1 实测形态：声明 3-9，题面只有 1、2 与 10、11、12
        md = ("**Exercises**\n\n"
              "For Exercises 3-9, determine whether the graph shown has directed "
              "or undirected edges, whether it has multiple edges, and whether it "
              "has one or more loops.\n\n" + _items([1, 2]) +
              "<div>\n  <img src=\"figure/a.png\" alt=\"Graphs\">\n</div>\n\n" +
              _items(range(10, 13)))
        self.assertEqual(_gaps(md), [])

    def test_oversized_span_not_treated_as_declaration(self):
        self.assertEqual(_o_group_decl_ordinals(
            "**Exercises 3-400.** This is clearly a misparse of a page range."),
            set())


if __name__ == '__main__':
    unittest.main()
