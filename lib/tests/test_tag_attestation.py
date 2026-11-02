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
                             strip_unattested, unattested_tags, condemned_map,
                             unharvested_anchor_tags, unharvested_anchor_problems,
                             glued_anchor_tags, glued_anchor_problems,
                             exercise_context_keys,
                             numbering_gaps, numbering_gap_problems,
                             margin_anchor_audit, page_anchor_index, number_column,
                             bare_only_leg_enabled, lettered_leg_enabled, _condemned,
                             _label_index, _label_index_by_page, anchor_locations,
                             operand_only_paren_anchor, standalone_label_sites,
                             paren_block_is_factor_form, _num_shape,
                             _standalone_labels, _LATEX_STYLE_MACROS)


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
        self.assertTrue(any("2n" in p and "字母尾巴" in p for p in probs), probs)

    def test_lettered_tag_with_standalone_anchor_passes(self):
        """印面确有 `(18.10a)` 时形态启发式必须让位（2026-10-01 Koopman ch18 实测）。

        旧判据只看形态（21 个号里 19 个纯整数）就判「须在收割处剔除」，而 Q 层同一
        号要求写 `\tag` = 两头堵；Strogatz 的 `2n` 按定义没有括号锚点，故上一条
        负向用例与本条同时成立才算「只削假阳」。
        """
        tags = [str(n) for n in range(1, 20)] + ["18.10a", "18.10b"]
        tree = contract(tags, lo=500, hi=502)
        pages = {p: ["(%d)" % n for n in range(1, 20)]
                 + ["(18.10a)", "(18.10b)"] for p in range(500, 503)}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])

    def test_lettered_tag_with_bare_only_anchor_still_flagged(self):
        """只有裸排 `18.10a`（无括号）时照旧判毒：裸块多半是公式内部碎片。"""
        tags = [str(n) for n in range(1, 20)] + ["18.10a"]
        tree = contract(tags, lo=500, hi=501)
        pages = {p: ["%d" % n for n in range(1, 20)] + ["18.10a"]
                 for p in range(500, 502)}
        probs = tag_attestation_problems(tree, loader(pages))
        self.assertTrue(any("18.10a" in p and "字母尾巴" in p for p in probs), probs)

    def test_lettered_factorial_anchor_still_flagged(self):
        """`(2n)!!` 是双阶乘不是编号：块内任意位置的括号形态**不构成** lettered 豁免。

        基础\数学分析 ch7 p325 / ch14 p209 实测——若豁免沿用宽松口径（`paren` 收块内
        任意 `(N)`），这个公式碎片号会被放行并要求写手 `\tag{2n}`。
        """
        tags = [str(n) for n in range(1, 20)] + ["2n"]
        tree = contract(tags, lo=304, hi=306)
        pages = {p: ["%d" % n for n in range(1, 20)] + ["(2n)!!", "2·4..(2n)"]
                 for p in range(304, 307)}
        probs = tag_attestation_problems(tree, loader(pages))
        self.assertTrue(any("2n" in p and "字母尾巴" in p for p in probs), probs)

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
        self.assertTrue(any("字母尾巴" in p for p in
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


class TestLetteredLegEvidencePaths(unittest.TestCase):
    """判据③的「本章体例不用字母」有**两条证据腿**，且分母读**全量** tag。

    动因（2026-10-30 跨 58 书 / 477 契约行普查，`tools/census_gate14_lettered_blindness.py`）：
    旧口径只有一条契约侧比例腿，而且它的样本是**摘掉 `attested` 之后**的 tag 集 —— 于是
    「登记得越多、闸越弱」。基础\\数学分析 把 ``known_book`` 写成 `1..30`（本书编号正是章内
    `(1)`..`(30)` 型），采样纯整数 tag 塌到 0–2 个，`n_numeric >= 5` 这道门**永远**进不去，
    该腿在全语料**点名 0 处＝死代码**，13 个公式残渣字母尾幻影（`2x` / `2M` / `12x` / `0x`）
    全部放过。两条改动的分工：
      * 分母读全量（登记只豁免**裁决**，不豁免**体例样本**）→ `test_full_registry...`；
      * 加印面侧证据（页窗里「整块就是 `(号)`」的独立编号 ≥5 且字母尾 ≤10%）→
        `test_printed_convention...`；它读的是页窗，与契约厚薄、登记多少无关，方向才对。
    反向保护同样测：印面自己就在用字母编号的章（Numerical-Methods ch11 实测 15 块独立编号
    里 13 块带字母尾）不许被形态启发式开口；页窗量不到体例（独立块 <5，数学分析 ch8 /
    Evans-SDE 附录实测）也不许猜。
    """

    def _kinds(self, tree, pages, attested=None):
        return _condemned(tree, loader(pages), attested)[1]

    def test_full_registry_does_not_gut_the_convention_sample(self):
        tree = contract([str(n) for n in range(1, 31)] + ["2x"], lo=10, hi=12)
        pages = {p: ["%d" % n for n in range(1, 31)] + ["2x"]
                 for p in range(10, 13)}
        # 30 个纯整数号全部「已登记」：旧口径下体例样本 = 0 个整数 → 腿关 → `2x` 逃过
        self.assertEqual(self._kinds(tree, pages, attested=[str(n) for n in range(1, 31)]),
                         {"2x": "lettered"})

    def test_registered_numbers_stay_exempt_although_in_the_denominator(self):
        """全量样本只喂**分母**；`attested` 里的号照旧不得判毒（登记 = 人工确证真印）。"""
        tree = contract([str(n) for n in range(1, 16)] + ["7a"], lo=10, hi=12)
        pages = {p: ["(%d)" % n for n in range(1, 16)] + ["7a"]
                 for p in range(10, 13)}
        self.assertEqual(set(self._kinds(tree, pages)), {"7a"})
        self.assertEqual(self._kinds(tree, pages, attested=["7a"]), {})
        self.assertEqual(tag_attestation_problems(tree, loader(pages),
                                                  attested=["7a"]), [])

    def test_printed_convention_names_lettered_phantom_when_contract_is_thin(self):
        """契约侧两条门都进不去（整数 3 个 <5；括号 tag 3 个 → bare-only 腿也关），
        但页窗有 7 块「整块就是 `(号)`」的纯整数独立编号 → 印面侧腿点名 `3x`。"""
        tree = contract(["1", "2", "3", "3x"], lo=10, hi=12)
        pages = {p: ["(%d)" % n for n in range(1, 8)] + ["3x"]
                 for p in range(10, 13)}
        self.assertEqual(self._kinds(tree, pages), {"3x": "lettered"})
        probs = "\n".join(tag_attestation_problems(tree, loader(pages)))
        self.assertIn("独立印刷号", probs)

    def test_below_five_standalone_blocks_is_unmeasurable_not_a_verdict(self):
        """页窗只有 4 块独立编号（数学分析 ch8 实测形态）→ 体例**量不到**，不许由 tag
        分布猜；补到 5 块即开口。"""
        tree = contract(["3", "2M"], lo=10, hi=12)
        pages = {p: ["(%d)" % n for n in range(1, 5)] + ["2M"]
                 for p in range(10, 13)}
        self.assertEqual(self._kinds(tree, pages), {})
        pages[10] = list(pages[10]) + ["(5)"]
        self.assertEqual(self._kinds(tree, pages), {"2M": "lettered"})

    def test_printed_lettered_convention_keeps_the_leg_shut(self):
        """印面字母尾 >10%（Numerical-Methods ch11 型：15 块独立编号里 13 块带字母尾）
        = 本章**真用**字母编号 → 形态启发式不开口，
        只在页窗里查无锚点的号仍由判据①处理。"""
        tree = contract(["9x", "9w"], lo=10, hi=11)
        pages = {p: ["(1)", "(2)", "(9x)", "(9y)", "(9z)", "9w"]
                 for p in range(10, 12)}
        self.assertEqual(self._kinds(tree, pages), {})

    def test_roman_prefix_labels_are_not_lettered_convention(self):
        """印面是 `V.1`..`V.6`（罗马数字章**前缀**）时，印面腿不得被「含字母」挤死。

        methods-of-homological-algebra ch5 实测：30 块独立编号里 29 块含字母，但**没有一块
        带字母尾巴** —— 旧口径（`_LETTER_RE` 数分母）下该章契约里的 `9x` / `9y`（公式内部的
        裸残渣）永远量不到体例矛盾（＝当时全架剩下的 2 个失明站点；2026-10-31 改口径后
        两个号都被点名，已按 fitz 裁剪目视裁定为笛卡尔方框箭头标号 `g_χ`/`g_y` 的 OCR 误读
        并摘账）。
        """
        tree = contract(["9x", "9y"], lo=10, hi=11)
        pages = {p: ["(%s)" % x for x in ("V.1", "V.2", "V.3", "V.4", "V.5", "V.6")]
                 + ["9x", "9y"] for p in range(10, 12)}
        self.assertEqual(self._kinds(tree, pages),
                         {"9x": "lettered", "9y": "lettered"})

    def test_prefix_lettered_tag_is_not_a_criterion_three_candidate(self):
        """字母**章位**号（`V.9` 型）没有尾巴 → 不是判据③的候选；页窗里查无此号时由判据①
        判（`unattested`），而不是「形态与本章体例矛盾」。"""
        tree = contract(["V.9"], lo=10, hi=11)
        pages = {p: ["(%s)" % x for x in ("V.1", "V.2", "V.3", "V.4", "V.5")]
                 for p in range(10, 12)}
        self.assertEqual(self._kinds(tree, pages), {"V.9": "unattested"})

    def test_message_names_the_evidence_that_fired(self):
        """报文要说清是哪条证据证的「本章不用字母」：契约侧证的不得写成印面侧的话，
        否则读者会以为页窗里有独立编号（印面其实量不到）。"""
        tree = contract([str(n) for n in range(34, 60)] + ["2n"], lo=10, hi=12)
        pages = {p: ["%d" % n for n in range(34, 60)] + ["2n"]
                 for p in range(10, 13)}
        probs = "\n".join(tag_attestation_problems(tree, loader(pages)))
        self.assertIn("不带字母尾巴", probs)
        self.assertNotIn("独立印刷号", probs)

    def test_condemned_map_matches_the_set_export(self):
        """普查出口（`condemned_map`）与收割/闸门用的集合出口（`unattested_tags`）
        必须是同一趟裁决 —— 两处各算一份 `setdefault` 链就会悄悄分叉。"""
        tree = contract(["7", "25", "1.104"], lo=10, hi=20)
        pages = {p: ["(%d)" % n for n in range(1, 20)] for p in range(10, 21)}
        mapping = condemned_map(tree, loader(pages))
        self.assertEqual(set(mapping), unattested_tags(tree, loader(pages)))
        self.assertEqual(mapping["25"], "unattested")
        self.assertEqual(mapping["1.104"], "unattested")

    def test_lettered_leg_needs_lettered_tags_at_all(self):
        """纯整数章没有字母尾 → 腿不成立（`n_lettered=0` 是硬门，两条证据腿都别想开口）。"""
        self.assertFalse(lettered_leg_enabled(50, 0, 30, 0))
        self.assertTrue(lettered_leg_enabled(0, 1, 20, 0))
        self.assertFalse(lettered_leg_enabled(0, 1, 20, 4))
        self.assertFalse(lettered_leg_enabled(0, 1, 4, 0))


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


class TestSymbolOnlyAnchors(unittest.TestCase):
    """**无数字头**的符号编号 `(*)`：印刷锚点识别（Arnold《经典力学的数学方法》实测）。

    动因 = 该书 §52（印刷 p.231）的展示式 ṗ = −∂H/∂q, q̇ = ∂H/∂q 印作 `(*)`，而编号
    主体 SSOT `formula_num_core` 以 `\\d+` 开头 → `_PAREN_LABEL_RE` / `_BARE_LABEL_RE`
    双双查无锚点 → 契约里回填的 tag `*` 判「疑似 OCR 噪声」，写手照印面 `\\tag{*}`
    判编造、删掉判漏写（两头堵）。
    负向用例锁住放宽的边界：**只**认括号形态，裸排星号（脚注号 / 乘号 / OCR 火星）
    一律不算锚点。
    """

    def test_parenthesized_star_anchor_attests(self):
        tree = contract([str(n) for n in range(1, 10)] + ["*"], lo=226, hi=249)
        pages = {p: ["(%d)" % n for n in range(1, 10)] for p in range(226, 250)}
        pages[246] = list(pages[226]) + ["(*)"]
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])
        self.assertEqual(strip_unattested(tree, loader(pages)), [])
        self.assertIn("*", [n for _k, n in collect_contract_tags(tree)])

    def test_star_detected_as_formula_attests(self):
        """`(*)` 被 MFD 当**公式**检测出来（`( * )` 带空格）时同样算锚点。"""
        tree = contract(["*"], lo=246, hi=247)
        pages = {246: ["( * )"], 247: ["prose"]}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])

    def test_star_without_printed_anchor_still_condemned(self):
        """负向：页窗里没印过 `(*)` 时 tag `*` 照旧判毒（放宽不是免检）。"""
        tree = contract([str(n) for n in range(1, 10)] + ["*"], lo=226, hi=228)
        pages = {p: ["(%d)" % n for n in range(1, 10)] for p in range(226, 229)}
        probs = tag_attestation_problems(tree, loader(pages))
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("*", probs[0])
        self.assertEqual(strip_unattested(tree, loader(pages)), ["*"])

    def test_bare_star_is_not_an_anchor(self):
        """负向：裸排 `*`（脚注星号 / 乘号 / OCR 火星）与编号无形态区别 → 不采信。"""
        tree = contract(["*"], lo=246, hi=247)
        pages = {246: ["*", "**"], 247: ["a * b = c"]}
        probs = tag_attestation_problems(tree, loader(pages))
        self.assertTrue(any("*" in p for p in probs), probs)

    def test_double_star_attests(self):
        tree = contract(["**"], lo=10, hi=11)
        pages = {10: ["(**)"], 11: ["prose"]}
        self.assertEqual(tag_attestation_problems(tree, loader(pages)), [])

    def test_digit_head_poison_verdicts_unaffected(self):
        """放宽不得顺手放过**有数字头**的实测毒 tag（Kreyszig 小数尾巴 / 波长）。"""
        tree = contract([str(n) for n in range(1, 23)] + ["22", "18751A", "*"],
                        lo=10, hi=12)
        pages = {p: ["(%d)" % n for n in range(1, 22)] + ["(*)"] for p in range(10, 13)}
        probs = "\n".join(tag_attestation_problems(tree, loader(pages)))
        self.assertIn("22", probs)
        self.assertIn("18751A", probs)
        self.assertNotIn("契约编号 * ", probs)
        self.assertEqual(strip_unattested(tree, loader(pages)), ["22", "18751A"])


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

    def test_math_index_paren_is_not_a_neighbor(self):
        r"""判据④负向：兄弟单元正文里的 KaTeX 块位指标 `^{(11)}` 不是「印刷裸编号」。

        实测动因（郑大钟《线性系统理论》ch10 例10.3，2026-11-02）：契约把印面右缘的
        **分块矩阵块位标签** `(12)` 误收成锚点，成为候选漏号；同节兄弟单元 0092 忠实照
        印面写了 `\eta_1^{(11)}`（第 (1,1) 块的行列表记号）。旧 `_UNIT_PAREN_RE` 把
        `(11)` 当裸编号收进逃逸池 → 判据④「(12) 有邻居 11」假命中 → 整章凭空变红。
        收紧后的后顾 `(?<![\\^_{\\\\])` 排除 `^{...}` 之后的数学分组括号 → 池里没有 "11"
        → 判据④不成立 → 不报。真正的印刷裸编号（行首/空白/中文标点后）仍会被收（见
        :meth:`test_number_already_rendered_in_section_escapes`）。
        """
        tree = self.tree([self.disp(r"\mathbf{D}_{\mathrm{hc}}^{-1}\mathbf{D}_{\mathrm{Lc}}"),
                          self.txt("(12)", line_start=True, indent=24.8)])
        # 候选 (12) 需靠邻居 11/13 才够着判据④；0092 的 `^{(11)}` 恰是唯一会喂 "11" 的串
        bodies = {"13.5": [r"$\eta_1^{(11)}$ 与 $\eta_1^{(1q)}$ 组成块阵\n"]}
        self.assertEqual(unharvested_anchor_problems(tree, bodies), [])
        # 对照：把同一 (11) 换成真·印刷裸编号形态（空白后独立成括），邻居即成立、照报
        bodies_real = {"13.5": ["矩阵见表 \\qquad (11) 处\n"]}
        probs = unharvested_anchor_problems(tree, bodies_real)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("(12)", probs[0])

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

    def test_exercise_context_switches_prescription_not_verdict(self):
        """习题语境只换**处方**不换**判定**：照旧报，但不逼写手写 `\\tag{N}`。

        实测 复变函数论（钟玉泉第五版）ch6：契约把「第六章习题」尾块折进
        `定理6.13`（键不含 `-`，④ 后半条例够不着），印面 `(3)` 是 (一)1 的小问标号，
        旧措辞却写「须回填契约 tag + manifest 后由单元补 \\tag{3}」——照做就是凭空编号。
        """
        tree = self.tree([self.disp("\\frac{1}{(z-\\alpha)^m}"), self.txt("(3)")],
                         key="定理6.13")
        bodies = {"定理6.13": ["正文 (2) 在账\n\n> ## 第六章习题\n\n" + chr(92) + "tag{2}\n"]}
        probs = unharvested_anchor_problems(tree, bodies, chapter_label="ch6")
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("小问标号", probs[0])
        self.assertIn("先回印面裁向", probs[0])
        self.assertNotIn("须回填契约 tag", probs[0])

    def test_no_exercise_heading_keeps_harvest_prescription(self):
        """负向：正文没有习题标题 → 旧处方原样保留（回填契约 tag + `\\tag{N}`）。"""
        tree = self.tree([self.disp("a = b"), self.txt("(3)")])
        bodies = {"13.5": [chr(92) + "tag{2}\n"]}
        probs = unharvested_anchor_problems(tree, bodies)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("收割漏号，须回填契约 tag + manifest 后由单元补 "
                      + chr(92) + "tag{3}", probs[0])
        self.assertNotIn("小问标号", probs[0])

    def test_prose_mention_of_exercises_is_not_a_heading(self):
        """负向：从句式散文提到习题 ≠ 习题标题（尾锚把整行锁死，防语境被冒领）。"""
        bodies = {"D3": ["由第五章习题（二)第14题，可知 f 解析。\n",
                         "Exercise 3 shows the bound is sharp.\n",
                         chr(92) + "tag{2}\n"]}
        self.assertEqual(exercise_context_keys(bodies), set())
        tree = self.tree([self.disp("a = b"), self.txt("(3)")], key="D3")
        probs = unharvested_anchor_problems(tree, bodies)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("须回填契约 tag", probs[0])

    def test_exercise_heading_recognised_shapes(self):
        """标题侧的正/负形：`## 第六章习题`/`**Exercises**`/裸「习题」/**引用壳 `> ##`**
        算；带句子的长行与 `习题解》` 一类不算。"""
        ok = ["## 第六章习题", "### 习题", "习题", "**Exercises**", "## Problems",
              "## 第六节 思考题", "## 习题（第 200 页）",
              "> ## 第六章习题", "> > ## 习题", "> 习题"]     # 单元尾块的实际书写形
        bad = ["## 6.13 分歧覆盖定理", "习题与提要见书末", "由第六章习题（二)第5题可知",
               "问题在于该级数是否收敛", "## 例 6.20", "> 由第五章习题（二)第14题，可知"]
        for s in ok:
            self.assertEqual(exercise_context_keys({"K": [s + "\n"]}), {"K"}, s)
        for s in bad:
            self.assertEqual(exercise_context_keys({"K": [s + "\n"]}), set(), s)


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


