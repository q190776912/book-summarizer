"""闸门 ⑲（散文交叉引用对账）判据测试：正向抓真丢，负向防误伤。

正向 = 契约散文回指了式 `(N)`、本节单元只剩 `\\tag{N}` 而散文里该号消失；
负向 = 行首列表序标 / 范围右端 / 行内数学 / 跨节引用 / 无落点 / 已保留引用。
"""

import unittest

import lib.boot  # noqa: F401  (导入即完成 sys.path 引导)
from lib.crossref_attestation import (contract_prose_by_section,
                                      dropped_crossref_problems,
                                      prose_ref_numbers)


def _txt(t):
    return {"text": t, "line_start": True}


def _formula(f, tag=None):
    d = {"formula": f, "display": True}
    if tag:
        d["tag"] = tag
    return d


def _sec(key, blocks, children=None):
    node = {"key": key, "type": "section", "name": key, "sub_sec": list(blocks)}
    for c in children or []:
        node["sub_sec"].append(c)
    return node


def _chapter(secs):
    return {"key": "ch1", "type": "chapter", "name": "One", "sub_sec": secs}


class TestProseRefNumbers(unittest.TestCase):
    def test_mid_sentence_ref_counted(self):
        self.assertEqual(prose_ref_numbers("Equation (2) is the governing one."), {"2"})

    def test_fullwidth_parens_counted(self):
        self.assertEqual(prose_ref_numbers("由此即知式（2）成立。"), {"2"})

    def test_line_initial_ordinal_is_not_a_ref(self):
        self.assertEqual(prose_ref_numbers("(1) the first condition\nnext line"), set())

    def test_range_tail_is_not_a_ref(self):
        self.assertEqual(prose_ref_numbers("conditions (1)-(4) of the theorem"), {"1"})

    def test_inline_math_not_mistaken_for_ref(self):
        self.assertEqual(prose_ref_numbers("the fast $O ( 1 )$ time scale"), set())

    def test_display_and_tag_stripped(self):
        body = "$$\n\\dot x = f(x).\n\\tag{3}\n$$\nprose continues here"
        self.assertEqual(prose_ref_numbers(body), set())

    def test_year_and_zero_excluded(self):
        self.assertEqual(prose_ref_numbers("Lorenz (1963) and x(0) = 1 give (0) noise"),
                         set())

    def test_error_notation_glued_to_digit_is_not_a_ref(self):
        """Table 10.6.1 的 `4.4(1)` = 实验误差记法，不是式号回指（本书 §10.6 实测误报源）。"""
        self.assertEqual(
            prose_ref_numbers("the estimate δ = 4.4(1) agrees well, cf. 4.3(8)."), set())

    def test_ocr_function_call_glued_to_letter_is_not_a_ref(self):
        """OCR 把 `ln` 认成 `In` → 剥数学剥不掉；`(` 前紧贴字母即非回指。"""
        self.assertEqual(prose_ref_numbers("hence In(1) = 0 and f(2) vanish too."), set())

    def test_spaced_paren_after_space_still_counted(self):
        self.assertEqual(prose_ref_numbers("hence 4.4 (1) and In (1) agree."), {"1"})


class TestContractProseBySection(unittest.TestCase):
    def test_texts_grouped_by_nearest_section(self):
        tree = _chapter([
            {"key": "D1", "type": "description", "sub_sec": [_txt("intro prose")]},
            _sec("1.1", [_txt("see (2) here")],
                 children=[{"key": "1.1-1", "type": "example",
                            "sub_sec": [_txt("inside the example (5)")]},
                           {"key": "1.1-1-P1", "type": "proof",
                            "sub_sec": [_txt("proof prose (7)")] }]),
        ])
        out = contract_prose_by_section(tree)
        self.assertEqual(out[None], ["intro prose"])
        self.assertEqual(sorted(out["1.1"]),
                         sorted(["see (2) here", "inside the example (5)",
                                 "proof prose (7)"]))


