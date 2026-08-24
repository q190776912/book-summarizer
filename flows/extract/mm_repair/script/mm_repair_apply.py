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
  "to_structured": {
     "001": { "text:9": "x^2 + y^2 = r^2" },   // 字符串：整行即一个公式
     "002": { "text:3": [                        // 分段列表：一行拆成 文本+公式+文本
               {"type":"text","text":"("},
               {"type":"formula","latex":"k = 0,1,\\dots,n"},
               {"type":"text","text":")"} ] },
     ...
  },
  "unavailable": {                        // 经多轮视觉审读仍不可恢复（纯 OCR 噪声 / 严重乱码）
     "091": ["text:23", "formula:4"],     // 形态同 ok：按页归集的条目键列表
     ...
  }
}

对 corrections: 把 text[].text / formulas[].latex 改为正确值，
  设 mm_repaired=true，原值存入 text_ocr / latex_ocr。
对 ok: 设 mm_reviewed=true（值不变，避免下一轮重复送审）。
对 unavailable: 条目经多轮视觉审读仍不可恢复（纯 OCR 噪声 / 严重乱码）→ 设 per-entry
  mm_unavailable=true + 页级 data["MM_UNAVAILABLE"]=true + manifest 该条目 resolved=true
  （闸门放行）。下游 dump_chapter_ocr.py 会跳过 mm_unavailable 条目，不污染内容。
  🔴 不可恢复必须诚实标 unavailable，绝不强行编造修正值。
对 to_structured: 把被 OCR 误判为文本的整行（或整行中的一段）公式，转成 formulas[]
  的新 item，设 mm_converted=true；随后**删除原 text 项**（不保留低置信原 OCR
  文本，不存 text_ocr）。

  to_structured 的值支持两种形态：
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

  反向（公式→文本）：若 MFD 把一条纯文本误判为公式，agent 在 to_structured 里
  对该 formula:<i> 写同样的两种形态；apply 会把公式项从 formulas[] 移除、按
  (y,x) 插回对应 text[] 项（设 mm_converted=true），从而把误判公式还原为文本。
  分段列表中若同时含 formula 段，则文本段转回 text[]、公式段保留为原公式项的 latex。
回写 page_NNN.json，并更新 manifest 中对应条目的 resolved=true。

用法:
    python mm_repair_apply.py <extract_dir> [--dry]
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
import repairs
import mm_repair_manifest
from page_json import PageJson

import sys, os, json, argparse, glob, time
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


def bbox_to_poly(bbox):
    """把 [x0,y0,x1,y1] 包围盒转成 OCR 的 poly（4 角点扁平 [x0,y0,x1,y0,x1,y1,x0,y1]）。"""
    if not bbox or len(bbox) < 4:
        return [0, 0, 0, 0, 0, 0, 0, 0]
    x0, y0, x1, y1 = bbox[0], bbox[1], bbox[2], bbox[3]
    return [x0, y0, x1, y0, x1, y1, x0, y1]


