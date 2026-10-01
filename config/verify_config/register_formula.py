#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""register_formula.py — 唯一被允许的 `formula.known_book` 登记入口.

`known_book` 登记的是「**原书确实印着、但抽取器从 page_*.json 里读不到**」的公式
编号（编号与正文粘连、页边号整块漏读等）。它是 Q 层与写源闸门 ⑭ **共用**的人工
确证通道（见 `flows/write-source/write-source.md` 闸门 ⑭、`lib/tag_attestation.py`）：
没有它，两头会互相矛盾——Q 层要求写手照印面写该号，⑭ 又把该号判成凭空编造。

登记纪律（本 CLI 机械执行的部分）：
1. **先目视印面**（fitz 裁剪/渲染），确认该号真的印在书上——`--evidence` 必填，
   且连同章号、时间写入 `formula.known_book_audit` 账本，供事后审阅；
2. **不得登记契约已经登记的号**：本 CLI 读该章内容化契约（`chapter_tag_map`），
   已在契约账上的号拒绝——单元门控本来就**要求**写手写它，挂号等于把写手漏写
   （或契约挂错公式）洗白；
3. **契约缺档即可登记，即使 Q 层从页 JSON 收得到该号**。这条是 2026-09-28 修的正
   向缺口：旧判据拿「Q 层收得到」当拒绝理由，恰好把本通道**设计要服务的那一类**
   挡在门外——编号与公式**同行内联粘连**（Arnold 中译本 ch1 印面
   `ẍ = −g, 这里 g ≈ 9.8 m/s²(伽利略).  (2)`：整条式子是行内 `$...$`，`(2)` 粘在
   散文块尾部）时，契约侧既没有可挂 `tag` 的**展示公式块**、正文块上的 `tag` 又不
   被 `chapter_tag_map` 收集，闸门 ⑱（`unharvested_anchor_tags`）要求的「给该公式
   块补 tag」回填**无从下手**。于是 Q 层（独立页扫描，收得到 `(2)`）要求写
   `\tag{2}`、单元门控（契约 tag 真值）判它编造、登记工具又拒绝豁免 = **三头堵**。
   现在这类号照常收登记，但账本多记两个布尔（`contract_missing` / `harvested`），
   并在输出里提示「契约漏挂」——先确认回填契约是否可行，可行则回填、不必挂号；
4. **不得手写/手改 `verify_config.json`**（文件自带 `_provenance.warning` 已声明
   手写无效）：本 CLI 只做「读→改 formula 的 known_book 两键→原子写回」，并保留
   原文件的换行风格；`make_config --force` 经 `_load_old_formula` 保留这两键，
   重生成不会清空登记（回归测试 `tests/test_force_preserves_manual_flags.py`）。

用法：
    python config/verify_config/register_formula.py <书目录或 _extract> \
        --chapter 2 --number 4 \
        --evidence "fitz 裁页 p.161（印刷 p.149）左缘确有 (4)，页 JSON 全章查无此号"
    python config/verify_config/register_formula.py <同上> --list
