#!/usr/bin/env python3
"""rereview_montage.py — 渲染审计后仍低置信的 47 条公式裁图，拼成带标签的 montage，
供 agent 视觉复核（mode A）。每条显示：页码 / formula 索引 / conf / 现有 latex。

输出: <extract_dir>/_mm_repair/rereview/montage_XX.png
用法:
    python rereview_montage.py <pdf_path> <extract_dir> [--dpi 300] [--per 12]
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
from page_json import PageJson

import sys, os, json, glob, re, argparse
sys.stdout.reconfigure(encoding="utf-8")
import fitz
from PIL import Image, ImageDraw, ImageFont

def load_font(size=18):
    for c in (r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\msyh.ttc",
              r"/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.isfile(c):
            try:
                return ImageFont.truetype(c, size)
            except Exception:
                pass
    return ImageFont.load_default(size)

def find_unmarked(pdf_path, extract_dir, text_thresh, formula_conf):
    """返回 [(pno, fidx, conf, latex, bbox)] 仍低置信且未 mm_* 标记的公式。"""
    out = []
    for pf in sorted(glob.glob(os.path.join(extract_dir, "page_*.json"))):
        m = re.search(r"page_(\d+)\.json$", pf)
        if not m:
            continue
        pno = int(m.group(1))
        d = PageJson.load(pf).data
        for i, f in enumerate(d.get("formulas", [])):
            if f.get("mm_repaired") or f.get("mm_reviewed") or f.get("mm_converted"):
                continue
            conf = f.get("conf")
            latex = f.get("latex")
            bad = (latex in (None, "") or any(x in str(latex) for x in
                  ("[MFR_ERR", "[MFR_SKIPPED", ".notdef", "\ufffd")))
            if (isinstance(conf, (int, float)) and conf < formula_conf) or bad:
                out.append((pno, i, conf, latex, f.get("bbox")))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf_path")
    ap.add_argument("extract_dir")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--per", type=int, default=12, help="每张 montage 放几条")
    ap.add_argument("--text-thresh", type=float, default=0.80)
    ap.add_argument("--formula-conf", type=float, default=0.30)
    args = ap.parse_args()

    items = find_unmarked(args.pdf_path, args.extract_dir, args.text_thresh, args.formula_conf)
    print(f"找到未标记低置信公式 {len(items)} 条")
    if not items:
        return

    doc = fitz.open(args.pdf_path)
    font = load_font(18)
    label_font = load_font(15)
    out_dir = os.path.join(args.extract_dir, "_mm_repair", "rereview")
    os.makedirs(out_dir, exist_ok=True)

    thumb_w = 520
    pad = 10
    label_h = 46
    border = 2

    batches = [items[i:i+args.per] for i in range(0, len(items), args.per)]
    for bi, batch in enumerate(batches):
        cells = []
        for (pno, fidx, conf, latex, bbox) in batch:
            page = doc[pno - 1]
            if bbox and len(bbox) == 4:
                x0, y0, x1, y1 = [v for v in bbox]
                # 适度外扩，覆盖下标/根号
                w = x1 - x0; h = y1 - y0
                ex = max(6, int(w * 0.06)); ey = max(6, int(h * 0.18))
                clip = fitz.Rect(x0-ex, y0-ey, x1+ex, y1+ey)
                pix = page.get_pixmap(dpi=args.dpi, clip=clip)
            else:
                pix = page.get_pixmap(dpi=args.dpi)
            img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
            w, h = img.size
            sc = thumb_w / w if w > thumb_w else 1.0
            tw = max(1, int(w * sc)); th = max(1, int(h * sc))
            tc = img.resize((tw, th))
            latex_s = "" if latex is None else str(latex)
            if len(latex_s) > 90:
                latex_s = latex_s[:87] + "..."
            label = f"p{pno:03d} f{fidx} conf={conf:.3f}\n{latex_s}"
            cells.append((tc, label, tw))
        # compose
        rows = (len(cells) + 1) // 2  # 2 columns
        col_w = thumb_w + pad * 2
        row_hs = []
        for r in range(rows):
            c0 = cells[r*2] if r*2 < len(cells) else None
            c1 = cells[r*2+1] if r*2+1 < len(cells) else None
            hmax = max((c0[2] if c0 else 0), (c1[2] if c1 else 0))
            row_hs.append(label_h + hmax + pad * 2)
        canvas_w = 2 * col_w
        canvas_h = sum(row_hs)
        canvas = Image.new("RGB", (canvas_w, canvas_h), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        for idx, (tc, label, tw) in enumerate(cells):
            r, c = divmod(idx, 2)
            y_off = sum(row_hs[:r])
            x = c * col_w + pad
            y = y_off + pad
            draw.text((x, y), label, fill=(180, 0, 0), font=label_font)
            cy = y + label_h
            canvas.paste(tc, (x, cy))
            draw.rectangle([x, cy, x + tc.width, cy + tc.height],
                           outline=(150, 150, 150), width=border)
        out_path = os.path.join(out_dir, f"montage_{bi:02d}.png")
        canvas.save(out_path)
        print(f"  写出 {out_path} ({len(batch)} 条)")
    doc.close()

if __name__ == "__main__":
    main()
