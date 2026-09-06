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
    check_long_formula_rows, vis_len, row_metrics, rendered_rows)


class LongRowCheckTest(unittest.TestCase):
    def test_vis_len_ignores_commands_and_braces(self):
        # 命令名与花括号不计；`\frac{a}{b}` 分子分母是**竖向堆叠** → 宽度取
        # max(a, b)=1 而非 a+b=2（旧口径按横向累加，会高估矩阵/分式宽度）。
        # 故 `\frac{a}{b} + c` = frac(1) + ' + '(2) = 3。
        self.assertEqual(vis_len(r'\frac{a}{b} + c'), 3)

    def test_vis_len_counts_symbols_not_zero(self):
        # 旧口径把 \sum / \int 等命令整条删掉（计 0，低估）；现按 1 个字形计。
        self.assertEqual(vis_len(r'\sum a'), 2)

    def test_measures_rendered_row_not_source_line(self):
        # 🔴 回归用例：一个渲染行被折成多行书写时，逐源码行测量会漏报。
        # 一个渲染行跨 4 行源码书写（行尾才出现 \\）
        md = [
            '$$',
            '\\begin{aligned}',
            'x &= \\sum_{m=1}^{\\infty} U^{t}\\phi(y)',
            '\\begin{bmatrix} a \\\\ b \\end{bmatrix}',
            '= \\sum \\exp(\\lambda t)\\,\\phi(z)',
            '\\begin{bmatrix} c \\\\ d \\end{bmatrix} \\\\',
            'y &= z',
            '\\end{aligned}',
            '\\tag{18.11}',
            '$$',
        ]
        widest_source_line = max(
            vis_len(ln) for ln in md[2:-3] if ln.strip())
        row_w = max(row_metrics(r)[0] for r in rendered_rows('\n'.join(md[1:-2])))
        # 整行渲染宽度显著大于"最长源码行"——旧口径量的是后者，故漏报
        self.assertGreater(row_w, widest_source_line)
        # 阈值取 15：整行(≈25)超标被抓，而最长源码行(≈13)不超标
        # → 若退回"逐源码行"测量，下面这条断言就会变成 0 而失败
        self.assertEqual(len(check_long_formula_rows(md, max_vis=15)), 1)
        self.assertEqual(len(check_long_formula_rows(md, max_vis=60)), 0)

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