class TestDroppedCrossrefProblems(unittest.TestCase):
    def _tree(self):
        return _chapter([
            _sec("1.1", [_txt("Equation (2) is the governing equation in the frame."),
                         _formula("x' = f(x)", "1"), _formula("x'' = g(x)", "2")]),
        ])

    def _bodies(self, body):
        return {"1.1": [body]}

    def test_dropped_ref_reported(self):
        probs = dropped_crossref_problems(
            self._tree(), self._bodies("That is the governing equation.\n"
                                       "$$\n\\tag{2}\n$$"), "ch1")
        self.assertEqual(len(probs), 1)
        self.assertIn("(2)", probs[0])
        self.assertTrue(probs[0].startswith("[ch1]"))

    def test_retained_ref_not_reported(self):
        probs = dropped_crossref_problems(
            self._tree(), self._bodies("Equation (2) is the governing one.\n"
                                       "$$\\tag{2}$$"), "ch1")
        self.assertEqual(probs, [])

    def test_target_not_in_section_exempt(self):
        tree = _chapter([
            _sec("1.1", [_txt("As shown in (9) elsewhere.")]),
            _sec("1.2", [_formula("y = z", "9")]),
        ])
        probs = dropped_crossref_problems(
            tree, {"1.1": ["plain prose without any number."],
                   "1.2": ["$$\\tag{9}$$"]}, "ch1")
        self.assertEqual(probs, [])

    def test_section_without_unit_record_skipped(self):
        probs = dropped_crossref_problems(self._tree(), {}, "ch1")
        self.assertEqual(probs, [])

    def test_list_marker_only_not_reported(self):
        tree = _chapter([
            _sec("1.1", [_txt("(2) second item of an OCR'd list\n\n"
                              "More prose that carries no reference at all here.")]),
        ])
        probs = dropped_crossref_problems(
            tree, {"1.1": ["body text\n$$\\tag{2}$$"]}, "ch1")
        self.assertEqual(probs, [])

    def test_cn_fullwidth_reference_satisfied_by_cn_style(self):
        """译单元用「式（2）」全角形态保留引用 —— 不得判丢（双语对称判据）。"""
        probs = dropped_crossref_problems(
            self._tree(), self._bodies("式（2）即旋转坐标系下的控制方程。\n$$\\tag{2}$$"),
            "ch1")
        self.assertEqual(probs, [])

    def test_ref_in_node_without_unit_record_skipped(self):
        """收紧 ⓪：散文所属节点**没有单元记录**（典型 = 本章习题条目整条未收进笔记）
        → 无处可补，不判。实测 Strogatz ch13 §13.6 的 6 处误报即此类，硬判会逼写手
        自撰一段罗列 (1)…(13) 的「概览」喂闸门。"""
        tree = _chapter([
            _sec("13.6", [_txt("Section opener with no reference here.")], children=[
                _sec("13.6.1", [_txt("(Gradient flow) Show that system (1) is a "
                                     "gradient flow.")]),
            ]),
            _sec("13.2", [_formula("th = w + k sin", "1")]),
        ])
        # 13.6 有落点单元（正文只带式 (2)），13.6.1 没有单元记录
        probs = dropped_crossref_problems(
            tree, {"13.6": ["body\n$$\\tag{2}$$"], "13.2": ["body\n$$\\tag{1}$$"]}, "ch13")
        self.assertEqual(probs, [])

    def test_control_same_ref_in_recorded_node_reported(self):
        """对照组：同样一句挂在**有单元记录**的节里 → 必须照判（收紧 ⓪ 不许放水）。"""
        tree = _chapter([
            _sec("13.6", [_txt("Show that system (1) is a gradient flow.")]),
            _sec("13.2", [_formula("th = w + k sin", "1")]),
        ])
        # 13.6 单元的节池里没有 (1)，但 13.2 有 → 按节池判：跨节豁免，不报
        self.assertEqual(
            dropped_crossref_problems(
                tree, {"13.6": ["body\n$$\\tag{2}$$"], "13.2": ["body\n$$\\tag{1}$$"]},
                "ch13"), [])
        # 同节（1）在账而散文引用丢了 → 报
        tree2 = _chapter([
            _sec("13.6", [_txt("Show that system (1) is a gradient flow."),
                          _formula("th = w + k sin", "1")]),
        ])
        probs = dropped_crossref_problems(
            tree2, {"13.6": ["body\n$$\\tag{1}$$"]}, "ch13")
        self.assertEqual(len(probs), 1)
        self.assertIn("(1)", probs[0])

        """本书实测形态：印面 `Equation (3) may look intimidating…`，笔记只留 \\tag。"""
        tree = _chapter([
            _sec("13.5", [_txt("Equation (3) may look intimidating, but it is not."),
                          _formula("I = int int rho", "3")]),
        ])
        probs = dropped_crossref_problems(
            tree, {"13.5": ["The double integral looks intimidating.\n"
                            "$$\nI = \\int\\!\\int \\rho\n\\tag{3}\n$$"]}, "ch13")
        self.assertEqual([p for p in probs if "(3)" in p], probs)


if __name__ == "__main__":
    unittest.main()
