# -*- coding: utf-8 -*-
"""test_item_numbering_primed_entry.py — B 层「撇号重述项」不进阅读顺序窗。

Background (Serre《Linear Representations of Finite Groups》ch18 merge_source,
2026-09-29)
---------------------------------------------------------------------------
原书用带撇编号陈述已述定理的**重述/加强**：p.152 上 ``Theorem 35'`` 合法地印在
``Theorem 42`` 之后（裁剪目视核对 `_extract/_z_th35.png`），ch11 甚至排到
``Theorem 23'''``。`_parse_entry` 剥掉撇号后 35' 解析成条目 35，落进同一条
`0:file:Theorem` 阅读序列 → 假「顺序错乱 [42, 35, 43]」BLOCKING，整章无法过
merge_source。

根治 = 条头**自身编号**后紧跟撇号的条目只豁免「顺序」校验，仍照常计入
groups/present_md（「存在」这一项不豁免：撇号项所重述的号与自身都不会被误报缺号，
真错位的无撇条目也照旧 BLOCKING）。

Run:  python verify/tests/test_item_numbering_primed_entry.py
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
    _md_gap_blocking, _own_number_primed)
from verify.script.base import VerifyContext                   # noqa: E402


def _ctx(md_text, ch=18):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "chapter%d.md" % ch)
    with open(p, "w", encoding="utf-8") as f:
        f.write(md_text)
    # Serre: 全书一条章内 1..N 共享计数器（Theorem/Proposition/… 各自起号、
    # 序标只有一级 —— type=1/scope=1 ⇒ gk="0:file:LABEL"，与实测 gk 一致）。
    cfg = BookConfig(
        ordinal=[GroupConfig(type=1, name=["Theorem", "Proposition", "Corollary",
                                           "Lemma", "Definition", "Example",
                                           "Exercise"], scope=1)],
        strict=True,
    )
    return VerifyContext(ch=ch, start=1, end=1, md_file=p, ext_dir=d, config=cfg)


def _head(n, label="Theorem", prime=""):
    return "**%s %d%s**: item %d.\n\n" % (label, n, prime, n)


class PrimedOwnNumberDetection(unittest.TestCase):
    def test_primed_spellings_recognized(self):
        for inner in ["Theorem 35'", "Theorem 35′", "Theorem 35$'$",
                      "Theorem 23'''", "Theorem 42'' (Brauer)",
                      "Proposition 30'", "35' 定理"]:
            self.assertTrue(_own_number_primed(inner), inner)

    def test_plain_and_quoted_headers_not_primed(self):
        for inner in ["Theorem 35", "Theorem 42 (R. Brauer)",
                      "Definition 7 'the norm map'", "定理 5.3",
                      "Theorem 5 (cf. Theorem 3')"]:   # 自身号 5，撇号属引用
            self.assertFalse(_own_number_primed(inner), inner)


class PrimedEntryOrdering(unittest.TestCase):
    def test_primed_restatement_after_bigger_number_is_legal(self):
        """印面 42 → 42' → 35' → 43：无 BLOCKING（旧实现报「35 出现在 42 之后」）。"""
        md = ("# Chapter 18\n\n" + _head(41) + _head(42)
              + _head(42, prime="'") + _head(35, prime="'") + _head(43))
        blocking, _w, _p, _t, _g = _md_gap_blocking(_ctx(md))
        text = "\n".join(blocking)
        self.assertNotIn("顺序错乱", text, "撇号重述项被误判错位：%s" % text)

    def test_real_misplacement_still_blocks(self):
        """收紧后不得失去检出力：无撇的 35 掉到 42 之后仍须 BLOCKING。"""
        md = ("# Chapter 18\n\n" + _head(41) + _head(42)
              + _head(35) + _head(43))
        blocking, _w, _p, _t, _g = _md_gap_blocking(_ctx(md))
        self.assertIn("顺序错乱", "\n".join(blocking))

    def test_primed_items_still_count_as_present(self):
        """「存在」不豁免：只印 30 与 30' 时，30' 仍是一条真条目（groups 非空），
        而真缺的 29（序列 min..max 之间的洞）照旧上报。"""
        md = ("# Chapter 11\n\n" + _head(27) + _head(28) + _head(30)
              + _head(30, prime="'"))
        blocking, _w, _p, _t, groups = _md_gap_blocking(_ctx(md, ch=11))
        nums = [n for n, _k in list(groups.values())[0]]
        self.assertIn(30, nums, "撇号条目被整条丢弃")
        self.assertIn("缺号 29", "\n".join(blocking))


if __name__ == "__main__":
    unittest.main(verbosity=2)
