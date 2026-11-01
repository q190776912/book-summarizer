# -*- coding: utf-8 -*-
r"""章级闸 ⑳（图 alt 卫生）的负向测试。

判据本体在 `lib/figure_alt.py`、取数在 `lib/figure_alt_audit.py`（出厂入口）；本文件锁
的是**门控口径**——p1108 全架自证（units 29 / units-translate 29 / D 58，与 `alt_rows`
直接数逐腿相等）说明数字对，但数字对不说明**该拦的拦、该放量的放量**。四档各有用例：

  ① 脏 alt → FAIL（处方指 SSOT 工具，不复述修法）；
  ② 未登记 src → **只报数**：alt 侧没有题注真值，判了就是逼写手凭空编题注（图改名波的账）；
  ③ 非纯编号 label 脏行 → FAIL 且注明「只能走登记腿出厂装配」；
  ④ 登记题注自己脏 → FAIL 照旧，但 note 点名「别在 alt 侧改字」。

🔴 静默失明控件（⑥⑦）：PASS 也必须把四桶计数打进 detail（门控没有 WARN 通道，只在
FAIL 时打 = 静音）；`only_unit` 收窄只许改**报告面**，不许把脏行筛成 0。
最后一组（⑧）锁**接线**：`gate_chapter` 必须真调出厂入口（判据写了没接线是闸门 bug）。
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, _ROOT)
for sub in ("lib", "tools", "tools/tests", "flows/write-source/script",
            "flows/extract/script", "verify/script"):
    sys.path.insert(0, os.path.join(_ROOT, sub))
import lib.boot as _boot  # noqa: E402
_boot.setup()
import lib.figure_alt_audit as AUD  # noqa: E402
# 假书生成器与回写工具共用（不复制一份：两份 builder 会漂）
from test_clean_figure_alts import JUNK104, GOOD104, CAP104, build  # noqa: E402


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def book(self, **kw):
        b = os.path.join(self.tmp, "b")
        build(b, **kw)
        return os.path.join(b, "_extract"), b

    # ① ────────────────────────────────────────────────────────────────────────
    def test_dirty_unit_alt_fails(self):
        ext, _b = self.book(unit_alt=JUNK104, trans_alt=GOOD104, deliv_alt=GOOD104)
        probs, note = AUD.chapter_alt_problems(ext, "10", units_sub="units")
        self.assertTrue(probs, probs)
        self.assertIn(u"图 alt 卫生", probs[0])
        self.assertIn(u"ch10_fig10.4.png", probs[0])
        self.assertIn(u"clean_figure_alts.py", u"\n".join(probs))   # 处方指 SSOT 工具
        self.assertIn(u"脏 1", note)

    def test_prescription_printed_once_per_chapter(self):
        # 处方按章给一次：多行脏时不许逐行复读同一句（把别处真 FAIL 挤出视野）。
        ext, _b = self.book(unit_alt=JUNK104, deliv_alt=GOOD104, siblings=[
            (u"10.5", CAP104, u"Figure FIG U RE 10.5An additive treatment effec")])
        probs, _n = AUD.chapter_alt_problems(ext, "10", units_sub="units")
        n = sum(1 for p in probs if u"clean_figure_alts.py" in p)
        self.assertEqual(1, n, probs)
        self.assertGreaterEqual(len([p for p in probs if u"图 alt 卫生：" in p]), 2)

    def test_side_scoping_reports_only_gated_side(self):
        # 同一本书、同一张图：units 脏 / units-translate 净 ⇒ 只有被门控的那半边 FAIL。
        # 收窄反了（把译侧也算进源侧）会让两半区都红，白跑一轮返工。
        ext, _b = self.book(unit_alt=JUNK104, trans_alt=GOOD104, deliv_alt=GOOD104)
        self.assertTrue(AUD.chapter_alt_problems(ext, "10", units_sub="units")[0])
        self.assertEqual(
            [], AUD.chapter_alt_problems(ext, "10", units_sub="units-translate")[0])

    def test_clean_chapter_passes_but_note_counts(self):
        ext, _b = self.book(unit_alt=GOOD104, trans_alt=GOOD104, deliv_alt=GOOD104)
        probs, note = AUD.chapter_alt_problems(ext, "10", units_sub="units")
        self.assertEqual([], probs)
        self.assertIn(u"行 ", note)                             # ⑥ 全净也要报分母
        self.assertIn(u"脏 0", note)

    # ② ────────────────────────────────────────────────────────────────────────
    def test_unregistered_src_is_counted_not_blocked(self):
        # 正文挂了本章 figure_index 里没有的图名 ⇒ alt 侧没有题注真值可判，**只报数**：
        # 拦门等于逼写手凭空编一条题注（那是图改名波/`resync_figure_refs` 的账）。
        ext, _b = self.book(unit_alt=GOOD104, trans_alt=GOOD104)
        path = os.path.join(_b, "_extract", "book_structure", "units", "ch10",
                            "0002_desc_D2.md")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        io.open(path, "w", encoding="utf-8", newline=u"").write(
            u"<!-- book-summarizer DONE unit: id=0002 type=desc key=D2 name=N2 -->\n"
            + u'    <img src="figure/ch10_fig10.99.png" alt="%s" width="60%%">\n'
            % JUNK104)
        probs, note = AUD.chapter_alt_problems(ext, "10", units_sub="units")
        self.assertEqual([], probs, probs)                      # 碎字 alt 也不拦（未登记）
        self.assertIn(u"未登记 src 1", note)
        self.assertIn(u"resync_figure_refs", note)
        self.assertIn(u"ch10_fig10.99.png", note)

    # ③ ────────────────────────────────────────────────────────────────────────
    def test_nonplain_label_fails_with_registry_leg_hint(self):
        # Katok 附录实测形：题注 `FIGURE F.1.`、alt `Figure FIGURE F.1.`（号写了两遍）。
        # `F.1` 不是纯编号形 ⇒ 修法只能走登记腿出厂装配，闸必须把这句话一起报出来。
        ext, _b = self.book(unit_alt=u"Figure FIGURE F.1.", cap=u"FIGURE F.1.",
                            label=u"F.1", trans_alt=None)
        probs, note = AUD.chapter_alt_problems(ext, "10", units_sub="units")
        self.assertTrue(probs, probs)
        self.assertIn(u"登记腿出厂装配", probs[0])
        self.assertIn(u"非纯编号 1", note)

    # ④ ────────────────────────────────────────────────────────────────────────
    def test_dirty_registry_caption_is_named_in_note(self):
        ext, _b = self.book(unit_alt=JUNK104, cap=JUNK104.split(u"10.4")[0] +
                            u"10.4An additive treatment effect")
        probs, note = AUD.chapter_alt_problems(ext, "10", units_sub="units")
        self.assertTrue(probs, probs)                           # alt 照旧拦
        self.assertIn(u"登记题注同脏", note)
        self.assertIn(u"印面取证", note)                        # 但不许在 alt 侧改字

    def test_no_figure_index_is_not_blocked(self):
        # 知识库输入的书没有 figure_index.json ⇒ 题注真值不存在，判据不启用。
        ext = os.path.join(self.tmp, "kb", "_extract")
        os.makedirs(os.path.join(ext, "book_structure", "units", "ch1"))
        probs, note = AUD.chapter_alt_problems(ext, "1")
        self.assertEqual([], probs)
        self.assertIn(u"未启用", note)

    # ⑤ 读不到 ≠ 内容脏 ────────────────────────────────────────────────────────
    def test_broken_registry_is_reported_not_failed(self):
        ext, _b = self.book(unit_alt=JUNK104)
        io.open(os.path.join(ext, "figure_index.json"), "w",
                encoding="utf-8", newline=u"").write(u"{坏 JSON")
        probs, note = AUD.chapter_alt_problems(ext, "10", units_sub="units")
        self.assertEqual([], probs)
        self.assertIn(u"读不到", note)

    # ⑥⑦ 静默失明控件 ──────────────────────────────────────────────────────────
    def test_only_unit_narrows_report_not_judgement(self):
        # 写手逐单元自检：同一张脏图必须在自检里看得见（否则翻 DONE 后章门控再打回）。
        ext, _b = self.book(unit_alt=JUNK104, trans_alt=GOOD104, deliv_alt=GOOD104)
        probs, _n = AUD.chapter_alt_problems(ext, "10", units_sub="units",
                                             only_unit="0001_desc_D1.md")
        self.assertTrue(probs, probs)
        # 给错文件名 ⇒ 报 0 是**收窄**的结果，不是判据失效：同一 ext 章级仍须报脏。
        self.assertEqual(
            [], AUD.chapter_alt_problems(ext, "10", units_sub="units",
                                         only_unit="不存在.md")[0])
        self.assertTrue(AUD.chapter_alt_problems(ext, "10", units_sub="units")[0])

    def test_note_printed_on_both_branches(self):
        import inspect
        import gate_units as G
        src = inspect.getsource(G.gate_chapter)
        self.assertIn(u"chapter_alt_problems", src)             # ⑧ 真接线
        self.assertIn(u"problems.extend(alt_problems)", src)
        self.assertIn(u"alt_note", src[src.index(u"if problems:"):])   # FAIL 带计数
        self.assertIn(u"alt_note)", src[src.index(u"return True,"):])  # PASS 也带
        self.assertTrue(callable(G.chapter_alt_problems))

    def test_delivery_rows_are_out_of_gate_scope(self):
        # 闸只管被门控的那半边；交付侧 alt 脏由步骤 8 verify 负责。这里锁「不串腿」：
        # 单元两半区全净、只有交付脏 ⇒ 源/译门控都必须绿。
        ext, _b = self.book(unit_alt=GOOD104, trans_alt=GOOD104, deliv_alt=JUNK104)
        for side in AUD.UNIT_SIDES:
            self.assertEqual(
                [], AUD.chapter_alt_problems(ext, "10", units_sub=side)[0], side)
        self.assertTrue(AUD.chapter_alt_problems(
            ext, "10", units_sub=AUD.DELIV)[0])                # 同一函数能数到 D


if __name__ == "__main__":
    unittest.main()
