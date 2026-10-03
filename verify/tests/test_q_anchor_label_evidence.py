r"""Q 层「定义位置锚点」的标签证据分级（Lasota-Mackey《Chaos, Fractals and Noise》实测，2026-10-02）。

「提及」冒充「标签」抢到定义位置 = 一批 ORDER_MISMATCH 假阳的唯一成因。两条同源漏洞：

① 裸号 pattern 的左邻永远是编号自己的开括号。`allow_bare`（默认 true）同时注册
   `(N.M)` 与裸 `N.M` 两枚 pattern：散文回指 `Further, by (11.1.4),` 里括号形态的
   命中被 `_embedded_ref`（左邻字母 `y`）正确拒掉，裸号形态却因左邻是 `(` 被判成
   「行首/标点 → 独立标签」→ 回指拿到定义位置（实测：ch11 的 11.1.4 锚到页 364、
   ch12 的 12.7.4 锚到页 446，两枚都是纯回指，把后面的真标签顶成倒序）。
   修复 = 遇到开括号**跨过去再用同一谓词判一次**。

② `keep_cross_refs=True` 下，纯散文块里的括号命中必须进 S（否则总结里忠实转写的
   `\tag` 被误判 FABRICATED），但「进了 S」≠「是位置证据」。旧写法把「带括号」当成
   无条件强信号：FIGURE 1.2.2 的图注被 OCR 切成 5 块，第 4 块以
   `(1.2.11) (shown as a dashed line)…` 开头（命中在块首，`_embedded_ref` 看不见
   左边的文字），其 y=648 既早于真标签 `(1.2.11)`（y=1173）也早于上一号
   `(1.2.10)`（y=948）→ ch1 的 1.2.11 报 ORDER_MISMATCH。
   修复 = 锚点强度再叠「标签证据等级」= **整块就是一个编号** 或 **该块含数学记号**；
   散文里的提及降级为弱证据（`_record_pos` 既有强弱分级：无强证据时行为逐字节同
   旧写法，故本修复只可能纠正锚点，不会把「无法判断」变成「报警」）。

🔴 反向约束（防「放宽判据把真标签也降级」）：`_block_has_math` 的短块豁免只到 8
   字符，那是为 Kreyszig 单分量 `(N)` 设的；多分量书的独立标签块 `(11.1.15)` 有 10
   字符且不含任何数学记号。若只用 `has_math` 分级，真标签会被降级、反倒输给一句含
   `>` 的散文回指（实测 ch11 的 11.1.15/11.1.17 各挪到更晚一页，多出 4 条假阳）。
   故 standalone 编号块必须算强证据——本文件第 3 个用例钉住这一点。
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

from formula_tag import SourceFormulaIndex, build_formula_patterns  # noqa: E402


def _emb(txt, span):
    i = txt.index(span)
    return SourceFormulaIndex._embedded_ref(txt, i, i + len(span))


class TestEmbeddedRefLooksThroughOwnParen(unittest.TestCase):
    def test_bare_match_inside_prose_paren_is_reference(self):
        # 实测形态（ch11 p364 / ch12 p446）：裸号形态不得绕过括号判据
        self.assertTrue(_emb('where mi = E(). Further, by (11.1.4),', '11.1.4'))
        self.assertTrue(_emb('and from (12.7.4) with v = va + v', '12.7.4'))
        self.assertTrue(_emb('P2 f(c) given by (1.2.10) to show how rapidly', '1.2.10'))

    def test_cjk_prose_reference_same_rule(self):
        self.assertTrue(_emb('由（1.2.9）可知极限密度唯一', '1.2.9'))

    def test_standalone_label_still_anchors(self):
        # 行首就是一个编号 → 不是引用（真标签，必须继续锚定位置）
        self.assertFalse(_emb('(1.2.11)', '1.2.11'))
        self.assertFalse(_emb('(11.1.15)', '11.1.15'))

    def test_label_glued_after_math_still_anchors(self):
        # 标签并进公式行尾：括号左边是运算符/标点 → 真标签
        self.assertFalse(_emb('f_{*}(x) = \\frac{1}{\\pi\\sqrt{x(1-x)}}. (1.2.11)',
                             '1.2.11'))
        self.assertFalse(_emb('P(Pf(x)) = P^2 f(x) (1.2.9)', '1.2.9'))

    def test_parenthesized_span_verdict_unchanged(self):
        # 括号形态命中（span 含括号）与旧写法一致：左邻文字 → 引用
        self.assertTrue(_emb('Further, by (11.1.4),', '(11.1.4)'))
        self.assertFalse(_emb('(1.2.11)', '(1.2.11)'))


class TestAnchorLabelGrade(unittest.TestCase):
    """_scan_text 的位置锚点分级（ncomp=3 / keep_cross_refs=True，即本书体例）。"""

    def _idx(self):
        return SourceFormulaIndex(
            '.', build_formula_patterns(3, allow_bare=True),
            chapter_prefix=False, ncomp=3, keep_cross_refs=True)

    def test_wrapped_figure_caption_loses_to_real_label(self):
        idx = self._idx()
        nums = set()
        # 图注第 4 块（OCR 换行），命中在块首——旧写法在此锚定 (23, 648)
        idx._scan_text('(1.2.11) (shown as a dashed line) with the sustained '
                       'irregularity shown by the', nums, pg=23, y=648.0)
        idx._scan_text('(1.2.10)', nums, pg=23, y=948.0)
        idx._scan_text('(1.2.11)', nums, pg=23, y=1173.0)
        self.assertEqual(idx.primary_pos('1.2.11'), (23, 1173.0))
        self.assertEqual(idx.primary_pos('1.2.10'), (23, 948.0))
        # 集合成员不受影响（否则总结里忠实的 \tag{1.2.11} 会被误判 FABRICATED）
        self.assertIn('1.2.11', nums)

    def test_standalone_label_block_outranks_later_prose_line(self):
        # 🔴 反向约束：`(11.1.15)` 长 10 字符、无数学记号，若只按 has_math 分级会被
        # 降级，反而让 p358 那句含 `>` 的散文赢 → 锚点跑到更晚一页。
        idx = self._idx()
        nums = set()
        idx._scan_text('(11.1.15)', nums, pg=356, y=1605.0)
        idx._scan_text('(11.1.15) converge to the same limit if c(0) > 0. '
                       'However, if c(0) = 0, then', nums, pg=358, y=1577.0)
        self.assertEqual(idx.primary_pos('11.1.15'), (356, 1605.0))

    def test_prose_only_evidence_still_anchors(self):
        # 弱证据兜底 = 旧写法逐字节行为（「无强证据」不得变成「无证据」）
        idx = self._idx()
        nums = set()
        idx._scan_text('(1.2.11) (shown as a dashed line) with the sustained '
                       'irregularity shown by the', nums, pg=23, y=648.0)
        self.assertEqual(idx.primary_pos('1.2.11'), (23, 648.0))
        self.assertIn('1.2.11', nums)

    def test_pure_cross_reference_carries_no_position(self):
        idx = self._idx()
        nums = set()
        idx._scan_text('where mi = E(). Further, by (11.1.4),', nums, pg=364, y=980.0)
        self.assertIsNone(idx.primary_pos('11.1.4'))
        self.assertIn('11.1.4', nums)   # 进 S 但不锚位


if __name__ == '__main__':
    unittest.main()
