# -*- coding: utf-8 -*-
"""Regression: 章级「习题键唯一」闸须按页窗+内容裁决，不得把原书**重新起号**当碎片。

Arnold《经典力学的数学方法》§8 实测（2026-09-29，ch2 门控）：印刷 p.27–28 有问题
1–6，中译者注的补充讨论之后（印刷 p.32）又印着问题 1–3，**各带完整题面与解**。
旧闸假定「同键两节点 = OCR 续行碎片被切成幻影条目」（Rosen 重号练习组、Katok 空壳
单元即此形态），对这类合法形态一律 FAIL，而唯一「修法」是把印面习题并回上一条目 =
删内容。根治点同在闸的判据：以契约同键节点的**页窗是否不相交**（后者起始页 > 前者
结束页）与**是否各自带内容块**裁决——两条都成立 = 重新起号，放行；否则照报。

本测试锁死两件事：
① 放行只发生在证据齐备时（页窗缺失 / 空壳 / 同页相交 / 节点数与单元数不符 /
   拿不到契约，一律仍 FAIL —— fail-closed，绝不因判据失效静默绿灯）；
② 页窗真值 `exercise_node_windows` 与 `split_draft_units.walk_container` 的习题单元
   选取判据一字对应（consolidated 成堆块不出单元也不下钻），否则闸会凭空造出
   「节点数不符」的假阴。
"""
import os
import sys
import unittest

_here = os.path.dirname(os.path.abspath(__file__))
_root = _here
while not os.path.exists(os.path.join(_root, "SKILL.md")):
    _parent = os.path.dirname(_root)
    if _parent == _root:
        raise RuntimeError("SKILL.md not found above %s" % _here)
    _root = _parent
sys.path.insert(0, _root)
import lib.boot  # noqa: E402
lib.boot.setup()

from data.book_structure.book_structure import exercise_node_windows  # noqa: E402
import gate_units as gu  # noqa: E402


def _problem(key, ps, pe, blocks=3, name=None):
    """一个习题节点：blocks 个 text 内容块（blocks=0 且 name 无题面 = 碎片/幻影）。"""
    return {"key": key, "type": "problem", "name": name if name is not None else key,
            "page_start": ps, "page_end": pe,
            "sub_sec": [{"text": "题面 %d" % i} for i in range(blocks)]}


def _contract(nodes, key="8"):
    return {"key": "2", "type": "chapter", "name": "2 运动方程的研究",
            "sub_sec": [{"key": key, "type": "section", "name": "§%s" % key,
                         "sub_sec": list(nodes)}]}


def _units(pairs):
    return [{"type": "exercise", "key": k, "file": f, "id": i}
            for i, (k, f) in enumerate(pairs)]


class TestRenumberExempted(unittest.TestCase):
    """正例：两套不相交页窗、各带题面的同号问题 = 原书重新起号，放行。"""

    def test_disjoint_windows_with_content_pass(self):
        c = _contract([_problem("问题1", 27, 28), _problem("问题1", 32, 33)])
        units = _units([("问题1", "0015_exercise_问题1.md"),
                        ("问题1", "0021_exercise_问题1.md")])
        self.assertEqual(gu._check_exercise_key_uniqueness(units, c), [])

    def test_three_sets_monotonic_pass(self):
        c = _contract([_problem("问题2", 10, 11), _problem("问题2", 20, 21),
                       _problem("问题2", 30, 31)])
        units = _units([("问题2", "a.md"), ("问题2", "b.md"), ("问题2", "c.md")])
        self.assertEqual(gu._check_exercise_key_uniqueness(units, c), [])

    def test_unique_keys_need_no_adjudication(self):
        c = _contract([_problem("问题1", 27, 28), _problem("问题2", 27, 28)])
        units = _units([("问题1", "a.md"), ("问题2", "b.md")])
        self.assertEqual(gu._check_exercise_key_uniqueness(units, c), [])


