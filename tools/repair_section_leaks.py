# -*- coding: utf-8 -*-
"""repair_section_leaks.py — 节界泄漏（check_section_leak）四账同步修复驱动。

前置
----
只处理单元制收官书（units / units-translate + manifest + 分章契约 + 交付 md）。
LEAK-A / LEAK-B / LEAK-D 的成因与判据见 ``verify/script/check_section_leak.py``
模块 docstring。

修复语义（与检查器的建议归位同规则）
------------------------------------
* MOVE_WHOLE（LEAK-A / LEAK-B，**仅编号项/习题**）：整节点从 §S 搬到
  home = 「节头锚点 ≤ 节点锚点的最后一个 section」（无 → 章级前言）。契约节点 +
  双侧 manifest 记录同步移动；单元文件正文不变。
* description 类与 LEAK-D / SECORDER：**一律留人工**——写源期引言经过重写，
  泄漏的前节尾部常与本节引言混在同一段落（Weibel 0014_desc 实测），行级锚定
  看不出句级边界；整搬会把本节引言搬进上一节，部分搬须逐条印面裁定句界。

交付侧
------
**不手工搬交付行**：契约 + manifest 改完后按章重新 ``merge_chapter``（自带
gate_units 强制门控）；已按节拆分的数字章随即 ``split_one_file(force)`` 再生节
文件；字母章/合并形态章只 merge。核对（任一失败 = 整章回滚）：
  * 未受影响节文件逐字节相等；
  * 受影响文件非空行多重集守恒（排除纯 ``---`` 行——搬移会改变 V-F 分隔线分布）；
  * 再生节文件名集合与现有集合一致。

用法
----
    python tools/repair_section_leaks.py <book_dir> [--ch N ...] [--apply]
默认 dry-run。--apply 写盘；写盘前逐文件备份 ``<extract>/_bak_leak_repair/<ts>/``，
证据落 ``<extract>/_leak_repair_log.jsonl``。

安全边界
--------
home 判不出 / 节点定位不唯一 / 契约↔manifest 签名多重集不一致 / 再生文件名集合
漂移 / 多重集不守恒：跳过该条或整章回滚，绝不猜。
"""
import argparse
import json
import os
import re
import shutil
import sys
import time
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = None
_c = _HERE
while True:
    if os.path.exists(os.path.join(_c, "SKILL.md")):
        _ROOT = _c
        break
    _p = os.path.dirname(_c)
    if _p == _c:
        break
    _c = _p
