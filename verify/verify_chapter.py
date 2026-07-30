"""
verify_chapter.py — the single MANDATORY gate for a chapter. It enforces ALL
completeness/validity layers in one command.

REFACTOR (ADR-VERIFY-001): the ~16 layers (EXTRACT/D/A/B/C/E/F/G/H/I/J/K/L/M/N/O)
now live as independent modules under `verify/layers/`, registered in
`verify/register_all.py` and orchestrated by `verify/registry.VerifyManager`.
This file is now a THIN SHELL:

  * `verify_one(...)` builds a per-chapter ManagerConfig and delegates to
    `VerifyManager.verify_one(...)`, which returns the SAME byte-compatible
    result dict the old inline implementation produced (so `report.print_result`,
    `verify_all` and `main` are unchanged).
  * `--fix` calls `fix_all_layers(md)`, a backward-compatible shim that delegates
    to `VerifyManager.fix(...)`, returning the same {h,h_stmt,h_ul,h_mbq,g,i,j,k,l,m,n}
    change dict.

Layer order / fix order (stable codes):
  EXTRACT 0, D 1, A 2, B 3, C 4, E 5, F 6, G 7 (fix 5), H 8 (fix 1),
  I 9 (fix 6), J 10 (fix 7), K 11 (fix 8), L 12 (fix 9), M 13 (fix 10),
  N 14 (fix 11), O 15.

Exit 0 only when there is NO truly-missing item AND NO B-layer blocking issue AND
NO KaTeX error AND (if figure_index.json present) NO missing-figure gap AND NO
invalid figure AND NO quote-block continuity gap (G-layer).
Referenced by Step 4 校验 #0.
"""
import sys, os, json, glob

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# New registry / manager / layers.
from verify.registry import VerifyManager, ManagerConfig
from verify.register_all import LAYER_REGISTRY
# Result printing / summary formatting lives in verify.report (unchanged).
from verify.report import print_result
# --ignore / --ignore-figure loaders (relocated; no longer import fig_layers).
from verify.ignore_files import load_ignore, load_ignore_fig


def verify_one(ch, start, end, md, ext, manual_path, ignore_keys=None, scheme='three-level', ignore_fig=None, disabled=None):
    """Verify a single chapter. Returns the byte-compatible result dict.

    Delegates all layer execution to VerifyManager, which merges each layer's
    metadata into the legacy verify_one contract (see registry.py).
    `disabled` is an optional iterable of layer codes (e.g. {"O"}) to skip —
    normally wired from <book_dir>/verify_config.json by verify_all.
    """
    cfg = ManagerConfig(
        scheme=scheme,
        ignore_keys=ignore_keys or set(),
        ignore_fig=ignore_fig or set(),
        manual_path=manual_path,
        disabled=set(disabled) if disabled else set(),
    )
    mgr = VerifyManager(LAYER_REGISTRY, cfg)
    return mgr.verify_one(ch, start, end, md, ext)


def _lookup_item_detail(key, items):
    """Look up an item by key in the extracted items list.
    Returns dict with label, page, text (first 150 chars), or None."""
    for it in items:
        if it['key'] == key:
            return {
                'label': it.get('label', ''),
                'page': it.get('page', '?'),
                'text': it.get('text', '').strip()[:150]
            }
    return None


def _load_page_context(ext, ch, key, items):
    """Try to find the page JSON and return surrounding lines for a missing item."""
    detail = _lookup_item_detail(key, items)
    if not detail or detail['page'] == '?':
        return None
    try:
        pg = int(detail['page'])
    except ValueError:
        return None
    fp = os.path.join(ext, f'page_{pg:03d}.json')
    if not os.path.exists(fp):
        return None
    data = json.load(open(fp, encoding='utf-8'))
    text_blocks = data.get('text', [])
    item_text = detail['text']
    # Find block containing the item text
    for block in text_blocks:
        txt = block.get('text', '')
        if item_text[:30] in txt:
            return txt.strip()[:200]
    return None


