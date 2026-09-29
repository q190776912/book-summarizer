# -*- coding: utf-8 -*-
r"""译本「结构继承源本」文档级豁免的回归（Apostol《解析数论导引》2026-09-29 实测）。

背景（第 9 处根治）：单元门控（`check_unit_quality`）在 2026-09-29 已按**配对源单元**
放行两条「源过 / 译不过」的判据（必包表 `_H_MISSING_BQ` / I 层缺 `---`），所以
`gate_units --units-dir units-translate` 15 章 exit 0；而合并后章 md 的全量 verify
（`FLayer`）**没有配对口**，同一条写法在步骤 8 复活成 9 处硬 FAIL，落账证据被拒
（`merge_translation` 的「全量 verify 未通过 exit 1」）。⇒ 判据本体搬进 format_verify
（SSOT），文档级经 `ctx.src_pair_md` 消费同一份实现；配对口径由 `verify_chapter` 统一
解析（`_src_lang_group`），检测趟 / 修复趟 / 单元趟三处共用。

本测试盯住四件事：
1. **豁免只认「与源本逐位同构」**：译文多拆或漏拆一个顶层标签 → 族失衡 → 照旧 FAIL。
2. **没有配对就一条都不豁免**（中文原书、三语书歧义、配对文件缺失 = fail-closed）。
3. **源语言侧不受影响**：配对方向永远是「译 ← 源」，绝不把译文当源去豁免源侧。
4. **修复趟与检测趟同口径**：verify 已豁免的写法，`--fix --fix-force` 不得再把它包进 `>`。
"""
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

import format_verify as fv  # noqa: E402
from format_verify import (  # noqa: E402
    FLayer, inherited_structure_exemptions, top_label_families,
    bq_label_block_then_prose, MBQ_ERR_MARK, ISEP_ERR_MARK)
import verify_chapter as vc  # noqa: E402
import fix_structural_label_guard as hfix  # noqa: E402


def _lines(text):
    return text.split('\n')


# 英文源：复数集体小标题留顶层（`Example(?![\w\-])` 天然不命中），单条 Note 包 `>`
EN_MIRROR = _lines("""\
**Examples.** Since $I(n)\\log n = 0$ we have $I' = 0$.

> **Note.** The original wraps this one.
""")
# 中文译文：逐位照抄同一结构（`**例。**` 命中必包表 → 单元趟已豁免，文档趟必须同样豁免）
CN_MIRROR = _lines("""\
**例.** 由于对一切 $n$ 都有 $I(n)\\log n = 0$，所以 $I' = 0$。

> **注.** 原文这条是包好的。
""")
# 负例：译者把源侧包在 `>` 里的 Note 也提到顶层 → 族失衡，必须照报
CN_HOISTED = _lines("""\
**例.** 由于对一切 $n$ 都有 $I(n)\\log n = 0$，所以 $I' = 0$。

**注.** 被从 `>` 里拆出来了。
""")
EN_MIRROR_TEXT = "\n".join(EN_MIRROR)
CN_MIRROR_TEXT = "\n".join(CN_MIRROR)
CN_HOISTED_TEXT = "\n".join(CN_HOISTED)


