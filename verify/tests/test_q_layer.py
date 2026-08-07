"""
test_q_layer.py — regression / acceptance tests for the Q-LAYER (formula
sequence-label audit), the incremental "公式序标层" change (2026-08-07).

Covers:
  * SourceFormulaIndex.norm() — separator folding, prefix stripping, trailing
    letter suffix, unparseable -> None.
  * build_formula_patterns() — derives regex from component count (depth).
  * _extract_summary_tags() — block extraction + tag normalization.
  * _compare() judgment matrix: OK / FABRICATED / INCONSISTENT (duplicate &
    cross-chapter) / MISSING / ignore-skip / S-empty degradation.
  * QLayer.run() no-op gate (formula=None) — neutral metadata, no FAIL.
  * QLayer.run() end-to-end with real temp extract pages + summary .md.
  * Auto-registration (register_all discovers Q after P, order == 17).

Run (stdlib unittest or pytest):
    python verify/tests/test_q_layer.py
    python -m pytest verify/tests/ -q
"""
import os
import sys
import json
import tempfile
import unittest

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SKILL_ROOT not in sys.path:
    sys.path.insert(0, SKILL_ROOT)

from lib.config import BookConfig                                            # noqa: E402
from verify.layers.base import VerifyContext                               # noqa: E402
from verify.layers.q_layer import (                                         # noqa: E402
    QLayer, SourceFormulaIndex, _extract_summary_tags, _compare, FormulaTag,
    build_formula_patterns)
from verify.register_all import LAYER_REGISTRY                             # noqa: E402


def _ctx(ch, start, end, md_file, ext_dir, formula=None):
    cfg = BookConfig(formula=formula)
    return VerifyContext(ch=ch, start=start, end=end, md_file=md_file,
                         ext_dir=ext_dir, config=cfg)


class NormTest(unittest.TestCase):
    def test_variants(self):
        n = SourceFormulaIndex.norm
        cases = [
            ('（11.1-1）', '11.1.1'),
            ('(11.1-1)', '11.1.1'),
            ('11.1-1', '11.1.1'),
            ('Eq. 2.3', '2.3'),
            ('equation 5-2', '5.2'),
            ('式（3,4）', '3.4'),
            ('(8.3)', '8.3'),
            ('2.3a', '2.3a'),
            ('  (  3.2  )  ', '3.2'),
            ('（1.1-1）', '1.1.1'),       # 3-component with dash separator
        ]
        for raw, expected in cases:
            self.assertEqual(n(raw), expected, msg=f"norm({raw!r})")

    def test_unparseable_returns_none(self):
        n = SourceFormulaIndex.norm
        for raw in ['', None, 'abc', '（lol）', 'x.y.z', '1']:
            self.assertIsNone(n(raw), msg=f"norm({raw!r}) should be None")


class ExtractTagsTest(unittest.TestCase):
    def test_extract_and_normalize(self):
        md = ("intro\n\n$$\nE=mc^2 \\tag{3.1}\n$$\n\n"
              "$$\na^2+b^2=c^2 \\tag{3.2}\n$$\n\n"
              "$$\nx+y=z\n$$\n")
        with tempfile.NamedTemporaryFile('w', suffix='.md', encoding='utf-8',
                                         delete=False) as f:
            f.write(md)
            path = f.name
        try:
            tags = _extract_summary_tags(path)
            self.assertEqual(len(tags), 3)
            self.assertEqual(tags[0].normalized, '3.1')
            self.assertEqual(tags[1].normalized, '3.2')
            self.assertEqual(tags[2].normalized, '')  # no \tag -> empty
        finally:
            os.remove(path)


class PatternsTest(unittest.TestCase):
    def test_depth_drives_components(self):
        import re
        p2 = build_formula_patterns(2)
        p3 = build_formula_patterns(3)
        # depth-2 group captures exactly 2 components (1 separator).
        m2 = None
        for p in p2:
            m = re.search(p, 'see 3.2 here')
            if m:
                m2 = m
                break
        self.assertIsNotNone(m2)
        g = m2.group(1)
        self.assertEqual(g.count('.') + g.count('-') + g.count('·') + g.count(','), 1)
        # depth-3 group captures exactly 3 components (2 separators).
        m3 = None
        for p in p3:
            m = re.search(p, 'see 11.1-1 here')
            if m:
                m3 = m
                break
        self.assertIsNotNone(m3)
        g3 = m3.group(1)
        self.assertEqual(g3.count('.') + g3.count('-') + g3.count('·') + g3.count(','), 2)
        # each pattern must compile and carry exactly one capture group.
        for pat in p2 + p3:
            compiled = re.compile(pat)
            self.assertEqual(compiled.groups, 1, msg=f"groups != 1 in {pat!r}")


