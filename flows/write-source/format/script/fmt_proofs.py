#!/usr/bin/env python3
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

# -*- coding: utf-8 -*-
"""
fmt_proofs.py — 章节总结「生产期」格式化（幂等可重跑）。

⚠️ 本工具只做生产期变换；格式修复不在本工具职责内。
   格式修复（blockquote 连续性 / 嵌套展平 / 例证空隙合并与同行拆分 / 标题下
   `---` 清理 / 条目间 `---` 补全 / KaTeX 前后空行）由 verify 的统一修复器
   FIXERS 在写作完成后统一执行（`verify --fix`）。各修复器代号沿用原层字母：
   G=blockquote_continuity / L=separator_spacing / I=item_separator / C=katex，
   完整说明见 verify/format_verify/format_verify.md。

   生产期（本工具保留）：
     - stage1  (bq_core)：把独立的 证明/例 包进块引用 `>`；在相邻编号条目之间补
       `---` 分隔线；展平 `> > **`（生产期即产出单层块引用）。
     - stage2  (proof_steps, --number)：对多步骤证明按标记拆分为编号步骤。

⚠️ 关键约定（与生产期一致）：定义/定理/引理/推论/命题/断言/公理等结构性标签
   必须**独立成行（顶层）**，绝不进块引用 `>`；只有 **证明** 与 **例** 才进 `>`。
   本工具严格遵守此约定，绝不吞并标签。

用法:
  python fmt_proofs.py <dir>            # 生产期：stage1 包块引用 + 条目间 `---`（不编号）
  python fmt_proofs.py <dir> --number  # 生产期 + stage2(证明步骤编号)
  python fmt_proofs.py <dir> --check   # 仅提示：格式修复请改跑 `verify --fix`

（blockquote 引擎见 format/bq_core.py；证明编号见 format/proof_steps.py。）
"""
import os, sys

import re
import glob

from bq_core import stage1
from proof_steps import stage2


def main():
    if len(sys.argv) < 2:
        print("Usage: python fmt_proofs.py <dir> [--number] [--check]")
        sys.exit(2)
    d = sys.argv[1]
    args = sys.argv[2:]
    do_number = '--number' in args
    do_check = '--check' in args
    files = sorted(glob.glob(os.path.join(d, '第*.md')) +
                   glob.glob(os.path.join(d, 'Chapter*.md')))
    if not files:
        print("No 第*.md found in", d)
        sys.exit(1)
    if do_check:
        print("[check] 格式修复已迁移到 verify：请改用 `verify --fix <dir>`。")
        print("[check] 本工具现在只做生产期变换（stage1 包块引用 + 可选 stage2 编号）。")
        return
    # --- 生产期：只做 stage1（包块引用 + 条目间 ---）+ 可选 stage2（编号） ---
    for f in files:
        raw = open(f, encoding='utf-8').read()
        t = stage1(raw)                 # 生产期：包块引用 + 条目分隔 + 展平嵌套
        if do_number:
            t = stage2(t)               # 生产期：证明步骤编号
        if t != raw:
            open(f, 'w', encoding='utf-8').write(t)
            print(f"[OK] {os.path.basename(f)}  (formatted)")
        else:
            print(f"[--] {os.path.basename(f)}  (no change)")


if __name__ == '__main__':
    main()
