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
fmt_proofs.py — 规范化章节总结的「证明(思路|梗概|概要)」与条目分隔（幂等可重跑）。

⚠️ 关键约定：定义/定理/引理/推论/命题/断言/公理等结构性标签必须**独立成行（顶层）**，
绝不进块引用 `>`；只有 **证明** 与 **例** 才进 `>`。本工具严格遵守此约定，绝不吞并标签。

流水线（当前版默认**不**跑 repair_leaked_bq，见下）：
  repair_leaked_bq(): 【已不再默认调用】旧版假设「条目都带 > 前缀」（周民强型），
                      会把夹在两个证明块引用之间的独立 `**定理/引理**` 误吞进上一个
                      块引用。它仅保留为历史参考函数，main 不再调用。
  阶段1 (默认): 把所有独立的 **证明思路/梗概/概要** 包进块引用 `>`；并在相邻编号条目
                (定义/定理/引理/推论/命题/注/注记) 之间补 `---` 分隔线
                （每节/子节首个条目前不加）。结构性标签识别为硬边界，绝不吞并。
  阶段2 (--number): 对多步骤证明按「首先/其次/最后/先/再/情形一/（一）/
                其一…/(i)(ii)/(iii)(iv)/必要性/充分性」等标记拆分为编号步骤，
                渲染为块引用内的有序列表（已编号或单步证明跳过）。

附加清理（始终执行，幂等）：
  - 删除「紧邻任意层级节标题（## / ### / #### 等，正则 ^#{2,6}）之下的 '---'」，即某 '---' 的
    【最近上方非空行】是标题（标题 -> --- 中间无任何内容）。
  - 合法分隔线仅两类：(a) 引子段落下方；(b) 相邻 item 之间（含 item 附属块结束后）。
    故「标题 -> 引子段落 -> ---」「item -> --- -> item」均【保留】不受影响。

用法:
  python fmt_proofs.py <dir>            # 阶段1 + 标题下分隔线清理（不吞并结构性标签）
  python fmt_proofs.py <dir> --number  # 阶段1 + 阶段2(证明步骤编号) + 标题下分隔线清理
  python fmt_proofs.py <dir> --check   # 仅检测标题下分隔线，有则退出码 1（不改文件）

