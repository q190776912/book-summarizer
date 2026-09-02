#!/usr/bin/env python3
"""build_chapter_map.py — 一步从 OCR 生成正确的 chapter_map.json 页码。

设计动机（取代旧的"手写页码 → 再脚本校验"两步法）：
    章节映射的**结构真相**（章列表 + 干净 name/name_en + 附录标记）只能由人从
    目录页校订，OCR 给不出；但**页码**可以、也必须由证据（OCR 正文）算出，不该
    让人从 TOC 手抄印刷页号（易错、且是印刷页≠PDF 页的经典坑）。

本工具一次性完成"算页码"：
  1. 读 agent 校订的 chapter_map.json（ch / name / name_en / 可选粗略 start/end
     来自 TOC / appendix 标记）。
  2. scan_headings(page_*.json) → headings + title_lines。
  3. detect_starts(...) → 每章真实起点（Mode A "Chapter N" 标题匹配；Mode B 裸标题
     回退）。检测引擎（scan_headings / detect_starts / _ch_sort_key）已**内联于本
     文件**，无跨文件依赖——原独立 check_chapter_map.py 已废弃删除。
  4. start = 检测值（未检出则保留 agent 值，仍无则留空标 UNDTECTED）；
     end = 推断值（下一章起点-1；末章保留 agent 值或全书末页）。
  5. 写回 chapter_map.json（保留原 on-disk 形态 A/B 与所有附加字段）+ 生成
     chapter_map.build_report.md。
  6. 任一章 UNDTECTED → exit 1，强制 agent 干预。

🔴 **agent 判断环节**：生成的 chapter_map.build_report.md 就是给人看的。agent 读它、
确认 CORRECTED 值、对 UNDTECTED 章手动补 start/end 后重跑本工具。这就是"生成 +
判断"，不再有独立的校验脚本闸步。

Usage:
    python build_chapter_map.py <extract_dir> [--no-write] [--max-deviation N] [--verbose]
"""
import argparse
import glob
import json
import os
import re
import sys
from difflib import SequenceMatcher
from pathlib import Path

# ── skill bootstrap ─────────────────────────────────────────────────────────
for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from data.chapter_map.chapter_map import load_chapter_records, load_chapter_map_raw  # noqa: E402


# ═══════════════════════════════════════════════════════════════════════════
# 检测引擎（内联，原自 check_chapter_map.py；从 page_*.json 定位每章真实起点）
# ═══════════════════════════════════════════════════════════════════════════
_ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100}


def roman_to_int(s: str) -> int:
    total = 0
    prev = 0
    for ch in reversed(s.upper()):
        v = _ROMAN[ch]
        total += -v if v < prev else v
        prev = v
    return total


def parse_number(raw: str):
    """Return int page-label if ``raw`` is arabic or roman; else None."""
    if raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    if raw.isdigit():
        return int(raw)
    if re.fullmatch(r"[IVXLC]+", raw):
        try:
            return roman_to_int(raw)
        except KeyError:
            return None
    return None


def norm_title(s: str) -> str:
    if not s:
        return ""
    s = s.upper()
    return re.sub(r"[^A-Z0-9]", "", s)


def clean_title_for_sim(s: str) -> str:
    """Strip TOC dotted-leaders / trailing page numbers before normalising,
    so 'Metric Spaces . . . . . 16' collapses to 'METRICSPACES'."""
    if not s:
        return ""
    s = re.sub(r"[\.·•]+\s*\d*\s*$", "", s)   # trailing '.... 16'
    s = re.sub(r"\.\s*\.\s*\.", "", s)         # embedded '....' (spaced)
    s = re.sub(r"[\.·•]+", " ", s)             # any stray dots -> space
    return norm_title(s)


def is_toc_line(line: str) -> bool:
    """True for table-of-contents entries ('Chapter 1. Metric Spaces .... 16')."""
    if re.search(r"\.\s*\.\s*\.", line):
        return True
    if re.search(r"[\.·•]{3,}", line):
        return True
    if re.search(r"(chapter|chap)", line, re.I) and re.search(r"\.\s*\d+\s*$", line):
        return True
    return False


def title_similarity(a: str, b: str) -> float:
    """Raw normalised similarity of two cleaned title strings.

    No substring/prefix bonus: degraded OCR frequently embeds a chapter title
    *inside* a sentence (e.g. an Introduction summary "Chapter 9 discusses
    Hochschild and cyclic homology ..."), and a bonus would wrongly score such
    body text as a confident heading match.
    """
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _looks_like_label(s: str) -> bool:
    """True for tokens that are chapter-number labels rather than title words
    (e.g. OCR 'T'/'L'/'c', roman 'III', arabic '2', or a bare short token)."""
    a = re.sub(r"[^A-Za-z0-9]", "", s)
    if not a:
        return True
    if len(a) <= 2:
        return True
    if a.isdigit():
        return True
    if re.fullmatch(r"[IVXLC]+", a):
        return True
    return False


