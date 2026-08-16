"""Regression tests for the `_group_headings_by_counter` fix in
``config/verify_config/make_config.py`` (book-summarizer, 2026-08-16).

Background
----------
The function was previously hard-coding ``MAIN_CANONS`` to FORCE-merge every
"main" entry-type family (Definition/Theorem/Lemma/Corollary/Proposition/
Example/Axiom) into a single primary group.  That produced a WRONG single
merged counter for books whose main types are independently numbered (e.g.
Koopman Operator).

The fix removes the hard-coded rule and instead:
  * clusters every detected type family by its canon (via ``_FORM_CANON``),
  * selects the reference counter (see Round-2 note below),
  * merges a family into the primary group only when
    ``_shares_main_counter(data["comps"], ref_comps)`` returns True (i.e. it
    actually re-uses/shares the same ascending counter), otherwise gives it
    its OWN group.

Round 2 (from-1 fallback) — 2026-08-16 hardening
------------------------------------------------
Reference-counter selection defaults to the family with the MOST detected
headings.  That is correct for the common case (and for independently-numbered
books like Koopman -> 8 separate groups).  BUT when that most-frequent family
does NOT start at 1 it cannot be the TRUE primary of a shared ascending chain:
a sibling that legitimately resets to 1 (Definition 6.1 in a
Definition 6.1 / Theorem 6.2 / Lemma 6.8 chain) would then be mis-split into
its own group.  So when the most-frequent family's counter min != 1, selection
falls back to the family that BEGINS at 1 and has the LARGEST span (the full
1..N primary), instead of a mid-chain fragment.  The fallback is applied ONLY
when the default reference fails to start at 1 (unconditionally preferring a
from-1 family would change the reference for normally-numbered books and cause
spurious merges such as Koopman's Corollary/Problem).

These tests prove the fix produces the correct grouping for four scenarios
(Cases A-D) plus an edge case.  Case D specifically guards the Round-2 from-1
fallback: with the fallback it merges Theorem+Definition+Lemma into ONE group;
on the pre-Round-2 code the most-frequent (non-1) family becomes the reference
and Definition (starting at 1) is WRONGLY split off into its own group -> 2
groups.  They import ONLY the function under test; they do NOT modify any
business logic in make_config.py.

Run
---
    python config/verify_config/tests/test_group_heading_clustering.py
        (or)
    python -m unittest config.verify_config.tests.test_group_heading_clustering -v

The script auto-locates the skill root via ``SKILL.md`` so it runs from any cwd.
"""
import os
import sys
import unittest
from pathlib import Path

# --- robust skill-root resolution (no dependency on cwd) ---
_THIS = Path(__file__).resolve()
_ROOT = None
for _c in _THIS.parents:
    if (_c / "SKILL.md").exists():
        _ROOT = _c
        break
if _ROOT is None:
    # fallback: tests live at <root>/config/verify_config/tests -> 3 levels up
    _ROOT = _THIS.parents[3]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from config.verify_config.make_config import _group_headings_by_counter  # noqa: E402


# --- helpers ----------------------------------------------------------------
def _all_names(groups):
    """Flatten the returned groups (list of form-lists) into a name set."""
    names = set()
    for g in groups:
        for f in g:
            names.add(f)
    return names


def _group_containing(groups, form):
    """Return the single group that contains ``form`` (or None)."""
    for g in groups:
        if form in g:
            return g
    return None


# --- 用例 A: Koopman 式「各主类型独立编号」 -> 多个独立 group ----------
def _headings_koopman_independent():
    h = []
    for n in (1, 2, 3, 4, 5):
        h.append((0, "Definition", (1, n)))
    for n in (1, 2, 3):
        h.append((0, "Proposition", (1, n)))
    for n in (1, 2, 3, 4, 5, 6, 7):
        h.append((0, "Example", (1, n)))
    h.append((0, "Remark", (1, 1)))
    return h


# --- 用例 B: 合并计数器书 -> 单一 group --------------------------------
def _headings_merged_counter():
    # One ascending chain 1,2,3,4,5,6,7,8 shared by Definition/Theorem/Lemma.
    # Definition listed first so it is the reference counter (most entries).
    return [
        (0, "Definition", (1, 1)),
        (0, "Definition", (1, 3)),
        (0, "Definition", (1, 5)),
        (0, "Theorem", (1, 2)),
        (0, "Theorem", (1, 4)),
        (0, "Theorem", (1, 6)),
        (0, "Lemma", (1, 7)),
        (0, "Lemma", (1, 8)),
    ]


# --- 用例 C: 混合 — 主类型共享 + Remark 独立重排 -----------------------
def _headings_mixed_shared_and_remark():
    # Definition 1,2 + Theorem 3,4 share one ascending chain;
    # Remark resets to 1 -> independent counter.
    # Definition listed first so it is the reference counter (most entries).
    return [
        (0, "Definition", (1, 1)),
        (0, "Definition", (1, 2)),
        (0, "Theorem", (1, 3)),
        (0, "Theorem", (1, 4)),
        (0, "Remark", (1, 1)),
    ]


