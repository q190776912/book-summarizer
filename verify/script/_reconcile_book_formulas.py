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
import page_json

# -*- coding: utf-8 -*-
"""
reconcile_book_formulas.py  --  Chapter formula reconciliation helper (v2).

REUSES book-summarizer's q_layer helpers (build_formula_patterns, norm,
_block_has_math, _section_match, SourceFormulaIndex._plausible) so the
book-side number extraction is IDENTICAL to the Q-layer audit (noise-filtered,
section-aware).  On top of that it ADDS:
  * per-section LaTeX recovery  (number token -> nearest formulas[].latex),
  * per-section page tracking,
  * a content-similarity renumber check against the summary's own formulas.

Output: a readable markdown reconciliation for the chapter.  No edits to the
summary .md — this is a review draft for human verification against the book.

Usage (run from the skill root so `formula_tag` (in formula_tag/script/) is importable via sys.path injection):
  python verify/script/_reconcile_book_formulas.py <extract_dir> <md_file> <first> <last> [out_md]
"""
import json, re, os, sys

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from formula_tag import (build_formula_patterns, SourceFormulaIndex,
                            _section_match)

NUM_RE = re.compile(r'^[\(（]\s*(\d{1,3}[a-zA-Z]?)\s*[\)）]$')


def bbox_of(poly):
    if not isinstance(poly, list) or len(poly) < 4:
        return None
    xs = poly[0::2]; ys = poly[1::2]
    return (min(xs), min(ys), max(xs), max(ys))


def centroid(b):
    return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def load(p):
    return page_json.PageJson.load(p).data


def scan_sectioned(extract_dir, patterns, first, last, md_sections):
    """Mirror q_layer.build_sectioned's section tracking + noise filter, but
    additionally recover (latex, page) for each book formula number and track
    the page ranges per section."""
    compiled = [re.compile(p) for p in patterns]
    sectioned = {s: {} for s in md_sections}   # sec -> num -> {latex,page,ctx}
    sec_pages = {s: set() for s in md_sections}
    cur = 0
    for pg in range(int(first), int(last) + 1):
        fp = os.path.join(extract_dir, f'page_{pg:03d}.json')
        if not os.path.exists(fp):
            continue
        try:
            data = load(fp)
        except Exception:
            continue
        texts = []
        for t in data.get('text', []):
            s = t.get('text', '').strip()
            if not s:
                continue
            b = bbox_of(t.get('poly'))
            if b:
                texts.append((b, s))
        forms = []
        for f in data.get('formulas', []):
            l = f.get('latex', '').strip()
            if not l:
                continue
            b = bbox_of(f.get('bbox'))
            if b:
                forms.append((b, l))
        for (tb, ts) in texts:
            # advance current section via entry marker C.S-1
            for mm in re.finditer(r'(\d{1,3}\.\d{1,3})-(\d{1,3})', ts):
                if mm.group(2) != '1':
                    continue
                after = ts[mm.end():mm.end() + 1]
                if after in '）)':
                    continue
                cs = mm.group(1)
                j = _section_match(cs, md_sections, cur)
                if j > cur:
                    cur = j
            sec = md_sections[cur] if cur < len(md_sections) else md_sections[-1]
            if not SourceFormulaIndex._block_has_math(ts):
                continue
            for pat in compiled:
                for m in pat.finditer(ts):
                    raw = m.group(1)
                    n =SourceFormulaIndex.norm(raw)
                    if not n or not SourceFormulaIndex._plausible(n):
                        continue
                    bc = centroid(tb)
                    best = None; bestscore = 1e18
                    for (fb, fl) in forms:
                        fc = centroid(fb)
                        dy = abs(fc[1] - bc[1])
                        if dy > (tb[3] - tb[1]) * 1.4 + 6:
                            continue
                        if fb[2] > bc[0] + 12:
                            continue
                        score = dy * 10.0 + (bc[0] - fc[0])
                        if score < bestscore:
                            bestscore = score; best = fl
                    rec = sectioned[sec].setdefault(n, {'latex': best or '',
                                                        'page': pg, 'ctx': ts[:60]})
                    rec['page'] = pg
                    if best and not rec.get('latex'):
                        rec['latex'] = best
    return sectioned


# ---------- summary side ----------
SEC_RE = re.compile(r'^##\s*§?\s*(\d{1,3}\.\d{1,3})\b', re.M)
TAG_RE = re.compile(r'\\tag\{\s*([^}]+?)\s*\}')