class TestFragmentStillCondemned(unittest.TestCase):
    """负例：碎片形态一项都不许被放宽。"""

    def _two_units(self):
        return _units([("问题1", "0015_exercise_问题1.md"),
                       ("问题1", "0021_exercise_问题1.md")])

    def test_same_page_fragment_flagged(self):
        c = _contract([_problem("问题1", 27, 28), _problem("问题1", 28, 28)])
        probs = gu._check_exercise_key_uniqueness(self._two_units(), c)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("页窗相交", probs[0])

    def test_overlapping_windows_flagged(self):
        c = _contract([_problem("问题1", 27, 30), _problem("问题1", 29, 31)])
        probs = gu._check_exercise_key_uniqueness(self._two_units(), c)
        self.assertTrue(any("页窗相交" in p for p in probs), probs)

    def test_empty_shell_flagged(self):
        c = _contract([_problem("问题1", 27, 28), _problem("问题1", 32, 33, blocks=0)])
        probs = gu._check_exercise_key_uniqueness(self._two_units(), c)
        self.assertTrue(any("无题面" in p for p in probs), probs)

    def test_missing_page_window_flagged(self):
        c = _contract([_problem("问题1", 27, 28), _problem("问题1", None, None)])
        probs = gu._check_exercise_key_uniqueness(self._two_units(), c)
        self.assertTrue(any("页窗缺失" in p for p in probs), probs)

    def test_node_unit_count_mismatch_flagged(self):
        c = _contract([_problem("问题1", 27, 28)])
        probs = gu._check_exercise_key_uniqueness(self._two_units(), c)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("不符", probs[0])

    def test_no_contract_is_fail_closed(self):
        probs = gu._check_exercise_key_uniqueness(self._two_units(), None)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("无契约页窗可裁决", probs[0])
        self.assertIn("问题1", probs[0])

    def test_mid_window_overlap_reported_even_with_later_disjoint_pair(self):
        # 三套：1↔2 同页（碎片），2↔3 不相交 —— 逐对判定，不得因存在合法对而整体放行
        c = _contract([_problem("问题1", 27, 28), _problem("问题1", 27, 28),
                       _problem("问题1", 40, 41)])
        units = _units([("问题1", "a.md"), ("问题1", "b.md"), ("问题1", "c.md")])
        probs = gu._check_exercise_key_uniqueness(units, c)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("页窗相交", probs[0])


class TestWindowSelectionMatchesSplit(unittest.TestCase):
    """页窗真值的选取判据必须与 split_draft_units 出习题单元的判据一致。"""

    def test_consolidated_block_excluded(self):
        c = _contract([_problem("问题1", 27, 28),
                       {"key": "问题1", "type": "exercise", "consolidated": True,
                        "page_start": 51, "page_end": 52,
                        "sub_sec": [{"text": "整块章末习题"}]}])
        self.assertEqual(exercise_node_windows(c),
                         [("问题1", 27, 28, 3, "问题1")])

    def test_problem_type_collected_and_not_descended(self):
        node = _problem("问题1", 27, 28)
        node["sub_sec"].append({"key": "问题9", "type": "problem",
                                "page_start": 29, "page_end": 29,
                                "sub_sec": [{"text": "子项"}]})
        c = _contract([node])
        self.assertEqual([t[0] for t in exercise_node_windows(c)], ["问题1"])

    def test_sections_are_descended(self):
        c = _contract([_problem("问题1", 27, 28)], key="8")
        c["sub_sec"].append({"key": "9", "type": "section",
                             "sub_sec": [_problem("问题1", 33, 34)]})
        self.assertEqual(exercise_node_windows(c),
                         [("问题1", 27, 28, 3, "问题1"),
                          ("问题1", 33, 34, 3, "问题1")])

    def test_page_end_falls_back_to_page_start(self):
        node = {"key": "问题1", "type": "exercise", "page_start": 27,
                "sub_sec": [{"text": "题面"}]}
        self.assertEqual(exercise_node_windows(_contract([node])),
                         [("问题1", 27, 27, 1, "")])

    def test_name_carries_the_statement(self):
        node = _problem("问题2", 152, 152, blocks=0,
                        name="问题2 证明实轴上每个1-微分形式都是某函数的微分")
        self.assertEqual(exercise_node_windows(_contract([node])),
                         [("问题2", 152, 152, 0,
                           "问题2 证明实轴上每个1-微分形式都是某函数的微分")])


class TestStatementPredicateShared(unittest.TestCase):
    """重号裁决与幻影闸必须共用「节点带题面」谓词，否则同一节点两种结论。"""

    def test_contentless_node_with_full_statement_pair_passes(self):
        # Arnold ch7 实测形态：短题整行进 name，无 text 子块
        c = _contract([_problem("问题2", 150, 150, blocks=1),
                       _problem("问题2", 152, 152, blocks=0,
                                name="问题2 证明实轴上每个1-微分形式都是某函数的微分"),
                       _problem("问题2", 158, 158, blocks=2)])
        units = _units([("问题2", "a.md"), ("问题2", "b.md"), ("问题2", "c.md")])
        self.assertEqual(gu._check_exercise_key_uniqueness(units, c), [])

    def test_contentless_residue_pair_still_fails(self):
        c = _contract([_problem("问题2", 150, 150, blocks=1),
                       _problem("问题2", 152, 152, blocks=0, name="的量")])
        units = _units([("问题2", "a.md"), ("问题2", "b.md")])
        probs = gu._check_exercise_key_uniqueness(units, c)
        self.assertEqual(len(probs), 1, probs)
        self.assertIn("无题面", probs[0])


if __name__ == "__main__":
    unittest.main(verbosity=2)
