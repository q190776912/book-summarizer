# -*- coding: utf-8 -*-
"""只读普查：B 层「疑似幽灵重复节点」WARN 行的跨语料现状（2026-10-03）。

动因：`item_numbering_integrity._md_gap_blocking` 的顺序校验把「保留首次去重后单调」
的同号二现一律报成幽灵重复节点（正文引用被误建为条目节点）。实测（Arnold《经典力学
的数学方法》4 行 / Katok 2 行）该形态里混着两类**印面合法的多计数器交错**：
  A. 节内字母子块重启（§8.D 的 问题1..6 与 §8.E 的 问题1..3，同一节号窗、不同 `### §X`）
  B. 合并组内跨类型各自起号（§9.2 的 Example 9.2.1 与 Proposition 9.2.1，同一 gk、不同标签）
收紧前必须先看清全网有多少行、各行属于哪一类，否则会把**真幻影**（Katok §1.1 的
第二个 定义1.1.1）一起放掉。

本工具只做三件事（🔴 不写任何书目录内容；多文件章按 verify 同口径合并到 verify 自己的
`._verify_merged_*` 临时视图，用完即按同一路径清理）：
  1. 逐书逐章取 B 层 blocking/warnings；
  2. 抽出含「疑似幽灵重复节点」的行；
  3. 对每行附带**逐次出现上下文**（条头标签、号、所在最深 § 标题）供人工归类 A/B/幻影。

用法：
    python tools/census_ghost_rows.py [--corpus DIR] [--filter 子串] [--json]
"""
import argparse
import bisect
import io
import json
import os
import re
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
import lib.boot as _boot          # noqa: E402
_boot.setup()

import item_numbering_integrity as ini      # noqa: E402
import verify_chapter as vc                 # noqa: E402
from base import ConfigLoader, VerifyContext  # noqa: E402
from lib.user_config import get as _uc_get    # noqa: E402

GHOST = u"疑似幽灵重复节点"

HEAD_RE = re.compile(r"^(#{2,4})[ \t]*§[ \t]*([^\n]*)$", re.M)


def _books(corpus, filt):
    out = []
    for sub in sorted(os.scandir(corpus), key=lambda e: e.name):
        if not sub.is_dir():
            continue
        for bk in sorted(os.scandir(sub.path), key=lambda e: e.name):
            if not bk.is_dir():
                continue
            ext = os.path.join(bk.path, "_extract")
            if not os.path.isdir(os.path.join(ext, "book_structure")):
                continue
            if not os.path.exists(os.path.join(ext, "verify_config.json")):
                continue
            if filt and filt.lower() not in bk.name.lower():
                continue
            out.append(bk.path)
    return out


def _anchors(txt):
    """(offsets, tokens) for EVERY `^##..#### §` heading（含字母子块）。"""
    pos, tok = [], []
    for m in HEAD_RE.finditer(txt):
        toks = (m.group(2) or "").strip().split()
        if not toks:
            continue
        pos.append(m.start())
        tok.append(toks[0].strip(":.,;")[:20])
    return pos, tok


def _context(md_file, prefix):
    """Head occurrences belonging to the row's window: (line, label, own-num,
    section-anchor, deepest-anchor, text).  scope-3 books print bare numbers
    (`**问题1**`) and carry the section only in the heading chain, so a head is
    attributed to the nearest **numeric** heading token (its `## §8`/`## §32`
    section) while the nearest heading of any kind is shown as the sub-block
    anchor — lettered `### §C` blocks are exactly what the restart classes turn on."""
    txt = io.open(md_file, encoding="utf-8").read()
    apos, atok = _anchors(txt)
    npos, ntok = [], []
    for p, t in zip(apos, atok):
        if re.match(r"^\d", t):
            npos.append(p)
            ntok.append(t)
    pref_show = prefix.split(":")[-1] if ":" in prefix else prefix
    out = []
    for m in re.finditer(r"^\s*>?\s*\*\*([^*]{1,90})\*\*", txt, re.M):
        inner = m.group(1).strip()
        lab = re.match(r"^([A-Za-z\u4e00-\u9fff]+)", inner)
        nums = re.findall(r"[0-9]+(?:\.[0-9]+)*", inner)
        if not nums:
            continue
        own = nums[0]
        i = bisect.bisect_right(apos, m.start()) - 1
        anchor = atok[i] if i >= 0 else "-"
        j = bisect.bisect_right(npos, m.start()) - 1
        sec = ntok[j] if j >= 0 else "-"
        if pref_show and pref_show not in ("<章级>", "-", ""):
            if not (sec == pref_show or own == pref_show or own.startswith(pref_show + ".")):
                continue
        tail = own.split(".")[-1]
        line = txt[:m.start()].count("\n") + 1
        out.append((line, lab.group(1) if lab else "uncat", tail, sec + "/" + anchor,
                    inner[:48]))
    return out


