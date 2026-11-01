"""Tests for lib/section_titles.py — 章级闸 ⑰「节标题折行截短 / 词间空格丢失」。

Run:  python lib/tests/test_section_titles.py

负向用例锁的是 Rosen《离散数学》8e 实测缺陷（全书 623 节点里 34 个中招，此前所有闸门
全绿）：原书节题排两行时抽取器只取第一行 → 契约 name 残缺（`6.1 The Basics of`），
顺着拆分灌进单元 H2、首行 name=、manifest 与最终 md 文件名。两种半修形态都要拦：
(a) 写手只补了单元 H2、契约照旧残缺（SSOT 与成品分叉，重拆即回退）；
(b) 契约/单元双双残缺（成品直接是残题，如 `8.5 Inclusion-`）。
正向用例锁零假阳：单个词的合法节题、并列同义词、粘连页码残渣、撇号异形、
译文标题（CJK 虚词结尾合法，「……是如何陈述的」）。

第二类缺陷（2026-09-28 Shafarevich《Basic Algebraic Geometry 1》实测）= OCR 把印刷
词间空格吞掉：契约 §3.1 name=`IrreducibleAlgebraicSubsets`（`page_051.json` 该标题块
text 本身就是 `'3.1IrreducibleAlgebraicSubsets'`），写手按印面写的 H2 带空格，而
`norm_title` 比较前剥全部空白 → 两侧判等、门控放行，契约成了唯一带病的 SSOT。
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

from section_titles import (clean_title, dangling_reason, fold_typeset_markup,  # noqa: E402
                            glued_reason, norm_title, title_problems)


def _contract(pairs):
    """[(key, name)] -> 形如分章契约的嵌套 dict。"""
    return {"key": "6", "type": "chapter", "name": "6 Counting",
            "sub_sec": [{"key": k, "type": "section", "name": n,
                         "sub_sec": []} for k, n in pairs]}


def _units(rows):
    return [{"type": "section", "key": k, "file": "%s.md" % k, "name": k + " " + t}
            for k, t in rows]


def _read(bodies):
    return lambda u: bodies[u["file"]]


class TestDangling(unittest.TestCase):
    def test_dangling_preposition(self):
        self.assertTrue(dangling_reason("## §1.2 Applications of", "1.2"))

    def test_trailing_hyphen(self):
        self.assertTrue(dangling_reason("## §8.5 Inclusion-", "8.5"))
        self.assertTrue(dangling_reason("## §10.2 Graph Termi-", "10.2"))

    def test_legit_single_word_title(self):
        for t in ("## §2.1 Sets", "## §3.1 Algorithms", "## §10.4 Connectivity",
                  "## §4.6 Cryptography", "### §6.3.3 Combinations"):
            self.assertIsNone(dangling_reason(t, "x"), t)

    def test_hyphenated_compound_not_dangling(self):
        # 末词整体是连字符复合词（含 and 词素）——整词比较才不会被误杀
        self.assertIsNone(
            dangling_reason("## §8.3 Divide-and-Conquer Algorithms and Recurrence "
                            "Relations", "8.3"))
        self.assertIsNone(dangling_reason("## §10.6 Shortest-Path Problems", "10.6"))

    def test_clean_title_strips_glued_page_number(self):
        self.assertEqual(clean_title("## §2 Phase Flows 57", "2"), "Phase Flows")
        self.assertEqual(norm_title("Phase Flows 57", ""), norm_title("Phase Flows", ""))

    def test_title_ending_in_single_digit_not_page_glue(self):
        """Vakil 3e §19.8 实测假阳：'Curves of genus 4 and 5' 是真节题，
        「 5」不是粘连页码——带空格的剥除只认两位数以上，否则剥出假 and 悬空。"""
        self.assertEqual(clean_title("## §19.8 Curves of genus 4 and 5", "19.8"),
                         "Curves of genus 4 and 5")
        self.assertIsNone(
            dangling_reason("## §19.8 Curves of genus 4 and 5", "19.8"))
        for t in ("## §19.5 Curves of genus 0", "## §19.7 Curves of genus 3"):
            self.assertIsNone(dangling_reason(t, "19.x"), t)
        # 两位数尾数仍按页码残渣剥（正文页码 ≥10 恒两位数起）
        self.assertEqual(clean_title("## §19.8 Curves of genus 4 and 157", "19.8"),
                         "Curves of genus 4 and")


class TestContractUnitReconciliation(unittest.TestCase):
    def test_contract_truncated_unit_complete_fails(self):
        """Rosen ch6 §6.1 实测形态：契约残缺、写手已把单元 H2 补全。"""
        c = _contract([("6.1", "6.1 The Basics of")])
        u = _units([("6.1", "The Basics of Counting")])
        probs = title_problems(c, u, _read({"6.1.md": "## §6.1 The Basics of Counting\n\n正文"}))
        self.assertEqual(len(probs), 1, probs)
        # 契约侧悬空 → 报「SSOT 残缺」（比泛化的「前缀」更准），须回填契约而非削短单元
        self.assertIn("契约", probs[0])
        self.assertIn("SSOT", probs[0])

    def test_both_truncated_fails(self):
        """Rosen ch8 §8.5 实测形态：契约与单元双双残题。"""
        c = _contract([("8.5", "8.5 Inclusion-")])
        probs = title_problems(c, _units([("8.5", "Inclusion-")]),
                               _read({"8.5.md": "## §8.5 Inclusion-\n\n正文"}))
        self.assertTrue(any("折行截短" in p for p in probs), probs)

    def test_aligned_passes(self):
        c = _contract([("6.1", "6.1 The Basics of Counting")])
        probs = title_problems(c, _units([("6.1", "The Basics of Counting")]),
                               _read({"6.1.md": "## §6.1 The Basics of Counting\n\n正文"}))
        self.assertEqual(probs, [])

    def test_apostrophe_variant_passes(self):
        """ch7 §7.3.2：契约弯引号 / 单元直引号，同一标题的异形不算分叉。"""
        c = _contract([("7.3.2", "7.3.2 Bayes’ Theorem")])
        probs = title_problems(c, _units([("7.3.2", "Bayes' Theorem")]),
                               _read({"7.3.2.md": "### §7.3.2 Bayes' Theorem\n\n正文"}))
        self.assertEqual(probs, [])

    def test_dash_variant_passes(self):
        """Shafarevich 代数几何 1 ch3 §7 实测假阳：印面排 en dash，契约侧被抽成半角。

        写手照印面写 `Riemann–Roch` 是正确做法，dash 族异形不得算分叉。
        """
        c = _contract([("7", "7 The Riemann-Roch Theorem on Curves"),
                       ("7.2", "7.2 Preliminary Form of the Riemann-Roch Theorem")])
        units = _units([("7", "The Riemann–Roch Theorem on Curves"),
                        ("7.2", "Preliminary Form of the Riemann–Roch Theorem")])
        bodies = {"7.md": "## §7 The Riemann–Roch Theorem on Curves\n\n正文",
                  "7.2.md": "## §7.2 Preliminary Form of the Riemann–Roch Theorem\n\n正文"}
        self.assertEqual(title_problems(c, units, _read(bodies)), [])
        # Minus sign U+2212（数学体排版常见）与 em dash 同样折
        self.assertEqual(norm_title("Grothendieck−group", ""),
                         norm_title("Grothendieck-group", ""))

    def test_dash_fold_does_not_mask_real_difference(self):
        """负向：折 dash 只吞连接符异形，真缺词/改写仍须报。"""
        c = _contract([("7.2", "7.2 Preliminary Form of the Riemann-Roch Theorem")])
        probs = title_problems(
            c, _units([("7.2", "Form of the Riemann–Roch Theorem")]),
            _read({"7.2.md": "## §7.2 Form of the Riemann–Roch Theorem\n\n正文"}))
        self.assertTrue(any("不一致" in p for p in probs), probs)

    def test_glued_words_now_reported(self):
        """Rosen ch1 §1.4.8 实测：契约粘连成 LogicalEquivalencesInvolvingQuantifiers。

        旧断言是 `probs == []`（比对剥空白 → 判等放行），那正是本模块的**盲区**：
        写手按印面写对、契约带病，重拆即回退成粘连题。自 ⑰ 补 glued 判据后必须报。
        """
        c = _contract([("1.4.8", "1.4.8 LogicalEquivalencesInvolvingQuantifiers")])
        probs = title_problems(
            c, _units([("1.4.8", "Logical Equivalences Involving Quantifiers")]),
            _read({"1.4.8.md": "### §1.4.8 Logical Equivalences Involving Quantifiers\n\n正文"}))
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("词间空格丢失", probs[0])
        # 归一形仍相等（前缀/缺词类判据不得被粘连误伤）
        self.assertEqual(norm_title("1.4.8 LogicalEquivalencesInvolvingQuantifiers", "1.4.8"),
                         norm_title("### §1.4.8 Logical Equivalences Involving Quantifiers", "1.4.8"))

    def test_unit_shorter_than_contract_fails(self):
        c = _contract([("9.1", "9.1 Relations and Their Properties")])
        probs = title_problems(c, _units([("9.1", "Relations and")]),
                               _read({"9.1.md": "## §9.1 Relations and\n\n正文"}))
        self.assertTrue(any("缺词" in p or "折行截短" in p for p in probs), probs)

    def test_translation_dir_skips_name_comparison(self):
        """units-translate：H2 是中文译文，只查悬空，绝不与英文契约名对账。"""
        c = _contract([("2.4", "2.4 Sequences and Summations")])
        bodies = {"2.4.md": "## §2.4 序列与求和\n\n正文",
                  "1.7.3.md": "### §1.7.3 理解定理是如何陈述的\n\n正文"}
        u = _units([("2.4", "序列与求和")])
        u.append({"type": "section", "key": "1.7.3", "file": "1.7.3.md", "name": "1.7.3"})
        probs = title_problems(c, u, _read(bodies), compare_names=False)
        self.assertEqual(probs, [])

    def test_no_contract_only_dangling(self):
        probs = title_problems(None, _units([("1.1", "Introduction to")]),
                               _read({"1.1.md": "## §1.1 Introduction to\n\n正文"}))
        self.assertEqual(len(probs), 1, probs)

    def test_unit_without_heading_is_skipped(self):
        c = _contract([("6.1", "6.1 The Basics of")])
        probs = title_problems(c, _units([("6.1", "The Basics of Counting")]),
                               _read({"6.1.md": "没有标题行的正文"}))
        self.assertEqual(probs, [])


class TestTrailingDigitShields(unittest.TestCase):
    r"""⑰ 相等腿的第二通道：**尾部数字被数学模式遮蔽的不对称**不算分叉。

    实测（Fraleigh《AFCAA》6 站，2026-10-31）：账目面按 `tools/fix_section_name.py` 的硬规
    禁含 `$`/`\`，印面 `Order of (8,4,10) in $\mathbb{Z}_{12} \times \mathbb{Z}_{60} \times
    \mathbb{Z}_{24}$` 只能写成裸文本 `… Z12 × Z60 × Z24`。`clean_title` 的 `_TRAIL_PAGE`
    在比对之前运行：裸文本侧收尾是数字 ⇒ 剥掉；`$` 侧收尾是 `$` ⇒ 剥不到。于是
    `…z12×z60×z` 是 `…z12×z60×z24` 的前缀 → 闸永远判「契约 name 截短」，**回填契约也修不好**。

    第二通道只在「两侧保住尾数后**逐位相等**」时判同形 ⇒ 数字真不同（`Z12`/`Z24`、
    `360`/`361`）仍报，`_TRAIL_PAGE` 与展示形 `clean_title` 一字节不动。
    """

    def _site(self, cname, h2):
        c = _contract([("9.10", cname)])
        u = [{"type": "section", "key": "9.10", "file": "9.10.md", "name": cname}]
        return c, u, (lambda _u: h2 + "\n\n正文")

    def test_blackboard_bold_trailing_subscript_passes(self):
        c, u, read = self._site(
            "9.10 Example — Order of (8, 4, 10) in Z12 × Z60 × Z24",
            "## §9.10 Example — Order of $(8, 4, 10)$ in $\\mathbb{Z}_{12} "
            "\\times \\mathbb{Z}_{60} \\times \\mathbb{Z}_{24}$")
        self.assertEqual(title_problems(c, u, read), [])

    def test_space_separated_trailing_number_passes(self):
        """`… Order $360$` vs 裸文本 `… Order 360`：带空格那档同样只遮蔽不对称。"""
        c, u, read = self._site("9.13 Example — Abelian Groups of Order 360",
                                "## §9.13 Example — Abelian Groups of Order $360$")
        self.assertEqual(title_problems(c, u, read), [])

    def test_second_channel_is_what_clears_it(self):
        """控件：常规形必须**仍然不同形**（否则这条通道没在本案上起作用）。"""
        cname = "9.10 Example — Order of (8, 4, 10) in Z12 × Z60 × Z24"
        h2 = ("## §9.10 Example — Order of $(8, 4, 10)$ in $\\mathbb{Z}_{12} "
              "\\times \\mathbb{Z}_{60} \\times \\mathbb{Z}_{24}$")
        self.assertNotEqual(norm_title(cname, "9.10"), norm_title(h2, "9.10"))
        self.assertEqual(norm_title(cname, "9.10", True), norm_title(h2, "9.10", True))

    def test_different_trailing_digits_still_fail(self):
        c, u, read = self._site(
            "9.10 Example — Order of (8, 4, 10) in Z12 × Z60 × Z12",
            "## §9.10 Example — Order of $(8, 4, 10)$ in $\\mathbb{Z}_{12} "
            "\\times \\mathbb{Z}_{60} \\times \\mathbb{Z}_{24}$")
        probs = title_problems(c, u, read)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("不一致", probs[0])

    def test_wrong_trailing_number_with_space_still_fails(self):
        c, u, read = self._site("9.13 Example — Abelian Groups of Order 360",
                                "## §9.13 Example — Abelian Groups of Order $361$")
        self.assertEqual(len(title_problems(c, u, read)), 1)

    def test_real_truncation_still_caught_by_dangling(self):
        """第二通道不许吞掉折行截短：末词是虚词时由 `dangling_reason` 先报（与尾数无关）。"""
        c = _contract([("6.1", "6.1 The Basics of")])
        probs = title_problems(c, _units([("6.1", "The Basics of")]),
                               _read({"6.1.md": "## §6.1 The Basics of Counting\n\n正文"}))
        self.assertTrue(probs, probs)

    def test_display_form_is_untouched(self):
        """`clean_title` 默认照剥尾数：展示面（manifest/marker/文案）不因本参数改一个字。"""
        self.assertEqual(clean_title("## §2 Phase Flows 57", "2"), "Phase Flows")
        self.assertEqual(clean_title("## §9.10 In Z12 × Z60 × Z24", "9.10"),
                         "In Z12 × Z60 × Z")     # 现状形态，锁住「展示面不变」这一承诺


class TestHyphenTailArtifact(unittest.TestCase):
    r"""悬空腿的连字符档：`_TRAIL_PAGE` 吃掉「负号+数字」造出的**假**折行残体不算截短。

    与相等腿同源的另一刀（2026-10-31 Fraleigh《AFCAA》§3.12 实测）：印面
    `Example: Find all solutions of $z^4 = -16$`，账目面按工具硬规只能写裸文本
    `… z^4 = -16` ⇒ 粘连档剥掉 `16`，展示形**凭空**收在负号上 → ⑰ 报「以连字符收尾
    （印刷折行标题的续行被丢弃）」。单元 H2 收尾是 `$` ⇒ 剥不到 ⇒ 只有契约侧挨刀。
    跨架标定（776 章）：豁免只放行这一条，`NEWFAIL 0 / DISPLAY 0`，控件两侧同码全 0
    （`_p861_hyphen_guard*.json`）。
    """

    def test_minus_digits_tail_is_not_dangling(self):
        self.assertIsNone(dangling_reason("3.12 Example: Find all solutions of z^4 = -16",
                                          "3.12"))
        self.assertIsNone(dangling_reason("## §3.12 Example: Find all solutions of "
                                          "$z^4 = -16$", "3.12"))

    def test_real_hyphen_wrap_still_reported(self):
        """负向：真折行残体（连字符后面**没有数字**）照报，豁免不碰这一支。"""
        self.assertEqual(dangling_reason("8.5 Inclusion-", "8.5"),
                         "以连字符收尾（印刷折行标题的续行被丢弃）")
        self.assertEqual(dangling_reason("## §8.5 Inclusion-", "8.5"),
                         "以连字符收尾（印刷折行标题的续行被丢弃）")

    def test_dangling_word_after_page_strip_still_reported(self):
        """负向：虚词档**不豁免**——`Applications of 57` 剥掉页码后露出的 `of` 仍须报。"""
        self.assertEqual(dangling_reason("6.1 Applications of 57", "6.1"),
                         "以英文虚词「of」收尾（印刷折行标题的续行被丢弃）")

    def test_title_problems_clears_the_fraleigh_shape(self):
        c = _contract([("3.12", "3.12 Example: Find all solutions of z^4 = -16")])
        probs = title_problems(
            c, _units([("3.12", "Example: Find all solutions of $z^4 = -16$")]),
            _read({"3.12.md": "## §3.12 Example: Find all solutions of $z^4 = -16$\n\n正文"}))
        self.assertEqual(probs, [], probs)

    def test_guard_is_what_clears_it(self):
        """控件：让 `clean_title` 无视 `keep_trailing_digits` ⇒ 假报必须**逐字复现**。"""
        import section_titles as st
        saved = st.clean_title
        try:
            st.clean_title = lambda text, key="", keep_trailing_digits=False: saved(
                text, key, False)
            self.assertEqual(st.dangling_reason("3.12 Example: Find all solutions of "
                                                "z^4 = -16", "3.12"),
                             "以连字符收尾（印刷折行标题的续行被丢弃）")
        finally:
            st.clean_title = saved
        self.assertIsNone(dangling_reason("3.12 Example: Find all solutions of z^4 = -16",
                                          "3.12"))

    def test_real_truncated_contract_still_reported_through_gate(self):
        """负向：契约真把印面题少写了一段（负号收尾但**单元侧更长**）仍须报出来。"""
        c = _contract([("3.12", "3.12 Example: Find all solutions of z^4 =")])
        probs = title_problems(
            c, _units([("3.12", "Example: Find all solutions of $z^4 = -16$")]),
            _read({"3.12.md": "## §3.12 Example: Find all solutions of $z^4 = -16$\n\n正文"}))
        self.assertEqual(len(probs), 1, probs)


class TestGluedWords(unittest.TestCase):
    """OCR 吞词间空格：`norm_title` 剥空白看不见，必须由 ⑰ 独立判。"""

    def test_glued_contract_name_reported_despite_equal_compare(self):
        """Shafarevich ch1 §3.1 实测形态：契约粘连、单元按印面带空格。"""
        c = _contract([("3.1", "3.1 IrreducibleAlgebraicSubsets")])
        probs = title_problems(
            c, _units([("3.1", "Irreducible Algebraic Subsets")]),
            _read({"3.1.md": "## §3.1 Irreducible Algebraic Subsets\n\n正文"}))
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("词间空格丢失", probs[0])
        self.assertIn("SSOT", probs[0])

    def test_glued_unit_title_with_clean_contract_reported(self):
        c = _contract([("5.4", "5.4 Noether Normalisation")])
        probs = title_problems(
            c, _units([("5.4", "NoetherNormalisation")]),
            _read({"5.4.md": "## §5.4 NoetherNormalisation\n\n正文"}))
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("补回空格", probs[0])

    def test_translation_dir_never_judged(self):
        """units-translate 的 H2 是中文译文，粘连判据整条跳过。"""
        c = _contract([("3.1", "3.1 IrreducibleAlgebraicSubsets")])
        probs = title_problems(c, _units([("3.1", "不可约代数子集")]),
                               _read({"3.1.md": "## §3.1 不可约代数子集\n\n正文"}),
                               compare_names=False)
        self.assertEqual(probs, [])

    def test_multiword_names_are_not_judged(self):
        """负向（保守边界）：含空格的形态不判——那是「整句被当节名」另一类，噪声大。"""
        self.assertIsNone(glued_reason(
            "ExampleLet G=GL（n,R)andXthesetofall columnvectors"))
        self.assertIsNone(glued_reason("Rosen DiscreteMath"))

    def test_single_word_and_short_names_pass(self):
        """负向：合法单词节题 / 短缩写不可能有驼峰接缝，长度 <8 亦不判。"""
        for t in ("Sets", "Connectivity", "Theorem", "OpenSSL", "SL2R", "p-adic"):
            self.assertIsNone(glued_reason(t, "x"), t)
        # 阈值 ≥8：`AppendixA`（9 字）确实该判——印面是 "Appendix A"
        self.assertTrue(glued_reason("AppendixA"))
        self.assertIsNone(glued_reason("Fig1a"))

    def test_cjk_names_pass(self):
        self.assertIsNone(glued_reason("序列与求和", "2.4"))
        self.assertIsNone(glued_reason("离散数学及其应用", ""))


class TestTypesetFold(unittest.TestCase):
    r"""契约 name（页 OCR 裸字符）↔ 单元 H2（印面 KaTeX）异形不算分叉。

    2026-09-28 Apostol《Introduction to Analytic Number Theory》ch2 实测 6 处假报：
    契约 `The Mobius function μ(n)` 而写手**按印面**写 `The Möbius function $\mu(n)$`
    ——写数学模式是写作要求，旧 `norm_title` 却判「两侧互非前缀（其中一侧被 OCR 改写）」
    并索要「统一五处」，等于逼写手把正确写法降级去迁就 OCR 残骸。
    """

    def test_mu_markup_matches_bare_greek(self):
        self.assertEqual(norm_title("The Möbius function $\\mu(n)$", ""),
                         norm_title("The Mobius function μ(n)", ""))

    def test_varphi_macro_case_fold(self):
        # OCR 把印面 φ 读成大写 Φ：字母码位大小写经 .lower() 归一
        self.assertEqual(norm_title("A relation connecting $\\varphi$ and $\\mu$", ""),
                         norm_title("A relation connecting Φ and μ", ""))

    def test_text_macro_and_braces_fold(self):
        self.assertEqual(norm_title("$\\operatorname{Li}(x)$ theorem", ""),
                         norm_title("Li(x) theorem", ""))

    def test_font_family_macros_fold_to_bare_glyphs(self):
        r"""字体族宏只改字形，账目面必须能用裸字符表达（Fraleigh《AFCAA》实测 133 站）。

        `tools/fix_section_name.py` 的 `--name` 硬禁 `$` 与反斜杠（账目面存印刷裸文本），
        而旧白名单缺 `\mathbb` 一族 → H2 的 `$\mathbb{Z}$` 折成 `mathbbz`、账目面的 `Z`
        折成 `z`，两侧**永不同形**：工具自己承诺的裸文本形写不进去，133 个含黑板粗体的
        节题全部卡死（既不能改判据也不能改正文）。
        """
        self.assertEqual(norm_title("Example: $\\mathbb{Z}$ and $2\\mathbb{Z}$ are isomorphic", ""),
                         norm_title("Example: Z and 2Z are isomorphic", ""))
        self.assertEqual(norm_title("Subgroups of $\\mathbb{Z}$", ""),
                         norm_title("Subgroups of Z", ""))
        for macro in ("mathbb", "mathcal", "mathfrak", "mathscr", "boldsymbol",
                      "textbf", "texttt", "mathinner"):
            self.assertEqual(norm_title("The group $\\%s{G}$" % macro, ""),
                             norm_title("The group G", ""), macro)

    def test_nested_font_macros_fold_to_fixpoint(self):
        r"""嵌套字体宏须剥到不动点（`\mathbb{\mathcal{X}}` 一层正则只剥外面）。"""
        self.assertEqual(norm_title("$\\mathbb{\\mathcal{X}}$-spaces", ""),
                         norm_title("X-spaces", ""))

    def test_font_fold_keeps_letter_content_distinct(self):
        r"""负向：剥的是**外壳**不是内容——Z 与 Q、Z 与 W 不得折成同一形。"""
        self.assertNotEqual(norm_title("$\\mathbb{Z}$ and $\\mathbb{Q}$", ""),
                            norm_title("$\\mathbb{Z}$ and $\\mathbb{Z}$", ""))
        self.assertNotEqual(norm_title("Subgroups of $\\mathbb{Z}$", ""),
                            norm_title("Subgroups of W", ""))
        self.assertNotEqual(norm_title("$\\mathbb{Q}^{+}$", ""), norm_title("$\\mathbb{Q}^{-}$", ""))

    def test_font_fold_is_what_makes_the_pair_agree(self):
        r"""mutation control：把字体剥壳关掉必须**复现**旧的不同形。

        没有这条控件，「两侧同形」可能来自别处（如 `_TEX_MACRO_RE` 丢反斜杠的顺带效果），
        日后有人改回归因就查不动了。
        """
        import re
        import section_titles as st
        lhs, rhs = r"Example: $\mathbb{Z}$ and $2\mathbb{Z}$", "Example: Z and 2Z"
        self.assertEqual(norm_title(lhs, ""), norm_title(rhs, ""))
        original = st._FONT_ARG_RE
        try:
            st._FONT_ARG_RE = re.compile(r"(?!)")             # 永不匹配 == 剥壳关闭
            self.assertNotEqual(norm_title(lhs, ""), norm_title(rhs, ""),
                                "剥壳已生效？那这条等式不该成立，判据归因有误")
        finally:
            st._FONT_ARG_RE = original

    def test_gate_passes_on_blackboard_bold_unit_title(self):
        r"""门控级正例：契约写账目面裸文本、单元按印面写 KaTeX，须放行（Fraleigh 形态）。"""
        c = _contract([("2.23", "2.23 Example: Z and 2Z Are Isomorphic")])
        units = _units([("2.23", "Example: $\\mathbb{Z}$ and $2\\mathbb{Z}$ Are Isomorphic")])
        bodies = {"2.23.md": "## §2.23 Example: $\\mathbb{Z}$ and $2\\mathbb{Z}$ Are Isomorphic\n\n正文"}
        self.assertEqual(title_problems(c, units, _read(bodies)), [])

    def test_gate_passes_on_typeset_unit_title(self):
        c = _contract([("2.2", "2.2 The Mobius function μ(n)"),
                       ("2.8", "2.8 The Mangoldt function Λ(n)")])
        units = _units([("2.2", "The Möbius function $\\mu(n)$"),
                        ("2.8", "The Mangoldt function $\\Lambda(n)$")])
        bodies = {"2.2.md": "## §2.2 The Möbius function $\\mu(n)$\n\n正文",
                  "2.8.md": "## §2.8 The Mangoldt function $\\Lambda(n)$\n\n正文"}
        self.assertEqual(title_problems(c, units, _read(bodies)), [])

    def test_fold_does_not_mask_real_ocr_misread(self):
        """负向：φ(n) 被 OCR 读成 `p(n)` 是真残缺，折形后仍须报。"""
        c = _contract([("2.3", "2.3 The Euler totient function p(n)")])
        probs = title_problems(
            c, _units([("2.3", "The Euler totient function $\\varphi(n)$")]),
            _read({"2.3.md": "## §2.3 The Euler totient function $\\varphi(n)$\n\n正文"}))
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("不一致", probs[0])

    def test_fold_does_not_mask_truncation(self):
        """负向：折形只吞排版异形，折行截短（契约残题）仍按前缀关系报出。"""
        c = _contract([("2.7", "2.7 Dirichlet inverses and the Mobius")])
        probs = title_problems(
            c, _units([("2.7", "Dirichlet inverses and the Möbius function")]),
            _read({"2.7.md": "## §2.7 Dirichlet inverses and the Möbius function\n\n正文"}))
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("契约侧截短", probs[0])

    def test_symbol_macro_and_scripts_fold(self):
        r"""`\mid`、`\zeta`、`\sigma_a` vs `\sigma_{a}`、`x^2` vs `x2` 全部同形。"""
        self.assertEqual(norm_title("Evaluation of $(-1\\mid p)$ and $(2\\mid p)$", ""),
                         norm_title("Evaluation of (-1|p) and (2|p)", ""))
        self.assertEqual(norm_title("Zero-free regions for $\\zeta(s)$", ""),
                         norm_title("Zero-free regions for ζ(s)", ""))
        self.assertEqual(norm_title("contour integral for $\\psi_{1}(x)/x^{2}$", ""),
                         norm_title("contour integral for ψ_1(x)/x2", ""))
        self.assertEqual(norm_title("primitive roots mod $2^\\alpha$ for $\\alpha \\ge 3$", ""),
                         norm_title("primitive roots mod 2α for α ≥ 3", ""))
        self.assertEqual(norm_title("Chebyshev's functions $\\psi(x)$ and $\\vartheta(x)$", ""),
                         norm_title("Chebyshev's functions ψ(x) and ϑ(x)", ""))

    def test_symbol_fold_keeps_real_differences(self):
        """负向：折形不得把 ζ 与 θ、ψ 与 φ 折成同一个字母。"""
        self.assertNotEqual(norm_title("Zero-free regions for $\\zeta(s)$", ""),
                            norm_title("Zero-free regions for $\\theta(s)$", ""))
        self.assertNotEqual(norm_title("The average order of $\\varphi(n)$", ""),
                            norm_title("The average order of $\\psi(n)$", ""))

    def test_prime_macro_folds_to_apostrophe(self):
        r"""Apostol《IANT》ch13 §13.4/§13.6 实测：写手按印面写 `$\zeta ^ { \prime } ( s )$`，
        契约/OCR 侧给 `ζ'(s)`（或 U+2032 的 `ζ′(s)`）。`\prime` 不在符号表里时宏名退化成
        裸词 `prime` → 两侧永不同形 → `fix_section_name` 只能 REFUSE，闸把正确写法判死。"""
        for lhs in (r"Upper bounds for $| \zeta ( s ) |$ and $| \zeta ^ { \prime } ( s ) |$",
                    r"Upper bounds for $|\zeta(s)|$ and $|\zeta'(s)|$",
                    "Upper bounds for |ζ(s)| and |ζ′(s)|"):
            self.assertEqual(norm_title(lhs, ""),
                             norm_title("Upper bounds for |ζ(s)| and |ζ'(s)|", ""), lhs)

    def test_prime_fold_keeps_real_differences(self):
        r"""负向：`\prime`（一阶导）不得与裸 `p`、也不得与 `\P`/双撇号折成同一形。"""
        self.assertNotEqual(norm_title("Inequalities for $\\zeta^{\\prime}(s)$", ""),
                            norm_title("Inequalities for $\\zeta(s)$", ""))
        self.assertNotEqual(norm_title("Bounds for $f^{\\prime\\prime}(x)$", ""),
                            norm_title("Bounds for $f^{\\prime}(x)$", ""))


    # ── 无花括号的字体宏 + `\colon`（Fraleigh《AFCAA》实测三处已把 `mathbb` 写进入档名）──
    #
    # 期望值里 `→`/`:` 后**带一个空格**是折叠函数的真实行为，不是笔误：`_TEX_MACRO_RE` 只吃掉
    # `\` + 宏名，宏名后那个「命令分隔空格」留在原地。这不影响判据——`norm_title` 走
    # `"".join(t.split())` 把**所有**空白删掉，所以账目面写 `M_{m×n}` 还是 `M_{m × n}` 同形；
    # 这里钉的是折叠输出本身，供 `account_name` 一类派生通道对照。
    def test_unbraced_font_macro_folds_to_glyph(self):
        self.assertEqual(fold_typeset_markup("$\\mathbb R\\to U$"), "R→ U")
        self.assertEqual(fold_typeset_markup("$\\mathbb Z_n\\to D_n$"), "Zn→ Dn")
        self.assertEqual(fold_typeset_markup("$\\mathbb Z_n\\to D_n$", keep_scripts=True),
                         "Z_n→ D_n")
        self.assertEqual(fold_typeset_markup("$\\mathbf x$"), "x")

    def test_unbraced_fold_is_what_clears_the_pair(self):
        """控件：把无花括号档关掉必须退回裸词 `mathbb`（差异只来自这一条）。"""
        import re
        import section_titles as st
        text = "$\\mathbb R\\to U$"
        saved = st._FONT_BARE_RE
        try:
            st._FONT_BARE_RE = re.compile(r"(?!)")            # 关掉本条
            self.assertEqual(fold_typeset_markup(text), "mathbb R→ U")
        finally:
            st._FONT_BARE_RE = saved
        self.assertEqual(fold_typeset_markup(text), "R→ U")

    def test_unbraced_fold_does_not_swallow_relation_macros(self):
        r"""负向：`\in`/`\to`/`\mid` 不在字体白名单，不许被「宏名+空格+字母」规则吃掉。"""
        self.assertEqual(fold_typeset_markup("$f \\in \\mathbb{Z}$"), "f ∈ Z")
        self.assertEqual(fold_typeset_markup("$A \\mid B$"), "A | B")
        self.assertNotEqual(fold_typeset_markup("$\\mathbb Z$"),
                            fold_typeset_markup("$\\mathbb Q$"))

    def test_colon_macro_folds_not_the_word_colon(self):
        self.assertEqual(fold_typeset_markup("$\\phi \\colon \\mathbb{Z} \\to R$"),
                         "φ : Z → R")
        self.assertEqual(norm_title(r"31.17 The map $\phi \colon \mathbb{Z} \to R$", "31.17"),
                         norm_title("31.17 The map φ : Z → R", "31.17"))
        self.assertNotEqual(norm_title(r"$\phi \colon \mathbb{Z}$", ""),
                            norm_title(r"$\phi \langle \mathbb{Z}$", ""))

    def test_keep_scripts_only_changes_the_derived_name_face(self):
        """账目面派生形（`keep_scripts=True`）保住下标结构，比对形照旧剥掉。"""
        h2 = "2.11 Example: Matrices $M_{m \\times n}(\\mathbb{R})$ Under Addition"
        self.assertEqual(fold_typeset_markup(h2, keep_scripts=True),
                         "2.11 Example: Matrices M_{m × n}(R) Under Addition")
        self.assertNotIn("_", fold_typeset_markup(h2))          # 默认（比对侧）照剥
        # 派生形与 H2 在闸里同形 ⇒ 账目面写法可用
        self.assertEqual(norm_title("2.11 Example: Matrices M_{m × n}(R) Under Addition", "2.11"),
                         norm_title(h2, "2.11"))
        # 负向：`keep_scripts` 只改**输出形**，不改判据——标记（`_`/`{}`）在闸里照剥所以
        # 两种写法同形，但**丢掉结构里的字母/关系符**是另一个标题，必须仍不同形。
        self.assertEqual(norm_title("2.11 Example: Matrices Mm×n(R) Under Addition", "2.11"),
                         norm_title(h2, "2.11"))
        self.assertNotEqual(fold_typeset_markup(h2, keep_scripts=True),
                            fold_typeset_markup(h2))
        self.assertNotEqual(norm_title("2.11 Example: Matrices M_{m}(R) Under Addition", "2.11"),
                            norm_title(h2, "2.11"))
        self.assertNotEqual(norm_title("2.11 Example: Matrices M_{mn}(R) Under Addition", "2.11"),
                            norm_title(h2, "2.11"))


class TestDanglingBracketTail(unittest.TestCase):
    def test_bracket_tail_math_variable_not_dangling(self):
        """Apostol《IANT》实测假阳：`Hurwitz's formula for ζ(s, a)` 末尾的 `a` 是 Hurwitz
        zeta 的第二个**变体**，被当成冠词判成「折行续行被丢弃」。带右括号收尾说明该括号组
        本身完整，不是悬空。"""
        self.assertIsNone(dangling_reason("12.7 Hurwitz's formula for ζ(s, a)", "12.7"))
        self.assertIsNone(dangling_reason("12.11 Evaluation of ζ(-n, a)", "12.11"))
        self.assertIsNone(dangling_reason("## §3.2 The function f (a)", "3.2"))

    def test_bracket_tail_exemption_does_not_mask_real_truncation(self):
        """负向：真折行截短（标题名里带括号、但**收在裸虚词上**）仍须报出来。"""
        self.assertTrue(dangling_reason("## §6.2 A relation between f ( x ) and", "6.2"))
        self.assertTrue(dangling_reason("## §1.2 Applications of", "1.2"))
        self.assertTrue(dangling_reason("## §5.4 The set S (see Chapt-", "5.4"))


class TestMathVariableCapitalTail(unittest.TestCase):
    r"""收尾的**大写单字母 `A`** 是数学变元，不是冠词（Fraleigh《AFCAA》§20.4/§20.5 实测）。

    跨架普查（776 章 / 58 本，`_p863_dangle_upper_a.py`）：虚词收尾报告总共 4 条
    = 这 2 站 × 契约/单元两侧，末 token 全部正是 `A`；其余（`of`/`and`/`the`/`a`…）
    **0 条** ⇒ 收这一档的爆炸半径就是这 2 站。印面这两节只排 `20.4 Definition` /
    `20.5 Definition`（无描述性节题，裁图 `agent_w3/sheet_ch20_heads.png`），尾部的 `A`
    是笔记侧描述语里的生成集记号（原书正文即 `G is free on A`）。闸的处方「按印刷全题补全」
    在这里**无题可补**，只能凭空造尾词 ⇒ 闸门 bug。
    """

    def test_capital_A_tail_is_not_dangling(self):
        self.assertIsNone(dangling_reason("20.4 Definition — The free group generated by A",
                                          "20.4"))
        self.assertIsNone(dangling_reason("## §20.5 Definition — Free on a set A", "20.5"))

    def test_lowercase_article_tail_still_reports(self):
        """控件（同一条档、只差大小写）：冠词形态 `a` 收尾必须照报——豁免**只认**大写 `A`。"""
        self.assertEqual(dangling_reason("6.4 A relation between x and a", "6.4"),
                         "以英文虚词「a」收尾（印刷折行标题的续行被丢弃）")

    def test_other_capitalized_particles_still_report(self):
        r"""负向：Title Case 的 `Of`/`The`/`An` 收尾**不豁免**（普查显示这一档零假阳，不收）。"""
        for t in ("9.3 Field Of", "9.4 The Basis Of", "9.5 An", "9.6 And", "9.7 In"):
            self.assertTrue(dangling_reason(t, t.split()[0]), t)

    def test_title_problems_clears_the_fraleigh_sites(self):
        for key, title in (("20.4", "Definition — The free group generated by A"),
                           ("20.5", "Definition — Free on a set A")):
            c = _contract([("%s" % key, "%s %s" % (key, title))])
            probs = title_problems(c, _units([("%s" % key, title)]),
                                   _read({"%s.md" % key: "## §%s %s\n\n正文" % (key, title)}))
            self.assertEqual(probs, [], (key, probs))


if __name__ == "__main__":
    unittest.main(verbosity=2)
