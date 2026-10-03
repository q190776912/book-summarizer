r"""Q 层 ORDER_MISMATCH 位置比较的「页级证据」回归（Iwaniec–Kowalski ch5 实测，2026-09-28）。

背景：`_compute_order_and_section` 用 ``cur < prev_pos`` 直接比较书源位置元组
``(page, y)``。``_record_pos`` 明确允许 y 为 ``None``（该编号只落在页级证据：
formulas 通道无 poly / text 块缺 poly）。同页两点一旦有 ``y=None``，元组比较退化成
``None < 560.0`` → TypeError，**整本 verify 崩在 Q 层**（本书 ch5 的 5.114 触发，
`--all` 直接 exit 1，后面 21 章根本没跑）。

修复 = 比较改走 `_pos_before`：页号不同仍按页判先后；同页且任一侧缺 y 时返回
``None``（证据不足，不下结论），既不崩也不误报。

断言：
  1. 同页 + y=None → 不崩、不报 ORDER_MISMATCH；
  2. 真倒序（页更小 / 同页 y 更小）仍报（不得因修崩而放行真错）；
  3. 正序不报。

🔴 2026-09-29 追加（Apostol IANT 实测）：同一 None-y 形态在**写路径**（`build_sectioned`
的 `_pos_sec` 记录、`_record_pos`）仍裸比较元组，把 `verify --all` 崩在 Q 层。现读写两侧
收敛到 `_pos_better`（内部调 `_pos_before`）一个判据，见 `TestPosBetterWritePath`。
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

from formula_tag import _compute_order_and_section, _pos_before, _pos_better


class _Tag:
    def __init__(self, normalized):
        self.normalized = normalized
        self.latex = "x = y"


class _FakeSrc:
    """只喂 `_compute_order_and_section` 用到的接口（含 MISPLACED 侧的属性）。"""

    def __init__(self, positions, sections=None):
        self._pos = dict(positions)
        self._sections = dict(sections or {})
        self._book_section_sec = {}
        self._n_pages = {}
        self._sec_start_page = {}
        self._pos_sec = {}
        self._walk_last_page = 0

    def source_numbers(self):
        return set(self._pos)

    def primary_pos(self, n):
        return self._pos.get(n)

    def book_section(self, n):
        return self._sections.get(n)


def _run(positions, order, reset_on_section=False):
    src = _FakeSrc(positions)
    tags_sec = [("5.14", _Tag(n)) for n in order]
    return _compute_order_and_section(tags_sec, src, set(),
                                      reset_on_section=reset_on_section)


class TestPosBefore(unittest.TestCase):
    def test_same_page_missing_y_is_no_verdict(self):
        self.assertIsNone(_pos_before((156, None), (156, 560.0)))
        self.assertIsNone(_pos_before((156, 560.0), (156, None)))

    def test_page_order_still_decided(self):
        self.assertIs(_pos_before((155, None), (156, 10.0)), True)
        self.assertIs(_pos_before((157, 1.0), (156, None)), False)

    def test_same_page_y_order(self):
        self.assertIs(_pos_before((156, 100.0), (156, 560.0)), True)
        self.assertIs(_pos_before((156, 600.0), (156, 560.0)), False)

    def test_missing_page_is_no_verdict(self):
        self.assertIsNone(_pos_before((None, 1.0), (156, 1.0)))
        self.assertIsNone(_pos_before(None, (156, 1.0)))


class TestOrderMismatchNoCrash(unittest.TestCase):
    def test_y_none_on_same_page_does_not_raise(self):
        # 5.113 有 y，5.114 只有页级证据；总结按 5.113 → 5.114 列出（正序）。
        # 旧代码在此处执行 (156, None) < (156, 560.0) → TypeError 崩掉整本 verify。
        om, mp = _run({"5.113": (156, 560.0), "5.114": (156, None)},
                      ["5.113", "5.114"])
        self.assertEqual(om, [])

    def test_y_none_as_earlier_item_does_not_raise(self):
        # 反方向（先列页级证据、后列带 y 者）同样不得崩
        om, mp = _run({"5.113": (156, 560.0), "5.114": (156, None)},
                      ["5.114", "5.113"])
        self.assertEqual(om, [])

    def test_real_inversion_still_flagged_across_pages(self):
        # 总结先列 5.2（书源 p170）后列 5.1（书源 p160）→ 后列者书源位置更靠前
        om, mp = _run({"5.2": (170, 100.0), "5.1": (160, 100.0)},
                      ["5.2", "5.1"])
        self.assertEqual([r["number"] for r in om], ["5.1"])

    def test_real_inversion_still_flagged_same_page(self):
        om, mp = _run({"5.2": (160, 100.0), "5.1": (160, 90.0)},
                      ["5.2", "5.1"])
        self.assertEqual([r["number"] for r in om], ["5.1"])

    def test_forward_order_clean(self):
        om, mp = _run({"5.1": (160, 90.0), "5.2": (160, 100.0)},
                      ["5.1", "5.2"])
        self.assertEqual(om, [])


class TestPosBetterWritePath(unittest.TestCase):
    r"""写路径（记录锚点）与读路径共用一个判据（Apostol IANT 2026-09-29 根治）。

    旧代码：`build_sectioned` 里 ``if _pp is None or (pg, y) < _pp`` 是手搓的裸元组
    比较。formulas 通道合成的标签块没有 `poly` → ``y=None``，同页已有一条带 y 的
    记录时比较退化成 ``None < 560.0`` → TypeError，`verify --all` 整趟崩在 Q 层
    （2026-09-28 只在读侧修了同形态，写侧漏网）。
    """

    def test_old_raw_tuple_compare_reproduces_the_crash(self):
        """负向锚点：确认本夹具正是当年崩的那一组输入。"""
        with self.assertRaises(TypeError):
            (156, None) < (156, 560.0)

    def test_y_none_new_does_not_crash_and_keeps_anchored(self):
        self.assertIs(_pos_better((156, None), (156, 560.0)), False)

    def test_y_none_old_is_replaced_by_defined(self):
        self.assertIs(_pos_better((156, 560.0), (156, None)), True)

    def test_earlier_page_still_wins(self):
        self.assertIs(_pos_better((155, None), (156, 560.0)), True)
        self.assertIs(_pos_better((157, 1.0), (156, None)), False)

    def test_same_page_smaller_y_wins(self):
        self.assertIs(_pos_better((156, 100.0), (156, 560.0)), True)
        self.assertIs(_pos_better((156, 600.0), (156, 560.0)), False)

    def test_missing_page_side_yields(self):
        self.assertIs(_pos_better((None, 1.0), (156, 1.0)), False)
        self.assertIs(_pos_better((156, 1.0), (None, 1.0)), True)
        self.assertIs(_pos_better((None, None), (None, None)), False)

    def test_first_record_always_written(self):
        self.assertIs(_pos_better((156, None), None), True)
        self.assertIs(_pos_better(None, (156, 1.0)), False)

    def test_record_pos_matches_the_predicate(self):
        """`_record_pos` 收敛到同一判据后，原分支表的行为逐条不变。"""
        from formula_tag import SourceFormulaIndex
        idx = SourceFormulaIndex.__new__(SourceFormulaIndex)
        idx._primary_pos = {}
        # `_record_pos` 的强/弱证据分支（2026-10-02）另开两张账本；`__new__` 夹具
        # 绕过 `__init__`，故此处按构造契约补齐。
        idx._pos_strong = {}
        for n, pg, y in (("1", None, None), ("1", 156, 560.0), ("1", 156, None),
                         ("2", 156, 560.0), ("2", 155, None), ("2", 156, 100.0),
                         ("3", 156, None), ("3", 156, None)):
            idx._record_pos(n, pg, y)
        self.assertEqual(idx._primary_pos["1"], (156, 560.0))
        self.assertEqual(idx._primary_pos["2"], (155, None))
        self.assertEqual(idx._primary_pos["3"], (156, None))


if __name__ == "__main__":
    unittest.main(verbosity=2)
