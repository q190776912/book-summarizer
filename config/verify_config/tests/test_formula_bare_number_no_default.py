# -*- coding: utf-8 -*-
"""test_formula_bare_number_no_default.py — `formula.bare_number` **无默认值**回归
（2026-10-01，用户裁定：所有配置字段不得静默兜底）。

背景：`bare_number` 决定 Q 层是否把正文里裸 `N.M` 也当公式号收录，直接改变公式
抽取结果。旧「默认 true」＝静默兜底，对「公式号一律带括号 / 满是裸号交叉引用」
的书（Lee / Apostol 型）会批量造出幻影 MISSING（Apostol ch10 实测 176 条），
故一律禁止默认。

落死的分层原则（与 strict/chapter_first/section_scoped/language 同则）：

1. **加载期 `from_dict` 保持宽容**：程序化 / 测试构造的 formula map 常省略
   bare_number，放 from_dict 会误伤它们。故本字段**不在** from_dict 强制——
   `BookConfig.from_dict({... formula:{type,scope} ...})` 缺 bare_number 仍须
   成功构造（本文件有专门用例锁死这一点）。
2. **完整性门 `require_complete` 每段强制**（body `ch` 与 appendix/supplement
   一律）：凡 formula **声明了 type**（即选定体例、开启 Q 层）就**必须显式带布尔**
   `bare_number`；缺 → `ConfigError`（no-default）；非 bool → `ConfigError`。
   判据是「key 在不在场」（`cfg.formula` 原样存 raw dict），故显式 `false` 也
   通过。只含 `ignore` / `known_book` 而无 `type` 的**登记式**残块不选体例、豁免。
3. `make_config` 从此为每个带 type 的 formula 段无条件播种 bare_number
   （旧登记值优先回贴），故 `--force` 重生成恒通过；存量未回填的真实书被本门挡下,
   正是提示其补定。

运行：
  python -m pytest config/verify_config/tests/test_formula_bare_number_no_default.py -q
"""
import os
import sys
import json
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

from verify_config import BookConfig, ConfigLoader, ConfigError  # noqa: E402


def _ext_loader(cfg):
    """Write `cfg` as verify_config.json (+ completion marker) into a fresh temp
    extract dir and return a ConfigLoader over it (extract_dir == book_dir).

    The marker is required by ConfigLoader's upstream flow_gate; these tests
    target require_complete semantics only."""
    ext = tempfile.mkdtemp(prefix="bn_ext_")
    with open(os.path.join(ext, "verify_config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    with open(os.path.join(ext, "_extraction_done.json"), "w", encoding="utf-8") as f:
        json.dump({"done": True}, f)
    return ConfigLoader(ext, ext, extra_ignore=None)


# A complete flat MAIN body (passes type/scope/name + the four required main
# fields) with NO formula block at all — the safe baseline every formula test
# is built on top of by injecting a `formula` key.
def _main_body(**extra):
    cfg = {
        "ordinal": [{"type": 3, "name": ["uncat"], "scope": 2}],
        "strict": True,
        "chapter_first": True,
        "section_scoped": False,
        "language": "cn",
    }
    cfg.update(extra)
    return cfg


class TestFromDictStaysTolerant(unittest.TestCase):
    """`formula.bare_number` must NOT be enforced at load time (`from_dict`)."""

    def test_from_dict_accepts_formula_type_without_bare_number(self):
        # Programmatic / test configs routinely omit bare_number; from_dict
        # stays tolerant so they keep constructing (enforcement is at
        # require_complete). scope is required at from_dict, so include it.
        cfg = BookConfig.from_dict(_main_body(formula={"type": 2, "scope": 2}))
        self.assertIsNotNone(cfg.formula)
        self.assertNotIn("bare_number", cfg.formula)


class TestRequireCompleteBareNumber(unittest.TestCase):
    """`require_complete` per-segment gate on `bare_number`."""

    def test_formula_type_present_but_bare_number_absent_raises(self):
        loader = _ext_loader(_main_body(formula={"type": 2, "scope": 2}))
        with self.assertRaises(ConfigError) as ctx:
            loader.require_complete()
        msg = str(ctx.exception)
        self.assertIn("bare_number", msg)
        self.assertTrue("无默认值" in msg or "no-default" in msg,
                        "错误文案须点明 no-default：%r" % msg)

    def test_explicit_bare_number_true_passes(self):
        loader = _ext_loader(
            _main_body(formula={"type": 2, "scope": 2, "bare_number": True}))
        loader.require_complete()  # must not raise

    def test_explicit_bare_number_false_passes(self):
        # KEY: absence is decided by KEY presence, not value — explicit false
        # is a legitimate operator decision (Lee/Apostol-style books) and must
        # NOT be treated as missing.
        loader = _ext_loader(
            _main_body(formula={"type": 2, "scope": 2, "bare_number": False}))
        loader.require_complete()  # must not raise

    def test_bare_number_non_bool_int_raises(self):
        loader = _ext_loader(
            _main_body(formula={"type": 2, "scope": 2, "bare_number": 1}))
        with self.assertRaises(ConfigError) as ctx:
            loader.require_complete()
        self.assertIn("bare_number", str(ctx.exception))

    def test_bare_number_non_bool_string_raises(self):
        loader = _ext_loader(
            _main_body(formula={"type": 2, "scope": 2, "bare_number": "true"}))
        with self.assertRaises(ConfigError):
            loader.require_complete()

    def test_registration_only_formula_without_type_is_exempt(self):
        # A formula ledger chunk carrying only ignore/known_book (NO type)
        # selects no numbering scheme -> opens no Q layer -> exempt from the
        # bare_number requirement (must not be blocked as "missing field").
        loader = _ext_loader(
            _main_body(formula={"ignore": ["3.1"], "known_book": ["2.17"]}))
        loader.require_complete()  # must not raise

    def test_no_formula_block_is_exempt(self):
        loader = _ext_loader(_main_body())
        loader.require_complete()  # must not raise (formula absent entirely)


class TestAppendixSupplementSegments(unittest.TestCase):
    """Outer-map format: the bare_number gate applies to EVERY segment, not
    just the main body (appendix/supplement are optional overrides but a
    formula-with-type there is still a formula with a real scheme)."""

    def test_appendix_segment_formula_type_missing_bare_number_raises(self):
        cfg = {
            "ch": _main_body(),  # complete body, no formula -> exempt
            "appendix": {
                "ordinal": [{"type": 3, "name": ["uncat"], "scope": 2}],
                "formula": {"type": 2, "scope": 2},  # no bare_number
            },
        }
        loader = _ext_loader(cfg)
        with self.assertRaises(ConfigError) as ctx:
            loader.require_complete()
        self.assertIn("bare_number", str(ctx.exception))

    def test_appendix_segment_formula_with_bare_number_passes(self):
        cfg = {
            "ch": _main_body(),
            "appendix": {
                "ordinal": [{"type": 3, "name": ["uncat"], "scope": 2}],
                "formula": {"type": 2, "scope": 2, "bare_number": True},
            },
        }
        loader = _ext_loader(cfg)
        loader.require_complete()  # must not raise

    def test_supplement_segment_formula_type_missing_bare_number_raises(self):
        cfg = {
            "ch": _main_body(),
            "supplement": {
                "ordinal": [{"type": 3, "name": ["uncat"], "scope": 2}],
                "formula": {"type": 2, "scope": 2},
            },
        }
        loader = _ext_loader(cfg)
        with self.assertRaises(ConfigError) as ctx:
            loader.require_complete()
        self.assertIn("bare_number", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
