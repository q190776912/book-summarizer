"""条头「数词-连字符-词」复合术语误识的判据测试。

缺陷现场（2026-09-29 Arnold《经典力学的数学方法》附录C 实测）：原书该定理**无编号**，
扫描版 OCR 把条头与紧随其后的正文粘成一行
`定理2-微分形式 S 在复射影空间上给出一个辛构造.`
——其中 `2-微分形式` 是数学术语 2-form（二阶微分形式），不是序标。旧 `lab_re`
只拦「后继数字」与「助词」，对连字符形态放行 ⇒ 契约长出幻影键 `定理2`，
而 md 忠实渲染成无号的 `**定理** 2-微分形式 …`，M 层报 TRULY MISSING 且**无法回填**
（书里从来没有这条编号，回填＝编造条目）。

判据（`extract_items_cn_single.lab_re` 尾部负向前查）：
  ① 号后是**连字符**（半角 `-` / 全角 `－` / 破折号 `—–`，可隔空白）且连字符后
     **不是数字** ⇒ 复合术语，不是序标，整行不入账；
  ② 号后连字符**接数字**（章-项连字符编号 `定理5-2`、回指范围 `例3-4`）一律照旧
     放行——本判据只认「连字符后面是词」这一种形态，不收窄任何现有真条；
  ③ 抽取侧与查漏/回填侧共用同一谓词（`check_structure_completeness.scan_raw_items`
     对 CN 单级书直接委托本函数），故幻影键在两侧同时消失，不会一侧剔除、
     另一侧又要求补录；
  ④ 只拒绝连字符，不拒绝号后空白/句点起头的正文（`定理2 微分形式…` 仍是真条头）。

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_label_dash_compound_term.py
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
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from extract_items_cn_single import extract_items_cn_single
from verify_config import GroupConfig


GROUPS = [GroupConfig(type=1, name=["例"], scope=3),
          GroupConfig(type=1, name=["定理"], scope=3)]


def _mk_pages(d, pages):
    for i, lines in enumerate(pages, start=1):
        with open(os.path.join(d, f"page_{i:03d}.json"), "w", encoding="utf-8") as f:
            json.dump({"text": [{"text": t} for t in lines], "formulas": []}, f)


def _keys(d, n):
    return [it["key"] for it in extract_items_cn_single(d, 1, n, groups=GROUPS)]


class TestDashCompoundTermRejected(unittest.TestCase):
    def test_printed_phantom_line_is_not_an_item(self):
        # 现场原文（page_286 t31）：无编号定理 + 复合术语 2-微分形式。
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [['定理2-微分形式 S 在复射影空间上给出一个辛构造.']])
            self.assertEqual(_keys(d, 1), [])

    def test_ocr_spacing_and_dash_variants_all_rejected(self):
        for variant in ('例3-维向量场的积分曲线',
                        '定理2－微分形式给出辛构造',
                        '定理2 — 微分形式给出辛构造',
                        '定理2 - 微分形式给出辛构造'):
            with self.subTest(variant=variant), tempfile.TemporaryDirectory() as d:
                _mk_pages(d, [[variant]])
                self.assertEqual(_keys(d, 1), [])

    def test_scan_raw_items_shares_the_predicate(self):
        # 判据③：查漏/回填侧同视图——幻影键不会一侧剔除、另一侧又要求补录。
        from check_structure_completeness import scan_raw_items
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [['定理2-微分形式 S 在复射影空间上给出一个辛构造.']])
            out = scan_raw_items(d, 1, 1, 1, primary_type=1,
                                 chapter_first=True, language="cn",
                                 groups=GROUPS)
            self.assertEqual([o["key"] for o in out], [])


class TestGenuineHeadsStillAccepted(unittest.TestCase):
    def test_dash_followed_by_digit_untouched(self):
        # 判据②：章-项连字符编号照旧入账（号 = 5），只拒「连字符后是词」。
        for line, want in (('定理5-2 是辛构造的必要条件', '定理5'),
                           ('例3-4 给出对称形式', '例3')):
            with self.subTest(line=line), tempfile.TemporaryDirectory() as d:
                _mk_pages(d, [[line]])
                self.assertEqual(_keys(d, 1), [want])

    def test_space_terminated_head_untouched(self):
        # 判据④：号后空白接正文仍是真条头。
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [['定理2 微分形式 S 在复射影空间上给出一个辛构造.']])
            self.assertEqual(_keys(d, 1), ['定理2'])

    def test_real_item_following_phantom_page_is_kept(self):
        # 同一页既有复合术语行、也有真条头：只丢前者。
        with tempfile.TemporaryDirectory() as d:
            _mk_pages(d, [
                ['定理2-微分形式 S 在复射影空间上给出一个辛构造.',
                 '例7 验证该构造在 CP^n 上非退化.'],
            ])
            self.assertEqual(_keys(d, 1), ['例7'])


if __name__ == "__main__":
    unittest.main(verbosity=2)