(blockquote 引擎见 format/bq_core.py；证明编号见 format/proof_steps.py。)
"""
import os, sys

import re
import glob
import subprocess

from bq_core import merge_example_block, stage1, remove_heading_seps
from proof_steps import stage2


# Regex: example+proof on same line (`> **例**：...**证明梗概**：...`)
_SAME_LINE_EX_PROOF_RE = re.compile(
    r'^(> \*\*例(?:\d[\d.]*-[0-9]+|\d+)?\*\*[^>]*?)(\*\*(?:证明思路|证明|证明梗概|证明概要)\*\*[^>]*)$'
)

def fix_inline_example_proof(text):
    """Split `> **例**：...**证明梗概**：...` into two separate `>` lines."""
    lines = text.split('\n')
    out = []
    changed = False
    for ln in lines:
        m = _SAME_LINE_EX_PROOF_RE.match(ln)
        if m:
            changed = True
            before = m.group(1).rstrip()
            after = m.group(2)
            out.append(before)
            out.append('> ' + after)
        else:
            out.append(ln)
    if changed:
        return '\n'.join(out)
    return text


# Item-starting patterns for separator fix
_SEP_ITEM_STRUCT_RE = re.compile(
    r'^\*\*(?:定义|定理|引理|推论|命题|断言|公理'
    r'|Definition|Theorem|Lemma|Corollary|Proposition|Axiom)'
)
_SEP_ITEM_EX_RE = re.compile(r'^> \*\*(?:例|Example)')
from lib.regexlib import FMT_SEC_RE as _SEP_SEC_RE
from lib.regexlib import FMT_HR_RE as _SEP_HR_RE

def fix_missing_item_sep(text):
    """Insert `---` between consecutive items where it is missing.

    Scans for pairs of item-starting lines (definition/theorem/lemma/etc
    and example) and inserts `\n\n---\n\n` between them if no `---` or
    section heading already separates them. Skips items >100 lines apart
    (likely across sections). Idempotent.
    """
    lines = text.split('\n')
    # Collect item line indices
    item_idxs = []
    for i, ln in enumerate(lines):
        if _SEP_ITEM_STRUCT_RE.match(ln) or _SEP_ITEM_EX_RE.match(ln):
            item_idxs.append(i)
    if len(item_idxs) < 2:
        return text

    # Work backwards so insertions don't invalidate indices
    changed = False
    insertions = []  # list of (pos, alt_text) where alt_text replaces the gap
    for idx in range(len(item_idxs) - 1, 0, -1):
        i = item_idxs[idx - 1]
        j = item_idxs[idx]
        if j - i > 100:
            continue
        # Look for --- or section boundary between i and j
        has_sep = False
        section_between = False
        for k in range(i + 1, j):
            t = lines[k].strip()
            if t == '---':
                has_sep = True
                break
            if _SEP_SEC_RE.match(lines[k]):
                section_between = True
                break
        if has_sep or section_between:
            continue
        # Insert `---` just before the second item's preceding blank lines
        # Find the first blank line before j
        insert_pos = j
        while insert_pos > i + 1 and lines[insert_pos - 1].strip() == '':
            insert_pos -= 1
        # Remove trailing blanks between i and insert_pos, then insert: [blank, ---, blank]
        tail = []
        k = i + 1
        while k < insert_pos:
            if lines[k].strip() == '':
                tail.append(k)
            k += 1
        # Replace the blank-run with
        #   ''
        #   '---'
        #   ''
        # working backwards
        for t_idx in reversed(tail):
            del lines[t_idx]
        # Now insert_pos is after the deleted blanks
        # Find the new position
        offset = 0
        for t_idx in tail:
            if t_idx < insert_pos:
                offset += 1
        new_insert_pos = insert_pos - offset
        lines.insert(new_insert_pos, '')
        lines.insert(new_insert_pos, '---')
        lines.insert(new_insert_pos, '')
        changed = True
        # Update item indices for earlier pairs (moved down by 3)
        for k in range(idx, len(item_idxs)):
            item_idxs[k] += 3

    if changed:
        return '\n'.join(lines)
    return text


def _fix_katex_blank_lines(book_dir):
    """Run check_katex.py --fix on the book directory to fix missing blank lines
    around $$ display math and <div> blocks. Idempotent."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    check_path = os.path.join(script_dir, 'check_katex.py')
    if os.path.exists(check_path):
        subprocess.run(
            [sys.executable, '-X', 'utf8', check_path, '--dir', book_dir, '--fix'],
            capture_output=True, text=True, encoding='utf-8'
        )


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
    # --- No-check = apply fixes ---
    for f in files:
        raw = open(f, encoding='utf-8').read()
        # 阶段0：合并例和证明到同一 blockquote
        t = merge_example_block(raw)
        t = stage1(t)
        if do_number:
            t = stage2(t)
        t = remove_heading_seps(t)
        # 阶段3：拆分同行例+证明
        t = fix_inline_example_proof(t)
        # 阶段4：补全条目间缺失的 ---（定义定理↔例，例↔定义定理）
        t = fix_missing_item_sep(t)
        if t != raw:
            open(f, 'w', encoding='utf-8').write(t)
            print(f"[OK] {os.path.basename(f)}  (fixed)")
        else:
            print(f"[--] {os.path.basename(f)}  (no change)")
    # 阶段5：check_katex.py --fix（全目录，幂等修复 $$/<div> 前后缺空行）
    _fix_katex_blank_lines(d)


if __name__ == '__main__':
    main()
