# -*- coding: utf-8 -*-
"""Regression: chapter-scoped-counter books must not bind `Problem C.N`
exercises to the numerically-coinciding section (Etingof《群表示论》ch3/4/5,
2026-09-27).

The book prints ONE per-chapter counter shared by theorems/definitions/problems
("Problem 3.4" sits inside §3.2 on p33, while the real §3.4 starts on p35).
`_section_of_exer` derived §3.4 from the exercise number, so the exercise node
was attached to that section and `page_start = min(子项页)` dragged the section
anchor back to p33 — build_structure then refused the whole chapter with
"ANCHOR-SANITY FAIL | 小节 §3.4（原书 p33）的小节号晚于 §3.3（原书 p34）"
(7 occurrences across ch3/ch4/ch5).

Fix under test: `_section_of_exer(..., chapter_scoped=True)` returns None for a
plain two-component `C.N` key so the exercise falls back to page-nearest
placement — the same semantics `_section_of_key` already implements for
`chapter_scoped_items` books. Zero regression: without the flag (and for
appendix letter / three-component keys) the derivation is unchanged.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_chapter_scoped_exer_section.py
"""
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
from lib import boot  # noqa: E402
boot.setup()

from build_structure import _section_of_exer  # noqa: E402


class TestChapterScopedExerSection(unittest.TestCase):
    def test_two_component_key_suppressed_when_chapter_scoped(self):
        # 负向（bug 本体）：章内计数器书的 "3.4" 不得派生 §3.4
        self.assertIsNone(_section_of_exer("3.4", chapter_scoped=True))
        self.assertIsNone(_section_of_exer("5.5", chapter_scoped=True))

    def test_two_component_key_kept_without_flag(self):
        # 零回归：默认（节基编号书）仍按「章.节」派生
        self.assertEqual(_section_of_exer("3.4"), "3.4")
        self.assertEqual(_section_of_exer("3.4", chapter_local_numbering=True), "4")

    def test_letter_prefix_and_three_component_unaffected(self):
        # 附录字母章位（Weibel）与三级键（Vakil 1.2.A）不受旗标影响
        self.assertEqual(_section_of_exer("A.4-1", chapter_scoped=True), "A.4")
        self.assertEqual(_section_of_exer("1.2.A", chapter_scoped=True), "1.2")

    def test_single_component_key_stays_underived(self):
        self.assertIsNone(_section_of_exer("12", chapter_scoped=True))
        self.assertIsNone(_section_of_exer("12"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
