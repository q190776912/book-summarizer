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

import os, json, re

from page_json import PageJson
from verify.script.fig_common import normfig, load_figure_index, fig_cap_re, sortkey, cv2
from lib.figure_io import load_fig_components


# --- attribution (figure -> owning item block) ---------------------------------
# Captures the blind spot: a figure (<img>) whose caption/alt references an item
# (e.g. "Example 1.5-9") but floats OUTSIDE that item's block (typically outside
# the `>` blockquote that the item lives in). E/F/H layers do not check this.
_ITEM_TITLE_RE = re.compile(r'^\s*(?:>\s*)?\*\*\s*(\d+\.\d+-\d+)\b')
_SECTION_RE = re.compile(r'^\s*##\s*§?\s*(\d+\.\d+)\b')
_IMG_RE = re.compile(r'^\s*<img\b')
_IMG_SRC_ALT = re.compile(r'src="([^"]+)"\s+alt="([^"]*)"')
# alt item ref: "Example 1.5-9" / "Theorem 1.3-4" / "proof of Theorem 1.6-2" / "Def. 1.3-3"
_ALT_ITEM_RE = re.compile(
    r'(?:Example|Theorem|Lemma|Corollary|Definition|Def\.?|'
    r'Proof\s+of\s+(?:a\s+)?(?:Theorem|Lemma|Corollary))\s*(\d+\.\d+-\d+)',
    re.I,
)


def _logical_blocks(lines):
    """Split md into logical blocks. Each block = (kind, start, end, item_ref).

    kind: 'blockquote' (lines starting with `>`), 'section' (`## `),
          'item_top' (top-level `**N.M-K**` not inside a `>` block),
          'floating' (a bare <div>/<img> group with no `>` prefix),
          'other' (skipped).
    item_ref is the `N.M-K` parsed from a `**N.M-K**` title, else None.
    """
    n = len(lines)
    blocks, i = [], 0
    while i < n:
        stripped = lines[i].lstrip()
        if stripped == '':
            i += 1
            continue
        if stripped.startswith('>'):
            j = i
            while j + 1 < n and (lines[j + 1].lstrip().startswith('>') or lines[j + 1].strip() == ''):
                j += 1
            while j > i and lines[j].strip() == '':
                j -= 1
            m = _ITEM_TITLE_RE.match(lines[i])
            blocks.append(('blockquote', i, j, m.group(1) if m else None))
            i = j + 1
        elif stripped.startswith('##'):
            m = _SECTION_RE.match(lines[i])
            blocks.append(('section', i, i, m.group(1) if m else None))
            i += 1
        elif _ITEM_TITLE_RE.match(lines[i]):
            j = i
            while j + 1 < n:
                nxt = lines[j + 1].lstrip()
                if nxt.startswith('##') or _ITEM_TITLE_RE.match(nxt):
                    break
                j += 1
            while j > i and lines[j].strip() == '':
                j -= 1
            m = _ITEM_TITLE_RE.match(lines[i])
            blocks.append(('item_top', i, j, m.group(1) if m else None))
            i = j + 1
        elif stripped.startswith('<img') or stripped.startswith('<div'):
            j = i
            while j + 1 < n and (lines[j + 1].lstrip().startswith('<') or lines[j + 1].strip() == ''):
                j += 1
            blocks.append(('floating', i, j, None))
            i = j + 1
        else:
            i += 1
    return blocks


def check_figure_attribution(md_file):
    """Each `<img>` whose alt references an item (e.g. `Example 1.5-9`) must lie
    inside that item's block. For a blockquote item (`> **N.M-K**`) the figure
    MUST be inside the `>` block; a bare floating figure outside it is reported
    (WARN, non-blocking — the conservative embed strategy may legitimately place
    some figures outside, but the blind spot must be surfaced, not hidden).

    Returns a list of problem strings (empty when clean).
    """
    if not md_file or not os.path.exists(md_file):
        return []
    with open(md_file, encoding='utf-8') as f:
        lines = f.read().splitlines()
    blocks = _logical_blocks(lines)
    problems = []
    for bi, (kind, s, e, ref) in enumerate(blocks):
        if kind not in ('blockquote', 'item_top', 'floating'):
            continue
        for li in range(s, e + 1):
            ln = lines[li]
            if not _IMG_RE.match(ln):
                continue
            m = _IMG_SRC_ALT.search(ln)
            if not m:
                continue
            src, alt = m.group(1), m.group(2)
            am = _ALT_ITEM_RE.search(alt)
            want = am.group(1) if am else None
            # nearest owning item block (blockquote or item_top with a ref)
            owner_ref = owner_kind = None
            for bj in range(bi, -1, -1):
                k2, _s2, _e2, r2 = blocks[bj]
                if k2 in ('blockquote', 'item_top') and r2:
                    owner_ref, owner_kind = r2, k2
                    break
            if kind == 'floating':
                # floating figure: only a problem when the owning item is a
                # blockquote (figure should be inside its `>` block).
                if owner_kind == 'blockquote':
                    problems.append(
                        f"  ? FIG MISATTRIBUTED: {os.path.basename(src)} (alt={alt!r}) — "
                        f"floating outside its blockquote item {owner_ref}; "
                        f"should be moved inside the `>` block (line {li + 1})."
                    )
            elif kind == 'blockquote' and ref and owner_ref and ref != owner_ref:
                problems.append(
                    f"  ? FIG MISATTRIBUTED: {os.path.basename(src)} (alt={alt!r}) — "
                    f"inside blockquote item {ref} but nearest owning item is "
                    f"{owner_ref} (line {li + 1})."
                )
            elif kind == 'item_top' and want and owner_ref and want != owner_ref:
                problems.append(
                    f"  ? FIG MISATTRIBUTED: {os.path.basename(src)} (alt={alt!r}) — "
                    f"alt references {want} but sits in item {owner_ref} (line {li + 1})."
                )
    return problems


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
    cap_re = fig_cap_re(ext)  # book-specific prefix + component set (verify_config.json figure.labels / figure.components)
    components = load_fig_components(ext)  # 1=global int, 2=ch.fig (default), 3=ch.sec.fig
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
                num = m.group(1)
                if components == 1:
                    # global integer figure numbering (e.g. Kreyszig "Fig. 2");
                    # no chapter prefix, so compare on the bare number directly.
                    caption.add(normfig(num))
                else:
                    parts = num.split('.')
                    if len(parts) >= 2 and int(parts[0]) == ch:
                        caption.add(normfig(num))
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
        misattributed = check_figure_attribution(ctx.md_file)
        return LayerResult(code=self.code, legacy=res, metadata={
            'fig_missing': res['missing'],
            'fig_extra': res['extra'],
            'fig_invalid': res['invalid'],
            'fig_invalid_warn': res['invalid_warn'],
            'fig_misattributed': misattributed,
            'fig_skipped': fig_skipped,
        })
