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
  - **印面佐证闸**：以下五条至少命中一条才放行（`--evidence` 目视说明仍必填 ≥20 字）：
      (a) 该号 `(N)` 出现在该单元页区间的 `page_*.json` 文本里；
      (b) 该号是契约 tag 序列里的**夹心空洞**（`lib.tag_attestation.numbering_gaps`）；
      (c) 该号由闸门 ⑱ 的收割判据（`unharvested_anchor_tags` / `glued_anchor_tags`）
          点名——锚点块已在契约里、其展示式却没 tag。
      (d) 契约里有该号的**整块** `(N)` 锚点、且邻接闸判它与目标展示式**相邻**。
          动因：锚点块本身就是页文字层收割来的印面证据，而 (a) 用的是**宿主节点**的
          页窗（条目/证明跨页时 `page_start == page_end` 只有一页，实测本书 ch6 有
          10 个号、ch5 有 5.7.22 因此被 (a) 挡住，目视印面确有其号）。(d) 只在邻接
          **成立**时顶上，配对错照样被邻接闸否决，故不需要放宽 (a) 的窗口。
      (e) `--anchor-page <页号>`：判用人指出该号印在哪一物理页，工具**自己回查**该页
          `page_*.json` 的文字层（`page_anchor_hit`，与 (a) 同一谓词），查不到即不认。
          用于「契约里那个锚点被 OCR 粘进了表格行/句子（(d) 无从判）+ 宿主页窗不含该页
          （(a) 取不到）」的双盲形态——页号由人给，**号在不在页上仍由工具查**。
    检测趟与修复趟读**同一批谓词**，修复趟不自造第二套判据。
  - 目标块必须是 **display 公式块**且**当前无 tag**；该号不得已在章内任何块登记（拒绝
    重复挂号）；单元节点必须在 manifest 有**唯一**记录（同键多单元时必须 `--unit` 指定）。
  - 🔴 **锚点邻接闸**（否决「号真印但**挂错块**」，判据见 `anchor_adjacency` 上方注释）：该号
    若在契约里有**整块** `(N)` 锚点，目标 display 必须是该锚点的
      ① **紧邻块**（同一条内容序列，左右皆可，多行公式组允许跳过连续锚点），或
      ② 锚点**向后**跳过若干「非散文碎片」（行内公式 / 不含英文词的 text 碎片）后的
         **第一条展示式**（印面版式：编号行在展示式**上方**自成一行，同一条公式常被
         OCR 拆成「首行文字 + display」两块；本书 5 笔点名复核里 4 笔即此形）。
         向后行走**遇成句英文即停**——本书印面确有「整行散文被编号」的式子
         （(3.2.26) = 「the assignment … is made at random, i.e., with probability 1/2
         each …」），它的编号后面跟的是句子，跨过句子去配下一条展示式正是要拦的形。
    向前不做②的放宽。否则拒绝。动因 = 批量驱动的机械夹逼判据（「前后两在账号之间
    唯一未挂号展示块」）对中间的 text/表格块完全失明，实测把真挨着概率表的 (6.5.10)
    挂到了上面那条印面无号的展示式上、把挨着一行**被编号散文**的 (3.2.26) 挂到了下面
    第 32 块的 `I_j` 展示式（2026-10-16 两笔均已 `deregister_formula_tags.py --mispaired` 摘回）。
    契约里没有整块锚点（粘连 / 表格行 / OCR 整块漏）时本闸**不判**，既往行为不变。
    🔴 本闸仍会**误伤**一种形态：散文回引「The asymptotic level of (3.5.7) is …」被 OCR 切成
    独立块 `(3.5.7)`（本书普查 23 处点名里 8 处即此类，锚点在别节点或挨着整句散文）。
    因此留了具名出口 `--confirm-non-adjacent`：目视印面确认后方可放行，台账记
    `adjacency_confirmed: true`（机械批量驱动不会传这个旗，所以它照样被拦在门外）。
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
# 印刷公式编号形态：逐段 1–3 位、**不以 0 起**（`0`/`00`/`01` 是 OCR 碎片），段间点分，
# 末段可带一个小写字母后缀（`28a`），任一段可以是字母/罗马章位（附录/补篇 `(A.3)`、
# 罗马卷位 `(II.5)`）。
# 🔴 旧式 `^[1-9][0-9]{0,2}[a-z]?$` 只认**章内单级**号，把「按节重启」的多级号整类拒掉：
#   Lehmann《Elements of Large-Sample Theory》全书条目与公式都是 `(1.1.9)` 三级形，
#   于是印面确在、契约展示块却无 tag 的漏号在这条正规回填通道上一律 REFUSE（形态步就退），
#   写手只能把该式留成无 tag 行间式，Q 层与门控两头永远对不上。
# 🔴 该闸只校验**人工 `--number` 输入形态**（唯一消费点），不参与任何自动判据扫描，
#   放宽它不会在既有书上产生假阳——真正的假阳防线是印面佐证闸与 --evidence。
_SEG = r"(?:[1-9][0-9]{0,2}|[A-Z]{1,4}[0-9]{0,2})"
_NUM_RE = re.compile(r"^%s(?:\.%s){0,4}[a-z]?$" % (_SEG, _SEG))


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


