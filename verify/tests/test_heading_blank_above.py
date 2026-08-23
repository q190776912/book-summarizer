"""test_heading_blank_above.py — F-layer L-EXT2 rule: every ATX heading must
have a blank line directly above it (file start / code fences / $$ blocks
exempt).  Covers the detector (format_verify.check_heading_blank_above) and
the L fixer (fix_separator_spacing._fix_heading_blank_above, registered as
code 'L'), including idempotency and the legacy fix-dict key contract.

Run: python verify/tests/test_heading_blank_above.py
"""
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

import register_all  # noqa: F401  (triggers fixer registration)
from verify.format_verify.script.format_verify import check_heading_blank_above
from verify.format_verify.script.fix_separator_spacing import (
    _fix_heading_blank_above,
)
from verify.script.base import FIXERS


def _write_md(text):
    tf = tempfile.NamedTemporaryFile(
        "w", suffix=".md", delete=False, encoding="utf-8")
    tf.write(text)
    tf.close()
    return tf.name


class HeadingBlankAboveTest(unittest.TestCase):
    def test_flags_heading_after_list_item(self):
        # Real incident: Koopman ch12 — list item 10 directly followed by §12.5.
        p = _write_md("9. Get $B$.\n10. Set $u=k(z)$.\n## §12.5 Simulation Results\n")
        try:
            out = check_heading_blank_above(p)
            self.assertEqual(len(out), 1, out)
            self.assertIn("L3", out[0])
        finally:
            os.unlink(p)

    def test_flags_heading_after_paragraph(self):
        p = _write_md("text\n## §2.1 Title\n")
        try:
            self.assertEqual(len(check_heading_blank_above(p)), 1)
        finally:
            os.unlink(p)

    def test_flags_consecutive_headings(self):
        p = _write_md("# Ch\n## §1 A\n### §1.1 B\n")
        try:
            self.assertEqual(len(check_heading_blank_above(p)), 2)
        finally:
            os.unlink(p)

    def test_passes_blank_line_above(self):
        p = _write_md("10. Set $u$.\n\n## §12.5 Simulation Results\n")
        try:
            self.assertEqual(check_heading_blank_above(p), [])
        finally:
            os.unlink(p)

    def test_passes_file_start_heading(self):
        p = _write_md("# Chapter 1\n\ntext\n")
        try:
            self.assertEqual(check_heading_blank_above(p), [])
        finally:
            os.unlink(p)

    def test_ignores_code_fence_and_math_block(self):
        p = _write_md("```py\nx = 1\n## not a heading\n```\n$$\n## raw\n$$\n")
        try:
            self.assertEqual(check_heading_blank_above(p), [])
        finally:
            os.unlink(p)

    def test_fixer_inserts_and_is_idempotent(self):
        p = _write_md("10. Set $u$.\n## §12.5 Simulation Results\n\ntext\n")
        try:
            lines, n1 = _fix_heading_blank_above(
                Path(p).read_text(encoding="utf-8").split("\n"))
            self.assertEqual(n1, 1)
            lines2, n2 = _fix_heading_blank_above(lines)
            self.assertEqual((n2, lines2), (0, lines))
        finally:
            os.unlink(p)

    def test_registered_L_fixer_reports_legacy_key(self):
        self.assertIn("L", FIXERS)
        p = _write_md("10. Set $u$.\n## §12.5 Simulation Results\n")
        try:
            class _Ctx:
                md_file = p
            fr = FIXERS["L"][1](_Ctx())
            self.assertEqual(list(fr.fix_dict.keys()), ["l"])
            self.assertEqual(fr.fix_dict["l"], 1)
            fixed = Path(p).read_text(encoding="utf-8")
            self.assertIn("10. Set $u$.\n\n## §12.5", fixed)
        finally:
            os.unlink(p)


if __name__ == "__main__":
    unittest.main()