def verify_all(ext, book_dir, ignore_keys=None, ignore_fig=None, scheme_override=None):
    """Verify all chapters using chapter_map.json. Returns True if all pass.

    scheme_override: if set ('two-level'/'en'/...), forces this scheme for
    EVERY chapter, overriding any per-chapter scheme read from chapter_map.json.
    Useful for whole-English books where chapter_map.json has no scheme field.
    """
    ignore_keys = ignore_keys or set()
    ignore_fig = ignore_fig or set()
    book_cfg = ManagerConfig.load_book_config(book_dir)
    cm_path = os.path.join(ext, 'chapter_map.json')
    if not os.path.exists(cm_path):
        print(f"ERROR: chapter_map.json not found at {cm_path}")
        return False

    with open(cm_path, 'r', encoding='utf-8') as f:
        cm = json.load(f)

    # Support multiple chapter_map formats:
    # 1. Flat dict: {"1": {"start": 1, "end": 30, ...}, "2": ...}
    # 2. Nested list: {"chapters": [{"num": 1, "start_page": 1, "end_page": 30}, ...]}
    # 3. Bare list: [{"ch": 1, "start": 5, "end": 21, ...}, ...]
    def _norm_entry(e):
        if not isinstance(e, dict):
            return None
        num = e.get('num', e.get('ch'))
        sp = e.get('start_page', e.get('pdf_start', e.get('start')))
        ep = e.get('end_page', e.get('pdf_end', e.get('end')))
        if num is None or sp is None or ep is None:
            return None
        try:
            num_i = int(num)
        except (ValueError, TypeError):
            # Non-numeric chapter id (e.g. appendix "A") — cannot be verified
            # by the 第N章 filename convention; skip gracefully.
            print(f"[SKIP] chapter '{num}': non-numeric chapter id (appendix?), not verified")
            return None
        return {'num': num_i, 'start_page': int(sp), 'end_page': int(ep),
                'scheme': e.get('scheme', 'three-level')}

    if isinstance(cm, list):
        ch_entries = [x for x in (_norm_entry(e) for e in cm) if x]
    elif isinstance(cm, dict):
        chapters = cm.get('chapters', None)
        if chapters is not None:
            ch_entries = [x for x in (_norm_entry(e) for e in chapters) if x]
        else:
            ch_entries = [{'num': int(k), 'start_page': v['start'], 'end_page': v['end'],
                           'scheme': v.get('scheme', 'three-level')}
                          for k, v in cm.items() if k.lstrip('-').isdigit()]
    else:
        ch_entries = []

    results = []
    for entry in ch_entries:
        ch = entry['num']
        start, end = entry['start_page'], entry['end_page']
        scheme = scheme_override or entry.get('scheme', 'three-level')

        # Find matching .md file
        md_pattern = os.path.join(book_dir, f'第{ch}章_*.md')
        md_files = glob.glob(md_pattern)
        if not md_files:
            print(f"Ch{ch}: SKIP — no .md file found")
            continue

        md = md_files[0]
        manual_path = os.path.join(ext, f'manual_overrides_ch{ch}.json')
        # Per-chapter ignore file (ignore_ch{N}.json) auto-detected, merged with
        # any global --ignore set passed in.
        ch_ignore = load_ignore(os.path.join(ext, f'ignore_ch{ch}.json'))
        # Per-chapter figure ignore file (ignore_fig_ch{N}.json) auto-detected,
        # merged with any global --ignore-figure set (figure completeness layer).
        ch_ignore_fig = load_ignore_fig(os.path.join(ext, f'ignore_fig_ch{ch}.json'))
        r = verify_one(ch, start, end, md, ext, manual_path,
                       ignore_keys=ignore_keys | ch_ignore, scheme=scheme,
                       ignore_fig=ignore_fig | ch_ignore_fig,
                       disabled=book_cfg.disabled)
        print(f"--- Chapter {ch}: {os.path.basename(md)} ---")
        status = print_result(r)
        r['status'] = status
        results.append(r)
        print()

    # Summary
    print("=" * 60)
    print("SUMMARY:")
    all_pass = True
    for r in results:
        status = r['status']
        if status != 'PASS':
            all_pass = False
        tm = len(r['truly_missing'])
        bl = len(r['blocking'])
        ke = len(r['katex_lines'])
        dmiss = len(r['d_layer']['missing_sections'])
        dtail = len(r['d_layer']['tail_gaps'])
        dsus = len(r['d_layer']['suspect'])
        fgmiss = '-' if r.get('fig_skipped') else len(r.get('fig_missing', []))
        fginv = '-' if r.get('fig_skipped') else len(r.get('fig_invalid', []))
        ggaps = len(r.get('quote_gaps', []))
        epg = len(r.get('ex_proof_gaps', [[]])[0]) if r.get('ex_proof_gaps') else 0
        hbq = len(r.get('h_structural_bq', []))
        hstmt = len(r.get('h_stmt_bq', []))
        hul = len(r.get('h_ul_bq', []))
        hmbq = len(r.get('h_mbq', []))
        isp = len(r.get('i_sep_gaps', []))
        jsp = len(r.get('j_header_dash', []))
        ksp = len(r.get('k_proof_list', []))
        lsp = len(r.get('l_sep_blanks', []))
        mdm = len(r.get('m_dm_gt', []))
        nbq = len(r.get('n_bq_empty', []))
        osub = len([g for g in r.get('o_subitem_gaps', []) if g.strip().startswith('x')])
        print(f"  Ch{r['ch']:2d}: {status:4s}  M:{tm} B:{bl} K:{ke} Dmiss:{dmiss} Dtail:{dtail} Dsus:{dsus} "
              f"FgMiss:{fgmiss} FgInv:{fginv} G:{ggaps} EG:{epg} H:{hbq} Hstmt:{hstmt} Hul:{hul} Hmbq:{hmbq} I:{isp} J:{jsp} K:{ksp} L:{lsp} Mdm:{mdm} Nbq:{nbq} Osub:{osub}  {os.path.basename(r['md'])}")

    pass_count = sum(1 for r in results if r['status'] == 'PASS')
    print(f"\nPASS: {pass_count}/{len(results)}")
    return all_pass


