# -*- coding: utf-8 -*-
"""Regression: F7f「blockquote 显示式围栏过度缩进」单元级闸（Iwaniec–Kowalski ch4/ch21，2026-09-28）。

写手把长证明里的显示式嵌进引用块时写成 `>    $$`（`>` 后多个空格）。章级 F 层
（`check_katex.py` Pass 1h）判违规，但单元级 `_fence_issues` 先做
`re.sub(r"^\\s*>\\s?", "", raw)` 再 `strip()`——`>    $$` 与 `> $$` 归一后完全相同，
于是本书 88 处（ch4 34 / ch21 54）一路绿过 `gate_units`，直到步骤 6 拼接成整章 md
才被 verify 拦下：返工面从「一个单元」放大到「重拼 + 重验全书」。

锁死：单元级与章级同口径把 `>` 后 2 个以上空白接 `$$` 判违规；单个空格（`> $$`）
与顶层 `$$` 不得误伤。

Runs under stdlib unittest:
  python flows/write-source/script/tests/test_fence_overindent_gate.py
"""
import sys
import unittest
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, str(Path(_ROOT) / "flows" / "write-source" / "script"))

import check_unit_quality as cuq  # noqa: E402

OVER = "over-indented blockquote display math"


def _fence(text):
    return [p for p in cuq._fence_issues(text.split("\n")) if OVER in p]


class TestFenceOverindentGate(unittest.TestCase):
    def test_four_space_indent_caught(self):
        # 实测形态：证明引用块内 `>    $$` 成对出现
        body = "> **Proof.**\n> $$\n\\zeta(s) = \\sum n^{-s}\n>    $$\n> hence.\n"
        self.assertEqual(len(_fence(body)), 1, _fence(body))

    def test_tab_counts_as_indent(self):
        # 与章级 Pass 1h 同式（`^\s*>\s{2,}\$\$`）：`>` 后 2 个以上空白即违规
        self.assertEqual(len(_fence("> $$\nx\n> \t$$\n")), 1)

    def test_single_tab_parity_with_chapter_layer(self):
        # 单个制表符只有 1 个空白，章级 F 层同样不判——两侧口径必须一致，
        # 否则单元闸会在章级放行的形态上误拦（本书实测无此形态）。
        self.assertEqual(_fence("> $$\nx\n>\t$$\n"), [])

    def test_single_space_form_clean(self):
        self.assertEqual(_fence("> **Proof.**\n> $$\nx\n> $$\n"), [])

    def test_top_level_fence_clean(self):
        self.assertEqual(_fence("text\n\n$$\nx\n$$\n\nmore\n"), [])

    def test_unit_gate_fails_on_overindent(self):
        body = ("**Theorem 4.2.**  Statement.\n\n> **Proof.**\n> $$\n"
                "A(x) \\ll x\n>    $$\n> end.\n")
        ok, probs = cuq.check_body("item", "4.2 Statement", body)
        self.assertFalse(ok, probs)
        self.assertTrue(any(OVER in p for p in probs), probs)


if __name__ == "__main__":
    unittest.main(verbosity=2)
