# -*- coding: utf-8 -*-
r"""Q 层 2026-10-04 三项收窄的判据回归（Iwaniec–Kowalski《解析数论》实测）。

1. `_heading_num` 的字母残迹守卫收窄：`6.A` 图号子标照旧拒绝，但 "23.2. A
   partition of…" 形态的**英文节标题**必须识别——否则节游标停在上一节，
   整节忠实 `\tag` 整批 MISPLACED（ch19 §19.3 / ch23 §23.2+§23.6 实测）。
2. `_compute_order_and_section` 弱证据不判：位置只来自纯散文回指的编号
   （`_pos_strong` 无记录——印面标签块被 OCR 整块丢失）不得当顺序游标，
   也不得判 MISPLACED（ch1 (1.6) 实测）。
3. letter-led 探针滤**外章引用**：单字母头不在本书章键集（(A.36) 指向书末
   附录而 chapter_map 无附录章）→ 不发 letter_ch 误配提示。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot  # noqa: E402
_boot.setup()

from verify.formula_tag.script.formula_tag import (  # noqa: E402
    _heading_num, _compute_order_and_section, _detect_letter_led_formulas,
    SourceFormulaIndex)


class HeadingAlphaTitleTest(unittest.TestCase):
    def test_alpha_word_titles_recognised(self):
        for s, want in (
                ("23.2. A partition of A(9)().", "23.2"),
                ("19.3. A ternary additive problem with A'.", "19.3"),
                ("23.6. A lowerbound for the classnumber.", "23.6"),
                ("5.4 An Axiomatic treatment", "5.4"),
        ):
            self.assertEqual(_heading_num(s), want, s)

    def test_sublabel_fragments_still_rejected(self):
        for s in ("6.A", "3.4.B", "23.2. A"):
            self.assertIsNone(_heading_num(s), s)

    def test_prose_paren_continuation_rejected(self):
        """节号后「空格+括号」续句 = 散文回指行，绝非标题（ch10/ch26 实测）。"""
        for s in ("9.7 (or Theorem 9.16) together with the closing remarks",
                  "26.2 (non-vanishing in \u201cnatural\u201d average) can be done"):
            self.assertIsNone(_heading_num(s), s)

    def test_legacy_behaviour_unchanged(self):
        self.assertEqual(_heading_num("2.3.2 Preliminaries"), "2.3.2")
        self.assertIsNone(_heading_num("20.6 and it is stated"))
        self.assertEqual(_heading_num("5.3. e-Orbits"), "5.3")

    def test_track_heading_never_moves_backward(self):
        """书眉重印更早节标题不得把游标拉回去（Iwaniec–Kowalski ch7 p184 实测：
        "7.4.Applications…" 出现在 "7.5. Multiplicative…" 之后）。"""
        idx = SourceFormulaIndex.__new__(SourceFormulaIndex)
        idx._cur_heading = None
        idx._sec_keys = None
        idx._tail_exer_page = None
        idx._tail_exer_anchor_y = None
        idx._track_heading("7.4.Applications of the large sieve.")
        self.assertEqual(idx._cur_heading, "7.4")
        idx._track_heading("7.5. Multiplicative large sieve inequality.")
        self.assertEqual(idx._cur_heading, "7.5")
        idx._track_heading("7.4.Applications of the large sieve.")
        self.assertEqual(idx._cur_heading, "7.5", "书眉回跳必须被拒")
        idx._track_heading("7.6. Panorama of the large sieve inequalities.")
        self.assertEqual(idx._cur_heading, "7.6")


def _tag(n):
    return SimpleNamespace(normalized=n, latex='x')


class _StubSrc:
    _book_section_sec = {}

    def __init__(self, union, pos, strong, sec=None):
        self._u, self._p, self._s, self._sec = union, pos, strong, sec or {}
        self._pos_strong = strong
        self._book_section = {}

    def source_numbers(self):
        return self._u

    def primary_pos(self, n):
        return self._p.get(n)

    def book_section(self, n):
        return self._book_section.get(n)


class WeakEvidenceOrderTest(unittest.TestCase):
    def test_weak_only_number_skipped(self):
        """(1.6) 只有 p18 散文回指（弱），(1.7) 有 p17 强标签：总结忠实顺序
        1.6→1.7 不得报 ORDER_MISMATCH（旧写法拿弱位置当游标必报）。"""
        src = _StubSrc({'1.6', '1.7'},
                       {'1.6': (18, 0), '1.7': (17, 0)},
                       {'1.7': True})
        om, mp = _compute_order_and_section(
            [(None, _tag('1.6')), (None, _tag('1.7'))], src,
            reset_on_section=False)
        self.assertEqual(om, [])
        self.assertEqual(mp, [])

    def test_strong_inversion_still_flagged(self):
        """真倒挂（双强证据、**跨页**）照判：总结 1.8→1.7，书序 1.7(p17) 在 1.8(p20) 前。"""
        src = _StubSrc({'1.7', '1.8'},
                       {'1.7': (17, 0), '1.8': (20, 0)},
                       {'1.7': True, '1.8': True})
        om, _ = _compute_order_and_section(
            [(None, _tag('1.8')), (None, _tag('1.7'))], src,
            reset_on_section=False)
        self.assertEqual([r['number'] for r in om], ['1.7'])

    def test_same_page_y_inversion_not_flagged(self):
        """同页 y 倒序不判：多行公式的右缘标签 y 与号序无关（ch3 (3.53)/(3.55) 实测）。"""
        src = _StubSrc({'3.53', '3.55'},
                       {'3.53': (61, 578.0), '3.55': (61, 527.0)},
                       {'3.53': True, '3.55': True})
        om, _ = _compute_order_and_section(
            [(None, _tag('3.53')), (None, _tag('3.55'))], src,
            reset_on_section=False)
        self.assertEqual(om, [])


class LetterLedProbeFilterTest(unittest.TestCase):
    def _make_ext(self, pages_tokens, chapter_keys):
        ext = tempfile.mkdtemp()
        d = os.path.join(ext, 'book_structure')
        os.makedirs(d, exist_ok=True)
        for k in chapter_keys:
            label = f'ch{k}' if str(k).isdigit() else f'appendix{k}'
            with open(os.path.join(d, f'{label}.json'), 'w', encoding='utf-8') as f:
                json.dump({'key': str(k), 'type': 'chapter', 'sub_sec': []}, f)
        pdir = os.path.join(ext, 'pages')
        os.makedirs(pdir, exist_ok=True)
        with open(os.path.join(pdir, 'page_001.json'), 'w', encoding='utf-8') as f:
            json.dump({'text': [{'text': t} for t in pages_tokens]}, f,
                      ensure_ascii=False)
        return ext

    def test_external_appendix_reference_filtered(self):
        """(A.36) 指向书外附录（章键集无 'A'）→ 探针沉默。"""
        ext = self._make_ext(['Inserting this into (A.36) we get'], [1, 2, 3])
        self.assertEqual(_detect_letter_led_formulas(ext, 1, 1, ch=1), set())

    def test_in_book_letter_chapter_still_flagged(self):
        """章键集含 'A'（真附录章在册）→ 提示照发，不静默。"""
        ext = self._make_ext(['Inserting this into (A.36) we get'], ['A', 1])
        self.assertEqual(_detect_letter_led_formulas(ext, 1, 1, ch=1),
                         {'(A.36)'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
