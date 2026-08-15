"""
verify_chapter.py — the single MANDATORY gate for a chapter. It enforces ALL
completeness/validity layers in one command.

All verification layers live as independent modules under `verify/`,
registered in `verify/script/register_all.py` and orchestrated by
`verify/base.VerifyManager`.  This file is now a THIN SHELL:

  * The authoritative layer REGISTRY (ordered list, --fix scope) is
    `verify/verify.md` (SSOT).  Per-layer semantics / thresholds /
    byte-contract live in `verify/<semantic_name>/<snake>.md` — do NOT duplicate
    them here.  Run order == each layer's `order` attribute (auto-discovered).
  * Configuration is read ONCE by `config.ConfigLoader` (the single source
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

import sys, os, json, glob, re


from verify_config import ConfigLoader, ConfigError
from verify.script.base import VerifyManager
from verify.script.register_all import LAYER_REGISTRY
from verify.script.report import print_result
# --ignore / --ignore-figure loaders.
from verify.script.ignore_files import load_ignore, load_ignore_fig


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
    """Construct the single ConfigLoader (config source of truth).

    Enforces the mandatory book-config gate (config_setting 流程 规则1) before
    any verification: a **missing** config file is treated as a hard error
    (``allow_absent=False`` -> raise ConfigError -> exit 2), because per the
    rule "文件缺失不能用默认配置，必须重新配置" and "任何 verify 跑起来之前，
    配置必须完整". A present-but-incomplete config (no ordinal / invalid
    section hierarchy) also raises ConfigError.  All verify call sites
    (verify_one / verify_all / fix_all_layers / --all --fix) route through this
    helper, so the gate is applied uniformly.  (scan_skeleton uses its own
    ``require_complete(allow_absent=True)`` warn+default safety net — that is a
    deliberate carve-out, not a verify path.)
    """
    loader = ConfigLoader(ext, book_dir or os.path.dirname(ext) or ext,
                          extra_ignore=extra_ignore)
    loader.require_complete(allow_absent=False)
    return loader


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
        data = PageJson.load(os.path.join(ext, f'page_{pg:03d}.json')).data
    text_blocks = data.get('text', [])
    item_text = detail['text']
    for block in text_blocks:
        txt = block.get('text', '')
        if item_text[:30] in txt:
            return txt.strip()[:200]
    return None


def _write_formula_audit(ext, rows):
    """Aggregate Q-LAYER audit rows across chapters into <ext>/formula_audit.md.

    Machine only checks sequence-label structure; formula CONTENT correctness is
    left to human reconciliation via the side-by-side summary/source dump.
    """
    path = os.path.join(ext, 'formula_audit.md')
    fab = [r for r in rows if r.get('status') == 'FABRICATED']
    inc = [r for r in rows if r.get('status') == 'INCONSISTENT']
    miss = [r for r in rows if r.get('status') == 'MISSING']
    lines = [
        "# 公式序标对账报告（Formula Sequence-Label Audit）\n",
        "> 由 verify Q 层（verify_config.json 配置 `formula` map 时启用）生成。机器仅做**序标结构**校验"
        "（编造/错位/跨章/遗漏）；公式**内容正确性**请人工对账（本报告并排给出"
        "总结 LaTeX 与书源文本片段）。\n",
        "## 汇总\n",
        f"- 对账行数: {len(rows)}",
        f"- 编造 FABRICATED: {len(fab)}",
        f"- 不一致 INCONSISTENT: {len(inc)}",
        f"- 遗漏 MISSING: {len(miss)}",
        "",
        "## 明细\n",
        "| 序标(normalized) | 状态 | 总结公式LaTeX(截断60字) | 书源文本片段(截断60字) |",
        "|---|---|---|---|",
    ]
    for r in rows:
        number = (r.get('number') or '').replace('|', '\\|')
        status = r.get('status', '')
        sl = (r.get('summary_latex') or '').replace('|', '\\|')
        st = (r.get('source_text') or '').replace('|', '\\|')
        lines.append(f"| {number} | {status} | {sl} | {st} |")
    lines.append("")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
        print(f"\n[Q] formula_audit.md written -> {path}")
    except Exception as e:  # pragma: no cover - best-effort report
        print(f"\n[Q] WARNING: failed to write formula_audit.md: {e}")


def verify_all(ext, book_dir, extra_ignore=None):
    """Verify all chapters using chapter_map.json (read by ConfigLoader).
    Returns True if all pass."""
    loader = _make_loader(ext, book_dir, extra_ignore=extra_ignore)
    if not loader.chapters:
        cm_path = os.path.join(ext, 'chapter_map.json')
        print(f"ERROR: chapter_map.json not found / empty at {cm_path}")
        return False

    results = []
    # Q-LAYER audit aggregation (only meaningful when a chapter enabled the `formula` map).
    q_active = False
    all_q_rows = []
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
            if r.get('q_checked'):
                q_active = True
                all_q_rows.extend(r.get('q_rows', []) or [])
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
        dmiss = len(r['d_layer'].get('missing_sections', []))
        dcont = len(r['d_layer'].get('continuity_sections', []))
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
        # F-LAYER FORMAT 聚合（原 C/G/H/I/J/K/L/M/N 九层统一为代号 F）：
        # 所有格式子项 finding 数求和，单一 F 计数呈现。
        f_n = (ke + ggaps + epg + hbq + hstmt + hul + hmbq
               + isp + jsp + ksp + lsp + mdm + nbq)
        osub = len([g for g in r.get('o_subitem_gaps', []) if g.strip().startswith('x')])
        qf = len(r.get('q_fabricated', []) or [])
        qi = len(r.get('q_inconsistent', []) or [])
        qm = len(r.get('q_missing', []) or [])
        print(f"  Ch{r['ch']:2d}: {status:4s}  M:{tm} B:{bl} Dc:{dcont} Dmiss:{dmiss} "
              f"FgMiss:{fgmiss} FgInv:{fginv} F:{f_n} Osub:{osub} "
              f"QF:{qf}/{qi}/{qm}  {os.path.basename(r['md'])}")

    pass_count = sum(1 for r in results if r['status'] == 'PASS')
    print(f"\nPASS: {pass_count}/{len(results)}")

    # Q-LAYER formula audit report — only when some chapter enabled the `formula` map.
    if q_active and all_q_rows:
        _write_formula_audit(ext, all_q_rows)
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


def _run_ignore_audit(ext, chapter=None):
    """🔴 B 层（条目编号完整性）校验的强制最后一步，隶属 D/B 结构完整性域。

    作用域严格限定为 **编号 ignore**（B 层 item_numbering_integrity 消费的
    ignore / known_gaps / ignore_keys + 各 ignore_chN.json）。它**不是**对所有
    17 个校验层的全局末步：
      * Q 层公式豁免走独立命名空间 `formula.ignore`，不被本审计覆盖；
      * E 层图豁免走 `ignore_fig`，不被本审计覆盖。

    仅当被验证章节存在「编号 ignore 条目」时本步才生效（即"有 ignore 的 D/B
    校验流程"才需此步）；编号 ignore 为空时静默返回 0（审计对本次校验不适用）。
    返回 SUSPECT 数；>0 时校验流程不应 PASS（交由 agent 复核 / 补 manual_overrides）。
    """
    try:
        from verify.script.audit_ignore import run_audit, _print_report
    except Exception as e:
        print("\n[IGNORE-AUDIT] 跳过：无法导入 audit_ignore（%s）" % e)
        return 0
    rep = run_audit(ext, chapter)
    if rep["total"] == 0:
        # 无编号 ignore → 审计不在本次 D/B 校验作用域内，静默跳过（不污染其他层输出）。
        return 0
    print()
    print("[IGNORE-AUDIT] B 层(条目编号) ignore 条目 agent 审计（D/B 域强制最后一步）")
    _print_report(rep)
    return rep["suspect_count"]


def main():
    try:
        _main_impl()
    except ConfigError as e:
        # Mandatory book-config gate (rule H) failed — surface the message and
        # exit non-zero (exit 2) so the agent knows to fix verify_config.json.
        print(e)
        sys.exit(2)


def _main_impl():
    ignore_path = _flag_value('--ignore')
    ignore_keys = load_ignore(ignore_path)
    ignore_fig_global = load_ignore_fig(_flag_value('--ignore-figure'))
    extra_ignore = list(ignore_keys) + list(ignore_fig_global)

    # Apply --fix flag (auto-correct format-layer fixers: H/G/I/J/K/L/M/N, etc.) before verification
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
        # 🔴 强制最后一步：有 ignore 的校验流程收尾必须跑 agent 审计。
        suspect = _run_ignore_audit(ext)
        if suspect:
            ok = False
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
        print("  --fix: auto-correct format-layer fixer issues (H/G/I/J/K/L/M/N) before verification")
        print("  ordinal(数组) / language / strict / ignore / manual are")
        print("  configured in <book>/_extract/verify_config.json (see verify/verify.md).")
        print("  ordinal / section_types / section_depths 必须在 <book>/_extract/verify_config.json")
        print("  显式配置（缺失 ordinal 将直接报错 exit 2；缺失文件仅警告并沿用默认 ordinal=3）。")
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
    # 🔴 强制最后一步：有 ignore 的校验流程收尾必须跑 agent 审计。
    suspect = _run_ignore_audit(ext, ch)
    sys.exit(0 if (status == 'PASS' and suspect == 0) else 1)


def _all_md_files(book_dir):
    """Yield (group_of_md_files) for every chapter present, for --fix --all."""
    import glob as _glob
    out = []
    for fn in sorted(_glob.glob(os.path.join(book_dir, '*.md'))):
        out.append([fn])
    return out


if __name__ == '__main__':
    main()
