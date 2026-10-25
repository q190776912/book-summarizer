# -*- coding: utf-8 -*-
"""test_item_numbering_continued_block.py — B 层「(continued)/（续）」续块不算幽灵重复。

Background (elements-of-large-sample-theory ch4/ch6, 2026-10-24)
---------------------------------------------------------------------------
原书把被后续条目隔断的**同一条目**块续排，续块条头沿用原编号：
``Example 6.1.2 (continued)``（公式 6.1.77-78 + 节末散文 + Summary，印面 p393-394）
合法地印在 ``Example 6.1.3`` / ``Lemma 6.1.3`` **之后**。md 按印面正确位置搬移续部
（Q 层 ORDER_MISMATCH 的修法）后，B 层条目序列出现 ``[1, 2, 3, 2(续)]``：
last_pos 序倒挂（2 落到 3 之后）→「保留首次去重后单调」→ 同标签同子块命中
→ 「疑似幽灵重复节点」WARN——把合法印面形态误报成幻影，且 ch3/ch7 同型修复会
批量复现。

根治 = 续块出现（条头含 ``(continued)`` / ``（续）``）计 continuation：幽灵重复
判据的同号二现**不计它**；「存在」与顺序 BLOCKING 判据一字未动（真幻影：同一
(标签, 子块) 桶内两个**非续**同号头，照旧 WARN；真错位照旧 BLOCKING）。

Run:  python verify/tests/test_item_numbering_continued_block.py
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
from item_numbering_integrity import (                         # noqa: E402
    _md_gap_blocking, _is_continuation_head)
from verify.script.base import VerifyContext                   # noqa: E402


def _ctx(md_text, ch=6):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "chapter%d.md" % ch)
    with open(p, "w", encoding="utf-8") as f:
        f.write(md_text)
    # 本书 §6.1 体例：条目计数器按**章.节.序号**三级、按类型分组（Example 组
    # 内 6.1.1 / 6.1.2 / 6.1.3 各自起号），scope=3 ⇒ gk="0:6.1"。
    cfg = BookConfig(
        ordinal=[GroupConfig(type=3, name=["Example"], scope=3)],
        strict=True,
    )
    return VerifyContext(ch=ch, start=1, end=1, md_file=p, ext_dir=d, config=cfg)


def _head(n, cont=False, lang="en"):
    if lang == "en":
        return "**Example 6.1.%d%s**: item %d.\n\n" % (n, " (continued)" if cont else "", n)
    return "**例 6.1.%d%s**：第 %d 条。\n\n" % (n, "（续）" if cont else "", n)


class ContinuationHeadDetection(unittest.TestCase):
    def test_continued_spellings_recognized(self):
        for inner in ["Example 6.1.2 (continued)", "Example 6.1.2 (cont.)",
                      "例 6.1.2（续）", "例 6.1.2(续)", "Example 7.7.1. Cauchy (continued).",
                      "例 5.3 多项分布（续）。"]:
            self.assertTrue(_is_continuation_head(inner), inner)

    def test_plain_and_prose_heads_not_continuation(self):
        for inner in ["Example 6.1.2", "Example 6.1.2 (Wilcoxon two-sample statistic)",
                      "定理 5.3", "Example 6.1.2 (cf. Example 3.3.7)"]:
            self.assertFalse(_is_continuation_head(inner), inner)


class ContinuedBlockOrdering(unittest.TestCase):
    def test_continued_block_after_later_number_is_legal(self):
        """印面 Ex6.1.1 → Ex6.1.2 → Ex6.1.3 → Ex6.1.2(续)：无 WARN 无 BLOCKING。"""
        md = "# Chapter 6\n\n" + _head(1) + _head(2) + _head(3) + _head(2, cont=True)
        blocking, warnings, _p, _t, _g = _md_gap_blocking(_ctx(md))
        text = "\n".join(blocking + warnings)
        self.assertNotIn("幽灵重复节点", text, "合法续部被误报幻影：%s" % text)
        self.assertNotIn("顺序错乱", text, "合法续部被误判错位：%s" % text)

    def test_cn_continued_block_after_later_number_is_legal(self):
        """CN 侧同构：例 6.1.1 → 例 6.1.2 → 例 6.1.3 → 例 6.1.2（续）。"""
        md = "# 第 6 章\n\n" + _head(1, lang="cn") + _head(2, lang="cn") \
            + _head(3, lang="cn") + _head(2, cont=True, lang="cn")
        blocking, warnings, _p, _t, _g = _md_gap_blocking(_ctx(md))
        text = "\n".join(blocking + warnings)
        self.assertNotIn("幽灵重复节点", text, "CN 合法续部被误报幻影：%s" % text)
        self.assertNotIn("顺序错乱", text, "CN 合法续部被误判错位：%s" % text)

    def test_real_phantom_duplicate_still_warns(self):
        """收紧后不得失去检出力：**非续**同号头掉到更大编号之后（Katok §1.1 形态：
        第二个 定义1.1.1 印在更大编号之后）照旧 WARN。"""
        md = "# Chapter 6\n\n" + _head(1) + _head(2) + _head(3) + _head(2)
        blocking, warnings, _p, _t, _g = _md_gap_blocking(_ctx(md))
        self.assertIn("幽灵重复节点", "\n".join(warnings))

    def test_real_misplacement_still_blocks(self):
        """真错位（无续标记、无重复的 3 掉到 4 之后：首现序即非单调）仍须 BLOCKING。"""
        md = "# Chapter 6\n\n" + _head(1) + _head(2) + _head(4) + _head(3)
        blocking, _w, _p, _t, _g = _md_gap_blocking(_ctx(md))
        self.assertIn("顺序错乱", "\n".join(blocking))

    def test_continued_block_still_counts_as_present(self):
        """「存在」不豁免：只印 2 与 2(续) 时 2 仍存在，而 min..max 区间内真缺的 3
        （[1, 2, 2(续), 4] 的洞）照旧上报。"""
        md = "# Chapter 6\n\n" + _head(1) + _head(2) + _head(2, cont=True) + _head(4)
        blocking, _w, _p, _t, groups = _md_gap_blocking(_ctx(md))
        nums = [n for n, _k in list(groups.values())[0]]
        self.assertIn(2, nums, "续块所属条目被整条丢弃")
        self.assertIn("缺号 3", "\n".join(blocking))

    def test_mid_sequence_continuation_unchanged(self):
        """续块紧跟主部（未搬移的旧形态）本就无告警，回归保护。"""
        md = "# Chapter 6\n\n" + _head(1) + _head(2) + _head(2, cont=True) + _head(3)
        blocking, warnings, _p, _t, _g = _md_gap_blocking(_ctx(md))
        text = "\n".join(blocking + warnings)
        self.assertNotIn("幽灵重复节点", text)
        self.assertNotIn("顺序错乱", text)
        self.assertNotIn("缺号", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