class TestLegExtraction(unittest.TestCase):
    """``bare_only_leg_enabled`` 与 ``_condemned`` 里那条腿必须是**同一处算术**。

    抽成函数的动机：只读普查 ``tools/census_gate14_bare_blindness.py`` 要报「腿为什么关」，
    自己再写一遍 ``>= 5 and >= 0.9 *`` 就等着两边漂移。这里把真值表和 `_condemned` 的
    实际翻转钉在一起。
    """

    def test_truth_table(self):
        self.assertFalse(bare_only_leg_enabled(4, 0))     # paren 证据不足：本就不该开
        self.assertTrue(bare_only_leg_enabled(5, 0))
        self.assertTrue(bare_only_leg_enabled(9, 1))      # 9 >= 0.9*10
        self.assertFalse(bare_only_leg_enabled(0, 9))
        # 🔴 方向性缺陷的证据（不是回归）：幻影多一个 → 分母变大 → 腿自己关掉
        self.assertFalse(bare_only_leg_enabled(9, 2))

    def _pages(self, bare):
        return {p: ["(%d)" % n for n in range(1, 10)] + [str(x) for x in bare]
                for p in range(10, 21)}

    def test_condemned_flips_exactly_with_the_leg(self):
        one = contract(["1", "2", "3", "4", "5", "6", "7", "8", "9", "30"])
        _t, k1 = _condemned(one, loader(self._pages([30])))
        self.assertEqual(k1, {"30": "bare-only"})
        self.assertTrue(bare_only_leg_enabled(9, 1))

        two = contract(["1", "2", "3", "4", "5", "6", "7", "8", "9", "30", "31"])
        _t, k2 = _condemned(two, loader(self._pages([30, 31])))
        self.assertEqual(k2, {})                          # 腿被自己的幻影压死 → 放行
        self.assertFalse(bare_only_leg_enabled(9, 2))


