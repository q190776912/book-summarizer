"""section_boundary.py — S 层：章节边界内容错位检测（WARN，非阻断）。

本层只做**检测**，不改文件（``auto_fixable = False``）。判据与实现细节见
``verify/section_boundary/section_boundary.md``（SSOT）；本文件仅做 verify
上下文适配，核心逻辑单源在 ``lib/section_boundary.py``。

🔴 命名：核心模块是 ``lib/section_boundary.py``，本层目录也叫
``section_boundary``；boot 同时把 ``lib`` 与 ``**/script`` 注入 sys.path，
裸 ``import section_boundary`` 会撞名。故一律用包路径
``from lib.section_boundary import …``。
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

from verify.script.base import VerifyLayer, LayerResult
from lib.section_boundary import scan_verify_target


class SectionBoundaryLayer(VerifyLayer):
    code = 'S'
    name = 'section-boundary'
    order = 2                # D 之后、B 之前；纯检测，无数据依赖
    auto_fixable = False     # 边界错位 = 单元/页切分问题，修复须整块搬移，不可盲改
    depends_on = []

    def run(self, ctx):
        try:
            findings, stats = scan_verify_target(
                ctx.md_file, ctx.ext_dir, ctx.ch,
                start=getattr(ctx, 'start', None),
                end=getattr(ctx, 'end', None))
        except OSError as exc:
            # 读不到交付 md ≠ 没有边界问题。与 B/P/U 层同口径 fail-closed：
            # 无证据不得静音成 PASS。
            raise RuntimeError(
                "S 层读取交付 md 失败: %s (%r)" % (ctx.md_file, exc)) from exc
        return LayerResult(code=self.code, metadata={
            'section_boundary_findings': findings,
            'section_boundary_stats': stats,
        })