class TestPredicateSemantics(unittest.TestCase):
    def test_no_pair_exempts_nothing(self):
        self.assertEqual(inherited_structure_exemptions(CN_MIRROR, None), set())
        self.assertEqual(inherited_structure_exemptions(CN_MIRROR, []), set())

    def test_mirror_exempted_but_hoisting_is_not(self):
        self.assertEqual(inherited_structure_exemptions(CN_MIRROR, EN_MIRROR),
                         {'h_mbq', 'i_prose_sep'})
        self.assertEqual(inherited_structure_exemptions(CN_HOISTED, EN_MIRROR),
                         {'i_prose_sep'})

    def test_cn_head_noun_suffix_is_same_family(self):
        """中文定中倒装（「X的定义」）须与英文前缀式同族，否则整章豁免失效。"""
        src = _lines("**Definition of induced modulus.** Let $\\chi\\in\\Gamma(q)$.")
        tr = _lines("**导出模的定义.** 设 $\\chi\\in\\Gamma(q)$。")
        self.assertEqual(top_label_families(src), top_label_families(tr))
        self.assertIn('h_mbq', inherited_structure_exemptions(tr, src))

    def test_only_reportable_families_are_named(self):
        """可报族（证明/例/注…）保留族名，条目类与主题头统一落 'other'（处数仍逐位比较）。

        `**Proof of the reciprocity law.**` ↔ `**互反律的证明.**` 必须同为 'proof'：前者
        命中首词支、后者命中后缀支。而 `**Definition …**` / `**定理 …**` 永不被必包表
        报出，给它们单独族名只会制造中英不对称（`**Goldbach's conjecture.**` 首词是专名
        → other，而中文 `**哥德巴赫猜想。**` 走后缀支 → conjecture，Apostol ch8/ch14
        实测整章豁免被打掉）。
        """
        self.assertEqual(top_label_families(_lines("**Proof of the reciprocity law.**")),
                         ['proof'])
        self.assertEqual(top_label_families(_lines("**互反律的证明.**")), ['proof'])
        self.assertEqual(top_label_families(_lines("**Theorem 4.2.** statement")), ['other'])
        self.assertEqual(top_label_families(_lines("**定理 4.2.** 陈述。")), ['other'])

    def test_topic_heads_share_the_other_bucket(self):
        """主题式顶层小标题用词必然不同 → 同落 'other' 桶，仍要求两侧处数相等。"""
        src = _lines("**Goldbach's conjecture.** Every even integer...")
        tr = _lines("**哥德巴赫猜想.** 每个大于 2 的偶数……")
        self.assertEqual(top_label_families(src), ['other'])
        self.assertEqual(top_label_families(tr), ['other'])
        self.assertIn('h_mbq', inherited_structure_exemptions(tr, src))
        # 译文自己多加一个主题头 → other 桶失衡 → 不再豁免
        self.assertNotIn('h_mbq', inherited_structure_exemptions(
            tr + _lines("") + _lines("**华林问题.** 另一主题。"), src))

    def test_top_level_brace_line_is_counted(self):
        """`_H_MISSING_BQ_FOOTNOTE` 的 `{` 形不是粗体标签，必须进指纹（否则凭空多一行
        顶层 `{…}` 也能被豁免放过）。"""
        src = _lines("**Examples.** two of them.")
        tr = _lines("**例.** 两条。\n\n{一个源里没有的脚注。")
        self.assertNotIn('h_mbq', inherited_structure_exemptions(tr, src))
        self.assertIn('h_mbq', inherited_structure_exemptions(
            tr, _lines("**Examples.** two of them.\n\n{the footnote.")))

    def test_separator_fingerprint_is_language_neutral(self):
        src = _lines("> **Alternate proof.** shorter.\n> Take $f$ increasing.\n\n"
                     "Note. Since $t < 1$ it converges.\n")
        tr = _lines("> **另一证明.** 更短。\n> 取 $f$ 单调递增。\n\n"
                    "注. 由于 $t < 1$ 它收敛。\n")
        self.assertEqual(bq_label_block_then_prose(src),
                         bq_label_block_then_prose(tr))
        with_sep = list(src)
        with_sep.insert(3, "---")
        self.assertNotEqual(bq_label_block_then_prose(with_sep),
                            bq_label_block_then_prose(tr))


class _Ctx:
    """最小 ctx：`FLayer.run` 只读 md_file 与 src_pair_md。"""

    def __init__(self, md_file, src_pair_md=None):
        self.md_file = md_file
        self.src_pair_md = src_pair_md


def _tmp_md(text):
    fd, p = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    with open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return p


