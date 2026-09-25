# -*- coding: utf-8 -*-
"""Regression: books with no `formula` config must not harvest prose brackets as
formula numbers (Rosen 8e 16 chapters, 2026-09-25).

`formula_cfg` returns ``ncomp=None`` for a book that declares no numbering, and
``formula_num_core(None)`` is the unbounded fallback — so any text block that is
*exactly* a bracketed number got consumed as a tag anchor and **left the prose
flow**, while the phantom ``tag`` became gate truth that forces writers to
invent ``\\tag{…}``.  Real false positives on this book: bit strings ``(01)`` /
``(11)``, a coordinate ``(2, 0)`` (``_FORMULA_SEP`` allows comma), decimals
``(0.1)`` / ``(0.025)`` / ``(0.99999)``, table row numbers ``(7)`` / ``(10)``.

Fix under test: :func:`lib.numbering.formula_tag_shape_ok` applied at harvest
time only when ``ncomp is None`` — rejected candidates stay in the prose stream.
Genuine shapes (``8.11a``, ``2-17``, Vakil's zero-segmented ``1.5.0.1``) and
configured books (``ncomp=1`` single-level, ``letter=True`` ``(A.3)``) unchanged.

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_unconfigured_tag_shape.py
"""
import os
import sys
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

from attach_content import _attach_formula_tags              # noqa: E402
from lib.numbering import formula_tag_shape_ok               # noqa: E402


def _text(raw, y=100.0, x=900.0, h=12.0):
    """右缘独立编号块：x 落在公式行最右侧，与公式同一 y 带。"""
    return {"kind": "text", "text": raw, "y": y, "bottom": y + h,
            "x": x, "x1": x + 30.0}


def _formula(y=100.0, h=14.0):
    return {"kind": "formula", "formula": r"a = b", "display": True,
            "y": y, "bottom": y + h, "x": 60.0, "x1": 960.0}


def _run(blocks, **kw):
    out = _attach_formula_tags(blocks, **kw)
    tags = [str(b["tag"]) for b in out if b["kind"] == "formula" and "tag" in b]
    prose = [b["text"] for b in out if b["kind"] == "text"]
    return tags, prose


class TestUnconfiguredTagShape(unittest.TestCase):
    """``ncomp is None``（书未配置 `formula`）。"""

    UNCONFIGURED = dict(ncomp=None, bare=False)

    def test_bracketed_prose_never_becomes_a_tag(self):
        for raw in ["(01)", "(11)", "(2, 0)", "(0.1)", "(0.025)", "(0.99999)",
                    "(7)", "(10)", "(121)", "(0j)"]:
            tags, prose = _run([_text(raw), _formula()], **self.UNCONFIGURED)
            self.assertEqual(tags, [], "%s 被收成公式编号" % raw)
            self.assertIn(raw, prose, "%s 离开了正文流（内容丢失）" % raw)

    def test_genuine_multi_segment_numbers_still_attach(self):
        for raw, want in [("(8.11a)", "8.11a"), ("(2-17)", "2-17"),
                          ("(3.35)", "3.35"), ("(1.5.0.1)", "1.5.0.1")]:
            tags, prose = _run([_text(raw), _formula()], **self.UNCONFIGURED)
            self.assertEqual(tags, [want], "%s 应挂为编号" % raw)
            self.assertEqual(prose, [], "%s 应离开正文（纯版面锚点）" % raw)

    def test_configured_single_level_book_unchanged(self):
        # ncomp=1（Kreyszig / 数理逻辑导引等节内重置单级号）：`(7)` 是真编号
        tags, _ = _run([_text("(7)"), _formula()], ncomp=1, bare=False)
        self.assertEqual(tags, ["7"])

    def test_letter_chapter_position_unchanged(self):
        # Lee 附录 (A.3)：letter 路径不适用形态闸
        tags, _ = _run([_text("(A.3)"), _formula()],
                       ncomp=2, letter=True, bare=False)
        self.assertEqual(tags, ["A.3"])


class TestShapePredicate(unittest.TestCase):
    def test_rejects(self):
        for t in ["0", "01", "7", "10", "121", "2,0", "0.1", "0.025",
                  "0.99999", "0j", "9x", "1234.5", "", None]:
            self.assertFalse(formula_tag_shape_ok(t), "%s 不该可信" % t)

    def test_accepts(self):
        for t in ["3.35", "2-17", "8.11a", "1.5.0.1", "13.1.0.1", "1.0.2",
                  "10.9", "99-100"]:
            self.assertTrue(formula_tag_shape_ok(t), "%s 应可信" % t)


if __name__ == "__main__":
    unittest.main(verbosity=2)
