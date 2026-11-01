# -*- coding: utf-8 -*-
r"""test_clean_figure_alts.py — 图 alt 卫生回写的正向/负向闸（单元 / 交付 / 登记题注三腿）。

场景（MSDA ch10/ch14 实测形态）：`embed_figures.short_caption()` 把 OCR 题注 `[:40]`
硬截、不清图号拆字 ⇒ 单元正文里是
`Figure FIG U RE 10.4An additive treatment effec`，而**交付侧**是写手按印面核过的完整题注
（且与登记 caption 在内容上真的不同：交付 `C(y) = F(y - h)` / 登记 `G(y) = F(y − h)`）。
钉住的判据（p1082/p1083 三轮误判换来的）：
① 来源次序＝交付/另一单元侧**优先于**登记 caption ⇒ 不许把 OCR 稿盖回勘误；
② 与本轮串**逐字相同**的腿不算证人（units 与 units-translate 同源，MSDA 28 行全这形）；
③ 来源串的**散文**若带无佐证的粘连词（只有 OCR 稿这么写）⇒ 它不算证人 ⇒ 拒，须印面取证；
   但「脏在形制」（双图号 / 号后无空格）可由重组修掉 ⇒ 落（Lee ISM ch5 即这一形）；
   三腿逐字相同 ⇒ 没有证人 ⇒ 连判脏都不判（工具不猜词）；
④ 合法长词（`compactifications`）、印面断词（`approxi-mated`）、单子标号（`3.4A`）不许判脏；
⑤ 号后粘连只认「尾字母 ≥2 且与题注首词互为首尾前缀」，`3.4An` 才落；
⑥ 不跨语种改写（中文译侧 alt 对英文题注 ⇒ 拒那一腿，英文侧照修）；
⑦ 来源串开头的号必须就是本章登记号（不跨图搬题注）；
⑧ 前缀写法取该章多数净 alt 的形（多数 `Fig.` 时不把 `Figure` 写进去）；
⑨ 只换 `alt` 值：`src`/`width`/缩进/首行 DONE 标记/行数/换行符逐字节不动，同文件多条
   一次并行 splice，写完复跑归零；`--target` 与参照面解耦（修单元时交付仍是证人）。
⑩ 前导写法三档：本章净 alt → 本章脏 alt 的标签词∩**本书声明形** → 拒。章级 bail-out
   不再拦「根本不消费前导写法」的行（非纯编号行走登记腿）——Fraleigh/Katok 两处实测的
   静默失明；但**碎字形永远不作证据**（⑩ 的负向控件）。
⑪ 非纯编号形 label（unnamed 的 `''`、字母号 `F.1`）由**登记腿出厂装配**裁决，产物须
   逐字等于 `build_alt(caption, label, load_fig_labels(ext), short_caption)`（修完 ==
   将来重 merge），且受同一道「不跨语种」锁约束。
⑫ 连字符是人写的复合词标记，**不算粘连词**（被判侧按不并词形取 token、参照表两种词形
   都进）：否则 `Creasy-Williams` / `least-squares` 会被判脏，工具接着把写对的一侧覆写
   成 OCR 侧、或把核对过的长体截到 40 字符（p1103 实测两枪）。
⑬ 登记题注里被 OCR 拆开的词（`configura.tions`，行末连字符读成句点）不许反过来把正词
   判成粘连——否则「修」出来的串是把 `configurations` 拆成 `configura tions`（实测 4 行）。
⑭ 同一形的**连字符 + 空格**变体（印面断词被 OCR 写成 `approxi- mated`）照旧零写入：
   证人侧的标点合并若要求右边紧贴字母，这一形进不了参照表 ⇒ 正词被判粘连 ⇒ 工具把它
   拆成两个半词回写（p1104 A/B 控件：旧合并形判脏 / 现形判净）。
   🔴 反向也钉住：**句点带空格不许参与合并**（`regres-sion. Each`）——小写化后粘成
   `regressioneach` 会让真证人词消失，Koopman ch11/ch16 实测 8 行差点把写对的
   `programming`/`regression` 改成 `program ming`/`regres sion`（p1106 逐字坐实）。
⑮ **禁改短**（闸⑧ `shortens`）：改写后的体不许是任一**已写全的 alt**（含本轮串自己）
   的体的严格前缀。MSDA 图 14.26 交付腿实测：脏在二次转义 ⇒ 原地档改不动 ⇒ 走来源腿，
   第一条证人就是单元那条 47 字符的 `[:40]` 截断稿 ⇒ 旧工具把 137 字符改成 39 字符
   ＝亲手删印面内容。登记腿装配同受锁，但 **caption 不算长度证人**（否则每条长题注的
   出厂截断稿都被判改短，⑪「修完 == 将来重 merge」当场作废）；截断稿被拦 ⇒ 退到
   未截断的全题注形（两条腿：来源腿那一档与「非纯编号 label 走登记腿」那一档各测一条）。
⑯ **档 C 跨腿对齐（`--align-stale`，默认关）**：净 alt 也可按**登记腿的未截断装配**
   统一（目标形＝`cands_from_caption(...)[-1]`，不取截断稿、不取别的腿的串）。它的正当性
   押在「登记 caption == 印面」上 ⇒ 开关**按书裁定**，且四条锁一条不许少：闸③目标自证净
   （登记 caption 自己是 OCR 粘连稿 ⇒ 拒并要印面取证，且 caption **不作自己的证人**）、
   闸⑤不跨语种、闸⑧禁改短、另加「**体不许被清空**」（登记题注只剩标签词 ⇒ 装配出的
   正形体为空 ⇒ 拒）。默认关时一条都不许动。
"""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "lib"))
sys.path.insert(0, os.path.join(_ROOT, "tools"))
import lib.boot as _boot  # noqa: E402
_boot.setup()
import clean_figure_alts as C  # noqa: E402

MARK = ("<!-- book-summarizer DONE unit: id=%s type=desc key=D%s "
        "name=N%s -->")
JUNK104 = u"Figure FIG U RE 10.4An additive treatment effec"
GOOD104 = (u"Figure 10.4 An additive treatment effect. The solid line is F(y), "
           u"and the dotted line is C(y) = F(y - h).")
CAP104 = (u"An additive treatment effect. The solid line is F(y), and the dotted "
          u"line is G(y) = F(y − h).")


def img(src, alt):
    return ('    <img src="figure/%s" alt="%s" width="60%%" height="auto">'
            % (src, alt))


