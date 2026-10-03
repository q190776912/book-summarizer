# -*- coding: utf-8 -*-
r"""B 层「无标签习题序列按契约类型独立开窗」判据回归（2026-10-02 Katok 根治）。

实测：Katok《Modern Theory》每节后段的习题**不冠任何标签词**，直接印成裸号条头
（`2.9.1.` / `3.1.6*.`，fitz 目视 + 契约 `book_structure/ch2.json` §2.9 三个
`type: "exercise"` 节点为证），而该书条目计数器**跨类型共享且按节重启**
（`Definition 2.9.1` → `Theorem 2.9.2` → … 单一 ordinal 组）。于是 `**Definition 2.9.1**`
与 `**2.9.1.**` 是**两条不同的印刷序列**，旧的「按条头标签词路由 ex 窗」判据在裸号头
上读不到标签 → 两序列并成一窗 → 全书 81 条「疑似幽灵重复节点」WARN（同号二现
[1,2,3]）。该 WARN 正是 B 层区分「重复节点伪影」与「真条目错位 BLOCKING」的那一支，
把真序列碰撞说成伪影 = 错位信号被稀释。

修法 = 让**契约类型**（标签无关的真值）参与路由，且分两步：
  `_exercise_window_routing` 只把「裸号 + 契约登记为习题」的头列为**候选**，
  `_resolve_bare_ex_candidates` 再按「同号二现」碰撞决定要不要真开窗——因为
  Weibel 类书每节只有一条 1..N 共享计数器，裸号头本身就是序列成员，只按契约类型
  抢先开窗会把主窗挖成假缺号（跨书普查 2026-10-02：Weibel ch1–10 BLOCKING 0→79）。

本测试断言正反两侧：
  1. 裸号头 + 契约登记为 exercise → 成为候选；同窗有具名同号头时才进 ex 窗；
  2. 带习题标签词的头照旧进 ex 窗（原行为不回退）；
  3. 五道守卫逐个挡住：uncat 合并计数器（Vakil）/ 共享计数器（Lee、Etingof）/
     共享下同形的 Problem（stays_main）/ 无节前缀（`gi:file` 窗）/
     条头里本有习题词、只是被行首 `\*` 挡住解析（两步法管辖，Intro ch3 实测）；
  4. 裸号头但该键**不在**契约习题窗里（= 条目序列的裸号）必须留在主窗，
     否则就是「靠放宽判据把真缺号洗掉」。
"""
import json
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
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot  # noqa: E402
_boot.setup()

from verify.item_numbering_integrity.script.item_numbering_integrity import (  # noqa: E402
    _exercise_window_routing, _norm_ex_key_form, _contract_exercise_keys,
    _resolve_bare_ex_candidates)


def _route(label, prefix_str, key, ex_keys, **kw):
    kw.setdefault('combined', False)
    kw.setdefault('shared', False)
    kw.setdefault('stays_main', False)
    return _exercise_window_routing(label, prefix_str, key, ex_keys, **kw)


def _E(gk, num, key, label='Definition'):
    """一条 entries 记录（6 元组，与扫描循环同形）。"""
    return (gk, num, key, label, gk.split(':', 1)[1] if ':' in gk else '', False)


class TestKeyForm(unittest.TestCase):
    def test_contract_key_to_md_key_form(self):
        self.assertEqual(_norm_ex_key_form('2.9.1'), '2.9-1')
        self.assertEqual(_norm_ex_key_form('3.1.6'), '3.1-6')
        self.assertEqual(_norm_ex_key_form('12.1'), '12-1')

    def test_never_invents_a_number(self):
        for s in ('问题1', 'Example A', '', None, 'abc'):
            self.assertEqual(_norm_ex_key_form(s), (s or '').strip() if s else '')


