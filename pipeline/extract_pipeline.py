"""Background pipeline driver — runs batches with incremental figure detection + per-chapter assignment.

Usage (launch detached from the skill dir):
    python extract_pipeline.py <pdf_path> <total_pages> [--force] [--no-figures]

The _extract/ output directory is derived automatically as <pdf_parent>/_extract.

Incremental figure workflow (runs interleaved with extraction batches):
  - After each batch, detection runs on the batch's pages (appends to figure_detect.json)
  - When a chapter's pages are ALL detected, assignment (assign_figures.run_chapter)
    runs automatically for that chapter — the agent's polling loop can then reference
    figure_index.json as soon as each chapter is done, without waiting for all pages.
"""

import sys, os, json, time, glob, re, gc, argparse
from pathlib import Path
import torch

sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent.absolute()))
from pipeline.extract_book import init_models, process_batch
from figure.extract_figures import detect_pages_range, load_chapter_map, detected_pages_set
from figure.assign_figures import run_chapter

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


def find_max_page(extract_dir):
    """Return highest page number found in existing page_*.json, or 0."""
    pat = os.path.join(extract_dir, "page_*.json")
    files = glob.glob(pat)
    if not files:
        return 0
    nums = []
    for f in files:
        m = re.search(r"page_(\d+)\.json$", f)
        if m:
            nums.append(int(m.group(1)))
    return max(nums) if nums else 0


def main():
    ap = argparse.ArgumentParser(
        description="Background pipeline with incremental figure detection+assignment")
    ap.add_argument("pdf", help="path to source PDF, e.g. D:\\study\\book\\<书名>\\<书名>.pdf")
    ap.add_argument("total_pages", type=int, help="total page count of the PDF")
    ap.add_argument("--force", action="store_true",
                    help="restart from page 1, ignoring existing pages")
    ap.add_argument("--no-figures", action="store_true",
                    help="skip figure detection and assignment entirely")
    args = ap.parse_args()

    global LOG_FILE
    PDF = args.pdf
    TOTAL_PAGES = args.total_pages
    EXTRACT_DIR = str(Path(PDF).resolve().parent / "_extract")
    LOG_FILE = Path(EXTRACT_DIR) / "extract_pipeline.log"
    Path(EXTRACT_DIR).mkdir(parents=True, exist_ok=True)

    if args.force:
        resume_from = 1
        log("--force: restarting from page 1")
    else:
        resume_from = find_max_page(EXTRACT_DIR) + 1
        if resume_from > 1:
            log(f"Resuming from page {resume_from} (highest existing: {resume_from - 1})")
        else:
            log("Starting fresh (no existing pages found)")

    # State for incremental figure workflow (model reused across batches)
    layout_model = None
    assigned_chs = set()

    # --- Extraction (MFD+MFR+OCR) phase ---
    if resume_from <= TOTAL_PAGES:
        log("Loading models (single init for all batches)...")
        tasks, mfr_model, mfr_proc, device = init_models(log)
        log("Models loaded. Starting batch loop.")

        start = resume_from
        while start <= TOTAL_PAGES:
            end = min(start + BATCH_SIZE - 1, TOTAL_PAGES)

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
                                  MFR_BS, DPI, blog_log)
                    blog_log(f"Batch {start}–{end} done")
                except Exception as e:
                    blog_log(f"Batch {start}–{end} FAILED: {e}")
                    log(f"Batch {start}–{end} FAILED — see {batch_log.name}")
                    if device == "cuda":
                        torch.cuda.empty_cache()
                    gc.collect()
                    break

            # --- Incremental figure detection on this batch's pages ---
            if not args.no_figures:
                try:
                    layout_model, new_ents = detect_pages_range(
                        PDF, EXTRACT_DIR, start, end, model=layout_model)
                    log(f"Figure detect pages {start}–{end}: {len(new_ents)} crops")

                    # Per-chapter assignment: for any chapter whose pages are
                    # now ALL detected, run assignment immediately.
                    chap_map = load_chapter_map(EXTRACT_DIR)
                    if chap_map:
                        detected = detected_pages_set(EXTRACT_DIR)
                        for ch, info in chap_map.items():
                            if ch in assigned_chs:
                                continue
                            s, e = info.get("start"), info.get("end")
                            if s and e and all(p in detected for p in range(s, e + 1)):
                                try:
                                    run_chapter(PDF, EXTRACT_DIR, ch, s, e)
                                    log(f"Figure assign ch{ch}: pages {s}–{e} -> figure_index.json")
                                    assigned_chs.add(ch)
                                except Exception as ae:
                                    log(f"Figure assign ch{ch} FAILED: {ae}")
                    else:
                        log("Chapter map not ready yet; skipping assignment check")
                except Exception as fe:
                    log(f"Figure detection on pages {start}–{end} FAILED: {fe}")

            start = end + 1

        last = min(start - 1, TOTAL_PAGES)
        log(f"Extraction finished (pages {resume_from}–{last})")
        try:
            del mfr_model
        except NameError:
            pass
        if device == "cuda":
            torch.cuda.empty_cache()
        gc.collect()
    else:
        log("All pages already extracted. Skipping extraction phase.")
        # Catch up: detect any undetected pages, then assign remaining chapters
        if not args.no_figures:
            try:
                chap_map = load_chapter_map(EXTRACT_DIR)
                if chap_map:
                    detected = detected_pages_set(EXTRACT_DIR)
                    undetected = sorted(set(range(1, TOTAL_PAGES + 1)) - detected)
                    if undetected:
                        log(f"Detecting {len(undetected)} previously undetected pages...")
                        layout_model, _ = detect_pages_range(
                            PDF, EXTRACT_DIR, undetected[0], undetected[-1],
                            model=layout_model)
                    detected = detected_pages_set(EXTRACT_DIR)
                    for ch, info in chap_map.items():
                        s, e = info.get("start"), info.get("end")
                        if s and e and all(p in detected for p in range(s, e + 1)):
                            try:
                                run_chapter(PDF, EXTRACT_DIR, ch, s, e)
                                assigned_chs.add(ch)
                            except Exception as ae:
                                log(f"Figure assign ch{ch} FAILED: {ae}")
                else:
                    log("Chapter map not found; skipping figure phase")
            except Exception as fe:
                log(f"Figure catch-up FAILED: {fe}")

    # --- Final pass: assign any remaining chapters that are fully detected ---
    if not args.no_figures:
        chap_map = load_chapter_map(EXTRACT_DIR)
        if chap_map:
            detected = detected_pages_set(EXTRACT_DIR)
            for ch, info in chap_map.items():
                s, e = info.get("start"), info.get("end")
                if ch not in assigned_chs and s and e and all(p in detected for p in range(s, e + 1)):
                    try:
                        run_chapter(PDF, EXTRACT_DIR, ch, s, e)
                        log(f"Figure assign ch{ch}: final pass -> figure_index.json")
                        assigned_chs.add(ch)
                    except Exception as ae:
                        log(f"Figure assign ch{ch} FAILED: {ae}")

    log("Pipeline finished.")


if __name__ == "__main__":
    main()
