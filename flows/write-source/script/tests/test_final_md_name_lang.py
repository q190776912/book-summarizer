# -*- coding: utf-8 -*-
"""Regression: 英文源书的**英文版**章文件名不得带中文（merge_units._final_md_name）。

Kreyszig（英文书，2026-09-26 收官实测）：契约 `ch{N}.json` 的 `name` 按中文标题登记
（`5 进一步应用：巴拿赫不动点定理`），而旧 `_final_md_name` 不分语种直接拿它拼名，
于是英文版产出 `Chapter5_进一步应用：巴拿赫不动点定理.md`。同书其余英文文件都是
拆节时按**文内英文标题**生成的 ASCII 名（`Chapter1_1.1_MetricSpace.md`），所以缺陷
只在**没被拆分的章**上露出来——一本书两套语言规则。

根治 = `language == "en"` 时优先取 chapter_map 的 `name_en`，并在兜底处剥掉残留 CJK。

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_final_md_name_lang.py
"""
import re
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, str(Path(_ROOT) / "flows" / "write-source" / "script"))

from merge_units import _final_md_name  # noqa: E402

CJK = re.compile(r"[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef]")
CN_NAME = "5 进一步应用：巴拿赫不动点定理"
EN_NAME = "Further Applications: Banach Fixed Point Theorem"


class TestEnglishNameNotCJK(unittest.TestCase):
    def test_en_prefers_name_en(self):
        got = _final_md_name("5", "en", CN_NAME, EN_NAME)
        self.assertEqual(got, "Chapter5_Further_Applications_Banach_Fixed_Point_Theorem.md")
        self.assertFalse(CJK.search(got))

    def test_en_falls_back_to_stripped_contract_name(self):
        # chapter_map 里根本没有英文名：剥掉中文后标题为空 → 退回**裸名**，
        # 也绝不把中文拼进英文版文件名（宁可短名，不要跨语种名）。
        self.assertEqual(_final_md_name("5", "en", CN_NAME), "Chapter5.md")
        # CJK 前缀契约名（附录「A 提示」，rest 解析不出来）同样退裸名。
        self.assertEqual(_final_md_name("A", "en", "附录A 提示"), "AppendixA.md")
        # 标题中英混杂：只留 ASCII 片段。
        self.assertEqual(_final_md_name("7", "en", "7 Hilbert 空间 Notes"),
                         "Chapter7_Hilbert_Notes.md")
        for got in (_final_md_name("5", "en", CN_NAME),
                    _final_md_name("A", "en", "附录A 提示"),
                    _final_md_name("7", "en", "7 Hilbert 空间 Notes")):
            self.assertFalse(CJK.search(got))

    def test_cn_version_keeps_chinese_name(self):
        self.assertEqual(_final_md_name("5", "cn", CN_NAME, EN_NAME),
                         "第5章_进一步应用：巴拿赫不动点定理.md")

    def test_chinese_book_source_unaffected(self):
        # 中文书：源版 language=cn，行为与旧实现逐字一致。
        self.assertEqual(_final_md_name("3", "cn", "3 正则曲面", "Regular Surfaces"),
                         "第3章_正则曲面.md")

    def test_appendix_and_supplement_heads(self):
        # 契约名已是 ASCII 时**不覆盖**（旧形态逐字保持：附录字母留在标题里）。
        self.assertEqual(_final_md_name("A", "en", "Appendix A Hints", "Hints"),
                         "Appendix_A_Hints.md")
        # 契约名是中文 → 用 name_en，序标仍按 chapter_ordinal/章键判定。
        self.assertEqual(_final_md_name("A", "en", "附录 A 提示", "Hints"),
                         "AppendixA_Hints.md")
        self.assertFalse(CJK.search(_final_md_name("A", "en", "附录A 提示", "Hints")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
