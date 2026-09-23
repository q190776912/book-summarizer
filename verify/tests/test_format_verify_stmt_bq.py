"""
test_format_verify_stmt_bq.py — h_stmt_bq 证明头识别回归（Leinster BCT 实测）。

`> **引理2.2.2的证明思路**：` 是 CN 版证明头（标签前置）。旧 _h_ext_is_legit_bq
只认 `**证明**` 开头、数字前置 `**2.2.2 证明**` 与 EN `**Proof`，CN 证明头
不被承认为 legit opener → 其后的 `> $$` 落进 statement 区 → 假报
「statement content wrapped in `>`」。修复 = 增加「…的证明 / …的证明思路 /
…证毕」加粗头判定。真子项 `> （a）` / statement 区 `> $$` 仍必须被报。
"""
import os
import re
import sys
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

from format_verify import _h_ext_is_legit_bq, _h_ext_is_structural_bq


class CnProofHeaderLegitTest(unittest.TestCase):
    def test_label_prefixed_cn_proof_header(self):
        self.assertTrue(_h_ext_is_legit_bq(
            "> **引理2.2.2的证明思路**：我们证明三角 (2.4) 交换。"))

    def test_plain_cn_proof_header_still_ok(self):
        self.assertTrue(_h_ext_is_legit_bq("> **证明**：设 $A \\in \\mathcal{A}$。"))

    def test_en_proof_header_still_ok(self):
        self.assertTrue(_h_ext_is_legit_bq("> **Proof of Lemma 2.2.2:** ..."))

    def test_statement_region_subpoint_still_structural(self):
        line = "> （a）这是被错误包进块引用的命题子项。"
        self.assertFalse(_h_ext_is_legit_bq(line))
        self.assertTrue(_h_ext_is_structural_bq(line))


if __name__ == '__main__':
    unittest.main()