# --- 用例 D: Round-2 from-1 回退 —— 合并计数器书，但「频次最高」的类型不从 1 起始 ---
def _headings_round2_from1_fallback():
    # 单个 scope 窗口（第 6 章）内共享同一条升序链：6.1 .. 6.8。
    #   Theorem   : (6,2),(6,3),(6,4),(6,5),(6,6) -> 5 条（频次最高），min=2（不从 1 起始）
    #   Definition: (6,1),(6,7)                   -> min=1, max=7（从 1 起始、跨度最大 = 真正主类型）
    #   Lemma     : (6,8)                         -> 共享链尾
    # 期望（Round-2 代码）：from-1 回退选中 Definition 作参考，Theorem/Lemma 仍共享计数器
    #   -> 全部合并为 1 个 group {Theorem, Definition, Lemma}。
    # 旧版（无回退）：参考=频次最高的 Theorem（min=2），Definition 因从 1 重置被判为独立
    #   -> 错误拆成 2 个 group。本用例即为此回归守卫。
    return [
        (0, "Theorem", (6, 2)),
        (0, "Theorem", (6, 3)),
        (0, "Theorem", (6, 4)),
        (0, "Theorem", (6, 5)),
        (0, "Theorem", (6, 6)),
        (0, "Definition", (6, 1)),
        (0, "Definition", (6, 7)),
        (0, "Lemma", (6, 8)),
    ]


class TestGroupHeadingsByCounter(unittest.TestCase):

    def test_case_a_koopman_independent_numbering(self):
        """Every main type is independently numbered -> 4 SEPARATE single-type
        groups (no forced merge)."""
        groups = _group_headings_by_counter(_headings_koopman_independent(), depth=2)

        self.assertEqual(len(groups), 4,
                         f"期望 4 个独立 group，实际 {len(groups)}: {groups}")
        # 每个 group 都是单一类型（name 长度为 1）
        for g in groups:
            self.assertEqual(len(g), 1,
                             f"存在被强制合并的 group（name 长度应为 1）: {g}")
        expected = {"Definition", "Proposition", "Example", "Remark"}
        self.assertEqual(_all_names(groups), expected,
                         f"group 的 name 集合应为 {expected}，实际 {_all_names(groups)}")

    def test_case_b_merged_counter_single_group(self):
        """Definition/Theorem/Lemma share ONE ascending counter -> 1 group."""
        groups = _group_headings_by_counter(_headings_merged_counter(), depth=2)

        self.assertEqual(len(groups), 1,
                         f"合并计数器书应只有 1 个 group，实际 {len(groups)}: {groups}")
        self.assertEqual(len(groups[0]), 3,
                         f"唯一 group 应含 3 个类型，实际 {groups[0]}")
        self.assertEqual(set(groups[0]), {"Definition", "Theorem", "Lemma"},
                         f"唯一 group 的 name 集合不符: {groups[0]}")

    def test_case_c_mixed_shared_plus_independent_remark(self):
        """Definition+Theorem share a counter (1 group); Remark resets to 1 and
        must get its OWN group. So 2 groups total."""
        groups = _group_headings_by_counter(_headings_mixed_shared_and_remark(), depth=2)

        self.assertEqual(len(groups), 2,
                         f"混合场景应返回 2 个 group，实际 {len(groups)}: {groups}")

        remark_g = _group_containing(groups, "Remark")
        self.assertIsNotNone(remark_g, "未找到含 Remark 的 group")
        self.assertEqual(remark_g, ["Remark"],
                         f"Remark 应独占一个 group，实际 {remark_g}")

        dt_g = _group_containing_def_and_thm = [g for g in groups
                                                if "Definition" in g and "Theorem" in g]
        self.assertEqual(len(dt_g), 1,
                         "Definition 与 Theorem 应在同一 group 内")
        # Remark 不能与 Definition/Theorem 合并
        self.assertNotIn("Remark", dt_g[0],
                         "Remark 不应与 Definition+Theorem 合并")

    def test_case_d_round2_from1_fallback(self):
        """Round-2 from-1 fallback guard.

        A merged-counter book where the MOST-frequent family (Theorem, 5
        entries) does NOT start at 1, while a sibling (Definition) starts at 1
        and spans the full chain.  With the fallback the from-1 family becomes
        the reference and EVERYTHING shares one counter -> 1 group.  On the
        pre-Round-2 code the reference would be Theorem (min=2) and Definition
        (resetting to 1) would be wrongly split off -> 2 groups.
        """
        groups = _group_headings_by_counter(_headings_round2_from1_fallback(), depth=2)

        self.assertEqual(len(groups), 1,
                         f"Round-2 回退后应为 1 个 group，实际 {len(groups)}: {groups}")

        # Theorem 与 Definition 必须在同一 group（共享计数器）
        dt_g = [g for g in groups if "Theorem" in g and "Definition" in g]
        self.assertEqual(len(dt_g), 1,
                         "Theorem 与 Definition 应在同一 group 内（共享计数器）")
        # 该 group 应同时含 Lemma（也共享同链）
        self.assertIn("Lemma", dt_g[0], "Lemma 也应并入合并后的 group")

    def test_edge_empty_headings(self):
        """防御性：空输入应安全返回单兜底 group，而非抛异常。"""
        groups = _group_headings_by_counter([], depth=2)
        self.assertEqual(groups, [["uncat"]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
