"""Figure-group guarantee regression (2026-09-24 Atiyah-Macdonald incident).

Root cause: `lib.figure_io.load_fig_components` refuses ANY silent default —
a config without a Figure group in `ordinal` raises ConfigError and aborts the
whole `verify --all` run at the first chapter that reads figure config. But
the OLD `make_config.py` only emitted a Figure group for HUM books or when the
previous config already carried one: for a normal unnumbered-figures book the
generator produced a config that was *guaranteed* to crash verify, and the
only sanctioned remediation (`make_config.py --force`) regenerated the same
broken config.

Fix under test:
  * `_detect_fig_numbering` — printed-caption series probe (>=2 distinct
    figure numbers; depth = majority component count).
  * `_build_config_dict` — ALWAYS emits an explicit Figure group:
    detected 1/2/3 when a caption series exists, else `type: 0` (UNNUMBERED).
  * fail-closed stays: a hand-stripped config must STILL raise.

Runs under stdlib unittest:
  python config/verify_config/tests/test_fig_group_guarantee.py
"""
import os
import sys
import json
import shutil
import tempfile
import unittest
import subprocess
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

import make_config as MC
from lib import figure_io
from verify_config import ConfigError

MAKE_CLI = os.path.join(_ROOT, "config/verify_config/make_config.py")


def _page(texts):
    return {"text": [{"text": t, "poly": [0, 200, 100, 210, 100, 220, 0, 220]}
                     for t in texts]}


def _mk_ext(pages, chapter=True):
    ext = tempfile.mkdtemp(prefix="figgate_")
    if chapter:
        with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
            json.dump({"chapters": [{"ch": 1, "start": 1,
                                     "end": len(pages) or 1}]}, f)
        with open(os.path.join(ext, "_extraction_done.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"done": True}, f)
    for i, p in enumerate(pages, 1):
        with open(os.path.join(ext, "page_%03d.json" % i), "w",
                  encoding="utf-8") as f:
            json.dump(p, f)
    return ext


class TestDetectFigNumbering(unittest.TestCase):
    def _det(self, texts):
        ext = _mk_ext([_page(texts)], chapter=False)
        try:
            return MC._detect_fig_numbering(ext)
        finally:
            shutil.rmtree(ext, ignore_errors=True)

    def test_two_level_series(self):
        d, labels = self._det(["Figure 1.1 The system", "Figure 1.2 Second caption"])
        self.assertEqual(d, 2)
        self.assertIn("Figure", labels)

    def test_global_integer_series(self):
        d, labels = self._det(["Fig. 3 Some caption", "Fig. 4 Another caption"])
        self.assertEqual(d, 1)
        self.assertIn("Fig", labels)

    def test_three_level_series(self):
        d, _ = self._det(["Figure 1.2.3 cap", "Figure 1.2.4 cap"])
        self.assertEqual(d, 3)

    def test_cjk_series(self):
        d, labels = self._det(["图 2.1 系统框图", "图 2.2 另一个图"])
        self.assertEqual(d, 2)
        self.assertEqual(labels, ["图"])

    def test_cross_reference_only_is_not_a_series(self):
        # Single distinct number repeated in prose = cross-references, not
        # captions -> must NOT fake a numbering scheme.
        d, _ = self._det(["see Figure 7 above", "as in Figure 7", "cf. Figure 7"])
        self.assertEqual(d, 0)

    def test_no_figures(self):
        d, labels = self._det(["Theorem 1.1 Every ring has an identity.",
                               "Proof. Consider the ideal."])
        self.assertEqual(d, 0)
        self.assertEqual(labels, [])


class TestFigureGroupGuarantee(unittest.TestCase):
    """End-to-end: make_config output must always satisfy load_fig_components."""

    def _gen(self, page_texts):
        ext = _mk_ext([_page(page_texts)])
        rc = subprocess.run([sys.executable, MAKE_CLI, ext], cwd=_ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=300, encoding="utf-8", errors="replace")
        self.assertEqual(rc.returncode, 0,
                         "make_config failed: %s%s" % ((rc.stdout or "")[-400:],
                                                       (rc.stderr or "")[-400:]))
        return ext

    def _ordinal(self, ext):
        with open(os.path.join(ext, "verify_config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        seg = cfg.get("ch", cfg)
        return seg.get("ordinal") or []

    def test_no_caption_book_still_gets_type0_group_and_no_crash(self):
        ext = self._gen(["定理 1.1 每个环都有单位元。", "证明：考虑理想 I。"])
        try:
            figs = [g for g in self._ordinal(ext)
                    if any(figure_io._is_fig_kw(nm) for nm in g.get("name", []))]
            self.assertEqual(len(figs), 1,
                             "generated config must carry exactly one figure group")
            self.assertEqual(figs[0]["type"], 0)
            # the consumer that crashed the AM run must now load cleanly
            self.assertEqual(figure_io.load_fig_components(ext), 0)
        finally:
            shutil.rmtree(ext, ignore_errors=True)

    def test_caption_book_gets_detected_depth(self):
        ext = self._gen(["Theorem 1.1 identity exists.",
                         "Figure 1.1 diagram", "Figure 1.2 another diagram"])
        try:
            figs = [g for g in self._ordinal(ext)
                    if any(figure_io._is_fig_kw(nm) for nm in g.get("name", []))]
            self.assertTrue(figs)
            self.assertEqual(figs[0]["type"], 2)
            self.assertIn("Figure", figs[0]["name"])
        finally:
            shutil.rmtree(ext, ignore_errors=True)

    def test_fail_closed_preserved(self):
        # Regression guard for the OPPOSITE direction: a config with the figure
        # group hand-stripped must STILL raise (no silent default may return).
        ext = _mk_ext([_page(["定理 1.1 每个环都有单位元。"])])
        try:
            with open(os.path.join(ext, "verify_config.json"), "w",
                      encoding="utf-8") as f:
                json.dump({"ordinal": [{"type": 2, "name": ["定理"], "scope": 2}],
                           "language": "cn"}, f)
            with self.assertRaises(ConfigError):
                figure_io.load_fig_components(ext)
        finally:
            shutil.rmtree(ext, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
