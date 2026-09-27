"""test_h_legit_bq_pingzhu.py — 「已包裹的评注/说明块」开吻识别双语对称回归。

Etingof《群表示论》步骤6 实测（2026-09-28）：必包表 `_H_MISSING_BQ` 要求
`**评注 N.M**` / `**说明 N.M**` 包进 `>`（且 `Remarks?` 的 CN 标准译名就是「评注」，
Weibel / do Carmo / 本书全书用此形），但**认合法块引用开吻**的
`_h_ext_is_legit_bq` 只列了 `**证明 / **例 / **注 / **解` —— `**评注` 既不 startswith
`**注`，也不在 EN 分支，于是「已经按规矩包好」的中文评注块不被承认为合法开吻，
`_h_ext_items` 把它的 `> $$` 当成「陈述区里被误包的内容」报 h_stmt_bq，
而同结构的英文 `> **Remark 6.12**` 走 EN 分支直接放行 → **「源过 / 译不过」**，
译者唯一的出路竟是把 `>` 拆掉（拆了又被 `_H_MISSING_BQ` 抓）。

根治 = 合法开吻表与必包表同源补齐（评注、说明）。本测试锁两件事：
1. `_h_ext_is_legit_bq` 对中英同义标签判定相等（此前 EN 真 / CN 假）；
2. 集成面：顶层条目 + 包裹的评注块内含 `> $$`，中英两版 `check_h_statement_in_blockquote`
   都必须为空（旧版此处 CN 报假违规）。
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
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from format_verify import (_h_ext_is_legit_bq, check_h_statement_in_blockquote)

_PAIRS = [("> **Remark 6.12** A remark with a formula.", "> **评注 6.12** 一条带公式的评注。"),
          ("> **Note 2.1** Something to keep in mind.", "> **说明 2.1** 需要记住的一点。"),
          ("> **Remark 6.12** text.", "> **注 6.12** 正文。"),
          ("> **Proof 3.1** text.", "> **证明 3.1** 正文。"),
          ("> **Example 4.2** text.", "> **例 4.2** 正文。")]


class LegitBlockquoteOpenerSymmetry(unittest.TestCase):
    def test_cn_pingzhu_is_legit_opener(self):
        # 旧版此处假红：CN 评注不被承认，EN Remark 承认 → 双语判据不等
        self.assertTrue(_h_ext_is_legit_bq("> **评注 6.12** 一条带公式的评注。"))
        self.assertTrue(_h_ext_is_legit_bq("> **说明 2.1** 需要记住的一点。"))

    def test_bilingual_same_verdict(self):
        for en, cn in _PAIRS:
            self.assertEqual(
                _h_ext_is_legit_bq(en), _h_ext_is_legit_bq(cn),
                "EN/CN legit-opener verdict differ for %r vs %r" % (en, cn))
            self.assertTrue(_h_ext_is_legit_bq(en), "legit opener must be recognized: %r" % en)

    def test_unwrapped_or_foreign_lines_not_legit(self):
        # 不得过度触发：非 `>` 行、无标签散文行仍不认作合法开吻
        self.assertFalse(_h_ext_is_legit_bq("**评注 6.12** 顶层未包裹。"))
        self.assertFalse(_h_ext_is_legit_bq("> 一句没有标签的散文。"))
        self.assertFalse(_h_ext_is_legit_bq("> $$"))


def _flagged(md):
    fd, p = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    try:
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(md)
        return check_h_statement_in_blockquote(p)
    finally:
        os.remove(p)


class WrappedRemarkFormulaNotFlagged(unittest.TestCase):
    """包裹的评注/Remark 块内的 `> $$` 不是「被误包的陈述内容」。"""

    def _doc(self, label_line, formula_note):
        return "\n".join([
            "## §6.6 Abelian categories",
            "",
            "**Definition 6.12** An object $X$ is injective if the functor",
            "",
            "$$\\operatorname{Hom}(X, -)$$",
            "",
            "is exact.",
            "",
            label_line,
            ">",
            "> $$\\operatorname{Ext}^{1}(Z, X) = 0$$",
            ">",
            formula_note,
            "",
            "That is all.",
            "",
        ])

    def test_en_remark_block_passes(self):
        self.assertEqual(
            _flagged(self._doc("> **Remark 6.12**", "> It holds for every $Z$.")), [])

    def test_cn_pingzhu_block_passes(self):
        # 旧版此处报假违规（把块内 `> $$` 当陈述区内容）
        self.assertEqual(
            _flagged(self._doc("> **评注 6.12**", "> 对每个 $Z$ 成立。")), [])

    def test_bilingual_same_verdict(self):
        en = self._doc("> **Note 2.1**", "> Keep this in mind.")
        cn = self._doc("> **说明 2.1**", "> 记住这一点。")
        self.assertEqual(bool(_flagged(en)), bool(_flagged(cn)))
        self.assertEqual(_flagged(cn), [])


if __name__ == "__main__":
    unittest.main()
