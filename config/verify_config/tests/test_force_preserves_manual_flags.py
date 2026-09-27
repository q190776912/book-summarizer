"""`--force` must not silently drop human-declared structure flags (2026-09-28).

Root cause: `make_config.py --force` rescans the whole book and OVERWRITES
`verify_config.json`.  The item-numbering ledger (`ordinal`) and the operator
keys of `formula` are re-attached from the previous file, but the *structure*
flags a human declared while setting the book config up
(`chapter_local_numbering`, `chapter_local_sections`, `chapter_scoped_items`,
`gm_bare_numbered`, `exercise_region_headings`) have **no detector** — by
design, since deciding "do §N restart every chapter?" needs cross-page
semantics any heuristic would mis-fire on for other books.

Shafarevich《Basic Algebraic Geometry 1》was hit by exactly this: a `--force`
run dropped `chapter_local_numbering: true`, scan_skeleton fell back to the
generic `§C.S` route, and the whole book came out with `sections=0` while the
config looked perfectly normal (a false green that only explodes three steps
later).

Fix under test: `_load_old_manual_flags` + its use in `_build_config_dict` —
re-attach declared-true flags from the previous config (both legacy-flat and
outer-map layouts), never injecting `False`, and never overriding a key the
detector itself wrote this round.

Runs under stdlib unittest:
  python config/verify_config/tests/test_force_preserves_manual_flags.py
"""
import json
import os
import shutil
import subprocess
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

import make_config as MC

MAKE_CLI = os.path.join(_ROOT, "config/verify_config/make_config.py")


def _page(texts):
    return {"text": [{"text": t, "poly": [0, 200, 100, 210, 100, 220, 0, 220]}
                     for t in texts]}


def _mk_ext(pages, chapter_ranges=None):
    ext = tempfile.mkdtemp(prefix="mf_")
    rngs = chapter_ranges or [{"ch": 1, "start": 1, "end": len(pages) or 1}]
    with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump({"chapters": rngs}, f)
    with open(os.path.join(ext, "_extraction_done.json"), "w",
              encoding="utf-8") as f:
        json.dump({"done": True}, f)
    for i, p in enumerate(pages, 1):
        with open(os.path.join(ext, "page_%03d.json" % i), "w",
                  encoding="utf-8") as f:
            json.dump(p, f)
    return ext


class TestLoadOldManualFlags(unittest.TestCase):
    def _w(self, cfg):
        ext = _mk_ext([_page(["Theorem 1.1 x"])])
        p = os.path.join(ext, "verify_config.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        self._ext = ext
        return p

    def tearDown(self):
        if getattr(self, "_ext", None):
            shutil.rmtree(self._ext, ignore_errors=True)
            self._ext = None

    def test_flat_format_true_only(self):
        p = self._w({"ordinal": [], "chapter_local_numbering": True,
                     "chapter_scoped_items": False,
                     "exercise_region_headings": ["Exercises"]})
        out = MC._load_old_manual_flags(p)
        self.assertEqual(out, {"chapter_local_numbering": True,
                               "exercise_region_headings": ["Exercises"]})

    def test_map_format_reads_matching_section_key(self):
        p = self._w({"ch": {"ordinal": []},
                     "appendix": {"ordinal": [], "gm_bare_numbered": True}})
        self.assertEqual(MC._load_old_manual_flags(p, "appendix"),
                         {"gm_bare_numbered": True})
        self.assertEqual(MC._load_old_manual_flags(p, "ch"), {})

    def test_missing_file_is_silent(self):
        self.assertEqual(MC._load_old_manual_flags(
            os.path.join(tempfile.gettempdir(), "nope_absent.json")), {})


class TestForceKeepsFlagsEndToEnd(unittest.TestCase):
    PAGES = [_page(["Theorem 1.1 Every variety has a tangent space.",
                    "Proposition 2.3 A second statement."])]

    def _run(self, initial_cfg):
        ext = _mk_ext(self.PAGES)
        try:
            with open(os.path.join(ext, "verify_config.json"), "w",
                      encoding="utf-8") as f:
                json.dump(initial_cfg, f)
            rc = subprocess.run([sys.executable, MAKE_CLI, ext, "--force"],
                                cwd=_ROOT, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=300,
                                encoding="utf-8", errors="replace")
            self.assertEqual(rc.returncode, 0,
                             "make_config failed: %s%s" % ((rc.stdout or "")[-400:],
                                                           (rc.stderr or "")[-400:]))
            with open(os.path.join(ext, "verify_config.json"),
                      encoding="utf-8") as f:
                return json.load(f)
        finally:
            shutil.rmtree(ext, ignore_errors=True)

    def test_flat_legacy_flag_survives_force(self):
        cfg = self._run({"ordinal": [{"type": 2, "name": ["Theorem"],
                                      "scope": 2}],
                         "language": "en", "chapter_first": True,
                         "chapter_local_numbering": True})
        ch = cfg.get("ch", cfg)
        self.assertIs(ch.get("chapter_local_numbering"), True,
                      "--force dropped a human-declared structure flag")

    def test_map_format_flag_survives_force(self):
        cfg = self._run({"ch": {"ordinal": [{"type": 2, "name": ["Theorem"],
                                             "scope": 2}],
                                "language": "en",
                                "chapter_local_numbering": True}})
        self.assertIs(cfg["ch"].get("chapter_local_numbering"), True)

    def test_absent_flag_is_never_injected(self):
        # Zero regression: a book that never declared the flag must not gain it.
        cfg = self._run({"ordinal": [{"type": 2, "name": ["Theorem"],
                                      "scope": 2}],
                         "language": "en", "chapter_first": True})
        ch = cfg.get("ch", cfg)
        self.assertNotIn("chapter_local_numbering", ch)


if __name__ == "__main__":
    unittest.main(verbosity=2)
