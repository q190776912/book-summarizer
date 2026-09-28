# -*- coding: utf-8 -*-
r"""Regression: 左缘编号书把公式编号**粘在显示公式行开头**（形态③）。

Apostol《Introduction to Analytic Number Theory》(2026-09-28 实测)：编号印在
**左缘**并与公式同一行，OCR 出来的块长这样——`(12) B(x) = \sum...`、无空格的
`(16)x(a) = x(b)`、以及数学式被读残的 `(26) If(n)l`（|f(n)| 掉成字母）。旧的
ncomp==1 节级抽取只认「独立成块的裸 `(N)`」（形态①）和「含数学记号且以 `(N)`
结尾」（形态②，右缘书），于是 15 处忠实继承印刷号的 `\tag` 全被判 FABRICATED。

Fix under test: `build_sectioned` 的形态③分支（`_FORM3_HEAD_RE` +
`_FORM3_MATHISH_RE`）——编号必须在块**最开头**且其后确有数学正文，才能与
`(31) gives us …` 这类散文回指区分；另加双括号 OCR 残迹 `((40)` 的拒绝
（Apostol ch11 p253，收下即造出一条该书从未印过的 MISSING）。

Runs under stdlib unittest:
  python verify/tests/test_q_layer_leftmargin_label_form3.py
"""  # noqa: E501  (raw docstring: it quotes OCR'd LaTeX fragments verbatim)
import json
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

from formula_tag import SourceFormulaIndex, build_formula_patterns  # noqa: E402


def _one_label_per_page(ext, blocks):
    """Write one page per block so pages stay far below the TOC signature
    (>= 4 titled heading-like short blocks) and no block hides another."""
    os.makedirs(ext, exist_ok=True)
    for i, b in enumerate(blocks, start=1):
        with open(os.path.join(ext, "page_%03d.json" % i), "w",
                  encoding="utf-8") as f:
            json.dump({"text": [{"text": b, "poly": [0, 40, 200, 52]}]},
                      f, ensure_ascii=False)
    src = SourceFormulaIndex(ext, build_formula_patterns(1), False)
    return src.build_sectioned(3, 1, len(blocks), ["3.11"], ncomp=1)["_union"]


class TestLeftMarginLabelAccepted(unittest.TestCase):
    def test_spaced_label_glued_to_formula(self):
        self.assertEqual(_one_label_per_page(
            os.path.join(tempfile.mkdtemp(), "_extract"),
            ["(12) B(x) = \\sum_{n \\le x} a_n"]), {"12"})

    def test_no_space_label_glued_to_formula(self):
        self.assertEqual(_one_label_per_page(
            os.path.join(tempfile.mkdtemp(), "_extract"),
            ["(16)x(a) = x(b)"]), {"16"})

    def test_mangled_math_still_accepted_via_paren_group(self):
        # `(26) If(n)l` = 原书 `|f(n)|` 被 OCR 读成字母：整块过不了
        # _block_has_math，但剩余含自括号函数群 `(n)`，与散文回指可分。
        self.assertIn("26", _one_label_per_page(
            os.path.join(tempfile.mkdtemp(), "_extract"), ["(26) If(n)l"]))


class TestProseAndNoiseStillRejected(unittest.TestCase):
    def test_anaphoric_prose_reference_rejected(self):
        self.assertEqual(_one_label_per_page(
            os.path.join(tempfile.mkdtemp(), "_extract"),
            ["(31) gives us the desired bound"]), set())

    def test_doubled_paren_ocr_artifact_rejected(self):
        # Apostol ch11 p253 `'((40)'`：数学内容 ζ(2s) 读残后粘上的括号碎片，
        # 收下即造出本书从未印过的 40。
        self.assertEqual(_one_label_per_page(
            os.path.join(tempfile.mkdtemp(), "_extract"), ["((40)"]), set())

    def test_mid_block_paren_number_still_rejected(self):
        self.assertEqual(_one_label_per_page(
            os.path.join(tempfile.mkdtemp(), "_extract"),
            ["we apply (7) to the sum on the right"]), set())

    def test_standalone_and_tail_forms_unchanged(self):
        # 形态①/②（既有路径）零回归。
        self.assertEqual(_one_label_per_page(
            os.path.join(tempfile.mkdtemp(), "_extract"),
            ["(5)", "f(x) \\le M (9)"]), {"5", "9"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
