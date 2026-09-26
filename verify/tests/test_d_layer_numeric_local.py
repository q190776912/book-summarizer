"""D-layer must STRICTLY verify the Arnold-ODE third tier (numeric local subs).

``_check_d_layer_global`` previously knew only two tiers: single-number global §
and bare-LETTER sub-blocks (role 5).  Arnold ODE adds a THIRD tier of bare
numeric subsections that RESTART per § (contract keys ``1.1 .. 1.18``).  The md
transcribes them as ``### 3. Title`` (no ``§``).  This test pins that the D-layer
now reports:

  * a subsection omitted from the md  -> ``missing_sections``  (``§P.K``),
  * a hole BELOW the largest written local number -> ``continuity_sections``,
  * a complete transcription -> clean (no false positives, the decisive
    regression guard for the real pipeline).

``_load_global_contract`` (which would otherwise read book_structure/ch*.json) is
patched, so this exercises the md-vs-contract comparison in isolation.

Runs under stdlib unittest:
  python verify/tests/test_d_layer_numeric_local.py
"""
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
    _ROOT = str(Path(__file__).resolve().parents[1])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import section_continuity as SC
from verify_config import BookConfig


def _cfg():
    return BookConfig.from_dict({
        "ordinal": [{"type": 1, "name": ["Theorem"], "scope": 2}],
        "language": "en",
        "section_types": [1, 1, 1],
        "sections_global": True,
        "numeric_local_sections": True,
        "strict": True,
    })


# contract § + dotted subsection keys (book order); here §1(1..3), §2(1..2)
_CONTRACT_SECS = ["1", "1.1", "1.2", "1.3", "2", "2.1", "2.2"]


class TestDLayerNumericLocal(unittest.TestCase):
    def _run(self, md_text, contract_secs):
        orig = SC._load_global_contract
        SC._load_global_contract = lambda ext, ch: (list(contract_secs), {})
        try:
            with tempfile.TemporaryDirectory() as d:
                mdp = os.path.join(d, "ch1.md")
                with open(mdp, "w", encoding="utf-8") as f:
                    f.write(md_text)
                return SC._check_d_layer_global(1, 1, 1, mdp, d, _cfg())
        finally:
            SC._load_global_contract = orig

    def test_complete_transcription_is_clean(self):
        md = "\n".join([
            "# Chapter 1",
            "## §1 Phase Spaces",
            "### 1. Examples of Evolutionary Processes",
            "### 2. Phase Spaces",
            "### 3. The Integral Curves of a Direction Field",
            "## §2 Vector Fields on the Line",
            "### 1. Existence and Uniqueness of Solutions",
            "### 2. A Counterexample",
        ])
        res = self._run(md, _CONTRACT_SECS)
        self.assertEqual(res["missing_sections"], [])
        self.assertEqual(res["continuity_sections"], [])

    def test_omitted_subsection_is_missing_tail(self):
        md = "\n".join([
            "## §1 Phase Spaces",
            "### 1. Examples of Evolutionary Processes",
            "### 2. Phase Spaces",
            "### 3. The Integral Curves of a Direction Field",
            "## §2 Vector Fields on the Line",
            "### 1. Existence and Uniqueness of Solutions",
            # §2 subsection 2 dropped from the end -> missing tail
        ])
        res = self._run(md, _CONTRACT_SECS)
        self.assertIn("§2.2", res["missing_sections"])
        self.assertNotIn("§2.2", res["continuity_sections"])

    def test_interior_hole_is_continuity(self):
        md = "\n".join([
            "## §1 Phase Spaces",
            "### 1. Examples of Evolutionary Processes",
            # §1 subsection 2 dropped but 3 present -> interior hole
            "### 3. The Integral Curves of a Direction Field",
            "## §2 Vector Fields on the Line",
            "### 1. Existence and Uniqueness of Solutions",
            "### 2. A Counterexample",
        ])
        res = self._run(md, _CONTRACT_SECS)
        self.assertIn("§1.2", res["continuity_sections"])
        self.assertNotIn("§1.2", res["missing_sections"])

    def test_all_subs_of_a_section_missing_is_tail(self):
        md = "\n".join([
            "## §1 Phase Spaces",
            "### 1. Examples of Evolutionary Processes",
            "### 2. Phase Spaces",
            "### 3. The Integral Curves of a Direction Field",
            "## §2 Vector Fields on the Line",
            # §2 written but BOTH subsections omitted
            "body text under section two with no sub heads",
        ])
        res = self._run(md, _CONTRACT_SECS)
        self.assertIn("§2.1", res["missing_sections"])
        self.assertIn("§2.2", res["missing_sections"])

    def test_disabled_for_non_numeric_local_books(self):
        # numeric_local_sections absent -> tier ignored entirely (zero regression).
        cfg = BookConfig.from_dict({
            "ordinal": [{"type": 1, "name": ["Theorem"], "scope": 2}],
            "language": "en", "section_types": [1, 1], "sections_global": True,
            "strict": True,
        })
        orig = SC._load_global_contract
        SC._load_global_contract = lambda ext, ch: (list(_CONTRACT_SECS), {})
        try:
            with tempfile.TemporaryDirectory() as d:
                mdp = os.path.join(d, "ch1.md")
                with open(mdp, "w", encoding="utf-8") as f:
                    f.write("## §1 Phase Spaces\n## §2 Vector Fields\n")
                res = SC._check_d_layer_global(1, 1, 1, mdp, d, cfg)
        finally:
            SC._load_global_contract = orig
        # subsections must NOT be demanded for a book that didn't declare them
        self.assertEqual([s for s in res["missing_sections"] if "." in s], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