if _ROOT is None:
    _ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "lib"), _HERE,
           os.path.join(_ROOT, "verify", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import io
import check_section_leak as csl  # noqa: E402  锚点/判据只此一份
from data.book_structure.book_structure import (  # noqa: E402
    BookStructure, chapter_json_path, unit_dir_name, chapter_label)

_MANIFEST_TYPE = {
    "chapter": "chapter", "section": "section", "description": "desc",
    "exercise": "exercise", "problem": "exercise",
}
_MT_TO_CONTRACT = {"chapter": "chapter", "section": "section",
                   "desc": "description", "exercise": "exercise",
                   "item": "item"}
MOVEABLE = ("LEAK-A", "LEAK-B")


# ------------------------------------------------------------- 小工具 ----

def nk(n):
    return str(csl._node_f(n, "key") or "")


def nt(n):
    return str(csl._node_f(n, "type") or "")


def nname(n):
    return str(csl._node_f(n, "name") or "")


def npg(n):
    return int(csl._node_f(n, "page_start") or 0)


def node_sig(n):
    """契约节点 → manifest 签名 (记录type, key)。"""
    return (_MANIFEST_TYPE.get(nt(n), "item"), nk(n))


def rec_sig(r):
    ct = r.get("ntype") or _MT_TO_CONTRACT.get(str(r.get("type") or ""), "")
    return (_MANIFEST_TYPE.get(ct, "item"), str(r.get("key") or ""))


def walk_unit_nodes(ch_node):
    """契约文档序平铺全部「应有单元记录」的节点——与 split_draft_units.
    walk_container 严格同语义：
      * chapter 自身 → ("chapter", 章 key)；
      * section → 单元 + 下钻（consolidated 章末集中习题节：不出单元、不下钻）；
      * description → 单元（不下钻——孩子全是内容块）；
      * proof → 跳过（item 内部附属，由 item 单元渲染）；
      * exercise / problem → exercise 单元（consolidated 跳过）；
      * 其余 → item 单元；
      * 裸内容块（_is_block）→ 兜底 desc 单元（key=""，与 split 同款）。"""
    out = [ch_node]

    def walk(container):
        for child in (csl._node_f(container, "sub_sec") or []):
            if csl._is_block_el(child):
                out.append({"type": "description", "key": "", "name": ""})
                continue
            t = nt(child)
            if t == "section":
                if csl._node_f(child, "consolidated"):
                    continue
                out.append(child)
                walk(child)
            elif t == "description":
                out.append(child)
            elif t == "proof":
                continue
            elif t in ("exercise", "problem"):
                if csl._node_f(child, "consolidated"):
                    continue
                out.append(child)
            else:
                out.append(child)

    walk(ch_node)
    return out


def find_section(root, key):
    if key == "#chapter":
        return root
    for n in walk_unit_nodes(root):
        if nt(n) == "section" and nk(n) == key:
            return n
    return None


def is_ancestor_of(anc, node):
    return any(n is node for n in walk_unit_nodes(anc))


def is_letter_kind(ch_key):
    kind = str(unit_dir_name(ch_key))
    return not re.match(r"^ch\d+$", kind)


def chapter_num(ch_key):
    m = re.match(r"^(\d+)", str(ch_key))
    return int(m.group(1)) if m else None


# ------------------------------------------------------------- 备份 ----

class Backup(object):
    """写盘前把原文件复制进 <extract>/_bak_leak_repair/<ts>/，可整批回滚。"""

    def __init__(self, ext, ts, dry_run):
        self.dir = os.path.join(ext, "_bak_leak_repair", ts)
        self.dry_run = dry_run
        self._saved = {}    # abs path -> backup copy path
        self.created = []   # 修复过程中新建的临时文件（回滚时删除）

    def touch(self, path):
        p = os.path.abspath(path)
        if p in self._saved:
            return
        if not os.path.exists(p):
            return
        if self.dry_run:
            self._saved[p] = None
            return
        os.makedirs(self.dir, exist_ok=True)
        rel = os.path.relpath(p, ext_root(self.dir))
        dst = os.path.join(self.dir, rel.replace(os.sep, "__"))
        shutil.copy2(p, dst)
        self._saved[p] = dst

    def mark_created(self, path):
        self.created.append(os.path.abspath(path))

    def rollback_all(self):
        # 🔴 先删「纯新建」的临时产物，再恢复备份；同一文件既在备份又在 created
        # （merge 同名覆盖原交付）时以备份为准恢复，**不得**删除（否则恢复被撤销
        # ——ch3 试点实测：EN 交付被这样弄丢）。
        n = 0
        for p in self.created:
            if p in self._saved:
                continue
            if os.path.exists(p):
                os.remove(p)
        for p, dst in self._saved.items():
            if dst and os.path.exists(dst):
                shutil.copy2(dst, p)
                n += 1
        print("[repair] 回滚 %d 个文件、删除 %d 个临时产物"
              % (n, len([p for p in self.created if p not in self._saved])))


def ext_root(dir_path):
    """_bak_leak_repair/<ts> 的上一级 = _extract。"""
    return os.path.dirname(os.path.dirname(os.path.abspath(dir_path)))


# ------------------------------------------------------------- 契约 ----

def detach_node(parent, node):
    subs = parent.get("sub_sec")
    if not isinstance(subs, list):
        return False
    for i, c in enumerate(list(subs)):
        if c is node:
            del subs[i]
            return True
    return False


def anchor_order_insert(home, node, ext, ch):
    """按印刷序插进 home.sub_sec：最后一个锚点 ≤ 节点锚点的孩子之后。"""
    subs = home.setdefault("sub_sec", [])
    a_node = (csl._section_anchor(ext, ch, node) if nt(node) == "section"
              else csl._node_anchor(ext, ch, node))
    if a_node is None:
        subs.append(node)
        return len(subs) - 1
    pos = 0
    for i, c in enumerate(list(subs)):
        if c is node:
            continue
        a_c = (csl._section_anchor(ext, ch, c) if nt(c) == "section"
               else csl._node_anchor(ext, ch, c))
        if a_c is None:
            continue
        if (a_c[0], a_c[1]) <= (a_node[0], a_node[1]):
            pos = i + 1
    subs.insert(pos, node)
    return pos


# ---------------------------------------------------------- manifest ----

def manifest_dir(ext, ch_key, side):
    return os.path.join(ext, "book_structure",
                        "units" if side == "units" else "units-translate",
                        unit_dir_name(ch_key))


def load_manifest(ext, ch_key, side):
    mp = os.path.join(manifest_dir(ext, ch_key, side), "manifest.json")
    if not os.path.exists(mp):
        return None
    with io.open(mp, encoding="utf-8") as f:
        return json.load(f)


def realigned_records(records, sig_seq):
    """按 sig_seq 重排 records（多重集必须恰好一致；同签名稳定分配）。

    严格签名失败时退回**仅按 key** 对齐（老书的 manifest 记录 type 与契约节点
    type 有漂移——convex appendixA 实测：契约 description / 记录 item 同键；
    key 双侧唯一才允许，否则照旧 fail-closed）。"""
    try:
        return _realigned_by(records, sig_seq, rec_sig)
    except ValueError:
        # 仅按 key 稳定配对（同 key 按双侧各自的出现序 pop(0)）：老书记录 type
        # 与契约节点 type 有漂移（convex appendixA 实测：契约 description /
        # 记录 item 同键），且节号与例号可同形碰撞（A.1 既是 §A.1 也是例 A.1）
        # ——只要 key 多重集一致即对齐；错配会以交付多重集守恒断言兜底回滚。
        want = Counter(str(k) for _t, k in sig_seq)
        have = Counter(str(r.get("key") or "") for r in records)
        if want != have:
            raise
        return _realigned_by(records, [k for _t, k in sig_seq],
                             lambda r: str(r.get("key") or ""))


def _realigned_by(records, seq, keyfn):
    want = Counter(seq)
    have = Counter(keyfn(r) for r in records)
    if want != have:
        raise ValueError("多重集不一致：缺 %s / 多 %s"
                         % (dict(want - have), dict(have - want)))
    pools = {}
    for r in records:
        pools.setdefault(keyfn(r), []).append(r)
    return [pools[s].pop(0) for s in seq]


def write_manifest(ext, ch_key, side, man, backup):
    d = manifest_dir(ext, ch_key, side)
    backup.touch(os.path.join(d, "manifest.json"))
    with io.open(os.path.join(d, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------------- 交付 ----

def delivery_file_list(book_dir, ch_key, lang, ch_num):
    """该章该语种交付文件 (merged_names, section_names)。"""
    zh = lang == "zh"
    merged, sections = [], []
    if is_letter_kind(ch_key):
        key = str(ch_key)
        if key in ("appendix", "supplement"):
            pats = [r"^附录\.", r"^附录_", r"^Appendix\.", r"^Appendix_",
                    r"^附录\.md$", r"^Appendix\.md$"]
        else:
            pats = [r"^附录%s[._]" % re.escape(key), r"^附录%s\.md$" % re.escape(key),
                    r"^Appendix%s[._]" % re.escape(key),
                    r"^Appendix%s\.md$" % re.escape(key)]
        for fn in sorted(os.listdir(book_dir)):
            if fn.endswith(".md") and any(re.match(p, fn) for p in pats):
                merged.append(fn)
        return merged, sections
    sec_pat = (r"^第%d章_\d" % ch_num) if zh else (r"^Chapter%d_\d" % ch_num)
    all_pat = (r"^第%d章_" % ch_num) if zh else (r"^Chapter%d_" % ch_num)
    for fn in sorted(os.listdir(book_dir)):
        if not fn.endswith(".md"):
            continue
        if re.match(sec_pat, fn):
            sections.append(fn)
        elif re.match(all_pat, fn):
            merged.append(fn)
    return merged, sections


def snapshot_delivery(book_dir, ch_key, ch_num, lang):
    """merge 前快照该章交付 {文件名: 文本}。"""
    merged, sections = delivery_file_list(book_dir, ch_key, lang, ch_num)
    out = {}
    for fn in merged + sections:
        with io.open(os.path.join(book_dir, fn), encoding="utf-8") as f:
            out[fn] = f.read()
    return out


def sect_key_from_file(path):
    """节拆分件首部 `## §K …` 的章内节键；无则 None。"""
    with io.open(path, encoding="utf-8") as f:
        for ln in f:
            m = re.match(r"^#{1,3}\s+§\s*([0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)", ln)
            if m:
                return m.group(1)
    return None


def top_level_map(ch_node):
    """顶层 section key → 子树内全部 section key 集合。"""
    out = {}
    for c in (csl._node_f(ch_node, "sub_sec") or []):
        if nt(c) == "section":
            keys = set(nk(n) for n in walk_unit_nodes(c) if nt(n) == "section")
            out[nk(c)] = keys
    return out


def _strip_ms(text):
    return Counter(ln for ln in text.split("\n")
                   if ln.strip() and ln.strip() != "---")


def regenerate_and_verify(ext, book_dir, ch_key, ch_num, side, lang, before,
                          touched_tops, backup):
    """merge（+已拆分章 split）再生交付并逐文件核对。失败抛 RuntimeError。"""
    import merge_units as mu  # (flows/write-source/script 由 boot 注入 sys.path)
    import split_chapters as sc  # (tools 目录由本脚本注入 sys.path)
    letter = is_letter_kind(ch_key)
    old_merged, old_sections = delivery_file_list(book_dir, ch_key, lang, ch_num)
    merged_path = mu.merge_chapter(ext, ch_key, units_sub=side)
    backup.mark_created(merged_path)
    if old_sections and not letter:
        paths = sc.split_one_file(merged_path, 1, ch_num, lang,
                                  dry_run=False, force=True)
        new_sections = [os.path.basename(p) for p in paths]
        if os.path.exists(merged_path):
            os.remove(merged_path)
        got, want = set(new_sections), set(old_sections)
        if got != want:
            raise RuntimeError("再生节文件名不一致：多 %s / 缺 %s"
                               % (sorted(got - want), sorted(want - got)))
    else:
        new_sections = []
    # 文件名映射：新名 → 旧名（同名优先；合并稿改名按前缀唯一匹配）
    old_names = set(before.keys())
    now_merged, now_sections = delivery_file_list(book_dir, ch_key, lang, ch_num)
    mapping = {}
    for fn in now_merged + now_sections:
        if fn in old_names:
            mapping[fn] = fn
        else:
            head = fn.split("_")[0]
            cands = [o for o in old_names if o.split("_")[0] == head]
            if len(cands) != 1:
                raise RuntimeError("新交付文件 %s 找不到唯一旧名对应（%s）"
                                   % (fn, sorted(cands)))
            mapping[fn] = cands[0]
    # 顶层键映射（供受影响判定）
    bs = BookStructure.load(ext)
    ch_node = bs.find_chapter(str(ch_key))
    ch_node = ch_node.to_dict() if hasattr(ch_node, "to_dict") else ch_node
    tl = top_level_map(ch_node)

    def touched(fn):
        if not (old_sections and not letter):
            return True  # 合并形态章（无节文件）：整文件按受影响断言
        if "#" in touched_tops or not tl:
            return True
        k = sect_key_from_file(os.path.join(book_dir, fn))
        if k is None:
            return True  # 合并稿/附录：整文件断言
        for top, keys in tl.items():
            if k in keys:
                # 🔴 touched_tops 里可能是**子节键**（home = §10.1.3）：只要它落
                # 在本文件顶层节的子树内，本文件即受影响（convex ch10 实测）
                return any(t == top or t in keys for t in touched_tops)
        return True  # 键认不出 → 按受影响断言（多重集）

    def read(fn):
        with io.open(os.path.join(book_dir, fn), encoding="utf-8") as f:
            return f.read()

    touched_pairs = []
    for fn in sorted(set(mapping.values()) | set(mapping.keys())):
        old_fn = mapping.get(fn)
        if old_fn is None:
            old_fn = fn
        path = os.path.join(book_dir, fn)
        backup.touch(path)
        new_text = read(fn)
        old_text = before[old_fn]
        if touched(fn):
            # 🔴 内容跨文件搬移必然改变单文件多重集（接收文件多一块、让出文件
            # 少一块）——守恒断言在全部受影响文件的**并集**上做（循环后统一核）。
            touched_pairs.append((old_fn, fn))
        else:
            if new_text != old_text:
                raise RuntimeError("未受影响交付文件被改动：%s" % fn)
        if old_fn != fn and os.path.exists(os.path.join(book_dir, old_fn)):
            backup.touch(os.path.join(book_dir, old_fn))
            os.remove(os.path.join(book_dir, old_fn))
    if touched_pairs:
        old_ms, new_ms = Counter(), Counter()
        for old_fn, fn in touched_pairs:
            old_ms += _strip_ms(before[old_fn])
            new_ms += _strip_ms(read(fn))
        if old_ms != new_ms:
            diff = (list((old_ms - new_ms).elements())[:4],
                    list((new_ms - old_ms).elements())[:4])
            raise RuntimeError("受影响交付文件并集非空行多重集不守恒（多 %s / 少 %s）"
                               % diff)
    # 旧文件里已消失且未在 mapping 中的（如旧合并稿被拆分消耗）：核对多重集后删除
    consumed = set(old_names) - set(mapping.values()) - set(mapping.keys())
    for old_fn in sorted(consumed):
        p = os.path.join(book_dir, old_fn)
        if not os.path.exists(p):
            continue
        raise RuntimeError("旧交付文件 %s 未被再生映射消费，位置异常" % old_fn)


# ------------------------------------------------------------- 主流程 ----

def plan_chapter(ext, bs, ch_key):
    node = bs.find_chapter(str(ch_key))
    if node is None:
        return [], None
    node = node.to_dict() if hasattr(node, "to_dict") else node
    fnd = csl.section_leak_findings(ext, str(ch_key), npg(node),
                                    int(csl._node_f(node, "page_end") or 0), node)
    return fnd, node


def _ordinals(key):
    """条目序标的候选形态：原样 + 点划互换 + 剥标签前缀的数字核。

    🔴 CN 规范键带标签前缀（"例10.2"），而单元首行是 EN/裸号形态
    （"**Example 10.2 …"）——必须同时拿数字核 "10.2" 去匹配（convex ch10
    实测：只拿原键判会误判「非自包含」跳过全部合法搬移）。"""
    k = str(key)
    out = [k]
    if "-" in k:
        out.append(k.replace("-", "."))
    if "." in k:
        out.append(k.replace(".", "-"))
    m = re.search(r"(\d+(?:[.\-]\d+)*)", k)
    if m:
        core = m.group(1)
        for v in (core, core.replace("-", "."), core.replace(".", "-")):
            if v not in out:
                out.append(v)
    return out


def unit_selfcontained(ext, ch_key, node, side):
    """单元自包含守卫：单元正文**首行**必须含本条目序标。

    🔴 防内容分裂搬移（Weibel ch3 3.6-2 实测 2026-11-17）：写源期会把越界条目的
    题干写进**前一单元**的文件（3.6.2 的题干长进 3.6-1 的单元、自己的单元只剩
    证明）——此时整节点搬移只搬走证明、题干留在原处，题干与证明被拆进两节，
    比原状更糟。首行含序标 = 题干在本单元内，搬移才安全；否则跳过留人工。"""
    man = load_manifest(ext, ch_key, side)
    if man is None:
        return False, "缺 manifest"
    recs = [r for r in (man.get("units") or [])
            if str(r.get("key") or "") == nk(node)
            and rec_sig(r) == node_sig(node)]
    if len(recs) != 1:
        return False, "单元记录定位不唯一（%d）" % len(recs)
    fp = os.path.join(manifest_dir(ext, ch_key, side), recs[0].get("file") or "")
    if not os.path.exists(fp):
        return False, "缺单元文件"
    with io.open(fp, encoding="utf-8") as f:
        lines = f.read().split("\n")
    for ln in lines[1:]:  # 跳过首行 DONE 标记
        s = ln.strip()
        if not s:
            continue
        first = s
        break
    else:
        return False, "单元正文为空"
    ords = _ordinals(nk(node))
    if not any(o in first for o in ords):
        return False, "首行不含序标 %s（题干在别的单元，内容分裂）" % first[:40]
    return True, ""


def move_whole(ext, ch_key, ch_node, f):
    """整节点搬移（契约就地修改）；返回 (status, detail)。"""
    ntype, nkey = f["node_type"], f["node_key"]
    home_key = f.get("home_key") or ""
    if not home_key:
        return "skip", "home 判不出来"
    parent = find_section(ch_node, f.get("parent_key") or "#chapter")
    if parent is None:
        return "skip", "parent 找不到：%s" % f.get("parent_key")
    cands = [c for c in (csl._node_f(parent, "sub_sec") or [])
             if not csl._is_block_el(c) and nt(c) == ntype and nk(c) == nkey]
    if len(cands) != 1:
        return "skip", "节点定位不唯一（%d）" % len(cands)
    node = cands[0]
    # 🔴 单元自包含守卫：任一侧（源/译）单元首行不含本条目序标 → 内容分裂，
    # 整搬会拆散题干与证明，跳过留人工。
    for side in ("units", "units-translate"):
        if load_manifest(ext, ch_key, side) is None:
            continue
        ok, why = unit_selfcontained(ext, ch_key, node, side)
        if not ok:
            return "skip", "单元非自包含：%s" % why
    home = find_section(ch_node, home_key)
    if home is None:
        return "skip", "home 找不到：%s" % home_key
    if home is node or is_ancestor_of(node, home):
        return "skip", "home 是节点自身/子树"
    old_sigs = [node_sig(n) for n in walk_unit_nodes(ch_node)]
    detach_node(parent, node)
    anchor_order_insert(home, node, ext, str(ch_key))
    new_sigs = [node_sig(n) for n in walk_unit_nodes(ch_node)]
    if Counter(new_sigs) != Counter(old_sigs):
        return "abort", "搬移后契约签名多重集变化（内部错误）"
    return "ok", {"node": [ntype, nkey], "home": home_key,
                  "old_parent": f.get("parent_key")}


# --------------------------------------------------- desc-split 手术 ----
# LEAK-D/LEAK-A desc 头部泄漏的手工手术（切点 n_paras 须先按印面裁定）：
# 把 desc 单元头部 n_paras 个段落搬归 home 节 = 新建尾部 desc 节点（契约加
# 幻影节点 content=0——合法形态，OCR 源块保留在原 desc 节点不动）+ 双侧
# manifest 插记录（插在 home 子树最后一条记录之后）+ 双语单元文件切分
# （EN/CN 段落数必须一致，否则中止）+ 交付再生与守恒断言。

def _split_paragraphs(body_lines):
    """正文行 → 段落列表（空行分隔，段落保留内部行序）。"""
    paras, cur = [], []
    for ln in body_lines:
        if ln.strip():
            cur.append(ln)
        elif cur:
            paras.append(cur)
            cur = []
    if cur:
        paras.append(cur)
    return paras


def _next_desc_key(ch_node, used_manifest_keys=()):
    """章内新 desc 键 = D<max+1>；🔴 必须同时避开**双侧 manifest 已用的编号**
    ——契约 desc 键有历史缺口时 manifest 仍留着孤儿记录（Lee ch9 的 D3/D7/
    D17/D23/D31/D37/D39），新键撞上孤儿键 = 同键两条记录，⑪ 页序判定把它判
    两次（第二次落在孤儿位置 → 页序倒退假报）。"""
    mx = 0
    for n in walk_unit_nodes(ch_node):
        m = re.match(r"^D(\d+)$", nk(n))
        if m:
            mx = max(mx, int(m.group(1)))
    for k in used_manifest_keys:
        m = re.match(r"^D(\d+)$", str(k))
        if m:
            mx = max(mx, int(m.group(1)))
    return "D%d" % (mx + 1)


def _para_print_pos(ext, ch, para_lines, page_lo, page_hi):
    """首段在页 JSON 的行首命中 (page, y)（±1 页回退）；无证据返回 None。"""
    probe = csl._norm_md(" ".join(l.strip() for l in para_lines))[:60]
    if len(probe) < 12:
        return None
    for p in range(max(1, page_lo), page_hi + 1):
        for cand in (p, p - 1, p + 1):
            if cand < 1:
                continue
            for _x, y, t in csl._page_blocks(ext, ch, cand):
                tn = csl._norm_md(t)
                if probe[:40] in tn:
                    return (cand, float(y))
    return None


def _para_print_page(ext, ch, para_lines, page_lo, page_hi):
    """首段命中页（±1 页回退）；无证据返回 None。"""
    pos = _para_print_pos(ext, ch, para_lines, page_lo, page_hi)
    return pos[0] if pos else None


def _split_body_at(body_lines, n_paras):
    """在段落 n_paras 结束处切一刀，返回 (moved_lines, kept_lines)。

    🔴 按原行切片而非按段落重组：段间空行必须逐字保留（重组会吞掉 `$$` 前的
    空行，门控「missing blank line before opening $$」实拒——do Carmo D7 实测）。
    moved 含其后随空行；kept 从下一段首行开始。"""
    last_nonblank = {}
    para = 0
    prev_blank = True
    for i, ln in enumerate(body_lines):
        if ln.strip():
            if prev_blank:
                para += 1
            last_nonblank[para] = i
            prev_blank = False
        else:
            prev_blank = True
    if n_paras not in last_nonblank:
        raise RuntimeError("段落切点 %d 越界（共 %d 段）"
                           % (n_paras, max(last_nonblank) if last_nonblank else 0))
    cut = last_nonblank[n_paras] + 1
    while cut < len(body_lines) and not body_lines[cut].strip():
        cut += 1
    return body_lines[:cut], body_lines[cut:]


def _manifest_insert_index_page(man, ch_node, home_key, subtree_keys, pg):
    """home 节记录之后、**按印刷页序**的插入下标：home 子树内第一个
    page_start > pg 的记录之前（Lee ch9 实测：U8 子树含 p249 的 例9.45——
    「父节条目印在自己子节标题之后」的合法形态，append 到末尾会页序倒退）。"""
    i0 = None
    for i, r in enumerate(man["units"]):
        if str(r.get("type")) == "section" and str(r.get("key")) == home_key:
            i0 = i
            break
    if i0 is None:
        raise RuntimeError("home 节记录找不到：%s" % home_key)
    # home 子树的单元节点（文档序，不含 home 自身）——与 manifest 记录顺序 1:1
    home = find_section(ch_node, home_key)
    sub_nodes = [n for n in walk_unit_nodes(home) if n is not home]
    j = i0 + 1
    for n in sub_nodes:
        if j >= len(man["units"]):
            break
        r = man["units"][j]
        if str(r.get("type")) == "section" and str(r.get("key")) not in subtree_keys:
            break  # 已到 home 子树末尾
        ps = csl._node_f(n, "page_start")
        if ps and int(ps) > pg:
            return j
        j += 1
    return j


def _manifest_insert_index(man, home_key, subtree_keys):
    """home 节记录之后、home 子树之外下一条记录之前的插入下标。"""
    i0 = None
    for i, r in enumerate(man["units"]):
        if str(r.get("type")) == "section" and str(r.get("key")) == home_key:
            i0 = i
            break
    if i0 is None:
        raise RuntimeError("home 节记录找不到：%s" % home_key)
    j = i0 + 1
    while j < len(man["units"]):
        r = man["units"][j]
        if str(r.get("type")) == "section" and str(r.get("key")) not in subtree_keys:
            break
        j += 1
    return j


def run_desc_split(ext, book_dir, ch_key, desc_key, n_paras, home_key,
                   backup, dry_run):
    """执行一次 desc-split；dry_run 只打印计划，不写盘。"""
    fnd, ch_node = plan_chapter(ext, BookStructure.load(ext), ch_key)
    node, parent = None, None
    for s in walk_unit_nodes(ch_node):
        if nt(s) != "section":
            continue
        for c in (csl._node_f(s, "sub_sec") or []):
            if nt(c) == "description" and nk(c) == desc_key:
                node, parent = c, s
    if node is None:
        for c in (csl._node_f(ch_node, "sub_sec") or []):
            if nt(c) == "description" and nk(c) == desc_key:
                node, parent = c, ch_node
    if node is None:
        raise RuntimeError("desc 节点 %s 定位失败" % desc_key)
    home = find_section(ch_node, home_key)
    if home is None:
        raise RuntimeError("home 节点找不到：%s" % home_key)
    ch_num = chapter_num(ch_key)
    sides = sides_of(ext, ch_key)
    subtree_keys = {nk(n) for n in walk_unit_nodes(home) if nt(n) == "section"}
    man_src = load_manifest(ext, ch_key, "units")
    recs = [r for r in man_src["units"]
            if str(r.get("key")) == desc_key and str(r.get("type")) == "desc"]
    if len(recs) != 1:
        raise RuntimeError("desc 记录定位不唯一（%d）" % len(recs))
    rec = recs[0]

    # 1) 双侧按行切片（只读；空行逐字保留）
    splits = {}
    for side, _man in sides:
        up = os.path.join(manifest_dir(ext, ch_key, side), rec["file"])
        with io.open(up, encoding="utf-8") as f:
            text = f.read()
        nl = "\r\n" if "\r\n" in text else "\n"
        lines = text.split("\n")
        body = lines[1:]
        while body and not body[-1].strip():
            body.pop()
        n_paras_all = len(_split_paragraphs(body))
        if n_paras_all <= n_paras:
            raise RuntimeError("%s 段落数 %d ≤ 切点 %d" % (side, n_paras_all, n_paras))
        moved, kept = _split_body_at(body, n_paras)
        splits[side] = (up, lines, moved, kept, nl)
    print("   切点 %s：前 %d 段 → §%s 尾部；其余 %d 段留在原地"
          % (desc_key, n_paras, home_key,
             len(splits["units"][3])))

    used_keys = set()
    for _side, _man in sides:
        for r in _man["units"]:
            used_keys.add(str(r.get("key") or ""))
    newkey = _next_desc_key(ch_node, used_keys)
    pos = _para_print_pos(ext, ch_key, [splits["units"][2][0]],
                          int(csl._node_f(parent, "page_start") or 1),
                          int(csl._node_f(parent, "page_end") or 1))
    pg = pos[0] if pos else int(csl._node_f(parent, "page_start") or 1)
    new_anchor = pos or (pg, 0.0)
    print("   新节点 %s (p%s, y%s) 按 (page,y) 锚序插入 §%s 子树"
          % (newkey, pg, new_anchor[1], home_key))
    for side in splits:
        print("   [%s] 首行: %s" % (side, splits[side][2][0][:90]))
    if dry_run:
        return newkey

    # 2) 交付先快照 + 备份（任何写盘之前）
    befores = {}
    for side, man in sides:
        lang = side_lang(man)
        befores[side] = snapshot_delivery(book_dir, ch_key, ch_num, lang)
        for fn in befores[side]:
            backup.touch(os.path.join(book_dir, fn))
    backup.touch(chapter_json_path(ext, ch_key))

    # 3) 契约加幻影 desc 节点（按 (page,y) 锚序插入）——必须先于 manifest 重排：
    #    manifest 的插入位置由「更新后的契约文档序」决定（Lee ch9 实测：U8 子树
    #    存在既有契约↔manifest 序漂移，重排顺带把它修掉）。🔴 锚序必须比较
    #    (page,y) 并包含**节兄弟**——ch12 实测：D3 的 home 是父节 U1，新节点
    #    锚 (322,160) 必须排到子节 U2（锚 (322,1070)）之前，仅按页比较会插到
    #    U2 子树之后（整段 §U2 内容被新节点压在后面）。
    subs = home.setdefault("sub_sec", [])
    cpos = len(subs)
    for i, c in enumerate(subs):
        if c is node:
            continue
        a_c = (csl._section_anchor(ext, ch_key, c) if nt(c) == "section"
               else csl._node_anchor(ext, ch_key, c))
        if a_c is None:
            continue
        if (a_c[0], a_c[1]) <= new_anchor:
            cpos = i + 1
    subs.insert(cpos, {"key": newkey, "type": "description", "name": "",
                       "page_start": pg, "page_end": pg, "sub_sec": []})
    backup.touch(chapter_json_path(ext, ch_key))
    with io.open(chapter_json_path(ext, ch_key), "w", encoding="utf-8") as f:
        json.dump(ch_node, f, ensure_ascii=False, indent=1)
    sig_seq = [node_sig(n) for n in walk_unit_nodes(ch_node)]

    # 4) 双侧单元切分 + manifest（新记录 append 后整体按契约序重排）
    import hashlib
    en_bodies = None
    for side, man in sides:
        d = manifest_dir(ext, ch_key, side)
        up, lines, moved, kept, nl = splits[side]
        backup.touch(up)
        mid = max([int(m.group(1)) for r in man["units"]
                   for m in [re.match(r"^(\d+)", r.get("id") or "")] if m] + [0])
        newid = "%04d" % (mid + 1)
        has_suffix = any("_desc_" in (r.get("file") or "")
                         for r in man["units"] if str(r.get("type")) == "desc")
        newfile = "%s_desc%s.md" % (newid, ("_" + newkey) if has_suffix else "")
        mark = ("<!-- book-summarizer DONE unit: id=%s type=desc key=%s name= -->"
                % (newid, newkey))
        new_body = list(moved)
        kept_body = list(kept)
        new_up = os.path.join(d, newfile)
        backup.mark_created(new_up)
        with io.open(new_up, "w", encoding="utf-8",
                     newline="") as f:
            f.write(mark + "\n" + "\n".join(new_body).rstrip() + nl)
        with io.open(up, "w", encoding="utf-8", newline="") as f:
            f.write(lines[0] + "\n" + "\n".join(kept_body).rstrip() + nl)
        import hashlib as _h
        h_new = _h.sha1("\n".join(new_body).encode("utf-8")).hexdigest()
        h_kept = _h.sha1("\n".join(kept_body).encode("utf-8")).hexdigest()
        # 🔴 译侧记录必须带 src_hash（= 对应**源**单元正文的 sha1，与 parity
        # 判据 6 同源）；源改了而译侧快照不更新 = fail-closed 漂移（do Carmo 实测）
        new_rec = {"id": newid, "file": newfile, "type": "desc",
                   "ntype": "description", "key": newkey, "name": "",
                   "tags": [], "images": [], "content": 0, "hash": h_new}
        if side == "units":
            en_bodies = {"new": "\n".join(new_body).rstrip(),
                         "kept": "\n".join(kept_body).rstrip()}
        else:
            new_rec["src_hash"] = _h.sha1(
                en_bodies["new"].encode("utf-8")).hexdigest()
        # 🔴 span 局部重排：U8 一类子树存在既有契约↔manifest 序漂移（Lee ch9
        # 实测：命题9.41 契约第 71 位、manifest 第 72 位内容之后），全量重排会
        # 被孤儿记录（契约已删、manifest 还在的 desc）卡死——只在 home 子树的
        # manifest 跨度内按契约子树序重排，孤儿记录在其外不受影响。
        i0 = next(i for i, r in enumerate(man["units"])
                  if str(r.get("type")) == "section" and str(r.get("key")) == home_key)
        j = i0 + 1
        while j < len(man["units"]) and not (
                str(man["units"][j].get("type")) == "section"
                and str(man["units"][j].get("key")) not in subtree_keys):
            j += 1
        span = man["units"][i0 + 1:j]
        # 契约子树含刚插入的新节点（D39），但 span 此刻还没有它的记录——
        # 配对集排除新节点，新记录由页序规则单独插入
        sub_nodes = [n for n in walk_unit_nodes(home)
                     if n is not home and nk(n) != newkey]
        want = Counter(node_sig(n) for n in sub_nodes)
        # 🔴 Lee ch9 实测：契约 desc 键有历史缺口（D3/D7/D17/D23/D31/D37 的节点
        # 已删、manifest 记录还在且参与 merge）——配对记录按契约子树序重排，
        # **孤儿记录按原序号回插**（内容零丢失）；孤儿落在子树外则照旧 fail-closed。
        orphan_pos, matched = [], []
        for k, r in enumerate(span):
            if rec_sig(r) in want and want[rec_sig(r)] > 0:
                matched.append(r)
            else:
                orphan_pos.append(k)
        def _orphan_page(r):
            # 孤儿记录的印刷页（单元首行在页 JSON 的行首命中；无证据 = None）
            up = os.path.join(manifest_dir(ext, ch_key, side), r.get("file") or "")
            try:
                with io.open(up, encoding="utf-8") as f:
                    bl = f.read().splitlines()
            except Exception:
                return None
            first = next((l for l in bl if l.strip()), "")
            if len(first.strip()) < 12:
                return None
            return _para_print_page(ext, ch_key, [first],
                                    int(csl._node_f(home, "page_start") or 1),
                                    int(csl._node_f(parent, "page_end") or 1) + 2)
        have = Counter(rec_sig(r) for r in matched)
        if want != have:
            raise RuntimeError("home 子树跨度内契约↔manifest 多重集不一致：缺 %s / 多 %s"
                               % (dict(want - have), dict(have - want)))
        pools = {}
        for r in matched:
            pools.setdefault(rec_sig(r), []).append(r)
        ordered = [pools[node_sig(n)].pop(0) for n in sub_nodes]
        # 新记录按 (page,y) 锚序插入：第一个锚 > 新锚的节点之前——🔴 须含节
        # 兄弟并比较 y（Lee ch12 实测：D3 的 home=父节 U1，新节点锚 (322,160)
        # 必须排到子节 U2（锚 (322,1070)）之前，仅按页比较会插到 U2 子树后）
        pos = len(ordered)
        for i, n in enumerate(sub_nodes):
            a_n = (csl._section_anchor(ext, ch_key, n) if nt(n) == "section"
                   else csl._node_anchor(ext, ch_key, n))
            if a_n is None:
                continue
            if (a_n[0], a_n[1]) > new_anchor:
                pos = i
                break
        ordered.insert(pos, new_rec)
        # 孤儿按原 span 序号回插（new_rec 占位后序号 +1 平移）
        final = []
        oi, mi = 0, 0
        shift = 0
        total = len(span) + 1
        new_emitted = False
        for k in range(total):
            if oi < len(orphan_pos) and k == orphan_pos[oi] + shift:
                op = span[orphan_pos[oi]]
                # 🔴 孤儿印面页晚于新节点页（例9.45 p249 > D39 p246，Lee ch9
                # 实测）时新记录先出，否则页序倒退被 ⑪ 拒
                if (not new_emitted and mi < len(ordered)
                        and ordered[mi] is new_rec):
                    opg = _orphan_page(op)
                    if opg is None or opg > pg:
                        final.append(new_rec)
                        new_emitted = True
                final.append(op)
                oi += 1
            elif mi < len(ordered):
                r = ordered[mi]
                if r is new_rec:
                    new_emitted = True
                    shift = 1
                final.append(r)
                mi += 1
            else:
                break
        if not new_emitted:
            final.append(new_rec)
        while oi < len(orphan_pos):
            final.append(span[orphan_pos[oi]])
            oi += 1
        while mi < len(ordered):
            final.append(ordered[mi])
            mi += 1
        man["units"] = man["units"][:i0 + 1] + final + man["units"][j:]
        for r in man["units"]:
            if str(r.get("key")) == desc_key and str(r.get("type")) == "desc"                     and r.get("id") == rec.get("id"):
                r["hash"] = h_kept
                if side == "units-translate":
                    r["src_hash"] = _h.sha1(
                        en_bodies["kept"].encode("utf-8")).hexdigest()
        write_manifest(ext, ch_key, side, man, backup)
        print("   [%s] 新单元 %s（%d 行）+ %s 缩短（hash/src_hash 更新，manifest 已按契约序重排）"
              % (side, newfile, len(moved), rec["file"]))

    # 5) 交付再生 + 核对
    touched_tops = {home_key, str(csl._node_f(parent, "key") or "#chapter")}
    for side, _man in sides:
        lang = side_lang(_man)
        regenerate_and_verify(ext, book_dir, ch_key, ch_num, side, lang,
                              befores[side], touched_tops, backup)
    print("   desc-split 完成")


# ------------------------------------------------- --move / --set-page ----
# 收官后手工搬移：把任意节点（条目/节）搬进指定 home 节，或修正契约页锚。
# manifest 侧 = span 局部重排（配对记录按契约子树序 + 孤儿按原序号回插 +
# 移动记录与孤儿的先后由印面页裁定）——全量重排会被孤儿记录卡死（Lee ch9 实测）。

def _resolve_records_for_nodes(man, parent, moved_nodes, missing_ok=False):
    """改动前定位 moved_nodes 的记录：旧父 span 记录 ↔ 旧子树节点序列按签名
    贪婪配对（孤儿跳过）；重复键的章（do Carmo 的 评注1 跨节重号）由此按位置
    唯一解析。返回 {节点 key: record}。
    missing_ok=True：契约里无记录的节点（Tu appendixB 的 B.2 陈述幻影——内容
    在别的单元里、自身不渲染进交付）静默跳过 = 契约-only 搬移。"""
    missing_ok = bool(missing_ok)
    moved_keys = {nk(n) for n in moved_nodes}
    if str(csl._node_f(parent, "type") or "") == "section":
        i0 = next(i for i, r in enumerate(man["units"])
                  if str(r.get("type")) == "section"
                  and str(r.get("key")) == str(csl._node_f(parent, "key") or ""))
        subtree = {nk(n) for n in walk_unit_nodes(parent) if nt(n) == "section"}
        j = i0 + 1
        while j < len(man["units"]) and not (
                str(man["units"][j].get("type")) == "section"
                and str(man["units"][j].get("key")) not in subtree):
            j += 1
    else:
        # 父为章节点（条目挂在章级）：span = 章记录之后到第一个节记录之前
        i0 = next(i for i, r in enumerate(man["units"])
                  if str(r.get("type")) == "chapter")
        j = i0 + 1
        while j < len(man["units"]) and str(man["units"][j].get("type")) != "section":
            j += 1
    span = man["units"][i0:j]
    sub_nodes = [n for n in walk_unit_nodes(parent) if n is not parent]
    pools = {}
    for r in span:
        pools.setdefault(rec_sig(r), []).append(r)
    out = {}
    for n in sub_nodes:
        sig = node_sig(n)
        if nk(n) in moved_keys and pools.get(sig):
            out[nk(n)] = pools[sig].pop(0)
    missing = moved_keys - set(out)
    if missing:
        if missing_ok:
            for k in missing:
                out.setdefault(k, None)
        else:
            raise RuntimeError("记录定位失败（span 内缺）：%s" % sorted(missing))
    return out


def _manifest_rehome_span(man, home_key, subtree_keys, sub_nodes,
                          moved_records, ext, ch_key, side, home):
    """把 moved_records（契约节点已在 home 子树内、sub_nodes = home 子树契约
    文档序）落回 home 的 manifest 跨度：配对记录按契约子树序重排，孤儿记录按
    原序号回插，移动记录与孤儿的先后由印面页裁定（例9.45 p249 > D39 p246 教训）。"""
    i0 = next(i for i, r in enumerate(man["units"])
              if str(r.get("type")) == "section" and str(r.get("key")) == home_key)
    j = i0 + 1
    while j < len(man["units"]) and not (
            str(man["units"][j].get("type")) == "section"
            and str(man["units"][j].get("key")) not in subtree_keys):
        j += 1
    span = man["units"][i0 + 1:j]
    moved_ids = {id(r) for r in moved_records}
    want = Counter(node_sig(n) for n in sub_nodes)
    orphan_pos, matched = [], []
    for k, r in enumerate(span):
        if id(r) in moved_ids:
            continue
        if rec_sig(r) in want and want[rec_sig(r)] > 0:
            matched.append(r)
        else:
            orphan_pos.append(k)
    have = Counter(rec_sig(r) for r in matched)
    moved_sigs = Counter(rec_sig(r) for r in moved_records)
    if have + moved_sigs != want:
        raise RuntimeError("home 子树跨度内契约↔manifest 多重集不一致：缺 %s / 多 %s"
                           % (dict(want - have - moved_sigs),
                              dict(have + moved_sigs - want)))
    pools = {}
    for r in matched + moved_records:
        pools.setdefault(rec_sig(r), []).append(r)
    ordered = [pools[node_sig(n)].pop(0) for n in sub_nodes]

    def _orphan_page(r):
        up = os.path.join(manifest_dir(ext, ch_key, side), r.get("file") or "")
        try:
            with io.open(up, encoding="utf-8") as f:
                bl = f.read().splitlines()
        except Exception:
            return None
        first = next((l for l in bl if l.strip()), "")
        if len(first.strip()) < 12:
            return None
        return _para_print_page(ext, ch_key, [first], 1, 10 ** 6)

    def _moved_page(r):
        n = next((n for n in sub_nodes if node_sig(n) == rec_sig(r)), None)
        return int(csl._node_f(n, "page_start") or 0) if n is not None else None

    final, oi, mi = [], 0, 0
    total = len(span) + len(moved_records)
    for k in range(total):
        if oi < len(orphan_pos) and k == orphan_pos[oi]:
            op = span[orphan_pos[oi]]
            if mi < len(ordered) and id(ordered[mi]) in moved_ids:
                opg = _orphan_page(op)
                mpg = _moved_page(ordered[mi])
                if opg is None or mpg is None or opg > mpg:
                    final.append(ordered[mi])
                    mi += 1
            final.append(op)
            oi += 1
        elif mi < len(ordered):
            final.append(ordered[mi])
            mi += 1
        else:
            break
    while mi < len(ordered):
        final.append(ordered[mi])
        mi += 1
    while oi < len(orphan_pos):
        final.append(span[orphan_pos[oi]])
        oi += 1
    man["units"] = man["units"][:i0 + 1] + final + man["units"][j:]


def run_manual_moves(ext, book_dir, ch_key, moves, setpages, backup, dry_run):
    """批量 --move KEY:HOME[:PARENT] + --set-page KEY:PG；一次契约落盘 + 每语种
    一次再生。🔴 移动记录必须在**契约改动前**定位（改动后节点已从旧父 sub_sec
    摘除，span 对齐找不到它——Lee ch8 首次实跑的教训）。"""
    fnd, ch_node = plan_chapter(ext, BookStructure.load(ext), ch_key)
    ch_num = chapter_num(ch_key)
    sides = sides_of(ext, ch_key)

    # 0) 改动前：定位节点 + 双侧记录
    infos = []
    moved_nodes = []
    old_parents = []
    node_records = {}    # node_key -> {side: record}
    for node_key, home_key, parent_hint in moves:
        cands = [n for n in walk_unit_nodes(ch_node)
                 if nk(n) == node_key and nt(n) != "chapter"]
        if len(cands) > 1 and parent_hint:
            def _parent_of(n):
                for s2 in walk_unit_nodes(ch_node):
                    if nt(s2) == "section":
                        for c2 in (csl._node_f(s2, "sub_sec") or []):
                            if c2 is n:
                                return s2
                return ch_node
            cands = [n for n in cands
                     if nk(_parent_of(n)) == parent_hint
                     or (parent_hint == "#chapter" and _parent_of(n) is ch_node)]
        if len(cands) != 1:
            raise RuntimeError("节点 %s 定位不唯一（%d）——同键多节点需父级消歧"
                               % (node_key, len(cands)))
        node = cands[0]
        parent = ch_node
        for s in walk_unit_nodes(ch_node):
            if nt(s) == "section":
                for c in (csl._node_f(s, "sub_sec") or []):
                    if c is node:
                        parent = s
        recs = {}
        for side, man in sides:
            recs[side] = _resolve_records_for_nodes(
                man, parent, [node], missing_ok=True).get(node_key)
        node_records[node_key] = recs
        moved_nodes.append(node)
        old_parents.append(parent)
        infos.append({"node_key": node_key, "node_type": nt(node),
                      "home_key": home_key,
                      "parent_key": nk(parent) if parent is not ch_node
                      else "#chapter"})
        print("   [move] %s (%s) -> §%s" % (node_key, nt(node), home_key))
    for node_key, pg in setpages:
        cands = [n for n in walk_unit_nodes(ch_node) if nk(n) == node_key]
        if len(cands) != 1:
            raise RuntimeError("--set-page %s 定位不唯一" % node_key)
        cands[0]["page_start"] = int(pg)
        cands[0]["page_end"] = int(pg)
        print("   [set-page] %s → p%s" % (node_key, pg))
    if dry_run:
        return

    # 1) 交付先快照 + 备份
    befores = {}
    for side, man in sides:
        lang = side_lang(man)
        befores[side] = snapshot_delivery(book_dir, ch_key, ch_num, lang)
        for fn in befores[side]:
            backup.touch(os.path.join(book_dir, fn))
    backup.touch(chapter_json_path(ext, ch_key))
    for side, _man in sides:
        backup.touch(os.path.join(manifest_dir(ext, ch_key, side), "manifest.json"))
    # 2) 契约搬移（move_whole 逐个）+ 落盘
    for info in infos:
        f = {"node_key": info["node_key"], "node_type": info["node_type"],
             "home_key": info["home_key"], "parent_key": info["parent_key"]}
        node = next(n for n in walk_unit_nodes(ch_node)
                    if nk(n) == info["node_key"] and nt(n) == info["node_type"])
        old_parent = next((p for p in old_parents
                           if any(c is node for c in (csl._node_f(p, "sub_sec") or []))),
                          None)
        if old_parent is None:
            old_parent = next((p for p in old_parents), ch_node)
        st, reason = _move_node(ext, ch_key, ch_node, node, old_parent,
                                info["home_key"])
        if st != "ok":
            raise RuntimeError("--move %s 失败：%s" % (info["node_key"], reason))
    for node_key, pg in setpages:
        cands = [n for n in walk_unit_nodes(ch_node) if nk(n) == node_key]
        if len(cands) != 1:
            raise RuntimeError("--set-page %s 定位不唯一" % node_key)
        cands[0]["page_start"] = int(pg)
        cands[0]["page_end"] = int(pg)
    with io.open(chapter_json_path(ext, ch_key), "w", encoding="utf-8") as f:
        json.dump(ch_node, f, ensure_ascii=False, indent=1)
    # 3) 双侧 manifest：弹出记录 + 逐 home span 重建
    for side, man in sides:
        moved_records = []
        for info in infos:
            rec = node_records[info["node_key"]].get(side)
            if rec is None:
                continue   # 无记录节点：契约-only 搬移，manifest/交付不受影响
            man["units"].remove(rec)
            moved_records.append(rec)
        seen_homes = []
        for info in infos:
            hk = info["home_key"]
            if hk not in seen_homes:
                seen_homes.append(hk)
        recordless_sigs = set()
        for info in infos:
            if not node_records[info["node_key"]].get(side):
                recordless_sigs.add((_MANIFEST_TYPE.get(info["node_type"], "item"),
                                     info["node_key"]))
        for home_key in seen_homes:
            home = find_section(ch_node, home_key)
            subtree_keys = {nk(n) for n in walk_unit_nodes(home)
                            if nt(n) == "section"}
            sub_nodes = [n for n in walk_unit_nodes(home)
                         if n is not home
                         and node_sig(n) not in recordless_sigs]
            grp = []
            for info in infos:
                if info["home_key"] != home_key:
                    continue
                sig = (_MANIFEST_TYPE.get(info["node_type"], "item"),
                       info["node_key"])
                grp.extend(r for r in moved_records if rec_sig(r) == sig)
            _manifest_rehome_span(man, home_key, subtree_keys, sub_nodes,
                                  grp, ext, ch_key, side, home)
        write_manifest(ext, ch_key, side, man, backup)
    # 4) 交付再生 + 核对
    touched_tops = set()
    for info in infos:
        touched_tops.add(info["home_key"])
        touched_tops.add(info["parent_key"])
    for side, _man in sides:
        lang = side_lang(_man)
        regenerate_and_verify(ext, book_dir, ch_key, ch_num, side, lang,
                              befores[side], touched_tops, backup)
    print("   manual-moves 完成（%d move / %d set-page）" % (len(moves), len(setpages)))


def _move_node(ext, ch_key, ch_node, node, parent, home_key):
    """把单个节点从 parent 搬到 home（契约就地修改）；返回 (status, detail)。"""
    home = find_section(ch_node, home_key)
    if home is None:
        return "skip", "home 找不到：%s" % home_key
    if home is node or is_ancestor_of(node, home):
        return "skip", "home 是节点自身/子树"
    old_sigs = [node_sig(n) for n in walk_unit_nodes(ch_node)]
    if not detach_node(parent, node):
        return "skip", "从旧父摘除失败"
    anchor_order_insert(home, node, ext, str(ch_key))
    new_sigs = [node_sig(n) for n in walk_unit_nodes(ch_node)]
    if Counter(new_sigs) != Counter(old_sigs):
        return "abort", "搬移后契约签名多重集变化（内部错误）"
    return "ok", {"node": [nt(node), nk(node)], "home": home_key,
                  "old_parent": nk(parent) if parent is not ch_node else "#chapter"}


def sides_of(ext, ch_key):
    out = []
    man = load_manifest(ext, ch_key, "units")
    if man is None:
        raise RuntimeError("缺源侧 manifest")
    out.append(("units", man))
    man_t = load_manifest(ext, ch_key, "units-translate")
    if man_t is not None:
        out.append(("units-translate", man_t))
    return out


def side_lang(man):
    return "zh" if (man.get("language") or "cn") == "cn" else "en"


def main(argv=None):
    ap = argparse.ArgumentParser(description="节界泄漏四账同步修复（dry-run 默认）")
    ap.add_argument("book_dir")
    ap.add_argument("--ch", action="append", default=None,
                    help="只处理指定章（可多次；默认全部有命中章）")
    ap.add_argument("--apply", action="store_true", help="写盘（默认 dry-run）")
    ap.add_argument("--desc-split", action="append", default=None, metavar="KEY:N:HOME",
                    help="desc 手工手术：把 desc 单元头部 N 个段落搬归 HOME 节"
                         "（切点须先按印面裁定；可多次；HOME 为节 key）")
    ap.add_argument("--move", action="append", default=None, metavar="KEY:HOME",
                    help="手工搬移任意节点到 HOME 节（可多次；同批一次再生）")
    ap.add_argument("--set-page", action="append", default=None, metavar="KEY:PG",
                    help="修正契约节点页锚为 PG（可多次；随 --move 同批再生）")
    args = ap.parse_args(argv)
    book_dir = os.path.abspath(args.book_dir)
    ext = os.path.join(book_dir, "_extract")
    if not os.path.isdir(os.path.join(ext, "book_structure")):
        raise SystemExit("[repair] 缺 %s" % os.path.join(ext, "book_structure"))
    bs = BookStructure.load(ext)
    sys.stdout.reconfigure(encoding="utf-8")
    ts = time.strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(ext, "_leak_repair_log.jsonl")
    tally = Counter()
    want = {str(c) for c in args.ch} if args.ch else None

    # 🔴 desc 手工手术模式：--desc-split KEY:N:HOME（与批量搬移互斥使用）
    if args.desc_split or args.move or args.set_page:
        backup = Backup(ext, "%s_manual" % ts, dry_run=not args.apply)
        try:
            if args.desc_split:
                if not want:
                    raise SystemExit("[repair] --desc-split 必须配合 --ch <章> 指定章")
                chapter_key = list(want)[0]
                for spec in args.desc_split:
                    parts = str(spec).split(":")
                    if len(parts) != 3 or not parts[1].isdigit():
                        raise SystemExit("[repair] --desc-split 形态应为 KEY:N:HOME，收到 %r"
                                         % spec)
                    dkey, n, home = parts[0], int(parts[1]), parts[2]
                    print("== desc-split %s：%s 前 %d 段 → §%s" % (chapter_key, dkey, n, home))
                    run_desc_split(ext, book_dir, chapter_key, dkey, n, home,
                                   backup, dry_run=not args.apply)
                tally["ok"] += 1
            if args.move or args.set_page:
                if not want:
                    raise SystemExit("[repair] --move/--set-page 必须配合 --ch <章> 指定章")
                chapter_key = list(want)[0]
                moves = []
                for spec in args.move or []:
                    parts = str(spec).split(":")
                    if len(parts) not in (2, 3):
                        raise SystemExit("[repair] --move 形态应为 KEY:HOME[:PARENT]，收到 %r" % spec)
                    moves.append((parts[0], parts[1], parts[2] if len(parts) == 3 else None))
                setpages = []
                for spec in args.set_page or []:
                    parts = str(spec).split(":")
                    if len(parts) != 2 or not parts[1].lstrip("-").isdigit():
                        raise SystemExit("[repair] --set-page 形态应为 KEY:PG，收到 %r" % spec)
                    setpages.append((parts[0], int(parts[1])))
                print("== manual-moves %s：%d move / %d set-page"
                      % (chapter_key, len(moves), len(setpages)))
                run_manual_moves(ext, book_dir, chapter_key, moves, setpages,
                                 backup, dry_run=not args.apply)
                tally["ok"] += 1
        except SystemExit as e:
            print("   ✗ 失败（门控拒绝）：%s —— 回滚" % (e,))
            backup.rollback_all()
            tally["fail"] += 1
        except Exception as e:
            print("   ✗ 失败：%r —— 回滚" % (e,))
            backup.rollback_all()
            tally["fail"] += 1
        print("TOTAL %s" % dict(tally))
        if not args.apply:
            print("（dry-run：未写盘；--apply 执行）")
        return 0

    for chapter in bs.chapters:
        ck = str(chapter.key)
        if want and ck not in want:
            continue
        fnd, ch_node = plan_chapter(ext, bs, ck)
        if not fnd or ch_node is None:
            continue
        movable = [f for f in fnd
                   if f["code"] in MOVEABLE and f["node_type"] != "description"]
        # 🔴 description 类一律留人工：写源期引言经过重写，泄漏的前节尾部常与
        # 本节引言**混在同一段落**（Weibel 0014_desc 实测），行级锚定看不出句级
        # 边界；整搬会把本节引言搬进上一节，部分搬需要逐条印面裁定句界。
        desc_findings = [f for f in fnd if f["code"] in MOVEABLE
                         and f["node_type"] == "description"]
        leave = [f for f in fnd if f["code"] not in MOVEABLE]
        print("== %s：命中 %d（编号项可自动搬移 %d；desc %d + LEAK-D/SECORDER %d "
              "留人工）"
              % (chapter_label(ck), len(fnd), len(movable),
                 len(desc_findings), len(leave)))
        if not movable:
            tally["leave"] += len(leave)
            continue
        if not args.apply:
            for f in movable:
                print("   [%s] %s %s (p%s) -> %s" % (
                    f["code"], f["node_type"], f["node_key"],
                    f.get("node_page"), f.get("home_key") or "?"))
            tally["plan"] += len(movable)
            tally["leave"] += len(leave)
            continue
        applied = []
        # 🔴 按章独立备份：一章失败只回滚本章，不得撤销前面章节已落盘的修复
        backup = Backup(ext, "%s_%s" % (ts, ck.replace(".", "_")),
                        dry_run=not args.apply)
        try:
            sides = sides_of(ext, ck)
            ch_num = chapter_num(ck)
            # 1) 交付先快照 + 备份（merge 之前，备份才是旧内容）
            befores = {}
            for side, man in sides:
                lang = side_lang(man)
                befores[side] = snapshot_delivery(book_dir, ck, ch_num, lang)
                for fn in befores[side]:
                    backup.touch(os.path.join(book_dir, fn))
            backup.touch(chapter_json_path(ext, ck))
            for side, _man in sides:
                backup.touch(os.path.join(manifest_dir(ext, ck, side),
                                          "manifest.json"))
            # 2) 契约搬移
            for f in movable:
                st, info = move_whole(ext, ck, ch_node, f)
                if st == "ok":
                    applied.append((f, info))
                else:
                    tally["skip"] += 1
                    print("   跳过 [%s] %s %s：%s" % (f["code"], f["node_type"],
                                                     f["node_key"], info))
            if not applied:
                continue
            # 3) 契约 + 双侧 manifest 落盘
            with io.open(chapter_json_path(ext, ck), "w", encoding="utf-8") as f:
                json.dump(ch_node, f, ensure_ascii=False, indent=1)
            sig_seq = [node_sig(n) for n in walk_unit_nodes(ch_node)]
            for side, man in sides:
                man["units"] = realigned_records(man.get("units") or [], sig_seq)
                write_manifest(ext, ck, side, man, backup)
            # 4) 交付再生 + 逐文件核对
            touched_tops = set()
            for f, info in applied:
                touched_tops.add(str(info.get("home") or ""))
                touched_tops.add(str(info.get("old_parent") or "#chapter"))
            for side, _man in sides:
                lang = side_lang(_man)
                regenerate_and_verify(ext, book_dir, ck, ch_num, side, lang,
                                      befores[side], touched_tops, backup)
        except SystemExit as e:
            # merge_chapter 门控失败抛 SystemExit：本章放弃进人工清单，但书本
            # 批量继续（不接住会杀死整本书的驱动进程——statistical-inference 实测）
            print("   ✗ %s 修复失败（门控拒绝）：%s —— 整章回滚"
                  % (chapter_label(ck), e))
            backup.rollback_all()
            tally["fail"] += 1
            continue
        except Exception as e:
            print("   ✗ %s 修复失败：%r —— 整章回滚" % (chapter_label(ck), e))
            backup.rollback_all()
            tally["fail"] += 1
            continue
        # 5) 复核：该章 LEAK-A/B 应归零（从盘上重载契约，勿用启动时的内存模型）
        bs2 = BookStructure.load(ext)
        fnd2, _ = plan_chapter(ext, bs2, ck)
        resid_ab = len([f for f in fnd2 if f["code"] in MOVEABLE])
        print("   已修 %d 条；章内 LEAK-A/B 剩余 %d" % (len(applied), resid_ab))
        with io.open(log_path, "a", encoding="utf-8") as lf:
            for f, info in applied:
                lf.write(json.dumps({"ts": ts, "ch": ck,
                                     "code": f.get("code"),
                                     "node": info.get("node"),
                                     "home": info.get("home"),
                                     "residual": resid_ab},
                                    ensure_ascii=False) + "\n")
        tally["ok"] += len(applied)
        tally["leave"] += len(leave)

    print("TOTAL %s" % dict(tally))
    if not args.apply:
        print("（dry-run：未写盘；--apply 执行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
