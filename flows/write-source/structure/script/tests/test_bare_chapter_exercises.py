# -*- coding: utf-8 -*-
"""章末裸单号习题 + 页眉复本不得抢先闩锁（Apostol《Introduction to Analytic
Number Theory》实测 2026-09-28）。

根因（两处，同一页暴露）：印刷把当前习题块标题 **作为页眉**印在每页页首右侧
（p155 页眉 "Exercises for Chapter 7" x0=721 y=59），而该页页中还有正文条目
Theorem 7.10。旧逻辑用 EXER_HEADING 命中页眉就闩 `in_exercise` → 同页其后的
正文条目被习题区抑制整条吞掉（抽取器漏条、契约缺项，只能靠源侧回填兜底）。
同时本书习题印成**裸单号**（"4. Let S be any infinite subset …"），
STICKY_EXER_RE（要求 C.S 两段）与 EXER_3N（三段）都收不到 → 全书练习 0 收录。

判据：
  1. 页眉带（块顶 y < 100 **且** 块首 x 右移过本页 1/4 页宽）的习题块标题复本
     不激活闩锁；左对齐的页顶真标题照旧激活（零回归）。
  2. 闩锁内 `N.`/`N)` + 空白 + 大写字母或小题括号、且 N 恰为计数器 +1 的行收为
     EXER（键 = 裸号）；断号不收，公式残行 "1 = A(k) +" 不收。
  3. 体例仲裁：本章只要存在带点题号习题（C.S / C.S-N），裸单号行整体退回。
  4. 端到端：块头上方的同页真条目仍进契约，块头下方的裸号行成练习节点。

运行：
  python flows/write-source/structure/script/tests/test_bare_chapter_exercises.py
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

CH = 7


def _book():
    return types.SimpleNamespace(
        primary_type=bs.ORDINAL_TWO_LEVEL, language="en", chapter_first=True,
        section_depths=[1, 2],
        ordinal=[GroupConfig(type=2, name=["Theorem"], scope=2)],
        section_scoped=False, gm_bare_numbered=False,
        exercise_region_headings=None,
        sections_global=False, numeric_local_sections=False,
        chapter_local_numbering=False, sections_unnumbered=False,
        chapter_local_sections=False, chapter_scoped_items=True)


def _cm(npages, ch=CH):
    return {"chapters": [{"ch": ch, "name": "Dirichlet", "start": 1, "end": npages}]}


def _mk(d, pages):
    """每行一个块：`lines` 项为 (text, x0, y)；缺省 x0=71（左边界）、y 递增。"""
    for p, lines in enumerate(pages, start=1):
        blocks = []
        for i, ln in enumerate(lines):
            text, x0, y = (ln if isinstance(ln, tuple) else (ln, 71, 150 + 60 * i))
            blocks.append({"text": text,
                           "poly": [x0, y, x0 + 900, y, x0, y + 30, x0, y]})
        with open(os.path.join(d, "page_%03d.json" % p), "w", encoding="utf-8") as fh:
            json.dump({"text": blocks, "formulas": []}, fh)


def _scan(pages, ch=CH):
    with tempfile.TemporaryDirectory() as d:
        _mk(d, pages)
        return ss.scan(d, ch, 1, len(pages), "two-level",
                       section_depths=[1, 2], chapter_first=True, language="en")


def _build(pages, ch=CH):
    with tempfile.TemporaryDirectory() as d:
        _mk(d, pages)
        return bs.build_chapter(d, ch, 1, len(pages), _book(), _cm(len(pages), ch))


def _flatten(node, out=None):
    out = [] if out is None else out
    out.append(node)
    for s in (node.get("sub_sec") or []):
        _flatten(s, out)
    return out


# p1：页眉（右对齐 y=59）+ 正文条目 + 页中真习题块标题 + 裸号习题 1、2。
PAGE1 = [
    ("Exercises for Chapter 7", 721, 59),          # 页眉复本：不得闩锁
    "We conclude this chapter by giving an alternate formulation.",
    "Theorem 7.10 If the relation holds for every integer a prime to k.",
    "1 = A(k) plus a sum over the residue classes.",
    "Exercises for Chapter 7",                      # 真块标题（左边界）
    "1. Prove that for every integer n there are infinitely many.",
    "2. Prove that A(h, k) contains an infinite subset.",
]
PAGE2 = [
    ("Exercises for Chapter 7", 721, 59),          # 次页页眉
    "3. (a) Find all positive integers n with the stated property.",
    "4. Let S be any infinite subset of A(h, k). Prove the claim.",
]


class TestRunningHeadLatch(unittest.TestCase):
    def test_running_head_does_not_latch(self):
        # 真块标题在页中：其**上方**的 Theorem 7.10 必须成条目（闩锁未抢先激活）
        tree = _build([PAGE1, PAGE2])
        keys = [str(n.get("key")) for n in _flatten(tree)]
        self.assertIn("定理7.10", keys,
                      "页眉复本不得在页顶抢先激活习题区而吞掉同页正文条目：%s" % keys)

    def test_real_heading_still_latches(self):
        rows = _scan([PAGE1, PAGE2])
        self.assertEqual([r[2] for r in rows if r[1] == 'EXER'],
                         ["1", "2", "3", "4"],
                         "真块标题之下的裸号习题须全部收为 EXER")

    def test_left_aligned_top_of_page_heading_still_latches(self):
        # 块标题印在新页页顶（左边界）：仍是真标题，照旧闩锁（零回归）。
        pages = [[("Exercises for Chapter 7", 71, 59),
                  "1. Prove the first statement given here today."]]
        rows = _scan(pages)
        self.assertEqual([r[2] for r in rows if r[1] == 'EXER'], ["1"])


class TestBareExerciseGuards(unittest.TestCase):
    def test_formula_fragment_not_collected(self):
        rows = _scan([[("Exercises for Chapter 7", 71, 1200),
                       "1 = A(k) plus more prose about the sum.",
                       "1. Prove the first statement given here today.",
                       "2. Prove the second statement given here today."]])
        self.assertEqual([r[2] for r in rows if r[1] == 'EXER'], ["1", "2"],
                         '"1 = A(k) …" 是公式残行，不得当题号')

    def test_gap_number_not_collected(self):
        rows = _scan([[("Exercises for Chapter 7", 71, 1200),
                       "1. Prove the first statement given here today.",
                       "7. Prove a far-later statement whose head broke the chain."]])
        self.assertEqual([r[2] for r in rows if r[1] == 'EXER'], ["1"],
                         "断号（宁缺毋滥）不收：计数器只认 +1")

    def test_dotted_form_wins_arbitration(self):
        # C.S 题号体例的书（Casella & Berger 形）：裸号行不得混入同一章。
        pages = [[("EXERCISES FOR CHAPTER 7", 71, 1200),
                  "7.1 Find the marginal distribution of the given joint pdf.",
                  "1. A stray bare-number line in the same region."]]
        rows = _scan(pages)
        got = [r[2] for r in rows if r[1] == 'EXER']
        self.assertEqual(got, ["7.1"],
                         "存在带点题号时裸单号行整体退回（体例互斥仲裁）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
