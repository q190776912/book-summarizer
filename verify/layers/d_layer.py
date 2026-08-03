# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 references/layers/d.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""
d_layer.py — D-LAYER (order 1): section-missing & tail-ordinal check.

Self-contained implementation (bodies relocated from verify_chapter.py during the per-layer split). Scans the RAW _extract JSON directly
and cross-checks against the written .md, INDEPENDENTLY of extract_items' output.

For scheme='gm' (Gelfand-Manin style: "## §1." sections, "### N. Title" item
headings — legacy "**N.**" bold also accepted, roman machine keys) it uses
check_d_layer_gm, which reuses the
extractor's heading scan (extract.extract_items_gm.scan_gm_blocks).
"""
import re
import os
import json

from verify.registry import VerifyLayer, LayerResult
from verify.key_parse import GM_SEC_RE, GM_ENTRY_RE
from extract.extract_items_gm import scan_gm_blocks, _load_sections

D_SEC_HEAD_A = re.compile(r'^(?:§|8)(\d+)\.(\d+)')   # §6.6 / 86.6 (OCR §->8 glued)
D_SEC_HEAD_B = re.compile(r'^(\d+)\.(\d+)\s+\S')     # 6.6 样条函数
D_SEC_HEAD_C = re.compile(r'§\s*(\d+)\.(\d+)')       # § 6.6 (short block)
D_ITEM_RE = re.compile(r'(\d{1,3})\.(\d{1,3})[.\-·](\d{1,3})')  # N.S-N (no space sep -> no chain misread)
D_LABEL_KW = re.compile(
    r'(定义|定理|引理|命题|推论|例|公理|练习|评注|准则'
    r'|Definition|Theorem|Lemma|Proposition|Corollary|Example|Axiom|Exercise|Remark)')
D_MD_SEC_RE = re.compile(r'^##\s*§\s*(\d+)\.(\d+)')


def _d_is_labeled(txt, m):
    """True if a label keyword sits within +-10 chars of the item number."""
    lo = max(0, m.start() - 10)
    hi = min(len(txt), m.end() + 10)
    return bool(D_LABEL_KW.search(txt[lo:hi]))


def check_d_layer_gm(ch, start, end, md_file, ext):
    """Gelfand-Manin variant: sections are chapter-local ("## §1."), items are
    bare per-section ordinals ("### N. Title" / legacy "**N. ...**"), machine
    keys are roman."""
    with open(md_file, encoding='utf-8') as f:
        md_text = f.read()
    md_sections = set()
    md_item_max = {}
    cur_sec = None
    for line in md_text.split('\n'):
        sm = GM_SEC_RE.match(line.strip())
        if sm:
            cur_sec = int(sm.group(1))
            md_sections.add(cur_sec)
            continue
        if cur_sec is None:
            continue
        for m in GM_ENTRY_RE.finditer(line):
            n = int(m.group(1))
            if n > 40:
                continue
            md_item_max.setdefault(cur_sec, n)
            if n > md_item_max[cur_sec]:
                md_item_max[cur_sec] = n

    sections = _load_sections(ext, ch)
    raw_sec_header = set()
    raw_labeled_item = {}
    for h in scan_gm_blocks(ext, start, end, sections):
        raw_sec_header.add(h['sec'])
        raw_labeled_item.setdefault(h['sec'], h['num'])
        if h['num'] > raw_labeled_item[h['sec']]:
            raw_labeled_item[h['sec']] = h['num']

    missing = sorted(s for s in raw_sec_header
                     if s in raw_labeled_item and s not in md_sections)
    tail = {}
    suspect = {}
    for s, rmax in raw_labeled_item.items():
        if s not in md_sections:
            continue
        mmax = md_item_max.get(s, 0)
        if rmax > mmax:
            if rmax - mmax > 5:
                suspect[s] = (mmax, rmax)
            else:
                tail[s] = (mmax, rmax)
    return {'missing_sections': missing, 'tail_gaps': tail, 'suspect': suspect}


def check_d_layer(ch, start, end, md_file, ext, scheme='three-level'):
    if scheme in ('gm', 'roman'):
        return check_d_layer_gm(ch, start, end, md_file, ext)
    with open(md_file, encoding='utf-8') as f:
        md_text = f.read()
    md_sections = set()
    md_item_max = {}
    for line in md_text.split('\n'):
        m = D_MD_SEC_RE.match(line.strip())
        if m and int(m.group(1)) == ch:
            md_sections.add(int(m.group(2)))
        if '**' in line:
            for m in D_ITEM_RE.finditer(line):
                if int(m.group(1)) != ch or int(m.group(3)) == 0:
                    continue
                s = int(m.group(2)); n = int(m.group(3))
                md_item_max.setdefault(s, n)
                if n > md_item_max[s]:
                    md_item_max[s] = n
    raw_sec_header = set()
    raw_labeled_item = {}
    for p in range(start, end + 1):
        fp = os.path.join(ext, f'page_{p:03d}.json')
        if not os.path.exists(fp):
            continue
        with open(fp, encoding='utf-8') as f:
            data = json.load(f)
        for t in data.get('text', []):
            txt = t.get('text', '').strip()
            if not txt:
                continue
            for rgx in (D_SEC_HEAD_A, D_SEC_HEAD_B):
                m = rgx.match(txt)
                if m and int(m.group(1)) == ch:
                    raw_sec_header.add(int(m.group(2)))
            m = D_SEC_HEAD_C.search(txt)
            if m and int(m.group(1)) == ch and len(txt) < 60:
                raw_sec_header.add(int(m.group(2)))
            for m in D_ITEM_RE.finditer(txt):
                if int(m.group(1)) != ch or int(m.group(3)) == 0:
                    continue
                s = int(m.group(2)); n = int(m.group(3))
                if _d_is_labeled(txt, m):
                    raw_labeled_item.setdefault(s, n)
                    if n > raw_labeled_item[s]:
                        raw_labeled_item[s] = n
    missing = sorted(s for s in raw_sec_header
                     if s in raw_labeled_item and s not in md_sections)
    tail = {}
    suspect = {}
    for s, rmax in raw_labeled_item.items():
        if s not in md_sections:
            continue
        mmax = md_item_max.get(s, 0)
        if rmax > mmax:
            if rmax - mmax > 5:
                suspect[s] = (mmax, rmax)
            else:
                tail[s] = (mmax, rmax)
    return {'missing_sections': missing, 'tail_gaps': tail, 'suspect': suspect}


class DLayer(VerifyLayer):
    code = 'D'
    order = 1
    auto_fixable = False

    def run(self, ctx):
        d_layer = check_d_layer(ctx.ch, ctx.start, ctx.end, ctx.md_file,
                                ctx.ext_dir, scheme=ctx.scheme)
        ctx.d_layer = d_layer
        return LayerResult(code=self.code, legacy=d_layer, metadata={'d_layer': d_layer})
