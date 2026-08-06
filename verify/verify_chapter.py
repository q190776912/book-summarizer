"""
verify_chapter.py — the single MANDATORY gate for a chapter. It enforces ALL
completeness/validity layers in one command.

All verification layers live as independent modules under `verify/layers/`,
registered in `verify/register_all.py` and orchestrated by
`verify/layers/base.VerifyManager`.  This file is now a THIN SHELL:

  * The authoritative layer REGISTRY (ordered list, --fix scope) is
    `references/verification.md` (SSOT).  Per-layer semantics / thresholds /
    byte-contract live in `references/layers/<code>.md` — do NOT duplicate
    them here.  Run order == each layer's `order` attribute (auto-discovered).
  * Configuration is read ONCE by `lib.config.ConfigLoader` (the single source
    of truth for verify_config.json + chapter_map.json + figure_index.json +
    per-chapter ignore/manual files).  Layers read config through their
    VerifyContext; nothing is passed field-by-field anymore (`disable` /
    `scheme` / `ignore_*` passthrough are gone).
  * `verify_one(...)` delegates to `VerifyManager.verify_one(...)`, which returns
    the SAME byte-compatible result dict the old inline implementation produced
    (so `report.print_result`, `verify_all` and `main` are unchanged).
  * `--fix` calls `fix_all_layers(md)`, a backward-compatible shim that delegates
    to `VerifyManager.fix(...)`, returning the same {h,h_stmt,h_ul,h_mbq,g,i,j,k,l,m,n}
    change dict.

Exit 0 only when there is NO truly-missing item AND NO B-layer blocking issue
AND NO KaTeX error AND (if figure_index.json present) NO missing-figure gap AND
NO invalid figure AND NO quote-block continuity gap (G-layer).
Referenced by Step 4 校验 #0.
"""
import sys, os, json, glob, re

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.config import ConfigLoader
from verify.layers.base import VerifyManager
from verify.register_all import LAYER_REGISTRY
from verify.report import print_result
# --ignore / --ignore-figure loaders (relocated; no longer import fig_layers).
from verify.ignore_files import load_ignore, load_ignore_fig


def _section_num_from_filename(fn):
    """Extract the section number (as str) from a split section filename.

    Section files follow the rule-D naming: `第{N}章{M}{名称}.md` (zh) or
    `Chapter{N}_{M}{名称}.md` (en), where {M} is the section id (digits,
    possibly with a single dot for N.M style). Returns None if the name is
    not a section file (e.g. the merged 第N章_*.md / ChapterN_*.md file).
    """
    base = os.path.basename(fn)
    m = None
    if base.startswith('第') and '章' in base:
        m = re.match(r'^第\d+章([\d.]+)', base)
    else:
        m = re.match(r'^Chapter\d+_([\d.]+)', base)
    if not m:
        return None
    sec = m.group(1)
    if not sec or sec.endswith('.'):
        return None
    return sec


def chapter_md_groups(book_dir, ch):
    """Return per-language verification groups for chapter `ch`.

    A group is a list of .md files that together form one language's full
    chapter: either the single merged file (第N章_*.md / ChapterN_*.md if it
    still exists) or the rule-D section files sorted by section number.
    Returns [] if none found.
    """
    groups = []
    for merged_pat, sec_pat in (
        (f'第{ch}章_*.md', f'第{ch}章*.md'),       # zh
        (f'Chapter{ch}_*.md', f'Chapter{ch}_*.md'),  # en
    ):
        merged = [f for f in glob.glob(os.path.join(book_dir, merged_pat))
                  if _section_num_from_filename(f) is None]
        if merged:
            groups.append(sorted(merged))
            continue
        sec = [(f, _section_num_from_filename(f))
               for f in glob.glob(os.path.join(book_dir, sec_pat))]
        sec = [(f, n) for f, n in sec if n is not None]
        if not sec:
            continue
        sec.sort(key=lambda x: tuple(int(p) for p in x[1].split('.')))
        groups.append([f for f, n in sec])
    return groups


def _merge_section_files(section_files):
    """Merge section files back into one full-chapter content string."""
    merged_lines = []
    title_seen = False
    for i, fp in enumerate(section_files):
        with open(fp, encoding='utf-8-sig') as f:
            lines = f.read().split('\n')
        for j, line in enumerate(lines):
            if j == 0 and line.startswith('# ') and not title_seen:
                merged_lines.append(line)
                title_seen = True
                continue
            if j == 0 and line.startswith('# ') and title_seen:
                continue
            merged_lines.append(line)
    return '\n'.join(merged_lines).rstrip('\n') + '\n'


