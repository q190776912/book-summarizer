# -*- coding: utf-8 -*-
r"""Regression: 练习题头的中英不对称（Iwaniec–Kowalski《解析数论》ch18 0006，2026-09-29）。

英文源印 `> **Exercise 1.** …` 且 `Exercise` 历来在 `_H_UL_OPENERS` 白名单内 → 源单元过闸；
中文译版照印面写 `> **练习1。** …`，表内却没有中文同位词 → 判「unlabeled blockquote」，
同一结构「源过 / 译不过」。译者只剩两条自撰出路：把练习题头改成 `注`/`说明`（改印面标签），
或拆出 `>`（破坏附属块规则）。⇒ `练习|习题` 与 `Exercise` 对等入白名单。

必须保住的**反向**判据：`_H_MISSING_BQ`（必包表）不含 `Exercise`，故也不得含 练习/习题——
顶层 `**习题 3.**` 是印面合法形态，不得反过来逼译者把练习包进 `>`。
真阳照旧：无标签 `> 普通散文` 仍须报。
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

from format_verify import (_H_MISSING_BQ, _H_UL_OPENERS,  # noqa: E402
                           check_unlabeled_blockquotes)


class TestExerciseLabelCNSymmetry(unittest.TestCase):
    def _check(self, lines):
        fd, p = tempfile.mkstemp(suffix=".md")
        os.close(fd)
        try:
            with io.open(p, "w", encoding="utf-8", newline="") as f:
                f.write("\n".join(lines))
            return check_unlabeled_blockquotes(p)
        finally:
            os.remove(p)

    def test_cn_exercise_head_is_allowed_opener(self):
        for ln in (u'> **练习1。** 证明命题18.2蕴含原理3。',
                   u'> **练习 2** 由命题18.2导出实零点的西格尔界 (5.73)。',
                   u'> **习题3.** 设 $q\\geqslant1$。',
                   u'> **Exercise 1.** Prove Proposition 18.2.'):
            self.assertTrue(_H_UL_OPENERS.match(ln), ln)

    def test_cn_exercise_block_passes_unlabeled_check(self):
        lines = [u'> **练习1。** 证明命题18.2蕴含原理3。',
                 u'>',
                 u'> **练习2。** 导出 (5.73)。',
                 u'',
                 u'正文散文。']
        self.assertEqual(self._check(lines), [])

    def test_top_level_exercise_not_forced_into_blockquote(self):
        # 必包表对称地**不含**练习/习题（EN 侧也不含 Exercise）
        for ln in (u'**习题 3.** 设 $q\\geqslant1$。',
                   u'**练习3。** 证明之。',
                   u'**Exercise 3.** Prove it.'):
            self.assertIsNone(_H_MISSING_BQ.match(ln), ln)

    def test_true_positive_unlabeled_prose_still_reported(self):
        lines = [u'> 这里是一句没有任何标签的普通散文，继续续行。',
                 u'正文。']
        self.assertTrue(self._check(lines))


if __name__ == "__main__":
    unittest.main()
