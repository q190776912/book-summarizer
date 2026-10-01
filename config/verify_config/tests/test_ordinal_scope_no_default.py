# -*- coding: utf-8 -*-
"""test_ordinal_scope_no_default.py — ordinal 组 `scope` **无默认值**回归（2026-10-01）。

用户诉求（与 formula.scope 同一原则）：**所有配置不应有默认值**，编号重置窗口
（scope）必须从书中确定；无法确定的交由 agent 确定。据此落死加载期硬校验
（`BookConfig.from_dict`）：

1. 声明了**真实编号体例**（type != 0）的组必须显式带 `scope∈{1,2,3}`；缺 `scope` /
   非法（越界、非整数）一律 `ConfigError`——绝不再悄悄回落 SCOPE_CHAPTER。
   跨章/跨节计数器窗口设错会造成串号假缺号，故不允许默认。
2. `type 0`（UNNUMBERED，无编号）组的 scope 无语义（永不参与重置）：**允许省略**，
   但显式写了就照常校验（写了非法值仍报错）。
3. 加载期是唯一权威闸门；`make_config.py` 每条 ordinal 生成分支都**显式写 scope**，
   故 `--force` 重生成产出的配置必可通过本校验（账本保真 + `_repaste_old_scopes`
   只覆写不删）。

运行：
  python -m pytest config/verify_config/tests/test_ordinal_scope_no_default.py -q
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

from verify_config import BookConfig, ConfigError   # noqa: E402


class LoadTimeOrdinalScopeValidation(unittest.TestCase):
    """`BookConfig.from_dict`：真实体例组必带合法 scope，否则硬报错。"""

    def test_real_type_without_scope_rejected(self):
        for t in (1, 2, 3, 8, 12, 13, 14):
            with self.assertRaises(ConfigError, msg="type=%d 缺 scope 应被拒" % t):
                BookConfig.from_dict({"ordinal": [{"type": t, "name": ["uncat"]}]})

    def test_scope_out_of_range_rejected(self):
        for bad in (0, 4, -1):
            with self.assertRaises(ConfigError, msg="scope=%r 应被拒" % bad):
                BookConfig.from_dict(
                    {"ordinal": [{"type": 2, "name": ["uncat"], "scope": bad}]})

    def test_scope_non_integer_rejected(self):
        for bad in ("chapter", None, "2.5"):
            with self.assertRaises(ConfigError, msg="scope=%r 应被拒" % bad):
                BookConfig.from_dict(
                    {"ordinal": [{"type": 2, "name": ["uncat"], "scope": bad}]})

    def test_valid_scopes_accepted(self):
        for good in (1, 2, 3):
            cfg = BookConfig.from_dict(
                {"ordinal": [{"type": 2, "name": ["uncat"], "scope": good}]})
            self.assertEqual(cfg.ordinal[0].scope, good)

    def test_missing_scope_error_mentions_no_default(self):
        with self.assertRaises(ConfigError) as ctx:
            BookConfig.from_dict({"ordinal": [{"type": 3, "name": ["定理"]}]})
        msg = str(ctx.exception)
        self.assertIn("scope", msg)
        self.assertTrue("无默认值" in msg or "no-default" in msg,
                        "错误文案须点明 no-default：%r" % msg)

    def test_type0_may_omit_scope(self):
        # UNNUMBERED（type 0）scope 无语义，允许省略（给一个不被读到的占位值）。
        cfg = BookConfig.from_dict({"ordinal": [{"type": 0, "name": ["Figure"]}]})
        self.assertEqual(cfg.ordinal[0].type, 0)
        # scope 落在合法集合内（占位），不影响任何计数逻辑。
        self.assertIn(cfg.ordinal[0].scope, (1, 2, 3))

    def test_type0_with_valid_scope_still_ok(self):
        for good in (1, 2, 3):
            cfg = BookConfig.from_dict(
                {"ordinal": [{"type": 0, "name": ["Figure"], "scope": good}]})
            self.assertEqual(cfg.ordinal[0].scope, good)

    def test_type0_with_explicit_bad_scope_rejected(self):
        # 省略可以，但一旦写了就必须合法（写了越界/非整数仍报错）。
        with self.assertRaises(ConfigError):
            BookConfig.from_dict(
                {"ordinal": [{"type": 0, "name": ["Figure"], "scope": 9}]})
        with self.assertRaises(ConfigError):
            BookConfig.from_dict(
                {"ordinal": [{"type": 0, "name": ["Figure"], "scope": "x"}]})

    def test_mixed_groups_each_independently_validated(self):
        # 多组：只要有任一带真实 type 却缺 scope，整体硬报错。
        with self.assertRaises(ConfigError):
            BookConfig.from_dict({"ordinal": [
                {"type": 3, "name": ["定理"], "scope": 2},
                {"type": 2, "name": ["例"]},        # 缺 scope → 报错
            ]})
        # 全合法则通过，各组 scope 独立保留。
        cfg = BookConfig.from_dict({"ordinal": [
            {"type": 3, "name": ["定理"], "scope": 2},
            {"type": 2, "name": ["例"], "scope": 3},
            {"type": 0, "name": ["Figure"]},        # type0 允许省略
        ]})
        self.assertEqual([g.scope for g in cfg.ordinal], [2, 3, cfg.ordinal[2].scope])

    def test_absent_ordinal_is_type0_no_error(self):
        # 无 ordinal → 单条 UNNUMBERED(type0) uncat 回退，不强制 scope（内部构造）。
        cfg = BookConfig.from_dict({})
        self.assertEqual(len(cfg.ordinal), 1)
        self.assertEqual(cfg.ordinal[0].type, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
