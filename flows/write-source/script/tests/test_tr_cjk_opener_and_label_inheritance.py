# -*- coding: utf-8 -*-
r"""Regression: 两处「源过 / 译不过」判据缺口（Apostol《解析数论导引》2026-09-29 实测）。

1. **`>` 块合法开吻的 bold-led catch-all 只认拉丁首字**。`_H_UL_OPENERS` 末支
   `[A-Z0-9].*?\*\*` 让英文「关键词不在首位」的证明头天然放行（`> **Alternate
   proof.**`、`> **Proof of the reciprocity law.**`），而中文同位写法
   `> **另一证明。**`（ch4/0010）、`> **互反律的证明。**`（ch9/0038）既不入关键词表
   也不入 catch-all → 整块判「unlabeled blockquote」，块内每行 `> $$` 连带重复报错
   （ch4 一处标签 4 条 FAIL）。译者只剩改词规避或拆掉 `>` 两条自撰出路。
   ⇒ catch-all 首字类补 CJK（`一-鿿`），**只放宽检测**，不进必包表。
   真阳必须保住：无标签 `> 普通中文散文` 照报。

2. **必包表对中文复数小标题无豁免同位词**。英文源顶层 `**Examples.**` / `**Notes.**`
   经 `Example(?![\w\-])` 天然不命中（复数尾 s），留顶层过源闸；中文没有复数形态，
   译者写 `**例。**` / `**注.**` 却命中 `_H_MISSING_BQ` → 判「label should be inside
   `>`」，逼出「塞进 `>`（与已过闸的源结构分叉）」或「自撰替代词」（`例子` 有豁免，
   `Notes` 连一个豁免词都没有）。⇒ **译单元以配对源单元为结构真值**：译文顶层粗体
   标签的族多重集与源侧相等时，说明译者逐位镜像了源侧选择，本条放行；只要多拆/多包
   一个顶层标签，族多重集失衡 → 照旧 FAIL（盲区不扩大）。源单元侧不受影响。
"""
import io
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
sys.path.insert(0, _ROOT)
import lib.boot  # noqa: E402
lib.boot.setup()

import check_unit_quality as cq  # noqa: E402
# 🔴 继承判据本体住在 format_verify（SSOT），单元趟与文档趟共用同一份实现；
# 本测试直接从那里导入谓词，避免「测的是副本」。
from format_verify import (  # noqa: E402
    _H_UL_OPENERS, check_unlabeled_blockquotes,
    check_labels_missing_blockquote,
    top_label_families, bq_label_block_then_prose,
    MBQ_ERR_MARK, ISEP_ERR_MARK)


