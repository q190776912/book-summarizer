"""Regression / acceptance tests for the "rule H — 书级配置强制前置" change
(book-summarizer incremental change B, 2026-08-06) — REWRITTEN for the
verify_config v2 schema (GroupConfig ARRAY, not int `ordinal`).

Covers the new mandatory book-config gate:

  * `lib.config.ConfigLoader.require_complete()` — the gate logic.
  * `verify/verify_chapter.py` entry — `require_complete()` invoked inside
    `_make_loader()`; `main()` catches `ConfigError` -> print + exit 2.
  * `extract/scan_skeleton.py` entry — constructs `ConfigLoader`, calls
    `require_complete()`, reads `loader.book.primary_type` (int).
  * `verify/make_config.py` — best-effort starter-config generator (now emits
    the v2 array form).

v2 schema contract (per SKILL.md 规则 H / references/verify_config_schema_v2_design.md):
  * `ordinal` is a LIST of `GroupConfig` dicts
    (`{type:int 1..7, name:[str], depth:int>=1, scope:1|2|3}`).
  * `BookConfig.from_dict` REJECTS the old int/str `ordinal` with a ConfigError
    carrying the "make_config --force" migration hint.
  * `require_complete()`:
      (a) file ABSENT            -> WARNING + keep default (single uncat
                                    GroupConfig, primary_type=3, back-compat),
                                    verify/scan must NOT hard-fail.
      (b) file ABSENT + allow_absent=False -> raise ConfigError.
      (c) file PRESENT but no `ordinal` array -> raise ConfigError (exit 2).
      (d) file PRESENT + legal ordinal array -> no raise.
  * R6 override: `from_dict` does NOT auto-append an uncat group, and
    `require_complete` does NOT hard-require one. A config declaring groups
    with NO uncat group is ACCEPTED; `uncat_group()` falls back to `ordinal[0]`.

No pytest dependency: runs under stdlib unittest
  python verify/tests/test_config_complete.py
or
  python -m unittest verify.tests.test_config_complete -v
(verify.tests is not a package in this repo, so prefer the direct-module form.)
"""
import os
import sys
import json
import tempfile
import subprocess
import unittest
import warnings

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if SKILL_ROOT not in sys.path:
    sys.path.insert(0, SKILL_ROOT)

from lib.config import (ConfigLoader, ConfigError, BookConfig, GroupConfig)  # noqa: E402

PY = sys.executable
VERIFY_CLI = os.path.join(SKILL_ROOT, "verify", "verify_chapter.py")
SCAN_CLI = os.path.join(SKILL_ROOT, "extract", "scan_skeleton.py")
MAKE_CLI = os.path.join(SKILL_ROOT, "verify", "make_config.py")

# Real corpus book (read-only use; generated files cleaned up afterwards).
REAL_HAS_CFG = r"D:\study\book\基础\泛函分析导论及应用\_extract"      # v2 ordinal array, type=3

# A real NO_CFG book is discovered at runtime (the corpus changes); we do not
# hard-code one because a book that used to lack config may gain one.
CORPUS_ROOT = r"D:\study\book"


def _find_real_no_cfg_book():
    """Return the _extract path of a real book that has chapter_map.json + at
    least one page_*.json but NO verify_config.json, or None if none found."""
    if not os.path.isdir(CORPUS_ROOT):
        return None
    for root, dirs, files in os.walk(CORPUS_ROOT):
        if os.path.basename(root) != "_extract":
            continue
        if "verify_config.json" in files:
            continue
        if "chapter_map.json" not in files:
            continue
        if not any(f.startswith("page_") and f.endswith(".json") for f in files):
            continue
        return root
    return None


