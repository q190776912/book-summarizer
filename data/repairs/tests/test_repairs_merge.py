# -*- coding: utf-8 -*-
"""Regression tests for ``Repairs.merge`` (mode-B base fold + cross-section arbitration).

Background
----------
A scanned book with a legacy OCR text layer runs BOTH repair channels:
``mm_repair_text_compare.py`` (mode B) writes its candidate verdicts straight into
``_mm_repair/repairs.json``, then mode A vision agents re-review the entries mode B
could not settle and write one fragment per batch.  ``merge`` knew only about
``repairs_part_*.json`` and then **overwrote** ``repairs.json`` — so folding the two
channels meant either hand-merging (unmechanical, lossy) or losing all of mode B.

🔴 The second, subtler hazard: ``mm_repair_apply.py`` consumes the sections in a
fixed precedence (corrections > ok > to_structured > unavailable).  When a vision
agent downgrades a mode-B *candidate* correction to ``ok`` (text layer was garbage,
original OCR was right), a naive merge leaves the key in BOTH sections and apply
silently writes the stale text-layer junk back — the exact "假绿" failure the
repair chain exists to prevent.  A merge must therefore be **cross-section
consistent**: the newer ruling wins and the key is stripped everywhere else.

Run:
    python data/repairs/tests/test_repairs_merge.py
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "data", "repairs")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from repairs import Repairs  # noqa: E402


def _dump(path, doc):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False)


class MergeBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.addCleanup(self.tmp.cleanup)

    def manifest(self, pages):
        """pages: {page: [key, ...]}"""
        _dump(os.path.join(self.dir, "manifest.json"),
              {"pages": {p: {"sheet": f"page_{p}_sheet.png",
                             "entries": [{"key": k,
                                          "type": ("formula" if k.startswith("formula") else "text"),
                                          "index": int(k.split(":")[1])} for k in ks]}
                         for p, ks in pages.items()}})

    def merge(self, base_name=None):
        base = os.path.join(self.dir, base_name) if base_name else None
        return Repairs.merge(self.dir, base_path=base)


class TestBaseFold(MergeBase):
    def test_base_entries_survive_and_count(self):
        self.manifest({"014": ["text:5", "formula:2"], "020": ["text:1"]})
        _dump(os.path.join(self.dir, "repairs.modeB.json"), {
            "corrections": {"014": {"text:5": "corrected prose"}},
            "ok": {"020": ["text:1"]},
        })
        _dump(os.path.join(self.dir, "_frag_A00.json"), {
            "corrections": {"014": {"formula:2": r"n \ge 1"}},
        })
        inst, col, warn, counts, report = self.merge("repairs.modeB.json")
        self.assertEqual(inst.corrections["014"]["text:5"], "corrected prose")
        self.assertEqual(inst.corrections["014"]["formula:2"], "n \\ge 1")
        self.assertEqual(inst.ok["020"], ["text:1"])
        self.assertEqual(report["missing"], [])
        self.assertEqual(col, [])
        self.assertTrue(any(t.startswith("base:") for t in counts))

    def test_no_base_keeps_legacy_behaviour(self):
        self.manifest({"014": ["text:5"]})
        _dump(os.path.join(self.dir, "repairs_part_01.json"),
              {"ok": {"014": ["text:5"]}})
        inst, col, warn, counts, report = self.merge()
        self.assertEqual(inst.ok["014"], ["text:5"])
        self.assertFalse(report["base"])

    def test_frag_glob_is_recognised(self):
        _dump(os.path.join(self.dir, "_frag_A06.json"), {"ok": {"014": ["text:1"]}})
        inst, *_ , _ = self.merge()
        self.assertEqual(inst.ok["014"], ["text:1"])


class TestCrossSectionArbitration(MergeBase):
    def test_fragment_downgrade_strips_stale_correction(self):
        """The bug this whole change exists for: apply reads corrections first, so a
        leftover mode-B candidate would outrank the agent's `ok` and re-write junk."""
        self.manifest({"014": ["text:5"]})
        _dump(os.path.join(self.dir, "repairs.modeB.json"), {
            "corrections": {"014": {"text:5": "fop(5m + 4)X5m+4 = v, sj,"}},
        })
        _dump(os.path.join(self.dir, "_frag_A00.json"), {"ok": {"014": ["text:5"]}})
        inst, col, warn, counts, report = self.merge("repairs.modeB.json")
        self.assertNotIn("text:5", inst.corrections.get("014", {}))
        self.assertEqual(inst.ok["014"], ["text:5"])
        self.assertEqual(len(report["overrides"]), 1)
        self.assertEqual(col, [])

    def test_fragment_value_wins_within_same_section(self):
        self.manifest({"014": ["text:5"]})
        _dump(os.path.join(self.dir, "repairs.modeB.json"),
              {"corrections": {"014": {"text:5": "Oc,"}}})
        _dump(os.path.join(self.dir, "_frag_A00.json"),
              {"corrections": {"014": {"text:5": "\\phi(x)"}}})
        inst, col, *_ = self.merge("repairs.modeB.json")
        self.assertEqual(inst.corrections["014"]["text:5"], "\\phi(x)")
        self.assertEqual(col, [])

    def test_page_emptied_by_override_is_dropped_not_left_blank(self):
        self.manifest({"014": ["text:5"]})
        _dump(os.path.join(self.dir, "repairs.modeB.json"),
              {"corrections": {"014": {"text:5": "junk"}}})
        _dump(os.path.join(self.dir, "_frag_A00.json"),
              {"unavailable": {"014": ["text:5"]}})
        inst, *_ = self.merge("repairs.modeB.json")
        self.assertNotIn("014", inst.corrections)
        self.assertEqual(inst.unavailable["014"], ["text:5"])

    def test_two_fragments_ruling_the_same_entry_is_a_collision(self):
        """Same tier = real anomaly (the fan-out plan promises disjoint pages)."""
        self.manifest({"014": ["text:5"]})
        _dump(os.path.join(self.dir, "_frag_A00.json"), {"ok": {"014": ["text:5"]}})
        _dump(os.path.join(self.dir, "_frag_A01.json"),
              {"corrections": {"014": {"text:5": "second opinion"}}})
        inst, col, warn, counts, report = self.merge()
        self.assertTrue(col)


