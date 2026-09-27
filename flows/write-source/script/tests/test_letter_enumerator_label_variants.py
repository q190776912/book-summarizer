# -*- coding: utf-8 -*-
"""回归：**字母序标**条目（`Theorem A` / `Proposition A.1`）的中英标签互译变体。

事故（Shafarevich《Basic Algebraic Geometry 1》ch3 §4.2/§4.4，2026-09-28，
merge_source 证据复核被假报硬拒）：契约把字母序标条目登记成中文标签 + 字母
（键 `定理 A`，归一 `定理a`），而英文源 md 印 `**Theorem A**`。判据
`physical_evidence._label_variants` 的正则要求序标以**数字**起头
（`^(标签)(\\d.*)$`），于是 `定理a` 生成不出 `theorema` 变体 →
`_missing_contract_names` 报「ch3 [en] 缺 4 项（定理 A/B/C/D）」，而这四条在 md
里**确实在位**（`grep 'Theorem A' Chapter3_4_AlgebraicGroups.md` 命中）。
`_flow_contract` 的证据门拒绝 mark，写手被逼迫的出路只有两条，都是坏的：给真在位的
条目伪造内容，或把契约/单元里的印刷标签改成中文。

根治 = 序标分支同时接受字母（`a` / `a1` / `a.1`），**数字分支逐字节不变**；反方向
（契约键是 EN `Theorem A`、中文版印 `定理 A`）由同一条正则的回溯自然覆盖。
本测试同时锁死负向：真缺失仍须报（放宽的只是**变体生成**，不是「在位」判据本身）。
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
    _ROOT = str(Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

from flows._flow_contract import physical_evidence as pe  # noqa: E402


def _variants(key):
    return sorted(pe._label_variants(pe._norm_text(key)))


def _contract(key, name, typ="theorem"):
    return {"key": "3", "type": "chapter", "name": "3 Divisors",
            "sub_sec": [{"key": "3.4", "type": "section",
                         "name": "3.4 Algebraic Groups", "sub_sec": [
                             {"key": key, "type": typ, "name": name,
                              "text": [{"text": "body"}]}]}]}


class LetterEnumeratorVariantsTest(unittest.TestCase):
    def test_cn_label_with_letter_ordinal_gets_en_variant(self):
        """事故本体：契约键 `定理 A` → 英文 md 的 `Theorem A` 必须在候选里。"""
        self.assertIn("theorema", _variants("定理 A"))

    def test_en_label_with_letter_ordinal_gets_cn_variant(self):
        """反方向（译版证据）：契约键 `Theorem A` → 中文版印 `定理 A`。"""
        self.assertIn("定理a", _variants("Theorem A"))

    def test_letter_ordinal_with_dot_and_digit_still_translated(self):
        got = _variants("推论 A.1")
        self.assertIn("推论a1", got)
        self.assertIn("corollarya1", got)

    def test_digit_branch_unchanged(self):
        """数字序标（占绝大多数）判据零回归。"""
        self.assertEqual(_variants("定理3.15"), ["theorem315", "定理315"])
        self.assertEqual(_variants("定义 1.1"), ["definition11", "定义11"])

    def test_unknown_label_with_letter_makes_no_variant(self):
        """🔴 不得凭空造变体：标签不在词表时只有原串（放宽只作用于**已知标签**）。"""
        self.assertEqual(_variants("函子 A"), ["函子a"])


class EvidenceGateTest(unittest.TestCase):
    def test_lettered_item_present_in_en_md_is_not_reported(self):
        """端到端（事故复现）：md 印 `**Theorem A**` 时不得再报缺项。"""
        md = pe._norm_text("### 3.4 Algebraic Groups\n**Theorem A**: The abstract "
                           "group $G/N$ can be made into a variety.\n")
        self.assertEqual(pe._missing_contract_names(
            _contract("定理 A", "定理 A The abstract group G/N"), md), [])

    def test_lettered_item_genuinely_absent_still_reported(self):
        """🔴 真漏写照报：md 只有别的定理、没有 Theorem A 文本。"""
        md = pe._norm_text("### 3.4 Algebraic Groups\n**Theorem 3.15** An Abelian "
                           "variety is an Abelian group.\n")
        miss = pe._missing_contract_names(
            _contract("定理 A", "定理 A The abstract group G/N"), md)
        self.assertEqual(miss, ["定理 A"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
