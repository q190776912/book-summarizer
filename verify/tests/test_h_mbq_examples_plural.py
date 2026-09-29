# -*- coding: utf-8 -*-
r"""h_mbq 必包闸的「Examples 复数题头」语言对称性回归（Iwaniec–Kowalski 解析数论，2026-09-29）。

背景：必包表 `_H_MISSING_BQ` 的英文分支写作 `Example(?![\w\-])`，复数尾巴 `s` 使
印面 run-in 标签 `**Examples.**`（后随显示公式，非 item 附属块）**天然不命中**；
跨书普查 69,403 个源单元里有 22 处该形，分布于 8 本已收官书、全部按印面留在顶层
并过闸。中文同位写法 `**例子。**` 旧版却命中 `例` 分支 → 同一结构「源过 / 译不过」，
译者只能把合法顶层标签塞进 `>`（还会触发 G 层「半包」）或改词规避，两版结构分叉
（与 2026-09-27/28 的 Note/Notes、Remark/评注 同族）。

根治 = `例` 分支排除复数尾 `子`（`例(?!子)`），与英文侧对齐；带编号或单数的例子块
（`**例。**` / `**例 3.**` / `**Example.**` / `**Example 1.1**`）**必须仍然**判必包
（负向断言）。
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

from format_verify import check_labels_missing_blockquote, _H_MISSING_BQ
from fix_structural_label_guard import fix_labels_missing_blockquote


def _run(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                    encoding="utf-8")
    f.write(text)
    f.close()
    try:
        return check_labels_missing_blockquote(f.name)
    finally:
        os.unlink(f.name)


def _fix(text):
    f = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                    encoding="utf-8")
    f.write(text)
    f.close()
    try:
        n = fix_labels_missing_blockquote(f.name)
        with open(f.name, encoding="utf-8") as fh:
            body = fh.read()
        return n, body
    finally:
        os.unlink(f.name)


CLEAN_BOTH = {
    # 本书 ch4 0012 实测：run-in 复数标签引出 (4.27)(4.28) 两个显示公式
    "cn-plural-runin": "**例子。** 由 Fourier 对 (4.83)、(4.84)、(4.85) 可得下列等式：\n",
    "cn-plural-heading": "**例子**\n\n见下式。\n",
    "en-plural-runin": "**Examples.** From the Fourier pairs (4.83), (4.84) "
                       "we obtain:\n",
    "en-plural-heading": "**Examples**\n\nsee below.\n",
}

STILL_REQUIRED = {
    "cn-bare": "**例。** 取 $f ( x ) = x ^ { 2 }$ 即得。\n",
    "cn-numbered": "**例 3.** 这是带编号的例子块。\n",
    "cn-number-first": "**3.1-3 例子（Poisson）** 取 $f$ 为示性函数。\n",
    "en-singular": "**Example.** Take $f(x)=x^{2}$.\n",
    "en-numbered": "**Example 1.1-2**: a numbered one.\n",
    "en-number-first": "**3.1-3 Example (Poisson)** take the indicator.\n",
}


class TestExamplesPluralSymmetry(unittest.TestCase):
    def test_plural_examples_clean_both_languages(self):
        for k, text in CLEAN_BOTH.items():
            self.assertEqual(_run(text), [], f"{k}: 复数 Examples/例子 题头不得判必包")

    def test_fixer_leaves_plural_examples_alone(self):
        n, body = _fix(CLEAN_BOTH["cn-plural-runin"])
        self.assertEqual(n, 0, "修复器不得把合法顶层 Examples 标签包进 `>`")
        self.assertTrue(body.startswith("**例子。**"))

    def test_regex_vocabulary(self):
        self.assertIsNone(_H_MISSING_BQ.match("**例子。** x"))
        self.assertIsNone(_H_MISSING_BQ.match("**Examples.** x"))
        for k, text in STILL_REQUIRED.items():
            self.assertTrue(_H_MISSING_BQ.match(text.split("\n")[0]),
                            f"{k}: 单数/带编号例子块仍须在必包表内")


class TestSingularExampleStillRequired(unittest.TestCase):
    def test_singular_or_numbered_example_still_flagged(self):
        for k, text in STILL_REQUIRED.items():
            self.assertEqual(len(_run(text)), 1, f"{k}: 单数/带编号例子块仍须判必包")


if __name__ == "__main__":
    unittest.main(verbosity=2)
