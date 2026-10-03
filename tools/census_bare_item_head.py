r"""census_bare_item_head.py — 跨书普查 Q 层「块首裸号 + 句点 = 条目/习题头」门禁的影响面。

用途：`SourceFormulaIndex._bare_item_head`（2026-10-03 根治；Katok 实测三条
ORDER_MISMATCH 假阳同源：`2.4.7. If f is close to Ek…` / `2.9.3. For w E S2 let…` /
`15.2.2. Given e > 0…` 抢到定义位置）把这种排版的命中**同时踢出书源集合 S 与位置
锚点**。风险方向不是误报而是**新造误报**：若某书的公式标签本身印成「行首裸号 +
句点」，该号从此不进 S → 总结里忠实的 `\tag` 反被误判 FABRICATED。

做法 = 同一页窗、同一配置，把真判据**开着 / 关着**各跑一遍现网扫描（`build` /
`build_sectioned`），只统计差集：
  S_LOST   关闭时有、开启后没了的号 —— 若总结给它挂了 `\tag`，就是一条新 FABRICATED
  ANCHOR_MOVED 定义位置锚点因门禁而后移的号 —— 门禁的**收益**（把假阳改回真标签）

用法：
    python tools/census_bare_item_head.py <corpus_root> [--book 子串] [--verbose]

🔴 只读：不改任何文件、不写台账（monkeypatch 只在探针进程内，不落盘）。
"""
import argparse
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
import lib.boot as _boot
_boot.setup()

from lib.numbering import resolve_formula_type                        # noqa: E402
from formula_tag import (SourceFormulaIndex, build_formula_patterns,    # noqa: E402
                         known_book_scopes, _TAG_RE,
                         _detect_summary_sections)
from verify_chapter import chapter_md_groups                          # noqa: E402

_GUARD = SourceFormulaIndex._bare_item_head


def _book_dirs(corpus_root):
    for kind in sorted(os.listdir(corpus_root)):
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


def _summary_tags(book_dir, ch):
    """该章交付 md（源/译任一）里出现过的 \tag 归一编号集合。"""
    out = set()
    for grp in chapter_md_groups(book_dir, ch):
        for md in grp:
            txt = io.open(md, encoding="utf-8", errors="replace").read()
            for m in _TAG_RE.finditer(txt):
                n = SourceFormulaIndex.norm(m.group(1))
                if n:
                    out.add(n)
    return out


def _scan(ext, ch, start, end, fblock, ncomp, lead, sections, guard_on):
    """跑一遍现网扫描，返回 (书源号集, {号: 定义位置})。"""
    SourceFormulaIndex._bare_item_head = staticmethod(
        _GUARD if guard_on else (lambda *a, **k: False))
    try:
        idx = SourceFormulaIndex(
            ext, build_formula_patterns(
                ncomp, allow_bare=bool(fblock.get('bare_number', True)),
                letter=(lead == 'letter'), lead=lead),
            False, set(str(x) for x in (fblock.get('ignore') or [])),
            ncomp=ncomp, keep_cross_refs=True,
            known_book=known_book_scopes(fblock))
        if sections:
            idx.build_sectioned(ch, start, end, sections, ncomp=ncomp)
        else:
            idx.build(ch, start, end)
        # 与 ORDER 支同一取数口径（`_compute_order_and_section`：sectioned 书用
        # `_pos_sec[(sec, n)]`，否则 `_primary_pos`），否则 `_primary_pos` 的
        # 强弱分级会把 `_pos_sec` 的变化全遮住。
        if sections:
            pos = {}
            for (_s, n), p in (getattr(idx, '_pos_sec', {}) or {}).items():
                cur = pos.get(n)
                _k = lambda t: (t[0], t[1] if t[1] is not None else -1)
                if cur is None or _k(p) < _k(cur):
                    pos[n] = p
        else:
            pos = dict(getattr(idx, '_primary_pos', {}))
        return set(idx.source_numbers()), pos
    finally:
        # 🔴 必须包成 staticmethod 再挂回：`Class.attr` 取到的是**裸函数**，
        # 直接赋值会让它变成实例方法（多绑一个 self → TypeError）。
        SourceFormulaIndex._bare_item_head = staticmethod(_GUARD)


