# -*- coding: utf-8 -*-
r"""Regression: 多分量书（ncomp>=2）里**内联粘连的边栏印刷号**被 sectioned 误丢。

周民强 / 常庚哲 /《a-first-course-in-stochastic-processes》本卷实测：
书把公式编号 `(7.9)`（ch6 忠实转写）/ `(6.6)`（ch7 忠实转写）**印在纯散文段旁**，
OCR 出来就是一段没有数学记号的散文里粘着一个**带括号**的编号——例如
`"…is a measurable random variable; (7.9)"`。

plain 路径（_scan_text）对**强信号**（带括号 / `Eq.` 前缀）无条件保留
（keep_cross_refs），因此同样的 `\tag` 走 plain 不误判；但 sectioned 抽取在
`elif not self._block_has_math(txt):` 分支此前**直接 continue 丢弃**，两路不对称
→ 总结里忠实继承印刷号的 `\tag{7.9}` / `\tag{6.6}` 被判 **FABRICATED**。

Fix under test（本文件）：sectioned 的 math-free 分支在 `keep_cross_refs=True`
时，把**强信号**括号编号收进 `_cross_ref_union`，build 末尾并入**章级 union**
（FABRICATED 免疫）。判据严格收窄，零回归：
  * 只进 union，**不进**分节 S / 不 _count_label / 不登记位置
    → 不新增 MISSING、不动 ORDER·MISPLACED、不放宽 INCONSISTENT；
  * 只认 `_is_strong_signal`（带括号 / Eq.）——裸 `7.9`（节标题 / 图号 / 页码）
    仍被拒，正是 keep_cross_refs=False 当初要防的 q-miss 污染源；
  * 双括号 OCR 残迹 `((N)` 仍拒（与主提取同判据）；
  * `keep_cross_refs=False` 维持原丢弃行为不变。

Runs under stdlib unittest:
  python verify/tests/test_q_sectioned_inline_glued_label.py
"""  # noqa: E501  (raw docstring quotes OCR'd fragments verbatim)
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


def _union_for(blocks, ch=6, keep=True):
    """One block per page (keeps pages far below the TOC signature so no block
    is mistaken for a section anchor), ncomp=2 patterns, return chapter union."""
    ext = os.path.join(tempfile.mkdtemp(), "_extract")
    os.makedirs(ext, exist_ok=True)
    for i, b in enumerate(blocks, start=1):
        with open(os.path.join(ext, "page_%03d.json" % i), "w",
                  encoding="utf-8") as f:
            json.dump({"text": [{"text": b, "poly": [0, 40, 200, 52]}]},
                      f, ensure_ascii=False)
    src = SourceFormulaIndex(ext, build_formula_patterns(2), False,
                             keep_cross_refs=keep)
    return src.build_sectioned(ch, 1, len(blocks), ["6.1"], ncomp=2)["_union"]


class TestGluedMarginNumberAccepted(unittest.TestCase):
    def test_paren_number_in_math_free_prose_reaches_union(self):
        # ch6 real case: prose-only block with an inline-glued `(7.9)`.
        self.assertIn("7.9", _union_for(
            ["Thus the process X is a measurable random variable; (7.9)"]))

    def test_second_real_case(self):
        # ch7 real case: `(6.6)` glued into a math-free sentence.
        self.assertIn("6.6", _union_for(
            ["It follows from the construction that B is continuous (6.6)"]))

    def test_union_only_no_section_pollution(self):
        # Immunity is union-only: the glued number must NOT enter the per-section
        # map (else it would create a MISSING the book never asked us to write).
        ext = os.path.join(tempfile.mkdtemp(), "_extract")
        os.makedirs(ext, exist_ok=True)
        with open(os.path.join(ext, "page_001.json"), "w", encoding="utf-8") as f:
            json.dump({"text": [{"text": "X is measurable; (7.9)",
                                 "poly": [0, 40, 200, 52]}]}, f, ensure_ascii=False)
        src = SourceFormulaIndex(ext, build_formula_patterns(2), False,
                                 keep_cross_refs=True)
        built = src.build_sectioned(6, 1, 1, ["6.1"], ncomp=2)
        in_any_section = any("7.9" in s for s in built["_sectioned"].values())
        self.assertFalse(in_any_section,
                         "glued cross-ref must not populate the per-section S")
        self.assertIn("7.9", built["_union"])


class TestGuardsStillReject(unittest.TestCase):
    def test_bare_number_not_a_strong_signal_rejected(self):
        # No parens, no Eq. prefix → NOT a strong signal. Must NOT be collected,
        # otherwise keep_cross_refs=False's original q-miss protection regresses.
        self.assertNotIn("7.9", _union_for(
            ["compare with the estimate 7.9 obtained above"]))

    def test_doubled_paren_ocr_artifact_rejected(self):
        # `((6.6)` = math content mis-read then glued: never a real label column.
        self.assertNotIn("6.6", _union_for(["we rewrite ((6.6) in matrix form"]))

    def test_keep_cross_refs_false_preserves_drop(self):
        # The other documented behaviour: keep_cross_refs=False keeps dropping
        # math-free paren hits (books that never reproduce cross-chapter tags).
        self.assertNotIn("7.9", _union_for(
            ["X is a measurable random variable; (7.9)"], keep=False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
