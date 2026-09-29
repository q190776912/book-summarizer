# -*- coding: utf-8 -*-
"""Regression: **无编号附录**的 H1 与最终 md 文件名不得从「标题首词」猜序标。

Shafarevich《Basic Algebraic Geometry 1》附录印刷标题就是裸的 ``Algebraic Appendix``
（无 ``Appendix A``／无数字序标）。按 SKILL.md 附录命名总则，chapter_map 该章键须写
``appendix``（kind=2），序标归空 → ``appendix.json`` / ``units/appendix/`` /
``Appendix.md`` / ``附录.md``。但本书实测（2026-09-29）：

* ``render_draft._chapter_heading`` 与 ``merge_units._final_md_name`` 都先拿
  ``_CH_NAME`` 扫**契约名**的第一个词，把 ``Algebraic`` 当成了序标——
  H1 产出 ``# Appendix Algebraic: Appendix``，文件名产出 ``AppendixAlgebraic_Appendix.md``。
  旧书未暴露，是因为已收官的裸名附录（Serre「Appendix: Artinian rings」、周民强「附录」）
  标题首词带冒号或为 CJK，正则恰好不匹配。

根治 = 两函数先问 SSOT ``chapter_ordinal(ch_key)``：序标为空即裸名，标题逐字用、
文件名不拼 slug；数字章／字母附录／补篇的旧形态逐字保持（负向断言在下方）。

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_bare_appendix_heading_and_md_name.py
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
sys.path.insert(0, str(Path(_ROOT) / "flows" / "write-source" / "script"))

from merge_units import _final_md_name  # noqa: E402
from render_draft import _chapter_heading  # noqa: E402


class TestHeading(unittest.TestCase):
    def test_bare_appendix_heading_uses_printed_title(self):
        node = {"key": "appendix", "type": "chapter", "name": "Algebraic Appendix"}
        self.assertEqual(_chapter_heading(node, "en"), "# Algebraic Appendix")

    def test_bare_appendix_heading_cn_bare_word(self):
        node = {"key": "appendix", "type": "chapter", "name": "附录"}
        self.assertEqual(_chapter_heading(node, "cn"), "# 附录")

    def test_bare_supplement_heading_not_mangled(self):
        node = {"key": "supplement", "type": "chapter", "name": "Dynamical Systems",
                "kind": 3}
        self.assertEqual(_chapter_heading(node, "en"), "# Dynamical Systems")

    # ---- 负向：有印刷序标的章，旧形态逐字保持 ----
    def test_numbered_chapter_heading_unchanged(self):
        node = {"key": "5", "type": "chapter", "name": "5 Algebraic Appendix"}
        self.assertEqual(_chapter_heading(node, "en"), "# Chapter 5: Algebraic Appendix")
        self.assertEqual(_chapter_heading(node, "cn"), "# 第5章 Algebraic Appendix")

    def test_letter_appendix_heading_unchanged(self):
        node = {"key": "A", "type": "chapter", "name": "A Hints", "kind": 2}
        self.assertEqual(_chapter_heading(node, "en"), "# Appendix A: Hints")


class TestFinalMdName(unittest.TestCase):
    def test_bare_appendix_md_name_is_bare(self):
        self.assertEqual(_final_md_name("appendix", "en", "Algebraic Appendix"),
                         "Appendix.md")
        self.assertEqual(_final_md_name("appendix", "cn", "附录"), "附录.md")

    # ---- 负向 ----
    def test_numbered_chapter_md_name_unchanged(self):
        self.assertEqual(_final_md_name("5", "en", "5 Further Applications"),
                         "Chapter5_Further_Applications.md")

    def test_letter_appendix_md_name_unchanged(self):
        self.assertEqual(_final_md_name("A", "en", "附录A 提示"), "AppendixA.md")
        self.assertEqual(_final_md_name("A", "en", "A Hints"), "AppendixA_Hints.md")


if __name__ == "__main__":
    unittest.main(verbosity=2)