def find_node(tree, key, want_type=None):
    """契约里按 key 定位节点；**同键多型**时按 want_type（manifest 记录的 ntype）收窄。

    🔴 印面把条目序标按「节内该类型第 K 条」起号的书（Lehmann 三级号 `1.1-1`：
    Definition 1.1.1 / Lemma 1.1.1 / Example 1.1.1 全挂 key=1.1-1），同一 key 命中
    3 个节点是本类的**常态**；旧判据一律拒绝，等于让这类书永远回填不了漏号。
    收窄后仍不唯一（0 或 ≥2）照旧拒绝，绝不猜。
    """
    hits = [n for n in all_nodes(tree) if str(n.get("key")) == str(key)]
    if not hits:
        raise Refuse("契约里找不到 key=%r 的节点" % key)
    if len(hits) > 1 and want_type:
        narrowed = [n for n in hits if str(n.get("type") or "") == str(want_type)]
        if len(narrowed) == 1:
            return narrowed[0]
        hits = narrowed if narrowed else hits
    if len(hits) > 1:
        raise Refuse("契约里 key=%r 命中 %d 个节点（type=%s），无法定位唯一节点（拒绝猜）；"
                     "该编号属于哪一个单元请用 --unit <file> 指定"
                     % (key, len(hits), sorted({str(n.get("type")) for n in hits})))
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


def corroborate(extract_dir, tree, num, unit_node, adj=None, anchor_pages=()):
    reasons = []
    if str(num) in {str(h[0]) for h in numbering_gaps(tree)}:
        reasons.append("(b) 契约 tag 序列夹心空洞")
    if str(num) in {str(n) for _k, n, _f in harvest_candidates(tree)}:
        reasons.append("(c) 闸门⑱收割判据点名")
    if page_anchor_hit(extract_dir, num, unit_node.get("page_start"),
                       unit_node.get("page_end")):
        reasons.append("(a) 页区间 page_*.json 有 (N) 锚点")
    if adj is True:
        reasons.append("(d) 契约内有整块 (N) 锚点且与目标展示式相邻"
                       "（锚点块本身即页文字层收割来的印面证据；条目/证明跨页时 (a) 的"
                       "单页页窗取不到，本条顶上）")
    for p in anchor_pages or ():
        if page_anchor_hit(extract_dir, num, p, p):
            reasons.append("(e) 指定页 p%s 的页文字层里有该号（页号由判用人给出，"
                           "工具自己回查该页，查不到即不认）" % p)
            break
    return reasons


# ── 锚点**邻接**闸：机械夹逼不构成印面证据（配对错的机械否决）────────────────
# 🔴 成因实测（2026-10-16 Lehmann ch6 (6.5.10)）：批量驱动按「前后两在账号之间唯一
# 未挂号展示块」这条夹逼判据挑块，把号挂到了 Example 6.5.3 里的
# `P(X*₍₁₎=b, X*₍₂₎=b, X*₍₃₎=c)=3/27`；而契约同一节点的内容序列里
# **就躺着**整块锚点 `(6.5.10)`，它挨的是下面那张概率表（`bbb bbc … / 1/27 3/27 …`，
# 契约里只是 text 块）。夹逼判据只看**展示块序列**，对中间的文字/表格块完全失明，
# 于是「唯一未挂号的 display」≠「印面带号的块」。
# 本闸用契约**自己的**印面证据否决这类配对：该号若在契约里有整块 `(N)` 锚点，
# 目标块就必须与该锚点**相邻**（同一条内容序列、左右皆容、允许多行公式组共用一列
# 编号时跳过连续锚点），否则拒绝写出并打印锚点位置与它实际挨着的块。
# 锚点被 OCR 粘连成 `(9) p(k)`、混进表格行或整块漏掉时，契约里没有整块锚点 ⇒
# 本闸**不判**（保持既往行为），因为那种情形给不出位置信息，硬判会造成假拒。
_ANCHOR_STANDALONE_RE = re.compile(r"^\s*[（(\[]\s*([^\s()\[\]（）]{1,16}?)\s*[)）\]]\s*[.。]?\s*$")
# 锚点主体须**像编号**：`(b, b, c)` / `(X*)` 这类独立成行的元组不是编号列，
# 若把它们当锚点参与「跳过连续锚点」的行走，会把真锚点的邻接判据带偏。
# 纯字母且无分隔（`(a)` = 子项标号，不是公式号）也不算——要求含数字或含分隔点。
_ANCHOR_NUM_LIKE_RE = re.compile(r"^[0-9A-Za-z]{1,4}(?:[.\-·][0-9A-Za-z]{1,4}){0,4}[a-z]?$")


