# -*- coding: utf-8 -*-
"""`_plausible` 的算术演算串守卫（2026-10《概率论与数理统计教程》根治）。

事故实测：统计课本例题里 OCR 把带括号的小数减法 / 乘法整块读成一个 token——
`(239.5-240)`、`(1-0.8)`、`(101-104.25)`、`(315-312.75)`——而 `norm()` 把 `-`
折成分隔符，于是伪造成一枚「多段编号」`239.5.240` / `1.0.8` / `101.104.25` 注入
书源集合 S。MISSING 硬闸反过来要求总结凭空补 `\tag{239.5.240}`（假阳），运维只能
逐号塞 `formula.ignore`（症状补丁）。根因在检测器，故在 `_plausible` 这一 S 成员
唯一闸口集中拦截。

本测试钉两条守卫（G1 首分量 ≥3 位；G2 dash 之后再现分隔符 = 减法式），并**反向
钉住**：真印刷号——连字符体例 `11.1-1` / `8.5-2`、点体例 `1.1.1` / `1.2.10`、
大 item 尾号 `5.120`、含中段 0 的 `1.5.0.1`——一律放过（关掉守卫即误杀，即回归）。
"""
import os
import sys
import unittest

_ROOT = os.environ.get("SKILL_ROOT") or os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "lib"))
import lib.boot as _boot
_boot.setup()

from formula_tag import SourceFormulaIndex  # noqa: E402
from formula_tag import build_formula_patterns  # noqa: E402

_plausible = SourceFormulaIndex._plausible
_norm = SourceFormulaIndex.norm


class TestArithmeticGuard(unittest.TestCase):
    def test_artifacts_rejected(self):
        # (norm(raw), raw) —— 全是印面演算串，绝不该进 S。
        cases = [
            ("239.5.240", "239.5-240"),     # G1 首分量 239
            ("101.104.25", "101-104.25"),   # G1 + G2
            ("108.104.25", "108-104.25"),
            ("315.312.75", "315-312.75"),
            ("1.0.8", "1-0.8"),              # G2：dash 后有 dot
            ("1.0.9", "1-0.9"),
        ]
        for n, raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual(_norm("(" + raw + ")"), n)
                self.assertFalse(_plausible(n, raw),
                                 f"演算串 {raw!r} 仍被当成编号放进 S")

    def test_genuine_labels_kept(self):
        # 关掉守卫就会误杀这些真号 → 本组是反向钉。
        cases = [
            ("1.1.1", "1.1.1"),
            ("1.2.10", "1.2.10"),
            ("11.1.1", "11.1-1"),    # 连字符为末段分隔（点在前 dash 在后）
            ("8.5.2", "8.5-2"),
            ("5.1.20", "5.1.20"),
            ("2.5.12", "2.5.12"),
            ("1.5.0.1", "1.5.0.1"),  # 中段 0（Vakil 定义第 0 项）
            ("13.6.5", "13.6-5"),
        ]
        for n, raw in cases:
            with self.subTest(raw=raw):
                self.assertTrue(_plausible(n, raw),
                                f"真号 {raw!r} 被守卫误杀")

    def test_single_component_large_still_rejected(self):
        # 既有语义：单段 >99（页码/OCR 噪声）照旧拒。
        self.assertFalse(_plausible("146", "146"))
        self.assertTrue(_plausible("96", "96"))

    def test_large_item_number_in_trailing_component_survives(self):
        # 🔴 安全性关键：首分量小、末分量 3 位（章节号小、item 号大）绝不能被 G1 杀。
        #    若某书 (5.120) = 第5章第120式，必须留在 S。
        self.assertTrue(_plausible("5.120", "5.120"))
        self.assertTrue(_plausible("2.3.245", "2.3.245"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
