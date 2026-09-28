"""全局单号节书（`sections_global`）的「幻一节头」闸。

缺陷现场（Arnold《经典力学的数学方法》中译本，2026-09-28 structure 步骤实测）：
印刷把节头 `§N．标题` **居中**排印、并把当前/下一节的节名**重复印在每页页眉**；
OCR 把页眉行与其下的正文行粘成一行，命中 `SEC_GLOBAL_GLUE`（数字 + 直接粘连
汉字）→ 发出假 SEC 行 → build_structure 落成假节节点：

    ch1  p19  '4黄上成事件堂宙A4电的平移构成一大重宝同八：'   （§4 真身在 ch2 p26）
    ch2  p34  '22平面上就给出了所求的轨道，称为利萨如图形.'
    ch8  p174 '2n个数组成 T*V上点的局部坐标.'
    ch9  p210 '9光线的方向'            （x0=1024，图版右侧碎片，标题形态完全正常）
    ch10 p232 '2n个常微分方程'         （正文「化为 2n 个常微分方程」的断行）

闸门据此报「节序逆序」BLOCKING（§3 排在 §4 之后 …），7/26 章卡死。

判据（`scan_skeleton._global_sec_intruders` + `_sec_title_shaped`）：
  ① 体例事实：全局 § 号全书严格递增 ⇒ 一章（连续页区间）内按阅读序取出的单号
     § 序列也必须严格递增；
  ② 硬冲突：某号**不在任何**极大严格递增子序列（LIS）上 ⇒ 剔除它才能使保留节数
     严格变多 → 无条件剔除（②式信号与标题形态无关，ch9/ch10 靠它）；
  ③ 平局：LIS 长度相等的二选一时，只剔除**余文不成标题**的一方（句中子句标点
     ，,；;？！ / 收尾句读 . 。 ： / 以标点运算符起头）；双方都像标题 ⇒ 一个都
     不剔除，把歧义留给闸门与人工；
  ④ 剔除后把被幻影带偏的裸字母子块父键（`<幻影号>.<字母>`）按页码重挂到该页
     之前最近的真节，章内无前置真节时退化为无父键（与附录字母头同型）。

负例守住的回归面：本书真节头必须照样收录；谷超豪《数学物理方程》式**粘连**真节头
（GLUE 是其主通道）不得被动；页眉同号复本（一个号出现多次）不得被当成冲突；
合法的跳号（OCR 吞掉一个真节头）不得触发任何剔除；非 `sections_global` 书逐字节
零回归。

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_global_sec_intruder_heads.py
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
import lib.boot as _boot
_boot.setup()

import scan_skeleton as S


def _mk_pages(d, pages):
    """pages = [[block_text, ...], ...] -> page_001.json（块无 poly：宽度/y 守卫
    按 None 放行，与 test_numeric_local_sections 同构）。"""
    for i, blocks in enumerate(pages, start=1):
        fp = os.path.join(d, f"page_{i:03d}.json")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"text": [{"text": b} for b in blocks], "formulas": []}, f)


def _sec(rows, kind='SEC'):
    """(该行的 键, 标题) 列表，按阅读序。"""
    return [(str(r[2]), str(r[3])) for r in rows if r[1] == kind]


def _keys(rows, kind='SEC'):
    return [k for k, _t in _sec(rows, kind)]


class TestTitleShape(unittest.TestCase):
    """判据③的标题形态：真节题通过，正文残句/页眉粘连句不通过。"""

    def test_real_titles_shaped(self):
        for t in ['力学系的例子', '具二自由度的力学系', '流形上的辛构造',
                  '庞加莱-嘉当积分不变量', '作用量-角变量', 'n质点力学系的运动',
                  '方程的导出、定解条件',          # 顿号是并列，不是子句标点
                  '变分法', 'Phase Spaces', '1 相对性原理和决定性原理']:
            self.assertTrue(S._sec_title_shaped(t), t)

    def test_prose_residue_not_shaped(self):
        for t in ['黄上成事件堂宙A4电的平移构成一大重宝同八：',   # 收尾冒号
                  '平面上就给出了所求的轨道，称为利萨如图形.',   # 句中逗号 + 尾点
                  'n个数组成 T*V上点的局部坐标.',               # 收尾句点（正文句）
                  '，故得证', '.3 个自由度', '', '   ']:
            self.assertFalse(S._sec_title_shaped(t), repr(t))


class TestIntruderRule(unittest.TestCase):
    """纯函数判据：阅读序号序列 -> 应剔除的号集合。"""

    def test_book_cases(self):
        # ch1：平局（[1,2,4] 与 [1,2,3] 同为极大）→ 只杀不成标题的 4
        self.assertEqual(S._global_sec_intruders(
            [(1, '相对性原理和决定性原理'), (2, '伽利略群和牛顿方程'),
             (4, '黄上成事件堂宙A4电的平移构成一大重宝同八：'),
             (3, '力学系的例子')]), {4})
        # ch2：22 不在任何极大 LIS 上（硬冲突），且余文不成标题
        self.assertEqual(S._global_sec_intruders(
            [(4, '具一自由度的力学系'), (5, '具二自由度的力学系'),
             (22, '平面上就给出了所求的轨道，称为利萨如图形.'),
             (6, '保守力场'), (7, '角动量'), (8, '在有心力场中的运动的研究'),
             (9, '三维空间中质点的运动'), (10, 'n质点力学系的运动'),
             (11, '相似性方法')]), {22})
        # ch8 / ch9 / ch10：硬冲突，标题形态正常也必须杀（判据②）
        self.assertEqual(S._global_sec_intruders(
            [(37, '流形上的辛构造'), (2, 'n个数组成 T*V上点的局部坐标.'),
             (38, '哈密顿相流及其积分不变量')]), {2})
        self.assertEqual(S._global_sec_intruders(
            [(44, '庞加莱-嘉当积分不变量'), (45, '推论'), (46, '惠更斯原理'),
             (9, '光线的方向'), (47, '哈密顿-雅可比方法'), (48, '生成函数')]), {9})
        self.assertEqual(S._global_sec_intruders(
            [(49, '可积方程组'), (50, '作用量-角变量'), (2, 'n个常微分方程'),
             (51, '平均化'), (52, '摄动的平均化')]), {2})

    def test_monotone_book_sequence_untouched(self):
        # 负例：本书真节序（§44..§48，粘连形态的真头）一个都不能掉
        seq = [(44, '庞加莱-嘉当积分不变量'), (45, '庞加莱一嘉当积分不变量的推论'),
               (46, '惠更斯原理'), (47, '求积哈密顿典则方程的哈密顿-雅可比方法'),
               (48, '生成函数')]
        self.assertEqual(S._global_sec_intruders(seq), set())
        # 判据③的歧义保守性：两条同形态的散文碎片不得被顺手删除
        self.assertEqual(S._global_sec_intruders(
            [(10, '守恒律'), (11, '对称群'), (3, '一个合法标题'), (4, '另一个合法标题')]),
            set())

    def test_legit_gap_and_duplicate_copies_untouched(self):
        # OCR 吞掉 §5（合法跳号）：序列仍单调 → 不裁决
        self.assertEqual(S._global_sec_intruders(
            [(4, '具一自由度的力学系'), (6, '保守力场'), (7, '角动量')]), set())
        # 页眉同号复本（一个号出现多次，标题形态各异）：不得判成冲突
        self.assertEqual(S._global_sec_intruders(
            [(1, '相对性原理'), (2, '伽利略群和牛顿方程'),
             (2, '伽利略群和牛顿方程'), (3, '力学系的例子')]), set())
        # 空/单元素清单
        self.assertEqual(S._global_sec_intruders([]), set())
        self.assertEqual(S._global_sec_intruders([(7, '角动量')]), set())

    def test_non_numeric_keys_ignored(self):
        # 字母节键（附录升格行）与点分小节键不参与本闸
        self.assertEqual(S._global_sec_intruders(
            [('A', '记号'), ('B', '左不变度量'), ('F', '黎曼曲率')]), set())


class TestScanEndToEnd(unittest.TestCase):
    """`scan(sections_global=True)` 端到端：幻影不进骨架，真节与子块不受伤。"""

    def _scan(self, d, n, ch=1, glob=True):
        return S.scan(d, ch, 1, n, 'two-level', chapter_first=True,
                      sections_global=glob)

    def test_ch1_phantom_dropped_real_sections_kept(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ['第一章 运动学的研究',
                 '§1．相对性原理和决定性原理',
                 '一切物理现象都按照一定的规律发生.'],
                ['$2．伽利略群和牛顿方程',
                 'A.坐标',
                 '4黄上成事件堂宙A4电的平移构成一大重宝同八：',
                 'B.伽利略变换'],
                ['$3．力学系的例子',
                 '考察由n个质点组成的力学系.'],
            ])
            rows = self._scan(d, 3)
            ks = _keys(rows)
            self.assertEqual([k for k in ks if k.isdigit()], ['1', '2', '3'],
                             '幻影 §4 必须被剔除，真节按阅读序全部保留')
            subs = _keys(rows, 'SUB')
            self.assertIn('2.A', subs)     # 幻影之前：父键本就是 2
            self.assertIn('2.B', subs)     # 幻影之后：父键由 '4.B' 重挂回 2
            self.assertNotIn('4.B', subs)

    def test_hard_intruder_dropped_clean_title(self):
        # ch10 现场：幻影标题形态完全正常，仅凭单调性硬冲突剔除
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ['§49．可积方程组', '正文行。'],
                ['$50.作用量-角变量', '2n个常微分方程', '变量I称为作用量变量；'],
                ['§51．平均化'],
            ])
            ks = _keys(self._scan(d, 3, ch=10))
            self.assertEqual([k for k in ks if k.isdigit()], ['49', '50', '51'])

    def test_gu_chaohao_glued_heads_untouched(self):
        # 谷超豪《数学物理方程》：GLUE 是**主通道**，粘连真头一律不得被动
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ['1方程的导出、定解条件', '设有一根弹性弦。'],
                ['2叠加原理'],
                ['3初边值问题的分离变量法'],
                ['4二阶线性偏微分方程的分类'],
            ])
            ks = _keys(self._scan(d, 4, ch=1))
            self.assertEqual([k for k in ks if k.isdigit()], ['1', '2', '3', '4'])

    def test_non_global_books_zero_regression(self):
        # 同一批页面（含非单调的单号 GLUE 序列）：
        #  * `sections_global=True` 时本闸剔掉幻影 4；把闸置空则幻影留在骨架里
        #    → 证明剔除动作**只**出自本闸；
        #  * `sections_global=False`（其余一切书）时，收与不收完全一致
        #    → 本闸的 post-pass 对非全局书逐字节 inert。
        pages = [
            ['§1．相对性原理和决定性原理'],
            ['$2．伽利略群和牛顿方程', '4黄上成事件堂宙A4电的平移构成一大重宝同八：'],
            ['$3．力学系的例子'],
        ]
        orig = S._global_sec_intruders
        try:
            with tempfile.TemporaryDirectory() as d:
                _mk_pages(d, pages)
                guarded = self._scan(d, 3, glob=True)
                S._global_sec_intruders = lambda seq: set()
                plain_glob = self._scan(d, 3, glob=True)
                guarded_off = self._scan(d, 3, glob=False)
                S._global_sec_intruders = lambda seq: {int(x) for x in ()}
                guarded_noglob = self._scan(d, 3, glob=False)
        finally:
            S._global_sec_intruders = orig
        self.assertEqual([k for k in _keys(guarded) if k.isdigit()],
                         ['1', '2', '3'])
        self.assertIn('4', [k for k in _keys(plain_glob) if k.isdigit()],
                      'without the guard the phantom is still emitted')
        self.assertEqual(guarded_off, guarded_noglob,
                         'non-global books must not be touched by the guard')


if __name__ == '__main__':
    unittest.main(verbosity=2)
