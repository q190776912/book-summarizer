"""Negative/positive tests for the unit-gate formula-layer switch.

Vakil "The Rising Sea" 实测（2026-09-25）：make_config 判定本书不追踪编号公式
（verify_config 无 `formula` 块 → Q 层 opt-out），但 build_structure 在 `ncomp=None`
下仍把裸数字（`\tag{0}`/`\tag{3}`）和散文里的交叉引用（`(1.6.5.4)`）过度挂成 contract
tag，单元门控据此误判「漏写编号公式」并阻断全章。根治 = 单元门控的 `\tag` 对账与章级
verify 的 Q 层**同开关**。锁死：无 formula 块 → 门控不启用 tag 对账；有 formula 块
（扁平 / 分组 / 历史 data 三形状）→ 启用。
"""
import json
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
    _ROOT = str(Path(__file__).resolve().parents[3])
sys.path.insert(0, str(Path(_ROOT) / "flows" / "write-source" / "script"))

import gate_units as gu  # noqa: E402


def _write_cfg(cfg):
    d = tempfile.mkdtemp(prefix="formula_layer_")
    with open(os.path.join(d, "verify_config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return d


class TestFormulaLayerEnabled(unittest.TestCase):
    def test_no_formula_block_is_off(self):
        # Vakil shape: ordinal + section_types only, NO formula key.
        ext = _write_cfg({"ch": {"ordinal": [{"type": 8, "scope": 3}],
                                 "section_types": [1, 2], "strict": True},
                          "section_types": [1, 2]})
        self.assertFalse(gu._formula_layer_enabled(ext))

    def test_missing_config_is_off(self):
        self.assertFalse(gu._formula_layer_enabled(tempfile.mkdtemp()))

    def test_flat_formula_is_on(self):
        ext = _write_cfg({"formula": {"type": 2}, "ch": {}})
        self.assertTrue(gu._formula_layer_enabled(ext))

    def test_grouped_formula_is_on(self):
        ext = _write_cfg({"ch": {"ordinal": [{"type": 3, "scope": 2}],
                                 "formula": {"type": 2, "known_book": ["2.17"]}}})
        self.assertTrue(gu._formula_layer_enabled(ext))

    def test_formula_ignore_only_is_on(self):
        ext = _write_cfg({"ch": {"formula": {"ignore": ["3.1"]}}})
        self.assertTrue(gu._formula_layer_enabled(ext))

    def test_legacy_data_wrapper_is_on(self):
        ext = _write_cfg({"data": {"ch": {"formula": {"type": 2}}}})
        self.assertTrue(gu._formula_layer_enabled(ext))

    def test_empty_formula_dict_is_off(self):
        ext = _write_cfg({"ch": {"formula": {}}})
        self.assertFalse(gu._formula_layer_enabled(ext))


if __name__ == "__main__":
    unittest.main()
