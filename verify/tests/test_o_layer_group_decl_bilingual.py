"""Regression tests: O 层「组题声明」必须认得中文版形态（Rosen ch10 实测）。

背景：一条印刷声明（`For Exercises 3-9, determine …`）覆盖的 3–9 题**只印图、没有
题面行**，于是清单从 2 直接跳到 10。O 层靠 `_O_GROUP_DECL_RE` 把这些号记进抑制集合
才不报 HEAD 缺号。该正则带英文偏置——介词只有 `For|In`、范围连接词只有 `[-–—]`，
所以同一段落**译成中文后完全不变形**（`对习题 3 至 9，判断…` + 同样的 `<div>` 图组）
却漏匹配，中文版凭空报出 `HEAD gap — missing (6, 7, 8, 9)`（ch10 §10.1 实测 3 条）。
判据本身没错，错的是检测器只看英文 → 修检测器，**不改忠实译文**。

根治后行为（本文件锁定）：
  1. 中文声明（对/对于/针对/在/关于 + 习题|练习 + 至|到|~|～|-–—）覆盖号集；
  2. 英文声明行为不变（回归护栏）；
  3. 端到端：EN 版式与 CN 版式在 `check_ordinal_subitem_gaps` 下**同为 0 告警**，
     而删掉声明行（负向对照）后两版都必须重新报出 HEAD 缺 3–9 → 证明抑制确实来自
     声明，而不是判据被整体放松。
"""
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
for _p in (_ROOT, str(Path(_ROOT) / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from subitem_continuity import (_o_group_decl_ordinals,
                                check_ordinal_subitem_gaps)


class TestGroupDeclOrdinals(unittest.TestCase):
    def test_chinese_declarations(self):
        cases = {
            "对习题 3 至 9，判断所给的图含有有向边还是无向边。": range(3, 10),
            "对于练习 5 到 11，求给定图的色数。": range(5, 12),
            "针对习题 13～15，判断所画图形是否可一笔画出。": range(13, 16),
            "在习题 7~9 中给出模型。": range(7, 10),
            "习题3至5：画出图。": range(3, 6),
            "对习题 4，判断该图是否为简单图。": [4],
        }
        for line, expected in cases.items():
            with self.subTest(line=line):
                self.assertEqual(_o_group_decl_ordinals(line), set(expected))

    def test_english_declarations_still_match(self):
        cases = {
            "For Exercises 3-9, determine whether the graph shown has edges.": range(3, 10),
            "In Exercises 5-11 find the chromatic number of the given graph.": range(5, 12),
            "**Exercises 13-15.** Determine whether the picture shown can be drawn.": range(13, 16),
            "Exercise 7. How many vertices does a cube have?": [7],
        }
        for line, expected in cases.items():
            with self.subTest(line=line):
                self.assertEqual(_o_group_decl_ordinals(line), set(expected))

    def test_non_declarations_not_matched(self):
        for line in (
                "10. 对习题 3 至 9 中每一幅不是简单图的无向图，找出一组边。",
                "见习题 3 至 9 的答案。",              # 句中回指，非行首声明
                "本节习题答案见附录。",
                "## §10.1 习题",
                "Exercises 1-4000 are all picture-only.",  # 超跨度上限
        ):
            with self.subTest(line=line):
                self.assertEqual(_o_group_decl_ordinals(line), set())


HEAD = ("1. 画出图模型，并指明所使用的图的类型。\n"
        "   a) 当两座城市之间有航班时连一条边。\n"
        "   b) 两座城市之间每有一个航班连一条边。\n"
        "2. 对于主要城市之间的公路系统，各可用哪一种图来建模？\n"
        "   a) 有州际公路时有一条边？\n"
        "   b) 每有一条州际公路就有一条边？\n\n")
TAIL = ("10. 找出一组边，使得删去它们之后该图成为简单图。\n"
        "11. 试证：$G$ 的顶点集上的关系 $R$ 是对称的、反自反的。\n"
        "12. 试证：$G$ 的顶点集上的关系 $R$ 是对称的、自反的。\n"
        "13. 构造下列各集合族的交集图。\n"
        "    a) $A_1 = \\{0, 2, 4\\}$\n"
        "    b) $A_2 = \\{0, 1, 2\\}$\n")
IMAGES = ("\n<div style=\"display:flex\">\n"
          "  <img src=\"figure/ch10_fig1.png\" alt=\"Graphs for Exercises 3 and 4.\" width=\"37%\">\n"
          "  <img src=\"figure/ch10_fig2.png\" alt=\"Graphs for Exercises 5, 6, and 7.\" width=\"37%\">\n"
          "  <img src=\"figure/ch10_fig3.png\" alt=\"Graph for Exercises 8 and 9.\" width=\"17%\">\n"
          "</div>\n\n")


def _gaps(body):
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ch10.md"
        p.write_text(body, encoding="utf-8")
        return check_ordinal_subitem_gaps(str(p))


class TestHeadGapSuppression(unittest.TestCase):
    def test_chinese_and_english_declarations_both_suppress(self):
        en = HEAD + "For Exercises 3-9, determine whether the graph shown has edges." \
            + IMAGES + TAIL
        cn = HEAD + "对习题 3 至 9，判断所给的图含有有向边还是无向边。" \
            + IMAGES + TAIL
        self.assertEqual(_gaps(en), [])
        self.assertEqual(_gaps(cn), [])

    def test_missing_declaration_still_reports(self):
        # 负向对照：声明行换成不含号数的普通引导语 → 3–9 无人覆盖，必须报 HEAD 缺号
        body = HEAD + "判断下面各图。" + IMAGES + TAIL
        gaps = _gaps(body)
        self.assertTrue(any("HEAD gap" in g and "missing (3, 4, 5" in g
                            for g in gaps), msg=str(gaps))


if __name__ == "__main__":
    unittest.main(verbosity=2)
