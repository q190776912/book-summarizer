"""test_long_row_check.py — F 层 long_formula_rows（显示公式行过长）检测。

Run with stdlib unittest:
    python verify/tests/test_long_row_check.py
"""
import os
import sys
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

import unittest
from verify.format_verify.script.long_row_check import (
    check_long_formula_rows, vis_len)


class LongRowCheckTest(unittest.TestCase):
    def test_vis_len_ignores_commands_and_braces(self):
        # \\frac 命令名与花括号不计；空格计入（不影响"相对长度"排序）
        self.assertEqual(vis_len(r'\frac{a}{b} + c'), 6)

    def test_flags_only_long_tagged_display_rows(self):
        md = [
            '# T',
            '',
            '$$',
            '\\begin{aligned}',
            'a &= b + c \\\\',
            'x &= y + z + w + p + q + r + s + t + u + v + k + l + m + n + o + 1 + 2 + 3 + 4 + 5 + 6 + 7 + 8 + 9 \\\\',
            '\\end{aligned}',
            '\\tag{1.1}',
            '$$',
            '',
            'untagged long row has no tag so not reported:',
            '$$',
            'x = y + z + w + p + q + r + s + t + u + v + k + l + m + n + o + 1 + 2 + 3 + 4',
            '$$',
        ]
        finds = check_long_formula_rows(md, max_vis=40)
        # 只命中带 tag 的 (1.1) 块内超长行
        self.assertEqual(len(finds), 1, finds)
        self.assertIn('1.1', finds[0])

    def test_short_rows_not_flagged(self):
        md = ['$$', 'x = y + z', '\\tag{1.2}', '$$']
        self.assertEqual(check_long_formula_rows(md, max_vis=100), [])


if __name__ == '__main__':
    unittest.main()
