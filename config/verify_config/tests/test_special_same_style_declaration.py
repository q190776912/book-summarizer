"""An appendix that was **adjudicated** "same numbering style as the body" must
not keep emitting a warning no remedy can silence (2026-09-29).

Root cause (Serre《Linear Representations of Finite Groups》, GTM 42): the book
has one unlettered appendix whose items are numbered exactly like the body
(``Theorem 29``, ``Proposition 38`` — no letter slot).  ``make_config``
therefore correctly refuses to write an ``"appendix"`` sub-config (it would be
a byte-for-byte copy of ``"ch"``), but ``ConfigLoader._warn_missing_special_config``
cannot tell "scanned, judged same-style" apart from "never scanned at all" and
prints, on **every** verify run:

    [CONFIG] ⚠ 附录/补篇配置缺失 … 补救：make_config.py <extract_dir> --force
    （会自动补写缺失的 appendix/supplement 子配置）

That remedy is unactionable: re-running ``--force`` re-reaches the same verdict
and re-prints the same warning forever.  A warning whose prescribed fix can
never satisfy it is a gate-chain bug, so the verdict is now **recorded**:
``verify_config.json`` carries ``_special_same_style: ["appendix"]`` and the
loader stays silent only for kinds actually listed there.

Judgement points under test:
  * producer: same-style verdict -> recorded; letter-slot verdict -> sub-config
    written instead; kind never scanned (no chapters / no pages) -> NOT recorded
    (fallback stays visible);
  * ``--force`` writes the declaration into the outer map;
  * incremental (non ``--force``) upgrade records it too;
  * consumer: declared kind -> no stderr, undeclared kind -> warning, and the
    warning's remedy text now points at the record.

Runs under stdlib unittest:
  python config/verify_config/tests/test_special_same_style_declaration.py
"""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "config", "verify_config")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import make_config as MC
import verify_config as VC
from verify_config import ConfigLoader, MAP_KEY_SPECIAL_SAME_STYLE


def _page(texts):
    return {"text": [{"text": t, "poly": [0, 200, 100, 210, 100, 220, 0, 220]}
                     for t in texts]}


def _quiet(fn, *a, **kw):
    """Run a producer entry point swallowing its stdout (the console here may
    be cp936; the reports are Chinese by design)."""
    with redirect_stdout(io.StringIO()):
        return fn(*a, **kw)


def _run_main(argv):
    """`make_config.main()` reads sys.argv (CLI entry) — drive it that way."""
    saved = sys.argv
    sys.argv = [saved[0]] + list(argv)
    try:
        with redirect_stdout(io.StringIO()):
            return MC.main()
    finally:
        sys.argv = saved


def _mk_ext(pages, chapters):
    """Synthetic finished-extraction _extract dir (pages[i] -> page_{i+1})."""
    ext = tempfile.mkdtemp(prefix="sss_")
    with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump({"chapters": chapters}, f)
    with open(os.path.join(ext, "_extraction_done.json"), "w", encoding="utf-8") as f:
        json.dump({"done": True}, f)
    for i, p in enumerate(pages, 1):
        with open(os.path.join(ext, "page_%03d.json" % i), "w", encoding="utf-8") as f:
            json.dump(p, f)
    return ext


BODY_MAP = [{"ch": 1, "kind": 1, "start": 1, "end": 1, "name": "Chapter I"},
            {"ch": "appendix", "kind": 2, "start": 2, "end": 2, "name": "Appendix"}]