class TestFLayerWiring(unittest.TestCase):
    """文档级 verify 必须经 `ctx.src_pair_md` 消费**同一份**判据（不是单元趟的副本）。"""

    def setUp(self):
        self._katex = fv.check_katex
        fv.check_katex = lambda p: ([], [])       # 只隔离 KaTeX 子进程，被测的是豁免接线
        self._files = []

    def tearDown(self):
        fv.check_katex = self._katex
        for p in self._files:
            os.remove(p)

    def _run(self, cn_text, en_text=None):
        md = _tmp_md(cn_text)
        self._files.append(md)
        pair = None
        if en_text is not None:
            pair = _tmp_md(en_text)
            self._files.append(pair)
        return FLayer().run(_Ctx(md, pair)).metadata

    def test_inherited_labels_exempted_with_pair(self):
        meta = self._run(CN_MIRROR_TEXT, EN_MIRROR_TEXT)
        self.assertEqual(meta['h_mbq'], [])
        self.assertEqual(meta['i_prose_sep'], [])

    def test_without_pair_nothing_is_exempted(self):
        meta = self._run(CN_MIRROR_TEXT)
        self.assertTrue([m for m in meta['h_mbq'] if MBQ_ERR_MARK in m],
                        "无配对（中文原书 / 配对缺失）必须照报，不得静默放行")

    def test_hoisted_label_still_fails_with_pair(self):
        meta = self._run(CN_HOISTED_TEXT, EN_MIRROR_TEXT)
        self.assertTrue([m for m in meta['h_mbq'] if MBQ_ERR_MARK in m],
                        "译者凭空把附属块提到顶层 = 与源本分歧，必须照报")

    def test_source_language_side_unaffected(self):
        """源语言 md 即便带 src_pair_md（配置错误）也不因译文而放宽。"""
        md = _tmp_md(EN_MIRROR_TEXT + "\n**Note.** hoisted in EN too.\n")
        self._files.append(md)
        meta = FLayer().run(_Ctx(md, None)).metadata
        self.assertEqual(len([m for m in meta['h_mbq'] if MBQ_ERR_MARK in m]), 1)
        # 配对指向「同族处数相同」的另一份文件时，族失衡仍须照报
        pair = _tmp_md(EN_MIRROR_TEXT)
        self._files.append(pair)
        meta2 = FLayer().run(_Ctx(md, pair)).metadata
        self.assertEqual(len([m for m in meta2['h_mbq'] if MBQ_ERR_MARK in m]), 1)


class TestFixPassSharesThePredicate(unittest.TestCase):
    """检测趟豁免、修复趟照包 = 判据分叉：`--fix --fix-force` 不得把继承来的顶层标签包进 `>`。"""

    def setUp(self):
        self._files = []

    def tearDown(self):
        for p in self._files:
            os.remove(p)

    def _apply(self, cn_text, en_text=None):
        md = _tmp_md(cn_text)
        self._files.append(md)
        pair = None
        if en_text is not None:
            pair = _tmp_md(en_text)
            self._files.append(pair)
        res = hfix.apply_fix(_Ctx(md, pair))
        with open(md, encoding="utf-8") as f:
            return res.fix_dict['h_mbq'], f.read()

    def test_inherited_label_not_wrapped(self):
        n, text = self._apply(CN_MIRROR_TEXT, EN_MIRROR_TEXT)
        self.assertEqual(n, 0)
        self.assertIn("**例.** 由于", text)
        self.assertNotIn("> **例.**", text)

    def test_divergent_label_is_still_wrapped(self):
        n, text = self._apply(CN_HOISTED_TEXT, EN_MIRROR_TEXT)
        self.assertGreater(n, 0)
        self.assertIn("> **注.**", text)

    def test_no_pair_keeps_old_behaviour(self):
        n, text = self._apply(CN_MIRROR_TEXT)
        self.assertGreater(n, 0)
        self.assertIn("> **例.**", text)