# ── OCR heading scan ─────────────────────────────────────────────────────────
CHAPTER_RE = re.compile(r"(?i)\b(chapter|chap|ch\.)\b\.?\s*([0-9]+|[IVXLC]+)?")
NUM_LINE_RE = re.compile(r"^\s*\d{1,4}\s*$")


def _line_text(item) -> str:
    if isinstance(item, dict):
        return item.get("text", "") or ""
    return str(item)


# Words that, when they immediately follow "Chapter N", mark the line as a
# body-text *mention* ("Chapter 9 discusses ...", "Chapter 7 concerns ...")
# rather than a real chapter heading. Articles ("the"/"a"/"an") are deliberately
# excluded so titles like "The Derived Category" are not mistaken for mentions.
BODY_MENTION_VERBS = {
    "discusses", "discuss", "covers", "cover", "concerns", "concern",
    "considers", "consider", "deals", "describes", "describe", "gives",
    "give", "shows", "show", "presents", "present", "see", "recall",
    "suppose", "let", "note", "here", "below", "above", "chapter",
    "section", "we", "you", "i", "he", "she", "they", "it", "our",
    "their", "its", "this", "these", "those", "in", "of", "from", "to",
    "by", "that", "which", "when", "if", "as", "for", "and", "but", "or",
    "such", "both", "each", "all", "some", "any", "no", "not", "can",
    "will", "would", "may", "might", "should", "must", "has", "have",
    "had", "be", "been", "do", "does", "did", "also", "then", "now",
    "first", "next", "later", "following", "using", "used", "via",
    "about", "into", "onto", "over", "under", "between", "is", "are",
    "was", "were", "more", "less", "many", "few", "new", "main", "basic",
    "general", "particular", "similar", "other", "another",
}


def scan_headings(pages_dir: str):
    """Scan all page_*.json and return ``(headings, title_lines)``.

    ``headings`` — "Chapter N" matches (Mode A). Each dict:
        {page, label_raw, label_norm, title_cands, toc, body_mention,
         same_line_title, line_idx, near_top}
      ``title_cands`` is a *list* of progressively-lengthened cleaned title
      prefixes (e.g. ["fundamental", "fundamental theoremsfor", ...]) so the
      matcher can use whichever candidate best matches the known title — needed
      when a title's first OCR line is a short fragment ("FUNDAMENTAL") while the
      full title spans several lines.
      TOC entries (dotted leaders / consecutive "Chapter" lines) are flagged
      via ``toc``; body-text mentions ("Chapter N discusses ...") via
      ``body_mention``. Both are excluded from matching.

    ``title_lines`` — every near-top, non-trivial line (Mode B fallback for
      books whose chapters are headed by the bare title, e.g. "1 Chain
      Complexes", with no "Chapter" keyword). Each dict:
        {page, line_idx, norm, raw, next_raw, page_first}
      ``next_raw`` (line after the candidate) and ``page_first`` (page's first
      line) let the matcher reject running heads (title followed by a page
      number) and TOC pages (first line is "Contents").
    """
    headings = []
    title_lines = []
    files = sorted(glob.glob(os.path.join(pages_dir, "page_*.json")))
    for f in files:
        m = re.search(r"(\d+)", os.path.basename(f))
        if not m:
            continue
        page = int(m.group(1))
        try:
            with open(f, encoding="utf-8-sig") as fh:
                data = json.load(fh)
        except Exception:
            continue
        lines = [_line_text(x) for x in data.get("text", [])]
        for i, line in enumerate(lines):
            cm = CHAPTER_RE.search(line)
            if cm:
                label_raw = cm.group(2)
                label_norm = parse_number(label_raw)
                same = line[cm.end():].strip()
                # Collect up to 3 following lines that continue the title.
                flines = []
                for j in range(i + 1, min(i + 5, len(lines))):
                    t = lines[j].strip()
                    if not t:
                        continue
                    if CHAPTER_RE.search(t):
                        break
                    if _looks_like_label(t):
                        continue
                    flines.append(t)
                    if len(flines) >= 3:
                        break
                # Build cumulative title candidates — progressive *prefixes* of
                # the true title: [same, same+flines[0], same+flines[0..1], ...].
                # detect_starts picks whichever best matches the known title,
                # which recovers chapters whose first OCR line is a short fragment
                # ("FUNDAMENTAL") while the real title spans several lines.
                raw_cands = []
                acc = same if (same and not _looks_like_label(same)) else ""
                if same and not _looks_like_label(same):
                    raw_cands.append(same)
                for f in flines:
                    acc = (acc + " " + f).strip() if acc else f
                    if acc not in raw_cands:
                        raw_cands.append(acc)
                if not raw_cands:
                    # only a bare label present (e.g. "CHAPTER" w/o title)
                    raw_cands = [same] if same else [""]
                title_cands = [clean_title_for_sim(c) for c in raw_cands]
                next_line_is_chapter = False
                for j in range(i + 1, len(lines)):
                    t = lines[j].strip()
                    if t:
                        next_line_is_chapter = bool(CHAPTER_RE.search(t))
                        break
                toc = is_toc_line(line) or (bool(same) and next_line_is_chapter)
                # body mention? same-line remainder led by a verb/article-pronoun
                body_mention = False
                if same:
                    first_tok = re.sub(r"[^A-Za-z]", "", same).lower()
                    body_mention = first_tok in BODY_MENTION_VERBS
                headings.append({
                    "page": page,
                    "label_raw": label_raw,
                    "label_norm": label_norm,
                    "title_cands": title_cands,
                    "toc": toc,
                    "body_mention": body_mention,
                    "same_line_title": bool(same),
                    "line_idx": i,
                    "near_top": i <= 3,
                })
            # Mode B: collect near-top candidate title lines (every page).
            # Limit to a few lines from the top so we still catch real headings
            # that sit *below* a short preamble (e.g. an "APPENDICES" list) — but
            # NOT so deep that we swallow section headings buried in the body.
            if i <= 6:
                s = line.strip()
                if s and not NUM_LINE_RE.match(s) and len(re.sub(r"[^A-Za-z]", "", s)) >= 4:
                    nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
                    title_lines.append({
                        "page": page,
                        "line_idx": i,
                        "norm": norm_title(s),
                        "raw": s,
                        "next_raw": nxt,
                        "page_first": lines[0].strip(),
                    })
    return headings, title_lines


