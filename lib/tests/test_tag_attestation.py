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
                             unharvested_anchor_tags, unharvested_anchor_problems)


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

    def test_noop_when_all_attested(self):
        tree = contract(["3", "7"], lo=10, hi=20)
        self.assertEqual(strip_unattested(tree, loader(self.PAGES)), [])
        self.assertEqual([n for _k, n in collect_contract_tags(tree)], ["3", "7"])

    def test_noop_when_pages_missing(self):
        tree = contract(["99"], lo=10, hi=12)
        self.assertEqual(strip_unattested(tree, loader({})), [])
        self.assertEqual([n for _k, n in collect_contract_tags(tree)], ["99"])


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