def _merged_temp_path(book_dir, ch, section_files):
    """Write merged chapter content to a temp file and return its path."""
    tmp = os.path.join(book_dir, f'._verify_merged_ch{ch}.md')
    with open(tmp, 'w', encoding='utf-8') as f:
        f.write(_merge_section_files(section_files))
    return tmp


def _make_loader(ext, book_dir, extra_ignore=None):
    """Construct the single ConfigLoader (config source of truth)."""
    return ConfigLoader(ext, book_dir or os.path.dirname(ext) or ext,
                        extra_ignore=extra_ignore)


def verify_one(ch, start, end, md, ext, book_dir=None, extra_ignore=None):
    """Verify a single chapter. Returns the byte-compatible result dict.

    All configuration is read by a ConfigLoader built from <ext>/<book_dir>;
    no config is passed field-by-field.
    """
    loader = _make_loader(ext, book_dir, extra_ignore=extra_ignore)
    mgr = VerifyManager(LAYER_REGISTRY, loader)
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
    with open(fp, encoding='utf-8') as f:
        data = json.load(f)
    text_blocks = data.get('text', [])
    item_text = detail['text']
    for block in text_blocks:
        txt = block.get('text', '')
        if item_text[:30] in txt:
            return txt.strip()[:200]
    return None


def verify_all(ext, book_dir, extra_ignore=None):
    """Verify all chapters using chapter_map.json (read by ConfigLoader).
    Returns True if all pass."""
    loader = _make_loader(ext, book_dir, extra_ignore=extra_ignore)
    if not loader.chapters:
        cm_path = os.path.join(ext, 'chapter_map.json')
        print(f"ERROR: chapter_map.json not found / empty at {cm_path}")
        return False

    results = []
    for info in sorted(loader.chapters.values(), key=lambda c: c.ch):
        ch = info.ch
        start, end = info.start, info.end

        groups = chapter_md_groups(book_dir, ch)
        if not groups:
            print(f"Ch{ch}: SKIP — no .md file found")
            continue

        for grp in groups:
            if len(grp) == 1:
                md = grp[0]
                md_display = os.path.basename(md)
            else:
                md = _merged_temp_path(book_dir, ch, grp)
                md_display = (f"{os.path.basename(grp[0]).split('_')[0]}_"
                              f"合并{len(grp)}节")
            try:
                r = verify_one(ch, start, end, md, ext, book_dir,
                               extra_ignore=extra_ignore)
            finally:
                if len(grp) > 1:
                    try:
                        os.remove(md)
                    except OSError:
                        pass
            print(f"--- Chapter {ch}: {md_display} ---")
            status = print_result(r)
            r['status'] = status
            r['md'] = md_display
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
        if i + 1 < len(sys.argv) and not sys.argv[i + 1].startswith('-'):
            return sys.argv[i + 1]
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


def fix_all_layers(md_file, book_dir=None):
    """Deprecated shim → VerifyManager.fix. Kept for backward-compatible callers
    (main / --fix). Returns the same change dict as the old fix_all_layers."""
    ext = os.path.join(book_dir, '_extract') if book_dir else os.path.dirname(md_file)
    book_dir = book_dir or os.path.dirname(md_file)
    loader = _make_loader(ext, book_dir)
    mgr = VerifyManager(LAYER_REGISTRY, loader)
    return mgr.fix(md_file)


