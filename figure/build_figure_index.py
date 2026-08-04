"""build_figure_index.py — book-agnostic helper to synthesize `_extract/figure_index.json`
and `_extract/figure_embed_overrides.json` from the detector output (`figure_detect.json`)
when the figure pipeline did NOT produce a figure_index.json.

Why needed:
- `figure_detect.json` carries a `chapter` field that is frequently MIS-assigned (it lags
  the real chapter). We re-derive the true chapter from the figure's `page` using
  `chapter_map.json` (the same page->chapter map the extractor uses).
- The detector `cap_text` is just "Figure X.Y" (a figure NUMBER, not a theorem/example
  number), so `embed_figures.py`'s automatic caption->item matching (`parse_ref`) finds
  nothing and would SKIP every figure. We therefore emit a manual override that anchors
  each figure to the SECTION (`## §N.M`) it sits in, derived by scanning the chapter OCR
  (`chN_ocr.txt`, which has `===== PAGE NN =====` markers + "N.M Title" headings) for the
  last section heading at or before the figure's page.

Usage:
    python build_figure_index.py <book_dir>
"""
import os, re, json, sys

ITEM_SEC_RE = re.compile(r'^\s*(\d{1,2})\.(\d{1,2})\b\s*[:.]?\s*[A-Za-z]')
PAGE_RE = re.compile(r'=====\s*PAGE\s*(\d+)\s*=====')


def chapter_of_page(page, chaps):
    for c in chaps:
        if c["start"] <= page <= c["end"]:
            return c["chapter"]
    return None


def section_map_for(ext, ch):
    ocr = os.path.join(ext, f"ch{ch}_ocr.txt")
    if not os.path.exists(ocr):
        return {}
    cur = None
    out = {}
    with open(ocr, encoding="utf-8") as f:
        page = None
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
    if not os.path.exists(det_path):
        print("No figure_detect.json — nothing to build.")
        return
    det = json.load(open(det_path, encoding="utf-8"))
    chaps = json.load(open(cmap_path, encoding="utf-8"))["chapters"]

    fig_index = []
    overrides = {}
    for e in det:
        page = e["page"]
        ch = chapter_of_page(page, chaps) or e.get("chapter")
        smap = section_map_for(ext, ch)
        sec = None
        cand = [p for p in smap if p <= page]
        if cand:
            sec = smap[max(cand)]
        if sec is None:
            sec = f"§{ch}.1"
        fname = e["file"].split("/")[-1]
        fig_index.append({
            "chapter": ch,
            "page": page,
            "file": e["file"],
            "caption": e.get("cap_text"),
            "bbox": e.get("bbox"),
            "dpi": 200,
        })
        overrides[fname] = {"anchors": [f"## {sec} "], "is_proof": False}

    json.dump(fig_index, open(os.path.join(ext, "figure_index.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(overrides, open(os.path.join(ext, "figure_embed_overrides.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"Wrote figure_index.json ({len(fig_index)} figures) + figure_embed_overrides.json")
    # quick report
    for e in fig_index:
        print(f"  p{e['page']:>3} ch{e['chapter']} {e['file'].split('/')[-1]:<22} -> {overrides[e['file'].split('/')[-1]]['anchors'][0]}")


if __name__ == "__main__":
    main()
