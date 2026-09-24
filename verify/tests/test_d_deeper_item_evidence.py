"""D-layer deeper-level item-head evidence (Rising Sea §12.8 incident, 2026-09-24).

Root cause: for Vakil-style books the sections print at depth 2 (`12.8 Title`)
while every numbered item prints at depth 3 (`12.8.3. Theorem. —`). The generic
d_item_re only captures 2-component numbers, and the range-continuation guard
skips `12.8` inside `12.8.3` (mid-number). So a section only got labeled-item
evidence from a lucky mixed-case prose cross-reference; §12.8 (items all
Theorem/Fact-headed, no such reference) vanished from the D-layer truth and
passed the gate silently — the whole section went missing from the contract.

Fix under test (section_continuity._build_deeper_item_re + per-line branch):
a LINE-ANCHORED exactly-(depth+1)-component number followed (within 30 chars)
by a label keyword contributes its section prefix to raw_labeled_item.
Negatives kept intact: mid-prose `in Theorem 12.6.4`, longer numbers
`12.6.4.1`, 2-component Casella items `8.38. Let X1 ...`.

Runs under stdlib unittest:
  python verify/tests/test_d_deeper_item_evidence.py
"""
import os
import sys
import json
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

from verify_config import BookConfig, GroupConfig, SCOPE_CHAPTER, ORDINAL_THREE_LEVEL
from section_continuity import check_d_layer, _build_deeper_item_re, _split_num


def _vakil_cfg():
    # Rising Sea: uncat type-8 items (C.S.N), sections C.S → depth [1, 2]
    return BookConfig(
        ordinal=[GroupConfig(type=ORDINAL_THREE_LEVEL, scope=SCOPE_CHAPTER)],
        section_types=[1, 2],
    )


def _run(md_content, blocks):
    tmp = tempfile.mkdtemp(prefix="d_deeper_")
    md = os.path.join(tmp, "ch.md")
    with open(md, "w", encoding="utf-8") as f:
        f.write(md_content)
    ext = os.path.join(tmp, "_extract")
    os.makedirs(ext)
    data = {"text": [{"text": b,
                      "poly": [0, 200, 100, 200, 100, 210, 0, 210]}
                     for b in blocks]}
    with open(os.path.join(ext, "page_001.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)
    return check_d_layer(12, 1, 1, md, ext, cfg=_vakil_cfg())


class TestDeeperItemRegex(unittest.TestCase):
    def test_exact_three_components_only(self):
        rx = _build_deeper_item_re(3)
        m = rx.match("12.8.3. Theorem. — If X is")
        self.assertIsNotNone(m)
        self.assertEqual(_split_num(m.group(1)), [12, 8, 3])
        self.assertIsNone(rx.match("12.8.3.4 Definition"))   # longer number
        self.assertIsNone(rx.match("12.8. Let X"))            # 2-component item
        self.assertIsNone(rx.match("see 12.8.3 above"))       # not line-anchored
        self.assertIsNone(rx.match("8.38-8.42 Theorem"))      # range mid-piece


class TestMissingSectionRecovered(unittest.TestCase):
    def test_theorem_headed_section_flagged_missing(self):
        md = "# Ch\n\n## §12.7 X\n\n## §12.9 Y\n"
        blocks = [
            "12.7 + Valuative criteria for separatedness and properness\n"
            "12.7.1. Theorem (Valuative criterion for separatedness, DVR).",
            "12.8 + More sophisticated facts about regular local rings",
            "12.8.3. Theorem. — If X is a finite type scheme over a field",
            "12.9 + Filtered rings and modules, and the Artin-Rees Lemma\n"
            "12.9.2. Proposition.",
        ]
        out = _run(md, blocks)
        self.assertEqual(out["levels"][2]["continuity"], ["8"])
        self.assertEqual(out["continuity_sections"], ["8"])


class TestNoFalsePositives(unittest.TestCase):
    def test_prose_reference_and_range_do_not_create_sections(self):
        # All sections already written; only FP-shaped evidence exists for 12.5
        md = ("# Ch\n\n## §12.1 A\n\n## §12.2 B\n\n## §12.3 C\n\n"
              "## §12.4 D\n\n## §12.6 E\n")
        blocks = [
            "12.1 Section one\n12.1.1. Definition.",
            "12.2 Section two\n12.2.1. Theorem.",
            "12.3 Section three\n12.3.1. Proposition.",
            "12.4 Section four\n12.4.1. Lemma.",
            "see Theorem 12.5.6 for the argument, continued here in the",
            "(Exercises 12.5.7-12.5.9 give the details for this part ok",
            "12.6 Section six\n12.6.1. Corollary.",
        ]
        out = _run(md, blocks)
        self.assertEqual(out["levels"][2]["continuity"], [])
        self.assertEqual(out["levels"][2]["missing"], [])

    def test_two_component_item_book_unaffected(self):
        # Casella-style 2-component items must not gain L3-ish evidence
        md = "# Ch\n\n## §12.7 X\n\n## §12.8 Y\n"
        blocks = [
            "12.7 Exercises\n8.38. Let X1, ..., Xn be i.i.d. random",
            "12.8 Another\n(Exercises 8.38-8.42 are related to Theorem)",
        ]
        out = _run(md, blocks)
        self.assertEqual(out["levels"][2]["continuity"], [])
        self.assertEqual(out["levels"][2]["missing"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