def _write(text):
    fd, p = tempfile.mkstemp(suffix=".md")
    os.close(fd)
    with io.open(p, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return p


class CjkBoldLedOpener(unittest.TestCase):
    def test_cjk_label_head_is_legit_opener(self):
        for head in ("> **另一证明。** 熟悉 Riemann-Stieltjes 积分的读者可用更短的证明",
                     "> **互反律的证明。** 要从 (23) 推出二次互反律",
                     "> **定理的证明思路。** 分三步",
                     "> **Alternate proof.** A shorter proof is available"):
            self.assertTrue(_H_UL_OPENERS.match(head), head)

    def test_unlabeled_cjk_prose_still_flagged(self):
        p = _write("> 这是一段没有任何标签的中文散文\n> 继续散文\n")
        try:
            self.assertTrue(check_unlabeled_blockquotes(p))
        finally:
            os.remove(p)

    def test_labeled_cjk_proof_block_with_math_passes(self):
        p = _write("\n".join([
            "> **Alternate proof.** A shorter proof is available.",
            ">",
            "> $$",
            "> \\sum_{y < n \\leq x} a(n) f(n) = \\int_y^x f(t)\\, dA(t) .",
            "> $$",
            "",
            "> **另一证明。** 一个更短的证明如下。",
            ">",
            "> $$",
            "> \\sum_{y < n \\leq x} a(n) f(n) = \\int_y^x f(t)\\, dA(t) .",
            "> $$",
        ]) + "\n")
        try:
            self.assertEqual(check_unlabeled_blockquotes(p), [])
        finally:
            os.remove(p)


class TranslationLabelInheritance(unittest.TestCase):
    SRC = ["**Examples.** Since $I(n)\\log n = 0$ we have $I' = 0$.",
           "",
           "> **Note.** The original wraps this one.",
           ""]
    TR = ["**例。** 由于对一切 $n$ 都有 $I(n)\\log n = 0$，所以 $I' = 0$。",
          "",
          "> **注.** 原文这条是包好的。",
          ""]

    def test_family_multiset_matches_source(self):
        self.assertEqual(sorted(top_label_families(self.SRC)),
                         sorted(top_label_families(self.TR)))

    def test_source_side_still_flags_bare_cn_label(self):
        # 无源上下文（源单元侧）→ 必包闸照报
        got = cq._run_format_verify_unit_checks(self.TR)
        self.assertTrue(any(MBQ_ERR_MARK in p for p in got), got)

    def test_translation_inherits_top_level_label(self):
        got = cq._run_format_verify_unit_checks(self.TR, self.SRC)
        self.assertFalse([p for p in got if MBQ_ERR_MARK in p], got)

    def test_extra_unwrapped_label_is_not_exempted(self):
        tr = list(self.TR)
        tr[2] = "**注.** 被从 `>` 里拆出来了"        # 源侧这条是包裹的 → 族失衡
        self.assertNotEqual(sorted(top_label_families(self.SRC)),
                            sorted(top_label_families(tr)))
        got = cq._run_format_verify_unit_checks(tr, self.SRC)
        self.assertTrue(any(MBQ_ERR_MARK in p for p in got), got)

    def test_check_body_passes_src_body_through(self):
        ok, probs = cq.check_body("desc", "D28", "\n".join(self.TR),
                                  translation=True, src_body="\n".join(self.SRC))
        self.assertFalse([p for p in probs if MBQ_ERR_MARK in p], probs)


class TranslationSeparatorInheritance(unittest.TestCase):
    r"""缺口 3：I 层「`>` 标签块 → 顶层散文缺 `---`」在中英两侧不对称开块。

    `G_ITEM_BQ_HEAD_RE` 的关键词表要求关键词**紧跟** `**`（或中文定中倒装收尾），
    英文「Alternate proof.」（ch4/0010 印面写法）不开块 → 源侧不追分隔线；
    中文同位「另一证明。」命中倒装支 → 译文被要求插入**源里没有**的 `---`，
    两版结构分叉，译者只能自撰一条源书不存在的分隔线才过闸。
    ⇒ 与必包豁免同口径：**以源单元结构为真值**——译文里「`> **标签**` 块 → 顶层
    散文（中间无 `---`）」的语言无关指纹处数与源侧相等时放行；译者自己漏了源里
    在位的 `---` 时两侧不等 → 照旧 FAIL。
    """

    # 英文源：关键词后置证明头 → I 层不开块（指纹仍数得到该结构位置）
    SRC_NOSEP = [
        "> **Alternate proof.** A shorter proof is available.",
        "> Take $f$ monotonically increasing and integrate by parts.",
        "",
        "Note. Since $t < 1$ the integral converges.",
        "",
    ]
    # 中文译文：逐位照抄源结构（源无 `---`，译文也不加）
    TR_MIRROR = [
        "> **另一证明。** 更短的证明如下。",
        "> 取 $f$ 单调递增并分部积分。",
        "",
        "注. 由于 $t < 1$，该积分收敛。",
        "",
    ]
    # 英文源：块与散文之间有 `---`
    SRC_WITH_SEP = [
        "> **Alternate proof.** A shorter proof is available.",
        "> Take $f$ monotonically increasing and integrate by parts.",
        "",
        "---",
        "",
        "Note. Since $t < 1$ the integral converges.",
        "",
    ]

    def test_structure_fingerprint_is_language_neutral(self):
        self.assertEqual(bq_label_block_then_prose(self.SRC_NOSEP),
                         bq_label_block_then_prose(self.TR_MIRROR))

    def test_source_side_cn_unit_is_still_flagged(self):
        # 无源上下文（源单元侧）→ 缺分隔线照报，确认这确是一条真实 FAIL 而非静默
        got = cq._run_format_verify_unit_checks(self.TR_MIRROR)
        self.assertTrue(any(ISEP_ERR_MARK in p for p in got), got)

    def test_translation_inherits_absent_separator(self):
        got = cq._run_format_verify_unit_checks(self.TR_MIRROR, self.SRC_NOSEP)
        self.assertFalse([p for p in got if ISEP_ERR_MARK in p], got)

    def test_dropped_separator_is_not_exempted(self):
        # 源里有 `---`，译文把它删掉 → 指纹不等 → 照旧 FAIL
        self.assertNotEqual(bq_label_block_then_prose(self.SRC_WITH_SEP),
                            bq_label_block_then_prose(self.TR_MIRROR))
        got = cq._run_format_verify_unit_checks(self.TR_MIRROR, self.SRC_WITH_SEP)
        self.assertTrue(any(ISEP_ERR_MARK in p for p in got), got)

    def test_check_body_passes_src_body_through_for_separator(self):
        ok, probs = cq.check_body("item", "定理4.2", "\n".join(self.TR_MIRROR),
                                  translation=True,
                                  src_body="\n".join(self.SRC_NOSEP))
        self.assertFalse([p for p in probs if ISEP_ERR_MARK in p], probs)


class PairedSourceBodyLookup(unittest.TestCase):
    """配对源单元的**唯一**路径推导（落账证据趟与门控趟共用）。

    Apostol《解析数论导引》2026-09-29 实测：`gate_units --units-dir units-translate`
    15 章 exit 0，`flow_runner verify` 却报 ch2/0077 必包 FAIL —— 根因是
    `_flow_contract._units_gate_ok` 从不加载源单元正文，两条译文结构继承豁免
    （`top_label_families` / `bq_label_block_then_prose`，判据本体在 format_verify）
    在落账趟恒不生效。
    """

    SRC = ["<!-- book-summarizer DONE unit: id=0077 type=desc key=D28 name= -->",
           "**Definition.** A function $I$ is additive.", "", "**Examples.** $I(n) = 0$.", ""]
    TR = ["<!-- book-summarizer DONE unit: id=0077 type=desc key=D28 name= -->",
          "**定义.** 若 $I$ 满足…则称其为可加的。", "", "**例.** $I(n) = 0$。", ""]

    def setUp(self):
        import tempfile
        self.tmp = tempfile.mkdtemp()
        self.ex = os.path.join(self.tmp, "book_structure")
        for sub, lines in (("units", self.SRC), ("units-translate", self.TR)):
            d = os.path.join(self.ex, sub, "ch2")
            os.makedirs(d)
            with open(os.path.join(d, "0077_desc_D28.md"), "w",
                      encoding="utf-8") as f:
                f.write("\n".join(lines))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_translation_dir_yields_source_body_without_marker(self):
        got = cq.paired_source_body(os.path.join(self.ex, "units-translate", "ch2"),
                                    "0077_desc_D28.md")
        self.assertIsNotNone(got)
        self.assertNotIn("book-summarizer", got)
        self.assertIn("**Definition.**", got)

    def test_source_dir_is_not_paired(self):
        # 源单元侧没有「继承」概念 → None，绝不把自身当源（否则豁免会对源侧也放行）
        self.assertIsNone(cq.paired_source_body(
            os.path.join(self.ex, "units", "ch2"), "0077_desc_D28.md"))

    def test_missing_source_file_returns_none(self):
        self.assertIsNone(cq.paired_source_body(
            os.path.join(self.ex, "units-translate", "ch2"), "0099_desc_D99.md"))

    def test_inheritance_actually_fires_through_the_lookup(self):
        # 正向：源/译族集合对齐 → 必包报错消失
        src_body = cq.paired_source_body(
            os.path.join(self.ex, "units-translate", "ch2"), "0077_desc_D28.md")
        tr_path = os.path.join(self.ex, "units-translate", "ch2", "0077_desc_D28.md")
        with open(tr_path, encoding="utf-8") as f:
            tr_body = cq._UNIT_MARK_LINE_RE.sub("", f.read(), count=1).strip("\n")
        ok, probs = cq.check_body("desc", "", tr_body, translation=True,
                                  src_body=src_body)
        self.assertFalse([p for p in probs if MBQ_ERR_MARK in p], probs)
        # 负向：去掉源上下文（= 本轮 bug 的落账趟形态）→ 同一条照旧报错
        ok2, probs2 = cq.check_body("desc", "", tr_body, translation=True)
        self.assertTrue(any(MBQ_ERR_MARK in p for p in probs2), probs2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
