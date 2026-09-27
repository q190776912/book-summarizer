# -*- coding: utf-8 -*-
"""章末集中习题区：分组小标题不得解除闩锁，习题须留在章末（Strogatz 3e，2026-09-27）。

根因（四处，全部由本书实测暴露）：
  1. `scan_skeleton` 通用节检测：章末习题区按节分组印「2.1 A Geometric Way of
     Thinking」等小标题，与正文真节头**逐字同形** → 旧逻辑发 SEC 并解除 in_exercise
     闩锁，其后三段题号习题（2.1.1 / 2.2.1 …）不再走 EXER_3N → 13 章习题 0 收录。
     真节号一章内不可能印刷两次，闩锁内的重复节号必是习题分组头。
  2. `build_chapter` 习题挂接：按号→节挂进 §2.1 后，契约前序摊平成
     §2.1(p31) → 习题(p53) → §2.2(p33) 的页码倒退，ANCHOR-SANITY 13 章 67 处拒绝落盘。
     章末集中块须挂**章级子列表末尾**并标 ``consolidated: true``
     （docs/writing-rules.md「有专门习题小标题的集中习题块一律省略」）。
  3. `build_chapter` 习题区 ITEM 剔除：旧版只取块头**页码**，与块头同页却印在其
     **上方**的真条目被连页误杀（ch6 p213 y=852 的 `Example 6.8.6:` 先于同页 y=1149
     的 `EXERCISES FOR CHAPTER 6`）。改为 (page, y) 字典序比较。
  4. `build_chapter` 同键习题行：题干跨页续行「6.1.1. The nullcline …」(p214) 与真
     习题 6.1.1(p213) 同键 → 两个同号节点把文档序排乱，ANCHOR-SANITY 6 处拒绝落盘。

运行：
  python flows/write-source/structure/script/tests/test_strogatz_chapter_end_exercises.py
"""
import json
import os
import sys
import tempfile
import types
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

_SCRIPT = os.path.join(_ROOT, "flows", "write-source", "structure", "script")
if _SCRIPT not in sys.path:
    sys.path.insert(0, _SCRIPT)
import scan_skeleton as ss           # noqa: E402
import build_structure as bs         # noqa: E402
from verify_config import GroupConfig  # noqa: E402


# 正文两节（p1/p2）→ 章末集中习题块（p3）→ 题干跨页续行（p4）。
# 行按 y=100+60*i 排列（块顶纵坐标），便于断言 y 感知剔除。
BODY = [
    ["2.0 Introduction",
     "Consider the equation dx/dt = rx(1 - x/K) of population growth.",
     "2.1 A Geometric Way of Thinking",
     "The sign of f(x) determines the direction of the flow."],
    ["2.2 Overdamped Motion",
     "The mass slowly returns to equilibrium without oscillating.",
     "Example 2.2.1:",
     "Investigate the flow near each fixed point of the overdamped case."],
    ["Example 2.2.2:",
     "A final remark closes the section before the problem set begins.",
     "EXERCISES FOR CHAPTER 2",
     "2.1 A Geometric Way of Thinking",
     "2.1.1 Find all the fixed points of dx/dt = x - x^3.",
     "2.1.2 Sketch the graph of f(x) = exp(-x^2) in the cusp case.",
     "2.2.1 Consider the equation m x'' + c x' + k x = 0 for a mass.",
     "Example 2.2.9:",
     "This line sits below the block heading and is not a real item."],
    ["2.1.1 The nullcline equation then implies that the trajectory is straight."],
]


def _mk(d, pages):
    for p, lines in enumerate(pages, start=1):
        blocks = [{"text": ln,
                   "poly": [60, 100 + 60 * i, 1100, 140 + 60 * i,
                            60, 140 + 60 * i, 60, 100 + 60 * i]}
                  for i, ln in enumerate(lines)]
        with open(os.path.join(d, "page_%03d.json" % p), "w", encoding="utf-8") as fh:
            json.dump({"text": blocks, "formulas": []}, fh)


def _book():
    return types.SimpleNamespace(
        primary_type=bs.ORDINAL_THREE_LEVEL, language="en", chapter_first=True,
        section_depths=[1, 2],
        ordinal=[GroupConfig(type=3, name=["Example", "Definition", "Theorem"],
                             scope=1)],
        section_scoped=False, gm_bare_numbered=False, exercise_region_headings=None,
        sections_global=False, numeric_local_sections=False,
        chapter_local_numbering=False, sections_unnumbered=False,
        chapter_local_sections=False, chapter_scoped_items=False)


