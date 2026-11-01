# -*- coding: utf-8 -*-
r"""只读普查 + A/B：⑭「假锚」通道两条腿的收窄/放宽影响面（2026-10-31）。

动因（Gelfand–Manin《方法同调代数》ch2/ch3 实测）：`tools/deregister_formula_tags.py
--false-anchor` 的机械放行判据 `lib.tag_attestation.operand_only_paren_anchor` 两条腿
在**混排编号书**上双双失灵——
  ① 旧「整章一个独立编号块都不许有」：该书页边印章级罗马号 `(III.41)`，于是任何裸
     阿拉伯幻影都声称不了假锚，只能改口 `--mispaired` 去指认一个印面上不存在的主展示块；
  ② 旧「每个 `(N)` 至少一侧贴运算符/括号」：正文里 `F(\mathcal{G})`、`T(1)`、`f'(9)`
     这类**函数应用**（左括号零间隙贴字母）被当成编号本形。
新口径：① 按**号形**收窄（`_num_shape`：plain/dotted/lettered 三档互不背书）；
② 增「零间隙左贴拉丁字母/数字/撇号」一档（`_span_is_factor`）。

本工具**不出判据、不写任何书目录**，只做三档归因：
  A   = 旧① ∧ 旧②（= 改动前的放行面）
  B1  = 新① ∧ 旧②（只改号形腿）
  B   = 新① ∧ 新②（两条腿都改）
并另记**反向控件** `real_label`：该号本身在页窗里就是独立编号块（印面确有此号）——
这类 tag 在 A/B 三档下都必须**不放行**，任一放行即回归。

用法：
    python tools/census_gate14_falseanchor_scope.py --dump OUT.jsonl [--corpus DIR] [--filter 子串]
    python tools/census_gate14_falseanchor_scope.py --report OUT.jsonl
"""
import argparse
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
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot  # noqa: E402
_boot.setup()

from data.book_structure.book_structure import resolve_chapter_json_path  # noqa: E402
from census_gate14_bare_blindness import _books, _ch_key, _contract_files  # noqa: E402
import lib.tag_attestation as _lta  # noqa: E402
from lib.page_dir import node_page_dir as _node_page_dir  # noqa: E402
from lib.user_config import get as _uc_get  # noqa: E402


def _old_span_is_factor(s, i, j):
    """**改动前**的②：只认「任一侧贴运算符/括号」（跳水平空白），无邻接档。"""
    lead, tail = _lta._flank_chars(s, i, j)
    return (lead in _lta._FACTOR_FLANK) or (tail in _lta._FACTOR_FLANK)


def _forms_with_spans(raw, num):
    """该块承载号 `num` 的形态 → ``[(form, [(i, j), ...])]``（与判据同一趟匹配）。"""
    out = []
    for t in _lta._label_forms(raw):
        tt = t.replace("．", ".")
        spans = list(_lta._paren_spans(tt, num))
        if spans:
            out.append((tt, spans))
    return out


def _leg_verdict(sites, blocks, num):
    """→ ``(old1, new1, old2_ok, new2_ok, n_blocks, real_label)``。

    ``blocks`` = 本章页窗**一趟**扫出的 ``[(页, 原块)]``（各号共用，避免逐号重读整窗）。
    """
    shape = _lta._num_shape(num)
    old1 = not sites
    new1 = not [n for n in sites if _lta._num_shape(n) == shape]
    real_label = str(num) in {str(n) for n in sites}
    n_blocks = 0
    old_bad = new_bad = 0
    for _pg, raw in blocks:
        forms = _forms_with_spans(raw, num)
        if not forms:
            continue
        n_blocks += 1
        # 与 `paren_block_is_factor_form` 同一「任一形态成立即算因子」口径
        old_ok = any(all(_old_span_is_factor(t, i, j) for i, j in sp)
                     for t, sp in forms)
        new_ok = any(all(_lta._span_is_factor(t, i, j) for i, j in sp)
                     for t, sp in forms)
        if not old_ok:
            old_bad += 1
        if not new_ok:
            new_bad += 1
    return (old1, new1, n_blocks > 0 and old_bad == 0,
            n_blocks > 0 and new_bad == 0, n_blocks, real_label)


