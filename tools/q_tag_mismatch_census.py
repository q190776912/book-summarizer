r"""q_tag_mismatch_census.py — 跨书普查 Q 层「同号配错式」判据的命中量。

用途：`q_tag_mismatch`（`verify/formula_tag/script/tag_formula_pairing.py`）是 2026-10-03
新加的**非阻断 WARN** 判据。按本项目既定规程，任何判据的松紧必须先在整个语料上
普查校准（宁可先取证再执法），本工具就是那次普查：逐书逐章跑配对判据，按书打印
命中数与明细，供人工判断阈值 `hi` / `min_body` 是否会把「内容改写」误读成「配错号」。

用法：
    python tools/q_tag_mismatch_census.py <corpus_root> [--hi 0.80] [--min-body 12]
                                          [--book 子串] [--lang en|cn] [--verbose]

🔴 只读：不改任何文件、不写台账。
"""
import io
import json
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[1])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from lib.numbering import resolve_formula_type                      # noqa: E402
from chapter_map import load_chapter_records                        # noqa: E402
from tag_formula_pairing import (pairing_problems,                  # noqa: E402
                                 printed_tag_bodies)
from verify_chapter import chapter_md_groups                        # noqa: E402


def _book_dirs(corpus_root):
    for kind in os.listdir(corpus_root):
        shelf = os.path.join(corpus_root, kind)
        if not os.path.isdir(shelf):
            continue
        for name in sorted(os.listdir(shelf)):
            bd = os.path.join(shelf, name)
            if os.path.isdir(os.path.join(bd, "_extract")):
                yield bd


def _formula_for_kind(cfg, kind):
    block = cfg.get("ch") or {}
    if kind == 2:
        block = cfg.get("appendix") or block
    elif kind == 3:
        block = cfg.get("supplement") or block
    return block.get("formula")


def _ignore_for_chapter(ext, label, fblock):
    ign = set(str(x) for x in (fblock.get("ignore") or []))
    fp = os.path.join(ext, "ignore_%s.json" % label)
    if os.path.exists(fp):
        try:
            d = json.load(io.open(fp, encoding="utf-8"))
            if isinstance(d, list):
                ign |= {str(x) for x in d}
            elif isinstance(d, dict):
                ign |= {str(k) for k in d.keys()}
        except Exception:
            pass
    return ign


def census_book(book_dir, hi, min_body, only_lang=None, verbose=False):
    ext = os.path.join(book_dir, "_extract")
    cfp = os.path.join(ext, "verify_config.json")
    mfp = os.path.join(ext, "chapter_map.json")
    if not (os.path.exists(cfp) and os.path.exists(mfp)):
        return None
    cfg = json.load(io.open(cfp, encoding="utf-8"))
    if "ch" not in cfg:            # 老平铺格式：整体即正文配置
        cfg = {"ch": cfg}
    # 🔴 必须走 `chapter_map.iter_chapter_records` 的归一化通道：磁盘上有三种形态
    # （canonical `num` / legacy list `ch` / legacy flat dict），手写 `info.get("num")`
    # 会把 legacy 形态**整本静默跳过**并报 0 行——2026-10-04 实测：语料 51 本里
    # 只有 8 本用 canonical `num`，其余 30+ 本（含 Koopman，其 ch2/ch11/ch16 的
    # TAG_MISMATCH 在交付物里明明存在）全被读成 0，据此得出的「阈值安全」结论无效。
    chapters = load_chapter_records(mfp)
    out = []
    examined = 0
    skipped = []
    for info in chapters:
        ch = info.get("num")
        if ch is None:
            skipped.append("no-num")
            continue
        kind = int(info.get("kind") or 1)
        fblock = _formula_for_kind(cfg, kind)
        if not fblock or fblock.get("type") is None:
            skipped.append("%s:no-formula-cfg" % ch)
            continue
        lead, ncomp = resolve_formula_type(
            fblock.get("type"), letter_ch=bool(fblock.get("letter_ch")))
        ign = _ignore_for_chapter(ext, str(ch), fblock)
        start, end = info.get("start"), info.get("end")
        if start is None or end is None:
            skipped.append("%s:no-page-window" % ch)
            continue
        groups = list(chapter_md_groups(book_dir, ch))
        if not groups:
            skipped.append("%s:no-md" % ch)
            continue
        examined += 1
        for grp in groups:
            lang = "cn" if os.path.basename(grp[0]).startswith("第") else "en"
            if only_lang and lang != only_lang:
                continue
            printed = printed_tag_bodies(ext, ch, start, end, ncomp, lead)
            if len(printed) < 3:
                continue
            for md in grp:
                rows = pairing_problems(ext, ch, start, end, md, ncomp=ncomp,
                                        ignore=ign, lead=lead, hi=hi,
                                        min_body=min_body, printed=printed)
                for r in rows:
                    out.append((ch, lang, os.path.basename(md), r))
    census_book.last = (examined, len(chapters), skipped)
    return out


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    root = argv[0]
    hi, min_body, only_lang, verbose = 0.80, 12, None, ("--verbose" in argv)
    sub = None
    if "--hi" in argv:
        hi = float(argv[argv.index("--hi") + 1])
    if "--min-body" in argv:
        min_body = int(argv[argv.index("--min-body") + 1])
    if "--lang" in argv:
        only_lang = argv[argv.index("--lang") + 1]
    if "--book" in argv:
        sub = argv[argv.index("--book") + 1]
    total = 0
    books = 0
    seen_ch = 0
    skip_notes = []
    for bd in _book_dirs(root):
        if sub and sub.lower() not in bd.lower():
            continue
        books += 1
        try:
            rows = census_book(bd, hi, min_body, only_lang, verbose)
        except Exception as exc:
            print("!! %-60s 探针未跑成 %r" % (os.path.basename(bd), exc))
            continue
        if rows is None:
            continue
        ex, nch, skipped = getattr(census_book, "last", (0, 0, []))
        seen_ch += ex
        if ex < nch:
            skip_notes.append("%s: %d/%d 章有账, 跳过 %s"
                              % (os.path.relpath(bd, root), ex, nch,
                                 ",".join(skipped[:6]) + ("…" if len(skipped) > 6 else "")))
        n = len(rows)
        total += n
        if n or verbose:
            print("== %-60s %d" % (os.path.relpath(bd, root), n))
        if verbose:
            for ch, lang, md, r in rows:
                print("   ch%s [%s] (%s) %s" % (ch, lang, r["number"],
                                                r["source_text"]))
    print("\ncensus: %d books, %d 章实际有账, %d TAG_MISMATCH rows "
          "(hi=%.2f min_body=%d lang=%s)"
          % (books, seen_ch, total, hi, min_body, only_lang or "both"))
    for s in skip_notes:
        print("   [SKIP] %s" % s)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
