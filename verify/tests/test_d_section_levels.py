"""Targeted regression tests for the D-layer "nested section hierarchy"
feature (book-summarizer, 2026-08-06 incremental change) — REWRITTEN for the
verify_config v2 schema (GroupConfig ARRAY, not int `ordinal`).

Covers:
  * BookConfig.from_dict — back-compat section_types inference (now driven by
    the primary GroupConfig `type`, NOT an int `ordinal`); explicit 4-level
    declaration; illegal role codes filtered; depth DERIVED from section_types
    via SECTION_TYPE_DEPTH (no separate `section_depths` field); and the
    max_level / section_depth / section_role helpers.
  * d_layer._partition_sections_by_level — per-level continuity / tail split,
    merged list relative-to-chapter path strings, ancestor-prefix auto-existence.
  * d_layer.check_d_layer (end-to-end, synthetic md + raw page JSON) for 1/2/3/4
    level books — proves ordinal=3/5 three-level books verify 1.1.1 for the
    first time (no false positive) AND two-level books do NOT emit subsection
    findings.  Configs are built as `BookConfig(ordinal=[GroupConfig(...)])`.
  * d_layer.check_d_layer_gm — returns a structure WITHOUT a 'levels' key
    (gm / roman path must not trigger the per-level report block).
  * report.print_result — the per-level block must NOT double-count problems.

No pytest dependency: runs under stdlib unittest
  python verify/tests/test_d_section_levels.py
or
  python -m unittest verify.tests.test_d_section_levels -v
(verify.tests is not a package in this repo, so prefer the direct-module form.)
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
import io
import json
import tempfile
import unittest
import contextlib

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from verify_config import (
    BookConfig, GroupConfig, ORDINAL_DEPTH, SCOPE_CHAPTER,
    ORDINAL_SINGLE, ORDINAL_TWO_LEVEL, ORDINAL_THREE_LEVEL,
    ORDINAL_ROMAN, ORDINAL_GM, SECTION_ROLE_CHAPTER, SECTION_ROLE_SECTION,
    SECTION_ROLE_SUBSECTION, SECTION_ROLE_SUBSUBSECTION, SECTION_ROLE_CODES,
    ORDINAL_SECTION_TYPES,
)
from section_continuity import (
    _project, _rel_path, _split_num, _build_item_re,
    _partition_sections_by_level, check_d_layer, check_d_layer_gm,
)
from verify.script.base import DEFAULT_RESULT


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _make_page(path, texts, y=200):
    """Write a synthetic OCR page JSON with `texts` as text blocks (y high so
    gm item scan keeps them)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {"text": [{"text": t, "poly": [0, y, 100, y, 100, y + 10, 0, y + 10]}
                      for t in texts]}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_md(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _sets(*levels):
    """Build the {L: set_of_tuples} dict for levels 1..len(levels)."""
    return {L: set(t) for L, t in enumerate(levels, start=1)}


# ==========================================================================
# 1) BookConfig.from_dict  (v2: ordinal is a GroupConfig ARRAY)
# ==========================================================================
class TestBookConfigFromDict(unittest.TestCase):

    def test_empty_dict_defaults_to_unnumbered_uncat(self):
        # v2 "no default type": an absent ordinal must NOT be silently upgraded
        # to a fabricated three-level scheme — it becomes a single UNNUMBERED
        # uncat group (type 0); require_complete() decides whether that is
        # acceptable (warn) or fatal (raise).
        cfg = BookConfig.from_dict({})
        self.assertEqual(cfg.primary_type, 0)
        self.assertEqual(len(cfg.ordinal), 1)
        self.assertTrue(cfg.ordinal[0].is_uncat)
        # Section hierarchy falls back to the minimal chapter-only projection.
        self.assertEqual(cfg.section_types, [1])

    def test_ordinal_3_infers_three_level(self):
        cfg = BookConfig.from_dict({"ordinal": [{"type": 3, "scope": 2}]})
        self.assertEqual(cfg.primary_type, ORDINAL_THREE_LEVEL)
        self.assertEqual(cfg.section_types, [1, 2, 3])
        self.assertEqual(cfg.section_depths, [1, 2, 3])
        self.assertEqual(cfg.max_level, 3)

    def test_ordinal_2_infers_two_level(self):
        cfg = BookConfig.from_dict({"ordinal": [{"type": 2, "scope": 2}]})
        self.assertEqual(cfg.primary_type, ORDINAL_TWO_LEVEL)
        self.assertEqual(cfg.section_types, [1, 2])
        self.assertEqual(cfg.section_depths, [1, 2])
        self.assertEqual(cfg.max_level, 2)

    def test_ordinal_1_infers_single_level(self):
        cfg = BookConfig.from_dict({"ordinal": [{"type": 1, "scope": 2}]})
        self.assertEqual(cfg.primary_type, ORDINAL_SINGLE)
        self.assertEqual(cfg.section_types, [1])
        self.assertEqual(cfg.section_depths, [1])
        self.assertEqual(cfg.max_level, 1)

    def test_ordinal_5_roman_infers_three_level(self):
        # roman (ordinal=5) is a three-level book -> subsection level now live.
        cfg = BookConfig.from_dict({"ordinal": [{"type": 5, "scope": 2}]})
        self.assertEqual(cfg.primary_type, ORDINAL_ROMAN)
        self.assertEqual(cfg.section_types, [1, 2, 3])
        self.assertEqual(cfg.section_depths, [1, 2, 3])
        self.assertEqual(cfg.max_level, 3)

    def test_explicit_four_level(self):
        cfg = BookConfig.from_dict({"section_types": [1, 2, 3, 4]})
        self.assertEqual(cfg.section_types, [1, 2, 3, 4])
        self.assertEqual(cfg.section_depths, [1, 2, 3, 4])  # derived via map
        self.assertEqual(cfg.max_level, 4)
        self.assertEqual(cfg.section_depth(4), 4)

    def test_section_depths_input_is_ignored(self):
        # The stored `section_depths` field is gone; depth is derived from
        # section_types via SECTION_TYPE_DEPTH.  A stale `section_depths` key
        # in the config must NOT affect the derived depths.
        cfg = BookConfig.from_dict({
            "section_types": [1, 2, 3],
            "section_depths": [9, 9, 9],
        })
        self.assertEqual(cfg.section_types, [1, 2, 3])
        self.assertEqual(cfg.section_depths, [1, 2, 3])

    def test_invalid_role_code_filtered(self):
        # code 9 is not a valid SECTION_ROLE -> dropped; derived depths follow.
        cfg = BookConfig.from_dict({"section_types": [1, 2, 9, 4]})
        self.assertEqual(cfg.section_types, [1, 2, 4])
        self.assertEqual(cfg.section_depths, [1, 2, 4])
        self.assertEqual(cfg.max_level, 3)

    def test_all_illegal_roles_falls_back_to_chapter(self):
        cfg = BookConfig.from_dict({"section_types": [9, 8, 7]})
        self.assertEqual(cfg.section_types, [1])
        self.assertEqual(cfg.section_depths, [1])
        self.assertEqual(cfg.max_level, 1)

    def test_unregistered_role_raises_in_section_depth(self):
        # Guard against "depth == role_code": a registered-by-from_dict code
        # missing from SECTION_TYPE_DEPTH must raise, never inherit its value.
        import verify_config as vc
        cfg = BookConfig.from_dict({"section_types": [1, 2, 3]})
        saved = vc.SECTION_TYPE_DEPTH
        vc.SECTION_TYPE_DEPTH = {1: 1, 2: 2}  # role 3 unregistered
        try:
            with self.assertRaises(vc.ConfigError):
                cfg.section_depth(3)
        finally:
            vc.SECTION_TYPE_DEPTH = saved

    # -- helpers: max_level / section_depth / section_role --
    def test_helpers_on_three_level(self):
        cfg = BookConfig.from_dict({"ordinal": [{"type": 3, "scope": 2}]})
        self.assertEqual(cfg.primary_type, ORDINAL_THREE_LEVEL)
        self.assertEqual(cfg.max_level, 3)
        self.assertEqual(cfg.section_depth(1), 1)
        self.assertEqual(cfg.section_depth(2), 2)
        self.assertEqual(cfg.section_depth(3), 3)
        self.assertEqual(cfg.section_role(1), SECTION_ROLE_CHAPTER)
        self.assertEqual(cfg.section_role(2), SECTION_ROLE_SECTION)
        self.assertEqual(cfg.section_role(3), SECTION_ROLE_SUBSECTION)

    def test_helpers_on_four_level(self):
        cfg = BookConfig.from_dict({"section_types": [1, 2, 3, 4]})
        self.assertEqual(cfg.max_level, 4)
        self.assertEqual(cfg.section_depth(4), 4)
        self.assertEqual(cfg.section_role(4), SECTION_ROLE_SUBSUBSECTION)

    def test_section_role_codes_constant(self):
        # role 0 = 无序号标层级（SECTION_ROLE_UNNUMBERED）。角色码已扩展到
        # 5（五级小节层级，OCR 自动识别上限随之放开），范围 0..5。
        self.assertEqual(SECTION_ROLE_CODES, (0, 1, 2, 3, 4, 5))

    def test_ordinal_section_types_backcompat_table(self):
        # The exact reverse-inference table mandated by the change.
        self.assertEqual(ORDINAL_SECTION_TYPES[1], [1])
        self.assertEqual(ORDINAL_SECTION_TYPES[2], [1, 2])
        self.assertEqual(ORDINAL_SECTION_TYPES[3], [1, 2, 3])
        self.assertEqual(ORDINAL_SECTION_TYPES[4], [1, 2])
        self.assertEqual(ORDINAL_SECTION_TYPES[5], [1, 2, 3])
        self.assertEqual(ORDINAL_SECTION_TYPES[6], [1, 2])
        # 原 type 7 (fraleigh, 节基 EN 两级) 已并入 type 4（chapter_first:false），
        # 不再单列；补覆盖 type 8 (vakil EN 三级) / 9 (en3)。
        self.assertEqual(ORDINAL_SECTION_TYPES[8], [1, 2, 3])
        self.assertEqual(ORDINAL_SECTION_TYPES[9], [1, 2])

# ==========================================================================
# 2) primitive helpers
# ==========================================================================
class TestDLayerPrimitives(unittest.TestCase):

    def test_split_num(self):
        self.assertEqual(_split_num("1.2.3"), [1, 2, 3])
        self.assertEqual(_split_num("1-2"), [1, 2])
        self.assertEqual(_split_num("1.2.3.4"), [1, 2, 3, 4])

    def test_rel_path(self):
        self.assertEqual(_rel_path((1,)), "")
        self.assertEqual(_rel_path((1, 2)), "2")
        self.assertEqual(_rel_path((1, 2, 3)), "2.3")
        self.assertEqual(_rel_path((1, 1, 2)), "1.2")
        self.assertEqual(_rel_path((1, 1, 1, 2)), "1.1.2")

    def test_project_three_level(self):
        target = {L: set() for L in (1, 2, 3)}
        _project([1, 2, 3], [1, 2, 3], target)
        self.assertEqual(target[1], {(1,)})
        self.assertEqual(target[2], {(1, 2)})
        self.assertEqual(target[3], {(1, 2, 3)})

    def test_project_four_level(self):
        target = {L: set() for L in (1, 2, 3, 4)}
        _project([1, 2, 3, 4], [1, 2, 3, 4], target)
        self.assertEqual(target[4], {(1, 2, 3, 4)})

    def test_project_only_up_to_available_components(self):
        # A 2-component token in a 3-level config only fills levels 1 and 2.
        target = {L: set() for L in (1, 2, 3)}
        _project([1, 2], [1, 2, 3], target)
        self.assertEqual(target[1], {(1,)})
        self.assertEqual(target[2], {(1, 2)})
        self.assertEqual(target[3], set())

    def test_build_item_re_matches_component_count(self):
        re3 = _build_item_re(3)
        m = re3.match("1.2.3")
        self.assertIsNotNone(m)
        self.assertEqual([int(g) for g in m.groups()], [1, 2, 3])
        self.assertIsNone(re3.match("1.2"))  # needs exactly 3
        re4 = _build_item_re(4)
        self.assertIsNotNone(re4.match("1.2.3.4"))
        # cache: same object returned
        self.assertIs(_build_item_re(3), re3)


# ==========================================================================
# 3) _partition_sections_by_level — pure-logic partition
# ==========================================================================
class TestPartitionByLevel(unittest.TestCase):

    def test_three_level_subsection_continuity(self):
        # md wrote 1.1.1 and 1.1.3 but not 1.1.2 -> continuity gap at L3.
        md = _sets({(1,)}, {(1, 1), (1, 2), (1, 3)},
                   {(1, 1, 1), (1, 1, 3), (1, 2, 1), (1, 3, 1)})
        raw_hdr = _sets({(1,)}, {(1, 1), (1, 2), (1, 3)},
                         {(1, 1, 1), (1, 1, 2), (1, 1, 3), (1, 2, 1), (1, 3, 1)})
        raw_lbl = dict(raw_hdr)  # labeled items present on every raw section
        out = _partition_sections_by_level(md, raw_hdr, raw_lbl, max_level=3)
        self.assertEqual(out["levels"][3]["continuity"], ["1.2"])
        self.assertEqual(out["levels"][3]["missing"], [])
        self.assertEqual(out["continuity_sections"], ["1.2"])
        self.assertEqual(out["missing_sections"], [])
        # No false finding at the parent section level.
        self.assertEqual(out["levels"][2]["continuity"], [])
        self.assertEqual(out["levels"][2]["missing"], [])

    def test_three_level_subsection_tail(self):
        md = _sets({(1,)}, {(1, 2)}, {(1, 2, 1)})
        raw_hdr = _sets({(1,)}, {(1, 2)}, {(1, 2, 1), (1, 2, 2), (1, 2, 3)})
        raw_lbl = dict(raw_hdr)
        out = _partition_sections_by_level(md, raw_hdr, raw_lbl, max_level=3)
        self.assertEqual(out["levels"][3]["missing"], ["2.2", "2.3"])
        self.assertEqual(out["levels"][3]["continuity"], [])
        self.assertEqual(out["missing_sections"], ["2.2", "2.3"])
        self.assertEqual(out["continuity_sections"], [])

    def test_two_level_book_no_subsection_finding(self):
        # Even though raw contains a 1.1.2-style token, max_level=2 means the
        # subsection level is never checked -> no subsection finding, and the
        # genuine missing SECTION 2 is still reported at L2.
        md = _sets({(1,)}, {(1, 1), (1, 3)})
        raw_hdr = _sets({(1,)}, {(1, 1), (1, 2)})
        raw_lbl = dict(raw_hdr)
        out = _partition_sections_by_level(md, raw_hdr, raw_lbl, max_level=2)
        self.assertEqual(out["levels"][2]["continuity"], ["2"])
        self.assertEqual(out["continuity_sections"], ["2"])
        # Only levels 1 and 2 exist.
        self.assertEqual(sorted(out["levels"].keys()), [1, 2])
        self.assertNotIn(3, out["levels"])

    def test_single_level_book(self):
        md = _sets({(1,)})
        raw_hdr = _sets({(1,)})
        raw_lbl = dict(raw_hdr)
        out = _partition_sections_by_level(md, raw_hdr, raw_lbl, max_level=1)
        self.assertEqual(out["continuity_sections"], [])
        self.assertEqual(out["missing_sections"], [])
        self.assertEqual(out["levels"][1], {"continuity": [], "missing": []})

    def test_empty_md_all_tail(self):
        md = _sets({(1,)}, set())
        raw_hdr = _sets({(1,)}, {(1, 2), (1, 3)})
        raw_lbl = dict(raw_hdr)
        out = _partition_sections_by_level(md, raw_hdr, raw_lbl, max_level=2)
        self.assertEqual(out["levels"][2]["missing"], ["2", "3"])
        self.assertEqual(out["missing_sections"], ["2", "3"])
        self.assertEqual(out["continuity_sections"], [])

    def test_ancestor_prefix_auto_exists(self):
        # raw has a labeled subsection 1.2.1/1.2.2 but NO explicit 1.2 header;
        # projection auto-creates the (1,2) prefix. md has ## §1.2 (so the
        # parent section is present) -> no false L2 continuity finding.
        md = _sets({(1,)}, {(1, 1), (1, 2), (1, 3)}, set())
        # raw subsection labeled items auto-project (1,2) into L2 header set.
        raw_lbl = _sets({(1,)}, {(1, 1), (1, 2), (1, 3)},
                         {(1, 2, 1), (1, 2, 2)})
        raw_hdr = dict(raw_lbl)
        out = _partition_sections_by_level(md, raw_hdr, raw_lbl, max_level=3)
        # subsection 1.2.1 / 1.2.2 missing (tail) at L3, parent 1.2 OK at L2.
        self.assertEqual(sorted(out["levels"][3]["missing"]), ["2.1", "2.2"])
        self.assertEqual(out["levels"][2]["continuity"], [])
        self.assertEqual(out["levels"][2]["missing"], [])


# ==========================================================================
# 4) check_d_layer end-to-end (synthetic md + raw page JSON)
# ==========================================================================
class TestCheckDLayerE2E(unittest.TestCase):
    """Drive the full scan: read .md section headers + scan raw page JSON."""

    def _case(self, primary_type, md_content, page_texts,
              section_types=None):
        tmp = tempfile.mkdtemp(prefix="d_layer_e2e_")
        md = os.path.join(tmp, "ch.md")
        _write_md(md, md_content)
        ext = os.path.join(tmp, "_extract")
        _make_page(os.path.join(ext, "page_001.json"), page_texts)
        cfg = BookConfig(
            ordinal=[GroupConfig(
                type=primary_type,
                scope=SCOPE_CHAPTER,
            )],
            section_types=list(section_types or []),
        )
        return check_d_layer(1, 1, 1, md, ext, cfg=cfg), tmp

    def test_three_level_subsection_continuity_e2e(self):
        md = "# Chapter 1\n\n## §1\n\n### §1.1\n\n#### §1.1.1\n\n#### §1.1.3\n"
        # raw presents §1.1.2 header + a labeled item 1.1.2 定义 (close label).
        pages = ["§1.1.2 小节二", "1.1.2 定义 某定义内容此处", "§1.1.1 小节一",
                 "1.1.1 定义 已有", "§1.1.3 小节三", "1.1.3 命题 已有"]
        out, _ = self._case(ORDINAL_THREE_LEVEL, md, pages)
        self.assertIn("levels", out)
        self.assertEqual(out["levels"][3]["continuity"], ["1.2"])
        self.assertEqual(out["continuity_sections"], ["1.2"])
        self.assertEqual(out["missing_sections"], [])

    def test_two_level_book_no_subsection_false_positive_e2e(self):
        # ordinal=2 -> max_level 2. raw contains 1.1.2-style text; the missing
        # SECTION 2 must be reported, but NO subsection finding must appear.
        md = "# Chapter 1\n\n## §1\n\n### §1.1\n\n### §1.3\n"
        pages = ["§1.2 第二节", "1.2 定义 第二节定义",
                 "§1.1.2 嵌套小节", "1.1.2 定义 嵌套",  # subsection-like noise
                 "§1.1 第一节", "1.1 定理 已有",
                 "§1.3 第三节", "1.3 引理 已有"]
        out, _ = self._case(ORDINAL_TWO_LEVEL, md, pages)
        self.assertEqual(sorted(out["levels"].keys()), [1, 2])
        self.assertEqual(out["levels"][2]["continuity"], ["2"])
        self.assertEqual(out["continuity_sections"], ["2"])
        # Crucial: no level-3 (subsection) finding for a two-level book.
        self.assertNotIn(3, out["levels"])

    def test_four_level_subsection_continuity_e2e(self):
        md = ("# Chapter 1\n\n## §1\n\n### §1.1\n\n#### §1.1.1\n\n"
              "##### §1.1.1.1\n\n##### §1.1.1.3\n")
        pages = ["§1.1.1.2 子小节二", "1.1.1.2 定义 子小节定义",
                 "§1.1.1.1 子小节一", "1.1.1.1 定义 已有",
                 "§1.1.1.3 子小节三", "1.1.1.3 定义 已有"]
        tmp = tempfile.mkdtemp(prefix="d4_")
        md_path = os.path.join(tmp, "ch.md")
        _write_md(md_path, md)
        ext = os.path.join(tmp, "_extract")
        _make_page(os.path.join(ext, "page_001.json"), pages)
        cfg = BookConfig(
            ordinal=[GroupConfig(type=ORDINAL_THREE_LEVEL,
                                 scope=SCOPE_CHAPTER)],
            section_types=[1, 2, 3, 4],
        )
        out = check_d_layer(1, 1, 1, md_path, ext, cfg=cfg)
        self.assertEqual(out["levels"][4]["continuity"], ["1.1.2"])
        self.assertEqual(out["continuity_sections"], ["1.1.2"])


# ==========================================================================
# 5) gm / roman path — must NOT emit a 'levels' key
# ==========================================================================
class TestCheckDLayerGM(unittest.TestCase):

    def _gm_setup(self, md_content, page_texts, chapter_map):
        tmp = tempfile.mkdtemp(prefix="d_gm_")
        md = os.path.join(tmp, "ch.md")
        _write_md(md, md_content)
        ext = os.path.join(tmp, "_extract")
        _make_page(os.path.join(ext, "page_001.json"), page_texts)
        with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
            json.dump(chapter_map, f)
        return md, ext, tmp

    def test_gm_returns_no_levels_key(self):
        md = "## §1. Triangulated Spaces\n\n### 1. Main Definitions\n\n### 3. Proposition\n"
        pages = ["§1. Triangulated Spaces", "1. Main Definitions",
                 "3. Proposition. Statement here"]
        md_path, ext, _ = self._gm_setup(
            md, pages, {"chapters": [{"num": 1, "sections": [
                {"sec": 1, "start": 1, "end": 1}]}]})
        cfg = BookConfig(ordinal=[GroupConfig(type=ORDINAL_GM,
                                             scope=SCOPE_CHAPTER)])
        out = check_d_layer(1, 1, 1, md_path, ext, cfg=cfg)
        self.assertNotIn("levels", out)
        self.assertIn("continuity_sections", out)
        self.assertIn("missing_sections", out)

    def test_gm_missing_section_reported_without_levels(self):
        # raw has section 2 present, md only §1 -> continuity gap, still no
        # 'levels' (gm uses the legacy two-bucket partition).
        md = "## §1. Triangulated Spaces\n"
        pages = ["§1. Triangulated Spaces", "1. Main Definitions",
                 "§2. Simplicial Sets", "2. Auxiliary. Some"]
        md_path, ext, _ = self._gm_setup(
            md, pages, {"chapters": [{"num": 1, "sections": [
                {"sec": 1, "start": 1, "end": 1},
                {"sec": 2, "start": 1, "end": 1}]}]})
        cfg = BookConfig(ordinal=[GroupConfig(type=ORDINAL_GM,
                                             scope=SCOPE_CHAPTER)])
        out = check_d_layer(1, 1, 1, md_path, ext, cfg=cfg)
        self.assertNotIn("levels", out)
        # gm path returns chapter-local INTEGER section numbers (legacy
        # behaviour, unchanged by this change) — report formats them
        # identically to the generalized rel-path strings ("§1.2").
        self.assertEqual(out["missing_sections"], [2])
        self.assertEqual(out["continuity_sections"], [])

    def test_roman_routes_to_gm_no_levels(self):
        md = "## §1. Triangulated Spaces\n"
        pages = ["§1. Triangulated Spaces", "1. Main Definitions"]
        md_path, ext, _ = self._gm_setup(
            md, pages, {"chapters": [{"num": 1, "sections": [
                {"sec": 1, "start": 1, "end": 1}]}]})
        cfg = BookConfig(ordinal=[GroupConfig(type=ORDINAL_ROMAN,
                                             scope=SCOPE_CHAPTER)])
        out = check_d_layer(1, 1, 1, md_path, ext, cfg=cfg)
        self.assertNotIn("levels", out)


# ==========================================================================
# 6) report.print_result — per-level block must NOT double-count problems
# ==========================================================================
class TestReportNoDoubleCount(unittest.TestCase):

    def test_levels_block_does_not_double_count(self):
        from verify.script.report import print_result
        r = dict(DEFAULT_RESULT)
        r["d_layer"] = {
            "continuity_sections": ["1.2"],
            "missing_sections": [],
            "levels": {3: {"continuity": ["1.2"], "missing": []}},
        }
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            status = print_result(r)
        out = buf.getvalue()
        self.assertEqual(status, "FAIL")
        self.assertIn("D-LAYER CONTINUITY GAP (1)", out)
        self.assertIn("D-LAYER LEVEL 3 CONTINUITY GAP (1)", out)
        # The merged list drives the FAIL-gate count; the per-level block must
        # NOT add a second problem -> exactly "1 D-layer section-gaps".
        self.assertIn("1 D-layer section-gaps", out)
        self.assertNotIn("2 D-layer section-gaps", out)

    def test_levels_block_with_no_findings_skips(self):
        from verify.script.report import print_result
        r = dict(DEFAULT_RESULT)
        r["d_layer"] = {"continuity_sections": [], "missing_sections": [],
                        "levels": {1: {"continuity": [], "missing": []}}}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            status = print_result(r)
        self.assertEqual(status, "PASS")
        self.assertNotIn("D-LAYER LEVEL", buf.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