def insert_text_by_position(texts, new_t):
    """把新 text 按 (y, x) 顺序插入 text[]，保证阅读顺序（与 insert_formula_by_position 对称）。"""
    b = poly_to_bbox(new_t.get("poly")) if new_t.get("poly") else [0, 0, 0, 0]
    y, x = b[1], b[0]
    lo, hi = 0, len(texts)
    while lo < hi:
        mid = (lo + hi) // 2
        mb = poly_to_bbox(texts[mid].get("poly")) if texts[mid].get("poly") else [0, 0, 0, 0]
        my, mx = mb[1], mb[0]
        if (my, mx) < (y, x):
            lo = mid + 1
        else:
            hi = mid
    texts.insert(lo, new_t)


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

    manifest = mm_repair_manifest.MmRepairManifest.load(manifest_path).data
    rep = repairs.Repairs.load(repairs_path).to_dict()
    # 归一化 part 文件的页码键为零填充 3 位（"71" -> "071"），与 manifest 键一致，
    # 否则 <100 页的 corrections/ok/to_structured 会因键不匹配被静默丢弃（Bug 2026-08-17）。
    _norm = lambda d: {f"{int(p):03d}": v for p, v in (d or {}).items()}
    corrections = _norm(rep.get("corrections"))
    ok = _norm(rep.get("ok"))
    to_structured = _norm(rep.get("to_structured"))
    unavailable = _norm(rep.get("unavailable"))

    applied = 0
    reviewed = 0
    converted = 0
    converted_text = 0
    log = []

    for pstr, page_info in manifest.get("pages", {}).items():
        pno = int(pstr)
        pf = os.path.join(extract_dir, f"page_{pno:03d}.json")
        if not os.path.isfile(pf):
            continue
        data = PageJson.load(pf).data
        texts = data.get("text", [])
        formulas = data.get("formulas", [])
        changed = False

        corr = corrections.get(pstr, {})
        ok_set = set(ok.get(pstr, []))
        tf_map = to_structured.get(pstr, {})
        unavail_set = set(unavailable.get(pstr, []))
        to_delete = []  # 本页待删除的 text 索引（整行转成单个公式，无文本段）
        text_replacements = {}  # idx -> [新 text 段 dict]，整行拆成多段时替代原项
        to_delete_formula = []  # 本页待删除的 formula 索引（整条误判、实际是纯文本）
        text_insertions = []  # 公式→文本 转换产生的新 text 项（按阅读顺序插回）
        formula_insertions = []  # text→公式 转换产生的新 formula 项（按 (y,x) 插入，loop 外统一落盘）

        for e in page_info.get("entries", []):
            # 幂等护栏：manifest 已 resolved 的条目（含 to_structured 插入/删除后的索引偏移）
            # 一律跳过，杜绝重跑时把相邻元素当原条目二次转换/写错位置。
            if e.get("resolved"):
                continue
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
                    e["resolved"] = True
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
                else:
                    # 🔴 索引越界（repairs.json 相对已写回的 page_*.json 过期，
                    # 常见于 to_structured 删除/替换后的索引漂移）：绝不置
                    # resolved —— 否则修复被静默丢弃还贡献「假绿」完成标记。
                    # 保持未解析，让 _all_resolved 门如实拦截并提示重审。
                    log.append(f"  page {pno:03d} {key}: SKIP ({kind}[{idx}] 越界，"
                               f"repairs.json 疑似过期——请重跑 audit 后再 apply)")
            elif key in ok_set:
                if kind == "text" and idx < len(texts):
                    texts[idx]["mm_reviewed"] = True
                    e["resolved"] = True
                elif kind == "formula" and idx < len(formulas):
                    formulas[idx]["mm_reviewed"] = True
                    e["resolved"] = True
                else:
                    log.append(f"  page {pno:03d} {key}: SKIP ({kind}[{idx}] 越界，"
                               f"repairs.json 疑似过期——请重跑 audit 后再 apply)")
                reviewed += 1
                changed = True
            elif kind == "text" and key in tf_map and idx < len(texts):
                # 被误判为文本的整行（或整行中的一段）→ 拆成 formulas[]/text[] 新段。
                # to_structured 值可以是：
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
                        # 关键：仅【收集】，loop 外统一插入。杜绝 loop 内即时 insert 导致
                        # 同页后续 formula corrections 的 formulas[idx] 索引漂移（Bug B index-drift）。
                        formula_insertions.append(new_f)
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

            elif kind == "formula" and key in tf_map and idx < len(formulas):
                # 被 MFD 误判为公式的整条（或整条中的一段）实际是文本 → 转回 text[]。
                # to_structured 值语义与 text 方向对称：
                #   - 字符串：整条公式实际就是一个文本串；
                #   - 分段列表：公式内「文本 + 公式 + …」交错，文本段转回 text[]，
                #     公式段留在 formulas[]（合并为原公式项的 latex）。
                entry = formulas[idx]
                val = tf_map[key]
                fbbox = entry.get("bbox") or [0, 0, 0, 0]
                if isinstance(val, str):
                    segs = [{"type": "text", "text": val}]
                elif isinstance(val, list):
                    segs = val
                else:
                    segs = []
                text_segs = [s for s in segs if s.get("type") == "text"]
                formula_segs = [s for s in segs if s.get("type") == "formula"]
                if text_segs:
                    for s in text_segs:
                        text_insertions.append({
                            "poly": bbox_to_poly(fbbox),
                            "text": s.get("text", ""),
                            "score": entry.get("conf") if isinstance(entry.get("conf"), (int, float)) else 0,
                            "mm_converted": True,
                        })
                        converted_text += 1
                        log.append(f"  page {pno:03d} {key}: formula→text "
                                   f"({len(s.get('text', ''))} chars)")
                if formula_segs:
                    merged_latex = " ".join(s.get("latex", "") for s in formula_segs)
                    entry["latex_ocr"] = entry.get("latex")
                    entry["latex"] = merged_latex
                    entry["mm_repaired"] = True
                    applied += 1
                    log.append(f"  page {pno:03d} {key}: formula kept, latex updated "
                               f"({len(merged_latex)} chars)")
                    changed = True
                else:
                    to_delete_formula.append(idx)
                    changed = True
                e["resolved"] = True

            elif key in unavail_set:
                # 条目经多轮视觉审读仍不可恢复（纯 OCR 噪声 / 严重乱码碎片）。
                # reviewed-but-unrecoverable：resolved=True（闸门放行），
                # 并标 mm_unavailable 让下游 write-source/verify 跳过、不污染内容。
                if kind == "text" and idx < len(texts):
                    texts[idx]["mm_unavailable"] = True
                    e["resolved"] = True
                    e["mm_unavailable"] = True
                    data["MM_UNAVAILABLE"] = True
                    changed = True
                elif kind == "formula" and idx < len(formulas):
                    formulas[idx]["mm_unavailable"] = True
                    e["resolved"] = True
                    e["mm_unavailable"] = True
                    data["MM_UNAVAILABLE"] = True
                    changed = True
                else:
                    # 越界：与 corr/ok 分支同规——不置 resolved，如实拦截。
                    log.append(f"  page {pno:03d} {key}: SKIP ({kind}[{idx}] 越界，"
                               f"repairs.json 疑似过期——请重跑 audit 后再 apply)")

        # 循环外用统一重建 text[]/formulas[]：先跳过被整体转换的项，再把拆分出的
        # 段按阅读顺序放回。单趟重建避免删除/插入导致的索引错位。
        if to_delete or text_replacements or text_insertions:
            new_texts = []
            for i, t in enumerate(texts):
                if i in to_delete:
                    continue
                if i in text_replacements:
                    new_texts.extend(text_replacements[i])
                    continue
                new_texts.append(t)
            for nt in sorted(text_insertions,
                             key=lambda t: (poly_to_bbox(t.get("poly"))[1],
                                            poly_to_bbox(t.get("poly"))[0])):
                insert_text_by_position(new_texts, nt)
            data["text"] = new_texts
            texts = data["text"]
        if formula_insertions or to_delete_formula:
            # 先按【原始】索引删公式 → 再按 (y,x) 位置插新公式（顺序关键，否则索引错位）。
            # 删除用原始索引（在插入前计算），插入用 bbox 绝对位置，与删除互不干扰，
            # 保证最终阅读顺序与「插入后删除」等价（根除 Bug B）。
            new_formulas = [f for i, f in enumerate(formulas)
                            if i not in to_delete_formula]
            for nf in formula_insertions:
                insert_formula_by_position(new_formulas, nf)
            data["formulas"] = new_formulas
            formulas = data["formulas"]

        if changed and not dry:
            PageJson(data=data).dump(pf)

    # 仅当 manifest 所有条目均已 resolved 才标 applied；否则标 partial，杜绝假绿
    _all_resolved = all(
        e.get("resolved")
        for _p in manifest.get("pages", {}).values()
        for e in _p.get("entries", [])
    )
    manifest["status"] = "applied" if _all_resolved else "partial"
    manifest["applied"] = applied
    manifest["reviewed"] = reviewed
    manifest["converted"] = converted
    manifest["converted_text"] = converted_text
    if not dry:
        mm_repair_manifest.MmRepairManifest(data=manifest).dump(manifest_path)

    for line in log:
        print(line)
    print(f"MM_APPLY DONE: {applied} repaired, {reviewed} confirmed-ok, "
          f"{converted} text→formula, {converted_text} formula→text"
          + (" (DRY RUN, no files changed)" if dry else ""))
    return 0


