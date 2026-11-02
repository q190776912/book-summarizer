# -*- coding: utf-8 -*-
"""Regression: V-F "`>` item block -> top-level prose" separator, unit-boundary only.

Two opposite shapes, found 2026-11-02 on Fraleigh ch25 and Apostol IANT ch4:

* ``0006_section_25_2.md`` **ends** with a ``> **Example 25.1.**`` block and
  ``0007_desc_D2.md`` opens with prose.  ``_assemble``'s type state machine only
  inserts ``---`` for ``desc`` when ``prev == "item"``, and a contract node that
  packs "section heading + example" into one ``section`` unit leaves ``prev ==
  "heading"`` — so the separator the I-layer *requires* never appears in the
  splice.  Resetting the delivery from units deleted the ``---`` the delivery
  legitimately had, and the whole-book verify then reported ``F:2``.
* Apostol IANT ch4 CN has the same missing line **inside one unit**, where the
  unit gate deliberately exempts it (the translation mirrors the printed source
  structure).  Fixing that from the assembler would fabricate a ``---`` the EN
  side does not have — the exact two-version structural fork the 2026-09-27/29
  root fixes exist to prevent.

So the assembler inserts only at **unit boundaries** (``owners`` differ).  These
tests pin the boundary insert, the intra-unit hands-off, and the requirement that
the shared detector and the documented judge never diverge.

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_merge_prose_separator_boundary.py
"""
import importlib.util
import io
import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
sys_path_root = _ROOT
import sys
sys.path.insert(0, sys_path_root)
import lib.boot as _boot
_boot.setup()

spec = importlib.util.spec_from_file_location(
    "merge_units_prose_sep",
    os.path.join(_ROOT, "flows/write-source/script/merge_units.py"))
mu = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mu)

from verify.script.struct_labels import (
    find_prose_separator_gaps, insert_prose_separators)

_fv_spec = importlib.util.spec_from_file_location(
    "format_verify_prose_sep",
    os.path.join(_ROOT, "verify/format_verify/script/format_verify.py"))
fv = importlib.util.module_from_spec(_fv_spec)
_fv_spec.loader.exec_module(fv)

BLOCK = ["> **Example 25.1.** Invert the matrix below.",
         "> Reduce it to row-echelon form first."]
PROSE = "Hence $x=1$ and the map is bijective."


def _fence_count(lines):
    return sum(1 for ln in lines if re.match(r'^---+\s*$', ln))


def _owned_lines(lines, owners):
    """the unit bytes only — separators/blank rows inserted by the assembler are not."""
    return [ln for (ln, own) in zip(lines, owners) if own is not None]


class DetectorMatchesJudge(unittest.TestCase):
    """The splice-side detector and the documented judge must be one walk.

    A divergence here is the "merge fixed it but verify still says missing" bug,
    so every shape below is checked twice: by ``find_prose_separator_gaps`` and
    by ``check_i_prose_separator`` reading the same bytes off disk.
    """

    SHAPES = {
        "gap": BLOCK + ["", PROSE],
        "gap no blank": BLOCK + [PROSE],
        "separator present": BLOCK + ["", "---", "", PROSE],
        "empty quote tail then prose": BLOCK + ["> ", "", PROSE],
        "followed by heading": BLOCK + ["", "## Next section"],
        "followed by top-level label": BLOCK + ["", "**Definition 25.2.** A group."],
        "followed by display math": BLOCK + ["", "$$x^2 + y^2 = z^2$$"],
        "followed by another block": BLOCK + ["", "> **Example 25.2.** Another one.",
                                              "> Body line."],
        "half-wrapped block": ["> **Example 25.3.** Only the head, no body.", PROSE],
        "block at eof": BLOCK,
    }

    # The detector reports ``(block-head, exclusive-block-end, prose)`` indices; the
    # judge prints the block's **last quoted line** and the prose line as 1-based
    # numbers, so the pair to compare is ``(end, prose + 1)``.
    _MSG = re.compile(r'^  x L(\d+): missing `---` between the .*?'
                      r'\(ends L(\d+)\) and the descriptive prose at L(\d+)', re.S)

    def _judge_sites(self, lines):
        """judge verdicts as 1-based ``(last quoted line, prose line)``."""
        tmp = tempfile.mkdtemp()
        try:
            path = os.path.join(tmp, "a.md")
            with io.open(path, "w", encoding="utf-8", newline="") as f:
                f.write(u"\n".join(lines) + u"\n")
            out = []
            for msg in fv.check_i_prose_separator(path):
                m = self._MSG.match(msg)
                self.assertTrue(m, msg)                     # a message we cannot locate
                self.assertEqual(m.group(1), m.group(2), msg)
                out.append((int(m.group(2)), int(m.group(3))))
            return out
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_same_sites_on_every_shape(self):
        for name, lines in self.SHAPES.items():
            gaps = [(j, k + 1) for (_head, j, k) in find_prose_separator_gaps(lines)]
            self.assertEqual(gaps, self._judge_sites(lines), name)

    def test_the_gap_shapes_are_the_ones_flagged(self):
        flagged = sorted(n for n, l in self.SHAPES.items() if find_prose_separator_gaps(l))
        self.assertEqual(flagged, ["empty quote tail then prose", "gap", "gap no blank"])


