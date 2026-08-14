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

import re, sys, os, json
try:
    import cv2
except Exception:
    cv2 = None
from key_parse import sortkey
from lib.figure_io import load_figure_index, load_fig_labels, load_fig_label_re, build_fig_label_re, FIGURE_LABELS_DEFAULT


def fig_cap_re(out_dir=None):
    """Compiled regex that finds figure caption labels (图 X.X / Figure X.X / …)
    in OCR text. The prefix list is BOOK-SPECIFIC (verify_config.json
    `figure.labels`); `out_dir=None` uses the default prefix set. This makes the
    E-layer honor each book's OWN figure numbering instead of a hardcoded 图."""
    # Honor BOTH the book's figure.labels AND figure.components (1=global int,
    # 2=chapter.figure, 3=chapter.section.figure). out_dir=None -> default prefixes
    # with the historical 2-component default.
    if out_dir:
        return load_fig_label_re(out_dir)
    labels = list(FIGURE_LABELS_DEFAULT)
    return build_fig_label_re(labels)


# Backward-compatible module-level default (no book dir -> default prefixes).
FIG_CAP_RE = fig_cap_re()
def normfig(s):
    return str(s).strip().replace(' ', '')
