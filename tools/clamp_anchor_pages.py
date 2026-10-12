#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tools/clamp_anchor_pages.py — 契约「锚点」blocker 的根因修复（contract-only，零排序）。

缺陷：`check_structure_completeness` 的 `residual_anchor_order`（BLOCKING(锚点)）来自
`lib.unit_order.check_contract_anchors`——契约节点按**前序遍历**的 `page_start` 必须单调不减。
OCR 常把某结构节点的 page_start 命到「正文首现/页眉/被引用」的较早页，导致该节点在树里的
页码比其前序内容更小 → 前序页码「向后跳」，报「锚点与树序矛盾」。这是**元数据页码**问题，
内容并未挂错节（归属=0）。

正解（判据与 check_contract_anchors 严格同源，方向单调）：
  沿前序、对「参与锚点判定」的同一节点集（norm_secnum(key) 为真 ∧ page_start 存在 ∧
  type != 'proof' ∧ 非章末 dash 习题键）维护 running_max：某节点 page_start < running_max
  （向后跳）时，把它抬到 running_max（其真实阅读位置），page_end 一并抬到 ≥ page_start。
  只**抬高向后节点**，从不压低别的节点、从不重排子节点、从不改父节点。
    ⇒ 前序页码子列变单调不减 ⇒ 锚点归零；
    ⇒ 树序(=编号序)不变 ⇒ 不引入 residual_b_blocking（顺序错乱）；
    ⇒ 父成员关系不变 ⇒ 不引入归属问题。

⚠ 切勿用「按 page_start 重排子节点」来消锚点——当页码序≠编号序时会制造顺序错乱(B)阻断。
   （这正是 clamp 优于 sort 的地方。）

fail-closed：落盘前自检 check_contract_anchors(new)==[]，否则拒绝写出。
默认 dry-run，加 `--commit` 才写盘；写盘只动该契约 JSON，绝不触碰 units/交付。

用法:
  python -X utf8 tools/clamp_anchor_pages.py <contract.json> [--commit]
"""
import os, sys, json, copy
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
from lib.unit_order import check_contract_anchors, is_dash_problem, norm_secnum


def clamp_stream(root):
    """就地按前序对参与锚点判定的节点做「向后抬高」。返回被抬高的 (type,key,old,new) 列表。"""
    touched = []
    state = {"mx": -1}

    def walk(node):
        if not isinstance(node, dict):
            return
        key = node.get("key")
        ps = node.get("page_start")
        ntype = node.get("type")
        nk = norm_secnum(key) if key is not None else None
        participates = bool(nk) and ps is not None and ntype != "proof" \
            and not is_dash_problem(key)
        if participates:
            try:
                page = int(ps)
            except (TypeError, ValueError):
                page = None
            if page is not None:
                if page < state["mx"]:
                    node["page_start"] = state["mx"]
                    pe = node.get("page_end")
                    try:
                        if pe is not None and int(pe) < state["mx"]:
                            node["page_end"] = state["mx"]
                    except (TypeError, ValueError):
                        pass
                    touched.append((ntype, key, page, state["mx"]))
                else:
                    state["mx"] = page
        for sub in (node.get("sub_sec") or []):
            walk(sub)

    walk(root)
    return touched


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__); return 0
    cpath = sys.argv[1]
    commit = "--commit" in sys.argv[2:]
    orig = json.loads(open(cpath, encoding="utf-8").read())
    new = copy.deepcopy(orig)

    before = check_contract_anchors(orig)
    touched = clamp_stream(new)
    after = check_contract_anchors(new)

    print(f"contract = {os.path.basename(cpath)}")
    print(f"anchor BEFORE = {len(before)} | clamped nodes = {len(touched)} | anchor AFTER = {len(after)}")
    for t in touched[:40]:
        print(f"   clamp {t[0]}「{t[1]}」 p{t[2]} -> p{t[3]}")
    if len(touched) > 40:
        print(f"   ...(+{len(touched)-40} more)")

    if after:
        print(">> 抬升后仍有残留锚点问题，拒绝落盘（fail-closed）：")
        for p in after[:20]:
            print("   -", p)
        return 1
    if commit and touched:
        json.dump(new, open(cpath, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        print(f"COMMITTED (contract-only)：仅抬升 {len(touched)} 个向后锚点，未重排、未改父、未动正文。")
    elif not touched:
        print("(无向后锚点，无需改动)")
    else:
        print("(dry-run; add --commit to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
