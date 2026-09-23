"""
test_item_numbering_integrity_label_recovery.py

Regression test for the v2 B-layer label-recovery fix.

BACKGROUND (Koopman per-type regression under the v2 config schema)
---------------------------------------------------------------------
v2 groups B-layer counters by `gi:prefix` where `gi` is the group index.
For *per-type* groups (each label in its OWN GroupConfig, e.g. a dedicated
"Theorem" group, scope=chapter, depth=2) the human-readable label is carried
by the group index `gi` and is NOT part of the grouping key.  When emitting a
缺号 (missing-number) token the label must therefore be re-derived from `gi`
so that a config `ignore` / `known_gaps` entry written as "Theorem 12.3" can
match the emitted token.

Before the fix the emit token was a bare "12-3" (label dropped), which never
matched an ignore entry "Theorem 12.3" -> confirmed-sparse numbers produced a
FALSE BLOCK (a regression vs the old `separate_types:1` mode that emitted the
label-bearing token).

This test builds a per-type config, lists Theorem 12.3 / 12.4 as confirmed
sparse in `ignore`, and asserts they are NOT flagged, while a genuinely missing
Theorem 12.7 (not in ignore) IS still flagged.  Without the fix the test fails
because 12.3 / 12.4 would be falsely BLOCKed.

Run (stdlib unittest, no pytest dependency):
    python verify/tests/test_item_numbering_integrity_label_recovery.py
"""
import os
import sys
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

import os
import sys
import tempfile
import unittest


from verify_config import BookConfig, GroupConfig
from item_numbering_integrity import _md_gap_blocking
from verify.script.base import VerifyContext


def _ctx_with_md(md_text, config):
    """Build a VerifyContext pointing at a temp .md file containing `md_text`."""
    d = tempfile.mkdtemp()
    md_path = os.path.join(d, 'chapter12.md')
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(md_text)
    # ext_dir / ch / start / end are unused by _md_gap_blocking (it only reads
    # ctx.config, ctx.ignore, ctx.md_file); they are set to valid placeholders.
    return VerifyContext(
        ch=12, start=12, end=12,
        md_file=md_path, ext_dir=d, config=config,
    )


class ItemNumberingIntegrityLabelRecoveryTest(unittest.TestCase):
    # Chapter 12: Theorem 12.2, 12.5, 12.6, 12.8 present; 12.3/12.4 missing
    # (confirmed sparse) and 12.7 missing (real gap).  Definitions 12.1-12.4
    # present and complete (fill the merged counter so only Theorem gaps show).
    MD = (
        "# Chapter 12\n\n"
        "**Theorem 12.2.** statement two.\n\n"
        "**Definition 12.1.** d1.\n\n"
        "**Definition 12.2.** d2.\n\n"
        "**Definition 12.3.** d3.\n\n"
        "**Definition 12.4.** d4.\n\n"
        "**Theorem 12.5.** statement five.\n\n"
        "**Theorem 12.6.** statement six.\n\n"
        "**Theorem 12.8.** statement eight.\n\n"
    )

    def _per_type_cfg(self, ignore):
        """Per-type groups: dedicated Theorem group + dedicated Definition group,
        both scope=chapter / depth=2 (mirrors the Koopman v2 config shape)."""
        return BookConfig(
            ordinal=[
                GroupConfig(type=2, name=['Theorem'], scope=2),
                GroupConfig(type=2, name=['Definition'], scope=2),
            ],
            ignore=list(ignore),
        )

    def test_ignored_theorem_gaps_suppressed_after_fix(self):
        """Theorem 12.3 / 12.4 are in `ignore` -> must NOT produce a BLOCK.

        The emitted token for a per-type group is "gi:prefix 缺号 N" (e.g.
        "0:12 缺号 3"); the label "Theorem" is recovered from `gi` so the
        ignore entry "Theorem 12.3" matches.  Without the fix the token is a
        bare "0:12 缺号 3" that never matches -> this assertion fails.
        """
        cfg = self._per_type_cfg(['Theorem 12.3', 'Theorem 12.4'])
        ctx = _ctx_with_md(self.MD, cfg)
        blocking, _warnings, _present, _tail, _groups = _md_gap_blocking(ctx)
        blocking_text = '\n'.join(blocking)
        self.assertNotIn(
            '缺号 3', blocking_text,
            'Theorem 12.3 is registered as sparse in ignore -> must NOT block')
        self.assertNotIn(
            '缺号 4', blocking_text,
            'Theorem 12.4 is registered as sparse in ignore -> must NOT block')

    def test_real_theorem_gap_still_flagged(self):
        """Theorem 12.7 is genuinely missing and NOT ignored -> must still block.

        Guards against the fix over-suppressing: a real gap outside `ignore`
        must still be reported.
        """
        cfg = self._per_type_cfg(['Theorem 12.3', 'Theorem 12.4'])
        ctx = _ctx_with_md(self.MD, cfg)
        blocking, _warnings, _present, _tail, _groups = _md_gap_blocking(ctx)
        blocking_text = '\n'.join(blocking)
        self.assertIn(
            '缺号 7', blocking_text,
            'Theorem 12.7 is a real gap (not in ignore) -> must still block')


class CnWarningNotationLabelTest(unittest.TestCase):
    """Leinster BCT 实测（2026-09-23）：书里 Warning/Notation 条目在 CN 版写作
    **警告1.2.17（…）** / **记号4.3.1**。EN 词表早有 Warning|Notation，CN 侧
    _ENTRY_LABELS 漏收 警告/记号/术语 → CN md 该条解析不出，B 层假报「缺号」
    （EN 过、CN 挂）。修复=CN 词表补齐 + _LABEL_NORM 配对恒等映射。"""

    def _parse(self, inner, levels=3):
        from item_numbering_integrity import _parse_entry
        return _parse_entry(inner, levels)

    def test_cn_warning_parsed(self):
        got = self._parse('警告1.2.17（注意 $A$ 与 $A^{\\prime}$ 在定义中的角色）')
        self.assertIsNotNone(got, 'CN 警告 条目必须被解析为条目')
        self.assertEqual(got[0], [1, 2, 17])

    def test_cn_notation_parsed(self):
        got = self._parse('记号4.3.1')
        self.assertIsNotNone(got, 'CN 记号 条目必须被解析为条目')
        self.assertEqual(got[0], [4, 3, 1])

    def test_cn_terminology_parsed(self):
        got = self._parse('术语6.1.1')
        self.assertIsNotNone(got, 'CN 术语 条目必须被解析为条目')
        self.assertEqual(got[0], [6, 1, 1])

    def test_label_norm_pairs_en_canon(self):
        from item_numbering_integrity import _LABEL_NORM
        self.assertEqual(_LABEL_NORM.get('警告'), 'Warning')
        self.assertEqual(_LABEL_NORM.get('记号'), 'Notation')
        self.assertEqual(_LABEL_NORM.get('术语'), 'Terminology')

    def test_control_definition_still_parsed(self):
        got = self._parse('定义1.2.16（忠实 (faithful) 与满 (full)）')
        self.assertIsNotNone(got)
        self.assertEqual(got[0], [1, 2, 16])


if __name__ == '__main__':
    unittest.main()
