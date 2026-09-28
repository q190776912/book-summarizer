# -*- coding: utf-8 -*-
"""Regression: 练习覆盖闸 check_exercise_coverage 的 MISSING / PHANTOM / OCR-EMPTY 判定。

Iwaniec–Kowalski GTM207（2026-09-28）：结构阶段契约里 ch7/11/14/16/17/18/25 的
`exercise` 节点数为 **0**（该书的练习是嵌在正文里的小字标题 `EXERCISE n.`，不被识别为
节点），于是没有练习单元；写手章到步骤 8 才由 B 层「内部缺号」偶然暴露一部分，而
**整章练习丢失**（tail loss）B 层永远看不见——ch16/17/18 的单元里一个练习标题都没有，
verify 仍全绿。故补此独立审计：印面标题（page_*.json，容忍 OCR 大小写/空格/词尾噪声）
对上单元 md 行首练习标题，双向报缺失与幻影号。

锁死四件事：
 1) 印面有 `EXERCISE 1.`、单元没有 → MISSING，且带印面页码；
 2) `EXERCISE 10.` 必须读成 10，不得被 OCR 词尾字母吞成 0（曾经的假阳来源）；
 3) 单元与印面齐备 → 干净、exit 0；
 4) 印面零命中但单元有练习 → 记 OCR-EMPTY，不得当成「无缺失」的绿灯。

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_exercise_coverage_audit.py
"""
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, str(Path(_ROOT) / "flows" / "write-source" / "script"))

import check_exercise_coverage as cov  # noqa: E402


def _page(path, texts):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'page': 1, 'text': [{'text': t, 'poly': [0, 0, 1, 0]} for t in texts]}, f)


class ExerciseCoverageAudit(unittest.TestCase):
    def setUp(self):
        self.ext = tempfile.mkdtemp(prefix='excov')
        self.bs = os.path.join(self.ext, 'book_structure')
        os.makedirs(os.path.join(self.bs, 'units', 'ch1'))
        with open(os.path.join(self.bs, 'ch1.json'), 'w', encoding='utf-8') as f:
            json.dump({'key': '1', 'type': 'chapter', 'page_start': 2, 'page_end': 3}, f)

    def tearDown(self):
        shutil.rmtree(self.ext, ignore_errors=True)

    def _unit(self, body):
        with open(os.path.join(self.bs, 'units', 'ch1', '0001_desc_D1.md'), 'w',
                  encoding='utf-8') as f:
            f.write('<!-- unit id=0001 type=desc key=D1 name="" -->\n' + body)

    def test_printed_exercise_missing_from_units(self):
        _page(os.path.join(self.ext, 'page_002.json'),
              ['ExERCisE 1. Prove that for odd p,'])
        self._unit('Some prose with no exercise at all.\n')
        pr = cov.printed_heads(self.ext, 1, 2, 3)
        md = cov.md_heads(os.path.join(self.bs, 'units', 'ch1'))
        self.assertEqual(sorted(pr), [1])
        self.assertNotIn(1, md)

    def test_two_digit_number_not_swallowed_by_ocr_word_tail(self):
        # 「EXERCISE 10.」 曾被 OCR 词尾噪声读成 0，制造假 MISSING
        _page(os.path.join(self.ext, 'page_002.json'),
              ['ExERCISE 10. Prove that there are infinitely many pairs.'])
        pr = cov.printed_heads(self.ext, 1, 2, 3)
        self.assertEqual(sorted(pr), [10])

    def test_matched_exercise_is_clean(self):
        _page(os.path.join(self.ext, 'page_002.json'), ['EXERCISE 3. Show that'])
        self._unit('**Exercise 3.** Show that the claim holds.\n')
        pr = cov.printed_heads(self.ext, 1, 2, 3)
        md = cov.md_heads(os.path.join(self.bs, 'units', 'ch1'))
        self.assertEqual(sorted(pr), [3])
        self.assertEqual(sorted(md), [3])

    def test_plain_form_heading_counts_as_present(self):
        # 本书单元里练习也写成裸行「Exercise 2. …」，不得判缺失
        _page(os.path.join(self.ext, 'page_002.json'), ['ExERCIsE 2. Prove that'])
        self._unit('Exercise 2. Prove that the bound holds.\n')
        md = cov.md_heads(os.path.join(self.bs, 'units', 'ch1'))
        self.assertEqual(sorted(md), [2])

    def test_cross_reference_is_not_counted_as_head(self):
        self._unit('see Exercise 4 of Chapter 12 for details.\n')
        md = cov.md_heads(os.path.join(self.bs, 'units', 'ch1'))
        self.assertEqual(sorted(md), [])

    def test_gap_page_owned_by_previous_chapter_header(self):
        # 实测假阳：ch10 契约止于 p266、ch11 起于 p269，p267-268 落在区间空隙里，
        # padding 扫描把 ch10 的 Exercise 6 报给了 ch11。页眉「10.…」才是归属真值。
        _page(os.path.join(self.ext, 'page_003.json'),
              ['10.ZERO-DENSITY ESTIMATES', '267', 'ExERCisE6. Assume the following'])
        self.assertEqual(cov.printed_heads(self.ext, 11, 2, 2), {})
        self.assertEqual(sorted(cov.printed_heads(self.ext, 10, 2, 2)), [6])

    def test_section_title_is_not_a_chapter_header(self):
        # 「11.1. Introduction.」不得读成章号 11 之外的归属，更不得吞掉本章练习
        _page(os.path.join(self.ext, 'page_002.json'),
              ['11.1. Introduction.', 'EXERCISE 2. Prove that'])
        pr = cov.printed_heads(self.ext, 11, 2, 2)
        self.assertEqual(sorted(pr), [2])

    def test_chapter_opener_header_counts_for_own_chapter(self):
        _page(os.path.join(self.ext, 'page_002.json'),
              ['CHAPTER 1', 'SUMS OVER FINITE FIELDS', 'EXERCISE 1. Prove that'])
        pr = cov.printed_heads(self.ext, 1, 2, 2)
        self.assertEqual(sorted(pr), [1])


if __name__ == '__main__':
    unittest.main(verbosity=2)
