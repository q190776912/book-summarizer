"""Regression tests: 「要求 / Requirement」类条头必须进入 B 层条目序列（Kreyszig ch4 实测）。

背景：``_ENTRY_LABELS`` 的类型词表收了 定义/定理/引理/…，但漏了 Kreyszig
《Introductory Functional Analysis with Applications》§4.11 的条目类型
「Requirement」（中译「要求」）。后果是**同一份内容两版判定不一致**：

  * EN 版条头 ``**4.11-2 Requirement.**`` 编号在前，走 num-first 分支在余串里搜类型词，
    搜不到也仍被兜底计为条目 → §4.11 序列 1..5 完整，PASS；
  * CN 版条头 ``**要求 4.11-2。**`` 标签在前，label-first 无词可配、又不是裸编号 →
    整条不被计数 → 假「0:4.11 缺号 2（序列 1..5 不连续）」BLOCKING。

根治 = 把「要求 / Requirement(s)」补进类型词表（并在 ``_LABEL_NORM`` 里配对正名，
使英文写法的 ``known_gaps`` 也能压住中文条头），而不是在 ignore 里登记假缺号——
后者会把「该条确实存在」这一事实从校验里抹掉。
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


class TestRequirementLabel(unittest.TestCase):
    def test_cn_label_first_header_parsed(self):
        # The regression: before 要求 entered _ENTRY_LABELS this returned None,
        # and the B layer reported a phantom gap at ordinal 2 of §4.11.
        self.assertEqual(_parse_entry("要求 4.11-2。", 3, "cn"), ([4, 11, 2], "要求"))
        self.assertEqual(_parse_entry("要求 4.11-2", 3, "cn"), ([4, 11, 2], "要求"))

    def test_en_label_first_and_plural_parsed(self):
        self.assertEqual(_parse_entry("Requirement 4.11-2", 3, "en"),
                         ([4, 11, 2], "Requirement"))
        self.assertEqual(_parse_entry("Requirements 4.11-2", 3, "en"),
                         ([4, 11, 2], "Requirements"))

    def test_number_first_form_parsed(self):
        self.assertEqual(_parse_entry("4.11-2 Requirement", 3, "en"),
                         ([4, 11, 2], "Requirement"))

    def test_labels_canonicalize_together(self):
        # known_gaps written in English must suppress the CN header and vice versa.
        self.assertEqual(_norm_label("要求"), "Requirement")
        self.assertEqual(_norm_label("Requirement"), "Requirement")

    def test_non_entry_still_rejected(self):
        # 「要求 (7)」is prose about a numbered formula, not an item header.
        self.assertIsNone(_parse_entry("要求 (7) 成立", 3, "cn"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
