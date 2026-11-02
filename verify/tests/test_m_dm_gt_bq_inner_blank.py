# -*- coding: utf-8 -*-
"""test_m_dm_gt_bq_inner_blank.py — M 层 `check_displaymath_gt` 的第二条子判据：
引用块 display math 的**围栏内空 `>` 行**（乙形）。

为什么要进闸（不是排版洁癖）：CommonMark 里块引用内的空行结束当前块 ⇒ `> $$` 围栏被劈成
两段，关门 `> $$` 与后面的散文并进同一段（cmark-gfm 实测见 `bq_math_inner_blanks` docstring）。
读者看到的是「数学块不闭合 + 散文被吞」。

🔴 与修复工具（`tools/fix_bq_math_blank.py`）的分工：判据**一律报**（含「空行两侧都有内容」
那种删了会并块的形态），工具只修能安全删的、其余计 REFUSE。本测试两侧都要钉住：
  * 甲形（空行在围栏外）**必须 0 命中**——否则就是假阳，会把 5 万处正常块全报掉；
  * 乙形必须命中并点名空行行号；
  * 原有子判据（顶层 `$$…$$` 内泄 `>`）不能被改写出血——返回类型仍是**字符串列表**。
"""
import io
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
import lib.boot as _boot  # noqa: E402
_boot.setup()

from format_verify import bq_math_inner_blanks, check_displaymath_gt  # noqa: E402

JIA = [u"**例1**：", u">", u"> $$", u"> x_1 + x_2 = 2", u"> $$", u">", u"> 后文散文。"]
YI = [u"**例1**：", u">", u"> $$", u"> x_1 + x_2 = 2", u">", u"> $$", u">", u"> 后文散文。"]


def _md(lines):
    fd = tempfile.mkdtemp(prefix="mdm_")
    p = os.path.join(fd, "c.md")
    with io.open(p, "w", encoding="utf-8", newline="\n") as f:
        f.write(u"\n".join(lines) + u"\n")
    return p


class TestInnerBlank(unittest.TestCase):
    def test_jia_zero_findings(self):
        """甲形 0 命中（全架 5 万处都是这个形，误报即毁掉整条闸）。"""
        self.assertEqual(check_displaymath_gt(_md(JIA)), [])
        self.assertEqual(bq_math_inner_blanks(JIA), [])

    def test_yi_names_the_blank_line(self):
        got = check_displaymath_gt(_md(YI))
        self.assertEqual(len(got), 1)
        self.assertIsInstance(got[0], str, u"M 层返回类型须仍是字符串列表（report/verify 直接计数）")
        self.assertIn(u"L5", got[0], u"须点名被删的空行行号：%s" % got[0])
        self.assertIn(u"开门 L3", got[0], u"须给出围栏位置：%s" % got[0])

    def test_p4_two_blanks_both_named(self):
        lines = [u">", u"> $$", u">", u"> y = 3", u">", u"> $$", u">", u"> 散文。"]
        got = check_displaymath_gt(_md(lines))
        self.assertEqual(len(got), 2)
        self.assertTrue(all(u"围栏内" in g for g in got))

    def test_two_blocks_reported_in_line_order(self):
        lines = (YI + [u">", u"> $$", u"> a = 1", u">", u"> $$", u">"])
        got = check_displaymath_gt(_md(lines))
        nums = [int(g.split(u"L")[1].split(u":")[0].split(u" ")[0]) for g in got]
        self.assertEqual(len(got), 2)
        self.assertEqual(nums, sorted(nums), u"两条子判据合并后须按行号排")

    def test_over_indented_fence_recognised(self):
        """`>    $$`（多余空格）也是围栏——门控 F7f 会另行管缩进，本判据不能漏认。"""
        lines = [u">", u">    $$", u"> x = 1", u">", u">    $$", u">"]
        self.assertEqual(len(bq_math_inner_blanks(lines)), 1)

    def test_unpaired_fence_not_guessed(self):
        """开门找不到关门 ⇒ 不猜（未配对围栏由别的判据管），本判据必须 0 命中。"""
        lines = [u">", u"> $$", u"> z = 9", u">", u"散文在引用块外"]
        self.assertEqual(bq_math_inner_blanks(lines), [])
        self.assertEqual(check_displaymath_gt(_md(lines)), [])

    def test_blank_between_two_content_runs_is_still_reported(self):
        """判据**照报**（工具侧才 REFUSE）：闸不能因为「修不了」就不报。"""
        lines = [u">", u"> $$", u"> a = 1", u">", u"> b = 2", u"> $$", u">"]
        self.assertEqual(len(bq_math_inner_blanks(lines)), 1)


class TestLegacySubRuleUntouched(unittest.TestCase):
    """原有「顶层 `$$…$$` 内泄 `>`」子判据不能因合并返回结构而出血。"""

    def test_bare_gt_inside_top_level_math_still_fires(self):
        lines = [u"$$", u"> x = 1", u"$$"]
        got = check_displaymath_gt(_md(lines))
        self.assertEqual(len(got), 1)
        self.assertIn(u"inside display math", got[0])
        self.assertIn(u"L2", got[0])

    def test_two_subrules_can_coexist(self):
        lines = [u"$$", u"> x = 1", u"$$", u"", u">", u"> $$", u"> y = 2", u">", u"> $$"]
        got = check_displaymath_gt(_md(lines))
        self.assertEqual(len(got), 2)

    def test_missing_file_returns_empty(self):
        self.assertEqual(check_displaymath_gt(os.path.join(tempfile.gettempdir(),
                                                           "nope_mdm_test.md")), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
