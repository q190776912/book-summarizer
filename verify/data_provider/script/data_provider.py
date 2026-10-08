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
from verify.script.structure_io import read_structure_items, md_keys_for_chapter

# ---------------------------------------------------------------------------
# data_provider.py — EXTRACT provider (order 0).
#
# 纯数据供给层（provider 模式）：从「书的真相集」(分章契约 book_structure/ch{N}.json) 与「md 写入集」
# (keys_in_md) 取值，挂到 ctx 上供下游所有层使用。它**不做任何缺失项比对/查漏**——
# 那些职责已统一归 B 层 (item_numbering_integrity)：B 是查漏的唯一权威，本层只供水。
#
# 本层挂入 ctx 的字段（SSOT，下游消费者唯一数据来源）：
#     ctx.items       书的编号项真相集（非 exercise/chapter/section 节点）
#     ctx.entry_keys  md 中加粗独立条目 **标签N.N**
#     ctx.all_keys    md 中出现过的一切键（含正文/交叉引用里的 mention）
#     ctx.label_warns 契约标签与**印面条头标签**不符告警（report 打印，非阻断）；
#                   只比对条头，不扫描正文中段（避免交叉引用/专名/动词误报）
#
# 不参与：truly_missing / mentioned_only / extra（现由 B 层负责）、
#         提取侧查漏(整类首项缺失 + over-mark 守卫)（现由 B 层负责）、
#         ignored_hit / extraction_blocking（B 自行计算并写 ctx，不再依赖本层 stage1）。
#
# 这是全管线唯一的数据入口（"no global mutable state，everything flows through ctx"）。
# ---------------------------------------------------------------------------


def _dispatch_items(ctx):
    """编号项来源：统一读分章契约（structure 产物，SSOT，经 BookStructure.load 聚合为书对象）。
    旧书须先重跑 build_structure 生成 JSON，不再回退抽取器（无兼容性代码）。"""
    # primary_type 透传：附录章（ORDINAL_APP / type 13 三级、ORDINAL_APP2 /
    # type 14 两段）据此把字母章位键 `A.1.1` / `B.4` 规范化成 `定义A.1-1` /
    # `定理B.2`；其余书零影响。
    items = read_structure_items(ctx.ext_dir, ctx.ch,
                                 primary_type=getattr(ctx.config, 'primary_type', None))
    if items is None:
        # 旧书未生成 JSON：不保留兼容性代码。verify 前应先对本书跑 build_structure；
        # 此处给空列表，由 B 层如实报「缺失项」提示该书尚未生成契约。
        items = []
    return items


# 条头标签词表（仅用于「条头位置」比对，见 check_label_consistency）。
# 🔴 判据根治（2026-10-07）：只认 text **开头**的标签词，绝不扫描正文中段。
#    旧判据在 text[:60] 的**任意位置**搜 `定理[（(]` 等，把三类良性用法误报成
#    LABEL MISMATCH（基础目录 17 本全量普查共 5 条，逐条核源书确认全为假阳）：
#      ① 交叉引用：`例5.5 同质放大存在性定理（定理5.6）的超幂证明`      （条头=例）
#      ② 定理专名：`推论9.3（塔尔斯基-赛登伯格定理（Tarski…）…）`      （条头=推论）
#      ③ 普通动词：`例9.1.1 设R_n…定义(α,β)=x1y1+…，则在此定义下…`     （条头=例）
#    这些「定理 / 定义」都不宣告项目自身的类别，只有条头才有此权威，故判据收紧为
#    「首标签」。收紧后全目录告警 5 → 0，未掩盖任何真实不符（差分普查已证）。
_HEAD_LABEL_RE = re.compile(r'^\s*(定\s*义|定\s*理|引\s{0,2}理)')


def check_label_consistency(items):
    """Return list of warning strings for items with label-vs-**head** mismatch.

    判据（SSOT）：契约项 `label` 与**印面条头标签**不符时告警。条头标签取 `text`
    **开头**处出现的标签词（前导空白可容忍；词内空格如 `定 理` 归一化后比对）——
    条头是「本项目叫什么」的唯一权威宣告。

    🔴 绝不扫描正文中段：正文中段出现的同类词语既可能是交叉引用（「…（定理5.6）」）、
    定理专名（「塔尔斯基-赛登伯格定理」），也可能是普通动词（「定义(α,β)=…」），
    一律不作判据（旧判据即因扫描中段而误报，见 `_HEAD_LABEL_RE` 上方注释）。

    `label` 为 'uncat' / 空 → 类别未知，不是不符，跳过（避免出现 '裸' 式假告警）。
    条头无标签词（裸号 / 外文条头等）→ 无从判断，同样跳过。
    """
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
        m = _HEAD_LABEL_RE.match(text)
        if not m:
            continue
        head = re.sub(r'\s+', '', m.group(1))   # '定 理' / '引 理' → '定理' / '引理'
        if head != extracted:
            warns.append(f"  LABEL MISMATCH: {it['key']} has label='{extracted}' "
                         f"but its head label is '{head}' (text: {text[:60]})")
    return warns


class ExtractLayer(VerifyLayer):
    code = 'EXTRACT'
    name = 'data-provider'
    order = 0
    auto_fixable = False

    def run(self, ctx):
        # 编号项来源：统一分章契约（SSOT，经 BookStructure.load 聚合），无旧文件回退。
        items = _dispatch_items(ctx)

        label_warns = check_label_consistency(items)

        cfg = ctx.config
        entry_keys, all_keys = md_keys_for_chapter(ctx.md_file, cfg, ctx.ch)

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
