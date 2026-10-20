r"""E 层：**节级图号**（section-local figure numbering）的 CONFIRM-ONLY 识别
（Lehmann–Casella《Theory of Point Estimation》ch5/ch6 实测 2026-10）。

背景：有些书把图号印成 `节.序`（前导数是**本章内的节号**，不是章号）。Lehmann–Casella
即如此：ch5 的裁剪图标签是 `2.1 / 5.1 / 5.2`（分别是该章 §2、§5 的图），ch6 的是
`2.1`。多分量编号书（components==2）旧判据只认 `int(parts[0]) == ch`——前导数须等于
**章号**，于是这些前导数=节号（2、5）的真图**永远进不了 caption 集**，
`extra = extracted - caption` 遂把每张节级真图报成 FIGURE EXTRA（WARN）。

根治（`figure_completeness.py::check_figure` 的 components>=2 分支）：当前导数落在
**本章契约在册的顶层小节号集**（`_chapter_section_numbers`）内、且该号**已有同名裁剪
图**（`normfig(num) in extracted`）时，把它当作节级图题收入 caption——**只用于确认
已裁剪图**（clear 假阳 EXTRA），**绝不据 OCR 里出现却无裁剪图的号伪造 blocking
MISSING**。

为何 CONFIRM-ONLY（正向护栏不得变成盲区）：ch5 页 390 的 OCR 把 `Figure 5.2` 误读成
孤立的 `Figure 6.2`（该句正讨论 λ→∞ 的最大成分风险 = Figure 5.2）。若放宽到「前导数
∈ 节号就收进 caption」，`6.2` 会进 caption 却无裁剪图 → 凭空造出 blocking MISSING。
CONFIRM-ONLY 的 `and normfig(num) in extracted` 恰好挡住这种 OCR 误读号（无同名裁剪
→ 不收入 → 不产生 MISSING）。章号分支（`== ch`）原样不动，故真正的 `章.序` 缺图照旧
上报 MISSING。

断言：
  1. 节级裁剪图，其印面号在 OCR 出现 → **不报 EXTRA**（本闸修复目标）；
  2. OCR 里出现却无裁剪图的节级号（误读）→ **不报 MISSING**（不得伪造阻断）；
  3. 章号分支不回归：`== ch` 形态的缺图照旧 FAIL。
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

from verify.figure_completeness.script.figure_completeness import check_figure  # noqa: E402


def _write_cfg(ext, fig_type):
    with open(os.path.join(ext, "verify_config.json"), "w", encoding="utf-8") as f:
        json.dump({"ordinal": [{"name": ["图", "Figure"], "type": fig_type}],
                   "section_scoped": True}, f, ensure_ascii=False)


def _write_index(ext, entries):
    with open(os.path.join(ext, "figure_index.json"), "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False)


def _write_page(ext, pg, blocks):
    with open(os.path.join(ext, f"page_{pg:03d}.json"), "w", encoding="utf-8") as f:
        json.dump({"page": pg, "text": [{"text": t} for t in blocks],
                   "formulas": []}, f, ensure_ascii=False)


def _write_contract(ext, ch, section_keys):
    """Minimal per-chapter contract: chapter root with top-level `section` children
    keyed by `section_keys`, so `_chapter_section_numbers(ext, ch)` returns those
    leading integers."""
    d = os.path.join(ext, "book_structure")
    os.makedirs(d, exist_ok=True)
    root = {
        "key": str(ch), "type": "chapter", "name": f"ch{ch}",
        "page_start": 1, "page_end": 9999,
        "sub_sec": [{"key": sk, "type": "section", "name": f"§{sk}",
                     "sub_sec": []} for sk in section_keys],
    }
    with open(os.path.join(d, f"ch{ch}.json"), "w", encoding="utf-8") as f:
        json.dump(root, f, ensure_ascii=False)


class TestSectionLocalFigureConfirmOnly(unittest.TestCase):
    def setUp(self):
        self._d = tempfile.TemporaryDirectory()
        self.ext = self._d.name
        self.addCleanup(self._d.cleanup)
        # ch6 has sections 1..8 (Lehmann–Casella ch6 = §1..§8)
        _write_cfg(self.ext, 2)
        _write_contract(self.ext, 6, [str(i) for i in range(1, 9)])

    def test_section_local_crop_with_printed_caption_is_not_extra(self):
        """ch6 §2 的图印作 `Figure 2.1`，裁剪图标签 `2.1` 存在、OCR 也出现该题面
        → 修复前误报 EXTRA，修复后（CONFIRM-ONLY 确认同名裁剪）须豁免。"""
        _write_index(self.ext, [
            {"chapter": 6, "page": 470, "fig_idx": 1, "label": "2.1",
             "file": "figure/ch06_fig2.1.png", "caption": "Figure 2.1"}])
        _write_page(self.ext, 470, [
            "Figure 2.1. Comparison of the efficiencies", "some prose here"])
        res = check_figure(6, 470, 470, self.ext)
        self.assertEqual(res["extra"], [],
                         "节级真图（前导=节号）被印面题确认后不得报 EXTRA")
        self.assertEqual(res["missing"], [])

    def test_ocr_misread_section_local_number_does_not_fabricate_missing(self):
        """ch5 页 390 把 `Figure 5.2` 误读成孤立 `Figure 6.2`（无同名裁剪图）。
        CONFIRM-ONLY 只确认已有裁剪，绝不据误读号伪造 blocking MISSING。"""
        _write_cfg(self.ext, 2)
        _write_contract(self.ext, 5, [str(i) for i in range(1, 9)])
        _write_index(self.ext, [
            {"chapter": 5, "page": 391, "fig_idx": 2, "label": "5.2",
             "file": "figure/ch05_fig5.2.png", "caption": "Figure 5.2"}])
        _write_page(self.ext, 390, [
            "the maximum risk pr(λ) approaches as λ→",
            "Figure 6.2.",  # OCR mis-scan of Figure 5.2; no crop named 6.2
            "see Figure 5.2 for the component risk"])
        res = check_figure(5, 390, 391, self.ext)
        self.assertNotIn("6.2", res["missing"],
                         "误读出的节级号（无同名裁剪）不得凭空造出 MISSING")
        self.assertEqual(res["extra"], [], "真图 5.2 被确认后不得报 EXTRA")

    def test_chapter_qualified_missing_still_blocks(self):
        """章号分支（`== ch`）原样不动：`章.序` 形态的缺图照旧 FAIL——
        本闸放宽仅针对已确认裁剪的节级号，不得变成真丢图的盲区。"""
        _write_cfg(self.ext, 2)
        _write_contract(self.ext, 6, [str(i) for i in range(1, 9)])
        _write_index(self.ext, [
            {"chapter": 6, "page": 460, "fig_idx": 1, "label": "6.1",
             "file": "figure/ch06_fig6_1.png", "caption": "Figure 6.1"}])
        _write_page(self.ext, 460, [
            "Figure 6.1. a chapter-qualified figure",
            "另见 Figure 6.9 的构造"])  # 6.9 前导=章号 6，无裁剪 → 真缺图
        res = check_figure(6, 460, 460, self.ext)
        self.assertIn("6.9", res["missing"],
                      "章号前缀形态的缺图必须照旧上报（正向护栏不回归）")


if __name__ == "__main__":
    unittest.main(verbosity=2)
