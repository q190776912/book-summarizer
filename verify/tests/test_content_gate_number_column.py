# -*- coding: utf-8 -*-
"""内容完整性闸门 ②b 的**编号列几何闸**与**噪声形态**判据（2026-09-30 Evans《PDE》）。

根因：Evans 附录B（p714–718）印面公式编号是 `(1)…(18)`，全部排在**左缘同一列**
（x0≈178–189 / 200dpi 像素）。扫描本 OCR 把**公式内部**的数字切成独立裸块：
`b^q/q` → `69`（p715 x0=1067）、`b²/4ε` → `62`（p715 x0=612）、`η(0)` → `(0)`
（p717 x0=688）。契约侧闸门 ⑭（`lib.tag_attestation._condemned` 的 `bare-only`）
按「本章编号以 `(N)` 为主 ⇒ 裸数字块多半是公式内部碎片」把 `69` 从契约剔除（判得
**对**，fitz 目视印面已确认），但 `_source_formula_tags` 另起一套只看文本形态的判据
照收 → 源/契约不对称 → `CONTENT GATE: FAIL 公式编号丢失 ['69']`，步骤 4 拆分被一个
**不存在的**内容丢失阻断（还会诱导写手凭空 `\\tag{69}`）。

根治 = 两侧共用同一条**几何**证据：从页窗里「整块恰为 `(N)`」的高可信锚点学出编号列
（`lib.tag_attestation.number_column`），列**外**的裸排候选判为残渣；`(0)` / 前导零 /
节内重置书的 ≥3 位纯数字走 `lib.numbering.formula_tag_noise`（与 attach 侧同一判据）。

运行：
  python verify/tests/test_content_gate_number_column.py
"""
import json
import os
import shutil
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

import check_content_completeness as ccc  # noqa: E402

FOOTER_Y = 1700.0      # 设定页高（≈1728），使 12%/90% 页边带不吞正文


def _blk(text, y, x=120.0, h=28.0):
    return {"text": text,
            "poly": [x, y, x + 120, y, x + 120, y + h, x, y + h]}


def _body(y=900.0, x=300.0):
    return _blk("some body paragraph text of the chapter here", y, x=x)


class _Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ccc_num_col_")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _tags(self, pages, ncomp=1, **kw):
        for p, blocks in pages.items():
            with open(os.path.join(self.tmp, "page_%03d.json" % p), "w",
                      encoding="utf-8") as f:
                json.dump({"text": blocks}, f)
        return ccc._source_formula_tags(self.tmp, 1, max(pages), "", ncomp,
                                        letter=False, bare=True, **kw)


class TestColumnGateEvansAppendixB(_Base):
    """正判据：`(N)` 成列时，列外裸数字块是公式内部残渣，不进序标真值集。"""

    def test_out_of_column_bare_debris_excluded(self):
        pages = {
            1: [_blk("(1)", 400.0, x=180), _blk("(2)", 700.0, x=182),
                _body(), _blk("footer", FOOTER_Y)],
            2: [_blk("(3)", 400.0, x=178), _blk("(4)", 700.0, x=178),
                _blk("69", 1283.0, x=1067),        # b^q/q 的 OCR 残渣
                _body(), _blk("footer", FOOTER_Y)],
            3: [_blk("(5)", 400.0, x=180),
                _blk("62", 754.0, x=612),          # b²/4ε 的 OCR 残渣
                _body(), _blk("footer", FOOTER_Y)],
            4: [_blk("(6)", 400.0, x=178), _body(), _blk("footer", FOOTER_Y)],
            5: [_blk("(7)", 400.0, x=185), _body(), _blk("footer", FOOTER_Y)],
        }
        got = self._tags(pages)
        self.assertEqual(got, {"1", "2", "3", "4", "5", "6", "7"},
                         "列外裸块 69/62 不得进入序标真值集（否则闸门把 ⑭ 的正确剔除"
                         "报成『公式编号丢失』）：%s" % got)

    def test_in_column_bare_number_still_accepted(self):
        # 反例（防过度剔除）：同一列里的裸块可能是**真编号被 OCR 漏读括号**，
        # 列内一律收录。
        pages = {
            1: [_blk("(1)", 400.0, x=180), _blk("(2)", 700.0, x=182),
                _blk("3", 1000.0, x=181), _body(), _blk("footer", FOOTER_Y)],
            2: [_blk("(4)", 400.0, x=178), _body(), _blk("footer", FOOTER_Y)],
            3: [_blk("(5)", 400.0, x=185), _body(), _blk("footer", FOOTER_Y)],
        }
        got = self._tags(pages)
        self.assertIn("3", got, "编号列内的裸排块须按真编号收录：%s" % got)

    def test_column_learned_from_right_margin_too(self):
        # 列不写死左右：右缘编号的书（`(N)` 在 x=1450）学到右缘，正文区里的裸块出局。
        pages = {
            1: [_blk("(1)", 400.0, x=1450), _blk("(2)", 700.0, x=1452),
                _body(), _blk("footer", FOOTER_Y)],
            2: [_blk("(3)", 400.0, x=1448), _blk("69", 405.0, x=612),
                _body(), _blk("footer", FOOTER_Y)],
            3: [_blk("(4)", 400.0, x=1450), _body(), _blk("footer", FOOTER_Y)],
        }
        got = self._tags(pages)
        self.assertEqual(got, {"1", "2", "3", "4"}, "%s" % got)