def _cm(ch, npages, name="T"):
    return {"chapters": [{"ch": ch, "name": name, "start": 1, "end": npages}]}


def _flatten(node, out=None):
    out = [] if out is None else out
    out.append(node)
    for s in (node.get("sub_sec") or []):
        _flatten(s, out)
    return out


def _build(pages, ch=2):
    with tempfile.TemporaryDirectory() as d:
        _mk(d, pages)
        return bs.build_chapter(d, ch, 1, len(pages), _book(), _cm(ch, len(pages)))


def _scan(pages, ch):
    with tempfile.TemporaryDirectory() as d:
        _mk(d, pages)
        return ss.scan(d, ch, 1, len(pages), "three-level",
                       section_depths=[1, 2], chapter_first=True)


class TestExerciseGroupLatch(unittest.TestCase):
    """判据 1：闩锁内重复节号不发 SEC、不解锁。"""

    def test_group_head_does_not_release_latch(self):
        rows = _scan([BODY[0], BODY[2]], 2)
        secs = [r[2] for r in rows if r[1] == 'SEC']
        self.assertEqual(secs.count("2.1"), 1,
                         "习题分组头「2.1 A Geometric Way of Thinking」不得再发 SEC")
        got = sorted((r[2] for r in rows if r[1] == 'EXER'))
        self.assertEqual(got, ["2.1.1", "2.1.2", "2.2.1"],
                         "闩锁未解除时三段题号须全部走 EXER")

    def test_genuine_new_section_still_releases_latch(self):
        rows = _scan([BODY[0] + ["EXERCISES", "2.1.1 Find the fixed points here."],
                      BODY[1]], 2)
        secs = [(r[0], r[2]) for r in rows if r[1] == 'SEC']
        self.assertIn((2, "2.2"), secs, "习题块之后的真节头仍须解锁并发 SEC")

    def test_guard_does_not_swallow_exercises(self):
        # 闩锁内三段题号**全部**成 EXER（守卫只拦重复节号，不吞题号）；
        # 跨页续行在 scan 层就是同键重复行，去重发生在 build_chapter。
        rows = _scan([BODY[0], BODY[2], BODY[3]], 2)
        self.assertEqual(sorted(r[2] for r in rows if r[1] == 'EXER'),
                         ["2.1.1", "2.1.1", "2.1.2", "2.2.1"])


class TestChapterTailConsolidation(unittest.TestCase):
    """判据 2：章末块挂章级子列表末尾 + consolidated。"""

    def test_tail_exercises_marked_consolidated(self):
        tree = _build([BODY[0], BODY[1], BODY[2]])
        tail = [c for c in tree["sub_sec"] if c.get("consolidated")]
        self.assertEqual([c["key"] for c in tail], ["2.1.1", "2.1.2", "2.2.1"],
                         "章末集中块须排在章级子列表**末尾**（全部节之后）")
        self.assertTrue(all(c["type"] == "exercise" for c in tail))

    def test_exercises_not_nested_under_their_section(self):
        tree = _build([BODY[0], BODY[1], BODY[2]])
        for sec in [c for c in tree["sub_sec"] if c["type"] == "section"]:
            self.assertEqual([s["key"] for s in sec["sub_sec"]
                              if s.get("consolidated")], [],
                             "习题块节点不得挂进派生小节")

    def test_flat_document_order_is_page_monotone(self):
        tree = _build(BODY[:3] + [BODY[3]])
        pages = [int(n.get("page_start") or 0) for n in _flatten(tree)
                 if n.get("page_start") is not None]
        self.assertEqual(pages, sorted(pages),
                         "契约前序摊平的 page_start 必须单调不减（ANCHOR-SANITY）")

    def test_per_section_block_is_not_consolidated(self):
        # do Carmo 形态（节末 EXERCISES，其后还有真节）：不得标 consolidated。
        pages = [
            ["3.1 Existence and Uniqueness",
             "The theorem asserts a local flow exists.",
             "EXERCISES",
             "3.1.1 Verify the Lipschitz condition for the given vector field."],
            ["3.2 The Exponential Map",
             "One-parameter subgroups are integral curves of the field."],
        ]
        tree = _build(pages, ch=3)
        self.assertFalse([n for n in _flatten(tree) if n.get("consolidated")],
                         "节末块（真节之后仍出现内容）不属章末集中形态")


