# -*- coding: utf-8 -*-
r"""Q 层 MISPLACED（scope==3 每节重启）的**重启复用感知**跳过回归。

背景（2026-10-09 Evans 根治 + 全库 scope==3 普查）：
per-section 书里裸号 `(1)` 在每个 `## §N.M` 都重启一次，`_n_pages['1']` 是全书
**所有节**里独立印出的 `(1)` 标签页的并集——它天生无法指认「总结这枚 `\tag{1}`
属于哪一节」。旧判据（Apostol/Lee 三段式证据门之后）仍会在「本节点页跨 `[start,
start(next)]` 内没有该号页、但该号在别处别节印过」时开报 MISPLACED：Evans 中文侧
ch2/ch4/ch5/ch6/ch8 共 7 条 `\tag` 全为此类假阳（裸号复用 + 页级粒度定不了归属）。

修法（新增第 5 段，仅作用于 scope==3 节级路径，FABRICATED/MISSING/ORDER 三支不动）：
当该号的独立标签页**横跨 ≥ 2 个不同的总结节页跨**（`_spanned_section_count >= 2`）
时，页证据无法把归属缩到唯一节 = 「无法证明放错」→ 跳过不判（与既有「无证据不判」
同一 fail-open 约定）。真放错在编号**唯一属于一个页跨**（多分量号 `(2.5.12)`、
`(8.11a)`，或恰好只出现在一节的裸号）时照判，一条不流失。判据单调：新支只会**少报**，
绝不新增 MISPLACED。

跨书普查（census，20 本 scope==3 + 3 本 scope==2 控制）实测：helper 命中 6221 次，
OLD 会报 7 条、NEW 报 0 条、ADDED=0、7 条被移除的全是 spanned>=2、0 条真错位被吞、
scope==2 控制调用 0 次。本测试固化这套语义。
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
    _compute_order_and_section, _reset_on_section_misplaced,
    _spanned_section_count)


def _tag(n, latex="$$\nx\n$$\n"):
    return SimpleNamespace(normalized=n, latex=latex, raw_tag="(%s)" % n)


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


# 四节页跨把 100..140 铺满：9.1[100,110] 9.2[110,120] 9.3[120,130] 9.4[130,140]
STARTS = {'9.1': 100, '9.2': 110, '9.3': 120, '9.4': 130}
WALK_LAST = 140


class TestRecurrenceSkipRemovesFalsePositive(unittest.TestCase):
    """裸号横跨 ≥2 节页跨 → 无唯一归属证据 → 不判（旧判据的假阳之源）。"""

    def test_bare_number_reused_across_two_spans_is_skipped(self):
        # `(1)` 只在 9.1 页(105) 与 9.4 页(135) 独立印出；总结把 `\tag{1}` 挂在 9.3。
        # 9.3 自己的页跨 [120,130] 内没有 1 的页 → 旧三段式证据门会开报。
        src = _Src(['1'], sec_start=STARTS, walk_last=WALK_LAST,
                   n_pages={'1': [105, 135]})
        self.assertGreaterEqual(_spanned_section_count(src, '1'), 2,
                                "该号应被识别为跨 >=2 节复用")
        mp = _compute_order_and_section([('9.3', _tag('1'))], src,
                                        reset_on_section=True)[1]
        self.assertEqual(mp, [], "裸号复用无唯一归属证据必须跳过，不得判 MISPLACED")

    def test_evans_style_multiple_bare_tags_all_skipped(self):
        # 复刻 Evans ch5 中文侧的 `{3,8}` / ch4 的 `{11,19}`：每枚都是跨节复用裸号。
        for n in ('3', '8', '11', '19'):
            src = _Src([n], sec_start=STARTS, walk_last=WALK_LAST,
                       n_pages={n: [101, 137]})
            mp = _compute_order_and_section([('9.2', _tag(n))], src,
                                            reset_on_section=True)[1]
            self.assertEqual(mp, [], "%s 跨节复用应跳过" % n)


class TestGenuineMisplacementStillFlags(unittest.TestCase):
    """负向守卫：跳过只吃掉「跨节复用无归属」，编号唯一属于一个页跨的真放错照判。"""

    def test_unique_multicomponent_in_foreign_span_still_flagged(self):
        # `(9.4.2)` 只在 9.4 页(135) 出现；总结把它挂在 9.2 → 号唯一属一节，归属明确。
        src = _Src(['9.4.2'], sec_start=STARTS, walk_last=WALK_LAST,
                   n_pages={'9.4.2': [135]})
        self.assertEqual(_spanned_section_count(src, '9.4.2'), 1,
                         "多分量号只落一个页跨")
        om, mp = _compute_order_and_section([('9.2', _tag('9.4.2'))], src,
                                            reset_on_section=True)
        self.assertEqual([r['number'] for r in mp], ['9.4.2'],
                         "唯一归属 + 挂错节 → 必须仍报 MISPLACED")
        self.assertEqual(om, [])

    def test_bare_unique_to_one_span_out_of_section_still_flagged(self):
        # 阈值精确：裸号若恰好只出现在**一个**页跨(105∈9.1)、却被挂到 9.3，
        # spanned==1 → 不满足复用豁免 → 仍判。
        src = _Src(['5'], sec_start=STARTS, walk_last=WALK_LAST,
                   n_pages={'5': [105]})
        self.assertEqual(_spanned_section_count(src, '5'), 1)
        mp = _compute_order_and_section([('9.3', _tag('5'))], src,
                                        reset_on_section=True)[1]
        self.assertEqual([r['number'] for r in mp], ['5'],
                         "spanned==1 的越界号是真错位，不得被复用豁免吞掉")


class TestMonotonicityAndGuards(unittest.TestCase):
    """单调性 + 既有豁免：复用支只可能少报，且自述/节内桶优先。"""

    def test_helper_never_adds_relative_to_pre_recurrence_rule(self):
        """对同一批 fixture，逐条比较 OLD(无复用段) vs NEW：NEW 判真 ⇒ OLD 必判真。"""
        fixtures = [
            ('1', {'1': [105, 135]}, '9.3'),       # OLD 真 → NEW 假（复用跳过）
            ('5', {'5': [105]}, '9.3'),            # OLD 真 → NEW 真（spanned==1）
            ('9.4.2', {'9.4.2': [135]}, '9.2'),    # OLD 真 → NEW 真（多分量唯一）
            ('9.3.7', {'9.3.7': [135]}, '9.3'),    # 自述 → 两支都假
        ]
        for n, n_pages, sec in fixtures:
            src = _Src([n], sec_start=STARTS, walk_last=WALK_LAST,
                       n_pages=n_pages)
            old_flagged = not _old_exempt(src, sec, n)
            new_flagged = _reset_on_section_misplaced(
                src, sec, n, n.startswith(sec + '.'))
            if new_flagged:
                self.assertTrue(old_flagged,
                                "NEW 判真时 OLD 必判真（不得新增 MISPLACED）：%s@%s"
                                % (n, sec))


    def test_self_reported_still_exempt(self):
        src = _Src(['9.3.7'], sec_start=STARTS, walk_last=WALK_LAST,
                   n_pages={'9.3.7': [135]})
        mp = _compute_order_and_section([('9.3', _tag('9.3.7'))], src,
                                        reset_on_section=True)[1]
        self.assertEqual(mp, [], "自述节号(中段=本节)一律豁免")

    def test_pos_sec_bucket_still_overrides(self):
        src = _Src(['1'], sec_start=STARTS, walk_last=WALK_LAST,
                   n_pages={'1': [105, 135]},
                   pos_sec={('9.3', '1'): (122, 90.0)})
        mp = _compute_order_and_section([('9.3', _tag('1'))], src,
                                        reset_on_section=True)[1]
        self.assertEqual(mp, [], "节内桶命中(块序证据)优先于复用判断，直接放过")


def _old_exempt(src, sec, n):
    """OLD（Apostol/Lee 三段式、无复用段）的「放过」判据；取反即 OLD 是否开报。"""
    from verify.formula_tag.script.formula_tag import _section_page_range
    if n.startswith(sec + '.'):                 # 自述
        return True
    if getattr(src, '_pos_sec', {}).get((sec, n)) is not None:  # 节内桶
        return True
    rng = _section_page_range(src, sec)
    npages = getattr(src, '_n_pages', {}).get(n) or set()
    if rng is None or not npages:               # 无证据
        return True
    return any(rng[0] <= p <= rng[1] for p in npages)  # 本节点跨命中


if __name__ == "__main__":
    unittest.main(verbosity=2)
