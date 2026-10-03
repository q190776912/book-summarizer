# -*- coding: utf-8 -*-
"""test_group_name_no_default.py — ordinal 组 `name` **无默认值**回归（2026-10-01）。

用户诉求（与 `type` / `scope` / `formula.scope` 同一原则）：**所有配置不应有默认值**，
本组计数器要匹配的条目标签集合（`name`）必须从书中确定；无法确定的交由 agent 确定。
据此落死加载期硬校验（`BookConfig.from_dict`）：

1. 声明了**真实编号体例**（type != 0）的组必须显式带**非空**字符串数组 `name`；缺
   `name` / 空数组 / 非数组一律 `ConfigError`——绝不再悄悄回落 `["uncat"]`。省略 name
   会被当成通用兜底桶，等于伪造「本组不匹配任何具名标签」这一体例事实。
2. 显式写通用桶 `["uncat"]` 是**允许**的（作者的真实决策），但必须写出来。
3. `type 0`（UNNUMBERED，无编号）组 name 无语义，**允许省略**（占位 `["uncat"]`，
   与 scope 对 type 0 的豁免对称）；但一旦写了就必须是**非空**字符串数组。
4. `dataclass` 的 `GroupConfig.name` 默认 `["uncat"]` 仅覆盖程序化构造，**不是**加载默认。

运行：
  python -m pytest config/verify_config/tests/test_group_name_no_default.py -q
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

from verify_config import BookConfig, ConfigError, GroupConfig  # noqa: E402


class LoadTimeGroupNameValidation(unittest.TestCase):
    """`BookConfig.from_dict`：真实体例组必带合法非空 name，否则硬报错。"""

    def test_real_type_without_name_rejected(self):
        for t in (1, 2, 3, 8, 12, 13, 14):
            with self.assertRaises(ConfigError, msg="type=%d 缺 name 应被拒" % t):
                BookConfig.from_dict({"ordinal": [{"type": t, "scope": 2}]})

    def test_real_type_empty_name_rejected(self):
        # 空数组曾被旧代码 `g.get('name') or ["uncat"]` 静默当成 uncat——现在禁止。
        for t in (1, 2, 3):
            with self.assertRaises(ConfigError, msg="type=%d name=[] 应被拒" % t):
                BookConfig.from_dict({"ordinal": [{"type": t, "name": [], "scope": 2}]})

    def test_real_type_non_list_name_rejected(self):
        for bad in ("定理", 5, {"a": 1}):
            with self.assertRaises(ConfigError, msg="name=%r 应被拒" % bad):
                BookConfig.from_dict({"ordinal": [{"type": 3, "name": bad, "scope": 2}]})

    def test_real_type_non_string_elements_rejected(self):
        with self.assertRaises(ConfigError):
            BookConfig.from_dict({"ordinal": [{"type": 3, "name": [1, 2], "scope": 2}]})

    def test_valid_names_accepted(self):
        for good in (["定理"], ["定理", "引理"], ["uncat"], ["Definition", "Theorem"]):
            cfg = BookConfig.from_dict(
                {"ordinal": [{"type": 3, "name": good, "scope": 2}]})
            self.assertEqual(cfg.ordinal[0].name, good)

    def test_explicit_uncat_bucket_is_allowed(self):
        # 通用兜底桶作为**显式**声明被接受（真实决策，非缺省）。
        cfg = BookConfig.from_dict(
            {"ordinal": [{"type": 3, "name": ["uncat"], "scope": 2}]})
        self.assertTrue(cfg.ordinal[0].is_uncat)

    def test_missing_name_error_mentions_no_default(self):
        with self.assertRaises(ConfigError) as ctx:
            BookConfig.from_dict({"ordinal": [{"type": 3, "scope": 2}]})
        msg = str(ctx.exception)
        self.assertIn("name", msg)
        self.assertTrue("无默认值" in msg or "no-default" in msg,
                        "错误文案须点明 no-default：%r" % msg)

    def test_type0_may_omit_name(self):
        # UNNUMBERED（type 0）name 无语义，允许省略（占位 uncat）。
        cfg = BookConfig.from_dict({"ordinal": [{"type": 0, "scope": 2}]})
        self.assertEqual(cfg.ordinal[0].type, 0)
        self.assertEqual(cfg.ordinal[0].name, ["uncat"])

    def test_type0_with_explicit_name_still_ok(self):
        cfg = BookConfig.from_dict(
            {"ordinal": [{"type": 0, "name": ["Figure"], "scope": 2}]})
        self.assertEqual(cfg.ordinal[0].name, ["Figure"])

    def test_type0_with_empty_name_rejected(self):
        # 省略可以，但一旦写了就必须是非空字符串数组。
        with self.assertRaises(ConfigError):
            BookConfig.from_dict({"ordinal": [{"type": 0, "name": [], "scope": 2}]})
        with self.assertRaises(ConfigError):
            BookConfig.from_dict({"ordinal": [{"type": 0, "name": "Figure"}]})

    def test_mixed_groups_each_independently_validated(self):
        # 多组：任一带真实 type 却缺 name → 整体硬报错。
        with self.assertRaises(ConfigError):
            BookConfig.from_dict({"ordinal": [
                {"type": 3, "name": ["定理"], "scope": 2},
                {"type": 2, "scope": 3},        # 缺 name → 报错
            ]})
        # 全合法则通过，各组 name 独立保留。
        cfg = BookConfig.from_dict({"ordinal": [
            {"type": 3, "name": ["定理"], "scope": 2},
            {"type": 2, "name": ["例"], "scope": 3},
            {"type": 0},                        # type0 允许省略 name
        ]})
        self.assertEqual([g.name for g in cfg.ordinal],
                         [["定理"], ["例"], ["uncat"]])

    def test_absent_ordinal_is_type0_uncat_no_error(self):
        # 无 ordinal → 单条 UNNUMBERED(type0) uncat 回退，不强制 name（内部构造）。
        cfg = BookConfig.from_dict({})
        self.assertEqual(len(cfg.ordinal), 1)
        self.assertEqual(cfg.ordinal[0].type, 0)
        self.assertEqual(cfg.ordinal[0].name, ["uncat"])

    def test_dataclass_default_is_programmatic_only(self):
        # GroupConfig(...) 直接构造仍吃 dataclass 默认 ["uncat"]——它不是加载默认。
        g = GroupConfig(type=3, scope=2)
        self.assertEqual(g.name, ["uncat"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