def dump(corpus, flt, out_path):
    rows = []
    for bk in _books(corpus):
        if flt and flt not in bk:
            continue
        bs = os.path.join(bk, "_extract", "book_structure")
        ext = os.path.join(bk, "_extract")
        for fname in _contract_files(bs):
            ch = _ch_key(fname)
            try:
                tree = json.loads(open(resolve_chapter_json_path(ext, ch),
                                       encoding="utf-8").read())
                lo, hi = int(tree["page_start"]), int(tree["page_end"])
            except Exception as e:
                rows.append({"book": os.path.basename(bk), "ch": ch, "err": str(e)[:80]})
                continue
            ld = _lta.dir_page_loader(_node_page_dir(ext, tree, ch), ext)
            nums = sorted({str(n) for _k, n in _lta.collect_contract_tags(tree)
                           if _lta._num_shape(n) == "plain"},
                          key=lambda s: (len(s), s))
            if not nums:
                continue
            sites = _lta.standalone_label_sites(ld, lo, hi)
            blocks = [(pg, raw) for pg in range(lo, hi + 1)
                      for raw in (ld(pg) or [])]
            real_sites = {str(n) for n in sites}
            for num in nums:
                old1, new1, old2, new2, nb, real = _leg_verdict(sites, blocks, num)
                rows.append({"book": os.path.basename(bk), "ch": ch, "num": num,
                             "A": bool(old1 and old2), "B1": bool(new1 and old2),
                             "B": bool(new1 and new2), "n_blocks": nb,
                             "real_label": real or (num in real_sites),
                             "old1": old1, "new1": new1, "old2": old2, "new2": new2})
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("DUMPED %d 行 → %s" % (len(rows), out_path))
    return rows


def report(path):
    rows = [json.loads(l) for l in open(path, encoding="utf-8")]
    ok = [r for r in rows if "A" in r]
    a = [r for r in ok if r["A"]]
    b1 = [r for r in ok if r["B1"]]
    b = [r for r in ok if r["B"]]
    print("plain 裸号 tag 总数 = %d（%d 本 / %d 章次）" % (
        len(ok), len({r["book"] for r in ok}), len({(r["book"], r["ch"]) for r in ok})))
    print("A  旧口径放行        = %d" % len(a))
    print("B1 只改号形腿放行    = %d（新增 %d）" % (len(b1), len(b1) - len(a)))
    print("B  两腿都改放行      = %d（比 B1 再新增 %d）" % (len(b), len(b) - len(b1)))
    print("\n新增放行（B 放行、A 不放行）逐条：")
    for r in b:
        if not r["A"]:
            leg = "号形腿" if r["B1"] else "邻接腿"
            print("  %-46s ch%-8s 号=%-4s 经=%-4s 括号块=%d" % (
                r["book"], r["ch"], r["num"], leg, r["n_blocks"]))
    bad = [r for r in b if r["real_label"]]
    print("\n🔴 反向控件 real_label（该号本身就是独立编号块）放行数 = %d（必须 0）" % len(bad))
    for r in bad:
        print("   %s ch%s 号=%s" % (r["book"], r["ch"], r["num"]))
    lost = [r for r in a if not r["B"]]
    print("A 放行而 B 不放行（不该发生，判据只放宽）= %d" % len(lost))
    for r in lost:
        print("   %s ch%s 号=%s old1=%s new1=%s old2=%s new2=%s" % (
            r["book"], r["ch"], r["num"], r["old1"], r["new1"], r["old2"], r["new2"]))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--corpus", default=None)
    ap.add_argument("--filter", default=None)
    ap.add_argument("--dump", default=None)
    ap.add_argument("--report", default=None)
    a = ap.parse_args()
    if a.dump:
        dump(a.corpus or _uc_get("corpus_root"), a.filter, a.dump)
    if a.report:
        report(a.report)
