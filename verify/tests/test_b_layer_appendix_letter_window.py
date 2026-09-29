r"""B 层窗口锚：附录把字母块升到 `## §A` 时**不得**逐字母开窗（阿诺尔德附录B 实测 2026-09-29）。

背景：单级前缀-less 条目（ordinal type1 / scope3）用 `## §` 标题做计数器窗口锚。
附录B 全篇只有**一条** 定理计数器（定理1..6 印在字母块 D、7..10 在块 F、11..12 在 H、
13 在 J、14..15 在 K），而本书附录的字母块被写成二级标题 `## §F`——旧逻辑只在
「裸字母是三级标题且有数字父节」时继承父节锚，`## §F` 没有父节可继承，于是每个
字母各开一窗，前一窗用掉的号被后一窗报成自己的缺号：

    1:F 缺号 1（序列 7..10 不连续 …）   ← BLOCKING，整章卡死

修复 = 无父节（`_cur_num is None`）的单大写字母 token 同样**不注册锚点**，整篇共用
一个窗；与「字母子块继承父节」同源。真按字母重启计数的书（`Theorem A.1` 型条头）
走 prefix_str 分支，本判据碰不到——所以正向对照必须用**带前缀**的字母条头。

断言：
  1. 负——`## §A/§B/§F` 字母块不产生锚点（否则连续计数器被切开 = 假缺号）；
  2. 数字两级节仍各自开窗（不得顺手把真边界也抹掉）；
  3. 回归保护——`### §A` 挂在 `## §32` 下仍继承父节锚（ch7 形态）。
端到端（附录B 整章 verify PASS）由本书 `_extract/_verify_cn_r8.txt` 留证。
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

from item_numbering_integrity import _section_anchors  # noqa: E402


def _anchors_of(txt):
    _off, anc = _section_anchors(txt)
    return anc


APX_LETTERS = "".join(
    f"\n## §{L} {L} 块小节\n" + "".join(f"\n**定理{n}**：陈述 {n}。\n"
                                        for n in grp) + "\n"
    for L, grp in (("D", (1, 2, 3, 4, 5, 6)), ("F", (7, 8, 9, 10)),
                   ("H", (11, 12)), ("J", (13,)), ("K", (14, 15))))


class TestAnchors(unittest.TestCase):
    def test_letter_blocks_do_not_open_windows(self):
        anc = _anchors_of(APX_LETTERS)
        self.assertEqual([a for a in anc if a.strip() in
                          {"D", "F", "H", "J", "K"}], [],
                         "附录字母块不得各自成为计数器窗口边界")

    def test_numeric_sections_still_window(self):
        txt = ("## §14 第一组\n\n**定理1**：甲。\n\n**定理2**：乙。\n"
               "## §15 第二组\n\n**定理1**：丙。\n")
        anc = _anchors_of(txt)
        self.assertIn("14", anc)
        self.assertIn("15", anc)

    def test_letter_subs_under_numeric_section_still_inherit(self):
        # 回归保护（ch7 形态）：`### §A` 挂在 `## §32` 下 → 锚 = "32"，不另开窗
        txt = ("## §32 外形式\n\n**问题1**：甲。\n\n### §A 情形 A\n\n"
               "**问题2**：乙。\n\n### §B 情形 B\n\n**问题3**：丙。\n")
        anc = _anchors_of(txt)
        self.assertEqual(anc.count("32"), 1)
        self.assertNotIn("A", anc)
        self.assertNotIn("B", anc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