def _w(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    io.open(path, "w", encoding="utf-8", newline="").write(text)


def build(book, unit_alt, trans_alt=None, deliv_alt=None, cap=CAP104,
          label="10.4", ch="10", siblings=(), cfg_labels=None):
    u"""一本假书：`chN_fig<label>.png` 挂在单元（两半区）与交付上，各腿 alt 分别指定。

    `None` = 该腿不写这张图。`siblings` = [(label, caption, alt), …] 提供本章**其它图**的
    参照 alt（前导写法与证人词表都从这里来；一张参照都没有时按「本章无可参照的 alt 前缀
    写法」拒——那是设计，不是漏检）。`cfg_labels` = 本书声明的图标签词形，写进
    `_extract/verify_config.json` 的遗留 `figure.labels` 块；不给就用 `FIGURE_LABELS_DEFAULT`。
    返回 (src, 单元路径, 译路径, 交付路径)。
    """
    src = u"ch%s_fig%s.png" % (ch, label)
    os.makedirs(os.path.join(book, "figure"), exist_ok=True)
    _w(os.path.join(book, "figure", src), u"x")
    ext = os.path.join(book, "_extract")
    if cfg_labels is not None:
        _w(os.path.join(ext, "verify_config.json"),
           json.dumps({"figure": {"labels": cfg_labels}}, ensure_ascii=False))
    idx = [{"chapter": int(ch), "label": label, "file": u"figure/" + src,
            "caption": cap}]
    for (lab, c, _a) in siblings:
        idx.append({"chapter": int(ch), "label": lab,
                    "file": u"figure/ch%s_fig%s.png" % (ch, lab), "caption": c})
    _w(os.path.join(ext, "figure_index.json"), json.dumps(idx, ensure_ascii=False))
    paths = {}
    for side, alt in (("units", unit_alt), ("units-translate", trans_alt)):
        if alt is None:
            continue
        body = [MARK % ("0001", "1", "1"), u"文字。", u"", img(src, alt), u"",
                u"尾注。", u""]
        paths[side] = os.path.join(ext, "book_structure", side, "ch%s" % ch,
                                   "0001_desc_D1.md")
        _w(paths[side], u"\n".join(body))
    for n, (lab, _c, alt) in enumerate(siblings, start=2):
        _w(os.path.join(ext, "book_structure", "units", "ch%s" % ch,
                        "%04d_desc_D%d.md" % (n, n)),
           u"\n".join([MARK % ("%04d" % n, str(n), str(n)),
                       img(u"ch%s_fig%s.png" % (ch, lab), alt), u""]))
    dp = None
    if deliv_alt is not None:
        dp = os.path.join(book, u"Chapter%s_%s.1_x.md" % (ch, ch))
        _w(dp, u"# 章头\n\n%s\n\n尾注。\n" % img(src, deliv_alt))
    return src, paths.get("units"), paths.get("units-translate"), dp


def run(book, ch, commit=False, extra=()):
    old = sys.argv
    sys.argv = [sys.argv[0], book, ch] + list(extra) + (["--commit"] if commit else [])
    buf, real = io.StringIO(), sys.stdout
    sys.stdout = buf
    try:
        C.main()
    finally:
        sys.stdout = real
        sys.argv = old
    return buf.getvalue()


def read(path):
    return io.open(path, encoding="utf-8-sig", newline="").read() if path else None


def changed(a, b):
    la, lb = a.split(u"\n"), b.split(u"\n")
    return [(x, y) for (x, y) in zip(la, lb) if x != y]


CLEAN_SIB = (u"10.1", u"Normal probability plot.",
             u"Figure 10.1 Normal probability plot.")


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cfa_")
        self.book = os.path.join(self.tmp, "B")
        os.makedirs(self.book)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------------------------------------------------------------- 正向
    def test_dry_run_writes_nothing(self):
        _s, u1, u2, _d = build(self.book, JUNK104, JUNK104, GOOD104)
        before = {p: read(p) for p in (u1, u2)}
        out = run(self.book, "10")
        self.assertIn(u"命中 2 处", out)
        for p, b in before.items():
            self.assertEqual(read(p), b, u"dry-run 不许落盘")
        self.assertFalse(os.path.isdir(os.path.join(
            self.book, "_extract", "_bak_clean_figure_alts")))

    def test_commit_prefers_delivery_over_caption(self):
        u"""交付腿写净 ⇒ 单元按**交付文本**回写，而不是把 OCR caption（`G(y)`）盖回勘误。"""
        _s, u1, u2, dp = build(self.book, JUNK104, JUNK104, GOOD104)
        before = {p: read(p) for p in (u1, u2, dp)}
        out = run(self.book, "10", commit=True)
        self.assertIn(u"复跑残留 0", out)
        self.assertIn(u"形制自检失败 0", out)
        for p in (u1, u2):
            self.assertIn(u'alt="%s"' % GOOD104, read(p))
            self.assertNotIn(u"G(y)", read(p))
            self.assertEqual(
                [(x, y) for (x, y) in changed(before[p], read(p))],
                [(x, y) for (x, y) in changed(before[p], read(p))
                 if u"<img" in x and u'src="figure/ch10_fig10.4.png"' in x])
        self.assertEqual(read(dp), before[dp], u"target=units 不许碰交付")
        self.assertIn(u"resync_src_hash", out)
        self.assertIn(u"无可写项", run(self.book, "10"), u"再跑必须幂等")

    def test_two_images_in_one_file_land_separately(self):
        u"""同文件两条脏 alt 一次并行落 ⇒ 各自对位，不串台。"""
        book2 = os.path.join(self.tmp, "B2")
        os.makedirs(book2)
        src2 = u"ch10_fig10.5.png"
        a2 = u"Figure FIG U RE 10.5Histogram of 1000 bootstra"
        good2 = u"Figure 10.5 Histogram of 1000 bootstrap medians."
        cap2 = u"Histogram of 1000 bootstrap medians."
        _w(os.path.join(book2, "figure", src2), u"x")
        _s, up, _u2, _d = build(book2, JUNK104, None, GOOD104)
        _w(os.path.join(book2, "_extract", "figure_index.json"),
           json.dumps([{"chapter": 10, "label": "10.4",
                        "file": "figure/ch10_fig10.4.png", "caption": CAP104},
                       {"chapter": 10, "label": "10.5", "file": u"figure/" + src2,
                        "caption": cap2}], ensure_ascii=False))
        _w(up, u"\n".join([MARK % ("0001", "1", "1"), u"图一。", u"",
                           img(u"ch10_fig10.4.png", JUNK104), u"",
                           img(src2, a2), u"", u"尾注。", u""]))
        _w(os.path.join(book2, u"Chapter10_10.1_x.md"),
           u"# 章头\n\n%s\n\n%s\n\n尾注。\n"
           % (img(u"ch10_fig10.4.png", GOOD104), img(src2, good2)))
        out = run(book2, "10", commit=True)
        self.assertIn(u"命中 2 处", out)
        t = read(up)
        self.assertIn(u'alt="%s"' % GOOD104, t)
        self.assertIn(u'alt="%s"' % good2, t)
        self.assertIn(u"复跑残留 0", out)

    def test_target_delivery_uses_unit_as_donor(self):
        u"""参照面与可写面解耦：只修交付时，**单元**是证人；单元文件逐字节不动。"""
        _s, u1, _u2, dp = build(self.book, GOOD104, GOOD104, JUNK104)
        before = read(u1)
        self.assertIn(u"命中 1 处", run(self.book, "10",
                                        extra=[u"--target", "delivery"]))
        self.assertEqual(read(u1), before)
        out = run(self.book, "10", extra=[u"--target", "delivery"], commit=True)
        self.assertIn(u'alt="%s"' % GOOD104, read(dp))
        self.assertIn(u"复跑残留 0", out)
        self.assertEqual(read(u1), before)

    def test_delivery_jam_repaired_in_place_not_from_abridged_caption(self):
        u"""MSDA 图 9.7 形（印面 p373 取证）：交付 alt 是**完整**题注，只粘了一处
        `doubleexponential`；登记 caption 是**缩略**题注（丢了 `pseudorandom`）。
        ⇒ 必须原地补空格，不许搬 caption —— 搬过来就是把印面内容改短。"""
        cap = u"normal probability plot of 500 variables from a double exponential distribution"
        printed = (u"Figure 9.7 Normal probability plot of 500 pseudorandom variables "
                   u"from a doubleexponential distribution.")
        fixed = (u"Figure 9.7 Normal probability plot of 500 pseudorandom variables "
                 u"from a double exponential distribution.")
        abridged = u"Figure 9.7: normal probability plot of 500 variables from a double exponential distribution"
        _s, u1, u2, dp = build(self.book, abridged, abridged, printed,
                               cap=cap, label="9.7", ch="9",
                               siblings=[(u"9.1", u"Normal probability plot.",
                                          u"Figure 9.1 Normal probability plot.")])
        before_u = (read(u1), read(u2))
        out = run(self.book, "9", extra=[u"--target", "delivery", u"--list"])
        self.assertIn(u"命中 1 处", out)
        self.assertIn(u"来源腿 原地", out)
        self.assertIn(u"粘连词=doubleexponential", out)
        res = run(self.book, "9", extra=[u"--target", "delivery"], commit=True)
        self.assertIn(u'alt="%s"' % fixed, read(dp))
        self.assertIn(u"pseudorandom", read(dp))       # 印面词不许被 caption 抹掉
        self.assertNotIn(u"500 variables", read(dp))
        self.assertEqual((read(u1), read(u2)), before_u)
        self.assertIn(u"复跑残留 0", res)

    def test_in_place_refuses_half_word_truncation(self):
        u"""`short_caption()` 的 `[:40]` 半词截断不许走原地修（原地只会留下截断稿），
        必须交回来源腿重组 ⇒ `in_place` 对该串返回 None。"""
        legs = [(u"C", u"An additive treatment effect. The solid line is F(y)."),
                (u"D", GOOD104)]
        self.assertIsNone(C.in_place(JUNK104, u"10.4", u"Figure", legs))
        # 完整题注（只是前导碎字）⇒ 原地可修，且散文一字不改
        self.assertEqual(C.in_place(
            u"Figure FIG U RE 10.4 " + GOOD104.split(u"10.4 ", 1)[1],
            u"10.4", u"Figure", legs), GOOD104)

    # ---------------------------------------------------------------- 负向
    def test_in_place_refuses_alt_without_the_registered_number(self):
        u"""数值分析 ch13–16 形：alt 里**根本没写登记号**（`strip_lead` 的号可省，
        于是剥前导照返回整串）。原地档只会拼出「Figure 13.4 加原串」的重复号，
        必须交来源腿；且不许崩在「号之前那段」的查找上（p1093 普查即在此处 NoneType）。"""
        legs = [(u"C", u"Comparison of the three estimators."), (u"D", GOOD104)]
        self.assertIsNone(C.in_place(
            u"Figure Comparison of the three estimators", u"13.4", u"Figure", legs))

    # ---------------------------------------------------------------- 闸⑧ 禁改短
    def test_shortens_predicate(self):
        u"""`shortens` 的四种关系：严格前缀⇒拦；等长⇒放；更长⇒放；只缺登记 caption
        那一条更长的证人⇒**放**（caption 不算长度证人，否则每条长题注的出厂截断稿都被
        判改短，闸⑪「修完 == 将来重 merge」当场作废）。转义层数不算内容差。"""
        long_alt = u"Figure 14.26 Linear relationships fit over the ranges 0 x .5."
        legs = [(u"C", u"Linear relationships fit over the ranges 0 x .5."),
                (u"D", long_alt)]
        self.assertTrue(C.shortens(u"Figure 14.26 Linear relationships fit o",
                                   u"14.26", legs))
        self.assertFalse(C.shortens(long_alt, u"14.26", legs))            # 逐字等长
        self.assertFalse(C.shortens(long_alt + u" and more.", u"14.26", legs))
        # 只有 caption 比候选长、alt 证人都不比它长 ⇒ 出厂截断稿照写
        legs2 = [(u"C", u"An additive treatment effect. The solid line is F(y), and the "
                        u"dotted line is G(y) = F(y - h)."),
                 (u"D", u"Figure 10.4 An additive treatment effect. The solid line is F")]
        self.assertFalse(C.shortens(legs2[1][1], u"10.4", legs2))
        # `&amp;lt;` 与 `<` 是同一句话：按本形比才判得出「短了」
        legs3 = [(u"D", u"Figure 1 x &amp;lt; y &amp;lt; z tail.")]
        self.assertTrue(C.shortens(u"Figure 1 x < y <", u"1", legs3))

    def test_truncated_unit_donor_never_shortens_delivery(self):
        u"""MSDA 图 14.26 实测形（本档根治的那一枪）：交付腿脏在**二次转义**，原地档补
        空格改不动 ⇒ 走来源腿；而 `donor_order(D)` 第一条证人就是单元那条 47 字符的
        `[:40]` 半词截断稿。旧工具把交付从 137 字符改成 39 字符＝**删印面内容**。
        ⇒ 必须退到登记腿的全题注装配：转义清掉、尾巴一句不少。"""
        cap = (u"Linear relationships fit over the ranges 0 ≤ x ≤ .1, .1 < x ≤ .2, "
               u".2 < x ≤ .3, .3 < x ≤ .4, and .4 < x ≤ .5.")
        unit = u"Figure FIGU RE 14.26 Linear relationships fit o"
        deliv = (u"Figure 14.26 Linear relationships fit over the ranges 0 ≤ x ≤ .1, "
                 u".1 &amp;lt; x ≤ .2, .2&amp;lt;x≤.3, .3&amp;lt;x≤.4, and .4&amp;lt;x≤.5.")
        _s, _u1, _u2, dp = build(self.book, unit, unit, deliv, cap=cap, label="14.26",
                                 ch="14",
                                 siblings=[(u"14.1", u"Normal probability plot.",
                                           u"Figure 14.1 Normal probability plot.")])
        before = read(dp)
        out = run(self.book, "14", extra=[u"--target", "delivery", u"--list"])
        self.assertIn(u"命中 1 处", out)
        self.assertIn(u"来源腿 C", out)
        self.assertIn(u"二次转义", out)
        # 单元那条截断稿不许当来源：dry-run 列出的「新」不许是它重挂前导的产物
        self.assertNotIn(u"新 'Figure 14.26 Linear relationships fit o'", out)
        out = run(self.book, "14", extra=[u"--target", "delivery"], commit=True)
        self.assertIn(u"复跑残留 0", out)
        txt = read(dp)
        self.assertIn(u'alt="Figure 14.26 Linear relationships fit over the ranges '
                      u'0 ≤ x ≤ .1, .1 < x ≤ .2', txt)
        self.assertIn(u"and .4 < x ≤ .5.", txt)          # 尾巴一句不许被删
        self.assertNotIn(u"&amp;lt;", txt)
        self.assertNotIn(u'alt="%s"' % unit, txt)
        self.assertEqual(len(changed(before, txt)), 1)   # 只动 img 那一行

    def test_truncated_registry_clip_falls_back_to_full_caption(self):
        u"""同一道锁的**登记腿**侧（非纯编号 label 那一档，Fraleigh/Katok 形）：出厂装配
        把长题注截到 40，而交付 alt 自己已经写了 60 个字符 ⇒ 截断稿会删字 ⇒ 必须退到
        未截断的全题注形。没这一档的话，「修完」就是「把已核过的题注改短」。"""
        full = (u"Residuals from the regression of flow rate on depth for the "
                u"four candidate bandwidths")
        alt = u"Figure F.1 Residuals from the regression of flow rate on depthfor the fo"
        cap = u"FIGURE F.1. " + full
        _s, _u1, _u2, dp = build(self.book, None, None, alt, cap=cap, label=u"F.1",
                                 siblings=[(u"10.1", u"Normal plot.",
                                            u"Figure 10.1 Normal plot.")])
        out = run(self.book, "10", extra=[u"--target", "delivery", u"--list"])
        self.assertIn(u"命中 1 处", out)
        out = run(self.book, "10", extra=[u"--target", "delivery"], commit=True)
        self.assertIn(u"复跑残留 0", out)
        self.assertIn(u'alt="Figure F.1 ' + full + u'"', read(dp))
        self.assertNotIn(u"depthfor", read(dp))

    def test_label_form_repaired_when_prose_attested(self):
        u"""Lee ISM ch5 形：双图号 + `5.3Smooth`，三腿都脏**但脏在形制** ⇒ 只补空格、
        去重复号，散文 token 一字不动；`--target units` 不碰交付。"""
        cap = u"Fig. 5.3Smooth compatibility of slice charts"
        alt = u"Fig. 5.3 Fig. 5.3Smooth compatibility of slice charts"
        fixed = u"Fig. 5.3 Smooth compatibility of slice charts"
        _s, u1, u2, dp = build(
            self.book, alt, alt, alt, cap=cap, label="5.3", ch="5",
            siblings=[(u"5.1", u"A slice chart.", u"Fig. 5.1 A slice chart.")])
        before = {p: read(p) for p in (u1, u2, dp)}
        out = run(self.book, "5")
        self.assertIn(u"命中 2 处", out)
        self.assertIn(fixed, out)
        out = run(self.book, "5", commit=True)
        self.assertIn(u"复跑残留 0", out)
        for p in (u1, u2):
            self.assertIn(u'alt="%s"' % fixed, read(p))
            # 散文必须与登记题注**逐字同形**：只补空格、去重复号，不增删词
            self.assertEqual(C.strip_lead(fixed, "5.3"), C.strip_lead(cap, "5.3"))
            self.assertTrue(all(u"<img" in x for (x, _y)
                                in changed(before[p], read(p))))
        self.assertEqual(read(dp), before[dp], u"target=units 不许碰交付")

    def test_caption_with_unattested_jam_refuses(self):
        u"""p1082 教训②控件：登记 caption 里的粘连词在别处**无佐证**（`timesequence`
        能切成两个别处存在的词）⇒ caption 不是证人 ⇒ 零写入，拒因点名印面取证。"""
        cap = u"Plot showing timesequence of measurements of heat."
        alt = u"Figure FIG U RE 10.10Plot showing time sequence"
        _s, u1, _u2, _d = build(self.book, alt, alt, None, cap=cap, label="10.10",
                                siblings=[CLEAN_SIB])
        before = read(u1)
        out = run(self.book, "10")
        self.assertIn(u"命中 0 处", out)
        self.assertIn(u"印面取证", out)
        self.assertIn(u"无可写项", out)
        self.assertEqual(read(u1), before)

    def test_all_legs_identically_jumbled_is_not_adjudicable(self):
        u"""三腿（含登记题注）逐字相同 ⇒ 没有证人 ⇒ 不判脏也不写（工具不猜词）。"""
        s = u"Figure 10.13 Boxplot of theplatinum data."
        _s, u1, _u2, _d = build(self.book, s, s, s, cap=s, label="10.13")
        self.assertIn(u"命中 0 处", run(self.book, "10"))
        self.assertIn(s, read(u1))

    def test_spread_label_junk_caught(self):
        u"""散开形 `FI G U RE`（MSDA ch14 图 14.27 实测）+ 号后有空格 ⇒ 没有 stuck
        信号，只能靠「号前全短片段连成 FIGURE」认出；写对的 alt 不许被这条例误伤。"""
        spread = u"Figure FI G U RE 10.2 Survival functions for gui"
        good = (u"Figure 10.2 Survival functions for guinea pig lifetimes. "
                u"For purposes of visual clarity, the points have been jittered.")
        cap = u"Survival functions for guinea pig lifetimes."
        _s, u1, _u2, _d = build(self.book, spread, None, good, cap=cap,
                                label="10.2")
        out = run(self.book, "10", commit=True)
        self.assertIn(u"命中 1 处", out)
        self.assertIn(u'alt="%s"' % good, read(u1))

    def test_lead_junk_predicate(self):
        self.assertTrue(C.lead_junk(u"Figure FIG U RE 10.4An x"))
        self.assertTrue(C.lead_junk(u"Figure FI G U RE 14.27 Local linear"))
        self.assertFalse(C.lead_junk(u"Figure 14.27 Local linear estimates"))
        self.assertFalse(C.lead_junk(u"Fig. 5.1 A slice chart."))
        self.assertFalse(C.lead_junk(u"Figure 1.2 ANOVA of the data"))
        self.assertFalse(C.lead_junk(u"Figure 1.2 QQ plots of I B M scores"))

    def test_long_legal_word_not_flagged(self):
        u"""教训①：`compactifications` 这类合法长词不许判粘连。"""
        cap = u"Two compactifications of the moduli space."
        alt = u"Figure 3.1 Two compactifications of the moduli space."
        _s, u1, _u2, _d = build(self.book, alt, alt, None, cap=cap, label="3.1")
        self.assertIn(u"命中 0 处", run(self.book, "10"))

    def test_printed_hyphenation_does_not_flag_correct_word(self):
        u"""教训③：登记 caption 里的印面断词 `approxi-mated` 不许把写对的
        `approximated` 反判成粘连。"""
        cap = u"The approxi-mated error is small."
        alt = u"Figure 3.2 The approximated error is small."
        _s, u1, _u2, _d = build(self.book, alt, alt, None, cap=cap, label="3.2")
        self.assertIn(u"命中 0 处", run(self.book, "10"))

    def test_deliberate_hyphen_never_overwritten_by_ocr_caption(self):
        u"""教训④（p1103 两枪逐字取证）：alt 里的是**人写的复合词**，登记题注里的是
        印面/OCR 形 ⇒ 判据不许把连字符并成一个「别处没写过」的 token 再判它粘连。
        两枪的实测后果都是**把写对的一侧覆写成 OCR 侧**（第一枪写回 `Creasy- Williams`，
        第二枪更狠：登记腿那一档把 254 字符的核对稿截成 45 字符）。⇒ 零写入。"""
        cap = u"F statistic defining Creasy- Williams confidence set, X = 1"
        alt = u"Figure 12.2.3 F statistic defining Creasy-Williams confidence set, lambda = 1"
        _s, u1, u2, dp = build(self.book, alt, alt, alt, cap=cap, label="12.2.3",
                               ch="12", siblings=[(u"12.1", u"Normal plot.",
                                                    u"Figure 12.1 Normal plot.")])
        before = {p: read(p) for p in (u1, u2, dp)}
        out = run(self.book, "12", extra=("--target", "both"))
        self.assertIn(u"命中 0 处", out)
        self.assertEqual(before, {p: read(p) for p in (u1, u2, dp)},
                         u"连字符复合词不许被 OCR 拆词形覆写")

        cap2 = (u"Figure 13.1.A linear combination of sines and cosines with various "
                u"k-values up to 110(top panel), filtered by taking its best least "
                u"squares trigonometric polynomial approximation thatinvolves the "
                u"first 20 basis functions")
        alt2 = (u"Figure 13.1. A linear combination of sines and cosines with various "
                u"k-values up to 110 (top panel), filtered by taking its best "
                u"least-squares trigonometric polynomial approximation")
        book2 = os.path.join(self.tmp, "B2")
        os.makedirs(book2)
        _s2, v1, _v2, _d2 = build(book2, alt2, None, None, cap=cap2, label="13.1",
                                  ch="13", siblings=[(u"13.2", u"Alias plot.",
                                                      u"Figure 13.2 Alias plot.")])
        out = run(book2, "13")
        self.assertIn(u"命中 0 处", out)
        self.assertIn(alt2, read(v1))
        self.assertNotIn(u"least squares trigonometric polynomial approximation",
                         read(v1))

    def test_ocr_split_word_in_caption_does_not_split_correct_alt(self):
        u"""教训⑤（Modern Robotics ch5 图 5.32 实测）：登记题注把行末连字符读成句点
        （`configura.tions`）⇒ 旧词表拆出两个碎片，反过来把写对的 `configurations`
        判成粘连词，`in_place` 再「插一个空格」把正词拆成半词回写。⇒ 零写入。"""
        cap = (u"Figure 5.32: Left: The 2R robot arm. Right: The arm at four "
               u"different configura.tions.")
        alt = (u"Figure 5.32: Left: The 2R robot arm. Right: The arm at four "
               u"different configurations.")
        _s, u1, u2, dp = build(self.book, alt, alt, alt, cap=cap, label="5.32",
                               ch="5", siblings=[(u"5.1", u"Planar arm.",
                                                  u"Figure 5.1 Planar arm.")])
        before = {p: read(p) for p in (u1, u2, dp)}
        out = run(self.book, "5", extra=("--target", "both"))
        self.assertIn(u"命中 0 处", out)
        self.assertEqual(before, {p: read(p) for p in (u1, u2, dp)})
        self.assertNotIn(u"configura tions", read(u1))

    def test_printed_hyphenation_with_space_does_not_split_word(self):
        u"""教训⑥（⑬ 的「标点 + 空格」变体，p1104 A/B 控件）：登记题注把印面断词写成
        `approxi- mated` ⇒ 证人侧若要求标点右边紧贴字母，参照表里只有 `approxi`/`mated`
        两个碎片，写对的 `approximated` 被判粘连，`in_place` 再「补一个空格」把正词拆成
        半词回写。⇒ 零写入。"""
        cap = u"The approxi- mated error is small."
        alt = u"Figure 3.2 The approximated error is small."
        _s, u1, u2, dp = build(self.book, alt, alt, alt, cap=cap, label="3.2",
                               ch="3", siblings=[(u"3.1", u"Residual plot.",
                                                  u"Figure 3.1 Residual plot.")])
        before = {p: read(p) for p in (u1, u2, dp)}
        out = run(self.book, "3", extra=("--target", "both"))
        self.assertIn(u"命中 0 处", out)
        self.assertEqual(before, {p: read(p) for p in (u1, u2, dp)})
        self.assertNotIn(u"approxi mated", read(u1))

        # 句点带空格 = 句末标点，不许参与证人侧合并（Koopman ch16 图 16.2 实测形）
        cap_k = (u"Fig. 16.2 Performance comparison between EDMD, Gaussian processes, "
                 u"and kernel ridge regres-sion. Each model was trained on the same "
                 u"dataset collected from a 4 s trajectory of the free dynamics")
        alt_k = (u"Fig. 16.2 Performance comparison between EDMD, Gaussian processes, "
                 u"and kernel ridge regression. Each model was trained on the same "
                 u"dataset collected from a 4 s trajectory of the fr")
        book3 = os.path.join(self.tmp, "B3")
        os.makedirs(book3)
        _s3, w1, _w2, _w3 = build(book3, alt_k, None, None, cap=cap_k, label=u"16.2",
                                  ch=u"16",
                                  siblings=[(u"16.1", u"Phase plot.",
                                             u"Fig. 16.1 Phase plot.")])
        self.assertIn(u"命中 0 处", run(book3, u"16"))
        self.assertIn(alt_k, read(w1))
        self.assertNotIn(u"regres sion", read(w1))

    def test_true_glom_still_lands_when_caption_is_hyphen_split(self):
        u"""⑭ 的正向控件（防「只放宽不检出」漂成静默失明）：题注带 `approxi- mated`
        这种 OCR 断词时，alt 里**真的**粘成一团（`approximatederror`）仍须命中。
        落点由登记腿出厂装配裁决（`build_alt`），产物里那处断词照登记题注原样保留 ⇒
        与「修完 == 将来重 merge」同形，本测试不锁具体串、只锁「粘连没了」。"""
        cap = u"The approxi- mated error is small."
        dirty = u"Figure 3.2 The approximatederror is small."
        _s, u1, _u2, _d = build(self.book, dirty, None, None, cap=cap, label="3.2",
                                ch="3", siblings=[(u"3.1", u"Residual plot.",
                                                    u"Figure 3.1 Residual plot.")])
        out = run(self.book, "3", commit=True)
        self.assertIn(u"命中 1 处", out)
        self.assertNotIn(u"approximatederror", read(u1))
        self.assertIn(u"mated error is small.", read(u1))

    def test_single_letter_sublabel_legal_but_stuck_word_not(self):
        u"""`3.4A`（单子标号）合法；`3.4An`（号后直接跟题注首词）才判粘连并补空格。"""
        cap = u"An additive treatment effect."
        ok = u"Figure 3.4A An additive treatment effect."
        _s, _a, _b, _c = build(self.book, ok, ok, None, cap=cap, label="3.4")
        self.assertIn(u"命中 0 处", run(self.book, "10"))
        book2 = os.path.join(self.tmp, "B2")
        os.makedirs(book2)
        bad = u"Figure 3.4An additive treatment effect."
        _s2, u1, _u2, _d2 = build(book2, bad, None, None, cap=cap, label="3.4",
                                  siblings=[CLEAN_SIB])
        out = run(book2, "10", commit=True)
        self.assertIn(u"命中 1 处", out)
        self.assertIn(u'alt="Figure 3.4 An additive treatment effect."', read(u1))

    def test_no_cross_language_write(self):
        u"""译侧写中文、题注是英文 ⇒ 那一腿按语种拒，英文侧照修。"""
        cn = u"图 FIG U RE 10.4加性处理效应"
        _s, u1, u2, dp = build(self.book, JUNK104, cn, GOOD104)
        before = read(u2)
        out = run(self.book, "10", commit=True)
        self.assertIn(u"命中 1 处", out)
        self.assertIn(u"语种", out)
        self.assertEqual(read(u2), before, u"中文 alt 不许被英文题注覆盖")
        self.assertIn(u'alt="%s"' % GOOD104, read(u1))

    def test_donor_with_other_number_never_used(self):
        u"""来源腿串的号不是本章登记号 ⇒ 那份题注**绝不**当来源（不跨图搬题注）；
        退到 caption 时也只取本章这张的号。"""
        wrong = u"Figure 10.99 An additive treatment effect full text."
        dirty_cap = u"Fig U RE 10.4An additive treatment effect"
        _s, u1, _u2, _d = build(self.book, JUNK104, None, wrong,
                                cap=dirty_cap, siblings=[CLEAN_SIB])
        out = run(self.book, "10")
        self.assertIn(u"命中 1 处", out)
        self.assertNotIn(u"10.99", out)
        out = run(self.book, "10", commit=True)
        self.assertIn(u"复跑残留 0", out)
        self.assertIn(u'alt="Figure 10.4 An additive treatment effect"', read(u1))
        self.assertNotIn(u"10.99", read(u1))

    def test_prefix_form_follows_chapter_majority(self):
        u"""本章多数写 `Fig.` ⇒ 回写用 `Fig.`，不把来源腿的 `Figure` 形塞进来。"""
        _s, u1, _u2, _d = build(
            self.book, JUNK104, None, GOOD104,
            siblings=[(u"10.1", u"Normal probability plot.",
                       u"Fig. 10.1 Normal probability plot."),
                      (u"10.2", u"Scatter plot.", u"Fig. 10.2 Scatter plot.")])
        out = run(self.book, "10", commit=True)
        self.assertIn(u"命中 1 处", out)
        self.assertIn(u'alt="Fig. 10.4 An additive treatment effect. The solid line',
                      read(u1))
        self.assertNotIn(u'alt="Figure 10.4', read(u1))

    def test_all_dirty_chapter_falls_back_to_declared_word(self):
        u"""Fraleigh 图 3.10 实测形：登记题注写成「号 + 标签词」（`'10.4 Figure'`）⇒ 交付
        alt 是 `Figure 10.4 Figure`（图号写了两遍），而**本章一个净 alt 都没有**。旧判据
        整章拒（p1093 普查里 Fraleigh 56 行全落「本章无可参照的 alt 前缀写法」＝**静默
        失明**：脏得越彻底越修不了）⇒ 现在前导写法退到「本章脏 alt 的标签词 ∩ 本书声明形」，
        体只剩标签词那一档交登记腿出厂装配。🔴 并钉住不变式：**修完的 alt 逐字等于将来
        重 merge 的产物**（同一个 `build_alt` + 同一份 labels 取数）。"""
        cap = u"10.4 Figure"
        alt = u"Figure 10.4 Figure"
        _s, _u1, _u2, dp = build(self.book, None, None, alt, cap=cap, label="10.4")
        out = run(self.book, "10", extra=[u"--target", "delivery", u"--list"])
        self.assertIn(u"前导写法退到本章脏alt∩声明形", out)
        self.assertIn(u"'Figure'", out)
        expect = C.build_alt(cap, u"10.4",
                             C.load_fig_labels(os.path.join(self.book, "_extract")),
                             C.writer_body)
        self.assertEqual(expect, u"Figure 10.4")     # 不是 `图 10.4`，也不重复标签词
        out = run(self.book, "10", extra=[u"--target", "delivery"], commit=True)
        self.assertIn(u"命中 1 处", out)
        self.assertIn(u'alt="%s"' % expect, read(dp))
        self.assertIn(u"复跑残留 0", out)
        self.assertIn(u"无可写项",
                      run(self.book, "10", extra=[u"--target", "delivery"]))

    def test_unnamed_letter_label_lands_from_registry_leg(self):
        u"""Katok 附录图实测形：题注自己写着 `FIGURE F.1.`，交付 alt 是
        `Figure FIGURE F.1.`（`FIGURE FIGURE` 连续拆字档）。旧的两道闸都把它挡死：
        闸①「label 须纯编号形」（字母号 `F.1` 与 unnamed 的空串都算），以及章级前导
        bail-out（标签词后不紧贴数字 ⇒ 判不出写法 ⇒ 整章在行级之前就拒＝静默失明）。
        ⇒ 现在这类行**只**由登记腿出厂装配裁决：字母号归到本书声明形（`Figure F.1`），
        unnamed（label 空串）则整条题注就是 alt（`FIGURE F.1.`，前导不重说一遍）。
        🔴 两形的产物都必须逐字等于 `build_alt(cap, label, labels, short_caption)`。"""
        cap = u"FIGURE F.1."
        alt = u"Figure FIGURE F.1."
        ext = os.path.join(self.book, "_extract")
        labels = C.load_fig_labels(ext)
        for lab, want in ((u"F.1", u"Figure F.1"), (u"", u"FIGURE F.1.")):
            book = os.path.join(self.tmp, "BK" + (lab or u"x"))
            os.makedirs(book)
            _s, _u1, _u2, dp = build(book, None, None, alt, cap=cap,
                                     label=lab, ch="10")
            out = run(book, "10", extra=[u"--target", "delivery", u"--list"])
            self.assertIn(u"登记腿出厂装配", out)
            self.assertNotIn(u"本章无可参照的 alt 前缀写法", out)
            self.assertEqual(C.build_alt(cap, lab, labels, C.writer_body), want)
            out = run(book, "10", extra=[u"--target", "delivery"], commit=True)
            self.assertIn(u"命中 1 处", out)
            self.assertIn(u'alt="%s"' % want, read(dp))
            self.assertIn(u"复跑残留 0", out)

    def test_registry_leg_refuses_cross_language_caption_for_letter_label(self):
        u"""非纯编号腿也受「不跨语种」约束：登记题注是中文、本轮 alt 是英文碎字形 ⇒ 拒。
        没有这一道锁，`build_alt` 会把 `图 F.1 相空间…` 写进英文笔记（装配是净的，
        判据三档都放行 ⇒ 只有语种锁拦得住）。"""
        cap = u"相空间轨迹的投影图"
        alt = u"FIG U RE F.1 phase portrait projection"
        _s, u1, _u2, _d = build(self.book, alt, None, None, cap=cap, label=u"F.1",
                                siblings=[(u"10.9", u"Normal plot.",
                                          u"Figure 10.9 Normal plot.")])
        before = read(u1)
        out = run(self.book, "10", extra=[u"--list"])
        self.assertIn(u"语种", out)
        self.assertIn(u"命中 0 处", out)
        self.assertEqual(read(u1), before)

    def test_prefix_word_never_invented_when_book_declares_other_language(self):
        u"""第②档的**硬约束**：脏 alt 里的标签词必须与本书声明的形对得上才对账。
        本书只声明 `图`（verify_config）而本章 alt 全是 `Figure …` ⇒ 声明形里没有
        `Figure` ⇒ 照旧拒，不拿「看见了什么词」当体例证据。"""
        cap = u"10.4 Figure"
        alt = u"Figure 10.4 Figure"
        _s, _u1, _u2, dp = build(self.book, None, None, alt, cap=cap, label="10.4",
                                 cfg_labels=[u"图"])
        out = run(self.book, "10", extra=[u"--target", "delivery", u"--list"])
        self.assertIn(u"本章无可参照的 alt 前缀写法", out)
        self.assertIn(u"命中 0 处", out)
        self.assertIn(u'alt="%s"' % alt, read(dp), u"dry-run 不许落盘")

    def test_junk_only_chapter_still_refuses_prefix_form(self):
        u"""控件（钉住**设计而非漏检**）：本章 alt 全是拆字形 ⇒ 碎字不配当体例证据，
        即使题注腿是净的也不许自造前缀。脏 alt 的**散文**由登记腿裁决，前导写法仍拒。"""
        cap = u"An additive treatment effect."
        alt = u"Figure FIG U RE 10.4An additive treatment effec"
        _s, u1, _u2, _d = build(self.book, alt, None, None, cap=cap)
        out = run(self.book, "10", extra=[u"--list"])
        self.assertIn(u"本章无可参照的 alt 前缀写法", out)
        self.assertIn(u"命中 0 处", out)
        self.assertIn(alt, read(u1))

    def test_only_alt_value_moves(self):
        u"""闸⑦控件：首行 DONE 标记、`src`、`width`、缩进、行数与换行符逐字节不动。"""
        _s, u1, _u2, _d = build(self.book, JUNK104, None, GOOD104)
        before = read(u1)
        run(self.book, "10", commit=True)
        after = read(u1)
        self.assertEqual(before.split(u"\n")[0], after.split(u"\n")[0])
        self.assertEqual(len(before.split(u"\n")), len(after.split(u"\n")))
        self.assertEqual(before.count(u"\r\n"), after.count(u"\r\n"))
        norm = lambda t: re.sub(r'alt="[^"]*"', 'alt="X"', t)  # noqa: E731
        self.assertEqual(norm(before), norm(after))
        self.assertIn(u'    <img src="figure/ch10_fig10.4.png" alt="', after)

    def test_unregistered_src_is_refused_not_guessed(self):
        u"""正文挂了未登记的图名 ⇒ 不猜题注，只报告（那是改名波的账，归 resync_figure_refs）。"""
        _s, u1, _u2, _d = build(self.book, JUNK104, None, GOOD104)
        other = os.path.join(self.book, "_extract", "book_structure", "units",
                             "ch10", "0002_desc_D2.md")
        _w(other, u"\n".join([MARK % ("0002", "2", "2"),
                              img(u"ch10_fig99.9.png",
                                  u"Figure FIG U RE 99.9Whatever text here"), u""]))
        out = run(self.book, "10")
        self.assertIn(u"src 未在本章登记", out)
        self.assertIn(u"命中 1 处", out)
        self.assertIn(u"Figure FIG U RE 99.9", read(other))

    def test_unit_body_change_reminds_src_hash(self):
        _s, u1, _u2, _d = build(self.book, JUNK104, JUNK104, GOOD104)
        out = run(self.book, "10", commit=True)
        self.assertIn(u"resync_src_hash.py", out)
        self.assertIn(u"译侧 src_hash", out)


    # ---------------------------------------------------------------- 档 C 跨腿对齐
    def test_align_stale_off_by_default(self):
        u"""档 C **默认关**：净但陈旧的 alt（写手抄的是老 OCR 视图：登记题注写 `λ`、
        写手写 `lambda`）默认一条都不许动；显式开才改。"""
        cap = (u"Normal probability plot of 500 pseudorandom variables from a gamma "
               u"distribution with the shape parameter λ = 5.")
        stale = (u"Figure 9.8 Normal probability plot of 500 pseudorandom variables "
                 u"from a gamma distribution with the shape parameter lambda = 5.")
        _s, u1, u2, dp = build(self.book, stale, stale, stale, cap=cap, label="9.8",
                               ch="9", siblings=[CLEAN_SIB])
        before = {p: read(p) for p in (u1, u2, dp)}
        out = run(self.book, "9", extra=[u"--target", "both"])
        self.assertIn(u"命中 0 处", out)
        self.assertEqual(before, {p: read(p) for p in (u1, u2, dp)},
                         u"默认关时净 alt 一条都不许动")
        out = run(self.book, "9", extra=[u"--target", "both", u"--align-stale"])
        self.assertIn(u"命中 3 处", out)

    def test_align_stale_rewrites_to_registry_full_assembly(self):
        u"""开档 C：目标形＝登记腿的**未截断**装配（`cands_from_caption(...)[-1]`），
        不是别的腿的串、也不是出厂的 40 词截断稿。写完复跑归零、行数与换行符守恒。"""
        cap = (u"Normal probability plot of 500 pseudorandom variables from a gamma "
               u"distribution with the shape parameter λ = 5.")
        stale = (u"Figure 9.8 Normal probability plot of 500 pseudorandom variables "
                 u"from a gamma distribution with the shape parameter lambda = 5.")
        _s, u1, u2, dp = build(self.book, stale, stale, stale, cap=cap, label="9.8",
                               ch="9", siblings=[CLEAN_SIB])
        before = {p: read(p) for p in (u1, u2, dp)}
        ext = os.path.join(self.book, "_extract")
        labels = C.load_fig_labels(ext)
        want = C.build_alt(cap, u"9.8", labels, C.full_body)
        self.assertNotEqual(want, stale)
        out = run(self.book, "9", extra=[u"--target", "both", u"--align-stale"],
                  commit=True)
        self.assertIn(u"复跑残留 0", out)
        self.assertIn(u"形制自检失败 0", out)
        for p in (u1, u2, dp):
            t = read(p)
            self.assertIn(u'alt="%s"' % want, t)
            self.assertNotIn(u"lambda = 5", t)
            self.assertTrue(all(u"<img" in x for (x, _y)
                                in changed(before[p], t)),
                            u"只许动 alt 那一行")
        self.assertIn(u"无可写项",
                      run(self.book, "9", extra=[u"--target", "both",
                                                 u"--align-stale"]))

    def test_align_stale_refuses_when_target_shortens_witness(self):
        u"""闸⑧在档 C 下照样生效：登记题注是**缩略**题注时，装配出来的体是本轮 alt 的
        严格前缀 ⇒ 那是把已核过的印面内容改短 ⇒ 拒，零写入。"""
        cap = u"Normal probability plot of serum potassium data"
        alt = (u"Figure 10.4 Normal probability plot of serum potassium data. "
               u"A normal curve is fitted to their histogram.")
        _s, u1, u2, dp = build(self.book, alt, alt, alt, cap=cap, label="10.4",
                               ch="10", siblings=[CLEAN_SIB])
        before = {p: read(p) for p in (u1, u2, dp)}
        out = run(self.book, "10", extra=[u"--target", "both", u"--align-stale",
                                          u"--list"])
        self.assertIn(u"命中 0 处", out)
        self.assertIn(u"禁改短", out)
        self.assertEqual(before, {p: read(p) for p in (u1, u2, dp)})

    def test_align_stale_refuses_when_body_would_be_emptied(self):
        u"""档 C 的第四条锁：**体不许被清空**。登记题注只剩标签词（`'10.4 Figure'`）时
        装配出的正形体为空 ⇒ 那是登记侧欠账，不是这张图该没题注 ⇒ 拒，零写入。"""
        cap = u"10.4 Figure"
        alt = u"Figure 10.4 An additive treatment effect."
        _s, u1, u2, dp = build(self.book, alt, alt, alt, cap=cap, label="10.4",
                               ch="10", siblings=[CLEAN_SIB])
        before = {p: read(p) for p in (u1, u2, dp)}
        out = run(self.book, "10", extra=[u"--target", "both", u"--align-stale",
                                          u"--list"])
        self.assertIn(u"命中 0 处", out)
        self.assertIn(u"清空", out)
        self.assertEqual(before, {p: read(p) for p in (u1, u2, dp)})

    def test_align_stale_refuses_dirty_registry_caption(self):
        u"""闸③在档 C 下照样生效，而且**登记 caption 不许给自己作证**：题注里的 OCR 粘连
        词（`timesequence`）在别处有佐证（写手写对了 `time sequence`）⇒ 装配出来的目标
        自证不净 ⇒ 拒并要印面取证，绝不把 OCR 稿刷进所有腿。"""
        cap = u"Plot showing timesequence of measurements of heat."
        alt = u"Figure 10.10 Plot showing time sequence of measurements of heat."
        _s, u1, u2, dp = build(self.book, alt, alt, alt, cap=cap, label="10.10",
                               ch="10", siblings=[CLEAN_SIB])
        before = {p: read(p) for p in (u1, u2, dp)}
        out = run(self.book, "10", extra=[u"--target", "both", u"--align-stale",
                                          u"--list"])
        self.assertIn(u"命中 0 处", out)
        self.assertIn(u"印面取证", out)
        self.assertEqual(before, {p: read(p) for p in (u1, u2, dp)})

    def test_align_stale_never_crosses_language(self):
        u"""闸⑤在档 C 下照样生效：中文 alt 对英文登记题注 ⇒ 那一腿拒，英文侧照对齐。"""
        cap = u"Normal probability plot of the serum potassium data."
        cn = u"图 10.4 血清钾数据的正态概率图"
        en = u"Figure 10.4 Normal probability plot."
        _s, u1, u2, dp = build(self.book, cn, cn, en, cap=cap, label="10.4",
                               ch="10", siblings=[CLEAN_SIB])
        before_cn = {p: read(p) for p in (u1, u2)}
        out = run(self.book, "10", extra=[u"--target", "both", u"--align-stale",
                                          u"--list"])
        self.assertIn(u"语种", out)
        self.assertEqual(before_cn, {p: read(p) for p in (u1, u2)},
                         u"中文 alt 不许被英文登记题注覆盖")
        out = run(self.book, "10", extra=[u"--target", "both", u"--align-stale"],
                  commit=True)
        self.assertIn(u"复跑残留 0", out)
        self.assertEqual(before_cn, {p: read(p) for p in (u1, u2)})

    def test_align_stale_refuses_non_plain_label(self):
        u"""档 C 只走**纯编号形** label：非纯编号形（unnamed 的 `''`、字母号 `F.1`）的
        登记腿出厂装配不可靠 —— MSDA 附录B 实测：无名条目其实是**表**附录，装配出的
        目标是裸标签词 `Figure`（体被清空）⇒ 档 C 直接按行拒，不许拿它当目标形。"""
        cap = u"Cumulative standard normal distribution table"
        alt = u"Cumulative standard normal distribution table"
        _s, u1, u2, dp = build(self.book, None, None, alt, cap=cap, label=u"",
                               ch="10")
        before = read(dp)
        out = run(self.book, "10", extra=[u"--target", "delivery", u"--align-stale",
                                          u"--list"])
        self.assertIn(u"命中 0 处", out)
        self.assertIn(u"非纯编号形", out)
        self.assertEqual(read(dp), before)

    def test_align_stale_never_guesses_unregistered_src(self):
        u"""未登记的 src 在档 C 下也不许猜：没有登记题注就没有目标形 ⇒ 只报告。"""
        alt = u"Figure 99.9 Whatever text here"
        _s, u1, u2, dp = build(self.book, alt, None, None, cap=CAP104, label="10.4")
        other = os.path.join(self.book, "_extract", "book_structure", "units",
                             "ch10", "0002_desc_D2.md")
        _w(other, u"\n".join([MARK % ("0002", "2", "2"), img(u"ch10_fig99.9.png", alt), u""]))
        out = run(self.book, "10", extra=[u"--target", "both", u"--align-stale"])
        self.assertIn(u"src 未在本章登记", out)
        self.assertIn(alt, read(other))


if __name__ == "__main__":
    unittest.main(verbosity=2)
