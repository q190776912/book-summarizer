#!/usr/bin/env python3
"""mm_repair_text_compare.py — 非多模态场景下的「文本层补偿」(Mode B)。

当运行模型**不支持看图**且书籍为**文本类（非扫码/扫描版，PDF 含可选中数字
文本层）**时，用本脚本替代 Agent 视觉审读：从 PDF 抽取对应区域的干净数字文本，
与 page_*.json 中低置信的 OCR 文本条目比对，自动产出 repairs.json（文本修正 /
确认），随后复用 mm_repair_apply.py 写回。

核心思路：
  - 文本类 PDF 的「数字文本层」通常比 OCR 可靠；但部分书（尤其公式密集的数学
    教材）的 CMap 损坏，公式区会吐出 𝐸ሾ𝑋ሿ / ଵ / ቆ 这类 tofu 乱码，此时文本层
    反而不如 OCR 读视觉字形可靠。故本脚本用**白名单**严格校验数字文本，凡含
    数学字母符号块 / PUA / 生僻文字的一律判不可信 → 保守保留 OCR。
  - 对每个被 audit 标出的低置信 text 条目，按其 poly 在 PDF 坐标里裁出同一区域，
    用「词中心落在 (y,x) 带内」取干净文字（不用 clip 相交，避免行距极窄时吞邻行）；
  - 比对：数字文本干净且与 OCR 不同 → 以数字文本修正（corrections）；
           数字文本与 OCR 一致 / 为空 → 确认 OCR 可用（ok）；
           数字文本含白名单外字符（乱码）/ 与 OCR 差异过大 → 「不可信」：
             · 非混合模式（默认）：保守保留 OCR，记 ok（因无后续视觉补偿可用）；
             · 混合模式（--hybrid，后续将跑模式 A）：**保持未解决**，留给模式 A
               由 agent 视觉读取真实印刷页来修正（数字文本层在此区域不可信，
               但视觉模型看像素比 OCR 更准）。
  - 公式条目无文本层可取 → **保持未解决**并标记 text_mode_skipped，不在本模式
    补偿；后续若有视觉能力则交模式 A，否则 summary 阶段按规则 G（理解后重写）处理。

  ⚠️ 本模式与模式 A 的分工（混合策略）：
     文本类书先跑模式 B → 把「文本层干净的文字」修准/确认（标 resolved），
     剩下的（公式 + 文本层不可信的文字）保持未解决；随后若模型支持看图，
     **重跑 audit** 会重新标出这些残留条目（已修文字因 page JSON 标记被跳过），
     由模式 A（agent 视觉）处理。故本脚本**绝不**把公式/不可信文字标成 resolved，
     以免卡住后续 audit 的重新标出。

前置：先跑 mm_repair_audit.py 生成 manifest.json（本脚本读它的 flagged 列表）。

用法:
    python mm_repair_text_compare.py <pdf_path> <extract_dir>
        [--src-dpi 200] [--expand-pt 2.0] [--force-text] [--force-scan] [--hybrid]

    --src-dpi    : 与 audit 一致（默认 200），用于把 poly 像素坐标换算成 PDF 点。
    --expand-pt  : 区域外扩点数，确保边缘字符不漏（默认 2.0 pt）。
    --force-text : 强制按文本类处理（跳过自动探测）。
    --force-scan : 强制按扫描版处理 → 直接退出，不补偿（等价 MM_UNAVAILABLE）。
    --hybrid     : 混合模式——不可信文字与公式保持未解决，留给后续模式 A（agent
                   视觉）处理；省略则当纯模式 B，把不可信文字记 ok（信任 OCR）。
"""
import sys, os, json, glob, re, argparse, difflib
sys.stdout.reconfigure(encoding="utf-8")

import fitz

REPAIR_DIRNAME = "_mm_repair"


