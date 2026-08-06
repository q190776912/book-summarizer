# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 references/layers/d.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""
d_layer.py — D-LAYER (order 1): section-continuity + missing-tail-section check (BLOCKING).

Self-contained implementation (bodies relocated from verify_chapter.py during the per-layer split). Scans the RAW _extract JSON directly
and cross-checks against the written .md, INDEPENDENTLY of extract_items' output.

For ordinal=ORDINAL_GM (Gelfand-Manin style: "## §1." sections, "### N. Title" item
headings — legacy "**N.**" bold also accepted, roman machine keys) it uses
check_d_layer_gm, which reuses the
extractor's heading scan (extract.extract_items_gm.scan_gm_blocks).
"""
import re
import os
import json

from verify.layers.base import VerifyLayer, LayerResult
from verify.key_parse import GM_SEC_RE, GM_ENTRY_RE
from extract.extract_items_gm import scan_gm_blocks, _load_sections
from lib.regexlib import SEP_TIGHT
from lib.config import ORDINAL_GM, ORDINAL_ROMAN, ORDINAL_THREE_LEVEL

D_SEC_HEAD_A = re.compile(r'^(?:§|8)(\d+)' + SEP_TIGHT + r'(\d+)')   # §6.6 / 86.6 (OCR §->8 glued)
D_SEC_HEAD_B = re.compile(r'^(\d+)' + SEP_TIGHT + r'(\d+)\s+\S')     # 6.6 样条函数
D_SEC_HEAD_C = re.compile(r'§\s*(\d+)' + SEP_TIGHT + r'(\d+)')       # § 6.6 (short block)
D_ITEM_RE = re.compile(r'(\d{1,3})' + SEP_TIGHT + r'(\d{1,3})' + SEP_TIGHT + r'(\d{1,3})')  # N.S-N (no space sep -> no chain misread)
D_LABEL_KW = re.compile(
    r'(定义|定理|引理|命题|推论|例|公理|练习|评注|准则'
    r'|Definition|Theorem|Lemma|Proposition|Corollary|Example|Axiom|Exercise|Remark)')
D_MD_SEC_RE = re.compile(r'^##\s*§\s*(\d+)' + SEP_TIGHT + r'(\d+)')
# Nested subsection headers (### §C.S.T and deeper). A section that owns such
# nested subsections is a "subsection container", NOT an "item container"; source
# C.S.N numbers inside it are subsections, not labeled items. Used to suppress
# false tail-ordinal gaps on books whose items are 2-level (e.g. `定理 3.2`) while
# keeping genuine per-section examples (e.g. Ch3 §3.7 `3.7.1`/`3.7.2`).
D_MD_NESTED_SEC_RE = re.compile(r'^#{3,6}\s*§\s*(\d+)' + SEP_TIGHT + r'(\d+)')


def _d_is_labeled(txt, m):
    """True if a label keyword sits within +-10 chars of the item number."""
    lo = max(0, m.start() - 10)
    hi = min(len(txt), m.end() + 10)
    return bool(D_LABEL_KW.search(txt[lo:hi]))


def _partition_sections(md_sections, raw_sec_header, raw_labeled_item):
    """Split source-present-but-md-absent sections into two BLOCKING buckets.

    - continuity_sections: INTERIOR breaks — the chapter's section sequence has
      a hole (md has a smaller AND a larger section, but this one is missing).
      This mirrors B layer's item-level continuity, lifted to section
      granularity (the section analog of "缺号").
    - missing_sections: TAIL breaks — a section exists in raw (header + labeled
      item) but beyond md's last written section; the whole trailing section
      was simply not written.

    A section is only considered "present in source" when the raw JSON shows BOTH
    a section-header feature AND a labeled item, so chapters that legitimately
    skip a number are NOT false-flagged.  The two buckets are disjoint by
    construction (`s <= md_max` vs `s > md_max`).
    """
    raw_present = raw_sec_header & raw_labeled_item
    md_max = max(md_sections) if md_sections else 0
    missing = sorted(s for s in raw_present if s not in md_sections)
    continuity = [s for s in missing if s <= md_max]
    tail = [s for s in missing if s > md_max]
    return {'continuity_sections': continuity, 'missing_sections': tail}


def check_d_layer_gm(ch, start, end, md_file, ext):
    """Gelfand-Manin variant: sections are chapter-local ("## §1."), items are
    bare per-section ordinals ("### N. Title" / legacy "**N. ...**"), machine
    keys are roman."""
    with open(md_file, encoding='utf-8') as f:
        md_text = f.read()
    md_sections = set()
    for line in md_text.split('\n'):
        sm = GM_SEC_RE.match(line.strip())
        if sm:
            md_sections.add(int(sm.group(1)))
    sections = _load_sections(ext, ch)
    raw_sec_header = set()
    raw_labeled = set()
    for h in scan_gm_blocks(ext, start, end, sections):
        raw_sec_header.add(h['sec'])
        if h['num'] > 0:
            raw_labeled.add(h['sec'])
    return _partition_sections(md_sections, raw_sec_header, raw_labeled)


def check_d_layer(ch, start, end, md_file, ext, ordinal=ORDINAL_THREE_LEVEL):
    if ordinal in (ORDINAL_GM, ORDINAL_ROMAN):
        return check_d_layer_gm(ch, start, end, md_file, ext)
    with open(md_file, encoding='utf-8') as f:
        md_text = f.read()
    md_sections = set()
    for line in md_text.split('\n'):
        m = D_MD_SEC_RE.match(line.strip())
        if m and int(m.group(1)) == ch:
            md_sections.add(int(m.group(2)))
    raw_sec_header = set()
    raw_labeled_item = set()
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
                s = int(m.group(2))
                if _d_is_labeled(txt, m):
                    raw_labeled_item.add(s)
    return _partition_sections(md_sections, raw_sec_header, raw_labeled_item)


class DLayer(VerifyLayer):
    code = 'D'
    order = 1
    auto_fixable = False

    def run(self, ctx):
        d_layer = check_d_layer(ctx.ch, ctx.start, ctx.end, ctx.md_file,
                                ctx.ext_dir, ordinal=ctx.config.ordinal)
        ctx.d_layer = d_layer
        return LayerResult(code=self.code, legacy=d_layer, metadata={'d_layer': d_layer})
