# -*- coding: utf-8 -*-
"""Regression: 首行标记内含多余 `-->` 必须 FAIL（do Carmo 黎曼几何 ch12/ch3/ch8，2026-09-27）。

翻译代理照旧例把 line-1 `name=` 里的 Unicode 箭头（OCR 常成 `-→`）改写成 ASCII，
于是 HTML 注释在名字中途就闭合。`_OUT_RE` 非贪婪 `name=(.*?) -->` 匹配到**第一个**
`-->` 为止，而 gate 与 merge 都取 `raw[m.end():]` 当正文 → 行尾残句成了正文第一行。
残句常不足 8 词，「未翻译散文」阈值放行，最后随 merge 落进终稿 md（实测 ch12 0011/0017/
0018、ch3 0007、ch8 0016/0023 六处）。marker 行本身从不进 F 层裸箭头检查
（`check_unit_quality` 先 pop 掉前导注释行），所以「必须改成 ASCII」的旧判据是错的。

锁死：line-1 出现第二个 `-->` → `_marker_leak_reason` 报因；逐字箭头 / 只改
DRAFT→DONE 的 marker 不得报。
"""
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, *[os.pardir] * 4))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402

lib.boot.setup()

import gate_units  # noqa: E402  (boot.setup 已把 script 目录注入 sys.path)


def _write(text):
    fd, path = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return path


class MarkerLeakGate(unittest.TestCase):
    def test_leaked_ascii_arrow_in_name_fails(self):
        p = _write(
            "<!-- book-summarizer DONE unit: id=0011 type=item key=定义2.5 "
            "name=定义2.5 2.5 DEFINITION. An isometry f: M --> M without fixed points is -->\n"
            "**定义 2.5**: 正文。\n"
        )
        try:
            self.assertIn("残句会漏成正文", gate_units._marker_leak_reason(p))
        finally:
            os.remove(p)

    def test_verbatim_unicode_arrow_passes(self):
        p = _write(
            "<!-- book-summarizer DONE unit: id=0011 type=item key=定义2.5 "
            "name=定义2.5 2.5 DEFINITION. An isometry f: M -→ M without fixed points is -->\n"
            "**定义 2.5**: 正文。\n"
        )
        try:
            self.assertEqual(gate_units._marker_leak_reason(p), "")
        finally:
            os.remove(p)

    def test_draft_marker_still_single_close(self):
        p = _write(
            "<!-- book-summarizer DRAFT unit: id=0001 type=chapter key=11 name=11 -->\n"
            "正文。\n"
        )
        try:
            self.assertEqual(gate_units._marker_leak_reason(p), "")
        finally:
            os.remove(p)

    def test_non_marker_line_passes(self):
        p = _write("普通正文 A --> B --> C\n")
        try:
            self.assertEqual(gate_units._marker_leak_reason(p), "")
        finally:
            os.remove(p)


if __name__ == "__main__":
    unittest.main()
