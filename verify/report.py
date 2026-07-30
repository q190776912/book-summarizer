"""
report.py — print_result + summary formatting for verify_one results.

This module formats and prints the verification result dict produced by
verify_one. It lazily imports the private helpers `_lookup_item_detail` and
`_load_page_context` from verify.verify_chapter (only at call time) so that
there is NO circular import at module-load time.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def print_result(r):
    """Print verification result for one chapter.

    D-LAYER prints FIRST: an entire missing section is the most fundamental
    defect and must be seen before item-level (A/B/C) noise.

    If r['items'] is available, TRULY MISSING items are printed with their
    label, page, and text snippet for immediate triage.
    """
    # Lazy import to avoid a circular import at module load time
    # (verify_chapter imports print_result from this module).
    from verify.verify_chapter import _lookup_item_detail, _load_page_context

    problems = 0
    ch = r['ch']; md = r['md']

    # D-LAYER FIRST: section-missing & tail-ordinal (independent of extract_items)
    d = r['d_layer']
    if d['missing_sections']:
        problems += 1
        print(f"D-LAYER MISSING SECTION ({len(d['missing_sections'])}): book has these sections "
              f"(header + labeled item in raw JSON) but the .md has no `## §` for them — MUST be added:")
        for s in d['missing_sections']:
            print(f"  ! Ch{ch} §{ch}.{s}")
    if d['tail_gaps']:
        print(f"\nD-LAYER TAIL ORDINAL GAP ({len(d['tail_gaps'])}): section present in .md, but raw JSON "
              f"shows a higher labeled item number — possible missed tail item (review):")
        for s, (mmax, rmax) in sorted(d['tail_gaps'].items()):
            print(f"  ~ Ch{ch} §{ch}.{s}: md max = {mmax}, raw labeled max = {rmax}")
    if d['suspect']:
        print(f"\nD-LAYER SUSPECT (likely OCR noise, {len(d['suspect'])}):")
        for s, (mmax, rmax) in sorted(d['suspect'].items()):
            print(f"  ? Ch{ch} §{ch}.{s}: md max = {mmax}, raw labeled max = {rmax} (gap>{5}, probably misread)")

    if r.get('ignored_hit'):
        print(f"\nIGNORED ({len(r['ignored_hit'])}): confirmed-noise keys suppressed via --ignore "
              f"(excluded from A/B comparison; C/D unaffected):")
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
    if r['katex_errors']:
        problems += 1
        print(f"\nC-LAYER KATEX ERRORS ({len(r['katex_lines'])}):")
        for l in r['katex_lines']:
            try:
                print(f"  x {l}")
            except UnicodeEncodeError:
                print(f"  x {l.encode('ascii', errors='replace').decode('ascii')}")

    # E-LAYER: figure completeness (analog of B-layer) — only if figure extraction ran.
    if r.get('fig_skipped'):
        print("\nE/F-LAYER FIGURES: SKIPPED — no figure_index.json (figure extraction not run for this chapter).")
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
            print(f"\nF-LAYER FIGURE VALIDITY ERRORS ({len(r['fig_invalid'])}):")
            for l in r['fig_invalid']:
                print(l)
        if r['fig_invalid_warn']:
            print(f"\nF-LAYER FIGURE SUSPICIOUS ({len(r['fig_invalid_warn'])}):")
            for l in r['fig_invalid_warn']:
                print(l)

    # G-LAYER: quote-block continuity (structural, always runs).
    # A bare blank line inside a `> **证明/例` block splits it into
    # separate boxes — the "图跟例子断开了" symptom. Blocking like C-layer.
    if r.get('quote_gaps'):
        problems += 1
        print(f"\nG-LAYER QUOTE CONTINUITY ({len(r['quote_gaps'])}): a bare blank line "
              f"inside a `> **证明/例` block breaks it into separate boxes — "
              f"convert the blank to `> ` (empty-quote line) so the block stays contiguous:")
        for g in r['quote_gaps']:
            print(g)

    if r.get('nested_bq'):
        problems += 1
        print(f"\nG-LAYER NESTED BLOCKQUOTE ({len(r['nested_bq'])}): `> > **证明/例` nested "
              f"blockquotes detected — use single `>` level (proof inside example must "
              f"use `> **证明**`, not `> > **证明**`):")
        for g in r['nested_bq']:
            print(g)

    ex_gaps, ex_warns = r.get('ex_proof_gaps', ([], []))
    if ex_gaps:
        problems += 1
        print(f"\nG-LAYER EXAMPLE-PROOF GAP ({len(ex_gaps)}): example and its proof are NOT "
              f"in the same contiguous blockquote — remove empty lines between them so "
              f"the entire example+proof uses the same `>` level:")
        for g in ex_gaps:
            print(g)
    if ex_warns:
        print(f"\nG-LAYER EXAMPLE-PROOF WARN ({len(ex_warns)}): blank `>` line between "
              f"example and proof (visual spacing OK, but can be removed):")
        for w in ex_warns:
            print(w)

    # H-LAYER: structural label inside blockquote (blocking, always runs).
    h_bq = r.get('h_structural_bq', [])
    if h_bq:
        problems += 1
        print(f"\nH-LAYER STRUCTURAL BLOCKQUOTE ({len(h_bq)}): labels like "
              f"定义/定理/引理/推论/命题/断言/公理/Theorem/Definition/Lemma/Corollary/Proposition/Axiom "
              f"must be TOP-LEVEL (no `>` wrapper) — remove the `> ` prefix:")
        for g in h_bq:
            print(g)

    # H-LAYER ext (ISSUE1): a theorem/definition/lemma/...'s OWN statement content
    # (enumerated clauses, display formulas, sub-point lists) must be TOP-LEVEL —
    # only proof/example/note/footnote blocks belong in `>`. Blocking.
    h_stmt = r.get('h_stmt_bq', [])
    if h_stmt:
        problems += 1
        print(f"\nH-LAYER STATEMENT-IN-BLOCKQUOTE ({len(h_stmt)}): a definition/theorem/lemma/"
              f"corollary/proposition's STATEMENT content (`（N）` / `**（N）**` / `$$` / `- （a）` "
              f"inside the item, before any `> **证明/例/注`) must be TOP-LEVEL — unwrap those "
              f"`>` lines. `>` is reserved for proof/example/note/footnote only:")
        for g in h_stmt:
            print(g)

    # H-LAYER ext (unlabeled BQ): free-standing `>` blocks without a recognized
    # label (证明/证/例/注/说明/脚注). Blocking.
    h_ul = r.get('h_ul_bq', [])
    if h_ul:
        problems += 1
        print(f"\nH-LAYER UNLABELED BLOCKQUOTE ({len(h_ul)}): a `>` blockquote must start "
              f"with a recognized label (证明/证/例/注/说明/脚注). Found plain text in `>` "
              f"without any label — remove the `>` prefix or add a label:")
        for g in h_ul:
            print(g)

    # H-LAYER ext (missing BQ): labels that MUST be inside `>` but are at top level.
    h_mbq = r.get('h_mbq', [])
    if h_mbq:
        problems += 1
        print(f"\nH-LAYER MISSING BLOCKQUOTE ({len(h_mbq)}): labels like 证明/证/例/注/说明/注记 "
              f"must be wrapped in `>` — add `> ` prefix:")
        for g in h_mbq:
            print(g)

    # I-LAYER: item separator completeness (blocking, always runs).
    i_sep = r.get('i_sep_gaps', [])
    if i_sep:
        problems += 1
        print(f"\nI-LAYER MISSING SEPARATOR ({len(i_sep)}): consecutive items without `---` "
              f"between them — insert `---` (blank line + --- + blank line) between each pair:")
        for g in i_sep:
            print(g)

    # J-LAYER: any `---` INSIDE an item block (header ↔ sub-points) is a defect
    # (blocking, always runs). Covers BOTH a header split from its first `**(N)**`
    # sub-point AND `**(i)**` split from `**(i+1)**` — even when a sub-point spans
    # multiple lines (its continuation text / a `$$` formula sits directly above
    # the `---`). The `---` belongs *between* two top-level items (I-LAYER), never
    # inside one item's block — remove that `---`.
    j_hd = r.get('j_header_dash', [])
    if j_hd:
        problems += 1
        print(f"\nJ-LAYER HEADER-DASH ({len(j_hd)}): a `---` sits INSIDE an item block "
              f"(between the header and its first `**(N)**` sub-point, OR between two "
              f"`**(i)**`/`**(i+1)**` sub-points) — remove that `---` so the item's parts "
              f"stay directly connected (matching `**引理3.3**` … `(1)` … `(2)` style, "
              f"no `---` between them):")
        for g in j_hd:
            print(g)

    # K-LAYER: blank line between numbered list and proof blockquote.
    k_list = r.get('k_proof_list', [])
    if k_list:
        problems += 1
        print(f"\nK-LAYER PROOF-AFTER-LIST ({len(k_list)}): a `> **证明**` blockquote "
              f"directly follows a numbered list item without a blank line — add a "
              f"blank line so the proof aligns at the theorem's outer level:")
        for g in k_list:
            print(g)

    # L-LAYER: blank lines around `---` separators (blocking, always runs).
    l_sep = r.get('l_sep_blanks', [])
    if l_sep:
        problems += 1
        print(f"\nL-LAYER SEPARATOR BLANK-LINES ({len(l_sep)}): every `---` separator "
              f"must have a blank line immediately before AND after it — "
              f"insert missing blank line(s):")
        for g in l_sep:
            print(g)

    # M-LAYER: `>` lines inside display math blocks.
    m_dm = r.get('m_dm_gt', [])
    if m_dm:
        problems += 1
        print(f"\nM-LAYER DISPLAYMATH-GT ({len(m_dm)}): `>` lines found inside "
              f"`$$...$$` display math blocks — strip the blockquote prefix from "
              f"these lines:")
        for g in m_dm:
            print(g)

    # N-LAYER: excessive empty `>` lines inside blockquotes.
    n_bq = r.get('n_bq_empty', [])
    if n_bq:
        problems += 1
        print(f"\nN-LAYER BQ-EMPTY-LINES ({len(n_bq)}): excessive consecutive empty "
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

    if problems:
        print(f"\nFAIL: {len(r['truly_missing'])} truly missing / {len(r['blocking'])} B-layer blocking "
              f"/ {len(r['katex_lines'])} KaTeX / {len(d['missing_sections'])} D-layer missing sections "
              f"/ {len(r.get('fig_missing', []))} fig-missing / {len(r.get('fig_invalid', []))} fig-invalid "
              f"/ {len(r.get('quote_gaps', []))} quote-gaps / {len(r.get('nested_bq', []))} nested-bq "
              f"/ {len(ex_gaps)} ex-proof-gap / {len(h_bq)} h-layer-struct-bq "
              f"/ {len(h_stmt)} h-layer-stmt-bq "
              f"/ {len(i_sep)} i-layer-sep / {len(j_hd)} j-layer-header-dash "
              f"/ {len(k_list)} k-layer-proof-list / {len(l_sep)} l-layer-sep-blanks "
              f"/ {len(m_dm)} m-layer-dm-gt / {len(n_bq)} n-layer-bq-empty "
              f"/ {len([g for g in o_gaps if g.strip().startswith('x')])} o-layer-subitem "
              f"— {os.path.basename(md)}")
        return 'FAIL'
    else:
        print(f"\nPASS: {os.path.basename(md)} (entries={len(r['entry_keys'])}, mentioned-only={len(r['mentioned_only'])})")
        return 'PASS'
