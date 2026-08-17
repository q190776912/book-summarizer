"""
test_q_layer_formula_regression.py — regression tests for the Q-LAYER formula
sequence-label *anti-cheat / config-validation* behaviour added in the
2026-08-09 hardening pass.

Covers:
  * scope=3 (Kreyszig per-section single-component) happy path: every ``\\tag``
    maps 1:1 to a book-source formula -> all OK, no FAIL.
  * opt-in gate: ``formula=None`` but the summary has ``\\tag`` -> loud
    ``[Q-LAYER WARN]`` to stderr and a neutral (``q_checked=False``) result (no
    silent PASS); ``formula=None`` and no ``\\tag`` -> clean no-op, no WARN.
  * mis-config MUST FAIL, not silently PASS: a single-component book wrongly
    configured as type4/depth2/scope2 yields ``q_inconsistent=[err_row]`` (so
    report.py FAILs the chapter) instead of letting every ``\\tag`` be judged.
  * anti-cheat: deleting all ``\\tag`` from the summary (leaving only
    ``$$...$$``) under a correct scope=3 config produces ``q_missing`` -> FAIL;
    you cannot cheat the audit by stripping tags.
  * ``make_config.detect_formula``: a full-book scan emits the ``formula`` key
    with ``depth==1`` / ``scope==3`` for a Kreyszig-shaped extract (no longer
    xfail; the real scan bug is fixed).
  * global detection must scan ALL pages, not just the first N: a 40-page
    fixture whose two-component form only appears on pages 21-40 is correctly
    classified ``depth=2`` by the full scanner, while a sampled ``[:20]``
    scanner mis-judges ``depth=1`` -> proves "later pages cannot be missed".
  * (optional, skip-if-missing) real Kreyszig corpus: under the correct
    scope=3/depth=1 the ``(N)`` extraction yields a non-empty set, no crash.

Fixtures live in ``config/verify_config/tests/fixtures/q_formula/`` (kreyszig_ch3.md +
kreyszig_ch3_ext/page_*.json).  The real corpus is read-only, never modified.

Run:
    python config/verify_config/tests/test_q_layer_formula_regression.py
    python -m pytest config/verify_config/tests/test_q_layer_formula_regression.py -q
"""
import os
import sys
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

import os
import re
import io
import sys
import json
import glob
import tempfile
import contextlib
import subprocess
import unittest

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from verify_config import BookConfig                                          # noqa: E402
from verify.script.base import VerifyContext                            # noqa: E402
from formula_tag import (                                 # noqa: E402
    QLayer, SourceFormulaIndex, build_formula_patterns)

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           'fixtures', 'q_formula')
KREYSZIG_MD = os.path.join(FIXTURE_DIR, 'kreyszig_ch3.md')
KREYSZIG_EXT = os.path.join(FIXTURE_DIR, 'kreyszig_ch3_ext')
MAKE_CONFIG_PY = os.path.join(_ROOT, 'config/verify_config/make_config.py')
REAL_EXT_DIR = r'D:/study/book/基础/泛函分析导论及应用/_extract'

# Inline copies of make_config's formula-shape regexes, so the global-detection
# test can run its own sampled-vs-full detectors WITHOUT importing make_config
# at module load (make_config reconfigures sys.stdout on import, which is
# unsafe under pytest's output capture).  These mirror config/verify_config/make_config.py.
from lib.regexlib import F_SINGLE_RE as _F_SINGLE_RE, F_DOT_RE as _F_DOT_RE, F_EQ_RE as _F_EQ_RE, F_CN_EQ_RE as _F_CN_EQ_RE


def _ctx(ch, start, end, md_file, ext_dir, formula=None):
    cfg = BookConfig(formula=formula)
    return VerifyContext(ch=ch, start=start, end=end, md_file=md_file,
                         ext_dir=ext_dir, config=cfg)


def _write_pages(ext, texts):
    """Write a contiguous run of page_NNN.json files (1-indexed)."""
    os.makedirs(ext, exist_ok=True)
    for i, t in enumerate(texts, start=1):
        with open(os.path.join(ext, f'page_{i:03d}.json'), 'w',
                  encoding='utf-8') as f:
            json.dump({'text': [{'text': t}]}, f, ensure_ascii=False)


def _write_page_at(ext, i, texts):
    """Write a single page_NNN.json at explicit index ``i``."""
    os.makedirs(ext, exist_ok=True)
    with open(os.path.join(ext, f'page_{i:03d}.json'), 'w',
              encoding='utf-8') as f:
        json.dump({'text': [{'text': t} for t in texts]}, f, ensure_ascii=False)


class SectionHappyPathTest(unittest.TestCase):
    def test_section_n_happy_path_scope3(self):
        # Kreyszig shape: per-section single-component numbers (1)(2) in §3.1,
        # (1) in §3.2, with matching \tag; correct scope=3 config.
        ctx = _ctx(3, 1, 2, KREYSZIG_MD, KREYSZIG_EXT,
                   formula={'type': 1, 'scope': 3, 'ignore': []})
        res = QLayer().run(ctx)
        md = res.metadata
        self.assertTrue(md['q_checked'])
        self.assertEqual(md['q_fabricated'], [])
        self.assertEqual(md['q_inconsistent'], [])
        self.assertEqual(md['q_missing'], [])
        self.assertTrue(md['q_rows'], "expected per-formula audit rows")
        self.assertTrue(all(r['status'] == 'OK' for r in md['q_rows']))


