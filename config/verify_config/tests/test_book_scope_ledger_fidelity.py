"""`make_config --force` must neither lose a calibrated counter boundary nor
be unable to express a whole-book counter (2026-09-29).

Root cause (Serre《Linear Representations of Finite Groups》, GTM 42): the book
numbers Theorem / Proposition / Lemma **continuously through the whole book**
(ch2 prints Theorem 3-8, ch12 prints Theorem 24-28 + Proposition 32-37 +
Lemma 12-19), while Corollary restarts per section.  The accepted config
declared exactly that (scope 1 / scope 3, strict false).  `SCOPE_BY_TYPE`
gives single-level (type 1) groups scope=2 — there is **no** detector path
that can ever emit scope=1 — and `_load_old_ordinal` was only consulted for
the Figure group, so a `--force` regenerate rewrote every counter to
"restarts each chapter" and turned `strict` on.  Result measured live:
verify went 40/40 PASS -> 14/40 with 26 chapters of fake B-layer
"缺号 1..17" BLOCKING.

Fixes under test:
  * `_book_scope_votes` / `_refine_book_scope` — derive scope=1 from the
    structure contract's (chapter, number) evidence, fail-closed;
  * `_repaste_old_scopes` — re-attach the previous file's `scope` per label
    (ledger fidelity, same philosophy as `_load_old_manual_flags`);
  * `_load_old_section_cfg` — one map/flat-aware reader, used to keep the old
    `strict` declaration instead of hard-coding True.

Runs under stdlib unittest:
  python config/verify_config/tests/test_book_scope_ledger_fidelity.py
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
for p in (_ROOT, os.path.join(_ROOT, "lib"),
          os.path.join(_ROOT, "config", "verify_config")):
    if p not in sys.path:
        sys.path.insert(0, p)
import lib.boot as _boot
_boot.setup()

import make_config as mc


class TestBookScopeVotes(unittest.TestCase):
    def test_whole_book_continuation_votes_book_scope(self):
        # ch1: Th 1-2, ch2: Th 3-5, ch3: Th 6-7  -> never restarts
        cont, restart = mc._book_scope_votes({1: [1, 2], 2: [3, 4, 5], 3: [6, 7]})
        self.assertEqual((cont, restart), (2, 0))

    def test_per_chapter_restart_votes_restart(self):
        cont, restart = mc._book_scope_votes({1: [1, 2, 3, 4, 5],
                                              2: [1, 2, 3], 3: [1, 2, 3, 4]})
        self.assertEqual((cont, restart), (0, 2))

    def test_needs_two_chapters(self):
        self.assertEqual(mc._book_scope_votes({1: [1, 2, 3]}), (0, 0))


class TestRefineBookScope(unittest.TestCase):
    def setUp(self):
        self._orig = mc._contract_counter_evidence
        self.evidence = []
        mc._contract_counter_evidence = lambda extract_dir, include_chapter=False, \
                letter_chapter=False: list(self.evidence)

    def tearDown(self):
        mc._contract_counter_evidence = self._orig

    def test_single_level_group_becomes_scope_book(self):
        self.evidence = [("Theorem", (1, 1)), ("Theorem", (1, 2)),
                         ("Theorem", (2, 3)), ("Theorem", (2, 4)),
                         ("Theorem", (3, 5)), ("Theorem", (3, 6))]
        arr = [{"type": 1, "name": ["Theorem"], "scope": 2}]
        arr, notes = mc._refine_book_scope("whatever", arr)
        self.assertEqual(arr[0]["scope"], mc.SCOPE_BOOK)
        self.assertTrue(notes)

    def test_restart_counter_stays_chapter_scoped(self):
        self.evidence = [("Theorem", (1, 1)), ("Theorem", (1, 2)),
                         ("Theorem", (2, 1)), ("Theorem", (2, 2)),
                         ("Theorem", (3, 1))]
        arr = [{"type": 1, "name": ["Theorem"], "scope": 2}]
        arr, notes = mc._refine_book_scope("whatever", arr)
        self.assertEqual(arr[0]["scope"], 2)
        self.assertEqual(notes, [])

    def test_multi_level_group_is_never_touched(self):
        # Same numbers, but a type-2 (two-component) group: last-component
        # semantics differ, so refinement must not apply.
        self.evidence = [("Theorem", (1, 1)), ("Theorem", (1, 2)),
                         ("Theorem", (2, 3)), ("Theorem", (3, 5))]
        arr = [{"type": 2, "name": ["Theorem"], "scope": 2}]
        arr, _ = mc._refine_book_scope("whatever", arr)
        self.assertEqual(arr[0]["scope"], 2)

    def test_mixed_group_waits_for_every_label(self):
        # Proposition runs through the book, Lemma restarts per chapter ->
        # the merged group must NOT be reclassified.
        self.evidence = [("Proposition", (1, 1)), ("Proposition", (1, 2)),
                         ("Proposition", (2, 3)), ("Proposition", (3, 5)),
                         ("Lemma", (1, 1)), ("Lemma", (1, 2)),
                         ("Lemma", (2, 1)), ("Lemma", (3, 1))]
        arr = [{"type": 1, "name": ["Proposition", "Lemma"], "scope": 2}]
        arr, notes = mc._refine_book_scope("whatever", arr)
        self.assertEqual(arr[0]["scope"], 2)
        self.assertEqual(notes, [])

    def test_sparse_evidence_is_not_enough(self):
        # Only two chapters carry items -> below the >=3-chapter bar.
        self.evidence = [("Theorem", (1, 1)), ("Theorem", (2, 3))]
        arr = [{"type": 1, "name": ["Theorem"], "scope": 2}]
        arr, notes = mc._refine_book_scope("whatever", arr)
        self.assertEqual(arr[0]["scope"], 2)


class TestRepasteOldScopes(unittest.TestCase):
    def _write(self, payload):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        self.addCleanup(os.remove, path)
        return path

    def test_flat_legacy_account_is_re_attached(self):
        path = self._write({"ordinal": [{"type": 1, "name": ["Theorem"], "scope": 1},
                                        {"type": 1, "name": ["Corollary"],
                                         "scope": 3}]})
        arr = [{"type": 1, "name": ["Theorem"], "scope": 2},
               {"type": 1, "name": ["Proposition", "Lemma", "Example"], "scope": 2},
               {"type": 1, "name": ["Corollary"], "scope": 2},
               {"type": 1, "name": ["Remark"], "scope": 2}]
        arr, notes = mc._repaste_old_scopes(path, arr, "ch")
        self.assertEqual(arr[0]["scope"], 1)       # Theorem  ← old scope 1
        self.assertEqual(arr[2]["scope"], 3)       # Corollary ← old scope 3
        self.assertEqual(arr[1]["scope"], 2)       # untouched (no old record)
        self.assertEqual(arr[3]["scope"], 2)
        self.assertEqual(len(notes), 2)

    def test_map_format_reads_own_section_only(self):
        path = self._write({"ch": {"ordinal": [{"type": 1, "name": ["Theorem"],
                                               "scope": 1}]},
                            "appendix": {"ordinal": [{"type": 14,
                                                      "name": ["Theorem"],
                                                      "scope": 2}]}})
        arr = [{"type": 1, "name": ["Theorem"], "scope": 2}]
        # 深拷贝：两次断言各看一份未被上一次调用改过的 arr
        fresh = lambda: json.loads(json.dumps(arr))
        ch, ch_notes = mc._repaste_old_scopes(path, fresh(), "ch")
        self.assertEqual(ch[0]["scope"], 1)
        self.assertEqual(len(ch_notes), 1)
        app, _ = mc._repaste_old_scopes(path, fresh(), "appendix")
        self.assertEqual(app[0]["scope"], 2)      # 字母段旧账声明 scope=2

    def test_missing_old_file_keeps_detection(self):
        arr = [{"type": 1, "name": ["Theorem"], "scope": 2}]
        arr, notes = mc._repaste_old_scopes(os.devnull, arr, "ch")
        self.assertEqual(arr[0]["scope"], 2)
        self.assertEqual(notes, [])


class TestRepasteOldPartition(unittest.TestCase):
    """旧账的计数器划分优先于本轮合并（缺席证据不推翻正面账本）。"""

    def _write(self, payload):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        self.addCleanup(os.remove, path)
        return path

    OLD = {"ordinal": [{"type": 1, "name": ["Theorem"], "scope": 1},
                       {"type": 1, "name": ["Proposition"], "scope": 1},
                       {"type": 1, "name": ["Lemma"], "scope": 1},
                       {"type": 1, "name": ["Corollary"], "scope": 3}]}

    def test_merged_proposition_lemma_is_split_back(self):
        path = self._write(self.OLD)
        detected = [{"type": 1, "name": ["Proposition", "Lemma", "Example"],
                     "scope": 1},
                    {"type": 1, "name": ["Theorem"], "scope": 1},
                    {"type": 1, "name": ["Corollary"], "scope": 3},
                    {"type": 1, "name": ["Definition"], "scope": 2},
                    {"type": 0, "name": ["Figure"], "scope": 2}]
        arr, notes = mc._repaste_old_partition(path, detected, "ch")
        names = [g["name"] for g in arr]
        self.assertIn(["Proposition"], names)
        self.assertIn(["Lemma"], names)
        self.assertNotIn(["Proposition", "Lemma", "Example"], names)
        # 本轮新检出的标签自己成组，探测 scope 不动
        self.assertIn(["Example"], names)
        self.assertIn(["Definition"], names)
        self.assertIn(["Figure"], names)
        self.assertEqual([g for g in arr if g["name"] == ["Definition"]][0]["scope"], 2)
        self.assertTrue(notes)

    def test_no_old_account_is_noop(self):
        detected = [{"type": 1, "name": ["Theorem"], "scope": 2}]
        arr, notes = mc._repaste_old_partition(os.devnull, detected, "ch")
        self.assertEqual(arr, detected)
        self.assertEqual(notes, [])

    def test_old_merged_group_stays_merged(self):
        # Lee 式真共享计数器：旧账本来就是一组，不得被拆开。
        path = self._write({"ordinal": [{"type": 2, "name": ["Exercise", "Example"],
                                         "scope": 2}]})
        detected = [{"type": 2, "name": ["Exercise", "Example"], "scope": 2}]
        arr, _ = mc._repaste_old_partition(path, detected, "ch")
        self.assertEqual([g["name"] for g in arr], [["Exercise", "Example"]])

    def test_old_label_missing_from_detection_is_kept(self):
        path = self._write(self.OLD)
        detected = [{"type": 1, "name": ["Theorem"], "scope": 1}]
        arr, notes = mc._repaste_old_partition(path, detected, "ch")
        names = [g["name"] for g in arr]
        for want in (["Proposition"], ["Lemma"], ["Corollary"]):
            self.assertIn(want, names)
        self.assertTrue(any("旧账划分" in n for n in notes))

    def test_truncated_old_group_is_backfilled_from_detection(self):
        """残缺旧账（`[{"name": ["Figure"]}]`，无 type/scope）不得原样写出。

        曾经直接产出一个没有 `type` 的组，下游按 `g["type"]` 消费即 KeyError
        （test_fig_group_guarantee.test_inherited_group_missing_fields_falls_back_to_probe
        实测）——账本保真只保**声明过**的字段，缺的必须由本轮探测补齐。
        """
        path = self._write({"ordinal": [{"name": ["Figure"]}]})
        detected = [{"type": 2, "name": ["Theorem"], "scope": 2},
                    {"type": 2, "name": ["Figure"], "scope": 2}]
        arr, _ = mc._repaste_old_partition(path, detected, "ch")
        fig = [g for g in arr if g["name"] == ["Figure"]][0]
        self.assertEqual(fig["type"], 2, "missing type backfilled from probe")
        self.assertEqual(fig["scope"], 2, "missing scope backfilled from probe")
        self.assertTrue(all("type" in g for g in arr),
                        "no group may be emitted without a type")

    def test_truncated_old_group_without_probe_match_uses_primary(self):
        """旧标签本轮完全没检出、旧组又缺字段 → 退回本轮主组字段，仍不写出无 type 组。"""
        path = self._write({"ordinal": [{"name": ["Figure"]}]})
        detected = [{"type": 1, "name": ["Theorem"], "scope": 1}]
        arr, _ = mc._repaste_old_partition(path, detected, "ch")
        fig = [g for g in arr if g["name"] == ["Figure"]][0]
        self.assertEqual(fig["type"], 1)
        self.assertEqual(fig["scope"], 1)


class TestOldSectionCfg(unittest.TestCase):
    def _write(self, payload):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
        self.addCleanup(os.remove, path)
        return path

    def test_strict_survives_both_layouts(self):
        flat = self._write({"strict": False, "ordinal": []})
        self.assertIs(mc._load_old_section_cfg(flat, "ch").get("strict"), False)
        self.assertIs(mc._load_old_section_cfg(flat, "appendix").get("strict"),
                      False)     # 扁平顶层当年对附录同样生效
        mapped = self._write({"ch": {"strict": False},
                              "appendix": {"strict": True}})
        self.assertIs(mc._load_old_section_cfg(mapped, "ch").get("strict"), False)
        self.assertIs(mc._load_old_section_cfg(mapped, "appendix").get("strict"),
                      True)

    def test_unreadable_config_yields_empty(self):
        self.assertEqual(mc._load_old_section_cfg(os.devnull, "ch"), {})


if __name__ == "__main__":
    unittest.main(verbosity=2)
