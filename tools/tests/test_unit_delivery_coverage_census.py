"""test_unit_delivery_coverage_census.py — 「单元 → 交付 单向覆盖」普查判据的回归。

本工具**只报不拦**（交付在 merge 之后按印面手修是正确结果，等式闸会把正确交付判违规、
逼代理回抄单元里的 OCR 粘连形）。正因它靠人工看报告，判据里那三处「放行」必须有负向
测试锁住，否则工具会悄悄把真丢失也放行掉：

1. 排版脚手架（`array`/`&`/`\\\\`/`\\left`）差异放行 —— 但同一块被砍半截仍须报；
2. `\\tag` 形态差异记为 TAG_FORM（不算丢失）；
3. `merge: false` 的单元（V-I 集中习题块）不进候选；
4. 交付侧**不按文件名 ASCII 分侧**（EN 交付文件名带弯引号时不得漏查）；
5. 真分叉（单元残留 `4,1` 而交付是 `4.1`）仍须报出来 —— 防止「放行」把工具变成空壳。

Run with stdlib unittest:
    python tools/tests/test_unit_delivery_coverage_census.py
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
           os.path.join(_ROOT, "tools"),
           os.path.join(_ROOT, "flows", "write-source", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import census_unit_delivery_coverage as cuc

# Fraleigh ch29/0034（印面 Example 30.1）实测形态：单元 = array 对齐式，交付 = 行内散文式
UNIT_ARRAY = ("$$\n\\begin{array}{lcl}\n"
              "a'b' &=& (a + nk)(b + nr) \\\\\n"
              "     &=& ab + n(kb + knr + ar) \\in ab + n\\mathbb{Z}.\n"
              "\\end{array}\n$$\n")
DELIVERY_INLINE = ("**Example 30.1.** Thus $a'b' = (a + nk)(b + nr) = ab + n(kb + knr + ar)"
                   " $\\in ab + n\\mathbb{Z}$.\n")


def _hay(text):
    return {"raw": cuc._flatten_math(text), "shape": cuc.shape_norm(cuc._flatten_math(text)),
            "tags": set(cuc.TAG_RE.findall(text))}


class ShapeAndTag(unittest.TestCase):
    def test_array_alignment_form_not_flagged(self):
        self.assertIsNone(cuc.block_problems(
            cuc.DISPLAY_RE.findall(UNIT_ARRAY)[0], _hay(DELIVERY_INLINE), "x.md"))

    def test_shape_norm_does_not_mask_truncation(self):
        """放行只认**完整**内核：同一 array 式在交付里只剩前半仍须报。"""
        p = cuc.block_problems(cuc.DISPLAY_RE.findall(UNIT_ARRAY)[0],
                               _hay("Thus $a'b' = (a + nk)$ is clear.\n"), "x.md")
        self.assertIsNotNone(p)
        self.assertEqual(p["kind"], "BLOCK_LOST")

    def test_tag_form_divergence_is_not_loss(self):
        """单元 `\\tag{1.2}` vs 交付 `\\tag{I.2}`：块体在交付里对得上 = TAG_FORM。"""
        blk = "$$\n0\\leq\\xi_{1}\\leq\\ldots\\leq\\eta_{q}\\leq1\\tag{1.2}\n$$\n"
        hay = _hay("$$\n0\\leq\\xi_{1}\\leq\\ldots\\leq\\eta_{q}\\leq1\\tag{I.2}\n$$\n")
        p = cuc.block_problems(blk, hay, "0009_item.md")
        self.assertEqual(p["kind"], "TAG_FORM")

    def test_absent_block_is_flagged_absent(self):
        blk = "$$\n\\int_X\\int_Y\\chi_D(x,y)\\mu(dy)m(dx)\\neq\\int_Y\\int_X\\chi_D(x,y)m(dx)\\mu(dy).\n$$\n"
        p = cuc.block_problems(blk, _hay("**定理 5.1**：$a+b=c$ 成立。\n"), "0025_item.md")
        self.assertEqual((p["kind"], p["bucket"]), ("BLOCK_LOST", "ABSENT"))

    def test_unit_side_stale_numbering_still_reported(self):
        """数值分析 ch2/0057 实测：单元残留 OCR 的欧式逗号 `27,7`/`4,1`，交付已按印面写成
        `27.7`/`4.1` → 是**分叉**，必须进候选（工具不是只会被放行拖空）。"""
        blk = "$$\nf(x_{0})=f(27,7)=4,1,\\quad f(x_{1})=f(28)=4.3,\n$$\n"
        p = cuc.block_problems(blk, _hay("$$\nf(x_0)=f(27.7)=4.1,\\quad f(x_1)=f(28)=4.3.\n$$\n"),
                               "0057_item.md")
        self.assertIsNotNone(p)
        self.assertEqual(p["kind"], "BLOCK_LOST")


class ScanBook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bks_cov_")
        self.book = Path(self.tmp)
        (self.book / "_extract" / "book_structure" / "units" / "ch10").mkdir(parents=True)

    def tearDown(self):
        for p in sorted(Path(self.tmp).rglob("*"), reverse=True):
            try:
                os.rmdir(str(p)) if p.is_dir() else os.remove(str(p))
            except OSError:
                pass

    def _write_units(self, names_blocks, extra_recs=None):
        udir = self.book / "_extract" / "book_structure" / "units" / "ch10"
        recs = []
        for i, (fname, blk) in enumerate(names_blocks):
            (udir / fname).write_text("<!-- book-summarizer DONE unit: id=%04d type=exercise "
                                      "key=k name= -->\n%s\n" % (i, blk), encoding="utf-8")
            r = {"file": fname, "id": "%04d" % i, "type": "exercise", "key": "k", "name": ""}
            if extra_recs:
                r.update(extra_recs(i))
            recs.append(r)
        (udir / "manifest.json").write_text(json.dumps({"units": recs}, ensure_ascii=False),
                                            encoding="utf-8")

    def test_merge_false_unit_is_skipped(self):
        """V-I：集中习题块 `merge: false` → 本就不进交付，不得算丢失。"""
        self._write_units([("0016_exercise_10-1.md",
                            "$$\n\\mu(\\{x:|f_n(x)-f_m(x)|>a\\})<\\varepsilon.\n$$")],
                          extra_recs=lambda i: {"merge": False})
        (self.book / "Chapter10_Types.md").write_text("# 第10章\n\n**定理 10.8**：$a\\leq b$。\n",
                                                     encoding="utf-8")
        self.assertEqual(cuc.scan_book(str(self.book)), [])

    def test_merged_unit_missing_from_delivery_is_caught(self):
        """同一单元去掉 `merge: false`（= 应进交付）→ 必须进候选。"""
        self._write_units([("0016_exercise_10-1.md",
                            "$$\n\\mu(\\{x:|f_n(x)-f_m(x)|>a\\})<\\varepsilon.\n$$")])
        (self.book / "Chapter10_Types.md").write_text("# 第10章\n\n**定理 10.8**：$a\\leq b$。\n",
                                                     encoding="utf-8")
        probs = cuc.scan_book(str(self.book))
        self.assertEqual([p["kind"] for p in probs], ["BLOCK_LOST"])

    def test_delivery_with_non_ascii_file_name_is_still_searched(self):
        """🔴 分侧 bug 回归：EN 交付文件名带弯引号时曾被划成中文版而漏查 → 整书虚报。"""
        self._write_units([("0004_desc_D2.md", "$$\nf_{t} = \\frac{D}{2} f_{xx}.\n$$")])
        (self.book / u"Chapter3_Brownian_Motion_and_\u201cWhite_Noise\u201d.md").write_text(
            "$$\nf_{t} = \\frac{D}{2} f_{xx}.\n$$\n", encoding="utf-8")
        (self.book / u"\u7b2c3\u7ae0_Brownian.md").write_text(
            "$$\nf_{t} = \\frac{D}{2} f_{xx}.\n$$\n", encoding="utf-8")
        self.assertEqual(cuc.scan_book(str(self.book), side="src"), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
