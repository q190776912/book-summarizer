r"""Q 层「印面标签 ↔ 展示式正文」配对判据（`q_tag_mismatch`）的正反例。

缺陷形态（Katok《Introduction to the Modern Theory of Dynamical Systems》ch2 §2.6
实测，2026-10-03）：写手**漏贴**一枚印面标签（印面 `(2.6.1)` 那行在交付里不带 tag），
随后把后面每一枚 `\tag` **整体错位一格**（印面 `(2.6.2)` 的式子挂成 `\tag{2.6.1}`），
末了再给印面**无号**的展示式贴一枚号补齐集合。

既有判据全部只看**号**：FABRICATED/MISSING 比集合成员、ORDER_MISMATCH 比首现顺序、
MISPLACED 比归属小节，`gate_units` 的契约 tag 对账也是**章级集合**比较——于是这条
错位链集合完整、顺序单调、归属正确，一路全绿，只有当某枚号被贴到别的章节时才偶然
露出一条 MISPLACED。本判据把号与式重新钉在一起，故正反例都必须钉死：

  正例 = 错位链必须开报（否则新族形同虚设）；
  反例 = 「合法改写 / 无载体 / 账太薄 / 过短」一律不判（放宽判据前先证不误伤，
         跨 51 书普查见 `tools/q_tag_mismatch_census.py`：hi=0.80 时 51 书 74 行，
         其中 24 行 r=1.00 集中在 Katok，其余为灰带待裁决）。
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

from tag_formula_pairing import (norm_math, pairing_problems,               # noqa: E402
                                 connector_share, printed_tag_bodies,
                                 summary_tag_bodies)


def _page(pg, labels, formulas):
    """构造一页 page_*.json：labels=[(y, '(N.M.K)')]，formulas=[(y, latex)]。"""
    return {
        "page_num": pg,
        "width": 612, "height": 792, "dpi": [150, 150],
        "text": [{"text": t,
                  "poly": [400, y, 470, y, 470, y + 14, 400, y + 14],
                  "score": 0.99} for y, t in labels],
        "formulas": [{"latex": lx, "bbox": [60, y, 380, y + 20],
                      "score": 0.98} for y, lx in formulas],
    }


class _Fixture(unittest.TestCase):
    HI = 0.80

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="q_tm_")
        self.book = self.tmp
        self.ext = os.path.join(self.tmp, "_extract")
        os.makedirs(self.ext)

    def _write_pages(self, pages):
        for pg, d in pages.items():
            with open(os.path.join(self.ext, "page_%03d.json" % pg),
                      "w", encoding="utf-8") as f:
                json.dump(d, f, ensure_ascii=False)

    def _write_md(self, blocks, name="Chapter2_2.6_x.md"):
        parts = ["## \u00a72.6 Stability\n"]
        for body, tag in blocks:
            if tag is None:
                parts.append("$$\n%s\n$$\n\n" % body)
            else:
                parts.append("$$\n%s\n\\tag{%s}\n$$\n\n" % (body, tag))
        fp = os.path.join(self.book, name)
        with open(fp, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))
        return fp

    def _run(self, md, ignore=None, hi=None, min_body=12, ch=2, start=1, end=2):
        return pairing_problems(self.ext, ch, start, end, md, ncomp=3,
                                lead="digit", ignore=ignore,
                                hi=self.HI if hi is None else hi,
                                min_body=min_body)


E1 = r"h\circ g=F_{L}\circ h \quad\mathrm{~o r ~}\quad h=F_{L}^{-1}\circ h\circ g."
E2 = r"\tilde{h}=L^{-1}\tilde{g}+L^{-1}\circ\tilde{h}\circ(L+\tilde{g})."
E3 = r"\tilde{h}=h_{1}e_{1}+h_{2}e_{2},\qquad\tilde{g}=g_{1}e_{1}+g_{2}e_{2}."
E4 = (r"\begin{array}{r}{h_{1}=\lambda_{1}^{-1}g_{1}+\lambda_{1}^{-1}h_{1}"
      r"\circ(L+\tilde{g}),}\\ {h_{2}=\lambda_{2}^{-1}g_{2}"
      r"+\lambda_{2}^{-1}h_{2}\circ(L+\tilde{g}).}\end{array}")
E5 = r"\|h_{2}\|\leq\frac{\|g_{2}\|}{1-|\lambda_{2}|}."


class TestShiftedByOneIsCaught(_Fixture):
    r"""Katok §2.6 实测形态：印面 (2.6.1) 未贴 tag，其后每枚 tag 前移一格。"""

    def setUp(self):
        super().setUp()
        self._write_pages({
            1: _page(1, [(100, "(2.6.1)"), (300, "(2.6.2)"), (500, "(2.6.3)")],
                     [(100, E1), (300, E2), (500, E3)]),
            2: _page(2, [(100, "(2.6.4)"), (300, "(2.6.5)")],
                     [(100, E4), (300, E5)]),
        })
        # 交付：E1 无号（漏贴）；E2 挂 2.6.1；E3 挂 2.6.2；E4 挂 2.6.3；E5 挂 2.6.4
        #（E5 印面 2.6.5，交付把它的号前移一格）
        self.md = self._write_md([(E1, None), (E2, "2.6.1"), (E3, "2.6.2"),
                                  (E4, "2.6.3"), (E5, "2.6.4")])

    def test_ledger_has_five_printed_tags(self):
        led = printed_tag_bodies(self.ext, 2, 1, 2, ncomp=3, lead="digit")
        self.assertEqual(sorted(led), ["2.6.1", "2.6.2", "2.6.3", "2.6.4", "2.6.5"])

    def test_three_shifted_tags_reported(self):
        rows = self._run(self.md)
        got = {r["number"]: r for r in rows}
        # E2/E3/E4 三枚都配到了前一格那号的正文；E5 配的是印面 (2.6.5) 的正文，
        # 但交付写的是 `\tag{2.6.4}` —— 同样必须开报。
        for n in ("2.6.1", "2.6.2", "2.6.3"):
            self.assertIn(n, got, "漏报错位 %s" % n)
            self.assertEqual(got[n]["status"], "TAG_MISMATCH")
        self.assertIn("2.6.4", got)

    def test_reported_row_names_the_printed_owner(self):
        rows = {r["number"]: r for r in self._run(self.md)}
        self.assertIn("(2.6.2)", rows["2.6.1"]["source_text"])
        self.assertIn("相符 r=1.00", rows["2.6.1"]["source_text"])

    def test_ignore_silences_a_registered_number(self):
        self.assertEqual(self._run(self.md, ignore={"2.6.1"}),
                         [r for r in self._run(self.md) if r["number"] != "2.6.1"])

    def test_wire_keys_present(self):
        r"""🔴 三处消费面必须同步认得这个键，否则报告静默丢族（formula_tag /
        base.DEFAULT_RESULT / report）。漂移过一次就会永久漏报。"""
        from verify.script.base import DEFAULT_RESULT
        from formula_tag import _EMPTY_Q
        self.assertIn("q_tag_mismatch", _EMPTY_Q)
        self.assertIn("q_tag_mismatch", DEFAULT_RESULT)
        self.assertEqual(_EMPTY_Q["q_tag_mismatch"], [])

class TestCorrectPairingIsSilent(_Fixture):
    def test_all_tags_match_their_own_printed_body(self):
        self._write_pages({
            1: _page(1, [(100, "(2.6.1)"), (300, "(2.6.2)"), (500, "(2.6.3)")],
                     [(100, E1), (300, E2), (500, E3)]),
            2: _page(2, [(100, "(2.6.4)")], [(100, E4)]),
        })
        md = self._write_md([(E1, "2.6.1"), (E2, "2.6.2"), (E3, "2.6.3"),
                             (E4, "2.6.4")])
        self.assertEqual(self._run(md), [])

    def test_reworded_body_is_not_judged(self):
        r"""正文哪边都配不上 = 内容改写（散文重排 / Tier 压缩），本族不判。"""
        self._write_pages({
            1: _page(1, [(100, "(2.6.1)"), (300, "(2.6.2)"), (500, "(2.6.3)")],
                     [(100, E1), (300, E2), (500, E3)]),
            2: _page(2, [(100, "(2.6.4)")], [(100, E4)]),
        })
        md = self._write_md([("q = \\sum_{n=1}^{\\infty} n^{-s}", "2.6.1"),
                             ("\\zeta(s) = \\prod_{p}(1-p^{-s})^{-1}", "2.6.2"),
                             (E3, "2.6.3"), (E4, "2.6.4")])
        nums = {r["number"] for r in self._run(md)}
        self.assertNotIn("2.6.1", nums)
        self.assertNotIn("2.6.2", nums)

    def test_number_without_carrier_page_is_skipped(self):
        r"""总结的号在书侧查无载体（known_book 白名单 / 抽取漏收）→ MISSING 一支已管。"""
        self._write_pages({
            1: _page(1, [(100, "(2.6.1)"), (300, "(2.6.2)"), (500, "(2.6.3)")],
                     [(100, E1), (300, E2), (500, E3)]),
            2: _page(2, [(100, "(2.6.4)")], [(100, E4)]),
        })
        md = self._write_md([(E1, "2.6.1"), (E2, "2.6.2"), (E3, "2.6.9"),
                             (E4, "2.6.4")])
        self.assertEqual(self._run(md), [])

    def test_thin_ledger_is_not_judged(self):
        r"""书侧账 <3 条 = 抽取没建立可比真值（老 OCR 页 / 无编号书 / 段数配错）→
        无证据不判（与 Q 层 MISPLACED / ORDER 同一约定）。"""
        self._write_pages({
            1: _page(1, [(100, "(2.6.1)")], [(100, E1)]),
        })
        md = self._write_md([(E2, "2.6.1")])
        self.assertEqual(self._run(md), [])

    def test_short_body_is_not_judged(self):
        self._write_pages({
            1: _page(1, [(100, "(2.6.1)"), (300, "(2.6.2)"), (500, "(2.6.3)")],
                     [(100, E1), (300, E2), (500, E3)]),
            2: _page(2, [(100, "(2.6.4)")], [(100, E4)]),
        })
        md = self._write_md([("a=b", "2.6.1"), (E2, "2.6.2"), (E3, "2.6.3"),
                             (E4, "2.6.4")])
        self.assertNotIn("2.6.1", {r["number"] for r in self._run(md)})


class TestLabelShapesAndNormalization(_Fixture):
    def test_tail_glued_label_builds_ledger(self):
        r"""形态②：标签被 OCR 并进公式行尾（`… (8)`）也要进账，正文不含号。"""
        self._write_pages({
            1: _page(1, [], [(100, E1 + " (2.6.1)"), (300, E2 + " (2.6.2)")]),
            2: _page(2, [(100, "(2.6.3)")], [(100, E3)]),
        })
        led = printed_tag_bodies(self.ext, 2, 1, 2, ncomp=3, lead="digit")
        self.assertIn("2.6.1", led)
        # 记账时尾号已被剔出正文：账里存的必须是**不含** `(2.6.1)` 的纯式子
        self.assertNotIn("2.6.1", led["2.6.1"][0] + "")
        md = self._write_md([(E2, "2.6.1"), (E1, "2.6.2"), (E3, "2.6.3")])
        rows = {r["number"] for r in self._run(md)}
        self.assertEqual(rows, {"2.6.1", "2.6.2"})

    def test_text_line_glued_label_builds_ledger(self):
        r"""形态④（Katok p669 (20.5.5)/(20.5.6) 实测，2026-10-03）：印面右缘的号被 OCR
        并进**整行公式的文字转写**尾部时也要进账。旧账只认 latex 侧的尾号（形态②），
        这类号在书侧**没有载体**，于是「同号配错式」一路读不出。"""
        self._write_pages({
            1: _page(1,
                     [(100, "W(x) :=Uo-(Ws(o(x))) and Wu(x) :=Up*(Wu(o-t(x) (2.6.1)"),
                      (300, "(2.6.2)")],
                     [(100, E1), (300, E2)]),
            2: _page(2, [(100, "(2.6.3)")], [(100, E3)]),
        })
        led = printed_tag_bodies(self.ext, 2, 1, 2, ncomp=3, lead="digit")
        self.assertIn("2.6.1", led)
        # 账身取的是**同行那条展示式 latex**（不是 OCR 的乱码文字行），且不含号
        self.assertEqual(norm_math(led["2.6.1"][0]), norm_math(E1))
        self.assertNotIn("2.6.1", led["2.6.1"][0])
        # 有了这份载体，E1/E2 互换才读得出来
        md = self._write_md([(E1, "2.6.2"), (E2, "2.6.1"), (E3, "2.6.3")])
        self.assertEqual({r["number"] for r in self._run(md)}, {"2.6.1", "2.6.2"})

    def test_prose_reference_ending_a_line_is_not_a_label(self):
        r"""形态④的反例钉：散文回指即便以 `(20.5.1)` 收尾，也**不**与任何展示式同行，
        窄窗（±`_GLUED_TEXT_LABEL_DY`）必须把它挡在账外，否则 prose 会把别人的式子
        认领过来，账本反而失去判别力。"""
        self._write_pages({
            1: _page(1,
                     [(400, "Using Lemma 20.5.1 and the Fubini Theorem, (20.5.1)")],
                     [(100, E1), (300, E2)]),
            2: _page(2, [], []),
        })
        led = printed_tag_bodies(self.ext, 20, 1, 2, ncomp=3, lead="digit")
        self.assertNotIn("20.5.1", led)

    def test_fragment_line_does_not_steal_the_label(self):
        r"""兜底窗口里的**碎片行**不得冒充账身（Katok p669 (20.5.7) 实测，2026-10-03）：
        右缘号与式子之间夹着 OCR 拆出的 `i = u , s` 一类短行，逐字最近的是碎片，
        旧兜底把碎片记成账身 → 正文过短被拒 → 该号在书侧没有载体。"""
        self._write_pages({
            1: _page(1, [(300, "(2.6.1)"), (500, "(2.6.2)")],
                     [(300, r"i = u , s"), (330, E1), (500, E2)]),
            2: _page(2, [], []),
        })
        led = printed_tag_bodies(self.ext, 2, 1, 2, ncomp=3, lead="digit")
        self.assertIn("2.6.1", led)
        self.assertEqual(norm_math(led["2.6.1"][0]), norm_math(E1))
        self.assertEqual(norm_math(led["2.6.2"][0]), norm_math(E2))

    def test_array_shell_does_not_dilute_ratio(self):
        r"""回归钉（Katok §2.6 (2.6.7)/(2.6.8) 实测）：OCR 把两行共用一个号的显示式存成
        `\begin{array}{r} … \end{array}`，壳留着会把逐字相同的正文稀释到 r=0.78，
        差 0.02 就漏报整条错位链。"""
        bare = r"h_{1}=\lambda_{1}^{-1}g_{1}+\lambda_{1}^{-1}h_{1}\circ(L+\tilde{g})"
        wrapped = r"\begin{array}{r}{%s}\end{array}" % bare
        self.assertEqual(norm_math(bare), norm_math(wrapped))

    def test_cn_fullwidth_label_recognised(self):
        self._write_pages({
            1: _page(1, [(100, "\uff082.6.1\uff09"), (300, "(2.6.2)"),
                         (500, "(2.6.3)")],
                     [(100, E1), (300, E2), (500, E3)]),
            2: _page(2, [(100, "(2.6.4)")], [(100, E4)]),
        })
        led = printed_tag_bodies(self.ext, 2, 1, 2, ncomp=3, lead="digit")
        self.assertIn("2.6.1", led)

    def test_two_lines_sharing_one_array_still_pairable(self):
        r"""印面一枚号对应 array 的一行、另一枚号对应同一段落第二行时，两侧账都拿到
        整条 array：不得因为「同一条正文挂在两个号下」而误报（无判别力 = 不判）。"""
        two = (r"\begin{array}{l}{a=b}\\{c=d}\end{array}")
        self._write_pages({
            1: _page(1, [(100, "(2.6.1)"), (110, "(2.6.2)"), (500, "(2.6.3)")],
                     [(100, two), (500, E3)]),
            2: _page(2, [(100, "(2.6.4)")], [(100, E4)]),
        })
        md = self._write_md([(two, "2.6.1"), (E3, "2.6.2"), (E3, "2.6.3"),
                             (E4, "2.6.4")])
        self.assertNotIn("2.6.1", {r["number"] for r in self._run(md)})

    def test_summary_blocks_parsed_in_document_order(self):
        self._write_pages({1: _page(1, [(100, "(2.6.1)")], [(100, E1)])})
        md = self._write_md([(E1, "2.6.1"), (E2, None), (E3, "2.6.3")])
        self.assertEqual([n for n, _b in summary_tag_bodies(md)],
                         ["2.6.1", "2.6.3"])


class TestCensusFalsePositivesAreSilent(_Fixture):
    r"""51 书普查（hi=0.80 → 74 行）里除 Katok 外**全部**经印面取证裁决为假阳，
    三类成因各钉一条回归例；每条都是「先有代理用 `page_*.json` 逐行 y 序重建书侧
    真值、再确认总结配号没错」的实测形态，不是臆造的边界情形。"""

    def test_big_delimiter_shells_are_stripped_both_sides(self):
        r"""real-analysis ch14 (14.6)/(14.7) 实测：书侧 OCR 用 `\biggl\{…\biggr\}`，
        交付用 `\left\{…\right\}`。旧壳表里 `big|Big|bigg|Bigg` 后接 `\b`，遇
        `\biggl` 无词边界 → 五个字母留在账里，逐字相同的正文被稀释到 r=0.79，
        而「只差下标的另一式」给到 0.95 → 误报。"""
        src = r"\biggl\{f_{1}(x)=\sum_{n\leq x}a(n)^{+}\biggr\}"
        ours = r"\left\{f_{1}(x)=\sum_{n\leq x}a(n)^{+}\right\}"
        self.assertEqual(norm_math(src), norm_math(ours))
        self._write_pages({
            1: _page(1, [(100, "(2.6.1)"), (300, "(2.6.2)")],
                     [(100, src), (300, r"\biggl\{f_{2}(x)=\sum_{n\leq x}"
                                    r"a(n)^{-}\biggr\}")]),
            2: _page(2, [(100, "(2.6.3)")], [(100, E3)]),
        })
        md = self._write_md([(ours, "2.6.1"),
                             (r"\left\{f_{2}(x)=\sum_{n\leq x}a(n)^{-}\right\}",
                              "2.6.2"),
                             (E3, "2.6.3")])
        self.assertEqual(self._run(md), [])

    def test_duplicated_ocr_line_does_not_inflate_the_ledger(self):
        r"""Apostol ch11 / Arnold ch9 实测：同一行公式被 OCR 双检成两条 `formulas`
        条目，±25px 并窗把重复行也拼进账身 → 书侧串长一倍 → r_self 系统性偏低。
        并窗须按归一化去重。"""
        self._write_pages({
            1: _page(1, [(100, "(2.6.1)"), (300, "(2.6.2)"), (500, "(2.6.3)")],
                     [(100, E1), (108, E1), (300, E2), (500, E3)]),
            2: _page(2, [(100, "(2.6.4)")], [(100, E4)]),
        })
        led = printed_tag_bodies(self.ext, 2, 1, 2, ncomp=3, lead="digit")
        self.assertEqual(norm_math(led["2.6.1"][0]), norm_math(E1))
        md = self._write_md([(E1, "2.6.1"), (E2, "2.6.2"), (E3, "2.6.3"),
                             (E4, "2.6.4")])
        self.assertEqual(self._run(md), [])

    def test_holder_ownership_arbitration_silences_same_formula_twice(self):
        r"""Apostol ch11 (11.9)=(11.10) 实测：书里同一式子**印了两次**（引理估计在
        定理证明里回用），交付两格都贴对了。此时某格若因账本噪声 self_r 偏低，
        「另一号」的高匹配毫无判别力——归属仲裁：贴在 (m) 那一格的正文自己就配对
        了 (m)，则 n 那格像 (m) 不算错配。"""
        self._write_pages({
            1: _page(1, [(100, "(2.6.1)"), (300, "(2.6.2)"), (500, "(2.6.3)")],
                     [(100, E1), (300, E2), (500, E1)]),
            2: _page(2, [(100, "(2.6.4)")], [(100, E4)]),
        })
        # 交付：E1 同时贴 2.6.1 与 2.6.3（印面确实两处同式），2.6.2 贴 E2。
        # 再让 2.6.4 那格装 E1：它「高匹配 (2.6.1)」，但 (2.6.1) 那一格自己
        # 就配对了 E1 → 属同式两印，不报。
        md = self._write_md([(E1, "2.6.1"), (E2, "2.6.2"), (E1, "2.6.3"),
                             (E1, "2.6.4")])
        self.assertNotIn("2.6.4", {r["number"] for r in self._run(md)})

    def test_single_component_numbered_books_are_not_judged(self):
        r"""ncomp==1（编号形如 `(9)`，按节重启）整体不判：Arnold 经典力学 7/7、
        Apostol 16/16 全为假阳且**无一条真缺陷**可标定阈值——同骨架短式互为
        「高匹配的另一号」是这类书的结构性必然。这里故意造一条标准错位链，
        仍须返回空。"""
        self._write_pages({
            1: _page(1, [(100, "(9)"), (300, "(10)"), (500, "(11)")],
                     [(100, E1), (300, E2), (500, E3)]),
        })
        md = self._write_md([(E1, None), (E2, "9"), (E3, "10")],
                            name="Chapter2_2.6_x.md")
        self.assertEqual(pairing_problems(self.ext, 2, 1, 1, md, ncomp=1,
                                          lead="digit", hi=self.HI), [])

    # ---- Leinster ch5 实测串（交换图被 OCR 读成命令名串）--------------------
    # 印面 (5.3)/(5.15)/(5.17)/(5.21)/(5.23) 逐字取自 page_*.json，交付正文同样逐字
    # 取自该书 ch5 中英两版：两侧是**同一个式子**，只是箭头写法不同
    # （`A \xrightarrow{f_i} X_i` vs `A \stackrel{f_i}{\longrightarrow} X_i`）。
    P_STACK = (r"\left( A \ { \stackrel { f _ { i } } { \longrightarrow } } \ "
               r"X _ { i } \right) _ { i \in I }")
    P_OVERSET = (r"\left( A \overset { { \, \, f _ { I } \, } } \longrightarrow "
                 r"D ( I ) \right) _ { I \in \mathbf { I } }")
    P_XRIGHT = (r"\left( D ( I ) \xrightarrow { \ f _ { I } } A \right) _ "
                r"{ I \in \mathbf { I } }")
    P_ARRAY_GARB = (r"\begin{array} { l } { { X \longrightarrow \atop { } } } \\ "
                    r"{ { \iota \atop { } } } \\ { { \chi } } \end{array}")
    P_SPAN = r"X \leftarrow Z \rightarrow Y"
    D_RIGHT_FI = r"\bigl( A \xrightarrow{f_i} X_i \bigr)_{i \in I}"
    D_SPAN = r"Y \xleftarrow{\ s\ } X \xrightarrow{\ t\ } Z"

    def test_connector_dominated_ledger_entries_are_not_kept(self):
        r"""占比普查里 Leinster ch5 的账身 0.55~0.91（Katok 42 行的 claimed owner
        全是 0.000）：这类条目不进账——账身只剩箭头骨架时「像」不构成归属证据。"""
        self._write_pages({
            1: _page(1, [(100, "(2.6.1)"), (300, "(2.6.2)"), (500, "(2.6.3)")],
                     [(100, self.P_STACK), (300, self.P_ARRAY_GARB),
                      (500, self.P_SPAN)]),
            2: _page(2, [(100, "(2.6.4)"), (300, "(2.6.5)")],
                     [(100, E1), (300, E2)]),
        })
        led = printed_tag_bodies(self.ext, 2, 1, 2, ncomp=3, lead="digit")
        for n in ("2.6.1", "2.6.2", "2.6.3"):
            self.assertNotIn(n, led, "箭头词表撑起来的图不该进账")
        self.assertIn("2.6.4", led)
        self.assertIn("2.6.5", led)

    def test_correctly_tagged_diagrams_are_silent(self):
        r"""Leinster ch5 实测的 6 行假阳形态：交付 5.3/5.15 贴的是**自己那枚号**的
        式子，只因 OCR 把箭头读成 `stackrel…longrightarrow` / `xrightarrow` 两种写法
        （r_self 掉到 0.67）而「另一枚号」的乱码图给到 0.85 就开报。
        反向钉：同一份数据把闸门关掉（`_CONNECTOR_SHARE_MAX` 抬高）**必须**开报，
        否则这条静音等于什么都没测。"""
        self._write_pages({
            1: _page(1, [(100, "(2.6.1)"), (300, "(2.6.2)"), (500, "(2.6.3)"),
                         (700, "(2.6.4)")],
                     [(100, self.P_STACK), (300, self.P_XRIGHT),
                      (500, self.P_OVERSET), (700, self.P_ARRAY_GARB)]),
            2: _page(2, [(100, "(2.6.5)"), (300, "(2.6.6)"), (500, "(2.6.7)")],
                     [(100, E1), (300, E2), (500, E4)]),
        })
        md = self._write_md([(self.D_RIGHT_FI, "2.6.1"),
                             (self.D_SPAN, "2.6.4"),
                             (E1, "2.6.5"), (E2, "2.6.6"), (E4, "2.6.7")])
        self.assertEqual(self._run(md), [])
        import tag_formula_pairing as T
        old = T._CONNECTOR_SHARE_MAX
        try:
            T._CONNECTOR_SHARE_MAX = 9.9          # 关掉新闸门
            nums = {r["number"] for r in self._run(md)}
        finally:
            T._CONNECTOR_SHARE_MAX = old
        self.assertIn("2.6.1", nums, "闸门一关就该复现原假阳，否则静音是无的放矢")

    def test_real_math_using_circ_is_still_evidence(self):
        r"""词表只收**无歧义的多字符箭头/堆叠名**：Katok 的正文里 `\circ`/`\bigcap`/
        `\overline` 是实义运算，占比必须为 0，否则真错位链会被新闸门静音。"""
        for s in (E1, E2, E4, E5,
                  r"\bigcap_{n\in\mathbb{Z}}\overline{\operatorname{Int}(\Omega)}"):
            self.assertLess(connector_share(norm_math(s)), 0.50, s)
        self.assertGreaterEqual(connector_share(norm_math(self.P_ARRAY_GARB)),
                                0.50)


if __name__ == "__main__":
    unittest.main(verbosity=2)