def standalone_anchor(block):
    """内容块 → 该块**整块**是否为 `(N)` 印刷锚点（是则返回裸号，否则 None）。

    与闸门 ⑱ 的 `_ANCHOR_ONLY_RE` 同一口径（整块-only，不含粘连形）：句中回引
    （`… in generalization of (6.5.6).`）与粘连形都给不出「该号挨着哪条公式」的位置信息。
    """
    if not isinstance(block, dict) or block.get("text") is None:
        return None
    m = _ANCHOR_STANDALONE_RE.match(str(block.get("text")).strip())
    if not m:
        return None
    g = m.group(1).strip()
    if not _ANCHOR_NUM_LIKE_RE.match(g):
        return None
    return g if (re.search(r"[0-9]", g) or any(s in g for s in ".-·")) else None


def anchor_paths(tree, num):
    """契约树 → 整块 `(num)` 锚点的 sub_sec 下标路径列表（文档序）。"""
    out = []

    def rec(n, trail):
        for i, c in enumerate(n.get("sub_sec") or []):
            if not isinstance(c, dict):
                continue
            if standalone_anchor(c) == str(num):
                out.append(trail + [i])
            rec(c, trail + [i])

    rec(tree, [])
    return out


def _is_display(b):
    return (isinstance(b, dict) and b.get("formula") is not None
            and bool(b.get("display")))


# 「碎片 vs 散文」的可机读分界：印面被编号的**散文行**（实测 (3.2.26)
# 「the assignment … is made at random, i.e., with probability 1/2 each …」）与
# 「同一条公式被切开的碎片」（实测 (2.1.14) `(x-x)=∑x-()xx-1`、(2.8.46)
# `n-Cov(XN1, XN2) .`）的区别就是后者不含英文词。
_PROSE_WORD_RE = re.compile(r"[A-Za-z]{5,}")
_PROSE_PAIR_RE = re.compile(r"\b[A-Za-z]{4,}\b.*\b[A-Za-z]{4,}\b")


def _is_prose_fragment(b):
    """text 块读起来像**成句英文**（≥1 个 5+ 字母词，或 2 个 4+ 字母词）→ True。

    行内公式块不算散文（它们本就是公式的一部分）。
    """
    if not isinstance(b, dict) or b.get("text") is None:
        return False
    t = str(b.get("text"))
    return bool(_PROSE_WORD_RE.search(t) or _PROSE_PAIR_RE.search(t))


def _first_display_forward(seq, aidx):
    """锚点**向后**（文档序）遇到的第一条 display 的下标；走到序列尾/条目边界则 None。

    跳过的是「同一条印面展示式被 OCR 切碎的碎片」：非散文的 `text` 块与**行内**公式块。
    遇到带 key 的子条目（既非 text 亦非 inline formula）或**成句散文**即停——
    散文停下是因为本书印面确有「整行散文被编号」的式子（(3.2.26)），它的编号后面
    跟着的是句子而不是公式；跨过句子去配下一条展示式正是本闸要拦的错挂形。
    """
    k = aidx + 1
    while 0 <= k < len(seq) and isinstance(seq[k], dict):
        b = seq[k]
        if _is_display(b):
            return k
        if standalone_anchor(b):
            k += 1
            continue
        if _is_prose_fragment(b):
            return None
        if b.get("text") is not None or (b.get("formula") is not None
                                         and not b.get("display")):
            k += 1
            continue
        return None
    return None


