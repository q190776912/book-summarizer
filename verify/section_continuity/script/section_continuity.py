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

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 verify/section_continuity/section_continuity.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""
section_continuity.py — D-LAYER (order 1): section-continuity + missing-tail-section check (BLOCKING).

Self-contained implementation (bodies relocated from verify_chapter.py during the per-layer split). Scans the RAW _extract JSON directly and cross-checks against the written .md, INDEPENDENTLY of extract_items' output.

The D-layer now supports an ARBITRARY nested section hierarchy (1–4 levels: chapter / section / subsection / sub-subsection) driven by ``BookConfig.section_types`` / ``section_depths``. For every detected numbering token it projects a prefix at every hierarchy level, then partitions missing sections into continuity (interior hole) vs tail (beyond last written) buckets PER LEVEL. The legacy two-level behaviour is preserved: ordinals 2/4/6/7 verify chapter + section only; ordinals 3/5 additionally verify the subsection (1.1.1) level for the first time (the old D_MD_NESTED_SEC_RE was dead code).

For ordinal=ORDINAL_GM / ORDINAL_ROMAN it uses check_d_layer_gm, which reuses the extractor's heading scan (extract.extract_items_gm.scan_gm_blocks).
"""
import re
import os
import json

from verify.script.base import VerifyLayer, LayerResult
from verify.script.key_parse import GM_SEC_RE, GM_ENTRY_RE
from verify.script.gm_scan import scan_gm_blocks, _load_sections
from lib.regexlib import SEP_TIGHT
from verify_config import (
    ORDINAL_GM, ORDINAL_ROMAN, ORDINAL_THREE_LEVEL, BookConfig, ORDINAL_SECTION_TYPES,
)

# Separator for splitting a captured dotted numbering token into int components.
# Mirrors the characters allowed by SEP_TIGHT (single source of truth in
# lib.regexlib) so the split matches what the matching regexes captured.
_SEP_RE = re.compile(r'[.\-–·/．－〜]')

# --- markdown section headers (`## § C.S[.K...]`) ----------------------------
# Generalized to 1..N components so any nesting depth is matched (chapter-level
# `## §1` through deep sub-subsections `###### §1.2.3.4`). The leading number is
# the chapter prefix and is compared against `ch` during the scan. Replaces the
# old fixed 2-component D_MD_SEC_RE + the dead D_MD_NESTED_SEC_RE.
D_MD_SEC_RE = re.compile(r'^#{2,6}\s*§\s*(\d+(?:' + SEP_TIGHT + r'\d+)*)')

# --- raw (OCR) section-header features (1..N components) ---------------------
# A: "§6.6" / "86.6" (OCR glues § -> 8).  B: "6.6 样条函数" (number then title).
# C: "§ 6.6" short block (kept for the brief header lines < 60 chars).
D_SEC_HEAD_A = re.compile(r'^(?:§|8)(\d+(?:' + SEP_TIGHT + r'\d+)*)')
D_SEC_HEAD_B = re.compile(r'^(\d+(?:' + SEP_TIGHT + r'\d+)*)\s+\S')
D_SEC_HEAD_C = re.compile(r'§\s*(\d+(?:' + SEP_TIGHT + r'\d+)*)')

# D_ITEM_RE is BUILT dynamically per chapter from `max(cfg.section_depths)`
# (see `_build_item_re`). The old fixed 3-component regex is replaced because the
# hierarchy depth is now book-configurable; hi = the deepest level's component
# count so a labeled item is never truncated.

D_LABEL_KW = re.compile(
    r'(定义|定理|引理|命题|推论|例|公理|练习|评注|准则'
    r'|Definition|Theorem|Lemma|Proposition|Corollary|Example|Axiom|Exercise|Remark)')

# Item-regex cache keyed by hi (built lazily, module-level so repeated calls in
# a run reuse the compiled pattern).
_ITEM_RE_CACHE = {}


def _build_item_re(hi):
    """Build (and cache) the labeled-item regex matching `hi` numeric components (1..N)."""
    hi = max(int(hi), 1)
    if hi in _ITEM_RE_CACHE:
        return _ITEM_RE_CACHE[hi]
    parts = [r'(\d{1,3})']
    for _ in range(hi - 1):
        parts.append(SEP_TIGHT + r'(\d{1,3})')
    rx = re.compile(''.join(parts))
    _ITEM_RE_CACHE[hi] = rx
    return rx


def _split_num(s):
    """Split a dotted numbering token (e.g. '1.2.3') into a list of ints."""
    try:
        return [int(p) for p in _SEP_RE.split(s) if p != '']
    except ValueError:
        return []


def _project(c, section_depths, target):
    """Project the full component list `c` into `target[L]` (set of prefixes) for
    every hierarchy level L whose depth <= len(c).

    A token 'C.S.K' (3 components) contributes (C,) at level 1, (C,S) at level 2
    and (C,S,K) at level 3 — i.e. a subsection header automatically satisfies its
    parent section / chapter prefixes too.
    """
    for L in range(1, len(section_depths) + 1):
        depth = section_depths[L - 1]
        if depth <= len(c):
            target[L].add(tuple(c[:depth]))


def _rel_path(t):
    """Relative-to-chapter path string (drops the leading chapter component):
    (1, 2) -> '2', (1, 2, 3) -> '2.3'."""
    return '.'.join(str(x) for x in t[1:])


def _d_is_labeled(txt, m):
    """True if a label keyword sits within +-10 chars of the item number."""
    lo = max(0, m.start() - 10)
    hi = min(len(txt), m.end() + 10)
    return bool(D_LABEL_KW.search(txt[lo:hi]))


# ---------------------------------------------------------------------------
# GM (Gelfand-Manin) path — UNCHANGED (kept intact; uses _partition_sections).
# ---------------------------------------------------------------------------

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
    keys are roman"""
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


