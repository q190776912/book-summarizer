#!/usr/bin/env python
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
import book_index

# -*- coding: utf-8 -*-
"""
make_summary.py — 汇总 Phase1(validate_report.json) + Phase2(validate_report_phase2.json)
输出 validation_summary.md (人类可读) + 打印关键统计。
"""

import os, sys

import os, json, datetime

SKILL = r"C:\Users\ye190\.workbuddy\skills\book-summarizer"
P1 = os.path.join(SKILL, "validate_report.json")
P2 = os.path.join(SKILL, "validate_report_phase2.json")
OUT = os.path.join(SKILL, "validation_summary.md")


def parse_pass(s):
    if not s or s == "?":
        return (None, None)
    try:
        a, b = s.split("/")
        return (int(a), int(b))
    except Exception:
        return (None, None)


def main():
    p1 = book_index.BookIndex.load(P1).data if os.path.exists(P1) else {"books": {}}
    p2 = book_index.BookIndex.load(P2).data if os.path.exists(P2) else {"books": {}}
    books = p1.get("books", {})
    lines = []
    lines.append("# 书籍总结校验总报告")
    lines.append("")
    lines.append(f"- 生成时间: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 总书籍数: {len([b for b,v in books.items() if isinstance(v,dict)])}")
    lines.append("")

    total_md = 0
    total_pass = 0
    total_ch = 0
    fail_books = []
    for b, v in sorted(books.items()):
        if not isinstance(v, dict):
            continue
        total_md += v.get("md_count", 0)
        pp = parse_pass(v.get("verify_pass"))
        if pp[0] is not None:
            total_pass += pp[0]
            total_ch += pp[1]
        fails = v.get("verify_fails") or []
        if v.get("verify_pass") not in (None, "?") and (pp[0] != pp[1] or fails):
            fail_books.append((b, v))

    lines.append(f"- 总结文件总数(md): {total_md}")
    lines.append(f"- 校验章节: 通过 {total_pass} / 共 {total_ch}")
    lines.append(f"- 未完全通过校验的书籍: {len(fail_books)}")
    lines.append("")

    # Per-book table
    lines.append("## 各书校验状态")
    lines.append("")
    lines.append("| 书籍 | md数 | KaTeX修正 | G层修正 | 嵌入 | 校验(通过/总) | 需图片识别 |")
    lines.append("|---|---|---|---|---|---|---|")
    for b, v in sorted(books.items()):
        if not isinstance(v, dict):
            continue
        pp = parse_pass(v.get("verify_pass"))
        vpass = f"{pp[0]}/{pp[1]}" if pp[0] is not None else "?"
        emb = v.get("embed", {})
        emb_s = str(emb.get("rc")) if isinstance(emb, dict) else str(emb)
        recog = "是" if v.get("needs_image_recognition") else "-"
        lines.append(f"| {b} | {v.get('md_count',0)} | {v.get('katex',{}).get('fixed',0)} "
                     f"| {v.get('g_fixed',0)} | {emb_s} | {vpass} | {recog} |")
    lines.append("")

    # Failing chapters detail
    lines.append("## 未通过校验章节明细")
    lines.append("")
    any_fail = False
    for b, v in sorted(books.items()):
        if not isinstance(v, dict):
            continue
        fails = v.get("verify_fails") or []
        if not fails:
            continue
        any_fail = True
        lines.append(f"### {b}")
        for f in fails:
            detail = (f"M={f.get('M')} B={f.get('B')} K={f.get('K')} Dmiss={f.get('Dmiss')} "
                      f"G={f.get('G')} EG={f.get('EG')} FgMiss={f.get('FgMiss')} FgInv={f.get('FgInv')}")
            lines.append(f"- 第{f['ch']}章 ({f['file']}): {detail}")
        lines.append("")
    if not any_fail:
        lines.append("_无未通过章节_")
        lines.append("")

    # Phase 2 status
    if p2.get("books"):
        lines.append("## 图片识别(Phase 2)状态")
        lines.append("")
        lines.append("| 书籍 | 状态 | 识别图数 | 嵌入 | 复验(通过/总) |")
        lines.append("|---|---|---|---|---|")
        for b, v in sorted(p2["books"].items()):
            if not isinstance(v, dict):
                continue
            st = v.get("status", "")
            figidx_n = ""
            if "embed_rc" in v:
                figidx_n = "已生成"
            pp = parse_pass(v.get("verify_pass"))
            vpass = f"{pp[0]}/{pp[1]}" if pp[0] is not None else "-"
            emb = v.get("embed_rc", "-")
            lines.append(f"| {b} | {st or 'done'} | {figidx_n} | {emb} | {vpass} |")
        lines.append("")

    lines.append("---")
    lines.append("注: M=缺失条目(A层) B=阻断项(B层) K=KaTeX错误(C层) Dmiss=整节缺失(D层) "
                 "G=引用块连续性 G层 EG=例-证间隙 G层 FgMiss/FgInv=图片缺失/无效(E/F层)。")
    txt = "\n".join(lines)
    open(OUT, "w", encoding="utf-8").write(txt)
    print(txt)
    print(f"\n[written] {OUT}")


if __name__ == "__main__":
    main()
