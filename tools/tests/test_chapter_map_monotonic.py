"""test_chapter_map_monotonic.py — 目录页命中压过真开页时的章序单调修复判据。

缺陷根因（Apostol《Introduction to Analytic Number Theory》实测 2026-09-28）：
目录页 p7 首行是 ``Contents``，其下 ``Chapter 1`` / ``Chapter 2`` 条目与后随标题行
在 OCR 通道里和真章开页**同形**，``is_toc_line``（靠点线/尾部页号）认不出，于是
Mode A 把 ch1、ch2 双双锚到 p7：起点不随章序递增、ch0 的推断 end 变成 6，
`build_chapter_map` 只能整本标 SUSPECT 拒绝落账——页码是下游所有阶段的区间真值，
一处目录页命中就级联污染前后三章。

修复形态：``detect_starts`` 把每章**全部**过阈候选（A0/A/B）交回候选池；
``repair_monotonic_starts`` 按章序走一遍，起点不递增的章改取「上一页 > 前章起点」
的最优候选。🔴 池内无候选满足约束时**保留原值**（自检照旧标 SUSPECT 逼人工介入），
绝不为了「看起来单调」伪造页码。

正向：TOC 高分命中 + 池内有章序合法的次优候选 → 改锚真开页、标 REPAIRED。
负向：①池内无合法候选 → 不改动、不伪造；②本就单调 → 零修复；
      ③同分候选取更早页（与 Mode A/B 同口径），不越窗挑远的。
"""
import os
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "lib"))
import lib.boot as _boot  # noqa: E402
_boot.setup()

import importlib.util  # noqa: E402

_SPEC = importlib.util.spec_from_file_location(
    "build_chapter_map", os.path.join(_ROOT, "tools", "build_chapter_map.py"))
bcm = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(bcm)


def _heading(page, title, label=None, toc=False, near_top=True):
    norm = bcm.norm_title(title)
    return {
        "page": page,
        "label_norm": label,
        "title_cands": [norm],
        "toc": toc,
        "body_mention": False,
        "same_line_title": False,
        "near_top": near_top,
        "raw": title,
        "next_raw": "1.1 Introduction",
        "page_first": "Contents" if page == 7 else title,
        "line_idx": 0,
        "norm": norm,
        "norms": [norm],
    }


def _ch(ch, name, start, end):
    return {"ch": ch, "name": name, "name_en": name, "start": start, "end": end}


CHAPTERS = [
    _ch(0, "Historical Introduction", 13, 24),
    _ch(1, "The Fundamental Theorem of Arithmetic", 25, 35),
    _ch(2, "Arithmetical Functions and Dirichlet Multiplication", 36, 63),
]

# p7 目录页：首行 "Contents"，"Chapter N" 条目无点线 → scan_headings 不会标 toc，
# Mode A 以满分命中；真开页 p25/p36 只有裸标题（无 "Chapter N" 行）→ 仅 Mode B 命中。
HEADINGS = [
    _heading(7, "The Fundamental Theorem of Arithmetic", label=1),
    _heading(7, "Arithmetical Functions and Dirichlet Multiplication", label=2),
]
TITLE_LINES = [
    _heading(25, "The Fundamental Theorem of Arithmetic"),
    _heading(36, "Arithmetical Functions and Dirichlet Multiplication"),
]


class DetectCandidates(unittest.TestCase):
    def test_pool_covers_all_modes_even_when_a_wins(self):
        """A 当选时 B 池仍须交回——真开页往往只在 B 池里。"""
        pool = {}
        det = bcm.detect_starts(CHAPTERS, HEADINGS, TITLE_LINES,
                                openers=[], cn_head_start=None, candidates=pool)
        self.assertEqual(det["1"][0], 7)          # 修复前：被目录页蹭中
        self.assertIn((7, 1.02, "A"), pool["1"])  # 页眉近顶 +0.02
        self.assertIn((25, 1.0, "B"), pool["1"])
        self.assertIn((36, 1.0, "B"), pool["2"])

    def test_no_candidates_argument_is_noop(self):
        """不传 candidates 时行为与历史逐字节一致（不回填、不改选）。"""
        det = bcm.detect_starts(CHAPTERS, HEADINGS, TITLE_LINES,
                                openers=[], cn_head_start=None)
        self.assertEqual({k: v[0] for k, v in det.items()}, {"1": 7, "2": 7})


class RepairMonotonic(unittest.TestCase):
    def test_toc_hit_repointed_to_real_opener(self):
        """正向：起点违反章序递增 → 改取池内前一章起点之后的最优候选。"""
        pool = {}
        det = bcm.detect_starts(CHAPTERS, HEADINGS, TITLE_LINES,
                                openers=[], candidates=pool)
        starts = {ch: det[ch][0] for ch in det}
        starts["0"] = 13   # ch0 由开页/页眉正确定位
        order = ["0", "1", "2"]
        fixed, repairs = bcm.repair_monotonic_starts(starts, pool, order)
        self.assertEqual(fixed, {"0": 13, "1": 25, "2": 36})
        self.assertEqual(repairs["1"][:2], (7, 25))
        self.assertEqual(repairs["2"][:2], (7, 36))

    def test_no_legal_alternative_keeps_value_no_fabrication(self):
        """负向：池内没有满足「> 前章起点」的候选 → 原值保留，交自检标 SUSPECT。"""
        pool = {"1": [(7, 1.0, "A")], "2": []}
        starts = {"0": 13, "1": 7, "2": 36}
        fixed, repairs = bcm.repair_monotonic_starts(starts, pool, ["0", "1", "2"])
        self.assertEqual(fixed["1"], 7)
        self.assertEqual(repairs, {})

    def test_already_monotonic_repairs_nothing(self):
        """负向：本就单调递增时零改动（正常书不得被修复逻辑碰）。"""
        pool = {"1": [(25, 1.0, "B"), (7, 1.0, "A")], "2": [(36, 1.0, "B")]}
        starts = {"0": 13, "1": 25, "2": 36}
        fixed, repairs = bcm.repair_monotonic_starts(starts, pool, ["0", "1", "2"])
        self.assertEqual(fixed, starts)
        self.assertEqual(repairs, {})

    def test_tie_prefers_earliest_page(self):
        """同分候选取更早页：不越过真开页去挑后面的别章页眉。"""
        pool = {"1": [(40, 1.0, "A"), (25, 1.0, "B")]}
        fixed, repairs = bcm.repair_monotonic_starts(
            {"0": 13, "1": 7}, pool, ["0", "1"])
        self.assertEqual(fixed["1"], 25)

    def test_undetected_chapter_does_not_break_the_walk(self):
        """start 为 None 的章（UNDTECTED）跳过且不重置游标。"""
        pool = {"2": [(36, 1.0, "B")]}
        fixed, repairs = bcm.repair_monotonic_starts(
            {"0": 13, "1": 7, "2": 36}, pool, ["0", "1", "2"])
        self.assertEqual(fixed, {"0": 13, "1": 7, "2": 36})
        self.assertEqual(repairs, {})


if __name__ == "__main__":
    unittest.main()
