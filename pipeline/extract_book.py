"""PDF-Extract-Kit full pipeline: MFD -> crop -> MFR -> OCR.

Extracts formulas (as LaTeX) and prose text from a PDF. MFR inference is
batched across pages for higher GPU utilization — formulas from all pages are
collected first, then processed in fixed-size batches.

A simple free-VRAM check halves the batch when <1 GB remains.

Usage (inside `pdfextract` conda env):
    python extract_book.py <pdf_path> [--out DIR] [--start N] [--end N] [--dpi 200]
                                        [--mfr-batch-size 64]
                                        [--deskew auto|off|force]

Arguments:
    pdf_path         path to the source PDF (required)
    --out            output directory for per-page JSON (default: <pdf_dir>/_extract)
    --start          first 1-indexed page to process (default: 1)
    --end            last 1-indexed page to process (default: last page)
    --dpi            render DPI (default: 200)
    --mfr-batch-size target MFR batch size for all formula tiers (default: 64); larger = higher GPU
                     utilization but more memory; actual batches are fixed to 32 per tier
                     (small/medium/large) for stable VRAM use, regardless of this value.
    --logfile        path to persistent log file (default: <out>/extract.log)

Each output JSON has the shape:
    {"page": int, "formulas": [{"bbox":[x0,y0,x1,y1],"cls":int,"conf":float,"latex":str}],
     "text": [{"poly":[...],"text":str,"score":float}]}

The cudnn DLL collision fix: paddle reuses torch's bundled cudnn, so
`site-packages/nvidia/cudnn/bin` must stay EMPTY. Run via launch_pipeline.sh (or
extract_pipeline.py) which sets PATH to torch\\lib + the other nvidia cu12 bins
(deliberately omitting cudnn\\bin).
"""
import sys
import os
import json
import time
import traceback
import argparse
import logging
import datetime
import gc

logging.disable(logging.CRITICAL)

# --- absolute paths (verified on this machine; see SKILL.md Reference paths) ---
PEK_ROOT = r"D:\study\model\PDF-Extract-Kit"
PEK_PKG = r"D:\study\model\PDF-Extract-Kit\pdf_extract_kit"
MFD_WEIGHT = (r"D:\study\model\PDF-Extract-Kit\models\models\opendatalab--PDF-Extract-Kit"
              r"\snapshots\master\models\MFD\models\MFD\YOLO\yolo_v8_ft.pt")
MFR_DIR = r"D:\study\model\PDF-Extract-Kit\models\MFR\unimernet_tiny"
MFR_CFG = r"D:\study\model\PDF-Extract-Kit\pdf_extract_kit\configs\unimernet.yaml"
OCR_DET = r"D:\study\model\PDF-Extract-Kit\models\OCR\PaddleOCR\det\ch_PP-OCRv4_det"
OCR_REC = r"D:\study\model\PDF-Extract-Kit\models\OCR\PaddleOCR\rec\ch_PP-OCRv4_rec"

os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
for p in (PEK_ROOT, PEK_PKG):
    if p not in sys.path:
        sys.path.insert(0, p)

import fitz
import cv2
import numpy as np
import torch
import paddle
from PIL import Image
import pdf_extract_kit.tasks  # registers all tasks (incl. OCR)
from pdf_extract_kit.utils.config_loader import initialize_tasks_and_models
from pipeline.deskew import (
    render_page as deskew_render_page,
    DEFAULT_MAX_ANGLE as DESKEW_MAX_ANGLE,
    DEFAULT_THRESHOLD as DESKEW_THRESHOLD,
)


