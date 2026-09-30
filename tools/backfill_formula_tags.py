#!/usr/bin/env python3
"""tools/backfill_formula_tags.py — 把**印面确有、收割弄丢**的公式编号回填进契约与 manifest。

缺陷场景（Apostol《Introduction to Analytic Number Theory》实测 2026-09-29）：抽取器
收割 `tag` 时会整块丢掉印在编号列的 `(N)`（编号与展示式粘连、跨页、`array` 多行逐行
编号等）。后果是**对账空转**：单元级 tag 对账以契约 `tag` 为真值，契约无档 → 门控既不
要求写手写 `\tag{N}`，也不把写手照印面写出的号判成编造；章级 Q 层又常被**同章别处的
同号**掩盖。该书普查 368 个印面号里 17 个无档（`tools/census_numbering_gaps.py` 的
`numbering_gaps` + `margin_anchor_audit` 两条腿）。

修法有两条正规通道，按「契约里有没有可挂 tag 的展示块」分：
  * **没有**（编号与散文同行内联粘连）→ `config/verify_config/register_formula.py`
    登记 `known_book`（人工确证豁免）；
  * **有、只是没登记号**（本工具，绝大多数）→ **回填契约**。`register_formula` 判据 3
    也明确要求「可行则回填、不必挂号」，两头不冲突。

三本账（缺一即漂移，本工具一次改齐）：
  ① 分章契约 `ch{N}.json`（附录 `appendix{X}.json`）目标 display 公式块的 `tag`  —— 本工具改
  ② `units/ch{N}/manifest.json` 所属单元记录的 `tags`（重算 `node_tags(单元节点)`）—— 本工具改
  ③ `units-translate/ch{N}/manifest.json`（该侧已初始化时）按同一 `file` 同步        —— 本工具改
  ④ 单元正文的 `\tag{N}`                                                             —— **本工具不写**：
     回填后门控会把该号列为该单元的**缺失编号**，由写手（或主代理按印面）在正文补写，
     再重跑 `gate_units`。工具在报告里给出这条待办与确切命令。

保险（全部机械，不靠人自觉）：
  - 默认 dry-run，`--apply` 才写盘；写盘前把每个受影响文件备份到
    `<extract>/_bak_formula_tags/<时间戳>/`，逐次追加台账 `<extract>/_formula_tag_fixes.jsonl`。
  - **印面佐证闸**：以下三条至少命中一条才放行（`--evidence` 目视说明仍必填 ≥20 字）：
      (a) 该号 `(N)` 出现在该单元页区间的 `page_*.json` 文本里；
      (b) 该号是契约 tag 序列里的**夹心空洞**（`lib.tag_attestation.numbering_gaps`）；
      (c) 该号由闸门 ⑱ 的收割判据（`unharvested_anchor_tags` / `glued_anchor_tags`）
          点名——锚点块已在契约里、其展示式却没 tag。
    检测趟与修复趟读**同一批谓词**，修复趟不自造第二套判据。
  - 目标块必须是 **display 公式块**且**当前无 tag**；该号不得已在章内任何块登记（拒绝
    重复挂号）；单元节点必须在 manifest 有**唯一**记录（同键多单元时必须 `--unit` 指定）。
  - 只在「`json.dumps(obj, indent=2)` 与原字节逐字相同」的文件上整文件重写，否则拒绝；
    写出后再断言「去掉新增 tag 即回到原字节」，保证零附带改动。

用法:
  # 自动定位（推荐）：由 ⑱ 的收割判据点名，无需手填节点
  python tools/backfill_formula_tags.py <extract_dir> 12 --number 28 --auto \\
      --evidence "fitz 裁物理页282：(28) 印在 ζ(s,a) 多行展开式左缘" [--apply]
  # 手工定位：给单元键 + 公式正则（或 --list-blocks 看序号后用 --block）
  python tools/backfill_formula_tags.py <extract_dir> 12 --number 30 --node 定理12.23 \\
      --needle "1 - \\\\delta \\\\leq" --evidence "..."
  python tools/backfill_formula_tags.py <extract_dir> 12 --list        # 该章待回填清单
退出码：0 = 已写出 / dry-run 可行 / 已在账（幂等）；2 = 拒绝（未写任何文件）。
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

from data.book_structure.book_structure import (node_tags, prime_chapter_kinds,  # noqa: E402
                                                resolve_chapter_json_path, unit_dir_name)
from lib.tag_attestation import (collect_contract_tags, glued_anchor_tags,  # noqa: E402
                                 numbering_gaps, unharvested_anchor_tags)

_UNIT_TYPES = ("item", "desc", "exercise", "section")
_NUM_RE = re.compile(r"^[1-9][0-9]{0,2}[a-z]?$")


class Refuse(Exception):
    """拒绝写出（未触碰任何文件）。"""


# ── JSON：只在标准 indent=2 形上整文件重写 ──────────────────────────────────
def load_strict(path):
    with io.open(path, encoding="utf-8") as f:
        raw = f.read()
    obj = json.loads(raw)
    if dumps(obj) != raw:
        raise Refuse("%s：不是 indent=2 标准 JSON 形，拒绝整文件重写（先人工核对）" % path)
    return obj, raw


def dumps(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


def _mkdir_unique(bak):
    """秒级时间戳在同一批多次调用里会撞车（驱动脚本循环调用即撞），撞了就加序号，绝不复用已有备份目录。"""
    cand, i = bak, 0
    while True:
        try:
            os.makedirs(cand)
            return cand
        except FileExistsError:
            i += 1
            cand = "%s-%d" % (bak, i)


# ── 契约遍历（节点 = 带 key 的 dict；内容块 = 带 text/formula/image 的裸 dict）──
def child_nodes(node):
    return [c for c in (node.get("sub_sec") or []) if isinstance(c, dict)]


def all_nodes(tree):
    out = []

    def rec(n):
        for c in child_nodes(n):
            if c.get("key") is not None:
                out.append(c)
            rec(c)

    rec(tree)
    return out


def parent_map(tree):
    pm = {}

    def rec(n, parent):
        for c in child_nodes(n):
            pm[id(c)] = n
            rec(c, c if c.get("key") is not None else parent)

    rec(tree, None)
    return pm


def formula_blocks(node):
    """节点子树内的公式块（display 与行内都要，按文档序，含 proof 子节点）。

    🔴 不预先筛 display：行内块也必须**可见并可被拒**——`--needle` 命中行内块时要给出
    「走 register_formula」的明确指引，而不是含糊的「命中 0 个」。
    """
    out = []

    def rec(n):
        for c in child_nodes(n):
            if c.get("formula") is not None:
                out.append(c)
            rec(c)

    rec(node)
    return out


def find_node(tree, key):
    hits = [n for n in all_nodes(tree) if str(n.get("key")) == str(key)]
    if not hits:
        raise Refuse("契约里找不到 key=%r 的节点" % key)
    if len(hits) > 1:
        raise Refuse("契约里 key=%r 命中 %d 个节点，无法定位唯一节点（拒绝猜）"
                     % (key, len(hits)))
    return hits[0]


def path_to_block(tree, block):
    """根到目标内容块的 sub_sec 下标路径（按对象身份），用于在副本上复现同一改动。"""
    def rec(n, trail):
        for i, c in enumerate(n.get("sub_sec") or []):
            if c is block:
                return trail + [i]
            if isinstance(c, dict):
                r = rec(c, trail + [i])
                if r is not None:
                    return r
        return None

    path = rec(tree, [])
    if path is None:
        raise Refuse("目标块不在契约树里（内部错误）")
    return path


def follow(tree, path):
    node = tree
    for i in path:
        node = (node.get("sub_sec") or [])[i]
    return node


def owning_unit_node(node, pm, unit_keys):
    cur = node
    while cur is not None:
        if str(cur.get("key")) in unit_keys:
            return cur
        cur = pm.get(id(cur))
    return None


# ── manifest ────────────────────────────────────────────────────────────────
def manifest_paths(extract_dir, ch_key):
    sub = unit_dir_name(ch_key)
    out = []
    for side in ("units", "units-translate"):
        p = os.path.join(extract_dir, "book_structure", side, sub, "manifest.json")
        if os.path.isfile(p):
            out.append((side, p))
    if not out:
        raise Refuse("找不到 units/%s/manifest.json（先跑 split_draft_units）" % sub)
    return out


def pick_entry(man, ukey, unit_file, side):
    """该 key 下的单元记录；同键多义时必须 --unit 指定（译侧按同名 file 反查）。"""
    cands = [u for u in (man.get("units") or [])
             if str(u.get("key")) == str(ukey) and u.get("type") in _UNIT_TYPES]
    if unit_file:
        cands = [u for u in cands if u.get("file") == unit_file
                 or u.get("id") == unit_file]
        if not cands:
            raise Refuse("%s 侧 manifest 里没有 file/id=%r 的记录（key=%r）"
                         % (side, unit_file, ukey))
    if not cands:
        raise Refuse("key=%r 在 %s 侧 manifest 无单元记录（type 须为 %s）"
                     % (ukey, side, _UNIT_TYPES))
    if len(cands) > 1:
        raise Refuse("key=%r 对应 %d 个单元记录（同节内条目共用序标），必须用 "
                     "--unit <file> 指定该编号属于哪一个：%s"
                     % (ukey, len(cands), ", ".join(str(c.get("file")) for c in cands)))
    return cands[0]


# ── 印面佐证 ────────────────────────────────────────────────────────────────
def harvest_candidates(tree):
    return unharvested_anchor_tags(tree) + glued_anchor_tags(tree)


def page_anchor_hit(extract_dir, num, lo, hi):
    if not lo:
        return False
    pat = re.compile(r"[(\[（]\s*%s\s*[)\]）]" % re.escape(str(num)))
    for pno in range(int(lo) - 1, int(hi or lo) + 2):
        p = os.path.join(extract_dir, "page_%03d.json" % pno)
        if not os.path.isfile(p):
            continue
        try:
            with io.open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        for t in (d.get("text") or []):
            if pat.search(str(t.get("text") or "")):
                return True
    return False


def corroborate(extract_dir, tree, num, unit_node):
    reasons = []
    if str(num) in {str(h[0]) for h in numbering_gaps(tree)}:
        reasons.append("(b) 契约 tag 序列夹心空洞")
    if str(num) in {str(n) for _k, n, _f in harvest_candidates(tree)}:
        reasons.append("(c) 闸门⑱收割判据点名")
    if page_anchor_hit(extract_dir, num, unit_node.get("page_start"),
                       unit_node.get("page_end")):
        reasons.append("(a) 页区间 page_*.json 有 (N) 锚点")
    return reasons


# ── 定位目标块 ──────────────────────────────────────────────────────────────
def resolve(tree, args, unit_keys, pm):
    """→ (单元节点, 目标 display 块, 定位方式说明)。"""
    if args.auto:
        cands = [(k, n, f) for k, n, f in harvest_candidates(tree)
                 if str(n) == str(args.number)]
        if not cands:
            raise Refuse("--auto：⑱ 收割判据未点名该号（改用 --node + --needle/--block）")
        keys = {str(k) for k, _n, _f in cands}
        if len(keys) > 1:
            raise Refuse("--auto：该号在 %d 个节点被点名 %s，须人工定夺"
                         % (len(keys), ", ".join(sorted(keys))))
        anchor_key, _n, frag = cands[0]
        anchor = find_node(tree, anchor_key)
        un = owning_unit_node(anchor, pm, unit_keys)
        if un is None:
            raise Refuse("锚点节点 %s 及其祖先都没有单元记录" % anchor_key)
        hits = [b for b in formula_blocks(un)
                if b.get("display") and not b.get("tag") and str(b.get("formula")).startswith(frag[:40])]
        if len(hits) != 1:
            raise Refuse("--auto：锚点 %s 里按片段匹配到 %d 个未挂号公式块，"
                         "改用 --node %s --block 指定"
                         % (anchor_key, len(hits), un.get("key")))
        return un, hits[0], "--auto(⑱锚点 %s)" % anchor_key

    un = find_node(tree, args.node)
    blocks = formula_blocks(un)
    if not args.needle and args.block is None:
        un_tagged = [b for b in blocks if not b.get("tag")]
        if len(un_tagged) != 1:
            raise Refuse("节点 %r 有 %d 个未挂号公式块，无法唯一确定；"
                         "加 --needle 或 --block（--list-blocks 可列出）"
                         % (args.node, len(un_tagged)))
        return un, un_tagged[0], "唯一未挂号块"
    if args.needle:
        try:
            rx = re.compile(args.needle)
        except re.error as e:
            raise Refuse("--needle 不是合法正则：%s" % e)
        sel = [b for b in blocks if rx.search(str(b.get("formula")))]
        if len(sel) != 1:
            raise Refuse("--needle %r 命中 %d 个公式块（须唯一）；"
                         "用 --list-blocks 看序号后改 --block" % (args.needle, len(sel)))
        return un, sel[0], "--needle"
    # 🔴 --block 的下标与 --list-blocks 打印的序号**同一坐标系**（全部公式块，文档序），
    #    否则「照列表抄序号」会错位到别的公式上；已挂号的块由后续 tag 冲突闸拒绝。
    if not (0 <= args.block < len(blocks)):
        raise Refuse("--block %d 越界（该节点公式块共 %d 个，序号 0..%d）"
                     % (args.block, len(blocks), len(blocks) - 1))
    return un, blocks[args.block], "--block %d" % args.block


# ── 主流程 ──────────────────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("extract_dir")
    ap.add_argument("ch_key")
    ap.add_argument("--number", help="要回填的印刷公式编号（原书裸号）")
    ap.add_argument("--auto", action="store_true", help="由闸门⑱收割判据自动定位")
    ap.add_argument("--node", help="单元节点键（契约 / manifest 的 key）")
    ap.add_argument("--unit", help="同键多单元时指定 file 或 id")
    ap.add_argument("--needle", help="公式文本正则，须唯一命中该节点的公式块")
    ap.add_argument("--block", type=int, help="公式块序号（与 --list-blocks 同坐标系，文档序 0 起）")
    ap.add_argument("--evidence", default="")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--list-blocks", action="store_true", help="列出该节点的 display 块")
    ap.add_argument("--list", action="store_true", help="列该章 ⑱ 点名 + 夹心空洞")
    a = ap.parse_args(argv)

    try:
        # 🔴 先灌注该书的 chapter_map kind（补篇/附录前缀判据），否则 `unit_dir_name('S')`
        # 会算成 `appendixS` → 该章单元目录「找不到」→ 第②③本账静默跳过（与
        # `tools/deregister_formula_tags.py` 同源缺陷，判据见其 `unit_dirs` 注释）。
        prime_chapter_kinds(a.extract_dir)
        cpath = resolve_chapter_json_path(a.extract_dir, a.ch_key)
        if not cpath or not os.path.isfile(cpath):
            raise Refuse("找不到分章契约（%s）" % cpath)
        tree, craw = load_strict(cpath)

        if a.list:
            print("⑱ 收割点名（unharvested + glued）：")
            for k, n, f in harvest_candidates(tree):
                print("  node=%-14s num=%-4s %s" % (k, n, str(f)[:70]))
            print("夹心空洞（契约 tag 序列缺号，两侧邻居在账）：")
            for hole in numbering_gaps(tree):
                print("  缺 %s（%s 与 %s 之间）" % hole)
            return 0

        if not a.number:
            raise Refuse("需要 --number（或用 --list 看该章待回填清单）")
        if not _NUM_RE.match(str(a.number)):
            raise Refuse("--number %r 形态不像印刷编号（拒绝登记 0/00 类 OCR 碎片）"
                         % a.number)
        if len(a.evidence.strip()) < 20:
            raise Refuse("--evidence 必填且不少于 20 字（印面出处：页 / 行 / 渲染方式）")
        if not a.auto and not a.node:
            raise Refuse("定位方式缺失：--auto 或 --node")

        if str(a.number) in {str(n) for _k, n in collect_contract_tags(tree)}:
            print("NO-OP     章 %s 契约已登记 %s（该号在账，无需回填）"
                  % (a.ch_key, a.number))
            return 0

        manifests = manifest_paths(a.extract_dir, a.ch_key)
        man0, _mraw = load_strict(manifests[0][1])
        unit_keys = {str(u.get("key")) for u in (man0.get("units") or [])
                     if u.get("type") in _UNIT_TYPES}
        pm = parent_map(tree)

        if a.list_blocks:
            # 定位辅助：只列块，不做佐证/不写盘，供人工挑 --needle / --block
            if not a.node:
                raise Refuse("--list-blocks 需要 --node")
            for i, b in enumerate(formula_blocks(find_node(tree, a.node))):
                print("%s [%d] display=%-5s tag=%-4s %s"
                      % ("*" if not b.get("tag") else " ", i, bool(b.get("display")),
                         b.get("tag") or "-", str(b.get("formula"))[:90]))
            return 0

        unit_node, blk, how = resolve(tree, a, unit_keys, pm)
        ukey = str(unit_node.get("key"))

        if blk.get("formula") is None:
            raise Refuse("目标块不是公式块")
        if not blk.get("display"):
            raise Refuse("目标块是**行内**公式：编号应随散文走 register_formula 登记通道，"
                         "不回填 tag")
        if blk.get("tag"):
            raise Refuse("目标块已登记 tag=%r，拒绝覆盖真实编号" % blk.get("tag"))

        reasons = corroborate(a.extract_dir, tree, a.number, unit_node)
        if not reasons:
            raise Refuse("无印面佐证：该号既不在页区间锚点里、也不是夹心空洞、⑱ 也未点名"
                         "——回填等于凭空编号，拒绝（确有其号请先补页证据或走 register_formula）")

        # ① 契约：先按对象身份定位，再在活树上改（node_tags 要看到新号），
        #    最后断言「去掉新增 tag 即回到原字节」，保证零附带改动。
        path = path_to_block(tree, blk)
        blk["tag"] = str(a.number)
        after_craw = dumps(tree)
        undo = copy.deepcopy(tree)
        del follow(undo, path)["tag"]
        if dumps(undo) != craw:
            raise Refuse("契约改动不止目标块的 tag（一致性断言失败），拒绝写出")
        lit = '"tag": "%s"' % a.number
        if after_craw.count(lit) != craw.count(lit) + 1:
            raise Refuse("新增编号串计数异常（拒绝写出）")

        new_tags = node_tags(unit_node)
        targets = [(cpath, craw, after_craw)]
        touched = []
        src_file = None
        for side, mp in manifests:
            man, mraw = load_strict(mp)
            entry = pick_entry(man, ukey, a.unit if side == "units" else src_file, side)
            if side == "units":
                src_file = entry.get("file")
            old_tags = list(entry.get("tags") or [])
            entry["tags"] = new_tags
            touched.append((side, entry.get("file"), old_tags, new_tags))
            targets.append((mp, mraw, dumps(man)))

        print("章        = %s   契约=%s" % (a.ch_key, os.path.basename(cpath)))
        print("单元节点  = %s（%s，页 %s-%s）"
              % (ukey, unit_node.get("type"), unit_node.get("page_start"),
                 unit_node.get("page_end")))
        print("定位方式  = %s" % how)
        print("目标公式  = %s" % str(blk.get("formula"))[:100])
        print("新增编号  = (%s)" % a.number)
        print("印面佐证  = %s" % "; ".join(reasons))
        print("目视证据  = %s" % a.evidence.strip())
        for side, fname, old, new in touched:
            print("manifest  %s/%s  tags %s → %s" % (side, fname, old, new))
        for path_, before, after in targets:
            print("%s %s" % ("=" if before == after else "~",
                             os.path.basename(path_)))
        if all(b == af for _p, b, af in targets):
            print("NO-OP     三本账已一致，无需写出")
            return 0
        if not a.apply:
            print("DRY-RUN（未写盘）：加 --apply 落盘")
            return 0

        bak = _mkdir_unique(os.path.join(a.extract_dir, "_bak_formula_tags",
                                         time.strftime("%Y%m%d-%H%M%S")))
        for pth, before, after in targets:
            io.open(os.path.join(bak, "%s__%s" % (Path(pth).parent.name,
                                                  os.path.basename(pth))),
                    "w", encoding="utf-8", newline="\n").write(before)
            json.loads(after)
        for pth, _b, after in targets:
            io.open(pth, "w", encoding="utf-8", newline="\n").write(after)
        rec = os.path.join(a.extract_dir, "_formula_tag_fixes.jsonl")
        with io.open(rec, "a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                "extract_dir": os.path.abspath(a.extract_dir),
                                "ch_key": str(a.ch_key), "number": str(a.number),
                                "unit_key": ukey, "how": how,
                                "formula_head": str(blk.get("formula"))[:80],
                                "corroboration": reasons,
                                "evidence": a.evidence.strip(),
                                "manifest_tags": new_tags,
                                "files": [os.path.basename(p) for p, *_ in targets],
                                "backup": bak}, ensure_ascii=False) + "\n")
        print("APPLIED   备份=%s 台账=%s" % (bak, rec))
        print("待办（第④本账：单元正文补 `\\tag{%s}` 后重跑门控）：" % a.number)
        print("  python flows/write-source/script/gate_units.py \"%s\" %s"
              % (a.extract_dir, a.ch_key))
        return 0
    except Refuse as e:
        print("REFUSE: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