def md_inventory(md_file):
    txt = open(md_file, encoding='utf-8').read()
    md_sections = SEC_RE.findall(txt)
    tags_sec = []
    cur = md_sections[0] if md_sections else None
    for part in re.split(r'(^##\s*§?\s*\d+\.\d+.*$)', txt, flags=re.M):
        hm = re.match(r'^##\s*§?\s*(\d+\.\d+)', part)
        if hm:
            cur = hm.group(1); continue
        for blk in re.finditer(r'\$\$(.*?)\$\$', part, re.S):
            body = blk.group(1)
            tm = TAG_RE.search(body)
            if tm:
                tags_sec.append((cur, tm.group(1), body.strip()))
    return md_sections, tags_sec


# ---------- content similarity ----------
CMD_RE = re.compile(r'\\([a-zA-Z]+)')


def norm_latex(l):
    l = re.sub(r'\\tag\{[^}]*\}', ' ', l)
    l = re.sub(r'\\left|\\right|\\!|\\,|\\;|\\:|\\ |\\quad|\\qquad', ' ', l)
    return re.sub(r'\s+', ' ', l).strip().lower()


def toks(l):
    t = set(CMD_RE.findall(l))
    for lv in re.findall(r'\\?[a-zA-Z0-9]+\s*[\^_]\s*\{?[-+a-zA-Z0-9]+\}?', l):
        t.add(lv)
    return t


def similar(a, b):
    ta, tb = toks(norm_latex(a)), toks(norm_latex(b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))


def main():
    extract_dir, md_file = sys.argv[1], sys.argv[2]
    first, last = int(sys.argv[3]), int(sys.argv[4])
    out_md = sys.argv[5] if len(sys.argv) > 5 else None

    fdepth = 1  # Kreyszig per-section bare (N)
    patterns = build_formula_patterns(fdepth)
    md_sections, tags_sec = md_inventory(md_file)
    sectioned = scan_sectioned(extract_dir, patterns, first, last, md_sections)

    # summary tags per section
    md_by_sec = {s: [] for s in md_sections}
    for sec, tag, latex in tags_sec:
        if sec in md_by_sec:
            md_by_sec[sec].append((tag, latex))
    # global summary latex index for renumber check
    global_idx = [(SourceFormulaIndex.norm(tag), latex)
                 for sec, tag, latex in tags_sec]

    lines = ['# Ch1 公式对账（书源 p%d–%d vs 总结 .md，按节）' % (first, last), '']
    lines.append('- 总结小节: %s' % ', '.join(md_sections))
    lines.append('')
    lines.append('| 节 | 书源号 | 总结tag | 判定 | 相似度 | 书源OCR LaTeX | 书源上下文 |')
    lines.append('|---|---|---|---|---|---|---|')
    total_miss = 0
    for sec in md_sections:
        book_nums = sectioned.get(sec, {})
        md_tags = {t for t, _ in md_by_sec.get(sec, [])}
        # sort book numbers numerically
        def kn(n):
            c = re.sub(r'[a-zA-Z]$', '', n)
            return (int(re.sub(r'\D', '', c)) if re.sub(r'\D', '', c) else 0, n)
        for n in sorted(book_nums, key=kn):
            rec = book_nums[n]
            if n in md_tags:
                lines.append(f'| {sec} | {n} | {n} | 已在 | - | {rec["latex"][:55]} | {rec["ctx"][:40]} |')
                continue
            # missing in summary -> renumber check
            total_miss += 1
            bl = rec.get('latex', '')
            bt = toks(norm_latex(bl)) if bl else set()
            best_tag, best_sim = None, 0.0
            for (tn, tl) in global_idx:
                if not bt:
                    break
                sim = similar(bl, tl)
                if sim > best_sim:
                    best_sim, best_tag = sim, tn
            if best_tag and best_sim >= 0.55:
                judgment = '重编号?'
                ref = f'→总结\\tag{{{best_tag}}}'
            else:
                judgment = '真省略?'
                ref = '-'
            lines.append(f'| {sec} | {n} | {ref} | {judgment} | {best_sim:.2f} | {bl[:55]} | {rec["ctx"][:40]} |')
    lines.append('')
    lines.append(f'- 书源有而总结缺号的公式（MISSING 候选）合计: **{total_miss}**')
    lines.append('')
    lines.append('> 判定说明：「已在」=总结同节已有该号；「重编号?」=书源该号内容与总结另一tag公式高度相似（写手重编号，非真缺）；「真省略?」=总结无对应内容（需从书源重撰 LaTeX 后补入）。OCR 公式 LaTeX 扫花，所有 LaTeX 列仅供定位，最终以干净原书为准。')

    out = '\n'.join(lines)
    if out_md:
        with open(out_md, 'w', encoding='utf-8') as f:
            f.write(out)
        print('wrote', out_md, '| MISSING candidates:', total_miss)
    else:
        print(out)


if __name__ == '__main__':
    main()
