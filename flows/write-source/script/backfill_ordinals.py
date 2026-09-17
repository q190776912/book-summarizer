"""backfill_ordinals.py — 拼接后序标回填（write-source 步骤 7 之后、步骤 8 verify 同源）

把步骤 8 verify 的 B 层（条目缺号）/ O 层（子项缺号）发现的序标缺口，写回其归属的
总结单元 ``.md``（回填）。判定：缺口出现在合并 md 的第 L 行 → 经 ``merge_chapter_map``
的 line→unit 映射定位到归属单元；在该单元内、紧邻缺口前序条目的正确位置插入
**明确标注的占位条目**（不编造真实内容），便利你 / agent 后续补全。

设计要点
--------
🔴 **归属即回填**：你在哪个总结单元内找回的序标，就放回对应的总结单元内
   （用户原话）。映射由 ``merge_chapter_map`` 的 ``owners`` 提供，与真实合并 md 逐行对齐，
   故定位精确、不会跨单元串味。
🔴 **安全**：默认 ``--dry-run``（只报告将改什么、绝不写文件）。确认无误后加 ``--apply`` 才写盘。
🔴 **幂等**：单元内已存在该编号的回填占位则跳过，可重复运行不重复插入。
🔴 **不覆盖**：只插入占位，不改写既有条目正文。
🔴 **仅处理「缺号」**：B 层「缺号」+ O 层 HEAD/INTERNAL gap。「顺序错乱」类只报告、
   不自动改标签（重排风险高，留给人工 / agent 处理）。

用法
----
    python flows/write-source/script/backfill_ordinals.py <extract_dir> [ch ...] \
        [--units-dir units|units-translate] [--apply] [--dry-run]
    # 不传 <ch> 即全部章；默认 --dry-run（只报告）。
"""
import io
import json
import os
import re
import sys
import types
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
import lib.boot as _boot
_boot.setup()

sys.stdout.reconfigure(encoding="utf-8")

import attach_content as _ac
from data.book_structure.book_structure import (
    chapter_label, list_chapter_keys, prime_chapter_kinds, unit_dir_name)
import merge_units as _merge
from item_numbering_integrity import _SPAN_RE, _parse_entry, _md_gap_blocking
from subitem_continuity import (
    check_ordinal_subitem_gaps, _o_match_line, _roman_to_int, _alpha_to_int,
    _int_to_roman)
from verify_config import ConfigLoader

_PLACE = "回填占位"

# --- 解析层输出 ---------------------------------------------------------------

_B_RE = re.compile(
    r'^\s*WARN \(BLOCKING\):\s*(\S+)\s+缺号\s+(\d+)\s*（序列\s*([\d.]+)\.\.(\d+)')
# 🔴 emit 行里 INTERNAL gap 写法是 `missing: (3)`（带冒号），HEAD gap 写法是
# `missing (1, 2) ...`（不带冒号）——故 `missing` 后冒号须可选，否则 INTERNAL 整类
# 匹配失败、缺口被静默跳过（实测 O 层回填 planned=0）。
_O_RE = re.compile(
    r'^\s*x L(\d+):\s*\[([^\]]*)\]\s*(HEAD|INTERNAL) gap \((\w+)\)\s*—\s*.*?missing:?\s*\(([^)]*)\)')


def _gk_prefix(gk):
    """从 gk 取编号前缀字符串（'0:1.3'->'1.3'；'0:ex:1.3'->'1.3'；file 类->''）。"""
    body = gk.split(':', 1)[1] if ':' in gk else gk
    if body.startswith('ex:'):
        body = body[len('ex:'):]
    if body.startswith('file'):
        return ''
    return body


