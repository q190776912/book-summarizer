#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/fix_section_ties.py — 契约「节序」blocker（同页 tie）的根因修复（contract-only，零归属）。

缺陷：`check_structure_completeness.subsection_order_problems` 要求同一父节点下的 `section`
子节点，其数字键随契约列表顺序**严格递增**；否则报 BLOCKING(节序)「节序逆序」。常见成因是
**同一锚点页**上两个小节的列表顺序把小号排在了大号之后（章目录回扫/同页 tie）。

安全修法（可证不影响锚点）：只在**共享同一 page_start 的 section 子节点之间**按键升序重排，
把它们放回**原来那批同页槽位**。因这些槽位的页码全相等、且不动其余任何节点，整棵树的**前序
页码序列逐字节不变** ⇒ 绝不影响 check_contract_anchors。跨页的 section 一律不碰。

⚠ 边界：若两个同页 section 之间夹着「页码更高的条目/兄弟」，把它们排成键升序会把其中之移过
   那个高页节点 → 触发锚点逆序。此时本工具自检 check_contract_anchors 会变红并 fail-closed
   拒绝落盘——这是**真冲突**（锚点页本身错了），应回源核对后做 page_start 页码校正，而不是重排。
   若「顶层 section」其实是某节内第 N 条编号注记被误解析（正文常自证，如「下面§2及§3…」），
   正解是把该节点 type 由 section 降为 description（见 tools/clamp_anchor_pages.py 文档旁注）。

fail-closed：落盘前自检 check_contract_anchors(new)==[]，否则拒绝写出。默认 dry-run，`--commit` 才写。

用法:
  python -X utf8 tools/fix_section_ties.py <contract.json> [--commit]
"""
import os, sys, json, copy, re
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c); break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as boot; boot.setup()
from lib.unit_order import check_contract_anchors

_NUM_RE = re.compile(r"\d+(?:\.\d+)*")


def sec_key_nums(key):
    if key is None:
        return None
    m = _NUM_RE.search(str(key).strip())
    if not m:
        return None
    try:
        return tuple(int(x) for x in m.group(0).split("."))
    except ValueError:
        return None


def fix(root):
    moves = []

    def rec(node):
        kids = node.get("sub_sec") or []
        secs = [(i, c) for i, c in enumerate(kids) if c.get("type") == "section"]
        groups = {}
        for i, c in secs:
            groups.setdefault(c.get("page_start"), []).append((i, c))
        for pg, members in groups.items():
            if pg is None or len(members) < 2:
                continue
            ordered = sorted(members, key=lambda ic: (sec_key_nums(ic[1].get("key")) or (10**9,), ic[0]))
            slots = [i for i, _ in members]
            changed = False
            for slot, (_, c) in zip(slots, ordered):
                if kids[slot] is not c:
                    changed = True
                kids[slot] = c
            if changed:
                for _, c in ordered:
                    moves.append((pg, c.get("key")))
        for c in (node.get("sub_sec") or []):
            rec(c)

    rec(root)
    return moves


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__); return 0
    cpath = sys.argv[1]
    commit = "--commit" in sys.argv[2:]
    orig = json.loads(open(cpath, encoding="utf-8").read())
    new = copy.deepcopy(orig)
    a_before = check_contract_anchors(orig)
    moves = fix(new)
    a_after = check_contract_anchors(new)
    print(f"contract = {os.path.basename(cpath)} | reordered(same-page groups) = {len(moves)} | anchor {len(a_before)}->{len(a_after)}")
    if a_after:
        print(">> 重排后锚点出现逆序 = 真冲突（锚点页本身错，非纯 tie），拒绝落盘（fail-closed）：")
        for p in a_after[:20]:
            print("   -", p)
        return 1
    if commit and moves:
        json.dump(new, open(cpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"COMMITTED (contract-only)：重排 {len(moves)} 个同页 section，前序页码序列不变、未改归属、未动正文。")
    elif not moves:
        print("(无同页 section tie 需要重排)")
    else:
        print("(dry-run; add --commit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
