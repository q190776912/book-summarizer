# -*- coding: utf-8 -*-
r"""Tests for lib/figure_alt.py — 写手侧 alt 的**唯一装配入口** `build_alt`。

为什么单独测这个函数：alt 的三段（标签词 / 号 / 题注体）规则**互相依赖**——
「体开头已经带了标签词」这一条必须同时看到前导和体才能裁决。分成两个函数各判一半
就是 2026-11-01 抓到 `Figure 3.10 Figure` / `Figure FIGURE F.1.` 的原因（p1097 实测
81 条脏 alt 全部源于此）。这里钉住：
  ① 号只认登记 `label`，题注里再找一个号的旧写法不许回来；
  ② 体除了标签词什么都不剩 ⇒ 体交空、前导保留「词 + 号」（正形，不删登记的字）；
  ③ 体里标签词之后还有内容 ⇒ 保内容，前导只补号（宁可不优雅，不删登记侧的字）；
  ④ 中文标签词同样走这两档（码位取自 `FIGURE_LABELS_DEFAULT`，测试不手敲汉字）；
  ⑤ 题注散文**中间**出现的 `figure` 不算前导，前导必须保持本书声明的书写形；
  ⑥ 每条产物再过一遍判据 ⇒ 净；
  ⑦ 题注没写标签词时的兜底书写形**合语种**（默认表首项是中文形，直取首项会串语种）；
  ⑧ 连字符不算粘连词（被判侧不并词、参照表两种词形都进），真粘连照旧要点名；
  ⑨ 登记题注里被 OCR 拆开的词（`configura.tions`）不许反过来把正词判成粘连
     （证人侧并回词内标点，空格仍算分隔符）；
  ⑩ 同一形但**连字符后面还带空格**（印面断词被 OCR 写成 `approxi- mated`）也照并：
     证人侧的标点合并规则若要求右边紧贴字母，这一形就进不了参照表，正词会被
     「切成两个证人词」判成粘连（p1104 A/B 控件：旧形判脏 / 新形判净）；
  ⑪ 但**句点带空格不许并**（`program-ming. We`）：小写化后粘成 `programmingwe` ⇒
     真证人词消失、写对的 `programming` 反被拆切判粘连
     （p1106 在 Koopman ch11/ch16 实测 8 行，工具要把对的 alt 改成 `program ming`）。
跑法（tests 目录不是包）：`python lib/tests/test_figure_alt_build.py`
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

from lib.figure_alt import (  # noqa: E402
    RE_DUP_LABEL, RE_LABELJUNK, build_alt, dirty, half_junk, judge, lead_junk, raw_toks,
    strip_lead, toks, why, witness_toks,
)
from lib.figure_io import FIGURE_LABELS_DEFAULT  # noqa: E402

EN = [u"Figure"]
ZH = [FIGURE_LABELS_DEFAULT[0]]          # 中文书声明的第一个标签词形（不手敲码位）


def verdict(alt, label, cap):
    d = judge(alt, label or u"", [(u"C", cap or u"")])
    return u"脏:" + u",".join(sorted(
        {k for k in (d["label"] and u"碎字", d["stuck"] and u"粘连",
                     d["jam"] and u"jam") if k})) if dirty(d) else u"净"


class TestBuildAlt(unittest.TestCase):
    def assertClean(self, alt, label, cap, msg=None):
        self.assertEqual(verdict(alt, label, cap), u"净", msg or alt)
        self.assertIsNone(RE_LABELJUNK.search(alt), alt)
        self.assertIsNone(RE_DUP_LABEL.match(alt), alt)

    # -------------------------------------------------------------- 常规形
    def test_plain_caption_keeps_declared_word_and_number(self):
        cap = u"Figure 10.4 An additive treatment effect."
        self.assertEqual(build_alt(cap, u"10.4", EN),
                         u"Figure 10.4 An additive treatment effect.")

    def test_period_after_number_does_not_block_the_strip(self):
        u"""印面主流体例 `Figure 1.1. Caption`：号剥干净、号后句点进前导，不许拼回第二个号。"""
        cap = u"Figure 1.1. The combined effect of h and k"
        alt = build_alt(cap, u"1.1", EN)
        self.assertEqual(alt, u"Figure 1.1 The combined effect of h and k")
        self.assertClean(alt, u"1.1", cap)

    def test_label_word_in_the_middle_is_not_a_prefix(self):
        u"""题注散文里的 `figure 3` 不算前导 ⇒ 前导仍是声明形，体一字不少。"""
        cap = u"Figure 3.2 A map (see figure 3 for details)"
        alt = build_alt(cap, u"3.2", EN)
        self.assertTrue(alt.startswith(u"Figure 3.2 A map"), alt)
        self.assertIn(u"see figure 3 for details", alt)
        self.assertClean(alt, u"3.2", cap)

    # ---------------------------------------------------- ② 体只剩标签词
    def test_body_that_is_only_the_label_word_moves_to_the_prefix(self):
        u"""Fraleigh 登记 `'3.10 Figure'`：体交空 ⇒ `Figure 3.10`（旧写法造 `Figure 3.10 Figure`）。"""
        cap = u"3.10 Figure"
        alt = build_alt(cap, u"3.10", EN)
        self.assertEqual(alt, u"Figure 3.10")
        self.assertClean(alt, u"3.10", cap)

    def test_jammed_label_word_after_number_same_ruling(self):
        cap = u"3.6Figure"
        self.assertEqual(build_alt(cap, u"3.6", EN), u"Figure 3.6")

    def test_cjk_body_that_is_only_the_label_word(self):
        u"""丘维声登记 `'3.9图'`：同一档，中文形 ⇒ `图 3.9`，不是 `3.9 图`。"""
        cap = u"3.9" + ZH[0]
        alt = build_alt(cap, u"3.9", ZH)
        self.assertEqual(alt, ZH[0] + u" 3.9")
        self.assertClean(alt, u"3.9", cap)

    # ------------------------------------------- ③ 体里还有内容 ⇒ 保内容
    def test_content_after_the_label_word_survives(self):
        u"""Fraleigh 图 5.10：剥掉体的 `Figure` 就丢了 `(a) Subgroup diagram…` ⇒ 改前导只补号。"""
        cap = (u"5.10Figure(a) Subgroup diagram for Z4.(b) Subgroup diagram forV.")
        alt = build_alt(cap, u"5.10", EN)
        self.assertIn(u"Subgroup diagram for Z4.", alt)
        self.assertFalse(alt.startswith(u"Figure 5.10 Figure"), alt)
        self.assertClean(alt, u"5.10", cap)

    def test_unnamed_figure_with_uppercase_label_word(self):
        u"""Katok 附录图：label 空、题注是 `FIGURE F.1.` ⇒ 整条题注就是 alt，不再前挂一个 `Figure`。"""
        cap = u"FIGURE F.1."
        alt = build_alt(cap, u"", EN)
        self.assertEqual(alt, u"FIGURE F.1.")
        self.assertClean(alt, u"", cap)

    def test_cjk_caption_with_letter_numbered_body_keeps_its_own_word(self):
        u"""数学物理方程 `'图 A.1'`：字母子号不是纯数字 ⇒ 号剥不动 ⇒ 前导让位，体原样保留。"""
        cap = ZH[0] + u" A.1"
        alt = build_alt(cap, u"", ZH)
        self.assertEqual(alt, cap)
        self.assertClean(alt, u"", cap)

    # ---------------------------------------------------------------- 其它
    def test_empty_caption_falls_back_to_word_and_number(self):
        alt = build_alt(u"", u"7.3", EN)
        self.assertEqual(alt, u"Figure 7.3")

    def test_default_label_table_falls_back_by_language(self):
        u"""⑦ 题注自己**没写**标签词时的兜底形必须**合语种**。默认表是
        `["图", "Figure", "Fig"]`（首项中文），直取 `labels[0]` 会把中文形塞进英文题注
        （`图 10.4 An additive…`）；判据三档都不看语种 ⇒ 这类串**判不出脏**，只能在这里
        拦（回写工具把登记题注当来源腿时会走同一条兜底）。"""
        self.assertEqual(build_alt(u"An additive treatment effect.", u"10.4",
                                   FIGURE_LABELS_DEFAULT),
                         u"Figure 10.4 An additive treatment effect.")
        self.assertEqual(build_alt(u"加性处理效应", u"3.9", FIGURE_LABELS_DEFAULT),
                         FIGURE_LABELS_DEFAULT[0] + u" 3.9 加性处理效应")

    def test_quotes_never_reach_the_attribute_value(self):
        cap = u'Figure 2.1 A "bad" chart'
        self.assertNotIn(u'"', build_alt(cap, u"2.1", EN))

    def test_body_fn_hook_is_used_when_given(self):
        u"""写手可以把本书的体改写规则接进来（`embed_figures.short_caption` 那条通道）。"""
        def body_fn(cap, label, labels):
            return u"STUB"
        self.assertEqual(build_alt(u"Figure 1.1 x", u"1.1", EN, body_fn),
                         u"Figure 1.1 STUB")

    # ------------------------------------------- 粘连词判据的连字符边界
    def test_hyphenated_compound_is_never_a_jam(self):
        u"""⑧ 判据自己造的假阳（p1103 逐字取证，两枪）：alt 写**人给的复合词**
        `least-squares` / `Creasy-Williams`，登记题注写印面/OCR 形 `least squares` /
        `Creasy- Williams`。旧词表把 alt 侧并成 `leastsquares` 再去问「别处有没有这个
        词」⇒ 没人写过的 token 一律「查无此词」，且工具接着想把**写对的那侧**覆写成
        OCR 侧。现在：被判侧不并连字符（`raw_toks`），参照表两种词形都进（`witness_toks`）。
        代价照实说：印面真把两词粘住时若写手已用连字符分开，这一档不再报——连字符本身
        就是「人已裁决」的证据。"""
        for lab, cap, alt in (
                (u"13.1", u"Best least squares fit of the data.",
                 u"Figure 13.1 Best least-squares fit of the data."),
                (u"13.1", u"Best least-squares fit of the data.",
                 u"Figure 13.1 Best least squares fit of the data."),
                (u"12.2.3", u"F statistic defining Creasy- Williams confidence set.",
                 u"Figure 12.2.3 F statistic defining Creasy-Williams confidence set.")):
            self.assertEqual(verdict(alt, lab, cap), u"净", alt)
        # 真粘连没有分隔符可用 ⇒ 照旧点名（这条例外的边界）
        cap = u"Best least squares fit of the data."
        glued = u"Figure 13.1 Best leastsquares fit of the data."
        self.assertEqual(judge(glued, u"13.1", [(u"C", cap)])["jam"], [u"leastsquares"])
        self.assertEqual(verdict(glued, u"13.1", cap), u"脏:jam")
        # 两份词表各自钉住，防止「只留一份」漂回去
        self.assertEqual(toks(u"least-squares"), [u"leastsquares"])
        self.assertEqual(raw_toks(u"least-squares"), [u"least", u"squares"])
        self.assertEqual(witness_toks(u"least-squares"),
                         set([u"leastsquares", u"least", u"squares"]))

    def test_ocr_split_word_in_caption_does_not_convict_correct_alt(self):
        u"""⑨ 第三枪（Modern Robotics ch5 图 5.32 实测）：登记题注把行末连字符读成了
        **句点** `configura.tions` ⇒ 旧词表在句点处切出 `configura`/`tions` 两个碎片，
        反过来把写对的 `configurations` 判成「能切成两个证人词」的粘连词，工具接着
        把正词拆成两个半词回写。⇒ 证人侧词表必须把**词内标点**并回（空格仍算分隔符，
        否则印面真是两个词的 `least squares` 会被并成一个假词）。"""
        cap = (u"Figure 5.32: Left: The 2R robot arm. Right: The arm at four "
               u"different configura.tions.")
        alt = (u"Figure 5.32: Left: The 2R robot arm. Right: The arm at four "
               u"different configurations.")
        self.assertEqual(verdict(alt, u"5.32", cap), u"净")
        self.assertEqual(toks(u"configura.tions"), [u"configurations"])
        self.assertEqual(raw_toks(u"configura.tions"), [u"configura", u"tions"])
        # 空格仍是分隔符：印面两个词不许被并成一个假证人词
        self.assertEqual(toks(u"least squares"), [u"least", u"squares"])

    def test_printed_hyphenation_with_space_does_not_convict(self):
        u"""⑩ ⑨ 的**连字符 + 空格**变体（p1104 A/B 控件）：OCR 把印面断词写成
        `approxi- mated` ⇒ 证人侧的合并若要求标点右边紧贴字母，这一形切不开 ⇒ 参照表里
        只有两个碎片 ⇒ 写对的 `approximated` 反倒被 `split_ok` 判成粘连词。
        🔴 放宽**只给连字符**：句点带空格是句末标点，`s` 又先小写过 ⇒ `ming. We` 会被粘成
        `programmingwe`、真证人词从参照表里**消失**，写对的 `programming` 照样被判粘连
        （p1106 在 Koopman ch11/ch16 实测 8 行；工具当时要把对的 alt 改成 `program ming`）。
        被判侧仍走 `raw_toks` ⇒ 真粘连照旧点名。"""
        for shape in (u"approxi- mated", u"Creasy- Williams"):
            alt = (u"Figure 3.2 The approximated error is small." if u"approxi" in shape
                   else u"Figure 3.2 The Creasy-Williams error is small.")
            cap = u"The %s error is small." % shape
            self.assertEqual(verdict(alt, u"3.2", cap), u"净", shape)
        self.assertEqual(toks(u"approxi- mated"), [u"approximated"])
        self.assertEqual(raw_toks(u"approxi- mated"), [u"approxi", u"mated"])
        # 句末标点不许参与合并（Koopman 那 8 行的根因：`ming. We` 粘成 `mingwe`
        # ⇒ 真证人词消失 ⇒ 写对的 `programming` 反被拆切判粘连）
        self.assertEqual(toks(u"program-ming. We formulated"),
                         [u"programming", u"we", u"formulated"])
        cap = (u"Fig. 11.1 Switching the toggle. Top panel: Application of approximate "
               u"dynamic program-ming. We formulated the cost with y = O.7.")
        alt = (u"Fig. 11.1 Switching the toggle switch by approximate dynamic "
               u"programming (top) and by temporal pulses (bottom).")
        self.assertEqual(verdict(alt, u"11.1", cap), u"净")
        # 关掉放宽即复现（控件：旧合并形下同一对必须判脏）
        import re as _re

        def old_toks(s):
            t = (s or u"").lower()
            return [x for x in _re.split(r"[^a-z0-9]+",
                                         _re.sub(u"(?<=[a-z])[-.](?=[a-z])", u"", t))
                    if x]

        self.assertEqual(old_toks(u"approxi- mated"), [u"approxi", u"mated"])
        self.assertNotIn(u"approximated", set(old_toks(u"The approxi- mated x.")))
        # 真粘连（无分隔符）不受影响
        self.assertEqual(judge(u"Figure 3.2 The approximatederror is small.", u"3.2",
                               [(u"C", u"The approxi- mated error is small.")])["jam"],
                         [u"approximatederror"])

    def test_period_with_space_is_sentence_break_not_word_break(self):
        u"""⑪ ⑩ 的负向控件（防「顺手把句点也放宽」漂回去）：题注里
        `regres-sion. Each model` 这种「断词 + 句号 + 空格」的常见 OCR 形，证人表必须
        同时给出 `regression` 与 `each`，不许产出 `regressioneach`（那正是 Koopman ch16
        图 16.2 上写对的 `regression` 消失的路径）。"""
        cap = (u"Fig. 16.2 kernel ridge regres-sion. Each model was trained on the "
               u"same dataset.")
        ref = witness_toks(strip_lead(cap, u"16.2"))
        self.assertIn(u"regression", ref)
        self.assertIn(u"each", ref)
        self.assertNotIn(u"regressioneach", ref)
        alt = (u"Fig. 16.2 Performance comparison between EDMD, Gaussian processes, "
               u"and kernel ridge regression. Each model was trained on the same data.")
        self.assertEqual(verdict(alt, u"16.2", cap), u"净")


class TestHalfJumbledLabel(unittest.TestCase):
    u"""`label` 档第三形：号拆在**词中间**（`Figure FIGU RE 14.12`，MSDA ch14 实测）。

    旧两档都漏它：`RE_LABELJUNK` 要 `FIG` 与 `U` 之间带空白，`label_frags` 只连 1–3
    字母片段（`FIGU` 长 4 进不了表）。放宽必须带**号锚**，否则两类实测假阳会复活：
    中文 alt 里散落的单字母连成 `fig`（Rising Sea ch23）与 `FIGURE9`（裸整数号粘连，
    Rosen ch12）。p1131 全架量面：收紧后净增 4 行，全是 MSDA ch14 那两张图。
    """

    def test_half_jumble_convicted_and_clean_form_not(self):
        cap = u"A plot of residuals versus log population."
        bad = u"Figure FIGU RE 14.12 A plot of residuals versus"
        good = u"Figure 14.12 A plot of residuals versus log population."
        self.assertTrue(half_junk(bad), bad)
        self.assertTrue(lead_junk(bad), bad)
        d = judge(bad, u"14.12", [(u"C", cap), (u"D", good)])
        self.assertTrue(dirty(d), why(d))
        self.assertIn(u"词中半拆形", why(d))
        self.assertEqual(verdict(good, u"14.12", cap), u"净")

    def test_correctly_spelled_word_is_never_a_half_jumble(self):
        u"""放宽不许把**写对**的整词判成碎字：`Figure`/`Fig.`/`FIGURE` 连写都不命中。"""
        for s in (u"Figure 14.12 A plot", u"Fig. 14.12 A plot", u"FIGURE 3.4 The x",
                  u"Figure Figure 3.4 The x"):        # 重复号另有档，这里只认半拆
            self.assertFalse(half_junk(s), s)

    def test_no_real_number_anchor_means_no_conviction(self):
        u"""号锚缺失 ⇒ 一律不判（24 字符兜底是两类假阳的入口）。"""
        self.assertFalse(half_junk(u"see F I G here"))          # 散落单字母
        self.assertFalse(half_junk(u"FIGURE9"))                  # 裸整数粘连
        self.assertFalse(lead_junk(u"FIGURE9"))

    def test_strip_lead_drops_the_half_jumbled_lead(self):
        u"""剥号必须连半拆字前导一起丢，否则重组会把碎字搬进新串（= 新碎字）。"""
        self.assertEqual(strip_lead(u"Figure FIGU RE 14.12 A plot of residuals",
                                    u"14.12"), u"A plot of residuals")


class TestDoubleEscapedEntity(unittest.TestCase):
    u"""`esc` 档：印面 `<` 被转义两遍（`&amp;lt;`，MSDA ch14 图 14.26 交付实测）。

    单转义不许命中——`S&amp;P` 是印面 `S&P` 的正形（p1127 印面裁带坐实）。
    p1131 全架量面：`&amp;lt;` 形只有 MSDA 那 2 行。
    """

    def test_double_escape_convicted(self):
        alt = (u"Figure 14.26 Linear relationships fit over the ranges 0 x .1, "
               u".1 &amp;lt; x .2")
        d = judge(alt, u"14.26", [(u"C", u"Linear relationships fit over the ranges")])
        self.assertTrue(dirty(d), why(d))
        self.assertIn(u"二次转义", why(d))

    def test_single_escape_is_clean(self):
        alt = u"Figure 2.17 Returns on the S&amp;P 500 during 2003"
        self.assertEqual(verdict(alt, u"2.17",
                                 u"Returns on the S&P 500 during 2003."), u"净")


if __name__ == "__main__":
    unittest.main()
