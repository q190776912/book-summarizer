# -*- coding: utf-8 -*-
"""Q 层「降级归属」判据回归（2026-11-09 审计）。

`pairing_problems` 的 `ledger_coherence_val` 闸只服务**显式调用方**（普查工具 /
判据测试）。Q 层 `formula_tag.run()` 必须**不**传该值，才能先取原始
`q_tag_mismatch` 行供 `[Q-LAYER EVIDENCE-DEGRADED]` 逐号留痕、再清空三支；
若在下层提前 `return []`，降级 INFO 会丢掉被跳过的号。

此文件锁住「双层分工」的静态形态，防止退回 11-08 那个「参数定义了却没人传、
注释却说传了」的死代码状态。行为回归由 test_q_layer_ledger_coherence.py 覆盖。
"""
import inspect
import os
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
import lib.boot  # noqa: E402
lib.boot.setup()

import formula_tag as ft  # noqa: E402
import tag_formula_pairing as tfp  # noqa: E402


class TestDegradeOwnership(unittest.TestCase):
    def test_q_layer_helper_has_no_dead_coherence_param(self):
        sig = inspect.signature(ft._tag_pairing_rows)
        self.assertNotIn("coherence", sig.parameters)
        self.assertIn("printed", sig.parameters)

    def test_pairing_probe_keeps_optional_gate_for_direct_callers(self):
        sig = inspect.signature(tfp.pairing_problems)
        self.assertIn("ledger_coherence_val", sig.parameters)

    def test_q_layer_source_never_passes_coherence(self):
        src = (Path(_ROOT) / "verify" / "formula_tag" / "script" /
               "formula_tag.py").read_text(encoding="utf-8-sig")
        self.assertNotIn("ledger_coherence_val=coherence", src)
        self.assertIn("[Q-LAYER EVIDENCE-DEGRADED]", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
