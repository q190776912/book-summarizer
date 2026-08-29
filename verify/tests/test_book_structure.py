"""Regression tests for the per-chapter contract format (2026-08-29).

Covers the typed model (data.book_structure.book_structure: BookStructure /
StructureNode) over the SPLIT per-chapter files
(`<extract_dir>/book_structure/ch{N}.json`, appendix `appendix{X}.json`) and its
structural consumers:
  - verify.script.structure_io.read_structure_items   (data_provider source)
  - verify.verbose_gates._load_contract         (P-LAYER contract)
  - verify.script.check_structure_completeness backfill path (save round-trip)

The old single-file `book_structure.json` is DEPRECATED (2026-08-29):
`BookStructure.load` reads ONLY the split per-chapter files (no fallback).
"""
import os
import sys
import shutil
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
from verify.script.structure_io import read_structure_items
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
        written = bs.save(d)
        # 拆分写回：数字章 ch1.json（附录为 appendix{X}.json）
        assert len(written) == 1 and os.path.basename(written[0]) == "ch1.json"
        assert os.path.exists(written[0])
        bs2 = BookStructure.load(d)
        assert bs2 is not None
        # 聚合书根 name 取自书目录名（分章文件不存书名；装饰性字段）
        assert isinstance(bs2.name, str) and bs2.name
        assert [c.key for c in bs2.chapters] == ["1"]
        # 书根 name/页码为派生值（目录名 / 章区间聚合），比较章节内容
        assert [c.to_dict() for c in bs2.chapters] == [c.to_dict() for c in bs.chapters]
    finally:
        import shutil
        shutil.rmtree(d)


def test_recompute_pages_recursive():
    bs = _make_book()
    # 章级区间视为 chapter_map 权威值：recompute_pages 对 chapter 节点跳过重算，
    # 不再从子节点派生（修复无编号条目 / 空 section 的章 page_end 塌缩回 page_start）。
    # 这里章节点自带权威区间 (1,10)，故意比子节点派生值 (1,5) 更宽。
    bs.root.page_start = 0; bs.root.page_end = 0
    for ch in bs.root.sub_sec:
        ch.page_start, ch.page_end = 1, 10  # 模拟 build_chapter 回填 chapter_map 权威值
    bs.save(tempfile.mkdtemp(prefix="bstest_"))  # triggers recompute
    ch = bs.find_chapter("1")
    # 章级保留权威区间 (1,10)，不被子节点重算覆盖（关键：≠ 子节点派生的 1..5）
    assert ch.page_start == 1 and ch.page_end == 10, (ch.page_start, ch.page_end)
    # section/item 子节点仍按末代子孙页递归重算，且容器自身页参与 min
    # （2026-08 修复：谷超豪 ch2 §1 节头页不被子项推迟）：§1.2 节头 p4、定理 p5
    # -> (4,5)
    sec12 = next(s for s in ch.sub_sec if s.key == "1.2")
    assert sec12.page_start == 4 and sec12.page_end == 5, (sec12.page_start, sec12.page_end)
    # 书根聚合章区间
    assert bs.root.page_start == 1 and bs.root.page_end == 10


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


def test_structure_io_read_from_split_files():
    bs = _make_book()
    d = tempfile.mkdtemp(prefix="bstest_")
    try:
        bs.save(d)
        items = read_structure_items(d, "1")
        assert items is not None
        keys = [it["key"] for it in items]
        # Key canonicalisation (2026-08-24): keys are emitted in the SAME key
        # space `keys_in_md` produces, so the A-layer intersects 1:1.
        #  * dashed three-level keys stay BARE ('1.1-1');
        #  * dotted keys keep the legacy LABEL-PREFIXED form ('定理1.2.3'),
        #    with the label also exposed separately via it["label"].
        assert "1.1-1" in keys and "定理1.2.3" in keys
        assert "1.1.A" not in keys
        by_key = {it["key"]: it for it in items}
        assert by_key["1.1-1"]["label"] == "定义"
        assert by_key["定理1.2.3"]["label"] == "定理"
        # missing chapter -> empty list (not None)
        assert read_structure_items(d, "99") == []
    finally:
        import shutil
        shutil.rmtree(d)


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
        sections, item_keys, letter_sub_pairs = _load_contract(d, "1")
        sec_keys = [k for k, _ in sections]
        assert "1.1" in sec_keys and "1.2" in sec_keys
        # three-level dotted key is accepted as an item key; dashed is not
        assert "1.2.3" in item_keys
        assert "1.1-1" not in item_keys
        # 无 letter_subs 元数据 → 字母子节闸不启用
        assert letter_sub_pairs == []
        # missing chapter -> empty
        s2, k2, ls2 = _load_contract(d, "99")
        assert s2 == [] and k2 == set() and ls2 == []
    finally:
        import shutil
        shutil.rmtree(d)


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
        import shutil
        shutil.rmtree(d)


def _main():
    funcs = [
        test_node_roundtrip,
        test_book_save_load_roundtrip,
        test_recompute_pages_recursive,
        test_replace_chapter_upsert,
        test_chapter_items_excludes_exercise,
        test_structure_io_read_from_split_files,
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
