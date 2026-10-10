# -*- coding: utf-8 -*-
r"""Q 层 ORDER_MISMATCH（scope==3 每节重启）的**独立编号锚点**门回归。

背景（2026-10-09 Evans ch9 根治 + 全库 scope==3 普查）：
per-section 书里某号 `(n)` 在一节内可能出现多次——一次真正的**定义标签**（右缘
独立成块 `(1)`）与若干**回指**（散文里 `(1) onto …`、句末被 OCR 切成独立块的
`(1).`）。ORDER 支拿 `_pos_sec[(sec,n)]`（该号在节内的**最早**命中位置）当顺序
游标；旧写法无论这枚位置出自定义标签还是回指都照用。Evans ch9 两处假阳全源于此：

* §9.1：真定义 `(1)` 印在章首「目录+首节正文」混合页 p539，被整页跳过；节内最早
  命中的是 p541 把句中回指粘成行首块的 `(1) onto the finite-dimensional …`。
  总结忠实的 `(1)→(2)` 于是被判 `(2)` 倒挂（(2)@540 早于回指 (1)@541）。
* §9.1/§9.2 边界页 p545：页顶**书眉**「9.2. FIXED POINT METHODS」把节游标提前，
  使 §9.1 尾巴（含句末回指 `(1).`、显示号 (21)）误归 §9.2。总结 `(21)→(1)` 于是
  被判 `(1)` 倒挂（回指 (1)@545 y337 早于 (21)@545 y1377，真 Banach `(1)` 在 p546）。

修法（新增门，仅作用于 scope==3 节级路径的 ORDER 支，MISPLACED/FABRICATED/MISSING
三支与 plain 支一字未动）：在 `_pos_sec` 写入点同步登记 `_pos_sec_standalone[(sec,n)]`
=「这枚锚定位置是否出自**纯独立编号块**（整块=一枚 `(N)`，且不带句末标点）」。ORDER
支遇该号节内锚点**非**纯独立块时，既不判倒挂、也不回退游标（`prev_pos` 不动）——与
plain 支既有的 `_pos_strong`「纯散文回指不当定义位置、不判序」同一 fail-open 约定，
只是分节支的强弱落在 per-(sec,n) 的**形态**上。🔴 门控在「src 真带该账本」上：真
`SourceFormulaIndex` 恒有 `_pos_sec_standalone`；无该属性的旧测试替身保持原行为。

判据单调：本门只会**少报**（跳过不可信锚点），绝不新增 MISPLACED/ORDER；真倒挂
（两个相邻锚点都是纯独立编号）照判。跨书普查（census_q_order）实测 ADDED=0。
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
    _compute_order_and_section, SourceFormulaIndex)


def _tag(n, latex="$$\nx\n$$\n"):
    return SimpleNamespace(normalized=n, latex=latex, raw_tag="(%s)" % n)


class _Src:
    """最小 `SourceFormulaIndex` 替身：只暴露 ORDER 判据实际读取的账本。
    `standalone=None` 时**不设置** `_pos_sec_standalone` 属性（模拟旧替身 /
    门控惰性 → OLD 行为）；给定 dict 时按之登记（NEW 生效）。"""

    def __init__(self, union, pos_sec=None, standalone=None,
                 sec_start=None, n_pages=None, walk_last=None):
        self._union = set(union)
        self._pos_sec = dict(pos_sec or {})
        if standalone is not None:
            self._pos_sec_standalone = dict(standalone)
        self._sec_start_page = dict(sec_start or {})
        self._n_pages = {k: set(v) for k, v in (n_pages or {}).items()}
        self._walk_last_page = walk_last
        self._book_section = {}
        self._book_section_sec = {}
        self._full_keys = set()

    def source_numbers(self):
        return set(self._union)

    def primary_pos(self, n):
        return None

    def book_section(self, n):
        return self._book_section.get(n)


STARTS = {'9.1': 100, '9.2': 110, '9.3': 120, '9.4': 130}
WALK_LAST = 140


class TestMergedProseAnchorSkipped(unittest.TestCase):
    """行首粘连回指 / 句末标点回指都不是定义顺序锚点 → 跳过、不判倒挂。"""

    def test_backref_head_anchor_does_not_pollute_cursor(self):
        # 复刻 Evans §9.1：`(1)` 锚在把句中回指粘成行首块的 (541,981)（standalone
        # =False），`(2)` 是真独立标签 (540,367)。总结顺序 1→2。旧写法会因
        # (2)@540 早于回指 (1)@541 而误判 (2) 倒挂。
        src = _Src(['1', '2'],
                   pos_sec={('9.1', '1'): (541, 981.0),
                            ('9.1', '2'): (540, 367.0)},
                   standalone={('9.1', '1'): False, ('9.1', '2'): True},
                   sec_start=STARTS, walk_last=WALK_LAST,
                   n_pages={'1': [541], '2': [540]})
        om = _compute_order_and_section(
            [('9.1', _tag('1')), ('9.1', _tag('2'))], src, set(),
            reset_on_section=True)[0]
        self.assertEqual([r['number'] for r in om], [],
                         "不可信回指锚点既不判倒挂也不推进游标 → 忠实 1→2 不被误报")

    def test_evans_sec92_period_sentence_ref_skipped(self):
        # 复刻 Evans §9.1/§9.2 边界：书眉提前使 §9.1 尾巴 (21) 与句末回指 (1).
        # 误归 §9.2。总结顺序 21→1。(1). 带句点 → standalone=False（不可信）；
        # 旧写法因回指 (1)@545 y337 早于 (21)@545 y1377 而误判 (1) 倒挂。
        src = _Src(['1', '21'],
                   pos_sec={('9.2', '21'): (545, 1377.0),
                            ('9.2', '1'): (545, 337.0)},
                   standalone={('9.2', '21'): True, ('9.2', '1'): False},
                   sec_start=STARTS, walk_last=WALK_LAST,
                   n_pages={'1': [545], '21': [545]})
        om = _compute_order_and_section(
            [('9.2', _tag('21')), ('9.2', _tag('1'))], src, set(),
            reset_on_section=True)[0]
        self.assertEqual([r['number'] for r in om], [],
                         "句末标点回指不作顺序锚点 → 忠实 21→1 不被误报")


class TestGenuineStandaloneInversionStillFlagged(unittest.TestCase):
    """负向守卫：两个相邻锚点都是纯独立编号的真倒挂照判，一条不吞。"""

    def test_standalone_vs_standalone_inversion_flagged(self):
        # 总结顺序 1→2，但书里 (1) 定义在 (558,500)、(2) 定义在 (556,200)：
        # (2) 阅读顺序早于 (1) → 真倒挂。两锚点皆 standalone=True → 必判。
        src = _Src(['1', '2'],
                   pos_sec={('9.3', '1'): (558, 500.0),
                            ('9.3', '2'): (556, 200.0)},
                   standalone={('9.3', '1'): True, ('9.3', '2'): True},
                   sec_start=STARTS, walk_last=WALK_LAST,
                   n_pages={'1': [558], '2': [556]})
        om = _compute_order_and_section(
            [('9.3', _tag('1')), ('9.3', _tag('2'))], src, set(),
            reset_on_section=True)[0]
        self.assertEqual([r['number'] for r in om], ['2'],
                         "两纯独立标签的真顺序倒挂不得被独立锚点门吞掉")


class TestMonotonicityAndGatePresence(unittest.TestCase):
    """单调性 + 门控惰性：门只可能少报；账本缺失的旧替身保持 OLD 行为。"""

    def test_gate_inert_when_ledger_absent(self):
        # 同 §9.1 fixture，但不给 `_pos_sec_standalone`（旧替身）→ 门惰性 →
        # OLD 行为恢复：回指污染游标 → (2) 仍被误判倒挂。证明门确以账本存在为前提。
        src = _Src(['1', '2'],
                   pos_sec={('9.1', '1'): (541, 981.0),
                            ('9.1', '2'): (540, 367.0)},
                   standalone=None,   # 无账本
                   sec_start=STARTS, walk_last=WALK_LAST,
                   n_pages={'1': [541], '2': [540]})
        self.assertFalse(hasattr(src, '_pos_sec_standalone'),
                         "替身不应带账本")
        om = _compute_order_and_section(
            [('9.1', _tag('1')), ('9.1', _tag('2'))], src, set(),
            reset_on_section=True)[0]
        self.assertEqual([r['number'] for r in om], ['2'],
                         "无账本时逐字节回到 OLD（(2) 被回指顶成倒挂）")

    def test_never_adds_relative_to_no_ledger(self):
        """对同一批位置数据，NEW(带账本) 报出的号集 ⊆ OLD(无账本)。"""
        fixtures = [
            (['1', '2'], {('9.1', '1'): (541, 981.0), ('9.1', '2'): (540, 367.0)},
             {('9.1', '1'): False, ('9.1', '2'): True},
             [('9.1', '1'), ('9.1', '2')]),
            (['1', '21'], {('9.2', '21'): (545, 1377.0), ('9.2', '1'): (545, 337.0)},
             {('9.2', '21'): True, ('9.2', '1'): False},
             [('9.2', '21'), ('9.2', '1')]),
            (['1', '2'], {('9.3', '1'): (558, 500.0), ('9.3', '2'): (556, 200.0)},
             {('9.3', '1'): True, ('9.3', '2'): True},
             [('9.3', '1'), ('9.3', '2')]),
        ]
        for union, pos_sec, standalone, order in fixtures:
            tags = [(s, _tag(n)) for (s, n) in order]
            src_new = _Src(union, pos_sec=pos_sec, standalone=standalone,
                           sec_start=STARTS, walk_last=WALK_LAST,
                           n_pages={n: [int(p[0])] for n, p in pos_sec.items()})
            src_old = _Src(union, pos_sec=pos_sec, standalone=None,
                           sec_start=STARTS, walk_last=WALK_LAST,
                           n_pages={n: [int(p[0])] for n, p in pos_sec.items()})
            new_set = {r['number'] for r in _compute_order_and_section(
                tags, src_new, set(), reset_on_section=True)[0]}
            old_set = {r['number'] for r in _compute_order_and_section(
                tags, src_old, set(), reset_on_section=True)[0]}
            self.assertTrue(new_set <= old_set,
                            "NEW 不得新增 OLD 未报的 ORDER：%s (new=%s old=%s)"
                            % (pos_sec, new_set, old_set))

    def test_plain_branch_untouched(self):
        # reset_on_section=False（scope==1/2）：本门完全不参与（其门控是 _pos_strong，
        # 另一支）。给一个 plain 顺序数据，确保不因新账本改变判定。
        src = _Src(['1', '2'], pos_sec={}, standalone={('9.1', '1'): False},
                   sec_start=STARTS, walk_last=WALK_LAST)
        # plain 支 primary_pos 返回 None → cur None → 无比较 → 无告警（与门无关）
        om = _compute_order_and_section(
            [('9.1', _tag('1')), ('9.1', _tag('2'))], src, set(),
            reset_on_section=False)[0]
        self.assertEqual(om, [], "plain 支不受 scope==3 独立锚点门影响")


class TestStandaloneLabelBlockPredicate(unittest.TestCase):
    """形态判据单测：纯独立编号 vs 粘连回指 / 句末标点 / 节头 / 空。"""

    def test_pure_labels_are_standalone(self):
        for t in ['(1)', '（2）', ' (3) ', '(8a)', '(11.3.10)', '(21)']:
            self.assertTrue(SourceFormulaIndex._is_standalone_label_block(t),
                            "纯独立编号应判 True: %r" % t)

    def test_non_label_or_reference_blocks_rejected(self):
        for t in ['(1).', '（1）。', '(1) onto the finite-dimensional subspace',
                  '9.2. FIXED POINT METHODS', 'solution of (1).', '', '   ',
                  'see (2) above']:
            self.assertFalse(SourceFormulaIndex._is_standalone_label_block(t),
                             "带尾点/含散文/节头/空块不应作锚点: %r" % t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
