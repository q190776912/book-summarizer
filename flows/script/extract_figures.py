"""Detect figures from a PDF using PDF-Extract-Kit's DocLayout-YOLO layout model.

This is the **detection phase** of the skill's two-phase figure pipeline.

  Phase 1 (this module) — DETECTION (invoked by the `figure_detection` sub-flow,
    AFTER book config / verify_config.json has been generated, so it reads the
    book's own figure-label convention):
    DocLayout-YOLO's layout detection boxes text + image + formula in one pass.
    For every `figure` (class 3) box on every page we crop the region at the
    SAME 200-DPI used by the MFD+OCR pipeline and save it with a *positional /
    random* name ``det_p{PAGE:03d}_{IDX:02d}.png`` — **NO** semantic "图 X.X.X"
    name yet. We also record the box position (bbox), the chapter (via
    chapter_map.json), the detection confidence, and the caption OCR text
    (``cap_text``) recovered from the matching ``figure_caption`` (class 4)
    box. Everything is written to ``figure_detect.json``.

  Phase 2 (assign_figures.py) — ASSIGNMENT (runs at chapter-summary time):
    Reads ``figure_detect.json`` + the chapter's OCR page JSONs, recovers each
    figure's "图 X.X.X" label from (a) its caption text or (b) the nearest
    "图 X.X.X" caption by position, renames the crop to
    ``chNN_figX.X.X.png`` (matched) or ``chNN_unnamed_K.png`` (unmatched), and
    writes the assigned ``figure_index.json`` that ``verify_chapter.py`` (figure
    layer E, unified) consumes.

Keeping the two phases separate means detection is a dumb "save everything +
position" pass, and the semantic naming is deferred until we know the chapter
context — exactly the workflow described for this skill.

Two entry points:
  * run_full_book(pdf, out_dir, ...) -> detect on ALL pages (1..N), assign each
        to a chapter via chapter_map.json (pages outside any range -> ch 0),
        write a single global ``figure_detect.json``. Called by the
        ``figure_detection`` sub-flow (after config).
  * run_chapter(pdf, out_dir, ch, start, end, ...) -> re-detect a single
        chapter's pages (merges into the existing global figure_detect.json;
        removes that chapter's old det crops first). For targeted re-runs.

CLI:
    python extract_figures.py <pdf> --out DIR --book
    python extract_figures.py <pdf> --out DIR --ch N --start S --end E
"""
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
import figure_detect
from figure_detect import FigureDetect
from page_json import PageJson
from lib.figure_io import load_fig_labels, build_fig_label_re, FIGURE_LABELS_DEFAULT


import os, sys

from deskew import (
    render_page as _deskew_render_page,
    DEFAULT_MAX_ANGLE as DESKEW_MAX_ANGLE,
    DEFAULT_THRESHOLD as DESKEW_THRESHOLD,
)

import os
import re
import sys
import glob
import json
import argparse

import numpy as np
import fitz
from PIL import Image
import cv2
import torch
import torch.nn as nn
import torch.nn.functional as F


