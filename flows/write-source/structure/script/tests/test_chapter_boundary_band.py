# -*- coding: utf-8 -*-
"""章边界尾带回归测试（Etingof《Introduction to representation theory》实测）。

该书每一章的**起始页页首**都还印着上一章的收尾（章标题在页面中上部）：
  * p22 页首 = ch1 的 Problem 1.57 / 1.58
  * p31 页首 = ch2 的 **§2.10 整节**（Theorem 2.26 / Remark 2.27 及其证明）
  * p44 页首 = ch3 的 Problem 3.27
  * p73 页首 = ch4 的 **Theorem 4.75** 及其证明
  * p100 页首 = ch6 的 Definition 6.21 / Example 6.22 / 6.23
章图只到「页」的粒度，按整页归属时这些内容全被挂成**后一章的章首描述节点**，
于是前一章整节消失；D 层（比本章 § 集）与 B 层（比本章号空间）各查一边，
**两边都不报错**——全绿却缺整节。

本测试钉住 `chapter_boundary` 的三件事：
  ① 标题在页面中上部 → 给出裁剪线（`head_floor` / `tail_band` 两侧一致）；
  ② 标题就在页顶（正常书）→ 一律 None，历史行为逐字节不变（**负例**）；
  ③ `clip_page` 裁出的临时页只含尾带块（骨架 / 条目补扫的输入正确性）。
"""
import json
import os
import sys

for _c in [os.path.dirname(os.path.abspath(__file__)),
           *[os.path.abspath(os.path.join(os.path.dirname(__file__), *(['..'] * n)))
             for n in range(1, 6)]]:
    if os.path.exists(os.path.join(_c, 'SKILL.md')):
        sys.path.insert(0, _c)
        break
import lib.boot as _boot  # noqa: E402
_boot.setup()

import chapter_boundary as CB  # noqa: E402

PAGE_H = 2400.0


def _blk(text, y, h=40.0):
    return {"poly": [200.0, y, 1500.0, y, 1500.0, y + h, 200.0, y + h],
            "text": text, "score": 0.99}


def _write_page(ext, page, blocks, formulas=None):
    os.makedirs(ext, exist_ok=True)
    with open(os.path.join(ext, "page_%03d.json" % page), "w",
              encoding="utf-8") as f:
        json.dump({"page": page, "text": blocks,
                   "formulas": formulas or [], "deskew": 0.0},
                  f, ensure_ascii=False)


def _write_map(ext, recs):
    os.makedirs(ext, exist_ok=True)
    with open(os.path.join(ext, "chapter_map.json"), "w", encoding="utf-8") as f:
        json.dump({"chapters": recs}, f, ensure_ascii=False)


def _fixture(ext, spill_mid_page=True):
    """两章书：ch1 = p1..p2，ch2 起始页 p3；p3 上是否印着 ch1 尾料可控。"""
    _write_map(ext, [
        {"kind": 1, "num": 1, "name": "First chapter title", "start": 1, "end": 2},
        {"kind": 1, "num": 2, "name": "Second chapter title", "start": 3, "end": 4},
    ])
    y0 = 700.0 if spill_mid_page else 30.0
    _write_page(ext, 1, [_blk("1 First chapter title", 60.0),
                         _blk("Theorem 1.1. Something.", 200.0)])
    _write_page(ext, 2, [_blk("1.2 Some section", 60.0),
                         _blk("Definition 1.5. More.", 200.0)])
    _write_page(ext, 3, [
        _blk("Theorem 1.6. Tail of chapter one.", 60.0),
        _blk("2 Second chapter title", y0),
        _blk("2.1 Opening section of chapter two", y0 + 200.0),
        _blk("Definition 2.1. Chapter two content.", y0 + 400.0),
        # 真实扫描页总是排到页底（页脚页码）——`title_y_on_page` 用内容最大 bottom
        # 作页高代理来判断「标题是否在页顶」，缺了这块会把稀疏页的页顶误判成中上部。
        _blk("3", PAGE_H - 40.0),
    ], formulas=[{"bbox": [300.0, 80.0, 900.0, 130.0], "latex": "x = y", "cls": 1}])
    _write_page(ext, 4, [_blk("2.2 Next section", 60.0)])
    return y0


def test_head_floor_is_title_y_when_chapter_starts_mid_page(tmp_path=None):
    ext = _tmp("mid")
    _fixture(ext, spill_mid_page=True)
    assert CB.head_floor(ext, ext, "2", 3) == 700.0
    # 上一章在同一条线上收口（尾带 = 标题之上）
    assert CB.tail_band(ext, ext, "1") == (3, 700.0)


def test_no_clip_when_title_at_page_top(tmp_path=None):
    """正常书（章从新页开始）→ 两侧都 None，历史行为逐字节不变。"""
    ext = _tmp("top")
    _fixture(ext, spill_mid_page=False)
    assert CB.head_floor(ext, ext, "2", 3) is None
    assert CB.tail_band(ext, ext, "1") is None


def test_tail_band_requires_adjacent_pages():
    """章图不紧邻（ch1 只到 p1，p2 仍属别处）→ 不扩页。"""
    ext = _tmp("gap")
    _fixture(ext, spill_mid_page=True)
    _write_map(ext, [
        {"kind": 1, "num": 1, "name": "First chapter title", "start": 1, "end": 1},
        {"kind": 1, "num": 2, "name": "Second chapter title", "start": 3, "end": 4},
    ])
    assert CB.tail_band(ext, ext, "1") is None


def test_clip_page_keeps_only_band_above_title():
    ext = _tmp("clip")
    _fixture(ext, spill_mid_page=True)
    out = CB.clip_page(ext, os.path.join(ext, "_ov"), 3, hi=700.0)
    assert out and os.path.basename(out) == "page_003.json"
    d = json.load(open(out, encoding="utf-8"))
    assert [b["text"] for b in d["text"]] == ["Theorem 1.6. Tail of chapter one."]
    # 尾带内的行间公式一并保留（标题之下那条带外的会被裁掉）
    assert len(d["formulas"]) == 1
    out2 = CB.clip_page(ext, os.path.join(ext, "_ov2"), 3, lo=700.0)
    d2 = json.load(open(out2, encoding="utf-8"))
    assert [b["text"] for b in d2["text"]] == [
        "2 Second chapter title", "2.1 Opening section of chapter two",
        "Definition 2.1. Chapter two content.", "3"]
    assert d2["formulas"] == []


def test_clip_page_empty_band_returns_none():
    ext = _tmp("empty")
    _fixture(ext, spill_mid_page=True)
    assert CB.clip_page(ext, os.path.join(ext, "_ov3"), 3, lo=PAGE_H * 10) is None


def test_missing_chapter_map_fails_open():
    ext = _tmp("nomap")
    assert CB.head_floor(ext, ext, "2", 3) is None
    assert CB.tail_band(ext, ext, "1") is None


def _tmp(tag):
    import tempfile
    d = os.path.join(tempfile.gettempdir(), "bks_bound_" + tag)
    os.makedirs(d, exist_ok=True)
    return d