class TestCoverage(MergeBase):
    def test_unruled_entry_is_reported(self):
        self.manifest({"014": ["text:5", "formula:9"]})
        _dump(os.path.join(self.dir, "_frag_A00.json"), {"ok": {"014": ["text:5"]}})
        inst, col, warn, counts, report = self.merge()
        self.assertEqual(report["missing"], [("014", "formula:9")])

    def test_mode_b_candidate_on_reviewed_page_stays_open(self):
        """Silence is not a verdict: the agent re-reviewed the page but never ruled
        on this text-layer candidate, so merge must surface it instead of letting
        apply write it back as if it had been confirmed."""
        self.manifest({"014": ["text:5", "text:6"], "099": ["text:1"]})
        _dump(os.path.join(self.dir, "repairs.modeB.json"), {
            "corrections": {"014": {"text:5": "junk?", "text:6": "also junk?"},
                            "099": {"text:1": "untouched page"}},
        })
        _dump(os.path.join(self.dir, "_frag_A00.json"),
              {"corrections": {"014": {"text:5": "\\phi(x)"}}})
        inst, col, warn, counts, report = self.merge("repairs.modeB.json")
        self.assertEqual(report["base_unreviewed"], [("014", "text:6", "corrections")])
        self.assertEqual(report["base_unrevisited"], [("099", "text:1", "corrections")])

    def test_mode_b_ok_is_open_too(self):
        """`ok` = "text layer agrees with our OCR" — with a legacy-OCR text layer that
        is the SAME SOURCE with the SAME errors, so it is not a verified verdict."""
        self.manifest({"014": ["text:5", "text:6"]})
        _dump(os.path.join(self.dir, "repairs.modeB.json"),
              {"ok": {"014": ["text:5", "text:6"]}})
        _dump(os.path.join(self.dir, "_frag_A00.json"),
              {"corrections": {"014": {"text:6": "\\varphi(x)^{6}"}}})
        inst, col, warn, counts, report = self.merge("repairs.modeB.json")
        self.assertEqual(report["base_unreviewed"], [("014", "text:5", "ok")])
        self.assertEqual(inst.corrections["014"]["text:6"], "\\varphi(x)^{6}")
        self.assertNotIn("text:6", inst.ok.get("014", []))

    def test_agent_confirming_ok_closes_the_item(self):
        self.manifest({"014": ["text:5"]})
        _dump(os.path.join(self.dir, "repairs.modeB.json"), {"ok": {"014": ["text:5"]}})
        _dump(os.path.join(self.dir, "_frag_A00.json"), {"ok": {"014": ["text:5"]}})
        inst, col, warn, counts, report = self.merge("repairs.modeB.json")
        self.assertEqual(report["base_unreviewed"], [])
        self.assertEqual(inst.ok["014"], ["text:5"])
        self.assertFalse(col)

    def test_deferred_bucket_does_not_count_as_ruled(self):
        """apply ignores `deferred`; leaving one folded in must not fake coverage."""
        self.manifest({"014": ["text:5"]})
        _dump(os.path.join(self.dir, "repairs.modeB.json"),
              {"deferred": {"014": ["text:5"]}})
        _dump(os.path.join(self.dir, "_frag_A00.json"), {"corrections": {}})
        inst, col, warn, counts, report = self.merge("repairs.modeB.json")
        self.assertIn(("014", "text:5"), report["missing"])

    def test_unknown_key_still_warns(self):
        self.manifest({"014": ["text:5"]})
        _dump(os.path.join(self.dir, "_frag_A00.json"), {"ok": {"014": ["text:77"]}})
        inst, col, warn, counts, report = self.merge()
        self.assertTrue(any("text:77" in w for w in warn))


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestCliGates(MergeBase):
    """merge() must REFUSE to hand mm_repair_apply.py a repairs.json that still
    carries an unexamined text-layer claim: `ok` from the embedded layer only
    proves the layer matches our own OCR, and apply would stamp it mm_reviewed."""

    def _run(self, *extra):
        import contextlib
        import io
        from unittest import mock
        from repairs import main as merge_main
        argv = [self.dir, self.dir] + list(extra)
        buf = io.StringIO()
        with mock.patch.object(sys, "argv", ["repairs.py"] + argv):
            with contextlib.redirect_stdout(buf):
                rc = merge_main()
        return rc, buf.getvalue()

    def _base_ok_unruled(self):
        self.manifest({"014": ["text:5", "text:9"], "020": ["text:1"]})
        _dump(os.path.join(self.dir, "repairs.modeB.json"),
              {"ok": {"014": ["text:5"], "020": ["text:1"]}})
        _dump(os.path.join(self.dir, "_frag_A00.json"),
              {"corrections": {"014": {"text:9": r"x \le n"}}})

    def test_refuses_open_mode_b_verdict_and_keeps_repairs_unwritten(self):
        self._base_ok_unruled()
        rc, out = self._run("--base", os.path.join(self.dir, "repairs.modeB.json"))
        self.assertEqual(rc, 1)
        self.assertIn("OPEN MODE-B VERDICTS", out)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "repairs.json")),
                         "a dirty merge must not produce the file apply consumes")
        rep = json.load(open(os.path.join(self.dir, "_merge_report.json"), encoding="utf-8"))
        self.assertEqual(len(rep["base_unreviewed"]) + len(rep["base_unrevisited"]), 2)

    def test_clean_merge_writes_repairs_and_report_is_empty(self):
        self.manifest({"014": ["text:5", "text:9"]})
        _dump(os.path.join(self.dir, "repairs.modeB.json"), {"ok": {"014": ["text:5"]}})
        _dump(os.path.join(self.dir, "_frag_A00.json"),
              {"corrections": {"014": {"text:9": "n"}}, "ok": {"014": ["text:5"]}})
        rc, out = self._run("--base", os.path.join(self.dir, "repairs.modeB.json"))
        self.assertEqual(rc, 0, out)
        self.assertTrue(os.path.exists(os.path.join(self.dir, "repairs.json")))
        rep = json.load(open(os.path.join(self.dir, "_merge_report.json"), encoding="utf-8"))
        for k in ("missing", "base_unreviewed", "base_unrevisited", "collisions"):
            self.assertEqual(rep[k], [], k)

    def test_two_fragments_ruling_the_same_entry_block_apply(self):
        self.manifest({"014": ["text:5"]})
        _dump(os.path.join(self.dir, "_frag_A00.json"), {"ok": {"014": ["text:5"]}})
        _dump(os.path.join(self.dir, "_frag_A01.json"),
              {"corrections": {"014": {"text:5": "junk"}}})
        rc, out = self._run()
        self.assertEqual(rc, 1)
        self.assertIn("COLLISIONS", out)
        self.assertFalse(os.path.exists(os.path.join(self.dir, "repairs.json")))


class TestApplyGate(MergeBase):
    """apply (修复趟) reads merge's report instead of re-implementing the check."""

    def _gate(self, doc=None):
        import mm_repair_apply as A
        mm = os.path.join(self.dir, "_mm_repair")
        os.makedirs(mm, exist_ok=True)
        if doc is not None:
            _dump(os.path.join(mm, "_merge_report.json"), doc)
        return A.open_verdict_gate(mm)

    def test_absent_report_passes_for_books_without_merge(self):
        allowed, why = self._gate(None)
        self.assertTrue(allowed, why)

    def test_open_verdicts_block(self):
        allowed, why = self._gate({"base_unreviewed": [["014", "text:5", "ok"]],
                                   "base_unrevisited": [], "missing": [], "collisions": []})
        self.assertFalse(allowed)
        self.assertIn("STALE", why)

    def test_clean_report_passes(self):
        allowed, why = self._gate({"base_unreviewed": [], "base_unrevisited": [],
                                   "missing": [], "collisions": []})
        self.assertTrue(allowed, why)