def anchor_adjacency(tree, blk, num):
    """→ (判定, 说明)：判定 True=邻接成立 / False=配对错 / None=契约无整块锚点（不判）。

    两种成立形（印面编号行在展示式**上方**，故向后是版面方向）：
      * **紧邻**（左右皆可，允许多行公式组共用一列编号时跳过连续锚点）；
      * **向后第一条展示式**：锚点与目标之间只夹着 text/行内碎片（实测：编号行下面
        那条公式常被 OCR 拆成「首行文字 + display」两块，或 display 前先出一条同式
        的行内形）。**向前**不做这种放宽——实测两个真错挂（(6.5.10) 挨概率表行、
        (3.2.26) 挨一行被编号的散文）都是「锚点后面跟着散文/表行、目标在远处」。
    """
    paths = anchor_paths(tree, num)
    if not paths:
        return None, ("契约内无 (%s) 整块锚点（粘连 / 表格行 / OCR 漏），邻接闸不判" % num)
    tp = path_to_block(tree, blk)
    same = [p for p in paths if p[:-1] == tp[:-1]]
    seq = (follow(tree, tp[:-1]).get("sub_sec") or [])
    for ap in same:
        aidx = ap[-1]
        for step in (-1, 1):
            k = aidx + step
            while 0 <= k < len(seq) and isinstance(seq[k], dict) and standalone_anchor(seq[k]):
                k += step
            if k == tp[-1]:
                return True, ("锚点 (%s) 在同一内容序列的块 %d，与目标块 %d 相邻"
                              % (num, aidx, tp[-1]))
    for ap in same:
        f = _first_display_forward(seq, ap[-1])
        if f is not None and f == tp[-1]:
            return True, ("锚点 (%s) 在块 %d，向后跳过 %d 个文字/行内碎片后的**第一条**"
                          "展示式就是目标块 %d（印面编号行在其上方，同一公式被 OCR 切开）"
                          % (num, ap[-1], f - ap[-1] - 1, f))
    where = ", ".join("节点 %s 块 %d（挨着 %s）"
                      % (follow(tree, p[:-1]).get("key"), p[-1],
                         _neighbour_head(follow(tree, p[:-1]), p[-1]))
                      for p in paths[:4])
    fwd = [(_first_display_forward(seq, ap[-1]), ap[-1]) for ap in same]
    hint = ""
    if same and fwd and fwd[0][0] is not None:
        hint = "；锚点向后第一条展示式在块 %d（不是目标块）" % fwd[0][0]
    return False, ("(%s) 在契约里有整块锚点 %d 处：%s；目标块却在 %s 的块 %d —— "
                   "既不相邻、也不是锚点向后第一条展示式%s，说明该号印面挨的**不是**"
                   "这条展示式" % (num, len(paths), where,
                                   follow(tree, tp[:-1]).get("key"), tp[-1], hint))


def _neighbour_head(par, aidx):
    """锚点两侧邻居的首串（用于把「该号实际挨的是什么」打印给判用人）。"""
    seq = par.get("sub_sec") or []
    for k in (aidx - 1, aidx + 1):
        if 0 <= k < len(seq) and isinstance(seq[k], dict):
            b = seq[k]
            if b.get("formula") is not None:
                return "公式 %s" % str(b.get("formula"))[:40]
            if b.get("text") is not None:
                return "文字 %s" % str(b.get("text"))[:40]
    return "无邻居"


