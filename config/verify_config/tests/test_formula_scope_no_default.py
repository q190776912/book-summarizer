# -*- coding: utf-8 -*-
"""test_formula_scope_no_default.py — 公式 `scope` **无默认值**回归（2026-10-01）。

用户诉求：文档旧写法把 `formula.scope` 说成「默认 2」是错的——**所有配置不应有默认值**，
scope 必须从书中确定；无法确定的交由 agent 确定。据此落死三层保证：

1. **加载期硬校验**（`BookConfig.from_dict`）：只要 `formula` 声明了 `type`，就必须显式
   带 `scope∈{1,2,3}`；缺 `scope` / 非法（越界、非整数）一律 `ConfigError`。这是唯一的
   权威闸门——`gate_units._is_formula_map` 的启用探测只认 `type`，不受影响。
   例外：**登记式**残块（只有 `known_book`/`ignore`、无 `type`）不强制 scope（噪声账本）。
2. **消费侧去静默默认**（`formula_tag.QLayer.run`）：`formula` 有 `type` 却缺 `scope` →
   硬报错，绝不悄悄按 scope=2 跑章级守卫。
3. **探测从书证派生**（`make_config.detect_formula`）：两级数字 `(C.N)` 的 scope 由**首分量
   重置证据**派生（逐章重启→2 / 全书连续→1）；整书仅见单一首分量（无从观测重置）时
   **省略 scope**，交 agent 依书补定——不再有写死的 `scope:2`。

运行：
  python -m pytest config/verify_config/tests/test_formula_scope_no_default.py -q
"""
import os
import sys
import json
import tempfile
import subprocess
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

from verify_config import BookConfig, ConfigError                     # noqa: E402


def _base(**over):
    """一份合法 ordinal + 传入 formula 的 config dict。"""
    d = {"ordinal": [{"type": 2, "name": ["uncat"], "scope": 2}]}
    d.update(over)
    return d


class LoadTimeScopeValidation(unittest.TestCase):
    """`BookConfig.from_dict`：formula 有 type 必带合法 scope，否则硬报错。"""

    def test_type_without_scope_rejected(self):
        with self.assertRaises(ConfigError):
            BookConfig.from_dict(_base(formula={"type": 2, "ignore": []}))

    def test_scope_out_of_range_rejected(self):
        for bad in (0, 4, -1):
            with self.assertRaises(ConfigError, msg="scope=%r 应被拒" % bad):
                BookConfig.from_dict(_base(formula={"type": 2, "scope": bad}))

    def test_scope_non_integer_rejected(self):
        with self.assertRaises(ConfigError):
            BookConfig.from_dict(_base(formula={"type": 2, "scope": "chapter"}))
        with self.assertRaises(ConfigError):
            BookConfig.from_dict(_base(formula={"type": 2, "scope": None}))

    def test_valid_scopes_accepted(self):
        for good in (1, 2, 3):
            cfg = BookConfig.from_dict(
                _base(formula={"type": 2, "scope": good, "ignore": []}))
            self.assertEqual(cfg.formula["scope"], good)

    def test_alpha_only_codes_still_need_scope(self):
        # formula-only 字母码 15 / 罗马码 16 一样受 scope 硬校验约束。
        with self.assertRaises(ConfigError):
            BookConfig.from_dict(_base(formula={"type": 16, "ignore": []}))
        cfg = BookConfig.from_dict(_base(formula={"type": 15, "scope": 1}))
        self.assertEqual(cfg.formula["scope"], 1)

    def test_registration_only_map_without_type_is_allowed(self):
        # 只含 known_book / ignore（无 type）的登记式残块：不强制 scope（噪声账本）。
        cfg = BookConfig.from_dict(_base(formula={"known_book": ["7.1"]}))
        self.assertEqual(cfg.formula, {"known_book": ["7.1"]})
        cfg = BookConfig.from_dict(_base(formula={"ignore": ["3.1"]}))
        self.assertEqual(cfg.formula, {"ignore": ["3.1"]})

    def test_absent_or_empty_formula_is_none(self):
        self.assertIsNone(BookConfig.from_dict(_base()).formula)
        self.assertIsNone(BookConfig.from_dict(_base(formula={})).formula)


