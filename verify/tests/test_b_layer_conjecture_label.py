"""Regression tests: 「猜想 / Conjecture」类条头必须进入 B 层条目序列（Iwaniec-Kowalski ch7 实测）。

背景：``_ENTRY_LABELS`` 类型词表收了 定义/定理/引理/推论/命题/…，但漏了
``_LABEL_CANON`` 早已正名的 猜想/Conjecture（连带 断言/Assertion、假设/Assumption、
条件/Condition）。Iwaniec-Kowalski《Analytic Number Theory》为**章内共享计数器**
（Theorem/Corollary/Lemma/Proposition/Conjecture 同一条 1..N 序列），后果：

  * structure 完整性闸门的合成 md 条目头 ``**猜想7.32**`` label-first 无词可配，
    只剩裸号 `7.32` 走 num-first 且 tail 为空 → 整条被丢弃 →
    假「0:7 缺号 32（序列 1..35 不连续）」BLOCKING，整章卡闸门；
  * EN 侧同源：``**Conjecture 7.32**`` 在旧词表下会先匹配短词碎片
    （正则碎片误配）→ 同样 None。

根治 = 把 猜想/断言/假设/假定/条件 与 Conjecture/Assertion/Assumption/Condition
（复数在前）补进词表，并在 ``_LABEL_NORM`` 配对正名，而非 ignore 登记假缺号。
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
    _norm_label, _parse_entry)


class TestConjectureLabel(unittest.TestCase):
    def test_cn_label_first_header_parsed(self):
        # The regression: before 猜想 entered _ENTRY_LABELS this returned None,
        # and the shared-counter window 0:7 reported a phantom gap at 32.
        self.assertEqual(_parse_entry("猜想7.32", 2, "en"), ([7, 32], "猜想"))
        self.assertEqual(_parse_entry("猜想 7.32", 2, "en"), ([7, 32], "猜想"))

    def test_en_label_first_and_plural_parsed(self):
        self.assertEqual(_parse_entry("Conjecture 7.32", 2, "en"),
                         ([7, 32], "Conjecture"))
        self.assertEqual(_parse_entry("Conjecture 7.32.", 2, "en"),
                         ([7, 32], "Conjecture"))
        self.assertEqual(_parse_entry("Conjectures 7.32", 2, "en"),
                         ([7, 32], "Conjectures"))

    def test_sibling_types_parsed(self):
        for s, exp in [("Assertion 7.5", ([7, 5], "Assertion")),
                       ("Condition 5.1", ([5, 1], "Condition")),
                       ("断言7.5", ([7, 5], "断言")),
                       ("假设7.6", ([7, 6], "假设"))]:
            self.assertEqual(_parse_entry(s, 2, "en"), exp, s)

    def test_labels_canonicalize_together(self):
        self.assertEqual(_norm_label("猜想"), "Conjecture")
        self.assertEqual(_norm_label("Conjecture"), "Conjecture")
        self.assertEqual(_norm_label("条件"), "Condition")

    def test_existing_labels_unaffected(self):
        self.assertEqual(_parse_entry("定理7.33", 2, "en"), ([7, 33], "定理"))
        self.assertEqual(_parse_entry("Calculation 6.2", 2, "en"),
                         ([6, 2], "Calculation"))


if __name__ == "__main__":
    unittest.main()
