#!/usr/bin/env python3
"""tools/deregister_formula_tags.py — 把契约里**印面根本不存在的公式序标**摘掉（四本账同步）。

缺陷场景（Katok–Hasselblatt《Introduction to the Modern Theory of Dynamical Systems》
实测 2026-09-29）：收割器把条目序标 / 散文交叉引用（`12.2.2` 是节内练习号、`18.3.1` 是
定理号、`i'` 是证明里条件列表的 `(i')`）误挂成展示式的 `tag`。后果与「漏号」相反但同样
两头堵：契约不该登记的号成了对账真值 → 写手照印面**不写** `\tag{}` 判「漏写」，删掉又
判「编造」，而号已顺着契约流进两侧单元正文和两版最终 md（本书 19 处：18 处经 PDF 出版方
文字层逐号复核——全章页窗里该号只作为条目号/交叉引用出现，从未以 `(N)` 编号形态出现；
剩一处 `ch14 i'` 的契约块本身是**空公式** `{"formula": "", "tag": "i'"}`，编号列不可能给
空块编号）。

判据**不自造**：检测趟与修复趟共用闸门 ⑭（`lib.tag_attestation.unattested_tags`，读页
口径 `dir_page_loader(ext)` 与 `gate_units` 一致；人工确证豁免 `attested_numbers(ext)` 与
Q 层同一份登记）。于是：
  * ⑭ 没判毒的号 → 本工具**拒绝**删除（它在页窗里找得到印刷锚点，多半是真编号）；
  * 真印却被 OCR 漏掉的号 → 走 `config/verify_config/register_formula.py` 登记
    `known_book`（登记后 ⑭ 与本工具同时看见它，这才是正解，不是删）。
与 `tools/backfill_formula_tags.py`（回填丢失的号）互为反向通道，两者共用同一批谓词。

四本账（缺一即漂移）：
  ① 分章契约 `ch{N}.json`（附录 `appendix{X}.json` / 补篇 `supplement{S}.json`）目标公式块
     的 `tag` → `""`（与收割处 `strip_unattested` 同一形态：块留着、只是不再声称带编号）
  ② `units/ch{N}/manifest.json` 与 ③ `units-translate/ch{N}/manifest.json` 的 `tags` 列表
     （无该字段/无该号时本账自动跳过并如实报告；多数书由 `split_draft_units` 写入 `tags`）
  ④ 两侧单元正文里的 `\tag{N}` / `\tag*{N}` —— **本工具直接删**（删除是纯机械操作，不像
     回填那样需要写手按印面补内容）：独占一行的 `\tag{}` 连同该行一起删（不留空围栏行），
     行尾内联形只去掉 token 与前导空格；首行 marker 一字节不动。
  写完后待办（工具打印确切命令）：重跑 `gate_units` → `init_translate_units`（源正文变了，
  译侧 `src_hash` 快照必须重同步）→ 该章 `merge_units` 重拼两版 md。

保险（全部机械）：
  - 默认 dry-run，`--apply` 才写盘；写盘前把每个受影响文件备份到
    `<extract>/_bak_deregister_tags/<时间戳>/`，逐次追加台账
    `<extract>/_formula_tag_deregistrations.jsonl`。
  - **字节守恒**：逐文件探测换行符（CRLF/LF）与末尾换行，先断言「按该风格复演即原字节」，
    再做锚定字面替换；写出前断言「解析后的新契约树 == 在旧树副本上只清这些 tag 的语义模型」。
    故非标准序列化的契约（indent=1 / ensure_ascii=True / 尾部游离 LF）也能安全修，
    且除目标串外一字节不变。
  - `--number` 必须在 ⑭ 判毒集合里；契约与两侧正文都没有该 tag → NO-OP（幂等）；
    manifest 的 `tags` 账只在「该文件是标准 indent=2 形」时改写，否则拒绝并说明；
    单元正文替换后断言「再无 `\tag{N}`」且首行 marker 未变。

用法:
  python tools/deregister_formula_tags.py <extract_dir> 18 --list          # 该章 ⑭ 判毒清单
  python tools/deregister_formula_tags.py <extract_dir> 18 --number 18.3.1 \\
      --number i' --evidence "fitz 文字层 p586-617 全窗：18.3.1 只作定理号出现，无 (18.3.1)" [--apply]
退出码：0 = 已写出 / dry-run 可行 / 已在账（幂等 NO-OP）；2 = 拒绝（未写任何文件）。
"""
import argparse
import copy
import io
import json
import os
import re
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

