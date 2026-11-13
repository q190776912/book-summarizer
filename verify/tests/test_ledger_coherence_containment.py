# -*- coding: utf-8 -*-
"""2026-11-13：ledger_coherence 度量口径与 pairing_problems 对齐。

旧实现只用对称 `_ratio`：同一枚式子的**残缺/误读账身**被长度差压到 ~0.75 < hi，
整章被误判「账本不自洽」→ ORDER/MISPLACED/TAG 三支 WARN 被撤（覆盖空洞）。
`pairing_problems` 早已用 `_containment >= 0.90` 豁免同一形态，两者口径不一致。
修后两者同源；全库实验：8 本降级书里 5 章恢复校验，WARN 仍 0、PASS 未变。
"""
import importlib.util
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
import lib.boot as _boot
_boot.setup()

spec = importlib.util.spec_from_file_location(
    "_test_pairing_mod", os.path.join(
        _ROOT, "verify/formula_tag/script/tag_formula_pairing.py"))
tp = importlib.util.module_from_spec(spec)
sys.modules["_test_pairing_mod"] = tp
spec.loader.exec_module(tp)


def _body(i):
    return ("x_{%d}^{2}+y_{%d}^{2}=z_{%d}^{2}+\\alpha_{%d}\\beta_{%d}"
            % (i, i, i, i, i))


class TestLedgerCoherenceContainment(unittest.TestCase):
    def _build(self, n=8, truncate=True):
        printed, summary = {}, []
        for i in range(1, n + 1):
            key = "9.%d" % i
            full = _body(i)
            summary.append((key, full))
            # 残缺账身 = 总结正文的前 60%（OCR 只读了上半行）
            printed[key] = [full[:int(len(full) * 0.6)] if truncate
                            else "totally_unrelated_%d_%d" % (i, i * 7)]
        return printed, summary

    def test_truncated_books_are_coherent(self):
        """残缺账身与总结是同一枚式子 → 不得降级（旧实现 ≈0.75 < 0.80 判不自洽）。"""
        printed, summary = self._build(truncate=True)
        # 先证明确实是「_ratio 判不自洽、_containment 判配上自己」的形态
        full = summary[0][1]
        frag = printed["9.1"][0]
        self.assertLess(tp._ratio(tp.norm_math(full), tp.norm_math(frag)), 0.80)
        self.assertGreaterEqual(
            tp._containment(tp.norm_math(frag), tp.norm_math(full)), 0.90)
        self.assertGreaterEqual(tp.ledger_coherence(printed, summary),
                                tp.LEDGER_COHERENCE_MIN)

    def test_unrelated_bodies_still_incoherent(self):
        """反向锁：两条完全不同的式子不得被包含度闸误放行。"""
        printed, summary = self._build(truncate=False)
        got = tp.ledger_coherence(printed, summary)
        self.assertIsNotNone(got)
        self.assertLess(got, tp.LEDGER_COHERENCE_MIN)

    def test_too_few_samples_returns_none(self):
        """样本不足仍不降级（口径不变）。"""
        printed, summary = self._build(n=4, truncate=False)
        self.assertIsNone(tp.ledger_coherence(printed, summary))

    def test_empty_input_returns_none(self):
        self.assertIsNone(tp.ledger_coherence({}, []))
        self.assertIsNone(tp.ledger_coherence({"9.1": ["abc"]}, []))


if __name__ == "__main__":
    unittest.main()
