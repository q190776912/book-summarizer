# -*- coding: utf-8 -*-
"""内容挂载锚点的「正文带优先」判据测试（`build_structure._band_split_y`）。

立项缺陷（2026-09-28 Arnold《经典力学的数学方法》中文扫描版 p240 实测）：同一页眉
复本问题在**锚点解析**这一路还有第二个消费者。`attach_content._section_anchor` 拿
`_find_title_pos` / `_numbered_heading_y` 定节头位置，两者都是「同页命中取最小 y /
取块序第一个命中」——页眉每页重印本节标题，恒排在真节头**前面**：

    p240  idx 0   x=530,  y=119    'S52.摄动的平均化'   ← 页眉复本
    p240  idx 20  x=126,  y=1032   '$52．摄动的平均化'  ← 真节头（左边界）

于是 §52 的锚点被提到 (240, 119)：同页页眉之下的**上一节尾料**（问题/系/证/例1/例2，
y=208..935）整片灌进 §52，而章末末条目的尾随散文（p245..248）无上界挂到 §51 →
`ANCHOR-SANITY` 前序页码回归（契约根本写不出来）。

判据与 `scan_skeleton.is_running_head` **同源一份**（检测/采纳两侧共用同一谓词，
不留第二套页眉规则）：同页命中先按页眉带分组，**有正文命中就用正文最小 y**，
全是页眉时回落到页眉 y（跨页节的续页只有页眉，回落保证节仍有锚点）。

负向锁死：① 无正文命中时不得返回 None（否则节失去锚点、内容整片错位）；
② `_numbered_heading_y` 只服务**带点**序标（`_NUM_KEY_RE`），裸全局节号（本书的
"52"）按设计返回 None 让位给标题词搜索——放开这个门槛会让「2 个关系…」这类
正文行首数字当成节头，故此处以测试钉住现状，改动必须是显式的。

Runs under stdlib unittest:
  python flows/write-source/structure/script/tests/test_anchor_band_preference.py
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
import lib.boot as _boot                # noqa: E402
_boot.setup()

from build_structure import (           # noqa: E402
    _band_split_y, _find_title_pos, _numbered_heading_y)


def _blk(text, x, y, right=1133.0, h=38.0):
    """OCR 文本块（单栏：右边界恒等于 `right`，页宽跨度才可信；见同族测试
    `test_running_head_band._blk` 的说明）。"""
    return {"text": text,
            "poly": [x, y, right, y, right, y + h, x, y + h]}


class TestBandSplitY(unittest.TestCase):
    def test_body_hit_beats_smaller_header_y(self):
        """实测 p240：页眉 (530,119) 与真节头 (126,1032) 同时命中 → 取 1032。"""
        blocks = [_blk("S52.摄动的平均化", 530, 119),
                  _blk("·225·", 1087, 117),
                  _blk("$52．摄动的平均化", 126, 1032)]
        hits = [(530.0, 119.0), (1087.0, 117.0), (126.0, 1032.0)]
        self.assertEqual(_band_split_y(hits, blocks), 1032.0)

    def test_only_header_hits_falls_back(self):
        """负向①：本页只有页眉命中时回落页眉 y，不得返回 None。

        页上另有一个左对齐正文块（不是命中）用来定左边界——没有它整页都是页眉，
        1/4 页宽阈值失去参照，右移判据就只是「碰巧」。
        """
        blocks = [_blk("3.2 The big oh notation", 530, 119),
                  _blk("·7·", 1087, 117),
                  _blk("正文散文与本节无关", 126, 300)]
        self.assertEqual(_band_split_y([(530.0, 119.0)], blocks), 119.0)

    def test_smallest_body_y_wins(self):
        blocks = [_blk("a", 126, 300), _blk("b", 126, 200), _blk("c", 530, 119)]
        self.assertEqual(_band_split_y([(126.0, 300.0), (126.0, 200.0),
                                        (530.0, 119.0)], blocks), 200.0)

    def test_empty_hits_is_none(self):
        self.assertIsNone(_band_split_y([], [_blk("a", 126, 300)]))

    def test_missing_geometry_fails_open_to_min_y(self):
        """块无 poly（老提取器输出）→ 页眉无从判定，fail-open 取最小 y（宁闩不漏）。"""
        blocks = [{"text": "3.2 x"}, {"text": "3.2 y"}]
        self.assertEqual(_band_split_y([(700.0, 60.0), (100.0, 400.0)], blocks),
                         60.0)


class TestNumberedHeadingY(unittest.TestCase):
    """带点序标的小节头 y（Koopman/Apostol 那一路）同样要避开页眉。"""

    @staticmethod
    def _page(blocks, page=42):
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "page_%03d.json" % page), "w",
                  encoding="utf-8") as f:
            json.dump({"text": blocks, "formulas": []}, f)
        return d

    def test_header_row_loses_to_body_heading(self):
        d = self._page([_blk("3.2 The big oh notation", 530, 119),
                        _blk("·7·", 1087, 117),
                        _blk("3.2 The big oh notation and asymptotic equality",
                             126, 1103)])
        self.assertEqual(_numbered_heading_y(d, "3.2", 42), 1103.0)

    def test_glued_ocr_variant_still_matches(self):
        """粘连形态（`3.2Continuous-Time…`，无空格）照旧命中。"""
        d = self._page([_blk("3.2Continuous-Time Systems", 126, 1490)])
        self.assertEqual(_numbered_heading_y(d, "3.2", 42), 1490.0)

    def test_bare_global_section_key_defers_to_title_search(self):
        """负向②（钉现状）：裸号 "52" 不走编号锚定，返回 None。

        `_NUM_KEY_RE` 要求带点序标；本书的 §1..§52 是裸全局节号，锚点一律由
        `_find_title_pos` 决定（本类的下一组用例）。放宽门槛 = 把正文行首数字
        （'2 个关系…'）当节头，属需显式评审的改动。
        """
        d = self._page([_blk("$52．摄动的平均化", 126, 1032)])
        self.assertIsNone(_numbered_heading_y(d, "52", 42))

    def test_missing_page_is_none(self):
        self.assertIsNone(_numbered_heading_y(tempfile.mkdtemp(), "3.2", 99))


class TestFindTitlePos(unittest.TestCase):
    """`_find_title_pos` 三段匹配（Pass 1a 锚定 / Pass 1b 包含）都要正文带优先。"""

    @staticmethod
    def _dir(pages):
        d = tempfile.mkdtemp()
        for p, blocks in pages.items():
            with open(os.path.join(d, "page_%03d.json" % p), "w",
                      encoding="utf-8") as f:
                json.dump({"text": blocks, "formulas": []}, f)
        return d

    def test_pass1b_containment_skips_header(self):
        """实测 p240 形态：节名（不带序标，契约里的 `name`）同时出现在页眉与真
        节头里，块序页眉在前 → 取真节头。

        旧 Pass 1b「返回块序第一个命中」正是把 §52 钉到页顶的那条规则。两条 OCR
        行都带 `S52.`/`$52．` 前缀，故 Pass 1a 的 `^节名` 锚定两边都不命中，
        必然落到包含匹配这一路（本书裸全局节号的锚点解析实况）。
        """
        d = self._dir({240: [_blk("S52.摄动的平均化", 530, 119),
                             _blk("·225·", 1087, 117),
                             _blk("$52．摄动的平均化", 126, 1032)]})
        self.assertEqual(_find_title_pos(d, "摄动的平均化", 240, 240),
                         (240, 1032.0))

    def test_pass1a_anchored_head_wins_over_header(self):
        d = self._dir({42: [_blk("3.2 The big oh notation", 530, 119),
                            _blk("·7·", 1087, 117),
                            _blk("3.2 The big oh notation", 126, 1103)]})
        self.assertEqual(_find_title_pos(d, "3.2 The big oh notation", 42, 42),
                         (42, 1103.0))

    def test_earlier_page_still_wins(self):
        """带优先只在**同页**内比较：前一页的真命中仍先于后一页。"""
        d = self._dir({41: [_blk("3.2 The big oh notation", 126, 900)],
                       42: [_blk("3.2 The big oh notation", 530, 119),
                            _blk("3.2 The big oh notation", 126, 1103)]})
        self.assertEqual(_find_title_pos(d, "3.2 The big oh notation", 41, 42),
                         (41, 900.0))

    def test_header_only_page_still_returns_a_position(self):
        """负向：整段区间只剩页眉命中时仍给出位置（有锚点比没有好）。

        页上另配左对齐正文块定左边界，使页眉确实被 `is_running_head` 命中。
        """
        d = self._dir({43: [_blk("3.2 The big oh notation", 530, 119),
                            _blk("Some body prose line", 126, 400)]})
        self.assertEqual(_find_title_pos(d, "3.2 The big oh notation", 43, 43),
                         (43, 119.0))

    def test_no_hit_is_none(self):
        d = self._dir({43: [_blk("无关正文", 126, 400)]})
        self.assertIsNone(_find_title_pos(d, "3.2 The big oh notation", 43, 43))


if __name__ == "__main__":
    unittest.main(verbosity=2)
