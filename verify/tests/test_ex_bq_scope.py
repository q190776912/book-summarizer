# -*- coding: utf-8 -*-
"""2026-11-15: F-layer rule 17 `ex_bq_scope` detector + report wiring."""
import importlib.util
import io
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
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if os.path.join(_ROOT, "lib") not in sys.path:
    sys.path.insert(0, os.path.join(_ROOT, "lib"))
import lib.boot as _boot
_boot.setup()


def _load(alias, rel):
    spec = importlib.util.spec_from_file_location(alias, os.path.join(_ROOT, rel))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


fv = _load("_test_ex_bq_scope_fv", "verify/format_verify/script/format_verify.py")
from verify.script.base import DEFAULT_RESULT  # noqa: E402
from verify.script.report import print_result  # noqa: E402

DUP_LINE = ("The number of specialized techniques that have been developed to solve partial "
            "differential equations is staggering, and flows reduce first-order PDEs to ODEs "
            "in a way that needs no specialized PDE theory at all.")


def _clean_md():
    return [
        "# Chapter 9",
        "",
        "## § Integral Curves",
        "",
        "> **Example 9.50.** Define a time-dependent vector field $V$ on $\\mathbb{R}^n$ by",
        "> ",
        "> $$",
        "> V(t, x) = \\frac{1}{t} x^i",
        "> $$",
        "> ",
        "> The maximal solution to this system is $x^i(t) = t x_0^i / t_0$, defined for all $t > 0$.",
        "",
        "---",
        "",
        "We now turn to a different topic and develop the language needed for the next section.",
        "",
    ]


class ExampleScopeDetectorTests(unittest.TestCase):

    def test_clean_example_is_silent(self):
        self.assertEqual(fv.check_example_block_scope(_clean_md()), [])

    def test_duplicated_top_level_prose_is_detected(self):
        lines = _clean_md()
        lines.insert(11, "> " + DUP_LINE)
        lines.append(DUP_LINE)
        out = fv.check_example_block_scope(lines)
        self.assertEqual(len(out), 1, out)
        self.assertIn("[DUP]", out[0])

    def test_standalone_numbered_item_is_detected(self):
        lines = _clean_md()
        lines.insert(11, "> Exercise 14.28. Prove that diagram (14.27) commutes and use it.")
        out = fv.check_example_block_scope(lines)
        self.assertEqual(len(out), 1, out)
        self.assertIn("[ITEM]", out[0])

    def test_running_prose_citation_is_not_a_false_positive(self):
        lines = _clean_md()
        for s in ("Theorem 2.4.3 assumes that the distribution $F$ is not a lattice distribution.",
                  "Problem 13-21 shows that the gradient of a function $f$ has the same form.",
                  "Corollary 7.6 shows that the estimator is admissible under convex loss."):
            lines.insert(11, "> " + s)
        self.assertEqual(fv.check_example_block_scope(lines), [])

    def test_section_heading_inside_block_is_detected(self):
        lines = _clean_md()
        lines.insert(11, "> ### § Quasilinear Equations")
        out = fv.check_example_block_scope(lines)
        self.assertEqual(len(out), 1, out)
        self.assertIn("[SECTION]", out[0])

    def test_bold_heading_matching_real_section_is_detected(self):
        lines = _clean_md()
        lines.insert(2, "### § An Invariant Formula for the Exterior Derivative")
        lines.insert(12, "> **An invariant formula for the exterior derivative.** In addition to")
        out = fv.check_example_block_scope(lines)
        self.assertTrue(any("[SECTION]" in x for x in out), out)

    def test_cn_head_without_space_is_recognised(self):
        lines = [
            "# 第 9 章", "", "## § 含时向量场", "",
            "> **例9.50**：在 $\\mathbb{R}^n$ 上定义含时向量场 $V$ 为", "> ",
            "> $$", "> V(t,x) = x/t", "> $$", "> ",
            "> " + "原则上我们可能需要给 $u$ 加上一个常数以满足初值条件，" * 4,
            "", "---", "",
            "原则上我们可能需要给 $u$ 加上一个常数以满足初值条件，" * 4,
        ]
        out = fv.check_example_block_scope(lines)
        self.assertEqual(len(out), 1, out)
        self.assertIn("[DUP]", out[0])

    def test_math_fence_lines_are_ignored(self):
        lines = _clean_md()
        lines.extend(["", "$$", "V(t, x) = \\frac{1}{t} x^i", "$$"])
        self.assertEqual(fv.check_example_block_scope(lines), [])

    def test_tag_inside_example_is_not_itself_a_violation(self):
        lines = _clean_md()
        lines.insert(9, "> \\tag{9.20}")
        self.assertEqual(fv.check_example_block_scope(lines), [])


class ExampleScopeWiringTests(unittest.TestCase):

    def test_default_result_has_key(self):
        self.assertIn("ex_bq_scope", DEFAULT_RESULT)
        self.assertEqual(DEFAULT_RESULT["ex_bq_scope"], [])

    def test_flayer_emits_key(self):
        self.assertIn("ex_bq_scope", fv.FLayer.run.__code__.co_consts)

    def test_report_marks_chapter_fail(self):
        r = dict(DEFAULT_RESULT)
        r.update({"ch": 9, "md": "dummy.md", "status": "PASS",
                  "ex_bq_scope": ["  x L11: [DUP] Example blockquote swallowed following prose"]})
        buf = io.StringIO()
        old = sys.stdout
        sys.stdout = buf
        try:
            status = print_result(r)
        finally:
            sys.stdout = old
        text = buf.getvalue()
        self.assertEqual(status, "FAIL")
        self.assertIn("Example block scope", text)
        self.assertIn("[DUP]", text)


if __name__ == "__main__":
    unittest.main()
