"""O 层带星习题回归（do Carmo ch2 §2-2 实测，2026-09-26）。

背景：do Carmo 把较难题印刷为 `*5. Let …`（行首单星）。旧 `_O_PLAIN_DOT_RE`
不认前导星 → `*5.` 对 O 层隐身，习题表被拆成块 [1,2,3,4] + [6,7,…]，
后段假报 HEAD gap「sequence starts at (6), missing (1..5)」（5 明明印着）。
修复 = plain-dot 模式允许单个前导 `*`（粗体 `**5.**` 仍由 Pattern B 接管）。

断言正反两侧：
  1. `*5. text` 必须被识别为编号 5；
  2. 星号项在位时，其后的续段不得报 HEAD 缺号；
  3. 真缺号（5 确实不存在）仍必须报 HEAD 缺号——放行只认「出现过」。
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

from subitem_continuity import _o_match_line, check_ordinal_subitem_gaps


def _run_gaps(body_lines):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False,
                                     encoding="utf-8") as f:
        f.write("\n".join(body_lines) + "\n")
        path = f.name
    try:
        return check_ordinal_subitem_gaps(path)
    finally:
        os.unlink(path)


class StarredExerciseTest(unittest.TestCase):
    def test_starred_line_matched(self):
        self.assertEqual(_o_match_line("*5. Let $P$ be a plane"), ['5'])
        # 粗体形态不变（由 Pattern B 处理），普通形态不受影响
        self.assertEqual(_o_match_line("**5.** Let"), ['5'])
        self.assertEqual(_o_match_line("5. Let"), ['5'])
        self.assertEqual(_o_match_line("* See previous section"), [])

    def _exercise_table(self, with_star5):
        items = [
            "1. Show that the cylinder is regular.",
            "2. Is the set with boundary regular?",
            "3. Show that the cone is regular.",
            "4. Let $f = z^2$; prove regular value.",
        ]
        if with_star5:
            items.append("*5. Let $P$ be a plane; is x a parametrization?")
        head = ["## §2-2 Regular Surfaces", "", "> **Proof**:", "> 1. step",
                "> 2. step", "> 3. step", "> 4. step", "> 5. step", "", ""]
        tail = ["6. Give another proof of Prop. 1.",
                "7. Let $f(x,y,z)$ be squared linear form.",
                "8. Prove that the graph of a differentiable function is regular.",
                "9. Show that the sphere minus a point is regular."]
        return head + items + [""] * 6 + tail

    def test_starred_item_prevents_false_head_gap(self):
        out = _run_gaps(self._exercise_table(with_star5=True))
        self.assertEqual([o for o in out if "HEAD gap" in o], [],
                         f"带星习题 5 在位仍假报 HEAD 缺号: {out}")

    def test_real_missing_item_still_flagged(self):
        out = _run_gaps(self._exercise_table(with_star5=False))
        self.assertTrue(any("HEAD gap" in o for o in out),
                        "真缺 (5) 必须仍报 HEAD gap（修复不得吞真缺号）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
