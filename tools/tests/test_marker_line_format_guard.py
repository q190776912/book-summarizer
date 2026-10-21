"""test_marker_line_format_guard.py — 整文件格式重写**不得碰首行单元标记**的回归。

首行 `<!-- book-summarizer DONE unit: id=… type=… key=… name=… -->` 是本侧
`manifest.json` 记录的逐字抄本（判据 12 的对账面）。它同时又是文件里唯一「长得像正文」
的一行 —— 任何整文件正则重写（定界符归一 / 裸 Unicode 字形包 `$…$`）扫到它，就会把
题名改成契约与 manifest 里都不存在的形态：实测 Fraleigh《A First Course in Abstract
Algebra》一本 550 处、全库 1129 处脱账全属此类（正文一字节未变，纯首行被顺手改过）。

锁两件事：
1. `lib.unit_markers.outside_marker` 保住首行（含 CRLF），正文照改；无标记时不许吞功能；
2. `tools/_wrap_raw_math.py` 的 `process()` 把标记行整行加入保护集。

Run with stdlib unittest:
    python tools/tests/test_marker_line_format_guard.py
"""
import os
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from lib.unit_markers import outside_marker, is_unit_marker_line  # noqa: E402
from lib.normalize_math import normalize  # noqa: E402
import _wrap_raw_math as wrm  # noqa: E402

MARK = "<!-- book-summarizer DONE unit: id=0007 type=desc key=$D_1$ name=1.3 Example 的 ∈ 记法 -->"


class TestOutsideMarker(unittest.TestCase):
    def test_marker_line_survives_while_body_is_fixed(self):
        # 正文里的 backtick 数学是 normalize() 的靶子；标记行里同样有靶子，必须原样留着
        text = MARK + "\n正文 $\\xi_1$ 与 `\\xi_1` 同义。\n"
        out = outside_marker(text, normalize)
        self.assertEqual(out.split("\n")[0], MARK)
        self.assertNotIn("`\\xi_1`", out.split("\n", 1)[1])

    def test_crlf_marker_line_kept_byte_identical(self):
        text = MARK + "\r\n\r\n> **定义**：`\\alpha` 是字母。\r\n"
        out = outside_marker(text, normalize)
        self.assertTrue(out.startswith(MARK + "\r\n"), "CRLF 首行被改坏")
        self.assertNotIn("`\\alpha`", out)

    def test_plain_file_still_fully_processed(self):
        """没有标记的文件（章 md / 普通片段）不许因为守卫而少改。"""
        text = "标题\n`\\beta` 要变成数学。\n"
        out = outside_marker(text, normalize)
        self.assertEqual(out, normalize(text))

    def test_marker_recognizer(self):
        self.assertTrue(is_unit_marker_line(MARK))
        self.assertTrue(is_unit_marker_line("<!-- book-summarizer DRAFT unit: "
                                            "id=1 type=item key=1.1 name=x -->"))
        self.assertFalse(is_unit_marker_line("# 第1章 标题"))


class TestWrapRawMathGuard(unittest.TestCase):
    def _unit(self, d, marker, body):
        p = os.path.join(d, "u.md")
        with open(p, "w", encoding="utf-8", newline="") as f:
            f.write(marker + "\n" + body)
        return p

    def test_bare_glyph_in_marker_untouched_body_wrapped(self):
        marker = ("<!-- book-summarizer DONE unit: id=0002 type=desc key=D1 "
                  "name=1.1 设 a ∈ R 且 a ≥ 0 -->")
        with tempfile.TemporaryDirectory() as d:
            p = self._unit(d, marker, "正文：设 a ∈ R 且 a ≥ 0。\n")
            wrm.process(p)
            with open(p, encoding="utf-8") as f:   # 默认 newline：统一掉 EOL，只比首行内容
                first, rest = f.read().split("\n", 1)
        self.assertEqual(first, marker, "标记行被批量重写=判据 12 集体脱账的成因")
        self.assertIn("$\\in$", rest)
        self.assertIn("$\\ge$", rest)

    def test_non_marker_file_still_wrapped_on_line_one(self):
        with tempfile.TemporaryDirectory() as d:
            p = self._unit(d, "# 第1章 设 a ∈ R", "\n正文 a ∈ R。\n")
            wrm.process(p)
            with open(p, encoding="utf-8") as f:
                got = f.read()
        self.assertIn("$\\in$", got.split("\n", 1)[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
