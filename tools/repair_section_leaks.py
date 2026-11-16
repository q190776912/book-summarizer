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