class TestLabelIndexByPage(unittest.TestCase):
    """按页锚点索引 ≡ 章级索引的键集（普查要的是「锚在哪一页」这一维，不是第二套判据）。"""

    def test_keys_equal_label_index(self):
        pages = {10: ["(7)", "42"], 11: ["(8)", "42", "x = 9"], 12: None}
        paren, bare = _label_index(loader(pages), 10, 12)
        p_by, b_by = _label_index_by_page(loader(pages), 10, 12)
        self.assertEqual(set(p_by), paren)
        self.assertEqual(set(b_by), bare)

    def test_pages_are_attributed_not_merged(self):
        _p, b_by = _label_index_by_page(
            loader({10: ["(7)", "42"], 11: ["(8)", "42"]}), 10, 11)
        self.assertEqual(b_by["42"], {10, 11})
        self.assertEqual(b_by.get("7"), None)             # 括号形不进裸排集
        # 🔴 章级并集给不出的东西：只有一个裸块在**别的页**，本地就没锚（幻影自证的通道）
        _p2, one_page = _label_index_by_page(loader({10: ["42"], 11: ["7"]}), 10, 11)
        self.assertEqual(one_page["42"], {10})
        self.assertEqual(one_page["7"], {11})


class TestAnchorLocations(unittest.TestCase):
    """假锚通道的举证来源：`anchor_locations` 要能**按页把原块交回来**，
    且「裸块」按整块成立（`tools/deregister_formula_tags.py --false-anchor` 打印的
    `假锚证据` 就是这份；判据松一分，摘除真号的通道就宽一分）。
    """

    def test_bare_needs_the_whole_block(self):
        locs = anchor_locations(loader({10: ["29"],
                                         11: ["page 29 of 41", "see 29 above"]}),
                                 10, 11)
        self.assertEqual(set(locs["29"]["bare"]), {10})
        self.assertEqual(locs["29"]["paren"], {})
        self.assertNotIn("41", locs)          # 混排块里的数字一个都不算锚点

    def test_raw_block_is_kept_for_forensics(self):
        """归一化号会骗人（`(12)` 与 `x^2 = (12) + 1` 是两种印面），台账要原块。"""
        locs = anchor_locations(loader({10: ["(12)", "x^2 = (12) + 1"]}), 10, 10)
        self.assertEqual(locs["12"]["paren"][10],
                         ["(12)", "x^2 = (12) + 1"])
        self.assertEqual(locs["12"]["bare"], {})

    def test_samples_are_distinct_blocks_and_capped(self):
        r"""同一个原块（去首尾空白）只记一次，样本上限 3 块——假锚通道的台账打印靠这份。

        四个块都必须是**白名单壳**宏：`\a`/`\b` 一类未收录的命令按新折平留在形态里，
        整块就不再是「纯编号形」，测不到「去重 + 截 3」这条本意（2026-10-30 该缺陷修复时
        旧夹具正是靠无差别删宏才凑出 4 个锚点）。
        """
        locs = anchor_locations(loader({10: ["29", "  29  ", "\\mathbf { 29 }"]}),
                                10, 10)
        self.assertEqual(locs["29"]["bare"][10], ["29", "\\mathbf { 29 }"])
        locs = anchor_locations(
            loader({10: ["\\mathbf { 29 }", "\\mathrm { 29 }",
                         "\\text { 29 }", "\\mathsf { 29 }"]}),
            10, 10)
        self.assertEqual(len(locs["29"]["bare"][10]), 3)

    def test_is_the_source_of_label_index_by_page(self):
        """同一处算术：按页索引必须由本函数投影出来，不许第二份匹配。"""
        pages = {10: ["(7)", "42"], 11: ["(8)", "42", "x = 9"], 12: None}
        locs = anchor_locations(loader(pages), 10, 12)
        p_by, b_by = _label_index_by_page(loader(pages), 10, 12)
        self.assertEqual(p_by, {n: set(d["paren"]) for n, d in locs.items()
                               if d["paren"]})
        self.assertEqual(b_by, {n: set(d["bare"]) for n, d in locs.items()
                                if d["bare"]})


