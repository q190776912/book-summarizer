# -*- coding: utf-8 -*-
"""Regression: 第 17 项「裸变量+下标数字」判据的**重音字母**豁免（katex_heuristics._VAR_DIGIT_RE）。

背景（Robinson ch1 0085，2026-09-27）：印面文献键 `[Hén76]`（Hénon）里 `é` 紧跟数字串，
旧判据 `(?<![A-Za-z$\\\\])` 只认 ASCII 字母 → 把 `én76` 读成裸变量 `n7` 判 FAIL，写手被迫
把题录改成 `[Hén 76]`（篡改印面形态）才过闸。根治 = 判据的边界类改成 **Unicode 字母类**
`[^\\W\\d_$]`（外加 `$` / 反斜杠），数字与下划线照旧**不**算字母，故 `2x0`、`x_0` 行为不变。

锁死方向：印面题录（含重音/非 ASCII 字母）不报；真裸变量必须照报。

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_bare_math_accented_letters.py
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:  # pragma: no cover
    _ROOT = str(Path(__file__).resolve().parents[4])
sys.path.insert(0, str(Path(_ROOT) / "verify" / "format_verify" / "script"))

import katex_heuristics as kh  # noqa: E402


def _hits(text):
    return kh.find_bare_math_errors(text.splitlines())


class TestVarDigitAccentExemption(unittest.TestCase):
    def test_accented_bibliography_keys_do_not_fire(self):
        for ok in ["where $a$ and $b$ are constants [Hén76].",
                   "Rigorous results are available [BF96], [KH95].",
                   "see [Kat95] and [Pe189] for the details.",
                   "the argument of [Mis76]; cf. [Din71]."]:
            self.assertEqual(_hits(ok), [], ok)

    def test_bare_variable_still_fires(self):
        for bad in ["the value n7 is bounded by 1.",
                    "consider x0 and t1 as initial data",
                    "[Hén76] and n7 appear together here"]:
            self.assertTrue(_hits(bad), bad)

    def test_digit_and_underscore_neighbours_unchanged(self):
        # 数字/下划线不是「字母」：既不能豁免判据，也不该新报
        self.assertTrue(_hits("we map 2x0 onto the axis"))
        self.assertEqual(_hits("the sequence $x_{0}$ converges"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
