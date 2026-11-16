# -*- coding: utf-8 -*-
"""F 层规则17 `ex_bq_scope` 在**单元门控**的接线回归。

背景（2026-11-16）：规则17 先在文档级 F 层落地（`verify/format_verify`），但
单元门控 `check_unit_quality._run_format_verify_unit_checks` 只复用了旧的
nested_bq / ex_proof_gaps / … 几项，`check_example_block_scope` 没接进去 ⇒
写源期单元里「例块吞掉后续散文 / 编号条目 / 小节标题」要等拼接后整章 verify
才暴露，返工面从 1 个单元放大到整章。本测试锁死单元级接线：

  ① 越界信号 ITEM / SECTION / DUP 在 `check_body`（出厂入口）即 FAIL；
  ② 合法体例（Example 内 `Theorem … assumes …` 回指、`\\tag{}`）不误报；
  ③ 干净的例块 0 命中。

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_ex_bq_scope_unit_gate.py
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, str(Path(_ROOT) / "flows" / "write-source" / "script"))

import check_unit_quality as cuq  # noqa: E402

MARK = "Example blockquote swallowed following prose"

DUP_PROSE = (
    "The number of specialized techniques that have been developed to solve partial "
    "differential equations is staggering, and flows reduce first-order PDEs to ODEs "
    "in a way that needs no specialized PDE theory at all.")


def _clean_body():
    return (
        "> **Example 9.50.** Define a time-dependent vector field $V$ on "
        "$\\mathbb{R}^n$ by\n"
        ">\n"
        "> $$\n"
        "> V(t, x) = \\frac{1}{t} x^i\n"
        "> $$\n"
        ">\n"
        "> The maximal solution to this system is $x^i(t) = t x_0^i / t_0$, "
        "defined for all $t > 0$.\n")


def _hits(body):
    """走 `check_body`（单元闸出厂入口），只取规则17 的报文。"""
    _ok, probs = cuq.check_body("item", "9.50 Example (time-dependent vector field)",
                                body)
    return [p for p in probs if MARK in p]


class TestExampleBlockScopeUnitGate(unittest.TestCase):

    def test_clean_example_is_silent(self):
        self.assertEqual(_hits(_clean_body()), [])

    def test_swallowed_numbered_exercise_is_detected(self):
        body = _clean_body().replace(
            "defined for all $t > 0$.\n",
            "defined for all $t > 0$.\n"
            "> Exercise 14.28. Prove that diagram (14.27) commutes and use it.\n")
        got = _hits(body)
        self.assertEqual(len(got), 1, got)
        self.assertIn("[ITEM]", got[0])

    def test_swallowed_section_heading_is_detected(self):
        body = _clean_body().replace(
            "defined for all $t > 0$.\n",
            "defined for all $t > 0$.\n"
            "> ### § Quasilinear Equations\n")
        got = _hits(body)
        self.assertEqual(len(got), 1, got)
        self.assertIn("[SECTION]", got[0])

    def test_duplicated_top_level_prose_is_detected(self):
        body = _clean_body() + "> " + DUP_PROSE + "\n\n---\n\n" + DUP_PROSE + "\n"
        got = _hits(body)
        self.assertEqual(len(got), 1, got)
        self.assertIn("[DUP]", got[0])

    def test_running_citation_inside_example_is_not_a_false_positive(self):
        body = _clean_body().replace(
            "defined for all $t > 0$.\n",
            "defined for all $t > 0$.\n"
            "> Theorem 2.4.3 assumes that the distribution $F$ is not a lattice "
            "distribution.\n")
        self.assertEqual(_hits(body), [])

    def test_tag_inside_example_is_not_a_violation(self):
        body = _clean_body().replace(
            "> V(t, x) = \\frac{1}{t} x^i\n",
            "> V(t, x) = \\frac{1}{t} x^i \\tag{9.20}\n")
        self.assertEqual(_hits(body), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
