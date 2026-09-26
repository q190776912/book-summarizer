# -*- coding: utf-8 -*-
"""Regression: 第 18 项「控制字符闸」（Kreyszig ch9 9.1-2，2026-09-26）。

写手代理用 shell / ``python -c`` 内嵌字符串改单元时，``\\alpha`` / ``\\beta`` 里的
``\\a`` / ``\\b`` 被当成转义序列吞掉，正文留下 ``($\x07lpha$)`` 这类**吃掉字母**的
内容。损坏落在数学模式内：F1–F6 散文启发式看不见（``_prose_text`` 已剥掉
``$...$``），契约 tag 对账也看不见，只有真实 KaTeX 渲染报 ``Unexpected character``，
而报错串本身又把控制字符打成不可见转义，极难定位。

锁死：C0 控制字符（``\t\n\r`` 除外）一律判不通过；item / desc / exercise 三种单元
都执行（exercise 跳过 F1–F6，本闸不得随之跳过）；正常含 ``\t`` / CRLF 的正文不误伤。

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_control_char_gate.py
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

BEL, BS = "\x07", "\x08"


def _problems(body, utype="item"):
    ok, probs = cuq.check_body(utype, "9.1-2 Resolvent set).  Let T", body)
    return ok, [p for p in probs if "控制字符" in p]


class TestControlCharGate(unittest.TestCase):
    def test_alpha_beta_escape_damage_caught(self):
        # 实测形态：($\a lpha$) → BEL + "lpha"
        body = ("**9.1-2 Theorem.** Let $T$ be linear. Then:\n>\n"
                "> ($%slpha$) $T_{\\lambda}$ is bijective.\n" % BEL)
        ok, hits = _problems(body)
        self.assertFalse(ok)
        self.assertEqual(len(hits), 1, hits)
        self.assertIn("U+0007", hits[0])

    def test_bell_and_backspace_reported_together(self):
        ok, hits = _problems("text ($%slpha$) and ($%seta$) here\n" % (BEL, BS))
        self.assertFalse(ok)
        self.assertIn("U+0007", hits[0])
        self.assertIn("U+0008", hits[0])

    def test_exercise_unit_not_exempt(self):
        # exercise 单元跳过 F1–F6，但控制字符闸必须照跑
        ok, hits = _problems("1. Show that ($%seta$) holds.\n" % BS,
                             utype="exercise")
        self.assertFalse(ok)
        self.assertTrue(hits)

    def test_clean_math_not_flagged(self):
        for body in [
            "**9.1-2 Theorem.** Let $x\\in H$. Then ($\\alpha$) and ($\\beta$).\n",
            "a tab\there and CRLF\r\nended body\n",
            "> 1. By (2) we have $\\alpha_n\\to\\alpha$.\n",
        ]:
            ok, hits = _problems(body)
            self.assertEqual(hits, [], body)

    def test_no_false_positive_on_normal_body(self):
        # 整段无控制字符的正常单元正文：本闸不得贡献任何问题
        body = ("**3.10-5 Theorem (Sequences of self-adjoint operators).** Let "
                "$(T_n)$ be bounded self-adjoint with $\\lVert T_n - T\\rVert\\to 0$.\n\n"
                "> **Proof.**\n>\n"
                "> 1. By 3.9-4, $\\lVert T_n^* - T^*\\rVert = \\lVert T_n - T\\rVert$.\n"
                "> 2. Hence $\\lVert T - T^*\\rVert = 0$.\n")
        _ok, hits = _problems(body)
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