class TestAnchorFormWhitelist(unittest.TestCase):
    r"""🔴 折平**只**许删排版壳：内容宏留在形态里，否则展示式自己的括号会**造出**一个
    印面上根本不存在的 `(N)` 锚点。动因（基础\数学分析 下册 物理页 259 = 印刷 245 实测）：
    旧 `_label_forms` 用 `\\[a-zA-Z]+` 无差别删宏名，于是
    `f ^ { \prime } \left( { \frac { 1 } { n \pi } } \right)` 被折成 `f'(1n)'`
    ——幻影 tag `1n` / `1x` 拿到「括号锚点」→ ⑭ 判不出毒，且
    `tools/deregister_formula_tags.py --false-anchor` 见「有 `(N)` 锚点」即**机械拒绝**，
    把真幻影分流到 `--mispaired`（处方指向一个并不存在的宿主节点）。

    放宽判据的每一分都得两头测：假阳（公式残渣不得成锚）与反向误伤（壳里的真号必须照旧
    成锚）。跨 776 章契约行 / 1,412,735 去重块的 A/B 见
    `tools/census_gate14_anchor_forms.py`（paren 站点 −3430/+15、bare −7343/+1、
    裁决变化仅 1 条、`known_true` 四档全数保住）。
    """

    def test_content_macros_do_not_fabricate_a_paren_anchor(self):
        """七条纯公式块（无一条印面带编号）在旧折平下各自造出 `1n`/`1x`/`12` 一类假锚。"""
        for blk in [r"f ^ { \prime } \left( { \frac { 1 } { n \pi } } \right)",
                    r"\left( { \frac { 1 } { x } } \right)",
                    r"g ( x ) = \Big( \frac { \pi } { 2 } \Big)",
                    r"\int _ { 0 } ^ { 1 } \left( \frac { 1 } { 2 } \right) dx",
                    r"\left( \frac { n + 1 } { n } \right) ^ { n }",
                    r"a _ { n } = ( 1 + \frac { 1 } { n } ) ^ { n } < ( e )",
                    r"( \frac { 1 } { 2 } )"]:
            self.assertEqual(anchor_locations(loader({10: [blk]}), 10, 10), {}, blk)

    def test_shell_macros_still_yield_their_printed_numbers(self):
        """真锚点靠的正是这批壳：字体/加粗/文本包装、定界符尺寸、老式字体切换开关。

        `({\\it20.60})`（Iwaniec–Kowalski p462）是这条的**存在理由**：命令名后面直接跟数字，
        按整词取名才命中——旧白名单分支用 `\\b` 时在这里反向误伤过一次。
        """
        locs = anchor_locations(loader({10: [
            r"( 7 \mathbf { c } ^ { \prime } )",
            r"\mathbf { 29 }",
            r"({\it20.60})",
            r"( 7 ^ { * } )",
            r"(2. 7. 5)",
        ]}), 10, 10)
        self.assertEqual(set(locs), {"7c'", "29", "20.60", "7*", "2.7.5"})
        self.assertEqual(set(locs["29"]["bare"]), {10})
        for n in ("7c'", "20.60", "7*", "2.7.5"):
            self.assertEqual(set(locs[n]["paren"]), {10}, n)

    def test_number_glued_into_a_formula_line_is_still_an_anchor(self):
        """既有口径不变：编号被 OCR 粘进公式行时按**块内任意位置**命中，内容宏不是障碍。"""
        locs = anchor_locations(loader({10: [r"\sum_k (12) + \pi"]}), 10, 10)
        self.assertEqual(set(locs["12"]["paren"]), {10})
        self.assertEqual(locs["12"]["paren"][10], [r"\sum_k (12) + \pi"])

    def test_accent_macros_are_content_not_shell(self):
        """`\\dot`/`\\hat` 的参数是**数学内容**，删掉就会把 `\\dot{2}` 之外的东西贴进括号 →
        不收进白名单；同一块里真印的 `(2)` 照旧命中，说明「不收录」不等于「吃掉锚点」。"""
        self.assertNotIn("dot", _LATEX_STYLE_MACROS)
        locs = anchor_locations(loader({10: [r"\dot { x } = ( 2 )"]}), 10, 10)
        self.assertEqual(set(locs["2"]["paren"]), {10})


