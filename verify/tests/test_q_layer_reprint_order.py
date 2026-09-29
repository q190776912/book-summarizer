# -*- coding: utf-8 -*-
r"""Q 层 ORDER_MISMATCH：**原书重印同一编号**时第二次出现不得回指首次位置。

背景（第 11 处根治，2026-09-29 Apostol IANT ch3 §3.11 实测）：印面在
`(16)(17)(18)` 之后，Theorem 3.13 的推导结尾又把 identity (17) 原样重排并
**再次印出右缘 `(17)`**（物理页 79 = 印面 67；`page_079.json` block 9 独立
标签块 + fitz 300dpi 目视双证）。总结忠实挂两枚 `\tag{17}`（重复检测已由
`label_limit` 放宽 → Q:0/0/0），但顺序支拿第二枚 17 与**首次**位置（页 78
block 8）比较，而游标此时已推进到 (18)（页 78 block 26）→ 必然倒挂 → 一条
假 ORDER_MISMATCH。

修法 = 复用重复支的同一谓词 `_dup_beyond_source`（同一 `label_limit` 账，
检测与放宽永不漂移）：出现次序 ≤ 书里印过的不同页数 → 跳过比较且**不回退游标**。
`label_limit` 无记录时返回 1，故未重印的书逐字节行为不变。

负向守卫：①无重印记录时第二次出现照旧报；②出现次数超过印面次数照旧报；
③真倒挂（无重复）照旧报。
"""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

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

from verify.formula_tag.script.formula_tag import (  # noqa: E402
    _compute_order_and_section)


def _tag(n):
    return SimpleNamespace(normalized=n, latex="$$\nsum\n\\tag{%s}\n$$" % n)


class _Src:
    """最小 `SourceFormulaIndex` 替身：只暴露顺序支读取的账本。"""

    def __init__(self, union, pos_sec=None, primary=None, label_limit=None):
        self._union = set(union)
        self._pos_sec = dict(pos_sec or {})
        self._primary = dict(primary or {})
        self._limits = dict(label_limit or {})
        self._book_section = {}
        self._book_section_sec = {}
        self._n_pages = {}
        self._sec_start_page = {}
        self._walk_last_page = None

    def source_numbers(self):
        return set(self._union)

    def primary_pos(self, n):
        return self._primary.get(n)

    def book_section(self, n):
        return self._book_section.get(n)

    def label_limit(self, n, sec=None):
        return self._limits.get((sec, n), 1)


# Apostol ch3 §3.11 实测位置（页, 块序）
_POS = {('3.11', '16'): (78, 100), ('3.11', '17'): (78, 200),
        ('3.11', '18'): (78, 300), ('3.11', '19'): (79, 400)}
_TAGS = ['16', '17', '18', '17', '19']


def _sec_src(limits=None):
    return _Src([n for (_, n) in _POS], pos_sec=_POS, label_limit=limits)


class TestSectionedReprint(unittest.TestCase):
    def test_print_attested_repeat_is_not_flagged(self):
        src = _sec_src({('3.11', '17'): 2})
        om, mp = _compute_order_and_section(
            [('3.11', _tag(n)) for n in _TAGS], src, reset_on_section=True)
        self.assertEqual(om, [], "印面重印过的号，第二枚 \\tag 不是顺序错乱")
        self.assertEqual(mp, [])

    def test_repeat_without_print_record_still_flags(self):
        src = _sec_src()          # label_limit 无记录 -> 1（原严格度）
        om, _ = _compute_order_and_section(
            [('3.11', _tag(n)) for n in _TAGS], src, reset_on_section=True)
        self.assertEqual([r['number'] for r in om], ['17'],
                         "书里只印一次的号被挂第二枚 tag 仍须报（放宽不得变成盲区）")

    def test_repeat_beyond_printed_count_still_flags(self):
        src = _sec_src({('3.11', '17'): 2})
        om, _ = _compute_order_and_section(
            [('3.11', _tag(n)) for n in ['16', '17', '18', '17', '17', '19']],
            src, reset_on_section=True)
        self.assertEqual([r['number'] for r in om], ['17'],
                         "第三枚 17 超出印面两次，照旧报")

    def test_genuine_inversion_still_flags(self):
        src = _sec_src({('3.11', '17'): 2})
        om, _ = _compute_order_and_section(
            [('3.11', _tag(n)) for n in ['17', '16', '18']], src,
            reset_on_section=True)
        self.assertEqual([r['number'] for r in om], ['16'],
                         "无重复的真倒挂不受本豁免影响")


class TestPlainPathReprint(unittest.TestCase):
    def _src(self, limits=None):
        return _Src(['16', '17', '18'],
                    primary={'16': (78, 100), '17': (78, 200), '18': (78, 300)},
                    label_limit=limits)

    def test_chapter_scoped_repeat_attested(self):
        om, mp = _compute_order_and_section(
            [('3.11', _tag(n)) for n in ['16', '17', '18', '17']],
            self._src({(None, '17'): 2}), reset_on_section=False)
        self.assertEqual(om, [])
        self.assertEqual(mp, [])

    def test_chapter_scoped_repeat_unattested(self):
        om, _ = _compute_order_and_section(
            [('3.11', _tag(n)) for n in ['16', '17', '18', '17']],
            self._src(), reset_on_section=False)
        self.assertEqual([r['number'] for r in om], ['17'])


if __name__ == "__main__":
    unittest.main(verbosity=2)
