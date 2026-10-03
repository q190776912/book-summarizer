# -*- coding: utf-8 -*-
r"""B 层「打星裸号条头」判据回归（2026-10-02 Katok《现代动力系统导论》实测）。

背景：Katok 把较难习题印刷为带星号序标（`3.1.6*`）。总结里写成粗体 + LaTeX 转义
星号 `**3.1.6\***.`，而 `_SPAN_RE`（非贪婪 `\*\*(.+?)\*\*`）把 `\*` 的星号吞进
闭合 `**` 里 —— 真正传进 `_parse_entry` 的 inner 只剩 `3.1.6\`。旧裸号分支只做
`rstrip('.．。')`，认不下这个尾巴，于是该条目对 B 层**完全隐身**：

    §3.1 印 9 题（1..9，其中 6、9 打星）→ B 层只看到 7 条 → 假 BLOCKING
    「0:ex:3.1 缺号 6（序列 1..7 不连续）」；§3.3 的 3.3.4 同理。

内容并未缺失（契约有 3.1.6/3.1.9/3.3.4 节点，manifest 有对应单元，md 有题面），
所以放行方向与 O 层既有的「带星习题」判据同源（`test_subitem_continuity_starred`）：
**难度星号永远不是条目隐身的理由**。放宽只发生在「尾部纯粹是星号残段」这一形态上。

负向守卫（缺一不可，否则就是「靠放宽判据刷绿」）：
  · 两级书的裸号仍不成条目（星号不改变 levels 门槛）；
  · 前导星 / 纯星号 span 仍一律拒绝；
  · 内部星（`3.1*6`）不得被当成尾巴剥掉；
  · 无星裸号（Vakil 无标题条目 `3.2.1.`、Kreyszig `1.5-4`）逐字节行为不变。
"""
import os
import re
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
import lib.boot as _boot  # noqa: E402
_boot.setup()

from verify.item_numbering_integrity.script.item_numbering_integrity import (  # noqa: E402
    _parse_entry, _bare_head_core, _SPAN_RE)


class TestStarredBareHead(unittest.TestCase):

    def test_real_md_line_inner_is_backslash_only(self):
        """印面 `3.1.6*` → md `**3.1.6\\***.`：先证明 inner 真的是 `3.1.6\\`。"""
        line = '**3.1.6\\***. Show that the growth is exponential'
        m = _SPAN_RE.search(line)
        self.assertIsNotNone(m)
        self.assertEqual(m.group(1).strip(), '3.1.6\\')
        self.assertEqual(_parse_entry(m.group(1).strip(), 3, 'en'),
                         ([3, 1, 6], 'uncat'))

    def test_star_tail_variants_all_parse(self):
        for inner in (r'3.1.6\*', r'3.1.6*', r'3.1.6\*.', r'3.1.6\***',
                      r'3.1.6 \*', r'1.5-4\*', r'3.1.6\*\* '):
            got = _parse_entry(inner, 3, 'en')
            self.assertEqual(got[1], 'uncat', inner)
            self.assertIn(got[0], ([3, 1, 6], [1, 5, 4]), inner)

    def test_label_first_starred_head_unchanged(self):
        r"""带标签的星号头走的是原路径（`_is_header_boundary` 早认 `\`），逐字节不变。"""
        self.assertEqual(_parse_entry(r'Exercise 13.3.3\*', 3, 'en'),
                         ([13, 3, 3], 'Exercise'))
        self.assertEqual(_parse_entry(r'习题 13.3.3\*', 3, 'cn'),
                         ([13, 3, 3], '习题'))

    def test_plain_bare_heads_unchanged(self):
        """无星裸号（Vakil 无标题条目 / Kreyszig 裸键）行为必须一字不差。"""
        self.assertEqual(_parse_entry('3.2.1.', 3, 'en'), ([3, 2, 1], 'uncat'))
        self.assertEqual(_parse_entry('1.5-4', 3, 'en'), ([1, 5, 4], 'uncat'))
        self.assertEqual(_bare_head_core('3.2.1.'), '3.2.1')
        self.assertEqual(_bare_head_core('1.5-4'), '1.5-4')

    def test_two_level_bare_head_still_rejected(self):
        """星号不得把两级书裸号抬成条目（原 levels==3 门槛仍在）。"""
        for inner in (r'3.1\*', '3.1', r'1.5-4'):
            self.assertIsNone(_parse_entry(inner, 2, 'en'), inner)

    def test_leading_and_pure_star_rejected(self):
        for inner in (r'\*3.1.6', r'\*', '*', r'\*\*', '   ', r'*3.1.6'):
            self.assertIsNone(_parse_entry(inner, 3, 'en'), inner)

    def test_internal_star_not_stripped(self):
        """星号只有**成尾**才是难度标记；夹在号里的不得被剥开冒充条目。"""
        self.assertEqual(_bare_head_core(r'3.1*6'), r'3.1*6')
        self.assertIsNone(_parse_entry(r'3.1*6', 3, 'en'))

    def test_bare_core_only_touches_star_tail(self):
        """`_bare_head_core` 的剥离集必须只含 反斜杠 / 星号 / 空白 / 句点。"""
        for s in ('4.1-1 例', r'4.1-1 \*', '4.1-1.', r'4.1-1.'):
            self.assertIn(_bare_head_core(s), ('4.1-1 例', '4.1-1'))
        # 分隔符型尾（下划线/波浪线在 SEP_TIGHT 里）不得被当成星号尾巴
        self.assertNotEqual(_bare_head_core('4.1-1_'), '4.1-1')


if __name__ == '__main__':
    unittest.main()