# ---------------------------------------------------------------------------
# Generalized (CN/EN) path — nested 1..N section hierarchy.
# ---------------------------------------------------------------------------

def _partition_sections_by_level(md_sections, raw_sec_header, raw_labeled_item, max_level):
    """Generalized per-level partition (1..N hierarchy levels).

    For each level L, take the source-present sections (raw header ∩ labeled
    item), compare against what the .md wrote at that level, and split the
    missing ones into:
      * continuity — interior holes (md has a smaller AND a larger prefix)
      * tail       — beyond md's last written prefix at this level
    Returns the top-level merged lists (relative-to-chapter path strings) plus a
    per-level breakdown dict consumed by report.py.
    """
    levels = {}
    continuity_all = []
    missing_all = []
    for L in range(1, max_level + 1):
        raw_present = raw_sec_header[L] & raw_labeled_item[L]
        md_max = max(md_sections[L]) if md_sections[L] else None
        missing = sorted(s for s in raw_present if s not in md_sections[L])
        continuity = [s for s in missing if md_max and s <= md_max]
        tail = [s for s in missing if not md_max or s > md_max]
        levels[L] = {
            'continuity': [_rel_path(s) for s in continuity],
            'missing': [_rel_path(s) for s in tail],
        }
        continuity_all.extend(continuity)
        missing_all.extend(tail)
    continuity_sections = [_rel_path(s) for s in sorted(set(continuity_all))]
    missing_sections = [_rel_path(s) for s in sorted(set(missing_all))]
    return {
        'continuity_sections': continuity_sections,
        'missing_sections': missing_sections,
        'levels': levels,
    }


def check_d_layer(ch, start, end, md_file, ext, cfg=None, ordinal=ORDINAL_THREE_LEVEL):
    """Common (CN/EN) section-continuity check supporting an arbitrary nesting
    depth (1–4) from ``cfg.section_depths``.

    When ``cfg`` is not supplied (legacy callers) it is reconstructed from
    ``ordinal`` via BookConfig (back-compat). GM / Roman books route to
    check_d_layer_gm (2-level chapter-local semantics, no nested `levels`).
    """
    if cfg is None:
        cfg = BookConfig(ordinal=ordinal)
    if cfg.primary_type in (ORDINAL_GM, ORDINAL_ROMAN):
        return check_d_layer_gm(ch, start, end, md_file, ext)
    # Resolve the verified hierarchy. Real configs come via ConfigLoader ->
    # from_dict (section_depths populated); fall back to the ordinal default so
    # a directly-constructed BookConfig still verifies something sensible.
    section_depths = list(cfg.section_depths) or list(
        ORDINAL_SECTION_TYPES.get(cfg.primary_type, [1]))
    max_level = len(section_depths)
    hi = max(section_depths) if section_depths else 3
    d_item_re = _build_item_re(hi)

    with open(md_file, encoding='utf-8') as f:
        md_text = f.read()
    md_sections = {L: set() for L in range(1, max_level + 1)}
    for line in md_text.split('\n'):
        m = D_MD_SEC_RE.match(line.strip())
        if not m:
            continue
        c = _split_num(m.group(1))
        if not c or c[0] != ch:
            continue
        _project(c, section_depths, md_sections)

    raw_sec_header = {L: set() for L in range(1, max_level + 1)}
    raw_labeled_item = {L: set() for L in range(1, max_level + 1)}
    for p in range(start, end + 1):
        fp = os.path.join(ext, f'page_{p:03d}.json')
        if not os.path.exists(fp):
            continue
        with open(fp, encoding='utf-8') as f:
            data = page_json.PageJson.load(os.path.join(ext, f'page_{p:03d}.json')).data
        for t in data.get('text', []):
            txt = t.get('text', '').strip()
            if not txt:
                continue
            for rgx in (D_SEC_HEAD_A, D_SEC_HEAD_B):
                m = rgx.match(txt)
                if m:
                    c = _split_num(m.group(1))
                    if c and c[0] == ch:
                        _project(c, section_depths, raw_sec_header)
            m = D_SEC_HEAD_C.search(txt)
            if m and len(txt) < 60:
                c = _split_num(m.group(1))
                if c and c[0] == ch:
                    _project(c, section_depths, raw_sec_header)
            for m in d_item_re.finditer(txt):
                c = [int(g) for g in m.groups()]
                if c[0] != ch or c[-1] == 0:
                    continue
                if _d_is_labeled(txt, m):
                    _project(c, section_depths, raw_labeled_item)

    return _partition_sections_by_level(md_sections, raw_sec_header, raw_labeled_item, max_level)


class DLayer(VerifyLayer):
    code = 'D'
    name = 'section-continuity'
    order = 1
    auto_fixable = False

    def run(self, ctx):
        cfg = ctx.config
        d_layer = check_d_layer(ctx.ch, ctx.start, ctx.end, ctx.md_file,
                                ctx.ext_dir, cfg=cfg)
        ctx.d_layer = d_layer
        return LayerResult(code=self.code, legacy=d_layer, metadata={'d_layer': d_layer})