def _scan_entries(lines, lang):
    """扫描合并 md 行，返回 [(line_0idx, prefix_str, num, inner)] 加粗条目。"""
    res = []
    for li, ln in enumerate(lines):
        m = _SPAN_RE.search(ln)
        if not m:
            continue
        inner = m.group(1).strip()
        parsed = None
        for lv in (3, 2, 1):
            p = _parse_entry(inner, lv, lang)
            if p:
                parsed = p
                break
        if not parsed:
            continue
        comps, _label = parsed
        if not comps:
            continue
        prefix = '.'.join(str(c) for c in comps[:-1])
        num = comps[-1]
        res.append((li, prefix, num, inner))
    return res


def _relabel_head(anchor_inner, new_last):
    """anchor_inner 形如 'Definition 1.3.4' / '1.3-4' / '定理 1.3.4'。
    返回把末尾数字段替换为 new_last 的条头（不含 ** 与正文）。失败返回 None。"""
    m = re.match(r'^(\D*?)([\d.\-]+)(.*)$', anchor_inner)
    if not m:
        return None
    head, numpath, tail = m.group(1), m.group(2), m.group(3)
    if '-' in numpath:
        base, _ = numpath.rsplit('-', 1)
        newp = base + '-' + str(new_last)
    else:
        base, _ = numpath.rsplit('.', 1)
        newp = base + '.' + str(new_last)
    return head + newp + tail


# --- 序数转换（O 层 raw label <-> int）----------------------------------------

def _to_ord(raw, type_tag):
    if type_tag == 'num':
        try:
            return int(raw)
        except ValueError:
            return 0
    if type_tag == 'roman':
        return _roman_to_int(raw)
    if type_tag == 'alpha':
        return _alpha_to_int(raw)
    try:
        return int(raw)
    except ValueError:
        return 0


def _to_label(ord_val, type_tag):
    if type_tag == 'roman':
        return _int_to_roman(ord_val)
    if type_tag == 'alpha':
        return chr(ord('a') + ord_val - 1) if 1 <= ord_val <= 26 else str(ord_val)
    return str(ord_val)


# --- 单元内插入 ---------------------------------------------------------------

def _entry_block_end(unit_lines, anchor_idx):
    """返回 anchor 条目块之后的插入索引（下一个条目 / ``---`` / EOF 之前）。"""
    n = len(unit_lines)
    i = anchor_idx + 1
    while i < n:
        ln = unit_lines[i]
        if ln.strip() == '---':
            break
        sm = _SPAN_RE.search(ln)
        if sm:
            inner = sm.group(1).strip()
            if any(_parse_entry(inner, lv, None) for lv in (3, 2, 1)):
                break
        i += 1
    return i


def _unit_item_lines(unit_lines):
    """返回 [(unit_line_idx, ordinal_int, raw_label)] 子项行。"""
    out = []
    for ui, uln in enumerate(unit_lines):
        labels = _o_match_line(uln)
        if labels:
            raw = labels[0]
            oi = _to_ord(raw, 'num') or _roman_to_int(raw) or _alpha_to_int(raw)
            if oi > 0:
                out.append((ui, oi, raw))
    return out


def _has_placeholder(unit_text, marker):
    return marker in unit_text


def _apply_inserts(unit_path, inserts, apply):
    """inserts: list of (anchor_unit_idx, placeholder, after_bool)。
    返回 (changed: bool, applied: bool)。"""
    with open(unit_path, encoding="utf-8") as f:
        unit_lines = f.read().split('\n')
    unit_text = '\n'.join(unit_lines)
    # 幂等：已含任一占位标记则整体跳过该单元
    planned = []
    for anchor_idx, placeholder, after in inserts:
        marker = _placeholder_marker(placeholder)
        if _has_placeholder(unit_text, marker):
            continue
        planned.append((anchor_idx, placeholder, after))
    if not planned:
        return False, False
    if not apply:
        return True, False
    # 自底向上插入，保持索引有效
    planned.sort(key=lambda x: x[0], reverse=True)
    for anchor_idx, placeholder, after in planned:
        if after:
            if 0 <= anchor_idx < len(unit_lines) and _o_match_line(unit_lines[anchor_idx]):
                # 锚点本身是子项行（如 (2)）：直接插在该行之后（其尾随空行之前），
                # 避免 _entry_block_end 因不识别子项为边界而越过同块子项跑到 EOF，
                # 把 (3) 错插到 (4) 之后（实测 O 层 after 插入顺序颠倒）。
                j = anchor_idx + 1
            else:
                j = _entry_block_end(unit_lines, anchor_idx)
            unit_lines[j:j] = ['', placeholder]
        else:
            unit_lines[anchor_idx:anchor_idx] = [placeholder, '']
    with open(unit_path, "w", encoding="utf-8") as f:
        f.write('\n'.join(unit_lines).rstrip() + '\n')
    return True, True