# --------------------------------------------------------------------------
# Part A — pure unit tests for ConfigLoader.require_complete()  (v2 array API)
# --------------------------------------------------------------------------
def _loader_with_config(cfg):
    """Build a ConfigLoader whose only candidate config is `cfg` (dict) or
    None (no file). Returns the loader; extract_dir == book_dir == temp."""
    ext = tempfile.mkdtemp(prefix="qc_ext_")
    if cfg is not None:
        with open(os.path.join(ext, "verify_config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    return ConfigLoader(ext, ext, extra_ignore=None)


class TestRequireComplete(unittest.TestCase):
    # --- (a) file absent, allow_absent=True -> warn + no raise -------------
    def test_missing_file_allow_absent_true_warns_no_raise(self):
        loader = _loader_with_config(None)
        with self.assertWarns(UserWarning) as cm:
            loader.require_complete(allow_absent=True)
        msg = str(cm.warning)
        self.assertIn("verify_config.json", msg)
        self.assertIn("ordinal=3", msg)
        # v2: default is a single uncat GroupConfig with primary_type 3.
        self.assertEqual(loader.book.primary_type, 3)
        self.assertIsInstance(loader.book.ordinal, list)
        self.assertEqual(len(loader.book.ordinal), 1)
        self.assertTrue(loader.book.ordinal[0].is_uncat)

    # --- (b) file absent, allow_absent=False -> raise ----------------------
    def test_missing_file_allow_absent_false_raises(self):
        loader = _loader_with_config(None)
        with self.assertRaises(ConfigError) as ctx:
            loader.require_complete(allow_absent=False)
        self.assertIn("[CONFIG]", str(ctx.exception))
        self.assertIn("allow_absent=False", str(ctx.exception))

    # --- (c) file present but no ordinal -> raise (HARD GATE, works) -------
    def test_present_no_ordinal_raises(self):
        loader = _loader_with_config({"disable": ["O"]})  # no ordinal key
        with self.assertRaises(ConfigError) as ctx:
            loader.require_complete()
        msg = str(ctx.exception)
        self.assertIn("[CONFIG]", msg)
        self.assertIn("ordinal", msg)

    # --- (d) file present + legal ordinal array -> no raise ---------------
    def test_valid_array_ordinal_3_no_raise(self):
        loader = _loader_with_config(
            {"ordinal": [{"type": 3, "depth": 3, "scope": 2}]})
        loader.require_complete()  # must not raise
        self.assertEqual(loader.book.primary_type, 3)
        self.assertEqual(len(loader.book.ordinal), 1)
        self.assertEqual(loader.book.ordinal[0].type, 3)
        self.assertEqual(loader.book.ordinal[0].depth, 3)
        self.assertEqual(loader.book.ordinal[0].scope, 2)

    # --- valid explicit four-level declaration -> no raise ----------------
    def test_valid_array_ordinal_4_with_section_hierarchy_no_raise(self):
        cfg = {"ordinal": [{"type": 4, "depth": 2, "scope": 2}],
               "section_types": [1, 2, 3, 4],
               "section_depths": [1, 2, 3, 4]}
        loader = _loader_with_config(cfg)
        loader.require_complete()  # must not raise
        self.assertEqual(loader.book.primary_type, 4)
        self.assertEqual(loader.book.section_types, [1, 2, 3, 4])
        self.assertEqual(loader.book.section_depths, [1, 2, 3, 4])

    # --- v2: old int ordinal is REJECTED with the migration hint ----------
    def test_old_int_ordinal_rejected_with_migration_hint(self):
        # from_dict REJECTS the deprecated int ordinal and points the user to
        # `make_config.py --force`. This is the v2 gate behaviour (was a KNOWN
        # GAP under the old clamp-and-silent design). The actual emitted text
        # is "make_config.py --force"; assert both tokens are present.
        with self.assertRaises(ConfigError) as ctx:
            _loader_with_config({"ordinal": 3})
        msg = str(ctx.exception)
        self.assertIn("make_config", msg)
        self.assertIn("--force", msg)

    def test_old_int_ordinal_99_rejected(self):
        # Any int ordinal (not just a "legal" code) is rejected at construction.
        with self.assertRaises(ConfigError) as ctx:
            _loader_with_config({"ordinal": 99})
        msg = str(ctx.exception)
        self.assertIn("make_config", msg)
        self.assertIn("--force", msg)

    # --- v2: old str ordinal is REJECTED -----------------------------------
    def test_old_str_ordinal_rejected(self):
        with self.assertRaises(ConfigError) as ctx:
            _loader_with_config({"ordinal": "three_level"})
        self.assertIn("数组", str(ctx.exception))

    # --- R6: no uncat group declared -> ACCEPTED, no auto-append ----------
    def test_r6_no_uncat_group_accepted_no_auto_append(self):
        # R6 override: a config declaring groups with NO uncat group must be
        # accepted by both from_dict and require_complete. from_dict must NOT
        # auto-append an uncat; uncat_group() falls back to ordinal[0].
        cfg = {"ordinal": [{"type": 3, "name": ["定理"], "depth": 3, "scope": 2}]}
        bc = BookConfig.from_dict(cfg)
        self.assertEqual([g.name for g in bc.ordinal], [["定理"]])
        self.assertEqual(bc.uncat_group().name, ["定理"])  # fallback to ordinal[0]
        loader = _loader_with_config(cfg)
        loader.require_complete()  # must NOT raise
        self.assertEqual(loader.book.uncat_group().name, ["定理"])

    # --- KNOWN GAP: illegal section config is NOT a hard error (spec ⑥) ----
    def test_illegal_section_config_is_not_hard_error(self):
        # Task spec case ⑥ & docs require illegal section_types/section_depths
        # -> ConfigError. ACTUAL: from_dict SANITIZES (length mismatch / d<1 /
        # invalid role / depths[0]!=1), so require_complete never sees an
        # illegal value and does NOT raise. Each variant below is a legal
        # post-sanitization config -> no raise. (Now uses the v2 ordinal ARRAY.)
        bad_variants = [
            {"ordinal": [{"type": 3, "depth": 3, "scope": 2}],
             "section_types": [1, 2], "section_depths": [1, 9]},
            {"ordinal": [{"type": 3, "depth": 3, "scope": 2}],
             "section_types": [1, 2, 9], "section_depths": [1, 2, 3]},
            {"ordinal": [{"type": 3, "depth": 3, "scope": 2}],
             "section_types": [1, 2, 3], "section_depths": [1, 2]},
            {"ordinal": [{"type": 3, "depth": 3, "scope": 2}],
             "section_types": [1, 2], "section_depths": [1, 0]},
            {"ordinal": [{"type": 3, "depth": 3, "scope": 2}],
             "section_types": [2, 2], "section_depths": [2, 2]},
        ]
        for bad in bad_variants:
            loader = _loader_with_config(bad)
            try:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    loader.require_complete()
            except ConfigError:
                self.fail("require_complete raised on %r; current code "
                          "sanitizes section configs instead of raising "
                          "per spec/docs." % bad)


# --------------------------------------------------------------------------
# Part B — integration tests (real CLIs via subprocess)
# --------------------------------------------------------------------------
def _build_synthetic_book(with_config, config_obj, with_page=True):
    """Build a minimal real-looking book (chapter_map + 1 md + optional page)
    under a temp dir. Returns (book_dir, ext_dir, md_path)."""
    base = tempfile.mkdtemp(prefix="qc_book_")
    ext = os.path.join(base, "_extract")
    os.makedirs(ext, exist_ok=True)
    with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump({"chapters": [{"ch": 1, "start": 1, "end": 1}]}, f)
    if with_page:
        page = {"text": [{"text": "§1.1 小节一\n1.1.1 定义 某定义。\n"
                                  "§1.2 小节二\n1.2.1 定理 某定理。",
                           "poly": [0, 200, 100, 210, 100, 220, 0, 220]}]}
        with open(os.path.join(ext, "page_001.json"), "w", encoding="utf-8") as f:
            json.dump(page, f)
    md = os.path.join(base, "第1章_测试.md")
    md_text = ("# 第一章 测试\n\n## §1 节一\n\n### §1.1 小节一\n\n"
               "#### §1.1.1 定义\n\n内容。\n\n"
               "### §1.2 小节二\n\n#### §1.2.1 定理\n\n内容。\n")
    with open(md, "w", encoding="utf-8") as f:
        f.write(md_text)
    if with_config and config_obj is not None:
        with open(os.path.join(ext, "verify_config.json"), "w", encoding="utf-8") as f:
            json.dump(config_obj, f)
    return base, ext, md


def _run(args, expect_exists=None):
    p = subprocess.run([PY, args[0]] + args[1:], cwd=SKILL_ROOT,
                       capture_output=True, text=True, timeout=300)
    return p.returncode, p.stdout, p.stderr


class TestVerifyChapterEntry(unittest.TestCase):
    def test_all_missing_config_warns_and_no_hard_fail(self):
        # Back-compat: a book WITHOUT verify_config.json must only WARN and
        # must NOT exit 2 (rule H: "文件缺失仅警告并沿用默认 ordinal=3").
        _, ext, md = _build_synthetic_book(with_config=False, config_obj=None)
        rc, out, err = _run([VERIFY_CLI, "--all", ext, os.path.dirname(ext)])
        self.assertNotEqual(rc, 2,
                            "verify --all on no-config book must NOT hard-fail "
                            "(rc=2). out=%s err=%s" % (out[-500:], err[-500:]))
        combined = out + err
        self.assertIn("[CONFIG] 未找到 verify_config.json", combined)

    def test_present_no_ordinal_exits_2(self):
        # File present but no ordinal -> ConfigError -> exit 2 with [CONFIG].
        _, ext, md = _build_synthetic_book(with_config=True,
                                           config_obj={"disable": ["O"]})
        rc, out, err = _run([VERIFY_CLI, "--all", ext, os.path.dirname(ext)])
        self.assertEqual(rc, 2,
                         "verify --all with config-but-no-ordinal must exit 2. "
                         "out=%s err=%s" % (out[-500:], err[-500:]))
        self.assertIn("[CONFIG]", out + err)


class TestScanSkeletonEntry(unittest.TestCase):
    def test_scan_real_book_with_config_exit_0(self):
        # Real book with a v2 array ordinal config: scan must read
        # primary_type and exit 0.
        # (side effect: creates ch1_skeleton.txt in the real _extract — removed
        # afterwards so the corpus is left untouched)
        skel = os.path.join(REAL_HAS_CFG, "ch1_skeleton.txt")
        try:
            if os.path.exists(skel):
                os.remove(skel)
            rc, out, err = _run([SCAN_CLI, REAL_HAS_CFG, "1"])
            self.assertEqual(rc, 0,
                             "scan_skeleton on configured real book must exit 0. "
                             "out=%s err=%s" % (out[-500:], err[-500:]))
        finally:
            if os.path.exists(skel):
                os.remove(skel)

    def test_scan_missing_config_warns_no_hard_fail(self):
        # No config -> WARNING + default ordinal=3, scan still completes (rc 0).
        _, ext, _ = _build_synthetic_book(with_config=False, config_obj=None)
        rc, out, err = _run([SCAN_CLI, ext, "1"])
        self.assertEqual(rc, 0,
                         "scan_skeleton on no-config book must not hard-fail. "
                         "out=%s err=%s" % (out[-500:], err[-500:]))
        self.assertIn("[CONFIG] 未找到 verify_config.json", out + err)

    def test_scan_present_no_ordinal_exits_2(self):
        # File present but no ordinal -> ConfigError -> exit 2 with [CONFIG].
        _, ext, _ = _build_synthetic_book(with_config=True,
                                          config_obj={"disable": ["O"]})
        rc, out, err = _run([SCAN_CLI, ext, "1"])
        self.assertEqual(rc, 2,
                         "scan_skeleton with config-but-no-ordinal must exit 2. "
                         "out=%s err=%s" % (out[-500:], err[-500:]))
        self.assertIn("[CONFIG]", out + err)


class TestMakeConfig(unittest.TestCase):
    def test_make_config_generates_on_temp_no_config_book(self):
        # Best-effort generator on a synthetic no-config _extract (CN three-level
        # page content) -> creates file + prints 人工核对 prompt, exit 0.
        ext = tempfile.mkdtemp(prefix="qc_mk_")
        with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
            json.dump({"chapters": [{"ch": 1, "start": 1, "end": 1}]}, f)
        page = {"text": [{"text": "1.1.1 定义 某定义。\n1.2.1 定理 某定理。",
                           "poly": [0, 200, 100, 210, 100, 220, 0, 220]}]}
        with open(os.path.join(ext, "page_001.json"), "w", encoding="utf-8") as f:
            json.dump(page, f)
        rc, out, err = _run([MAKE_CLI, ext])
        self.assertEqual(rc, 0,
                         "make_config should exit 0. out=%s err=%s"
                         % (out[-500:], err[-500:]))
        self.assertTrue(os.path.exists(os.path.join(ext, "verify_config.json")),
                        "make_config must write verify_config.json")
        self.assertIn("人工核对", out + err)
        # v2: the generated ordinal is a LIST of GroupConfig dicts.
        gen = json.load(open(os.path.join(ext, "verify_config.json"), encoding="utf-8"))
        self.assertIsInstance(gen["ordinal"], list)
        self.assertEqual(len(gen["ordinal"]), 1)
        self.assertIn(gen["ordinal"][0]["type"], (1, 2, 3, 4, 5, 6, 7))

    def test_make_config_existing_config_skips_exit_0(self):
        # Real book that already has verify_config.json (v2 array form):
        # non --force -> skip, exit 0 (read-only, corpus untouched).
        rc, out, err = _run([MAKE_CLI, REAL_HAS_CFG])
        self.assertEqual(rc, 0,
                         "make_config on existing-config book (no --force) must "
                         "skip and exit 0. out=%s err=%s" % (out[-500:], err[-500:]))
        self.assertIn("已存在", out + err)
        self.assertIn("跳过", out + err)

    def test_make_config_real_no_config_book_then_cleanup(self):
        # Real no-config book (discovered at runtime): make_config should
        # generate a starter file + print 人工核对. We DELETE the generated
        # file afterwards so the real corpus is left exactly as found.
        ext = _find_real_no_cfg_book()
        if ext is None:
            self.skipTest("no real NO_CFG book (with pages+chapter_map) found")
        cfg_path = os.path.join(ext, "verify_config.json")
        existed_before = os.path.exists(cfg_path)
        try:
            rc, out, err = _run([MAKE_CLI, ext])
            self.assertEqual(rc, 0,
                             "make_config on real no-config book must exit 0. "
                             "out=%s err=%s" % (out[-500:], err[-500:]))
            self.assertTrue(os.path.exists(cfg_path),
                            "make_config must generate verify_config.json for "
                            "the real no-config book")
            self.assertIn("人工核对", out + err)
        finally:
            if (not existed_before) and os.path.exists(cfg_path):
                os.remove(cfg_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
