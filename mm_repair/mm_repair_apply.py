#!/usr/bin/env python3
"""mm_repair_apply.py — 把 agent 的多模态补全写回 page_*.json。

读取:
    <extract_dir>/_mm_repair/manifest.json   （由 mm_repair_audit.py 生成）
    <extract_dir>/_mm_repair/repairs.json     （由 agent 视觉补全后写出）

repairs.json 格式:
{
  "corrections": {
     "001": { "text:3": "修正后的文本", "formula:0": "修正后的 LaTeX" },
     ...
  },
  "ok": {
     "001": ["text:5", "formula:2"],   // agent 确认 OCR 正确、无需改的条目
     ...
  },
  "to_formula": {
     "001": { "text:9": "x^2 + y^2 = r^2" },   // 字符串：整行即一个公式
     "002": { "text:3": [                        // 分段列表：一行拆成 文本+公式+文本
               {"type":"text","text":"("},
               {"type":"formula","latex":"k = 0,1,\\dots,n"},
               {"type":"text","text":")"} ] },
     ...
  }
}

对 corrections: 把 text[].text / formulas[].latex 改为正确值，
  设 mm_repaired=true，原值存入 text_ocr / latex_ocr。
对 ok: 设 mm_reviewed=true（值不变，避免下一轮重复送审）。
对 to_formula: 把被 OCR 误判为文本的整行（或整行中的一段）公式，转成 formulas[]
  的新 item，设 mm_converted=true；随后**删除原 text 项**（不保留低置信原 OCR
  文本，不存 text_ocr）。

  to_formula 的值支持两种形态：
    (a) 字符串：整行即一个公式（旧行为），用该 text 的 poly 求包围盒作 bbox。
    (b) 分段列表：整行其实是「文本 + 公式 + 文本 + …」交错，例如
          [{"type":"text","text":"("},
           {"type":"formula","latex":"k = 0,1,\\dots,n"},
           {"type":"text","text":")"}]
        此时把整行 x 区间按各段权重切成子区间，文本段回填 text[]（带子 poly）、
        公式段按 (y,x) 顺序插入 formulas[]，从而**保留行内阅读顺序**，而非把整
        行压成单一公式或追加到 formulas 末尾。原 text 项被这些段整体替代/删除。

  单字符串形态回写后 summary 按正常公式渲染 mm_converted 项即可；分段形态下
  行内文本与公式均带正确 (y,x)，下游按 (page,poly_y) 合并时顺序自然正确。
回写 page_NNN.json，并更新 manifest 中对应条目的 resolved=true。

用法:
    python mm_repair_apply.py <extract_dir> [--dry]
"""
import sys, os, json, argparse
sys.stdout.reconfigure(encoding="utf-8")

REPAIR_DIRNAME = "_mm_repair"