def _placeholder_marker(placeholder):
    """从占位行提取稳定去重标记（含编号）。"""
    m = re.search(r'回填占位·([^\·]*)', placeholder)
    return m.group(0) if m else _PLACE


# --- 单章回填 -----------------------------------------------------------------

def _owner_near(owners, idx):
    """owners[idx] 为 None 时向两侧找最近的非 None 归属。"""
    if 0 <= idx < len(owners) and owners[idx]:
        return owners[idx]
    for d in range(1, len(owners)):
        for j in (idx - d, idx + d):
            if 0 <= j < len(owners) and owners[j]:
                return owners[j]
    return None


def _backfill_chapter(ext, ch_key, units_sub, apply, report):
    """回填单章。report 为 list，收集人类可读的变更描述。返回 (planned, applied)。"""
    book_dir = os.path.dirname(os.path.abspath(ext.rstrip("/\\"))) or ext
    # 🔴 fail-closed：merge_chapter_map 缺单元文件 / 门控未过会抛 SystemExit（非
    # Exception 子类），必须在进入 try 前捕获，否则会穿透到 main 也未兜住 -> 整章崩溃。
    try:
        tmp_md, owners, out_dir = _merge.merge_chapter_map(
            ext, ch_key, units_sub=units_sub, require_gate=False)
    except (Exception, SystemExit) as e:
        report.append("  [%s] ⚠️ 拼接失败（可能缺单元文件 / 门控未过），跳过本章回填：%r"
                      % (chapter_label(ch_key), e))
        return 0, 0
    try:
        with open(tmp_md, encoding="utf-8") as f:
            md_lines = f.read().split('\n')
        loader = ConfigLoader(ext, book_dir)
        cfg = loader.config_for_chapter(ch_key)
        lang = getattr(cfg, "language", None) or "cn"
        ctx = types.SimpleNamespace(
            config=cfg, ignore=list(getattr(cfg, "ignore", None) or []),
            md_file=tmp_md, language=lang)
        # 🔴 tmp_md 由 merge_chapter_map 亲自产出（=最终章 md），与步骤 8 同源；
        # B / O 两真层都读它，跑完再删（finally 兜底）。
        blocking, _w, _p, _t, _g = _md_gap_blocking(ctx)
        o_out = check_ordinal_subitem_gaps(tmp_md)

        # 收集每单元的插入操作
        per_unit = {}  # unit_rel -> list of (anchor_unit_idx, placeholder, after)

        # ---- B 层（条目缺号）----
        entries = _scan_entries(md_lines, lang)
        for bs in (blocking or []):
            m = _B_RE.match(bs or '')
            if not m:
                continue  # 顺序错乱等其他 BLOCKING 不自动回填
            gk, n_str, first, last = m.group(1), m.group(2), m.group(3), m.group(4)
            n = int(n_str)
            prefix = _gk_prefix(gk)
            loc = _locate_b_anchor(entries, prefix, n)
            if not loc:
                report.append("  [B] %s 缺号 %d（%s）：无法在合并 md 定位前序条目，跳过"
                              % (gk, n, chapter_label(ch_key)))
                continue
            merged_line, pn, inner, after = loc
            owner = _owner_near(owners, merged_line)
            if not owner:
                report.append("  [B] %s 缺号 %d：映射不到归属单元，跳过" % (gk, n))
                continue
            relabeled = _relabel_head(inner, n)
            head = ("**%s**" % relabeled) if relabeled else ("**%s-%d**" % (prefix, n))
            placeholder = "%s [%s·N=%d·原文章节疑似缺失该条目·待补真实内容]" % (head, _PLACE, n)
            uidx = _find_unit_entry(out_dir, owner, prefix, pn, lang)
            if uidx is None:
                report.append("  [B] %s 缺号 %d：在单元 %s 内找不到前序条目 %s-%d，跳过"
                              % (gk, n, owner, prefix, pn))
                continue
            per_unit.setdefault(owner, []).append((uidx, placeholder, after))
            report.append("  [B] %s 缺号 %d → 单元 %s（%s %s-%d 之后插入占位 %s）"
                          % (gk, n, owner, "之后" if after else "之前",
                             prefix, pn, head))

        # ---- O 层（子项缺号）----
        for os_ in (o_out or []):
            if not (os_ or '').strip().startswith('x'):
                continue
            m = _O_RE.match(os_ or '')
            if not m:
                continue
            L = int(m.group(1))
            ctx_label = m.group(2)
            gap_kind = m.group(3)
            type_tag = m.group(4)
            missing_raw = [x.strip() for x in m.group(5).split(',') if x.strip()]
            owner = _owner_near(owners, L - 1)
            if not owner:
                report.append("  [O] L%d %s gap：映射不到归属单元，跳过" % (L, gap_kind))
                continue
            unit_path = os.path.join(out_dir, owner)
            if not os.path.exists(unit_path):
                report.append("  [O] L%d %s gap：单元 %s 不存在，跳过" % (L, gap_kind, owner))
                continue
            with open(unit_path, encoding="utf-8") as f:
                unit_lines = f.read().split('\n')
            target = md_lines[L - 1].strip() if 0 <= L - 1 < len(md_lines) else ''
            anchor_idx = None
            for ui, uln in enumerate(unit_lines):
                if uln.strip() == target:
                    anchor_idx = ui
                    break
            if anchor_idx is None:
                report.append("  [O] L%d %s gap：单元 %s 内找不到对应行，跳过" % (L, gap_kind, owner))
                continue
            block = _o_block(unit_lines, anchor_idx)
            if not block:
                report.append("  [O] L%d %s gap：单元 %s 内找不到子项块，跳过" % (L, gap_kind, owner))
                continue
            for raw in missing_raw:
                mv = _to_ord(raw, type_tag)
                if mv <= 0:
                    continue
                marker_check = "%s·(%s)" % (_PLACE, raw)
                if _has_placeholder('\n'.join(unit_lines), marker_check):
                    continue
                ins_before = None
                for (ui, oi, r) in block:
                    if oi < mv:
                        ins_before = ui
                if ins_before is None:
                    ins_idx = block[0][0]
                    after = False
                else:
                    ins_idx = ins_before
                    after = True
                label = _to_label(mv, type_tag)
                placeholder = "(%s) [%s·(%s)·原文章节疑似缺失该子项·待补]" % (label, _PLACE, raw)
                per_unit.setdefault(owner, []).append((ins_idx, placeholder, after))
                report.append("  [O] L%d %s gap 缺失 (%s) → 单元 %s（%s插入占位 (%s)）"
                              % (L, gap_kind, raw, owner,
                                 "之后" if after else "块首之前", label))

        # ---- 应用 ----
        planned_total = sum(len(v) for v in per_unit.values())
        applied_total = 0
        for owner, inserts in per_unit.items():
            unit_path = os.path.join(out_dir, owner)
            if not os.path.exists(unit_path):
                continue
            _changed, _applied = _apply_inserts(unit_path, inserts, apply)
            if _applied:
                applied_total += 1
        return planned_total, applied_total
    finally:
        try:
            os.unlink(tmp_md)
        except OSError:
            pass
