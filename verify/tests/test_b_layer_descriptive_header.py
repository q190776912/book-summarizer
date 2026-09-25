"""Regression tests: 描述性条头不得被 B 层判为「缺号」（Gelfand–Manin 实测）。

背景：``_parse_entry`` 的 number-first 分支在余串里找到类型词后，要求类型词之后
必须是「条头边界」（``_after_label_boundary``）。印刷条头常是描述性短语：
  * 英文复数（**2.1-8 8. Remarks**）——``_ENTRY_LABELS`` 的交替式里单数在前
    （``Remark|Remarks``），"Remarks" 只匹配到 "Remark"，剩下的 's' 被当成词内
    延续 → 判为引用 → 真实条目被丢弃；
  * 英文专名延续（**2.1-4 4. Examples of Categories from Chapter I**）——类型词后
    直接跟拉丁单词，同样被边界检查丢弃；
  * 中文词干误命中（**1.4-7 7. 系数系统**、**1.4-9 9. 注记与例子**）——类型词后
    紧跟汉字被丢弃（其中 '系' 还会把「系数系统」读成 系/Porism）。
中文孪生条头（「8. 注记」）与英文孪生条头各自受害，所以同一本书两个语言版报的假
「缺号」数量还不一致（ch2 实测 EN 16 vs CN 6），且严格模式下全部 BLOCKING。

根治后行为（本文件锁定）：
  1. 复数类型词整词命中 → 条目在正确计数窗里出现。
  2. 类型词开头、后接专名 → 仍以该类型词入账（"Examples of Categories …"）。
  3. 类型词只是标题中间被引用的词或复合词的词干 → 归 uncat，仍是真实条目。
  4. 负向不变：引用/回指（"see the Remark below"、"定理 4.1 的应用"、"cf. Example 2"）、
     证明标题、类型词后紧跟另一串数字的路径仍不是条目。
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
    _parse_entry)


class TestEnDescriptiveHeader(unittest.TestCase):
    def test_plural_label_matches_whole_word(self):
        self.assertEqual(_parse_entry("2.1-8 8. Remarks", 3, "en"), ([2, 1, 8], "Remarks"))
        self.assertEqual(_parse_entry("2.1-5 5. More Examples", 3, "en"), ([2, 1, 5], "Examples"))
        self.assertEqual(_parse_entry("2.1-1 1. Definition.", 3, "en"), ([2, 1, 1], "Definition"))

    def test_label_led_descriptive_name_still_uses_its_type_word(self):
        got = _parse_entry("2.1-4 4. Examples of Categories from Chapter I", 3, "en")
        self.assertEqual(got, ([2, 1, 4], "Examples"))
        got = _parse_entry("2.1-11 11. Examples from Chapter I", 3, "en")
        self.assertEqual(got, ([2, 1, 11], "Examples"))

    def test_type_word_quoted_mid_title_falls_back_to_uncat(self):
        got = _parse_entry("2.1-9 9. More Examples of Functors", 3, "en")
        self.assertIsNotNone(got, "a real item must not be dropped")
        self.assertEqual(got[0], [2, 1, 9])
        self.assertEqual(got[1], "uncat")

    def test_cjk_descriptive_headers_unchanged(self):
        self.assertEqual(_parse_entry("2.1-8 8. 注记", 3, "cn"), ([2, 1, 8], "注记"))
        self.assertEqual(_parse_entry("2.1-12 12. 若干定义", 3, "cn"), ([2, 1, 12], "定义"))
        # 专名在类型词之前（「黎斯引理」）仍按类型词入账 —— 旧行为不得回退。
        self.assertEqual(_parse_entry("2.5-4 4. 黎斯引理", 3, "cn"), ([2, 5, 4], "引理"))

    def test_han_type_word_stem_inside_a_compound_is_uncat_not_dropped(self):
        # Gelfand-Manin ch1 §1.4 CN: '系' is 系/Porism, but 系数系统 / 带系数系统 uses
        # it as a word stem; '注记与例子' runs straight on.  None of them may vanish
        # from the window (that was 假「缺号 7 / 9 / 10」).
        for inner, comps in (("1.4-7 7. 系数系统 (coefficient systems)", [1, 4, 7]),
                             ("1.4-9 9. 注记与例子", [1, 4, 9]),
                             ("1.4-10 10. 带系数系统的同调与上同调", [1, 4, 10])):
            got = _parse_entry(inner, 3, "cn")
            self.assertIsNotNone(got, f"{inner!r} must count as an item")
            self.assertEqual(got[0], comps)
            self.assertNotIn(got[1], ("系", "注记", "例子"),
                             "a compound stem must not become the item's label")

    def test_cjk_punct_delimited_label_keeps_its_type_word(self):
        got = _parse_entry("1.5-2 2. 定义。a) 拓扑空间 $Y$ 上的集合值预层 (presheaf)", 3, "cn")
        self.assertEqual(got, ([1, 5, 2], "定义"))

    def test_references_are_still_not_entries(self):
        for inner, lang in (("2.1-8 见定理 4.1", "cn"),
                            ("3.5-2 定理 4.1 的应用", "cn"),
                            ("5.2-3 see the Remark below", "en"),
                            ("5.2-3 cf. Example 2", "en"),
                            ("4.1-2 Proof of Theorem 3.8", "en"),
                            ("2.5-4 证明", "cn")):
            self.assertIsNone(_parse_entry(inner, 3, lang), f"{inner!r} must not be an entry")


if __name__ == "__main__":
    unittest.main(verbosity=2)
