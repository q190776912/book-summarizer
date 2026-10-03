"""§(HUM) / Ross contract branches must close themselves.

`verify/script/structure_io.read_structure_items` grew its emit inside the
"first digit run" branch (bare dash three-level keys + the `定理 A` letter
branch), but the two branches that never compute a digit run —
``if '§' in raw`` (Humphreys-style `Theorem §4.1`) and the Ross letter-slot
branch (``Example 2a``) — kept only setting ``_canon`` and then fell through to
``if '-' in num_raw:``:

  * first item of the chapter is such a key -> UnboundLocalError, the whole
    chapter's contract read dies (measured: Robinson《Introduction to Lie
    Algebras…》 ch1-7, `Proposition §2.2` as the first item);
  * an earlier item happened to bind `num_raw` -> the stale digit run decides
    the key, so the contract truth set silently carries **another node's**
    number (worse: no crash, just wrong B-layer items).

Both branches now append their own item and `continue`.  The tests pin the
crash-free ordering (leading §/Ross item) AND the stale-binding ordering
(a § item right after a digit item must keep its own label-only key).
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

from data.book_structure.book_structure import (BookStructure, StructureNode,  # noqa: E402
                                                ROOT_KEY, ROOT_TYPE)
from verify.script.structure_io import read_structure_items  # noqa: E402


def _n(key, ntype, page=10):
    return StructureNode(key=key, type=ntype, name=key, page_start=page, page_end=page)


def _save(nodes):
    ch = StructureNode(key="1", type="chapter", name="Chapter 1",
                       page_start=1, page_end=99, sub_sec=nodes)
    bs = BookStructure(root=StructureNode(
        key=ROOT_KEY, type=ROOT_TYPE, name="Test Book", page_start=0, page_end=0,
        sub_sec=[ch]), book_dir=None)
    d = tempfile.mkdtemp(prefix="secross_")
    bs.save(d)
    return d


def _keys(nodes, **kw):
    d = _save(nodes)
    try:
        return [it["key"] for it in read_structure_items(d, "1", **kw)]
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


def test_leading_section_key_does_not_crash():
    keys = _keys([_n("Proposition §2.2", "proposition"),
                  _n("Theorem §3.2", "theorem"),
                  _n("Lemma §10.2B", "lemma"),
                  _n("Corollary §10.2-2", "corollary"),
                  _n("Example §22.4-1", "example"),
                  _n("Lemma §23.App", "lemma")])
    # 后缀优先级（`_letter` > `_exnum` > `_app` > `_slotsuffix`）按分支既有规则：
    # `Corollary §10.2-2` 的 `-2` 命中 `_exnum` → `推论2`（不是 `推论-2`）。
    assert keys == ["命题", "定理", "引理 B", "推论2", "例1", "引理 App"]


def test_section_key_after_digit_item_does_not_steal_stale_number():
    """§ 节点排在一个数字条目之后：旧实现会拿**上一条**的 num_raw 造键。"""
    keys = _keys([_n("1.4", "theorem"),
                  _n("Proposition §2.2", "proposition"),
                  _n("Example 2a", "example"),
                  _n("2.7-3", "definition")])
    assert keys == ["定理1.4", "命题", "例2a", "2.7-3"]


def test_leading_ross_key_does_not_crash():
    assert _keys([_n("Example 2a", "example"),
                  _n("Proposition 4.1", "proposition")]) == ["例2a", "命题4.1"]
