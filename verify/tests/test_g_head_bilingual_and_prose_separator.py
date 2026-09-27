# -*- coding: utf-8 -*-
r"""G/I 层块引用判据的**语言对称性**回归（Strogatz 3e 实测，2026-09-27）。

背景（第 8 处根治）：`check_g_quote_continuity` 旧用 `lib.regexlib.G_HEAD`
（只认中文「证明|证|例」）开块，于是**同一结构**在英文源单元不开块（判不出）、
在中文译单元判「bare blank 断裂」假 FAIL。本书实测 18 处 item 块结束后接顶层
散文的边界：EN 侧全部裸奔无反应，CN 侧被迫用「空 `>` 行」（11 处）或私加
`---`（另处）规避，两版结构分叉。

修复 = ① 开块判据换成 `struct_labels.G_ITEM_BQ_HEAD_RE`（例/Example/证明/Proof/
解答/Solution，语言无关）；② 「块后接顶层散文」不再算断裂——正文完整的 item 块
到此确实结束，改由新判据 `check_i_prose_separator`（writing-rules V-F「item 上下
需 `---`」第 316 条）在**两侧同口径**报缺分隔线；③ 只有「`>` 组除头行外无正文」
的半包例子仍以 G 层报（原 328 条判据不流失）。

断言：同一结构在 CN 头与 EN 头下必须得到**完全相同**的判定。
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

from format_verify import check_g_quote_continuity, check_i_prose_separator


def _run(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                    encoding="utf-8")
    f.write(text)
    f.close()
    try:
        return check_g_quote_continuity(f.name), check_i_prose_separator(f.name)
    finally:
        os.unlink(f.name)


# 三种语言/标签写法的同一结构：完整 item 块 → 裸空行 → 顶层散文
BODY_THEN_PROSE = {
    "cn-example": "> **例 7.4.1**：证明方程有唯一稳定极限环。\n"
                  ">\n> 1. _first step_.\n> 2. _second step_.\n"
                  "\n此外还有几条经典判据。\n",
    "en-example": "> **Example 7.4.1**: Prove the equation has a unique "
                  "stable limit cycle.\n>\n> 1. _first step_.\n"
                  "> 2. _second step_.\n"
                  "\nSeveral other classical criteria exist.\n",
    "cn-proof": "> **证明梗概**：分两步。\n>\n> 1. a.\n> 2. b.\n"
                "\n下一段是描述性散文。\n",
    "en-proof": "> **Proof sketch**: two steps.\n>\n> 1. a.\n> 2. b.\n"
                "\nThe next paragraph is descriptive prose.\n",
}


class TestSymmetricVerdicts(unittest.TestCase):
    def test_body_then_prose_identical_across_languages(self):
        for k, text in BODY_THEN_PROSE.items():
            g, i = _run(text)
            self.assertEqual(g, [], f"{k}: 正文完整块后的合法分块空行不得判断裂")
            self.assertEqual(len(i), 1,
                             f"{k}: item 块后接顶层散文必须两侧同口径报缺 `---`")

    def test_half_wrapped_example_still_caught_both_languages(self):
        # V-F 328「半包例子」：只有头行带 `>`，正文裸奔 → G 层判，I 层不重复报
        cn = _run("> **例 7.4.1**：考虑系统\n\n"
                  "相邻两个质量弹簧系统的运动方程为 $M \\ddot x = K x$。\n")[0]
        en = _run("> **Example 7.4.1**: consider the system\n\n"
                  "The equations of motion are $M \\ddot x = K x$.\n")[0]
        self.assertEqual(len(cn), 1)
        self.assertEqual(len(en), 1, "EN 半包例子旧版完全漏检，现须与 CN 同判")
        self.assertEqual(_run("> **例 7.4.1**：考虑系统\n\n"
                              "相邻方程为 $M \\ddot x = K x$。\n")[1], [],
                         "半包只报 G 层一条，I 层不得重复报缺 `---`")

    def test_true_split_flagged_both_languages(self):
        cn = _run("> **例 3.1.1**：陈述。\n> 陈述续行。\n\n> 被劈开的第二段。\n")[0]
        en = _run("> **Example 3.1.1**: stmt.\n> stmt continued.\n\n"
                  "> split second half.\n")[0]
        self.assertEqual(len(cn), 1)
        self.assertEqual(len(en), 1)


class TestLegitSeparators(unittest.TestCase):
    def test_hr_present_is_clean(self):
        text = ("> **例 1.1.1**：题面。\n>\n> 1. 解。\n"
                "\n---\n\n描述性散文。\n")
        g, i = _run(text)
        self.assertEqual(g, [], "`---` 已在位不得报")
        self.assertEqual(i, [])

    def test_new_item_head_after_blank_is_clean(self):
        text = ("> **例 1.1.1**：A。\n>\n> 1. a。\n\n"
                "> **Example 1.1.2**: B.\n>\n> 1. b.\n")
        g, i = _run(text)
        self.assertEqual(g, [], "新 item 头前的空行是合法块间分隔")
        self.assertEqual(i, [], "下一块是 `>` 块，不属「散文」边界")

    def test_top_level_label_and_heading_and_display_are_clean(self):
        base = "> **例 2.1.1**：题面。\n>\n> 1. a.\n\n"
        for nxt in ("**定理 2.1.2**：陈述。\n", "## §2.2 新节\n",
                    "$$\nx = y\n$$\n", "| a | b |\n|---|---|\n"):
            g, i = _run(base + nxt)
            self.assertEqual(g, [], f"下块 {nxt[:12]!r} 自带边界，不得判断裂")
            self.assertEqual(i, [], f"下块 {nxt[:12]!r} 不是描述性散文")

    def test_quote_end_of_file_is_clean(self):
        g, i = _run("> **例 2.1.1**：题面。\n>\n> 1. a.\n\n")
        self.assertEqual(g, [])
        self.assertEqual(i, [])


class TestTrailingEmptyGtIsNotSeparator(unittest.TestCase):
    def test_empty_gt_then_prose_reports_missing_hr(self):
        # 上一轮译者用「空 `>` 行」规避假 FAIL 的形态：空 `>` 是块**内**留白，
        # 不是块间分隔线 → 仍须报缺 `---`（判据不因规避形态失效）。
        g, i = _run("> **例 6.8.2**：题面。\n>\n> 1. a。\n>\n散文段落。\n")
        self.assertEqual(g, [], "G 层不再误报（假 FAIL 的源头已消除）")
        self.assertEqual(len(i), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