from data.book_structure.book_structure import resolve_chapter_json_path, unit_dir_name  # noqa: E402
from lib.tag_attestation import (attested_numbers, collect_contract_tags,  # noqa: E402
                                 dir_page_loader, unattested_tags)

_TAG_OPEN = r"\\tag\*?\{\s*%s\s*\}"


class Refuse(Exception):
    """拒绝写出（未触碰任何文件）。"""


# ── 字节守恒读写：不折行、不补末尾，按原字节复现 ─────────────────────────────
def read_text(path):
    """→ 文本（**保留原换行形态**，含混合 CRLF/LF）。非 UTF-8 即拒绝。"""
    with open(path, "rb") as f:
        raw = f.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as e:
        raise Refuse("%s：不是 UTF-8（%s），拒绝改写" % (path, e))
    if text.encode("utf-8") != raw:
        raise Refuse("%s：UTF-8 复演与原字节不符，拒绝改写" % path)
    return text


def write_text(path, text):
    with open(path, "wb") as f:
        f.write(text.encode("utf-8"))


def restyle(new_text, old_text):
    """整文件重写时跟随原换行风格（混合形态按多数派；无 CRLF 即 LF）。"""
    if "\r\n" in old_text and old_text.count("\r\n") >= old_text.count("\n") / 2:
        return new_text.replace("\n", "\r\n")
    return new_text


# ── ① 契约：锚定字面替换 + 语义模型一致性断言 ────────────────────────────────
def clear_in_model(tree, nums):
    """在副本上把 tag∈nums 的公式块清空 tag（镜像收割处 `strip_unattested` 的语义）。"""
    out = copy.deepcopy(tree)

    def walk(node):
        if isinstance(node, dict):
            if node.get("formula") is not None:
                t = str(node.get("tag") or "").strip()
                if t and t in nums:
                    node["tag"] = ""
                    node.pop("tags", None)
                elif node.get("tags"):
                    keep = [x for x in node["tags"] if str(x).strip() not in nums]
                    if len(keep) != len(node["tags"]):
                        if keep:
                            node["tags"] = keep
                        else:
                            node.pop("tags", None)
            for c in node.get("sub_sec") or []:
                walk(c)
        elif isinstance(node, list):
            for c in node:
                walk(c)

    walk(out)
    return out


def contract_edit(text, tree, nums):
    """契约文本 → (new_text, {号: 删除处数})；语义不符即 Refuse。"""
    counts = {}
    for num in nums:
        lit = '"tag": "%s"' % num
        counts[num] = text.count(lit)
        if counts[num]:
            text = text.replace(lit, '"tag": ""')
    if not any(counts.values()):
        return text, counts
    try:
        after = json.loads(text)
    except ValueError as e:
        raise Refuse("契约替换后不是合法 JSON（%s），拒绝写出" % e)
    if after != clear_in_model(tree, set(nums)):
        raise Refuse("契约替换后的解析树 ≠ 「只清这些 tag」的语义模型——该号可能登记在 "
                     "`tags` 列表里或序列化形态不同 %s，拒绝写出" % counts)
    return text, counts


# ── ②③ manifest 的 tags 账 ──────────────────────────────────────────────────
def manifest_edit(text, path, nums):
    """manifest 文本 → (new_text|None, 说明)。None = 该侧无此账（幂等跳过）。"""
    obj = json.loads(text)
    units = obj.get("units") or []
    hits = [u for u in units if any(str(x).strip() in nums for x in (u.get("tags") or []))]
    if not hits:
        return None, ("该 manifest 无 tags 字段" if not any(u.get("tags") is not None
                                                           for u in units)
                      else "无这些号的 tags 登记")
    if json.dumps(obj, ensure_ascii=False, indent=2) != text.replace("\r\n", "\n"):
        raise Refuse("%s：要改 `tags` 列表但文件不是标准 indent=2 形，拒绝整文件重写"
                     "（该本账请人工同步后重跑）" % path)
    changed = []
    for u in hits:
        old = list(u["tags"])
        keep = [x for x in old if str(x).strip() not in nums]
        if keep:
            u["tags"] = keep
        else:
            u.pop("tags", None)
        changed.append("%s %s→%s" % (u.get("file"), old, keep))
    return (restyle(json.dumps(obj, ensure_ascii=False, indent=2), text),
            "; ".join(changed))


