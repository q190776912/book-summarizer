"""Apply manually-specified figure crops declared in figure_manual_chN.json.

Use this when DocLayout-YOLO misses a figure (e.g. a rotated, text-dense
diagram it mis-classifies as `plain text`). The model is not perfect; the
E-layer (figure completeness) in verify_chapter.py will report the missing
caption labels. To recover them:

  1. Render the offending page(s) and visually identify the figure region.
     A quick way: save a 200-DPI render of the page as PNG, view it, and
     read the bbox in rendered-image coordinates. The 110-DPI render under
     <corpus_root>/_tmp_pg/pNNN.png (if you made one) scales by 200/110.
  2. Edit (or create) `_extract/figure_manual_chN.json`:
         {
           "1.3.1": {
             "page": 27,
             "bbox": [x0, y0, x1, y1],   # 200-DPI rendered image, BEFORE rotation
             "rotate": 90,                # 0 / 90 / 180 / 270 (CW degrees)
             "caption": "图 1.3.1 (optional)"
           }
         }
  3. Run this script:
         python apply_manual_figures.py <extract_dir> <ch> --pdf <pdf_path>
     It renders the page at the same DPI as the auto pipeline, crops the
     bbox, rotates if requested, saves to _extract/figure/ch{NN}_fig{LABEL}.png,
     and appends (or updates) the entry in figure_index.json with
     source="manual". The E-layer will then see the label as "provided".

  cv2.imwrite on Windows cannot write to paths containing non-ASCII
  characters (returns False silently); this script writes to an ASCII
  temp file first and then moves the result.

Usage:
    python apply_manual_figures.py <extract_dir> <ch> --pdf <pdf_path>
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


import os, sys

import os
import sys
import json
import argparse
import shutil
import tempfile

import numpy as np
import fitz
import cv2


def load_manual(ext, ch):
    p = os.path.join(ext, f"figure_manual_ch{ch}.json")
    if not os.path.exists(p):
        return {}
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


def render_page_bgr(pdf, pno, dpi):
    doc = fitz.open(pdf)
    page = doc[pno - 1]
    pix = page.get_pixmap(dpi=dpi)
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n)[:, :, :3][:, :, ::-1].copy()
    doc.close()
    return arr, pix.width, pix.height


def safe_imwrite(path, img):
    """cv2.imwrite wrapper that handles non-ASCII paths on Windows."""
    fd, tmp = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    ok = cv2.imwrite(tmp, img)
    if not ok:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False
    shutil.move(tmp, path)
    return True


def apply_one(ext, ch, pdf, label, spec, dpi=200, fig_dir=None, idx=None):
    """Crop, rotate, save one manual figure; return (entry, ok)."""
    if fig_dir is None:
        fig_dir = os.path.join(ext, "figure")
    os.makedirs(fig_dir, exist_ok=True)

    pno = int(spec.get("page", 0))
    bbox = spec.get("bbox")
    rotate = int(spec.get("rotate", 0))
    if not pno or not bbox or len(bbox) != 4:
        return None, False

    arr, W, H = render_page_bgr(pdf, pno, dpi)
    x0, y0, x1, y1 = bbox
    x0 = max(0, x0); y0 = max(0, y0)
    x1 = min(W, x1); y1 = min(H, y1)
    if x1 - x0 < 4 or y1 - y0 < 4:
        return None, False
    crop = arr[y0:y1, x0:x1]
    if rotate:
        if rotate == 90:
            crop = cv2.rotate(crop, cv2.ROTATE_90_CLOCKWISE)
        elif rotate == 180:
            crop = cv2.rotate(crop, cv2.ROTATE_180)
        elif rotate == 270:
            crop = cv2.rotate(crop, cv2.ROTATE_90_COUNTERCLOCKWISE)

    fname = f"ch{ch:02d}_fig{label}.png"
    out_path = os.path.join(fig_dir, fname)
    ok = safe_imwrite(out_path, crop)
    if not ok:
        return None, False

    entry = {
        "chapter": ch,
        "page": pno,
        "fig_idx": 0,  # manual; 0 indicates "not part of the auto per-page sequence"
        "label": label,
        "bbox": [x0, y0, x1, y1],
        "conf": 1.0,
        "file": f"figure/{fname}",
        "caption": spec.get("caption"),
        "source": "manual",
    }
    if idx is not None:
        # remove any prior entry with the same (chapter, label) and append the new one
        idx[:] = [e for e in idx if not (e.get("chapter") == ch and e.get("label") == label)]
        idx.append(entry)
    return entry, True


def main():
    ap = argparse.ArgumentParser(description="Apply manual figure overrides")
    ap.add_argument("ext_dir", help="path to _extract")
    ap.add_argument("ch", type=int, help="chapter number")
    ap.add_argument("--pdf", required=True, help="path to source PDF")
    ap.add_argument("--dpi", type=int, default=200)
    args = ap.parse_args()

    ext = args.ext_dir
    manual = load_manual(ext, args.ch)
    if not manual:
        print(f"no figure_manual_ch{args.ch}.json (or empty)")
        return

    idx_path = os.path.join(ext, "figure_index.json")
    idx = []
    if os.path.exists(idx_path):
        try:
            idx = json.load(open(idx_path, encoding="utf-8"))
        except Exception:
            idx = []

    fig_dir = os.path.join(ext, "figure")
    n_ok = 0
    for label, spec in manual.items():
        entry, ok = apply_one(ext, args.ch, args.pdf, label, spec,
                              dpi=args.dpi, fig_dir=fig_dir, idx=idx)
        if ok:
            n_ok += 1
            print(f"  ok  {label} -> {entry['file']} (p{entry['page']} bbox={entry['bbox']})")
        else:
            print(f"  FAIL {label} (page={spec.get('page')} bbox={spec.get('bbox')})")

    with open(idx_path, "w", encoding="utf-8") as f:
        json.dump(idx, f, ensure_ascii=False, indent=2)
    print(f"applied {n_ok}/{len(manual)} manual figures; figure_index.json updated ({len(idx)} total entries)")


if __name__ == "__main__":
    main()
