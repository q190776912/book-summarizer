"""Regression tests: 描述性条头不得被 B 层判为「缺号」（Gelfand–Manin 实测）。

背景：``_parse_entry`` 的 number-first 分支在余串里找到类型词后，要求类型词之后
必须是「条头边界」（``_after_label_boundary``）。印刷条头常是描述性短语：
  * 英文复数（**2.1-8 8. Remarks**）——``_ENTRY_LABELS`` 的交替式里单数在前
    （``Remark|Remarks``），"Remarks" 只匹配到 "Remark"，剩下的 's' 被当成词内
    延续 → 判为引用 → 真实条目被丢弃；
  * 英文专名延续（**2.1-4 4. Examples of Categories from Chapter I**）——类型词后
    直接跟拉丁单词，同样被边界检查丢弃；
  * 中文词干误命中（**1.4-7 7. 系数系统**、**1.4-9 9. 注记与例子**）——类型词后
    紧跟汉字被丢弃（其中 '系' 还会把「系数系统」读成 系/Porism）。
中文孪生条头（「8. 注记」）与英文孪生条头各自受害，所以同一本书两个语言版报的假
「缺号」数量还不一致（ch2 实测 EN 16 vs CN 6），且严格模式下全部 BLOCKING。

根治后行为（本文件锁定）：
  1. 复数类型词整词命中 → 条目在正确计数窗里出现。
  2. 类型词开头、后接专名 → 仍以该类型词入账（"Examples of Categories …"）。
  3. 类型词只是标题中间被引用的词或复合词的词干 → 归 uncat，仍是真实条目。
  4. 负向不变：引用/回指（"see the Remark below"、"定理 4.1 的应用"、"cf. Example 2"）、
     证明标题、类型词后紧跟另一串数字的路径仍不是条目。
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
sys.path.insert(0, _ROOT)
from lib.boot import setup  # noqa: E402
setup()

from verify.item_numbering_integrity.script.item_numbering_integrity import (  # noqa: E402
    _parse_entry)


class TestEnDescriptiveHeader(unittest.TestCase):
    def test_plural_label_matches_whole_word(self):
        self.assertEqual(_parse_entry("2.1-8 8. Remarks", 3, "en"), ([2, 1, 8], "Remarks"))
        self.assertEqual(_parse_entry("2.1-5 5. More Examples", 3, "en"), ([2, 1, 5], "Examples"))
        self.assertEqual(_parse_entry("2.1-1 1. Definition.", 3, "en"), ([2, 1, 1], "Definition"))

    def test_label_led_descriptive_name_still_uses_its_type_word(self):
        got = _parse_entry("2.1-4 4. Examples of Categories from Chapter I", 3, "en")
        self.assertEqual(got, ([2, 1, 4], "Examples"))
        got = _parse_entry("2.1-11 11. Examples from Chapter I", 3, "en")
        self.assertEqual(got, ([2, 1, 11], "Examples"))

    def test_type_word_quoted_mid_title_falls_back_to_uncat(self):
        got = _parse_entry("2.1-9 9. More Examples of Functors", 3, "en")
        self.assertIsNotNone(got, "a real item must not be dropped")
        self.assertEqual(got[0], [2, 1, 9])
        self.assertEqual(got[1], "uncat")

    def test_cjk_descriptive_headers_unchanged(self):
        self.assertEqual(_parse_entry("2.1-8 8. 注记", 3, "cn"), ([2, 1, 8], "注记"))
        self.assertEqual(_parse_entry("2.1-12 12. 若干定义", 3, "cn"), ([2, 1, 12], "定义"))
        # 专名在类型词之前（「黎斯引理」）仍按类型词入账 —— 旧行为不得回退。
        self.assertEqual(_parse_entry("2.5-4 4. 黎斯引理", 3, "cn"), ([2, 5, 4], "引理"))

    def test_han_type_word_stem_inside_a_compound_is_uncat_not_dropped(self):
        # Gelfand-Manin ch1 §1.4 CN: '系' is 系/Porism, but 系数系统 / 带系数系统 uses
        # it as a word stem; '注记与例子' runs straight on.  None of them may vanish
        # from the window (that was 假「缺号 7 / 9 / 10」).
        for inner, comps in (("1.4-7 7. 系数系统 (coefficient systems)", [1, 4, 7]),
                             ("1.4-9 9. 注记与例子", [1, 4, 9]),
                             ("1.4-10 10. 带系数系统的同调与上同调", [1, 4, 10])):
            got = _parse_entry(inner, 3, "cn")
            self.assertIsNotNone(got, f"{inner!r} must count as an item")
            self.assertEqual(got[0], comps)
            self.assertNotIn(got[1], ("系", "注记", "例子"),
                             "a compound stem must not become the item's label")

    def test_cjk_punct_delimited_label_keeps_its_type_word(self):
        got = _parse_entry("1.5-2 2. 定义。a) 拓扑空间 $Y$ 上的集合值预层 (presheaf)", 3, "cn")
        self.assertEqual(got, ([1, 5, 2], "定义"))

    def test_cited_type_word_with_number_inside_parens_is_uncat_not_dropped(self):
        # Vakil ch1 §1.2 EN: '1.2.18 Topological example (cf. Example 1.2.13; ...)'
        # — re.search hits the UPPERCASE 'Example' inside the citation, and the
        # old digit-after-label verdict dropped the whole header → false
        # 缺号 18.  The match does not head the tail, so the entry must survive
        # as uncat; genuine header-led refs ('定理 4.1 的应用') stay dropped.
        got = _parse_entry(
            "1.2.18 Topological example (cf. Example 1.2.13; for those who have seen cohomology).",
            3, "en")
        self.assertIsNotNone(got, "cited paren must not drop the real entry")
        self.assertEqual(got, ([1, 2, 18], "uncat"))
        got = _parse_entry("1.2.18 拓扑例子（cf. Example 1.2.13；看过上同调的人）", 3, "cn")
        self.assertIsNotNone(got, "CN twin must count too")
        self.assertEqual(got[0], [1, 2, 18])
        self.assertIsNone(_parse_entry("1.2.18 定理 4.1 的应用", 3, "cn"),
                          "header-led cross-ref must stay non-entry")

    def test_references_are_still_not_entries(self):
        for inner, lang in (("2.1-8 见定理 4.1", "cn"),
                            ("3.5-2 定理 4.1 的应用", "cn"),
                            ("5.2-3 see the Remark below", "en"),
                            ("5.2-3 cf. Example 2", "en"),
                            ("4.1-2 Proof of Theorem 3.8", "en"),
                            ("2.5-4 证明", "cn")):
            self.assertIsNone(_parse_entry(inner, 3, lang), f"{inner!r} must not be an entry")


class TestVakilProofTitleEntries(unittest.TestCase):
    """Vakil《Rising Sea》ch11/ch18 实测（FIX ⑤⑥⑦）：印刷书把「X 的证明」列为
    共享计数器条目（如 18.3.2 = 定理 18.1.3 的证明），三种条头形态都曾从 B 层
    窗里消失、制造整窗假缺号：
      ⑤ CN 译文证明词挪到条头开头：「**证明 11.2.7（定理 11.2.1：…）。**」
         被顶部 _PROOF_RE 守卫整条丢弃 → 11.2 窗缺 7/11/14；
      ⑥ 引用号在证明词前：「**18.3.2 定理 18.1.3 的证明。**」lv=3 时类型词
         居余串开头+数字随后 → 旧判据按交叉引用丢弃；
      ⑦ lv 回退复活引用：同一 span 在 lv=2 回退轮经 m3 归因搜索把引用号
         「定理 18.1」复活成幽灵条目 [18,1] → 幽灵窗「0:18 缺号 2..6」。
    负向不变：裸证明块头与「证明 定理 3.8 / Proof of Theorem 3.8」（类型词
    挡在自身号前）仍不是条目。"""

    def test_proof_led_cn_header_with_own_number_is_entry(self):
        # FIX ⑤：证明词 + 完整 levels 段自身号 → uncat 条目
        self.assertEqual(
            _parse_entry("证明 11.2.7（定理 11.2.1：维数与超越次数）。", 3, "cn"),
            ([11, 2, 7], "uncat"))
        self.assertEqual(
            _parse_entry("证明 11.2.11（定理 11.2.9）。", 3, "cn"),
            ([11, 2, 11], "uncat"))

    def test_cite_then_proof_tail_is_own_entry(self):
        # FIX ⑥：类型词居余串开头但标题以证明词收尾、引用号 ≠ 自身号
        self.assertEqual(
            _parse_entry("18.3.2 定理 18.1.3 的证明。", 3, "cn"),
            ([18, 3, 2], "uncat"))

    def test_shallow_fallback_must_not_resurrect_quoted_ref(self):
        # FIX ⑦：lv=2 回退轮不得把深号条头里的「定理 18.1」复活成 [18,1]
        self.assertIsNone(_parse_entry("18.3.2 定理 18.1.3 的证明。", 2, "cn"))
        self.assertIsNone(
            _parse_entry("18.9.3 Grothendieck 凝聚性定理 18.9.1 的证明。", 2, "cn"))

    def test_shallow_fallback_must_not_truncate_deeper_numpath(self):
        # FIX ⑧（ch25 幽灵窗）：lv=2 回退不得把「定理 25.2.2 的证明（续）」啃成
        # [25,2] 灌进章窗；字母习题位「25.2.A」同理不得截成 [25,2]。
        self.assertEqual(_parse_entry("定理 25.2.2。", 3, "cn"),
                         ([25, 2, 2], "定理"))
        self.assertIsNone(_parse_entry("定理 25.2.2 的证明（续）。", 2, "cn"))
        self.assertIsNone(_parse_entry("引理 25.3.4 的证明（完）。", 2, "cn"))
        self.assertIsNone(_parse_entry("练习 25.2.A（光滑蕴含平坦）。", 2, "cn"))

    def test_bare_proof_headers_stay_non_entries(self):
        for inner, levels, lang in (
                ("证明 定理 3.8", 3, "cn"),          # 类型词挡在号前
                ("Proof of Theorem 3.8", 3, "en"),
                ("证明.", 3, "cn"),
                ("11.2.7 的证明", 3, "cn"),           # 自指证明块
                ("1.2.3 定理 1.2.3 的证明。", 3, "cn"),  # 引用号 == 自身号
        ):
            self.assertIsNone(_parse_entry(inner, levels, lang),
                              f"{inner!r} must stay a proof block")


class TestVakilTitledByCitedItem(unittest.TestCase):
    """Vakil《Rising Sea》ch9/10/12/19/20/21/23/24/30 实测（FIX ②b/⑤b/⑨）：印刷书
    常以「被引用条目」为标题命名自己的共享计数器条目（证明梗概 / 提示 / 后续 / 应用 /
    多步证明的某步）。三种条头形态都曾在 B 层窗里消失、制造整窗假缺号：

      ⑨ 类型词居余串开头 + 紧跟编号：「9.1.5 定理 9.1.1 证明背后的想法」——旧判据
         一律按交叉引用丢弃。判据：编号构成完整 levels 段引用（或 levels-1 数字 +
         字母习题位）且 ≠ 自身号 → 真实 uncat 条目；裸浅号题名（「推论 1」）也算。
      ②b 证明词开头 + 引用有名字无编号的定理：「12.4.3 Proof of Bertini's Theorem,
         continued」——无引用号可比对，旧判据按裸证明块丢弃。
      ⑤b 证明词后跟括号引用 + 「步骤 N」自身号：「证明（Hodge 指标定理 20.2.11），
         步骤 20.2.12」/「Proof (of …), step 20.2.12」。

    负向锁死：浅号 + 描述文字的交叉引用（「定理 4.1 的应用」）、回指自身号
    （「定理 1.2.3 的证明。」）、裸「证明（定理 X）。」块仍不是条目。"""

    def test_full_citation_led_title_is_own_item(self):
        for inner, comps in (
                ("9.1.5 定理 9.1.1 证明背后的想法。", [9, 1, 5]),
                ("19.1.3 定理 19.1.1 归约为定理 19.1.2。", [19, 1, 3]),
                ("21.2.11 定理 21.2.9 的证明（相对余切正合列，仿射版本）。", [21, 2, 11]),
                ("30.4.7 定理 30.4.3 的应用。", [30, 4, 7]),
                ("12.7.3 定理 12.7.1（分离性的赋值判别法，DVR 版本）证明背后的想法。", [12, 7, 3]),
        ):
            got = _parse_entry(inner, 3, "cn")
            self.assertIsNotNone(got, f"{inner!r} must count as an item")
            self.assertEqual(got, (comps, "uncat"))

    def test_letter_exercise_slot_citation_is_own_item(self):
        # 提示 / 后续 / 改进：类型词后是 levels-1 数字 + 字母习题位（23.3.C）。
        self.assertEqual(_parse_entry("23.3.3 练习 23.3.C 的提示（构造复形的投射分解）。",
                                      3, "cn"), ([23, 3, 3], "uncat"))
        self.assertEqual(_parse_entry("24.5.4 练习 24.5.G 的后续。", 3, "cn"),
                         ([24, 5, 4], "uncat"))
        self.assertEqual(_parse_entry("24.5.11 练习 24.5.M 可以改进。", 3, "cn"),
                         ([24, 5, 11], "uncat"))

    def test_bare_shallow_title_is_own_item(self):
        # 「推论 1」——浅号且其后无描述 → 条目自名。
        self.assertEqual(_parse_entry("10.2.3 推论 1。", 3, "cn"), ([10, 2, 3], "uncat"))

    def test_named_proof_step_without_cited_number_is_item(self):
        # FIX ②b：Proof + 无编号定理名 + 「continued」。
        self.assertEqual(
            _parse_entry("12.4.3 Proof of Bertini's Theorem, continued.", 3, "en"),
            ([12, 4, 3], "uncat"))

    def test_proof_led_paren_citation_then_step_number_is_item(self):
        # FIX ⑤b：证明词 + 括号引用 + 「步骤 N」自身号（CN + EN 孪生）。
        self.assertEqual(
            _parse_entry("证明（Hodge 指标定理 20.2.11），步骤 20.2.12。", 3, "cn"),
            ([20, 2, 12], "uncat"))
        self.assertEqual(
            _parse_entry("Proof (of the Hodge Index Theorem 20.2.11), step 20.2.15.",
                         3, "en"),
            ([20, 2, 15], "uncat"))

    def test_shallow_citation_with_description_stays_reference(self):
        # 负向：浅号（2 段 < levels=3）+ 描述文字 = 交叉引用，仍不是条目。
        self.assertIsNone(_parse_entry("1.2.18 定理 4.1 的应用", 3, "cn"))
        self.assertIsNone(_parse_entry("3.5-2 定理 4.1 的应用", 3, "cn"))
        # 回指自身号 → 证明块。
        self.assertIsNone(_parse_entry("1.2.3 定理 1.2.3 的证明。", 3, "cn"))
        # Proof + 浅号引用（3.8）→ 证明块，非条目。
        self.assertIsNone(_parse_entry("4.1-2 Proof of Theorem 3.8", 3, "en"))
        # 裸「证明（定理 X）。」无自身号 → 证明块。
        self.assertIsNone(_parse_entry("证明（定理 20.2.11）。", 3, "cn"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
