# -*- coding: utf-8 -*-
r"""B 层提及桶「领域归属」判据第二版回归（2026-10-04 动力系统书架 9 书根治）。

第一版（2026-10-02，`test_b_layer_mention_domain.py` / `test_b_layer_entry_domain_eqref_guard.py`）
只认三域（tag / figref / eqref），把公式标签、图表号、括号公式回指洗掉了；书架巡检
（`_shelf_exm_probe.py` + `_shelf_exm_classify2.py`，逐处出现打印上下文）发现残留
EXTRA-MENTION 仍集中在**六个同形而不同域**的形态上，它们的键在 `keys_in_md` 里与条目号
同形，但所属领域从不作契约条目登记：

  exref     `Exercises 2.8.7 and 2.8.8`（题集内容在本管线不作条目登记，`load_contract`
            对 exercise/problem 直接 return；`_EXM_DROP_RE` 只剥**键里带标签词**的形态，
            裸号键看不见）
  formulref `参见方程 7.6.10` / `cf. equation 7.6.10` / 图注 `alt="… equation 6.2.13 …"`
            （与 `_LABEL_BEFORE_PAREN_RE` 删 `Equation` 同一条理由：编号公式归 Q 层）
  bibref    `定理证明可参见文献[21] Theorem 3.3.3`（引文里的号是**外书**条目号）
  chref     第 6 章 md 里的 `定理 5.1.2`（该条目属别章契约辖域，本层只对
            「本章契约 ↔ 本章 md」负责；跨章号既不是本章漏登记条目，也不该占用提及桶）
  title     `### §2.3.3 应用`（小节序标；条目标头从不用 `§` 起头）
  续列继承  `图 6.4.1 至 6.4.4` / `Exercises 13.5.7 and 13.5.8`——第二项之前只有连接词，
            标签在上一项前面，故辖域判据只看本行前缀并剥去「上一项 + 连接词」
  字母后缀  `(8.4.3a)`（分图/分部号；旧闭合判据只认 `)` → 该处被判 real，全键永不豁免）

🔴 负向守卫（缺一即成「靠放宽判据刷绿」），每条都有实测出处：
  · **同章跨节回指不豁免**：chaos ch5 的 `定义 5.6.5`——印面自身那条回指指向原书不存在
    的条目、交付逐字照抄，属必须留在报告里的信号（走 `mention_ignore` 取证，非放宽判据）；
  · 跨章引用**必须有条目词引导**：裸号散文提及 `见 5.1.2` 照旧报；
  · 章标题锚点否决：正文实际处于 `# 第7章` 之下的 `定理 7.1.2` 不算跨章；
  · 同键另有一处真条头 `**定理 6.1.2**` → 一处 `real` 即全盘照报；
  · `例/例子/Example` 不在题集词表里（例题在多数书里是真条目）；
  · 连接词剥取**必须**数字在前：`核对，另外 5.1.3` 不继承任何域；
  · 小节标题域必须有 `§`：`## 5.6.5 标题` 照旧报；带条目词的 `#### 定理 5.6.5` 不归 title；
  · 只动非阻断 EXTRA 三桶，`truly_missing` / `mentioned_only` / `blocking` 逐字节不变。
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

import item_numbering_integrity as MOD  # noqa: E402
from verify.script.base import VerifyManager  # noqa: E402
from verify.script.register_all import LAYER_REGISTRY  # noqa: E402
from verify_config import BookConfig, GroupConfig  # noqa: E402

_TAG = MOD._TAG_SPAN_RE


def _dom(txt, needle, ch=None, sec_keys=None):
    """needle 在 txt 中唯一时的出现域判读。"""
    rx = MOD._mention_num_regex(needle)
    ms = list(rx.finditer(txt))
    assert len(ms) == 1, (needle, len(ms))
    anchors = MOD._heading_anchors(txt) if ch is not None else []
    return MOD._mention_occurrence_domain(
        txt, ms[0], [(m.start(), m.end()) for m in _TAG.finditer(txt)],
        ch, anchors, sec_keys)


def _doms(txt, needle, ch=None, sec_keys=None):
    """needle 的**每一处**出现各自判什么域（同形多处时用）。"""
    rx = MOD._mention_num_regex(needle)
    anchors = MOD._heading_anchors(txt) if ch is not None else []
    spans = [(m.start(), m.end()) for m in _TAG.finditer(txt)]
    return [MOD._mention_occurrence_domain(txt, m, spans, ch, anchors, sec_keys)
            for m in rx.finditer(txt)]


def _sup(txt, keys, ch=None, sec_keys=None):
    return MOD.domain_suppressed_mentions(txt, set(keys), ch, sec_keys)


class TestExerciseDomain(unittest.TestCase):
    """exref + 续列继承：题集引用从不作契约条目。"""

    def test_exercise_list_continuation_inherits_exref(self):
        txt = "> 改进版见 Exercises 2.8.7 and 2.8.8。\n"
        self.assertEqual(_dom(txt, '2.8.7'), 'exref')
        self.assertEqual(_dom(txt, '2.8.8'), 'exref',
                         '第二项之前只有连接词，须剥「上一项+连接词」继承同域')
        self.assertEqual(_sup(txt, ['2.8-7', '2.8-8']), {'2.8-7', '2.8-8'})

    def test_cn_exercise_range_inherits_exref(self):
        txt = "> 至于 3 与 4，见习题 12.2.9 和 12.2.10。\n"
        self.assertEqual(_dom(txt, '12.2.10'), 'exref')

    def test_three_hops_of_list(self):
        txt = "> Exercises 1.1.1, 1.1.2 and 1.1.3 treat it.\n"
        self.assertEqual(_dom(txt, '1.1.3'), 'exref')

    def test_example_label_is_not_exref(self):
        """🔴 `例/例子/Example` 不在题集词表：例题在多数书里是**真条目**。"""
        for txt in ['> 例 5.1.2 说明如下。\n', '> 例子 5.1.2 说明如下。\n',
                    '> Example 5.1.2 says so.\n']:
            self.assertEqual(_dom(txt, '5.1.2'), 'real', txt)

    def test_conj_strip_requires_a_digit_before_it(self):
        """🔴 裸连接词不剥：`核对，另外 5.1.3` 不继承任何域（散文提及照旧报）。"""
        txt = "> 前面的正文需要核对，另外 5.1.3 也要人工确认。\n"
        self.assertEqual(_dom(txt, '5.1.3'), 'real')


class TestFigureDomain(unittest.TestCase):
    def test_figure_list_and_letter_suffix(self):
        txt = "> 图 5.1.3 与 5.1.4 中的轨线是椭圆。\n"
        self.assertEqual(_dom(txt, '5.1.4'), 'figref')
        txt2 = "> 与图 5.1.5a 和 5.1.5c 中一样。\n"
        self.assertEqual(set(_doms(txt2, '5.1.5')), {'figref'},
                         '两处出现（一处直连图、一处续列）须同归图域')
        self.assertEqual(_sup(txt2, ['5.1-5']), {'5.1-5'})
        txt3 = "> Combining Figures 6.4.1 through 6.4.4 gives Figure 6.4.5.\n"
        self.assertEqual(_dom(txt3, '6.4.4'), 'figref')

    def test_letter_suffix_paren_eqref(self):
        """分图/分部号 `(8.4.3a)`：只放宽闭合侧，条目词否决分支照旧。"""
        self.assertEqual(_dom('(8.4.3a) 是分图形态', '8.4.3'), 'eqref')
        self.assertEqual(_dom('Definition (5.6.5a) below', '5.6.5'), 'real')


class TestFormulaAndBibDomain(unittest.TestCase):
    def test_formula_word_led_ref_is_formulref(self):
        self.assertEqual(_dom('> 考虑特殊情形（参见方程 7.6.10）。\n', '7.6.10'),
                         'formulref')
        self.assertEqual(_dom('Then cf. equation 7.6.10 holds.\n', '7.6.10'),
                         'formulref')

    def test_caption_alt_equation_is_explained(self):
        txt = ('<img src="ch06_fig6.2.4.png" alt="Figure 6.2.4: the transformation '
               'of equation 6.2.13 with epsilon 0.01">\n')
        self.assertEqual(_sup(txt, ['6.2-13']), {'6.2-13'})

    def test_bibref_with_trailing_label_word(self):
        """`文献[21] Theorem 3.3.3`：先剥一个条目词再证书目标记（同章号，chref 不救）。"""
        txt = "> 定理证明可参见文献[21] Theorem 3.3.3．\n"
        self.assertEqual(_dom(txt, '3.3.3', ch='3'), 'bibref')
        self.assertEqual(_sup(txt, ['3.3-3'], ch='3'), {'3.3-3'})

    def test_plain_prose_bare_number_is_not_bibref(self):
        self.assertEqual(_dom('> 由 3.3.3 可知。\n', '3.3.3', ch='3'), 'real')


class TestCrossChapterDomain(unittest.TestCase):
    def test_label_led_other_chapter_ref_is_chref(self):
        txt = "> 环面双曲自同构（即例子 5.1.2）是公理 A 的。\n"
        self.assertEqual(_dom(txt, '5.1.2', ch='6'), 'chref')
        self.assertEqual(_sup(txt, ['5.1-2'], ch='6'), {'5.1-2'})

    def test_same_chapter_cross_section_ref_stays_real(self):
        """🔴 同章跨节回指不得豁免（chaos `定义 5.6.5` 实测：印面自身的错指，
        交付逐字照抄 = 必须留在报告里走取证通道的信号）。"""
        txt = "> 对每个 $f \\in D_0$（$D$ 的一个稠密子集，定义 5.6.5），将轨迹记为…\n"
        self.assertEqual(_dom(txt, '5.6.5', ch='5'), 'real')
        self.assertEqual(_sup(txt, ['5.6-5'], ch='5'), set())

    def test_bare_number_cross_chapter_needs_label_word(self):
        """🔴 无条目词引导的跨号 = 裸号散文提及，照旧报（原始信号不洗）。"""
        txt = "> 详见 6.1.2 的讨论。\n"
        self.assertEqual(_dom(txt, '6.1.2', ch='2'), 'real')
        self.assertEqual(_sup(txt, ['6.1-2'], ch='2'), set())

    def test_chapter_heading_anchor_defeats_chref(self):
        """🔴 正文实际处于 `# 第7章` 之下时，`定理 7.1.2` 不算跨章。"""
        txt = "# 第5章\n\n正文。\n\n# 第7章\n\n> 定理 7.1.2 在此章内。\n"
        self.assertEqual(_dom(txt, '7.1.2', ch='5'), 'real')

    def test_real_entry_head_defeats_suppression(self):
        """🔴 同键既有跨章引用又有真条头 → 一处 `real` 即全盘照报。"""
        txt = ("# 第5章\n\n> 定理 6.1.2 见别章。\n\n"
               "**定理 6.1.2** 本章契约里没有的真条头。\n")
        self.assertEqual(_sup(txt, ['6.1-2'], ch='5'), set())
        self.assertIn('real', _doms(txt, '6.1.2', ch='5'),
                      '行首粗体条头必须否决一切豁免（内容放错章是真缺陷）')

    def test_v1_fake_bold_span_still_eqref(self):
        """🔴 第一版校准形态不得被粗体条头否决反噬：假跨度的行首粗体已在 `证明**`
        处闭合，`(4.2.6)` 照旧走 eqref 豁免。"""
        txt = "> **证明**：1. 由 (4.2.6) 与定理 4.2.1 可知 $f^{*}$ 几乎处处为常数。\n"
        self.assertEqual(_dom(txt, '4.2.6'), 'eqref')

    def test_ch_without_number_disables_the_branch(self):
        txt = "> 定理 6.1.2 见别章。\n"
        self.assertEqual(_dom(txt, '6.1.2'), 'real', '缺省 ch = 不判跨章支，回到改前行为')
        self.assertEqual(_sup(txt, ['6.1-2']), set())


class TestSectionTitleDomain(unittest.TestCase):
    """title 域：**契约作证**的小节标题（`_contract_section_keys` 真值）。"""

    def test_section_heading_is_title_domain(self):
        txt = "### §2.3.3 应用\n\nBirkhoff 遍历定理有广泛的应用。\n"
        self.assertEqual(_dom(txt, '2.3.3', ch='2', sec_keys={'2-3-3'}), 'title')
        self.assertEqual(_sup(txt, ['2.3-3'], ch='2', sec_keys={'2-3-3'}), {'2.3-3'})

    def test_unattested_section_heading_stays_real(self):
        """🔴 契约里没有这个小节 = 号形标题可疑（可能条目被错写成标题），照旧报。"""
        txt = "### §2.3.9 应用\n\n正文。\n"
        self.assertEqual(_dom(txt, '2.3.9', ch='2', sec_keys={'2-3-3'}), 'real')
        self.assertEqual(_sup(txt, ['2.3-9'], ch='2', sec_keys={'2-3-3'}), set())

    def test_no_sec_keys_disables_the_branch(self):
        txt = "### §2.3.3 应用\n\n正文。\n"
        self.assertEqual(_dom(txt, '2.3.3', ch='2'), 'real',
                         '缺省 sec_keys = 不判 title 支（回到改前行为）')

    def test_heading_without_section_sign_stays_real(self):
        """🔴 `§` 是本支的唯一通行证：无 `§` 的号形标题照旧报。"""
        self.assertEqual(_dom("## 5.6.5 一个标题\n", '5.6.5', ch='5',
                              sec_keys={'5-6-5'}), 'real')

    def test_label_led_heading_is_not_title(self):
        """带条目词的标题不归 title（交给 chref/real 判定，别绕过条目词否决）。"""
        self.assertEqual(_dom("#### 定理 5.6.5 标题\n", '5.6.5', ch='5',
                              sec_keys={'5-6-5'}), 'real')

    def test_entry_head_bold_span_is_still_real(self):
        self.assertEqual(_dom("> **例 3.4-1** 说明如下\n", '3.4.1', ch='3',
                              sec_keys={'3-4-1'}), 'real')


def _node(key, type_='definition'):
    return {'key': key, 'type': type_, 'name': key, 'page_start': 100,
            'page_end': 100, 'sub_sec': [{'type': 'text', 'text': '内容'}]}


class _Loader:
    def __init__(self, cfg):
        self._cfg = cfg
        self.figure_index = []

    def config_for_chapter(self, ch):
        return self._cfg

    def manual_for_chapter(self, ch):
        return []


class _OnlyExtractB:
    def all_ordered(self):
        return [l for l in LAYER_REGISTRY.all_ordered() if l.code in ('EXTRACT', 'B')]

    def fixable_ordered(self):
        return []


MD5 = (
    "# 第5章\n\n"
    "## §5.1 双曲性\n\n"
    "**定理 5.1.1** 契约在册的条目。\n\n"
    "## §5.3 应用\n\n"
    "> 环面自同构（即定理 5.1.2）是公理 A 的。\n\n"          # 同章 -> 照报
    "> 见别章的定理 6.1.2 与推论 6.1.3。\n\n"                 # 跨章 -> 豁免
    "> 见习题 5.9.1 和 5.9.2。\n\n"                           # 题集续列 -> 豁免
    "### §5.3.4 补充\n\n"                                    # 小节标题 -> 豁免
    "> 参见方程 5.9.9 的推导。\n\n"                           # 公式域 -> 豁免
)


class EndToEndTest(unittest.TestCase):
    def _run(self, md_text, guard=True):
        ext = tempfile.mkdtemp()
        d = os.path.join(ext, 'book_structure')
        os.makedirs(d, exist_ok=True)
        root = {'key': '5', 'type': 'chapter', 'sub_sec': [
            {'key': '5.1', 'type': 'section', 'sub_sec': [_node('5.1.1')]},
            {'key': '5.3', 'type': 'section',
             'sub_sec': [{'key': '5.3.4', 'type': 'section', 'sub_sec': []}]},
        ]}
        with open(os.path.join(d, 'ch5.json'), 'w', encoding='utf-8') as f:
            json.dump(root, f, ensure_ascii=False)
        md = os.path.join(ext, 'ch5.md')
        with open(md, 'w', encoding='utf-8') as f:
            f.write(md_text)
        cfg = BookConfig(ordinal=[GroupConfig(type=3, name=['uncat'], scope=3)],
                         language='cn')
        mgr = VerifyManager(_OnlyExtractB(), _Loader(cfg))
        if guard:
            return mgr.verify_one(5, 5, 5, md, ext)
        orig = MOD.domain_suppressed_mentions
        orig_inline = MOD._inline_only_entry_keys
        MOD.domain_suppressed_mentions = (
            lambda txt, keys, ch=None, sec_keys=None, type_vocab=None: set())
        MOD._inline_only_entry_keys = lambda lines, keys: []
        try:
            return mgr.verify_one(5, 5, 5, md, ext)
        finally:
            MOD.domain_suppressed_mentions = orig
            MOD._inline_only_entry_keys = orig_inline

    @staticmethod
    def _keys(res, field):
        return sorted(str(x) for x in (res.get(field) or []))

    def test_cross_chapter_and_exercise_keys_leave_buckets(self):
        on = self._run(MD5)
        em = self._keys(on, 'extra_mention') + self._keys(on, 'extra_entry')
        for k in ('6.1-2', '6.1-3', '5.9-2', '5.9-9', '5.3-4'):
            self.assertFalse(any(k in x for x in em),
                             '%s 应已归域豁免，实得 %r' % (k, em))
        dom = self._keys(on, 'extra_mention_domain')
        for k in ('6.1-2', '6.1-3', '5.9-2', '5.9-9', '5.3-4'):
            self.assertTrue(any(k in x for x in dom),
                            '豁免必须留痕（不静默消失），缺 %s：%r' % (k, dom))

    def test_same_chapter_stray_still_reported(self):
        """🔴 同章跨节的条目词引用（`定理 5.1.2` 而契约无该条）必须照旧在提及桶。"""
        on = self._run(MD5)
        self.assertTrue(any('5.1-2' in x
                            for x in self._keys(on, 'extra_mention')
                            + self._keys(on, 'extra_entry')),
                        '同章回指不属豁免域，实得 %r' % (on.get('extra_mention'),))

    def test_widening_moves_only_extra_buckets(self):
        on, off = self._run(MD5), self._run(MD5, guard=False)
        for field in ('truly_missing', 'mentioned_only'):
            self.assertEqual(self._keys(on, field), self._keys(off, field), field)
        self.assertEqual(len(on.get('blocking') or []),
                         len(off.get('blocking') or []))
        for field in ('extra', 'extra_mention', 'extra_entry'):
            self.assertTrue(set(self._keys(off, field)) >= set(self._keys(on, field)) -
                            set(self._keys(on, 'extra_mention_domain')),
                            field + ' 只应收窄')
        self.assertTrue(set(self._keys(on, 'extra_mention_domain')) >=
                        set(self._keys(off, 'extra_mention_domain')),
                        '豁免清单只可增长（每个被移键都须留痕）')


if __name__ == '__main__':
    unittest.main()
