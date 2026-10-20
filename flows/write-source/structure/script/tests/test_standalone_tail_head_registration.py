# -*- coding: utf-8 -*-
"""印面「无序号节末标题」登记为有名 description 节点的判据测试（根治 #20）。

立项缺陷（Lehmann《Elements of Large-Sample Theory》文字层实测 2026-10-20）：每节末尾印
一个独占一行、居中的 `Summary`，其下是该节的编号要点列表。该词不带序标 ⇒ 结构检测器不
产生锚点。真实根因是**两层**，本文件按两层各钉一组：

**第一层（内容整块消失）**：`_filter_noise` 的「同一归一文本在 ≥2 页的边缘带复现 ⇒ 整章
丢弃」家具规则，把每章复现 4–8 次的 `Summary` 连坐删光——ch1 6/6、ch7 8/8 全灭，只有
ch5（7 处都在正文带）幸存。跨库普查（`_extract/_errata/census_noise_filter_tail_heads.py`，
57 书）命中面 = Lehmann 36 + Strogatz 6；后者经印面取证判定是**偶数页页眉**
（`Overview` 就是本页最顶印刷行，同行还有书码 3/7/11），必须继续当家具删。
⇒ 豁免判据只借用 `scan_skeleton.is_running_head`（带下界 = max(绝对 100, 本页最顶行 + 容差)），
不新造第二套页眉规则：Lehmann 的节末标题下面还有正文、且不是本页最顶行 ⇒ 放行；
   Strogatz 的页眉正是本页最顶行 ⇒ 照旧丢弃。

**第二层（幸存的标题词语义丢失）**：放行后的词块此前既不进节点 `name` 也不切开，
渲染成散文里一句光秃秃的 `Summary`。⇒ `_lift_head_word`（桶首）+ `_cut_at_tail_head`
（桶中间，实测 ch1 p26 / ch7 p497 落在节首散文中间、ch5 p362 / ch7 p564 落在 proof 之后的
尾随桶中间）把词登记成节点 name，节点只在剥题后**仍有正文**时才建。

负向锁死：`Discussion of the proof follows.`（以标题词起头的整句）、`Remark 2.1`（定理环境
名，词表刻意不收）、非 `line_start` 的行内碎片、只有标题词没有正文（不建幻影节点）、
Strogatz 形态的页眉复本（家具规则仍然生效）。

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_standalone_tail_head_registration.py
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
import lib.boot as _boot                # noqa: E402
_boot.setup()

import attach_content as ac             # noqa: E402
import scan_skeleton as sk              # noqa: E402

H = 1685.0                               # Lehmann 扫描页高（实测）


def _tb(text, page=1, y=700.0, x=566.0, w=140.0, line_start=True):
    """内部块流的一个 text 块（字段与 `_collect_blocks` 一致：x/x1/y/bottom）。"""
    b = {"page": page, "y": y, "x": x, "x1": x + w, "bottom": y + 30.0,
         "kind": "text", "text": text}
    if line_start:
        b["line_start"] = True
    return b


class TestStandaloneTailHead(unittest.TestCase):
    """判据本体：整块 = 一个概述词，且独立成行。"""

    def test_word_family_recognised(self):
        for t in ("Summary", "SUMMARY", "Overview:",
                  "Summing Up", "Conclusions", "Discussion",
                  "Recapitulation", "Perspectives", "Review"):
            self.assertEqual(
                ac._standalone_tail_head(_tb(t)), t.strip(" :.．。"), t)

    def test_wrapped_paragraph_tail_is_not_a_head(self):
        # 🔴 全库 63 处候选里唯一的假阳档（Apostol p141 / Rosen p176 ×2 / Humphreys p43
        # 逐页确证）：段落**折行的最后一行**恰好只剩该词，印面是小写续句 + 句号收尾
        # （`…some of the` / `discussion.`、`…in light` / `summary.`、`…the desired` /
        # `conclusion.`）。⇒ 判据只认「大写起首 + 无句号」；全库 `Summary.`（大写带句号）
        # 与 `summary`（小写无句号）零出现，放宽须再普查。
        for t in ("discussion.", "summary.", "conclusion.", "overview.",
                  "summary", "conclusion"):
            self.assertEqual(ac._standalone_tail_head(_tb(t)), "", t)

    def test_uncalibrated_word_shape_is_not_recognised(self):
        # 🔴 词表按普查实测形态收紧：`Summing` 与 `Up` 之间只允许空白（可再带一个
        # 连字符），57 书实测只有 `Summing Up`。无空格的 `Summing-up` 库里零出现，
        # 放宽判据须先跨书普查出真形态，不能靠测试反向放宽。
        self.assertEqual(ac._standalone_tail_head(_tb("Summing-up")), "")

    def test_whole_sentence_starting_with_word_is_not_a_head(self):
        # 🔴 全匹配（非前缀）：`Discussion of the proof follows.` 是正文句子
        for t in ("Discussion of the proof follows.",
                  "Summary of the chapter shows that the estimator is consistent.",
                  "Review exercises are collected at the end of the section."):
            self.assertEqual(ac._standalone_tail_head(_tb(t)), "", t)

    def test_environment_names_are_not_in_the_word_list(self):
        # `Remark 2.1` 与节末标题同为「居中独占一行」，收进来＝把条目当节标题（假阳源）
        for t in ("Remark 2.1", "Remark", "Note", "Note 3", "Comment", "Proof"):
            self.assertEqual(ac._standalone_tail_head(_tb(t)), "", t)

    def test_inline_fragment_without_line_start_is_not_a_head(self):
        self.assertEqual(ac._standalone_tail_head(_tb("Summary", line_start=False)), "")

    def test_non_text_block_never_qualifies(self):
        self.assertEqual(ac._standalone_tail_head(
            {"kind": "formula", "latex": "Summary", "line_start": True}), "")

    def test_is_tail_heading_short_circuits_on_english_form(self):
        # 证明收束 / 习题截断都读 `_is_tail_heading`，英文形态必须同样认账
        self.assertTrue(ac._is_tail_heading(_tb("Summary")))
        self.assertFalse(ac._is_tail_heading(_tb("Summary of the chapter is long prose.")))


class TestNoiseFilterFurnitureExemption(unittest.TestCase):
    """第一层：家具规则不得吃掉节末复现的标题行。"""

    def _corpus(self):
        """一章的块流：正文若干 + 8 个 `Summary`（其中 2 处落进 0.12/0.90 绝对边缘带，
        但那两页的**最顶印刷行另有其行**（页眉 + 书码）⇒ 不是页眉带复本）。"""
        blocks = []
        for p in (21, 26, 31, 38, 43, 47, 52, 55):
            blocks.append(_tb("1. Mathematical Background", page=p, y=86.0, x=259.0, w=335.0))
            blocks.append(_tb(str(100 + p), page=p, y=88.0, x=187.0, w=31.0))
            blocks.append(_tb("Some running prose of the section that continues.",
                              page=p, y=300.0, x=184.0, w=900.0))
            blocks.append(_tb("Summary", page=p,
                              y=150.0 if p in (31, 43) else 950.0, x=566.0))
        return blocks

    def test_repeated_tail_head_survives_edge_band(self):
        blocks = self._corpus()
        kept = ac._filter_noise(blocks, H, 46)
        survived = [b for b in kept if (b.get("text") or "").strip() == "Summary"]
        self.assertEqual(len(survived), 8,
                         "复现 8 次的节末标题被家具规则连坐删除（缺陷原状）")

    def test_exemption_is_deliberately_wider_than_registration(self):
        # 家具豁免只卡页眉带、不卡词形 ⇒ 段落折行尾行（`summary.`）即使落在边缘带也
        # **留在内容流**（只是不登记 name）。方向性：宽出来只会多留正文，不会丢内容。
        blocks = []
        for p in (10, 12, 14, 16):
            blocks.append(_tb("Prose of page %d continues over several lines here." % p,
                              page=p, y=300.0, x=184.0, w=900.0))
            blocks.append(_tb("summary.", page=p, y=1500.0, x=190.0, w=70.0))
        kept = ac._filter_noise(blocks, H, 46)
        self.assertEqual(len([b for b in kept
                              if (b.get("text") or "").strip() == "summary."]), 4, kept)
        self.assertEqual(ac._standalone_tail_head(_tb("summary.")), "")

    def test_running_head_with_folio_on_same_line_still_dropped(self):
        # Strogatz 形态：`Overview` **就是**本页最顶印刷行，同行右侧是书码
        blocks = []
        for p in (18, 20, 22, 24, 26):
            blocks.append(_tb("Overview", page=p, y=115.0, x=549.0, w=110.0))
            blocks.append(_tb(str(p), page=p, y=118.0, x=1055.0, w=35.0))
            blocks.append(_tb("Body prose continues here for the rest of the page.",
                              page=p, y=200.0, x=148.0, w=900.0))
        kept = ac._filter_noise(blocks, H, 46)
        self.assertEqual([b for b in kept if (b.get("text") or "").strip() == "Overview"], [],
                         "页眉复本必须继续当家具删除")

    def test_exemption_uses_the_shared_running_head_predicate(self):
        # 豁免只走 `is_running_head` 一份谓词：Lehmann 那处（页顶=86，标题=150）判 False，
        # Strogatz 那处（标题即页顶 115）判 True。
        self.assertFalse(sk.is_running_head(566.0, 150.0, 182.0, 908.0, 86.0))
        self.assertTrue(sk.is_running_head(549.0, 115.0, 148.0, 942.0, 115.0))

    def test_ordinary_furniture_still_dropped(self):
        # 未登记进词族的真页眉（章名）照旧整章丢弃——豁免范围不得外溢
        blocks = []
        for p in range(21, 27):
            blocks.append(_tb("Elements of Large-Sample Theory", page=p, y=86.0,
                              x=250.0, w=500.0))
            blocks.append(_tb("Prose line %d that differs on every page." % p, page=p,
                              y=400.0, x=184.0, w=800.0))
        kept = ac._filter_noise(blocks, H, 46)
        self.assertEqual([b for b in kept
                          if "Elements of Large" in (b.get("text") or "")], [])


class TestLiftAndCut(unittest.TestCase):
    """第二层：词登记成节点 name；桶中间同样切开；不建幻影节点。"""

    def test_bucket_head_word_lifted_into_name(self):
        blocks = [_tb("Summary"), _tb("1. The estimator is consistent.")]
        word, rest = ac._lift_head_word(blocks)
        self.assertEqual(word, "Summary")
        self.assertEqual(len(rest), 1)

    def test_word_in_middle_of_bucket_cut(self):
        blocks = [_tb("Tail prose of the previous item.", y=300.0),
                  _tb("More tail prose.", y=340.0),
                  _tb("Summary", y=700.0),
                  _tb("1. First bullet of the summary.", y=755.0)]
        pre, post = ac._cut_at_tail_head(blocks)
        self.assertEqual([b["text"] for b in pre],
                         ["Tail prose of the previous item.", "More tail prose."])
        self.assertEqual((post[0]["text"], len(post)), ("Summary", 2))

    def test_bucket_without_head_word_untouched(self):
        blocks = [_tb("Plain paragraph one."), _tb("Plain paragraph two.")]
        pre, post = ac._cut_at_tail_head(blocks)
        self.assertIs(post, None)
        self.assertEqual(len(pre), 2)

    def test_first_occurrence_only_cut_per_call(self):
        # 一处一切，后续由 `_emit` 循环逐段处理（key 仍按文档序分配）
        blocks = [_tb("Prose.", y=100.0), _tb("Summary", y=700.0),
                  _tb("Bullet.", y=760.0), _tb("Summary", y=900.0)]
        pre, post = ac._cut_at_tail_head(blocks)
        self.assertEqual([b["text"] for b in pre], ["Prose."])
        self.assertEqual(post[0]["text"], "Summary")

    def test_description_node_keeps_pages_and_name(self):
        node = ac._make_description("D1", [_tb("Body.", y=700.0, page=31)], "Summary")
        self.assertEqual((node["type"], node["key"], node["name"]),
                         ("description", "D1", "Summary"))
        self.assertEqual((node["page_start"], node["page_end"]), (31, 31))
        self.assertEqual(len(node["sub_sec"]), 1)

    def test_empty_page_list_does_not_crash(self):
        node = ac._make_description("D2", [])
        self.assertIsNone(node["page_start"])
        self.assertIsNone(node["page_end"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
