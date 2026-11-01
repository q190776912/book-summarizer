# -*- coding: utf-8 -*-
"""test_cross_chapter_registered_reference.py — 点分编号书「他章契约已登记」交叉引用降级。

Background（Fraleigh《A Course in Abstract Algebra》2026-10-29 实测）
--------------------------------------------------------------------
该书条号恒为 ``标签 章.序``（``Definition 8.1`` 属 ch8）。闸门按**页区间**扫某章，
章界重叠一页 + 正文回指会把邻章真身扫进本章，11 处判成 `readable` 缺项：
  ch7  Definition 8.1(p95)   ch13 Definition 1.1(p150) / Definition 14.3(p150)
  ch14 Definition 1.1(p150)  ch17 Theorem 14.17(p170) / Example 18.3(p175)
  ch21 Theorem 13.22(p196)   ch25 Example 24.13/24.14(p222)
  ch30 Example 31.4(p268)    ch39 Example 38.6(p328)
每一条的规范键都由**编号首段那一章**的契约实际承载（11/11，0 条无主），即真身在册、
本章交付没有它才是正确的；判 readable 会逼出「往 ch7 契约回填 定义8.1」的重复编号。

既有的 `_foreign_sections` 修不了它：那套判据只认**裸数字节键**（Tu 体例 §11 属 ch3），
而本书节键是点分形 ``14.1`` → foreign 集恒空。根治 = 新增按契约实际登记取证的
`_chapter_canon_owners` + `_cross_chapter_registered`，与前者并列同判 `reference`。

🔴 负向面（真缺不得被洗白）同样钉住：归属章**没有**登记该 canon（那章也丢了）、
只被他章登记（编号碰撞）、首段即本章、canon 非全 int 或只有一段 —— 四种都必须返回 None。

Run:  python verify/tests/test_cross_chapter_registered_reference.py
"""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

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

from verify.script.check_structure_completeness import (  # noqa: E402
    _chapter_canon_owners, _cross_chapter_registered)


def _item(key, type_="definition"):
    return SimpleNamespace(type=type_, key=key, name=key, sub_sec=[])


def _section(key, *items):
    return SimpleNamespace(type="section", key=key, name=key, sub_sec=list(items))


def _chapter(key, *nodes):
    return SimpleNamespace(type="chapter", key=key, name="ch" + key, sub_sec=list(nodes))


def _book(*chapters):
    # description 节点混进节里：证明它和 section 一样不入索引
    d = SimpleNamespace(type="description", key="D1", name="", sub_sec=[])
    return SimpleNamespace(root=_chapter("0", *([_section("0.1", d, _item("定义0.1"))]
                                               + list(chapters))))


def _bs(*chapters):
    return _book(*chapters)


OWNERS = _chapter_canon_owners(_bs(
    _chapter("1", _section("1.1", _item("定义1.1"))),
    _chapter("8", _section("8.1", _item("定义8.1"), _item("例8.2", "example"))),
))


class TestOwnersIndex(unittest.TestCase):
    def test_holds_item_keys_with_owning_chapter(self):
        self.assertEqual(OWNERS.get("定义8.1"), {"8"})
        self.assertEqual(OWNERS.get("例8.2"), {"8"})

    def test_section_and_description_keys_are_not_indexed(self):
        # 节键 8.1 / 描述键 D1 不是条目身份，进了索引就会把「节」当成条目持有者
        self.assertIsNone(OWNERS.get("8.1"))
        self.assertIsNone(OWNERS.get("D1"))

    def test_no_bs_returns_empty(self):
        self.assertEqual(_chapter_canon_owners(None), {})


class TestPositive(unittest.TestCase):
    def test_dotted_number_registered_by_that_chapter(self):
        it = {"label": "Definition", "key": "Definition 8.1"}
        self.assertEqual(_cross_chapter_registered((8, 1), it, "7", OWNERS), "8")

    def test_canonical_chinese_label_matches_too(self):
        it = {"label": "定义", "key": "定义 8.1"}
        self.assertEqual(_cross_chapter_registered((8, 1), it, "7", OWNERS), "8")

    def test_space_stripped_source_key_matches(self):
        owners = {"theorem14.17": {"14"}}
        it = {"label": "Theorem", "key": "Theorem 14.17"}
        self.assertEqual(_cross_chapter_registered((14, 17), it, "17", owners), "14")

    def test_three_segment_canon_uses_first_segment_as_owner(self):
        owners = {"定理14.1.7": {"14"}}
        it = {"label": "Theorem", "key": "Theorem 14.1.7"}
        self.assertEqual(_cross_chapter_registered((14, 1, 7), it, "17", owners), "14")


class TestNegative(unittest.TestCase):
    def test_owning_chapter_also_lost_it_stays_missing(self):
        # 真缺：ch8 契约里也没有 定义9.9 —— 不得洗成 reference
        self.assertIsNone(_cross_chapter_registered((9, 9),
                                                    {"label": "Definition", "key": "Definition 9.9"},
                                                    "7", OWNERS))

    def test_registered_only_in_another_chapter_is_a_collision_not_evidence(self):
        owners = {"定义8.1": {"3"}}   # 首段是 8，登记的却是 ch3
        self.assertIsNone(_cross_chapter_registered((8, 1),
                                                    {"label": "Definition", "key": "Definition 8.1"},
                                                    "7", owners))

    def test_first_segment_is_this_chapter(self):
        self.assertIsNone(_cross_chapter_registered((8, 1),
                                                    {"label": "Definition", "key": "Definition 8.1"},
                                                    8, OWNERS))

    def test_single_segment_canon(self):
        self.assertIsNone(_cross_chapter_registered((8,),
                                                    {"label": "Definition", "key": "Definition 8"},
                                                    "7", OWNERS))

    def test_non_int_segment(self):
        self.assertIsNone(_cross_chapter_registered(("A", 1),
                                                    {"label": "Definition", "key": "Definition A.1"},
                                                    "7", OWNERS))

    def test_empty_index(self):
        self.assertIsNone(_cross_chapter_registered((8, 1),
                                                    {"label": "Definition", "key": "Definition 8.1"},
                                                    "7", {}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
