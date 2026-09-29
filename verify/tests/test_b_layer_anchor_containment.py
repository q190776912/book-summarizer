# -*- coding: utf-8 -*-
"""Regression tests: B 层节锚「标题包含性」（Rosen 8e 实测，2026-09-25）。

背景：type1/scope3 书（Rosen：例1..16 在 §1.1、下一节又从例1 起）的计数器在
**二阶级** §1.1 重置；书里同时印刷三阶级小节头 "1.1.3 Conditional Statements"。
旧锚逻辑给每个不同的 `##/### §` token 都开新窗，于是挂在 "## §1.1.3" 下的
例10..13 被判「缺号 1..9」——structure 完整性闸门 ch1 实测 141 条假 blocking。

根治（_section_anchors）：token 以「当前节号 + '.'」为前缀 = 节内子小节头，
不注册锚点；真重启边界（谷超豪 "### §2"、跨节 "## §1.2"）行为逐字不变。
2026-09-29 追加：裸字母子块 "### §A" 同样**不**开新窗（继承父节锚）——Arnold
《经典力学的数学方法》节内计数器横跨字母块连续编号，旧的分窗字母锚假报 65 条缺号。
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, _ROOT)
from lib.boot import setup  # noqa: E402
setup()

from verify.item_numbering_integrity.script.item_numbering_integrity import (  # noqa: E402
    _section_anchors)


def _anchors(md):
    return _section_anchors(md)[1]


class TestAnchorContainment(unittest.TestCase):
    def test_deep_subsection_does_not_open_window(self):
        md = ("## §1.1 引言\n\n**例1** a\n\n**例9** b\n\n"
              "### §1.1.2 Propositions\n\n**例10** c\n\n"
              "### §1.1.3 Conditional Statements\n\n**例13** d\n\n"
              "## §1.2 Applications\n\n**例1** e\n")
        self.assertEqual(_anchors(md), ["1.1", "1.2"])

    def test_containment_also_applies_at_same_heading_level(self):
        # structure 合成 md 把子节也印成 `## §1.1.3` — 同样并窗。
        md = "## §1.1 x\n## §1.1.3 y\n## §1.2 z\n"
        self.assertEqual(_anchors(md), ["1.1", "1.2"])

    def test_sibling_section_still_resets(self):
        # "1.10" 不是 "1.1." 前缀的延伸 → 真节，正常开新窗。
        md = "## §1.1 x\n## §1.2 y\n## §1.10 z\n"
        self.assertEqual(_anchors(md), ["1.1", "1.2", "1.10"])

    def test_gu_chaohao_insection_restart_kept(self):
        # 谷超豪「一节内两套 性质1–4」：### §2 不以父节 "4" 为前缀 → 仍分窗。
        md = "## §4 a\n**性质1** x\n### §2 b\n**性质1** y\n"
        self.assertEqual(_anchors(md), ["4", "4-2"])

    def test_arnold_letter_blocks_inherit_parent_window(self):
        # 字母子块不是计数器边界（Arnold ch7 §32 实测：问题1..15 横跨 A..E）：
        # 挂在 `### §D` 下的 问题4..8 必须仍属 "32" 窗，不得切出 "32.D" 假缺号。
        md = ("## §32 外形式\n\n**问题1** a\n\n### §A 1-形式\n\n**问题2** b\n\n"
              "### §D 外乘积\n\n**问题4** c\n\n**问题8** d\n\n### §E 外单项式\n\n"
              "**问题9** e\n")
        self.assertEqual(_anchors(md), ["32"])

    def test_letter_blocks_in_different_sections_do_not_merge(self):
        # 旧逻辑担心的并窗（§24.B 的定理3、4 与 §25.B 的定理1 混成 [3,4,1]）仍被区分：
        # 父节锚天然不同窗 ⇒ 负向判据不许回退成裸字母锚。
        md = "## §24 a\n### §B b\n**定理3** x\n**定理4** y\n## §25 c\n### §B d\n**定理1** z\n"
        self.assertEqual(_anchors(md), ["24", "25"])

    def test_parentless_letter_heading_still_registers(self):
        # 无 `## §<数字>` 父节时（单级体例）裸字母标题维持旧注册行为。
        md = "### §A a\n### §B b\n"
        self.assertEqual(_anchors(md), ["A", "B"])

    def test_dangling_parentless_deep_heading_kept(self):
        # 父节未知（无 ## 节头）时深层数字标题维持旧注册行为（各自成窗）。
        md = "### §2 a\n### §2.1 b\n"
        self.assertEqual(_anchors(md), ["2", "2.1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