def poly_to_rect(poly, src_dpi):
    """把 page_*.json 的 poly（src-dpi 像素，8 值扁平或 [[x,y],...]）转 fitz.Rect（PDF 点）。"""
    if not poly:
        return None
    if isinstance(poly[0], (list, tuple)):
        pts = poly
    else:
        pts = [[poly[i], poly[i + 1]] for i in range(0, len(poly) - 1, 2)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    k = 72.0 / src_dpi  # 像素 → PDF 点
    return fitz.Rect(min(xs) * k, min(ys) * k, max(xs) * k, max(ys) * k)


def extract_region_text(page, y_band, x_band):
    """按**词中心**落在 poly 的 (y,x) 带内取文字，按阅读顺序拼接。

    关键：用词中心判定而非 bbox 相交（clip）。Koopman 等书行距极窄（<1pt），
    bbox 相交会把上一/下一行的词也吞进来；词中心则稳稳只取本行。
    y_band / x_band 单位均为 PDF 点，已含少量容差。
    """
    try:
        words = page.get_text("words")
    except Exception:
        words = []
    if not words:
        return ""
    sel = []
    for w in words:
        cx = (w[0] + w[2]) / 2.0
        cy = (w[1] + w[3]) / 2.0
        if y_band[0] <= cy <= y_band[1] and x_band[0] <= cx <= x_band[1]:
            sel.append(w)
    # 按词**中心** y（取整，同一行 y 一致；行距 ~12pt 不会误并）排序，冲突时按
    # x —— 取整可消除连字/上标包围盒亚点抖动（如 ﬁ 连字中心 63.8 vs 64.0）。
    sel.sort(key=lambda w: (round((w[1] + w[3]) / 2.0), w[0]))
    return " ".join(w[4] for w in sel).strip()


def norm(s):
    return re.sub(r"\s+", " ", (s or "").strip())


_PUNCT = set(".,;:!?()[]{}'\"\\-+/=<>%&*@#$^~|·•—–…“”‘’…‹›«»")

# 白名单：正常「数字文本层」里会出现的字符范围。落在该范围外的字符（尤其
# 数学字母符号块 U+1D400–U+1D7FF、PUA、印度/僧伽罗/埃塞俄比亚等生僻文字块）
# 是损坏 CMap 的 tofu 特征，绝不可能是正常文本——一旦出现即判定整段不可信。
_OK_RANGES = (
    (0x20,   0x7E),    # Basic Latin + ASCII 标点
    (0xA0,   0xFF),    # Latin-1 Supplement (ö é ñ ß × ÷ ² ³)
    (0x100,  0x24F),   # Latin Extended-A/B + IPA
    (0x2070, 0x209F),  # 上/下标数字字母
    (0x370,  0x3FF),   # Greek and Coptic（普通希腊字母 α β γ）
    (0x2000, 0x206F),  # General Punctuation（— – ‘ ’ “ ” … ·）
    (0x2100, 0x214F),  # Letterlike Symbols（ℕ ℤ ℝ ℂ ℚ）
    (0x2190, 0x21FF),  # Arrows
    (0x2200, 0x22FF),  # Mathematical Operators（∀ ∂ ∇ ∈ ∉ ∑ ∫ ≤ ≥）
    (0x2300, 0x23FF),  # Misc Technical
    (0x2A00, 0x2AFF),  # Supplementary Math Operators
    (0x3000, 0x303F),  # CJK Punctuation
    (0x3400, 0x4DBF),  # CJK Ext A
    (0x4E00, 0x9FFF),  # CJK Unified
    (0xF900, 0xFAFF),  # CJK Compatibility
    (0xFF00, 0xFFEF),  # Fullwidth forms
)

def _is_ok_char(cp):
    return any(lo <= cp <= hi for lo, hi in _OK_RANGES)

def is_clean(s):
    """数字文本层是否可信（白名单制）。

    采用**白名单**而非「字符占比」：只要出现一个白名单之外的字符（数学字母
    符号块 𝐸𝑋𝑛、PUA、印度/埃塞俄比亚/僧伽罗等生僻文字），即说明该区域文本层
    损坏（tofu），整段不可信 → 返回 False，让 decide 保守保留 OCR。

    这能拦掉诸如 Ross《A First Course in Probability》这类「正文干净、但公式区
    CMap 错乱」的书——其数字文本层在公式处会吐出 𝐸ሾ𝑋ሿൌ / ଵ / ቆ 等乱码，而 OCR
    反而读对了视觉字形。正常学术文本（ö é ñ ß、ﬁ 连字、—、•、≤ ≥ ∑ ∫、CJK）
    全部落在白名单内，不受影响。
    """
    s = s or ""
    if not s or "\ufffd" in s:
        return False
    for ch in s:
        if not _is_ok_char(ord(ch)):
            return False
    # 不能全是空白/标点（无实际内容）
    return any(not ch.isspace() for ch in s)


def decide(ocr, digital):
    """返回 (action, corrected, reason)。

    action/reason 取值：
      ("fix",    corrected, "fix")      数字文本干净且与 OCR 不同 → 以数字文本修正
      ("keep",   None,       "agree")   数字文本与 OCR 一致 → OCR 实际可用
      ("keep",   None,       "empty")   区域无文本层 → 无法补偿
      ("keep",   None,       "untrusted") 数字文本乱码/差异过大 → 不可信（由调用方
                                          按 hybrid 决定记 ok 还是留给模式 A）
    """
    o = norm(ocr)
    d = norm(digital)
    if not d:
        return ("keep", None, "empty")   # 区域无文本层 → 无法补偿，保留 OCR
    if o == d:
        return ("keep", None, "agree")   # 数字文本与 OCR 一致 → OCR 实际可用
    if not is_clean(d):
        return ("keep", None, "untrusted")  # 数字文本乱码 → 不可信
    # 长度差异过大（大概率是误吞相邻行/列） → 保守保留 OCR
    if len(o) > 3 and len(d) > len(o) * 2.0:
        return ("keep", None, "untrusted")
    # 与 OCR 差异过大（字符级相似度太低）→ 不可信，保守保留 OCR
    if len(o) >= 4:
        ratio = difflib.SequenceMatcher(None, o, d).ratio()
        if ratio < 0.45:
            return ("keep", None, "untrusted")
    return ("fix", d, "fix")             # 文本层干净且相近 → 以数字文本为准


def is_text_based(pdf_path, sample=6, min_avg_words=30):
    """自动探测：取样若干页，若平均每页可选中词数足够，判为文本类。"""
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return False
    n = min(sample, len(doc))
    if n == 0:
        doc.close()
        return False
    total = 0
    for i in range(n):
        try:
            total += len(doc[i].get_text("words"))
        except Exception:
            pass
    doc.close()
    avg = total / n
    return avg >= min_avg_words


def run(pdf_path, extract_dir, src_dpi, expand_pt, force_text=False, force_scan=False,
         hybrid=False):
    mm_dir = os.path.join(extract_dir, REPAIR_DIRNAME)
    manifest_path = os.path.join(mm_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        print("MM_TEXTCMP: no manifest.json — run mm_repair_audit.py first")
        return 1

    if force_scan:
        print("MM_TEXTCMP: --force-scan → 视为扫描版，跳过文本补偿（MM_UNAVAILABLE）。")
        return 0
    if not force_text and not is_text_based(pdf_path):
        print("MM_TEXTCMP: 自动探测判定为扫描/无文本层版本 → 跳过（MM_UNAVAILABLE）。"
              " 若确为文本类请用 --force-text。")
        return 0

    manifest = json.load(open(manifest_path, encoding="utf-8"))
    doc = fitz.open(pdf_path)

    repairs = {"corrections": {}, "ok": {}, "to_formula": {}, "deferred": {}}
    stats = {"fixed": 0, "kept": 0, "skipped_formula": 0, "deferred": 0}

    for pstr, page_info in manifest.get("pages", {}).items():
        pno = int(pstr)
        if pno - 1 >= len(doc):
            continue
        page = doc[pno - 1]
        pf = os.path.join(extract_dir, f"page_{pno:03d}.json")
        page_data = json.load(open(pf, encoding="utf-8")) if os.path.isfile(pf) else {}
        texts = page_data.get("text", [])

        corr = {}
        ok = []
        deferred = []
        for e in page_info.get("entries", []):
            if e.get("resolved"):
                continue
            key = e["key"]
            kind = e["type"]
            idx = e["index"]
            if kind == "formula":
                # 公式无文本层 → 本模式不补偿，**保持未解决**（标 text_mode_skipped
                # 仅作信息），以便后续重跑 audit 重新标出交给模式 A / 规则 G。
                e["text_mode_skipped"] = True
                stats["skipped_formula"] += 1
                continue
            if kind != "text" or idx >= len(texts):
                continue
            t = texts[idx]
            poly = t.get("poly")
            rect = poly_to_rect(poly, src_dpi)
            if rect is None:
                e["text_mode_skipped"] = True
                stats["skipped_formula"] += 1
                continue
            # 用词中心过滤（见 extract_region_text）：纵向容差收紧避免吞相邻行，
            # 横向留小容差避免 OCR poly 偏紧漏字。
            y0 = rect.y0 - 1.5
            y1 = rect.y1 + 1.5
            x0 = rect.x0 - (2.0 + expand_pt)
            x1 = rect.x1 + (2.0 + expand_pt)
            digital = extract_region_text(page, (y0, y1), (x0, x1))
            action, corrected, reason = decide(t.get("text", ""), digital)
            if action == "fix":
                corr[key] = corrected
                e["resolved"] = True
                stats["fixed"] += 1
                print(f"  page {pno:03d} {key}: FIX  OCR={t.get('text','')!r} "
                      f"→ DIGITAL={corrected!r}")
            elif reason in ("agree", "empty"):
                # 数字文本与 OCR 一致 / 区域无文本层 → 确认 OCR 可用，标 resolved
                ok.append(key)
                e["resolved"] = True
                stats["kept"] += 1
                print(f"  page {pno:03d} {key}: KEEP({reason}) OCR={t.get('text','')!r}")
            else:  # reason == "untrusted"：数字文本层在此区域不可信（tofu）
                if hybrid:
                    # 混合模式：保持未解决，留给模式 A（agent 视觉读真实印刷页）
                    e["text_deferred"] = True
                    deferred.append(key)
                    stats["deferred"] += 1
                    print(f"  page {pno:03d} {key}: DEFER(untrusted) → 留给模式 A "
                          f"OCR={t.get('text','')!r}")
                else:
                    # 纯模式 B（无后续视觉补偿）：保守信任 OCR，记 ok
                    ok.append(key)
                    e["resolved"] = True
                    stats["kept"] += 1
                    print(f"  page {pno:03d} {key}: KEEP(untrusted) 信任 OCR="
                          f"{t.get('text','')!r}")
        if corr:
            repairs["corrections"][pstr] = corr
        if ok:
            repairs["ok"][pstr] = ok
        if deferred:
            repairs["deferred"][pstr] = deferred

    doc.close()

    repairs_path = os.path.join(mm_dir, "repairs.json")
    json.dump(repairs, open(repairs_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    manifest["status"] = "text_compared"
    manifest["text_mode"] = True
    manifest["hybrid"] = hybrid
    json.dump(manifest, open(manifest_path, "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)

    mode_tag = " (hybrid: 不可信文字/公式留给模式 A)" if hybrid else ""
    print(f"MM_TEXTCMP DONE{mode_tag}: {stats['fixed']} text fixed, {stats['kept']} kept, "
          f"{stats['skipped_formula']} formula skipped, {stats['deferred']} deferred → {repairs_path}")
    if hybrid and (stats["skipped_formula"] or stats["deferred"]):
        print("  Next: 重跑 mm_repair_audit.py（已修文字因 page JSON 标记被跳过，"
              "公式/不可信文字会重新标出）→ 模式 A（agent 视觉）处理 → mm_repair_apply.py")
    else:
        print("  Next: run mm_repair_apply.py <extract_dir> to write corrections back.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Text-layer compensation for low-conf OCR (non-multimodal)")
    ap.add_argument("pdf_path")
    ap.add_argument("extract_dir")
    ap.add_argument("--src-dpi", type=int, default=200,
                    help="与 mm_repair_audit.py 一致（默认 200）")
    ap.add_argument("--expand-pt", type=float, default=2.0,
                    help="区域外扩点数，避免边缘字符漏取（默认 2.0）")
    ap.add_argument("--force-text", action="store_true",
                    help="强制按文本类处理，跳过自动探测")
    ap.add_argument("--force-scan", action="store_true",
                    help="强制按扫描版处理，直接跳过（MM_UNAVAILABLE）")
    ap.add_argument("--hybrid", action="store_true",
                    help="混合模式——不可信文字与公式保持未解决，留给后续模式 A "
                         "（agent 视觉）处理；省略则当纯模式 B，把不可信文字记 ok")
    args = ap.parse_args()

    if not os.path.isfile(args.pdf_path):
        print(f"ERROR: PDF not found: {args.pdf_path}")
        sys.exit(1)
    sys.exit(run(args.pdf_path, args.extract_dir, args.src_dpi,
                 args.expand_pt, args.force_text, args.force_scan, args.hybrid))


if __name__ == "__main__":
    main()