def _flag_value(flag):
    """Return the value following `flag` on the command line, or None."""
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv) and not sys.argv[i+1].startswith('-'):
            return sys.argv[i+1]
    return None


def _strip_flags(argv, flags_with_value):
    """Drop each flag token and its following value from argv (positional parse)."""
    out = []
    skip = False
    for a in argv:
        if skip:
            skip = False
            continue
        if a in flags_with_value:
            skip = True
            continue
        out.append(a)
    return out


def fix_all_layers(md_file, disabled=None):
    """Deprecated shim → VerifyManager.fix. Kept for backward-compatible callers
    (main / --fix). Returns the same change dict as the old fix_all_layers.
    `disabled` optionally skips layers (per-book verify_config.json)."""
    mgr = VerifyManager(LAYER_REGISTRY, ManagerConfig(disabled=set(disabled) if disabled else set()))
    return mgr.fix(md_file)


def main():
    ignore_path = _flag_value('--ignore')
    ignore_keys = load_ignore(ignore_path)
    ignore_fig_global = load_ignore_fig(_flag_value('--ignore-figure'))

    # Apply --fix flag (auto-correct G/H/I layers) before verification
    if '--fix' in sys.argv:
        # Single-chapter: fix the md file directly
        if '--all' not in sys.argv:
            args_fix = _strip_flags(sys.argv[1:], ('--manual', '--ignore', '--scheme', '--ignore-figure', '--fix'))
            if len(args_fix) >= 4:
                md_file = args_fix[3]
                ext_fix = args_fix[4] if len(args_fix) > 4 else None
                book_dir_fix = os.path.dirname(ext_fix) if ext_fix else None
                disabled_fix = ManagerConfig.load_book_config(book_dir_fix).disabled if book_dir_fix else set()
                print(f"[FIX] Auto-correcting layers on {os.path.basename(md_file)}...")
                res = fix_all_layers(md_file, disabled=disabled_fix)
                parts = [f"{k}={v}" for k, v in res.items() if v > 0]
                if parts:
                    print(f"[FIX] Applied: {', '.join(parts)}")
                else:
                    print(f"[FIX] No changes needed")

    # --all mode: verify all chapters
    if '--all' in sys.argv:
        pos_flags = ('--manual', '--ignore', '--scheme', '--ignore-figure', '--fix')
        pos = _strip_flags(sys.argv[1:], pos_flags)
        i = pos.index('--all')
        if i + 2 >= len(pos):
            print("Usage: python verify_chapter.py --all <extract_dir> <book_dir> [--ignore noise.json] [--ignore-figure fig_noise.json] [--scheme two-level|three-level|en]")
            sys.exit(2)
        ext = pos[i + 1]
        book_dir = pos[i + 2]
        scheme_override = _flag_value('--scheme')

        # Apply --fix to all chapters before verification
        if '--fix' in sys.argv:
            cm_path = os.path.join(ext, 'chapter_map.json')
            if os.path.exists(cm_path):
                with open(cm_path, 'r', encoding='utf-8') as f:
                    cm = json.load(f)
                if isinstance(cm, list):
                    chapters = cm
                elif isinstance(cm, dict):
                    chapters = cm.get('chapters', [])
                    if not chapters:
                        chapters = [{'num': int(k), 'start_page': v['start'], 'end_page': v['end']}
                                    for k, v in cm.items() if k.lstrip('-').isdigit()]
                else:
                    chapters = []
                for entry in chapters:
                    ch_num = entry.get('num') or entry.get('ch')
                    if ch_num is None:
                        continue
                    md_pattern = os.path.join(book_dir, f'第{int(ch_num)}章_*.md')
                    md_files = glob.glob(md_pattern)
                    if md_files:
                        res = fix_all_layers(md_files[0])
                        parts = [f"{k}={v}" for k, v in res.items() if v > 0]
                        if parts:
                            print(f"[FIX] Ch{ch_num}: {', '.join(parts)}")

        ok = verify_all(ext, book_dir, ignore_keys=ignore_keys, ignore_fig=ignore_fig_global,
                        scheme_override=scheme_override)
        sys.exit(0 if ok else 1)

    # Single-chapter mode — strip flags AND their values from positional args.
    # --fix is a BOOLEAN flag (no value): detect it, then drop it from the
    # positional list so it is NOT consumed as a value-taking flag.
    fix_requested = '--fix' in sys.argv
    args = _strip_flags(sys.argv[1:], ('--manual', '--ignore', '--scheme', '--ignore-figure'))
    args = [a for a in args if a != '--fix']
    if len(args) < 5:
        print("Usage: python verify_chapter.py <ch> <start> <end> <md_file> <extract_dir> "
              "[--manual overrides.json] [--ignore noise.json] [--ignore-figure fig_noise.json] [--scheme two-level|three-level]")
        print("       python verify_chapter.py --all <extract_dir> <book_dir> [--ignore noise.json] [--ignore-figure fig_noise.json]")
        print("  <extract_dir> is REQUIRED — the book's _extract folder (e.g. D:\\study\\book\\<书名>\\_extract).")
        print("  --manual: path to manual_overrides_ch{N}.json (added to extract_items items)")
        print("  --ignore: JSON list/dict of confirmed-noise keys (removed before A/B compare)")
        print("  --ignore-figure: JSON list/dict of confirmed-noise figure labels, e.g. [\"6.7.9\"]")
        print("  --scheme: 'three-level' (default) or 'two-level' (周民强型: 定义独立计数 +")
        print("           定理/引理/推论/命题共享计数器). Also auto-read from chapter_map.json.")
        print("  --fix: auto-correct G/H/I/J layer issues before verification")
        sys.exit(2)

    manual_path = _flag_value('--manual')
    scheme = _flag_value('--scheme') or 'three-level'

    ch = int(args[0]); start = int(args[1]); end = int(args[2])
    md = args[3]
    ext = args[4]

    # Auto-merge per-chapter ignore file (ignore_ch{N}.json) if present.
    ch_ignore = load_ignore(os.path.join(ext, f'ignore_ch{ch}.json'))
    ch_ignore_fig = load_ignore_fig(os.path.join(ext, f'ignore_fig_ch{ch}.json'))
    book_dir_single = os.path.dirname(ext) if ext else None
    disabled_single = ManagerConfig.load_book_config(book_dir_single).disabled if book_dir_single else set()
    if fix_requested:
        res = fix_all_layers(md, disabled=disabled_single)
        parts = [f"{k}={v}" for k, v in res.items() if v > 0]
        if parts:
            print(f"[FIX] Ch{ch}: {', '.join(parts)}")
    r = verify_one(ch, start, end, md, ext, manual_path,
                   ignore_keys=ignore_keys | ch_ignore, scheme=scheme,
                   ignore_fig=ignore_fig_global | ch_ignore_fig,
                   disabled=disabled_single)
    status = print_result(r)
    sys.exit(0 if status == 'PASS' else 1)


if __name__ == '__main__':
    main()
