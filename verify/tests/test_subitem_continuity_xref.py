"""
test_subitem_continuity_xref.py — O 层行内回指守卫回归（Leinster BCT 2.2.12 实测）。

背景：`(b) An adjunction satisfying the equivalent conditions of part (a) is
called a reflection. (Compare Example 2.1.3(d).)` 一行里 `part (a)` 与
`2.1.3(d)` 都是行文回指，不是子项序号；旧 finditer 全行捕获把它们拼成幻影
序列 (a, b, d) → 假报 INTERNAL gap missing (c)。修复 = _o_is_seq_marker：
紧贴字母/数字的附着回指一律不算；其余要求前为句读分隔或后随大写/中文/数字。
同时真内联序列 `(1) a；(2) b` 与 `(a) X. (b) Y.` 必须仍然全部捕获。
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

from subitem_continuity import _o_match_line, check_ordinal_subitem_gaps


class XrefGuardTest(unittest.TestCase):
    def test_prose_backrefs_dropped(self):
        line = ("(b) An adjunction satisfying the equivalent conditions of "
                "part (a) is called a reflection. (Compare Example 2.1.3(d).) "
                "Of the examples of adjunctions given in this chapter, which "
                "are reflections?")
        self.assertEqual(_o_match_line(line), ['b'])

    def test_inline_numeric_sequence_kept(self):
        line = "(1) 定义映射；(2) 证明单射；(3) 证明满射。"
        self.assertEqual(_o_match_line(line), ['1', '2', '3'])

    def test_inline_alpha_period_separated_kept(self):
        line = "(a) Show injectivity. (b) Show surjectivity. (c) Conclude."
        self.assertEqual(_o_match_line(line), ['a', 'b', 'c'])

    def test_cn_paren_backref_dropped(self):
        line = "（b）结合（a）与命题 2.1.3（d）即可完成。"
        self.assertEqual(_o_match_line(line), ['b'])

    def test_end_to_end_book_case_no_gap(self):
        md = ("# Chapter 2\n\n"
              "**2.2.12**: (a) Show that for any adjunction, the right adjoint "
              "is full and faithful if and only if the counit is an isomorphism.\n\n"
              "(b) An adjunction satisfying the equivalent conditions of part (a) "
              "is called a reflection. (Compare Example 2.1.3(d).) Of the examples "
              "of adjunctions given in this chapter, which are reflections?\n")
        d = tempfile.mkdtemp()
        p = os.path.join(d, 'ch2.md')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(md)
        self.assertEqual(check_ordinal_subitem_gaps(p), [])


if __name__ == '__main__':
    unittest.main()