class TestOperandOnlyParenAnchor(unittest.TestCase):
    r"""假锚通道的分流判据：页窗里的 `(N)` 是**算式里的一项**还是**页边编号**。

    动因（2026-10-31 Fraleigh《AFCAA》ch23 §23.1 印面 p.194 实测）：那页排的是 Z₁₂ 零因子
    的陪积链 `(2)(6) = (6)(2) = (3)(4) = … = (9)(8) = 0`，**整章页边一个公式编号也没印**
    （300 dpi 右缘裁剪 + 页窗 p208–220 跨距普查），可契约里躺着幻影 `tag:"3"` /
    `tags:["3","8"]`。⑭ 判不出它毒（括号锚点走「块内任意位置」口径，`(3)` 就在阵列**内容**
    里），而 `tools/deregister_formula_tags.py --false-anchor` 旧口径「有一个 `(N)` 就拒」
    又把它分流到 `--mispaired`——那条处方要求指认一个印面上不存在的宿主展示块。
    """

    def test_factor_chain_in_a_numberless_chapter_clears(self):
        """整章无独立编号块 + 每处 `(N)` 都贴括号/运算符 ⇒ 放行（本案四块原样）。"""
        pages = {10: [
            "(2)(6)=(6)(2)=(3)(4)=(4)(3)=(3)(8)=(8)(3)",
            "=(4)(6)=(6)(4)=(4)(9)=(9)(4)=(6)(6)=(6)(8)",
            "for（6-2）（6-3）=（4）(3)=0and（11-2)（11-3)=（9）（8)=0inZ12.",
            r"{ \begin{array} { r l } & { ( 2 ) ( 6 ) = ( 6 ) ( 2 ) = ( 3 ) ( 4 ) "
            r"= ( 4 ) ( 3 ) \end{array} }",
            "( 6 - 2 ) ( 6 - 3 ) = ( 4 ) ( 3 ) = 0"]}
        for num, want in (("3", 4), ("8", 3)):
            ok, why, ev = operand_only_paren_anchor(loader(pages), 10, 10, num)
            self.assertTrue(ok, "%s：%s %s" % (num, why, ev))
            # 放行时证据块要**原样**交给台账打印：只有含该号括号锚点的块才算。
            self.assertEqual(len(ev), want, "%s：%s" % (num, ev))

    def test_any_standalone_label_in_the_window_keeps_the_refusal(self):
        """🔴 承重墙的控件：同一批陪积链里**加一处**独立编号块 `(7)`，判据立刻翻回拒。

        「印面这一章有没有编号列」是放行唯一的章级依据——页窗里只要还印着整块就是 `(N)`
        的号，`(N)` 是编号的可能性就没被排除，通道必须照旧拒。
        """
        base = ["(2)(6)=(6)(2)=(3)(4)=(4)(3)=(3)(8)=(8)(3)"]
        ok, _why, _ev = operand_only_paren_anchor(loader({10: base}), 10, 10, "3")
        self.assertTrue(ok)
        ok, why, ev = operand_only_paren_anchor(
            loader({10: base + ["(7)"]}), 10, 10, "3")
        self.assertFalse(ok)
        self.assertIn("独立编号块", why)
        self.assertIn("(7)", ev[0])

    def test_glued_label_at_block_edge_is_number_form_not_factor(self):
        """页边编号被 OCR 粘在块首/块尾（一侧空着、一侧贴普通文字）仍是**编号本形**：
        「粘进公式行」的既有口径（`anchor_locations`）不许被本判据吃掉。"""
        for blk, num in (["(12) p(k) = 1", "12"],
                         ["x + y = z (12)", "12"]):
            ok, why, ev = operand_only_paren_anchor(loader({10: [blk]}), 10, 10, num)
            self.assertFalse(ok, blk)
            self.assertIn("编号本形", why)

    def test_roman_label_column_does_not_attest_a_bare_arabic_number(self):
        """承重墙从「整章任一独立编号块」收窄到「**同号形**」（2026-10-31 GM 实测）。

        Gelfand–Manin 页边印的是章级罗马号 `(III.41)`，而正文里 `F(\\mathcal{G})`、`f'(9)`
        这类**函子自变量**被 OCR 成 `(9)`：旧墙被罗马号列永久撑住，章章都印 `(III.x)` 的书里
        任何裸阿拉伯幻影都声称不了假锚，只能改口 `--mispaired` 去指认一个印面上不存在的主展示块。
        """
        pages = {10: ["(III.41)", "(111.12)",
                      "F(a) : F(9) —→ F(limG) = lim(F o G)",
                      "23. Construction of f'(9)",
                      "8(9)"]}
        ok, why, ev = operand_only_paren_anchor(loader(pages), 10, 10, "9")
        self.assertTrue(ok, "%s %s" % (why, ev))
        # 同一页窗里只要多出**一个**裸号独立块，同号形墙立刻落回：照旧拒。
        blocks = pages[10] + ["(9)"]
        ok, why, ev = operand_only_paren_anchor(loader({10: blocks}), 10, 10, "9")
        self.assertFalse(ok)
        self.assertIn("同号形", why)
        self.assertIn("(9)", ev[0])

    def test_num_shape_separates_the_two_label_columns(self):
        """号形三档口径：纯数字 `plain` / 带分隔点 `dotted` / 带字母 `lettered`。"""
        self.assertEqual(_num_shape("2"), "plain")
        self.assertEqual(_num_shape("12"), "plain")
        self.assertEqual(_num_shape("7c"), "lettered")
        self.assertEqual(_num_shape("11.12"), "dotted")
        self.assertEqual(_num_shape("III.41"), "dotted")
        self.assertNotEqual(_num_shape("III.41"), _num_shape("9"))
        self.assertEqual(_num_shape("7"), _num_shape("9"))

    def test_function_application_is_factor_only_when_zero_gap(self):
        """`F(9)`/`T(1)`/`f'(9)`＝**函数应用**（左括号零间隙贴拉丁字母/数字/撇号）算内容；
        带间隙的 `z (9)`、中文的 `其中(9)` 不算 —— 那两形正是页边号被切进正文行的样子。"""
        for blk, num in (("F(a) : F(9) —→ F(limG)", "9"),
                         ("8(9)", "9"),
                         ("23. Construction of f'(9)", "9"),
                         ("T →Y →→ C(r) —→T(1)", "1"),
                         (r"\longrightarrow } } & { { T ( 1 ) } }", "1")):
            self.assertIs(paren_block_is_factor_form(blk, num), True, blk)
        for blk, num in (("x + y = z (9)", "9"),
                         ("其中(9)成立", "9"),
                         ("On the contrary, in (2) we can consider", "2")):
            self.assertIs(paren_block_is_factor_form(blk, num), False, blk)

    def test_no_paren_anchor_at_all_is_not_a_clearance(self):
        """页窗里根本没有 `(num)` 时说「放行」是空转——调用方（假锚通道）此时没有门要开。"""
        ok, why, _ev = operand_only_paren_anchor(
            loader({10: ["29", "page 41 of 60"]}), 10, 10, "29")
        self.assertFalse(ok)
        self.assertIn("无需分流", why)

    def test_standalone_labels_projects_the_same_sites(self):
        """一处匹配：lettered 豁免的强证据口径必须是本判据那份 sites 的投影。"""
        pages = {10: ["(7)", "(12)  label", "> (3).", "( 2 ) ( 6 ) = ( 6 ) ( 2 )"]}
        self.assertEqual(_standalone_labels(loader(pages), 10, 10),
                         set(standalone_label_sites(loader(pages), 10, 10)))


if __name__ == "__main__":
    unittest.main(verbosity=2)

