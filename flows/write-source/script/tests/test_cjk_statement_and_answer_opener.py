# -*- coding: utf-8 -*-
r"""Regression: 两条中文形态判据缺口（Arnold《经典力学的数学方法》ch7/appendixD，2026-09-29）。

1. **`答` 不是 `>` 块合法开吻**。该书题后直接印 `答 …`（PDF p.130「答 C；下面将给出
   一个基底.」、p.137「答dx|(1,0)(ξ) = 0 …」），写手照印面写 `> **答** …`，而
   `_H_UL_OPENERS` 只收 `解答?` → 整块判「unlabeled blockquote」，块内每行 `> **答**`
   / `> $$` 连带重复报错（ch7 四单元 12 处）。⇒ `答` 与 `Solution`/`解答` 对等入白名单；
   修复趟 `fix_unlabeled_blockquotes` import 同一正则，检测/修复同源。
2. **CJK 题面按「连续串 = 1 词元」计**。`_name_carries_statement` 用 `[^\W\d_]+` 切词，
   汉字串被数字与连字符切成三段 → 印面真习题「证明实轴上每个1-微分形式都是某函数的
   微分」只得 3 词元 < 6，被判「契约习题节点不含任何内容块 = OCR 切片残渣」。⇒ 汉字
   逐字计数、拉丁词逐词计数。

两条都必须保住原有**真阳**：无标签 `> 普通散文` 照报；残渣 name（两三词、空正文）照报。
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
    _ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

import check_unit_quality as cq  # noqa: E402
from format_verify import _H_UL_OPENERS, check_unlabeled_blockquotes  # noqa: E402


def _write(text):
    fd, p = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return p


class AnswerOpener(unittest.TestCase):
    def test_cn_answer_is_legit_opener(self):
        self.assertTrue(_H_UL_OPENERS.match('> **答** $dx|_{(1,0)}(\\xi) = 0$'))
        self.assertTrue(_H_UL_OPENERS.match('> **答**；由外乘积的反交换性'))
        self.assertTrue(_H_UL_OPENERS.match('> **答案** 见下。'))

    def test_answer_block_with_display_math_not_flagged(self):
        md = "\n".join([
            '**问题3**：求 2-形式 $\\omega^2$ 的外平方。',
            '',
            '> **答** $\\omega^2 \\wedge \\omega^2 = 0$ 。',
            '>',
            '> $$',
            '> \\omega^2 \\wedge \\omega^2 .',
            '> $$',
            '',
        ])
        p = _write(md)
        try:
            self.assertEqual(check_unlabeled_blockquotes(p), [])
        finally:
            os.remove(p)

    def test_truly_unlabeled_blockquote_still_flagged(self):
        md = "\n".join([
            '> 这里是一段没有任何结构标签的普通散文句子。',
            '',
        ])
        p = _write(md)
        try:
            self.assertTrue(check_unlabeled_blockquotes(p))
        finally:
            os.remove(p)

    def test_fixer_shares_detector_predicate(self):
        # 检测与修复同源：`> **答**` 块不得被 fixer 剥掉 `>`
        import fix_structural_label_guard as fsl
        self.assertIs(fsl._H_UL_OPENERS, _H_UL_OPENERS)


class CjkStatementWeight(unittest.TestCase):
    def test_cjk_counts_per_character(self):
        self.assertEqual(cq._statement_weight("证明实轴上每个"), 7)
        self.assertEqual(cq._statement_weight("for fows."), 2)
        self.assertEqual(cq._statement_weight("Let B_k be the set"), 6)

    def test_printed_chinese_statement_exempted(self):
        name = ("问题2 证明实轴上每个1-微分形式都是某函数的微分")
        self.assertTrue(cq._name_carries_statement(name))

    def test_short_cjk_fragment_still_rejected(self):
        self.assertFalse(cq._name_carries_statement("的量"))
        self.assertFalse(cq._name_carries_statement("证明这个"))

    def test_english_threshold_unchanged(self):
        self.assertTrue(cq._name_carries_statement(
            "Interactions between adjoint functors and limits"))
        self.assertFalse(cq._name_carries_statement("for flows."))


class PhantomGateOnCjkProblem(unittest.TestCase):
    """幻影闸对「契约 name 自带印面题面而子块为 0」的中文习题须放行，残渣照旧拦。"""

    def _p(self, name, body, key, blocks=0):
        return cq.phantom_exercise_problems(name, blocks, [], [], key, body=body)

    def test_contentless_node_with_full_statement_name_passes(self):
        probs = self._p("问题2 证明实轴上每个1-微分形式都是某函数的微分",
                        "**问题2**：证明实轴上每个 1-微分形式都是某函数的微分。\n",
                        "问题2")
        self.assertEqual([p for p in probs if "不含任何内容块" in p], [], probs)

    def test_contentless_residue_still_flagged(self):
        probs = self._p("for fows.", "and the map on stalks is an isomorphism.",
                        "20.1.5")
        self.assertTrue(any("不含任何内容块" in p for p in probs), probs)

    def test_empty_body_never_exempted(self):
        probs = self._p("证明实轴上每个1-微分形式都是某函数的微分", "", "问题2")
        self.assertTrue(any("不含任何内容块" in p for p in probs), probs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