class BoundaryOnlyInsertion(unittest.TestCase):
    def setUp(self):
        self.lines = (["# Chapter 25: Introduction"] + BLOCK + ["", PROSE, ""])
        self.owners = ([None] + ["0006_section_25_2.md"] * len(BLOCK)
                       + [None, "0007_desc_D2.md", None])

    def test_cross_unit_gap_gets_the_separator(self):
        new_lines, new_owners = insert_prose_separators(self.lines, self.owners)
        self.assertEqual(len(new_lines), len(new_owners))
        prose = new_lines.index(PROSE)
        self.assertEqual(new_lines[prose - 1], "")
        self.assertEqual(new_lines[prose - 2], "---")
        self.assertIsNone(new_owners[prose - 2])            # not attributed to a unit
        self.assertEqual(_owned_lines(new_lines, new_owners),
                          _owned_lines(self.lines, self.owners))

    def test_intra_unit_gap_is_left_to_the_unit_gate(self):
        """🔴 the Apostol ch4 shape: block and prose are the *same* unit's bytes."""
        owners = ["0006_section_25_2.md"] * len(self.lines)
        self.assertEqual(insert_prose_separators(self.lines, owners),
                          (self.lines, owners))

    def test_no_separator_is_ever_duplicated(self):
        lines = ["# Chapter 25: Introduction"] + BLOCK + ["", "---", "", PROSE, ""]
        owners = ([None] + ["a.md"] * len(BLOCK) + [None, None, None, "b.md", None])
        self.assertEqual(_fence_count(lines),
                          _fence_count(insert_prose_separators(lines, owners)[0]))

    def test_non_prose_followups_are_not_touched(self):
        for tail in (["", "## Next section"], ["", "**Definition 25.2.** A group."]):
            lines = BLOCK + tail
            owners = ["a.md"] * len(BLOCK) + [None] * len(tail)
            self.assertEqual(insert_prose_separators(lines, owners)[0], lines)


class AssemblerBoundaryCase(unittest.TestCase):
    """``_assemble`` on the Fraleigh ch25 tree must emit the separator it used to drop."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.ext = os.path.join(self.tmp, "_extract")
        self.udir = os.path.join(self.ext, "book_structure", "units", "ch25")
        os.makedirs(self.udir)
        self.md = "Chapter25_Encryption.md"

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _unit(self, name, marker_type, key, body):
        with io.open(os.path.join(self.udir, name), "w",
                     encoding="utf-8", newline="") as f:
            f.write(u"<!-- book-summarizer DONE unit: id=%s type=%s key=%s name=%s -->\n"
                    u"%s\n" % (name[:4], marker_type, key, key, u"\n".join(body)))
        return name

    def _manifest(self, entries):
        with io.open(os.path.join(self.udir, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump({"language": "en", "final_md": self.md,
                       "units": [{"id": "000%d" % (i + 1), "file": n, "type": t,
                                  "key": k, "hash": "0" * 40}
                                 for (i, (n, t, k)) in enumerate(entries)]}, f,
                      ensure_ascii=False)

    def _assemble(self):
        return mu._assemble(self.ext, "25", "units", clean_cjk=None, require_gate=False)

    def _next_content(self, lines, start):
        nxt = start
        while nxt < len(lines) and lines[nxt].strip() == "":
            nxt += 1
        return nxt

    def _assert_separator(self, lines, owners):
        tail = self._next_content(lines, lines.index(BLOCK[-1]) + 1)
        self.assertIn("0007_desc_D2.md", owners, lines)     # prose really is its own unit
        self.assertEqual(lines[tail], "---", lines)
        self.assertIsNone(owners[tail])
        prose = self._next_content(lines, tail + 1)
        self.assertEqual(lines[prose], PROSE, lines)
        self.assertEqual(owners[prose], "0007_desc_D2.md", lines)

    def test_split_units_get_the_separator(self):
        self._manifest([
            (self._unit("0001_chapter_25.md", "chapter", "25",
                        ["# Chapter 25: Introduction"]), "chapter", "25"),
            (self._unit("0006_section_25_2.md", "section", "25.2",
                        ["## 25.2 Inverting a matrix", ""] + BLOCK), "section", "25.2"),
            (self._unit("0007_desc_D2.md", "desc", "D2", [PROSE]), "desc", "D2"),
        ])
        lines, owners = self._assemble()
        self._assert_separator(lines, owners)

    def test_packed_single_unit_is_not_rewritten(self):
        """Same bytes inside one unit ⇒ the assembler stays out (unit gate's call)."""
        self._manifest([
            (self._unit("0001_chapter_25.md", "chapter", "25",
                        ["# Chapter 25: Introduction"]), "chapter", "25"),
            (self._unit("0006_section_25_2.md", "section", "25.2",
                        ["## 25.2 Inverting a matrix", ""] + BLOCK + ["", PROSE]),
             "section", "25.2"),
        ])
        lines, owners = self._assemble()
        nxt = self._next_content(lines, lines.index(BLOCK[-1]) + 1)
        self.assertEqual(lines[nxt], PROSE, lines)
        self.assertEqual(owners[nxt], "0006_section_25_2.md", lines)

    def test_owners_stay_line_aligned(self):
        self._manifest([
            (self._unit("0001_chapter_25.md", "chapter", "25",
                        ["# Chapter 25: Introduction"]), "chapter", "25"),
            (self._unit("0006_section_25_2.md", "section", "25.2",
                        ["## 25.2 Inverting a matrix", ""] + BLOCK), "section", "25.2"),
            (self._unit("0007_desc_D2.md", "desc", "D2", [PROSE]), "desc", "D2"),
        ])
        lines, owners = self._assemble()
        self.assertEqual(len(lines), len(owners))
        # every content line still names the unit it came from
        for ln in BLOCK + [PROSE]:
            self.assertIn(ln, lines)
            self.assertNotEqual(owners[lines.index(ln)], None, ln)


if __name__ == "__main__":
    unittest.main(verbosity=2)