def _maybe_write_extraction_done(extract_dir):
    """仅在 MM Repair 真完成时写出 _extraction_done.json。

    真完成 = manifest 全部条目 resolved 且每页 page_*.json 至少含一个
    mm_repaired/mm_reviewed/mm_converted 标记（或整页 MM_UNAVAILABLE）。
    任一不满足则告警且不写，杜绝「手 touch 假绿 / apply 已跑但大量未修」被当作完成。
    """
    mpath = os.path.join(extract_dir, "_mm_repair", "manifest.json")
    if not os.path.exists(mpath):
        print("[mm_repair_apply] 无 manifest，跳过 _extraction_done.json 写入。")
        return
    try:
        m = json.load(open(mpath, encoding="utf-8"))
    except Exception as e:
        print(f"[mm_repair_apply] manifest 读取失败: {e}")
        return
    entries = [e for pg in m.get("pages", {}).values() for e in pg.get("entries", [])]
    total = len(entries)
    resolved = sum(1 for e in entries if e.get("resolved"))
    if total and resolved < total:
        print(f"[mm_repair_apply] ⚠️ MM Repair 未真完成（manifest {resolved}/{total} resolved），"
              f"不写 _extraction_done.json（避免假绿）。请继续模式 A 视觉审读后重跑 apply。")
        return
    # 每页标记核对：只对 manifest 中实际出现过条目（被 flag）的页面要求 mm 标记。
    # 未被 flag 的页面没有任何待修条目，自然不需要 mm 标记。
    # manifest entries carry NO "page" field — the page number is the KEY of
    # m["pages"] (e.g. "003"). Derive the flagged-page set from those keys;
    # building it from e.get("page", 0) yields {0} and silently skips every
    # real page file, so the per-page marker check below becomes dead code and
    # a false-green slips through. Bug found 2026-08-20 (数学物理方程 pure-scan).
    manifest_pages = set(int(k) for k in m.get("pages", {}).keys())
    pages = glob.glob(os.path.join(extract_dir, "page_*.json"))
    for pf in pages:
        try:
            data = json.load(open(pf, encoding="utf-8"))
        except Exception:
            print(f"[mm_repair_apply] 页 {os.path.basename(pf)} 读取失败，不写 marker。")
            return
        pno = data.get("page", 0)
        if pno not in manifest_pages:
            continue
        texts = data.get("text", []) + data.get("formulas", [])
        ok = any(isinstance(t, dict) and (t.get("mm_repaired") or t.get("mm_reviewed")
                                          or t.get("mm_converted")) for t in texts)
        if not ok and not data.get("MM_UNAVAILABLE"):
            print(f"[mm_repair_apply] ⚠️ 页 {os.path.basename(pf)} 仍无 mm 标记，"
                  f"MM Repair 未真完成，不写 _extraction_done.json。")
            return
    marker = os.path.join(extract_dir, "_extraction_done.json")
    if os.path.exists(marker):
        return
    json.dump({
        "generated_by": "mm_repair_apply.py",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "resolved": resolved,
        "total": total,
    }, open(marker, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"[mm_repair_apply] ✅ MM Repair 真完成，已写出 _extraction_done.json"
          f" ({resolved}/{total} resolved)。")


def main():
    ap = argparse.ArgumentParser(description="Apply multimodal repairs to page_*.json")
    ap.add_argument("extract_dir")
    ap.add_argument("--dry", action="store_true", help="preview only, no writes")
    ap.add_argument("--repairs", default=None, help="path to repairs.json (default: <mm_dir>/repairs.json)")
    args = ap.parse_args()
    rc = apply(args.extract_dir, dry=args.dry, repairs_path=args.repairs)
    # 非 dry 且 apply 成功 → 仅在真完成时写出 _extraction_done.json
    if not args.dry and rc == 0:
        _maybe_write_extraction_done(args.extract_dir)
    sys.exit(rc)


if __name__ == "__main__":
    main()
