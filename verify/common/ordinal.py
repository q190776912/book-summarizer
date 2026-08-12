"""verify/common/ordinal.py — 整数转罗马数字（从 flows/extract/structure/script/extract_items_gm.py 解耦复制）。

原本 data_provider 直接 `from extract_items_gm import int_to_roman`，而 extract_items_gm 位于
flows/ 抽取管线，违反「校验脚本不得依赖 flows」的约束。此处仅抽取该纯函数，使校验子流程
零 flows 依赖。函数实现与源文件逐字符一致。
"""
import os
import sys
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


def int_to_roman(n):
    vals = [(1000, 'M'), (900, 'CM'), (500, 'D'), (400, 'CD'), (100, 'C'),
            (90, 'XC'), (50, 'L'), (40, 'XL'), (10, 'X'), (9, 'IX'), (5, 'V'),
            (4, 'IV'), (1, 'I')]
    out = ''
    for v, sym in vals:
        while n >= v:
            out += sym
            n -= v
    return out
