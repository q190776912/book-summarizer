"""Negative tests: page furniture must never enter the formula-ordinal truth set.

Found on Strogatz *Nonlinear Dynamics and Chaos* 3e (2026-09-27): odd pages print
the page number in the **top** margin at y ~= 6.3% of page height, i.e. outside the
extreme-edge band (6%/94%) that `_source_formula_tags` used as its page-number
test. Every page number therefore leaked into the "book source equation numbers"
truth set (ch2 16..49, ch9 338..383, ch13 498..537 ... ~380 fake ordinals over 13
chapters), which (a) made the "公式编号未挂到公式" advisory meaningless and (b)
invited the step-5 writer agent to fabricate \\tag{16} for a page number.

Fix under test: bare numbers that track the page index (value = page - constant
offset, shared by >= 3 pages) inside the margin band are furniture; and an
unparenthesized short token carrying letters ('2e', '4c', '020m' — OCR debris of
`2e^{x}` fragments) is not an ordinal at all.
"""
import json
import os
import shutil
import sys
import tempfile
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
import lib.boot as _boot
_boot.setup()

import check_content_completeness as ccc  # noqa: E402

PAGE_H = 1750.0          # content bottom edge; sets the 12% / 90% margin bands
TOP_Y = 0.064 * PAGE_H   # ~= 112 — inside the 12% margin band, OUTSIDE the 6% band


def _blk(text, y, x=120.0, h=28.0):
    return {"text": text,
            "poly": [x, y, x + 120, y, x + 120, y + h, x, y + h]}


def _write_pages(ext, pages):
    for p, blocks in pages.items():
        with open(os.path.join(ext, "page_%03d.json" % p), "w",
                  encoding="utf-8") as f:
            json.dump({"text": blocks}, f)


class TestPageFurnitureNotOrdinal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ccc_page_furniture_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _tags(self, pages, ncomp=1):
        _write_pages(self.tmp, pages)
        return ccc._source_formula_tags(self.tmp, 1, max(pages), "", ncomp,
                                        letter=False, bare=True)

    def test_top_margin_page_numbers_excluded(self):
        # 三页页眉页码 15/16/17（值 = 页序 - 14，恒定偏移）+ 真编号 (1)
        pages = {
            1: [_blk("15", TOP_Y), _blk("2.1 A Geometric Way of Thinking", 244.0),
                _blk("Consider the following nonlinear differential equation:", 432.0),
                _blk("dx/dt = sin x.", 491.0, x=200.0), _blk("(1)", 491.0, x=1450.0),
                _blk("body paragraph one", 600.0), _blk("footer line", 1700.0)],
            2: [_blk("16", TOP_Y + 2), _blk("To emphasize our point about formulas", 300.0),
                _blk("csc x0 + cot x0", 900.0), _blk("footer line", 1700.0)],
            3: [_blk("17", TOP_Y + 1), _blk("This result is exact, but a headache", 300.0),
                _blk("footer line", 1700.0)],
        }
        got = self._tags(pages)
        self.assertEqual(got, {"1"}, "页码 15/16/17 不得进入公式序标真值集：%s" % got)

    def test_margin_number_that_does_not_track_pages_survives(self):
        # 反例（防过度剔除）：p1-3 的页眉 15/16/17 随页序恒定偏移 → 页码；p4 页眉带
        # 里的裸数字 7 偏移不一致（4-7=-3，只此一页）→ 仍按编号收录（可能是真右缘
        # 裸排编号被 OCR 读到页眉高度，或被 6% 极端带漏掉）。
        pages = {
            1: [_blk("15", TOP_Y), _blk("(1)", 491.0, x=1450.0),
                _blk("footer line", 1700.0)],
            2: [_blk("16", TOP_Y), _blk("body", 400.0), _blk("footer line", 1700.0)],
            3: [_blk("17", TOP_Y), _blk("body", 400.0), _blk("footer line", 1700.0)],
            4: [_blk("7", TOP_Y, x=1450.0), _blk("body", 400.0),
                _blk("footer line", 1700.0)],
        }
        got = self._tags(pages)
        self.assertIn("7", got, "不随页序跟踪的边缘裸号不得被误杀：%s" % got)
        self.assertEqual(got, {"1", "7"}, "页码仍须被排除：%s" % got)

    def test_bare_letter_debris_excluded(self):
        # OCR 把 `2e^{x}` / `4c` 切成独立小块：无括号又含字母 → 不是编号。
        pages = {
            1: [_blk("15", TOP_Y), _blk("(1)", 491.0, x=1450.0),
                _blk("2e", 800.0), _blk("4c", 830.0), _blk("footer line", 1700.0)],
            2: [_blk("16", TOP_Y), _blk("020m", 700.0), _blk("1970s", 720.0),
                _blk("footer line", 1700.0)],
            3: [_blk("17", TOP_Y), _blk("body", 400.0), _blk("footer line", 1700.0)],
        }
        got = self._tags(pages)
        self.assertEqual(got, {"1"}, "无括号字母碎片不得成为编号：%s" % got)

    def test_parenthesized_letter_suffix_still_collected(self):
        # 回归护栏：`(8.11a)` 这类**带括号**的字母后缀编号仍是编号。
        pages = {
            1: [_blk("(8.11a)", 491.0, x=1450.0), _blk("footer line", 1700.0)],
        }
        self.assertEqual(self._tags(pages, ncomp=2), {"8.11a"})

    def test_unicode_digit_debris_does_not_crash(self):
        # '²4' 之类的上标碎片：str.isdigit() 为真但 int() 会抛——判据须按 ASCII 数字收。
        from lib.numbering import page_number_furniture
        keys = page_number_furniture(
            [(1, 112.0, 140.0, "²4"), (2, 113.0, 141.0, "16"),
             (3, 114.0, 142.0, "17"), (4, 115.0, 143.0, "18")], 1750.0)
        self.assertEqual(keys, {(2, "16"), (3, "17"), (4, "18")},
                         "上标碎片不得参与页码跟踪，真页码仍须识别")


if __name__ == "__main__":
    unittest.main(verbosity=2)
