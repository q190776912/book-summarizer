"""Background text-extraction pipeline driver — MFD->MFR->OCR with gap-aware resume.

Usage (launch detached from the skill dir):
    python extract_pipeline.py <pdf_path> [--start N] [--end N] [--force] [--deskew auto|off|force]

Extraction RANGE (--start / --end), both optional:
  - Neither given  -> extract the whole PDF (start=1, end=auto-detected total).
  - Only --end E   -> extract pages 1..E  (start defaults to 1).
  - Only --start S -> extract pages S..(auto total).
  - --start S --end E -> extract exactly pages S..E.
The upper bound (end) is auto-detected from the PDF via PyMuPDF when --end is omitted,
so there is never a need to pass a bare "total page count".

The _extract/ output directory is derived automatically as <pdf_parent>/_extract.

IMPORTANT — this driver produces ONLY text + formula ``page_*.json`` (the "raw
material"). Figure detection + assignment is a SEPARATE phase — the
``figure_detection`` sub-flow of `extract` (see flows/extract/figure_detection/
figure_detection.md) — which runs AFTER the book config (``verify_config.json``)
has been generated. This ordering guarantees detection reads the book's own
figure-label convention (``figure.labels``) instead of the default fallback.
Do NOT inline figure detection here.
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


import sys, os, json, time, glob, re, gc, argparse, traceback
from pathlib import Path
import torch

sys.stdout.reconfigure(encoding="utf-8")

from extract_book import init_models, process_batch

SKILL_DIR = Path(__file__).parent.absolute()
BATCH_SIZE = 50
MFR_BS = int(os.environ.get("PEK_MFR_BS", "32"))  # per-book override: PEK_MFR_BS=1
DPI = 200


def log(msg):
    ts = time.strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def existing_pages(extract_dir):
    """Set of page numbers for which page_<n>.json already exists."""
    nums = set()
    for f in glob.glob(os.path.join(extract_dir, "page_*.json")):
        m = re.search(r"page_(\d+)\.json$", f)
        if m:
            nums.add(int(m.group(1)))
    return nums


def find_first_gap(extract_dir, hi=None):
    """First page p>=1 that has no page_<p>.json.

    Counts up from 1 (the first *discontinuous* gap), NOT highest-existing + 1.
    E.g. with pages 1–10 and 15–20 present, returns 11 (not 21).
    If `hi` is given, once p>hi it returns hi+1 (meaning: nothing missing in 1..hi).
    """
    existing = existing_pages(extract_dir)
    p = 1
    while True:
        if p not in existing:
            return p
        p += 1
        if hi is not None and p > hi:
            return hi + 1


def missing_ranges(extract_dir, lo, hi):
    """Contiguous (s, e) page ranges within [lo, hi] that are NOT yet extracted."""
    existing = existing_pages(extract_dir)
    ranges = []
    s = None
    for p in range(lo, hi + 1):
        if p in existing:
            if s is not None:
                ranges.append((s, p - 1))
                s = None
        else:
            if s is None:
                s = p
    if s is not None:
        ranges.append((s, hi))
    return ranges


def main():
    ap = argparse.ArgumentParser(
        description="Background text-extraction pipeline (MFD+MFR+OCR, gap-aware resume)")
    ap.add_argument("pdf", help="path to source PDF, e.g. D:\\study\\book\\<书名>\\<书名>.pdf")
    ap.add_argument("--start", type=int, default=1,
                    help="first page to extract (1-based). Default 1.")
    ap.add_argument("--end", type=int, default=None,
                    help="last page to extract (inclusive). Omitted -> auto-detected "
                         "PDF total page count (recommended: omit it).")
    ap.add_argument("--force", action="store_true",
                    help="restart from page 1, ignoring existing pages")
    ap.add_argument("--deskew", default="auto", choices=["auto", "off", "force"],
                    help="skew correction for scanned pages (see extract_book.py --deskew)")
    args = ap.parse_args()

    global LOG_FILE
    PDF = args.pdf
    EXTRACT_DIR = str(Path(PDF).resolve().parent / "_extract")
    LOG_FILE = Path(EXTRACT_DIR) / "extract_pipeline.log"
    Path(EXTRACT_DIR).mkdir(parents=True, exist_ok=True)

    # Upper bound (end) defaults to the PDF's auto-detected total page count.
    import fitz as _fitz
    with _fitz.open(PDF) as _doc:
        PDF_TOTAL = _doc.page_count
    if args.end is None:
        END = PDF_TOTAL
        log(f"--end omitted: using auto-detected PDF total={END} as end")
    else:
        END = min(args.end, PDF_TOTAL)
        if args.end > PDF_TOTAL:
            log(f"--end={args.end} exceeds PDF total {PDF_TOTAL}; clamped to {END}")
        else:
            log(f"Using --end={END}")

    START_ARG = args.start
    if START_ARG < 1:
        START_ARG = 1
        log("--start < 1 clamped to 1")

    if args.force:
        # Re-extract the whole requested span from the requested start,
        # overwriting any existing pages.
        resume_from = 1
        ACTUAL_START = max(START_ARG, 1)
        missing = [(ACTUAL_START, END)]
        log(f"--force: re-extracting pages {ACTUAL_START}–{END} (existing pages overwritten)")
    else:
        # Resume from the FIRST missing page counting up from 1 — the first
        # discontinuous gap, NOT highest-existing + 1. E.g. with pages 1–10 and
        # 15–20 present, resume from 11 (not 21). The end-page check follows the
        # same logic: if the first gap is past END, nothing is missing.
        resume_from = find_first_gap(EXTRACT_DIR, END)
        if resume_from > END:
            log("No missing pages in 1..END; nothing to resume")
            missing = []
        else:
            if resume_from > 1:
                log(f"Resuming from page {resume_from} (first missing page; "
                    f"pages 1..{resume_from - 1} already present)")
            else:
                log("Starting fresh (no existing pages found)")
            ACTUAL_START = max(START_ARG, resume_from)
            missing = missing_ranges(EXTRACT_DIR, ACTUAL_START, END)

    # --- Extraction (MFD+MFR+OCR) phase ---
    # `missing` holds contiguous (s, e) page ranges that still need extraction;
    # existing pages are never re-extracted (gap-aware resume fills only gaps).
    if missing:
        log("Loading models (single init for all batches)...")
        tasks, mfr_model, mfr_proc, device = init_models(log)
        log("Models loaded. Starting batch loop.")

        failed = False
        for (r_start, r_end) in missing:
            b = r_start
            while b <= r_end:
                start = b
                end = min(b + BATCH_SIZE - 1, r_end)

                batch_log = Path(EXTRACT_DIR) / f"batch_{start}-{end}.log"
                with open(batch_log, "w", encoding="utf-8") as blog:
                    def blog_log(msg):
                        ts = time.strftime("%H:%M:%S")
                        line = f"[{ts}] {msg}"
                        print(line)
                        blog.write(line + "\n")
                        blog.flush()

                    blog_log(f"Batch {start}–{end} starting...")
                    try:
                        process_batch(tasks, mfr_model, mfr_proc, device,
                                      PDF, EXTRACT_DIR, start, end,
                                      MFR_BS, DPI, blog_log,
                                      deskew_mode=args.deskew)
                        blog_log(f"Batch {start}–{end} done")
                    except Exception as e:
                        blog_log(f"Batch {start}–{end} FAILED: {e}")
                        blog_log("TRACEBACK:\n" + traceback.format_exc())
                        traceback.print_exc()
                        log(f"Batch {start}–{end} FAILED — see {batch_log.name}")
                        if device == "cuda":
                            torch.cuda.empty_cache()
                        gc.collect()
                        failed = True
                        break

                b = end + 1
            if failed:
                break

        if failed:
            log("Stopping due to batch failure (see batch_*.log)")
        else:
            lo = min(s for s, _ in missing)
            hi = max(e for _, e in missing)
            log(f"Extraction finished: filled {len(missing)} gap range(s) in pages {lo}–{hi}")
        try:
            del mfr_model
        except NameError:
            pass
        if device == "cuda":
            torch.cuda.empty_cache()
        gc.collect()
    else:
        log("All pages already extracted. Skipping extraction phase.")

    log("Pipeline finished. (Text extraction only — run the figure_detection "
        "sub-flow after config to produce figures.)")


if __name__ == "__main__":
    main()
