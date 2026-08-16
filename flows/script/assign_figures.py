"""Assign figure numbers (图 X.X.X) to detected figures — the SUMMARY phase.

This is **phase 2** of the skill's two-phase figure pipeline. It reads the raw
detection store ``figure_detect.json`` (produced by ``extract_figures.py``) plus
the chapter's OCR page JSONs, and for every detected figure recovers its
semantic label:

  (a) from its caption OCR text (``cap_text``) if it contains "图 X.X.X" /
      "Figure X.X";
  (b) otherwise from the nearest "图 X.X.X" caption in the chapter's OCR by
      reading order / position (same page, vertical proximity) — this is the
      "根据位置信息 + json 信息判断这张图属于哪张图" step.

Detected crops (named ``det_p{PAGE}_{IDX}.png`` by detection) are then renamed
to ``chNN_figX.X.X.png`` (matched) or ``chNN_unnamed_K.png`` (unmatched, still
embedded at summary as "图(未标号)"), and the assigned ``figure_index.json`` is
written — the file ``verify_chapter.py`` (figure layer E, unified) consumes.

figure-layer (E, unified) semantics after assignment:
  * a 图X.X.X referenced in OCR with NO nearby detected figure => E-layer (fig_missing)
    MISSING (truly missed -> re-detect that page, or declare it in
    ``figure_manual_chN.json`` and run ``apply_manual_figures.py``).
  * a detected figure that could not be matched to any 图X.X.X => kept as
    ``chNN_unnamed_K.png`` (label=null). It is NOT a FAIL — it was found, just
    unnamed. Embed it as "图(未标号)".

Manual figures (``source=="manual"`` in figure_index.json, produced by
``apply_manual_figures.py``) are ALWAYS preserved across re-assignments.

Two modes:
    python assign_figures.py <pdf> --out DIR --book            # assign ALL chapters
    python assign_figures.py <pdf> --out DIR --ch N --start S --end E  # one chapter

(The PDF path is accepted for pipeline symmetry but not used — assignment only
reads existing crops + OCR JSONs, it does not render.)
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
import figure_index
import figure_detect
import chapter_map

import os
import sys
import glob
import json
import argparse

import numpy as np


# ----------------------------------------------------------------------------
# reuse detection helpers (kept in extract_figures.py)
# ----------------------------------------------------------------------------
from extract_figures import load_ocr_text, center_of_poly, parse_fig_label  # noqa: E402
from lib.figure_io import load_fig_labels, load_fig_components, load_fig_label_re  # noqa: E402


def load_figure_detect(out_dir):
    """Load the RAW detection store (figure_detect.json) — a list of detection
    entries produced by extract_figures.py, each carrying ``cap_text`` (the
    caption OCR) and ``bbox`` used by assign_chapter's labeling.

    NOTE: this is the *detection* store, NOT figure_index.json. Loading it via
    figure_index.FigureIndex would filter entries to Figure fields and DROP
    ``cap_text`` (Figure has ``caption``, not ``cap_text``), which would break
    the caption-based labeling path and force the weaker proximity fallback.
    Use the FigureDetect adapter (the store's real model) to preserve all keys.
    """
    p = os.path.join(out_dir, "figure_detect.json")
    if not os.path.exists(p):
        return None
    try:
        return list(figure_detect.FigureDetect.load(p).data)
    except Exception:
        return None


from lib.figure_io import load_figure_index
from figure_index import merge_index  # figure_index.json instantiation lives with its model


def gather_refs(out_dir, start, end):
    """Collect every figure caption (图X.X / Figure X.X / …) in the chapter's
    OCR pages, with its (page, cy) position. Returns list of (label, page, cy).

    Which caption PREFIX counts as a figure label is BOOK-SPECIFIC — read from
    verify_config.json `figure.labels` (see config/config_schema.md), NOT a
    hardcoded 图/figure/fig list — so a book that numbers figures "Fig." or in
    another language is honored.

    OCR often splits a caption like "图 6.1.1" across several text items, so we
    reconstruct each page's text in reading order (sorted by y) and regex-find
    the figure label on the joined string — this yields the full label
    (1/2/3 component per ``figure.components``) instead of a partial fragment,
    and we map the match back to its line's y."""
    pat = load_fig_label_re(out_dir)
    refs = []
    for pno in range(start, end + 1):
        ocr = load_ocr_text(os.path.join(out_dir, f"page_{pno:03d}.json"))
        items = []
        for it in ocr:
            t = it.get("text", "")
            if not t:
                continue
            y = center_of_poly(it["poly"])[1] if it.get("poly") else 0
            items.append((t, y))
        items.sort(key=lambda x: x[1])
        parts, ranges, pos = [], [], 0
        for t, y in items:
            a = pos
            parts.append(t)
            pos += len(t)
            ranges.append((a, pos, y))
            parts.append("\n")
            pos += 1
        full = "".join(parts)
        for m in pat.finditer(full):
            s = m.start()
            y = 0
            for (a, b, yy) in ranges:
                if a <= s < b:
                    y = yy
                    break
            refs.append((m.group(1), pno, y))
    return refs


def bbox_center(bbox):
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def assign_chapter(det_all, ch, start, end, out_dir):
    """Assign labels to one chapter's detected figures; rename crops; return
    the list of assigned entries (label-filled) for this chapter."""
    fig_dir = os.path.join(out_dir, "figure")
    os.makedirs(fig_dir, exist_ok=True)
    labels = load_fig_labels(out_dir)
    fig_components = load_fig_components(out_dir)

    ch_dets = [e for e in det_all if e.get("chapter") == ch]
    ch_dets.sort(key=lambda e: (e["page"], e.get("fig_idx", 0)))

    refs = gather_refs(out_dir, start, end)
    used_refs = set()  # indices into refs claimed by a figure

    # ---- cleanup: drop previous NON-manual chNN_* crops for this chapter ----
    existing_idx = load_figure_index(out_dir)
    protected = {e["file"] for e in existing_idx
                 if e.get("chapter") == ch and e.get("source") == "manual"}
    for f in glob.glob(os.path.join(fig_dir, f"ch{ch:02d}_*")):
        rel = "figure/" + os.path.basename(f)
        if rel not in protected:
            try:
                os.remove(f)
            except OSError:
                pass

    assigned, unnamed_k = [], 0
    for det in ch_dets:
        label = parse_fig_label(det.get("cap_text"), labels, fig_components) if det.get("cap_text") else None

        if not label:
            # proximity fallback: same page, nearest unused 图X.X.X by vertical gap
            fig_cx, fig_cy = bbox_center(det["bbox"])
            best, best_i, best_d = None, None, 1e18
            for i, (rlabel, rpage, rcy) in enumerate(refs):
                if i in used_refs or rpage != det["page"]:
                    continue
                d = abs(rcy - fig_cy)
                if d < best_d and d < 500:   # same-page window (~half page @200dpi)
                    best_d, best, best_i = d, rlabel, i
            if best is not None:
                label, used_refs_add = best, best_i
                used_refs.add(used_refs_add)

        if label:
            base = f"ch{ch:02d}_fig{label}.png"
        else:
            unnamed_k += 1
            base = f"ch{ch:02d}_unnamed_{unnamed_k:02d}.png"

        src = os.path.join(fig_dir, os.path.basename(det["file"]))
        dst = os.path.join(fig_dir, base)
        if os.path.exists(src):
            if os.path.exists(dst):
                # dst exists: if it is a manual figure, keep it and drop the
                # redundant detection crop; else it is a duplicate label -> suffix
                if "figure/" + base in protected:
                    try:
                        os.remove(src)
                    except OSError:
                        pass
                    continue
                # duplicate label from two detections -> _2 suffix
                k = 2
                while os.path.exists(os.path.join(fig_dir, f"ch{ch:02d}_fig{label}_{k}.png")):
                    k += 1
                base = f"ch{ch:02d}_fig{label}_{k}.png"
                dst = os.path.join(fig_dir, base)
            os.rename(src, dst)

        assigned.append({
            "chapter": ch,
            "page": det["page"],
            "fig_idx": det.get("fig_idx", 0),
            "label": label,
            "bbox": det["bbox"],
            "conf": det.get("conf"),
            "file": f"figure/{base}",
            "caption": det.get("cap_text"),
            "source": "detect",
        })

    # ---- dedupe by (chapter, label) ----
    # The layout detector frequently emits 2-3 overlapping "figure" boxes for a
    # single actual figure (figure + a nearby formula/diagram box, or a figure
    # split into sub-boxes). All of them pair with the SAME caption "Fig. 22",
    # so without dedupe we would emit phantom entries chNN_fig22.png /
    # chNN_fig22_2.png that the figure (E) layer counts as multiple figures and
    # marks as missing/extra. Keep the LARGEST-area detection (the complete
    # figure) and remove the spurious crops. A real book never has two distinct
    # figures sharing one number, so a label collision within a chapter is
    # always a duplicate detection, never two genuine figures.
    best = {}
    to_drop = []
    for e in assigned:
        lab = e.get("label")
        if not lab:
            continue
        b = e.get("bbox") or [0, 0, 0, 0]
        area = max(0, (b[2] - b[0]) * (b[3] - b[1]))
        if lab in best:
            prev_e, prev_area = best[lab]
            if area > prev_area:
                to_drop.append(prev_e)
                best[lab] = (e, area)
            else:
                to_drop.append(e)
        else:
            best[lab] = (e, area)
    for e in to_drop:
        _fp = os.path.join(fig_dir, os.path.basename(e["file"]))
        if os.path.exists(_fp):
            try:
                os.remove(_fp)
            except OSError:
                pass
    assigned = [e for e in assigned if e not in to_drop]
    return assigned


# `merge_index` is defined in `data/figure_index/figure_index.py` (one-JSON-one-directory
# rule) and imported above via `from figure_index import merge_index`.


def write_figure_index_md(out_dir):
    """Write figure_index.md from the current figure_index.json (all chapters)."""
    entries = load_figure_index(out_dir)
    md_lines = [f"- 图 {e['label']}：![图 {e['label']}]({e['file']})"
                for e in entries if e.get("label")]
    md_lines += [f"- 图(未标号, p{e['page']})：![fig]({e['file']})"
                 for e in entries if not e.get("label")]
    with open(os.path.join(out_dir, "figure_index.md"), "w", encoding='utf-8') as f:
        f.write("\n".join(md_lines) + "\n")


def run_book(pdf_path, out_dir):
    det = load_figure_detect(out_dir)
    if det is None:
        print("ERROR: figure_detect.json not found — run extract_figures.py --book first")
        sys.exit(2)
    chap_map = {}
    cm_path = os.path.join(out_dir, "chapter_map.json")
    if os.path.exists(cm_path):
        try:
            raw = chapter_map.load_chapter_map_raw(cm_path)
            chapters = raw.get("chapters")
            if chapters is not None:
                # accept both "start"/"end" and "start_page"/"end_page" keys
                def _se(ch):
                    return (ch.get("start") or ch.get("start_page"),
                            ch.get("end") or ch.get("end_page"))
                chap_map = {ch["num"]: {"start": _se(ch)[0], "end": _se(ch)[1]}
                            for ch in chapters}
            else:
                chap_map = {int(k): v for k, v in raw.items()}
        except Exception:
            chap_map = {}

    chapters = sorted({e["chapter"] for e in det})
    total_assigned = 0
    for ch in chapters:
        if ch in chap_map:
            start, end = chap_map[ch].get("start"), chap_map[ch].get("end")
        else:
            # chapter not in map (e.g. ch00 front matter): use detected page range
            pg = [e["page"] for e in det if e["chapter"] == ch]
            start, end = min(pg), max(pg)
        assigned = assign_chapter(det, ch, start, end, out_dir)
        merge_index(out_dir, ch, assigned)
        n_label = sum(1 for e in assigned if e.get("label"))
        print(f"  chapter {ch}: {len(assigned)} figures, {n_label} named, "
              f"{len(assigned) - n_label} unnamed")
        total_assigned += len(assigned)
    write_figure_index_md(out_dir)
    print(f"[done] assigned {total_assigned} figures -> figure_index.json")


def run_chapter(pdf_path, out_dir, ch, start, end):
    det = load_figure_detect(out_dir)
    if det is None:
        print("ERROR: figure_detect.json not found — run extract_figures.py --book first")
        sys.exit(2)
    assigned = assign_chapter(det, ch, start, end, out_dir)
    merge_index(out_dir, ch, assigned)
    write_figure_index_md(out_dir)
    n_label = sum(1 for e in assigned if e.get("label"))
    print(f"[done] chapter {ch}: {len(assigned)} figures, {n_label} named, "
          f"{len(assigned) - n_label} unnamed -> figure_index.json")


def main():
    ap = argparse.ArgumentParser(description="Assign 图X.X.X labels to detected figures (summary phase)")
    ap.add_argument("pdf_path", nargs="?",
                    help="source PDF (accepted for symmetry; auto-discovered from --out parent if omitted)")
    ap.add_argument("--out", required=True, help="chapter extract dir")
    ap.add_argument("--book", action="store_true", help="assign ALL chapters")
    ap.add_argument("--ch", type=int, help="chapter number (single-chapter mode)")
    ap.add_argument("--start", type=int, help="1-based start page")
    ap.add_argument("--end", type=int, help="1-based end page")
    args = ap.parse_args()

    pdf_path = args.pdf_path

    if args.book:
        run_book(pdf_path, args.out)
    else:
        if not (args.ch and args.start and args.end):
            print("ERROR: provide --book, OR --ch/--start/--end (single chapter)")
            sys.exit(2)
        run_chapter(pdf_path, args.out, args.ch, args.start, args.end)


if __name__ == "__main__":
    main()
