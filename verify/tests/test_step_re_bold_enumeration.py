"""Regression tests for verbose_gates.STEP_RE / check_verbose_proofs enumeration
exemption.  2026-09-26 Kreyszig ch1 incident: Theorem 1.6-2's proof is printed in
four steps (a)-(d) and was faithfully laid out as `> **(a) Construction ...**`
blockquote steps with all display math kept, yet the old STEP_RE (bare `(a) `
only) saw it as "未分条" and flagged a >700-char proof block as a translated
wall.  Bold/italic and list markers before the step label must be tolerated;
genuine undivided prose walls must still be reported."""
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "verify", "verbose_gates", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from verbose_gates import STEP_RE, check_verbose_proofs  # noqa: E402

_FILLER = ("The construction proceeds by assigning limits to Cauchy sequences "
           "and checking every metric axiom carefully so that the claim holds. ")


class TestStepReBoldLabels(unittest.TestCase):
    def test_bold_paren_letter_step_matches(self):
        self.assertTrue(STEP_RE.match("**(a) Construction of $\\hat X$.**"))

    def test_bold_paren_number_step_matches(self):
        self.assertTrue(STEP_RE.match("**（1）定义等价关系**"))

    def test_list_marker_numbered_step_matches(self):
        self.assertTrue(STEP_RE.match("- 3. Uniqueness follows"))

    def test_bare_step_still_matches(self):
        self.assertTrue(STEP_RE.match("(b) Construction"))
        self.assertTrue(STEP_RE.match("1. Construct the sequence"))

    def test_prose_starting_with_paren_word_not_matched(self):
        # `(a)` 必须紧跟空白/粗体标记才是步标号；普通行文 `(a b)` 不算
        self.assertFalse(STEP_RE.match("here (ab ove) we saw"))


class TestCheckVerboseProofsExemption(unittest.TestCase):
    def _proof(self, step_fmts):
        lines = ["> **Proof.**"]
        for fmt in step_fmts:
            lines.append(">")
            lines.append(fmt)
            lines.append(">")
            lines.append("> " + _FILLER * 7)
        return lines

    def test_bold_lettered_steps_exempted(self):
        lines = self._proof([
            "> **(a) Construction of $\\hat{X}$**",
            "> **(b) Construction of an isometry $T$**",
            "> **(c) Completeness of $\\hat{X}$**",
            "> **(d) Uniqueness**",
        ])
        self.assertEqual(check_verbose_proofs(lines), [])

    def test_plain_prose_wall_still_reported(self):
        lines = ["> **Proof.** " + _FILLER * 30]
        out = check_verbose_proofs(lines)
        self.assertEqual(len(out), 1)
        self.assertIn("未分条", out[0])

    def test_single_step_marker_not_enough(self):
        # 豁免需要 ≥2 个步标号；只有一个不算已分条
        lines = self._proof(["> **(a) Construction**"])
        out = check_verbose_proofs(lines)
        self.assertEqual(len(out), 1)


if __name__ == "__main__":
    unittest.main()