# ── matching ─────────────────────────────────────────────────────────────────
TITLE_THRESHOLD = 0.75


def _in_window(page, claimed_start, claimed_end, max_dev):
    if claimed_start is None:
        return True
    hi = claimed_end if claimed_end is not None else claimed_start + 60
    return (claimed_start - max_dev) <= page <= (hi + max_dev)


def detect_starts(chapters, headings, title_lines, max_dev=35):
    """Return {ch: (pdf_page, confidence)} for confidently detected chapters.

    Mode A — "Chapter N" headings whose captured title matches the chapter's
    ``name_en``/``name``. TOC entries, body-text mentions ("Chapter N
    discusses ...") and pages far outside the claimed range are excluded, so a
    genuinely wrong claimed start still surfaces (as a mismatch) rather than a
    distant body mention being mistaken for the start.

    Mode B (fallback) — for chapters Mode A could not place, look for the bare
    title appearing as a near-top line within the claimed window (covers books
    headed "N. Title" / bare title with no "Chapter" keyword). The earliest
    such page is taken as the start.
    """
    detected = {}
    for c in chapters:
        ch = str(c.get("ch"))
        ch_int = int(ch) if ch.isdigit() else None
        target = norm_title(c.get("name_en") or c.get("name") or "")
        claimed_start = c.get("start")
        claimed_end = c.get("end")
        # ---- Mode A ----
        best = None
        best_score = -1.0
        for h in headings:
            if h["toc"] or h["body_mention"]:
                continue
            if not _in_window(h["page"], claimed_start, claimed_end, max_dev):
                continue
            # Use the BEST of the cumulative title candidates (shortest prefix ⇒
            # weakest match, longest ⇒ strongest but most contaminated). This
            # recovers chapters whose first OCR line is a short fragment while
            # rejecting headings whose longer candidates are OCR garbage.
            best_tsim = -1.0
            for cand in h["title_cands"]:
                tsim = title_similarity(cand, target) if (cand and target) else 0.0
                # Mode-A prefix/superstring bonus: OCR often splits a title
                # across lines, so the captured title is a *prefix* of the true
                # title. Safe here because the window and body-mention filters
                # already excluded distant/false matches; it only recovers
                # genuinely truncated real headings.
                if cand and target:
                    a, b = cand, target
                    if (a in b or b in a) and min(len(a), len(b)) >= 0.3 * max(len(a), len(b)):
                        tsim = max(tsim, 0.95)
                if tsim > best_tsim:
                    best_tsim = tsim
            if best_tsim < TITLE_THRESHOLD:
                continue
            score = tsim
            if h["same_line_title"]:
                score -= 0.1
            if ch_int is not None and h["label_norm"] is not None and h["label_norm"] == ch_int:
                score = min(1.0, score + 0.05)
            if h["near_top"]:
                score += 0.02
            if score > best_score:
                best = h
                best_score = score
        if best is not None:
            detected[ch] = (best["page"], round(best_score, 3))
            continue
        # ---- Mode B fallback (bare title) ----
        if not target:
            continue
        best_b = None
        best_b_score = -1.0
        for tl in title_lines:
            if not _in_window(tl["page"], claimed_start, claimed_end, max_dev):
                continue
            if tl["line_idx"] > 6:
                continue
            # Skip table-of-contents pages: a title listed on a "Contents" page
            # is a TOC entry, not a chapter start.
            if re.match(r"^(table of )?contents?$", tl["page_first"] or "", re.I):
                continue
            # avoid matching a section heading like "1.1 Complexes ..."
            if re.match(r"^\d+(\.\d+)*\s", tl["raw"]):
                continue
            sim = title_similarity(tl["norm"], target)
            if sim < 0.9:
                continue
            score = sim
            # Running-head penalty: a title immediately followed by a standalone
            # page number (e.g. "APPENDIX A: NOTATION" / "615") is the repeated
            # page header, not the genuine chapter heading. The real heading is
            # followed by the chapter's own first section / prose.
            if NUM_LINE_RE.match(tl["next_raw"] or ""):
                score -= 0.5
            better = False
            if score > best_b_score + 1e-9:
                better = True
            elif abs(score - best_b_score) <= 1e-9 and best_b is not None and tl["page"] < best_b["page"]:
                better = True
            if better:
                best_b = tl
                best_b_score = score
        if best_b is not None:
            detected[ch] = (best_b["page"], round(min(1.0, best_b_score), 3))
    return detected