class TestRouting(unittest.TestCase):
    def test_bare_head_with_contract_exercise_is_candidate(self):
        """裸号头只成为**候选**：开窗与否由碰撞判据（TestCollision）决定，
        因为裸号没有自证身份的标签词。"""
        routed, bare = _route('uncat', '2.9', '2.9-1', {'2.9-1', '2.9-2'})
        self.assertFalse(routed)
        self.assertTrue(bare)

    def test_labelled_exercise_head_still_routes_without_contract(self):
        """原行为：契约读不到（空集）时，带标签的习题头照旧开窗。"""
        routed, bare = _route('exercise', '2.9', '2.9-1', set())
        self.assertTrue(routed)
        self.assertFalse(bare)
        routed2, _ = _route('习题', '3.1', '3.1-3', None)
        self.assertTrue(routed2)

    def test_bare_head_not_in_contract_stays_main(self):
        """条目序列的裸号（契约里不是习题）绝不能被挪进 ex 窗——
        挪走就等于把该号从主序列里抹掉，真缺号会被洗白。"""
        routed, bare = _route('uncat', '2.9', '2.9-4', {'2.9-1', '2.9-2'})
        self.assertFalse(routed)
        self.assertFalse(bare)

    def test_entry_label_with_exercise_key_stays_main(self):
        """`Definition 2.9.1` 与裸 `2.9.1` 是两条序列：带条目标签的头按标签走，
        不得因为「该号在契约习题窗里」就被抢进 ex 窗。"""
        routed, _ = _route('definition', '2.9', '2.9-1', {'2.9-1'})
        self.assertFalse(routed)

    def test_demoted_word_head_is_not_a_bare_candidate(self):
        """Intro-to-Dynamical-Systems ch3 实测：`**\\*习题 3.2.2.**` 行首难度标记
        挡住标签解析 → label 落 'uncat'，但条头**确实写着**习题词。该头归两步法
        （`_resolve_demoted_entries`）按习题词所在组回补真习题窗；裸号腿抢先就会
        把它并进内容组的 `0:ex:3.2`，真习题窗 `1:ex:3.2` 反被挖出假「缺号 2」
        （跨书普查里该单元 BLOCKING 0→1）。"""
        routed, bare = _route('uncat', '3.2', '3.2-2', {'3.2-2'},
                              demoted_word=True)
        self.assertFalse(routed)
        self.assertFalse(bare)

    def test_guards_block_extra_window(self):
        ex = {'2.9-1'}
        # Vakil：uncat 合并计数器，练习本身就是主序列成员
        self.assertFalse(_route('exercise', '2.9', '2.9-1', ex, combined=True)[0])
        self.assertFalse(_route('uncat', '2.9', '2.9-1', ex, combined=True)[1])
        # Lee / Etingof：共享计数器。带习题标签词的头由调用方折算进 `stays_main`
        # （`_shared and label is exercise-ish`），裸号头由本函数的 `shared` 守卫
        # 挡住——两条路径都必须留在主窗，否则定理号全被报成「练习缺号」。
        self.assertFalse(_route('exercise', '2.9', '2.9-1', ex, shared=True,
                               stays_main=True)[0])
        self.assertFalse(_route('uncat', '2.9', '2.9-1', ex, shared=True)[1])
        # 共享计数器下同形的 Problem 留在主窗
        self.assertFalse(_route('problem', '2.9', '2.9-1', ex, stays_main=True)[0])
        self.assertFalse(_route('uncat', '2.9', '2.9-1', ex, stays_main=True)[1])
        # 无节前缀 → gk 是 `gi:file` 形态，另开窗会被 body 读成 prefix='file'
        routed, bare = _route('uncat', '', '2.9-1', ex)
        self.assertFalse(routed)
        self.assertFalse(bare)


