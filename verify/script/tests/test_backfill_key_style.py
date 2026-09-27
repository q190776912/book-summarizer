"""Regression test: --backfill 回填键式须与契约自身键式同构。

形态（Shafarevich《Basic Algebraic Geometry 1》ch3 实测，2026-09-28）：本书走
HOM 系抽取器（`extract_items_hom`），契约键是**中文标签**（`命题3.1`），而源侧
`scan_raw_items` 给出**印刷标签**（`Proposition 3.1`）。`insert_item` 直接用后者
建节点 → 契约里同时存在「命题3.12」（OCR 把 `Proposition 3.1 Ω` 的 Ω 读成 2 造出的
幽灵）与「Proposition 3.1」两个形态各异、类型相同的节点：B 层报「缺号 + 顺序错乱」
双 BLOCKING，门控 ㉓/P 层也认不出英文键。

判据不看书名：树内**同类型**条目键式多数为中文时，新键渲染为
`_canon_label(label) + 数字尾`；英文式或树内无同类条目则原样返回（零回归）。

断言：
  1. CN 式契约树 + 英文 raw 键 → 落树键为「命题3.1」；
  2. EN 式契约树 + 英文 raw 键 → 键式不变；
  3. 树内无同类型条目（首个回填）→ 键式不变；
  4. 键本身已是中文式 → 不变。
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

import check_structure_completeness as csc
from data.book_structure.book_structure import StructureNode


def _tree(item_type, existing_keys):
    """chapter -> one section holding the given item nodes."""
    kids = [StructureNode(key=k, type=item_type, name=k,
                          page_start=10, page_end=10, sub_sec=[])
            for k in existing_keys]
    sec = StructureNode(key="5.2", type="section", name="5.2 Algebraic",
                        page_start=9, page_end=12, sub_sec=kids)
    return StructureNode(key="3", type="chapter", name="ch3",
                         page_start=1, page_end=20, sub_sec=[sec])


def _inserted_keys(tree):
    sec = tree.sub_sec[0]
    return [str(n.key) for n in sec.sub_sec]


class TestBackfillKeyStyle(unittest.TestCase):
    def test_cn_contract_localizes_english_raw_key(self):
        tree = _tree('proposition', ['命题3.12', '命题3.5'])
        ok, _where = csc.insert_item(tree, 'Proposition 3.1', 'Proposition',
                                     9, (3, 1), 'Ω is generated as an A-module')
        self.assertTrue(ok)
        self.assertIn('命题3.1', _inserted_keys(tree))
        self.assertNotIn('Proposition 3.1', _inserted_keys(tree))

    def test_en_contract_keeps_printed_key(self):
        tree = _tree('proposition', ['Proposition 3.5'])
        ok, _ = csc.insert_item(tree, 'Proposition 3.1', 'Proposition', 9,
                                (3, 1), 'some statement')
        self.assertTrue(ok)
        self.assertIn('Proposition 3.1', _inserted_keys(tree))

    def test_first_item_of_type_keeps_printed_key(self):
        # no same-type sibling -> style unknown, never rewrite (zero regression)
        tree = _tree('proposition', [])
        ok, _ = csc.insert_item(tree, 'Proposition 3.1', 'Proposition', 9,
                                (3, 1), 'some statement')
        self.assertTrue(ok)
        self.assertIn('Proposition 3.1', _inserted_keys(tree))

    def test_already_localized_key_untouched(self):
        tree = _tree('proposition', ['命题3.5'])
        ok, _ = csc.insert_item(tree, '命题3.1', 'Proposition', 9, (3, 1),
                                'some statement')
        self.assertTrue(ok)
        self.assertIn('命题3.1', _inserted_keys(tree))
        self.assertEqual(len([k for k in _inserted_keys(tree) if k == '命题3.1']), 1)


if __name__ == '__main__':
    unittest.main(verbosity=2)
