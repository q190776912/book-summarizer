"""Letter-enumerated items in TWO-LEVEL books (Shafarevich《Basic Algebraic
Geometry 1》I, ch3 §3.4 Chevalley's Theorems A–D, measured 2026-09-28).

Such a book is numbered `N.S` two-level (type 2) for every ordinary item, but a
handful of headline theorems carry a LETTER ordinal only
(`**Theorem A (Chevalley's theorem)**`).  Before this fix:

  * `lib/key_parse.keys_in_md` (ORDINAL_TWO_LEVEL branch) required a digit after
    the label, so the four items produced NO md key -> the A layer reported the
    contract items as TRULY MISSING (blocking);
  * `verify/script/structure_io.read_structure_items` fell through to its
    "first digit run" branch with an empty digit string, so all four contract
    items collapsed into the bare label `定理`.

Both sides now emit the same canonical key (`定理 A` = canonical Chinese label +
ONE space + uppercase letter), which is byte-identical to the ORDINAL_HUM form.

Negative guards matter as much as the positive: prose that merely opens with an
article (`**Theorem An affine variety …**`), a bare label head (`**Theorem**`)
and lowercase-letter tails (`**Remark a posteriori …**`) must NOT mint keys.
"""
import os
import sys
import tempfile
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
from key_parse import keys_in_md, ENTRY_RE_TWO_LETTER_C
from verify_config import GroupConfig, ORDINAL_TWO_LEVEL
from verify.script.structure_io import read_structure_items


def _md_keys(text, chapter=None):
    fd, path = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return keys_in_md(path, groups=[GroupConfig(type=ORDINAL_TWO_LEVEL)],
                          chapter=chapter)
    finally:
        os.remove(path)


# --- md side ---------------------------------------------------------------

def test_letter_head_yields_contract_key():
    entries, allk = _md_keys(
        "## §3.4 Algebraic groups\n\n"
        "**Theorem A (Chevalley's theorem)**: the abstract group $G/N$ can be "
        "made into an algebraic variety.\n\n"
        "**定理 B**：an affine algebraic group is a closed subgroup of $GL_n$.\n")
    assert "定理 A" in entries and "定理 B" in entries
    assert "定理 A" in allk and "定理 B" in allk


def test_letter_head_bilingual_paren_forms():
    entries, _ = _md_keys(
        "**Theorem C (Chevalley's decomposition theorem).** Every algebraic "
        "group $G$ has a normal subgroup.\n"
        "**评注 D**：见 §3.4。\n")
    assert entries == {"定理 C", "评注 D"}


def test_prose_and_bare_heads_mint_no_keys():
    entries, allk = _md_keys(
        "**Theorem An affine variety is rational** if it is birational to $A^n$.\n"
        "**Theorem**: every nonsingular curve is projective.\n"
        "**Remark a posteriori bounds** are not entries.\n"
        "**Definition of the quotient** needs care.\n")
    assert entries == set()
    assert "定理" not in allk and "评注" not in allk and "定义" not in allk


def test_digit_heads_unaffected_by_letter_branch():
    entries, _ = _md_keys(
        "**Theorem 3.14**: something.\n**定义3.2（赋值）**：内容。\n")
    assert entries == {"定理3.14", "定义3.2"}
    assert not any(" " in k for k in entries)


def test_letter_regex_requires_uppercase_and_boundary():
    assert ENTRY_RE_TWO_LETTER_C.search("**Theorem A (Chevalley)**")
    assert ENTRY_RE_TWO_LETTER_C.search("**定理 A**")
    assert ENTRY_RE_TWO_LETTER_C.search("**Theorem A.**") is not None
    assert ENTRY_RE_TWO_LETTER_C.search("**Theorem An affine**") is None
    assert ENTRY_RE_TWO_LETTER_C.search("**Theorem a**") is None
    assert ENTRY_RE_TWO_LETTER_C.search("**Theorem 3.14**") is None
    assert ENTRY_RE_TWO_LETTER_C.search("see **Proof of Theorem A**") is None


# --- contract (source) side ------------------------------------------------

def _book_with_letter_items():
    ch1 = StructureNode(
        key="3", type="chapter", name="Chapter 3", page_start=163, page_end=248,
        sub_sec=[
            StructureNode(key="3.4", type="section", name="§3.4 Algebraic groups",
                          page_start=201, page_end=206,
                          sub_sec=[
                              StructureNode(key="定理 A", type="theorem",
                                            name="定理 A The abstract group G/N …",
                                            page_start=201, page_end=201),
                              StructureNode(key="定理 D", type="theorem",
                                            name="定理 D For X a nonsingular …",
                                            page_start=205, page_end=205),
                              StructureNode(key="3.14", type="theorem",
                                            name="Theorem 3.14.",
                                            page_start=206, page_end=206),
                          ]),
        ])
    return BookStructure(root=StructureNode(
        key=ROOT_KEY, type=ROOT_TYPE, name="Test Book", page_start=0, page_end=0,
        sub_sec=[ch1]), book_dir=None)


def test_contract_letter_key_canonizes_with_space():
    d = tempfile.mkdtemp(prefix="letterkeys_")
    try:
        _book_with_letter_items().save(d)
        items = read_structure_items(d, "3", primary_type=ORDINAL_TWO_LEVEL)
        keys = [it["key"] for it in items]
        assert "定理 A" in keys and "定理 D" in keys
        assert "定理3.14" in keys          # digit branch untouched
        assert "定理" not in keys          # the old collapse bug must not return
    finally:
        import shutil
        shutil.rmtree(d)


def test_contract_and_md_keys_intersect_1to1():
    d = tempfile.mkdtemp(prefix="letterkeys_")
    try:
        _book_with_letter_items().save(d)
        items = read_structure_items(d, "3", primary_type=ORDINAL_TWO_LEVEL)
        extracted = {it["key"] for it in items}
        entries, _allk = _md_keys(
            "**Theorem A (Chevalley's theorem)**: the group $G/N$.\n"
            "**Theorem D (Chevalley)**: for $X$ nonsingular.\n"
            "**Theorem 3.14**: something.\n", chapter=3)
        assert extracted - entries == set()
        assert entries - extracted == set()
    finally:
        import shutil
        shutil.rmtree(d)