class TestCollision(unittest.TestCase):
    """裸号头的开窗**必须**由「同号二现」碰撞决定（跨书普查 2026-10-02）。"""

    def test_colliding_bare_head_moves_to_ex_window(self):
        """Katok：具名头 `Definition 2.9.1` 与裸号头同窗同号 → 裸号头并入 ex 窗，
        两窗各自连续（幽灵重复 WARN 的正解）。"""
        entries = [_E('0:2.9', 1, '2.9-1'), _E('0:2.9', 2, '2.9-2'),
                   _E('0:2.9', 1, '2.9-1', 'uncat'),
                   _E('0:2.9', 2, '2.9-2', 'uncat'),
                   _E('0:2.9', 3, '2.9-3', 'uncat')]
        pending = [(2, '0:2.9', '2.9-1'), (3, '0:2.9', '2.9-2'),
                   (4, '0:2.9', '2.9-3')]
        out = _resolve_bare_ex_candidates(entries, pending)
        self.assertEqual(out[2][0], '0:ex:2.9')
        self.assertEqual(out[3][0], '0:ex:2.9')
        # 2.9-3 无具名头占号（条目序列止于 2）→ 留在主窗，不制造假缺号
        self.assertEqual(out[4][0], '0:2.9')
        # 具名头一律不动
        self.assertEqual(out[0][0], '0:2.9')
        self.assertEqual(out[1][0], '0:2.9')

    def test_weibel_shared_counter_bare_heads_all_stay(self):
        """Weibel：每节只有一条 1..N 共享计数器，裸号头无同号具名头 → 全部留在
        主窗。改前判据只看契约类型就开窗，普查里 ch1–10 一次 BLOCKING 0→79。"""
        entries = [_E('0:10.2', 1, '10.2-1'), _E('0:10.2', 2, '10.2-2'),
                   _E('0:10.2', 3, '10.2-3', 'uncat'),
                   _E('0:10.2', 4, '10.2-4')]
        pending = [(2, '0:10.2', '10.2-3')]
        out = _resolve_bare_ex_candidates(entries, pending)
        self.assertEqual([e[0] for e in out],
                         ['0:10.2', '0:10.2', '0:10.2', '0:10.2'])

    def test_no_pending_is_noop(self):
        entries = [_E('0:2.9', 1, '2.9-1')]
        self.assertEqual(_resolve_bare_ex_candidates(entries, []), entries)

    def test_other_window_collision_does_not_move(self):
        """碰撞必须同窗：`0:2.9` 的裸号头不因 `0:2.10` 里的同号具名头被搬走。"""
        entries = [_E('0:2.10', 1, '2.10-1'),
                   _E('0:2.9', 1, '2.9-1', 'uncat')]
        out = _resolve_bare_ex_candidates(entries, [(1, '0:2.9', '2.9-1')])
        self.assertEqual(out[1][0], '0:2.9')

    def test_two_bare_heads_do_not_collide_with_each_other(self):
        """碰撞对象必须是**具名**头：两个裸号候选同号不算二现（都没有自证身份），
        谁也不开窗——否则「两个裸号谁进 ex 窗」由顺序决定，判据不稳定。"""
        entries = [_E('0:2.9', 1, '2.9-1', 'uncat'),
                   _E('0:2.9', 1, '2.9-1', 'uncat')]
        out = _resolve_bare_ex_candidates(
            entries, [(0, '0:2.9', '2.9-1'), (1, '0:2.9', '2.9-1')])
        self.assertEqual([e[0] for e in out], ['0:2.9', '0:2.9'])



class TestContractReader(unittest.TestCase):
    """`_contract_exercise_keys` 必须按磁盘契约取真值，且读不到时 fail-soft。"""

    def _write_contract(self, ext, name, root):
        d = os.path.join(ext, 'book_structure')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, name), 'w', encoding='utf-8') as f:
            json.dump(root, f, ensure_ascii=False)

    def test_reads_exercise_and_problem_skips_consolidated(self):
        """契约真值形态：习题节点的内容块挂在 ``sub_sec`` 里（顶层带 ``text`` 的
        dict 会被 ``exercise_node_windows`` 当成**内容块**跳过，不是节点）。"""
        ext = tempfile.mkdtemp()

        def ex(k, t='exercise', consolidated=False):
            n = {'key': k, 'type': t, 'name': 'stem', 'page_start': 10,
                 'page_end': 10, 'sub_sec': [{'type': 'text', 'text': 'q'}]}
            if consolidated:
                n['consolidated'] = True
            return n
        root = {'key': '9', 'type': 'chapter', 'sub_sec': [
            {'key': '9.1', 'type': 'section', 'sub_sec': [
                ex('9.1.1'),
                ex('9.1.2', consolidated=True),
                ex('9.1.3', 'problem'),
                ex('9.1.4', 'definition'),
            ]},
        ]}
        self._write_contract(ext, 'ch9.json', root)
        self.assertEqual(_contract_exercise_keys(ext, 9), {'9.1-1', '9.1-3'})

    def test_fail_soft_without_contract(self):
        self.assertEqual(_contract_exercise_keys(None, 9), set())
        self.assertEqual(_contract_exercise_keys(tempfile.mkdtemp(), 9), set())
        self.assertEqual(_contract_exercise_keys(tempfile.mkdtemp(), None), set())


if __name__ == '__main__':
    unittest.main()
