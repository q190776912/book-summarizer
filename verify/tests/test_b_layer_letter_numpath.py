"""Regression tests: 字母型 numpath 不得让 B 层崩（Gelfand–Manin ch2 实测）。

背景：``_numpath_regexes`` 的数字路径模式带可选前导字母（附录式 "A3"），而
``_parse_entry`` 各分支过去直接 ``int(x)`` 转换捕获串。Gelfand–Manin《Methods of
Homological Algebra》ch2 条目 **2.5-2 2. Axiom A1** 里，「Axiom A1」是公理的**名字**，
label+numpath 回退分支捕获到 "A1" → ``int('A1')`` 抛 ValueError，整次 verify 直接中止
（fail-closed 变成 fail-crash，其余章全部拿不到报告）。

本文件锁定根治后的行为：
  1. ``_comps_of``：纯数字路径正常返回组件；含字母的路径返回 None（= 不是条目路径）。
  2. ``_parse_entry`` 对「Axiom A1」形态的条头**不抛异常**，且若仍解析成功，comps 必须是 int 列表。
  3. 真实条目路径解析行为不变（number-first / label-first 正常）。
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, _ROOT)
from lib.boot import setup  # noqa: E402
setup()

from verify.item_numbering_integrity.script.item_numbering_integrity import (  # noqa: E402
    _comps_of, _parse_entry, _split_numpath)


class TestCompsOf(unittest.TestCase):
    def test_pure_digits_ok(self):
        self.assertEqual(_comps_of("2.5-2"), [2, 5, 2])
        self.assertEqual(_comps_of("12"), [12])

    def test_letter_path_is_not_an_entry(self):
        # The crasher: appendix-style "A1" is matched by the capture pattern
        # but is not a consumable item path.
        self.assertIsNone(_comps_of("A1"))
        self.assertIsNone(_comps_of("A.3"))

    def test_split_numpath_agrees(self):
        self.assertIsNone(_split_numpath("A1", 3))
        self.assertEqual(_split_numpath("2.5-2", 3), [2, 5, 2])


class TestParseEntryLetterNumpath(unittest.TestCase):
    def test_axiom_named_A1_does_not_raise(self):
        # Gelfand-Manin ch2 unit 0015's real bold header.
        inner = "2.5-2 2. Axiom A1"
        try:
            got = _parse_entry(inner, 3, "en")
        except ValueError as e:                       # <- the old failure mode
            self.fail(f"_parse_entry raised ValueError on letter numpath: {e}")
        if got is not None:
            comps, label = got
            self.assertTrue(all(isinstance(c, int) for c in comps), comps)

    def test_label_first_letter_numpath_rejected(self):
        for inner in ("Axiom A1", "Theorem A3", "公理 A2"):
            try:
                got = _parse_entry(inner, 3, "en")
            except ValueError as e:
                self.fail(f"_parse_entry({inner!r}) raised ValueError: {e}")
            self.assertIsNone(got, f"{inner!r} must not parse as an item path")

    def test_real_entries_still_parse(self):
        self.assertEqual(_parse_entry("2.5-2 2. Axiom", 3, "en"), ([2, 5, 2], "Axiom"))
        # levels drives the component count: a 2-component path is only an
        # entry for a 2-level numbering (3-level books reject it by design).
        self.assertIsNone(_parse_entry("Theorem 3.1", 3, "en"))
        self.assertEqual(_parse_entry("Theorem 3.1", 2, "en"), ([3, 1], "Theorem"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
