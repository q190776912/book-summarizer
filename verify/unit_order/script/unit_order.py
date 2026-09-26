"""unit_order.py — U 层：总结单元「结构阅读顺序」校验（步骤 8 合并后终检）。

与 gate_units 章级闸 ⑪ 复用同一核心实现 ``lib/unit_order.check_unit_order``，是
「合并前门控」之后的**常跑安全网**：门控（步骤 5）可被跳过或单元事后被改，
verify_chapter --all（步骤 8）每次都会跑，故在此再断言一次合并顺序正确。

真值 = 分章契约节点的 ``page_start``（源书物理页序）；被测顺序 = 该章**源单元 manifest
的 units 数组**（``merge_units`` 严格以此顺序拼接，故 manifest 顺序 == 合并 md 阅读
顺序）。译文单元由 ``check_translate_parity`` 保证与源 manifest 索引逐条对齐，源有序
⇒ 译有序，故本层统一以源 manifest 为准（同一章的中/英两份 md 各报一次相同问题，属预期
的双重呈现）。

判据（细节见 lib/unit_order.py）：页码单调不减、相等允许、章末 dash 习题（``N-M``）
豁免、锚点缺失单元跳过。契约 / manifest 任一缺失 → 静默返回 []（无从判真值不误报）。
🔴 命名：核心模块在 ``lib/unit_order.py``，本层目录亦名 ``unit_order``；两者 import 名
冲突（boot 把 lib 与 verify/**/script 都注入 sys.path）。故一律用包路径
``from lib.unit_order import …`` 取核心，避免 `import unit_order` 解析到本层自身。
"""
import os
import sys
import json
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

from verify.script.base import VerifyLayer, LayerResult
from data.book_structure.book_structure import (
    chapter_json_path, unit_dir_name, prime_chapter_kinds)
from lib.unit_order import check_unit_order


def _locate(ext, ch):
    """返回 (contract_dict_or_None, units_list_or_None)。契约/清单任一缺失 → (None, None)。"""
    cpath = chapter_json_path(ext, ch)
    if not cpath or not os.path.exists(cpath):
        return None, None
    # 单元目录与契约同父（<ext>/book_structure/…）：units/<unitdir>/manifest.json
    units_dir = os.path.join(os.path.dirname(cpath), "units", unit_dir_name(ch))
    mpath = os.path.join(units_dir, "manifest.json")
    if not os.path.exists(mpath):
        return None, None
    try:
        with open(cpath, encoding="utf-8") as f:
            contract = json.load(f)
        with open(mpath, encoding="utf-8") as f:
            units = json.load(f).get("units") or []
    except Exception:
        return None, None
    return contract, units


class UnitOrderLayer(VerifyLayer):
    code = 'U'
    name = 'unit-order'
    order = 18               # 在 Q (17) 之后；纯顺序复检，与其它层无数据依赖
    auto_fixable = False     # 顺序错乱是结构缺陷，修复=重排单元，不可盲目自动改
    depends_on = []

    def run(self, ctx):
        ext = ctx.ext_dir
        try:
            prime_chapter_kinds(ext)   # 让 unit_dir_name 正确区分附录/章
        except Exception:
            pass
        contract, units = _locate(ext, ctx.ch)
        problems = check_unit_order(contract, units) if (contract and units) else []
        return LayerResult(code=self.code, metadata={'unit_order_problems': problems})