class TestPairingResolution(unittest.TestCase):
    """配对口径的唯一实现（`verify_chapter`）：唯一非中文组 / 节序对应 / 歧义不猜。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _touch(self, *names):
        paths = []
        for n in names:
            p = os.path.join(self.tmp, n)
            with open(p, "w", encoding="utf-8") as f:
                f.write("# t\n")
            paths.append(p)
        return paths

    def test_cn_resolves_to_the_en_sibling(self):
        cn, en = self._touch("第3章_Foo.md", "Chapter3_Foo.md")
        groups = vc.chapter_md_groups(self.tmp, "3")
        self.assertEqual(vc._src_lang_group(groups[0], groups), [en])
        self.assertEqual(vc.source_pair_for_md(self.tmp, "3", cn), en)
        self.assertEqual(vc.source_pair_for_md(self.tmp, "3", en), None,
                         "源语言侧没有「继承」→ 绝不反向配对")

    def test_chinese_only_book_has_no_pair(self):
        cn, = self._touch("第3章_Foo.md")
        groups = vc.chapter_md_groups(self.tmp, "3")
        self.assertIsNone(vc._src_lang_group(groups[0], groups))
        self.assertIsNone(vc.source_pair_for_md(self.tmp, "3", cn))

    def test_ambiguity_refuses_to_guess(self):
        """两个非中文组（原文 + 中 + 英）→ 不猜哪个才是配对源 → None（fail-closed）。

        直接喂手工组列表：`chapter_md_groups` 的命名契约目前只产出中文组 + 一个
        `ChapterN_*` 组，第三语言组要等命名扩展才会出现，届时本判据即生效。
        """
        cn = ["第3章_Foo.md"]
        self.assertIsNone(vc._src_lang_group(
            cn, [cn, ["Chapter3_Foo.md"], ["Kapitel3_Foo.md"]]))
        self.assertEqual(
            vc._src_lang_group(cn, [cn, ["Chapter3_Foo.md"]]), ["Chapter3_Foo.md"])
        self.assertIsNone(vc._src_lang_group(cn, [cn]))

    def test_section_files_pair_by_index(self):
        c1, c2, e1, e2 = self._touch("第3章_1_A.md", "第3章_2_B.md",
                                     "Chapter3_1_A.md", "Chapter3_2_B.md")
        self.assertEqual(vc.source_pair_for_md(self.tmp, "3", c2), e2)
        self.assertEqual(vc.source_pair_for_md(self.tmp, "3", c1), e1)

    def test_shape_mismatch_does_not_pair(self):
        """一侧整章、一侧按节 → 拿节比章毫无意义，宁可不豁免。"""
        cn, e1, e2 = self._touch("第3章_Foo.md", "Chapter3_1_A.md",
                                 "Chapter3_2_B.md")
        self.assertIsNone(vc.source_pair_for_md(self.tmp, "3", cn))

    def test_src_pair_view_merges_split_pair_and_cleans_up(self):
        c1, c2 = self._touch("第3章_1_A.md", "第3章_2_B.md")
        e1, e2 = self._touch("Chapter3_1_A.md", "Chapter3_2_B.md")
        groups = vc.chapter_md_groups(self.tmp, "3")
        cn_grp = next(g for g in groups if vc._group_lang(g) == 'cn')
        with vc._src_pair_view(self.tmp, "3", cn_grp, groups) as pair:
            self.assertTrue(pair.endswith("._verify_merged_ch3_en.md"))
            self.assertTrue(os.path.exists(pair))
            seen = pair
        self.assertFalse(os.path.exists(seen), "临时配对视图必须随上下文退出而清理")
        self.assertTrue(all(os.path.exists(p) for p in (c1, c2, e1, e2)),
                        "除自建临时文件外不得碰任何章 md")

    def test_src_pair_view_for_source_language_group_is_none(self):
        self._touch("第3章_Foo.md", "Chapter3_Foo.md")
        groups = vc.chapter_md_groups(self.tmp, "3")
        en_grp = next(g for g in groups if vc._group_lang(g) == 'en')
        with vc._src_pair_view(self.tmp, "3", en_grp, groups) as pair:
            self.assertIsNone(pair)


if __name__ == "__main__":
    unittest.main(verbosity=2)
