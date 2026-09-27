"""判据：图检测须忽略「章开页的超大独占章号数字」，不得裁成插图。

缺陷根因（Apostol《Introduction to Analytic Number Theory》实测 2026-09-28）：
p169（ch8 开页）与 p261（ch12 开页）各被 DocLayout-YOLO 以 conf 0.49/0.53 框出
一个「插图」，裁图内容就是章号本身（一张只印着 "8" 的图）。这类图会以
`chNN_unnamed_K.png` 身份进入 figure_index，写章时按「未标号图」嵌入笔记——
读者看到的是凭空多出的一个数字。

修复形态：`extract_figures.is_display_numeral_box` —— 框内 OCR 文本**恰好**是一个
1-3 位数字（真插图/数字表框内必然还有文字，拼接后不可能只剩一个数）且框心位于
页面上部，即判为章号数字、不裁不登记。

正向：真实开页数据（p169 的 "8" / p261 的 "12" / p141 的 "6"）→ 判为数字。
负向：①真插图框（内含 "Triangular:/10/15/…/Figure 1.1" 多块文本）→ 不判；
      ②框内只有一个坐标数字的**真图**（p70 Figure 3.1，数字块占框面积 0.2%）
        → 不判（首版判据在此误杀，见 is_display_numeral_box 判据 ③）；
      ③框内是 4 位年份 "2024" → 不判（避免误杀照片里的数字）；
      ④同样的单数字框落在页面下半部 → 不判（上部带是开页章号的必要条件）。
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
    _ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

from flows.script.extract_figures import is_display_numeral_box  # noqa: E402

PAGE_H = 2340  # 200-DPI A4 高


def _it(text, x0, y0, x1, y1):
    return {"text": text, "poly": [x0, y0, x1, y0, x1, y1, x0, y1]}


# 实测：p169 章号 "8" 与检测框
P169 = [_it("Periodic Arithmetical Functions", 200, 173, 800, 210),
        _it("8", 882, 158, 979, 308),
        _it("and Gauss Sums", 200, 228, 700, 270),
        _it("8.1 Functions periodic modulo k", 190, 775, 700, 800)]
BOX_169 = (872, 165, 976, 313)

# 实测：p261 章号 "12"
P261 = [_it("The Functions", 200, 159, 700, 200),
        _it("12", 778, 152, 967, 312),
        _it("(s) and L(s, x)", 200, 209, 700, 250)]
BOX_261 = (784, 158, 966, 308)

# 实测：p14 真插图（三角数/平方数/五边形数点阵 + 图题）
P14 = [_it("Triangular:", 191, 723, 290, 754),
       _it("10", 505, 814, 533, 837),
       _it("15", 667, 814, 697, 837),
       _it("Figure 1.1", 531, 1326, 646, 1359)]
BOX_14 = (182, 687, 975, 1357)

# 实测：p141（ch6 开页）章号 "6"
P141 = [_it("Finite Abelian Groups and", 200, 170, 800, 210),
        _it("6", 869, 159, 975, 306),
        _it("Their Characters", 200, 320, 700, 360)]
BOX_141 = (869, 159, 975, 306)

# 实测：p70 Figure 3.1（qd 点阵图）。页内其余标签走公式通道，text 里只剩坐标
# 数字 "1" —— 首版判据（只看框内文本是不是数字）把它误杀，故锁死为回归用例。
P70 = [_it("1", 519, 522, 539, 532)]
BOX_70 = (292, 149, 887, 722)


class DetectsNumeral(unittest.TestCase):
    def test_real_opener_numerals_are_filtered(self):
        self.assertTrue(is_display_numeral_box(P169, BOX_169, PAGE_H))
        self.assertTrue(is_display_numeral_box(P261, BOX_261, PAGE_H))
        self.assertTrue(is_display_numeral_box(P141, BOX_141, PAGE_H))


class KeepsRealFigures(unittest.TestCase):
    def test_figure_with_text_blocks_is_not_a_numeral(self):
        self.assertFalse(is_display_numeral_box(P14, BOX_14, PAGE_H))

    def test_real_figure_with_one_stray_digit_inside_is_kept(self):
        """回归（首版误杀）：p70 Figure 3.1 框内只有一个坐标数字，
        数字块仅占框面积 0.2% → 判据 ③ 必须放行。"""
        self.assertFalse(is_display_numeral_box(P70, BOX_70, PAGE_H))

    def test_four_digit_year_is_not_a_numeral(self):
        items = [_it("2024", 700, 160, 900, 300)]
        self.assertFalse(is_display_numeral_box(items, (690, 150, 910, 310), PAGE_H))

    def test_bare_number_low_on_page_is_not_the_opener_numeral(self):
        """负向：页心的孤立数字（题号/表头）不满足上部带条件。"""
        items = [_it("8", 882, 1400, 979, 1550)]
        self.assertFalse(is_display_numeral_box(items, (872, 1395, 990, 1560), PAGE_H))

    def test_no_ocr_data_fails_open(self):
        """无 OCR 数据时不做任何推断（宁可留图不误删）。"""
        self.assertFalse(is_display_numeral_box([], BOX_169, PAGE_H))
        self.assertFalse(is_display_numeral_box(P169, BOX_169, 0))


if __name__ == "__main__":
    unittest.main()
