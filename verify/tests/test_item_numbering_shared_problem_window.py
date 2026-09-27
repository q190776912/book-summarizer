# -*- coding: utf-8 -*-
"""test_item_numbering_shared_problem_window.py — B 层 `:ex:` 独立窗的形态判据。

Background (Etingof《群表示论》merge_source, 2026-09-27)
-------------------------------------------------------
The book runs ONE chapter-scoped counter over definitions, theorems **and**
problems: "Definition 1.19" is followed by "Problem 1.20".  B layer routed every
Problem label into its own `gi:ex:prefix` window, so the main window counted the
problems as gaps and the exercise window counted the entries as gaps — 58 false
BLOCKING findings in chapter 1 alone, on a chapter whose units/gate were complete.

`exercise_shared_numbering` already exempts Exercise labels; it did not exempt
Problem, because Lee's章末 Problems are numbered "1-1" (dash form) and *must*
keep a separate window or they collide with Theorem 1.1.  The discriminator is
therefore the **shape of the ordinal**, not the label: a dotted ordinal (1.20) is
the same shape as the entries and stays in the main window.

Run:  python verify/tests/test_item_numbering_shared_problem_window.py
"""
import os
import sys
import tempfile
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

from verify_config import BookConfig, GroupConfig          # noqa: E402
from item_numbering_integrity import _md_gap_blocking      # noqa: E402
from verify.script.base import VerifyContext               # noqa: E402


MD_DOTTED = (
    "# Chapter 1\n\n"
    "**Definition 1.1.** first.\n\n"
    "**Definition 1.2.** second.\n\n"
    "**Problem 1.3.** third.\n\n"
    "**Definition 1.4.** fourth.\n\n"
    "**Problem 1.5.** fifth.\n\n"
)


def _ctx(md_text, shared):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "chapter1.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(md_text)
    cfg = BookConfig(
        ordinal=[GroupConfig(type=2, name=["Definition", "Theorem", "Problem"],
                             scope=2)],
        exercise_shared_numbering=shared,
    )
    return VerifyContext(ch=1, start=1, end=1, md_file=p, ext_dir=d, config=cfg)


class SharedCounterDottedProblem(unittest.TestCase):
    def test_dotted_problem_stays_in_main_window(self):
        """点号 Problem 与条目同形 → 并入主窗，1..5 完整无缺号。"""
        blocking, _w, _p, _t, _g = _md_gap_blocking(_ctx(MD_DOTTED, True))
        self.assertEqual(blocking, [], "false gaps: %s" % blocking)

    def test_flag_off_still_opens_exercise_window(self):
        """负向对照：未声明共享计数器的书必须照旧独立开窗（Lee/Katok 保护）。

        1..5 是一条完整序列，但开窗后主窗只见 1,2,4（缺 3）、练习窗只见 3,5
        （缺 4）——两窗各报一条假缺号，正是本次要根治的形态。
        """
        blocking, _w, _p, _t, _g = _md_gap_blocking(_ctx(MD_DOTTED, False))
        text = "\n".join(blocking)
        self.assertIn(":ex:", text, "Problem 必须仍被切进练习窗")
        self.assertIn("缺号 3", text)
        self.assertIn("缺号 4", text)

    def test_real_gap_still_flagged_with_shared_counter(self):
        """收紧后不得失去检出力：真缺号（1.4 缺失）仍须 BLOCKING。"""
        md = MD_DOTTED.replace("**Definition 1.4.** fourth.\n\n", "")
        blocking, _w, _p, _t, _g = _md_gap_blocking(_ctx(md, True))
        self.assertIn("缺号 4", "\n".join(blocking))


if __name__ == "__main__":
    unittest.main(verbosity=2)
