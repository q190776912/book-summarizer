# -*- coding: utf-8 -*-
"""Regression tests: B 层节锚「标题包含性」（Rosen 8e 实测，2026-09-25）。

背景：type1/scope3 书（Rosen：例1..16 在 §1.1、下一节又从例1 起）的计数器在
**二阶级** §1.1 重置；书里同时印刷三阶级小节头 "1.1.3 Conditional Statements"。
旧锚逻辑给每个不同的 `##/### §` token 都开新窗，于是挂在 "## §1.1.3" 下的
例10..13 被判「缺号 1..9」——structure 完整性闸门 ch1 实测 141 条假 blocking。

根治（_section_anchors）：token 以「当前节号 + '.'」为前缀 = 节内子小节头，
不注册锚点；真重启边界（谷超豪 "### §2"、Arnold "### §A"、跨节 "## §1.2"）
行为逐字不变。
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

    def test_arnold_letter_blocks_kept(self):
        md = "## §24 a\n### §A b\n## §25 c\n### §B d\n"
        self.assertEqual(_anchors(md), ["24", "24.A", "25", "25.B"])

    def test_dangling_parentless_deep_heading_kept(self):
        # 父节未知（无 ## 节头）时深层数字标题维持旧注册行为（各自成窗）。
        md = "### §2 a\n### §2.1 b\n"
        self.assertEqual(_anchors(md), ["2", "2.1"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