class OptInTest(unittest.TestCase):
    def _run_capture(self, md_text):
        with tempfile.TemporaryDirectory() as d:
            md = os.path.join(d, 'ch3.md')
            with open(md, 'w', encoding='utf-8') as f:
                f.write(md_text)
            ext = os.path.join(d, '_extract')
            os.makedirs(ext, exist_ok=True)
            ctx = _ctx(3, 1, 1, md, ext, formula=None)
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                res = QLayer().run(ctx)
            return res, buf.getvalue()

    def test_optin_warn_emitted(self):
        # formula=None but summary has \tag -> must WARN (not silently pass).
        res, err = self._run_capture("$$\nx \\tag{3.1}\n$$\n")
        self.assertIn('[Q-LAYER WARN]', err)
        self.assertFalse(res.metadata['q_checked'])
        self.assertEqual(res.metadata['q_fabricated'], [])
        self.assertEqual(res.metadata['q_inconsistent'], [])
        self.assertEqual(res.metadata['q_missing'], [])

    def test_optin_clean_noop(self):
        # formula=None and no \tag -> clean neutral no-op, no WARN, no crash.
        res, err = self._run_capture("just prose, no numbered formulas here\n")
        self.assertNotIn('[Q-LAYER WARN]', err)
        self.assertFalse(res.metadata['q_checked'])
        self.assertEqual(res.metadata['q_fabricated'], [])
        self.assertEqual(res.metadata['q_inconsistent'], [])
        self.assertEqual(res.metadata['q_missing'], [])


class MismatchMustFailTest(unittest.TestCase):
    def test_mismatch_scope2_must_fail(self):
        # Single-component source, but a DANGEROUS multi-component config
        # (type4/depth2/scope2, the Kreyszig mis-set).  The layer must FAIL
        # (q_inconsistent=[err_row]) and print [Q-LAYER ERROR] -- NOT silently
        # pass every \tag as cross-chapter INCONSISTENT (which operators would
        # "fix" by deleting all \tag).
        with tempfile.TemporaryDirectory() as d:
            md = os.path.join(d, 'ch3.md')
            with open(md, 'w', encoding='utf-8') as f:
                f.write("$$\nx \\tag{1}\n$$\n\n$$\ny \\tag{2}\n$$\n")
            ext = os.path.join(d, '_extract')
            _write_pages(ext, [
                "3.1-1 Theorem. We set a = 1 (1).",
                "3.1-2 Lemma. We set b = 2 (2).",
            ])
            ctx = _ctx(3, 1, 2, md, ext,
                       formula={'type': 4, 'scope': 2, 'ignore': []})
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                res = QLayer().run(ctx)
            md_res = res.metadata
            self.assertTrue(md_res['q_checked'])
            self.assertTrue(
                md_res['q_inconsistent'],
                "mis-config must FAIL (q_inconsistent non-empty), "
                "not silently PASS")
            self.assertIn('[Q-LAYER ERROR]', buf.getvalue())


class AntiCheatTest(unittest.TestCase):
    def test_anticheat_delete_tags_still_fails(self):
        # Correct scope=3 config, but the operator deletes every \tag from the
        # summary (leaving only $$...$$).  The audit must still FAIL via
        # q_missing (source has formulas, summary has none) -- proving that
        # stripping tags cannot cheat the check.
        with open(KREYSZIG_MD, encoding='utf-8') as f:
            md_text = f.read()
        md_text = re.sub(r'\\tag\{[^}]*\}', '', md_text)  # strip all \tag
        with tempfile.TemporaryDirectory() as d:
            md = os.path.join(d, 'ch3_notags.md')
            with open(md, 'w', encoding='utf-8') as f:
                f.write(md_text)
            ctx = _ctx(3, 1, 2, md, KREYSZIG_EXT,
                       formula={'type': 1, 'scope': 3, 'ignore': []})
            buf = io.StringIO()
            with contextlib.redirect_stderr(buf):
                res = QLayer().run(ctx)
            md_res = res.metadata
            self.assertTrue(md_res['q_checked'])
            self.assertTrue(
                md_res['q_missing'],
                "deleting \\tag must still FAIL via q_missing (not cheat)")


