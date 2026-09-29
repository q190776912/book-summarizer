# -*- coding: utf-8 -*-
r"""Regression: 落账证据趟（`physical_evidence._units_gate_ok`）必须与权威 CLI
`gate_units --units-dir units-translate` 用**同一个** translation 口径。

2026-09-29 Iwaniec–Kowalski《解析数论》`flow_runner mark write_source translate_chapters`
被拒：27 章 `gate_units --units-dir units-translate` 全部 exit 0，落账证据趟却报
「ch7 单元 0050_item_定理7_28.md … 证明/注记/解答块过长且未分条（2992 字）」。
根因 = gate_units 传 `translation=(units_sub != "units")`（Tier-3 证明分条闸只管
自撰文本，译单元逐行镜像已过该闸的冻结源单元），而 shadow 的内联复刻漏传该参数，
于是按源侧判据罚译单元 → 两趟判据分叉（检测趟放行、落账趟打回），译者被逼去
把源书本就散文式的证明拆成 `1. 2. 3.` = 结构性偏离冻结源单元。

钉住：同一块散文式中文证明，translation=True 不报「未分条」、False 照报。
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
    _ROOT = str(Path(__file__).resolve().parents[4])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

from flows._flow_contract import physical_evidence as pe  # noqa: E402

_MARK = ("<!-- book-summarizer DONE unit: id=0050 type=item key=定理7.28 "
         "name=定理 7.28 -->\n")
# comfortably over VERBOSE_PROOF_CHARS (700), no step labels; 句子互不相同，
# 免得撞上「OCR 乱码重复片段」闸（本测试只钉 translation 口径）
_WALL = "".join("第%d类不完全和应用试验函数的光滑性，配合%d阶矩估计与相邻区间的"
                "覆盖引理，逐条核对全部假设后代回原式。\n" % (i, i * 3 + 1)
                for i in range(1, 31)).replace("\n", "")


def _dir(body):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "0050_item_定理7_28.md"), "w",
              encoding="utf-8", newline="") as f:
        f.write(_MARK + body)
    return d


class TranslationFlagThreading(unittest.TestCase):
    def _run(self, translation):
        body = "> **证明（梗概）。** %s\n" % _WALL
        d = _dir(body)
        manifest = {"language": "en",
                    "units": [{"file": "0050_item_定理7_28.md", "type": "item",
                               "key": "定理7.28", "name": "定理 7.28"}]}
        ok, problems = pe._units_gate_ok(d, manifest, translation=translation)
        return ok, problems

    def test_source_semantics_still_flag_undivided_proof(self):
        """源侧（translation=False，默认）照报——负向用例，防豁免扩到源单元。"""
        ok, problems = self._run(False)
        self.assertFalse(ok)
        self.assertTrue(any("未分条" in p for p in problems), problems)

    def test_translation_semantics_exempts_undivided_proof(self):
        """译侧口径：与 gate_units 一致，Tier-3 分条闸整个跳过。"""
        ok, problems = self._run(True)
        self.assertTrue(ok, problems)
        self.assertFalse(any("未分条" in p for p in problems), problems)

    def test_default_is_source_semantics(self):
        """默认参数不得翻转（源单元仍受闸）。"""
        d = _dir("> **证明。** %s\n" % _WALL)
        manifest = {"language": "en",
                    "units": [{"file": "0050_item_定理7_28.md", "type": "item",
                               "key": "定理7.28", "name": "定理 7.28"}]}
        ok, problems = pe._units_gate_ok(d, manifest)
        self.assertFalse(ok, problems)


class ShadowLoadsPairedSourceBody(unittest.TestCase):
    """落账证据趟必须自己取到**配对源单元正文**，否则译文的两条结构继承豁免恒不生效。

    Apostol《解析数论导引》2026-09-29 实测：`gate_units --units-dir units-translate`
    15 章全部 exit 0，`flow_runner verify write_source translate_chapters` 却报
    「ch2 单元 0077_desc_D28.md … `**例.**` should be inside `>`」。根因同上一类：
    gate_units 走 `paired_source_body` 把源正文喂给 `check_body(src_body=…)`，
    shadow 的内联复刻压根没取 → 族集合比较无从进行 → 权威趟放行、落账趟打回，
    译者被逼把已过源闸的印面结构改塞进 `>`（= 与冻结源单元分叉）。
    """

    _FN = "0077_desc_D28.md"
    # 源：顶层 `**Definition.**` + `**Examples.**`（复数尾 s 命中 `_H_MISSING_BQ` 的
    # 负向前瞻 → 源侧合法、过源闸）；译：同结构 `**定义.**` + `**例.**`（中文无复数
    # 形态 → 命中必包表）。族集合两侧均为 {definition, example}。
    SRC = ("<!-- book-summarizer DONE unit: id=0077 type=desc key=D28 name= -->\n"
           "**Definition.** A function $I$ on $\\mathbb{N}$ is additive when\n"
           "$I(mn) = I(m) + I(n)$.\n\n**Examples.** $I(n) = 0$ and $I(n) = \\log n$.\n")
    TR = ("<!-- book-summarizer DONE unit: id=0077 type=desc key=D28 name= -->\n"
          "**定义.** 若 $I(mn) = I(m) + I(n)$，则称 $I$ 为可加函数。\n\n"
          "**例.** $I(n) = 0$ 与 $I(n) = \\log n$。\n")

    def _tree(self, root_name="book_structure"):
        """造 `<ex>/book_structure/{units,units-translate}/ch2/0077_desc_D28.md`。"""
        ex = tempfile.mkdtemp()
        man = {"language": "en", "units": [
            {"file": self._FN, "type": "desc", "key": "D28", "name": ""}]}
        import json
        for sub, body in (("units", self.SRC), ("units-translate", self.TR)):
            d = os.path.join(ex, root_name, sub, "ch2")
            os.makedirs(d)
            with open(os.path.join(d, self._FN), "w",
                      encoding="utf-8", newline="") as f:
                f.write(body)
            with open(os.path.join(d, "manifest.json"), "w",
                      encoding="utf-8") as f:
                json.dump(man, f, ensure_ascii=False)
        return os.path.join(ex, root_name, "units-translate", "ch2")

    def _gate(self, tdir):
        import json
        with open(os.path.join(tdir, "manifest.json"), encoding="utf-8") as f:
            man = json.load(f)
        return pe._units_gate_ok(tdir, man, ch_key="2", translation=True)

    def test_shadow_passes_paired_real_tree(self):
        """正向：真目录树（units-translate 的父父 = book_structure）→ 配对生效、放行。"""
        ok, problems = self._gate(self._tree())
        self.assertTrue(ok, problems)
        self.assertFalse(any("should be inside" in p for p in problems), problems)

    def test_shadow_without_source_sibling_still_flags(self):
        """负向：源侧同名目录不存在 → 无继承真值，必包闸照旧打回（豁免不可无源生效）。"""
        tdir = self._tree()
        src_sibling = os.path.join(os.path.dirname(os.path.dirname(tdir)),
                                   "units", os.path.basename(tdir))
        import shutil
        shutil.move(src_sibling, src_sibling + "_absent")
        ok, problems = self._gate(tdir)
        self.assertFalse(ok, problems)
        self.assertTrue(any("should be inside" in p for p in problems), problems)


if __name__ == "__main__":
    unittest.main(verbosity=2)
