# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 references/layers/e.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""
e_layer.py — E-LAYER (order 5): figure completeness (analog of B-layer).

Self-contained implementation of check_e_figure_completeness (bodies relocated from the deleted fig_layers.py).
Skipped (returns None) when figure_index.json is absent OR this chapter has no
figure entries — the layer is then SKIPPED and never blocks.

HARD CONSTRAINT (code-reviewer F1): `fig_skipped` MUST equal `e_layer is None`
(full semantics: file-missing OR no figure entries for this chapter). It must
NOT be `ctx.figure_index is None` (file-missing only), which would wrongly mark
a chapter as NOT-skipped when the index exists but has no entries for this
chapter. The byte-level golden gate depends on this exact semantics.
"""

from verify.layers.base import VerifyLayer, LayerResult

import os, json

from verify.layers._fig_common import normfig, load_figure_index, FIG_CAP_RE, sortkey, cv2

def check_e_figure_completeness(ch, start, end, ext, ignore_fig=None):
    """E-LAYER: figure completeness (analog of B-layer).

    Returns None if figure_index.json is absent OR this chapter has no figure
    entries (figure extraction not run for this chapter) — the layer is then
    SKIPPED. Otherwise a dict with 'missing' (caption labels referenced in
    chapter OCR but not extracted) and 'extra' (extracted labels not found as
    captions in OCR). Only entries whose `chapter` field == ch are considered,
    because figure_index.json is a whole-book file shared across chapters.
    """
    ignore_fig = ignore_fig or set()
    idx = load_figure_index(ext)
    if idx is None:
        return None
    has_chapter_field = any('chapter' in e for e in idx)
    ch_entries = [e for e in idx if (not has_chapter_field) or e.get('chapter') == ch]
    if not ch_entries:
        return None  # no figure extraction for this chapter -> skip
    extracted = set()
    for e in ch_entries:
        if e.get('label'):
            extracted.add(normfig(e['label']))
    caption = set()
    for p in range(start, end + 1):
        fp = os.path.join(ext, f'page_{p:03d}.json')
        if not os.path.exists(fp):
            continue
        with open(fp, encoding='utf-8') as f:
            data = json.load(f)
        for t in data.get('text', []):
            txt = t.get('text', '')
            if not txt:
                continue
            for m in FIG_CAP_RE.finditer(txt):
                parts = m.group(1).split('.')
                if len(parts) >= 2 and int(parts[0]) == ch:
                    caption.add(normfig(m.group(1)))
    missing = sorted(caption - extracted - ignore_fig, key=sortkey)
    extra = sorted(extracted - caption, key=sortkey)
    return {'missing': missing, 'extra': extra}

class ELayer(VerifyLayer):
    code = 'E'
    order = 5
    fix_order = 5
    auto_fixable = False

    def run(self, ctx):
        e_layer = check_e_figure_completeness(
            ctx.ch, ctx.start, ctx.end, ctx.ext_dir, ctx.ignore)
        ctx.e_layer = e_layer
        fig_missing = e_layer['missing'] if e_layer else []
        fig_extra = e_layer['extra'] if e_layer else []
        fig_skipped = (e_layer is None)
        ctx.fig_skipped = fig_skipped
        return LayerResult(code=self.code, legacy=e_layer, metadata={
            'fig_missing': fig_missing,
            'fig_extra': fig_extra,
            'fig_skipped': fig_skipped,
        })