def ghost_rows(book_dir):
    ext = os.path.join(book_dir, "_extract")
    loader = ConfigLoader(ext, book_dir)
    loader.require_complete(allow_absent=False)
    rows = []
    for info in sorted(loader.chapters.values(), key=lambda c: str(c.ch)):
        ch = info.ch
        groups = vc.chapter_md_groups(book_dir, ch)
        for grp in groups or []:
            md = grp[0]
            if len(grp) > 1:
                md = vc._merged_temp_path(book_dir, ch, grp)
            try:
                cfg = loader.config_for_chapter(ch)
                ctx = VerifyContext(ch=ch, start=info.start, end=info.end,
                                    md_file=md, ext_dir=ext, config=cfg,
                                    figure_index=loader.figure_index,
                                    manual_overrides=loader.manual_for_chapter(ch))
                blocking, warnings, _present, _tail, _g = ini._md_gap_blocking(ctx)
            except Exception as e:
                rows.append({"book": os.path.basename(book_dir), "ch": str(ch),
                             "md": os.path.basename(grp[0]), "error": str(e)})
                continue
            finally:
                if len(grp) > 1 and os.path.exists(md):
                    os.remove(md)
            for w in warnings or []:
                if GHOST in w:
                    m = re.search(r"@(\S+?) \[gk=(\S+?)\]: 同号二现 \[([^\]]*)\]", w)
                    pref = m.group(1) if m else "?"
                    gk = m.group(2) if m else "?"
                    dups = [d.strip() for d in (m.group(3).split(",") if m else [])]
                    rows.append({"book": os.path.basename(book_dir), "ch": str(ch),
                                 "md": os.path.basename(grp[0]), "prefix": pref,
                                 "gk": gk, "dups": dups,
                                 "blocking": sum(1 for b in blocking or []
                                                 if "顺序错乱" in b)})
                    if len(grp) > 1:
                        md2 = vc._merged_temp_path(book_dir, ch, grp)
                        try:
                            rows[-1]["ctx"] = _context(md2, pref)
                        finally:
                            if os.path.exists(md2):
                                os.remove(md2)
                    else:
                        rows[-1]["ctx"] = _context(grp[0], pref)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--filter", default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    corpus = args.corpus or _uc_get("corpus_root")
    books = _books(corpus, args.filter)
    print("corpus=%s  books=%d" % (corpus, len(books)))
    all_rows, skipped = [], []
    for b in books:
        try:
            rows = ghost_rows(b)
        except Exception as e:
            skipped.append((os.path.basename(b), str(e)[:120]))
            continue
        for r in rows:
            all_rows.append(r)
        if any("error" not in r for r in rows):
            print("\n### %s" % os.path.basename(b))
            for r in rows:
                if "error" in r:
                    print("  ch%s ERROR %s" % (r["ch"], r["error"][:90]))
                    continue
                print("  ch%-4s %-30s @%-8s gk=%-12s dups=%s blocking_rows=%s"
                      % (r["ch"], r["md"][:30], r["prefix"], r["gk"], r["dups"],
                         r["blocking"]))
                for line, lab, num, anchor, inner in (r.get("ctx") or []):
                    print("        L%-6d lab=%-10s n=%-4s §%-6s | %s"
                          % (line, lab, num, anchor, inner))
    print("\nTOTAL ghost rows=%d  books scanned=%d  skipped=%d"
          % (len(all_rows), len(books), len(skipped)))
    for name, err in skipped:
        print("  SKIP %s : %s" % (name, err))
    if args.json:
        io.open(os.path.join(_ROOT, "tools", "_census_ghost_rows.json"),
                "w", encoding="utf-8").write(json.dumps(all_rows, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