def _safe_dilated_conv(self, x, dilation):
    """Drop-in replacement for doclayout_yolo's DilatedBlock.dilated_conv.

    The stock code does `bn = self.dcv.bn` and breaks on ultralytics>=8.3,
    which deletes the `bn` attribute during the auto-fuse that happens on
    `predict()`. This version tolerates a fused (bn folded into conv, `bn`
    set to Identity or deleted) or un-fused Conv.
    """
    conv = self.dcv.conv
    weight = conv.weight
    bias = conv.bias
    padding = dilation * (self.k // 2)
    out = F.conv2d(x, weight, bias, stride=1, padding=padding, dilation=dilation)
    bn = getattr(self.dcv, "bn", None)
    if bn is not None and not isinstance(bn, nn.Identity):
        out = bn(out)
    act = getattr(self.dcv, "act", None)
    if act is not None and not isinstance(act, nn.Identity):
        out = act(out)
    return out


# Monkeypatch the version-drift bug (doclayout_yolo 0.0.4 vs ultralytics 8.4.x).
try:
    from doclayout_yolo.nn.modules.g2l_crm import DilatedBlock
    DilatedBlock.dilated_conv = _safe_dilated_conv
except Exception:
    pass


# Default weights path (DocLayout-YOLO, from PDF-Extract-Kit 1.0 ModelScope repo).
DEFAULT_WEIGHTS = r"D:\study\model\PDF-Extract-Kit\models\Layout\YOLO\doclayout_yolo_ft.pt"


def render_page(doc, pno, dpi, deskew_mode="auto",
                max_angle=DESKEW_MAX_ANGLE, threshold=DESKEW_THRESHOLD):
    """Render pdf page `pno` (0-based) at `dpi`; return (BGR ndarray, (W,H)).

    Delegates to the shared ``deskew.render_page`` so that figure
    bounding boxes live in the SAME coordinate space as the text/formula
    boxes produced by ``extract_book.py`` (both must use the identical
    deskew render, otherwise caption matching and the figure layer (E) breaks).
    """
    img_bgr, (W, H), _ = _deskew_render_page(
        doc, pno, dpi, mode=deskew_mode, max_angle=max_angle, threshold=threshold)
    return img_bgr, (W, H)


def load_ocr_text(json_path):
    """Load page_NNN.json text items (each has 'poly' + 'text'). Return list."""
    if not json_path or not os.path.exists(json_path):
        return []
    try:
        data = figure_detect.FigureDetect.load(json_path).data
    except Exception:
        return []
    return data.get("text", []) or []


def center_of_poly(poly):
    # poly is a flat list of 8 floats: [x0,y0, x1,y1, x2,y2, x3,y3] (4 points)
    xs = poly[0::2]
    ys = poly[1::2]
    return (sum(xs) / len(xs), sum(ys) / len(ys))


def caption_text_for_bbox(ocr_items, bbox):
    """Reconstruct the caption string for a caption bbox from OCR text items
    whose center falls inside the bbox (coordinate spaces must match)."""
    if not bbox:
        return None
    x0, y0, x1, y1 = bbox
    parts = []
    for it in ocr_items:
        poly = it.get("poly")
        if not poly:
            continue
        cx, cy = center_of_poly(poly)
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            parts.append((cy, it.get("text", "")))
    parts.sort(key=lambda t: t[0])
    return "".join(t for _, t in parts)


# Figure-label prefixes are BOOK-SPECIFIC — each book declares its OWN
# convention in verify_config.json `figure.labels` (see config/config_schema.md).
# The detection reads it through lib.figure_io.load_fig_labels / build_fig_label_re
# so it honors the book's actual Figure / 图 / Fig. numbering, NOT a hardcoded list.


def parse_fig_label(text, labels=None):
    """Extract the sequential number after a figure-label prefix in `text`.

    The prefix list is BOOK-SPECIFIC (verify_config.json `figure.labels`); when
    `labels` is None the default prefix set is used. Returns the number string
    (e.g. "5.1") or None.

    A label is recognized only when it precedes a *sequential* number of 2–3
    components (e.g. "5.1" or "5.1.2"); a bare "3" is NOT a figure label, which
    keeps body text like "equation 3" from being mistaken for a caption.
    """
    if not text:
        return None
    if labels is None:
        labels = FIGURE_LABELS_DEFAULT
    m = build_fig_label_re(labels).search(text)
    return m.group(1) if m else None


def load_chapter_map(out_dir):
    """Load chapter_map.json (int chapter -> {start,end,...}) if present.
    Supports two formats:
      1. Flat dict: {"1": {"start": 1, "end": 30, ...}, "2": ...}
      2. Nested list: {"chapters": [{"num": 1, "start": 17, "end": 72, ...}, ...]}
    """
    p = os.path.join(out_dir, "chapter_map.json")
    if os.path.exists(p):
        try:
            raw = PageJson.load(p).data
            chapters = raw.get("chapters")
            if chapters is not None:
                # accept both "start"/"end" and "start_page"/"end_page" keys
                def _se(ch):
                    return (ch.get("start") or ch.get("start_page"),
                            ch.get("end") or ch.get("end_page"))
                return {ch["num"]: {"start": _se(ch)[0], "end": _se(ch)[1]}
                        for ch in chapters}
            return {int(k): v for k, v in raw.items()}
        except Exception:
            return None
    return None


def chapter_for_page(pno, chap_map):
    """Return chapter number (1-based) for a 1-based page, or 0 if outside all ranges."""
    if not chap_map:
        return 0
    for ch, info in chap_map.items():
        s = info.get("start")
        e = info.get("end")
        if s and e and s <= pno <= e:
            return int(ch)
    return 0


def load_layout_model(weights, device):
    """Load DocLayout-YOLO. Prefer doclayout_yolo.YOLOv10 (handles dict output);
    fall back to ultralytics.YOLO if unavailable."""
    model = None
    loader = None
    try:
        from doclayout_yolo import YOLOv10
        model = YOLOv10(weights)
        loader = "doclayout_yolo.YOLOv10"
    except Exception as e:
        from ultralytics import YOLO
        model = YOLO(weights)
        loader = f"ultralytics.YOLO(fallback:{e})"
    assert model is not None, "failed to load layout model"
    return model, loader


def detect_on_page(model, arr, W, H, conf, imgsz, device, fig_id, cap_id):
    """Return (figs, caps) lists; each item [x0,y0,x1,y1,conf] in 200-DPI px."""
    res = model.predict(arr, imgsz=imgsz, conf=conf, device=device, verbose=False)[0]
    boxes = res.boxes
    figs, caps = [], []
    for i in range(len(boxes)):
        cls = int(boxes.cls[i])
        c = float(boxes.conf[i])
        x0, y0, x1, y1 = [int(v) for v in boxes.xyxy[i].tolist()]
        x0, y0 = max(0, x0), max(0, y0)
        x1, y1 = min(W, x1), min(H, y1)
        if cls == fig_id:
            figs.append([x0, y0, x1, y1, c])
        elif cls == cap_id:
            caps.append([x0, y0, x1, y1, c])
    return figs, caps


def process_page(model, arr, W, H, ocr_items, fig_id, cap_id, ch, pno,
                 fig_dir, conf, imgsz, device, fig_labels=None):
    """Detect + crop figures on one page (DETECTION ONLY: positional names, no
    semantic label yet). Returns (entries, md_lines).

    Caption handling: a figure whose paired caption carries a sequential label
    (图 X.X / Fig X.X, see parse_fig_label) is cropped TOGETHER with its caption
    (label + following description text) as one image. A figure whose caption
    has no sequential label — or has no caption at all — is cropped alone.
    """
    figs, caps = detect_on_page(model, arr, W, H, conf, imgsz, device, fig_id, cap_id)
    entries, md_lines = [], []
    fi = 0
    for (x0, y0, x1, y1, confg) in figs:
        fi += 1
        # pair with nearest caption (by center distance, vertical-weighted) so
        # the captions text can be matched at assignment time
        cap_txt = None
        best = None
        best_d = 1e18
        cx = (x0 + x1) / 2
        cy = (y0 + y1) / 2
        for c in caps:
            ccx = (c[0] + c[2]) / 2
            ccy = (c[1] + c[3]) / 2
            d = abs(ccy - cy) + 0.5 * abs(ccx - cx)
            if d < best_d:
                best_d, best = d, c
        cap_txt = caption_text_for_bbox(ocr_items, best[:4]) if best else None

        # Does the paired caption carry a sequential label (图 X.X / Fig X.X)?
        # If yes, crop the figure + its caption (label + description) as ONE
        # image; otherwise crop the figure alone. This is the required
        # "include caption iff it has a label" logic.
        has_label = bool(cap_txt) and parse_fig_label(cap_txt, fig_labels) is not None

        # Crop region: figure box by default; extend to include the caption
        # (union of figure + caption boxes) only when a labeled caption exists.
        cx0, cy0, cx1, cy1 = x0, y0, x1, y1
        if best is not None and has_label:
            cx0 = min(x0, best[0]); cy0 = min(y0, best[1])
            cx1 = max(x1, best[2]); cy1 = max(y1, best[3])

        crop = arr[cy0:cy1, cx0:cx1]
        if crop.size == 0:
            continue
        # positional / random name — NO 图X.X.X yet (assignment phase does that)
        fname = f"det_p{pno:03d}_{fi:02d}.png"
        # NOTE: cv2.imwrite fails SILENTLY on Windows paths that contain
        # non-ASCII (e.g. Chinese) characters, which silently breaks this
        # pipeline for non-English book folders. Save via PIL instead.
        try:
            from PIL import Image as _PILImage
            _PILImage.fromarray(crop[:, :, ::-1]).save(os.path.join(fig_dir, fname))
        except Exception:
            cv2.imwrite(os.path.join(fig_dir, fname), crop)
        entries.append({
            "chapter": ch,
            "page": pno,
            "det_id": f"p{pno}_{fi}",
            "fig_idx": fi,
            "label": None,                 # filled by assign_figures.py
            "bbox": [cx0, cy0, cx1, cy1],  # figure box, or figure+caption if labeled
            "conf": round(confg, 3),
            "file": f"figure/{fname}",
            "cap_text": cap_txt,          # raw caption OCR, used at assignment
            "source": "detect",
        })
        md_lines.append(f"- 图(检测, p{pno}, 未命名)：![fig](figure/{fname})")
    return entries, md_lines


def _write_detect(out_dir, entries, md_lines):
    figure_detect.FigureDetect(data=entries).dump(os.path.join(out_dir, "figure_detect.json"))
    with open(os.path.join(out_dir, "figure_detect.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines) + "\n")


def detected_pages_set(out_dir):
    """Return a set of 1-based page numbers that have been detected in figure_detect.json."""
    dp = os.path.join(out_dir, "figure_detect.json")
    if not os.path.exists(dp):
        return set()
    try:
        entries = figure_detect.FigureDetect.load(dp).data
        return {e["page"] for e in entries}
    except Exception:
        return set()


def detect_pages_range(pdf_path, out_dir, start, end, model=None,
                       weights=DEFAULT_WEIGHTS, dpi=200, conf=0.25,
                       imgsz=1280, device="0", chap_map=None, deskew="auto"):
    """Incremental detection on pages start..end (1-based), appending to
    existing figure_detect.json.

    Unlike run_full_book() which overwrites, this function is designed for
    per-batch incremental use.  It loads the layout model if not provided,
    renders each page, detects figures, assigns chapters via chapter_map,
    and merges new entries into figure_detect.json without disturbing
    previously detected pages.

    Returns (model, new_entries) — pass model back on subsequent calls to
    keep the model resident in VRAM across batches.
    """
    fig_dir = os.path.join(out_dir, "figure")
    os.makedirs(fig_dir, exist_ok=True)

    if model is None:
        model, _ = load_layout_model(weights, device)

    names = model.names
    fig_id = next((k for k, v in names.items() if str(v).lower() == "figure"), 3)
    cap_id = next((k for k, v in names.items() if str(v).lower() == "figure_caption"), 4)

    if chap_map is None:
        chap_map = load_chapter_map(out_dir)
    fig_labels = load_fig_labels(out_dir)

    doc = fitz.open(pdf_path)
    new_entries = []
    for pno in range(start, end + 1):
        arr, (W, H) = render_page(doc, pno - 1, dpi, deskew_mode=deskew)
        json_path = os.path.join(out_dir, f"page_{pno:03d}.json")
        ocr_items = load_ocr_text(json_path)
        ch = chapter_for_page(pno, chap_map)
        e, _ = process_page(model, arr, W, H, ocr_items, fig_id, cap_id,
                            ch, pno, fig_dir, conf, imgsz, device, fig_labels)
        new_entries += e
    doc.close()

    # Merge: append new entries to existing figure_detect.json
    dp = os.path.join(out_dir, "figure_detect.json")
    existing = []
    if os.path.exists(dp):
        try:
            existing = figure_detect.FigureDetect.load(dp).data
        except Exception:
            existing = []
    merged = existing + new_entries
    figure_detect.FigureDetect(data=merged).dump(dp)

    return model, new_entries


def run_full_book(pdf_path, out_dir, weights=DEFAULT_WEIGHTS,
                  dpi=200, conf=0.25, imgsz=1280, device="0", deskew="auto"):
    """Detection phase: detect figures on every page (1..N), assign chapter via
    chapter_map.json (pages outside any range -> ch 0), write one global
    figure_detect.json. Detection crops get positional names det_pNNN_KK.png;
    NO semantic 图X.X.X name is assigned here (that is assign_figures.py)."""
    fig_dir = os.path.join(out_dir, "figure")
    os.makedirs(fig_dir, exist_ok=True)
    # remove previous DETECTION artefacts (keep any chNN_* assigned/manual crops)
    for old in glob.glob(os.path.join(fig_dir, "det_*.png")):
        try:
            os.remove(old)
        except OSError:
            pass
    dp = os.path.join(out_dir, "figure_detect.json")
    if os.path.exists(dp):
        try:
            os.remove(dp)
        except OSError:
            pass

    model, loader = load_layout_model(weights, device)
    names = model.names
    fig_id = next((k for k, v in names.items() if str(v).lower() == "figure"), 3)
    cap_id = next((k for k, v in names.items() if str(v).lower() == "figure_caption"), 4)
    print(f"[info] loader={loader}; figure class id={fig_id}, figure_caption id={cap_id}; names={names}")

    chap_map = load_chapter_map(out_dir)
    fig_labels = load_fig_labels(out_dir)
    doc = fitz.open(pdf_path)
    total = doc.page_count
    all_entries, all_md = [], []
    for pno in range(1, total + 1):
        arr, (W, H) = render_page(doc, pno - 1, dpi, deskew_mode=deskew)
        json_path = os.path.join(out_dir, f"page_{pno:03d}.json")
        ocr_items = load_ocr_text(json_path)
        ch = chapter_for_page(pno, chap_map)
        e, md = process_page(model, arr, W, H, ocr_items, fig_id, cap_id,
                             ch, pno, fig_dir, conf, imgsz, device, fig_labels)
        all_entries += e
        all_md += md
        if pno % 20 == 0 or pno == total:
            print(f"  figure detect pages {pno}/{total}: {len(all_entries)} crops so far")
    doc.close()
    _write_detect(out_dir, all_entries, all_md)
    print(f"[done] saved {len(all_entries)} detection crops to {fig_dir} (positional names)")
    print(f"[done] detection store -> {os.path.join(out_dir, 'figure_detect.json')}")
    print(f"[next] run assign_figures.py to name figures (图X.X.X) at summary time")
    return all_entries


def run_chapter(pdf_path, out_dir, ch, start, end, weights=DEFAULT_WEIGHTS,
                dpi=200, conf=0.25, imgsz=1280, device="0", deskew="auto"):
    """Re-detect a single chapter's pages; merge into the existing global
    figure_detect.json and remove this chapter's previously-saved det crops
    (by page range) first."""
    fig_dir = os.path.join(out_dir, "figure")
    os.makedirs(fig_dir, exist_ok=True)
    # remove this chapter's old det crops (named det_p{PAGE}_{IDX}.png)
    for old in glob.glob(os.path.join(fig_dir, "det_*.png")):
        try:
            base = os.path.basename(old)
            # det_p{page}_{idx}.png -> page = int after 'det_p'
            pg = int(base[len("det_p"):].split("_")[0])
            if start <= pg <= end:
                os.remove(old)
        except (ValueError, IndexError):
            pass

    model, loader = load_layout_model(weights, device)
    names = model.names
    fig_id = next((k for k, v in names.items() if str(v).lower() == "figure"), 3)
    cap_id = next((k for k, v in names.items() if str(v).lower() == "figure_caption"), 4)
    print(f"[info] loader={loader}; chapter={ch} pages {start}..{end}")
    fig_labels = load_fig_labels(out_dir)

    doc = fitz.open(pdf_path)
    entries, md = [], []
    for pno in range(start, end + 1):
        arr, (W, H) = render_page(doc, pno - 1, dpi, deskew_mode=deskew)
        json_path = os.path.join(out_dir, f"page_{pno:03d}.json")
        ocr_items = load_ocr_text(json_path)
        e, m = process_page(model, arr, W, H, ocr_items, fig_id, cap_id,
                            ch, pno, fig_dir, conf, imgsz, device, fig_labels)
        entries += e
        md += m
    doc.close()

    # merge: drop existing det entries for this chapter, append new
    dp = os.path.join(out_dir, "figure_detect.json")
    existing = []
    if os.path.exists(dp):
        try:
            existing = figure_detect.FigureDetect.load(dp).data
        except Exception:
            existing = []
    existing = [e for e in existing if e.get("chapter") != ch]
    merged = existing + entries
    _write_detect(out_dir, merged, [])  # md_lines only meaningful for full-book
    print(f"[done] chapter {ch}: {len(entries)} detection crops; detection store now {len(merged)} entries")
    return entries


def _find_pdf(out_dir):
    """Auto-discover PDF from _extract parent directory."""
    parent = os.path.dirname(os.path.abspath(out_dir))
    for f in sorted(os.listdir(parent)):
        if f.lower().endswith(".pdf"):
            return os.path.join(parent, f)
    return None


def main():
    ap = argparse.ArgumentParser(description="Figure DETECTION (DocLayout-YOLO) — positional names, no 图X.X.X yet")
    ap.add_argument("pdf_path", nargs="?",
                    help="path to PDF (optional if --out given; auto-discovered from _extract parent)")
    ap.add_argument("--out", required=True, help="chapter extract dir (contains page_NNN.json)")
    ap.add_argument("--book", action="store_true",
                    help="full-book mode: detect figures on ALL pages, chapter via chapter_map.json")
    ap.add_argument("--ch", type=int, help="chapter number (single-chapter mode)")
    ap.add_argument("--start", type=int, help="1-based json page number (start, inclusive)")
    ap.add_argument("--end", type=int, help="1-based json page number (end, inclusive)")
    ap.add_argument("--dpi", type=int, default=200)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--imgsz", type=int, default=1280)
    ap.add_argument("--device", default="0")
    ap.add_argument("--weights", default=DEFAULT_WEIGHTS)
    args = ap.parse_args()

    pdf_path = args.pdf_path
    if not pdf_path:
        pdf_path = _find_pdf(args.out)
        if not pdf_path:
            print("ERROR: no pdf_path argument and could not auto-discover PDF in parent of --out")
            sys.exit(2)
        print(f"[auto] discovered PDF: {pdf_path}")

    if args.book:
        run_full_book(pdf_path, args.out, args.weights, args.dpi,
                      args.conf, args.imgsz, args.device)
    else:
        if not (args.ch and args.start and args.end):
            print("ERROR: provide --book, OR --ch/--start/--end (single chapter)")
            sys.exit(2)
        run_chapter(pdf_path, args.out, args.ch, args.start, args.end,
                    args.weights, args.dpi, args.conf, args.imgsz, args.device)


if __name__ == "__main__":
    main()
