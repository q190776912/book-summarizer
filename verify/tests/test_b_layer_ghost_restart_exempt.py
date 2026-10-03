# -*- coding: utf-8 -*-
"""test_b_layer_ghost_restart_exempt.py — B 层「疑似幽灵重复节点」只报**同标签同子块**的同号二现。

Background（2026-10-03 跨语料普查 `tools/census_ghost_rows.py`，49 行 / 8 书）
---------------------------------------------------------------------------
顺序校验把「保留首次去重后单调」的同号二现一律报成幽灵重复节点（正文引用被
build_structure 误建为条目节点）。普查逐行取证后，绝大多数其实是**印面合法的
多计数器交错**：
  A. 节内字母子块重启 —— Arnold《经典力学的数学方法》§14.B 的 例1..4 与 §14.D 的
     例1..2（§27、§32、§8 的问题1.. 同形）；
  B. 合并窗内跨类型各自起号 —— Katok §9.2 的 Example 9.2.1 与 Proposition 9.2.1、
     Weibel §6.5 的 Definition 6.5.1 与 Exercises 6.5.1。
真幻影形态（Katok §1.1 的第二个 定义1.1.1：同号 + 同标签 + 同子块）必须照旧报。

根治 = 判据按 (标签, 子块锚) 分桶，只有**同桶内**的同号二现才叫幻影；子块锚取
`_subblock_anchors`（含 `### §C` 这一层，与计数器窗口判据 `_section_anchors`
刻意不同——那边字母子块必须继承父节，否则把连续计数器切开就假报缺号）。
🔴 BLOCKING 分支（去重后仍非单调 = 真错位）一字未动，本测试也钉住它。

Run:  python verify/tests/test_b_layer_ghost_restart_exempt.py
"""
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

from verify_config import BookConfig, GroupConfig              # noqa: E402
from item_numbering_integrity import _md_gap_blocking          # noqa: E402
from verify.script.base import VerifyContext                   # noqa: E402

GHOST = "疑似幽灵重复节点"


def _ctx(md_text, groups):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "chapter1.md")
    with open(p, "w", encoding="utf-8") as f:
        f.write(md_text)
    cfg = BookConfig(ordinal=groups, strict=True)
    return VerifyContext(ch=1, start=1, end=1, md_file=p, ext_dir=d, config=cfg)


# 节内单级计数器（例1 / 问题1），按 `## §` 节窗 —— Arnold §32 的形制
_ARNOLD = [GroupConfig(type=1, name=["例", "命题", "问题"], scope=3)]
# 三级序标（例9.2.1）+ 节内重置，同组含两个标签（合并窗）—— Katok §9.2 的形制
_KATOK = [GroupConfig(type=3, name=["例", "命题"], scope=3)]


def _h(label, num, body):
    return "**%s%s**：%s\n\n" % (label, num, body)


class LetterSubBlockRestart(unittest.TestCase):
    """类 A：字母子块内重启合法，不得报幻影。"""

    def test_restart_in_letter_subblock_is_silent(self):
        md = ("## §32 外形式\n\n### §B 2-形式\n\n"
              + _h("例", "1", "有向面积") + _h("例", "2", "流体流量")
              + _h("例", "3", "投影面积")
              + "\n### §C $k$-形式\n\n"
              + _h("例", "1", "有向体积") + _h("例", "2", "有向平面投影")
              + _h("问题", "3", "维数"))
        blocking, warnings = _md_gap_blocking(_ctx(md, _ARNOLD))[:2]
        self.assertEqual(blocking, [])
        self.assertEqual([w for w in warnings if GHOST in w], [], warnings)

    def test_same_subblock_same_label_dup_still_warns(self):
        """真幻影（Arnold ch7 §32.C 实测形态：C 块里 例1,例2,例3 之后又出现 例2）
        —— 同标签同子块的同号二现必须照旧报。"""
        md = ("## §32 外形式\n\n### §C k-形式\n\n"
              + _h("例", "1", "有向体积") + _h("例", "2", "流体流量")
              + _h("例", "3", "投影面积") + _h("例", "2", "又一个 例2")
              + _h("问题", "3", "维数"))
        blocking, warnings = _md_gap_blocking(_ctx(md, _ARNOLD))[:2]
        ghost = [w for w in warnings if GHOST in w]
        self.assertEqual(len(ghost), 1, warnings)
        self.assertIn("[2]", ghost[0])
        self.assertEqual(blocking, [])


class ParallelLabelSeries(unittest.TestCase):
    """类 B：合并窗内跨标签各自起号合法，不得报幻影。"""

    def test_cross_label_same_number_is_silent(self):
        md = (_h("例", "9.2.1", "圆") + _h("例", "9.2.2", "椭圆")
              + _h("命题", "9.2.1", "存在性")
              + _h("例", "9.2.3", "体育场"))
        blocking, warnings = _md_gap_blocking(_ctx(md, _KATOK))[:2]
        self.assertEqual(blocking, [])
        self.assertEqual([w for w in warnings if GHOST in w], [], warnings)


class RealMisplacementStillBlocks(unittest.TestCase):
    """🔴 收窄只作用于 WARN 分支：真错位（去重后仍非单调）必须继续 BLOCKING。"""

    def test_out_of_order_item_still_blocking(self):
        md = (_h("例", "9.2.1", "a") + _h("例", "9.2.3", "c")
              + _h("例", "9.2.2", "b 被排到 3 之后"))
        blocking, warnings = _md_gap_blocking(_ctx(md, _KATOK))[:2]
        self.assertTrue([b for b in blocking if "顺序错乱" in b], blocking)
        self.assertEqual([w for w in warnings if GHOST in w], [], warnings)

    def test_cross_label_misplacement_still_blocks(self):
        """跨标签也救不了真错位：去重后仍非单调 → BLOCKING 分支原样保留。"""
        md = (_h("例", "9.2.1", "a") + _h("命题", "9.2.3", "b")
              + _h("例", "9.2.2", "c 掉到后面"))
        blocking, _w = _md_gap_blocking(_ctx(md, _KATOK))[:2]
        self.assertTrue([b for b in blocking if "顺序错乱" in b], blocking)


if __name__ == "__main__":
    unittest.main(verbosity=2)