def poly_to_bbox(poly):
    """把 OCR 的 poly（[[x,y],...] 或扁平 [x0,y0,x1,y1,...]）转成 [x0,y0,x1,y1] 包围盒。"""
    if not poly:
        return [0, 0, 0, 0]
    if isinstance(poly[0], (list, tuple)):
        pts = poly
    else:
        pts = [[poly[i], poly[i + 1]] for i in range(0, len(poly) - 1, 2)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return [min(xs), min(ys), max(xs), max(ys)]


def insert_formula_by_position(formulas, new_f):
    """把新公式按 (y, x) 顺序插入 formulas[]，保证阅读顺序（而非追加到末尾）。"""
    b = new_f.get("bbox") or [0, 0, 0, 0]
    y = b[1] if len(b) >= 2 else 0
    x = b[0] if len(b) >= 1 else 0
    lo, hi = 0, len(formulas)
    while lo < hi:
        mid = (lo + hi) // 2
        mb = formulas[mid].get("bbox") or [0, 0, 0, 0]
        my = mb[1] if len(mb) >= 2 else 0
        mx = mb[0] if len(mb) >= 1 else 0
        if (my, mx) < (y, x):
            lo = mid + 1
        else:
            hi = mid
    formulas.insert(lo, new_f)


def apply(extract_dir, dry=False, repairs_path=None):
    mm_dir = os.path.join(extract_dir, REPAIR_DIRNAME)
    manifest_path = os.path.join(mm_dir, "manifest.json")
    if repairs_path is None:
        repairs_path = os.path.join(mm_dir, "repairs.json")
    if not os.path.isfile(manifest_path):
        print("MM_APPLY: no manifest.json — run mm_repair_audit.py first")
        return 1
    if not os.path.isfile(repairs_path):
        print("MM_APPLY: no repairs.json — agent must produce it first (or it's empty)")
        return 1

    manifest = json.load(open(manifest_path, encoding="utf-8"))
    repairs = json.load(open(repairs_path, encoding="utf-8"))
    corrections = repairs.get("corrections", {})
    ok = repairs.get("ok", {})
    to_formula = repairs.get("to_formula", {})

    applied = 0
    reviewed = 0
    converted = 0
    log = []

    for pstr, page_info in manifest.get("pages", {}).items():
        pno = int(pstr)
        pf = os.path.join(extract_dir, f"page_{pno:03d}.json")
        if not os.path.isfile(pf):
            continue
        data = json.load(open(pf, encoding="utf-8"))
        texts = data.get("text", [])
        formulas = data.get("formulas", [])
        changed = False

        corr = corrections.get(pstr, {})
        ok_set = set(ok.get(pstr, []))
        tf_map = to_formula.get(pstr, {})
        to_delete = []  # 本页待删除的 text 索引（整行转成单个公式，无文本段）
        text_replacements = {}  # idx -> [新 text 段 dict]，整行拆成多段时替代原项

        for e in page_info.get("entries", []):
            key = e["key"]
            kind = e["type"]
            idx = e["index"]
            if key in corr:
                new_val = corr[key]
                if kind == "text" and idx < len(texts):
                    entry = texts[idx]
                    if entry.get("text") != new_val:
                        entry["text_ocr"] = entry.get("text")
                        entry["text"] = new_val
                        entry["mm_repaired"] = True
                        applied += 1
                        log.append(f"  page {pno:03d} {key}: text repaired "
                                   f"(was {len(entry['text_ocr'])} chars)")
                        changed = True
                elif kind == "formula" and idx < len(formulas):
                    entry = formulas[idx]
                    if entry.get("latex") != new_val:
                        entry["latex_ocr"] = entry.get("latex")
                        entry["latex"] = new_val
                        entry["mm_repaired"] = True
                        applied += 1
                        log.append(f"  page {pno:03d} {key}: latex repaired")
                        changed = True
                e["resolved"] = True
            elif key in ok_set:
                if kind == "text" and idx < len(texts):
                    texts[idx]["mm_reviewed"] = True
                elif kind == "formula" and idx < len(formulas):
                    formulas[idx]["mm_reviewed"] = True
                reviewed += 1
                e["resolved"] = True
                changed = True
            elif kind == "text" and key in tf_map and idx < len(texts):
                # 被误判为文本的整行（或整行中的一段）→ 拆成 formulas[]/text[] 新段。
                # to_formula 值可以是：
                #   - 字符串：整行即一个公式（旧行为）；
                #   - 分段列表：一行其实是「文本+公式+文本+…」交错，需保留行内顺序。
                entry = texts[idx]
                val = tf_map[key]
                line_bbox = poly_to_bbox(entry.get("poly"))
                if isinstance(val, str):
                    segs = [{"type": "formula", "latex": val}]
                elif isinstance(val, list):
                    segs = val
                else:
                    segs = []

                def _seg_weight(s):
                    if s.get("type") == "formula":
                        b = s.get("bbox")
                        if b and len(b) == 4:
                            return max(1, b[2] - b[0])
                        return max(1, len(s.get("latex", "")) * 6)
                    return max(1, len(s.get("text", "")))

                weights = [_seg_weight(s) for s in segs]
                total = sum(weights) or 1
                x0, y0, x1, y1 = (list(line_bbox) + [0, 0, 0, 0])[:4]
                cursor = x0
                repl_text_segs = []
                for s, w in zip(segs, weights):
                    seg_w = (x1 - x0) * w / total
                    seg_x0, seg_x1 = cursor, cursor + seg_w
                    cursor = seg_x1
                    if s.get("type") == "formula":
                        b = s.get("bbox")
                        if not (b and len(b) == 4):
                            b = [seg_x0, y0, seg_x1, y1]
                        new_f = {
                            "bbox": b,
                            "conf": None,
                            "latex": s.get("latex", ""),
                            "mm_converted": True,
                        }
                        insert_formula_by_position(formulas, new_f)
                        converted += 1
                        log.append(f"  page {pno:03d} {key}: segment formula "
                                   f"(latex {len(new_f['latex'])} chars, bbox {b})")
                    else:
                        sub_poly = [seg_x0, y0, seg_x1, y0, seg_x1, y1, seg_x0, y1]
                        repl_text_segs.append({
                            "poly": sub_poly,
                            "text": s.get("text", ""),
                            "score": entry.get("score", 0),
                            "mm_converted": True,
                        })
                        log.append(f"  page {pno:03d} {key}: segment text "
                                   f"({len(s.get('text', ''))} chars)")
                # 原 text 项：要么整体删除（无文本段），要么被文本段替代
                if repl_text_segs:
                    text_replacements[idx] = repl_text_segs
                else:
                    to_delete.append(idx)
                changed = True
                e["resolved"] = True

        # 循环外用统一重建 text[]：先跳过被整体转换的项，再把拆分出的文本段按序
        # 放回原位置。单趟重建避免删除/插入导致的索引错位。
        if to_delete or text_replacements:
            new_texts = []
            for i, t in enumerate(texts):
                if i in to_delete:
                    continue
                if i in text_replacements:
                    new_texts.extend(text_replacements[i])
                    continue
                new_texts.append(t)
            data["text"] = new_texts
            texts = data["text"]

        if changed and not dry:
            json.dump(data, open(pf, "w", encoding="utf-8"), ensure_ascii=False)

    manifest["status"] = "applied"
    manifest["applied"] = applied
    manifest["reviewed"] = reviewed
    manifest["converted"] = converted
    if not dry:
        json.dump(manifest, open(manifest_path, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2)

    for line in log:
        print(line)
    print(f"MM_APPLY DONE: {applied} repaired, {reviewed} confirmed-ok, "
          f"{converted} converted-to-formula"
          + (" (DRY RUN, no files changed)" if dry else ""))
    return 0


def main():
    ap = argparse.ArgumentParser(description="Apply multimodal repairs to page_*.json")
    ap.add_argument("extract_dir")
    ap.add_argument("--dry", action="store_true", help="preview only, no writes")
    ap.add_argument("--repairs", default=None, help="path to repairs.json (default: <mm_dir>/repairs.json)")
    args = ap.parse_args()
    sys.exit(apply(args.extract_dir, dry=args.dry, repairs_path=args.repairs))


if __name__ == "__main__":
    main()
