# -*- coding: utf-8 -*-
r"""B 层提及桶「领域归属」判据第三版回归（2026-10-04 动力系统书架 9 书收尾）。

v2（`test_b_layer_mention_domain_v2.py`）把八个辖域判据上线后，书架残留 EXTRA-MENTION
逐键复核（`_shelf_exm_perlang.py` → `_exm_perlang_run.txt`，64 行）暴露**五类**判据缺陷，
每一类都让一个本来能归域的键永久卡在报告桶里：

  ① `noscan`（39 行）：`_mention_num_regex` 对 `_norm_path` 折不动的键（`定理1.6` /
     `引理20.3` 这类「标签 + **两段**号」）返回 None → 辖域判据根本看不见它。实测其中
     `参见文献[20] 定理3.4` 属书目域、`由定理 1.6`（第 3 章里）属跨章域。
  ② `eqref` 被条目词否决卡死（24 行）：`第二个性质 (4.2.7)` / `证明 (7.3.5) 中的分岔…`
     里的「性质/证明」是**散文词**，但 `_LABEL_BEFORE_PAREN_RE` 一律否决 → 该处判 real
     → 全键照报。印面区分得很清楚：编号公式的回指是贴着括号的 `(4.2.7)`，条目回指是
     「标签 + 空格 + 裸号」（`Definition 5.6.5`）。故**号在本文件 `\tag{}` 名册里**时
     让位给公式域（Q 层 formula_tag 辖域）。
  ③ 句末句号冒充「更深一层号」（7 行）：尾守卫 `(?![\d.])` 让 `见习题 12.2.9 和
     12.2.10。` / `given in Exercise 5.1.10.` 的号**扫不到** → `absent` → 永不豁免。
     改成「后邻数字」或「后邻 分隔符+数字」才拦。
  ④ md 侧**区间幻影键**（`lib/key_parse.py` 的 `_KEY_DEEP_RE`）：`第 10.4-10.6 节` /
     `Sections 7.2-7.4` 被无守卫的 `KEY_RE` 非重叠扫描切成假三段键 `10.4-10` / `7.2-7`
     （尾巴 `.6` 白送）。这种键契约永不可能在册，也永不可能归域（`absent`），
     只能从**造键处**根治。左守卫与右守卫缺一不可：只有右守卫时正则会退到
     `4-10.6` 错位重切，造出更假的 `4.10-6`。
  ⑤ ①–④ 之后书架只剩「标签 + **单段**号」的不可扫描键（文兰 `例3`、Arnold `例4`/`评注7`）：
     它们由 `keys_in_md` 的单号条头分支造出，各支辖域判据看不见号。补两支——
     `untyped`（本书 config 词表**未宣告**该条目类型 → 契约无从开槽，救济 = 补宣告）与
     `xref`（每一处出现都被 `§`/`Sect.`/`第 … 节` 锚点限定，如 `如 §1.3 的例 3 所证`、
     `一文 §9 的注 7`、`### §D 例 4：保守系` = 结构性交叉引用而非本章漏登记）。

🔴 51 书双侧对拍（`_census_b_ab_routing_v3.py` + `_diff_ab_guard_v3.py`）在 ①–⑤ 上线后
又暴露**三支**同族缺陷（20 个 GAINED 键 = 判据把出厂时被漏扫的出现重新看见，其中
18 个属「出现本身合法、只是当时没有对应的域支接住」）：
  ⑥ **锚点紧贴号前**（Vakil ch4 `我们会在 §11.3.11 中把这一点说精确`）：`xref` 一支要求
     锚点**后自带号**，于是 `§` 与号之间无字符的形态落到 real → 新增 `_SEC_ADJACENT_ANCHOR_RE`。
  ⑦ **散文里的小节回指**（Evans `Prove Theorem 15 in §2.2.4` / statistical-inference
     `See Miscellanea 7.5.5`）：`title` 一支此前只认 `### §N.M` 标题行。放宽的守卫是
     「归一后的号必须在本章契约的 section 名册里」**且**「号前不得是条目标签词」，
     名册外 / `Definition 4.9.1` 同形撞车一律照判 real。
  ⑧ **粗体条头否决收窄**（Vakil ch17 `**17.4.9 Revisiting Example 9.3.3.**`）：旧否决按
     「本号落在起始于行首的粗体跨度内」判 real，把**跨度序标之后**的跨章条目回指一并误伤。
     现要求 `**` 与本号之间不得再出现数字（= 本号就是该跨度的序标）才否决；跨度序标本体
     的否决逐字不变（`**定理 6.1.2**` 写在第 5 章仍是真缺陷；`**12.5.10.**` 这类契约无账的
     段落粗体头**故意保留在报告桶**——那是补登记信号，不许归域消音）。

🔴 负向守卫（放宽不得变成盲区）：
  · **标签锚定只收紧匹配，不放宽**：`引理20.3` 不得把同章的 `**定理20.3**` / `图 20.3` /
    `## §20.3` 读成自己的出现（Koopman 本书按类型分计数器，同号异类）；
  · `tag` 名册只推翻**括号贴号**那一支：chaos 的 `定义 5.6.5`（标签 + 裸号，号不贴括号）
    即便 `\tag{5.6.5}` 在册也必须照旧判 real——那是原书自己的误指、我们照印面转录，
    属必须留在报告里走举证通道的信号；字母后缀 `Definition (5.6.5a)` 同理不在名册；
  · 三段标签键（`定义1.1.1`）沿用 v2 的折号裸号匹配，**逐字节不变**（防 GAINED 倒退）；
  · 单段号键（`断言1` / `例3`）的号是**计数器值**不是章号 → 跨章一支对不可扫描键整体
    关闭（`第 5 章里的「由例 3 即得」不得被读成「第 3 章回指」），且**粗体条头否决**照旧
    先判（`> **注 7**：…` 是真条头形态，照常报）；无 § 锚定的裸提及（`由例 3 即得`）
    同样不豁免——同一键里只要有一处无域出现，整个豁免作废；
  · `untyped`（本书 config 未宣告该条目类型的「标签+单号」键）只在词表**闭合**（无
    `uncat` 兜底组）时生效，宣告了该类型即自动失效；
  · 区间幻影只从**扫描侧**消失，`truly_missing` / `mentioned_only` / `blocking` 逐字节不变。
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
from key_parse import keys_in_md  # noqa: E402
from verify.script.base import VerifyManager  # noqa: E402
from verify.script.register_all import LAYER_REGISTRY  # noqa: E402
from verify_config import BookConfig, GroupConfig  # noqa: E402

_TAG = MOD._TAG_SPAN_RE


def _doms(txt, key, ch=None, sec_keys=None, tag_nums=True):
    """key 的**每一处**出现各自判什么域（与出厂调用点同参）。"""
    rx = MOD._mention_num_regex(key)
    if rx is None:
        return []
    anchors = MOD._heading_anchors(txt) if ch is not None else []
    spans = [(m.start(), m.end()) for m in _TAG.finditer(txt)]
    tn = MOD._tag_num_set(txt) if tag_nums else None
    return [MOD._mention_occurrence_domain(txt, m, spans, ch, anchors, sec_keys, tn)
            for m in rx.finditer(txt)]


def _sup(txt, keys, ch=None, sec_keys=None, vocab=None):
    return MOD.domain_suppressed_mentions(txt, set(keys), ch, sec_keys, vocab)


# ---------------------------------------------------------------- ① 标签锚定
class TestLabelAnchoredScanning(unittest.TestCase):
    def test_cn_labelled_key_now_scans(self):
        txt = "> 我们用定理 1.6 的结论即得。\n"
        self.assertEqual(_doms(txt, '定理1.6', ch=3), ['chref'],
                         '标签引导的两段号键必须进入辖域判据（跨章回指）')
        self.assertEqual(_sup(txt, ['定理1.6'], ch=3), {'定理1.6'})

    def test_en_spelling_matches_canonical_key(self):
        """键是中文规范标签（`引理20.3`），md 印 `Lemma 20.3` 也要认（同书双语）。"""
        txt = "> Based on Lemma 20.3, each eigenvalue has an eigenfunction.\n"
        self.assertEqual(_doms(txt, '引理20.3', ch=20), ['real'],
                         '同章条目回指：照旧在报告桶（原书笔误族，走举证通道）')

    def test_same_number_other_type_is_not_an_occurrence(self):
        """🔴 `引理20.3` 不得把 `**定理20.3**` / `图 20.3` / `## §20.3` 算进自己。"""
        txt = ("## §20.3 系统流\n\n**定理20.3**：设映射 $\\mathbf{H}$ 满足…\n\n"
               "> 结果如图 20.3 所示。\n")
        self.assertEqual(MOD.mention_domains_of(txt, '引理20.3', 20), ['absent'])
        self.assertEqual(_sup(txt, ['引理20.3'], ch=20), set(),
                         '本章没有引理 20.3 的出现，谈不上归域')

    def test_three_level_labelled_key_keeps_v2_bare_matching(self):
        """🔴 出厂口径不变式：`_norm_path` 能折叠的三段标签键仍按裸号匹配。"""
        txt = "> 引理 1.1.1 见下册。\n"
        self.assertEqual(_doms(txt, '定义1.1.1', ch=1), ['real'])

    def test_single_number_key_stays_noscan(self):
        for k in ('断言1', '例3', '性质1', '命题4'):
            self.assertIsNone(MOD._mention_num_regex(k), k)


# ---------------------------------------------------- ② tag 名册推翻条目词否决
class TestTagRegisterEqref(unittest.TestCase):
    def test_property_paren_with_tag_register_hit(self):
        txt = ("$$\n\\tag{4.2.7}\n$$\n\n"
               "把 (4.2.5) 中的 $x$ 换成 $S(x)$ 即得方程 (4.2.6)。"
               "第二个性质 (4.2.7) 则由 $\\mu$ 的不变性得到。\n")
        self.assertIn('eqref', _doms(txt, '4.2.7', ch=4),
                      '括号贴号 + 号在 \\tag 名册 = 编号公式回指，归 Q 层辖域')

    def test_exercise_head_proving_a_tagged_formula(self):
        txt = ("**7.3.4.** 证明 (7.3.5) 中的分岔是结构稳定的。\n\n"
               "$$\n\\tag{7.3.5}\n$$\n")
        self.assertEqual(MOD.mention_domains_of(txt, '7.3-5', 7),
                         ['eqref', 'tag'])
        self.assertEqual(_sup(txt, ['7.3-5'], ch=7), {'7.3-5'})

    def test_no_tag_register_hit_stays_real(self):
        """🔴 名册没这个号（`4.2.9`）→ 条目词否决照旧生效，判据不是洗地机。"""
        txt = "$$\n\\tag{4.2.7}\n$$\n\n第二个性质 (4.2.9) 由不变性得到。\n"
        self.assertEqual(_doms(txt, '4.2.9', ch=4), ['real'])
        self.assertEqual(_sup(txt, ['4.2.9'], ch=4), set())

    def test_bare_labelled_form_with_tag_register_stays_real(self):
        """🔴 chaos 实测信号：`（$D$ 的一个稠密子集，定义 5.6.5）` 号**不贴括号**，
        即便 `\tag{5.6.5}` 在册也照旧 real——印面误指必须留在报告桶走举证通道。"""
        txt = ("对每个 $f \\in D_{0}$（$D$ 的一个稠密子集，定义 5.6.5），将轨迹记为\n\n"
               "$$\n\\tag{5.6.5}\n$$\n")
        self.assertIn('real', _doms(txt, '定义5.6.5', ch=5))
        self.assertEqual(_sup(txt, ['定义5.6.5', '5.6-5'], ch=5), set())

    def test_letter_suffix_not_in_register(self):
        """🔴 字母后缀键（`定义5.6.5a`）既不可扫描也**不得**被 tag 名册洗白。

        `_mention_num_regex` / `_unscannable_mention_regex` 都要求号**字面**成立，
        故 md 里根本没有可判的出现（`absent`）。豁免的前提是「每一处出现都有域」，
        扫不到 = 没有证据 = 照报（不静默、也不误豁免）。
        """
        txt = "$$\n\\tag{5.6.5}\n$$\n\n见 Definition (5.6.5a) 的讨论。\n"
        self.assertEqual(MOD.mention_domains_of(txt, '定义5.6.5a', ch=5), ['absent'])
        self.assertEqual(_sup(txt, ['定义5.6.5a'], ch=5), set())


# ------------------------------------------ ⑤ xref：§ 锚定的单段号标签键交叉引用
class TestXrefAnchoredMention(unittest.TestCase):
    """`例3` / `评注7` 这类**不可按号扫描**的「标签 + 单段号」键的最后一支。"""

    def _d(self, txt, key):
        return MOD.mention_domains_of(txt, key, ch=3)

    def test_cn_section_qualified_ref_is_xref(self):
        txt = "> $E^{s}$ 与这些竖直线的交点的高度为 $\\{nb\\}$。如 §1.3 的例 3 所证。\n"
        self.assertEqual(self._d(txt, '例3'), ['xref'])
        self.assertEqual(_sup(txt, ['例3'], ch=3), {'例3'})

    def test_heading_with_letter_anchor_is_xref(self):
        """Arnold 实测：印面把保守系一节写成标题 `### §D 例 4：保守系`——结构行不是条目。"""
        txt = "### §D 例 4：保守系 (conservative system)\n"
        self.assertEqual(self._d(txt, '例4'), ['xref'])

    def test_foreign_paper_qualified_ref_is_xref(self):
        txt = "> 在 Arnold … УМН. 1979 一文 §9 的注 7 中即已指出这种联系.\n"
        self.assertEqual(self._d(txt, '评注7'), ['xref'])

    def test_bare_prose_ref_stays_real(self):
        """🔴 没有 § 锚定的裸提及（`由例 3 即得`）不豁免——本支不是洗地机。"""
        txt = "由例 3 即得。\n"
        self.assertEqual(self._d(txt, '例3'), ['real'])
        self.assertEqual(_sup(txt, ['例3'], ch=3), set())

    def test_bold_entry_head_stays_real(self):
        """🔴 粗体条头否决对不可扫描键同样生效（真漏登记的最强信号）。"""
        txt = "> **注 7**：若一个力学系中包含有用杆、铰链等等连接起来的质点。\n"
        self.assertEqual(self._d(txt, '评注7'), ['real'])
        self.assertEqual(_sup(txt, ['评注7'], ch=3), set())

    def test_mixed_occurrences_stay_reported(self):
        """一处 § 锚定 + 一处裸提及 → 全键照报（豁免要求**每一处**都有域）。"""
        txt = "如 §1.3 的例 3 所证。\n\n由例 3 即得。\n"
        self.assertEqual(sorted(self._d(txt, '例3')), ['real', 'xref'])
        self.assertEqual(_sup(txt, ['例3'], ch=3), set())

    def test_single_number_is_not_read_as_chapter_ref(self):
        """🔴 单段号不得喂给跨章支：第 5 章里的 `由例 3 即得` 是本节自己的例，
        不是「第 3 章的回指」——跨章一支对不可扫描键整体关闭。"""
        txt = "由例 3 即得。\n"
        self.assertEqual(MOD.mention_domains_of(txt, '例3', ch=5), ['real'])

    def test_adjacent_section_anchor_is_xref(self):
        """⑥ 锚点**紧贴号前**（Vakil ch4 实测 `我们会在 §11.3.11 中…`）：
        `_XREF_ANCHOR_TAIL_RE` 要求锚点后自带号，故这一形态此前落到 real。"""
        for txt, key, ch in (("我们会在 §11.3.11 中把这一点说精确。\n", '11.3-11', 4),
                             ("We will make this precise in §11.3.11.\n", '11.3-11', 4)):
            with self.subTest(txt=txt[:18]):
                self.assertEqual(MOD.mention_domains_of(txt, key, ch), ['xref'])
                self.assertEqual(_sup(txt, [key], ch=ch), {key})

    def test_adjacent_anchor_does_not_wash_bare_prose(self):
        """🔴 没有锚点的裸号散文提及照旧在报告桶（本支只认 `§`/`Sect.`/`Art.` 字面）。"""
        txt = "We return to 11.3.11 below.\n"
        self.assertEqual(MOD.mention_domains_of(txt, '11.3-11', 4), ['real'])
        self.assertEqual(_sup(txt, ['11.3-11'], ch=4), set())


# ------------------------------------------ ⑦ 散文小节回指（契约小节作证）
class TestProseSubsectionRef(unittest.TestCase):
    """`See Miscellanea 7.5.5.` 一类**正文里**的小节回指。

    出厂的 title 支只认 `### §N.M` 标题行形态；印面把同一号写进散文时，那个号
    明明登记在**本章契约的 section 节点**里，却被读成「正文提到一个未登记条目」。
    放宽的代价由「契约名册 + 号前不得是条目词」两支守卫兜住（Evans / statistical-
    inference 51 书普查实测：16/20 个 GAINED 键由此归域，无一名册外键被放过）。
    """

    def test_registered_subsection_ref_is_title(self):
        txt = "**4.8** Referring to Miscellanea 4.9.1, we get the bound.\n"
        sk = {'4-8', '4-9-1'}
        self.assertEqual(_doms(txt, '4.9-1', ch=4, sec_keys=sk), ['title'])
        self.assertEqual(_sup(txt, ['4.9-1'], ch=4, sec_keys=sk), {'4.9-1'})

    def test_number_outside_contract_roster_stays_real(self):
        """🔴 名册外不放行：契约只登记到 `4.9`，`4.9.1` 仍须核对（是否漏开条目）。"""
        txt = "Referring to Miscellanea 4.9.1, we get the bound.\n"
        self.assertEqual(_doms(txt, '4.9-1', ch=4, sec_keys={'4-9'}), ['real'])
        self.assertEqual(_sup(txt, ['4.9-1'], ch=4, sec_keys={'4-9'}), set())

    def test_entry_label_before_voids_the_branch(self):
        """🔴 同形撞车：`Definition 4.9.1` 是条目回指，即便名册里有 `4-9-1` 也照判。"""
        txt = "Recall Definition 4.9.1 for the estimate.\n"
        self.assertEqual(_doms(txt, '4.9-1', ch=4, sec_keys={'4-9-1'}), ['real'])

    def test_missing_roster_disables_branch(self):
        """无 sec_keys（契约读不出）= 本支整体关闭，行为回到改前。"""
        txt = "Referring to Miscellanea 4.9.1.\n"
        self.assertEqual(_doms(txt, '4.9-1', ch=4), ['real'])

    def test_heading_line_is_out_of_prose_branches(self):
        """🔴 两支新豁免**只判散文行**：`## 5.6.5 一个标题`（名册内）与
        `### §2.3.9 应用`（名册外）都属 v2 钉住的「条目被错写成标题」形态，照旧 real。"""
        self.assertEqual(_doms("## 5.6.5 一个标题\n", '5.6.5', ch=5,
                               sec_keys={'5-6-5'}), ['real'])
        self.assertEqual(_doms("### §2.3.9 应用\n", '2.3.9', ch=2,
                               sec_keys={'2-3-3'}), ['real'])
        self.assertEqual(_doms("### §2.3.3 应用\n", '2.3.3', ch=2,
                               sec_keys={'2-3-3'}), ['title'],
                         '名册内的 § 标题仍走出厂那一支')


# ------------------------------------ ⑧ 粗体条头否决只对跨度自己的序标生效
class TestBoldHeadOwnOrdinalOnly(unittest.TestCase):
    def test_span_ordinal_still_vetoes(self):
        """🔴 条头序标本体否决不变：`**定理 6.1.2**` 写在第 5 章 = 条目放错章。"""
        txt = "**定理 6.1.2** 设 $\\varphi$ 为连续映射。\n"
        self.assertEqual(_doms(txt, '定理6.1.2', ch=5, sec_keys={'6-1-2'}), ['real'])
        self.assertEqual(_sup(txt, ['定理6.1.2'], ch=5, sec_keys={'6-1-2'}), set())

    def test_paragraph_head_not_in_contract_stays_real(self):
        """Vakil 实测（保留为**真信号**）：`**12.5.10.** 例如…` 是本跨度序标，
        而契约只登记到 `12.5`——粗体头无账 = 该走补登记，不得归域消音。"""
        txt = "**12.5.10.** For example (cf. Exercise 12.3.M), the scheme is regular.\n"
        self.assertEqual(_doms(txt, '12.5-10', ch=12, sec_keys={'12-5'}), ['real'])

    def test_earlier_ordinal_does_not_veto_later_ref(self):
        """🔴 反向：`**17.4.9 Revisiting Example 9.3.3.**` 的序标是 17.4.9，后面的
        `9.3.3` 只是标题里的跨章条目回指，旧否决把它一并读成 real（假阳）。"""
        txt = "**17.4.9 Revisiting Example 9.3.3.**\n\n> 该例说明…\n"
        self.assertEqual(_doms(txt, '9.3-3', ch=17, sec_keys={'17-4-9'}), ['chref'])
        self.assertEqual(_sup(txt, ['9.3-3'], ch=17, sec_keys={'17-4-9'}), {'9.3-3'})

    def test_blockquote_bold_span_still_reaches_eqref(self):
        """出厂校准过的假跨度（粗体在 `证明**` 处闭合）不受本次收窄影响。"""
        txt = "> **证明**：由 (4.2.6) 与 $f^{*}$ 即得。\n\\tag{4.2.6}\n"
        self.assertEqual(set(_doms(txt, '4.2-6', ch=4)), {'eqref', 'tag'},
                         '散文回指 (4.2.6) 走 tag 名册推翻条目词否决 -> eqref')
        self.assertEqual(_sup(txt, ['4.2-6'], ch=4), {'4.2-6'})


# ---------------------------------------------------------- ③ 句末句号守卫
class TestSentenceEndGuard(unittest.TestCase):
    def test_cn_sentence_final_period_is_scannable(self):
        txt = "> 至于 3 与 4，见习题 12.2.9 和 12.2.10。\n"
        self.assertEqual(set(_doms(txt, '12.2.10', ch=12)), {'exref'})
        self.assertEqual(_sup(txt, ['12.2-10'], ch=12), {'12.2-10'})

    def test_en_sentence_final_period_is_scannable(self):
        txt = "the construction given in Exercise 5.1.10.\n"
        self.assertEqual(MOD.mention_domains_of(txt, '5.1-10', 5), ['exref'])

    def test_deeper_number_still_blocked(self):
        """放行句末 `。`/`.` 不等于放开截断：`10.4-10.6` 里的 `10.4-10` 仍扫不到。"""
        txt = "见 第 10.4-10.6 节。\n"
        self.assertEqual(MOD.mention_domains_of(txt, '10.4-10', 10), ['absent'])


# ------------------------------------------------------- ④ 扫描侧区间幻影键
class TestScannerRangePhantom(unittest.TestCase):
    def _keys(self, text):
        d = tempfile.mkdtemp()
        p = os.path.join(d, 'ch10.md')
        with open(p, 'w', encoding='utf-8') as f:
            f.write(text)
        return keys_in_md(p, groups=[GroupConfig(type=3, name=['uncat'], scope=3)])[1]

    def test_no_phantom_from_cn_en_ranges(self):
        got = self._keys("见 第 10.4-10.6 节 与 Sections 7.2-7.4，另见 1.2.3.4。\n"
                         "**定义 10.5.2** 在册条目。\n")
        for bad in ('10.4-10', '7.2-7', '4.10-6', '1.2-3', '10.5.2'):
            self.assertNotIn(bad, got, '区间/更深号不得造出幻影键')
        self.assertIn('10.5-2', got, '真三段条头不受影响')

    def test_legit_two_and_three_level_keys_kept(self):
        got = self._keys("由 (10.1.3) 与 §10.4 的 5.6.5 即得。\n")
        self.assertTrue({'10.1-3', '5.6-5'} <= got, got)


# ------------------------------------------------------- untyped：词表未宣告
class TestUntypedSingleKey(unittest.TestCase):
    VOCAB = {'定理', '引理', '推论', '例', '定义', '图'}
    TXT = "> 1. 断言 1：若 $v,v'\\in E(r)$，则 $|v_u-v_u'|=|v-v'|$。\n"

    def test_undeclared_type_leaves_bucket_with_domain(self):
        self.assertEqual(MOD.mention_domains_of(self.TXT, '断言1', 2,
                                                type_vocab=self.VOCAB), ['untyped'])
        self.assertEqual(_sup(self.TXT, ['断言1'], ch=2, vocab=self.VOCAB), {'断言1'},
                         '本书无该类型计数器组 -> 契约永不可能开槽，提及桶无从核')

    def test_declared_type_still_reported(self):
        """🔴 词表宣告了 `断言` 即自动失效（真漏登记照旧报）。"""
        self.assertEqual(_sup(self.TXT, ['断言1'], ch=2,
                              vocab=self.VOCAB | {'断言'}), set())
        self.assertEqual(MOD.mention_domains_of(self.TXT, '断言1', 2,
                                                type_vocab=self.VOCAB | {'断言'}),
                         ['real'])

    def test_open_vocabulary_disables_branch(self):
        """🔴 含 `uncat` 兜底组 = 词表不闭合，本支整体关闭。"""
        self.assertIsNone(MOD._contract_type_vocab(
            BookConfig(ordinal=[GroupConfig(type=2, name=['uncat'], scope=2)],
                       language='cn')))
        self.assertEqual(_sup(self.TXT, ['断言1'], ch=2, vocab=None), set())

    def test_multi_number_key_not_in_this_branch(self):
        self.assertFalse(MOD._untyped_single_mention('断言1.2', self.VOCAB))
        self.assertEqual(sorted(MOD._contract_type_vocab(
            BookConfig(ordinal=[GroupConfig(type=2, name=['定理', 'Theorem'], scope=2),
                                GroupConfig(type=1, name=['例'], scope=2)],
                       language='cn'))), ['例', '定理'])


# ------------------------------------------------------------------ 端到端
def _node(key, type_='theorem'):
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


MD6 = (
    "# 第6章\n\n"
    "## §6.1 稳定集\n\n"
    "**定理 6.1.1** 契约在册的条目。\n\n"
    "> 1. 断言 1：若 $v,v'\\in E(r)$，则 $|v_u - v_u'| = |v-v'|$。\n\n"      # untyped
    "> 如 §1.3 的例 3 所证。\n\n"                                           # xref（§ 锚定）
    "> 我们改用定理 5.2.3 即得。\n\n"                                       # 跨章标签键
    "> 跟踪引理的证明可参见文献[20] 定理 3.4。\n\n"                          # 书目域
    "第二个性质 (6.1.7) 则由 $\\mu$ 的不变性得到。\n\n"                      # tag 名册 eqref
    "$$\n\\int_X f\\,d\\mu .\\qquad \\tag{6.1.7}\n$$\n\n"
    "> 改进版见 第 6.4-6.6 节。\n"                                          # 区间幻影（扫描侧）
)


class EndToEndTest(unittest.TestCase):
    def _run(self, md_text, guard=True):
        ext = tempfile.mkdtemp()
        d = os.path.join(ext, 'book_structure')
        os.makedirs(d, exist_ok=True)
        root = {'key': '6', 'type': 'chapter', 'sub_sec': [
            {'key': '6.1', 'type': 'section', 'sub_sec': [_node('6.1.1')]},
        ]}
        with open(os.path.join(d, 'ch6.json'), 'w', encoding='utf-8') as f:
            json.dump(root, f, ensure_ascii=False)
        md = os.path.join(ext, 'ch6.md')
        with open(md, 'w', encoding='utf-8') as f:
            f.write(md_text)
        # 词表**闭合**（无 uncat）：断言未宣告 -> untyped 支生效；`例` 已宣告 -> 只有
        # § 锚定（xref 支）才豁免。type=1 组是「标签+单号」键的**造键处**（`keys_in_md`
        # 的 ENTRY_RE_EN_SINGLE_C 分支），缺它则 `断言1`/`例3` 根本不进 all_keys。
        cfg = BookConfig(ordinal=[GroupConfig(type=3, name=['定理', '定义'], scope=2),
                                  GroupConfig(type=1, name=['例'], scope=2)],
                         language='cn')
        mgr = VerifyManager(_OnlyExtractB(), _Loader(cfg))
        if guard:
            return mgr.verify_one(6, 6, 6, md, ext)
        orig = MOD.domain_suppressed_mentions
        orig_inline = MOD._inline_only_entry_keys
        MOD.domain_suppressed_mentions = (
            lambda txt, keys, ch=None, sec_keys=None, type_vocab=None: set())
        MOD._inline_only_entry_keys = lambda lines, keys: []
        try:
            return mgr.verify_one(6, 6, 6, md, ext)
        finally:
            MOD.domain_suppressed_mentions = orig
            MOD._inline_only_entry_keys = orig_inline

    @staticmethod
    def _keys(res, field):
        return sorted(str(x) for x in (res.get(field) or []))

    def test_five_families_leave_report_buckets(self):
        on = self._run(MD6)
        em = self._keys(on, 'extra_mention') + self._keys(on, 'extra_entry')
        dom = self._keys(on, 'extra_mention_domain')
        for k in ('定理5.2.3', '定理3.4', '断言1', '例3', '6.1-7'):
            self.assertFalse(any(k in x for x in em),
                             '%s 应已归域豁免，实得 %r' % (k, em))
        for k in ('定理5.2.3', '断言1', '例3', '6.1-7'):
            self.assertTrue(any(k in x for x in dom),
                            '豁免必须留痕（不静默消失），缺 %s：%r' % (k, dom))
        # 🔴 扫描侧幻影：`第 6.4-6.6 节` 造出的假三段键根本不再进入 all_keys，
        # 故既不在报告桶、也不在豁免清单（不静默：判据在 `keys_in_md`，见上单测）。
        self.assertNotIn('6.4-6', self._keys(on, 'extra'))

    def test_same_chapter_stray_still_reported(self):
        """🔴 同章条目回指（`定理 6.1.2`，契约只到 6.1.1）不得被任何一支洗掉。"""
        on = self._run(MD6 + "\n> 由定理 6.1.2 即得。\n")
        self.assertTrue(any('定理6.1.2' in x or '6.1-2' in x
                            for x in self._keys(on, 'extra_mention')
                            + self._keys(on, 'extra_entry')),
                        '同章回指不属豁免域，实得 %r' % (on.get('extra_mention'),))

    def test_one_bare_mention_voids_the_xref_exemption(self):
        """🔴 同一键再加**一处无 § 锚定**的裸提及 → xref 豁免整体失效，照报。"""
        on = self._run(MD6 + "\n> 由例 3 即得。\n")
        self.assertTrue(any('例3' in x for x in self._keys(on, 'extra_mention')
                            + self._keys(on, 'extra_entry')),
                        '有一处无域出现就不许豁免，实得 %r'
                        % (self._keys(on, 'extra_mention'),))

    def test_widening_moves_only_extra_buckets(self):
        on, off = self._run(MD6), self._run(MD6, guard=False)
        for field in ('truly_missing', 'mentioned_only'):
            self.assertEqual(self._keys(on, field), self._keys(off, field), field)
        self.assertEqual(len(on.get('blocking') or []),
                         len(off.get('blocking') or []))
        for field in ('extra', 'extra_mention', 'extra_entry'):
            moved = set(self._keys(off, field)) - set(self._keys(on, field))
            if field == 'extra':
                # 扫描侧幻影只在 `extra` 里消失，其余移动键都必须能在 dom 查到。
                self.assertTrue(moved <= set(self._keys(on, 'extra_mention_domain'))
                                | {'6.4-6'}, field)
            else:
                self.assertTrue(moved <= set(self._keys(on, 'extra_mention_domain')),
                                field + ' 的被移键必须留痕')
        self.assertTrue(set(self._keys(on, 'extra_mention_domain')) >=
                        set(self._keys(off, 'extra_mention_domain')),
                        '豁免清单只可增长')


if __name__ == '__main__':
    unittest.main(verbosity=2)
