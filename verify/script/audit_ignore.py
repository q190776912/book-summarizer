#!/usr/bin/env python3
"""audit_ignore.py — 审核 ignore 条目是否真噪声（防误用隐藏真实缺项）

设计动机
--------
`ignore` 只应抑制「.md 中真实存在、但属 OCR 乱码 / 交叉引用误标」的条头；
绝不可用于掩盖「源侧序列洞」（被忽略的编号在 .md 中本就不存在 —— 那是真实缺项，
应经 manual_overrides 补回）。2.1-4 / 4.9-3 即此类误用：把序列洞塞进 ignore 隐藏缺口。

本工具供 **agent 审核** 使用：逐条核对每个 ignore 条目与契约（分章契约 book_structure/ch{N}.json，经 BookStructure.load 聚合）
及源（page_*.json）的关系，给出 SUSPECT / SAFE 判定与举证，阻止「隐藏问题」。

判定规则
--------
对每个 ignore 条目（键 C.S-N，可带标签前缀 / 原因）：
  1) 契约存在性：C.S-N 是否在分章契约（book_structure/ch{N}.json）中？
     - 存在 → SUSPECT：ignore 了一个真实存在的条目（真实条目绝不可进 ignore）。
  2) 序列洞：C.S-N 不在契约，但前后邻居 C.S-(N-1) 与 C.S-(N+1) 都在契约中？
     → SUSPECT：连续编号序列中的洞，应经 manual_overrides 补回，勿用 ignore 隐藏。
  3) 源内容：在章页面区间内是否存在「带标签但无干净编号」的条头（OCR 丢号迹象）？
     → SUSPECT：可恢复的 OCR 丢号，建议 manual_overrides 恢复而非 ignore 隐藏。
  4) 否则（契约无邻居、源侧无对应内容）→ SAFE：疑似真·OCR 噪点 / 稀疏编号（agent 复核举证）。
  5) 组索引伪组豁免键 `{gi}:{prefix}:{num}`（B 层 emit token，豁免的是某个编号组里的一个
     号，契约无对应 canon，上面 1–4 判不了）：解析出组标签（verify_config.ordinal[gi]）后
     只看举证——理由含 VERIFIED-SPARSE / 已核实跳号 等证据标记 → ACCEPTED；无标记 →
     NEEDS-EVIDENCE（点名要求补印面证据，**不阻断**：晚生判据不得把已收官书刷红）。
     旧实现对此类键一律 SKIP，于是带证据的豁免与裸静音在机器侧不可区分、全书
     ACCEPTED 恒为 0（微分遍历论 7 条伪组键实测，2026-10-22）。

用法
----
    python audit_ignore.py <extract_dir> [--chapter N] [--json]
    # 不传 --chapter 审计全书所有章。存在 SUSPECT 时退出码 1（提示 agent 复核）。
"""
import os
import re
import sys
import io
import json
import glob
from collections import defaultdict
from pathlib import Path

# ---- boot（与技能内其他脚本一致）----
for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
from lib.util import blk_text
_boot.setup()

from data.book_structure.book_structure import BookStructure
from lib.page_dir import resolve_page_dir


_LABEL_PREFIX = re.compile(
    r'^(?:Definition|Theorem|Lemma|Corollary|Proposition|Example|Exercise|Remark|Axiom|'
    r'定义|定理|引理|推论|命题|例|练习|习题|评注|注)\s+')
_THREE = re.compile(r'^(\d+)[.\-·，．]+(\d+)[.\-·，．]+(\d+)$')
_TWO = re.compile(r'^(\d+)[.\-·，．]+(\d+)$')
_LABEL_RE = re.compile(
    r'\b(Definition|Theorem|Lemma|Corollary|Proposition|Example|Exercise|Remark|Axiom|'
    r'定义|定理|引理|推论|命题|例|练习|习题|评注|注)\b')
_NUM_RE = re.compile(r'\d+[.\-·，．]+\d+(?:[.\-·，．]+\d+)?')


