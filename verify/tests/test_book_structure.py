"""Regression tests for the single-file book_structure.json refactor (2026-08-12).

Covers the typed model (data.book_structure.book_structure: BookStructure /
StructureNode) and its three structural consumers:
  - verify.common.structure_io.read_structure_items   (data_provider source)
  - verify.verbose_gates._load_contract         (P-LAYER contract)
  - verify.script.check_structure_completeness backfill path (save round-trip)

This replaces the old per-chapter structure-file design; every reader
now loads the single <extract_dir>/book_structure.json book object.
"""
import os
import sys
import tempfile
import json
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

from data.book_structure.book_structure import BookStructure, StructureNode, ROOT_KEY, ROOT_TYPE
from verify.common.structure_io import read_structure_items
from verify.verbose_gates.script.verbose_gates import _load_contract


def _make_book():
    """Build a synthetic 1-chapter book object (single-file design)."""
    ch1 = StructureNode(
        key="1", type="chapter", name="Chapter 1", page_start=1, page_end=10,
        sub_sec=[
            StructureNode(key="1.1", type="section", name="§1.1 Intro", page_start=1, page_end=3,
                          sub_sec=[
                              StructureNode(key="1.1-1", type="definition",
                                            name="1.1-1 Definition (Metric).", page_start=1, page_end=1),
                              StructureNode(key="1.1.A", type="exercise",
                                            name="1.1.A Exercise.", page_start=2, page_end=2),
                          ]),
            StructureNode(key="1.2", type="section", name="§1.2 More", page_start=4, page_end=10,
                          sub_sec=[
                              StructureNode(key="1.2.3", type="theorem",
                                            name="1.2.3 Theorem.", page_start=5, page_end=5),
                          ]),
        ])
    root = StructureNode(key=ROOT_KEY, type=ROOT_TYPE, name="Test Book",
                         page_start=0, page_end=0, sub_sec=[ch1])
    return BookStructure(root=root, book_dir=None)


def test_node_roundtrip():
    n = StructureNode(key="1.1-1", type="definition", name="x", page_start=2, page_end=3,
                      sub_sec=[StructureNode(key="1.1-2", type="example", name="y", page_start=2, page_end=2)])
    d = n.to_dict()
    n2 = StructureNode.from_dict(d)
    assert n2.key == "1.1-1" and n2.type == "definition"
    assert n2.name == "x" and n2.page_start == 2 and n2.page_end == 3
    assert len(n2.sub_sec) == 1 and n2.sub_sec[0].key == "1.1-2"
    # equality via dict
    assert n2.to_dict() == d


def test_book_save_load_roundtrip():
    bs = _make_book()
    d = tempfile.mkdtemp(prefix="bstest_")
    try:
        p = bs.save(d)
        assert os.path.exists(p)
        assert os.path.basename(p) == "book_structure.json"
        bs2 = BookStructure.load(d)
        assert bs2 is not None
        assert bs2.name == "Test Book"
        assert [c.key for c in bs2.chapters] == ["1"]
        assert bs2.dump_dict() == bs.dump_dict()
    finally:
        os.unlink(p)
        os.rmdir(d)


def test_recompute_pages_recursive():
    bs = _make_book()
    # reset container pages to force recompute from leaf pages
    bs.root.page_start = 0; bs.root.page_end = 0
    for ch in bs.root.sub_sec:
        ch.page_start = 0; ch.page_end = 0
    bs.save(tempfile.mkdtemp(prefix="bstest_"))  # triggers recompute
    ch = bs.find_chapter("1")
    # leaf pages span 1..5 (def p1, exercise p2, theorem p5) -> chapter 1..5
    assert ch.page_start == 1 and ch.page_end == 5, (ch.page_start, ch.page_end)
    assert bs.root.page_start == 1 and bs.root.page_end == 5


def test_replace_chapter_upsert():
    bs = _make_book()
    # replace existing chapter 1 with a modified copy
    new_ch = StructureNode(key="1", type="chapter", name="Chapter 1 (edited)",
                           page_start=1, page_end=10, sub_sec=[])
    replaced = bs.root.replace_chapter(new_ch)
    assert replaced is True
    assert bs.find_chapter("1").name == "Chapter 1 (edited)"
    # append a brand-new chapter 2
    ch2 = StructureNode(key="2", type="chapter", name="Chapter 2", page_start=11, page_end=20, sub_sec=[])
    appended = bs.root.replace_chapter(ch2)
    assert appended is False
    assert [c.key for c in bs.chapters] == ["1", "2"]


