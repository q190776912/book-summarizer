"""回归：**数字键登记的附录章**最终 md 组解析（Rosen《Discrete Mathematics》8e 实测，
2026-09-26，merge_source 证据复核假报「3 组最终 md 缺失」根治）。

原判据用 `key[:1].isdigit()` 当作「这是数字章」，于是章键 14/15/16（chapter_map 的
name 含 "Appendix" → kind=2，产物一律叫 `appendix14.json` / `units/appendix14/` /
`Appendix14_Appendix_A_….md`）被去找 `Chapter14_*.md`——**md 明明已经拼好**，
`merge_source` 却拒绝落账，且报错文案自相矛盾（点名 appendix14 却判它缺文件）。

根治 = 章型判据收进 `is_numbered_chapter()`（走 chapter_map 的 kind 注册表），
`_flow_contract._md_group` / `_md_group_lang` 与 `build_structure` 的 md 名猜测同用。

负向（必须仍然成立，否则修复无意义）：
* 真数字章（kind=1）仍解析成 `Chapter{N}_*`，**不**碰 `Appendix{N}_*`；
* 字母键附录（`appendixA` 形态，键首非数字）路径零回归；
* 无编号附录（键 == 前缀词本身 → 序标空）回退裸名 `Appendix.md` / `附录.md`。
"""
import json
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
    _ROOT = str(Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

from data.book_structure.book_structure import (  # noqa: E402
    chapter_json_name, is_numbered_chapter, prime_chapter_kinds, unit_dir_name)
from flows._flow_contract import physical_evidence  # noqa: E402


class _Primed(unittest.TestCase):
    """按 chapter_map 灌注 kind 后测判据（进程级注册表，setUp 里显式重置）。"""

    def _prime(self, entries):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "chapter_map.json"), "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False)
        prime_chapter_kinds(d)
        self.addCleanup(lambda: __import__('shutil').rmtree(d, ignore_errors=True))
        return d


class NumericKeyAppendixTest(_Primed):
    def test_numeric_key_with_appendix_name_is_not_a_chapter(self):
        self._prime({"1": {"name": "The Foundations", "start": 1, "end": 40},
                     "14": {"name": "Appendix A Axioms for the Real Numbers",
                            "start": 966, "end": 971}})
        self.assertTrue(is_numbered_chapter("1"))
        self.assertFalse(is_numbered_chapter("14"))
        # 命名三兄弟全部随 kind 走 appendix*，与 unit 目录 / 契约文件名同源
        self.assertEqual(chapter_json_name("14"), "appendix14.json")
        self.assertEqual(unit_dir_name("14"), "appendix14")

    def test_md_group_finds_appendix_file_not_chapter(self):
        self._prime({"14": {"name": "Appendix A Axioms for the Real Numbers"}})
        book = tempfile.mkdtemp()
        en = os.path.join(book, "Appendix14_Appendix_A_Axioms.md")
        zh = os.path.join(book, "附录14_公理.md")
        for p in (en, zh):
            with open(p, "w", encoding="utf-8") as f:
                f.write("# Appendix A\n")
        self.addCleanup(lambda: __import__('shutil').rmtree(book, ignore_errors=True))
        self.assertEqual(physical_evidence._md_group_lang(book, "14", "en"), [en])
        self.assertEqual(physical_evidence._md_group_lang(book, "14", "cn"), [zh])
        self.assertCountEqual(physical_evidence._md_group(book, "14"), [zh, en])

    def test_unnumbered_appendix_falls_back_to_bare_name(self):
        self._prime({"appendix": {"name": "附录", "kind": 2}})
        book = tempfile.mkdtemp()
        en = os.path.join(book, "Appendix.md")
        with open(en, "w", encoding="utf-8") as f:
            f.write("# 附录\n")
        self.addCleanup(lambda: __import__('shutil').rmtree(book, ignore_errors=True))
        self.assertEqual(is_numbered_chapter("appendix"), False)
        self.assertEqual(physical_evidence._md_group_lang(book, "appendix", "en"), [en])


