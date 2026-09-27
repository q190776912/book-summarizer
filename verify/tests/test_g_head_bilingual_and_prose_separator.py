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


class TestCjkSuffixProofHead(unittest.TestCase):
    """中文定中倒装标签（Robinson Lie 代数书 ch5/0014，2026-09-28 根治）。

    `**PBW 定理的证明**` 关键词在末尾，旧判据只认前缀 → CN 侧把块间合法空行判成
    「bare blank 断裂」，而英文同位写法 `**Proof of the PBW Theorem**` 以 Proof
    开头天然放行：同一结构两侧判定再度分叉，译者只能用空 `>` 行/私加 `---` 规避。
    负向：**无粗体头**的散文续行（`> 被劈开的第二段。`）后的裸空行必须仍被判断裂，
    否则放宽即失效。
    """

    def test_cjk_suffix_proof_head_is_a_legit_block_head(self):
        text = ("> **证明**：设 $t \\in T_m$。\n>\n> 1. a。\n> 2. b。\n\n"
                "> **PBW 定理的证明**：\n> 1. c。\n")
        g, i = _run(text)
        self.assertEqual(g, [], "中文倒装证明头须与英文 Proof of … 同判为块头")
        self.assertEqual(i, [], "下一块是 `>` 块，不属「散文」边界")

    def test_english_proof_of_head_agrees(self):
        text = ("> **Proof**: let $t \\in T_m$.\n>\n> 1. a.\n> 2. b.\n\n"
                "> **Proof of the PBW Theorem**:\n> 1. c.\n")
        g, i = _run(text)
        self.assertEqual(g, [])
        self.assertEqual(i, [])

    def test_non_head_quote_resume_still_flagged(self):
        # 旧负例写的是 `> **说明**：被劈开的第二段。`，但 2026-09-28 的宽判据
        # （`G_BQ_BOLD_HEAD_BOUNDARY_RE`，见 `test_g_quote_bold_head_boundary.py`）
        # 把**任何粗体标签头**认作新块：`说明`/`Note`/`Remark` 本就在 `_H_MISSING_BQ`
        # 的「必须包成 `>`」标签表里，要求包起来却又判它劈开上一块是自相矛盾。
        # 守卫意图不变——真续行（无粗体头的散文）必须仍被抓，故改用散文续行做负例。
        g, _ = _run("> **证明**：陈述。\n> 陈述续行。\n\n> 被劈开的第二段散文。\n")
        self.assertEqual(len(g), 1, "放宽后真断裂仍须捕获")


class TestOrdinalPrefixedHead(unittest.TestCase):
    """Vakil《Rising Sea》体例：条目头关键词前带三级序标（2026-09-28 根治）。

    `**18.8.3 Proof of Theorem 18.8.1.**` 的序标把关键词挤离 `**`，旧判据 EN 侧
    整头漏判，CN 同构块（`**18.8.3 定理 18.8.1 的证明。**`，定中倒装支）却命中
    → I 层只追 CN 侧要 `---`、EN 同位裸奔（本书 ch7/11/18/24/27 五处实测）。
    负向：序标后**非关键词**（`**18.2.A Exercise**`）仍不得开块。
    """

    def test_en_and_cn_ordinal_proof_heads_verdict_identical(self):
        en = ("> **18.8.3 Proof of Theorem 18.8.1.**\n>\n> 1. a.\n\n"
              "The following result is handy.\n")
        cn = ("> **18.8.3 定理 18.8.1 的证明。**\n>\n> 1. a。\n\n"
              "下面这个结论很好用。\n")
        ge, ie = _run(en)
        gc, ic = _run(cn)
        self.assertEqual(ge, [], "EN 序标证明头不再误判断裂")
        self.assertEqual(gc, [])
        self.assertEqual(len(ie), 1, "EN 侧须与 CN 同口径报缺 `---`")
        self.assertEqual(len(ic), 1)

    def test_ordinal_prefixed_example_head(self):
        en = ("> **7.3.7 Example.** A statement.\n>\n> 1. a.\n\n"
              "Some descriptive prose.\n")
        g, i = _run(en)
        self.assertEqual(g, [])
        self.assertEqual(len(i), 1)

    def test_non_keyword_ordinal_head_not_opened(self):
        g, i = _run("> **18.2.A Exercise 18.2.A**: do it.\n>\n> 1. a.\n\n"
                    "prose after block\n")
        self.assertEqual(g, [])
        self.assertEqual(i, [], "Exercise 不在 item 关键词表内，不得开块")


if __name__ == "__main__":
    unittest.main(verbosity=2)
