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

Second finding (2026-09-28, Arnold *Mathematical Methods of Classical Mechanics*
CN appendix O): the offset law is only as good as the normalization feeding it.
That book prints folios as `.376.` style decorated numbers, so the checker's
whitespace-only normalization saw zero furniture samples and the one page OCR
happened to read clean (`386`) was reported as a lost equation number. Both
sides now share `lib.numbering.folio_norm` — see
`TestDecoratedFolioSharesNormalization`.
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


class TestDecoratedFolioSharesNormalization(unittest.TestCase):
    """页码**带装饰点**时，跟踪律样本与查表键必须与契约侧同源（folio_norm）。

    阿诺尔德《经典力学的数学方法》附录O（2026-09-28 实测）：印刷页码 373..391 的
    OCR 形态是 `·373·` / `: 377 .` / `380·`，**只有 p401 漏掉了装饰点**读成干净的
    `386`。源真值侧用「只压空白」的 `_norm_text` 归一化：带点的版本进不了纯数字统计
    → 恒定偏移（页序 − 15）样本不足 3 页 → 跟踪律对整章失明；那唯一的干净 `386`
    于是被当成「书源独立成块的公式编号」→ `CONTENT GATE: FAIL 公式编号丢失 ['386']`，
    而契约侧（`_norm` 去标点）早已把 16 个页码整批当噪声丢弃。闸门拦住的是**不存在的
    内容丢失**，还会诱导写手给页码编造 `\\tag{386}`。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ccc_folio_dots_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _tags(self, pages, ncomp=1):
        _write_pages(self.tmp, pages)
        return ccc._source_formula_tags(self.tmp, 1, max(pages), "", ncomp,
                                       letter=False, bare=True)

    def test_dotted_folios_teach_the_law_that_bare_one_is_furniture(self):
        # p1..p3 页码带装饰点（只喂统计、本身不是编号），p4 同序列的页码恰好被 OCR
        # 读成干净裸号且落在 12% 页眉带内、6%/94% 极端带外 → 只能靠跟踪律剔除。
        pages = {
            1: [_blk("·15·", TOP_Y), _blk("(1)", 491.0, x=1450.0),
                _blk("body text one", 700.0), _blk("footer line", 1700.0)],
            2: [_blk(": 16 .", TOP_Y + 2), _blk("body text two", 700.0),
                _blk("footer line", 1700.0)],
            3: [_blk("17·", TOP_Y + 1), _blk("body text three", 700.0),
                _blk("footer line", 1700.0)],
            4: [_blk("18", TOP_Y), _blk("body text four", 700.0),
                _blk("footer line", 1700.0)],
        }
        got = self._tags(pages)
        self.assertEqual(got, {"1"},
                         "带装饰点的页码须与裸页码同属一个跟踪序列，"
                         "干净那页不得漏进序标真值集：%s" % got)

    def test_untracked_number_in_margin_band_survives(self):
        # 反例（防过度剔除）：p1..p3 的页码 `·15·/·16·/·17·` 随页序恒定偏移 → 页码；
        # p4 页眉带里的裸数字 7 偏移不一致（4-7=-3，只此一页）→ 仍按编号收录
        # （可能是真右缘裸排编号被 OCR 读到页眉高度）。
        pages = {
            1: [_blk("·15·", TOP_Y), _blk("(1)", 491.0, x=1450.0),
                _blk("footer line", 1700.0)],
            2: [_blk("·16·", TOP_Y), _blk("body", 400.0), _blk("footer line", 1700.0)],
            3: [_blk("·17·", TOP_Y), _blk("body", 400.0), _blk("footer line", 1700.0)],
            4: [_blk("7", TOP_Y, x=1450.0), _blk("body", 400.0),
                _blk("footer line", 1700.0)],
        }
        got = self._tags(pages)
        self.assertIn("7", got, "不随页序跟踪的边缘裸号不得被误杀：%s" % got)
        self.assertEqual(got, {"1", "7"}, "页码仍须被排除：%s" % got)

    def test_folio_norm_strips_edge_decoration_only(self):
        """归一化只剥**两端**装饰：内部分隔点与括号是编号结构，不得吃掉。

        跨书普查（2026-09-28，50 书 / 每章区间对拍）实测：把 `folio_norm` 写成
        「去全部标点」后，数值分析 ch2 的 2.4/2.5、Iwaniec ch15 的 15.10..15.12、
        随机过程 ch2/ch5 的 6.8/6.9/3.7/4.4/5.1/5.2 共 **12 个契约在账的真编号**
        归一成纯数字后撞上恒定偏移，整批从序标真值集消失 → 闸门对这些编号失明
        （漏报 = 假 PASS）。本条负向判据钉住「内部结构保留」。
        """
        from lib.numbering import folio_norm
        self.assertEqual(folio_norm("·376·"), "376")
        self.assertEqual(folio_norm(": 377 ."), "377")
        self.assertEqual(folio_norm("380·"), "380")
        self.assertEqual(folio_norm("386"), "386")
        # 🔴 内部/括号承载编号结构 → 原样保留，永远进不了「纯数字页码」候选集
        for keep in ("2.4", "15.10", "(7)", "8.11a", "11.1-1"):
            self.assertEqual(folio_norm(keep), keep,
                             "编号内部结构不得被剥掉：%r" % keep)

    def test_dotted_tag_on_consecutive_pages_is_not_a_folio(self):
        # 裸排两段式编号 1.2/1.3/1.4 依次落在 3 个连续页眉带上：值随页序 +1，
        # 若归一化去掉内部点就凑成「恒定偏移」→ 三个真编号会被当页码杀掉。
        pages = {
            1: [_blk("body", 400.0), _blk("footer line", 1700.0)],
            2: [_blk("1.2", TOP_Y, x=1450.0), _blk("body", 400.0),
                _blk("footer line", 1700.0)],
            3: [_blk("1.3", TOP_Y), _blk("body", 400.0), _blk("footer line", 1700.0)],
            4: [_blk("1.4", TOP_Y), _blk("body", 400.0), _blk("footer line", 1700.0)],
        }
        got = self._tags(pages, ncomp=2)
        self.assertEqual(got, {"1.2", "1.3", "1.4"},
                         "连续页上的裸排两段式编号不得被页码跟踪律误杀：%s" % got)

    def test_parenthesized_tag_never_read_as_folio(self):
        # 括号是编号的强信号：页码永远不写成 `(7)`，故 `(7)` 落在两族页码判据
        # （极端边缘短纯数字 / 跟踪律）里都必须豁免——归一化去点后它是纯数字，
        # 豁免只能在**原样文本**上做。
        pages = {
            1: [_blk("·15·", TOP_Y), _blk("(1)", 491.0, x=1450.0),
                _blk("footer line", 1700.0)],
            2: [_blk("·16·", TOP_Y), _blk("body", 700.0), _blk("footer line", 1700.0)],
            3: [_blk("·17·", TOP_Y), _blk("body", 700.0), _blk("footer line", 1700.0)],
            5: [_blk("(7)", 1700.0, x=1450.0), _blk("body", 700.0),
                _blk("footer line", 1700.0)],
        }
        got = self._tags(pages)
        self.assertEqual(got, {"1", "7"}, "页底带括号的编号不得被页码判据吞掉：%s" % got)

    def test_furniture_normalizes_decorated_text_itself(self):
        # 判据自带归一化：调用方传原样 OCR 文本即可，预归一化亦幂等——两侧不可能
        # 再因「一边去标点、一边只压空白」而分叉。
        from lib.numbering import page_number_furniture, folio_norm
        decorated = [(1, 138.0, 164.0, "·376·"), (2, 130.0, 159.0, ": 377 ."),
                     (3, 126.0, 153.0, "378·"), (4, 117.0, 132.0, "379")]
        keys = page_number_furniture(decorated, 1757.0)
        self.assertEqual(keys, {(1, "376"), (2, "377"), (3, "378"), (4, "379")},
                         "装饰点页码须归一后进入跟踪律")
        self.assertEqual(keys, page_number_furniture(
            [(p, y, b, folio_norm(t)) for p, y, b, t in decorated], 1757.0),
            "预归一化输入必须得到同一结果（幂等）")



if __name__ == "__main__":
    unittest.main(verbosity=2)