def build_config():
    return {
        "tasks": {
            "formula_detection": {
                "model": "formula_detection_yolo",
                "model_config": {
                    "model_path": MFD_WEIGHT, "device": "cuda",
                    "conf_thres": 0.25, "iou_thres": 0.45, "img_size": 1280,
                },
            },
            "formula_recognition": {
                "model": "formula_recognition_unimernet",
                "model_config": {
                    "cfg_path": MFR_CFG, "model_path": MFR_DIR, "visualize": False,
                },
            },
            "ocr": {
                "model": "ocr_ppocr",
                "model_config": {
                    "lang": "ch", "use_gpu": True, "show_log": False,
                    "det_model_dir": OCR_DET, "rec_model_dir": OCR_REC,
                    "det_db_box_thresh": 0.3,
                    "rec_batch_num": int(os.environ.get("PEK_OCR_BS", "2")),  # per-book override: PEK_OCR_BS=1
                },
            },
        }
    }


def init_models(log=None):
    """Initialize and return (tasks, mfr_model, mfr_proc, device).

    Must be called once; the returned objects are reused across batches.
    """
    _log = log or (lambda msg: None)
    _log("Initializing PDF-Extract-Kit tasks (MFD+MFR+OCR)...")
    tasks = initialize_tasks_and_models(build_config())
    mfd = tasks["formula_detection"].model
    mfr_task = tasks["formula_recognition"]
    ocr = tasks["ocr"]
    device = "cuda" if torch.cuda.is_available() else "cpu"
    mfr_model = mfr_task.model.model.to(device).half()
    mfr_proc = mfr_task.model.vis_processor
    _log(f"INIT OK | device={device} fp16 | tasks={list(tasks.keys())}")
    if device == "cuda":
        free, total = torch.cuda.mem_get_info()
        _log(f"  VRAM after init: {(total-free)/1024**3:.2f}GB / {total/1024**3:.1f}GB used")
    return tasks, mfr_model, mfr_proc, device