def _locate_b_anchor(entries, prefix, n):
    """在合并 md 条目中定位缺号 n 的前序条目。返回 (merged_line, prev_num, inner, after)。"""
    cands = [(li, pn, inner) for (li, pfx, pn, inner) in entries
             if pfx == prefix and pn < n]
    if cands:
        li, pn, inner = max(cands, key=lambda x: x[1])
        return li, pn, inner, True
    cands2 = [(li, pn, inner) for (li, pfx, pn, inner) in entries if pfx == prefix]
    if not cands2:
        cands2 = [(li, pn, inner) for (li, pfx, pn, inner) in entries if pn < n]
    if not cands2:
        return None
    li, pn, inner = min(cands2, key=lambda x: x[1])
    return li, pn, inner, False


def _find_unit_entry(out_dir, owner, prefix, pn, lang):
    """在单元文件内找 prefix+pn 条目的行号。"""
    unit_path = os.path.join(out_dir, owner)
    if not os.path.exists(unit_path):
        return None
    with open(unit_path, encoding="utf-8") as f:
        lines = f.read().split('\n')
    for li, ln in enumerate(lines):
        m = _SPAN_RE.search(ln)
        if not m:
            continue
        inner = m.group(1).strip()
        parsed = None
        for lv in (3, 2, 1):
            p = _parse_entry(inner, lv, lang)
            if p:
                parsed = p
                break
        if not parsed:
            continue
        comps, _label = parsed
        if not comps:
            continue
        pfx = '.'.join(str(c) for c in comps[:-1])
        num = comps[-1]
        if pfx == prefix and num == pn:
            return li
    return None


