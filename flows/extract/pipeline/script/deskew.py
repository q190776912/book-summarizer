"""Page deskew (skew correction) for scanned PDF pages.

Both `extract_book.py` (MFD/MFR/OCR) and `flows/script/extract_figures.py`
(DocLayout-YOLO figure detection) render the PDF page independently,
so they MUST share the SAME render+deskew routine.  Otherwise the
text/formula boxes (`poly` / `bbox`) would live in the deskewed
coordinate space while the figure boxes stay in the raw space, and the
caption matching + E/F verification layers would break.

Algorithm
---------
The skew angle is estimated with the **Hough transform** on the page's
text lines: threshold to a binary ink mask, dilate horizontally so that
the characters of each text line fuse into one long stroke, run Canny +
HoughLinesP, keep the near-horizontal segments, and take their median
angle.  Hough is robust for dense text pages (including math books with
formulas: vertical strokes are filtered out, horizontal fraction bars
reinforce the correct angle) and returns ~0 deg for already-straight
(born-digital) pages, so it never "invents" a skew.  The rotation is
then applied to the full-resolution BGR image with an expanded white
canvas so every bounding box stays valid relative to the straightened
page.  Estimation runs on a downscaled copy (fast); rotation is on the
full-res image.

Modes
-----
  off   - pass-through, no deskew
  auto  - estimate; rotate ONLY when |angle| > threshold AND the page has
          enough text to trust.  Safe for born-digital PDFs (stay straight).
  force - always rotate by the estimated angle (even sub-threshold).

Constants
---------
  DEFAULT_MAX_ANGLE - never trust / apply an estimate beyond this (guards
                      against a catastrophic mis-estimate on a pathological
                      page, e.g. one dominated by a single large figure).
  DEFAULT_THRESHOLD - minimum |angle| (deg) worth applying in auto mode.
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

import cv2
import numpy as np

DEFAULT_MAX_ANGLE = 10.0
DEFAULT_THRESHOLD = 0.5


def estimate_skew_angle(gray, max_angle=DEFAULT_MAX_ANGLE, lo_width=1000,
                        min_density=0.02, min_lines=5):
    """Estimate the rotation (deg, CCW positive) that would straighten `gray`.

    Returns ``(angle_deg, info)``.  `angle_deg` is the amount to rotate the
    *image* by `-angle_deg` to undo the skew.  `info` carries `density`,
    `n_lines` and `angle` so the caller can decide whether to apply the
    correction.  Returns ``(0.0, info)`` when the page is too sparse (blank /
    figure-only) or no reliable horizontal lines are found.
    """
    h, w = gray.shape[:2]
    if w == 0 or h == 0:
        return 0.0, {"density": 0.0, "n_lines": 0, "angle": 0.0}
    scale = lo_width / float(w)
    small = cv2.resize(gray, (lo_width, max(1, int(h * scale))),
                       interpolation=cv2.INTER_AREA)
    # Otsu: foreground (text/ink) -> white (255), background -> black
    _, binr = cv2.threshold(small, 0, 255,
                            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    density = float(np.count_nonzero(binr)) / binr.size
    info = {"density": density, "n_lines": 0, "angle": 0.0}
    if density < min_density:
        return 0.0, info  # too little ink -> don't trust an angle

    # Fuse the characters of each text line into one long horizontal stroke
    ksz = max(3, int(lo_width / 25))
    kern = cv2.getStructuringElement(cv2.MORPH_RECT, (ksz, 1))
    dil = cv2.dilate(binr, kern, iterations=1)
    edges = cv2.Canny(dil, 50, 150)

    lines = cv2.HoughLinesP(edges, 1, np.pi / 180,
                             threshold=lo_width // 8,
                             minLineLength=lo_width // 6,
                             maxLineGap=lo_width // 12)
    if lines is None:
        return 0.0, info
    angs = []
    for x1, y1, x2, y2 in lines.reshape(-1, 4):
        dx = x2 - x1
        dy = y2 - y1
        if abs(dx) < 1e-6:
            continue
        a = np.degrees(np.arctan2(dy, dx))
        if -max_angle <= a <= max_angle:
            angs.append(a)
    if len(angs) < min_lines:
        return 0.0, info
    angle = float(np.median(angs))
    info["n_lines"] = len(angs)
    info["angle"] = angle
    return angle, info


def deskew_image(img_bgr, angle_deg, bg=255):
    """Rotate a BGR image by `-angle_deg` (CCW positive) with an expanded
    white canvas. Returns the straightened BGR image (or the original if the
    angle is negligible)."""
    if abs(angle_deg) < 1e-6:
        return img_bgr
    h, w = img_bgr.shape[:2]
    center = (w / 2.0, h / 2.0)
    M = cv2.getRotationMatrix2D(center, -angle_deg, 1.0)
    cos = abs(M[0, 0]); sin = abs(M[0, 1])
    new_w = int(h * sin + w * cos)
    new_h = int(h * cos + w * sin)
    M[0, 2] += (new_w - w) / 2.0
    M[1, 2] += (new_h - h) / 2.0
    return cv2.warpAffine(img_bgr, M, (new_w, new_h),
                          flags=cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT,
                          borderValue=bg)


def maybe_deskew(img_bgr, mode="auto", threshold=DEFAULT_THRESHOLD,
                 max_angle=DEFAULT_MAX_ANGLE):
    """Apply deskew per `mode`. Returns ``(img_bgr, angle_applied_deg)``."""
    if mode in (None, "off", ""):
        return img_bgr, 0.0
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    angle, info = estimate_skew_angle(gray, max_angle=max_angle)
    density = info.get("density", 0.0)
    n_lines = info.get("n_lines", 0)
    if mode == "force":
        apply = abs(angle) > 1e-3
    else:  # auto: apply only when the page is confidently skewed and has
           # enough text.  A straight page returns ~0 deg, so the threshold
           # alone keeps born-digital PDFs untouched; the density / line
           # guards protect against noisy / figure-only pages.
        apply = (abs(angle) > threshold) and density >= 0.02 and n_lines >= 5
    if apply:
        return deskew_image(img_bgr, angle), angle
    return img_bgr, 0.0


def render_page(doc, pno, dpi, mode="auto",
                max_angle=DEFAULT_MAX_ANGLE, threshold=DEFAULT_THRESHOLD):
    """Render PDF page `pno` (0-based) at `dpi` and optionally deskew it.

    Returns (img_bgr, (W, H), angle_applied_deg).  Used by both the
    text/formula pipeline and the figure detector so all boxes share one
    coordinate space.
    """
    import fitz
    page = doc[pno]
    pix = page.get_pixmap(matrix=fitz.Matrix(dpi / 72.0, dpi / 72.0))
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n)[:, :, :3]
    img_bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
    angle = 0.0
    if mode and mode != "off":
        img_bgr, angle = maybe_deskew(
            img_bgr, mode=mode, threshold=threshold, max_angle=max_angle)
    h, w = img_bgr.shape[:2]
    return img_bgr, (w, h), angle