"""
import argparse
import json
import os
import sys
import time
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
import lib.boot as _boot  # noqa: E402
_boot.setup()

from lib.numbering import (resolve_formula_type,  # noqa: E402
                           FORMULA_LEAD_LETTER)
from formula_tag import (SourceFormulaIndex, build_formula_patterns  # noqa: E402
                         )


def _die(msg):
    print(f"[register-formula] REFUSED: {msg}", file=sys.stderr)
    raise SystemExit(2)


def _resolve_extract(arg):
    """Accept a book dir or an extract dir; return the dir holding the config."""
    p = os.path.abspath(arg)
    cands = [p, os.path.join(p, "_extract")]
    for c in cands:
        if os.path.exists(os.path.join(c, "verify_config.json")):
            return c
    _die("找不到 verify_config.json（须先由 make_config.py 生成配置）：" + arg)


def _formula_node(cfg, section_key):
    """Locate the `formula` map for this chapter's section, plus its holder.

    Returns (formula_map, holder_dict) — the holder is mutated in place.  Both
    the grouped shape {"ch": {...,"formula": {...}}} and the legacy flat shape
    are accepted; a book without a `formula` map has no Q layer to register for.
    """
    if isinstance(cfg.get(section_key), dict):
        holder = cfg[section_key]
    elif isinstance(cfg.get("formula"), dict):
        holder = cfg
    else:
        keys = [k for k in ("ch", "appendix", "supplement")
                if isinstance(cfg.get(k), dict)]
        if len(keys) == 1:
            holder = cfg[keys[0]]
        else:
            _die(f"配置里找不到 section {section_key!r}（现有分组 {keys or '扁平'}）")
    fm = holder.get("formula")
    if not isinstance(fm, dict):
        _die("该配置没有 `formula` 块 → Q 层未启用，known_book 无处登记；"
             "请先跑 config 子流程生成公式配置")
    return fm, holder


def _provenance_ok(cfg, holder):
    for node in (holder, cfg):
        if isinstance(node, dict) and isinstance(node.get("_provenance"), dict):
            return True
    return False


def _source_numbers(ext, formula, chapter):
    """Numbers the extractor CAN harvest for this chapter (plain ∪ sectioned).

    Mirrors the Q layer's own derivation (`QLayer.run`): the token shape
    `(lead, ncomp)` is resolved via `resolve_formula_type(type, letter_ch)` (the
    single entry point — the formula-only Roman code 16 / letter code 15 live
    outside ORDINAL_DEPTH, so `ordinal_depth` would crash on them), then the
    patterns come from `ncomp` + `bare_number` + `lead`.
    """
    from data.chapter_map.chapter_map import find_chapter
    rec = find_chapter(ext, chapter)
    start, end = rec.get("start"), rec.get("end")
    if not isinstance(start, int) or not isinstance(end, int):
        _die(f"chapter_map 里章 {chapter} 无页区间，无法核对书源集合 S")
    lead, ncomp = resolve_formula_type(
        formula.get("type"), letter_ch=bool(formula.get("letter_ch")))
    patterns = build_formula_patterns(
        ncomp, allow_bare=bool(formula.get("bare_number", True)),
        letter=(lead == FORMULA_LEAD_LETTER), lead=lead)
    fignore = {SourceFormulaIndex.norm(str(k))
               for k in (formula.get("ignore") or [])}
    fignore = {k for k in fignore if k}
    fkeep = formula.get("keep_cross_refs", True)
    out = set()
    plain = SourceFormulaIndex(ext, patterns, False, fignore, ncomp=ncomp,
                               keep_cross_refs=fkeep)
    plain.build(int(chapter), start, end)
    out |= plain.numbers_for_chapter(int(chapter))
    sect = SourceFormulaIndex(ext, patterns, False, fignore,
                              keep_cross_refs=fkeep)
    built = sect.build_sectioned(int(chapter), start, end, ["_"], ncomp=ncomp)
    out |= built.get("_union") or set()
    return out, (start, end)


def _contract_numbers(ext, chapter):
    """该章**内容化契约**已登记的公式序标集合（归一化裸号）。

    契约 tag 是步骤 5 单元门控（`gate_units` 判据 ③）的对账真值：在档 = 门控本来就
    **要求**写手写这个 `\tag`，挂号等于把写手漏写洗白 → 拒绝；缺档 = 门控会把照印面
    写出的 `\tag` 判「编造」→ 正是本通道要豁免的形态。

    路径用 `resolve_chapter_json_path`（按磁盘物理证据，不信进程级 kind 注册表）；
    读不到契约 = 返回空集（无从判断在档，交由 Q 层与门控自身兜住）。
    """
    from data.book_structure.book_structure import (resolve_chapter_json_path,
                                                    chapter_tag_map)
    p = resolve_chapter_json_path(ext, chapter)
    if not p or not os.path.exists(p):
        return set()
    try:
        with open(p, encoding="utf-8") as f:
            tree = json.load(f)
        out = set()
        for lst in chapter_tag_map(tree).values():
            for x in lst or []:
                nn = SourceFormulaIndex.norm(str(x))
                if nn:
                    out.add(nn)
        return out
    except Exception:
        return set()


def main(argv=None):
    ap = argparse.ArgumentParser(description="登记 known_book（人工印面确证）")
    ap.add_argument("target", nargs="?", help="书目录或 _extract 目录")
    ap.add_argument("--chapter", type=int)
    ap.add_argument("--number", action="append", default=[],
                    help="要登记的编号（可重复；写原样或归一皆可）")
    ap.add_argument("--evidence", default="",
                    help="印面目视证据（必填）：页码 + 看到什么")
    ap.add_argument("--section", default="ch",
                    choices=["ch", "appendix", "supplement"])
    ap.add_argument("--list", action="store_true", help="列出现有登记")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not args.target:
        ap.error("需要 <书目录或 _extract>")
    ext = _resolve_extract(args.target)
    cfg_path = os.path.join(ext, "verify_config.json")
    raw = open(cfg_path, "rb").read()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    cfg = json.loads(raw.decode("utf-8-sig"))
    fm, holder = _formula_node(cfg, args.section)

    if args.list:
        print(json.dumps({"known_book": fm.get("known_book") or [],
                          "known_book_audit": fm.get("known_book_audit") or []},
                         ensure_ascii=False, indent=2))
        return 0

    if not args.chapter and args.number:
        _die("--number 须配 --chapter")
    if not args.number:
        _die("没有要登记的编号（用 --number 或 --list）")
    if len(args.evidence.strip()) < 10:
        _die("`--evidence` 必填且要说清印面证据（先 fitz 裁页目视，再挂号）")
    if not _provenance_ok(cfg, holder):
        _die("该 verify_config.json 缺 `_provenance`（手写/手改配置不被接受），"
             "请先跑 make_config.py 再登记")

    known = [str(x) for x in (fm.get("known_book") or [])]
    known_norm = {SourceFormulaIndex.norm(x) for x in known}
    known_norm.discard(None)
    audit = list(fm.get("known_book_audit") or [])
    src_nums, page_range = _source_numbers(ext, fm, args.chapter)
    contract_nums = _contract_numbers(ext, args.chapter)

    added, skipped, notes = [], [], []
    for num in args.number:
        nn = SourceFormulaIndex.norm(str(num))
        if not nn:
            _die(f"编号 {num!r} 无法归一（不是可解析的公式序标）")
        if nn in known_norm:
            skipped.append((num, "已在册"))
            continue
        if nn in contract_nums:
            _die(f"{nn}（章 {args.chapter}）**契约已登记**——单元门控本来就要求写手"
                 f"写出 `\\tag{{{nn}}}`，挂号只会把漏写（或 tag 挂错公式）洗白。"
                 f"请回单元补写该编号公式，不要挂号")
        known.append(nn)
        known_norm.add(nn)
        added.append(nn)
        harvested = nn in src_nums
        entry = {"number": nn, "chapter": args.chapter,
                 "page_range": list(page_range),
                 "evidence": args.evidence.strip(),
                 "contract_missing": nn not in contract_nums,
                 "harvested": harvested,
                 "registered_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        audit.append(entry)
        if harvested:
            notes.append(f"{nn}：Q 层页扫描收得到而契约无档（编号与公式同行内联粘连"
                         f"一类）——若契约里存在可挂 tag 的展示式，优先**回填契约**"
                         f"而不是长期依赖登记")

    if not added:
        print(f"[register-formula] 无新增：{skipped}")
        return 0
    fm["known_book"] = sorted(set(known), key=lambda s: [len(s), s])
    fm["known_book_audit"] = audit
    print(f"[register-formula] 章 {args.chapter} 登记 {added}"
          f"（页区间 {page_range[0]}-{page_range[1]}），证据已入账本")
    for n in notes:
        print(f"[register-formula] 提示 {n}")
    if args.dry_run:
        print("[register-formula] --dry-run：未写回")
        return 0
    text = json.dumps(cfg, ensure_ascii=False, indent=2)
    if newline != "\n":
        text = text.replace("\n", newline)
    tmp = cfg_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(text.encode("utf-8"))
    os.replace(tmp, cfg_path)
    print("[register-formula] 已写回 verify_config.json；"
          "请重跑 verify_chapter.py 复核该章 Q 层")
    return 0


if __name__ == "__main__":
    sys.exit(main())