def process_batch(tasks, mfr_model, mfr_proc, device,
                  pdf_path, out_dir, start, end, mfr_batch_size, dpi, log,
                  deskew_mode="auto"):
    """Process pages start..end with already-initialized models.

    Loads MFD+OCR for Phase 1, then unloads them for Phase 2 (MFR),
    keeping MFR model in VRAM throughout.  The caller should provide
    a fresh log function that writes to its own log file.
    """
    mfd = tasks["formula_detection"].model
    ocr = tasks["ocr"]

    log(f"Processing pages {start}..{end} -> {out_dir}")

    doc = fitz.open(pdf_path)
    total = doc.page_count
    end = min(end, total)

    # ===================================================================
    # Phase 1 — render, MFD, crop & OCR
    # ===================================================================
    page_data = []
    all_crops = []
    page_crop_ranges = []
    phase1_t0 = time.time()
    render_total = mfd_total = ocr_total = 0.0

    for pno in range(start, end + 1):
        t0 = time.time()
        img_bgr, (W, H), skew = deskew_render_page(
            doc, pno - 1, dpi, deskew_mode=deskew_mode,
            max_angle=DESKEW_MAX_ANGLE, threshold=DESKEW_THRESHOLD)
        pil = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
        if skew:
            log(f"  deskew page {pno}: rotated {skew:+.2f}°")
        t1 = time.time()

        res = mfd.predict([img_bgr], None)[0]
        t2 = time.time()

        boxes = res.boxes.xyxy.cpu().numpy()
        clss = res.boxes.cls.cpu().numpy()
        confs = res.boxes.conf.cpu().numpy()

        crops_meta = []
        for b, c, cf in zip(boxes, clss, confs):
            x0, y0, x1, y1 = [int(v) for v in b]
            x0, y0 = max(0, x0), max(0, y0)
            x1, y1 = min(img_bgr.shape[1], x1), min(img_bgr.shape[0], y1)
            if x1 - x0 < 4 or y1 - y0 < 4:
                continue
            crop = pil.crop((x0, y0, x1, y1))
            crops_meta.append(([x0, y0, x1, y1], int(c), float(cf), crop))

        start_idx = len(all_crops)
        for _, _, _, crop in crops_meta:
            all_crops.append(crop)
        page_crop_ranges.append((start_idx, len(all_crops)))

        ocr_res = ocr.predict_image(pil)
        text = []
        for item in ocr_res:
            if isinstance(item, dict):
                text.append({
                    "poly": item.get("poly"), "text": item.get("text"),
                    "score": item.get("score"),
                })
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                text.append({"poly": item[0], "text": item[1][0],
                             "score": item[1][1] if len(item[1]) > 1 else None})
        t3 = time.time()

        page_data.append({"pno": pno, "crops_meta": crops_meta,
                          "text": text, "skew": skew})
        render_total += t1 - t0
        mfd_total += t2 - t1
        ocr_total += t3 - t2
        log(f"  MFD+OCR page {pno}: {len(crops_meta)}F {len(text)}T ({t3-t0:.1f}s)")

        if device == "cuda" and (pno % 5 == 0):
            torch.cuda.empty_cache()
            gc.collect()

    phase1_elapsed = time.time() - phase1_t0
    total_formulas = len(all_crops)
    log(f"Phase 1 done: {len(page_data)} pages, {total_formulas} formulas "
          f"({phase1_elapsed:.1f}s | render={render_total:.1f}s "
          f"MFD={mfd_total:.1f}s OCR={ocr_total:.1f}s)")

    # Unload MFD+OCR for Phase 2
    try: del mfd, ocr
    except NameError: pass
    if device == "cuda":
        torch.cuda.empty_cache()
        try: paddle.device.cuda.empty_cache()
        except: pass
    gc.collect()

    # ===================================================================
    # Phase 2 — MFR
    # ===================================================================
    phase2_t0 = time.time()
    use_cpu = False

    log(f"  Preprocessing {total_formulas} crops into tensors...")
    crop_items = []
    with torch.device("cpu"):
        for i, crop in enumerate(all_crops):
            t = mfr_proc(crop).unsqueeze(0)
            if t.device.type != "cpu":
                t_cpu = t.cpu(); del t; t = t_cpu
            crop_items.append((i, crop.width * crop.height, t))
    del all_crops
    if device == "cuda":
        torch.cuda.empty_cache()
        try: paddle.device.cuda.empty_cache()
        except: pass
    gc.collect()
    t_prep = time.time() - phase2_t0
    log(f"  Preprocessing done ({t_prep:.1f}s)")

    small = []; medium = []; large = []
    for item in crop_items:
        idx, a, t = item
        if a < 10000: small.append(item)
        elif a < 40000: medium.append(item)
        else: large.append(item)

    TIERS = [(small, "small", 32), (medium, "medium", 32), (large, "large", 32)]
    all_pred_strs = [None] * total_formulas
    batch_no = 0

    for tier_items, label, tier_batch_sz in TIERS:
        if not tier_items: continue
        n_tier = len(tier_items)
        log(f"  Tier {label}: {n_tier} formulas, batch={tier_batch_sz}")

        for s in range(0, n_tier, tier_batch_sz):
            batch_items = tier_items[s:s + tier_batch_sz]
            batch_indices = [it[0] for it in batch_items]
            batch_tensors = [it[2] for it in batch_items]

            if device == "cuda":
                free_bytes, _ = torch.cuda.mem_get_info()
                if free_bytes < 1.0 * (1024**3) and len(batch_tensors) > 1:
                    new_n = max(1, len(batch_tensors) // 2)
                    log(f"  Low VRAM ({free_bytes/(1024**3):.1f}GB): "
                        f"reducing batch {len(batch_tensors)} -> {new_n}")
                    batch_indices = batch_indices[:new_n]
                    batch_tensors = batch_tensors[:new_n]
                    torch.cuda.empty_cache()
                    try: paddle.device.cuda.empty_cache()
                    except: pass
                    gc.collect()

            batch_no += 1
            attempt_cpu = use_cpu

            while True:
                try:
                    cur_device = "cpu" if attempt_cpu else device
                    if cur_device not in str(mfr_model.device):
                        log(f"  Moving MFR model to {cur_device}...")
                        mfr_model.to(cur_device)
                    pixel_values = torch.cat(batch_tensors).to(
                        device=cur_device, dtype=torch.float16)
                    log(f"  Batch {batch_no}: {len(batch_tensors)} crops "
                        f"shape={list(pixel_values.shape)} on {cur_device}")
                    out_dict = mfr_model.generate({"image": pixel_values})
                    batch_strs = out_dict["pred_str"]
                    for orig_idx, pred in zip(batch_indices, batch_strs):
                        all_pred_strs[orig_idx] = pred
                    log(f"  Batch {batch_no} done ({len(batch_strs)} formulas)")
                    break
                except torch.cuda.OutOfMemoryError:
                    torch.cuda.empty_cache()
                    try: paddle.device.cuda.empty_cache()
                    except: pass
                    if not attempt_cpu and len(batch_tensors) > 1:
                        log(f"  OOM on batch {batch_no}, retrying one-at-a-time...")
                        for t_idx, t in enumerate(batch_tensors):
                            try:
                                tv = t.to(device=device, dtype=torch.float16)
                                out_dict = mfr_model.generate({"image": tv})
                                all_pred_strs[batch_indices[t_idx]] = out_dict["pred_str"][0]
                            except Exception as e2:
                                all_pred_strs[batch_indices[t_idx]] = f"[MFR_ERR {str(e2)[:200]}]"
                            torch.cuda.empty_cache()
                            try: paddle.device.cuda.empty_cache()
                            except: pass
                            gc.collect()
                        log(f"  Batch {batch_no} done (split into single crops)")
                        break
                    elif not attempt_cpu:
                        log(f"  OOM, falling back to CPU")
                        attempt_cpu = True
                        use_cpu = True
                    else:
                        for idx in batch_indices:
                            all_pred_strs[idx] = "[MFR_ERR CPU OOM]"
                        break
                except Exception as e:
                    for idx in batch_indices:
                        all_pred_strs[idx] = f"[MFR_ERR {str(e)[:200]}]"
                    log(f"  Exception on batch {batch_no}: {e}")
                    break

            if device == "cuda":
                try: del pixel_values
                except NameError: pass
                try: del out_dict
                except NameError: pass
                torch.cuda.empty_cache()
                try: paddle.device.cuda.empty_cache()
                except: pass
            gc.collect()

            done = sum(1 for s in all_pred_strs if s is not None)
            if done > 0:
                elapsed = time.time() - phase2_t0
                log(f"  Progress: {done}/{total_formulas} "
                    f"({elapsed:.1f}s, ~{elapsed/done*1000:.0f}ms/crop)")

    missing = [i for i, s in enumerate(all_pred_strs) if s is None]
    if missing:
        log(f"  WARNING: {len(missing)} formulas not processed: {missing[:10]}...")
        for i in missing:
            all_pred_strs[i] = "[MFR_SKIPPED]"

    phase2_elapsed = time.time() - phase2_t0
    log(f"Phase 2 done: {total_formulas} formulas in {batch_no} batches "
          f"({phase2_elapsed:.1f}s, ~{phase2_elapsed/total_formulas*1000:.0f}ms/crop)")

    if device == "cuda":
        torch.cuda.empty_cache()
        try: paddle.device.cuda.empty_cache()
        except: pass
    gc.collect()

    # ===================================================================
    # Phase 3 — write per-page JSON
    # ===================================================================
    phase3_t0 = time.time()
    for pg, (s_idx, e_idx) in zip(page_data, page_crop_ranges):
        pno = pg["pno"]
        formulas = []
        for (bbox, c, cf, _), latex in zip(pg["crops_meta"], all_pred_strs[s_idx:e_idx]):
            formulas.append({"bbox": bbox, "cls": c, "conf": cf, "latex": latex})
        skew = pg.get("skew", 0.0)
        out = {"page": pno, "formulas": formulas, "text": pg["text"],
               "deskew": {"angle_deg": round(skew, 3),
                          "mode": deskew_mode}}
        with open(os.path.join(out_dir, f"page_{pno:03d}.json"), "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False)
        log(f"  Write page {pno}: {len(formulas)}F {len(pg['text'])}T")

    phase3_elapsed = time.time() - phase3_t0
    doc.close()
    log(f"Phase 3 done ({phase3_elapsed:.1f}s)")

    total_elapsed = time.time() - phase1_t0
    log(f"BATCH DONE pages {start}..{end}  |  total={total_elapsed:.1f}s  "
          f"(Phase1={phase1_elapsed:.1f}s  Phase2={phase2_elapsed:.1f}s  "
          f"Phase3={phase3_elapsed:.1f}s)")


def main():
    ap = argparse.ArgumentParser(description="PDF-Extract-Kit MFD+MFR+OCR pipeline")
    ap.add_argument("pdf_path", help="path to source PDF")
    ap.add_argument("--out", default=None, help="output dir for per-page JSON")
    ap.add_argument("--start", type=int, default=1, help="first 1-indexed page")
    ap.add_argument("--end", type=int, default=None, help="last 1-indexed page")
    ap.add_argument("--dpi", type=int, default=200, help="render DPI")
    ap.add_argument("--mfr-batch-size", type=int, default=64,
                     help="MFR batch size hint (default: 64); actual per-tier batch is fixed to 32")
    ap.add_argument("--deskew", default="auto", choices=["auto", "off", "force"],
                    help="skew correction for scanned pages: auto (correct only when "
                         "confidently skewed, default), off (disabled), force (always rotate)")
    ap.add_argument("--logfile", default=None,
                    help="persistent log file path (default: <out>/extract.log)")
    ap.add_argument("--no-figures", action="store_true",
                    help="skip the figure-extraction phase at the end")
    args = ap.parse_args()

    pdf_path = os.path.abspath(args.pdf_path)
    if not os.path.isfile(pdf_path):
        print(f"ERROR: PDF not found: {pdf_path}")
        sys.exit(1)

    book_dir = os.path.dirname(pdf_path)
    out_dir = args.out or os.path.join(book_dir, "_extract")
    os.makedirs(out_dir, exist_ok=True)

    log_path = args.logfile or os.path.join(out_dir, "extract.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    _log_file = open(log_path, "a", encoding="utf-8")
    _log_file.write(f"\n--- {datetime.datetime.now().isoformat()} ---\n")
    _log_file.flush()

    def log(msg):
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:12]
        line = f"[{ts}] {msg}"
        _log_file.write(line + "\n")
        _log_file.flush()
        sys.stdout.write(line + "\n")
        sys.stdout.flush()

    end = args.end if args.end is not None else fitz.open(pdf_path).page_count
    tasks, mfr_model, mfr_proc, device = init_models(log)
    process_batch(tasks, mfr_model, mfr_proc, device,
                  pdf_path, out_dir, args.start, end,
                  args.mfr_batch_size, args.dpi, log,
                  deskew_mode=args.deskew)

    if device == "cuda":
        torch.cuda.empty_cache()
        try: paddle.device.cuda.empty_cache()
        except: pass
    gc.collect()
    log(f"EXTRACTION DONE -> {out_dir}")

    # --- Figure phase (two-stage): (1) detection saves crops with positional
    #     names + figure_detect.json; (2) assignment names them 图X.X.X into
    #     figure_index.json. Runs by default so the recognition step also stores
    #     figures; disable with --no-figures. ---
    if args.no_figures:
        log("Figure phase skipped (--no-figures).")
    else:
        try:
            from figure.extract_figures import run_full_book
            from figure.assign_figures import run_book as assign_figures_book
            log("Figure phase (1/2 detection): extracting figures on all pages...")
            run_full_book(pdf_path, out_dir, deskew=args.deskew)
            log("Figure detection done.")
            log("Figure phase (2/2 assignment): naming figures 图X.X.X...")
            assign_figures_book(pdf_path, out_dir)
            log("Figure assignment done -> figure_index.json")
        except Exception as e:
            log(f"Figure phase FAILED: {e}")

    log(f"ALL DONE -> {out_dir}")


if __name__ == "__main__":
    main()
