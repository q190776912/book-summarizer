"""Regression test: P 层缺节检测支持破折号序标与章内字母节（do Carmo 实测，2026-09-26）。

形态：do Carmo《Differential Geometry of Curves and Surfaces》各章节号印刷为
`§1-2` / `§5-10`（dash 分隔），章末字母节契约键 `2-A`…`5-A`、md 标题只印
`## §Appendix: ...`。旧判据：
  - SEC_HEADING_RE / _GLOBAL_SEC_TOKEN_RE 只认点分 → `## §1-2` 被截成 `1`，
    整章假阳 p-layer-missing-sec（5 章 31 节中 25+ 假缺）；
  - 字母节 `2-A` 既不被捕获也无 Appendix 放行通道 → 每章再假报一条。

断言（正反两侧都要有）：
  1. dash 节全部在位 → 0 缺节；点分书旧行为零回归；
  2. 真缺 `## §5-9` 仍必须报（修复不得吞真缺）；
  3. `## §Appendix: ...` 满足契约 `5-A`；
  4. 无 § 的裸词标题（`## Summary`）不得被当作节号污染 present。
"""
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..")))
from lib import boot  # noqa: E402
boot.setup()

import verify.verbose_gates.script.verbose_gates as vg  # noqa: E402

CFG = types.SimpleNamespace(sections_unnumbered=False)


def _run(sections, md_lines, monkey):
    orig = vg._load_contract
    vg._load_contract = lambda ext, ch: (sections, set(), [])
    try:
        return vg.check_missing_sections(md_lines, ext_dir=None, ch=monkey, cfg=CFG)
    finally:
        vg._load_contract = orig


class TestDashedSections(unittest.TestCase):
    def test_dash_headings_satisfy_dash_contract(self):
        secs = [("5-1", "Introduction"), ("5-2", "Rigidity"), ("5-10", "Abstract")]
        lines = ["## §5-1 Introduction", "text",
                 "## §5-10 Abstract Surfaces; Further Generalizations", "text",
                 "## §5-2 The Rigidity of the Sphere"]
        out = _run(secs, lines, "5")
        self.assertEqual([s for s in secs if any(k.replace('-', '.') in ln for ln in out for k in [s[0]])], [])
        self.assertEqual(out, [], f"dash 节全在位却报缺: {out}")

    def test_missing_dash_section_still_flagged(self):
        secs = [("5-1", "Introduction"), ("5-9", "Jacobi")]
        lines = ["## §5-1 Introduction"]
        out = _run(secs, lines, "5")
        self.assertEqual(len(out), 1)
        self.assertIn("5-9", out[0])

    def test_appendix_heading_satisfies_letter_section(self):
        secs = [("5-11", "Hilbert"), ("5-A", "Appendix")]
        lines = ["## §5-11 Hilbert's Theorem",
                 "## §Appendix: Point-Set Topology of Euclidean Spaces"]
        out = _run(secs, lines, "5")
        self.assertEqual(out, [], f"字母节 Appendix 标题未被放行: {out}")

    def test_bare_word_heading_not_captured_as_section(self):
        secs = [("5-1", "Introduction")]
        lines = ["## Summary", "## Introduction to the Theory"]
        out = _run(secs, lines, "5")
        self.assertEqual(len(out), 1)
        self.assertIn("5-1", out[0])

    def test_dotted_style_regression(self):
        secs = [("3.2", "Def"), ("3.5", "More")]
        lines = ["## §3.2 Definition", "## §3.5 More Things"]
        self.assertEqual(_run(secs, lines, "3"), [])
        self.assertEqual(len(_run(secs, ["## §3.2 Definition"], "3")), 1)

    def test_norm_captures_letter_suffixed_dash_heading(self):
        m = vg.SEC_HEADING_RE.match("## §2-A The Appendix")
        self.assertIsNotNone(m)
        self.assertEqual(vg._norm_secnum(m.group(1)), "2.A")
        m = vg._GLOBAL_SEC_TOKEN_RE.match("## §5-10 Abstract")
        self.assertEqual(vg.norm_secnum(m.group(1)), "5.10")


if __name__ == "__main__":
    unittest.main(verbosity=2)
