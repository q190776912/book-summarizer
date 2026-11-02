# -*- coding: utf-8 -*-
"""Regression: M 层 **auto-fix** 必须把判据的两条子判据都修掉，且删除决策与工具同一份 SSOT。

来历（2026-11-02 #83）：`check_displaymath_gt` 加了第二条子判据（引用块 `> $$ … > $$` 的围栏内
空 `>` 行）之后，`fix_displaymath_gt` 仍只会修第一条（顶层 `$$…$$` 里泄进的 `>`）。后果不是
「少修一点」而是**假闭环**：`verify --fix` 报「M 修了 N 行」，乙形照旧红，而 N 是上一轮删行
留下的行号位移算出来的，没人会去比对新报文。同时「哪一条空行可以安全删」原本只写在
`tools/fix_bq_math_blank.py` 里，闸要修就得再抄一份——两份决策迟早分叉。

锁死四件事：
 ① 乙形经 auto-fix 后**判据归零**（round trip），删的正是那条围栏内空行，别的一个字节不动；
 ② 「空行两侧都有内容」那种由 `bq_deletable_inner_blanks` 拒删 ⇒ auto-fix 也必须**不动**
    （判据照旧红，交人工分诊；闸不许为了变绿而并块）；
 ③ 第一条子判据（顶层 `$$` 里泄 `>`）的老行为不回退；
 ④ auto-fix 与批修工具读的是**同一个**决策函数对象（`is` 同一），不是各写一份等价逻辑。

Runs under stdlib unittest:
  python verify/tests/test_m_dm_gt_autofix.py
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
import lib.boot as _boot
_boot.setup()

from format_verify import (bq_deletable_inner_blanks, check_displaymath_gt)  # noqa: E402
from verify.format_verify.script import fix_math_blockquote_leak as fml  # noqa: E402

YI = ("> **Proof.**\n"
      ">\n"
      "> $$\n"
      "> C := \\bigcap_{i} f^i(\\mathcal{R})\n"
      ">\n"
      "> $$\n"
      ">\n"
      "> hence the claim.\n")

JIA = ("> **Proof.**\n"
       ">\n"
       "> $$\n"
       "> C := \\bigcap_{i} f^i(\\mathcal{R})\n"
       "> $$\n"
       ">\n"
       "> hence the claim.\n")

# 两条点名空行**之外**的两侧都还有内容：删任何一条都会把两段并成一段 ⇒ SSOT 拒删
SEPARATING = ("> **Proof.**\n"
              ">\n"
              "> $$\n"
              "> first part\n"
              ">\n"
              "> second part\n"
              "> $$\n"
              ">\n"
              "> hence the claim.\n")

LEAK = ("> **Remark.**\n"
        "\n"
        "$$\n"
        "> x = 1 + 2\n"
        "$$\n"
        "\n"
        "text\n")


class _Tmp(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".md")
        os.close(fd)

    def tearDown(self):
        os.unlink(self.path)

    def write(self, text):
        with io.open(self.path, "w", encoding="utf-8", newline="") as f:
            f.write(text)

    def read(self):
        with io.open(self.path, encoding="utf-8", newline="") as f:
            return f.read()


class TestBqInnerBlankAutoFix(_Tmp):
    def test_yi_fixed_and_judge_clean(self):
        self.write(YI)
        self.assertEqual(len(check_displaymath_gt(self.path)), 1)
        self.assertEqual(fml.fix_displaymath_gt(self.path), 1)
        self.assertEqual(check_displaymath_gt(self.path), [])
        self.assertEqual(self.read(), JIA)

    def test_jia_untouched(self):
        self.write(JIA)
        self.assertEqual(fml.fix_displaymath_gt(self.path), 0)
        self.assertEqual(self.read(), JIA)

    def test_second_run_is_noop(self):
        self.write(YI)
        fml.fix_displaymath_gt(self.path)
        self.assertEqual(fml.fix_displaymath_gt(self.path), 0)
        self.assertEqual(self.read(), JIA)

    def test_two_inner_blanks_both_removed(self):
        body = ("> $$\n> a = 1\n>\n> b = 2\n>\n> $$\n>\n> prose\n")
        self.write(body)
        self.assertEqual(len(check_displaymath_gt(self.path)), 2)
        self.assertEqual(fml.fix_displaymath_gt(self.path), 2)
        self.assertEqual(self.read(), "> $$\n> a = 1\n> b = 2\n> $$\n>\n> prose\n")

    def test_separating_blank_is_refused_not_merged(self):
        """SSOT 拒删的形态，auto-fix 必须**原样留着**（判据照旧红）——闸不许为变绿而并块。"""
        self.write(SEPARATING)
        drop, refuses, _blocks = bq_deletable_inner_blanks(SEPARATING.split("\n"))
        self.assertEqual((drop, len(refuses)), (set(), 1))
        before = check_displaymath_gt(self.path)
        self.assertEqual(len(before), 1)
        self.assertEqual(fml.fix_displaymath_gt(self.path), 0)
        self.assertEqual(self.read(), SEPARATING)
        self.assertEqual(check_displaymath_gt(self.path), before)


class TestLegacySubRuleStillRepaired(_Tmp):
    def test_top_level_leaked_gt_still_stripped(self):
        self.write(LEAK)
        self.assertTrue(any("inside display math" in m for m in check_displaymath_gt(self.path)))
        self.assertEqual(fml.fix_displaymath_gt(self.path), 1)
        self.assertEqual(check_displaymath_gt(self.path), [])
        self.assertNotIn(">", self.read().split("$$")[1])

    def test_both_subrules_in_one_file(self):
        self.write(YI + "\n" + LEAK)
        self.assertEqual(len(check_displaymath_gt(self.path)), 2)
        self.assertEqual(fml.fix_displaymath_gt(self.path), 2)
        self.assertEqual(check_displaymath_gt(self.path), [])


class TestSingleSourceOfDecision(unittest.TestCase):
    def test_fixer_imports_the_ssot_object(self):
        """`is` 同一对象：闸与 `tools/fix_bq_math_blank.py` 不可能对同一形态判出两种结果。"""
        sys.path.insert(0, os.path.join(_ROOT, "tools"))
        import fix_bq_math_blank as fb
        self.assertIs(fml.bq_deletable_inner_blanks, bq_deletable_inner_blanks)
        self.assertIs(fb.bq_deletable_inner_blanks, bq_deletable_inner_blanks)

    def test_fixer_module_has_no_own_fence_walker(self):
        """修复侧不许再写一份围栏配对/空行判定（围栏正则只住在 format_verify 的 `_BQ_MATH_FENCE_RE`）。"""
        path = os.path.join(_ROOT, "verify", "format_verify", "script",
                            "fix_math_blockquote_leak.py")
        with io.open(path, encoding="utf-8") as f:
            src = f.read()
        self.assertNotIn(r">\s*\$\$", src)
        self.assertNotIn("block_spans", src)


class TestNewlinePreserved(_Tmp):
    def test_crlf_file_stays_crlf(self):
        self.write(YI.replace("\n", "\r\n"))
        self.assertEqual(fml.fix_displaymath_gt(self.path), 1)
        self.assertEqual(self.read(), JIA.replace("\n", "\r\n"))

    def test_lf_file_stays_lf(self):
        self.write(YI)
        self.assertEqual(fml.fix_displaymath_gt(self.path), 1)
        self.assertNotIn("\r", self.read())


class TestApplyFixContract(_Tmp):
    def test_fix_dict_key_is_m(self):
        self.write(YI)

        class Ctx(object):
            md_file = self.path

        fr = fml.apply_fix(Ctx())
        self.assertEqual(list(fr.fix_dict.keys()), ["m"])
        self.assertEqual(fr.fix_dict["m"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
