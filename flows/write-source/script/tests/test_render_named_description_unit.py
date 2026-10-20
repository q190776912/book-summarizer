# -*- coding: utf-8 -*-
"""Regression: a printed **unnumbered section-tail heading** (`Summary`, …) must
survive contract → unit → gate as a *titled* description node
(Lehmann, Elements of Large-Sample Theory, rooting Task #20, 2026-10-20).

Upstream (`attach_content`) registers the standalone heading word into the
description node's `name` (see
`flows/write-source/structure/script/tests/test_standalone_tail_head_registration.py`
for the predicate itself).  This file covers the two downstream layers that the
rooting is only complete once both agree:

  * `render_draft._emit_desc_node` / `split_draft_units._render_desc` — an unnamed
    node still renders as a bare paragraph (original behaviour, every other book),
    a named node emits a standalone bold title line *before* the summary prose;
  * `check_unit_quality.check_body` — that contract-sourced bold line must not be
    mistaken for an agent-invented heading (gate #11c 「单元内私造标题行」) nor for a
    numbered item label (gate #23 三级序标须契约键).

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_render_named_description_unit.py
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot as _boot  # noqa: E402
_boot.setup()

import check_unit_quality as cu  # noqa: E402
import render_draft as rd  # noqa: E402


def _desc(name, prose=("1. The MLE is asymptotically normal.",
                       "2. Its risk attains the lower bound.")):
    # 内容块形如 attach_content._to_content 的输出：text 块只有 `text` +
    # `line_start`（🔴 没有 `type` 键，加了会被 _walk_mixed 当成结构节点）
    return {"type": "description", "key": "D7", "name": name,
            "page_start": 100, "page_end": 100,
            "sub_sec": [{"text": p, "line_start": True} for p in prose]}


def _render(node):
    out = []
    rd._emit_desc_node(node, out, False, "en")
    return out


class TestRenderNamedDescription(unittest.TestCase):
    def test_named_node_emits_standalone_title_line(self):
        lines = _render(_desc("Summary"))
        self.assertIn("**Summary**", lines, lines)
        # 标题行必须在小结正文之前
        first_prose = next(i for i, l in enumerate(lines) if "MLE" in l)
        self.assertLess(lines.index("**Summary**"), first_prose)

    def test_title_word_is_not_left_as_a_bare_paragraph(self):
        # 旧行为（未登记 name）= 正文里一句光秃秃的 `Summary` 段落
        lines = _render(_desc("Summary"))
        self.assertFalse([l for l in lines if l.strip() == "Summary"], lines)

    def test_unnamed_node_is_unchanged_bare_prose(self):
        lines = _render(_desc(""))
        self.assertNotIn("**", "".join(lines))
        self.assertTrue(any("MLE" in l for l in lines), lines)

    def test_run_in_heading_is_not_promoted(self):
        # `**Summary.** 正文同句` = 标题词与正文同块，不属本形态（渲染器不加行）
        node = _desc("", prose=("Summary. The MLE is asymptotically normal."))
        self.assertNotIn("**Summary**", _render(node))


class TestGateDoesNotFlagContractTitle(unittest.TestCase):
    def test_bold_tail_title_is_not_a_private_heading_or_ordinal_label(self):
        body = "\n".join(_render(_desc("Summary")))
        _ok, problems = cu.check_body("desc", "", body)
        joined = "\n".join(problems)
        self.assertNotIn("私造标题", joined, problems)
        self.assertNotIn("单元内出现标题行", joined, problems)
        self.assertNotIn("三级序标", joined, problems)

    def test_markdown_heading_inside_unit_is_still_caught(self):
        # 反向确认 #11c 没被放宽：真·私造 `##` 标题行照报
        body = "## §3.6 Exterior differentiation\n\nsome prose."
        _ok, problems = cu.check_body("desc", "", body)
        self.assertTrue(any("单元内出现标题行" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main(verbosity=2)
