"""EN three-level dispatch must follow the PRINTED heading form
(Kreyszig incident, 2026-09-25).

Root cause: build_structure._extract_items routed ORDINAL_THREE_LEVEL +
language=en unconditionally to extract_items_en3, which requires LABEL-FIRST
heads ("Definition 1.1.1").  Kreyszig prints NUMBER-FIRST heads
("1.1-1 Definition (Metric space, metric).") — the whole book nearly vanished
from the contract (ch1: 3 items captured vs 50 candidates by the generic
three-level extractor, which explicitly supports "N.S-N Lemma" English heads).

Fix under test (build_structure._three_level_en_number_first + dispatch):
  * probe counts block-start heads of both forms per chapter; number-first
    wins only when nf >= 5 AND nf > lf -> generic extract_items path;
  * label-first books (Strogatz / Lasota) and mixed-noise pages keep the
    exact prior en3 behavior (nf < 5 or lf >= nf).

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_three_level_en_form_dispatch.py
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
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import build_structure as bs


def _mk_pages(d, lines):
    """Write page_001..NNN.json whose single text block carries `lines`."""
    for i, ln in enumerate(lines, start=1):
        fp = os.path.join(d, f"page_{i:03d}.json")
        with open(fp, "w", encoding="utf-8") as f:
            json.dump({"text": [{"text": ln}], "formulas": []}, f)


NF_HEADS = [
    "1.1-1 Definition (Metric space, metric). A metric space is a set X.",
    "1.1-2 Examples  Real line R.",
    "1.2-3 Definition (Space l). The set of all bounded sequences.",
    "1.3-4 Theorem (Banach space). The space l is complete.",
    "1.3-5 Lemma (Triangle inequality). We have d(x,y) <= d(x,z)+d(z,y).",
    "1.4-6 Corollary. Every convergent sequence is bounded.",
]
LF_HEADS = [
    "Definition 1.1.1 (Metric space). A metric space is a set X.",
    "Theorem 1.2.3 (Banach). The space is complete.",
    "Example 1.2.4  Real line R.",
    "Lemma 1.3.1 Triangle inequality.",
    "Corollary 1.3.2 Every convergent sequence is bounded.",
]


class TestProbe(unittest.TestCase):
    def test_number_first_detected(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, NF_HEADS)
            self.assertTrue(bs._three_level_en_number_first(d, 1, len(NF_HEADS)))

    def test_label_first_not_swallowed(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, LF_HEADS)
            self.assertFalse(bs._three_level_en_number_first(d, 1, len(LF_HEADS)))

    def test_minority_noise_keeps_en3(self):
        # 4 number-first refs (< threshold 5) must NOT flip the route.
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, NF_HEADS[:4] + LF_HEADS)
            self.assertFalse(bs._three_level_en_number_first(d, 1, 9))

    def test_tie_breaks_to_en3(self):
        # equal counts => conservative default (existing en3 behavior).
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, NF_HEADS + LF_HEADS[:6])
            self.assertFalse(bs._three_level_en_number_first(d, 1, 12))

    def test_inline_prose_refs_not_counted(self):
        # "…see 1.2-1 and…" mid-line / "we can obtain" after number: not a head.
        prose = [
            "1. Show that in 1.2-1 we can obtain another metric by replacing.",
            "It follows from 1.3-4 that the space is complete, see also 2.1-1.",
            "(1.1-1) Definition of metric is in section 1.1.",
        ]
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, prose)
            self.assertFalse(bs._three_level_en_number_first(d, 1, len(prose)))

    def test_missing_pages_no_crash(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(bs._three_level_en_number_first(d, 1, 5))


class TestDispatch(unittest.TestCase):
    class _Book:
        primary_type = bs.ORDINAL_THREE_LEVEL
        language = "en"
        chapter_first = True
        section_scoped = False
        gm_bare_numbered = False
        ordinal = []

    def test_number_first_routes_to_generic(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, NF_HEADS)
            items = bs._extract_items(d, 1, 1, len(NF_HEADS), self._Book())
            keys = {it["key"] for it in items}
            self.assertIn("1.1-1", keys)   # generic bare-numeric key
            self.assertIn("1.2-3", keys)
            # the en3 route captured nothing of these number-first heads
            self.assertEqual(bs.extract_items_en3(d, 1, 1, len(NF_HEADS)), [])

    def test_label_first_still_routes_to_en3(self):
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, LF_HEADS)
            items = bs._extract_items(d, 1, 1, len(LF_HEADS), self._Book())
            keys = {it["key"] for it in items}
            self.assertIn("1.1-1", keys)
            self.assertIn("1.2-3", keys)
            self.assertIn("1.3-1", keys)


class TestNumberFirstDedup(unittest.TestCase):
    """Same-key head/reference collisions (Kreyszig 2026-09 dedup)."""

    def _it(self, key, text, page=1):
        return {"key": key, "label": "", "page": page, "text": text}

    def test_reference_loses_to_real_head(self):
        real = self._it("1.2-3", "1.2-3 Definition (Hilbert sequence space l2). "
                                  "This space consists of all sequences...")
        ref1 = self._it("1.2-3", "1.2-3 in the next section.) It is a sequence space", page=22)
        ref2 = self._it("1.2-3", "1.2-3.)", page=38)
        out = bs._nf_dedup_items([ref1, real, ref2])
        self.assertEqual(len(out), 1)
        self.assertIs(out[0], real)

    def test_funcword_tail_rejected_but_lowercase_title_kept(self):
        # 'n-tuples' lowercase heading title is REAL (Kreyszig 4.1-4);
        # 'and M is complete' after the number is a reference continuation.
        self.assertTrue(bs._nf_heading_like(
            self._it("4.1-4", "4.1-4 n-tuples of numbers. Let M be the set of all ordered")))
        self.assertFalse(bs._nf_heading_like(
            self._it("1.4-5", "1.4-5 and M is complete, (xn) converges in M, the limit")))
        self.assertFalse(bs._nf_heading_like(
            self._it("1.4-5", "1.4-5), say, convergence holds")))
        self.assertFalse(bs._nf_heading_like(
            self._it("2.6-4", "2.6-4?")))
        self.assertFalse(bs._nf_heading_like(
            self._it("1.5-3", "mple 1.5-3 in the next section includes")))

    def test_unique_reference_key_never_dropped(self):
        lone = self._it("9.9-9", "9.9-9, below). See the discussion.")
        out = bs._nf_dedup_items([lone])
        self.assertEqual([it["key"] for it in out], ["9.9-9"])

    def test_order_preserved_first_occurrence(self):
        a = self._it("1.1-1", "1.1-1 Definition (Metric space). A metric space...")
        b = self._it("1.2-1", "1.2-1 Theorem (Banach space). The space is complete...")
        c = self._it("1.1-1", "1.1-1 in the next section.")
        out = bs._nf_dedup_items([a, b, c])
        self.assertEqual([it["key"] for it in out], ["1.1-1", "1.2-1"])
        self.assertIs(out[0], a)

    def test_lettered_paren_ref_tail_rejected(self):
        # "(a)"/"(c)" reference tails must NOT outrank the printed heading
        # (Kreyszig 8.1-4@461 / 4.8-4@281 scramble, 2026-09-26).
        self.assertFalse(bs._nf_heading_like(
            self._it("8.1-4", "8.1-4(a) and a sum of compact operators is "
                              "compact. Let us prove that")))
        self.assertFalse(bs._nf_heading_like(
            self._it("4.8-4", "4.8-4(c). The two remaining concepts are "
                              "called strong and weak*")))
        # a genuine parenthesized TITLE ("(Finite dimensional domain...)")
        # stays heading-like.
        self.assertTrue(bs._nf_heading_like(
            self._it("8.1-4", "8.1-4 Theorem (Finite dimensional domain or "
                              "range). Let X and Y")))

    def test_position_follows_chosen_head_not_first_slot(self):
        # ref to 4.6-8 sits in the stream BEFORE real 4.6-7; after collapsing
        # the real head (4.6-8@260) must sort AFTER 4.6-7, not keep the ref slot.
        ref8 = self._it("4.6-8", "4.6-8 (below), which states that separability", page=257)
        head7 = self._it("4.6-7", "4.6-7 Theorem (Dual space). Let X be a normed space", page=258)
        head8 = self._it("4.6-8", "4.6-8 Theorem (Separability). If the dual space X", page=260)
        out = bs._nf_dedup_items([ref8, head7, head8])
        self.assertEqual([(it["key"], it["page"]) for it in out],
                         [("4.6-7", 258), ("4.6-8", 260)])


class TestUniqueKeysGenuineReplacesRef(unittest.TestCase):
    """item_dedup.dedup_items(unique_keys=True): a genuine head arriving after
    a reference-only group must REPLACE the phantom, not append a second entry
    (Kreyszig 4.12-2: prose ref p224 + real head p301 emitted both pages)."""

    def _ref(self):
        return {"key": "4.12-2", "label": "定理", "page": 224, "mstart": 24,
                "text": "orem 4.12-2. This theorem states that a bounded linear"}

    def _head(self):
        return {"key": "4.12-2", "label": "定理", "page": 301, "mstart": 0,
                "text": "4.12-2 Open Mapping Theorem, Bounded Inverse Theorem. A "
                        "bounded linear operator"}

    def test_single_entry_at_head_page(self):
        import item_dedup
        out = item_dedup.dedup_items([self._ref(), self._head()], unique_keys=True)
        same = [it for it in out if it["key"] == "4.12-2"]
        self.assertEqual(len(same), 1)
        self.assertEqual(same[0]["page"], 301)

    def test_reference_arriving_after_head_still_dropped(self):
        import item_dedup
        out = item_dedup.dedup_items([self._head(), self._ref()], unique_keys=True)
        same = [it for it in out if it["key"] == "4.12-2"]
        self.assertEqual(len(same), 1)
        self.assertEqual(same[0]["page"], 301)


class TestRefVetoWindow(unittest.TestCase):
    """_REF_AFTER_NEG must only veto on text IMMEDIATELY after the number
    (Kreyszig 6.2-4/7.3-3 incident, 2026-09-26): a real heading whose title
    sentence legitimately contains 'We have:' / 'as in' was searched over the
    WHOLE 80-char preview, marked non-genuine, and dedup kept the same-key
    reference phantom (6.2-4 anchored to its p342 cross-ref page)."""

    def _it(self, key, page, text, label="uncat", mstart=0):
        return {"key": key, "label": label, "page": page, "mstart": mstart,
                "text": text, "glued_label": None}

    def test_we_have_in_title_body_stays_genuine(self):
        import item_dedup
        head = self._it("6.2-4", 348,
                        "6.2-4 Lemma (Strict convexity).  We have:", label="引理")
        self.assertTrue(item_dedup._is_genuine(head))

    def test_as_in_title_body_stays_genuine(self):
        import item_dedup
        head = self._it("7.3-3", 392,
                        "7.3-3 Representation Theorem (Resolvent). For X and T as in")
        self.assertTrue(item_dedup._is_genuine(head))

    def test_glued_we_have_reference_still_vetoed(self):
        import item_dedup
        ref = self._it("1.2-3", 20, "1.2-3 we have shown that the operator is "
                                    "bounded, hence…")
        self.assertFalse(item_dedup._is_genuine(ref))

    def test_dedup_keeps_real_head_over_wrapped_ref(self):
        import item_dedup
        ref = self._it("6.2-4", 342, "6.2-4 and Sec. 6.5). For general normed "
                                     "spaces one may need addi-", label="uncat")
        head = self._it("6.2-4", 348, "6.2-4 Lemma (Strict convexity).  We have:",
                        label="引理")
        midref = self._it("6.2-4", 349, "emma 6.2-4 we see that in",
                          label="引理", mstart=35)
        out = item_dedup.dedup_items([ref, head, midref], unique_keys=True)
        lem = [it for it in out if it["label"] == "引理"]
        self.assertEqual([(it["page"], it["key"]) for it in lem], [(348, "6.2-4")])


if __name__ == "__main__":
    unittest.main(verbosity=2)
