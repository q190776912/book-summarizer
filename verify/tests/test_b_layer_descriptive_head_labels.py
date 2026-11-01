"""Regression tests: 描述性条头（号前无类型词）必须进入 B 层条目序列（Weibel ch10 实测）。

背景：``_ENTRY_LABELS`` 的类型词表按「定义/定理/引理/…」收词。Weibel《An
Introduction to Homological Algebra》把若干条目**印成纯描述性条头**，号前没有
任何类型词（印面取证 p294 页带）：

  * ``Exegesis 10.2.3``            印面 p376（ch10 §10.2）
  * ``Prototype 10.3.5 (…rings)``  印面 p381（ch10 §10.3）
  * ``Exact Functors 10.5.2``      印面 p392（ch10 §10.5）

后果与 Kreyszig「要求 / Requirement」同一型：交付里只要另有一份「编号在前」的
同形条头（``**10.2.3 (Exegesis)**``），num-first 兜底就把号数上了，词表缺口被
掩盖；一旦按印面去重、只留 label-first 形，共享计数器窗立刻假报
「0:10.2 缺号 3 / 0:10.3 缺号 5 / 0:10.5 缺号 2」三条硬 BLOCKING。

根治 = 把三词（及中译形「疏解 / 原型 / 正合函子」）补进类型词表并在
``_LABEL_NORM`` 配对正名，而不是在 ignore 里登记假缺号——后者会把「该条确实
存在」从校验里抹掉。放宽半径已用全架普查钉住：51 本交付 md 中
``\\*\\*(?:Exegesis|Prototype|Exact Functors|疏解|原型|正合函子)\\s*\\d``
只命中本书这 6 个条头本身，对其余书逐字节惰性。
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


class TestDescriptiveHeadLabels(unittest.TestCase):
    def test_en_descriptive_heads_parsed(self):
        # The regression: before these words entered _ENTRY_LABELS each returned
        # None, and the B layer reported phantom gaps 3 / 5 / 2 for ch10.
        self.assertEqual(_parse_entry("Exegesis 10.2.3", 3, "en"),
                         ([10, 2, 3], "Exegesis"))
        self.assertEqual(_parse_entry("Prototype 10.3.5 (Localizations of rings)", 3, "en"),
                         ([10, 3, 5], "Prototype"))
        self.assertEqual(_parse_entry("Exact Functors 10.5.2", 3, "en"),
                         ([10, 5, 2], "Exact Functors"))

    def test_cn_descriptive_heads_parsed(self):
        # 两侧必须同一判定（同一内容两版不一致就是证据）。
        self.assertEqual(_parse_entry("疏解 10.2.3", 3, "cn"), ([10, 2, 3], "疏解"))
        self.assertEqual(_parse_entry("原型 10.3.5（环的局部化）", 3, "cn"),
                         ([10, 3, 5], "原型"))
        self.assertEqual(_parse_entry("正合函子 10.5.2", 3, "cn"), ([10, 5, 2], "正合函子"))

    def test_number_first_form_still_parsed(self):
        # 去重前的旧形不得因本次放宽而失效（两条路都要落到同一个号）。
        self.assertEqual(_parse_entry("10.2.3 (Exegesis)", 3, "en"), ([10, 2, 3], "Exegesis"))
        self.assertEqual(_parse_entry("10.5.2 (Exact Functors)", 3, "en"),
                         ([10, 5, 2], "Exact Functors"))

    def test_labels_canonicalize_together(self):
        # known_gaps written in English must suppress the CN header and vice versa.
        self.assertEqual(_norm_label("疏解"), "Exegesis")
        self.assertEqual(_norm_label("原型"), "Prototype")
        self.assertEqual(_norm_label("正合函子"), "Exact Functors")
        self.assertEqual(_norm_label("Exegesis"), "Exegesis")

    def test_non_entry_still_rejected(self):
        # 证明标题不是条目：即便尾随一个在册号。
        self.assertIsNone(_parse_entry("Proof of Prototype 10.3.5", 3, "en"))
        self.assertIsNone(_parse_entry("证明 正合函子 10.5.2", 3, "cn"))
        # 只有词、没有号 → 不是条头。
        self.assertIsNone(_parse_entry("Exegesis", 3, "en"))
        self.assertIsNone(_parse_entry("正合函子", 3, "cn"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
