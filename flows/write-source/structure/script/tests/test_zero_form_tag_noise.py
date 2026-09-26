# -*- coding: utf-8 -*-
"""Regression: all-zero / leading-zero OCR artifacts are never formula numbers.

Kreyszig ch8 实测（2026-09-26，8.5-2）：印刷体
``c = sup_{y∈T_λ(X)} ‖x̃‖/‖y‖ < ∞`` 里右缘的 ``< ∞`` 被 OCR 读成裸编号 ``00``，
在**已配置** `formula` 的书上直接绕过形态闸（``formula_tag_shape_ok`` 只在
``ncomp is None`` 时启用），于是契约注册出 tag ``00``。而契约/manifest tag 是
``gate_units`` 的**对账真值**，门控于是反过来**要求**写手在该单元里凭空写出
``\\tag{00}``——脏数据被洗成「合规」。全书共 16 处（``0``/``00``/``07``，见
1.4-2、2.3-1、3.5-3、6.4-2、7.4-3、8.4-1、8.5-2、9.4-2、10.4-2、11.3-1）。

Fix under test（两层，共用 :func:`lib.numbering.formula_tag_noise` 单一判据）:
  * 抽取侧：`_attach_formula_tags` 在收割处拒挂，不分是否配置 `formula`；被拒的
    文本块**留在正文流**里（不丢内容）。
  * 消费侧：`node_tags` / `chapter_tag_map` 过滤既有契约里遗留的噪声号，使其
    不再被要求；单元里真写了 ``\\tag{00}`` 就按「编造」暴露出来。

真编号不受影响：单级 ``7``、多段 ``1.5.0.1``（Vakil 的中段 0）、字母后缀
``11t`` / ``3c`` / ``2i``。

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_zero_form_tag_noise.py
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

from attach_content import _attach_formula_tags              # noqa: E402
from lib.numbering import formula_tag_noise                   # noqa: E402
from data.book_structure.book_structure import node_tags, chapter_tag_map  # noqa: E402


def _text(raw, y=100.0, x=900.0, h=12.0):
    return {"kind": "text", "text": raw, "y": y, "bottom": y + h,
            "x": x, "x1": x + 30.0}


def _formula(y=100.0, h=14.0, body=r"a = b"):
    return {"kind": "formula", "formula": body, "display": True,
            "y": y, "bottom": y + h, "x": 60.0, "x1": 960.0}


def _run(blocks, **kw):
    out = _attach_formula_tags(blocks, **kw)
    tags = [str(b["tag"]) for b in out if b["kind"] == "formula" and "tag" in b]
    prose = [b["text"] for b in out if b["kind"] == "text"]
    return tags, prose


class TestNoisePredicate(unittest.TestCase):
    def test_zero_forms_are_noise(self):
        for t in ["0", "00", "000", "07", "002", " 0 "]:
            self.assertTrue(formula_tag_noise(t), "%s 应判为噪声" % t)

    def test_genuine_numbers_are_not_noise(self):
        # 带分隔符的形态不归本判据管（那是 formula_tag_shape_ok 的职责）
        for t in ["1", "7", "10", "17", "1.5.0.1", "8.11a", "0.0",
                  "11t", "3c", "2i", "2v", "6.7", None, ""]:
            self.assertFalse(formula_tag_noise(t), "%s 不该判为噪声" % t)

    def test_section_scoped_book_rejects_three_digit_bare_numbers(self):
        # Kreyszig 4.11-5：数值积分数表单元 0.931 476 / 0.144 被收成 931 / 144
        for t in ["144", "931", "1000"]:
            self.assertTrue(formula_tag_noise(t, section_scoped=True),
                            "%s 在节内重置号的书里应为噪声" % t)
            self.assertFalse(formula_tag_noise(t),
                             "%s 在全书/跨章编号书里不得误杀" % t)
        for t in ["17", "99", "8.11a", "11t"]:
            self.assertFalse(formula_tag_noise(t, section_scoped=True),
                             "%s 是合理节内编号" % t)


class TestHarvestRejectsNoise(unittest.TestCase):
    """已配置 `formula` 的书（Kreyszig：ncomp=1）同样不得收噪声号。"""

    CONFIGURED = dict(ncomp=1, bare=True)
    SECTION = dict(ncomp=1, bare=True, scope=3)

    def test_three_digit_bare_number_rejected_only_when_section_scoped(self):
        tags, prose = _run([_text("931"), _formula()], **self.SECTION)
        self.assertEqual(tags, [], "节内重置书里 931 被收成编号")
        self.assertIn("931", prose, "931 离开了正文流")
        tags2, _ = _run([_text("(931)"), _formula()], ncomp=1, bare=True, scope=2)
        self.assertEqual(tags2, ["931"], "全书编号书里的 (931) 不得误杀")

    def test_parenthesised_zero_never_attaches(self):
        for raw in ["(0)", "（0）", "(00)", "(07)"]:
            tags, prose = _run([_text(raw), _formula()], **self.CONFIGURED)
            self.assertEqual(tags, [], "%s 被收成公式编号" % raw)
            self.assertIn(raw, prose, "%s 离开了正文流（内容丢失）" % raw)

    def test_bare_zero_column_never_attaches(self):
        # 8.5-2 实测形态：display 右缘的裸 `00`（`< ∞` 的误读）
        tags, prose = _run([_text("00"), _formula(h=30.0)], **self.CONFIGURED)
        self.assertEqual(tags, [], "裸 00 被收成编号")
        self.assertIn("00", prose, "裸 00 离开了正文流")

    def test_single_level_genuine_number_still_attaches(self):
        tags, prose = _run([_text("(7)"), _formula()], **self.CONFIGURED)
        self.assertEqual(tags, ["7"], "真编号 (7) 被误杀")


class TestContractTruthDropsNoise(unittest.TestCase):
    """既有契约里遗留的噪声号不再是门控真值。"""

    def _node(self):
        return {"type": "chapter", "key": "8", "sub_sec": [
            {"type": "lemma", "key": "8.5-2", "sub_sec": [
                {"type": "formula", "tag": "00", "tags": ["00", "8"],
                 "formula": r"c=\sup \ldots"},
                {"type": "formula", "tag": "9", "formula": r"p(z_n)\to k"},
            ]},
            {"type": "definition", "key": "8.5-4", "sub_sec": [
                {"type": "formula", "tag": "0", "formula": r"\ldots"},
            ]},
        ]}

    def test_node_tags_skip_noise_but_keep_real(self):
        lemma = self._node()["sub_sec"][0]
        self.assertEqual(node_tags(lemma), ["8", "9"],
                         "噪声号应被剔除、真编号按文档序保留")
        dead = self._node()["sub_sec"][1]
        self.assertEqual(node_tags(dead), [], "只有噪声号时不得留下任何真值")

    def test_chapter_tag_map_has_no_entry_for_noise_only_nodes(self):
        m = chapter_tag_map(self._node())
        self.assertEqual(m.get("8.5-4", []), [])
        self.assertNotIn("0", m.get("8.5-2", []))
        self.assertEqual(sorted(m.get("8.5-2", [])), ["8", "9"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
