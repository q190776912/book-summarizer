"""Regression tests: 章末集中习题区的「语言无关」豁免（Lehmann–Casella《TPE》ch2 实测）。

背景：`exercise_region_headings` 是从**源语言**声明的 opt-in 配置（本书 = 英文
`["Problems","Notes"]`），verify 对**每个语言版**各跑一遍。源书把章末习题区印成
`**Problems**`，区内 1..N 题是 `**1.1** …` 形式的**习题编号**（非 number-first 条目标题）。

旧判据只按声明里的**英文词**整词匹配习题区标题，于是：
  * 英文侧 `**Problems**` 命中 → 区内裸题号 `**1.1**` 被 p_bare_item 整区豁免；
    且 `Problems` 不在告警词表 → p_exer_block 根本不碰它 → 两版判据双双通过。
  * 中文侧把同一标题忠实译成 `**习题**` → 旧匹配器不认 → 区内 10 道裸题号被
    p_bare_item 全数误报「标题被甩到 bold 外」，`**习题**` 又被 p_exer_block 判成
    「无中生有归拢块」（习题/exercise 命中告警词表，而 Problems 不命中）——纯翻译不对称。

根治后行为（本文件锁定）：习题区标题按**跨语言同族**识别（Problems/Exercises/练习/习题…
同族，Notes/评注/注… 同族），声明英文词即令译文 `**习题**` 走同一豁免；未声明 heads 的
书本分支恒不触发 → 对既有全部书目逐字节零回归。
"""
import os
import sys
import types
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

from verbose_gates import (check_bare_items, check_exer_blocks,
                           _is_exercise_region_head, _exercise_region_heads)


def _cfg(heads):
    return types.SimpleNamespace(exercise_region_headings=heads)


# 章末习题区：`**习题**`（CN 译题）+ `**Section 1**` 子题 + 裸题号 `**1.1** …`。
_CN_REGION = [
    "## §6 多参数情形",
    "",
    "**习题**",
    "",
    "**Section 1**",
    "",
    "**1.1** 验证：(a) (1.4) 定义了一个概率分布；(b) 条件 (1.5)。",
    "",
    "**1.2** 在例 1.5 中，证明 $a_i^*$ 极小化 (1.6)。",
]

_EN_REGION = [
    "## §6 The Multiparameter Case",
    "",
    "**Problems**",
    "",
    "**1.1** Verify (a) that (1.4) defines a probability distribution.",
]


class TestBilingualExerciseRegionHead(unittest.TestCase):
    def test_en_declared_head_matches_itself(self):
        self.assertTrue(_is_exercise_region_head("**Problems**",
                                                 _exercise_region_heads(_cfg(["Problems", "Notes"]))))

    def test_cn_translation_of_declared_head_is_recognised(self):
        """声明英文 Problems，译文 `**习题**`/`**练习**` 亦须认作同一习题区标题。"""
        heads = _exercise_region_heads(_cfg(["Problems", "Notes"]))
        for line in ("**习题**", "**练习**", "习题", "**问题**"):
            self.assertTrue(_is_exercise_region_head(line, heads),
                            f"{line!r} 是 Problems 同族译题，必须命中")

    def test_cn_translation_of_notes_head_is_recognised(self):
        heads = _exercise_region_heads(_cfg(["Problems", "Notes"]))
        for line in ("**注**", "**评注**", "**注记**"):
            self.assertTrue(_is_exercise_region_head(line, heads),
                            f"{line!r} 是 Notes 同族译题，必须命中")

    def test_undeclared_family_not_matched(self):
        """只声明 Problems（exercise 族）时，notes 族 `**注**` 不应命中。"""
        heads = _exercise_region_heads(_cfg(["Problems"]))
        self.assertFalse(_is_exercise_region_head("**注**", heads))

    def test_no_heads_opt_in_disables_everything(self):
        """opt-in 未声明 → 任何标题都不算习题区（零回归保证）。"""
        self.assertFalse(_is_exercise_region_head("**习题**", []))
        self.assertFalse(_is_exercise_region_head("**Problems**", []))


class TestBareItemsBilingualParity(unittest.TestCase):
    def test_cn_region_bare_items_exempt(self):
        got = check_bare_items(_CN_REGION, ordinal=2, cfg=_cfg(["Problems", "Notes"]))
        self.assertEqual(got, [], "章末习题区裸题号是习题编号，非条目标题，CN 侧须豁免")

    def test_en_region_bare_items_exempt(self):
        got = check_bare_items(_EN_REGION, ordinal=2, cfg=_cfg(["Problems", "Notes"]))
        self.assertEqual(got, [], "EN 侧同区须同样豁免（两版一致）")

    def test_without_opt_in_bare_items_still_flagged(self):
        """未声明 heads 的书：区内裸题号仍按 number-first 报告（不放宽默认行为）。"""
        got = check_bare_items(_CN_REGION, ordinal=2, cfg=_cfg([]))
        self.assertTrue(got, "未 opt-in 时不得豁免裸条目标题")


class TestExerBlockBilingualParity(unittest.TestCase):
    def test_cn_region_head_exempt_via_cfg(self):
        """`**习题**` 是声明习题区标题的同族译题 → 忠实，非归拢块。"""
        got = check_exer_blocks(_CN_REGION, ext_dir=None, ch=None,
                                cfg=_cfg(["Problems", "Notes"]))
        self.assertEqual([g for g in got if "习题" in g or "归拢" in g], [],
                         "声明章末题集标题的等价译题必须豁免")

    def test_cn_region_head_flagged_without_cfg(self):
        """不传 cfg（或 opt-in 为空）时 `**习题**` 仍按归拢块拦截（闸门保留牙齿）。"""
        got = check_exer_blocks(_CN_REGION, ext_dir=None, ch=None, cfg=None)
        self.assertTrue(any("归拢" in g for g in got),
                        "未 opt-in 时独立 `**习题**` 标题仍必须拦")


if __name__ == "__main__":
    unittest.main(verbosity=2)
