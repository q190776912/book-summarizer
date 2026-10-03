# -*- coding: utf-8 -*-
r"""B 层提及桶「领域归属」收窄的判据回归（2026-10-02 Lasota-Mackey / Strogatz 根治）。

实测：chaos-fractals-and-noise（Lasota-Mackey）634 个 EXTRA-MENTION 键里 627 个、
Strogatz《非线性动力学与混沌》全部 525 个，都是**别的层已负责**的编号冒充条目提及——
`\tag{1.2.11}` 公式标签、`图 1.1.2` / `ch01_fig1.1.2.png` 图表号、`(1.2.8)` 括号公式
回指，在 `keys_in_md` 眼里与条目号同形（三段号既可能是公式号也可能是定理号）。
上千行良性噪声把**真正的**契约漏登记信号淹掉，故按出现位置上下文判归属：
仅当该号的**全部**出现都落在 tag / figref / eqref 三域内才从提及桶剔除。

负向守卫（缺一不可，否则就是「靠放宽判据刷绿」）：
  · 条目词 + 括号的引用形态（`Definition (5.6.5)` / `定理（5.6.5）`）照旧报；
  · tag 与裸号散文提及混现 → 照旧报；
  · 非纯数字键（`性质1`）、md 里扫不到的键 → 一律不判；
  · 长号片段（`1.2.115`）不得冒充 `1.2.11`；
  · `config 1.2` 里的 'fig' 子串不得被当成图号引用；
  · 只动 `extra`/`extra_mention` 两个非阻断桶，`all_keys` 原样 → 阻断判据逐字节不变。
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
import lib.boot as _boot  # noqa: E402
_boot.setup()

from verify.item_numbering_integrity.script.item_numbering_integrity import (  # noqa: E402
    domain_suppressed_mentions, _mention_occurrence_domain, _mention_num_regex,
    _TAG_SPAN_RE)


def _occ_domain(txt, needle):
    """单处出现的上下文判读（needle 必须在 txt 中唯一）。"""
    rx = _mention_num_regex(needle)
    ms = list(rx.finditer(txt))
    assert len(ms) == 1, (needle, len(ms))
    spans = [(m.start(), m.end()) for m in _TAG_SPAN_RE.finditer(txt)]
    return _mention_occurrence_domain(txt, ms[0], spans)


class TestDomains(unittest.TestCase):
    def test_tag_label_only_is_explained(self):
        txt = '一些正文。\n\n$$  P f = f \\tag{1.2.11} $$\n\n另一段。\n'
        self.assertEqual(domain_suppressed_mentions(txt, ['1.2-11']), {'1.2-11'})

    def test_figure_reference_is_explained(self):
        txt = ('见图 1.1.2 的直方图。\n'
               '<img src="figure/ch01_fig1.1.3.png" alt="Figure 1.1.3: x">\n')
        self.assertEqual(domain_suppressed_mentions(txt, ['1.1-2', '1.1-3']),
                         {'1.1-2', '1.1-3'})

    def test_parenthesized_equation_cross_ref_is_explained(self):
        txt = '把它代入 (1.2.8) 后应得到 $Pf=f$；由（1.2.9）可知极限密度唯一。\n'
        self.assertEqual(domain_suppressed_mentions(txt, ['1.2-8', '1.2-9']),
                         {'1.2-8', '1.2-9'})


class NegativeGuards(unittest.TestCase):
    def test_label_before_paren_still_reported(self):
        # 条目引用形态：括号前是条目词 → 不是公式回指
        self.assertEqual(_occ_domain('see Definition (5.6.5) below', '5.6.5'),
                         'real')
        self.assertEqual(_occ_domain('由定理（5.6.5）可知', '5.6.5'), 'real')
        self.assertEqual(domain_suppressed_mentions(
            '由定理（5.6.5）可知\n', ['5.6-5']), set())

    def test_mixed_tag_and_prose_still_reported(self):
        txt = '公式 $$x=y\\tag{1.2.11}$$ 与正文里的裸号 1.2.11 混现。\n'
        self.assertEqual(domain_suppressed_mentions(txt, ['1.2-11']), set())

    def test_non_numeric_key_never_dropped(self):
        txt = '性质1 在正文出现，另处 性质1 再提。\n'
        self.assertEqual(domain_suppressed_mentions(txt, ['性质1']), set())

    def test_key_absent_from_md_is_not_judged(self):
        # 跨语言/跨文件带进来的键：md 里一处都扫不到 → 保守不判（照旧报）
        self.assertEqual(domain_suppressed_mentions('无关正文。\n', ['9.9-9']),
                         set())

    def test_longer_number_does_not_implicate_shorter_key(self):
        # 只有 1.2.115 → 键 1.2.11 无出现 → 不判、不剔除
        txt = '编号 1.2.115 属于另一条目。\n'
        self.assertEqual(_mention_num_regex('1.2-11').findall(txt), [])
        self.assertEqual(domain_suppressed_mentions(txt, ['1.2-11']), set())

    def test_word_containing_fig_is_not_a_figure_ref(self):
        # 'config' 末尾含 'fig' 子串：lookbehind 必须拦住
        self.assertEqual(_occ_domain('the config 1.2 case', '1.2'), 'real')

    def test_entry_head_bold_span_is_real(self):
        self.assertEqual(_occ_domain('**例 3.4-1** 说明如下', '3.4-1'), 'real')
        self.assertEqual(domain_suppressed_mentions(
            '**例 3.4-1** 说明如下\n', ['3.4-1']), set())

    def test_separators_variants_all_covered(self):
        txt = '见图 1·2-3 与 $$y\\tag{1·2-3}$$。\n'
        self.assertEqual(domain_suppressed_mentions(txt, ['1.2-3']), {'1.2-3'})

    def test_two_level_book_key_dropped_only_when_explained(self):
        txt = '式 (2.6) 给出 $a=b$，其标签为 $$a=b\\tag{2.7}$$。\n'
        self.assertEqual(domain_suppressed_mentions(txt, ['2.6', '2.7']),
                         {'2.6', '2.7'})


class TestNoBlockingSemanticsTouched(unittest.TestCase):
    def test_suppression_only_reaches_report_buckets(self):
        """B 层里领域豁免只改写 `extra` / `extra_mention`；`all_keys` 与阻断桶不引用它。"""
        src = Path(_ROOT, 'verify', 'item_numbering_integrity', 'script',
                   'item_numbering_integrity.py').read_text(encoding='utf-8')
        seg = src[src.index('if _drop:'):src.index('# --- P2：提取侧查漏')]
        self.assertIn('domain_suppressed_mentions', seg)
        for touched in ('all_keys =', 'truly_missing =', 'mentioned_only ='):
            self.assertNotIn(touched, seg)
        self.assertIn('_dom_sup', src[src.index('if _drop:'):src.index('# --- P2')])


if __name__ == '__main__':
    unittest.main()
