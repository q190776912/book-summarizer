# -*- coding: utf-8 -*-
"""中文形近型类型词补救（lib/label_typo._cn_typo_normalize，2026-11-01 郑大钟实测）。

根因：郑大钟《线性系统理论》主定理族「结论N.M」被 OCR 把类型词的**末字**读成形近字
（结论3.22 →「结诊3.22」、结论3.27 →「结沦3.27」），正字构造的 CN 二级正则整体失配
→ 整族掉出契约 → B 层只剩整段缺号死锁。判据四重（宁缺毋滥）：块首纯中文、长度等于
某 config 中文标签、前 (len-1) 字逐字相等**仅末字**不同、命中**恰好一个**、其后紧跟点分
序标。首字残（缩论/绪论）离「结论/推论」皆编辑距离 1 = 歧义，**一律不猜**。

运行：
  python lib/tests/test_label_typo_cn.py
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
    _ROOT = str(Path(__file__).resolve().parents[1])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot as _boot
_boot.setup()

from lib.label_typo import label_typo_normalize  # noqa: E402

# 郑大钟本书 config 声明的中文标签集合（无 定理/引理，故 论-族歧义只来自 结论/推论）
ZHENG = ['例', '定义', '算法', '推论', '结论']


class TestCJKLastGlyphRecovery(unittest.TestCase):
    """正判据：块首末字残 + 点分序标 → 归一为唯一正字，其余逐字保留。"""

    def test_jiezhen_becomes_jielun(self):
        got = label_typo_normalize("结诊3.22 [状态运动规律] 对连续时间线性时不变系统", ZHENG)
        self.assertEqual("结论3.22 [状态运动规律] 对连续时间线性时不变系统", got)

    def test_jielun_becomes_jielun(self):
        got = label_typo_normalize("结沦3.27[代数等价系统的脉冲响应矩阵] 两个代数", ZHENG)
        self.assertEqual("结论3.27[代数等价系统的脉冲响应矩阵] 两个代数", got)

    def test_ordinal_space_inside_number_tolerated(self):
        # 实测「结诊3. 34」点号后带空格：序标判据须容忍，且只改块首词、空格原样保留
        got = label_typo_normalize("结纶3. 34[状态转移矩阵]对连续时间线性时变系统", ZHENG)
        self.assertEqual("结论3. 34[状态转移矩阵]对连续时间线性时变系统", got)

    def test_offset_preserved(self):
        # 替换词与残字等长（都 2 字）→ 后续偏移不变
        src = "结诊3.9 head text continues here"
        got = label_typo_normalize(src, ZHENG)
        self.assertEqual(len(src), len(got))


class TestCJKAmbiguousNotGuessed(unittest.TestCase):
    """负向：首字残离两标签皆编辑距离 1（缩论↔结论/推论）= 歧义 → 不猜。"""

    def test_first_glyph_corruption_is_ambiguous(self):
        self.assertIsNone(label_typo_normalize("缩论3.38[脉冲响应矩阵] 对零初始状态", ZHENG))
        self.assertIsNone(label_typo_normalize("绪论 3.52 [状态响应] 对离散时间", ZHENG))


class TestCJKNoopCases(unittest.TestCase):
    """负向：正字 / 无序标 / 纯字母词表 / 单字标签 均不改写。"""

    def test_correct_head_untouched(self):
        self.assertIsNone(label_typo_normalize("结论3.1 [零输入响应] 连续时间", ZHENG))

    def test_no_ordinal_after_token_is_not_rescued(self):
        self.assertIsNone(label_typo_normalize("结诊上述意义的关键在于此", ZHENG))

    def test_english_only_vocab_is_inert(self):
        # 纯字母词表（英文书）→ CJK 通道恒 None，零回归
        self.assertIsNone(label_typo_normalize("Theorem 2.7 For all f", ['Theorem', 'Lemma']))

    def test_single_char_label_not_touched(self):
        # 例（单字）不参与末字补救（长度 <2）
        self.assertIsNone(label_typo_normalize("例3.1 某某例题", ZHENG))

    def test_book_without_jielun_group_does_not_rescue(self):
        # 词表没有「结论」（别的书）→ 结诊 无对应正字 → 不猜
        self.assertIsNone(label_typo_normalize("结诊3.22 [某族] 陈述", ['定义', '定理', '例']))


class TestCJKDingyiAmbiguity(unittest.TestCase):
    """定X 残字：本书无 定理 组 → 定议 唯一命中 定义；若有 定理 组则歧义不猜。"""

    def test_dingyi_unique_when_no_dingli_group(self):
        got = label_typo_normalize("定议1.3 [术语] 设", ZHENG)
        self.assertEqual("定义1.3 [术语] 设", got)

    def test_dingyi_ambiguous_when_dingli_group_present(self):
        labs = ['定义', '定理', '例']
        self.assertIsNone(label_typo_normalize("定议1.3 [术语] 设", labs))


if __name__ == "__main__":
    unittest.main(verbosity=2)
