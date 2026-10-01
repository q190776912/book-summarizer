"""回归：契约骨架节名与最终 md 标题的**乘法记号**须折到同一形态。

成因（Lee《Introduction to Smooth Manifolds》附录 D §U5，2026-10-01 实测）：
契约 section `name` 来自 OCR 印面「2×2 Constant-Coefficient Linear Systems」，
而最终 md 标题按写作规则（数学一律 KaTeX）写成
`### § $2\\times2$ Constant-Coefficient Linear Systems`。旧 `_norm_text` 只留
字母数字，于是两侧分别归一成 `22constant…` 与 `2times2constant…`，
`_missing_contract_names` 把在位节假报「不在位」并硬拒 merge_source 证据。

锁死三件事：
  ① 运算符折叠后在位节不再假报（正反例同串）；
  ② 真漏写该节时仍报缺（放宽判据的负向对照）；
  ③ 只折运算符：字母命令 `\\alpha` 不参与折叠，两个仅字母命令不同的节名
     不得被折成同名（否则「A 在位」会替「B 在位」背书）。
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

from flows._flow_contract import physical_evidence as pe  # noqa: E402


def _contract(name):
    return {"key": "D", "type": "chapter", "name": "Appendix D",
            "sub_sec": [{"key": "U5", "type": "section", "name": name,
                         "sub_sec": []}]}


HEADED = "### § $2\\times2$ Constant-Coefficient Linear Systems\n"
CN_HEADED = "### § $2 \\times 2$ 常系数线性方程组\n"


class MathSymbolFoldTest(unittest.TestCase):
    NAME = "2×2 Constant-Coefficient Linear Systems"

    def test_latex_times_matches_ocr_multiplication_sign(self):
        self.assertEqual(
            [], pe._missing_contract_names(_contract(self.NAME),
                                           pe._norm_text(HEADED)))

    def test_spaced_latex_form_also_matches(self):
        # 印面「2 × 2」两侧带空格，KaTeX 侧亦然；运算符按删除折叠（与旧行为
        # 「印面符号被字符过滤丢弃」同级），故两侧都归成 `22abc`。
        self.assertEqual("22abc", pe._norm_text("$2 \\times 2$ abc"))
        self.assertEqual(pe._norm_text("2×2 abc"), pe._norm_text("$2\\times2$ abc"))

    def test_still_reports_a_genuinely_missing_section(self):
        self.assertEqual(["U5"], pe._missing_contract_names(
            _contract(self.NAME), pe._norm_text("## § Some Other Section\n")))

    def test_letter_commands_are_not_folded(self):
        # \alpha 保留字母：只折运算符，避免把不同条目名折成同名。
        self.assertNotEqual(pe._norm_text("$\\alpha$ set"),
                            pe._norm_text("a set"))
        self.assertEqual(["U5"], pe._missing_contract_names(
            _contract(r"$\alpha$ Set"), pe._norm_text("### § a Set\n")))


if __name__ == "__main__":
    unittest.main()