def _ch_sort_key(k):
    """Natural sort: numbered chapters first (by int), then non-numeric keys
    such as appendices ('A', 'E') in lexical order."""
    if k.isdigit():
        return (0, int(k), "")
    return (1, 0, k)


# ═══════════════════════════════════════════════════════════════════════════
# 生成逻辑（build）
# ═══════════════════════════════════════════════════════════════════════════
def _agent_end(recs, ch):
    for c in recs:
        if str(c.get("ch")) == str(ch):
            return c.get("end")
    return None


def _set_range(rec, s, e):
    """在保留原 on-disk 形态的前提下写回 start/end（兼容 start/end 与
    start_page/end_page 两种字段命名）。"""
    sk = "start_page" if "start_page" in rec else "start"
    ek = "end_page" if "end_page" in rec else "end"
    rec[sk] = s
    rec[ek] = e


def _max_page(pages_dir):
    files = sorted(glob.glob(os.path.join(pages_dir, "page_*.json")))
    if not files:
        return 0
    m = re.search(r"(\d+)", os.path.basename(files[-1]))
    return int(m.group(1)) if m else 0


def build_report(recs, starts, ends, statuses, detected, max_page):
    """生成 agent 判断用的起飞前报告（Markdown 表格）。"""
    lines = []
    lines.append("# chapter_map 生成报告（build_chapter_map）")
    lines.append("")
    lines.append("> agent 判断环节：确认 CORRECTED 值；UNDTECTED 章须手动补 start/end "
                 "后重跑 `build_chapter_map.py`。全章 start/end 非 null 方可进入 "
                 "figure_detection。")
    lines.append("")
    lines.append("| ch | name | in_start | detected | in_end | inferred_end | status |")
    lines.append("|----|------|----------|----------|--------|--------------|--------|")
    n_corrected = n_undetected = 0
    for c in sorted(recs, key=lambda r: _ch_sort_key(str(r.get("ch")))):
        ch = str(c.get("ch"))
        name = c.get("name_en") or c.get("name") or ""
        inp_s = c.get("start")
        inp_e = c.get("end")
        det = detected.get(ch)
        st = statuses.get(ch, "OK")
        if st == "CORRECTED":
            n_corrected += 1
        elif st == "UNDTECTED":
            n_undetected += 1
        lines.append("| %s | %s | %s | %s | %s | %s | %s |" % (
            ch, name,
            "" if inp_s is None else inp_s,
            "" if det is None else det[0],
            "" if inp_e is None else inp_e,
            "" if ends.get(ch) is None else ends.get(ch),
            st,
        ))
    lines.append("")
    lines.append("- 全书末页（max page）: %d" % max_page)
    lines.append("- 自动校正 CORRECTED: %d 章" % n_corrected)
    lines.append("- 未检出 UNDTECTED: %d 章（须 agent 手动补）" % n_undetected)
    lines.append("")
    if n_undetected:
        lines.append("⚠️ 有 %d 章检测器未能从 OCR 定位起点（UNDTECTED），其 start/end "
                     "暂留空或保留 agent 原值。请在 chapter_map.json 中手动补正后重跑本工具。"
                     % n_undetected)
    else:
        lines.append("✅ 全章起点已由 OCR 检出，页码已据证据自动填正。")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(
        description="一步从 OCR 生成正确的 chapter_map.json 页码 + 起飞前报告")
    ap.add_argument("extract_dir", help="book _extract dir (holds chapter_map.json + page_*.json)")
    ap.add_argument("--no-write", action="store_true",
                    help="只打印报告、不写盘（dry-run 预览）")
    ap.add_argument("--max-deviation", type=int, default=35,
                    help="检测窗口容差（默认 35 页）")
    ap.add_argument("--verbose", action="store_true", help="打印检测器候选池")
    args = ap.parse_args()

    ex = args.extract_dir
    cmap_path = os.path.join(ex, "chapter_map.json")
    if not os.path.exists(cmap_path):
        sys.exit("chapter_map.json not found: %s" % cmap_path)
    recs = load_chapter_records(cmap_path)
    if not recs:
        sys.exit("chapter_map.json has no chapter records")

    headings, title_lines = scan_headings(ex)
    detected = detect_starts(recs, headings, title_lines, max_dev=args.max_deviation)
    max_page = _max_page(ex)

    # ── start：检测值优先；未检出则保留 agent 值，仍无则留空 ──
    starts, statuses = {}, {}
    for c in recs:
        ch = str(c.get("ch"))
        inp_s = c.get("start")
        det = detected.get(ch)
        if det is not None:
            starts[ch] = det[0]
            statuses[ch] = "CORRECTED" if (inp_s is not None and inp_s != det[0]) else "OK"
        elif inp_s is not None:
            starts[ch] = inp_s
            statuses[ch] = "KEPT_MANUAL"   # 未检出但 agent 已填，交由人审
        else:
            starts[ch] = None
            statuses[ch] = "UNDTECTED"

    # ── end：推断（下一章起点-1；末章保留 agent 值或全书末页）──
    order = sorted([ch for ch in starts if starts[ch] is not None],
                   key=lambda c: starts[c])
    ends = {}
    for i, ch in enumerate(order):
        nxt = order[i + 1] if i + 1 < len(order) else None
        if nxt is not None:
            ends[ch] = starts[nxt] - 1
        else:
            ends[ch] = _agent_end(recs, ch) if _agent_end(recs, ch) is not None else max_page
    # UNDTECTED（start 为空）章：end 保留 agent 原值（或空）
    for c in recs:
        ch = str(c.get("ch"))
        if starts.get(ch) is None:
            ends[ch] = c.get("end")

    # ── 报告 ──
    report = build_report(recs, starts, ends, statuses, detected, max_page)
    print(report)

    n_undetected = sum(1 for s in statuses.values() if s == "UNDTECTED")

    if args.no_write:
        print("\n[--no-write] 未写盘；预览如上。")
        sys.exit(1 if n_undetected > 0 else 0)

    # ── 写回：保留原 on-disk 形态与附加字段，仅改 start/end ──
    raw = load_chapter_map_raw(cmap_path)
    corrected = {str(c.get("ch")): (starts.get(str(c.get("ch"))),
                                    ends.get(str(c.get("ch")))) for c in recs}
    if isinstance(raw, dict) and isinstance(raw.get("chapters"), list):
        for c in raw["chapters"]:
            ch = str(c.get("ch", c.get("num", c.get("chapter"))))
            if ch in corrected:
                _set_range(c, *corrected[ch])
    elif isinstance(raw, dict):
        for k, v in raw.items():
            if isinstance(v, dict) and k in corrected:
                _set_range(v, *corrected[k])
    else:
        sys.exit("chapter_map.json 形态无法识别，未写盘")

    with open(cmap_path, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)
    report_path = os.path.join(ex, "chapter_map.build_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report)
    print("\nchapter_map.json 已写回（%d 章）；起飞前报告 -> %s"
          % (len(recs), report_path))
    if n_undetected:
        print("⚠️ %d 章 UNDTECTED：请在 chapter_map.json 手工补 start/end 后重跑本工具。"
              % n_undetected)
    sys.exit(1 if n_undetected > 0 else 0)


if __name__ == "__main__":
    main()