class TestColumnGateStaysQuiet(_Base):
    """列学不出来时**完全不生效**：既往行为逐字保持（近半数书是纯裸排编号）。"""

    def test_pure_bare_numbering_unaffected(self):
        pages = {
            1: [_blk("1", 400.0, x=1450), _blk("2", 700.0, x=1450),
                _body(), _blk("footer", FOOTER_Y)],
            2: [_blk("3", 400.0, x=1450), _blk("4", 900.0, x=612),
                _body(), _blk("footer", FOOTER_Y)],
            3: [_blk("5", 400.0, x=1450), _body(), _blk("footer", FOOTER_Y)],
        }
        got = self._tags(pages)
        self.assertEqual(got, {"1", "2", "3", "4", "5"},
                         "无 `(N)` 种子时不得引入任何几何筛选：%s" % got)

    def test_fewer_than_three_seeds_does_not_learn_a_column(self):
        pages = {
            1: [_blk("(1)", 400.0, x=1450), _blk("69", 1283.0, x=1067),
                _body(), _blk("footer", FOOTER_Y)],
            2: [_blk("(2)", 400.0, x=1450), _body(), _blk("footer", FOOTER_Y)],
        }
        got = self._tags(pages)
        self.assertEqual(got, {"1", "2", "69"},
                         "样本 <3 时 number_column 不出结论，列闸不得生效：%s" % got)


class TestNoiseFormSharedWithAttachSide(_Base):
    """`(0)` / 前导零 / 节内重置书的 ≥3 位纯数字：与 attach 侧同判据。"""

    def _pages(self):
        return {
            1: [_blk("(1)", 400.0, x=180), _blk("(0)", 700.0, x=182),
                _body(), _blk("footer", FOOTER_Y)],
            2: [_blk("(2)", 400.0, x=178), _blk("(07)", 700.0, x=178),
                _body(), _blk("footer", FOOTER_Y)],
            3: [_blk("659", 400.0, x=181), _body(), _blk("footer", FOOTER_Y)],
        }

    def test_zero_and_leading_zero_never_ordinals(self):
        got = self._tags(self._pages())
        self.assertNotIn("0", got, "没有任何书给公式印 `(0)`：%s" % got)
        self.assertNotIn("07", got, "前导零形态是 OCR 噪声：%s" % got)

    def test_long_bare_number_dropped_only_when_section_scoped(self):
        # scope=3（编号节内重置）→ 计数器到不了一百，三位纯数字是表格单元/页码碎片；
        # scope=1/2（全书/跨章连续）→ 三位号可能是真的，不得动。
        got_scoped = self._tags(self._pages(), section_scoped=True)
        self.assertNotIn("659", got_scoped, "%s" % got_scoped)
        got_plain = self._tags(self._pages())
        self.assertIn("659", got_plain,
                      "非节内重置体例不得套用三位数噪声判据：%s" % got_plain)


if __name__ == "__main__":
    unittest.main(verbosity=2)