def test_chapter_items_excludes_exercise():
    bs = _make_book()
    items = bs.chapter_items("1")
    keys = [i.key for i in items]
    assert "1.1-1" in keys and "1.2.3" in keys
    assert "1.1.A" not in keys  # exercise excluded by default
    # exercise included when requested
    items_all = bs.chapter_items("1", include_exercise=True)
    assert "1.1.A" in [i.key for i in items_all]


def test_structure_io_read_from_single_file():
    bs = _make_book()
    d = tempfile.mkdtemp(prefix="bstest_")
    try:
        bs.save(d)
        items = read_structure_items(d, "1")
        assert items is not None
        keys = [it["key"] for it in items]
        assert "1.1-1" in keys and "1.2.3" in keys
        assert "1.1.A" not in keys
        # label mapping (Chinese labels, per structure_io.TYPE_TO_LABEL)
        by_key = {it["key"]: it["label"] for it in items}
        assert by_key["1.1-1"] == "定义"
        assert by_key["1.2.3"] == "定理"
        # missing chapter -> empty list (not None)
        assert read_structure_items(d, "99") == []
    finally:
        os.unlink(os.path.join(d, "book_structure.json"))
        os.rmdir(d)


def test_structure_io_missing_file_returns_none():
    d = tempfile.mkdtemp(prefix="bstest_")
    try:
        assert read_structure_items(d, "1") is None
    finally:
        os.rmdir(d)


def test_verbose_gates_contract_load():
    bs = _make_book()
    d = tempfile.mkdtemp(prefix="bstest_")
    try:
        bs.save(d)
        sections, item_keys = _load_contract(d, "1")
        sec_keys = [k for k, _ in sections]
        assert "1.1" in sec_keys and "1.2" in sec_keys
        # three-level dotted key is accepted as an item key; dashed is not
        assert "1.2.3" in item_keys
        assert "1.1-1" not in item_keys
        # missing chapter -> empty
        s2, k2 = _load_contract(d, "99")
        assert s2 == [] and k2 == set()
    finally:
        os.unlink(os.path.join(d, "book_structure.json"))
        os.rmdir(d)


def test_check_structure_backfill_roundtrip():
    """Simulate check_structure_completeness: load -> find chapter -> insert item
    -> replace_chapter -> save -> reload -> item present."""
    bs = _make_book()
    d = tempfile.mkdtemp(prefix="bstest_")
    try:
        bs.save(d)
        bs2 = BookStructure.load(d)
        ch = bs2.find_chapter("1")
        # insert a readable backfilled definition into section 1.1
        sec11 = None
        for s in ch.sub_sec:
            if s.key == "1.1":
                sec11 = s
        assert sec11 is not None
        sec11.sub_sec.append(StructureNode(
            key="1.1-9", type="definition", name="1.1-9 Definition (Backfilled).",
            page_start=3, page_end=3))
        bs2.root.replace_chapter(ch)
        bs2.save(d)
        # reload and confirm the backfilled node persists
        bs3 = BookStructure.load(d)
        items = bs3.chapter_items("1", include_exercise=True)
        keys = [i.key for i in items]
        assert "1.1-9" in keys
    finally:
        os.unlink(os.path.join(d, "book_structure.json"))
        os.rmdir(d)


def _main():
    funcs = [
        test_node_roundtrip,
        test_book_save_load_roundtrip,
        test_recompute_pages_recursive,
        test_replace_chapter_upsert,
        test_chapter_items_excludes_exercise,
        test_structure_io_read_from_single_file,
        test_structure_io_missing_file_returns_none,
        test_verbose_gates_contract_load,
        test_check_structure_backfill_roundtrip,
    ]
    failed = []
    for f in funcs:
        try:
            f()
            print("PASS", f.__name__)
        except Exception as e:
            failed.append(f.__name__)
            print("FAIL", f.__name__, "->", repr(e))
    if failed:
        print("\n%d/%d checks FAILED: %s" % (len(failed), len(funcs), ", ".join(failed)))
        sys.exit(1)
    print("\nALL %d checks passed" % len(funcs))


if __name__ == "__main__":
    _main()
