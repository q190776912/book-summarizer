"""Tests for lib/tag_attestation.py — 契约公式编号的印刷锚点审计（闸门 ⑭）.

Run:  python lib/tests/test_tag_attestation.py

负向用例守的是 Kreyszig 实测的三类毒 tag（2026-09-26 源码 verify Q 层）：
``22`` = display 内两个 ε/2 的分母被 OCR 成独立数字块；``50``/``25`` =
``= 0.50`` 的小数尾巴；``18751A``/``12818A`` = 波长 ``18 751 Å``。
契约 tag 是门控对账真值，误挂会反逼写手凭空 ``\\tag``，故必须在闸门判 FAIL。
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

from tag_attestation import collect_contract_tags, tag_attestation_problems


def formula_block(tag, tags=None):
    b = {"formula": "x = y", "display": True}
    if tags:
        b["tag"] = tag
        b["tags"] = tags
    elif tag is not None:
        b["tag"] = tag
    return b


def contract(tags, lo=10, hi=20):
    """tags: [str|None] 或 [(str, [str])]（首号, 多号列表）→ 单节点契约。"""
    blocks = []
    for t in tags:
        if isinstance(t, (list, tuple)):
            blocks.append(formula_block(t[0], list(t[1])))
        else:
            blocks.append(formula_block(t))
    return {"key": "ch1", "type": "chapter", "page_start": lo, "page_end": hi,
            "sub_sec": [{"key": "1.4", "type": "section", "sub_sec": blocks}]}


def loader(pages):
    """pages: {pdf_page: [block text]}；未列出的页给 None（= 无页文件）。"""
    def load(pg):
        return pages.get(pg)
    return load


PAREN_PAGES = {p: ["(%d)" % n for n in range(1, 30)] for p in range(10, 21)}


class TestCollect(unittest.TestCase):
    def test_collects_tag_and_tags_in_doc_order(self):
        tree = contract(["7", ("9", ["9", "10"])])
        got = [n for _k, n in collect_contract_tags(tree)]
        self.assertIn("7", got)
        self.assertIn("10", got)
        self.assertEqual(len(got), len(set(got)), "重复编号须去重")

    def test_ignores_blocks_without_tag(self):
        tree = contract([None])
        self.assertEqual(collect_contract_tags(tree), [])


class TestAttested(unittest.TestCase):
    def test_parenthesized_labels_pass(self):
        tree = contract(["7", "12", "18"])
        pages = {p: ["(7)", "(12)", "(18)", "some prose"] for p in range(10, 21)}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])

    def test_label_glued_into_formula_line_passes(self):
        """编号被 OCR 粘进公式行（非独立块）时不得误报。"""
        tree = contract(["7"])
        pages = {p: ["d(x, y) = sqrt(x - y)  (7)"] for p in range(10, 21)}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])

    def test_bare_dominant_book_passes(self):
        """裸排点分编号书（Koopman 型）：整章无括号 → 裸块锚点合法。"""
        tree = contract(["3.21", "3.22"], lo=10, hi=12)
        pages = {10: ["3.21"], 11: ["3.22"], 12: ["prose"]}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])

    def test_label_detected_as_formula_attests(self):
        """左缘编号被 MFD 当**公式**检测出来（Kreyszig 3.7-2 印刷 `(7c')`/`(7*)`）：
        只看 text 流会误判真编号为噪声，故 latex 形态也算锚点。"""
        tree = contract(["7a", "7b", "7c", "7c'", "7*", "9"], lo=10, hi=11)
        pages = {10: ["(9)", "(7b)", "(7c)"],
                 11: ["( 7 \\mathsf { a } )", "( 7 \\mathbf { c } ^ { \\prime } )",
                      "( 7 ^ { * } )", "H _ { n } ( t ) = n ! \\sum"]}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])


class TestPhantom(unittest.TestCase):
    def test_unattested_number_flagged(self):
        """18751A 型：页窗内 (N) 与裸 N 都找不到。"""
        tree = contract(["7", "18751A"], lo=10, hi=12)
        pages = {p: ["(7)", "18 751 A", "E4 -> E3"] for p in range(10, 13)}
        probs = tag_attestation_problems(tree, loader(pages))
        self.assertEqual(len(probs), 1)
        self.assertIn("18751A", probs[0])
        self.assertIn("找不到任何印刷锚点", probs[0])

    def test_bare_only_tag_flagged_in_paren_chapter(self):
        """22 型：ε/2 分母被读成独立数字块，而本章编号一律 `(N)`。"""
        tree = contract([str(n) for n in range(1, 23)] + ["22"], lo=10, hi=12)
        pages = {p: ["(%d)" % n for n in range(1, 22)] for p in range(10, 13)}
        pages[12] = list(pages[10]) + ["22"]      # 公式内部碎片成独立块
        probs = tag_attestation_problems(tree, loader(pages))
        self.assertTrue(any("22" in p and "裸排" in p for p in probs), probs)

    def test_decimal_tail_flagged_in_paren_chapter(self):
        """50 型：`= 0.50` 的尾巴；页窗内无 `(50)`，只有裸块 50。"""
        tags = [str(n) for n in range(1, 20)] + ["50"]
        tree = contract(tags, lo=10, hi=12)
        pages = {p: ["(%d)" % n for n in range(1, 20)] + ["50"] for p in range(10, 13)}
        probs = tag_attestation_problems(tree, loader(pages))
        self.assertTrue(any("50" in p for p in probs), probs)

    def test_bare_only_tag_allowed_when_chapter_is_bare(self):
        """裸排书不得被 ⑭ 误伤：括号占比不足 90% 时裸锚点合法。"""
        tags = [str(n) for n in range(1, 21)]
        tree = contract(tags, lo=10, hi=12)
        pages = {p: ["(%d)" % n for n in range(1, 3)] +
                     ["%d" % n for n in range(3, 21)] for p in range(10, 13)}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])

    def test_missing_pages_fail_open(self):
        """整章无页文件 → 不判（缺数据不等于内容缺陷）。"""
        tree = contract(["7", "99"], lo=10, hi=12)
        self.assertEqual(tag_attestation_problems(tree, loader({})), [])

    def test_chapter_label_prefix(self):
        tree = contract(["99"], lo=10, hi=11)
        pages = {p: ["(7)", "prose"] for p in range(10, 12)}
        probs = tag_attestation_problems(tree, loader(pages), chapter_label="ch5")
        self.assertTrue(probs[0].startswith("[ch5]"), probs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
