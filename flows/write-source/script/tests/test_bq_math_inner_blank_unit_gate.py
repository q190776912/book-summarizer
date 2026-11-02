# -*- coding: utf-8 -*-
"""Regression: 单元闸必须当场拦下「引用块 display math 的**围栏内**空 `>` 行」（乙形）。

2026-11-02 全架批修 12 本 / 4282 行时才把这条子判据接进 M 层（`check_displaymath_gt` 第二条，
判据本体 `format_verify.bq_math_inner_blanks`）。为什么不能只在文档级查：

* CommonMark 里块引用内的空行**结束当前块** ⇒ `$$` 围栏被劈成两段，多出一个空的 `$$` 段
  （cmark-gfm 实测，见 `bq_math_inner_blanks` docstring）；这是渲染断裂不是排版洁癖。
* 单元里写成乙形，拼接后交付 md 一样是乙形 ⇒ 返工面从「一个单元」放大到「改交付 + 重同步
  `src_hash`」（本轮就是这么返工的）。

锁死三件事：
 ① 乙形在 `check_body`（单元闸的出厂入口）里必须 FAIL 且报文点名围栏内那条空行与开门行号；
 ② 甲形（空行在整对 `> $$` **之外**）必须 0 命中——否则会把 F7c 要求的开门空行也判违规；
 ③ 未配对的开门围栏不猜关门（交别的判据），闸不得因此造出假阳。

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_bq_math_inner_blank_unit_gate.py
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, str(Path(_ROOT) / "flows" / "write-source" / "script"))

import check_unit_quality as cuq  # noqa: E402

MARK = "引用块 display math 的围栏内"

# 乙形（真件形态，Katok units/ch20/0011_item_定理20_1_6.md 改前）：空行落在关门之前
YI = ("**Theorem 20.1.6.**  Statement.\n"
      "\n"
      "> **Proof.**\n"
      "> $$\n"
      "> C := \\bigcap_{i \\in \\mathbb{Z}} f^i(\\mathcal{R})\n"
      ">\n"
      "> $$\n"
      ">\n"
      "> hence the claim.\n")

# 两条空行都落在同一对围栏内（真件里也见过）
YI2 = ("**Theorem 20.1.6.**  Statement.\n"
       "\n"
       "> **Proof.**\n"
       "> $$\n"
       "> C := X\n"
       ">\n"
       "> D := Y\n"
       ">\n"
       "> $$\n"
       ">\n"
       "> hence the claim.\n")

# 甲形：同一条空 `>` 行挪到整对围栏之外（F7c 本来就要求开门前那条，这里两条都在位）
JIA = ("**Theorem 20.1.6.**  Statement.\n"
       "\n"
       "> **Proof.**\n"
       ">\n"
       "> $$\n"
       "> C := \\bigcap_{i \\in \\mathbb{Z}} f^i(\\mathcal{R})\n"
       "> $$\n"
       ">\n"
       "> hence the claim.\n")


def _hits(text):
    """走 `check_body`（出厂入口）跑一遍，只取本判据点名的报文。"""
    _ok, probs = cuq.check_body("item", "20.1.6 Statement", text)
    return [p for p in probs if MARK in p]


class TestBqMathInnerBlankUnitGate(unittest.TestCase):
    def test_yi_form_fails_gate(self):
        got = _hits(YI)
        self.assertEqual(len(got), 1, got)
        self.assertIn("L6", got[0])          # 点名的是围栏内那条空行
        self.assertIn("L4", got[0])          # 并报开门围栏行号，供人工定位

    def test_jia_form_clean(self):
        self.assertEqual(_hits(JIA), [])

    def test_two_inner_blanks_both_named(self):
        got = _hits(YI2)
        self.assertEqual(len(got), 2, got)
        self.assertTrue(any("L6:" in p for p in got), got)
        self.assertTrue(any("L8:" in p for p in got), got)

    def test_unpaired_fence_not_guessed(self):
        # 只有开门、没有关门 ⇒ 本判据不猜关门（另有判据管未闭合围栏）
        body = "> **Proof.**\n> $$\n> x = 1\n>\n> prose\n"
        self.assertEqual(_hits(body), [])

    def test_top_level_blank_lines_not_mixed_in(self):
        # 顶层 `$$…$$` 内的普通空行不是引用块围栏，不该由本判据报（原判据管的是泄进来的 `>`）
        body = "> **Proof.**  text\n\n$$\nx = 1\n\n$$\n\nmore\n"
        self.assertEqual(_hits(body), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
