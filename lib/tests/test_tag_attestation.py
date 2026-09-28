"""Tests for lib/tag_attestation.py — 契约公式编号的印刷锚点审计（闸门 ⑭）.

Run:  python lib/tests/test_tag_attestation.py

负向用例守的是 Kreyszig 实测的三类毒 tag（2026-09-26 源码 verify Q 层）：
``22`` = display 内两个 ε/2 的分母被 OCR 成独立数字块；``50``/``25`` =
``= 0.50`` 的小数尾巴；``18751A``/``12818A`` = 波长 ``18 751 Å``。
契约 tag 是门控对账真值，误挂会反逼写手凭空 ``\\tag``，故必须在闸门判 FAIL。
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

from tag_attestation import (collect_contract_tags, tag_attestation_problems,
                             strip_unattested, unattested_tags,
                             unharvested_anchor_tags, unharvested_anchor_problems,
                             glued_anchor_tags, glued_anchor_problems,
                             numbering_gaps, numbering_gap_problems,
                             margin_anchor_audit, page_anchor_index, number_column)


def formula_block(tag, tags=None):
    b = {"formula": "x = y", "display": True}
    if tags:
        b["tag"] = tag
        b["tags"] = tags
    elif tag is not None:
        b["tag"] = tag
    return b


def contract(tags, lo=10, hi=20):
    """tags: [str|None] 或 [(str, [str])]（首号, 多号列表）→ 单节点契约。"""
    blocks = []
    for t in tags:
        if isinstance(t, (list, tuple)):
            blocks.append(formula_block(t[0], list(t[1])))
        else:
            blocks.append(formula_block(t))
    return {"key": "ch1", "type": "chapter", "page_start": lo, "page_end": hi,
            "sub_sec": [{"key": "1.4", "type": "section", "sub_sec": blocks}]}


def loader(pages):
    """pages: {pdf_page: [block text]}；未列出的页给 None（= 无页文件）。"""
    def load(pg):
        return pages.get(pg)
    return load


PAREN_PAGES = {p: ["(%d)" % n for n in range(1, 30)] for p in range(10, 21)}


class TestCollect(unittest.TestCase):
    def test_collects_tag_and_tags_in_doc_order(self):
        tree = contract(["7", ("9", ["9", "10"])])
        got = [n for _k, n in collect_contract_tags(tree)]
        self.assertIn("7", got)
        self.assertIn("10", got)
        self.assertEqual(len(got), len(set(got)), "重复编号须去重")

    def test_ignores_blocks_without_tag(self):
        tree = contract([None])
        self.assertEqual(collect_contract_tags(tree), [])


class TestAttested(unittest.TestCase):
    def test_parenthesized_labels_pass(self):
        tree = contract(["7", "12", "18"])
        pages = {p: ["(7)", "(12)", "(18)", "some prose"] for p in range(10, 21)}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])

    def test_label_glued_into_formula_line_passes(self):
        """编号被 OCR 粘进公式行（非独立块）时不得误报。"""
        tree = contract(["7"])
        pages = {p: ["d(x, y) = sqrt(x - y)  (7)"] for p in range(10, 21)}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])

    def test_bare_dominant_book_passes(self):
        """裸排点分编号书（Koopman 型）：整章无括号 → 裸块锚点合法。"""
        tree = contract(["3.21", "3.22"], lo=10, hi=12)
        pages = {10: ["3.21"], 11: ["3.22"], 12: ["prose"]}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])

    def test_label_detected_as_formula_attests(self):
        """左缘编号被 MFD 当**公式**检测出来（Kreyszig 3.7-2 印刷 `(7c')`/`(7*)`）：
        只看 text 流会误判真编号为噪声，故 latex 形态也算锚点。"""
        tree = contract(["7a", "7b", "7c", "7c'", "7*", "9"], lo=10, hi=11)
        pages = {10: ["(9)", "(7b)", "(7c)"],
                 11: ["( 7 \\mathsf { a } )", "( 7 \\mathbf { c } ^ { \\prime } )",
                      "( 7 ^ { * } )", "H _ { n } ( t ) = n ! \\sum"]}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])


class TestPhantom(unittest.TestCase):
    def test_unattested_number_flagged(self):
        """18751A 型：页窗内 (N) 与裸 N 都找不到。"""
        tree = contract(["7", "18751A"], lo=10, hi=12)
        pages = {p: ["(7)", "18 751 A", "E4 -> E3"] for p in range(10, 13)}
        probs = tag_attestation_problems(tree, loader(pages))
        self.assertEqual(len(probs), 1)
        self.assertIn("18751A", probs[0])
        self.assertIn("找不到任何印刷锚点", probs[0])

    def test_bare_only_tag_flagged_in_paren_chapter(self):
        """22 型：ε/2 分母被读成独立数字块，而本章编号一律 `(N)`。"""
        tree = contract([str(n) for n in range(1, 23)] + ["22"], lo=10, hi=12)
        pages = {p: ["(%d)" % n for n in range(1, 22)] for p in range(10, 13)}
        pages[12] = list(pages[10]) + ["22"]      # 公式内部碎片成独立块
        probs = tag_attestation_problems(tree, loader(pages))
        self.assertTrue(any("22" in p and "裸排" in p for p in probs), probs)

    def test_decimal_tail_flagged_in_paren_chapter(self):
        """50 型：`= 0.50` 的尾巴；页窗内无 `(50)`，只有裸块 50。"""
        tags = [str(n) for n in range(1, 20)] + ["50"]
        tree = contract(tags, lo=10, hi=12)
        pages = {p: ["(%d)" % n for n in range(1, 20)] + ["50"] for p in range(10, 13)}
        probs = tag_attestation_problems(tree, loader(pages))
        self.assertTrue(any("50" in p for p in probs), probs)

    def test_bare_only_tag_allowed_when_chapter_is_bare(self):
        """裸排书不得被 ⑭ 误伤：括号占比不足 90% 时裸锚点合法。"""
        tags = [str(n) for n in range(1, 21)]
        tree = contract(tags, lo=10, hi=12)
        pages = {p: ["(%d)" % n for n in range(1, 3)] +
                     ["%d" % n for n in range(3, 21)] for p in range(10, 13)}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])

    def test_lettered_tag_in_integer_chapter_flagged(self):
        """Strogatz 3e ch7 型：`2n` 来自 `2` + 下行 `n ?` 的换行粘连。它**恰好**成了一块
        裸数字，所以逃过「无锚点」；判它的理由是「本章 60 个编号全是纯整数」。"""
        tags = [str(n) for n in range(34, 60)] + ["2n"]
        tree = contract(tags, lo=10, hi=12)
        pages = {p: ["%d" % n for n in range(34, 60)] + ["2n"] for p in range(10, 13)}
        probs = tag_attestation_problems(tree, loader(pages))
        self.assertTrue(any("2n" in p and "含字母" in p for p in probs), probs)

    def test_lettered_dominant_chapter_not_flagged(self):
        """字母编号书（Kreyszig `(7a)` 型）不得被判据③误伤：纯整数太少时字母是体例。"""
        tree = contract(["7a", "7b", "7c", "7d", "7e", "3"], lo=10, hi=11)
        pages = {p: ["7a", "7b", "7c", "7d", "7e", "(3)"] for p in range(10, 12)}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])

    def test_lettered_majority_chapter_not_flagged(self):
        """字母编号占多数（>10%）时不能判毒——那是该章体例而非 OCR 尾巴。"""
        tags = ["1", "2", "3", "4", "5", "6a", "6b", "6c"]
        tree = contract(tags, lo=10, hi=11)
        pages = {p: ["%s" % t for t in tags] for p in range(10, 12)}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])

    def test_missing_pages_fail_open(self):
        """整章无页文件 → 不判（缺数据不等于内容缺陷）。"""
        tree = contract(["7", "99"], lo=10, hi=12)
        self.assertEqual(tag_attestation_problems(tree, loader({})), [])

    def test_chapter_label_prefix(self):
        tree = contract(["99"], lo=10, hi=11)
        pages = {p: ["(7)", "prose"] for p in range(10, 12)}
        probs = tag_attestation_problems(tree, loader(pages), chapter_label="ch5")
        self.assertTrue(probs[0].startswith("[ch5]"), probs)


class TestStripUnattested(unittest.TestCase):
    """收割处剔除：Strogatz 3e ch7/ch8 实测毒 tag（`0c`/`2x`/`2i`/`25`）留在契约里
    会两头堵写手——凭空 `\tag` = 编造、删掉 = 漏写，且章级闸 ⑭ 永久 FAIL。"""

    PAGES = {p: ["(%d)" % n for n in range(1, 8)] for p in range(10, 21)}

    def test_unattested_tags_returns_set(self):
        tree = contract(["3", "25"], lo=10, hi=20)
        self.assertEqual(unattested_tags(tree, loader(self.PAGES)), {"25"})

    def test_strip_removes_only_poison(self):
        tree = contract(["3", "25"], lo=10, hi=20)
        removed = strip_unattested(tree, loader(self.PAGES))
        self.assertEqual(removed, ["25"])
        left = [n for _k, n in collect_contract_tags(tree)]
        self.assertEqual(left, ["3"])

    def test_strip_keeps_formula_block(self):
        """剔除的是**编号声称**，不是公式内容（正文一个不丢）。"""
        tree = contract(["25"], lo=10, hi=20)
        strip_unattested(tree, loader(self.PAGES))
        blocks = tree["sub_sec"][0]["sub_sec"]
        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["formula"], "x = y")
        self.assertEqual(blocks[0].get("tag"), "")

    def test_chapter_clean_after_strip(self):
        tree = contract(["3", "25", "0c"], lo=10, hi=20)
        self.assertTrue(tag_attestation_problems(tree, loader(self.PAGES)))
        strip_unattested(tree, loader(self.PAGES))
        self.assertEqual(tag_attestation_problems(tree, loader(self.PAGES)), [])

    def test_multi_tag_list_partial_strip(self):
        pages = {p: ["(%d)" % n for n in range(1, 10)] for p in range(10, 21)}
        tree = contract([("9", ["9", "40"])], lo=10, hi=20)
        self.assertEqual(strip_unattested(tree, loader(pages)), ["40"])
        blk = tree["sub_sec"][0]["sub_sec"][0]
        self.assertEqual(blk["tag"], "9")
        self.assertEqual(blk["tags"], ["9"])

    def test_strip_lettered_tag(self):
        """判据③的 tag 同样在**收割处**剔除（不只报错），剔除后章级闸 ⑭ 转绿。"""
        tags = [str(n) for n in range(34, 60)] + ["2n"]
        tree = contract(tags, lo=10, hi=20)
        pages = {p: ["%d" % n for n in range(34, 60)] + ["2n"] for p in range(10, 21)}
        self.assertTrue(tag_attestation_problems(tree, loader(pages)))
        self.assertEqual(strip_unattested(tree, loader(pages)), ["2n"])
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])

    def test_strip_keeps_attested(self):
        """人工确证登记里的号不得在收割处剔除：那正是「OCR 看不见、印面确有」的号。"""
        tree = contract(["3", "25"], lo=10, hi=20)
        self.assertEqual(strip_unattested(tree, loader(self.PAGES),
                                          attested=["25"]), [])
        self.assertEqual([n for _k, n in collect_contract_tags(tree)], ["3", "25"])

    def test_noop_when_all_attested(self):
        tree = contract(["3", "7"], lo=10, hi=20)
        self.assertEqual(strip_unattested(tree, loader(self.PAGES)), [])
        self.assertEqual([n for _k, n in collect_contract_tags(tree)], ["3", "7"])

    def test_noop_when_pages_missing(self):
        tree = contract(["99"], lo=10, hi=12)
        self.assertEqual(strip_unattested(tree, loader({})), [])
        self.assertEqual([n for _k, n in collect_contract_tags(tree)], ["99"])


class TestHumanAttestedExemption(unittest.TestCase):
    """``attested=`` 人工确证豁免（Iwaniec–Kowalski《ANT》ch1 的 `(1.104)` 实测）。

    扫描书 OCR 会**整块漏掉**真印的页边编号，判据①把这类号一律读成「查无锚点 =
    噪声」。若闸据此判毒，写手照印面写 ``\\tag{1.104}`` = 编造、删掉 = 漏写，两头堵，
    而同一份 `verify_config.json` 的 ``known_book``（Q 层）却在**要求**这个号——闸与
    Q 层互相矛盾。故 ⑭ 接受同一份人工确证登记作豁免，且**按号**豁免（不是按章）。
    """

    PAGES = {p: ["(%d)" % n for n in range(1, 20)] for p in range(10, 21)}

    def test_attested_unanchored_number_passes(self):
        tree = contract([str(n) for n in range(1, 20)] + ["1.104"], lo=10, hi=20)
        # 不豁免时判「找不到任何印刷锚点」
        self.assertTrue(any("1.104" in p for p in
                            tag_attestation_problems(tree, loader(self.PAGES))))
        self.assertEqual(tag_attestation_problems(tree, loader(self.PAGES),
                                                  attested=["1.104"]), [])

    def test_exemption_is_per_number_not_per_chapter(self):
        """豁免一个号不得顺手放过同章其他无锚点号（否则闸失去判别力）。"""
        tree = contract([str(n) for n in range(1, 20)] + ["1.104", "999"],
                        lo=10, hi=20)
        probs = tag_attestation_problems(tree, loader(self.PAGES),
                                        attested=["1.104"])
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("999", probs[0])

    def test_attested_bare_only_verdict_passes(self):
        """判据②同理：带括号章里「只有裸锚点」的号若已人工确证，不再判毒。"""
        tags = [str(n) for n in range(1, 22)] + ["22"]
        tree = contract(tags, lo=10, hi=12)
        pages = {p: ["(%d)" % n for n in range(1, 22)] for p in range(10, 13)}
        pages[12] = list(pages[10]) + ["22"]
        self.assertTrue(any("裸排" in p for p in
                            tag_attestation_problems(tree, loader(pages))))
        self.assertEqual(tag_attestation_problems(tree, loader(pages),
                                                  attested=["22"]), [])

    def test_attested_lettered_verdict_passes(self):
        """判据③（字母尾巴）也受豁免——个别 `6a` 型真印号在同体例章里会被误伤。"""
        tags = [str(n) for n in range(34, 60)] + ["2n"]
        tree = contract(tags, lo=10, hi=12)
        pages = {p: ["%d" % n for n in range(34, 60)] + ["2n"] for p in range(10, 13)}
        self.assertTrue(any("含字母" in p for p in
                            tag_attestation_problems(tree, loader(pages))))
        self.assertEqual(tag_attestation_problems(tree, loader(pages),
                                                  attested=["2n"]), [])

    def test_unattested_tags_respects_attested(self):
        tree = contract(["3", "25"], lo=10, hi=20)
        self.assertEqual(unattested_tags(tree, loader(self.PAGES)), {"25"})
        self.assertEqual(unattested_tags(tree, loader(self.PAGES),
                                         attested=["25"]), set())

    def test_attested_none_default_keeps_verdict(self):
        """默认不豁免：收割期（build_structure）还没有人工目视，行为须与既往一致。"""
        tree = contract(["3", "25"], lo=10, hi=20)
        self.assertEqual(unattested_tags(tree, loader(self.PAGES)),
                         unattested_tags(tree, loader(self.PAGES), attested=None))


class TestAttestedNumbersRegistry(unittest.TestCase):
    """``attested_numbers`` = ⑭ 与 Q 层共用的登记读取口（形状兼容 + fail-open）。"""

    def _write(self, cfg):
        import json
        import tempfile
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "verify_config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False)
        return d

    def test_flat_and_grouped_shapes(self):
        from tag_attestation import attested_numbers
        flat = self._write({"formula": {"type": 2,
                                        "known_book": ["1.104", " 3.7 "]}})
        self.assertEqual(attested_numbers(flat), {"1.104", "3.7"})
        grouped = self._write({"ch": {"formula": {"known_book": ["8.75"]}},
                               "appendix": {"formula": {"known_book": ["A.9"]}}})
        self.assertEqual(attested_numbers(grouped), {"8.75", "A.9"})

    def test_missing_config_or_empty_entries_is_empty(self):
        import tempfile
        from tag_attestation import attested_numbers
        self.assertEqual(attested_numbers(tempfile.mkdtemp()), set())
        empty = self._write({"ch": {"formula": {"known_book": ["", None]}}})
        self.assertEqual(attested_numbers(empty), set())


class TestLetterChapterAnchors(unittest.TestCase):
    """字母章位编号（附录 `(A.5)` 型）的锚点识别。

    动因 = Shafarevich《Basic Algebraic Geometry 1》附录 5 实测：`_PAREN_LABEL_RE`
    只认数字开头 → 页窗里 14 个 `(A.N)` 全「查无锚点」→ 收割处把**真实**编号剔光，
    契约不登记 tag、单元写 `\\tag{A.N}` 反判编造、完整性闸门 ① 复算与磁盘互相缺块。
    """

    APX_TAGS = ["A.1", "A.3", "A.4", "A.5", "A.7", "A.8"]

    def test_parenthesized_letter_anchor_attests(self):
        tree = contract(self.APX_TAGS, lo=299, hi=302)
        pages = {p: ["(A.%d)" % n for n in (1, 3, 4, 5, 7, 8)]
                 for p in range(299, 303)}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])
        self.assertEqual(strip_unattested(tree, loader(pages)), [])
        self.assertEqual([n for _k, n in collect_contract_tags(tree)], self.APX_TAGS)

    def test_letter_anchor_glued_into_formula_line_attests(self):
        """编号被 MFD 当**公式**检测出来（`( { \\mathsf { A } } . 5 )`）时同样算锚点——
        扁平形态分支（去宏名/花括号/空格）对字母章位一样有效。"""
        tree = contract(["A.5"], lo=299, hi=300)
        pages = {299: ["( { \\mathsf { A } } . 5 )"], 300: ["prose"]}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])

    def test_letter_tag_without_printed_anchor_still_condemned(self):
        """负向：字母章位**不是**免检牌——页窗里没印过的号照旧判毒。"""
        tree = contract(self.APX_TAGS + ["A.9"], lo=299, hi=302)
        pages = {p: ["(A.%d)" % n for n in (1, 3, 4, 5, 7, 8)]
                 for p in range(299, 303)}
        probs = tag_attestation_problems(tree, loader(pages))
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("A.9", probs[0])
        self.assertEqual(strip_unattested(tree, loader(pages)), ["A.9"])
        self.assertEqual([n for _k, n in collect_contract_tags(tree)], self.APX_TAGS)

    def test_bare_letter_label_does_not_attest(self):
        """裸排 `A.5` 与 `Fig. A.5` / 小节标题无形态区别 → 不算锚点（与
        `formula_tag_re(letter=True)` 同一取舍）。"""
        tree = contract(["A.5"], lo=299, hi=300)
        pages = {299: ["A.5"], 300: ["Scalar products"]}
        probs = tag_attestation_problems(tree, loader(pages))
        self.assertTrue(any("A.5" in p for p in probs), probs)

    def test_letter_led_chapter_not_flagged_by_lettered_rule(self):
        """判据③（字母尾巴 = OCR 粘连）只在纯整数占多数时生效：全字母章位附录
        不得被它误伤。"""
        tree = contract(self.APX_TAGS, lo=299, hi=302)
        pages = {p: ["(A.%d)" % n for n in (1, 3, 4, 5, 7, 8)]
                 for p in range(299, 303)}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])


    def test_comma_forms_are_not_anchors(self):
        """负向：锚点索引**不认逗号**（SSOT `_FORMULA_SEP` 含 `,`，此处收窄）。
        `(0, 1)` 是坐标 / 列表而非编号——methods-of-homological-algebra ch1/ch3 实测
        毒 tag `0,1` / `0,0,1` / `83,3`，跨语料 607 份契约标定要求它们继续判毒。"""
        tags = [str(n) for n in range(1, 8)] + ["0,1", "83,3"]
        tree = contract(tags, lo=14, hi=20)
        pages = {p: ["(%d)" % n for n in range(1, 8)] +
                     ["(0, 1)", "(83, 3)", "(0, 0, 1)"] for p in range(14, 21)}
        probs = "\n".join(tag_attestation_problems(tree, loader(pages)))
        self.assertIn("0,1", probs)
        self.assertIn("83,3", probs)
        self.assertEqual(strip_unattested(tree, loader(pages)), ["0,1", "83,3"])


class TestUnharvestedAnchors(unittest.TestCase):
    """闸门 ⑭ 的**对偶**：印面 `(N)` 锚点在契约里在档、其展示式却没登记 tag（收割漏号）。

    实测动因 = Strogatz 3e ch13 §13.5：印面 `(1)` 紧跟 `r e^{i\\psi} = \\langle
    e^{i\\theta} \\rangle`，契约该块无 `tag` → 单元从 `\\tag{2}` 起写，而章级
    tag 集合比较因 `(1)` 在 §13.4 也在账而**放行**（跨节串号盲区）。
    判据保守：只认「锚点的**前一个内容块**是 display 公式且无号」；``*_problems``
    再叠四条收紧（有落点 / 同节正文无该号 / 形态干净 / 序列有邻居且非习题键），
    每条评论对应一个负向用例。
    """

    @staticmethod
    def tree(blocks, key="13.5"):
        return {"key": "13", "type": "chapter", "page_start": 512, "page_end": 553,
                "sub_sec": [{"key": key, "type": "description", "sub_sec": blocks}]}

    @staticmethod
    def txt(s, **kw):
        b = {"text": s}
        b.update(kw)
        return b

    @staticmethod
    def disp(latex, tag=None, tags=None):
        b = {"formula": latex, "display": True}
        if tag is not None:
            b["tag"] = tag
        if tags is not None:
            b["tags"] = tags
        return b

    def test_untagged_display_before_anchor_detected(self):
        tree = self.tree([self.txt("Thus"),
                          self.disp(r"r e ^ { i \psi } = \langle e ^ { i \theta } \rangle"),
                          self.txt("(1)", line_start=True, indent=27.4)])
        got = unharvested_anchor_tags(tree)
        self.assertEqual([(k, n) for k, n, _f in got], [("13.5", "1")], got)

    def test_tagged_display_with_anchor_is_clean(self):
        tree = self.tree([self.disp("r = a + b", tag="2"), self.txt("(2)")])
        self.assertEqual(unharvested_anchor_tags(tree), [])

    def test_anchor_after_prose_not_judged(self):
        """保守边界：锚点前是散文（OCR 把公式切成多块）→ 不判，免得误伤。"""
        tree = self.tree([self.disp("x = y"), self.txt("some prose line"),
                          self.txt("(3)")])
        self.assertEqual(unharvested_anchor_tags(tree), [])

    def test_inline_formula_not_judged(self):
        tree = self.tree([{"formula": "r", "display": False}, self.txt("(1)")])
        self.assertEqual(unharvested_anchor_tags(tree), [])

    def test_multi_line_group_covered_by_tags_list(self):
        tree = self.tree([self.disp("array...", tag="9", tags=["9", "10"]),
                          self.txt("(9)"), self.txt("(10)")])
        self.assertEqual(unharvested_anchor_tags(tree), [])

    def test_bare_number_is_not_an_anchor(self):
        tree = self.tree([self.disp("x = y"), self.txt("3")])
        self.assertEqual(unharvested_anchor_tags(tree), [])

    def test_problems_only_for_nodes_with_unit_records(self):
        """无单元落点（V-I 省略的成堆习题块）不报——否则书书皆红、把闸变成噪声。"""
        tree = self.tree([self.disp("a = b"), self.txt("(1)")], key="13.6.5")
        self.assertTrue(unharvested_anchor_tags(tree))
        # 邻居号 2 在同单元正文里在账 → 满足序列相邻判据，只剩「有无落点」一条
        bodies = {"13.6.5": [r"$x=1$" + "\n" + chr(92) + "tag{2}" + "\n"]}
        self.assertEqual(unharvested_anchor_problems(tree, {}), [])
        probs = unharvested_anchor_problems(tree, bodies, chapter_label="ch13")
        self.assertEqual(len(probs), 1)
        self.assertTrue(probs[0].startswith("[ch13]"), probs)
        self.assertIn("13.6.5", probs[0])

    def test_number_already_rendered_in_section_escapes(self):
        """判据②：写手用 `\\qquad (1)` 之类的排版形态渲染过同号 = 没丢，不报。"""
        tree = self.tree([self.disp("a = b"), self.txt("(1)")])
        bodies = {"13.5": [chr(92) + "tag{2}\n", "…\n$$r=1 \\qquad (1)$$\n"]}
        self.assertEqual(unharvested_anchor_problems(tree, bodies), [])

    def test_ocr_fragment_number_not_judged(self):
        """判据③：`(00)` / `(01)` 一类是 OCR 碎片，形态不干净即不判。"""
        tree = self.tree([self.disp("a = b"), self.txt("(00)")])
        bodies = {"13.5": [chr(92) + "tag{1}\n" + chr(92) + "tag{2}\n"]}
        self.assertEqual(unharvested_anchor_problems(tree, bodies), [])

    def test_cross_reference_without_neighbor_not_judged(self):
        """判据④：散文式交叉引用自成一个 `(3)` 块，而序列里没有 2/4 → 不判。

        实测 Kreyszig 型误伤源：``Hence we may use (3) also in connection with
        particles.`` 被切成独立文本块，挂在上一条 display 之后。
        """
        tree = self.tree([self.disp("p = h / \\Lambda"), self.txt("(3)")])
        bodies = {"13.5": ["body with no 2 or 4 anywhere\n"]}
        self.assertEqual(unharvested_anchor_problems(tree, bodies), [])

    def test_exercise_key_exempt(self):
        """判据④后半：键含 `-`（习题条目）的号与公式号不同源，不判。"""
        tree = self.tree([self.disp("x = y"), self.txt("(1)")], key="11.2-3")
        bodies = {"11.2-3": [chr(92) + "tag{2}\n"]}
        self.assertEqual(unharvested_anchor_problems(tree, bodies), [])

    def test_strogatz_ch13_measured_case_reports(self):
        """端到端复现动因：§13.5 印面 `(1)` 漏挂，单元从 `\\tag{2}` 起写 → 必须报。

        池里只邻居 `2` 而无 `1` = 「连续号段里的洞」，正是 ⑱ 相对章级集合比较
        （`(1)` 在 §13.4 也在账）唯一的可见增量。
        """
        tree = {"key": "13", "type": "chapter", "page_start": 512, "page_end": 553,
                "sub_sec": [{"key": "13.4", "type": "description",
                             "sub_sec": [self.disp("z = 0", tag="1"),
                                         self.txt("(1)")]},
                            {"key": "13.5", "type": "description",
                             "sub_sec": [self.disp(
                                 r"r e ^ { i \psi } = \langle e ^ { i \theta } \rangle"),
                                 self.txt("(1)"),
                                 self.disp("\\dot{\\theta} = \\omega - \\mu", tag="2"),
                                 self.txt("(2)")]}]}
        bodies = {"D7": ["… " + chr(92) + "tag{2} … " + chr(92) + "tag{3} …"]}
        tree["sub_sec"][1]["key"] = "D7"          # 单元登记在公式块所在节点
        probs = unharvested_anchor_problems(tree, bodies, chapter_label="ch13")
        joined = "\n".join(probs)
        self.assertIn("收割漏号", joined, probs)
        self.assertIn("(1)", joined)


class TestGluedAnchors(unittest.TestCase):
    """粘连锚点探测（⑱ 的盲区）：OCR 把印面编号与公式残渣切成同一块。

    动因 = Apostol IANT ch7：印面 `(9)`（p.150）与 `(15)`（p.152）在契约里分别
    收成 `(9) p(k)` / `(15) G(x) = ∑α(n)F`，对「整块只有 `(N)`」的 ⑱ 判据完全
    隐形 → 契约不登记、单元两头堵（照写=编造、不写=漏号）。
    每条负向用例对应一个真实散文形态。
    """

    @staticmethod
    def tree(blocks, key="7.4"):
        return {"key": "7", "type": "chapter", "page_start": 158, "page_end": 168,
                "sub_sec": [{"key": key, "type": "description", "sub_sec": blocks}]}

    @staticmethod
    def txt(s):
        return {"text": s}

    @staticmethod
    def disp(latex, tag=None, tags=None):
        b = {"formula": latex, "display": True}
        if tag is not None:
            b["tag"] = tag
        if tags is not None:
            b["tags"] = tags
        return b

    @staticmethod
    def inline(latex):
        return {"formula": latex, "display": False}

    def test_apostol_ch7_measured_cases_report(self):
        """端到端复现动因：残渣锚点 + 未挂 tag 的展示式 → 必须报候选。"""
        tree = self.tree([self.txt("and rewrite (8) in the form"),
                          self.disp("\\varphi ( k ) \\sum _ { p \\leq x } { \\frac { \\log p } { p } }"),
                          self.inline("\\varphi(k)"),
                          self.txt("x1(p)iog p"),
                          self.txt("+(hxogP"),
                          self.txt("(9) p(k)")], key="D5")
        got = glued_anchor_tags(tree)
        self.assertEqual([(k, n) for k, n, _f in got], [("D5", "9")], got)

    def test_prose_cross_reference_residue_not_judged(self):
        """残渣含英文词（≥3 连字母）= 散文回指，不是版面锚点。"""
        for junk in ("(10) with (9) we obtain", "(1). But", "(3). See problem 12.",
                     "(2) of Theorem 6.18", "(5) gives us"):
            tree = self.tree([self.disp("a = b"), self.txt(junk)])
            self.assertEqual(glued_anchor_tags(tree), [], junk)

    def test_display_already_tagged_is_clean(self):
        tree = self.tree([self.disp("G ( x ) = \\sum \\alpha ( n ) F", tag="15"),
                          self.txt("(15) G(x) = ∑α(n)F")])
        self.assertEqual(glued_anchor_tags(tree), [])

    def test_prose_block_between_stops_search(self):
        """锚点与展示式之间隔着整句散文 → 归属无从断定，不判。"""
        tree = self.tree([self.disp("a = b"),
                          self.txt("This identity then yields, after summation by parts,"),
                          self.txt("(7) z \\log t")])
        self.assertEqual(glued_anchor_tags(tree), [])

    def test_inline_formula_only_before_anchor_not_judged(self):
        tree = self.tree([self.inline("\\chi _ { 1 }"), self.txt("(4) p(k)")])
        self.assertEqual(glued_anchor_tags(tree), [])

    def test_beyond_lookbehind_window_not_judged(self):
        tree = self.tree([self.disp("a = b"), self.txt("x"), self.txt("y"),
                          self.txt("z"), self.txt("w"), self.txt("v"),
                          self.txt("(6) p(k)")])
        self.assertEqual(glued_anchor_tags(tree), [])

    def test_only_anchor_also_seen_by_glued_probe(self):
        """整块-only 锚点形态在粘连判据下**不**重复报（残渣须非空）。"""
        tree = self.tree([self.disp("a = b"), self.txt("(1)")])
        self.assertEqual(glued_anchor_tags(tree), [])

    def test_problems_share_18_tightening_predicates(self):
        """①–④ 与 ⑱ 同源：无落点 / 同号已在节池 / 无邻居 都不报。"""
        blocks = [self.disp("\\varphi ( k ) S"), self.txt("+(hxogP"), self.txt("(9) p(k)")]
        tree = self.tree(blocks, key="D5")
        self.assertTrue(glued_anchor_tags(tree))
        self.assertEqual(glued_anchor_problems(tree, {}), [])           # ① 无落点
        self.assertEqual(glued_anchor_problems(                          # ② 已渲染
            tree, {"D5": [chr(92) + "tag{9}\n"]}), [])
        self.assertEqual(glued_anchor_problems(                          # ④ 无邻居
            tree, {"D5": ["no 8 or 10 anywhere\n"]}), [])
        probs = glued_anchor_problems(tree, {"D5": [chr(92) + "tag{8}\n"]},
                                      chapter_label="ch7")
        self.assertEqual(len(probs), 1)
        self.assertIn("[ch7]", probs[0])
        self.assertIn("(9)", probs[0])


class TestNumberingGaps(unittest.TestCase):
    """逐章连续编号序列的「空洞」判据（⑭/⑱ 与页池审计之外的第三条腿）。

    动因 = Apostol IANT 15 处丢失印刷编号（ch6 (12)、ch8 (14)(16)(26)、ch12
    (16)(28)(30)(31)(32)、ch13 (18)、ch14 (8)(25)…）：编号被收割整块丢弃时，
    契约既无 ``tag`` 也无锚点块，⑭/⑱/页池审计三者的 lost 实测全为 0，只有
    「一章的号集必须是 1..max 无洞前缀」这条不变量数得出来。
    """

    @staticmethod
    def tree(per_node):
        """per_node: [(节点 key, [tag|None|(首号,[多号])])] → 多节点章契约。"""
        secs = []
        for key, tags in per_node:
            blocks = []
            for t in tags:
                if isinstance(t, (list, tuple)):
                    blocks.append({"formula": "x = y", "display": True,
                                   "tag": t[0], "tags": list(t[1])})
                elif t is None:
                    blocks.append({"formula": "x = y", "display": True})
                else:
                    blocks.append({"formula": "x = y", "display": True, "tag": t})
            secs.append({"key": key, "type": "item", "sub_sec": blocks})
        return {"key": "ch6", "type": "chapter", "page_start": 150,
                "page_end": 160, "sub_sec": secs}

    def test_hole_in_dense_prefix_reported(self):
        tree = self.tree([("6.20", ["1", "2", "3", None, "5"])])
        self.assertEqual(numbering_gaps(tree), [(4, 3, 5)])
        probs = numbering_gap_problems(tree, {"6.20": ["body"]}, "ch6")
        self.assertEqual(len(probs), 1)
        self.assertIn("(4)", probs[0])
        self.assertTrue(probs[0].startswith("[ch6]"))

    def test_gapless_prefix_silent(self):
        self.assertEqual(numbering_gaps(self.tree([("1", ["1", "2", "3"])])), [])

    def test_truncation_is_not_a_hole(self):
        """判据只抓洞：max 之后的印面号不属本判据（那是 ⑱/粘连锚点的活）。"""
        tree = self.tree([("1", ["1", "2", "3", "4", "5"])])
        self.assertEqual(numbering_gaps(tree), [])
        self.assertEqual(numbering_gap_problems(tree, {"1": ["prose"]}, "ch1"), [])

    def test_sparse_set_is_not_consecutive_numbering(self):
        """按节重启编号 / 零星收割的书（Strogatz 型）密度不足 → 不出结论。"""
        tree = self.tree([("1", ["1", "3", "7", "20"])])
        self.assertEqual(numbering_gaps(tree), [])
        self.assertEqual(numbering_gap_problems(tree, {"1": ["x"]}, "ch1"), [])

    def test_rendered_number_not_reported(self):
        """单元已渲染该号（契约缺档）→ 本判据让路，闸门 ⑭ 的「编造」方向先报。"""
        tree = self.tree([("6.20", ["1", "2", "3", None, "5"])])
        self.assertEqual(numbering_gaps(tree), [(4, 3, 5)])
        self.assertEqual(numbering_gap_problems(
            tree, {"6.20": ["$$\na=b \\tag{4}\n$$"]}, "ch6"), [])

    def test_multi_tag_block_counts_every_number(self):
        tree = self.tree([("D14", ["1", ("2", ["2", "3"]), "4", ("5", ["5", "6", "7"])]),
                         ("14.8", ["8"])])
        self.assertEqual(numbering_gaps(tree), [])

    def test_letter_suffix_tag_shares_its_digit_head(self):
        tree = self.tree([("1", ["1", "2", "3b", "4"])])
        self.assertEqual(numbering_gaps(tree), [])

    def test_letter_chapter_tags_ignored(self):
        """附录字母章位编号 (A.5) 型不参与数字序列判据。"""
        tree = self.tree([("A.1", ["A.1", "A.2", "A.3"])])
        self.assertEqual(numbering_gaps(tree), [])

    def test_apostol_measured_case_ch6_12(self):
        """实测形态 ch6 (12)：截尾**不可见**（只判洞），中间空洞才报。"""
        tags = [str(i) for i in range(1, 12)]
        tree = self.tree([("6.20", tags)])
        probs = numbering_gap_problems(tree, {"6.20": ["prose without the number"]},
                                       "ch6")
        self.assertEqual([p for p in probs if "(12)" in p], [])
        tree2 = self.tree([("6.20", tags + [None])])   # 印面 (12) 的块在、tag 没了
        self.assertEqual(numbering_gap_problems(tree2, {"6.20": ["prose"]}, "ch6"),
                         [])                            # 12 在 max 之外 → 判据失明
        tree3 = self.tree([("6.20", tags[:9] + [None, "11", "12"])])
        probs3 = numbering_gap_problems(tree3, {"6.20": ["prose"]}, "ch6")
        self.assertEqual(len(probs3), 1)                 # (10) 是中间洞 → 报
        self.assertIn("(10)", probs3[0])


class TestMarginAnchorAuditGlued(unittest.TestCase):
    """页池编号列审计的**粘连锚点**开关（本书 19 处 unsupported 误报的根因）。

    动因 = Apostol IANT 实测：页边 `(N)` 被 OCR 与公式残渣切成同一块，整块-only
    的页池收不到号 → 契约里**真印的**号被 `unsupported` 方向成批误报（普查实测
    lost=0 / unsupported=19）。开关默认关（既往行为不变），开时与闸门 ⑱ 共用
    ``_ANCHOR_GLUED_RE`` / ``_RESIDUE_PROSE_RE`` 两条谓词。
    """

    COL = 60.0        # 编号列 x0（页边）
    BODY = 400.0      # 正文/公式区 x0
    TAGS = ["1", "2", "3", "4"]

    PROSE = "This proves the theorem and completes the whole argument here"

    def geom(self, rows_by_page, prose_at=None):
        """rows_by_page: {page: [(raw, x0)]} → page_geom_loader 同口径的 load。

        每页自动补一条**长散文块**（正文左缘 = ``prose_at``，默认 BODY）——编号列
        与正文区可分是本审计的前置条件（见 ``column_separable``），不补就无从判据。
        """
        pa = self.BODY if prose_at is None else prose_at
        pages = {}
        for p in set(rows_by_page) | {10, 11, 12}:   # 一章多页，正文缘样本才够
            rr = list(rows_by_page.get(p) or []) + [(self.PROSE, pa)]
            pages[p] = [(raw, x, x + 40, 100.0) for raw, x in rr]

        def load(pg):
            return pages.get(pg)
        return load

    def test_glued_off_keeps_past_behaviour(self):
        """默认关：与既往一致——粘连块不算锚点，真印的 (4) 被误报成假 tag。"""
        loader = self.geom({10: [("(1)", self.COL), ("(2)", self.COL),
                                 ("(3)", self.COL), ("(4) x = y", self.COL)]})
        lost, uns = margin_anchor_audit(contract(self.TAGS), loader, "ch1")
        self.assertEqual(lost, [])
        self.assertEqual(len(uns), 1)
        self.assertIn("(4)", uns[0])

    def test_glued_on_removes_false_unsupported(self):
        loader = self.geom({10: [("(1)", self.COL), ("(2)", self.COL),
                                 ("(3)", self.COL), ("(4) x = y", self.COL)]})
        lost, uns = margin_anchor_audit(contract(self.TAGS), loader, "ch1",
                                        glued=True)
        self.assertEqual((lost, uns), ([], []))

    def test_glued_lost_number_reported(self):
        """截尾形态（契约登记到 4，印面还有 (5)）——本审计看得见，空洞判据看不见。"""
        loader = self.geom({10: [("(1)", self.COL), ("(2)", self.COL),
                                 ("(3)", self.COL), ("(4)", self.COL),
                                 ("(5) B(x) = t(d) / r(qd)", self.COL)]})
        lost, uns = margin_anchor_audit(contract(self.TAGS), loader, "ch1",
                                        glued=True)
        self.assertEqual(uns, [])
        self.assertEqual(len(lost), 1)
        self.assertIn("(5)", lost[0])
        self.assertIn("粘连形态", lost[0])

    def test_glued_number_outside_column_not_trusted(self):
        """公式**内部**括号粘连成行首形状时，列外一律不收（几何仍是主筛子）。"""
        loader = self.geom({10: [("(1)", self.COL), ("(2)", self.COL),
                                 ("(3)", self.COL), ("(4)", self.COL),
                                 ("(99) = f(n)", self.BODY)]})
        lost, uns = margin_anchor_audit(contract(self.TAGS), loader, "ch1",
                                        glued=True)
        self.assertEqual(uns, [])
        self.assertEqual([m for m in lost if "(99)" in m], [])

    def test_glued_prose_residue_excluded(self):
        """`(12) We use Theorem 5.4 …` 是散文交叉引用，不是编号列锚点。"""
        loader = self.geom({10: [("(1)", self.COL), ("(2)", self.COL),
                                 ("(3)", self.COL), ("(4)", self.COL),
                                 ("(12) We use Theorem 5.4 to obtain", self.COL)]})
        lost, uns = margin_anchor_audit(contract(self.TAGS), loader, "ch1",
                                        glued=True)
        self.assertEqual([m for m in lost if "(12)" in m], [])

    def test_column_seeded_only_by_standalone_anchors(self):
        """列由独立锚点学出；全章无独立样本时**不出结论**（fail-closed）。"""
        loader = self.geom({10: [("(1) x = y", 900.0), ("(2) a + b", 30.0),
                                 ("(3) p(k)", 500.0)]})
        self.assertEqual(margin_anchor_audit(contract(self.TAGS[:3]), loader,
                                             "ch1", glued=True), ([], []))
        self.assertEqual(len(page_anchor_index(loader, 10, 20, glued=True)), 3)
        self.assertIsNone(number_column(page_anchor_index(loader, 10, 20),
                                        set(self.TAGS[:3])))

    def test_corrupted_opening_bracket_still_attests(self):
        """实测 ch2：印面 `(4)` 被 OCR 成 `C4)`，左括号腐蚀形也要认（列内才认）。"""
        loader = self.geom({10: [("(1)", self.COL), ("(2)", self.COL),
                                 ("(3)", self.COL), ("C4)", self.COL)]})
        lost, uns = margin_anchor_audit(contract(self.TAGS), loader, "ch1")
        self.assertEqual((lost, uns), ([], []))
        # 裸数字块（无任何括号形）**不**算锚点
        loader2 = self.geom({10: [("(1)", self.COL), ("(2)", self.COL),
                                  ("(3)", self.COL), ("4", self.COL)]})
        self.assertEqual(len(page_anchor_index(loader2, 10, 20)), 3)

    def test_column_band_tolerates_margin_jitter(self):
        """同列样本 x0 抖动 ~140 像素时不得把页边号判成列外（27/35 误报的根因）。"""
        loader = self.geom({10: [("(1)", 54.0), ("(2)", 120.0), ("(3)", 170.0),
                                 ("(4)", 185.0)]})
        lost, uns = margin_anchor_audit(contract(self.TAGS), loader, "ch1")
        self.assertEqual((lost, uns), ([], []))
        # 但正文区（x0 远大于列带）仍须排除
        far = self.geom({10: [("(1)", 54.0), ("(2)", 120.0), ("(3)", 170.0),
                              ("(4)", 330.0)]})
        _l, u2 = margin_anchor_audit(contract(self.TAGS), far, "ch1")
        self.assertEqual(len(u2), 1)                       # 列外 = 不采信
        self.assertIn("(4)", u2[0])

    def test_overlapping_body_column_stays_silent(self):
        """本书形态：页边编号与散文行**同 x 带** → 几何失去判别力 → 不出结论。"""
        loader = self.geom({10: [("(1)", self.COL), ("(2)", self.COL),
                                 ("(3)", self.COL), ("(9)", self.COL)]},
                           prose_at=self.COL)      # 正文左缘 = 编号列（Apostol 实测）
        # (9) 是契约里的假 tag，但列不可分 → 本审计不判（让位给 numbering_gaps）
        self.assertEqual(margin_anchor_audit(contract(["1", "2", "3", "9"]),
                                             loader, "ch1"), ([], []))
        self.assertEqual(margin_anchor_audit(contract(["1", "2", "3", "9"]),
                                             loader, "ch1", glued=True), ([], []))

    def test_page_anchor_index_default_excludes_glued(self):
        loader = self.geom({10: [("(7) x = y", self.COL), ("(8)", self.COL)]})
        self.assertEqual([n for n, _p, _x, _y in page_anchor_index(loader, 10, 10)],
                         ["8"])
        self.assertEqual(
            sorted(n for n, _p, _x, _y in page_anchor_index(loader, 10, 10,
                                                            glued=True)),
            ["7", "8"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
