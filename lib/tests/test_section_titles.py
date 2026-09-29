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

from section_titles import (clean_title, dangling_reason, glued_reason,  # noqa: E402
                            norm_title, title_problems)


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


if __name__ == "__main__":
    unittest.main(verbosity=2)
