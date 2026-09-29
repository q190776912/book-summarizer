# -*- coding: utf-8 -*-
r"""Q 层 MISPLACED（scope==3）的**证据驱动**判据回归。

背景（第 10 处根治，2026-09-29 Apostol IANT ch5 / Lee ch7 实测）：
旧写法 `flagged = not in_range`，而 `in_range = bool(rng) and any(...)` 把
「该节页跨未知」（节游标从未推进 → `_sec_start_page` 只有首节）与「该号在全书
无位置记录」（只作回指出现，或来自 `formula.known_book` 白名单）都算成
`not in_range = True`，于是**证据缺失 = 有罪**：Apostol ch5 24 条 `\tag` 全章
刷 MISPLACED、Lee ch7 16 条同形。ORDER 支早有相反约定（「某 tag 无节内位置
记录时跳过该 tag 的顺序判定」），plain MISPLACED 支也是 `bsec is not None` 才判，
本节级路径是唯一的例外。

修法 = 三段式：① `(sec,n) ∈ _pos_sec`（书趟自身同意，块序能分辨页内起头）→ 放过；
② 回退用整页跨度 `[start(sec), start(next)]`（**含**下一节起始页——页级粒度定不了
页内起点，Apostol 页顶书眉 `5.4: 节名` 早于本节最后一式 (8)）；
③ 两种证据都缺 → **不判**。

负向守卫：真放错（有节跨、有在册页、页页越界、且无节内位置记录）必须仍报。
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
    _compute_order_and_section, _section_page_range)


def _tag(n, latex="$$\nx\n$$\n"):
    return SimpleNamespace(normalized=n, latex=latex)


class _Src:
    """最小 `SourceFormulaIndex` 替身：只暴露判据实际读取的账本。"""

    def __init__(self, union, sec_start=None, n_pages=None, pos_sec=None,
                 walk_last=None):
        self._union = set(union)
        self._sec_start_page = dict(sec_start or {})
        self._n_pages = {k: set(v) for k, v in (n_pages or {}).items()}
        self._pos_sec = dict(pos_sec or {})
        self._walk_last_page = walk_last
        self._book_section = {}
        self._book_section_sec = {}

    def source_numbers(self):
        return set(self._union)

    def primary_pos(self, n):
        return None

    def book_section(self, n):
        return self._book_section.get(n)


class TestNoEvidenceNeverFlags(unittest.TestCase):
    def test_section_without_start_page_is_skipped(self):
        """③ 页跨未知（游标卡在首节）≠ 放错——旧写法在此开报，即全章刷屏之源。"""
        src = _Src(['1', '2'], sec_start={'5.1': 118}, n_pages={'2': [123]})
        om, mp = _compute_order_and_section(
            [('5.3', _tag('2'))], src, reset_on_section=True)
        self.assertEqual(mp, [], "无节起始页证据必须跳过，不得判 MISPLACED")
        self.assertEqual(om, [])

    def test_number_without_any_page_record_is_skipped(self):
        """known_book 白名单号 / 只作回指出现的号：全书无位置记录 → 无从判定位。"""
        src = _Src(['9'], sec_start={'5.1': 120, '5.2': 125})
        mp = _compute_order_and_section([('5.2', _tag('9'))], src,
                                        reset_on_section=True)[1]
        self.assertEqual(mp, [])


class TestBookAgreementIsStrongestEvidence(unittest.TestCase):
    def test_pos_sec_membership_overrides_out_of_span_pages(self):
        """① 书趟把 (n) 归在**同一**节桶里（块序能分辨页内起头）→ 书与总结同判。

        页跨记到的 `[5,6]` 属于另一处同名号的独立标签；本节桶里的位置记录才是
        该号在此节的定义点。旧写法只看页跨，会因边界页落外而误报。
        """
        src = _Src(['8'], sec_start={'5.3': 122, '5.4': 125},
                   n_pages={'8': [125]}, pos_sec={('5.3', '8'): (125, 215.0)})
        mp = _compute_order_and_section([('5.3', _tag('8'))], src,
                                        reset_on_section=True)[1]
        self.assertEqual(mp, [], "趟自身已把该号归入该节，不得再判挂错节")

    def test_boundary_page_counts_inside_span(self):
        """② 回退页跨**含**下一节起始页：页级粒度无法定位页内起点。"""
        src = _Src(['9'], sec_start={'5.4': 125, '5.5': 126},
                   n_pages={'9': [126]})
        self.assertEqual(_section_page_range(src, '5.4'), (125, 126))
        mp = _compute_order_and_section([('5.4', _tag('9'))], src,
                                        reset_on_section=True)[1]
        self.assertEqual(mp, [], "号印在下一节起始页的页顶（属上一节尾）不得判错位")


class TestRealMisplacementStillFlags(unittest.TestCase):
    """负向：放宽只吃掉「无证据」，真放错必须一条不流失。"""

    def test_number_clearly_outside_section_span_still_flagged(self):
        src = _Src(['3'],
                   sec_start={'5.1': 118, '5.2': 122, '5.3': 126, '5.4': 130},
                   n_pages={'3': [133]})
        om, mp = _compute_order_and_section([('5.2', _tag('3'))], src,
                                            reset_on_section=True)
        self.assertEqual([r['number'] for r in mp], ['3'],
                         "号确实只在别节页出现过 → 必须仍报 MISPLACED")
        self.assertEqual(om, [])

    def test_out_of_span_with_foreign_pos_sec_still_flagged(self):
        """趟把该号归在**别**的节 → 位置记录不构成豁免。"""
        src = _Src(['7'],
                   sec_start={'5.1': 118, '5.2': 125, '5.3': 131, '5.4': 137},
                   n_pages={'7': [140]}, pos_sec={('5.4', '7'): (140, 300.0)})
        mp = _compute_order_and_section([('5.2', _tag('7'))], src,
                                        reset_on_section=True)[1]
        self.assertEqual([r['number'] for r in mp], ['7'])

    def test_in_span_hit_exempts(self):
        src = _Src(['4'], sec_start={'5.1': 118, '5.2': 122},
                   n_pages={'4': [120, 131]})
        mp = _compute_order_and_section([('5.1', _tag('4'))], src,
                                        reset_on_section=True)[1]
        self.assertEqual(mp, [], "范围内有命中即视为放置正确（旧判据同款）")


class TestIgnoreStillSilences(unittest.TestCase):
    def test_scoped_ignore_key_skips(self):
        src = _Src(['3'], sec_start={'5.1': 118, '5.2': 122, '5.3': 130},
                   n_pages={'3': [140]})
        mp = _compute_order_and_section([('5.2', _tag('3'))], src,
                                        reset_on_section=True,
                                        scoped_ignore={('5.2', '3')})[1]
        self.assertEqual(mp, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