# ---------------------------------------------------------------------------
# producer — _generate_special_verify_configs records the verdict
# ---------------------------------------------------------------------------
class TestProducerVerdict(unittest.TestCase):
    """The three outcomes must be distinguishable in the returned dict."""

    def setUp(self):
        self._saved_build = MC._build_config_dict

    def tearDown(self):
        MC._build_config_dict = self._saved_build
        for attr in ("_ext",):
            ext = getattr(self, attr, None)
            if ext:
                shutil.rmtree(ext, ignore_errors=True)
                setattr(self, attr, None)

    def _fake_build(self, ordinal, cfg=None):
        def _f(extract_dir, cfg_path, **kw):
            return (cfg or {"ordinal": [{"type": ordinal, "name": ["Theorem"],
                                         "scope": 2}]},
                    None, [["Theorem"]], ordinal, 1)
        MC._build_config_dict = _f

    def test_same_style_verdict_is_recorded(self):
        """Appendix chapters scanned, numbering stays numeric-chapter (type 1)
        -> no sub-config, but the kind IS recorded as adjudicated."""
        self._ext = _mk_ext([_page(["Theorem 1 x"]), _page(["Theorem 2 x"])],
                            BODY_MAP)
        self._fake_build(1)          # 编号族 = type 1（正文式），非 13/14
        out = _quiet(MC._generate_special_verify_configs, self._ext)
        self.assertIsNone(out["appendix"])
        self.assertEqual(out["same_style"], ["appendix"])

    def test_letter_slot_verdict_is_not_recorded(self):
        """Real letter-slot appendix (type 13) -> sub-config produced instead."""
        self._ext = _mk_ext([_page(["Theorem 1 x"]), _page(["Theorem A.1 x"])],
                            BODY_MAP)
        self._fake_build(VC.ORDINAL_APP)
        out = _quiet(MC._generate_special_verify_configs, self._ext)
        self.assertIsNotNone(out["appendix"])
        self.assertEqual(out["same_style"], [])

    def test_unscanned_kind_is_not_recorded(self):
        """Detected appendix chapter WITHOUT page range = no verdict at all ->
        must NOT be silenced downstream (the Lee 2e silent-loss path)."""
        self._ext = _mk_ext([_page(["Theorem 1 x"])],
                            [{"ch": 1, "kind": 1, "start": 1, "end": 1,
                              "name": "Chapter I"},
                             {"ch": "appendix", "kind": 2, "start": 99,
                              "end": 99, "name": "Appendix"}])
        self._fake_build(1)
        out = _quiet(MC._generate_special_verify_configs, self._ext)
        self.assertEqual(out["same_style"], [])

    def test_book_without_appendix_is_not_recorded(self):
        """No appendix chapter in chapter_map -> nothing to adjudicate."""
        self._ext = _mk_ext([_page(["Theorem 1 x"])],
                            [{"ch": 1, "kind": 1, "start": 1, "end": 1,
                              "name": "Chapter I"}])
        self._fake_build(1)
        out = _quiet(MC._generate_special_verify_configs, self._ext)
        self.assertEqual(out["same_style"], [])


