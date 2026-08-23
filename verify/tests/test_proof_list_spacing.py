"""test_proof_list_spacing.py — F-layer K rule (generalized): a list's last
item must be separated by a blank line from a following NEW block
(blockquote / `$$` / top-level `**label**` / `<div`), at any list
indentation.  Subordinate indented content, subsequent list items, headings
and plain wrapped prose are exempt.

Covers the detector (format_verify.check_proof_after_list) and the K fixer
(fix_proof_list_spacing.fix_proof_after_list, registered as code 'K'),
including idempotency, the legacy 4-space-indented case, and the legacy
fix-dict key contract.

Run: python verify/tests/test_proof_list_spacing.py
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
from verify.format_verify.script.format_verify import check_proof_after_list
from verify.format_verify.script.fix_proof_list_spacing import (
    fix_proof_after_list,
)
from verify.script.base import FIXERS


def _write_md(text):
    tf = tempfile.NamedTemporaryFile(
        "w", suffix=".md", delete=False, encoding="utf-8")
    tf.write(text)
    tf.close()
    return tf.name


class ProofListSpacingTest(unittest.TestCase):
    def test_flags_top_level_list_then_proof(self):
        # Real incident: Koopman ch12 Theorem 12.2 — item `2.` then proof.
        p = _write_md("2. For each $x$, condition two holds.\n"
                      "> **Proof sketch**: Condition (2) is the SCP.\n")
        try:
            out = check_proof_after_list(p)
            self.assertEqual(len(out), 1, out)
            self.assertIn("L2", out[0])
        finally:
            os.unlink(p)

    def test_flags_legacy_indented_case(self):
        p = _write_md("**定义 1.1**\n    (1) 第一条。\n    (2) 第二条。\n"
                      "> **证明** 内容。\n")
        try:
            self.assertEqual(len(check_proof_after_list(p)), 1)
        finally:
            os.unlink(p)

    def test_flags_math_label_and_figure_followers(self):
        for follower in ("$$\nx=1\n$$", "**Theorem 2.1** Text.\n",
                         '<div style="display:flex">\n'):
            p = _write_md("1. item\n" + follower)
            try:
                self.assertEqual(len(check_proof_after_list(p)), 1,
                                 repr(follower))
            finally:
                os.unlink(p)

    def test_passes_blank_line_between(self):
        p = _write_md("2. item two\n\n> **Proof sketch**: ok.\n")
        try:
            self.assertEqual(check_proof_after_list(p), [])
        finally:
            os.unlink(p)

    def test_passes_next_item_subordinate_heading_prose(self):
        md = ("1. first\n2. second\n"          # next item — no flag
              "3. third\n    sub line\n"       # subordinate indent — no flag
              "4. fourth\n## §1.1 Head\n"      # heading owned by other rule
              "5. fifth\nwrapped prose line\n")  # lazy continuation — no flag
        p = _write_md(md)
        try:
            self.assertEqual(check_proof_after_list(p), [])
        finally:
            os.unlink(p)

    def test_bullet_marker_also_flagged(self):
        p = _write_md("- alpha\n- beta\n> **Note** tail.\n")
        try:
            self.assertEqual(len(check_proof_after_list(p)), 1)
        finally:
            os.unlink(p)

    def test_emphasis_star_is_not_a_bullet(self):
        # `*Data*:` has no whitespace after the marker char → not a list.
        p = _write_md("*Data*: some series.\n*Result*: feedback $u$.\n")
        try:
            self.assertEqual(check_proof_after_list(p), [])
        finally:
            os.unlink(p)

    def test_fixer_inserts_idempotently_under_legacy_key(self):
        p = _write_md("2. item two\n> **Proof sketch**: SCP.\n\ntext\n")
        try:
            n1 = fix_proof_after_list(p)
            self.assertEqual(n1, 1)
            fixed = Path(p).read_text(encoding="utf-8")
            self.assertIn("2. item two\n\n> **Proof sketch**", fixed)
            self.assertEqual(fix_proof_after_list(p), 0)  # idempotent

            class _Ctx:
                md_file = _write_md("1. item\n> **Proof** x.\n")
            try:
                fr = FIXERS["K"][1](_Ctx())
                self.assertEqual(list(fr.fix_dict.keys()), ["k"])
                self.assertEqual(fr.fix_dict["k"], 1)
            finally:
                os.unlink(_Ctx.md_file)
        finally:
            os.unlink(p)


if __name__ == "__main__":
    unittest.main()
