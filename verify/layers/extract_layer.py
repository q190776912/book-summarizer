# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 references/layers/extract.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""
extract_layer.py — EXTRACT provider (order 0).

Runs the extractor, performs the English two-level (ordinal=ORDINAL_EN) port, runs
label-consistency, and computes the STAGE-1 `ignored_hit` (confirmed-noise keys
removed from the extractor's key set BEFORE the A/B comparison). It also
populates the context fields the A/B layers depend on:

    ctx.items, ctx.entry_keys, ctx.all_keys, ctx.extracted,
    ctx.extraction_blocking, ctx.extraction_warnings, ctx.label_warns,
    ctx.ignored_hit (stage 1)

This is the only place that calls extract_items / extract_items_en, so the
"no global mutable state" rule holds — everything flows through `ctx`.

Self-contained implementation (bodies relocated from verify_chapter.py during the per-layer split).
"""
import json
import re
import os
from collections import defaultdict

from verify.layers.base import VerifyLayer, LayerResult
from verify.key_parse import (
    keys_in_md, _canon_label, _first_num, sortkey,
)
from lib.regexlib import SEP_TIGHT
from lib.config import ORDINAL_EN, ORDINAL_GM, ORDINAL_ROMAN, ORDINAL_THREE_LEVEL, ORDINAL_VAKIL
from extract.extract_items import extract_items, extract_items_en
from extract.extract_items_gm import extract_items_gm, int_to_roman
from extract.extract_items_vakil import extract_items_vakil


# ---------------------------------------------------------------------------
# Merged "重要概念首项完整性" (Q) + over-mark 守卫 — now part of B / 查漏层.
# Rationale (user 2026-08-05): B 层本就是"查漏"层，整类首项缺失与
# over-mark 误标都属于漏标/错标检测，无需独立 Q/R 层。两者复用 B 现有
# `blocking` / `warnings` 键，不加新契约键、不动核心 extract_items。
# ---------------------------------------------------------------------------
CAT_WORDS = ['定义', '定理', '引理', '推论', '命题']
EN_TO_CN = {'Definition': '定义', 'Theorem': '定理', 'Lemma': '引理',
            'Corollary': '推论', 'Proposition': '命题'}
# OCR 字母↔数字容错（章号首位）：扫描 raw page JSON 时把 A→4, B→8, O→0 …
OCR_DIGIT = {'O': 0, 'o': 0, 'Q': 0, 'D': 0, '0': 0,
             'I': 1, 'l': 1, 'i': 1, '1': 1,
             'Z': 2, 'z': 2, '2': 2,
             'A': 4, 'a': 4, '4': 4,
             'S': 5, 's': 5, '5': 5,
             'G': 6, 'g': 6, '6': 6,
             'T': 7, 't': 7, '7': 7,
             'B': 8, 'b': 8, '8': 8,
             'g': 9, '9': 9}


def _norm_ch(s):
    if s.isdigit():
        return int(s)
    return OCR_DIGIT.get(s)


# raw-text OCR-tolerant heading patterns (block-anchored with ^):
_CH = r'([0-9A-Za-z])'
_BOOK_LABEL_RES = [
    re.compile(r'^\s*(定义|定理|引理|推论|命题)\s*' + _CH + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)\b'),          # 定义4.7-1
    re.compile(r'^\s*(Definition|Theorem|Lemma|Corollary|Proposition)\s*' + _CH + SEP_TIGHT + r'(\d+)\b', re.IGNORECASE),  # Definition 4.7
    re.compile(r'^\s*' + _CH + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)\s*(定义|定理|引理|推论|命题)'),            # 4.7-1 定义
]


def _scan_book_category_items(ch, start, end, ext_dir):
    """Scan raw page JSON text blocks for category-heading items, OCR-tolerant on
    the chapter's first char (A→4 etc). Returns {(sec, cat): sorted[num,]}.
    Block-anchored (^) so cross-references like '由定义 4.7-1' are excluded."""
    by = defaultdict(list)
    for p in range(start, end + 1):
        fp = os.path.join(ext_dir, f'page_{p:03d}.json')
        if not os.path.exists(fp):
            continue
        try:
            d = json.load(open(fp, encoding='utf-8'))
        except Exception:
            continue
        for blk in d.get('text', []):
            t = blk.get('text', '').strip()
            if not t:
                continue
            for ri, rgx in enumerate(_BOOK_LABEL_RES):
                m = rgx.match(t)
                if not m:
                    continue
                if ri == 0:                      # 定义4.7-1
                    cat = m.group(1); chc = m.group(2)
                    sec = int(m.group(3)); num = int(m.group(4))
                elif ri == 1:                    # Definition 4.7
                    cat = EN_TO_CN.get(m.group(1).title(), '定义')
                    chc = m.group(2); sec = int(m.group(3)); num = int(m.group(4))
                else:                            # 4.7-1 定义
                    chc = m.group(1); sec = int(m.group(2)); num = int(m.group(3))
                    tail = t[m.end():m.end() + 8]
                    tm = re.search(r'(定义|定理|引理|推论|命题)', tail)
                    if not tm:
                        break
                    cat = tm.group(1)
                cc = _norm_ch(chc)
                if cc is None or cc != ch:
                    break
                by[(sec, cat)].append(num)
                break
    return {k: sorted(set(v)) for k, v in by.items()}


def _merged_category_first_missing(ctx, all_keys, blocking):
    """Q 逻辑并入 B：整类首项缺失检测。仅 three_level 方案启用（ordinal=3）。"""
    if ctx.config.primary_type != ORDINAL_THREE_LEVEL:
        return
    ch = ctx.ch
    book_cat = _scan_book_category_items(ch, ctx.start, ctx.end, ctx.ext_dir)
    if not book_cat:
        return
    # md 中各节已出现的编号（任何重要概念类别都算，避免同号异类误报）。
    # 注意：three-level 方案的 .md 键是数字型（如 3.3-2），不含类别前缀，
    # 故此处用数字型正则解析，不能套用带类别前缀的 _BOOK_LABEL_RES。
    md_by_sec = defaultdict(set)
    for k in all_keys:
        m = re.match(r'^(\d+)\.(\d+)-(\d+)$', k)
        if m and int(m.group(1)) == ch:
            md_by_sec[int(m.group(2))].add(int(m.group(3)))
    for (sec, cat), nums in book_cat.items():
        bmin = nums[0]
        if bmin in md_by_sec.get(sec, set()):
            continue                        # 该编号在总结中已出现（任何类别）→ 非首项缺失
        blocking.append(
            f"  ! §{ch}.{sec} 书中含「{cat}」{len(nums)} 条（首项 {cat}{ch}.{sec}-{bmin}），"
            f"但总结未含任何「{cat}」条目（编号 {bmin} 在总结中不存在）→ 疑似缺失首项 {cat}{ch}.{sec}-{bmin}")


def _merged_ocr_overmark_guard(ctx, items, warnings):
    """over-mark 守卫：.md 中带（OCR无法识别）的条目，若其编号已被 book 抽取识别
    → 误标警告（书中其实有该条目，不应标 OCR无法识别）。"""
    try:
        mdtext = open(ctx.md_file, encoding='utf-8').read()
    except Exception:
        return
    mark_re = re.compile(r'\*\*([^*]*?(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)[^*]*?)\*\*')
    md_mark = set()
    for m in mark_re.finditer(mdtext):
        if 'OCR无法识别' in m.group(0) or 'OCR无法识别' in m.group(1):
            md_mark.add(f"{int(m.group(2))}.{int(m.group(3))}-{int(m.group(4))}")
    if not md_mark:
        return
    book_num = set()
    for it in items:
        # agent_recovered (manual override) entries are NOT genuinely OCR-recognized;
        # an (OCR无法识别) marker on them is legitimate, so don't误-flag.
        if it.get('agent_recovered'):
            continue
        mm = re.search(r'(\d+)\.(\d+)-(\d+)', it['key'])
        if mm:
            book_num.add(f"{mm.group(1)}.{mm.group(2)}-{mm.group(3)}")
    for k in sorted(md_mark):
        if k in book_num and k not in ctx.ignore:
            warnings.append(
                f"  ? {k} 标注（OCR无法识别）但书中 OCR 已识别该条目 → 可能误标，请复核")


def check_label_consistency(items):
    """Return list of warning strings for items with label-vs-text mismatch."""
    import re
    LABEL_TEXT_PATTERNS = {
        '定义': r'定义[（(]',
        '定理': r'定理[（(]',
        '引理': r'引.{0,2}理[（(]',
    }
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
        for kw, pat in LABEL_TEXT_PATTERNS.items():
            if re.search(pat, text[:60]):
                if extracted != kw:
                    warns.append(f"  LABEL MISMATCH: {it['key']} has label='{extracted}' "
                                 f"but text contains '{kw}' (text: {text[:60]})")
                break
    return warns


class ExtractLayer(VerifyLayer):
    code = 'EXTRACT'
    order = 0
    auto_fixable = False

    def run(self, ctx):
        manual = ctx.manual_overrides
        cfg = ctx.config

        if ctx.config.primary_type == ORDINAL_EN:
            # English two-level book (ordinal=4): use the EN-aware extractor.
            # Its keys are "Definition 1.1" (English label + "N.M"); canonicalize
            # to the same Chinese form keys_in_md(ordinal=ORDINAL_EN) produces so
            # the A-layer comparison is meaningful (Definition->定义, Example->例,
            # ...). Drop any item whose leading number != ch (forward citations
            # to OTHER chapters).
            items = extract_items_en(ctx.ext_dir, ctx.start, ctx.end, want_examples=True)
            kept = []
            for it in items:
                lab, _, num = it['key'].partition(' ')
                chpart = num.split('.')[0]
                if chpart.isdigit() and int(chpart) != ctx.ch:
                    continue
                it['key'] = f"{_canon_label(lab)}{num}"
                kept.append(it)
            items = kept
            warnings, blocking = [], []
        elif ctx.config.primary_type in (ORDINAL_GM, ORDINAL_ROMAN):
            # Gelfand-Manin style (ordinal=6) / roman (ordinal=5): book-printed
            # headings in the .md, roman machine keys ("标签I.S-N" / "I.S-N").
            items, warnings, blocking = extract_items_gm(
                ctx.ext_dir, ctx.ch, ctx.start, ctx.end,
                manual_overrides=manual)
        elif ctx.config.primary_type == ORDINAL_VAKIL:
            # Vakil "Rising Sea": number-first three-level (N.M.item) + lettered
            # exercises; dedicated extractor returns only numbered items.
            items, warnings, blocking = extract_items_vakil(
                ctx.ext_dir, ctx.ch, ctx.start, ctx.end,
                manual_overrides=manual)
        else:
            # Single source of truth for the numbering convention: the
            # BookConfig.ordinal GroupConfig array carried on ctx.config
            # (same as the MD-side B-layer), not a parallel `numbering` proxy.
            items, warnings, blocking = extract_items(
                ctx.ext_dir, ctx.ch, ctx.start, ctx.end,
                manual_overrides=manual, cfg=cfg)

        label_warns = check_label_consistency(items)
        extracted_raw = {it['key'] for it in items}
        # Stage-1 ignored_hit: confirmed-noise keys present in the extract set.
        ignored_hit = sorted(extracted_raw & ctx.ignore, key=sortkey)
        # Remove confirmed-noise keys BEFORE the A/B comparison.
        extracted = extracted_raw - ctx.ignore

        if ctx.config.primary_type == ORDINAL_GM:
            # keys_in_md(group type=ORDINAL_GM) needs the md's roman chapter prefix;
            # the .md headings are bare per-section ordinals.
            entry_keys, all_keys = keys_in_md(
                ctx.md_file, groups=cfg.ordinal, chapter_roman=int_to_roman(ctx.ch))
        elif ctx.config.primary_type == ORDINAL_ROMAN:
            # keys_in_md(group type=ORDINAL_ROMAN) parses the roman chapter from the
            # .md text itself; chapter_roman is passed for symmetry.
            entry_keys, all_keys = keys_in_md(
                ctx.md_file, groups=cfg.ordinal, chapter_roman=int_to_roman(ctx.ch))
        else:
            entry_keys, all_keys = keys_in_md(ctx.md_file, groups=cfg.ordinal)
        if ctx.config.primary_type == ORDINAL_EN:
            entry_keys = {k for k in entry_keys if _first_num(k) == ctx.ch}
            all_keys = {k for k in all_keys if _first_num(k) == ctx.ch}

        # --- merged Q + over-mark 守卫（原独立 Q/R 层，现并入 B / 查漏层）---
        _merged_category_first_missing(ctx, all_keys, blocking)
        _merged_ocr_overmark_guard(ctx, items, warnings)

        # Populate context for A / B layers.
        ctx.items = items
        ctx.entry_keys = entry_keys
        ctx.all_keys = all_keys
        ctx.extracted = extracted
        ctx.extraction_blocking = blocking
        ctx.extraction_warnings = warnings
        ctx.label_warns = label_warns
        ctx.ignored_hit = ignored_hit

        return LayerResult(code=self.code, legacy=items, metadata={
            'items': items,
            'entry_keys': entry_keys,
            'blocking': blocking,
            'warnings': warnings,
            'label_warns': label_warns,
            'ignored_hit': ignored_hit,
        })
