"""
extract_layer.py — EXTRACT provider (order 0).

Runs the extractor, performs the English two-level (`scheme='en'`) port, runs
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

from verify.registry import VerifyLayer, LayerResult
from verify.key_parse import (
    keys_in_md, _canon_label, _first_num, sortkey,
)
from extract.extract_items import extract_items, extract_items_en
from extract.extract_items_gm import extract_items_gm, int_to_roman


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
        manual = None
        if ctx.manual_path and __import__('os').path.exists(ctx.manual_path):
            with open(ctx.manual_path, 'r', encoding='utf-8') as f:
                manual = json.load(f)

        if ctx.scheme == 'en':
            # English two-level book: use the EN-aware extractor. Its keys are
            # "Definition 1.1" (English label + "N.M"); canonicalize to the same
            # Chinese form keys_in_md('en') produces so the A-layer comparison is
            # meaningful (Definition->定义, Example->例, ...). Drop any item whose
            # leading number != ch (forward citations to OTHER chapters).
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
        elif ctx.scheme in ('gm', 'roman'):
            # Gelfand-Manin style: book-printed headings in the .md, roman
            # machine keys ("标签I.S-N" / "I.S-N").  'roman' is kept as a legacy
            # alias for chapter_map.json entries written before the rename.
            items, warnings, blocking = extract_items_gm(
                ctx.ext_dir, ctx.ch, ctx.start, ctx.end,
                manual_overrides=manual)
        else:
            items, warnings, blocking = extract_items(
                ctx.ext_dir, ctx.ch, ctx.start, ctx.end,
                manual_overrides=manual, scheme=ctx.scheme)

        label_warns = check_label_consistency(items)
        extracted_raw = {it['key'] for it in items}
        # Stage-1 ignored_hit: confirmed-noise keys present in the extract set.
        ignored_hit = sorted(extracted_raw & ctx.ignore_keys, key=sortkey)
        # Remove confirmed-noise keys BEFORE the A/B comparison.
        extracted = extracted_raw - ctx.ignore_keys

        if ctx.scheme in ('gm', 'roman'):
            # keys_in_md('gm') needs the md's roman chapter prefix, which is
            # known only here (the .md headings are bare per-section ordinals).
            entry_keys, all_keys = keys_in_md(
                ctx.md_file, scheme='gm', chapter_roman=int_to_roman(ctx.ch))
        else:
            entry_keys, all_keys = keys_in_md(ctx.md_file, scheme=ctx.scheme)
        if ctx.scheme == 'en':
            entry_keys = {k for k in entry_keys if _first_num(k) == ctx.ch}
            all_keys = {k for k in all_keys if _first_num(k) == ctx.ch}

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
