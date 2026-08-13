import os
import sys
import re
from pathlib import Path
from collections import defaultdict

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
from verify.common.key_parse import keys_in_md, _first_num, sortkey
from verify_config import ORDINAL_EN, ORDINAL_GM, ORDINAL_ROMAN
from verify.common.ordinal import int_to_roman
from verify.common.structure_io import read_structure_items

# ---------------------------------------------------------------------------
# data_provider.py — EXTRACT provider (order 0).
#
# 纯数据供给层（provider 模式）：从「书的真相集」(book_structure.json) 与「md 写入集」
# (keys_in_md) 取值，挂到 ctx 上供下游所有层使用。它**不做任何缺失项比对/查漏**——
# 那些职责已统一归 B 层 (item_numbering_integrity)：B 是查漏的唯一权威，本层只供水。
#
# 本层挂入 ctx 的字段（SSOT，下游消费者唯一数据来源）：
#     ctx.items       书的编号项真相集（非 exercise/chapter/section 节点）
#     ctx.entry_keys  md 中加粗独立条目 **标签N.N**
#     ctx.all_keys    md 中出现过的一切键（含正文/交叉引用里的 mention）
#     ctx.label_warns 标签(定义/定理)与正文不符告警（report 打印，非阻断）
#
# 不参与：truly_missing / mentioned_only / extra（现由 B 层负责）、
#         提取侧查漏(整类首项缺失 + over-mark 守卫)（现由 B 层负责）、
#         ignored_hit / extraction_blocking（B 自行计算并写 ctx，不再依赖本层 stage1）。
#
# 这是全管线唯一的数据入口（"no global mutable state，everything flows through ctx"）。
# ---------------------------------------------------------------------------


def _dispatch_items(ctx):
    """编号项来源：统一读 book_structure.json（extract/structure 产物，SSOT，书对象）。
    旧书须先重跑 build_structure 生成 JSON，不再回退抽取器（无兼容性代码）。"""
    items = read_structure_items(ctx.ext_dir, ctx.ch)
    if items is None:
        # 旧书未生成 JSON：不保留兼容性代码。verify 前应先对本书跑 build_structure；
        # 此处给空列表，由 B 层如实报「缺失项」提示该书尚未生成契约。
        items = []
    return items


def check_label_consistency(items):
    """Return list of warning strings for items with label-vs-text mismatch."""
    LABEL_TEXT_PATTERNS = {
        '定义': r'定义[（(]',
        '定理': r'定理[（(]',
        '引理': r'引.{0,2}理[（(]',
    }
    warns = []
    for it in items:
        text = it.get('text', '')
        if not text:
            continue
        extracted = it.get('label', '')
        # 'uncat' (extractor couldn't determine the category) or empty → unknown,
        # not a mismatch; skip so the verify output never shows a spurious '裸'-style alert.
        if extracted in ('uncat', '', None):
            continue
        for kw, pat in LABEL_TEXT_PATTERNS.items():
            if re.search(pat, text[:60]):
                if extracted != kw:
                    warns.append(f"  LABEL MISMATCH: {it['key']} has label='{extracted}' "
                                 f"but text contains '{kw}' (text: {text[:60]})")
                break
    return warns


class ExtractLayer(VerifyLayer):
    code = 'EXTRACT'
    name = 'data-provider'
    order = 0
    auto_fixable = False

    def run(self, ctx):
        # 编号项来源：统一结构 JSON（book_structure.json，SSOT 书对象），无旧书回退。
        items = _dispatch_items(ctx)

        label_warns = check_label_consistency(items)

        cfg = ctx.config
        if ctx.config.primary_type in (ORDINAL_GM, ORDINAL_ROMAN):
            # keys_in_md 需要 md 的罗马章前缀（标题是裸 per-section 序数）。
            entry_keys, all_keys = keys_in_md(
                ctx.md_file, groups=cfg.ordinal, chapter_roman=int_to_roman(ctx.ch))
        else:
            entry_keys, all_keys = keys_in_md(ctx.md_file, groups=cfg.ordinal)
        if ctx.config.primary_type == ORDINAL_EN:
            entry_keys = {k for k in entry_keys if _first_num(k) == ctx.ch}
            all_keys = {k for k in all_keys if _first_num(k) == ctx.ch}

        # Populate context for B / C / D / … layers. 本层只供水、不做事；
        # 所有缺失项比对 / 查漏 / 阻断均由 B 层完成，B 与 EXTRACT 解耦。
        ctx.items = items
        ctx.entry_keys = entry_keys
        ctx.all_keys = all_keys
        ctx.label_warns = label_warns

        return LayerResult(code=self.code, legacy=items, metadata={
            'items': items,
            'entry_keys': entry_keys,
            'label_warns': label_warns,
        })