class CompareTest(unittest.TestCase):
    def _src(self, ch, S):
        src = SourceFormulaIndex('/none', [], True)
        src._by_chapter = {ch: set(S)}
        src._source_text = {x: f'src:{x}' for x in S}
        return src

    def _tags(self, spec):
        # spec: list of raw_tag strings ('' for untagged)
        return [FormulaTag(latex=f"$$ {raw } $$" if raw else "$$ x $$",
                           raw_tag=raw,
                           normalized=SourceFormulaIndex.norm(raw) if raw else '')
                for raw in spec]

    def test_ok(self):
        src = self._src(3, {'3.1', '3.2'})
        tags = self._tags(['3.1', '3.2'])
        fab, inc, miss, rows = _compare(tags, src, 3, True, set())
        self.assertEqual(fab, [])
        self.assertEqual(inc, [])
        self.assertEqual(miss, [])
        self.assertTrue(all(r['status'] == 'OK' for r in rows))

    def test_fabricated(self):
        src = self._src(3, {'3.1', '3.2'})
        tags = self._tags(['3.1', '3.9'])  # 3.9 not in S
        fab, inc, miss, rows = _compare(tags, src, 3, True, set())
        self.assertEqual([r['number'] for r in fab], ['3.9'])
        self.assertEqual(inc, [])
        # 3.2 is in S but absent from the summary -> also reported as MISSING.
        self.assertEqual([r['number'] for r in miss], ['3.2'])

    def test_inconsistent_duplicate(self):
        src = self._src(3, {'3.1', '3.2'})
        tags = self._tags(['3.1', '3.1'])  # duplicate
        fab, inc, miss, rows = _compare(tags, src, 3, True, set())
        self.assertEqual([r['number'] for r in inc], ['3.1'])
        self.assertEqual(fab, [])

    def test_inconsistent_crosschapter(self):
        src = self._src(3, {'3.1', '3.2'})
        tags = self._tags(['3.1', '5.1'])  # 5.1 belongs to ch5
        fab, inc, miss, rows = _compare(tags, src, 3, True, set())
        self.assertEqual([r['number'] for r in inc], ['5.1'])
        self.assertEqual(fab, [])

    def test_missing(self):
        src = self._src(3, {'3.1', '3.2', '3.5'})
        tags = self._tags(['3.1', '3.2'])  # 3.5 absent
        fab, inc, miss, rows = _compare(tags, src, 3, True, set())
        self.assertEqual([r['number'] for r in miss], ['3.5'])
        self.assertEqual(fab, [])
        self.assertEqual(inc, [])

    def test_ignore_skips_fabricated_and_missing(self):
        # 3.9 fabricated, 3.5 missing; both in ignore -> not flagged at all.
        src = self._src(3, {'3.1', '3.5'})
        tags = self._tags(['3.1', '3.9'])
        ig = {'3.5', '3.9'}
        fab, inc, miss, rows = _compare(tags, src, 3, True, ig)
        self.assertEqual(fab, [])
        self.assertEqual(miss, [])
        self.assertTrue(all(r['status'] != 'FABRICATED' and r['status'] != 'MISSING'
                            for r in rows))

    def test_crosschapter_disabled_by_scope(self):
        # When chapter_prefix=False (scope != 2) a foreign-chapter number is
        # judged against S normally (no INCONSISTENT), not as cross-chapter.
        src = self._src(3, {'3.1', '5.1'})
        tags = self._tags(['5.1'])
        fab, inc, miss, rows = _compare(tags, src, 3, False, set())
        self.assertEqual(inc, [])
        self.assertTrue(any(r['status'] == 'OK' and r['number'] == '5.1'
                            for r in rows))

    def test_s_empty_degradation(self):
        # S empty: only structural checks (dup / cross-chapter) + one WARN;
        # no FABRICATED / no MISSING.
        src = self._src(3, set())  # empty S
        tags = self._tags(['3.1', '3.1', '5.1'])  # dup + cross-chapter
        fab, inc, miss, rows = _compare(tags, src, 3, True, set())
        self.assertEqual(fab, [])
        self.assertEqual(miss, [])
        self.assertEqual(sorted(r['number'] for r in inc), ['3.1', '5.1'])
        self.assertTrue(any(r['status'] == 'WARN' for r in rows))


