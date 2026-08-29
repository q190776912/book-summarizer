"""Regression / acceptance tests for the "rule 10 — 书级配置强制前置" change
(book-summarizer incremental change B, 2026-08-06) — REWRITTEN for the
verify_config v2 schema (GroupConfig ARRAY, not int `ordinal`).

Covers the new mandatory book-config gate:

  * `config.ConfigLoader.require_complete()` — the gate logic.
  * `verify/script/verify_chapter.py` entry — `require_complete(allow_absent=False)`
    invoked inside `_make_loader()` (STRICT gate: a missing config file ->
    exit 2, per config_setting 流程 规则1 "文件缺失必须重新配置"); `main()`
    catches `ConfigError` -> print + exit 2.
  * `scan_skeleton.py` entry — constructs `ConfigLoader`, calls
    `require_complete()`, reads `loader.book.primary_type` (int).
  * `config/verify_config/make_config.py` — best-effort starter-config generator (now emits
    the v2 array form).

v2 schema contract (per config_setting 流程 规则1 / config/config_schema.md §配置字段说明):
  * `ordinal` is a LIST of `GroupConfig` dicts
    (`{type:int 1..8, name:[str], depth:int>=1, scope:1|2|3}`).
  * `BookConfig.from_dict` REJECTS the old int/str `ordinal` with a ConfigError
    carrying the "make_config --force" migration hint.
  * `require_complete()` has two caller stances (config_setting 流程 规则1):
      (a) [verify_chapter — STRICT gate] `allow_absent=False`:
          file ABSENT            -> raise ConfigError (exit 2):
                                    "文件缺失必须重新配置";
          file PRESENT but no `ordinal` array -> raise ConfigError (exit 2);
          file PRESENT + legal ordinal array      -> no raise.
      (b) [scan_skeleton — SAFETY NET] `allow_absent=True`:
          file ABSENT            -> WARNING + keep default (single uncat
                                    GroupConfig, primary_type=3, back-compat),
                                    scan must NOT hard-fail;
          file PRESENT but incomplete            -> raise ConfigError (exit 2).
  * R6 override: `from_dict` does NOT auto-append an uncat group, and
    `require_complete` does NOT hard-require one. A config declaring groups
    with NO uncat group is ACCEPTED; `uncat_group()` falls back to `ordinal[0]`.

No pytest dependency: runs under stdlib unittest
  python config/verify_config/tests/test_config_complete.py
or
  python -m unittest config.script.tests.test_config_complete -v
(config.script.tests is not a package in this repo, so prefer the direct-module form.)
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
import sys
import json
import tempfile
import subprocess
import unittest
import warnings

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from verify_config import (ConfigLoader, ConfigError, BookConfig, GroupConfig)  # noqa: E402

PY = sys.executable
VERIFY_CLI = os.path.join(_ROOT, "verify/script/verify_chapter.py")
SCAN_CLI = os.path.join(_ROOT, "flows/write-source/structure/script/scan_skeleton.py")
MAKE_CLI = os.path.join(_ROOT, "config/verify_config/make_config.py")

# Real corpus books are discovered at runtime (the corpus changes); we do not
# hard-code paths. CORPUS_ROOT comes from user_config (example default).
from lib.user_config import get as _uc_get  # noqa: E402
CORPUS_ROOT = _uc_get("corpus_root", r"D:\study\book")


def _find_real_has_cfg_book():
    """Return the _extract path of a real book that already has
    verify_config.json, or None if none found."""
    if not os.path.isdir(CORPUS_ROOT):
        return None
    for root, dirs, files in os.walk(CORPUS_ROOT):
        if os.path.basename(root) != "_extract":
            continue
        if "verify_config.json" not in files:
            continue
        return root
    return None


# A real book with a v2 ordinal array config (used read-only; tests skip when
# the corpus is absent or no configured book exists).
REAL_HAS_CFG = _find_real_has_cfg_book()


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


def _find_real_unprepared_book():
    """Return the _extract path of a real book that has extracted pages but is
    NOT even chapter-mapped yet (early-stage extraction), or None."""
    if not os.path.isdir(CORPUS_ROOT):
        return None
    for root, dirs, files in os.walk(CORPUS_ROOT):
        if os.path.basename(root) != "_extract":
            continue
        if "verify_config.json" in files or "chapter_map.json" in files:
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
    None (no file). Returns the loader; extract_dir == book_dir == temp.

    Writes the `_extraction_done.json` phase marker: these tests target
    `require_complete` semantics, while ConfigLoader's own upstream gate
    hard-rejects any config whose extract dir lacks the MM-Repair completion
    marker (flow_gate contract)."""
    ext = tempfile.mkdtemp(prefix="qc_ext_")
    if cfg is not None:
        with open(os.path.join(ext, "verify_config.json"), "w", encoding="utf-8") as f:
            json.dump(cfg, f)
    with open(os.path.join(ext, "_extraction_done.json"), "w", encoding="utf-8") as f:
        json.dump({"done": True}, f)
    return ConfigLoader(ext, ext, extra_ignore=None)


