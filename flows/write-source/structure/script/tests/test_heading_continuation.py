# -*- coding: utf-8 -*-
"""节头标题跨行印刷时须并入**悬挂续行**（Apostol《Introduction to Analytic
Number Theory》实测 2026-09-28）。

根因：印刷把长节题排成两行（悬挂缩进），OCR 分成两块：
  p65  i22 [66, 899, 719]  '3.2 The big oh notation. Asymptotic equality'
       i23 [126, 936, 302] 'of functions'
       i24 [68, 992, 597]  'Definition If g(x) > 0 …'（正文栏归位）
同型还有 §3.6/§3.8/§3.12/§4.8/§7.2/§8.5/§8.10/§10.2/§13.3。扫描只取节头块首行：
  ① 契约节名丢掉标题尾巴 → 最终 md 的 `## §3.2 …` 少半截（保真缺陷）；
  ② 奇偶页页眉印**完整**标题，②c 正文守恒闸遂把页眉复本判成「印面收集到、
     契约里没有」的丢失正文块（CONTENT GATE FAIL，假丢失）。

判据（`heading_continuation`，纯几何 + 形态，不点名书、不查词表）：悬挂缩进
≥30pt、行距 8-72pt、续行 ≤60 字符且**窄于节头行**、非条头形态、不以句读收尾、
续行之后一行的左边界回到节头行左边界（正文重新起栏）。

运行：
  python flows/write-source/structure/script/tests/test_heading_continuation.py
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

import scan_skeleton as ss  # noqa: E402


def _b(text, x0, y, x1):
    return {"text": text, "poly": [x0, y, x1, y, x1, y, x0, y], "score": 0.99}


# 本书 p65 实测节头三件套（head / 悬挂续行 / 正文归位行）
_HEAD_TITLE = "The big oh notation. Asymptotic equality"
_HEAD = _b("3.2 The big oh notation. Asymptotic equality", 66, 899, 719)
_CONT = _b("of functions", 126, 936, 302)
_RESUME = _b("Definition If g(x) > 0 for all x ≥ a, we write", 68, 992, 597)


def _hc(cont_block, head=_HEAD, resume=_RESUME, title=_HEAD_TITLE, bi=0):
    return ss.heading_continuation([head, cont_block, resume], bi, title)


class TestPositive(unittest.TestCase):
    def test_apostol_p65_geometry(self):
        self.assertEqual(_hc(_CONT), "of functions")

    def test_apostol_p177_short_continuation(self):
        # §8.5 'Gauss sums associated with Dirichlet' + 'characters'
        blocks = [_b("8.5 Gauss sums associated with Dirichlet", 66, 200, 659),
                  _b("characters", 126, 240, 275),
                  _b("Definition For any Dirichlet character x mod k the sum",
                     70, 299, 723)]
        self.assertEqual(ss.heading_continuation(
            blocks, 0, "Gauss sums associated with Dirichlet"), "characters")

    def test_apostol_p159_math_tail_continuation(self):
        # §7.2 续行含算符与数字（但不以数字起头、非条头形态）
        blocks = [_b("7.2 Dirichlet's theorem for primes of", 55, 198, 592),
                  _b("the form 4n - 1 and 4n + 1", 118, 244, 522),
                  _b("Theorem 7.1 There are infinitely many primes of the form",
                     54, 289, 813)]
        self.assertEqual(ss.heading_continuation(
            blocks, 0, "Dirichlet's theorem for primes of"),
            "the form 4n - 1 and 4n + 1")

    def test_cjk_continuation(self):
        blocks = [_b("3.2 大 O 记号与渐近等式", 66, 899, 719),
                  _b("的若干性质", 126, 936, 302),
                  _b("定义 若 g(x) > 0 对一切 x ≥ a 成立，则记", 68, 992, 597)]
        self.assertEqual(ss.heading_continuation(
            blocks, 0, "大 O 记号与渐近等式"), "的若干性质")

    def test_ghost_anchor_is_skipped_for_resume(self):
        """Apostol ch2 §2.7 实测：归位锚点位置被 OCR 碎块占据（score 0.18、宽 94pt）。

        碎块 '2.8 If f' 左边界 253 既不对齐节头左边界 140 也不是回栏正文；旧逻辑把它当
        **唯一**锚点 → 三明治判据不成立 → 印刷标题尾巴 'inversion formula' 丢失。真锚点
        是它下面那行 'Theorem 2.8 If f is an arithmetical …'（x0=146，回到节头左边）。
        """
        blocks = [_b("2.7 Dirichlet inverses and the Mobius", 140, 1103, 692),
                  _b("inversion formula", 207, 1147, 463),
                  {"text": "2.8 If f", "score": 0.18,
                   "poly": [253, 1206, 347, 1206, 347, 1241, 253, 1241]},
                  _b("Theorem 2.8 If f is an arithmetical function with f(1)",
                     146, 1210, 1043)]
        self.assertEqual(ss.heading_continuation(
            blocks, 0, "Dirichlet inverses and the Mobius"), "inversion formula")

    def test_scan_row_title_is_complete(self):
        """端到端：scan 发出的 SEC 行标题含续行（页眉完整标题不再被②c判丢失）。"""
        with tempfile.TemporaryDirectory() as td:
            p64 = [_b("3.1 Introduction", 66, 200, 300),
                   _b("This chapter deals with the average order of arithmetical",
                      66, 260, 960)]
            p65 = [_b("3.2: The big oh notation. Asymptotic equality of functions",
                      341, 55, 961),                    # 页眉复本（右对齐页首）
                   _b("Some prose line before the heading continues here",
                      66, 700, 960),
                   _HEAD, _CONT, _RESUME,
                   _b("f(x) = O(g(x)) (read: f(x) is big oh of g(x))",
                      239, 1039, 821)]
            for pg, blocks in ((64, p64), (65, p65)):
                with open(os.path.join(td, "page_%03d.json" % pg), "w",
                          encoding="utf-8") as f:
                    json.dump({"text": blocks}, f, ensure_ascii=False)
            rows = ss.scan(td, 3, 64, 65, "two-level", section_depths=[1, 2])
        titles = [r[3] for r in rows if r[1] == "SEC" and str(r[2]) == "3.2"]
        self.assertEqual(titles, [_HEAD_TITLE + " of functions"])


class TestNegative(unittest.TestCase):
    def test_body_line_at_margin_is_not_continuation(self):
        self.assertIsNone(_hc(_b("It is clear that the definition applies",
                                 66, 936, 700)))

    def test_indented_full_width_paragraph_is_not_continuation(self):
        # 中文书首行缩进的正文段：缩进达标但宽度不小于节头行 → 拒
        self.assertIsNone(_hc(_b("这里把定义推广到任意正实数，并且讨论若干常用的渐近公式",
                                 126, 936, 960)))

    def test_item_head_shape_is_rejected(self):
        self.assertIsNone(_hc(_b("Theorem 3.4 There are infinitely many",
                                 126, 936, 700)))

    def test_bare_number_line_is_rejected(self):
        self.assertIsNone(_hc(_b("4. Let S be any infinite subset", 126, 936, 700)))

    def test_paragraph_gap_is_rejected(self):
        self.assertIsNone(_hc(_b("of functions", 126, 1030, 302)))

    def test_sentence_tail_is_rejected(self):
        self.assertIsNone(_hc(_b("defined as follows.", 126, 936, 302)))

    def test_resume_column_must_return_to_head_margin(self):
        self.assertIsNone(_hc(_CONT, resume=_b("Another indented block instead",
                                               260, 992, 900)))

    def test_resume_narrower_than_continuation_is_rejected(self):
        self.assertIsNone(_hc(_CONT, resume=_b("x", 68, 992, 130)))

    def test_long_continuation_is_rejected(self):
        self.assertIsNone(_hc(_b("a" * 61, 126, 936, 302)))

    def test_missing_geometry_is_rejected(self):
        blocks = [{"text": "3.2 Some heading"}, {"text": "of functions"},
                  {"text": "body line"}]
        self.assertIsNone(ss.heading_continuation(blocks, 0, "Some heading"))

    def test_all_candidates_ghost_is_not_rescued(self):
        """负向：探测窗内**全部**候选都不可信 → 照旧不补（保守，宁漏勿误）。"""
        blocks = [_b("2.7 Dirichlet inverses and the Mobius", 140, 1103, 692),
                  _b("inversion formula", 207, 1147, 463),
                  {"text": "2.8 If f", "score": 0.18,
                   "poly": [253, 1206, 347, 1206, 347, 1241, 253, 1241]},
                  {"text": "f * f-1", "score": 0.22,
                   "poly": [457, 1297, 758, 1297, 758, 1329, 457, 1329]},
                  {"text": "I", "score": 0.31,
                   "poly": [500, 1340, 560, 1340, 560, 1372, 500, 1372]}]
        self.assertIsNone(ss.heading_continuation(
            blocks, 0, "Dirichlet inverses and the Mobius"))

    def test_skipping_ghost_does_not_loosen_alignment(self):
        """负向：跳过碎块后落到的**可信**块若没回到节头左边，仍须拒。

        （碎块占据锚点位曾使该判据「看不见」后续行；顺延后判据强度不得下降——
        这里可信块是居中显示公式（x0=457 vs 节头 x0=140），不是回栏正文。）
        """
        blocks = [_b("2.7 Dirichlet inverses and the Mobius", 140, 1103, 692),
                  _b("inversion formula", 207, 1147, 463),
                  {"text": "2.8 If f", "score": 0.18,
                   "poly": [253, 1206, 347, 1206, 347, 1241, 253, 1241]},
                  _b("f * f-1 = f-1 * f = I (the identity function for",
                     457, 1297, 900)]
        self.assertIsNone(ss.heading_continuation(
            blocks, 0, "Dirichlet inverses and the Mobius"))

    def test_missing_title_or_short_block_list(self):
        self.assertIsNone(ss.heading_continuation([_HEAD], 0, _HEAD_TITLE))
        self.assertIsNone(ss.heading_continuation(None, 0, _HEAD_TITLE))
        self.assertIsNone(ss.heading_continuation([_HEAD, _CONT, _RESUME], 2,
                                                  _HEAD_TITLE))
        self.assertIsNone(ss.heading_continuation([_HEAD, _CONT, _RESUME], 0, ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)
