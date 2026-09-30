# -*- coding: utf-8 -*-
"""抽取器侧类型词形近补救（lib/label_typo 接入 extract_items_en，2026-09-28）。

根因：Apostol《Introduction to Analytic Number Theory》ch2 p42 印刷「Theorem 2.7
For all f we have I * f = f * I = f.」被 OCR 读成「**Theorerm** 2.7 …」。
`lab_re` 用正字（EN_LABELS）构造，形近残字**整体失配** → 该条既不入分章契约，
也不在 `check_structure_completeness` 的源侧候选集里，B 层只剩「序列 1..27 缺号 7」
的死锁。补救此前只在**校验侧**有（`_label_typo_normalize`），于是每轮重建契约都要
重跑一次 `--backfill` 才绿 = 补数据，不是根治。现两处共用 `lib/label_typo.py`。

运行：
  python flows/write-source/structure/script/tests/test_label_typo_extractor_rescue.py
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

_SCRIPT = os.path.join(_ROOT, "flows", "write-source", "structure", "script")
if _SCRIPT not in sys.path:
    sys.path.insert(0, _SCRIPT)
import extract_items_en as ee        # noqa: E402
from lib.label_typo import label_typo_normalize  # noqa: E402


def _mk(d, pages):
    """pages: [[行, …], …] → page_001.json …（poly 只给占位几何，抽取器不看）。"""
    for p, lines in enumerate(pages, start=1):
        blocks = [{"text": ln,
                  "poly": [90, 150 + 60 * i, 700, 190 + 60 * i,
                           90, 190 + 60 * i, 90, 150 + 60 * i]}
                 for i, ln in enumerate(lines)]
        with open(os.path.join(d, "page_%03d.json" % p), "w", encoding="utf-8") as fh:
            json.dump({"text": blocks, "formulas": []}, fh)


def _keys(pages, **kw):
    with tempfile.TemporaryDirectory() as d:
        _mk(d, pages)
        items = ee.extract_items_en(d, 1, len(pages), want_examples=True,
                                    section_scoped=False, **kw)
    return sorted(it["key"] for it in items), [(it["key"], it["page"]) for it in items]


GOOD = ["Theorem 2.6 Dirichlet multiplication is commutative and associative.",
        "Theorem 2.8 If f is an arithmetical function with f(1) != 0 there is a"]


class TestTypoHeadIsExtracted(unittest.TestCase):
    """正判据：块首形近类型词 + 点分序标 → 条目按正字入约。"""

    def test_theorerm_head_becomes_theorem_27(self):
        pages = [["Theorerm 2.7 For all f we have I * f = f * I = f."], GOOD]
        keys, _ = _keys(pages)
        self.assertIn("Theorem 2.7", keys,
                      "OCR 形近条头须由抽取器自愈入约，不得只靠 --backfill：%s" % keys)

    def test_anchor_page_follows_document_order(self):
        pages = [GOOD[0:1], ["Theorerm 2.7 For all f we have I * f = f * I = f."],
                 [GOOD[1]]]
        keys, pairs = _keys(pages)
        self.assertIn(("Theorem 2.7", 2), pairs, "锚点页须是形近条头所在页")

    def test_lowercase_garble_also_rescued(self):
        pages = [["theoremt 2.6 Dirichlet multiplication is associative here."]]
        keys, _ = _keys(pages)
        self.assertIn("Theorem 2.6", keys, "%s" % keys)


class TestSplitWordHeadIsExtracted(unittest.TestCase):
    """断词型（Evans 附录 C p720 实测 2026-09-30）：条头类型词被 OCR 从中间断开。

    印刷「THEOREM 1 (Gauss-Green Theorem)」读成「THEO REM 1 (Gauss-Green Theorem}」，
    正字正则整体失配 → 附录只剩定理 2..8，B 层报「缺号 1」而源侧差集为空，闸门
    FAIL 无从回填。同一 `lib/label_typo` 判据补一条断词通道。
    """

    def test_split_head_rescued_with_dotted_ordinal(self):
        pages = [["THEO REM 2.7 For all f we have I * f = f * I = f."]]
        keys, _ = _keys(pages)
        self.assertIn("Theorem 2.7", keys, "%s" % keys)

    def test_split_head_rescued_with_bare_ordinal(self):
        # Evans 附录体例：条内计数器裸单号（THEOREM 1 / THEOREM 2 …）。
        pages = [["THEO REM 1 (Gauss-Green Theorem}. (i) Suppose u is in C1(U)."],
                 ["THEOREM 2 (Integration by parts formula). Let u, v be given."]]
        keys, _ = _keys(pages, single=True)
        # 断词补救写正字大小写、原样条头保留 OCR 大写，键在 type 映射处归一，
        # 故此处按大小写无关比对（判的是「条目在不在账」，不是印刷大小写）。
        _up = {k.upper() for k in keys}
        self.assertIn("THEOREM 1", _up, "裸单号断词条头须自愈入约：%s" % keys)
        self.assertIn("THEOREM 2", _up, "%s" % keys)


class TestSplitWordGuardsHold(unittest.TestCase):
    """断词型负向：只容**一次**断点、首词已是正字不改、其后无序标不改。"""

    def test_first_token_already_canonical_is_untouched(self):
        keys, _ = _keys([["Theorem REM 3.1 is not how the head is printed."]])
        self.assertEqual([], [k for k in keys if k.startswith("Theorem")], "%s" % keys)

    def test_double_split_is_not_rescued(self):
        keys, _ = _keys([["TH EO REM 2.7 only one breakpoint is tolerated."]])
        self.assertEqual([], keys, "%s" % keys)

    def test_split_word_without_ordinal_is_not_rescued(self):
        keys, _ = _keys([["THEO REM mark that sentence is plain prose here."]])
        self.assertEqual([], keys, "%s" % keys)

    def test_helper_returns_none_for_correct_label(self):
        self.assertIsNone(label_typo_normalize("Theorem 2.7 Real head text.",
                                               ee.EN_LABELS))

    def test_helper_rewrites_split_word_to_canonical(self):
        got = label_typo_normalize("THEO REM 1 (Gauss-Green Theorem}.",
                                   ee.EN_LABELS)
        self.assertEqual("Theorem 1 (Gauss-Green Theorem}.", got)



class TestGuardsHold(unittest.TestCase):
    """负向四则：复数形 / 散文近似词 / 块中引用 / 无点分序标，均不得成条目。"""

    def test_plural_label_is_not_rescued(self):
        keys, _ = _keys([["Theorems 2.9 and 2.10 are stated without proofs here."]])
        self.assertEqual([], [k for k in keys if k.startswith("Theorem")],
                         "复数形只出现在交叉引用/眉题，永不是条头：%s" % keys)

    def test_prose_near_label_is_not_rescued(self):
        keys, _ = _keys([["These 2.7 definitions recur throughout the chapter."]])
        self.assertEqual([], keys, "%s" % keys)

    def test_midblock_reference_is_not_rescued(self):
        keys, _ = _keys([["We now need Theorerm 2.11 for the next chapter only."]])
        self.assertEqual([], keys, "%s" % keys)

    def test_no_ordinal_after_word_is_not_rescued(self):
        keys, _ = _keys([["Theorerm theory is the study of prime numbers."]])
        self.assertEqual([], keys, "%s" % keys)


class TestHelperIsSharedSingleSource(unittest.TestCase):
    """两处（抽取器 / 查漏校验）必须调同一个 lib/label_typo 判据。"""

    def test_helper_returns_none_for_correct_label(self):
        self.assertIsNone(label_typo_normalize("Theorem 2.7 Real head text.",
                                               ee.EN_LABELS))

    def test_helper_rewrites_only_the_first_word(self):
        got = label_typo_normalize("Theorerm 2.7 For all f we have I * f = f.",
                                   ee.EN_LABELS)
        self.assertEqual("Theorem 2.7 For all f we have I * f = f.", got)

    def test_checker_module_imports_the_shared_lib(self):
        sys.path.insert(0, os.path.join(_ROOT, "verify", "script"))
        import check_structure_completeness as csc
        self.assertIs(csc._label_typo_lib.label_typo_normalize,
                      label_typo_normalize,
                      "校验侧不得另写一份判据（分叉后两边漏抽/漏检形态会不一致）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