# ── 定位目标块 ──────────────────────────────────────────────────────────────
def resolve(tree, args, unit_keys, pm, want_type=None):
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

    un = find_node(tree, args.node, want_type)
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
def _want_type(man0, a):
    """同键多型（`1.1-1` 同时是 Definition/Lemma/Example 的序标）时用 --unit 那条
    manifest 记录的 ntype 收窄契约节点；拿不到记录就返回 None，让既有歧义闸照常拒绝。"""
    if a.auto or not a.node:
        return None
    try:
        rec = pick_entry(man0, a.node, a.unit, "units")
    except Refuse:
        return None
    return str(rec.get("ntype") or rec.get("type") or "") or None


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
    ap.add_argument("--confirm-non-adjacent", action="store_true",
                    help="已目视印面、确认该式确实带此号（契约里那个整块锚点是散文回引被"
                         "OCR 切成独立块）；仅用于放行锚点邻接闸，台账留名")
    ap.add_argument("--anchor-page", default="",
                    help="逗号分隔的物理页号：条目跨页导致 (a) 的宿主页窗取不到号时，"
                         "由判用人指定该号印在哪一页；工具自己回查这些页的文字层，"
                         "查不到即不认（佐证 (e)，不是自证）")
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

        manifests = manifest_paths(a.extract_dir, a.ch_key)
        man0, _mraw = load_strict(manifests[0][1])

        if a.list_blocks:
            # 定位辅助：只列块，不做佐证/不写盘，供人工挑 --needle / --block。
            # 🔴 本分支**不得**要求 --number/--evidence：列块正是为了看清目标块再定号，
            #   要求先给号 = 死锁（实测：`--node … --unit … --list-blocks` 被
            #   「需要 --number」直接拒掉，只能靠猜 --block 序号）。
            if not a.node:
                raise Refuse("--list-blocks 需要 --node")
            for i, b in enumerate(formula_blocks(find_node(tree, a.node,
                                                            _want_type(man0, a)))):
                print("%s [%d] display=%-5s tag=%-4s %s"
                      % ("*" if not b.get("tag") else " ", i, bool(b.get("display")),
                         b.get("tag") or "-", str(b.get("formula"))[:90]))
            return 0

        if not a.number:
            raise Refuse("需要 --number（或用 --list 看该章待回填清单）")
        if not _NUM_RE.match(str(a.number)):
            raise Refuse("--number %r 形态不像印刷编号（点分段：1–3 位数字或字母/罗马章位，"
                         "拒绝登记 0/00 类 OCR 碎片）" % a.number)
        if len(a.evidence.strip()) < 20:
            raise Refuse("--evidence 必填且不少于 20 字（印面出处：页 / 行 / 渲染方式）")
        anchor_pages = []
        for tok in str(a.anchor_page or "").replace("，", ",").split(","):
            tok = tok.strip().lstrip("pP")
            if not tok:
                continue
            if not tok.isdigit():
                raise Refuse("--anchor-page %r 不是页号（只收数字，可逗号分隔多个）" % tok)
            anchor_pages.append(int(tok))
        if not a.auto and not a.node:
            raise Refuse("定位方式缺失：--auto 或 --node")

        if str(a.number) in {str(n) for _k, n in collect_contract_tags(tree)}:
            print("NO-OP     章 %s 契约已登记 %s（该号在账，无需回填）"
                  % (a.ch_key, a.number))
            return 0

        unit_keys = {str(u.get("key")) for u in (man0.get("units") or [])
                     if u.get("type") in _UNIT_TYPES}
        pm = parent_map(tree)
        want_type = _want_type(man0, a)

        unit_node, blk, how = resolve(tree, a, unit_keys, pm, want_type)
        ukey = str(unit_node.get("key"))

        if blk.get("formula") is None:
            raise Refuse("目标块不是公式块")
        if not blk.get("display"):
            raise Refuse("目标块是**行内**公式：编号应随散文走 register_formula 登记通道，"
                         "不回填 tag")
        if blk.get("tag"):
            raise Refuse("目标块已登记 tag=%r，拒绝覆盖真实编号" % blk.get("tag"))

        # 🔴 先算邻接：它既是**否决**闸（配对错不放行），也是**佐证** (d)——契约里那个
        # 整块 `(N)` 锚点本身就是从页文字层收割来的印面证据，只是它常常落在宿主节点
        # 页窗之外（条目/证明跨页时 `page_start==page_end` 只有 1 页，实测本书 ch6 有
        # 10 个号因此被 (a) 挡住）。邻接成立 = 「号与式在同一内容序列里挨着」，
        # 位置信息比页窗更强，不需要再放宽 (a) 的窗口。
        adj, adj_note = anchor_adjacency(tree, blk, a.number)
        reasons = corroborate(a.extract_dir, tree, a.number, unit_node, adj=adj,
                              anchor_pages=anchor_pages)
        if not reasons:
            raise Refuse("无印面佐证：该号既不在页区间锚点里、也不是夹心空洞、⑱ 未点名、"
                         "契约里也没有与目标相邻的整块锚点、--anchor-page 给的页里也查不到"
                         "——回填等于凭空编号，拒绝（确有其号请补 --anchor-page <印面页号>"
                         "或走 register_formula）%s"
                         % ("" if adj is not False else "（另：邻接闸已判该号印面挨的不是这条展示式）"))

        if adj is False and not a.confirm_non_adjacent:
            raise Refuse("%s —— 机械夹逼（「两在账号之间唯一未挂号展示块」）不构成印面证据。"
                         "真主是别条展示式请用 --node/--block 指向锚点相邻的那条；"
                         "印面真主是表格/文字行（契约无展示块可挂）则该号**不入账**，"
                         "错挂号请走 tools/deregister_formula_tags.py --mispaired --host non-display；"
                         "已目视印面确认该式确实带此号（契约里那个整块锚点其实是散文回引被"
                         "OCR 切成独立块）则加 --confirm-non-adjacent 复核落账，台账留名"
                         % adj_note)

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
        print("锚点邻接  = %s%s" % (adj_note,
                                    "  ⚠️ 人工复核确认不相邻落账（--confirm-non-adjacent）"
                                    if adj is False else ""))
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
                                "anchor_adjacency": adj_note,
                                "adjacency_confirmed": bool(adj is False),
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