class MakeConfigFormulaKeyTest(unittest.TestCase):
    def test_make_config_emits_formula_key(self):
        # Synthetic Kreyszig-shaped _extract (every section restarts at (1)).
        # Subprocess the fixed make_config.py; the generated verify_config.json
        # must contain 'formula' with type==1 / scope==3 (depth derived from type, not stored).
        with tempfile.TemporaryDirectory() as d:
            ext = os.path.join(d, '_extract')
            os.makedirs(ext, exist_ok=True)
            _write_pages(ext, [
                "3.1-1 Theorem. We set a = 1 (1). 3.1-2 (2). 3.1-3 (3).",
                "3.2-1 Lemma. We set b = 1 (1). 3.2-2 (2).",
            ])
            # phase guard: whole-book extraction must be flagged done.
            with open(os.path.join(ext, '_extraction_done.json'), 'w',
                      encoding='utf-8') as f:
                json.dump({'done': True}, f)
            r = subprocess.run([sys.executable, MAKE_CONFIG_PY, ext],
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0,
                             msg=f"make_config failed: {r.stderr}\n{r.stdout}")
            cfg_path = os.path.join(ext, 'verify_config.json')
            self.assertTrue(os.path.exists(cfg_path),
                            msg=f"verify_config.json not written: {r.stdout}")
            with open(cfg_path, encoding='utf-8') as f:
                cfg = json.load(f)
            self.assertIn('formula', cfg,
                          "make_config must emit the 'formula' key")
            self.assertEqual(cfg['formula']['type'], 1)
            self.assertNotIn('depth', cfg['formula'])
            self.assertEqual(cfg['formula']['scope'], 3)


class GlobalDetectionTest(unittest.TestCase):
    def _inline_detect(self, page_paths):
        """Mirror make_config.detect_formula's classification logic inline so we
        can compare a SAMPLED scanner ([:20]) against a FULL scanner."""
        single = 0
        dotted = 0
        for pg in page_paths:
            with open(pg, encoding='utf-8') as f:
                data = json.load(f)
            texts = [b.get('text', '') for b in data.get('text', [])
                     if isinstance(b, dict)]
            for t in texts:
                single += len(_F_SINGLE_RE.findall(t))
                dotted += (len(_F_DOT_RE.findall(t))
                           + len(_F_EQ_RE.findall(t))
                           + len(_F_CN_EQ_RE.findall(t)))
        if single > dotted and single > 0:
            return 1   # single-component -> depth 1
        if dotted > single and dotted > 0:
            return 2   # two-component   -> depth 2
        return 0

    def test_global_detection_scans_all_pages(self):
        # 40 pages: 1-20 are single-component (N); 21-40 are two-component
        # (C.N) ONLY -- the multi-component form appears LATE in the book.
        with tempfile.TemporaryDirectory() as d:
            ext = os.path.join(d, '_extract')
            os.makedirs(ext, exist_ok=True)
            for i in range(1, 21):
                _write_page_at(ext, i, ["A formula appears (5)."])
            for i in range(21, 41):
                _write_page_at(ext, i,
                               ["Eq. 2.3 and (4.5) and 式（6.7） here."])
            with open(os.path.join(ext, '_extraction_done.json'), 'w',
                      encoding='utf-8') as f:
                json.dump({'done': True}, f)

            all_pages = sorted(glob.glob(os.path.join(ext, 'page_*.json')))
            self.assertEqual(len(all_pages), 40)  # full scan sees 40, not 20
            first20 = all_pages[:20]

            sampling_depth = self._inline_detect(first20)
            full_depth = self._inline_detect(all_pages)

            # The sampled scanner never sees the two-component pages -> wrongly
            # concludes single-component (depth=1).
            self.assertEqual(sampling_depth, 1,
                             "sampled [:20] must mis-judge depth=1")
            # The full scanner sees pages 21-40 -> correctly depth=2.
            self.assertEqual(full_depth, 2,
                             "full scan must see the late two-component form")

            # The PRODUCTION scanner (make_config.detect_formula) also does a
            # full scan; confirm it agrees (so the real code isn't sampling).
            # make_config now lives under config/verify_config (a top-level
            # public module), so put that dir — not the skill root — on sys.path.
            code = (
                "import sys, json;"
                "sys.path.insert(0, %r);"
                "from make_config import detect_formula;"
                "print(json.dumps(detect_formula(sys.argv[1])))"
                % os.path.join(_ROOT, 'config', 'verify_config')
            )
            r = subprocess.run([sys.executable, '-c', code, ext],
                               capture_output=True, text=True, timeout=120)
            self.assertEqual(r.returncode, 0,
                             msg=f"detect_formula failed: {r.stderr}")
            real = json.loads(r.stdout)
            self.assertIsNotNone(real, "detect_formula must not return None")
            self.assertEqual(real['type'], 4,
                             "production detector must read all 40 pages (two-component -> type 4)")
            self.assertNotIn('depth', real)


@unittest.skipUnless(os.path.isdir(REAL_EXT_DIR),
                     f"real corpus missing: {REAL_EXT_DIR}")
class KreyszigRealExtTest(unittest.TestCase):
    def test_kreyszig_real_ext_detection(self):
        # Read-only smoke check: under the correct scope=3/depth=1, the (N)
        # extraction must yield a non-empty set and must not crash.
        src = SourceFormulaIndex(REAL_EXT_DIR, build_formula_patterns(1),
                                 chapter_prefix=False)
        src.build(1, 1, 9999)  # covers all pages; missing pages are skipped
        nums = src.all_numbers()
        self.assertTrue(len(nums) > 0,
                        "scope=3/depth=1 should extract a non-empty (N) set "
                        "from the real Kreyszig corpus")


if __name__ == '__main__':
    unittest.main(verbosity=2)
