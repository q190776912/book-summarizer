# -*- coding: utf-8 -*-
r"""B 层 EXTRA 分桶的判据回归（第 12 处根治，2026-09-29 Apostol IANT ch9 例1）。

旧写法 `extra = all_keys - extracted` 单行输出，文案 "usually correctly-filtered
cross-refs" 把两类完全不同的东西混在一起：
  · **条目级**：md 里有独立加粗条头（`entry_keys`）而契约无条目 = 契约漏登记印面条目
    （Apostol ch9 §9.6 `EXAMPLE 1`，fitz 目视确证印面有条头，OCR 把条头粘进句子导致
    抽取器没认出 → 契约无节点 → 该行被误判成「交叉引用，无需处置」）；
  · **提及级**：只在正文/交叉引用里出现 = 通常确为正确过滤。
修法 = 只改**可读性**（分两桶、各给处置文案），`extra` 仍是并集 → pass/fail 逐字节
不变（跨书普查显示条目级 EXTRA 多数是体例而非漏登记，一律阻断会打爆已收官书）。

负向守卫：两桶必须**不重不漏**地铺满并集；契约已登记的条头不得出现在任何一桶。
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
import lib.boot as _boot  # noqa: E402
_boot.setup()

from verify.item_numbering_integrity.script.item_numbering_integrity import (  # noqa: E402
    _split_extra)


class TestBucketing(unittest.TestCase):
    def test_entry_head_missing_from_contract_goes_to_entry_bucket(self):
        # Apostol ch9 实测形态：例1 是条头、契约无节点；例2 双方都在账。
        allk = {"例1", "例2", "定理9.1", "练习2.34"}
        ent = {"例1", "例2", "定理9.1"}          # 练习2.34 只在正文被提到
        extracted = {"例2", "定理9.1"}
        union, ee, em = _split_extra(allk, ent, extracted)
        self.assertEqual(ee, ["例1"])
        self.assertEqual(em, ["练习2.34"])
        self.assertEqual(union, ["例1", "练习2.34"])   # 旧口径逐字节不变

    def test_registered_head_in_no_bucket(self):
        union, ee, em = _split_extra({"定理9.1"}, {"定理9.1"}, {"定理9.1"})
        self.assertEqual((union, ee, em), ([], [], []))

    def test_buckets_partition_union_without_overlap(self):
        allk = {"a", "b", "c", "d"}
        ent = {"a", "b"}
        extracted = {"b"}
        union, ee, em = _split_extra(allk, ent, extracted)
        self.assertEqual(set(ee) | set(em), set(union))
        self.assertFalse(set(ee) & set(em))

    def test_unnumbered_house_style_head_is_still_entry_level(self):
        # Lie 代数 ch1 体例：无号条头 `**例**` / `**定义**` → 条目级，但判读结论
        # 是「体例、无需处置」；分桶只负责把它摆到可判读的位置。
        union, ee, em = _split_extra({"例", "定义"}, {"例", "定义"}, set())
        self.assertEqual(sorted(ee), ["例", "定义"])
        self.assertEqual(em, [])

    def test_empty_inputs(self):
        self.assertEqual(_split_extra(set(), set(), set()), ([], [], []))


if __name__ == "__main__":
    unittest.main()