def _md_sections(book_dir, ch):
    """该章的节键列表（scope=3 书才有意义）——用 Q 层同一节探测器实测。"""
    for grp in chapter_md_groups(book_dir, ch):
        txt = '\n\n'.join(io.open(md, encoding="utf-8", errors="replace").read()
                          for md in grp)
        try:
            secs, _f, _s = _detect_summary_sections(txt)
        except Exception:
            secs = []
        if secs:
            return secs
    return None


def census_book(book_dir, verbose=False):
    ext = os.path.join(book_dir, "_extract")
    cfp = os.path.join(ext, "verify_config.json")
    mfp = os.path.join(ext, "chapter_map.json")
    if not (os.path.exists(cfp) and os.path.exists(mfp)):
        return []
    cfg = json.load(io.open(cfp, encoding="utf-8"))
    if "ch" not in cfg:
        cfg = {"ch": cfg}
    cmap = json.load(io.open(mfp, encoding="utf-8"))
    chapters = cmap.get("chapters") or []
    if isinstance(chapters, dict):
        chapters = [dict(v, num=k) for k, v in chapters.items()]
    rows = []
    for info in chapters:
        ch, kind = info.get("num"), int(info.get("kind") or 1)
        fblock = _formula_for_kind(cfg, kind)
        start, end = info.get("start"), info.get("end")
        if ch is None or not fblock or fblock.get("type") is None or start is None:
            continue
        lead, ncomp = resolve_formula_type(
            fblock.get("type"), letter_ch=bool(fblock.get("letter_ch")))
        sections = _md_sections(book_dir, ch) if fblock.get("scope") == 3 else None
        try:
            off, pos_off = _scan(ext, ch, start, end, fblock, ncomp, lead,
                                 sections, False)
            on, pos_on = _scan(ext, ch, start, end, fblock, ncomp, lead,
                               sections, True)
        except Exception as exc:
            rows.append((ch, 'ERROR', '', '', repr(exc)))
            continue
        lost = off - on
        if lost:
            tags = _summary_tags(book_dir, ch)
            for n in sorted(lost):
                rows.append((ch, 'S_LOST', n, n in tags,
                             '总结%s \\tag{%s}' % ('有' if n in tags else '无', n)))
        moved = [(n, pos_off[n], pos_on[n]) for n in sorted(pos_off)
                 if n in pos_on and pos_off[n] != pos_on[n]]
        for n, a, b in moved:
            rows.append((ch, 'ANCHOR_MOVED', n, '', '%s -> %s' % (a, b)))
        if verbose:
            print('   ch%s S: %d -> %d | anchors moved %d'
                  % (ch, len(off), len(on), len(moved)))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('corpus_root')
    ap.add_argument('--book')
    ap.add_argument('--verbose', action='store_true')
    a = ap.parse_args(argv)
    books = lost_total = risk_total = moved_total = 0
    for bd in _book_dirs(a.corpus_root):
        if a.book and a.book.lower() not in bd.lower():
            continue
        books += 1
        rows = census_book(bd, a.verbose)
        nlost = sum(1 for r in rows if r[1] == 'S_LOST')
        nrisk = sum(1 for r in rows if r[1] == 'S_LOST' and r[3] is True)
        nmoved = sum(1 for r in rows if r[1] == 'ANCHOR_MOVED')
        nerr = sum(1 for r in rows if r[1] == 'ERROR')
        lost_total += nlost
        risk_total += nrisk
        moved_total += nmoved
        if nlost or nmoved or nerr or a.verbose:
            print('== %-58s S_LOST=%d RISK=%d ANCHOR_MOVED=%d ERR=%d'
                  % (os.path.relpath(bd, a.corpus_root), nlost, nrisk, nmoved, nerr))
        for ch, kind_, n, risk, note in rows:
            if kind_ == 'S_LOST' and (risk or a.verbose):
                print('   %s ch%s %s  %s' % ('!!' if risk else '  ', ch, n, note))
            elif kind_ in ('ERROR',) or (a.verbose and kind_ == 'ANCHOR_MOVED'):
                print('   %s ch%s %s  %s' % ('!!' if kind_ == 'ERROR' else '  ',
                                             ch, n, note))
    print('\ncensus: %d books | S_LOST=%d（其中回归风险 RISK=%d）'
          ' ANCHOR_MOVED=%d' % (books, lost_total, risk_total, moved_total))
    return 0


if __name__ == '__main__':
    sys.exit(main())
