#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reconcile_kreyszig.py
=====================
Kreyszig-specific, content-level formula reconciliation.

Kreyszig numbers formulas per *section* with a bare ``(N)`` that RESTARTS in
every ``§C.S`` (unlike Koopman's chapter-global ``C.N``).  The summary is a
*compression*: it drops some book formulas and **renumbers** the rest (e.g.
book §1.2 (10)(11)(12) = Hölder/CS/Minkowski become summary (7)(8)(9)).  A
pure label-set diff is therefore structurally blind (false MISSING on renumber,
false OK on placeholder-masked true omissions).

This tool does a CONTENT-level, within-section reconciliation:

  * Book side  : scan ``page_*.json`` text blocks for bare ``(N)`` labels,
                 scope each to its nearest preceding ``C.S`` heading (the
                 ``C.S-N`` definition/example headers reliably carry the
                 section prefix), and recover the nearest OCR formula LaTeX
                 via vertical-centroid alignment with ``formulas[].bbox``.
  * Summary side: reuse formula_manifest parsing; group labeled display
                 formulas by their ``## §C.S`` heading.
  * Alignment  : within each section, greedily match summary formulas to the
                 next unused book formula by normalized-LaTeX token Jaccard,
                 keeping reading order.  Classify every book formula as
                 COVERED (label matches), RENUMBERED (content matches, label
                 differs) or OMITTED (no summary content match); summary
                 formulas with no book match are EXTRA.

Output: per-chapter + global counts and a JSON dump of OMITTED candidates
(page / context / recovered latex) for spot-checking the scale claim.

Usage:
    python reconcile_kreyszig.py --extract-dir _extract --chapter-map chapter_map.json \
        --md-root . --chapter 1 [--out DIR]
    python reconcile_kreyszig.py --extract-dir _extract --chapter-map chapter_map.json \
        --md-root . --all [--out DIR]
"""
import argparse
import glob
import json
import os
import re
import sys

SKILL_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SKILL_ROOT)

from formula.formula_manifest import parse as parse_summary, normalize as normalize_summary

# --------------------------------------------------------------------------
# Book side
# --------------------------------------------------------------------------
# Bare (N) / （N）, 1-2 digits only -> rejects OCR noise like (1912).
LABEL_RE = re.compile(r'[（(]\s*(\d{1,2})\s*[）)]')


def _is_short_label_block(t):
    """A formula *definition* marker is a short, near-isolated '(N)' / '（N）'
    block.  A *reference* like '利用（7）和（4）便得到' lives inside a long
    prose line and must be rejected so it is not mistaken for a definition."""
    s = t.strip()
    if len(s) > 14:
        return False
    core = LABEL_RE.sub('', s).strip()
    return len(core) <= 4
# Section prefix C.S at start of a (short) definition/example header line.
HEAD_RE = re.compile(r'^\s*(\d+)\.(\d+)')


def _yc(bbox):
    """Vertical center of a [x1,y1,x2,y2] bbox (image coords, y down)."""
    if not bbox or len(bbox) < 4:
        return None
    return (bbox[1] + bbox[3]) / 2.0


def _h(bbox):
    if not bbox or len(bbox) < 4:
        return 0
    return bbox[3] - bbox[1]


_DISP_MARKERS = ('\\sum', '\\frac', '\\int', '\\left', '\\right', '\\leqslant',
                 '\\geq', '\\prod', '\\sqrt', '\\overline', '\\underbrace',
                 '\\begin', '\\Big', '\\bigcap', '\\bigcup', '\\lim')


def is_display(latex, bbox):
    """True for a *displayed* (numbered-equation) formula block, as opposed
    to an inline variable/short expression.  Definitions we reconcile against
    are displayed blocks; inline math and stray single variables are excluded
    so that prose references like '利用（7）和（4）' are not mistaken for
    formula definitions."""
    h = _h(bbox)
    if h >= 22:
        return True
    if h >= 14 and any(k in latex for k in _DISP_MARKERS):
        return True
    return False


def build_book_manifest(chapter, cmap, extract_dir, use_position_labels=False):
    info = cmap.get(str(chapter)) or cmap.get(chapter)
    start, end = info['start'], info['end']
    name = info.get('name_en') or info.get('name')

    headings = []          # (page, y, sec)  detected section anchors
    # Collect DEFINITIONS: substantial formula blocks with a tightly-attached
    # (N) label.  References in prose have no own formula block -> excluded.
    defs = []              # {label, page, pos_y(formula yc), latex, context}
    for pg in range(start, end + 1):
        fp = os.path.join(extract_dir, f'page_{pg:03d}.json')
        if not os.path.exists(fp):
            fp = os.path.join(extract_dir, f'page_{pg}.json')
        if not os.path.exists(fp):
            continue
        d = json.load(open(fp, encoding='utf-8'))
        # section anchors -- FILTER: only accept headings whose FIRST dotted
        # component equals the chapter.  OCR frequently lifts stray figure /
        # table / page numbers as pseudo-headings (e.g. "84.12", "3.10") which
        # would otherwise steal formulas from their real section.
        for b in d.get('text', []):
            t = b.get('text', '')
            poly = b.get('poly') or []
            y = poly[1] if len(poly) >= 2 else 0
            hm = HEAD_RE.match(t.strip())
            if hm and len(t.strip()) < 80:
                try:
                    if int(hm.group(1)) != int(chapter):
                        continue
                except ValueError:
                    continue
                headings.append((pg, y, f'{hm.group(1)}.{hm.group(2)}'))
        # labels on this page -- only short, isolated marker blocks count as
        # definitions; references embedded in prose are rejected.
        page_labels = []   # (y, N, context)
        for b in d.get('text', []):
            t = b.get('text', '')
            if not _is_short_label_block(t):
                continue
            poly = b.get('poly') or []
            y = poly[1] if len(poly) >= 2 else 0
            for m in LABEL_RE.finditer(t):
                page_labels.append((y, int(m.group(1)), t))
        # formula blocks -> definitions
        for fb in d.get('formulas', []):
            bb = fb.get('bbox')
            latex = fb.get('latex', '')
            if not is_display(latex, bb):
                continue
            cyc = _yc(bb)
            if cyc is None:
                continue
            win = max(55, _h(bb) / 2.0 + 30)
            best, bd = None, 1e9
            for ly, LN, ctx in page_labels:
                dy = abs(ly - cyc)
                if dy <= win and dy < bd:
                    bd, best = dy, (LN, ctx)
            if best:
                defs.append({'label': best[0], 'page': pg, 'pos_y': cyc,
                             'latex': latex, 'context': best[1]})

    # dedupe multi-part blocks that share (page, ocr_label): keep the
    # tallest / longest-latex block (a single displayed equation split across
    # several OCR formula blocks collapses to one definition).
    seen = {}
    for r in defs:
        r['ocr_label'] = r['label']
        key = (r['page'], r['label'])
        if key not in seen or len(r['latex']) > len(seen[key]['latex']):
            seen[key] = r
    defs = list(seen.values())
    defs.sort(key=lambda r: (r['page'], r['pos_y'] or 0))

    headings.sort()
    # scope each definition to the nearest preceding (filtered) heading
    scoped = {}
    for r in defs:
        sec = None
        for hpg, hy, hsec in headings:
            if (hpg, hy) <= (r['page'], r['pos_y'] or 0):
                sec = hsec
            else:
                break
        scoped.setdefault(sec, []).append(r)

    def finalize(lst):
        """Drop restated references (near-identical LaTeX); keep only
        OCR-numbered blocks; repair scrambled labels.

        Kreyszig numbers only the *referenced* displayed equations, so we keep
        just the blocks that carry an OCR ``(N)`` (unnumbered auxiliary
        displays are excluded -- otherwise absolute numbers inflate).  Within a
        section the true numbers increase strictly by 1 between consecutive
        numbered equations; any OCR value that *decreases* (< previous) or
        jumps implausibly far (> previous+5, e.g. 36/56/86 from stray
        figure/page OCR) is a misread and is collapsed to previous+1.  This
        reproduces the clean sections exactly and repairs the scrambled ones
        without inventing unnumbered positions.
        """
        out = []
        for r in lst:
            if r['latex'].strip() and any(
                    r['latex'].strip() == o['latex'].strip()
                    or similar(r['latex'], o['latex']) >= 0.95
                    for o in out):
                continue   # restated reference -> drop
            if r.get('ocr_label') is None:
                continue   # unnumbered auxiliary display -> exclude
            out.append(r)
        if use_position_labels:
            prev = None
            for r in out:
                o = r['ocr_label']
                if prev is None:
                    prev = o
                    r['label'] = o
                elif o <= prev or o > prev + 5:
                    prev = prev + 1
                    r['label'] = prev
                else:
                    prev = o
                    r['label'] = o
        return out

    secs = {}
    unscoped = []
    for s, lst in scoped.items():
        if s is None:
            unscoped = finalize(lst)
        else:
            secs[s] = finalize(lst)
    return {
        'chapter': chapter,
        'chapter_name': name,
        'page_range': [start, end],
        'sections': secs,
        'unscoped': unscoped,
        'headings': [(h[0], h[1], h[2]) for h in headings],
    }


# --------------------------------------------------------------------------
# Summary side
# --------------------------------------------------------------------------
def build_summary_manifest(md_path):
    recs = parse_summary(md_path)
    secs = {}              # sec -> list of {label, content, line, heading}
    for r in recs:
        if r['kind'] != 'display' or not r.get('summary_label'):
            continue
        # summary_label is like "7" (bare N); keep as int when possible
        raw = r['summary_label']
        try:
            lab = int(re.match(r'\s*(\d+)', raw).group(1))
        except Exception:
            lab = raw
        sec = r.get('section')
        secs.setdefault(sec, []).append({
            'label': lab,
            'content': r['content_summary'],
            'line': r['line'],
            'heading': r.get('heading'),
        })
    for s in secs:
        secs[s].sort(key=lambda x: x['line'])
    return {'file': os.path.basename(md_path), 'sections': secs}


# --------------------------------------------------------------------------
# Content similarity
# --------------------------------------------------------------------------
_TOKEN_RE = re.compile(r'[a-zA-Z]+|\d+|[\\][a-zA-Z]+|[<>≤≥=+\-*/|.,;:()\[\]{}^_~]')


def norm_tokens(s):
    """Leaf-token multiset: keep command words, variable letters, operators,
    digits.  Lower-cased.  Designed to survive light OCR garbling (j<->1,
    p<->ρ) well enough for Jaccard signal."""
    if not s:
        return set()
    s = s.lower()
    toks = _TOKEN_RE.findall(s)
    out = []
    for t in toks:
        if t.startswith('\\'):
            out.append(t)              # \sum \frac \infty ...
        elif t.isalpha() and len(t) == 1:
            out.append(t)              # single variable
        elif re.fullmatch(r'[<>≤≥=+\-*/|.,;:()\[\]{}^_~]', t):
            out.append(t)              # operators / punctuation
        elif t.isdigit():
            out.append('#')            # collapse numerals -> presence only
    return set(out)


def similar(a, b, thresh=0.18):
    if not a or not b:
        return 0.0
    ta, tb = norm_tokens(a), norm_tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


# --------------------------------------------------------------------------
# Alignment
# --------------------------------------------------------------------------
def align_section(book_list, sum_list, thresh=0.18):
    """Order-preserving greedy match.  The summary is treated as an
    order-preserving *subsequence* of the book (compression: some book
    formulas dropped = OMITTED, the rest renumbered).  For each summary
    formula we take the FIRST unused book formula (from the cursor onward,
    within a bounded window) whose content similarity passes -- NOT the
    globally best, so reading order is respected and an earlier book formula
    is never wrongly skipped.  Returns (matches, omitted, extra)."""
    matched = [False] * len(book_list)
    cursor = 0
    matches = []          # (book_rec, sum_rec, kind, score)
    extra = []
    for s in sum_list:
        chosen = None
        for i in range(cursor, len(book_list)):
            if matched[i]:
                continue
            if i - cursor > 15:        # bound the skip window
                break
            sc = similar(book_list[i].get('latex'), s['content'], thresh)
            if sc >= thresh:
                chosen, chosen_sc = i, sc
                break                  # FIRST eligible -> respects order
        if chosen is not None:
            matched[chosen] = True
            cursor = chosen + 1
            bk = book_list[chosen]
            kind = 'COVERED' if str(bk['label']) == str(s['label']) else 'RENUMBERED'
            matches.append((bk, s, kind, round(chosen_sc, 3)))
        else:
            extra.append(s)
    omitted = [book_list[i] for i in range(len(book_list)) if not matched[i]]
    return matches, omitted, extra


# --------------------------------------------------------------------------
# Driver
# --------------------------------------------------------------------------
def reconcile_chapter(chapter, extract_dir, cmap, md_root, out_dir=None,
                      thresh=0.18):
    bm = build_book_manifest(chapter, cmap, extract_dir)
    md_files = glob.glob(os.path.join(md_root, f'第{chapter}章_*.md'))
    if not md_files:
        md_files = glob.glob(os.path.join(md_root, f'*{chapter}*.md'))
    if not md_files:
        raise SystemExit(f'no summary md for chapter {chapter}')
    sm = build_summary_manifest(md_files[0])

    per_sec = {}
    all_omitted = []
    all_extra = []
    covered = renumbered = 0
    for sec, blist in bm['sections'].items():
        slist = sm['sections'].get(sec, [])
        matches, omitted, extra = align_section(blist, slist, thresh)
        c = sum(1 for _bk, _s, k, _sc in matches if k == 'COVERED')
        r = sum(1 for _bk, _s, k, _sc in matches if k == 'RENUMBERED')
        covered += c
        renumbered += r
        per_sec[sec] = {
            'book': len(blist), 'summary': len(slist),
            'covered': c, 'renumbered': r,
            'omitted': len(omitted), 'extra': len(extra),
        }
        for o in omitted:
            o2 = dict(o); o2['section'] = sec; all_omitted.append(o2)
        for e in extra:
            e2 = dict(e); e2['section'] = sec; all_extra.append(e2)

    # unscoped book labels -> try to match against any summary section
    unsc = bm['unscoped']
    if unsc:
        all_slist = [(sec, s) for sec, sl in sm['sections'].items() for s in sl]
        for u in unsc:
            best, bs = None, 0.0
            for sec, s in all_slist:
                sc = similar(u.get('latex'), s['content'], thresh)
                if sc > bs:
                    best, bs = (sec, s), sc
            if best and bs >= thresh:
                per_sec.setdefault('_unscoped', {'book': 0, 'summary': 0,
                    'covered': 0, 'renumbered': 0, 'omitted': 0, 'extra': 0})
                per_sec['_unscoped']['book'] += 1
                # treat as covered/renumbered loosely
                if str(u['label']) == str(best[1]['label']):
                    per_sec['_unscoped']['covered'] += 1; covered += 1
                else:
                    per_sec['_unscoped']['renumbered'] += 1; renumbered += 1
            else:
                per_sec.setdefault('_unscoped', {'book': 0, 'summary': 0,
                    'covered': 0, 'renumbered': 0, 'omitted': 0, 'extra': 0})
                per_sec['_unscoped']['book'] += 1
                per_sec['_unscoped']['omitted'] += 1
                o2 = dict(u); o2['section'] = '_unscoped'; all_omitted.append(o2)

    book_total = sum(len(v) for v in bm['sections'].values()) + len(bm['unscoped'])
    summary_labeled = sum(len(v) for v in sm['sections'].values())
    result = {
        'chapter': chapter,
        'chapter_name': bm['chapter_name'],
        'page_range': bm['page_range'],
        'book_total': book_total,
        'summary_labeled': summary_labeled,
        'covered': covered,
        'renumbered': renumbered,
        'omitted': len(all_omitted),
        'extra': len(all_extra),
        'per_section': per_sec,
        'omitted_candidates': all_omitted,
        'extra_candidates': all_extra,
    }
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, f'recon_ch{chapter}.json'),
                  'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--extract-dir', required=True)
    ap.add_argument('--chapter-map', required=True)
    ap.add_argument('--md-root', required=True)
    ap.add_argument('--chapter', type=int, default=None)
    ap.add_argument('--all', action='store_true')
    ap.add_argument('--out', default=None)
    ap.add_argument('--thresh', type=float, default=0.18)
    args = ap.parse_args()

    cmap = json.load(open(args.chapter_map, encoding='utf-8'))
    chapters = ([args.chapter] if args.chapter
                else [int(k) for k in cmap.keys()]) if not args.all else \
               [int(k) for k in cmap.keys()]
    if args.all:
        chapters = sorted(int(k) for k in cmap.keys())

    results = []
    for ch in chapters:
        try:
            r = reconcile_chapter(ch, args.extract_dir, cmap, args.md_root,
                                  args.out, args.thresh)
        except SystemExit as e:
            print(f'  skip ch{ch}: {e}')
            continue
        results.append(r)
        print(f"ch{ch:>2} {r['chapter_name'][:18]:<18} "
              f"book={r['book_total']:>3} sum={r['summary_labeled']:>3} "
              f"cov={r['covered']:>3} ren={r['renumbered']:>3} "
              f"omit={r['omitted']:>3} extra={r['extra']:>2}")

    if args.out and results:
        agg = {
            'threshold': args.thresh,
            'per_chapter': results,
            'global': {
                'book_total': sum(r['book_total'] for r in results),
                'summary_labeled': sum(r['summary_labeled'] for r in results),
                'covered': sum(r['covered'] for r in results),
                'renumbered': sum(r['renumbered'] for r in results),
                'omitted': sum(r['omitted'] for r in results),
                'extra': sum(r['extra'] for r in results),
            },
        }
        with open(os.path.join(args.out, 'recon_all.json'), 'w',
                  encoding='utf-8') as f:
            json.dump(agg, f, ensure_ascii=False, indent=2)
        print(f"\nGlobal: book={agg['global']['book_total']} "
              f"sum={agg['global']['summary_labeled']} "
              f"cov={agg['global']['covered']} "
              f"ren={agg['global']['renumbered']} "
              f"omit={agg['global']['omitted']} "
              f"extra={agg['global']['extra']}")
        print(f"wrote {os.path.join(args.out, 'recon_all.json')}")


if __name__ == '__main__':
    main()
