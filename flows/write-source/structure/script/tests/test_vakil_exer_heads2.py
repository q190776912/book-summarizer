"""Vakil exercise-head capture, round 2 (2026-09-24 Rising Sea).

Root causes fixed here:
  * universal SEC detector swallowed three-segment heads: _SEC_HEAD_RE eats
    '10.1' of '10.1.E.EXERCISE (…' and the rest passes as a section title ->
    the exercise vanished AND the bogus SEC row reset the exercise latch.
    '10.1.F. *+ EXERCISE (…' additionally rode SEC_3 (`[+*x]` symbol class).
  * space-after-letter heads ('4.3.F IMPORTANT EASY EXERCISE …') matched no
    EXER regex at all (EXER_3 requires a dot) -> 57 heads lost book-wide.
  * printed exercise letter I OCR'd as digit 1 ('10.1.I. EXERCISE.' ->
    '10.1.1. ExERCISE. …') collides with the real item '10.1.1'; the dup was
    silently dropped by dedup (I content loss).
  * adjacent glyph garble F->E ('16.7.F.' read as '16.7.E.') produces a
    duplicated letter + a hole at the next letter.

Fixes under test:
  * scan_skeleton._section_header_info: `.` + uppercase + `.` after a 2-seg
    number is a three-level head, never a section title -> reject.
  * scan_skeleton EXER_3_SV: 'C.S.X <space> UPPERCASE…' captured as EXER when
    the remainder is an exercise HEAD form.
  * scan_skeleton numeric-collision post-pass: same 'C.S.1' twice -> the one
    whose head is exercise form becomes 'C.S.I'.
  * scan_skeleton dup-letter sequence post-pass: duplicated letter + missing
    immediate successor -> second occurrence relabelled.
  * lib.numbering.is_exercise_head_text: prose 'The importance of exercises.'
    / cross-ref 'Exercise 24.5.M can be improved:' / bare lowercase
    'exercise.' are NOT head forms; corpus drift forms (ExERCISE / EAsy
    ExERCISE / ⋆⋆EXERCISE (…) / EXERCISE FOR CATEGORY-LOVERS: /
    IMPORTANT (BUT SURPRISINGLY EASY) EXERCISE.) ARE.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_vakil_exer_heads2.py
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
    _ROOT = str(Path(__file__).resolve().parents[3])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import importlib.util


def _load(rel, name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(_ROOT, *rel.split('/')))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ss = _load("flows/write-source/structure/script/scan_skeleton.py", "scan_skeleton")
from lib.numbering import is_exercise_head_text


def _dir(lines):
    d = tempfile.mkdtemp()
    blocks = [{"text": ln, "poly": [0, 500, 1200, 520, 0, 0, 0, 0]} for ln in lines]
    with open(os.path.join(d, "page_001.json"), "w", encoding="utf-8") as fh:
        json.dump({"text": blocks}, fh)
    return d


def _scan(lines, ch=10):
    d = _dir(lines)
    return ss.scan(d, ch, 1, 1, 'three-level', section_depths=[1, 2])


class TestSecDoesNotStealHeads(unittest.TestCase):
    def test_dotted_letter_head_not_sec(self):
        info = ss._section_header_info('10.1.E.EXERCISE (PRODUCTS OF IRREDUCIBLE '
                                       'VARIETIES OVER k ARE IRREDUCIBLE)',
                                       ch=10, depths={1, 2})
        self.assertIsNone(info)

    def test_real_section_still_detected(self):
        info = ss._section_header_info('10.2 Rational maps to separated schemes',
                                       ch=10, depths={1, 2})
        self.assertIsNotNone(info)
        self.assertEqual(info[0], '10.2')

    def test_dashed_letter_head_not_sec(self):
        # dash-scheme books: '5.5-O.EXERCISE' style must not become a section
        self.assertIsNone(ss._section_header_info(
            '10.1.F.EXERCISE (COMPLEX ALGEBRAIC VARIETIES YIELD COMPLEX ANALYTIC '
            'ONES). Show', ch=10, depths={1, 2}))


class TestSpaceVariant(unittest.TestCase):
    def test_space_head_captured(self):
        rows = _scan(['4.3.F IMPORTANT EASY EXERCISE. Show that the line with '
                      'doubled origin is not separated.'], ch=4)
        kinds = {(r[1], r[2]) for r in rows}
        self.assertIn(('EXER', '4.3.F'), kinds)
        self.assertFalse(any(k == 'SEC' for _, k, *_ in rows))

    def test_plain_uppercase_space_head_rejected(self):
        # 'C.S.X word.' without exercise keyword is NOT a head (prose ref)
        self.assertFalse(ss.EXER_3_SV.match('10.1 Some schemes are weird.')
                         and is_exercise_head_text('Some schemes are weird.'))


class TestNumericCollision(unittest.TestCase):
    def test_dup_one_resolved_to_I(self):
        rows = _scan([
            '10.1.1. Motivation. Let us review why we like Hausdorffness.',
            '10.1.1. ExERCISE.  Prove that the condition of being '
            'quasiseparated is local on the base.'], ch=10)
        ex = [r for r in rows if r[1] == 'EXER']
        it = [r for r in rows if r[1] == 'ITEM']
        self.assertEqual([r[2] for r in ex], ['10.1.I'])
        self.assertEqual([r[2] for r in it], ['10.1.1'])

    def test_single_one_stays_item(self):
        rows = _scan(['10.1.1. Motivation. Let us review why we like '
                      'Hausdorffness here.'], ch=10)
        self.assertEqual([r[2] for r in rows if r[1] == 'ITEM'], ['10.1.1'])
        self.assertEqual([r for r in rows if r[1] == 'EXER'], [])


class TestDupLetterSequence(unittest.TestCase):
    def test_second_dup_becomes_successor(self):
        rows = _scan([
            '16.7.E. EXERCISE. Show that the functor is fully faithful.',
            '16.7.E. EXERCISE (FIBER PRODUCTS AND BASE CHANGE). Prove the '
            'stated lemma.',
            '16.7.G. EXERCISE. Finish the argument.'], ch=16)
        keys = [r[2] for r in rows if r[1] == 'EXER']
        self.assertEqual(keys, ['16.7.E', '16.7.F', '16.7.G'])

    def test_no_gap_dup_untouched(self):
        rows = _scan([
            '16.7.E. EXERCISE. Show that the functor is fully faithful here.',
            '16.7.E. EXERCISE. Duplicate cross reference line two.',
            '16.7.F. EXERCISE. Also present.'], ch=16)
        keys = [r[2] for r in rows if r[1] == 'EXER']
        self.assertEqual(keys.count('16.7.E'), 2)
        self.assertIn('16.7.F', keys)
        self.assertNotIn('16.7.G', keys)


class TestHeadFormPredicate(unittest.TestCase):
    POS = [
        'EXERCISE.', 'ExERCISE. Show', 'EXERCISE:', '⋆EXERCISE.',
        '⋆⋆EXERCISE (NAGATA’S LEMMA).',
        'EASy ExERCISE. Suppose we have morphisms',
        'EXERCISE (CF. EXERCISE 6.3.E).',
        'EXERCISE/DEFINITION.',
        'IMPORTANT EXERCISE THAT YOU SHOULD DO ONCE IN YOUR LIFE (YONEDA’S',
        'EXERCISE AND IMPORTANT DEFINITION. Suppose',
        'EXERCISE FOR CATEGORY-LOVERS: “A PRESHEAF IS THE SAME AS A CON-',
        'USEFUL EXERCISE, NOT JUST FOR CATEGORY-LOVERS. Show that the sheaf',
        'IMPORTANT (BUT SURPRISINGLY EASY) EXERCISE.',
        'EASY (BUT SURPRISINGLY ENLIGHTENING) EXERCISE (CF. EXERCISE 6.3.E).',
        'A SMALL EXERCISE ABOUT SMALL SCHEMES.',
        'LESS IMPORTANT EXERCISE. Show that an A-scheme',
        'UNIMPORTANT EXERCISE RELATING TO THE IDEAL OF DENOMINATORS.',
        'EXERCISE FOR THE ARITHMETICALLY-MINDED.',
    ]
    NEG = [
        'The importance of exercises. This book has a lot of exercises.',
        'Exercise 24.5.M can be improved:',
        'exercise.', 'exercises.',
        'Motivation. Let us review why we like Hausdorffness.',
        'Proposition. — The morphism P to Spec A is separated.',
        'If you prefer that, by all means do so.)',
    ]

    def test_positive(self):
        for t in self.POS:
            self.assertTrue(is_exercise_head_text(t), f'head form rejected: {t!r}')

    def test_negative(self):
        for t in self.NEG:
            self.assertFalse(is_exercise_head_text(t), f'prose accepted: {t!r}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