# ---------------------------------------------------------------------------
# --force: the verdict reaches the file
# ---------------------------------------------------------------------------
class TestForceWritesDeclaration(unittest.TestCase):
    def setUp(self):
        self._saved = MC._generate_special_verify_configs

    def tearDown(self):
        MC._generate_special_verify_configs = self._saved
        if getattr(self, "_ext", None):
            shutil.rmtree(self._ext, ignore_errors=True)

    def test_same_style_key_present_after_force(self):
        self._ext = _mk_ext([_page(["Theorem 1 x"]), _page(["Theorem 2 x"])],
                            BODY_MAP)
        MC._generate_special_verify_configs = lambda e: {
            "appendix": None, "supplement": None, "same_style": ["appendix"]}
        self.assertEqual(
            _run_main([self._ext, "--force"]), 0)
        with open(os.path.join(self._ext, "verify_config.json"),
                  encoding="utf-8") as f:
            data = json.load(f)
        self.assertNotIn("appendix", data)
        self.assertEqual(data.get(MAP_KEY_SPECIAL_SAME_STYLE), ["appendix"])

    def test_no_key_when_subconfig_written(self):
        """A book that DID get an appendix sub-config must not carry a stale
        same-style declaration for the same kind."""
        self._ext = _mk_ext([_page(["Theorem 1 x"]), _page(["Theorem 2 x"])],
                            BODY_MAP)
        MC._generate_special_verify_configs = lambda e: {
            "appendix": {"ordinal": [{"type": 13, "name": ["Theorem"],
                                      "scope": 2}]},
            "supplement": None, "same_style": []}
        self.assertEqual(_run_main([self._ext, "--force"]), 0)
        with open(os.path.join(self._ext, "verify_config.json"),
                  encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("appendix", data)
        self.assertNotIn(MAP_KEY_SPECIAL_SAME_STYLE, data)


# ---------------------------------------------------------------------------
# incremental upgrade (non --force) — the route an existing book takes
# ---------------------------------------------------------------------------
class TestIncrementalUpgradeRecordsVerdict(unittest.TestCase):
    def setUp(self):
        self._saved = MC._generate_special_verify_configs

    def tearDown(self):
        MC._generate_special_verify_configs = self._saved
        if getattr(self, "_ext", None):
            shutil.rmtree(self._ext, ignore_errors=True)

    def _write(self, cfg):
        self._ext = _mk_ext([_page(["Theorem 1 x"]), _page(["Theorem 2 x"])],
                            BODY_MAP)
        self._cfg_path = os.path.join(self._ext, "verify_config.json")
        with open(self._cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f)
        return self._cfg_path

    def _read(self, p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)

    def test_records_and_keeps_existing_keys(self):
        p = self._write({"ch": {"ordinal": [{"type": 1, "name": ["Theorem"],
                                             "scope": 1}], "strict": False},
                         "appendix": {"ordinal": [{"type": 2}]}})
        MC._generate_special_verify_configs = lambda e: {
            "appendix": None, "supplement": None, "same_style": ["supplement"]}
        self.assertEqual(_quiet(MC._upgrade_missing_special_keys,
                                self._ext, p), 0)
        data = self._read(p)
        self.assertEqual(data.get(MAP_KEY_SPECIAL_SAME_STYLE), ["supplement"])
        self.assertEqual(data["ch"]["strict"], False,
                         "incremental upgrade must not touch calibrated keys")
        self.assertIn("appendix", data)

    def test_idempotent_when_already_declared(self):
        p = self._write({"ch": {"ordinal": [{"type": 1, "name": ["Theorem"],
                                             "scope": 1}]},
                         MAP_KEY_SPECIAL_SAME_STYLE: ["appendix"]})
        MC._generate_special_verify_configs = lambda e: {
            "appendix": None, "supplement": None, "same_style": ["appendix"]}
        self.assertEqual(_quiet(MC._upgrade_missing_special_keys,
                                self._ext, p), 0)
        self.assertEqual(self._read(p).get(MAP_KEY_SPECIAL_SAME_STYLE),
                         ["appendix"])

    def test_absent_verdict_leaves_file_untouched(self):
        """No scan verdict (kind undetected / no pages) -> no declaration, so
        the fallback warning stays visible downstream."""
        p = self._write({"ch": {"ordinal": [{"type": 1, "name": ["Theorem"],
                                             "scope": 1}]}})
        MC._generate_special_verify_configs = lambda e: {
            "appendix": None, "supplement": None, "same_style": []}
        self.assertEqual(_quiet(MC._upgrade_missing_special_keys,
                                self._ext, p), 0)
        self.assertNotIn(MAP_KEY_SPECIAL_SAME_STYLE, self._read(p))


# ---------------------------------------------------------------------------
# consumer — ConfigLoader honours the declaration
# ---------------------------------------------------------------------------
class TestLoaderHonoursDeclaration(unittest.TestCase):
    def setUp(self):
        VC._SPECIAL_FALLBACK_WARNED.clear()

    def tearDown(self):
        VC._SPECIAL_FALLBACK_WARNED.clear()
        if getattr(self, "_ext", None):
            shutil.rmtree(self._ext, ignore_errors=True)

    def _loader(self, cfg, chapters=None):
        self._ext = _mk_ext([_page(["Theorem 1 x"]), _page(["Theorem 2 x"])],
                            chapters or BODY_MAP)
        with open(os.path.join(self._ext, "verify_config.json"), "w",
                  encoding="utf-8") as f:
            json.dump(cfg, f)
        return ConfigLoader(self._ext, self._ext, extra_ignore=None)

    def _call(self, loader, ch):
        buf = io.StringIO()
        with redirect_stderr(buf):
            loader.config_for_chapter(ch)
        return buf.getvalue()

    def _body(self):
        return {"ordinal": [{"type": 1, "name": ["Theorem"], "scope": 1}]}

    def test_declared_kind_falls_back_silently(self):
        loader = self._loader({"ch": self._body(),
                              MAP_KEY_SPECIAL_SAME_STYLE: ["appendix"]})
        self.assertEqual(loader.special_same_style, {"appendix"})
        self.assertEqual(self._call(loader, "appendix"), "",
                         "adjudicated same-style fallback must not warn")

    def test_undeclared_kind_still_warns(self):
        loader = self._loader({"ch": self._body()})
        err = self._call(loader, "appendix")
        self.assertIn("附录/补篇配置缺失", err)
        self.assertEqual(loader.config_for_chapter("appendix").ordinal[0].scope,
                         1, "fallback still uses the body config")

    def test_declaration_scopes_per_kind(self):
        """Declaring appendix must NOT silence an un-scanned supplement."""
        chapters = BODY_MAP + [{"ch": "supplement", "kind": 3, "start": 2,
                                "end": 2, "name": "Supplement"}]
        loader = self._loader({"ch": self._body(),
                              MAP_KEY_SPECIAL_SAME_STYLE: ["appendix"]},
                              chapters=chapters)
        self.assertEqual(loader.chapter_kind("supplement"),
                         VC.KIND_SUPPLEMENT, "fixture routes supplement kind")
        self.assertEqual(self._call(loader, "appendix"), "")
        VC._SPECIAL_FALLBACK_WARNED.clear()
        self.assertIn("补篇配置缺失", self._call(loader, "supplement"))

    def test_warning_remedy_is_actionable(self):
        """The remedy line must name the record that actually silences it —
        a bare '--force' promise is what made this warning unfixable."""
        loader = self._loader({"ch": self._body()})
        err = self._call(loader, "appendix")
        self.assertIn(MAP_KEY_SPECIAL_SAME_STYLE, err)
        self.assertIn("同体例", err)

    def test_legacy_flat_format_unaffected(self):
        """Flat (pre-map) configs keep the historic warning — zero regression."""
        loader = self._loader(self._body())
        self.assertEqual(loader.special_same_style, set())
        self.assertIn("附录/补篇配置缺失", self._call(loader, "appendix"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