class RunTest(unittest.TestCase):
    def _write_pages(self, ext, texts):
        os.makedirs(ext, exist_ok=True)
        for i, t in enumerate(texts, start=1):
            with open(os.path.join(ext, f'page_{i:03d}.json'), 'w',
                      encoding='utf-8') as f:
                json.dump({'text': [{'text': t}]}, f, ensure_ascii=False)

    def test_noop_gate(self):
        with tempfile.TemporaryDirectory() as d:
            md = os.path.join(d, 'ch3.md')
            with open(md, 'w', encoding='utf-8') as f:
                f.write("$$\nx \\tag{3.1}\n$$\n")
            ext = os.path.join(d, '_extract')
            self._write_pages(ext, ["see (3.1) here"])
            ctx = _ctx(3, 1, 1, md, ext, formula=None)
            res = QLayer().run(ctx)
            self.assertEqual(res.code, 'Q')
            md_res = res.metadata
            self.assertFalse(md_res['q_checked'])
            self.assertEqual(md_res['q_fabricated'], [])
            self.assertEqual(md_res['q_inconsistent'], [])
            self.assertEqual(md_res['q_missing'], [])
            self.assertEqual(md_res['q_rows'], [])

    def test_run_end_to_end(self):
        with tempfile.TemporaryDirectory() as d:
            md = os.path.join(d, 'ch3.md')
            md_text = ("intro\n\n$$\nE=mc^2 \\tag{3.1}\n$$\n\n"
                       "$$\na^2+b^2=c^2 \\tag{3.2}\n$$\n\n"
                       "$$\nx+y=z\n$$\n\n"
                       "$$\nf(t)=t^2 \\tag{5.1}\n$$\n")
            with open(md, 'w', encoding='utf-8') as f:
                f.write(md_text)
            ext = os.path.join(d, '_extract')
            # S = {3.1, 3.2} only; (5.1) is absent from the source pages.
            self._write_pages(ext, ["By (3.1) we get A.",
                                    "And (3.2) gives B."])
            ctx = _ctx(3, 1, 2, md, ext,
                       formula={'type': 3, 'depth': 2, 'scope': 2, 'ignore': []})
            res = QLayer().run(ctx)
            md_res = res.metadata
            self.assertTrue(md_res['q_checked'])
            self.assertEqual(md_res['q_fabricated'], [])
            # 5.1 is cross-chapter -> INCONSISTENT
            self.assertEqual([r['number'] for r in md_res['q_inconsistent']],
                             ['5.1'])
            self.assertEqual(md_res['q_missing'], [])
            # rows include the OK, the cross-chapter INCONSISTENT; S is
            # non-empty so no WARN. 3 numbered tags -> 3 rows (2 OK + 1 inc).
            self.assertEqual(len(md_res['q_rows']), 3)

    def test_run_fabricated_and_missing(self):
        with tempfile.TemporaryDirectory() as d:
            md = os.path.join(d, 'ch3.md')
            md_text = ("$$\nE=mc^2 \\tag{3.1}\n$$\n\n"
                       "$$\ng=x \\tag{3.9}\n$$\n")  # 3.9 fabricated
            with open(md, 'w', encoding='utf-8') as f:
                f.write(md_text)
            ext = os.path.join(d, '_extract')
            # S = {3.1, 3.2, 3.5}; 3.9 not in S, 3.2 & 3.5 missing in summary
            self._write_pages(ext, ["(3.1) A.", "(3.2) B.", "(3.5) C."])
            ctx = _ctx(3, 1, 3, md, ext,
                       formula={'type': 3, 'depth': 2, 'scope': 2, 'ignore': []})
            res = QLayer().run(ctx)
            md_res = res.metadata
            self.assertEqual([r['number'] for r in md_res['q_fabricated']],
                             ['3.9'])
            self.assertEqual(sorted(r['number'] for r in md_res['q_missing']),
                             ['3.2', '3.5'])


class RegistryTest(unittest.TestCase):
    def test_q_registered_after_p(self):
        reg = LAYER_REGISTRY
        self.assertIn('Q', reg.by_code())
        q = reg.by_code()['Q']
        self.assertEqual(q.code, 'Q')
        self.assertEqual(q.order, 17)
        self.assertFalse(q.auto_fixable)
        # must run after P (order 16)
        self.assertGreater(q.order, reg.by_code()['P'].order)


if __name__ == '__main__':
    unittest.main(verbosity=2)
