# -*- coding: utf-8 -*-
"""Regression: separator-free CN item keys must still render EN headers
(render_draft._item_header_name; Rosen 8e, 2026-09-25).

Rosen numbers every label **per section** with no dot at all — contract keys are
`例1` / `定义1` / `定理3`, and the printed name repeats the number (`例1 1`).
The old `_CN_KEY_RE` demanded `digits [-.] digits`, so single-level keys never
matched and the CN label leaked into an English-source draft
("`> **例1 1**: 1. Washington, D.C., is the capital …`") — every one of the
book's 1439 item units, and writing-rules' bilingual iron rule forbids CN
labels in the EN version.

Locks: single-level keys convert; the duplicated bare number in the name is
deduped; two-level keys keep working; label + space + word (unnumbered
Remark/Note) and CN books stay untouched.

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_en_item_header_labels.py
"""
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
import sys
sys.path.insert(0, str(Path(_ROOT) / "flows" / "write-source" / "script"))

from render_draft import _item_header_name  # noqa: E402


class TestSeparatorFreeKeys(unittest.TestCase):
    def test_single_level_key_converted(self):
        self.assertEqual(_item_header_name("例1", "en"), "Example 1")
        self.assertEqual(_item_header_name("定义1", "en"), "Definition 1")
        self.assertEqual(_item_header_name("定理3", "en"), "Theorem 3")
        self.assertEqual(_item_header_name("算法 12", "en"), "Algorithm 12")

    def test_duplicated_bare_number_deduped(self):
        # printed name carries the number twice: "例1 1" (key 例1 + body "1 …")
        self.assertEqual(_item_header_name("例1 1", "en"), "Example 1")
        self.assertEqual(_item_header_name("定理2 2 The Division Algorithm", "en"),
                         "Theorem 2 The Division Algorithm")

    def test_two_level_keys_unchanged(self):
        self.assertEqual(_item_header_name("定理2.1", "en"), "Theorem 2.1")
        self.assertEqual(_item_header_name("引理1-3 Gauss's Lemma", "en"),
                         "Lemma 1-3 Gauss's Lemma")
        self.assertEqual(_item_header_name("例9.2.3 (a) We show", "en"),
                         "Example 9.2.3 (a) We show")

    def test_unnumbered_label_left_alone(self):
        # label + space + word: no ordinal at all, nothing to translate
        self.assertEqual(_item_header_name("注 The following is useful", "en"),
                         "注 The following is useful")

    def test_cn_book_untouched(self):
        self.assertEqual(_item_header_name("例1 1", "cn"), "例1 1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
