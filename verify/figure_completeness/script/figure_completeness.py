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

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见
# verify/figure_completeness/figure_completeness.md（SSOT）；本文件仅含实现，勿在此复述叙事。

"""
figure_completeness.py — E-LAYER (order 5): unified FIGURE layer.

Merges the former E (completeness) and F (validity) layers into a single
figure layer. Both consumed the same whole-book `figure_index.json` and shared
the identical SKIP precondition (absent index OR no entries for this chapter),
so unifying removes a duplicate index load + chapter-filter pass.

Checks performed (all on chapter-filtered index entries):
  * completeness (was E): caption labels referenced in chapter OCR but absent
    from figure_index.json -> `fig_missing` (blocking FAIL); extracted labels
    with no OCR caption -> `fig_extra` (WARN only).
  * validity (was F): each cropped PNG decoded via cv2 (np.fromfile+imdecode to
    survive Unicode paths); missing/undecodable/too-small -> `fig_invalid`
    (blocking FAIL); near-blank low-variance crop -> `fig_invalid_warn` (WARN).

HARD CONSTRAINT (code-reviewer F1): `fig_skipped` MUST equal `result is None`
(full semantics: file-missing OR no figure entries for this chapter). It must
NOT be narrowed to `ctx.figure_index is None`. The byte-level golden gate
depends on this exact semantics.
"""

from verify.script.base import VerifyLayer, LayerResult

import os, json

from page_json import PageJson
from verify.common.fig_common import normfig, load_figure_index, fig_cap_re, sortkey, cv2


def _chapter_entries(idx, ch):
    """Whole-book figure_index.json filtered to this chapter (or all entries if
    the file has no `chapter` field). Returns [] when there is nothing for ch."""
    has_chapter_field = any('chapter' in e for e in idx)
    return [e for e in idx if (not has_chapter_field) or e.get('chapter') == ch]


def check_figure(ch, start, end, ext, ignore_fig=None):
    """Unified E+F figure layer.

    Returns None if figure_index.json is absent OR this chapter has no figure
    entries (figure extraction not run for this chapter) — the layer is then
    SKIPPED. Otherwise a dict with keys:
      missing       caption labels referenced in OCR but not extracted (FAIL)
      extra         extracted labels not found as OCR captions (WARN)
      invalid       blocking file errors: missing/undecodable/too-small (FAIL)
      invalid_warn  non-blocking: near-blank low-variance crop (WARN)
    """
    ignore_fig = ignore_fig or set()
    idx = load_figure_index(ext)
    if idx is None:
        return None
    ch_entries = _chapter_entries(idx, ch)
    if not ch_entries:
        return None  # no figure extraction for this chapter -> skip

    # --- completeness (was E) ---
    extracted = set()
    for e in ch_entries:
        if e.get('label'):
            extracted.add(normfig(e['label']))
    caption = set()
    cap_re = fig_cap_re(ext)  # book-specific prefix set (verify_config.json figure.labels)
    for p in range(start, end + 1):
        fp = os.path.join(ext, f'page_{p:03d}.json')
        if not os.path.exists(fp):
            continue
        with open(fp, encoding='utf-8') as f:
            data = PageJson.load(fp).data
        for t in data.get('text', []):
            txt = t.get('text', '')
            if not txt:
                continue
            for m in cap_re.finditer(txt):
                parts = m.group(1).split('.')
                if len(parts) >= 2 and int(parts[0]) == ch:
                    caption.add(normfig(m.group(1)))
    missing = sorted(caption - extracted - ignore_fig, key=sortkey)
    extra = sorted(extracted - caption, key=sortkey)

    # --- validity (was F) ---
    errors, warns = [], []
    if cv2 is None:
        errors.append('  ! cv2 unavailable — figure validity NOT checked (pip install opencv-python)')
    else:
        import numpy as np
        for e in ch_entries:
            # `e['file']` is a basename under the book's `_extract/figure/` subdir
            # (written that way by extract_figures.py). Joining ext+file resolves
            # to `_extract/figure/<file>`; if a given book stores crops directly
            # under `_extract/`, adjust the prefix here. (Kept identical to the
            # former F layer — verify path resolution during smoke test.)
            fpath = os.path.join(ext, e.get('file', ''))
            lbl = e.get('label') or e.get('file')
            if not os.path.exists(fpath):
                errors.append(f"  x FIG MISSING FILE: {lbl} -> {e.get('file')}")
                continue
            try:
                with open(fpath, 'rb') as fh:
                    buf = np.fromfile(fh, dtype=np.uint8)
                arr = cv2.imdecode(buf, cv2.IMREAD_COLOR)
            except Exception as ex:
                errors.append(f"  x FIG UNREADABLE: {lbl} ({e.get('file')}) {ex}")
                continue
            if arr is None:
                errors.append(f"  x FIG UNREADABLE: {lbl} ({e.get('file')}) decode failed")
                continue
            h, w = arr.shape[:2]
            if w < 20 or h < 20:
                errors.append(f"  x FIG TOO SMALL: {lbl} ({w}x{h}) — likely false-positive sliver")
                continue
            gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
            var = float(gray.var())
            if var < 50:
                warns.append(f"  ? FIG LOW-VARIANCE: {lbl} (var={var:.0f}) — maybe blank/text misdetected")
    return {'missing': missing, 'extra': extra, 'invalid': errors, 'invalid_warn': warns}


class ELayer(VerifyLayer):
    code = 'E'
    name = 'figure'
    order = 5
    fix_order = 5
    auto_fixable = False

    def run(self, ctx):
        res = check_figure(ctx.ch, ctx.start, ctx.end, ctx.ext_dir, ctx.ignore)
        fig_skipped = (res is None)
        ctx.fig_skipped = fig_skipped
        if res is None:
            # double-guard: ensure every contract key present even when skipped
            res = {'missing': [], 'extra': [], 'invalid': [], 'invalid_warn': []}
        return LayerResult(code=self.code, legacy=res, metadata={
            'fig_missing': res['missing'],
            'fig_extra': res['extra'],
            'fig_invalid': res['invalid'],
            'fig_invalid_warn': res['invalid_warn'],
            'fig_skipped': fig_skipped,
        })
