r"""形态②「块尾标签左侧」判据的**空白维**回归（Kreyszig 判据夹具 2026-09-29 实测）。

缺陷现场：`_tail_pre_guard` 此前把「剥完尾随空白后的左邻末字符是数字」一刀切拒收，
于是 Kreyszig 型右缘标签
    '3.1-1 Theorem. We define a = 1 (1).'
    'A second relation b = 2 (2).'
（式子以**数字**收尾、编号隔一个空白）全部落空 ⇒ 节级路径的源编号集 S 变空 ⇒
  * 正例章 `q_rows` 只剩「书源公式编号未抽到」WARN（happy path 非 OK），
  * 反作弊例「删光 `\tag` 仍须 q_missing 非空」失效（S 空 ⇒ 无缺失可报）——
    即**收紧判据把反作弊闸拆了**。

判据（`_tail_pre_guard` 吃**未剥空白**的左邻原文）：
  ① 印刷标签与式子之间必有空白：与括号**黏着**的左邻字符是字母/数字/CJK/`\`
     （`c_1(2)`、`SO(3)`、`f(x)`、`式(3)`、`\sin(2)`）⇒ 参数表，拒收；
  ② 左邻**隔空白**的单个 token 放行：数字（`b = 2 (2)`）、单字母（`f(x) \le M (9)`）
     都是合法右缘标签；
  ③ 空白分开的 **≥2 个大写字母 token**（`T S O ( 3 )`，Arnold 33 条实测噪声）仍拒；
  ④ 剥空白后以 CJK / `\` 收尾（`见式 (3)`、`\sin ( 2 )`）仍拒。

Runs under stdlib unittest:
  python verify/tests/test_q_tail_label_space_glue.py
"""
import os
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
import lib.boot as _boot
_boot.setup()

from formula_tag import _tail_pre_guard, tail_label_match


def _tail_num(txt):
    m = tail_label_match(txt)
    return None if m is None else m.group(0).strip()


class TestSpacedDigitLeftAccepted(unittest.TestCase):
    def test_kreyszig_fixture_tails_are_labels(self):
        # 现场正例：式子以数字收尾、编号隔空白。
        for line, want in (('3.1-1 Theorem. We define a = 1 (1).', '(1).'),
                           ('A second relation b = 2 (2).', '(2).'),
                           ('3.2-1 Lemma. We have c = 3 (1).', '(1).')):
            with self.subTest(line=line):
                self.assertEqual(_tail_num(line), want)

    def test_spaced_single_letter_left_still_accepted(self):
        self.assertEqual(_tail_num(r'f(x) \le M (9)'), '(9)')


class TestGluedLeftRejected(unittest.TestCase):
    def test_glued_argument_lists_are_not_labels(self):
        for line in ('We set c_1(2) as the bound',
                     'G = SO(3) is the rotation group',
                     'then f(x) gives the value(2)',
                     '式中(3) 已先行给出',
                     r'then \sin(2) vanishes'):
            with self.subTest(line=line):
                self.assertIsNone(_tail_num(line))

    def test_spaced_group_notation_still_rejected(self):
        # 判据③：Arnold 实测的 33 条群记号噪声族不得因空白维而回流。
        for line in ('S O ( 3 )', 'T S O ( 3 )',
                     r'\boldsymbol { T } \boldsymbol { S } \boldsymbol { O } ( 3 )',
                     r'\mathbb { R } ^ { 3 } \times S O ( 3 )'):
            with self.subTest(line=line):
                self.assertIsNone(_tail_num(line))

    def test_spaced_cjk_rejected(self):
        # 判据④：中文交叉引用即便隔了空白也不是右缘标签。
        for line in ('上述结论见式 (3)', '该结果由定理 (2)'):
            with self.subTest(line=line):
                self.assertIsNone(_tail_num(line))

    def test_spaced_latex_command_is_a_documented_tradeoff(self):
        # 判据④的边界：latex 命令名**隔空白**（`\phi ( 2 )`）落在放行侧——它与
        # 真空标签 `\quad (8)` 形态不可分，而实测噪声（群记号那 33 条）里没有
        # 这种形态。命令**黏着**括号时由判据①拒收（见上一例的 `\sin(2)`）。
        self.assertIsNotNone(_tail_num(r'在线性空间中 \phi ( 2 )'))
        self.assertIsNone(_tail_num(r'then \sin(2) vanishes'))

    def test_braced_group_symbol_argument_is_rejected(self):
        # 群表示论 Introduction to representation theory ch1 实测 2026-10-03：
        # 显示块 `{ \mathfrak { s l } } ( 2 )` = `\mathfrak{sl}(2)`，`(2)` 是**维数
        # 自变量**（`sl` 是名）——整块就是一个带花括号名的李代数记号、以 `}` 收尾，
        # 空格躲过了 ① 的黏着拒收与 ③ 的「孤立大写字母」群记号拒收，曾被当成
        # §1.1 的右缘标签 `(2)`，抢走真 Jacobi 恒等式 `(2)`（p15/§1.9）的定义节 →
        # 忠实 `\tag{2}` 误判 MISPLACED。判据收紧后须拒收这类「裸名字 + 括号自变量」。
        for line in (r'{ \mathfrak { s l } } ( 2 )',
                     r'\mathfrak { s l } ( 2 )',
                     r'\mathcal { O } ( 3 )',
                     r'\operatorname { char } ( 2 )',
                     r'\mathrm { Hom } ( 1 )'):
            with self.subTest(line=line):
                self.assertIsNone(_tail_num(line))

    def test_genuine_labels_next_to_braced_group_still_accepted(self):
        # 反向：真右缘标签的左邻含等式内容（`=`/数字/`(`）或是**无花括号**裸命令，
        # 新判据一律放行，不被误伤。
        for line, want in ((r'he - eh = 2e, \quad ( 1 )', '( 1 )'),
                           (r'x^{2} + y^{2} = z ( 3 )', '( 3 )'),
                           (r'f : V \to W \quad ( 5 )', '( 5 )')):
            with self.subTest(line=line):
                self.assertEqual(_tail_num(line), want)


class TestGuardPredicateShape(unittest.TestCase):
    def test_raw_prefix_is_the_input(self):
        # 判据本体吃**未剥空白**的左邻：同一 pre 内容，黏着与隔空白结论必须相反。
        self.assertFalse(_tail_pre_guard('we set c_1'))      # 黏着
        self.assertTrue(_tail_pre_guard('we set c_1 '))      # 隔空白
        self.assertTrue(_tail_pre_guard(''))                 # 行首即标签
        self.assertTrue(_tail_pre_guard('   '))


if __name__ == "__main__":
    unittest.main(verbosity=2)