# ── ④ 单元正文：删 \tag token ────────────────────────────────────────────────
def unit_edit(text, nums):
    """单元正文（含首行 marker）→ (new_text, 删除处数)。"""
    n = 0
    for num in nums:
        esc = re.escape(num)
        # 独占一行（可带 `> ` 前缀）：整行连换行一起去掉，避免留下空围栏行
        text, k = re.subn("(?m)^[ \t]*(?:>[ \t]*)?" + _TAG_OPEN % esc + r"[ \t]*\r?\n",
                          "", text)
        n += k
        # 内联形：只去掉 token 与其前导空格
        text, k = re.subn(r"[ \t]+" + _TAG_OPEN % esc, "", text)
        n += k
        if re.search(_TAG_OPEN % esc, text):
            raise Refuse("单元正文里仍有无法安全去除的 `\\tag{%s}` 形态，拒绝写出" % num)
    return text, n


def unit_dirs(bs, ch_key):
    """章 → 两侧单元目录，**以磁盘物理证据为准**。

    🔴 不能只信 `unit_dir_name`：它的前缀取进程级 kind 注册表（`prime_chapter_kinds`
    灌注），未灌注时把补篇键 `S` 算成 `appendixS` → 目录「不存在」→ 两侧正文/manifest
    两本账**静默跳过**，工具照样报成功（Katok supplementS 实测同型的 `sync_translate_markers`
    误跳 41 单元，见 `tools/tests/test_sync_markers_contract_path.py`）。故按三种章型
    逐一探测；同时命中多个目录 = 该键有歧义，拒绝而不是猜。
    """
    cands = []
    try:
        cands.append(unit_dir_name(ch_key))
    except Exception:
        pass
    for pre in ("ch", "appendix", "supplement"):
        cands.append("%s%s" % (pre, ch_key))
    out = []
    for side in ("units", "units-translate"):
        hits = []
        for nm in cands:
            d = os.path.join(bs, side, nm)
            if os.path.isdir(d) and d not in hits:
                hits.append(d)
        if len(hits) > 1:
            raise Refuse("%s 侧同时存在 %s 两个该章单元目录，键 %r 章型有歧义，"
                         "拒绝猜（先核对 chapter_map 的 kind）"
                         % (side, ", ".join(os.path.basename(h) for h in hits), ch_key))
        if hits:
            out.append((side, hits[0]))
    return out


def _mkdir_unique(bak):
    cand, i = bak, 0
    while True:
        try:
            os.makedirs(cand)
            return cand
        except FileExistsError:
            i += 1
            cand = "%s-%d" % (bak, i)


