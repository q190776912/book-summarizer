r"""Q 层预检「agnostic 命中必须有标签位置证据」判据（阿诺尔德附录F/J 实测 2026-09-29）。

背景：`_validate_formula_config` 判据①「configured 抽不到 + agnostic 抽得到 =
depth/scope 配错」用的 agnostic 并集含**裸 N.M**形态（`bare_number` 默认开），于是
OCR 粘连串与坐标/参数表都会被记成「编号」：

  · 附录F p318 `c=∑∑(2j- 1)n,(2) +`（印刷号 `(2)` 被 OCR 黏在数学行**中间**）、
    `H=±[(92j-1926-2++025926-2+2）` → 1926.2；
  · 附录J `从(1,0)变为-(1,0)`、`(5,9g 和g²)` → 1.0 / 5.9。

两侧都抽不到「标签形态」的号时本该走 S-empty 降级（结构检查照跑 + WARN 请人工
对账，SSOT 已登记），却被噪声抬成阻断 ERROR（章 md 里只有 1 条忠实 `\tag{2}`，
写手无从下手）。修复 = 命中须经位置门（形态① 独立标签块 / 形态② 数学块**行尾**
token，行尾守卫与抽取侧共用 `_tail_pre_guard`）。

断言（正/负两侧都必须成立，否则本闸只是把噪声换成盲区）：
  1. 负——坐标 / 行中间括号数字 / 裸粘连 N.M **不算**证据；`SO(3)` 型黏着尾不算；
  2. 正——独立标签块 `(1.1)` 与数学块行尾 `. (2)` **算**证据；
  3. 端到端——纯噪声章：configured 空 + agnostic 命中 + 有 `\tag` → 预检**放行**
     （None）；同一页把噪声换成行尾标签 → 预检**照旧报错**（旧保护不失效）。
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

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

from formula_tag import (SourceFormulaIndex, agnostic_label_evidence,  # noqa: E402
                         build_formula_patterns, _validate_formula_config)


def _page(path, text_blocks, formulas=None):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"page": 1,
                   "text": [{"text": t} for t in text_blocks],
                   "formulas": [{"latex": lx} for lx in (formulas or [])]},
                  f, ensure_ascii=False)


class _TmpBook(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.ext = self._d.name
        self.md = os.path.join(self._d.name, "第1章_x.md")
        with open(self.md, "w", encoding="utf-8") as f:
            f.write("## §1\n\n$$\na = b\n\\tag{2}\n$$\n")
        self.addCleanup(self._d.cleanup)

    def _ctx(self):
        return SimpleNamespace(ext_dir=self.ext, ch=1, start=1, end=1,
                               md_file=self.md,
                               config=SimpleNamespace(sections_global=False))


NOISE = [
    "c=∑∑(2j- 1)n,(2) +",                    # 印刷号被黏在数学行中间
    "H=±[(92j-1926-2++025926-2+2）",         # OCR 粘连 → 裸 1926.2
    "cossin),当9从0变到2π时,它从(1,0)变为-(1,0),见KUhlebecl",  # 坐标
    "其实有三个同频率的本征振动形式 (5,9g 和g²)，但其中",      # 参数表/乱码
    "\\| \\omega \\|_C < c_1 \\quad T S O ( 3 )",             # 黏着尾（群记号）
]

LABELS = [
    "(1.1)",                                  # 形态① 独立标签块
    "于是得到估计式 \\| R \\| < c_2 \\varepsilon^2. (2)",  # 形态② 数学块行尾
    "f(x) \\le M (9)",                        # 行尾标签，左侧单字母（不得一刀切）
]
# 正向对照用**点分**标签：单分量配置（ncomp=1）对它一无所获，正是预检该报警的
# 「配错」形态；若用单分量 `(2)`，configured 自己的尾号路径就先抽到了，测不出。
DOTTED_LABELS = [
    "(1.1)",
    "于是得到估计式 \\| R \\| < c_2 \\varepsilon^2. (3.2)",
    "一般位置的哈密顿函数没有重本征值",
]


class TestEvidence(_TmpBook):
    def test_noise_is_not_evidence(self):
        _page(os.path.join(self.ext, "page_001.json"), NOISE)
        nums = {"2", "1926.2", "1.0", "5.9", "3"}
        self.assertFalse(
            agnostic_label_evidence(self.ext, 1, 1, 1, nums),
            "坐标/行中间括号数字/裸粘连号不得算作印刷公式编号证据")

    def test_real_labels_are_evidence(self):
        _page(os.path.join(self.ext, "page_001.json"), LABELS)
        self.assertTrue(agnostic_label_evidence(self.ext, 1, 1, 1, {"1.1", "2"}))
        # 左侧只有**一个**字母的真标签仍算证据（一刀切拒字母会把真号判成噪声）
        self.assertTrue(agnostic_label_evidence(self.ext, 1, 1, 1, {"9"}))
        # 号不在 agnostic 集里 = 不算（不得凭「像标签」空判）
        self.assertFalse(agnostic_label_evidence(self.ext, 1, 1, 1, {"7.7"}))


class TestPreflight(_TmpBook):
    def _run(self, blocks, formulas=None):
        _page(os.path.join(self.ext, "page_001.json"), blocks, formulas)
        formula = {"type": 1, "scope": 3}
        ncomp = 1
        pats = build_formula_patterns(ncomp)
        ag = SourceFormulaIndex(self.ext,
                                build_formula_patterns(1) + build_formula_patterns(2),
                                chapter_prefix=False)
        ag.build(1, 1, 1)
        cfg = SourceFormulaIndex(self.ext, pats, chapter_prefix=False, ncomp=1)
        cfg.build(1, 1, 1)
        return ag.all_numbers(), cfg.all_numbers(), \
            _validate_formula_config(self._ctx(), formula, ncomp, pats)

    def test_noise_only_chapter_degrades_to_warn(self):
        agn, cfgn, err = self._run(NOISE)
        self.assertEqual(cfgn, set(), "前提：单分量配置在这页抽不到号")
        self.assertTrue(agn, "前提：agnostic 并集确实被噪声命中")
        self.assertIsNone(err, "纯噪声命中不得把 S-empty 降级抬成阻断 ERROR")

    def test_real_label_still_blocks(self):
        agn, cfgn, err = self._run(DOTTED_LABELS)
        self.assertTrue(agn)
        self.assertEqual(cfgn, set(), "前提：单分量配置对点分标签抽不到号")
        self.assertIsNotNone(err, "真有行尾/独立标签形态的号而配置抽不到时，"
                                  "预检必须照旧报错（本闸不得变成盲区）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
