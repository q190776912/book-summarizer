# -*- coding: utf-8 -*-
"""Regression: 第 26 项「占位符残留闸」+ 第 27 项「空展示块闸」（2026-10-20 全库普查）。

两条都源于**内容丢失而现有判据双盲**的实测形态：

* ``@@ARRAY@@``——Rosen《Discrete Mathematics》8e 步骤6 的译单元
  ``units-translate/ch9/0157_item_例14.md`` 把整块 ``\\begin{array}`` 展示式换成一个
  占位标记交回，一路进了交付 md ``第9章_9.5_等价关系.md``（该书收官早于 parity 判据 9，
  章级同构闸今天已能抓这一条，见 ``_math_content_problems``——但判据 9 **只比显示式块**：
  译者拿 ``@@TABLE@@`` / ``@@IMAGE@@`` 换掉表格或散文时它整条失明，且它要等到章级
  parity 重跑才生效。本闸把拦截提前到「单元交回的那一刻」，且不看语义只认形态）。
* 空 ``$$…$$``——Shafarevich《Basic AG 1》ch4 的两份修前备份实测 152 处：改写时把
  块内容整行删净只留围栏。``$$`` 闭合判据（F6）只查「成对到 EOF」，tag 对账只管契约
  要求编号的块，无编号空块两头都不在账。

🔴 第 27 项的**关键负向**是「相邻两个真块」形态：成对正则 ``\\$\\$\\n(.*?)\\n\\$\\$``
会把前一块的闭栏与后一块的开栏配成一对，中间那个空行被判成空块——全库实测该写法
假阳 **1701 个文件**，而按奇偶顺序 walk 围栏只剩 2 个备份文件（0 交付假阳）。

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_placeholder_and_empty_display_gates.py
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


def _ph(body):
    return cuq.placeholder_problems(body)


def _ed(body):
    return cuq.empty_display_problems(body)


class TestPlaceholderGate(unittest.TestCase):
    def test_real_placeholder_caught(self):
        body = ("**例 14.** 由模 4 同余所产生的整数划分中有哪些集合？\n>\n"
                "> $$\n> @@ARRAY@@\n> $$\n")
        hits = _ph(body)
        self.assertTrue(hits, body)
        self.assertIn("@@ARRAY@@", hits[0])

    def test_placeholder_anywhere_in_body(self):
        # 不限于 $$ 块内：表 / 图 / 证明的占位标记同一形态
        self.assertTrue(_ph("证明见书后。@@IMAGE@@\n"))
        self.assertTrue(_ph("> @@TABLE@@ 略\n"))

    def test_no_false_positive_on_plain_dollars_and_at(self):
        cases = [
            "设 $E$ 为等价关系，$a @ b$ 记 $a \\equiv b \\pmod n$。\n",
            "$$x = 1$$ 且 $y @ z$。\n",
            "邮箱 user@example.com 出现在文中。\n",
            "@@@ 三个连写不构成标记。\n",
            "@@ @@小写不合法形态。\n",
        ]
        for body in cases:
            self.assertEqual(_ph(body), [], body)

    def test_marker_line_not_double_flagged(self):
        # 首行 HTML 标记本身不含 @@，剥离与否不影响结论（判据只认形态）
        self.assertEqual(_ph("<!-- book-summarizer DONE unit: id=1 type=item -->\n正文。\n"), [])


class TestEmptyDisplayGate(unittest.TestCase):
    def test_empty_block_caught(self):
        body = "**定理 1**.\n\n$$\n\n$$\n\n后续散文。\n"
        hits = _ed(body)
        self.assertTrue(hits, body)
        self.assertIn("空的", hits[0])

    def test_adjacent_fences_with_math_outside_caught(self):
        r"""实测形态（Shafarevich ch4 修前备份 L18–21）：公式漏在闭栏**之后**。"""
        body = ("maximal ideal:\n\n$$\n$$\n(f_1,\\dots,f_n) \\supseteq m_x^k .\n\\tag{4.1}\n\n")
        hits = _ed(body)
        self.assertTrue(hits, body)
        self.assertIn("L3", hits[0].replace(" ", ""))

    def test_single_line_empty_block_caught(self):
        self.assertTrue(_ed("> $$  $$\n"))

    def test_block_with_only_tag_is_not_empty(self):
        # 只有 \\tag 而无公式体仍是「内容被删」，但本判据按「有非空内容」放行，
        # 该形态由契约 tag 对账与 KaTeX 渲染负责——此处锁边界不外扩。
        self.assertEqual(_ed("$$\n\\tag{1.2}\n$$\n"), [])

    def test_adjacent_real_blocks_are_NOT_empty(self):
        r"""🔴 核心负向：成对正则在这里必假阳（全库 1701 文件的错法）。"""
        body = ("$$\na = b\n$$\n\n$$\nc = d\n$$\n")
        self.assertEqual(_ed(body), [], body)

    def test_blockquote_fences_with_content_not_flagged(self):
        body = ("**例 2.** 问：\n>\n> $$\n> x_{n} \\to x\n> $$\n>\n> 答。\n")
        self.assertEqual(_ed(body), [], body)

    def test_empty_block_inside_blockquote_caught(self):
        body = "> $$\n>\n> $$\n"
        self.assertTrue(_ed(body), body)

    def test_unclosed_fence_left_open_no_report(self):
        # 未闭合由 F6「$$ 闭合」判据负责，本判据不得抢先报空块
        self.assertEqual(_ed("$$\na = b\n"), [])

    def test_unexpected_second_empty_block_reported(self):
        body = "$$\na\n$$\n\n$$\n\n$$\n\n$$\nb\n$$\n"
        hits = _ed(body)
        self.assertTrue(hits, body)
        self.assertIn("L5", hits[0].replace(" ", ""))   # 第二个块（L5–L7）为空


class TestGatesWiredIntoCheckBody(unittest.TestCase):
    def _msgs(self, body, utype="item"):
        ok, probs = cuq.check_body(utype, "定理 1", body)
        return ok, "\n".join(probs)

    def test_item_placeholder_fails(self):
        ok, joined = self._msgs("$$\n@@ARRAY@@\n$$\n")
        self.assertFalse(ok)
        self.assertIn("占位符", joined)

    def test_item_empty_block_fails(self):
        ok, joined = self._msgs("**定理 1.** 陈述。\n\n$$\n\n$$\n")
        self.assertFalse(ok)
        self.assertIn("空的", joined)

    def test_section_header_unit_still_scanned(self):
        """section / chapter 单元其余判据不跑，但这两条纯形态签名必须照跑。"""
        ok, probs = cuq.check_body("section", "1.4 Some Limit Distributions",
                                   "## 1.4 节末小结\n\n$$\n\n$$\n")
        self.assertFalse(ok, probs)
        ok2, probs2 = cuq.check_body("section", "1.4 Some Limit Distributions",
                                     "## 1.4 节末小结\n\n$$\nN(0, 1)\n$$\n")
        self.assertTrue(ok2, probs2)

    def test_clean_unit_not_flagged_by_new_gates(self):
        """常规写好单元（`>` 包裹的例 + 块内展示式）不得被这两条新闸报出。"""
        body = ("**例 1.** 设 $X_n \\to X$。\n>\n> $$\n> P(|X_n - X| > \\varepsilon) \\to 0\n> $$\n>\n"
                "> **证明：** 由定义即得。\\qquad $\\square$\n")
        self.assertEqual(_ph(body), [])
        self.assertEqual(_ed(body), [])
        ok, joined = self._msgs(body)
        self.assertNotIn("占位符", joined, joined)
        self.assertNotIn("空的 `$$", joined, joined)


if __name__ == "__main__":
    unittest.main(verbosity=2)
