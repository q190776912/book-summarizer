"""build_precise_anchors.py — derive PRECISE per-figure embed anchors.

For each figure in figure_detect.json we use PyMuPDF to read the PDF text
blocks (in 200-DPI pixel space, top-left origin — the SAME space as the
detector's bbox), find the text block(s) immediately ABOVE the figure, and
pick the most-recent item header (Theorem / Lemma / Example / Definition /
Corollary / Proposition + "X.Y") that appears before the figure. That item
is the figure's "owner" and becomes the embed anchor (both EN and CN label
forms, so the bilingual .md pair both get the figure).

Falls back to the section header (## §N.M ) when no item header is found
(e.g. figures inside pure introductory prose).

Output: _extract/figure_embed_overrides.json  (figure_index.json is kept as-is)
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
from data.book_structure.book_structure import chapter_label
import chapter_map
from figure_detect import FigureDetect

import os, re, json, sys

from lib.util import chapter_of_page

try:
    import fitz
except Exception:
    print("PyMuPDF (fitz) unavailable — cannot derive precise anchors.")
    sys.exit(1)

from lib.regexlib import FIG_ITEM_SEC_RE as ITEM_SEC_RE, FIG_PAGE_RE as PAGE_RE
from figure_embed_overrides import write_figure_embed_overrides

EN2CN = {'Theorem': '定理', 'Lemma': '引理', 'Example': '例',
         'Definition': '定义', 'Corollary': '推论', 'Proposition': '命题'}
# header pattern in the book's text (English, since Apostol is English)
HEADER_RE = re.compile(
    r'(Theorem|Lemma|Example|Definition|Corollary|Proposition)\s+(\d{1,2})\.(\d{1,2})',
    re.IGNORECASE)


def section_map_for(ext, ch):
    ocr = os.path.join(ext, f"{chapter_label(ch)}_ocr.txt")
    if not os.path.exists(ocr):
        return {}
    cur = None
    out = {}
    page = None
    with open(ocr, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            m = PAGE_RE.match(line)
            if m:
                page = int(m.group(1))
                continue
            if page is None:
                continue
            sm = ITEM_SEC_RE.match(line)
            if sm:
                cur = f"§{int(sm.group(1))}.{int(sm.group(2))}"
            if cur is not None:
                out[page] = cur
    return out


def main():
    book_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    ext = os.path.join(book_dir, "_extract")
    det_path = os.path.join(ext, "figure_detect.json")
    cmap_path = os.path.join(ext, "chapter_map.json")
    det = FigureDetect.load(det_path).data
    _cm_raw = chapter_map.load_chapter_map_raw(cmap_path)
    chaps = _cm_raw["chapters"] if isinstance(_cm_raw, dict) and "chapters" in _cm_raw else [dict(v, chapter=int(k)) for k, v in _cm_raw.items()]

    pdfs = [f for f in os.listdir(book_dir) if f.lower().endswith('.pdf')]
    doc = fitz.open(os.path.join(book_dir, pdfs[0]))
    s = 200 / 72.0  # pt -> 200dpi px

    overrides = {}
    report = []
    for e in det:
        page = e["page"]
        bbox = e.get("bbox")
        ch = chapter_of_page(page, chaps) or e.get("chapter")
        base_name = e["file"].split("/")[-1]
        cap = e.get("cap_text")
        anchor = None
        if bbox:
            x0, y0, x1, y1 = bbox  # 200dpi px, top-left
            # Prefer SAME-PAGE blocks fully above the figure (y1 <= y0). The
            # most-recent item header among them is the figure's owner.
            cand_text = []
            try:
                cb = doc[page - 1].get_text("blocks")
                for b in cb:
                    bx = [b[0] * s, b[1] * s, b[2] * s, b[3] * s]
                    if bx[3] <= y0 + 5:  # bottom at/above figure top
                        cand_text.append(b[4])
            except Exception:
                pass
            merged = "\n".join(cand_text)
            matches = list(HEADER_RE.finditer(merged))
            if matches:
                m = matches[-1]
                kind_en = m.group(1).title()  # normalize cap
                num = f"{int(m.group(2))}.{int(m.group(3))}"
                kind_cn = EN2CN.get(kind_en, kind_en)
                anchor = {
                    "anchors": [f"**{kind_en} {num}.", f"**{kind_cn} {num}"],
                    "is_proof": False,
                }
                report.append(f"  p{page:>3} {base_name:<22} -> ITEM **{kind_en} {num}. / **{kind_cn} {num}  (cap={cap})")
            else:
                # fallback: section header
                smap = section_map_for(ext, ch)
                sec = None
                cand = [p for p in smap if p <= page]
                if cand:
                    sec = smap[max(cand)]
                if sec is None:
                    sec = f"§{ch}.1"
                anchor = {"anchors": [f"## {sec} "], "is_proof": False}
                report.append(f"  p{page:>3} {base_name:<22} -> SECTION {sec}  (cap={cap})")
        else:
            anchor = {"anchors": [f"## §{ch}.1 "], "is_proof": False}
            report.append(f"  p{page:>3} {base_name:<22} -> SECTION §{ch}.1 (no bbox)")
        overrides[base_name] = anchor

    write_figure_embed_overrides(overrides, os.path.join(ext, "figure_embed_overrides.json"))
    print(f"Wrote figure_embed_overrides.json ({len(overrides)} figures)")
    for r in report:
        print(r)


if __name__ == "__main__":
    main()