def main():
    ignore_path = _flag_value('--ignore')
    ignore_keys = load_ignore(ignore_path)
    ignore_fig_global = load_ignore_fig(_flag_value('--ignore-figure'))
    extra_ignore = list(ignore_keys) + list(ignore_fig_global)

    # Apply --fix flag (auto-correct G/H/I layers) before verification
    if '--fix' in sys.argv:
        if '--all' not in sys.argv:
            args_fix = _strip_flags(sys.argv[1:], ('--manual', '--ignore', '--ignore-figure', '--fix'))
            if len(args_fix) >= 4:
                md_file = args_fix[3]
                ext_fix = args_fix[4] if len(args_fix) > 4 else None
                book_dir_fix = os.path.dirname(ext_fix) if ext_fix else None
                print(f"[FIX] Auto-correcting layers on {os.path.basename(md_file)}...")
                res = fix_all_layers(md_file, book_dir=book_dir_fix)
                parts = [f"{k}={v}" for k, v in res.items() if v > 0]
                if parts:
                    print(f"[FIX] Applied: {', '.join(parts)}")
                else:
                    print(f"[FIX] No changes needed")

    # --all mode: verify all chapters
    if '--all' in sys.argv:
        # NOTE: '--fix' is a no-value flag (handled via `if '--fix' in sys.argv`
        # below), so it must NOT be in this tuple — otherwise _strip_flags would
        # consume the token after it (e.g. '--all') as a "value" and drop it.
        pos_flags = ('--manual', '--ignore', '--ignore-figure')
        pos = _strip_flags(sys.argv[1:], pos_flags)
        # Strip the no-value '--fix' flag from positional parsing (it is detected
        # separately via `if '--fix' in sys.argv` below). Keeps '--all' and the
        # two positional args intact regardless of --fix ordering.
        pos = [a for a in pos if a != '--fix']
        i = pos.index('--all')
        if i + 2 >= len(pos):
            print("Usage: python verify_chapter.py --all <extract_dir> <book_dir> [--ignore noise.json] [--ignore-figure fig_noise.json]")
            sys.exit(2)
        ext = pos[i + 1]
        book_dir = pos[i + 2]

        # Apply --fix to all chapters before verification
        if '--fix' in sys.argv:
            loader = _make_loader(ext, book_dir, extra_ignore=extra_ignore)
            chapters = loader.chapters
            if chapters:
                for info in sorted(chapters.values(), key=lambda c: c.ch):
                    for grp in chapter_md_groups(book_dir, info.ch):
                        for md_file in grp:
                            res = fix_all_layers(md_file, book_dir=book_dir)
                            parts = [f"{k}={v}" for k, v in res.items() if v > 0]
                            if parts:
                                print(f"[FIX] {os.path.basename(md_file)}: {', '.join(parts)}")
            else:
                for grp in _all_md_files(book_dir):
                    for md_file in grp:
                        res = fix_all_layers(md_file, book_dir=book_dir)
                        parts = [f"{k}={v}" for k, v in res.items() if v > 0]
                        if parts:
                            print(f"[FIX] {os.path.basename(md_file)}: {', '.join(parts)}")

        ok = verify_all(ext, book_dir, extra_ignore=extra_ignore)
        sys.exit(0 if ok else 1)

    # Single-chapter mode — strip flags AND their values from positional args.
    fix_requested = '--fix' in sys.argv
    args = _strip_flags(sys.argv[1:], ('--manual', '--ignore', '--ignore-figure'))
    args = [a for a in args if a != '--fix']
    if len(args) < 5:
        print("Usage: python verify_chapter.py <ch> <start> <end> <md_file> <extract_dir> "
              "[--manual overrides.json] [--ignore noise.json] [--ignore-figure fig_noise.json]")
        print("       python verify_chapter.py --all <extract_dir> <book_dir> [--ignore noise.json] [--ignore-figure fig_noise.json]")
        print("  <extract_dir> is REQUIRED — the book's _extract folder (e.g. D:\\study\\book\\<书名>\\_extract).")
        print("  --manual: path to manual_overrides_ch{N}.json (added to extract_items items)")
        print("  --ignore: JSON list/dict of confirmed-noise keys (removed before A/B compare)")
        print("  --ignore-figure: JSON list/dict of confirmed-noise figure labels, e.g. [\"6.7.9\"]")
        print("  --fix: auto-correct G/H/I/J layer issues before verification")
        print("  ordinal / language / scope / separate_types / strict / ignore / manual are")
        print("  configured in <book>/_extract/verify_config.json (see references/verification.md).")
        sys.exit(2)

    manual_path = _flag_value('--manual')

    ch = int(args[0]); start = int(args[1]); end = int(args[2])
    md = args[3]
    ext = args[4]
    book_dir_single = os.path.dirname(ext) if ext else None

    if fix_requested:
        res = fix_all_layers(md, book_dir=book_dir_single)
        parts = [f"{k}={v}" for k, v in res.items() if v > 0]
        if parts:
            print(f"[FIX] Ch{ch}: {', '.join(parts)}")
    r = verify_one(ch, start, end, md, ext, book_dir_single, extra_ignore=extra_ignore)
    status = print_result(r)
    sys.exit(0 if status == 'PASS' else 1)


def _all_md_files(book_dir):
    """Yield (group_of_md_files) for every chapter present, for --fix --all."""
    import glob as _glob
    out = []
    for fn in sorted(_glob.glob(os.path.join(book_dir, '*.md'))):
        out.append([fn])
    return out


if __name__ == '__main__':
    main()