def _canon_key_of(key):
    """解析 ignore 键为 canon 元组 (ch, sec[, num])；带标签前缀自动剥离。"""
    if not isinstance(key, str):
        key = str(key)
    s = _LABEL_PREFIX.sub('', key.strip())
    m = _THREE.match(s)
    if m:
        return (int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _TWO.match(s)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return None


def _load_chapter_canons(ext, ch):
    """返回该章契约中所有条目的 canon 元组集合。"""
    bs = BookStructure.load(ext)
    if bs is None:
        return set()
    ch_node = bs.find_chapter(ch)
    if ch_node is None:
        return set()
    # find_chapter 返回 StructureNode 对象（非 dict），walk 用 .get() 遍历，
    # 先 to_dict() 转回普通字典。
    d = ch_node.to_dict()
    canons = set()

    def walk(n):
        if n.get("type") in ("chapter", "section"):
            for k in n.get("sub_sec", []):
                walk(k)
            return
        if n.get("type") in ("exercise", "problem"):
            return
        c = _canon_key_of(n.get("key"))
        if c is not None:
            canons.add(c)

    walk(d)
    return canons


def _chapter_range(ext, ch):
    """从 chapter_map.json 取该章 (start, end) 页区间；缺失返回 None。"""
    cm_path = os.path.join(ext, "chapter_map.json")
    if not os.path.exists(cm_path):
        return None
    try:
        cm = json.load(io.open(cm_path, encoding="utf-8-sig"))
    except Exception:
        return None
    rng = {}
    if isinstance(cm, dict) and "chapters" in cm:
        for c in cm["chapters"]:
            n = c.get("num", c.get("chapter", c.get("ch")))
            if n is None:
                continue
            try:
                key = int(n)
            except (TypeError, ValueError):
                key = str(n).strip()  # 字母章号（附录 A/B…）
            rng[key] = (c.get("start", c.get("start_page")), c.get("end", c.get("end_page")))
    elif isinstance(cm, dict):
        for kk, cc in cm.items():
            s = cc.get("start", cc.get("start_page"))
            e = cc.get("end", cc.get("end_page"))
            if s is None or e is None:
                continue
            try:
                key = int(kk)
            except (TypeError, ValueError):
                key = str(kk).strip()
            rng[key] = (int(s), int(e))
    return rng.get(ch)


def _scan_ocr_noise(ext, start, end, ch=None):
    """章页面区间内是否存在『带标签但无干净编号』的条头（OCR 丢号迹象）。"""
    if not start or not end:
        return False
    _pdir = resolve_page_dir(ext, ch) if ch is not None else ext
    for p in range(max(1, int(start)), int(end) + 1):
        fp = os.path.join(_pdir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        try:
            d = json.load(io.open(fp, encoding="utf-8-sig"))
        except Exception:
            continue
        for b in d.get("text", []):
            t = blk_text(b).strip()
            if not t:
                continue
            if _LABEL_RE.search(t) and not _NUM_RE.search(t):
                return True
    return False


def _collect_ignore(ext):
    """收集全书「编号 ignore」条目（B 层 item_numbering_integrity 消费的集合）：
    verify_config.json 的 ignore / known_gaps / ignore_keys + 各 ignore_chN.json。
    返回 [(key, reason, src_file), ...]。

    作用域严格限定为「编号项」ignore：
      * ignore / known_gaps / ignore_keys —— 旧/新编号 ignore 别名，B 层统一折叠消费，此处一并收集以与 B 层集合对齐；
      * 不含 ignore_fig（图 ignore，属 E 层 figure_completeness 命名空间）与 formula.ignore（Q 层公式命名空间）——二者不在此审计范围内。
    """
    entries = []
    cfg_path = os.path.join(ext, "verify_config.json")
    if os.path.exists(cfg_path):
        try:
            book_cfg = json.load(io.open(cfg_path, encoding="utf-8-sig"))
        except Exception:
            book_cfg = {}
        # 编号 ignore 的统一键（与 B 层 ctx.ignore 消费集合一致）
        for field in ("ignore", "known_gaps", "ignore_keys"):
            for k in book_cfg.get(field, []) or []:
                if isinstance(k, dict):
                    for kk, vv in k.items():
                        entries.append((str(kk), vv if isinstance(vv, str) else "", "verify_config.json"))
                else:
                    entries.append((str(k), "", "verify_config.json"))
    for fp in sorted(glob.glob(os.path.join(ext, "ignore_ch*.json"))
                             + glob.glob(os.path.join(ext, "ignore_appendix*.json"))):
        try:
            data = json.load(io.open(fp, encoding="utf-8-sig"))
        except Exception:
            continue
        src = os.path.basename(fp)
        if isinstance(data, dict):
            for kk, vv in data.items():
                entries.append((str(kk), vv if isinstance(vv, str) else "", src))
        elif isinstance(data, list):
            for kk in data:
                entries.append((str(kk), "", src))
    return entries


_EVIDENCE_TOKENS = ("VERIFIED-SPARSE", "已核实跳号", "源书真实跳号", "sparse numbering")

# 🔴 B 层组索引 emit token（伪组豁免键）形如 `{gi}:{prefix}:{num}`：`gi` 是
# verify_config.ordinal 的组下标，`prefix` 是该组的编号前缀（章号或节号，附录书可为
# 字母），`num` 是被豁免的序号。来源见 item_numbering_integrity.emit() 的候选串
# `f"{gk}:{n}"`——「0:5:2」读作「第 0 组（本书为图组）中 5 章的 2 号」。
# 本函数把它解析出来交给审核，使这类键与两级/三级键一样进入判定分支，而不是
# 一律 SKIP。
_GROUP_TOKEN = re.compile(r'^(\d+):([^:]*):(\d+)$')
_SRC_CH = re.compile(r'^ignore_(?:ch|appendix)([0-9A-Za-z]+)\.json$')


def _group_token_of(key):
    if not isinstance(key, str):
        key = str(key)
    m = _GROUP_TOKEN.match(key.strip())
    if not m:
        return None
    return int(m.group(1)), m.group(2).strip(), int(m.group(3))


def _ordinal_group_names(ext):
    """verify_config.json 的 ordinal 组名册（下标 → 标签词列表）；缺失返回 []。"""
    cfg_path = os.path.join(ext, "verify_config.json")
    if not os.path.exists(cfg_path):
        return []
    try:
        with io.open(cfg_path, encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except Exception:
        return []
    out = []
    for g in cfg.get("ordinal", []) or []:
        names = g.get("name") if isinstance(g, dict) else None
        out.append([str(x) for x in names] if names else [])
    return out


def _chapter_of_source(src):
    m = _SRC_CH.match(os.path.basename(str(src or "")))
    if not m:
        return None
    s = m.group(1)
    return int(s) if s.isdigit() else s


def _is_evidenced_sparse(reason):
    """ignore 理由是否明确记录了『已核实的源书稀疏跳号』证据。

    仅当理由携带显式证据标记时，才把序列洞 ignore 降级为非阻断 ACCEPTED；
    无证据的序列洞 ignore 仍判 SUSPECT 阻断——保住护栏（防止用 ignore 隐藏真实缺项）。
    """
    if not reason:
        return False
    return any(tok in reason for tok in _EVIDENCE_TOKENS)


def run_audit(ext, chapter=None):
    """审计全书（或指定章）ignore 条目。返回结构化结果 dict。"""
    entries = _collect_ignore(ext)
    group_names = _ordinal_group_names(ext)
    by_ch = defaultdict(list)
    unparsed = []
    # 🔴 组索引伪组键（`gi:prefix:num`）单独走「举证」判定：这类键豁免的是**某个编号
    # 组里的一个号**（多数是被 uncat 裸键/交叉引用误收进图组造出的伪洞），契约里没有
    # 对应 canon，通用分支（契约存在性/序列洞）判不了它。旧行为是整体 SKIP——于是
    # 「已核对印面并写好 VERIFIED-SPARSE 证据」的豁免也拿不到 ACCEPTED，全书审核报告
    # 永远是 ACCEPTED=0，取证与裸静音在机器侧不可区分。现按证据标记分 ACCEPTED /
    # NEEDS-EVIDENCE（后者**不阻断**，只点名要求补举证，避免晚生判据把已收官书刷红）。
    group_rows = []
    for key, reason, src in entries:
        gt = _group_token_of(key)
        if gt is not None:
            gi, prefix, num = gt
            names = group_names[gi] if gi < len(group_names) else []
            label = names[0] if names else "(ordinal[%d] 未宣告)" % gi
            ch = _chapter_of_source(src)
            if ch is None and str(prefix).isdigit():
                ch = int(prefix)
            if ch is None:
                ch = str(prefix)
            token = "%s %s.%s" % (label, prefix, num) if prefix else "%s %s" % (label, num)
            rec = {"key": key, "chapter": ch, "source": src, "reason": reason,
                   "group": {"index": gi, "label": label, "prefix": prefix, "num": num}}
            if _is_evidenced_sparse(reason):
                rec.update(verdict="ACCEPTED",
                           why="伪组豁免键（组 %d=%s，号 %s）理由携带 VERIFIED-SPARSE / 已核实跳号 等证据标记 → "
                               "agent 已核对印面确认 %s 非真实缺项，审计通过(非阻断)" % (gi, label, num, token))
            else:
                rec.update(verdict="NEEDS-EVIDENCE",
                           why="伪组豁免键（组 %d=%s，号 %s）理由**无**证据标记 → 请核对印面后把证据写入登记原因"
                               "（加 %s 之一）；当前不阻断，但裸豁免不可长期留存"
                               % (gi, label, num, " / ".join(_EVIDENCE_TOKENS[:2])))
            group_rows.append(rec)
            continue
        p = _canon_key_of(key)
        if p is None:
            unparsed.append({"key": key, "reason": reason, "source": src,
                             "verdict": "SKIP", "why": "无法解析为编号键（跳过）"})
            continue
        by_ch[p[0]].append((key, reason, src, p))

    chapters = [chapter] if chapter else sorted(by_ch.keys())
    # 单章审计只汇总本章结果：unparsed 是【全书】无法解析出编号键的条目，
    # 无法归属到具体章——只混入单章报告会让 total>0 而逐章循环零命中，
    # 调用方（verify_chapter 单章 verify）据此误判「已审」。故仅全书审计呈现。
    # 组索引伪组键能归属本章（来源文件名/前缀），两种模式都呈现。
    if chapter is not None:
        try:
            chapter = int(chapter)
        except (TypeError, ValueError):
            chapter = str(chapter).strip()  # 字母章号（附录 A/B…）
        results = [r for r in group_rows
                   if str(r["chapter"]) == str(chapter) or r["chapter"] == chapter]
    else:
        results = list(group_rows) + list(unparsed)
    suspect = len([u for u in results if u["verdict"] == "SUSPECT"])
    accepted = len([u for u in results if u["verdict"] == "ACCEPTED"])
    needs_evidence = len([u for u in results if u["verdict"] == "NEEDS-EVIDENCE"])
    safe = 0
    for ch in chapters:
        ch_entries = by_ch.get(ch, [])
        if not ch_entries:
            continue
        canons = _load_chapter_canons(ext, ch)
        rng = _chapter_range(ext, ch)
        noise = _scan_ocr_noise(ext, rng[0] if rng else None, rng[1] if rng else None, ch=ch)
        for key, reason, src, parsed in ch_entries:
            num = parsed[2] if len(parsed) == 3 else None
            rec = {"key": key, "chapter": ch, "source": src, "reason": reason}
            if parsed in canons:
                rec.update(verdict="SUSPECT",
                           why="ignore 了一个真实存在的条目（契约含 %s）→ 真实条目绝不可进 ignore，应移除" % key)
                suspect += 1
            elif len(parsed) == 3 and num is not None:
                prev = (parsed[0], parsed[1], num - 1)
                nxt = (parsed[0], parsed[1], num + 1)
                if prev in canons and nxt in canons:
                    if _is_evidenced_sparse(reason):
                        rec.update(verdict="ACCEPTED",
                                   why="已核实的源书稀疏跳号（理由含 VERIFIED-SPARSE / 源书真实跳号 证据）→ "
                                       "书源真实无此号，总结如实省略，非隐藏缺项，审计通过(非阻断)")
                        accepted += 1
                    else:
                        rec.update(verdict="SUSPECT",
                                   why="连续编号序列洞（邻居 %s 与 %s 均在契约中）→ 应经 manual_overrides 补回，勿用 ignore 隐藏"
                                   % (f"{parsed[0]}.{parsed[1]}-{num-1}", f"{parsed[0]}.{parsed[1]}-{num+1}"))
                        suspect += 1
                elif noise:
                    # 契约中该键无前后邻居 → 不构成「序列中间洞」；若 agent 已举证
                    # （VERIFIED-SPARSE 等证据标记 + 源页核对），按文档规则放行为
                    # 已核实噪声，不再无条件 SUSPECT。
                    if _is_evidenced_sparse(reason):
                        rec.update(verdict="ACCEPTED",
                                   why="已核实的源书噪声号（理由含 VERIFIED-SPARSE 等证据，且契约无前后邻居）→ "
                                       "agent 已核对源页确认真噪声 / 稀疏编号，非隐藏缺项，审计通过(非阻断)")
                        accepted += 1
                    else:
                        rec.update(verdict="SUSPECT",
                                   why="源侧存在『带标签但无编号』条头（OCR 丢号迹象）→ 建议 manual_overrides 恢复，而非 ignore 隐藏")
                        suspect += 1
                else:
                    rec.update(verdict="SAFE",
                               why="契约无前后邻居、源侧无对应内容 → 疑似真·OCR 噪点 / 稀疏编号（agent 复核并举证）")
                    safe += 1
            else:
                rec.update(verdict="SAFE",
                           why="两级键（无子编号），无法做序列洞判定 → 请 agent 核对源书确认")
                safe += 1
            results.append(rec)

    return {"entries": results, "suspect_count": suspect, "safe_count": safe,
            "accepted_count": accepted, "needs_evidence_count": needs_evidence,
            "total": len(results)}


def _print_report(rep):
    print("=" * 72)
    print("ignore 条目审核报告  (SUSPECT=%d  ACCEPTED=%d  SAFE=%d  待举证=%d  TOTAL=%d)"
          % (rep["suspect_count"], rep.get("accepted_count", 0),
             rep["safe_count"], rep.get("needs_evidence_count", 0), rep["total"]))
    print("=" * 72)
    for r in rep["entries"]:
        tag = {"SUSPECT": "⚠ 可疑", "SAFE": "✓ 安全", "ACCEPTED": "✓ 已核实",
               "NEEDS-EVIDENCE": "! 待举证", "SKIP": "· 跳过"}.get(r["verdict"], r["verdict"])
        print("\n[%s] %s   (来源: %s)" % (tag, r.get("key", "?"), r.get("source", "?")))
        if r.get("reason"):
            print("   登记原因: %s" % r["reason"])
        print("   判定: %s" % r["why"])
    print("\n" + "=" * 72)
    if rep["suspect_count"]:
        print("结论：存在 %d 条 SUSPECT，建议 agent 复核——优先用 manual_overrides 补回真实缺项，"
              "确认确为稀疏编号 / 真噪声才保留 ignore 并补举证（理由须含 VERIFIED-SPARSE 证据）。"
              % rep["suspect_count"])
    elif rep.get("needs_evidence_count", 0):
        print("结论：无 SUSPECT；%d 条伪组豁免键尚未举证（不阻断，但请把印面核对结果写进登记原因，"
              "带证据者才会计入 ACCEPTED）。" % rep["needs_evidence_count"])
    elif rep.get("accepted_count", 0):
        print("结论：无 SUSPECT；%d 条为已核实的源书稀疏跳号（带证据），非隐藏缺项，审计通过(非阻断)。"
              % rep["accepted_count"])
    else:
        print("结论：未发现可疑 ignore 条目。")


def main():
    raw = sys.argv[1:]
    chapter = None
    as_json = False
    positional = []
    i = 0
    while i < len(raw):
        a = raw[i]
        if a.startswith("--chapter"):
            if "=" in a:
                chapter = int(a.split("=", 1)[1])
            elif i + 1 < len(raw):
                chapter = int(raw[i + 1])
                i += 1
            else:
                print("error: --chapter 需要一个章节号参数")
                return 2
        elif a == "--json":
            as_json = True
        else:
            positional.append(a)
        i += 1
    if not positional:
        print(__doc__)
        return 2
    ext = positional[0]
    rep = run_audit(ext, chapter)
    if as_json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _print_report(rep)
    return 1 if rep["suspect_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
