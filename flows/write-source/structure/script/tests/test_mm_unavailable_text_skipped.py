# -*- coding: utf-8 -*-
"""Regression: text blocks marked `mm_unavailable` by MM Repair must not enter the
content stream (Lehmann, Elements of Large-Sample Theory, 2026-10-15).

MM Repair's `unavailable` verdict means "visually confirmed: this is the garbled
re-read of a display-formula region (or unreadable)".  `mm_repair_apply.py` only
*marks* such entries (`mm_unavailable: true`) — it never deletes them — and the
documented contract (flows/extract/mm_repair/mm_repair.md, Step 5 / 出口) promises
that downstream write-source skips them so the book is not polluted.  Only
tools/dump_chapter_ocr.py honoured that; `_collect_blocks` — the path that actually
feeds the chapter contract — ignored the flag, so ~650 garbage bands per book leaked
into units next to the very formula they duplicate (the geometry dedup in the same
function only catches mutually coincident boxes, `inter/max(ta,fa) > 0.5`, and a
full-width band inside a tall display scores far below that).

Fix under test: `_collect_blocks` skips text blocks carrying `mm_unavailable`, while
untouched blocks and formula blocks keep flowing.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_mm_unavailable_text_skipped.py
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

from attach_content import _collect_blocks   # noqa: E402


def _band(y, text, **extra):
    d = {"poly": [100, y, 400, y, 400, y + 20, 100, y + 20], "text": text,
         "score": 0.6}
    d.update(extra)
    return d


def _write_page(tmp, page, texts, formulas):
    with open(os.path.join(tmp, "page_%03d.json" % page), "w", encoding="utf-8") as f:
        json.dump({"page": page, "text": texts, "formulas": formulas}, f,
                  ensure_ascii=False)


class TestMMUnavailableTextSkipped(unittest.TestCase):
    def _kinds(self, tmp):
        blocks, _h = _collect_blocks(tmp, 18, 18)
        return [b.get("text") or b.get("latex") for b in blocks]

    def test_unavailable_band_dropped_others_kept(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_page(tmp, 18, [
                _band(100, "Proper prose line that must survive."),
                _band(200, "n -> 0 0:>=", mm_unavailable=True),
            ], [
                {"bbox": [90, 190, 420, 400], "cls": 1, "conf": 0.94,
                 "latex": "X_n \\to 0"},
            ])
            got = self._kinds(tmp)
            self.assertTrue(any("Proper prose" in (g or "") for g in got), got)
            self.assertTrue(any("X_n" in (g or "") for g in got), got)
            self.assertFalse(any("0:>" in (g or "") for g in got), got)

    def test_flag_absent_means_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_page(tmp, 18, [_band(100, "no marker at all here")], [])
            self.assertTrue(any("no marker" in (g or "") for g in self._kinds(tmp)))

    def test_empty_marker_false_is_not_a_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            _write_page(tmp, 18, [_band(100, "reviewed and confirmed ok",
                                        mm_reviewed=True, mm_unavailable=False)], [])
            self.assertTrue(any("reviewed" in (g or "") for g in self._kinds(tmp)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
