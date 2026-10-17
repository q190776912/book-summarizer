"""判据：条头位上的**散文谓语**必须降级为 reference，不得回填成幻影条目。

形态（Lehmann《Elements of Large-Sample Theory》ch3 §3.2 实测，2026-10-15）：
p159（物理页 172）段首印着
    Theorem 3.2.2 establishes consistency of the tests in Examples 3.1.3,
    3.1.5, and 3.1.6 (Problem 3.2).
而全书**没有** Theorem 3.2.2 这个条头（§3.2 只有 Example 3.2.1…3.2.6，且全书
"Theorem 3.2" 只此一处）。标题锚定扫描把它读成 `readable` 遗漏项 → 闸门 FAIL →
`--backfill` 会往契约里插一条正文是「谈论别的例子的一句散文」的定理，B 层序列
随之被撑歪。

判据三条同时成立才降级（`_prose_predicate_ref`）：
  ① 候选带类型词（has_label）且序标可读；
  ② 序标后紧跟**小写**报道/系动词（`_PROSE_PREDICATE_WORDS`，刻意不含
     if/of/in/we/it 等能真正开启一条陈述的词）；
  ③ 契约里**同节无同类型**条目（有则说明该号落在活序列上，是真条头）。
命中归 `reference`（不回填、不拦闸、报告留痕），与强引用标记同一分流。

正向：①「Theorem 3.2.2 establishes …」+ §3.2 只有 example → reference。
负向：②真条头「Theorem 3.1.1 Consider two tests…」不降；
     ③序标后是符号「Example 2.7.7 +Poisson binomial…」不降（本书真实漏抽项，
        必须保持 readable 才能被回填）；
     ④「(Liapounov) Let…」括号起头不降；
     ⑤同节已有同类型条目（契约持 theorem 3.2.1）时同号谓语句**不降**；
     ⑥无类型词（has_label=False）不降；
     ⑦契约键形态读不出（中文两级 `定理3.2`）时按真条头处理（安全方向）。

跨书校准（51 书 / 3736 个条头形态文本块，只判形态①、不判，故为降级量**上界**）：
词表命中 216 处（5.78%），散布 25 书；抽样 12 条逐一看过**全是散文**（Weibel
"Theorem 8.5.1 states that"、Shafarevich "Theorem 1.14 shows one respect in
which…"、"Theorem 1.21 is proved."）。唯一形似真条头的是 Weibel
"Corollary 9.4.14 be = e-b for i < n…"（陈述以数学符号起头、被 OCR 折成小写字母），
它正是靠条件③（同节同类型已有条目在账）兜住的——所以③不可省。
"""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

sys.path.insert(0, os.path.join(_ROOT, "verify", "script"))
import check_structure_completeness as csc  # noqa: E402


def _node(type_, key):
    return SimpleNamespace(type=type_, key=key, name="", sub_sec=[])


def _tree(children):
    return SimpleNamespace(type="chapter", key="3", name="", sub_sec=children)


def _entry(label, canon, snippet, has_label=True):
    return {"label": label, "canon": list(canon), "snippet": snippet,
            "has_label": has_label, "key": "-".join(str(x) for x in canon)}


class TestLeadAfterOrdinal(unittest.TestCase):
    def test_word_lead(self):
        self.assertEqual(
            csc._lead_after_ordinal("Theorem 3.2.2 establishes consistency of",
                                    (3, 2, 2)), "establishes")

    def test_capital_lead_still_returned_but_not_lower(self):
        lead = csc._lead_after_ordinal("Theorem 3.1.1 Consider two tests of",
                                       (3, 1, 1))
        self.assertEqual(lead, "Consider")
        self.assertFalse(lead.islower())

    def test_symbol_lead_is_empty(self):
        self.assertEqual(
            csc._lead_after_ordinal("Example 2.7.7 +Poisson binomial trials",
                                    (2, 7, 7)), "")
        self.assertEqual(
            csc._lead_after_ordinal("Theorem 2.7.2 (Liapounov) Let the Xij",
                                    (2, 7, 2)), "")


class TestProsePredicate(unittest.TestCase):
    def test_prose_reference_downgraded(self):
        tree = _tree([_node("example", "3.2-1"), _node("example", "3.2-2")])
        e = _entry("Theorem", (3, 2, 2),
                   "Theorem 3.2.2 establishes consistency of the tests in")
        self.assertEqual(csc._prose_predicate_ref(e, tree, e["canon"]),
                         "establishes")

    def test_real_head_not_downgraded(self):
        tree = _tree([_node("theorem", "3.1-1")])
        e = _entry("Theorem", (3, 1, 1),
                   "Theorem 3.1.1 Consider two tests of H : 0 = 0o, one of them")
        self.assertIsNone(csc._prose_predicate_ref(e, tree, e["canon"]))

    def test_symbol_lead_head_not_downgraded(self):
        tree = _tree([_node("example", "2.7-6")])
        e = _entry("Example", (2, 7, 7),
                   "Example 2.7.7 +Poisson binomial trials with rare events. In")
        self.assertIsNone(csc._prose_predicate_ref(e, tree, e["canon"]))

    def test_same_label_in_section_wins(self):
        tree = _tree([_node("theorem", "3.2-1"), _node("theorem", "3.2-3")])
        e = _entry("Theorem", (3, 2, 2),
                   "Theorem 3.2.2 establishes consistency of the tests in")
        self.assertTrue(csc._same_label_item_in_section(tree, (3, 2, 2), "Theorem"))
        self.assertIsNone(csc._prose_predicate_ref(e, tree, e["canon"]))

    def test_unlabelled_candidate_untouched(self):
        tree = _tree([_node("example", "3.2-1")])
        e = _entry("Theorem", (3, 2, 2),
                   "3.2.2 establishes consistency of the tests in Examples",
                   has_label=False)
        self.assertIsNone(csc._prose_predicate_ref(e, tree, e["canon"]))

    def test_unreadable_contract_keys_are_conservative(self):
        # 中文两级键（`定理3.2`）解析不出点分数字 → 无证据可判 → 按真条头处理。
        tree = _tree([_node("theorem", "定理3.2"), _node("theorem", "定理3.4")])
        self.assertTrue(csc._same_label_item_in_section(tree, (3, 2), "定理"))
        e = _entry("定理", (3, 2), "定理3.2  establishes consistency of the")
        self.assertIsNone(csc._prose_predicate_ref(e, tree, e["canon"]))

    def test_two_level_key_form_is_read(self):
        # 键为「节-号」两段（dash）时同样能读出同节同号序列
        tree = _tree([_node("theorem", "3.2-1")])
        self.assertTrue(csc._same_label_item_in_section(tree, (3, 2, 2), "Theorem"))
        self.assertFalse(csc._same_label_item_in_section(
            _tree([_node("example", "3.2-1")]), (3, 2, 2), "Theorem"))


class TestWordListIsNarrow(unittest.TestCase):
    def test_statement_openers_are_absent(self):
        # 这些词能真正开一条陈述，收进词表就会把真条头判成散文（丢内容）。
        for w in ("if", "of", "in", "to", "we", "it", "this", "there", "let",
                  "suppose", "assume", "every", "under", "given", "for", "as"):
            self.assertNotIn(w, csc._PROSE_PREDICATE_WORDS, w)

    def test_reporting_verbs_are_present(self):
        for w in ("establishes", "shows", "implies", "proves", "gives",
                  "follows", "is", "are"):
            self.assertIn(w, csc._PROSE_PREDICATE_WORDS, w)


if __name__ == "__main__":
    unittest.main(verbosity=2)