# ── 主流程 ───────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("extract_dir")
    ap.add_argument("ch_key")
    ap.add_argument("--number", action="append", default=[],
                    help="要摘掉的契约 tag（可重复；必须被闸门 ⑭ 判为无印刷锚点）")
    ap.add_argument("--evidence", default="")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--list", action="store_true", help="列该章 ⑭ 判毒号 + 两侧正文命中数")
    a = ap.parse_args(argv)

    ext = a.extract_dir
    bs = os.path.join(ext, "book_structure")
    try:
        cpath = resolve_chapter_json_path(ext, a.ch_key)
        if not cpath or not os.path.isfile(cpath):
            raise Refuse("找不到分章契约（%s）" % cpath)
        craw = read_text(cpath)
        tree = json.loads(craw)

        condemned = unattested_tags(tree, dir_page_loader(ext), attested_numbers(ext))
        dirs = unit_dirs(bs, a.ch_key)

        if a.list:
            print("闸门 ⑭ 判毒（契约 tag 在本章页窗内无印刷锚点，已豁免 known_book）：")
            for num in sorted(str(x) for x in condemned):
                hits = []
                for side, d in dirs:
                    for name in sorted(os.listdir(d)):
                        if name.endswith(".md"):
                            body = read_text(os.path.join(d, name))
                            if re.search(_TAG_OPEN % re.escape(num), body):
                                hits.append("%s:%s" % (side, name))
                print("  %-10s 单元正文命中 %d 个文件 %s" % (num, len(hits), " ".join(hits[:8])))
            att = attested_numbers(ext)
            print("（known_book 豁免登记：%s）" % (" ".join(sorted(att)) or "空"))
            return 0

        if not a.number:
            raise Refuse("需要 --number（或 --list 看该章 ⑭ 判毒清单）")
        if len(a.evidence.strip()) < 20:
            raise Refuse("--evidence 必填且不少于 20 字（印面出处：页窗 / 该号在印面上的实际形态）")

        # 先扫两侧正文与 manifest（一次读盘，供幂等判定与写出复用）
        bodies, mans = [], []
        for side, d in dirs:
            for name in sorted(os.listdir(d)):
                p = os.path.join(d, name)
                if name.endswith(".md"):
                    bodies.append([side, p, read_text(p)])
                elif name == "manifest.json":
                    raw = read_text(p)
                    mans.append([side, p, raw, json.loads(raw)])

        def _in_body(text, num):
            return re.search(_TAG_OPEN % re.escape(num), text) is not None

        def _in_tags(obj, num):
            return any(num in {str(x).strip() for x in (u.get("tags") or [])}
                       for u in (obj.get("units") or []))

        registered = {str(n) for _k, n in collect_contract_tags(tree)}
        condemned = {str(x) for x in condemned}
        nums, absent, blocked = [], [], []
        for num in {str(x) for x in a.number}:
            present = (num in registered
                       or any(_in_body(b[2], num) for b in bodies)
                       or any(_in_tags(m[3], num) for m in mans))
            if not present:
                absent.append(num)
            elif num not in condemned:
                blocked.append(num)
            else:
                nums.append(num)
        if blocked:
            raise Refuse("%s：闸门 ⑭ 未判它无毒（本章页窗里找得到印刷锚点）——多半是真编号，"
                         "删除等于毁掉对账真值。确要处理请先目视印面；真印却被抽取器漏挂的号"
                         "走 config/verify_config/register_formula.py 登记 known_book"
                         % ", ".join(sorted(blocked)))
        if not nums:
            print("NO-OP     %s：契约、两侧 manifest 与单元正文都没有这个 tag（已摘过），"
                  "无需写出" % " ".join(sorted(absent)))
            return 0
        if absent:
            print("提示      %s：四本账里都查无此号（已摘过），本次跳过" % " ".join(sorted(absent)))

        craw_after, ccounts = contract_edit(craw, tree, nums)
        targets = []
        if any(ccounts.values()):
            targets.append({"path": cpath, "before": craw, "after": craw_after})

        touched = []
        for side, p, raw in bodies:
            new, k = unit_edit(raw, nums)
            if not k:
                continue
            if new.split("\n")[0] != raw.split("\n")[0]:
                raise Refuse("%s：首行 marker 被动过，拒绝写出" % p)
            targets.append({"path": p, "before": raw, "after": new})
            touched.append("%s:%s(%d)" % (side, os.path.basename(p), k))

        man_notes = []
        for side, mp, raw, obj in mans:
            new, note = manifest_edit(raw, mp, nums)
            man_notes.append("%s/%s" % (side, note))
            if new is not None:
                targets.append({"path": mp, "before": raw, "after": new})

        print("章        = %s   契约=%s" % (a.ch_key, os.path.basename(cpath)))
        print("摘除编号  = %s" % " ".join(sorted(nums)))
        print("契约删除  = %s" % ", ".join("%s×%d" % (n, c) for n, c in sorted(ccounts.items())))
        print("单元正文  = %s" % (" ".join(touched) or "无命中"))
        print("manifest  = %s" % (" | ".join(man_notes) or "无该侧清单"))
        if not targets:
            print("NO-OP     契约、两侧 manifest 与单元正文都没有这些 tag（已摘过），无需写出")
            return 0
        if not a.apply:
            print("DRY-RUN（未写盘）：加 --apply 落盘")
            return 0

        bak = _mkdir_unique(os.path.join(ext, "_bak_deregister_tags",
                                         time.strftime("%Y%m%d-%H%M%S")))
        for t in targets:
            if t["path"].endswith(".json"):
                json.loads(t["after"])
            now = read_text(t["path"])
            if now != t["before"]:
                raise Refuse("%s：核对与写出之间文件被别人改过（并发会话？），拒绝写出"
                             % t["path"])
        for t in targets:
            write_text(os.path.join(bak, "%s__%s" % (Path(t["path"]).parent.name,
                                                     os.path.basename(t["path"]))),
                       t["before"])
        for t in targets:
            write_text(t["path"], t["after"])
        ledger = os.path.join(ext, "_formula_tag_deregistrations.jsonl")
        with io.open(ledger, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "extract_dir": os.path.abspath(ext),
                                "ch_key": str(a.ch_key), "numbers": nums,
                                "contract_removals": ccounts,
                                "unit_files": touched, "manifest": man_notes,
                                "evidence": a.evidence.strip(),
                                "gate_14_condemned": sorted(str(x) for x in condemned),
                                "backup": bak}, ensure_ascii=False) + "\n")
        print("APPLIED   备份=%s 台账=%s" % (bak, ledger))
        print("待办（顺序不可颠倒）：")
        print("  python flows/write-source/script/gate_units.py \"%s\" %s" % (ext, a.ch_key))
        print("  python flows/write-source/script/init_translate_units.py \"%s\" %s"
              % (ext, a.ch_key))
        print("  python flows/write-source/script/merge_units.py \"%s\" --ch %s"
              % (ext, a.ch_key))
        return 0
    except Refuse as e:
        print("REFUSE: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