class TestItemRegionYFilter(unittest.TestCase):
    """判据 3：习题区起点按 (page, y) 剔除，块头之上的同页条目保留。"""

    def test_item_above_block_heading_survives(self):
        tree = _build([BODY[0], BODY[1], BODY[2]])
        names = " | ".join((n.get("name") or "") + "#" + str(n.get("key"))
                           for n in _flatten(tree))
        self.assertIn("2.2-2", names,
                      "块头**上方**（同页 y 更小）的真条目不得被连页误杀")

    def test_item_below_block_heading_dropped(self):
        tree = _build([BODY[0], BODY[1], BODY[2]])
        keys = [str(n.get("key")) for n in _flatten(tree)]
        self.assertNotIn("2.2-9", keys,
                         "块头**下方**的 Example 行落在习题区，不得成条目")

    def test_region_helper_returns_page_and_y(self):
        with tempfile.TemporaryDirectory() as d:
            _mk(d, [BODY[0], BODY[1], BODY[2]])
            got = bs._exercise_region_start(d, 2, 1, 3, page_dir=d)
        self.assertIsNotNone(got)
        page, y = got
        self.assertEqual(page, 3)
        self.assertEqual(y, 100 + 60 * 2, "锚点 y 须取块头块顶，不是页顶")


class TestDuplicateExerciseRows(unittest.TestCase):
    """判据 4：同键习题行首现保留，题干跨页续行不得成第二个节点。"""

    def test_duplicate_key_kept_once(self):
        tree = _build(BODY[:3] + [BODY[3]])
        got = [n for n in _flatten(tree) if n.get("key") == "2.1.1"]
        self.assertEqual(len(got), 1,
                         "跨页续行「2.1.1 The nullcline…」不得再挂一节点")
        self.assertEqual(got[0]["page_start"], 3, "锚点取首现（真条头）页")


class TestOcrDigitOneInExerciseNumber(unittest.TestCase):
    """判据 6：`5.1.i3`（印刷 5.1.13，OCR 把 1 打成 i）须修回三段题号。

    未修复时 EXER_3N 失配 → 落两段题号兜底分支发成**假习题 5.1**：真号 13 丢失，
    契约里还多出一条与节号同形的条目。
    """

    def test_letter_one_repaired_to_three_part(self):
        rows = _scan([["EXERCISES FOR CHAPTER 5",
                       "5.1.12 (Closed orbits) Give a simple proof that works."],
                      ["5.1.i3 Why do you think a saddle point is called by that name?"]], 5)
        self.assertEqual([(r[0], r[1], r[2]) for r in rows],
                         [(1, 'EXER', '5.1.12'), (2, 'EXER', '5.1.13')],
                         "OCR 的 i3 须修成 13，不得退化成假习题 5.1")

    def test_letter_subpart_not_rewritten(self):
        # 字母分部（"10.3.A"，后面不接数字）不得被本修复改写成数字号。
        rows = _scan([["10.3.A EASY EXERCISE. Show that the affine line is not."]], 10)
        self.assertEqual([(r[1], r[2]) for r in rows], [('EXER', '10.3.A')])


class TestExerciseLabelReferenceNotDuplicated(unittest.TestCase):
    """判据 5：正文里的 "(See\\nExercise 9.1.3.) …" 回指不得追加第二个同号节点。

    3a 通道把抽取器抓出的练习类**条目**并入 EXER 行，去重集合用 skeleton 行的点分
    号（"9.1.3"），而条目键已过 normkey 转连字符（"9.1-3"）——字面比较永不命中，
    于是正文回指在 §9.1 下挂出一个假习题节点并吞掉其后 86 个正文块。
    """

    def test_label_reference_merged_with_region_head(self):
        pages = [
            ["9.1 The Lorenz Equations",
             "system (9). It turns out that (9) is equivalent to the Lorenz!",
             "Exercise 9.1.3.) Before we turn to that more famous system, let's"],
            ["EXERCISES FOR CHAPTER 9",
             "9.1.3 The goal of this exercise is to clarify the relationship."],
        ]
        tree = _build(pages, ch=9)
        nodes = [n for n in _flatten(tree)
                 if n.get("type") in ("exercise", "problem")
                 and str(n.get("key")).replace("-", ".") == "9.1.3"]
        self.assertEqual(len(nodes), 1,
                         "回指行不得再挂一个同号习题节点：%s"
                         % [(n.get("key"), n.get("page_start")) for n in nodes])
        self.assertEqual(nodes[0]["page_start"], 2, "留下的须是区内真头（p2）")
        self.assertTrue(nodes[0].get("consolidated"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