def _write_pages(ext, page_blocks):
    os.makedirs(ext, exist_ok=True)
    for i, blocks in enumerate(page_blocks, start=1):
        with open(os.path.join(ext, "page_%03d.json" % i), "w",
                  encoding="utf-8") as f:
            json.dump({"text": [{"text": t} for t in blocks]}, f,
                      ensure_ascii=False)


def _extract_with():
    d = tempfile.mkdtemp()
    ext = os.path.join(d, "_extract")
    os.makedirs(ext, exist_ok=True)
    with open(os.path.join(ext, "_extraction_done.json"), "w",
              encoding="utf-8") as f:
        json.dump({"done": True}, f)
    return d, ext


def _run_detect_formula(ext):
    code = (
        "import sys, json;"
        "sys.path.insert(0, %r);"
        "from make_config import detect_formula;"
        "print(json.dumps(detect_formula(sys.argv[1])))"
        % os.path.join(_ROOT, "config", "verify_config")
    )
    r = subprocess.run([sys.executable, "-c", code, ext],
                       capture_output=True, text=True, timeout=120,
                       encoding="utf-8", errors="replace")
    assert r.returncode == 0, "detect_formula failed: %s" % r.stderr
    return json.loads(r.stdout)


class TwoComponentScopeFromEvidence(unittest.TestCase):
    """两级数字 (C.N) 的 scope 由首分量重置证据派生，证据不足则省略（不写死 2）。"""

    def _chunks(self, tokens, per=8):
        pages = [tokens[i:i + per] for i in range(0, len(tokens), per)]
        return pages or [tokens]

    def test_per_chapter_reset_yields_scope_2(self):
        _d, ext = _extract_with()
        # 首分量 5、6 两章，各自从 1 重排 → 新首分量下末位回落 → scope 2。
        toks = ["Equation (5.%d)." % n for n in range(1, 17)]      # 5.1..5.16
        toks += ["Equation (6.%d)." % n for n in range(1, 17)]     # 6.1 < 5.16 → 重启
        _write_pages(ext, self._chunks(toks))
        res = _run_detect_formula(ext)
        self.assertIsNotNone(res)
        self.assertEqual(res["type"], 2)
        self.assertEqual(res.get("scope"), 2,
                         "逐章重启的两级编号应派生 scope=2：%r" % res)

    def test_bookwide_monotonic_yields_scope_1(self):
        _d, ext = _extract_with()
        # 首分量 5、6，但末位跨首分量连续上涨（6.17.. 从不低于 5.x）→ 无重置 → scope 1。
        toks = ["Eq. 5.%d." % n for n in range(1, 17)]             # 5.1..5.16
        toks += ["Eq. 6.%d." % n for n in range(17, 33)]           # 6.17..6.32 连续
        _write_pages(ext, self._chunks(toks))
        res = _run_detect_formula(ext)
        self.assertIsNotNone(res)
        self.assertEqual(res["type"], 2)
        self.assertEqual(res.get("scope"), 1,
                         "全书连续的两级编号应派生 scope=1：%r" % res)

    def test_single_leading_component_omits_scope(self):
        _d, ext = _extract_with()
        # 只见单一首分量 7（7.1..7.32）→ 无从观测跨首分量重置 → **省略 scope**，交 agent。
        toks = ["Equation (7.%d)." % n for n in range(1, 33)]
        _write_pages(ext, self._chunks(toks))
        res = _run_detect_formula(ext)
        self.assertIsNotNone(res)
        self.assertEqual(res["type"], 2, "仍应选出两级体例 type=2：%r" % res)
        self.assertNotIn("scope", res,
                         "证据不足时必须省略 scope，不得默认 2：%r" % res)

    def test_detector_never_writes_a_default_two_component_scope(self):
        # 三例合起来锁死：两级分支不再有写死的 scope:2——要么从证据派生 1/2，要么省略。
        seen = {}
        for name, builder in (
                ("reset", lambda: ["(%d.%d)" % (5 + (n // 15), n % 15 + 1)
                                   for n in range(30)]),
                ("omit", lambda: ["(7.%d)" % n for n in range(1, 31)])):
            _d, ext = _extract_with()
            toks = ["Label %s." % t for t in builder()]
            _write_pages(ext, self._chunks(toks))
            seen[name] = _run_detect_formula(ext)
        # 至少一例是省略的（omit），证明默认值已死。
        self.assertNotIn("scope", seen["omit"])


if __name__ == "__main__":
    unittest.main()