class RealChapterStillChapterTest(_Primed):
    """负向：数字键的真章不得被改判成附录（否则全书 13 章的 md 组全部解析不到）。"""

    def test_numbered_chapter_keeps_chapter_pattern(self):
        self._prime({"1": {"name": "The Foundations", "start": 1, "end": 40},
                     "14": {"name": "Appendix A Axioms"}})
        book = tempfile.mkdtemp()
        ch = os.path.join(book, "Chapter1_1.1_PropositionalLogic.md")
        apx = os.path.join(book, "Appendix14_Appendix_A_Axioms.md")
        for p in (ch, apx):
            with open(p, "w", encoding="utf-8") as f:
                f.write("## §1.1 Logic\n")
        self.addCleanup(lambda: __import__('shutil').rmtree(book, ignore_errors=True))
        self.assertEqual(physical_evidence._md_group_lang(book, "1", "en"), [ch])
        self.assertNotIn(apx, physical_evidence._md_group(book, "1"))


class LetterKeyAppendixTest(_Primed):
    """零回归：键本身就是字母位（appendixA 体例）的附录。"""

    def test_letter_key_appendix(self):
        self._prime({"A": {"name": "Appendix A", "kind": 2}})
        book = tempfile.mkdtemp()
        p = os.path.join(book, "AppendixA_Categories.md")
        with open(p, "w", encoding="utf-8") as f:
            f.write("# Appendix A\n")
        self.addCleanup(lambda: __import__('shutil').rmtree(book, ignore_errors=True))
        self.assertEqual(physical_evidence._md_group_lang(book, "A", "en"), [p])


class ContractLabelVocabularyTest(_Primed):
    """同一条闸的第二个假报成因：中英标签词表缺词（Rosen 8e `算法N` → `Algorithm N`）。

    `_missing_contract_names` 靠 `_label_variants` 把中文 key 翻成英文标签再去 md 里找；
    词表缺 `算法` 时，8 章的 merge_source 证据被「契约项不在位」硬拒，而条目其实逐字在
    md 里。负向：契约里有、md 里真没有的项**必须**仍然报缺。
    """

    def _contract(self, key, name):
        return {"key": "3", "type": "chapter", "name": "Algorithms",
                "sub_sec": [{"key": key, "type": "algorithm", "name": name,
                             "page_start": 90, "page_end": 95, "sub_sec": []}]}

    def test_algorithm_key_found_via_english_label(self):
        miss = physical_evidence._missing_contract_names(
            self._contract("算法1", "算法1 ALGORITHM1"),
            physical_evidence._norm_text(
                "**Algorithm 1 (Finding the Maximum Element).** text"))
        self.assertEqual(miss, [])

    def test_exercise_key_found_via_english_label(self):
        miss = physical_evidence._missing_contract_names(
            self._contract("练习7", "练习7"),
            physical_evidence._norm_text("**Exercise 7.** Find the complexity."))
        self.assertEqual(miss, [])

    def test_genuinely_absent_item_is_still_reported(self):
        miss = physical_evidence._missing_contract_names(
            self._contract("算法9", "算法9"),
            physical_evidence._norm_text("**Algorithm 1 (…).** 正文只到算法一号为止"))
        self.assertEqual(miss, ["算法9"])


class ZhSiblingLabelTest(_Primed):
    """中文同胞标签互换（do Carmo 中文版假报根因）。

    契约 key `评注N`（build_structure 依 EN "Remarks" 所起中文键），而 CN 译文本
    书体例统一印作 `注N`——`_label_variants` 旧版只做 zh→EN 互译，CN 组证据把
    `评注N` 翻成 remark/N 后在纯中文 md 里找不到，merge_translation 证据硬拒。
    负向：md 里 `注` 与 `评注` 两种写法都不在位的编号项必须仍报缺。
    """

    def _contract(self, key, name):
        return {"key": "1", "type": "chapter", "name": "Curves",
                "sub_sec": [{"key": key, "type": "item", "name": name,
                             "page_start": 20, "page_end": 25, "sub_sec": []}]}

    def test_ping_note_key_found_via_zh_sibling(self):
        miss = physical_evidence._missing_contract_names(
            self._contract("评注1", "评注1 1. In the particular case..."),
            physical_evidence._norm_text("> **注 1.** 在平面曲线的情形…"))
        self.assertEqual(miss, [])

    def test_remark_en_key_found_via_zh_sibling(self):
        miss = physical_evidence._missing_contract_names(
            self._contract("Remark2", "Remark2"),
            physical_evidence._norm_text("**注 2.** 给定一条正则参数化曲线…"))
        self.assertEqual(miss, [])

    def test_absent_under_both_zh_forms_still_reported(self):
        miss = physical_evidence._missing_contract_names(
            self._contract("评注3", "评注3"),
            physical_evidence._norm_text("**注 1.** 与 **评注 2.** 都在，唯独三缺席"))
        self.assertEqual(miss, ["评注3"])


if __name__ == "__main__":
    unittest.main()
