#!/usr/bin/env python3
"""mm_repair_audit.py — 扫描 page_*.json 的低置信条目，渲染裁图 + 拼版。

本脚本**不需要视觉能力**：它只做扫描、裁图、生成拼版，供支持看图的模型
（WorkBuddy agent）后续读取并补全。若当前模型不支持看图，整步跳过即可。

用法:
    python mm_repair_audit.py <pdf_path> <extract_dir>
        [--text-thresh 0.80] [--formula-conf 0.30] [--vpad-lines 0.5]
        [--src-dpi 200] [--dpi 300]

扫描 <extract_dir> 下所有 page_*.json：
  - 文本条目：score < text_thresh 且尚未 mm_repaired/mm_reviewed
  - 公式条目：conf < formula_conf 或 latex 含错误/乱码标记 且尚未 repaired
对命中的条目：
  - 按 --src-dpi → --dpi 缩放比例，用 poly(文本)/bbox(公式) 从 PDF 裁出区域，
    存 <extract_dir>/_mm_repair/page_NNN/<type>_<index>.png
  - 生成每页拼版 <extract_dir>/_mm_repair/page_NNN_sheet.png（带 key 标签，便于批量读）
  - 记入 <extract_dir>/_mm_repair/manifest.json（稳定 key = f"{type}:{index}"）

幂等：已 mm_repaired / mm_reviewed 的条目跳过；已存在的裁图复用，不重渲染。
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
import mm_repair_manifest
from page_json import PageJson

import sys, os, json, glob, re, argparse
sys.stdout.reconfigure(encoding="utf-8")

import fitz
from PIL import Image, ImageDraw, ImageFont

# 公式错误/乱码标记（命中即视为需重认）
ERR_MARKERS = ("[MFR_ERR", "[MFR_SKIPPED", ".notdef", "\ufffd")

REPAIR_DIRNAME = "_mm_repair"


def is_formula_bad(latex):
    if latex is None:
        return True
    s = str(latex)
    for m in ERR_MARKERS:
        if m in s:
            return True
    if s.strip() == "":
        return True
    return False


def load_font(size=20):
    candidates = [
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
        r"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for c in candidates:
        if os.path.isfile(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default(size)
    except Exception:
        return ImageFont.load_default()


def poly_to_bbox(poly, scale):
    if not poly:
        return None
    xs = [poly[i] for i in range(0, len(poly), 2)]
    ys = [poly[i + 1] for i in range(0, len(poly), 2)]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    return [x0 * scale, y0 * scale, x1 * scale, y1 * scale]


def page_avg_line_h(data):
    """Estimate average text line height (src coords) from text polys."""
    hs = []
    for t in data.get("text", []):
        poly = t.get("poly")
        if poly and len(poly) >= 8:
            ys = [poly[i + 1] for i in range(0, len(poly), 2)]
            h = max(ys) - min(ys)
            if h > 0:
                hs.append(h)
    return (sum(hs) / len(hs)) if hs else None


def render_page_crops(doc, pno, dpi, src_dpi, entries, out_dir, page_prefix,
                      avg_line_h=None, vpad_lines=0.5):
    """entries: list of (key, kind, region) where region is poly or bbox in src coords.
    avg_line_h: 该页平均行高(src coords)，用于计算纵向 padding；None 时回退小 padding。
    vpad_lines: 纵向 padding = avg_line_h * vpad_lines，默认 0.5（上下各半行，覆盖小倾斜）。
    Returns list of (key, crop_path, pil_crop)."""
    scale = dpi / src_dpi
    page = doc[pno - 1]
    pix = page.get_pixmap(dpi=dpi)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

    crops = []
    for key, kind, region in entries:
        if kind == "text":
            bbox = poly_to_bbox(region, scale)
        else:  # formula bbox already [x0,y0,x1,y1]
            bbox = [v * scale for v in region]
        if not bbox:
            continue
        x0, y0, x1, y1 = [int(round(v)) for v in bbox]
        x0, y0 = max(0, x0), max(0, y0)
        x1 = min(img.width, x1)
        y1 = min(img.height, y1)
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        # 纵向 padding：上下各加 vpad_lines 个平均行高，覆盖低置信区域的小倾斜
        if avg_line_h and avg_line_h > 0:
            vpad = int(round(avg_line_h * scale * vpad_lines))
        else:
            vpad = max(4, int((y1 - y0) * 0.05))
        # 横向 padding：保留小 context，避免裁掉相邻字符边缘
        hpad = max(4, int((x1 - x0) * 0.05))
        x0 = max(0, x0 - hpad); y0 = max(0, y0 - vpad)
        x1 = min(img.width, x1 + hpad); y1 = min(img.height, y1 + vpad)
        crop = img.crop((x0, y0, x1, y1))
        crop_path = os.path.join(out_dir, f"{page_prefix}_{key.replace(':', '_')}.png")
        crop.save(crop_path)
        crops.append((key, crop_path, crop))
    return crops


def make_sheet(page_crops, out_path, font, thumb_w=420):
    cols = 3
    pad = 14
    header_h = 30
    cells = []
    for key, _path, crop in page_crops:
        w, h = crop.size
        scale = thumb_w / w if w > thumb_w else 1.0
        tw = max(1, int(w * scale)); th = max(1, int(h * scale))
        tc = crop.resize((tw, th))
        cells.append((key, tc, th))
    if not cells:
        return
    rows = (len(cells) + cols - 1) // cols
    cell_w = thumb_w + pad * 2
    row_heights = [0] * rows
    for i, (_k, _tc, th) in enumerate(cells):
        r = i // cols
        row_heights[r] = max(row_heights[r], header_h + th + pad * 2)
    canvas_w = cols * cell_w
    canvas_h = sum(row_heights)
    canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
    draw = ImageDraw.Draw(canvas)
    for i, (key, tc, th) in enumerate(cells):
        r, c = divmod(i, cols)
        y_off = sum(row_heights[:r])
        x = c * cell_w + pad
        y = y_off + pad
        # key label
        draw.text((x, y), key, fill=(200, 0, 0), font=font)
        # crop
        canvas.paste(tc, (x, y + header_h))
        # border
        draw.rectangle([x, y + header_h, x + tc.width, y + header_h + tc.height],
                       outline=(180, 180, 180), width=1)
    canvas.save(out_path)


def audit(pdf_path, extract_dir, text_thresh, formula_conf, src_dpi, dpi,
          vpad_lines=0.5, thumb_w=420):
    mm_dir = os.path.join(extract_dir, REPAIR_DIRNAME)
    os.makedirs(mm_dir, exist_ok=True)
    font = load_font(20)

    page_files = sorted(glob.glob(os.path.join(extract_dir, "page_*.json")))
    if not page_files:
        print("MM_AUDIT: no page_*.json found, nothing to do")
        return 0

    # load existing manifest for already-resolved keys
    manifest_path = os.path.join(mm_dir, "manifest.json")
    prev_resolved = set()
    if os.path.isfile(manifest_path):
        try:
            prev = mm_repair_manifest.MmRepairManifest.load(manifest_path).data
            for p, info in prev.get("pages", {}).items():
                for e in info.get("entries", []):
                    if e.get("resolved"):
                        prev_resolved.add(f"{p}:{e['key']}")
        except Exception:
            prev_resolved = set()

    doc = fitz.open(pdf_path)
    pages_out = {}
    total_flagged = 0

    for pf in page_files:
        m = re.search(r"page_(\d+)\.json$", pf)
        if not m:
            continue
        pno = int(m.group(1))
        data = PageJson.load(pf).data
        page_prefix = f"page_{pno:03d}"
        avg_line_h = page_avg_line_h(data)

        flagged = []  # (key, kind, region, current, score)
        # text
        for i, t in enumerate(data.get("text", [])):
            if t.get("mm_repaired") or t.get("mm_reviewed"):
                continue
            score = t.get("score")
            if isinstance(score, (int, float)) and score < text_thresh:
                key = f"text:{i}"
                if f"{pno:03d}:{key}" in prev_resolved:
                    continue
                flagged.append((key, "text", t.get("poly"), t.get("text", ""), score))
        # formula
        for i, f in enumerate(data.get("formulas", [])):
            if f.get("mm_repaired") or f.get("mm_reviewed") or f.get("mm_converted"):
                continue
            conf = f.get("conf")
            latex = f.get("latex")
            bad = is_formula_bad(latex)
            if (isinstance(conf, (int, float)) and conf < formula_conf) or bad:
                key = f"formula:{i}"
                if f"{pno:03d}:{key}" in prev_resolved:
                    continue
                reason = "low_conf" if (isinstance(conf, (int, float)) and conf < formula_conf) else "bad_latex"
                flagged.append((key, "formula", f.get("bbox"), latex, conf, reason))

        if not flagged:
            continue

        page_out_dir = os.path.join(mm_dir, page_prefix)
        os.makedirs(page_out_dir, exist_ok=True)
        entries_for_render = [(k, kind, region) for (k, kind, region, *_rest) in flagged]
        page_crops = render_page_crops(doc, pno, dpi, src_dpi, entries_for_render,
                                       page_out_dir, page_prefix,
                                       avg_line_h=avg_line_h, vpad_lines=vpad_lines)

        entries = []
        for (key, kind, region, current, *rest) in flagged:
            crop_path = next((p for (k2, p, _c) in page_crops if k2 == key), None)
            rec = {
                "key": key, "type": kind, "index": int(key.split(":")[1]),
                "current": current, "crop": os.path.relpath(crop_path, mm_dir) if crop_path else None,
                "resolved": False,
            }
            if kind == "text":
                rec["score"] = rest[0]
            else:
                rec["conf"] = rest[0]
                rec["reason"] = rest[1]
            entries.append(rec)

        sheet_path = os.path.join(mm_dir, f"{page_prefix}_sheet.png")
        make_sheet(page_crops, sheet_path, font, thumb_w=thumb_w)

        pages_out[f"{pno:03d}"] = {
            "sheet": f"{page_prefix}_sheet.png",
            "count": len(entries),
            "entries": entries,
        }
        total_flagged += len(entries)
        print(f"  page {pno:03d}: {len(entries)} flagged -> {page_prefix}_sheet.png")

    doc.close()

    manifest = {
        "pdf": os.path.abspath(pdf_path),
        "extract_dir": os.path.abspath(extract_dir),
        "text_thresh": text_thresh,
        "formula_conf": formula_conf,
        "src_dpi": src_dpi,
        "dpi": dpi,
        "total_flagged": total_flagged,
        "status": "pending" if total_flagged else "none",
        "pages": pages_out,
    }
    mm_repair_manifest.MmRepairManifest(data=manifest).dump(manifest_path)

    if total_flagged:
        print(f"MM_AUDIT DONE: {total_flagged} entries flagged across "
              f"{len(pages_out)} pages -> {manifest_path}")
        print("  Next: agent reads each *_sheet.png + manifest, writes repairs.json, "
              "then runs mm_repair_apply.py")
    else:
        print("MM_AUDIT DONE: nothing flagged (all entries confident or already resolved)")
    return total_flagged


def main():
    ap = argparse.ArgumentParser(description="Audit low-confidence page_*.json entries")
    ap.add_argument("pdf_path")
    ap.add_argument("extract_dir")
    ap.add_argument("--text-thresh", type=float, default=0.80)
    ap.add_argument("--formula-conf", type=float, default=0.30)
    ap.add_argument("--src-dpi", type=int, default=200,
                    help="DPI used during extraction (poly/bbox coords are in this space)")
    ap.add_argument("--dpi", type=int, default=300,
                    help="DPI to render crops at (higher = clearer)")
    ap.add_argument("--vpad-lines", type=float, default=0.5,
                    help="纵向 padding = 平均行高 × 此值，加在被标区域上下两侧，"
                         "用于覆盖小倾斜导致的裁切不全（默认 0.5 = 上下各半行）")
    ap.add_argument("--thumb-w", type=int, default=420,
                    help="每页拼版 sheet 中每个裁图的缩略图宽度（默认 420，hard cases 可设 700）")
    args = ap.parse_args()

    if not os.path.isfile(args.pdf_path):
        print(f"ERROR: PDF not found: {args.pdf_path}")
        sys.exit(1)
    audit(args.pdf_path, args.extract_dir, args.text_thresh,
          args.formula_conf, args.src_dpi, args.dpi, args.vpad_lines, args.thumb_w)


if __name__ == "__main__":
    main()
