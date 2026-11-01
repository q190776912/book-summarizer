# -*- coding: utf-8 -*-
"""二级中文抽取器：OCR 残字 / 逗号点号 自愈，且**不得**造截断幻影键。

郑大钟《线性系统理论》实测 2026-11-01：主定理族「结论N.M」的三种 OCR 噪声形态
  ① 点号被读成逗号：「结论3,2」→ 须按 结论3.2 入约；
  ② 末字被读成形近字：「结诊3,3」/「结诊3.3」→ 经 lib/label_typo 归一为 结论3.3；
  ③ 首字被读成形近字（歧义）：「缩论3.4」→ **不入约、也不截成裸键 结论3**（交人工判读）。
🔴 回归重点：config 声明的**仅二级**族必须只进 lab_re、**不进** single_re；否则
「结论3,2」会被 single_re 抢先把标签+首数截成裸「结论3」幻影键（真序数 2 被丢），
与 lab_re 的正解并存 → 契约出现截断/重复键。本文件用「缩论3.4 不应产出任何 结论 键」
把这条锁死。

运行：
  python flows/write-source/structure/script/tests/test_two_level_cn_typo_extractor.py
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
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "config", "verify_config")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

_SCRIPT = os.path.join(_ROOT, "flows", "write-source", "structure", "script")
if _SCRIPT not in sys.path:
    sys.path.insert(0, _SCRIPT)

import extract_items as EI  # noqa: E402
from verify_config import BookConfig, GroupConfig, ORDINAL_TWO_LEVEL  # noqa: E402


def _cfg():
    return BookConfig(ordinal=[
        GroupConfig(type=ORDINAL_TWO_LEVEL, scope=2, name=['结论']),
        GroupConfig(type=ORDINAL_TWO_LEVEL, scope=2, name=['定义']),
    ])


def _extract(pages):
    with tempfile.TemporaryDirectory() as d:
        for p, lines in enumerate(pages, start=1):
            blocks = [{"text": ln,
                       "poly": [90, 150 + 60 * i, 700, 190 + 60 * i,
                                90, 190 + 60 * i, 90, 150 + 60 * i]}
                      for i, ln in enumerate(lines)]
            with open(os.path.join(d, "page_%03d.json" % p), "w", encoding="utf-8") as fh:
                json.dump({"text": blocks, "formulas": []}, fh)
        items, _, _ = EI.extract_items_two_level(d, 3, 1, len(pages),
                                                 chapter_first=True, cfg=_cfg())
    return sorted(it["key"] for it in items)


class TestTwoLevelCNRescue(unittest.TestCase):

    def test_comma_separator_recovers_full_number(self):
        keys = _extract([["结论3,2 [矩阵指数函数] 给定 n×n 矩阵A"],
                         ["结论3.1 [零输入响应] 连续时间线性时不变系统"]])
        self.assertIn("结论3.2", keys, "点号误读为逗号须按完整二级号入约：%s" % keys)
        self.assertIn("结论3.1", keys, "%s" % keys)

    def test_last_glyph_typo_recovers(self):
        keys = _extract([["结诊3.3 [状态运动规律] 对连续时间线性时不变系统"]])
        self.assertIn("结论3.3", keys, "末字形近须归一后入约：%s" % keys)

    def test_first_glyph_ambiguous_makes_no_key(self):
        # 🔴 首字残（缩论）歧义 → 既不产出 结论3.4，也绝不产出截断裸键 结论3
        keys = _extract([["缩论3.4 [脉冲响应矩阵] 对零初始状态"]])
        self.assertNotIn("结论3.4", keys, "%s" % keys)
        self.assertNotIn("结论3", keys,
                         "二级族被截成裸键 = 丢真序数，禁止：%s" % keys)
        self.assertEqual([], [k for k in keys if k.startswith("结论")],
                          "歧义残字不得凭空造任何结论键：%s" % keys)

    def test_no_truncated_key_from_comma_head(self):
        # 「结论3,2」同时喂给 lab_re(正解) 与 single_re(会截成 结论3)：后者必须不含 结论
        keys = _extract([["结论3,2 [矩阵指数函数] 给定 n×n 矩阵A"]])
        self.assertEqual(["结论3.2"], keys,
                         "逗号头只能产出一条完整二级键，不得并存裸截断键：%s" % keys)


if __name__ == "__main__":
    unittest.main(verbosity=2)
