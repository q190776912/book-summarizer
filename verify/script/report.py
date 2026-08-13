"""
report.py — print_result + summary formatting for verify_one results.

This module formats and prints the verification result dict produced by
verify_one. It lazily imports the private helpers `_lookup_item_detail` and
`_load_page_context` from verify.script.verify_chapter (only at call time) so that
there is NO circular import at module-load time.
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

import os, sys


# P 层聚合阈值（与 verify/layers/verbose_gates/script/verbose_gates.py 中的 VERBOSE_PARA_GATE / VERBOSE_PROOF_GATE 一致）
from verbose_gates import VERBOSE_PARA_GATE, VERBOSE_PROOF_GATE

def print_result(r):
    """Print verification result for one chapter.

    D-LAYER prints FIRST: an entire missing section is the most fundamental
    defect and must be seen before item-level (A/B/C) noise.

    If r['items'] is available, TRULY MISSING items are printed with their
    label, page, and text snippet for immediate triage.
    """
    # Lazy import to avoid a circular import at module load time
    # (verify_chapter imports print_result from this module).
    from verify.script.verify_chapter import _lookup_item_detail, _load_page_context

    problems = 0
    ch = r['ch']; md = r['md']

    # D-LAYER FIRST: section continuity + tail-section-missing (independent of extract_items)
    d = r['d_layer']
    if d.get('continuity_sections'):
        problems += 1
        print(f"D-LAYER CONTINUITY GAP ({len(d['continuity_sections'])}): the .md section sequence "
              f"has a HOLE — source has these sections (header + labeled item) but the .md jumps "
              f"over them (md has a smaller AND a larger §, yet this one is absent) — MUST be added:")
        for s in d['continuity_sections']:
            print(f"  ! Ch{ch} §{ch}.{s}")
    if d.get('missing_sections'):
        problems += 1
        print(f"D-LAYER MISSING TAIL SECTION ({len(d['missing_sections'])}): book has these sections "
              f"(header + labeled item in raw JSON) beyond the .md's last written § — MUST be added:")
        for s in d['missing_sections']:
            print(f"  ! Ch{ch} §{ch}.{s}")

    # Per-level breakdown — only when the generalized nested check emitted a
    # `levels` map (gm/roman books don't). This is SUPPLEMENTARY detail: the
    # FAIL gate above is driven entirely by the merged continuity/missing lists,
    # so we do NOT re-increment `problems` here (that would double-count). Renders
    # Level 1 (章) / Level 2 (节) / Level 3 (小节) / Level 4 (子小节) blocks.
    levels = d.get('levels')
    if levels:
        for L in sorted(levels.keys()):
            blk = levels[L] or {}
            cont = blk.get('continuity') or []
            miss = blk.get('missing') or []
            if cont:
                print(f"D-LAYER LEVEL {L} CONTINUITY GAP ({len(cont)}): section sequence has a HOLE "
                      f"at hierarchy level {L} — MUST be added:")
                for s in cont:
                    print(f"  ! Ch{ch} §{ch}.{s}")
            if miss:
                print(f"D-LAYER LEVEL {L} MISSING TAIL SECTION ({len(miss)}): beyond last written "
                      f"section at hierarchy level {L} — MUST be added:")
                for s in miss:
                    print(f"  ! Ch{ch} §{ch}.{s}")

    if r.get('ignored_hit'):
        print(f"\nIGNORED ({len(r['ignored_hit'])}): confirmed-noise keys suppressed via --ignore "
              f"(excluded from B-layer completeness comparison; C/D unaffected):")
        for k in r['ignored_hit']:
            print(f"  · {k}")

    if r['label_warns']:
        print("\nLabel consistency warnings (non-blocking, check --manual if needed):")
        for w in r['label_warns']:
            print(w)

    if r['truly_missing']:
        problems += 1
        print(f"\nTRULY MISSING ({len(r['truly_missing'])}): extracted items absent from the .md — MUST be added as entries:")
        for k in r['truly_missing']:
            items = r.get('items')
            if items:
                detail = _lookup_item_detail(k, items)
                if detail:
                    snippet = detail['text'][:100]
                    print(f"  - {k}  {detail['label']} p{detail['page']}: {snippet}")
                    # Show page context if available
                    ctx = _load_page_context(r.get('extract_dir', ''), r['ch'], k, items)
                    if ctx and ctx not in snippet:
                        print(f"    page context: {ctx}")
                else:
                    print(f"  - {k}")
            else:
                print(f"  - {k}")
    if r['mentioned_only']:
        print(f"\nMENTIONED-ONLY ({len(r['mentioned_only'])}): in .md as prose/cross-ref, not as own entry (review):")
        for k in r['mentioned_only']:
            print(f"  ~ {k}")
    if r['extra']:
        print(f"\nEXTRA ({len(r['extra'])}): keys in .md but not detected by extractor (usually correctly-filtered cross-refs):")
        for k in r['extra']:
            print(f"  + {k}")
    if r['blocking']:
        problems += 1
        print(f"\nB-LAYER BLOCKING ({len(r['blocking'])}): extraction may have missed items — resolve before writing:")
        for w in r['blocking']:
            print(f"  ! {w.strip()}")
    if r['warnings']:
        print("\nExtraction warnings (non-blocking, re-scan clean):")
        for w in r['warnings']:
            print(f"  {w}")
    if r.get('b_tail_warnings'):
        print("\nB-LAYER TAIL CHECK (non-blocking, verify chapter/section end):")
        for w in r['b_tail_warnings']:
            print(f"  ~ {w.strip()}")
    if r.get('b_gap_warnings'):
        print("\nB-LAYER NUMBERING GAP CHECK (non-blocking, verify against source):")
        for w in r['b_gap_warnings']:
            print(f"  ~ {w.strip()}")
    # E-LAYER: figure completeness (analog of B-layer) — only if figure extraction ran.
    if r.get('fig_skipped'):
        print("\nE-LAYER FIGURES: SKIPPED — no figure_index.json (figure extraction not run for this chapter).")
    else:
        if r['fig_missing']:
            problems += 1
            print(f"\nE-LAYER FIGURE COMPLETENESS MISSING ({len(r['fig_missing'])}): caption(s) referenced in "
                  f"chapter OCR but no matching crop in figure_index.json — re-run extract_figures.py on "
                  f"those pages or register in ignore_fig_ch{r['ch']}.json:")
            for k in r['fig_missing']:
                try:
                    print(f"  ! 图{k}")
                except UnicodeEncodeError:
                    print(f"  ! fig-{k.encode('ascii', errors='replace').decode('ascii')}")
        if r['fig_extra']:
            print(f"\nE-LAYER FIGURE EXTRA ({len(r['fig_extra'])}): cropped label not found as a caption in OCR "
                  f"(possible mislabel / duplicate caption pairing, review):")
            for k in r['fig_extra']:
                try:
                    print(f"  ~ 图{k}")
                except UnicodeEncodeError:
                    print(f"  ~ fig-{k.encode('ascii', errors='replace').decode('ascii')}")
        if r['fig_invalid']:
            problems += 1
            print(f"\nE-LAYER FIGURE VALIDITY ERRORS ({len(r['fig_invalid'])}):")
            for l in r['fig_invalid']:
                print(l)
        if r['fig_invalid_warn']:
            print(f"\nE-LAYER FIGURE SUSPICIOUS ({len(r['fig_invalid_warn'])}):")
            for l in r['fig_invalid_warn']:
                print(l)

    # ===========================================================================
    # F-LAYER FORMAT: 合并格式校验总结（原 C/G/H/I/J/K/L/M/N 九层统一为代号 F）。
    # 所有格式相关 finding 在单一 F-LAYER FORMAT 段内呈现；任一子项非空即阻断 FAIL。
    # ---- KaTeX（原 C 层）----
    if r['katex_errors']:
        problems += 1
        print(f"\nF-LAYER FORMAT · KaTeX ({len(r['katex_lines'])}):")
        for l in r['katex_lines']:
            try:
                print(f"  x {l}")
            except UnicodeEncodeError:
                print(f"  x {l.encode('ascii', errors='replace').decode('ascii')}")
    # ---- 引用块连续性（原 G 层）----
    if r.get('quote_gaps'):
        problems += 1
        print(f"\nF-LAYER FORMAT · Quote continuity ({len(r['quote_gaps'])}): a bare blank line "
              f"inside a `> **证明/例` block breaks it into separate boxes — "
              f"convert the blank to `> ` (empty-quote line) so the block stays contiguous:")
        for g in r['quote_gaps']:
            print(g)
    if r.get('nested_bq'):
        problems += 1
        print(f"\nF-LAYER FORMAT · Nested blockquote ({len(r['nested_bq'])}): `> > **证明/例` nested "
              f"blockquotes detected — use single `>` level (proof inside example must "
              f"use `> **证明**`, not `> > **证明**`):")
        for g in r['nested_bq']:
            print(g)
    ex_gaps, ex_warns = r.get('ex_proof_gaps', ([], []))
    if ex_gaps:
        problems += 1
        print(f"\nF-LAYER FORMAT · Example-proof gap ({len(ex_gaps)}): example and its proof are NOT "
              f"in the same contiguous blockquote — remove empty lines between them so "
              f"the entire example+proof uses the same `>` level:")
        for g in ex_gaps:
            print(g)
    if ex_warns:
        print(f"\nF-LAYER FORMAT · Example-proof warn ({len(ex_warns)}): blank `>` line between "
              f"example and proof (visual spacing OK, but can be removed):")
        for w in ex_warns:
            print(w)
    # ---- 结构标签守卫（原 H 层）----
    h_bq = r.get('h_structural_bq', [])
    if h_bq:
        problems += 1
        print(f"\nF-LAYER FORMAT · Structural-in-blockquote ({len(h_bq)}): labels like "
              f"定义/定理/引理/推论/命题/断言/公理/Theorem/Definition/Lemma/Corollary/Proposition/Axiom "
              f"must be TOP-LEVEL (no `>` wrapper) — remove the `> ` prefix:")
        for g in h_bq:
            print(g)
    h_stmt = r.get('h_stmt_bq', [])
    if h_stmt:
        problems += 1
        print(f"\nF-LAYER FORMAT · Statement-in-blockquote ({len(h_stmt)}): a definition/theorem/lemma/"
              f"corollary/proposition's STATEMENT content (`（N）` / `**（N）**` / `$$` / `- （a）` "
              f"inside the item, before any `> **证明/例/注`) must be TOP-LEVEL — unwrap those "
              f"`>` lines. `>` is reserved for proof/example/note/footnote only:")
        for g in h_stmt:
            print(g)
    h_ul = r.get('h_ul_bq', [])
    if h_ul:
        problems += 1
        print(f"\nF-LAYER FORMAT · Unlabeled blockquote ({len(h_ul)}): a `>` blockquote must start "
              f"with a recognized label (证明/证/例/注/说明/脚注). Found plain text in `>` "
              f"without any label — remove the `>` prefix or add a label:")
        for g in h_ul:
            print(g)
    h_mbq = r.get('h_mbq', [])
    if h_mbq:
        problems += 1
        print(f"\nF-LAYER FORMAT · Missing blockquote ({len(h_mbq)}): labels like 证明/证/例/注/说明/注记 "
              f"must be wrapped in `>` — add `> ` prefix:")
        for g in h_mbq:
            print(g)
    # ---- 条目分隔符完整性（原 I 层）----
    i_sep = r.get('i_sep_gaps', [])
    if i_sep:
        problems += 1
        print(f"\nF-LAYER FORMAT · Missing separator ({len(i_sep)}): consecutive items without `---` "
              f"between them — insert `---` (blank line + --- + blank line) between each pair:")
        for g in i_sep:
            print(g)
    # ---- 条目内分隔符（原 J 层）----
    j_hd = r.get('j_header_dash', [])
    if j_hd:
        problems += 1
        print(f"\nF-LAYER FORMAT · Header-dash ({len(j_hd)}): a `---` sits INSIDE an item block "
              f"(between the header and its first `**(N)**` sub-point, OR between two "
              f"`**(i)**`/`**(i+1)**` sub-points) — remove that `---` so the item's parts "
              f"stay directly connected (matching `**引理3.3**` … `(1)` … `(2)` style, "
              f"no `---` between them):")
        for g in j_hd:
            print(g)
    # ---- 证明-列表间距（原 K 层）----
    k_list = r.get('k_proof_list', [])
    if k_list:
        problems += 1
        print(f"\nF-LAYER FORMAT · Proof-after-list ({len(k_list)}): a `> **证明**` blockquote "
              f"directly follows a numbered list item without a blank line — add a "
              f"blank line so the proof aligns at the theorem's outer level:")
        for g in k_list:
            print(g)
    # ---- 分隔符空行（原 L 层）----
    l_sep = r.get('l_sep_blanks', [])
    if l_sep:
        problems += 1
        print(f"\nF-LAYER FORMAT · Separator blank-lines ({len(l_sep)}): every `---` separator "
              f"must have a blank line immediately before AND after it — "
              f"insert missing blank line(s):")
        for g in l_sep:
            print(g)
    # ---- 数学块引用泄漏（原 M 层）----
    m_dm = r.get('m_dm_gt', [])
    if m_dm:
        problems += 1
        print(f"\nF-LAYER FORMAT · Displaymath-gt ({len(m_dm)}): `>` lines found inside "
              f"`$$...$$` display math blocks — strip the blockquote prefix from "
              f"these lines:")
        for g in m_dm:
            print(g)
    # ---- 引用块空行过多（原 N 层）----
    n_bq = r.get('n_bq_empty', [])
    if n_bq:
        problems += 1
        print(f"\nF-LAYER FORMAT · BQ-empty-lines ({len(n_bq)}): excessive consecutive empty "
              f"`>` lines inside blockquote (max 1 allowed between content) — "
              f"collapse extras to a single empty `>` line:")
        for g in n_bq:
            print(g)

    # O-LAYER: ordinal sub-item gap detection (non-blocking warning).
    # Detects gaps in parenthesized numbered sequences (1), (2), (3)...
    # within annotation/remark blocks. HEAD/INTERNAL gaps are likely omissions;
    # TAIL gaps (from OCR cross-ref) are review suggestions.
    o_gaps = r.get('o_subitem_gaps', [])
    if o_gaps:
        blocking_o = [g for g in o_gaps if g.strip().startswith('x')]
        warning_o = [g for g in o_gaps if g.strip().startswith('~')]
        if blocking_o:
            problems += 1
            print(f"\nO-LAYER SUBITEM GAPS ({len(blocking_o)}): parenthesized numbered "
                  f"sequence has missing entries — review and add omitted items:")
            for g in blocking_o:
                print(g)
        if warning_o:
            print(f"\nO-LAYER SUBITEM TAIL ({len(warning_o)}): OCR cross-reference "
                  f"suggests possible tail omissions (non-blocking, review):")
            for g in warning_o:
                print(g)

    # P-LAYER: anti-regression gate (content/structure defects, blocking, never auto-fix).
    # Catches the Vakil incident class: exercise-consolidation blocks, OCR/header
    # noise, bare item numbers (missing title), and missing sections vs structure contract.
    p_exer = r.get('p_exer_block', [])
    p_noise = r.get('p_noise', [])
    p_bare = r.get('p_bare_item', [])
    p_miss = r.get('p_missing_sec', [])
    p_extra = r.get('p_extra_item', [])
    p_verbose = r.get('p_verbose', [])
    p_proof_verbose = r.get('p_proof_verbose', [])
    if p_exer:
        problems += 1
        print(f"\nP-LAYER EXERCISE CONSOLIDATION BLOCK ({len(p_exer)}): exercises must be "
              f"inline at their original page position (`**练习 N.M.X（Exercise N.M.X）：**`), "
              f"NOT pulled into a `### 练习`/`### Exercises` block at section/chapter end — "
              f"remove the consolidation block and restore each exercise in place:")
        for g in p_exer:
            print(g)
    if p_noise:
        problems += 1
        print(f"\nP-LAYER OCR/HEADER NOISE ({len(p_noise)}): page headers/footers/copyright "
              f"lines must be stripped — summaries are rewritten, never verbatim OCR:")
        for g in p_noise:
            print(g)
    if p_bare:
        problems += 1
        print(f"\nP-LAYER BARE ITEM NUMBER ({len(p_bare)}): number-first items need their "
              f"printed title inside the label (`**N.M.K（标题）：**` or `**定义 N.M.K**：`), "
              f"not a bare `**N.M.K**` with the title dropped into the body:")
        for g in p_bare:
            print(g)
    if p_miss:
        problems += 1
        print(f"\nP-LAYER MISSING SECTION vs CONTRACT ({len(p_miss)}): structure contract "
              f"(book_structure.json) is the writing contract — "
              f"every section must be emitted in order; add the missing `## §`:")
        for g in p_miss:
            print(g)
    if p_extra:
        problems += 1
        print(f"\nP-LAYER FABRICATED ITEM vs CONTRACT ({len(p_extra)}): structure contract "
              f"(book_structure.json) is the writing contract — "
              f"do NOT invent numbered items the source lacks "
              f"(e.g. a `**X.1.1（Implicit）：**` where §X.1 is prose); delete or demote to prose/remark:")
        for g in p_extra:
            print(g)
    if len(p_verbose) >= VERBOSE_PARA_GATE:
        problems += 1
        print(f"\nP-LAYER VERBOSE TOP-LEVEL PROSE ({len(p_verbose)} ≥ {VERBOSE_PARA_GATE}): non-core "
              f"content must be SUMMARIZED to core points (Tier 2) or omitted, not copied verbatim "
              f"from the book. Condense motivation/intros to 2–4 sentences or omit them; "
              f"definitions/theorems/examples/exercises AND remarks (Remark/Aside, Tier 1: kept "
              f"complete with only OCR fixes) are exempt:")
        for g in p_verbose:
            print(g)
    if len(p_proof_verbose) >= VERBOSE_PROOF_GATE:
        problems += 1
        print(f"\nP-LAYER VERBOSE PROOF/SOLUTION BLOCK ({len(p_proof_verbose)} ≥ {VERBOSE_PROOF_GATE}): "
              f"proofs and example solutions must be condensed to enumerated core steps (Tier 3), NOT a "
              f"verbatim translation of the book's proof paragraph. Each step = one sentence with a "
              f"`1. 2. 3. …` marker; the number of steps is unlimited (the `1,2,3` in the rule is "
              f"illustrative) — but a wall of un-numbered prose is forbidden. Remarks (Remark/Aside) "
              f"are Tier 1 (kept complete), exempt:")
        for g in p_proof_verbose:
            print(g)

    # Q-LAYER: formula sequence-label audit (opt-in; no-op when `formula` map absent).
    # FABRICATED / INCONSISTENT -> always FAIL (blocking).  MISSING -> WARN only
    # (never blocking; books register genuine gaps in the map's `ignore` list).
    # Content correctness is left to human reconciliation via
    # <extract_dir>/formula_audit.md (written by verify_all).
    q_checked = r.get('q_checked', False)
    if q_checked:
        q_fab = r.get('q_fabricated', []) or []
        q_inc = r.get('q_inconsistent', []) or []
        q_miss = r.get('q_missing', []) or []
        if q_fab:
            problems += 1
            print(f"\nQ-LAYER FORMULA FABRICATED ({len(q_fab)}): summary \\tag number "
                  f"not found in the book-source formula-number set S (fabricated / "
                  f"mis-copied) — must match a real source number 1:1:")
            for row in q_fab:
                print(f"  ! {row.get('number', '')}  {row.get('summary_latex', '')}")
        if q_inc:
            problems += 1
            print(f"\nQ-LAYER FORMULA INCONSISTENT ({len(q_inc)}): duplicate \\tag number "
                  f"or cross-chapter number (first component != ch) — fix numbering:")
            for row in q_inc:
                print(f"  ! {row.get('number', '')}  {row.get('summary_latex', '')}")
        if q_miss:
            print(f"\nQ-LAYER FORMULA MISSING ({len(q_miss)}) [WARN, non-blocking]: "
                  f"book-source formula numbers absent from the summary (review / add, "
                  f"or register in the `formula.ignore` list):")
            for row in q_miss:
                print(f"  ~ {row.get('number', '')}  {row.get('source_text', '')}")
        q_fab_n, q_inc_n, q_miss_n = len(q_fab), len(q_inc), len(q_miss)
    else:
        q_fab_n = q_inc_n = q_miss_n = 0
    q_part = (f"/ {q_fab_n} q-fab / {q_inc_n} q-inc / {q_miss_n} q-miss "
              if q_checked else "")

    # B-LAYER BLOCKING 已包含「重要概念首项缺失」(原 Q 层逻辑，2026-08-05 并入 B)：
    # 书中某节某类别（定义/定理/引理/推论/命题）首项在总结中缺失 → 该 finding
    # 已追加进 r['blocking']，于上方 "B-LAYER BLOCKING" 段统一展示。

    # F-LAYER FORMAT 聚合计数（原 C/G/H/I/J/K/L/M/N 九层统一为代号 F）：
    # 任一格式子项非空即计入 F 总数；ex_warns 为非阻断 warn，不计入阻断计数。
    f_n = (len(r.get('katex_lines', [])) + len(r.get('quote_gaps', [])) + len(r.get('nested_bq', []))
           + len(ex_gaps) + len(h_bq) + len(h_stmt) + len(h_ul) + len(h_mbq)
           + len(i_sep) + len(j_hd) + len(k_list) + len(l_sep) + len(m_dm) + len(n_bq))

    if problems:
        print(f"\nFAIL: {len(r['truly_missing'])} truly missing / {len(r['blocking'])} B-layer blocking "
              f"/ {len(d.get('continuity_sections', []))} D-layer section-gaps "
              f"/ {len(d.get('missing_sections', []))} D-layer missing tail sections "
              f"/ {len(r.get('fig_missing', []))} fig-missing / {len(r.get('fig_invalid', []))} fig-invalid "
              f"/ F:{f_n} F-layer-format "
              f"/ {len([g for g in o_gaps if g.strip().startswith('x')])} o-layer-subitem "
              f"/ {len(p_exer)} p-layer-exer-block / {len(p_noise)} p-layer-noise "
              f"/ {len(p_bare)} p-layer-bare-item / {len(p_miss)} p-layer-missing-sec "
              f"/ {len(p_extra)} p-layer-fabricated-item "
              f"/ {len(p_verbose)} p-layer-verbose-prose / {len(p_proof_verbose)} p-layer-verbose-proof "
              f"{q_part}— {os.path.basename(md)}")
        return 'FAIL'
    else:
        q_suffix = f" Q:{q_fab_n}/{q_inc_n}/{q_miss_n}" if q_checked else ""
        print(f"\nPASS: {os.path.basename(md)} (entries={len(r['entry_keys'])}, mentioned-only={len(r['mentioned_only'])}){q_suffix}")
        return 'PASS'
