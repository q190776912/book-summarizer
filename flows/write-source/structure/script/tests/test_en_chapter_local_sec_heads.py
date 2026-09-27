"""English chapter-local single-number section heads (Shafarevich shape).

Basic Algebraic Geometry 1 (3rd ed.) prints per-chapter sections as bare
``N Title`` heads that RESTART at 1 every chapter (ch4: ``1 Definition and
Basic Properties`` p249, ``2 Applications...`` p262, ``4 Singularities`` p286),
with LOCAL dotted subsections ``N.M Title`` underneath.  The book scans with
``chapter_local_numbering=True`` (丘维声 mode), but that mode's § channel
(`SEC_GLOBAL_GLUE` + ``_glue_title_ok``) requires ≥2 Han chars — for an
English book EVERY section vanished (sections=0 for all 5 chapters, the
regression that motivated this increment).

Feature under test (scan_skeleton ``_cln_en_title_ok`` EN channel, active only
when ``language == 'en'``): a bare ``N Title`` line is promoted to a SEC row
keyed ``N`` ONLY when

  * Title-Case noun phrase (multi-word: non-first words uppercase or in the
    function-word whitelist; single word allowed), 2..60 chars,
  * no digit / dot / math operator inside the title (kills cross-reference and
    formula residue lines), no sentence-final punctuation,
  * normalized title != the chapter title (kills the running header band —
    this book repeats ``N SectionTitle`` at y≈98 on EVERY page, and a real
    head may sit AT the top of a fresh page, so a y guard is impossible),
  * no item-label word + number (``3 Theorem 12`` style residue),
  * and the sequence latch accepts it: first hit must be N==1, later hits only
    N == current+1 (out-of-sequence exercise heads are rejected).

Chinese books (language default 'cn') never enter the EN branch — zero
regression for the 丘维声 channel.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_en_chapter_local_sec_heads.py
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

import scan_skeleton as S


def _mk_pages(d, pages, ch_map=None):
    """pages = [[line, ...], ...] -> one page_%03d.json each, ONE BLOCK PER LINE
    (scan() consumes `ln` after the per-line normalisation, i.e. it evaluates
    the last line of each block — line-level blocks mirror this book's OCR).
    Blocks carry a body-band poly (y=300, w=600 <= _GLUE_MAX_WIDTH): the EN
    channel keeps the same width guard as the CN GLUE channel."""
    for i, blocks in enumerate(pages, start=1):
        fp = os.path.join(d, f"page_{i:03d}.json")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"text": [{"text": b,
                                 "poly": [60, 300, 660, 300, 660, 330, 60, 330]}
                                for b in blocks],
                       "formulas": []}, f)
    if ch_map is None:
        ch_map = {"chapters": [{"ch": 4, "name": "Intersection Numbers",
                                "start": 1, "end": 9},
                               {"ch": 1, "name": "Basic Notions",
                                "start": 1, "end": 9}]}
    with open(os.path.join(d, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump(ch_map, f)


def _secs(rows):
    return {str(r[2]): (r[3] or '') for r in rows if r[1] == 'SEC'}


class TestEnChapterLocalSecHeads(unittest.TestCase):
    # 真实印面形态（ch4 §1..§4 + 局部小节 1.1..；页眉带复本按行入页）
    CH4 = {
        "chapters": [{"ch": 4, "name": "Intersection Numbers",
                      "start": 1, "end": 3}],
    }

    def _scan(self, d, ch, n, language='en', cln=True):
        return S.scan(d, ch, 1, n, 'three-level',
                      section_depths=[1, 1, 2], chapter_first=True,
                      chapter_local_numbering=cln, language=language)

    def test_positive_sections_and_local_subs(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["1 Definition and Basic Properties",
                 "1.1 The Class Group",
                 "body prose continues here for a while without headings",
                 "1.2 Additivity"],
                ["2 Applications of Intersection Numbers",
                 "2.1 Bezout Theorem in Projective Space",
                 "4 Intersection Numbers",       # running head (== chapter)
                 ],
                ["2.2 Varieties over the Reals",
                 "3 Birational Maps of Surfaces",
                 "3.1 Blowups of Surfaces",
                 "4 Singularities"],              # single-word real head
            ], ch_map=self.CH4)
            secs = _secs(self._scan(d, 4, 3))
            self.assertEqual({k for k in secs if '.' not in k},
                             {'1', '2', '3', '4'})
            self.assertEqual(secs['4'], 'Singularities')
            self.assertIn('1.1', secs)
            self.assertIn('2.1', secs)
            self.assertIn('3.1', secs)
            self.assertNotIn('4 Intersection Numbers', secs.values())

    def test_running_head_band_does_not_kill_top_of_page_head(self):
        # EN channel must NOT impose a y floor: real heads print at page top
        # for sections starting on a fresh page. (No poly => y None passes;
        # the negative control below is the chapter-title header rejection.)
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["1 First Section Head",
                 "2 Second Section Head"],       # on the SAME page, top band
            ], ch_map=self.CH4)
            secs = _secs(self._scan(d, 4, 1))
            self.assertIn('1', secs)
            self.assertIn('2', secs)

    def test_negative_fp_classes_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["1 Definition and Basic Properties",
                 "9 If D C C1 x C2 is a divisor, prove the inequality",  # exer
                 "3 Suppose that f is given by",                          # exer
                 "2.1 and the result follows from the previous theorem",  # ref
                 "2 2.10 3.4 4.5",                                        # number soup
                 "2 Applications of Intersection Numbers",                # real §2
                 "3 Theorem 12",                                          # item head
                 ],
                ["4 Intersection Numbers",           # running head == chapter
                 "3 Birational Maps of Surfaces"],   # real §3
            ], ch_map=self.CH4)
            secs = _secs(self._scan(d, 4, 2))
            self.assertEqual({k for k in secs if '.' not in k}, {'1', '2', '3'})
            self.assertNotIn('2', [k for k in secs if k.startswith('2.')])

    def test_sequence_latch_requires_restart_at_1(self):
        # A chapter whose first bare-N line is NOT 1 must seed nothing until a
        # genuine 1 shows up (kills mid-run exercise renumbering).
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["4 Singularities",               # out-of-sequence: no seed
                 "body text line here"],
                ["1 Algebraic Curves in the Plane",
                 "2 Closed Sets",
                 "5 Dimension"],                  # gap -> rejected
            ])
            secs = _secs(self._scan(d, 1, 2))
            self.assertEqual({k for k in secs if '.' not in k}, {'1', '2'})
            self.assertNotIn('4', secs)
            self.assertNotIn('5', secs)

    def test_cn_books_unaffected(self):
        # language='cn' (default): the EN channel is OFF — a bare EN head must
        # NOT be promoted through it (丘维声 GLUE needs ≥2 Han chars).
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["1 Definition and Basic Properties",
                 "2 Applications of Something"],
            ])
            secs = _secs(self._scan(d, 4, 1, language='cn'))
            self.assertNotIn('1', secs)
            self.assertNotIn('2', secs)

    def test_flag_off_no_en_promotion(self):
        # chapter_local_numbering=False (every other EN book): zero effect —
        # bare "N Title" lines never enter the EN channel.
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ["1 Definition and Basic Properties",
                 "2 Applications of Intersection Numbers"],
            ])
            secs = _secs(self._scan(d, 4, 1, cln=False))
            self.assertNotIn('1', secs)
            self.assertNotIn('2', secs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
