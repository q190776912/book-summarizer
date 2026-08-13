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

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 verify/layers/figure_validity/figure_validity.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""
figure_validity.py — F-LAYER (order 6): figure validity (analog of C-layer).

Self-contained implementation of check_f_figure_validity (bodies relocated from the deleted fig_layers.py). When the
layer is skipped (figure_index.json absent / no entries for this chapter), it
emits EMPTY LISTS ([]), never None, so the merged result dict stays byte-compatible
with the legacy contract (guardrail #2 from the audit).
"""

from verify.layers.script.base import VerifyLayer, LayerResult

import os

from verify.common.fig_common import load_figure_index, cv2

def check_f_figure_validity(ch, ext):
    """F-LAYER: figure validity (analog of C-layer).

    Returns None if figure_index.json is absent OR this chapter has no figure
    entries (layer skipped). Otherwise a tuple (errors, warns). errors =
    blocking (missing/undecodable/too-small); warns = non-blocking (suspicious
    near-uniform crop). Only entries whose `chapter` field == ch are validated,
    because figure_index.json is a whole-book file shared across chapters.

    Uses cv2.imdecode(np.fromfile(...)) instead of cv2.imread because OpenCV's
    imread on Windows cannot open paths containing non-ASCII characters (e.g.
    Chinese book-folder names) — it returns None and spams "can't open/read
    file" warnings. np.fromfile handles Unicode paths, so imdecode decodes fine.
    """
    idx = load_figure_index(ext)
    if idx is None:
        return None
    has_chapter_field = any('chapter' in e for e in idx)
    ch_entries = [e for e in idx if (not has_chapter_field) or e.get('chapter') == ch]
    if not ch_entries:
        return None  # no figure extraction for this chapter -> skip
    if cv2 is None:
        return (['  ! cv2 unavailable — figure validity NOT checked (pip install opencv-python)'], [])
    import numpy as np
    errors, warns = [], []
    for e in ch_entries:
        # `e['file']` is a basename under the book's `_extract/figure/` subdir
        # (written that way by extract_figures.py). Joining ext+file would
        # resolve to `_extract/<file>` (which doesn't exist), so prepend `figure/`.
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
    return errors, warns

class FLayer(VerifyLayer):
    code = 'F'
    name = 'figure-validity'
    order = 6
    auto_fixable = False

    def run(self, ctx):
        f_res = check_f_figure_validity(ctx.ch, ctx.ext_dir)
        # Guardrail #2: emit [] when skipped (legacy: (f_res if f_res else ([], []))).
        fig_invalid, fig_invalid_warn = (f_res if f_res else ([], []))
        return LayerResult(code=self.code, legacy=f_res, metadata={
            'fig_invalid': fig_invalid,
            'fig_invalid_warn': fig_invalid_warn,
        })
