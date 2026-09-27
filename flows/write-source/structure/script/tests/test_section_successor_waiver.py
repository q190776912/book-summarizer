# -*- coding: utf-8 -*-
"""「序位豁免」回归测试（Etingof《Introduction to representation theory》实测）。

该书节题**本身就是成句散文**，被两条散文形态守卫整节否决：
  * 小写连词动词闸 —— "1.1 What is representation theory?"（系词 `is`）
  * 句中句界守卫 —— "3.6 Unitary representations. Another proof of Maschke's
    theorem for complex representations"（句中句号 + 小写连跑 + 超长）
契约与骨架因此双双漏掉 §1.1 / §3.6 两整节，且 D 层与抽取器同源、报
`missing sections = 0`（假绿）。

豁免判据 = 该行编号恰为「本章上一个节号 +1」。本测试同时钉住**负例**：
无序位证据（`successor_num` 缺省或不匹配）时两条守卫照旧拦截，
其余书零回归。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import scan_skeleton as S  # noqa: E402

DEPTHS = {1, 2, 3}
Q_LINE = '1.1 What is representation theory?'
SENT_LINE = ("3.6  Unitary representations. Another proof of Maschke's "
             "theorem for complex")
# Kreyszig 章首编号导语（原守卫的实测负例）
INTRO_LINE = ('1.6. Another concept of theoretical and practical interest '
              'is separability')


def _info(ln, ch, succ):
    return S._section_header_info(ln, ch=ch, depths=DEPTHS, successor_num=succ)


def test_successor_waives_prose_guards():
    assert _info(Q_LINE, 1, '1.1') == ('1.1', 2, 'What is representation theory?')
    got = _info(SENT_LINE, 3, '3.6')
    assert got is not None and got[0] == '3.6'


def test_without_successor_still_rejected():
    assert _info(Q_LINE, 1, None) is None
    assert _info(SENT_LINE, 3, None) is None


def test_non_matching_successor_still_rejected():
    # 跳号（散文粘连行不可能恰为下一个节号）→ 守卫照旧。
    assert _info(Q_LINE, 1, '1.2') is None
    assert _info(SENT_LINE, 3, '3.11') is None


def test_expected_next_sec_chaining():
    assert S._expected_next_sec(None, 1) == '1.1'
    assert S._expected_next_sec('1.1', 1) == '1.2'
    assert S._expected_next_sec('4.24.3', 4) == '4.24.4'
    assert S._expected_next_sec('2-2', 2) == '2-3'
    assert S._expected_next_sec(None, None) is None


def test_intro_prose_still_caught_when_not_expected():
    # 该导语行只有在「恰为下一个节号」时才可能放行——Kreyszig 真节头
    # 印作 "1.6 The Hilbert Space l2"，序位锚点由先出现的真节头建立。
    assert _info(INTRO_LINE, 1, '1.7') is None
    assert _info(INTRO_LINE, 1, None) is None


if __name__ == '__main__':
    for _n, _f in sorted(globals().items()):
        if _n.startswith('test_'):
            _f()
            print('ok', _n)
