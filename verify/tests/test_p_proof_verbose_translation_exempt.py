"""Regression tests for the Tier-3 proof gate's TRANSLATION exemption
(`verbose_gates.is_translated_md` / `check_verbose_proofs(..., translation=)`).

2026-09-29 Iwaniec–Kowalski《Analytic Number Theory》ch7 unit 0050 incident:
the CN translate unit mirrors its frozen EN source byte-for-byte in structure
(`> **Sketch of proof.**` → `> **证明（梗概）。**`, a 2992-char prose proof with
no step labels).  The EN source PASSES the gate only because `PROOF_OPEN_RE`
lists `Proof sketch` and therefore never matches the printed word order
`Sketch of proof`; the CN side matches `证明` and got FAILed.  The gate then
demanded the translator restructure the source's own undivided argument into
`1. 2. 3.` — i.e. a gate that can only be satisfied by diverging from the
already-verified source is a gate bug, not a content defect.

Pinned here:
  * translated md (non-CN source book, `第/附/补` filename) → proof gate silent;
  * source md (EN filename, or a CN-authored book) → gate still fires;
  * the EN-side `Sketch of proof` vocabulary hole (known backlog, not a
    regression to introduce silently) — if someone adds it to PROOF_OPEN_RE,
    this test must be updated together with a cross-book census.
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "verify", "verbose_gates", "script"),
           os.path.join(_ROOT, "verify", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from verbose_gates import (PROOF_OPEN_RE, check_verbose_proofs,  # noqa: E402
                          is_translated_md)

# undivided prose proof block, comfortably over VERBOSE_PROOF_CHARS (700)
_SENT = ("the construction proceeds by assigning bounds to each incomplete sum "
         "and checking every hypothesis carefully so that the claim follows. ")
_WALL = (_SENT * 13).strip()
_CN_WALL = "证明思路如下：对每一个不完备和逐项估计界，并逐条核对全部假设，" \
           "于是结论成立；" * 30


def _block(open_label, wall):
    lines = ["> " + open_label]
    lines += ["> " + chunk for chunk in wall.split(". ")]
    return lines


class TestTranslationExemption(unittest.TestCase):
    def test_cn_proof_wall_fires_when_self_authored(self):
        out = check_verbose_proofs(_block("**证明（梗概）。**", _CN_WALL))
        self.assertEqual(len(out), 1, out)

    def test_cn_proof_wall_exempt_when_translation(self):
        lines = _block("**证明（梗概）。**", _CN_WALL)
        self.assertEqual(check_verbose_proofs(lines, translation=True), [])

    def test_en_proof_wall_still_fires_when_translation_flag_absent(self):
        # 镜像同一块：源侧（translation=False）不因新参数而放宽
        out = check_verbose_proofs(_block("**Proof.**", _WALL))
        self.assertEqual(len(out), 1, out)


class TestIsTranslatedMd(unittest.TestCase):
    def test_en_book_cn_md_is_translation(self):
        self.assertTrue(is_translated_md("第一章 解析导引.md", "en"))
        self.assertTrue(is_translated_md("附录A 习题提示.md", "en"))
        self.assertTrue(is_translated_md("补充 记号表.md", "en"))

    def test_en_book_en_md_is_source(self):
        self.assertFalse(is_translated_md("Chapter 7. Kloosterman sums.md", "en"))
        self.assertFalse(is_translated_md("Appendix B.md", "en"))

    def test_cn_book_never_translation(self):
        # 中文源书的 md 就是自撰文本，闸门照常生效
        self.assertFalse(is_translated_md("第一章 集合.md", "cn"))
        self.assertFalse(is_translated_md("第一章 集合.md", None))
        self.assertFalse(is_translated_md("第一章 集合.md", ""))

    def test_missing_filename_is_source(self):
        self.assertFalse(is_translated_md(None, "en"))
        self.assertFalse(is_translated_md("", "en"))

    def test_merged_section_view_carries_language(self):
        # 按节拆分章的合并临时视图：语言必须编进文件名，否则中文侧失去译版身份
        # （本书 ch7/ch15 的 `**证明梗概。**` 假阳即由此而来）。
        self.assertTrue(is_translated_md("._verify_merged_ch15_cn.md", "en"))
        self.assertTrue(is_translated_md("._verify_merged_appendixA_cn.md", "en"))
        self.assertFalse(is_translated_md("._verify_merged_ch15_en.md", "en"))

    def test_merged_view_path_is_produced_per_language(self):
        import tempfile

        from verify_chapter import _merged_temp_path
        with tempfile.TemporaryDirectory() as d:
            cn = os.path.join(d, "第15章_15.7_塞尔伯格迹公式.md")
            en = os.path.join(d, "Chapter15_15.7_TheSelbergtraceformula.md")
            for fp in (cn, en):
                with open(fp, "w", encoding="utf-8") as f:
                    f.write("# 标题\n\n正文\n")
            p_cn = _merged_temp_path(d, "15", [cn])
            p_en = _merged_temp_path(d, "15", [en])
            self.assertNotEqual(p_cn, p_en, "两个语言的临时视图不得同名")
            self.assertTrue(is_translated_md(p_cn, "en"))
            self.assertFalse(is_translated_md(p_en, "en"))


class TestProofOpenReVocabularyHole(unittest.TestCase):
    """Characterization test for the EN/CN vocabulary asymmetry (deferred backlog)."""

    def test_cn_side_matches_sketch_of_proof_family(self):
        self.assertTrue(PROOF_OPEN_RE.search("> **证明（梗概）。** ..."))
        self.assertTrue(PROOF_OPEN_RE.search("> **证明梗概** ..."))

    def test_en_side_order_proof_sketch_matches(self):
        self.assertTrue(PROOF_OPEN_RE.search("> **Proof sketch.** ..."))

    def test_en_side_order_sketch_of_proof_DOES_NOT_match(self):
        # 🔴 已知缺口：印刷体 `**Sketch of proof.**` 词序相反 → 源单元漏检。
        # 补进词表会新罚已收官英文书的源单元（Tier-3 未分条长证明），
        # 须先跨书普查并报 backlog 再动，故本用例锁死现状。
        self.assertIsNone(PROOF_OPEN_RE.search("> **Sketch of proof.** ..."))


if __name__ == "__main__":
    unittest.main(verbosity=2)
