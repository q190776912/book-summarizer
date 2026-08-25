"""embed_figures.py — skill-level, book-agnostic figure embedder.

For each chapter that has entries in `_extract/figure_index.json`, decide whether each
cropped figure is referenced by some summary item (definition / theorem / lemma / proposition /
corollary / example / proof) and, if so, embed it next to that item. Figures with no item
reference are skipped (per the skill's 图片嵌入规则).

This is a MANDATORY step of the summary workflow (Step 3.5 in SKILL.md), and must run
BEFORE `verify_chapter.py` (Step 4).

Design:
- Caption -> item anchor matching via OCR-noise-tolerant heuristic (parse_ref).
- Optional per-book override file `_extract/figure_embed_overrides.json` (used when a
  caption carries no usable item number but the figure clearly belongs to an item).
  Format: { "<fname.png>": {"anchors": ["**例1.5-9", ...], "is_proof": false}, ... }
- Idempotent: a figure already referenced in the .md is skipped (never double-inserted).
- Path written is always `_extract/figure/<fname>` (NOT `figure/<fname>`).
- After embedding, runs three post-scans automatically:
    (a) indent_inblock  — top-level images sitting inside a `> **证明/例**` block get a
        `>` prefix so they belong to the block;
    (b) fix_continuity — bare blank lines inside a block become `> ` so renderers don't
        split the block into several boxes;
    (c) wrap_images_in_flex — every `<img>` (single or consecutive run) is wrapped in a
        flexbox `<div>` so consecutive small images display side-by-side and singles center.
  All three are idempotent, so the output passes the G-layer of verify_chapter.py directly.

Usage:
    python embed_figures.py <book_dir> [--chapter N] [--dry-run] [--no-scan]
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
from lib.figure_io import load_fig_labels, fig_label_alt, FIGURE_LABELS_DEFAULT
import figure_index
import figure_embed_overrides


import os, sys

import os
import re
import json
import glob
import argparse
from PIL import Image

try:
    import fitz  # PyMuPDF — already a dependency of the figure pipeline
    _HAVE_FITZ = True
except Exception:
    _HAVE_FITZ = False

# Cache rendered page widths (px) keyed by (book_dir, page, dpi) so we don't
# reopen the PDF for every figure on the same page.
_PAGE_PX_CACHE = {}


def page_px_width(book_dir, page, dpi=200):
    """Return the rendered page width in px at `dpi` for a figure's PDF page.

    The embedder used to divide a figure's crop width by a HARD-CODED 1653
    (= A4 width @200 DPI). That is wrong for any book that is not A4 — e.g.
    the Karlin–Taylor stochastic-processes book is A3 (842x1191 pt), whose
    @200 DPI page width is 2339 px. Dividing by 1653 inflated every width by
    ~1.414x and pushed wide figures over 100%. We now read the ACTUAL page
    MediaBox from the PDF, so the percentage reflects the real column
    fraction regardless of page size/orientation (and handles landscape
    pages correctly too).

    Returns None when the PDF or fitz is unavailable, so callers fall back to
    the historical 1653 constant (preserves old behaviour elsewhere).
    """
    if not _HAVE_FITZ or not page:
        return None
    key = (book_dir, int(page), int(dpi))
    if key in _PAGE_PX_CACHE:
        return _PAGE_PX_CACHE[key]
    val = None
    pdfs = glob.glob(os.path.join(book_dir, "*.pdf"))
    if pdfs:
        try:
            doc = fitz.open(pdfs[0])
            mb = doc[int(page) - 1].mediabox
            val = float(mb.width) / 72.0 * dpi
            doc.close()
        except Exception:
            val = None
    _PAGE_PX_CACHE[key] = val
    return val

ITEM_KINDS = r"(?:定理|引理|命题|推论|例|示例|定义|公理|公设|注|注释|评注)"
# English item-kind -> canonical Chinese kind, so a bilingual .md that writes
# the SAME item in English (`**Theorem 3.5**`) or Chinese (`**定理3.5**`) both
# resolve to one anchor. Also lets English captions ("Figure 3.2: ... Theorem 3.5")
# drive embedding in an otherwise-English book.
EN_KIND_MAP = {'Definition': '定义', 'Theorem': '定理', 'Lemma': '引理',
               'Corollary': '推论', 'Proposition': '命题', 'Example': '例',
               'Remark': '评注', 'Assumption': '假设', 'Algorithm': '算法',
               'Axiom': '公理'}
EN_KIND_ALT = '|'.join(EN_KIND_MAP)
# Canonical CN kind -> all surface forms it can take in a .md, so an anchor is
# found whether the author wrote `**例 7.2**`, `**示例 7.2**`, `**注释 5.6**` or
# `**评注 5.6**`. Without this, bilingual books that mix label synonyms would
# leave figures unembedded.
CN_KIND_SYN = {
    '例': ['例', '示例'], '评注': ['评注', '注释', '注'], '定义': ['定义'],
    '定理': ['定理'], '引理': ['引理'], '命题': ['命题'], '推论': ['推论'],
    '假设': ['假设', '假定'], '算法': ['算法'], '公理': ['公理'],
}
NUM_RE = r"(\d+(?:\s*\.\s*\d+){0,3}(?:\s*-\s*\d+)?)"
ITEM_REF_RE = re.compile(ITEM_KINDS + r"\s*" + NUM_RE)
ITEM_REF_RE_EN = re.compile(r'(?:' + EN_KIND_ALT + r')\s*' + NUM_RE)
# Exercise (practice-problem) references — lettered Vakil-style `N.N.X` (X a
# letter) and plain numeric `N.N`, in Chinese (`习题`) or English (`Exercise`).
EX_NUM_RE = r"(\d+\.\d+(?:\.[A-Za-z])?)"
EX_ITEM_RE = re.compile(r'习题\s*' + EX_NUM_RE)
EX_ITEM_RE_EN = re.compile(r'Exercise\s*' + EX_NUM_RE)

# matches HTML `<img src="...">` (the only format used for figure embeds)
IMG_RE = re.compile(r'^\s*(<img\b[^>]*\bsrc="[^"]+"[^>]*>)')
HEAD_RE = re.compile(r"^\s*>\s*\*{0,2}(?:证明|证|例)")
TERM_RE = re.compile(r"^(?:---+\s*$|##\s|\*\*[^*]+\*\*)")


def short_caption(cap, labels=None):
    if labels is None:
        labels = FIGURE_LABELS_DEFAULT
    # strip the leading figure-label prefix (图 / Figure / Fig …) so the embedded
    # caption doesn't duplicate the number already shown on the cropped image.
    s = re.sub(rf"^(?:{fig_label_alt(labels)})\s*\d+(?:\.\d+)*\s*", "", cap or "", flags=re.IGNORECASE).strip()
    s = re.sub(r"图中.*$", "示意图", s)
    s = re.sub(r"中的.*$", "示意图", s)
    return s[:40]


def parse_ref(cap):
    if not cap:
        return None
    # English caption first (bilingual book support).
    m = ITEM_REF_RE_EN.search(cap)
    if m:
        kind_en = m.group(0).split()[0]   # first token, e.g. "Example"
        kind = EN_KIND_MAP.get(kind_en, kind_en)
        num = re.sub(r"\s+", "", m.group(1))
        return (kind, num, "proof" in cap.lower())
    m = ITEM_REF_RE.search(cap)
    if m:
        kind_match = re.match(ITEM_KINDS, m.group(0))
        kind = kind_match.group(0)
        num = re.sub(r"\s+", "", m.group(1))
        return (kind, num, "证明" in cap)
    # Exercise (practice-problem) reference. When an exercise entry is kept in the
    # summary (interleaved exercises per docs/writing-rules.md 习题收录规则), a
    # figure captioned with that exercise (e.g. "Exercise 11.4.A" / "习题 1.2.A")
    # anchors to the exercise entry (`**11.4.A（练习 (Exercise)）：…`) instead of
    # being skipped. (Chapter-end exercise blocks are omitted, so their figures
    # are simply not embedded.)
    em = EX_ITEM_RE_EN.search(cap) or EX_ITEM_RE.search(cap)
    if em:
        num = re.sub(r"\s+", "", em.group(1))
        return ('练习', num, False)
    return None


def parse_fig_self_ref(cap, fig_labels):
    """Fraleigh-style figures: the caption IS the figure's own number, e.g.
    '0.15Figure' or 'Figure 0.15'. The figure is a numbered *item* in the
    chapter (not a supplement to some other item), so instead of anchoring to
    an item number we anchor to the md reference of that figure itself.
    Returns the bare figure number (str, e.g. '0.15') or None.

    Only fires when the caption actually carries a figure-label word, so it
    never mis-extracts stray numbers from captions like 'see 3.5 above'.
    """
    if not cap:
        return None
    lab = fig_label_alt(fig_labels)
    if not lab:
        return None
    # Wrap lab in a non-capturing group: fig_label_alt returns a bare '|'
    # alternation (e.g. 'Figure\\.?|F[il]gure\\.?'), and concatenating it as
    # '{lab}\\s*(num)' would let the bare 'Figure\\.?' alternative match a
    # standalone "Figure" (inside '0.15Figure') and short-circuit before the
    # number is captured -> return None. Grouping fixes the precedence.
    lg = f"(?:{lab})"
    m = re.search(rf"{lg}\s*(\d+(?:\.\d+)*)", cap, re.IGNORECASE)
    if m and m.group(1):
        return m.group(1)
    m = re.search(rf"(\d+(?:\.\d+)*)\s*{lg}", cap, re.IGNORECASE)
    if m and m.group(1):
        return m.group(1)
    return None


def read_lines(p):
    return open(p, "r", encoding='utf-8').read().splitlines()


def write_lines(p, ls):
    t = "\n".join(ls)
    if not t.endswith("\n"):
        t += "\n"
    open(p, "w", encoding='utf-8').write(t)


def find_first_match(lines, candidates):
    # Pass 1: line-leading (prefix) match — handles bold item labels at start of line.
    for cand in candidates:
        if not cand:
            continue
        for i, ln in enumerate(lines):
            flat = ln.lstrip().lstrip("> ").strip()
            if flat.startswith(cand):
                return i, cand
    # Pass 2: substring match — handles inline bold terms in the *other* language
    # (e.g. English "A **subshift of finite type..." matched by the English anchor form).
    for cand in candidates:
        if not cand:
            continue
        for i, ln in enumerate(lines):
            if cand in ln:
                return i, cand
    return None, None


def find_proof(lines, start):
    i = start + 1
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    while i < len(lines):
        ln = lines[i]
        if ln.startswith(">"):
            return i
        if ln.strip().startswith("---") or ln.startswith("##") or ln.startswith("# "):
            return None
        if re.match(r"^\s*\*\*[定理引理命题推论例定义公理]", ln):
            return None
        i += 1
    return None


def find_after(lines, start):
    i = start + 1
    while i < len(lines) and lines[i].strip() == "":
        i += 1
    if i < len(lines) and lines[i].lstrip().startswith(">"):
        # Anchor sits inside a blockquote (e.g. an Example/Remark label, or a
        # caption-referenced example). Inserting a TOP-LEVEL figure <div>/<img>
        # before the next '>' line would split the blockquote and trip the
        # verifier's h-layer (blockquote-structure). Push the figure to just
        # AFTER the blockquote closes, keeping it adjacent to its item.
        if lines[start].lstrip().startswith(">"):
            j = i
            while j < len(lines) and (lines[j].lstrip().startswith(">") or lines[j].strip() == ""):
                j += 1
            return j
        return i
    while i < len(lines):
        ln = lines[i]
        if ln.startswith(">") or ln.strip().startswith("---") or ln.startswith("##") or ln.startswith("# "):
            return i
        if re.match(r"^\s*\*\*[定理引理命题推论例定义公理]", ln):
            return i
        i += 1
    return i


def _appendix_letter(book_dir, ch):
    """'A'..'Z' when book_structure names chapter `ch` "Appendix <L> ...". """
    fp = os.path.join(book_dir, "_extract", "book_structure.json")
    try:
        import json
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    stack = [data]
    while stack:
        node = stack.pop()
        for k in node.get("sub_sec", []) or []:
            if str(k.get("key")) == str(ch):
                m = re.search(r"\bAppendix\s+([A-Z])\b", str(k.get("name", "")))
                if m:
                    return m.group(1)
            stack.append(k)
    return None


def chap_mds(book_dir, ch):
    """Return ALL summary md files for chapter `ch` (both Chinese `第N章` and
    English `ChapterN` variants) so figures are embedded into every version."""
    out = []
    ch_s = str(ch)
    lab = _appendix_letter(book_dir, ch)
    for fn in sorted(os.listdir(book_dir)):
        if not fn.endswith(".md"):
            continue
        low = fn.lower()
        # Exact chapter-number match: "Chapter1_" must NOT match "Chapter10_...".
        en_ok = False
        if low.startswith("chapter" + ch_s.lower()):
            rest = fn[len("chapter") + len(ch_s):]
            en_ok = (rest == "" or not rest[0].isdigit())
        if fn.startswith(f"第{ch}章") or fn.startswith(f"第{ch}_") or en_ok:
            out.append(os.path.join(book_dir, fn))
            continue
        # Appendix units: Appendix{L}_*.md / 附录{L}_*.md
        if lab and (fn.startswith(f"Appendix{lab}_") or fn.startswith(f"附录{lab}")):
            out.append(os.path.join(book_dir, fn))
    return out


def load_overrides(book_dir):
    p = os.path.join(book_dir, "_extract", "figure_embed_overrides.json")
    if os.path.exists(p):
        try:
            return figure_embed_overrides.FigureEmbedOverrides.load(p).to_dict()
        except Exception:
            return {}
    return {}


def already_embedded(lines, fname):
    needle = f'src="_extract/figure/{fname}"'
    return any(needle in ln for ln in lines)


def indent_inblock(lines):
    out = []
    seg = False
    n = 0
    for ln in lines:
        m = IMG_RE.match(ln)
        if seg and m and not ln.lstrip().startswith(">"):
            out.append("> " + ln.lstrip())
            n += 1
            continue
        out.append(ln)
        if HEAD_RE.match(ln):
            seg = True
        elif TERM_RE.match(ln) and not ln.lstrip().startswith(">"):
            seg = False
    return out, n


def fix_continuity(lines):
    """Post-scan: turn a truly blank line that sits INSIDE a blockquote into a
    `> ` line so renderers don't split the block into several boxes.

    Robust, context-based, idempotent. The old implementation toggled a `seg`
    flag via HEAD_RE (start of a `> **证明/例**` block) and TERM_RE (end of such
    a block). When TERM_RE failed to fire at the real block boundary (e.g. a
    block ending in a `<img>` line or a `> $$` math block), `seg` stayed True
    past the block and a bare blank line that was actually BETWEEN two
    top-level items got converted to `> `, creating an "orphan `>`" that the
    H-layer of verify_chapter.py flags as "Structural-in-blockquote".

    The new logic makes a per-line CONTEXT decision that is the EXACT INVERSE
    of `verify_chapter.py`'s `check_h_structural_blockquote` orphan rule. For
    each truly blank line (`ln.strip() == ""`):
      1. Walk backwards (skipping truly-empty lines) to the nearest non-empty
         line `prev`; record `prev_bq = prev.lstrip().startswith(">")`.
      2. Walk forwards (skipping truly-empty lines) to the nearest non-empty
         line `nxt`; record `next_bq = nxt.lstrip().startswith(">")`.
      3. Convert the blank to `"> "` ONLY when `(prev_bq OR next_bq)` is True —
         i.e. the blank is adjacent (on at least one side) to blockquote
         content, so it belongs to / continues a block.
      4. NEVER convert a blank that is adjacent (on either side) to a horizontal
         rule `---`. The F-layer Separator check requires a *real* blank line
         immediately before AND after every `---`; a `> ` line does not count, so
         converting it would regress verify. A `---`-adjacent blank is by
         definition outside any blockquote, so leaving it blank is always correct.
      5. NEVER create a run of 2+ consecutive `> ` lines: the F-layer
         "BQ-empty-lines" check allows at most ONE empty `>` line between
         blockquote content. If the previously emitted line is already a bare
         `>`, leave the current blank as-is (the gap still renders as a single
         `>` line). This prevents converting 2+ consecutive in-block blanks into
         a forbidden `> ` / `> ` run.
      6. Otherwise (both sides are non-`>` top-level content, and neither side is
         `---`) leave it blank.

    The orphan check flags a bare `>` line only when `not (prev_bq or
    next_bq)`. By converting only when `prev_bq or next_bq`, the resulting `>
    ` line can NEVER be an orphan, so re-running the embedder on an
    already-embedded book cannot regress verify.

    A line that is already a bare `>` (i.e. `ln.strip() == ">"`) is NEVER
    touched — only truly empty (`ln.strip() == ""`) lines are acted on.

    Pure: list in -> (list, int) out. No I/O.
    """
    n = len(lines)
    out = []
    conv = 0
    for i in range(n):
        ln = lines[i]
        # Only act on a truly empty line. Never touch non-blank lines, and
        # never touch an already-bare `>` line (ln.strip() == ">").
        if ln.strip() != "":
            out.append(ln)
            continue
        # Walk backwards (skipping truly-empty lines) to nearest non-empty line.
        prev_bq = False
        prev_is_hr = False
        for k in range(i - 1, -1, -1):
            if lines[k].strip() != "":
                prev_bq = lines[k].lstrip().startswith(">")
                prev_is_hr = lines[k].strip() == "---"
                break
        # Walk forwards (skipping truly-empty lines) to nearest non-empty line.
        next_bq = False
        next_is_hr = False
        for k in range(i + 1, n):
            if lines[k].strip() != "":
                next_bq = lines[k].lstrip().startswith(">")
                next_is_hr = lines[k].strip() == "---"
                break
        # Do NOT convert a blank that sits next to a horizontal rule `---`.
        # The F-layer requires a *real* blank line immediately before AND after
        # every `---` separator; a `> ` line does not satisfy that, so converting
        # it would regress verify (F-layer Separator check). Such a `---`-adjacent
        # blank is by definition NOT inside a blockquote, so leaving it blank is
        # always correct.
        if prev_is_hr or next_is_hr:
            out.append(ln)
            continue
        if prev_bq or next_bq:
            # The F-layer "BQ-empty-lines" check allows at most ONE consecutive
            # empty `>` line between blockquote content. Never create a run of 2+
            # consecutive `> ` lines: if the previously emitted line is already a
            # bare `>`, leave this blank instead (the gap stays a single `>`).
            if out and out[-1].strip() == ">":
                out.append(ln)
            else:
                out.append("> ")
                conv += 1
        else:
            out.append(ln)
    return out, conv


def wrap_images_in_flex(lines):
    """Wrap every <img> line (or consecutive run) in a flex <div>.

    Emitted block is ALWAYS compact — no blank lines between the opening
    <div> and the first <img>, nor between the last <img> and </div>:

        <div style="display:flex; gap:6px; flex-wrap:wrap; justify-content:center">
          <img ...>
          <img ...>   (optional 2nd image, side-by-side)
        </div>

    It also re-cleans any PRE-EXISTING flex div block (e.g. ones that
    accidentally contain stray blank lines inside), so re-running the
    embed step on an already-embedded file normalises it to the compact
    form above.  Blank lines OUTSIDE the div are preserved (they are
    normal markdown paragraph breaks).  A blank line immediately before a
    `$$` math block is preserved.
    """
    n = len(lines)
    i = 0
    out = []
    flex_style = 'display:flex; gap:6px; flex-wrap:wrap; justify-content:center'
    flex_open = '<div style="' + flex_style + '">'

    def is_blank(ln):
        s = ln.strip()
        return s == '' or s == '>'

    def is_img(ln):
        s = core(ln)
        return s.startswith('<img') and s.endswith('>')

    def core(ln):
        # strip optional blockquote '> ' prefix and surrounding whitespace
        return ln.strip().lstrip('>').lstrip()

    def prefix_of(ln):
        s = ln.lstrip()
        if s.startswith('> '):
            return '> '
        if s.startswith('>'):
            return '>'
        return ''

    while i < n:
        c = core(lines[i])
        if c.startswith(flex_open):
            # pre-existing flex block -> re-emit compactly
            prefix = prefix_of(lines[i])
            imgs = []
            j = i + 1
            while j < n and core(lines[j]) != '</div>':
                if is_img(lines[j]):
                    imgs.append(core(lines[j]))
                j += 1
            out.append(prefix + flex_open)
            for im in imgs:
                out.append(prefix + '  ' + im)
            out.append(prefix + '</div>')
            i = j + 1
            continue

        if not is_img(lines[i]):
            out.append(lines[i])
            i += 1
            continue

        # fresh run of <img> lines (possibly separated by blanks)
        prefix = prefix_of(lines[i])
        run = []
        j = i
        while j < n:
            if is_img(lines[j]):
                run.append(core(lines[j]))
                j += 1
            elif is_blank(lines[j]):
                # skip blank, but stop if next non-blank is $$ (math block)
                k = j + 1
                while k < n and is_blank(lines[k]):
                    k += 1
                if k < n and lines[k].strip() in ('$$', '> $$'):
                    break
                j += 1
            else:
                break
        out.append(prefix + flex_open)
        for im in run:
            out.append(prefix + '  ' + im)
        out.append(prefix + '</div>')
        i = j

    # Ensure a blank line BEFORE each flex <div> and AFTER each </div> so the
    # HTML block is never swallowed by following markdown (KaTeX "missing blank
    # line after </div>" / L-layer `---` adjacency). Idempotent: skips when a
    # blank is already present. The blank inherits the blockquote prefix
    # ("> " or ">") when the div is inside a quote, else a plain empty line.
    final = []
    for idx, ln in enumerate(out):
        core_ln = ln.strip().lstrip('>').lstrip()
        if core_ln.startswith(flex_open) and final and final[-1].strip() != '':
            final.append(prefix_of(ln))  # blank line (same prefix as the div)
        final.append(ln)
        if core_ln == '</div>':
            nxt = out[idx + 1] if idx + 1 < len(out) else ''
            if nxt.strip() != '':
                final.append(prefix_of(ln))
    out = final
    return out, len(out) != len(lines)


def embed_chapter(book_dir, ch, overrides, dry_run, do_scan):
    md_paths = chap_mds(book_dir, ch)
    if not md_paths:
        return None
    figs = [e for e in load_figures(book_dir) if e.get("chapter", 0) == ch]
    fig_labels = load_fig_labels(os.path.join(book_dir, "_extract"))
    total_ins = []
    total_skip = []
    for p in md_paths:
        lines = read_lines(p)
        ins = []
        skipped = []
        for f in sorted(figs, key=lambda e: e.get("page", 0)):
            fname = f["file"].split("/")[-1]
            if already_embedded(lines, fname):
                skipped.append((fname, "already embedded (idempotent skip)"))
                continue
            r = parse_ref(f.get("caption", ""))
            idx = None
            anchor_used = None
            is_proof = False
            if r:
                kind, num, is_proof = r
                if kind == '练习':
                    # Exercises are written num-first: `**11.4.A（练习 (Exercise)）：…`
                    cands = [f"**{num}（", f"**{num} (", f"### 练习",
                             f"**练习 {num}", f"**练习{num}", f"**{num} 练习"]
                else:
                    # Try every surface form: canonical CN, its CN synonyms
                    # (示例/注释/...), and the English label form.
                    kind_en = {v: k for k, v in EN_KIND_MAP.items()}.get(kind, kind)
                    cands = []
                    for k in CN_KIND_SYN.get(kind, [kind]):
                        cands += [f"**{k} {num}", f"**{k}{num}", f"**{num} {k}"]
                    cands += [f"**{kind_en} {num}", f"**{kind_en}{num}", f"**{num} {kind_en}"]
                idx, anchor_used = find_first_match(lines, cands)
            # Fraleigh-style fallback: caption is the figure's OWN number
            # (e.g. '0.15Figure'); anchor to the md reference of that figure
            # ('**0.15 Figure**' item entry or 'Figure 0.15' prose reference).
            if idx is None:
                fnum = parse_fig_self_ref(f.get("caption", ""), fig_labels)
                if fnum:
                    cands = [f"**{fnum} Figure", f"Figure {fnum}", f"Fig. {fnum}"]
                    idx, anchor_used = find_first_match(lines, cands)
                    if idx is not None:
                        is_proof = False
            if idx is None and fname in overrides:
                ov = overrides[fname]
                mc = ov.get("anchors", [])
                idx, anchor_used = find_first_match(lines, mc)
                if idx is not None:
                    is_proof = bool(ov.get("is_proof", False))
            if idx is None:
                reason = "no item ref"
                if r:
                    reason = "parse ok but anchors not found"
                if fname in overrides:
                    reason += " (also manual miss)"
                skipped.append((fname, reason))
                continue
            # ---- idx is NOT None here: build the markdown image embed ----
            cap_raw = f.get("caption", "") or ""
            cap = short_caption(cap_raw, fig_labels)
            mt = re.search(rf"(?:{fig_label_alt(fig_labels)})\s*\d+", cap_raw, re.IGNORECASE)
            tag = mt.group(0) if mt else (fig_labels[0] if fig_labels else "图")
            # use <img> with proportional width attribute so the image
            # occupies the same fraction of the reader's column width as it
            # did in the original book page. The percentage is derived from
            # the figure's bbox crop width vs. A4 page width at 200 DPI (1653px).
            bbox = f.get("bbox", None)
            if bbox:
                crop_w = bbox[2] - bbox[0] + 16
                dpi = f.get("dpi", 200)
                denom = page_px_width(book_dir, f.get("page"), dpi) or 1653
                pct = round(crop_w / denom * 100, 1)
                if pct > 100:
                    pct = 100.0   # full-bleed figure -> fills the reader column
            else:
                pct = 45.0
            rel = "_extract/figure/" + fname
            alt = (tag + " " + cap).replace('"', "'")
            img = ('<img src="%s" alt="%s" width="%s%%" height="auto">\n' % (rel, alt, pct))
            if is_proof:
                pb = find_proof(lines, idx)
                if pb is None:
                    ins.append((find_after(lines, idx), f"\n{img}\n", "item", anchor_used, fname))
                else:
                    ins.append((pb + 1, f">\n> {img}", "proof", anchor_used, fname))
            else:
                ins.append((find_after(lines, idx), f"\n{img}", "item", anchor_used, fname))

        ins.sort(key=lambda x: x[0], reverse=True)
        for idx, txt, mode, anc, fname in ins:
            lines[idx:idx] = txt.splitlines()

        if do_scan:
            lines, n_indent = indent_inblock(lines)
            lines, n_cont = fix_continuity(lines)
            lines, n_sbs = wrap_images_in_flex(lines)
        else:
            n_indent = n_cont = n_sbs = 0

        if not dry_run:
            write_lines(p, lines)
        print(f"[ch{ch}] {'DRY ' if dry_run else ''}embedded {len(ins)} new figure(s) "
              f"into {os.path.basename(p)}"
              + (f"; scan: {n_indent} in-block indent, {n_cont} continuity fix, {n_sbs} side-by-side" if do_scan else ""))
        total_ins.extend(ins)
        total_skip.extend(skipped)
    return total_ins, total_skip


def load_figures(book_dir):
    p = os.path.join(book_dir, "_extract", "figure_index.json")
    if not os.path.exists(p):
        return []
    return figure_index.FigureIndex.load(p).to_dict()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book_dir")
    ap.add_argument("--chapter", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-scan", action="store_true",
                    help="skip the in-block indent + continuity post-scan")
    args = ap.parse_args()

    figs = load_figures(args.book_dir)
    if not figs:
        print("No _extract/figure_index.json — nothing to embed. "
              "Run the figure pipeline (extract_figures.py + assign_figures.py) first.")
        return
    overrides = load_overrides(args.book_dir)
    by_ch = {}
    for f in figs:
        c = f.get("chapter", 0)
        # 数字章号取 >=0；字母章号（附录 A/B…）原样保留（2026-08-25 Evans）
        if isinstance(c, str) or c >= 0:
            by_ch.setdefault(c, True)

    def _ch_sort_key(ch):
        try:
            return (0, int(str(ch)), "")
        except (TypeError, ValueError):
            return (1, 0, str(ch))

    chapters = [args.chapter] if args.chapter else sorted(by_ch, key=_ch_sort_key)
    total_placed = 0
    total_skip = 0
    for ch in chapters:
        if ch not in by_ch:
            continue
        res = embed_chapter(args.book_dir, ch, overrides, args.dry_run, not args.no_scan)
        if res is None:
            continue
        ins, skipped = res
        total_placed += len(ins)
        total_skip += len(skipped)
        for fname, reason in skipped:
            print(f"  skip ch{ch}: {fname} -> {reason}")

    print(f"\nNewly placed: {total_placed}; Skipped (no ref / already present): {total_skip}")


if __name__ == "__main__":
    main()