def _o_block(unit_lines, anchor_idx):
    """从 anchor_idx 起，按行距 ≤4 收集子项块（复刻 O 层分组）。"""
    uils = _unit_item_lines(unit_lines)
    si = None
    for k, (ui, oi, r) in enumerate(uils):
        if ui == anchor_idx:
            si = k
            break
    if si is None:
        return []
    block = [uils[si]]
    for k in range(si + 1, len(uils)):
        if uils[k][0] - block[-1][0] <= 4:
            block.append(uils[k])
        else:
            break
    return block


# --- CLI ----------------------------------------------------------------------

def main():
    argv = sys.argv[1:]
    units_sub = "units"
    if "--units-dir" in argv:
        i = argv.index("--units-dir")
        if i + 1 >= len(argv):
            print("[backfill] --units-dir 缺参数（units | units-translate）。")
            return 2
        units_sub = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    apply = "--apply" in argv
    argv = [a for a in argv if a not in ("--apply", "--dry-run")]
    if not argv:
        print(__doc__)
        return 2
    ext = argv[0]
    prime_chapter_kinds(ext)
    try:
        chapters = [int(x) for x in argv[1:]]
    except ValueError:
        chapters = argv[1:]
    keys = [k for k in list_chapter_keys(ext)
            if not chapters or k in {str(c) for c in chapters}]
    if not keys:
        print("[backfill] 无章节可处理。")
        return 2
    mode = "APPLY（写盘）" if apply else "DRY-RUN（只报告，不改文件）"
    print("[backfill] 模式：%s；单元目录：%s" % (mode, units_sub))
    total_planned = 0
    total_applied = 0
    for k in keys:
        report = []
        try:
            planned, applied = _backfill_chapter(ext, k, units_sub, apply, report)
        except (Exception, SystemExit) as e:  # fail-closed：单章异常不影响其余章
            print("[%s] ⚠️ 回填异常（跳过）：%r" % (chapter_label(k), e))
            continue
        total_planned += planned
        total_applied += applied
        head = "[%s] 计划 %d 处" % (chapter_label(k), planned)
        if apply:
            head += "，已写入 %d 个单元" % applied
        print(head)
        for line in report:
            print(line)
    print("[backfill] 完成：共计划 %d 处回填%s"
          % (total_planned, ("，已写入 %d 处" % total_applied) if apply else "（DRY-RUN，未写盘）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
