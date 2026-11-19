# -*- coding: utf-8 -*-
"""回归：分节文件名用**连字符节号**（`Chapter5_5-2_...`）时的解析与排序。

Bug 来源：differential-geometry-of-curves-and-surfaces（do Carmo）全 76 个分节
文件名为 `Chapter{N}_{N}-{M}_{名称}` / `第{N}章_{N}-{M}_{名称}`。旧正则
`^Chapter\\d+_([\\d.]+)` 只认点与数字，`5-2` 被截成 `5`（章号），于是同章 11 个
分节文件 secnum 全等于 `5`，`chapter_md_groups` 排序退化为文件名字典序
（5-10, 5-11, 5-1, 5-2, …, 5-9）——书末两节被拼到开头，U 层交付顺序闸连锁
报 132 条假倒退（p325-p432 全部"排在 p478 命题16 之后"）。

修法：`_section_num_from_filename` 正则支持 `[.\\-]` 分隔符；
`chapter_md_groups` 排序键同样按 `[.\\-]` 切分。点号节号（全库 2153 个）与纯
数字节号（559 个）必须逐字节不变。
"""
import os
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in (_ROOT, str(_ROOT / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot  # noqa: E402
lib.boot.setup()

from verify.script.verify_chapter import _section_num_from_filename, chapter_md_groups  # noqa: E402


def test_dash_section_num_en():
    assert _section_num_from_filename("Chapter5_5-2_TheRigidity.md") == "5-2"
    assert _section_num_from_filename("Chapter5_5-11_HilbertsTheorem.md") == "5-11"


def test_dash_section_num_zh():
    assert _section_num_from_filename("第5章_5-2_球面的刚性.md") == "5-2"
    assert _section_num_from_filename("第5章_5-11_Hilbert定理.md") == "5-11"


def test_dot_section_num_unchanged():
    assert _section_num_from_filename("Chapter3_3.2_TheGaussMap.md") == "3.2"
    assert _section_num_from_filename("第3章_3.2_高斯映射.md") == "3.2"
    assert _section_num_from_filename("Chapter7_28_Computation.md") == "28"


def test_merged_file_still_none():
    assert _section_num_from_filename("Chapter5_GlobalDifferentialGeometry.md") is None
    assert _section_num_from_filename("第5章_全局微分几何.md") is None


def test_dash_sections_sorted_numerically(tmp_path):
    book = tmp_path / "book"
    book.mkdir()
    for n in (1, 2, 10, 11, 9):
        (book / f"Chapter5_5-{n}_Sec{n}.md").write_text("# x", encoding="utf-8")
    groups = chapter_md_groups(str(book), 5)
    en = [Path(f).name for f in groups[0]]
    assert en == [
        "Chapter5_5-1_Sec1.md",
        "Chapter5_5-2_Sec2.md",
        "Chapter5_5-9_Sec9.md",
        "Chapter5_5-10_Sec10.md",
        "Chapter5_5-11_Sec11.md",
    ]


def test_dot_sections_sorted_numerically_unchanged(tmp_path):
    book = tmp_path / "book"
    book.mkdir()
    for n in (1, 2, 10, 9):
        (book / f"Chapter3_3.{n}_Sec{n}.md").write_text("# x", encoding="utf-8")
    groups = chapter_md_groups(str(book), 3)
    en = [Path(f).name for f in groups[0]]
    assert en == [
        "Chapter3_3.1_Sec1.md",
        "Chapter3_3.2_Sec2.md",
        "Chapter3_3.9_Sec9.md",
        "Chapter3_3.10_Sec10.md",
    ]