class TestRequireComplete(unittest.TestCase):
    # --- (a) file absent, allow_absent=True -> warn + no raise -------------
    def test_missing_file_allow_absent_true_warns_no_raise(self):
        loader = _loader_with_config(None)
        with self.assertWarns(UserWarning) as cm:
            loader.require_complete(allow_absent=True)
        msg = str(cm.warning)
        self.assertIn("verify_config.json", msg)
        # v2 "no default type": absent ordinal -> a single UNNUMBERED uncat
        # group (type 0), deliberately NOT the legacy default type 3.
        self.assertEqual(loader.book.primary_type, 0)
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
            {"ordinal": [{"type": 3, "scope": 2}]})
        loader.require_complete()  # must not raise
        self.assertEqual(loader.book.primary_type, 3)
        self.assertEqual(len(loader.book.ordinal), 1)
        self.assertEqual(loader.book.ordinal[0].type, 3)
        self.assertEqual(loader.book.ordinal[0].depth, 3)
        self.assertEqual(loader.book.ordinal[0].scope, 2)

    # --- valid explicit four-level declaration -> no raise ----------------
    def test_valid_array_ordinal_4_with_section_hierarchy_no_raise(self):
        # `section_depths` is NOT a config field — depth is DERIVED from each
        # `section_types` role code via SECTION_TYPE_DEPTH.  Declaring only
        # `section_types` must be accepted, and the derived `section_depths`
        # property must equal [1, 2, 3, 4].
        cfg = {"ordinal": [{"type": 4, "scope": 2}],
               "section_types": [1, 2, 3, 4]}
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
        cfg = {"ordinal": [{"type": 3, "name": ["定理"], "scope": 2}]}
        bc = BookConfig.from_dict(cfg)
        self.assertEqual([g.name for g in bc.ordinal], [["定理"]])
        self.assertEqual(bc.uncat_group().name, ["定理"])  # fallback to ordinal[0]
        loader = _loader_with_config(cfg)
        loader.require_complete()  # must NOT raise
        self.assertEqual(loader.book.uncat_group().name, ["定理"])

    # --- KNOWN GAP: illegal section config is NOT a hard error (spec ⑥) ----
    def test_illegal_section_config_is_not_hard_error(self):
        # Task spec case ⑥ & older docs required illegal section_types ->
        # ConfigError. ACTUAL: from_dict SANITIZES section_types (drops roles
        # outside SECTION_ROLE_CODES, coerces the first level to the chapter
        # role 1), so require_complete never sees an illegal value and does NOT
        # raise.  `section_depths` is NOT a config field (depth is derived from
        # each role via SECTION_TYPE_DEPTH); a stale `section_depths` key is
        # ignored.  Each variant below is sanitized to a legal config -> no raise.
        bad_variants = [
            {"ordinal": [{"type": 3, "scope": 2}],
             "section_types": [1, 2]},                       # valid after sanitize
            {"ordinal": [{"type": 3, "scope": 2}],
             "section_types": [1, 2, 9]},                    # role 9 dropped -> [1, 2]
            {"ordinal": [{"type": 3, "scope": 2}],
             "section_types": [1, 2, 3]},                    # valid
            {"ordinal": [{"type": 3, "scope": 2}],
             "section_types": [1, 2]},                       # valid (no depths key)
            {"ordinal": [{"type": 3, "scope": 2}],
             "section_types": [2, 2]},                       # head coerced -> [1, 2]
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
    p = subprocess.run([PY, args[0]] + args[1:], cwd=_ROOT,
                       capture_output=True, text=True, timeout=300,
                       encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


def _best_effort_remove(path):
    """Remove ``path`` if present, tolerating environments whose delete policy
    fails closed (e.g. a sandbox with no recycle bin). Cleanup is best-effort:
    the test's assertions have already run by the time we get here, so a blocked
    delete must NOT turn a passing test into an ERROR. In a normal environment
    the file is removed; in a locked-down sandbox it is left behind harmlessly.
    """
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


class TestVerifyChapterEntry(unittest.TestCase):
    def test_all_missing_config_exits_2(self):
        # config_setting 流程 规则1: a book WITHOUT verify_config.json must
        # HARD-FAIL (exit 2). verify is the strict gate. NOTE: on a synthetic
        # book that also lacks book_structure.json, the extract-stage STRUCTURE
        # gate fires BEFORE the config gate — both are hard blocks with rc=2,
        # so assert the exit code + a BLOCKED diagnostic rather than the exact
        # gate that tripped.
        _, ext, md = _build_synthetic_book(with_config=False, config_obj=None)
        rc, out, err = _run([VERIFY_CLI, "--all", ext, os.path.dirname(ext)])
        self.assertEqual(rc, 2,
                         "verify --all on no-config book must hard-fail (rc=2). "
                         "out=%s err=%s" % (out[-500:], err[-500:]))
        self.assertIn("BLOCKED", out + err)

    def test_present_no_ordinal_exits_2(self):
        # File present but no ordinal -> ConfigError -> exit 2 with [CONFIG].
        _, ext, md = _build_synthetic_book(with_config=True,
                                           config_obj={"disable": ["O"]})
        rc, out, err = _run([VERIFY_CLI, "--all", ext, os.path.dirname(ext)])
        self.assertEqual(rc, 2,
                         "verify --all with config-but-no-ordinal must exit 2. "
                         "out=%s err=%s" % (out[-500:], err[-500:]))
        self.assertIn("BLOCKED", out + err)


class TestScanSkeletonEntry(unittest.TestCase):
    def test_scan_real_book_with_config_exit_0(self):
        # Real book with a v2 array ordinal config: scan must read
        # primary_type and exit 0.
        # scan_skeleton no longer writes any file, so this only verifies the
        # config gate exit code and leaves the corpus untouched.
        if not REAL_HAS_CFG:
            self.skipTest("no configured real book found under %s" % CORPUS_ROOT)
        rc, out, err = _run([SCAN_CLI, REAL_HAS_CFG, "1"])
        self.assertEqual(rc, 0,
                         "scan_skeleton on configured real book must exit 0. "
                         "out=%s err=%s" % (out[-500:], err[-500:]))

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
    @staticmethod
    def _write_marker(ext):
        with open(os.path.join(ext, "_extraction_done.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"done": True}, f)

    def test_make_config_generates_on_temp_no_config_book(self):
        # Best-effort generator on a synthetic no-config _extract (CN three-level
        # page content) -> creates file + prints 人工核对 prompt, exit 0.
        # Requires the MM-Repair completion marker (flow_gate contract): without
        # it make_config BLOCKS with exit 2 by design.
        ext = tempfile.mkdtemp(prefix="qc_mk_")
        with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
            json.dump({"chapters": [{"ch": 1, "start": 1, "end": 1}]}, f)
        page = {"text": [{"text": "1.1.1 定义 某定义。\n1.2.1 定理 某定理。",
                           "poly": [0, 200, 100, 210, 100, 220, 0, 220]}]}
        with open(os.path.join(ext, "page_001.json"), "w", encoding="utf-8") as f:
            json.dump(page, f)
        self._write_marker(ext)
        rc, out, err = _run([MAKE_CLI, ext])
        self.assertEqual(rc, 0,
                         "make_config should exit 0. out=%s err=%s"
                         % (out[-500:], err[-500:]))
        self.assertTrue(os.path.exists(os.path.join(ext, "verify_config.json")),
                        "make_config must write verify_config.json")
        self.assertIn("人工核对", out + err)
        # v2: the generated ordinal is a LIST of GroupConfig dicts; detected
        # labels are split into per-counter groups (no uncat placeholder).
        with open(os.path.join(ext, "verify_config.json"), encoding="utf-8") as f:
            gen = json.load(f)
        self.assertIsInstance(gen["ordinal"], list)
        self.assertGreaterEqual(len(gen["ordinal"]), 1)
        for g in gen["ordinal"]:
            self.assertIn(g["type"], (1, 2, 3, 4, 5, 6, 8, 9))
            self.assertNotEqual(g.get("name"), ["uncat"])

    def test_make_config_existing_config_skips_exit_0(self):
        # Real book that already has verify_config.json (v2 array form):
        # non --force -> skip, exit 0 (read-only, corpus untouched).
        if not REAL_HAS_CFG:
            self.skipTest("no configured real book found under %s" % CORPUS_ROOT)
        rc, out, err = _run([MAKE_CLI, REAL_HAS_CFG])
        self.assertEqual(rc, 0,
                         "make_config on existing-config book (no --force) must "
                         "skip and exit 0. out=%s err=%s" % (out[-500:], err[-500:]))
        self.assertIn("已存在", out + err)
        self.assertIn("跳过", out + err)

    def test_make_config_en_three_level_detects_type3_scope3(self):
        # Regression for Kreyszig-style EN three-level books. Items are numbered
        # "Definition 1.5-3" / "1.5-3 Definition" (label + three-component number).
        # make_config MUST detect type 3 (NOT EN two-level type 4) and assign
        # scope 3 (per-section counter reset). The phase-guard marker
        # (_extraction_done.json) is required so detection actually scans the
        # pages instead of falling back to the default three_level(3).
        ext = tempfile.mkdtemp(prefix="qc_en3_")
        with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
            json.dump({"chapters": [{"ch": 1, "start": 1, "end": 1}]}, f)
        with open(os.path.join(ext, "_extraction_done.json"), "w", encoding="utf-8") as f:
            json.dump({"done": True}, f)
        page = {"text": [
            {"text": "1.1-1 Definition (Metric). 1.1-2 Theorem (Completeness).",
             "poly": [0, 200, 100, 210, 100, 220, 0, 220]},
            {"text": "Definition 1.5-3 (Bounded). 1.5-4 Lemma (Hahn).",
             "poly": [0, 300, 100, 310, 100, 320, 0, 320]},
        ]}
        with open(os.path.join(ext, "page_001.json"), "w", encoding="utf-8") as f:
            json.dump(page, f)
        rc, out, err = _run([MAKE_CLI, ext])
        self.assertEqual(rc, 0,
                         "make_config should exit 0. out=%s err=%s"
                         % (out[-500:], err[-500:]))
        with open(os.path.join(ext, "verify_config.json"), encoding="utf-8") as f:
            gen = json.load(f)
        self.assertIsInstance(gen["ordinal"], list)
        grp = gen["ordinal"][0]
        self.assertEqual(grp["type"], 3,
                         "EN three-level book must detect type 3, got %r (out=%s)"
                         % (grp, out[-500:]))
        self.assertEqual(grp["scope"], 3,
                         "three-level book must get scope 3, got %r" % grp)

    def test_make_config_fills_detected_labels_cn(self):
        # Incremental label fill (the "detect one, fill one" fix): a CN
        # three-level book whose pages contain numbered headings for ALL six
        # main entry types must generate a group whose `name` lists exactly
        # those detected labels (NOT the old hard-coded ["uncat"]). The
        # phase-guard marker (_extraction_done.json) is required for detection
        # to actually scan the pages.
        ext = tempfile.mkdtemp(prefix="qc_labels_cn_")
        with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
            json.dump({"chapters": [{"ch": 1, "start": 1, "end": 1}]}, f)
        with open(os.path.join(ext, "_extraction_done.json"), "w", encoding="utf-8") as f:
            json.dump({"done": True}, f)
        page = {"text": [{"text":
            "1.1.1 定义 X。1.2.1 定理 Y。1.3.1 引理 Z。"
            "1.4.1 推论 W。1.5.1 命题 V。1.6.1 例 U。",
            "poly": [0, 200, 100, 210, 100, 220, 0, 220]}]}
        with open(os.path.join(ext, "page_001.json"), "w", encoding="utf-8") as f:
            json.dump(page, f)
        rc, out, err = _run([MAKE_CLI, ext])
        self.assertEqual(rc, 0,
                         "make_config should exit 0. out=%s err=%s"
                         % (out[-500:], err[-500:]))
        with open(os.path.join(ext, "verify_config.json"), encoding="utf-8") as f:
            gen = json.load(f)
        self.assertIsInstance(gen["ordinal"], list)
        # Current contract: detected labels are split into PER-COUNTER groups
        # (independent numbering sequences each get their own group) — six
        # independently numbered entry types -> six groups, none named uncat.
        all_names = [nm for g in gen["ordinal"] for nm in g.get("name", [])]
        self.assertNotIn("uncat", all_names,
                         "detected labels must replace the default ['uncat']")
        for expected in ["定义", "定理", "引理", "推论", "命题", "例"]:
            self.assertIn(expected, all_names,
                          "detected label %s missing from group names %r"
                          % (expected, all_names))
        # type 3 (CN three-level) + scope 3 still hold alongside the label fill.
        for g in gen["ordinal"]:
            self.assertEqual(g["type"], 3)
            self.assertEqual(g["scope"], 3)

    def test_make_config_fills_detected_labels_en(self):
        # EN three-level (Kreyszig-style) book: numbered "Definition/Lemma/
        # Theorem" headings must be filled into `name` (stable LABEL_FORMS
        # order), reproducing the hand-written Kreyszig config shape.
        ext = tempfile.mkdtemp(prefix="qc_labels_en_")
        with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
            json.dump({"chapters": [{"ch": 1, "start": 1, "end": 1}]}, f)
        with open(os.path.join(ext, "_extraction_done.json"), "w", encoding="utf-8") as f:
            json.dump({"done": True}, f)
        # One heading per text block (real OCR output shape): make_config
        # deliberately rejects label hits deep inside LONG blocks (prose /
        # cross-reference guard), so multi-heading blocks undercount.
        page = {"text": [
            {"text": "Definition 1.1-1 (Metric).",
             "poly": [0, 200, 100, 210, 100, 220, 0, 220]},
            {"text": "Theorem 1.1-2 (Complete).",
             "poly": [0, 210, 100, 220, 100, 230, 0, 230]},
            {"text": "Lemma 1.5-3 (Hahn).",
             "poly": [0, 300, 100, 310, 100, 320, 0, 320]},
            {"text": "Corollary 1.6-1 (Baire).",
             "poly": [0, 310, 100, 320, 100, 330, 0, 330]},
            {"text": "Proposition 1.7-1 (Open).",
             "poly": [0, 320, 100, 330, 100, 340, 0, 340]},
            {"text": "Example 1.8-1 (Convergent).",
             "poly": [0, 330, 100, 340, 100, 350, 0, 350]},
        ]}
        with open(os.path.join(ext, "page_001.json"), "w", encoding="utf-8") as f:
            json.dump(page, f)
        rc, out, err = _run([MAKE_CLI, ext])
        self.assertEqual(rc, 0,
                         "make_config should exit 0. out=%s err=%s"
                         % (out[-500:], err[-500:]))
        with open(os.path.join(ext, "verify_config.json"), encoding="utf-8") as f:
            gen = json.load(f)
        self.assertIsInstance(gen["ordinal"], list)
        # Per-counter group contract (see the CN variant above).
        all_names = [nm for g in gen["ordinal"] for nm in g.get("name", [])]
        self.assertNotIn("uncat", all_names)
        for expected in ["Definition", "Theorem", "Lemma", "Corollary",
                         "Proposition", "Example"]:
            self.assertIn(expected, all_names,
                          "detected label %s missing from group names %r"
                          % (expected, all_names))
        for g in gen["ordinal"]:
            self.assertEqual(g["type"], 3)
            self.assertEqual(g["scope"], 3)
        self.assertEqual(gen["language"], "en")

    def test_make_config_real_no_config_book_then_cleanup(self):
        # Real no-config book (discovered at runtime), two tiers so the test
        # exercises whichever real-corpus shape exists:
        #   A) _extract WITH chapter_map but NO verify_config.json:
        #      - marker present  -> make_config must GENERATE (exit 0, file
        #        written + 人工核对 prompt); we DELETE the file afterwards so
        #        the corpus is left exactly as found.
        #      - marker missing  -> BLOCKED exit 2 (flow_gate contract).
        #   B) fallback — _extract with pages but NOT even chapter_map.json
        #      (early-stage extraction): config 子流程契约要求先建章节映射，
        #      make_config 必须 BLOCK（rc=2）且绝不写配置。
        ext = _find_real_no_cfg_book()
        if ext is None:
            ext = _find_real_unprepared_book()
        if ext is None:
            self.skipTest("no real no-config / unprepared book found under %s"
                          % CORPUS_ROOT)
        cfg_path = os.path.join(ext, "verify_config.json")
        marker = os.path.join(ext, "_extraction_done.json")
        cmap = os.path.join(ext, "chapter_map.json")
        existed_before = os.path.exists(cfg_path)
        try:
            rc, out, err = _run([MAKE_CLI, ext])
            if not os.path.exists(cmap):
                # Tier B: unprepared book — never fabricate a config.
                self.assertNotEqual(rc, 0,
                                    "make_config must not generate a config "
                                    "without chapter_map.json. out=%s err=%s"
                                    % (out[-500:], err[-500:]))
                self.assertIn("BLOCKED", out + err)
                self.assertFalse(os.path.exists(cfg_path),
                                 "make_config wrote a config for an "
                                 "unprepared book (no chapter_map)")
                return
            if not os.path.exists(marker):
                self.assertEqual(rc, 2,
                                 "make_config without MM-Repair marker must "
                                 "BLOCK (rc=2). out=%s err=%s"
                                 % (out[-500:], err[-500:]))
                self.assertIn("BLOCKED", out + err)
                return
            self.assertEqual(rc, 0,
                             "make_config on real no-config book must exit 0. "
                             "out=%s err=%s" % (out[-500:], err[-500:]))
            self.assertTrue(os.path.exists(cfg_path),
                            "make_config must generate verify_config.json for "
                            "the real no-config book")
            self.assertIn("人工核对", out + err)
        finally:
            if (not existed_before) and os.path.exists(cfg_path):
                _best_effort_remove(cfg_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
