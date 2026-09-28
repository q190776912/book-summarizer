# -*- coding: utf-8 -*-
"""Regression: 印面目录节覆盖审计 check_section_coverage 的 TOC 解析。

Iwaniec–Kowalski GTM207（2026-09-28）：结构阶段的节节点靠正文页 OCR 粗体标题识别，
扫描书里这些标题**整块被 OCR 漏掉**时该节在契约里根本没有节点 → 没有节单元 → 合并 md
缺节标题，而 D 层「契约↔单元对账」按同一份契约比，永远看不见（实测 §4.3 The Poisson
summation formula 印面 p.69 明晃晃印着，notes 里只有并入相邻条目的一段散文）。书首目录页
把 `§N.M 标题 页码` 印在同一块里，OCR 命中率高得多，故以它为真值做独立审计。

锁死六件事（全部是实测过的假阴/假阳来源）：
 1) § 被 OCR 成 `$`/`S` 且与数字粘连（`S1.1.Notation`）必须仍解析出 (1,1)——早先的
    「前面不得是字母」回看把整章条目全吞掉，missing 假阴成 0；
 2) 跨页页眉 `TABLE OF CONTENTS vii` 插在条目中间时不得吞掉下一条；
 3) `Chaptcr 7.`（chapter 被 OCR 读花）不得让 §7.x 全部失去章上下文；
 4) 整行 `Chapter 2.` 丢失时，`$2.1 …` 仍须采信（章上下文只作旁证，不是准入条件）；
 5) 标题里的无标记数字（`Theorein 26.2`）不得另立条目，也不得截断真条目的页码；
 6) 书末 `Bibliography 599 Index 611` / 字母附录节 `S4.A.` 不得污染上一条目的页码。
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, str(Path(_ROOT) / "flows" / "write-source" / "script"))

import check_section_coverage as csc  # noqa: E402


def toc(text):
    return csc.parse_toc(csc.RUNNING_HEAD.sub(" ", text))


class TestTocParsing(unittest.TestCase):
    def test_glued_section_marker_is_parsed(self):
        # (1) 判据：S/$ 与数字粘连
        got = toc("Chapter 1. Arithmetic Functions 9 S1.1.Notation anddefinitions 9 "
                  "$1.2. Generating series 10 $")
        self.assertIn((1, 1), got)
        self.assertEqual(got[(1, 1)][1], 9)
        self.assertEqual(got[(1, 2)][0], "Generating series")

    def test_running_header_between_entries(self):
        # (2) 判据：跨页页眉不得吞条目
        got = toc("$9.5. Dirichlet polynomials with characters 238 "
                  "TABLE OF CONTENTS vii $9.6. The reflection method 243 $")
        self.assertEqual(got[(9, 6)][1], 243)
        self.assertEqual(got[(9, 6)][0], "The reflection method")

    def test_mangled_chapter_word_keeps_section_context(self):
        # (3) 判据：Chaptcr 读花仍算章条目
        got = toc("Chaptcr 7.Bilinear Forms and the Large Sieve 169 "
                  "$7.1. General principles 169 $")
        self.assertEqual(got[(7, 1)][1], 169)

    def test_lost_chapter_line_does_not_drop_sections(self):
        # (4) 判据：章条目整行丢失（页边界被 OCR 吃掉）时仍采信带标记的节条目
        got = toc("$1.7. Distribution of additive functions 31 $2.1.The Prime Number "
                  "Theorem 31 $2.2. Tchebyshev method 32 $")
        self.assertEqual(sorted(got), [(1, 7), (2, 1), (2, 2)])

    def test_number_inside_title_is_not_an_entry(self):
        # (5) 判据：标题里的 "Theorem 26.2" 无 § 标记 → 不立条目、不断页码
        got = toc("$26.2. Principle of the proof of Theorein 26.2 580 "
                  "$26.3. Formulas for the first and the second moment 582 $")
        self.assertEqual(sorted(got), [(26, 2), (26, 3)])
        self.assertEqual(got[(26, 2)][1], 580)

    def test_back_matter_and_lettered_appendix_do_not_steal_pages(self):
        # (6) 判据：书末条目切断
        got = toc("$26.5. Proof of Theorem 26.2 595 Bibliography 599 Index 611 ")
        self.assertEqual(got[(26, 5)][1], 595)
        got = toc("$4.6. Functional equations of Dirichlet L-functions 84 "
                  "S4.A. Appendix: Fourier integrals and series 86 Chapter 5. 97 "
                  "$5.1. Introduction 97 $")
        self.assertEqual(got[(4, 6)][1], 84)
        self.assertNotIn((4, 10), got)
        self.assertEqual(got[(5, 1)][1], 97)

    def test_unmarked_prose_number_is_not_an_entry(self):
        # 反向负例：正文式句子（无标记、前面是字母）不得被当成目录条目
        got = toc("Some discussion of Theorem 26.2 and Lemma 3.4 continues here ")
        self.assertEqual(got, {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
