"""check_content_completeness.py — 内容化分章契约的完整性闸门（write-source 步骤 4）。

结构完整性（章节 / 定理定义等缺项）由 structure 子流程第 2–4 步闸门保证；本脚本
补上**内容完整性**——保证所有描述信息（description 节点）、证明（proof 子节点）、
图片（image 内容块）与全部文字 / 公式块都进入内容化分章契约，无遗漏、无多余：

  1. **确定性复算比对**：`attach_content.build_chapter_contract` 是纯函数——按同一
     管线（收集 → 噪声过滤 → 行内公式拼接 → 几何标记 → 锚点分派 → 证明拆分 → 描述
     聚合）在内存中重建该章契约，与磁盘上的 `book_structure_{N}.json` 做**内容块
     多重集比对**（text 按归一化文字、formula 按 latex+display、image 按路径）。
     不一致 = 磁盘契约相对管线过期 / 被手改 → FAIL。
  2. **图片完整性（独立真值）**：`figure_index.json` 中落在该章页码区间内的每张图
     必须以 image 块出现在契约中（按路径多重集比对）→ 缺图 FAIL。
  3. **证明覆盖审计（尽力而为）**：重算保留文本块中未被 proof 子节点收编的证明
     标记命中（内联「证…」漏检等）→ WARN 列出（供 agent 定位补拆，不阻断）。

用法
----
    python verify/script/check_content_completeness.py <extract_dir> [ch ...]
退出码：0 = 全部通过；1 = 存在 FAIL。write-source 步骤 4 以此为闸（渲染草稿前执行）。
"""
import collections
import json
import os
import re
import sys
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

import attach_content as ac


def _norm_text(s):
    return re.sub(r"\s+", " ", (s or "")).strip()


def _block_sig(b):
    """内容块 → 可比对的签名 (kind, content)。"""
    if "image" in b:
        return ("image", _norm_text(b.get("image")))
    if "formula" in b:
        return ("formula", (_norm_text(b.get("formula")), bool(b.get("display"))))
    return ("text", _norm_text(b.get("text")))


def _walk_nodes(node):
    """深度优先 yield 全部结构节点（含自身，跳过内容块）。"""
    yield node
    for c in node.get("sub_sec") or []:
        if not ac._is_block(c):
            yield from _walk_nodes(c)


def _collect_contract_blocks(node):
    """契约章节点 → 全部内容块签名多重集（含 description / proof 内的块）。"""
    sig = collections.Counter()
    for b in ac._iter_blocks(node):
        sig[_block_sig(b)] += 1
    return sig


def _nodes_by_type(node):
    cnt = collections.Counter()
    for n in _walk_nodes(node):
        t = n.get("type")
        if t in ("description", "proof"):
            cnt[t] += 1
    return cnt


def check_chapter(ext, ch_node):
    """校验单章：返回 (ok, lines[])。"""
    ch_key = str(ch_node.get("key"))
    lines = []
    ok = True

    # ① 确定性复算比对（块多重集）：build_chapter_contract 幂等
    # （内部先还原骨架），可直接对磁盘契约重建。
    built, stats = ac.build_chapter_contract(ext, ch_node)
    built_sig = _collect_contract_blocks(built)
    p = ac.out_path(ext, ch_key)
    if not os.path.exists(p):
        return False, [f"  x 缺内容化分章契约 book_structure_{ch_key}.json（先跑 attach_content）"]
    with open(p, encoding="utf-8") as f:
        saved = json.load(f)
    saved_sig = _collect_contract_blocks(saved)

    missing = built_sig - saved_sig      # 管线有、磁盘无 → 丢失
    extra = saved_sig - built_sig        # 磁盘有、管线无 → 手改 / 过期
    if missing:
        ok = False
        lines.append(f"  x 契约缺块 {sum(missing.values())} 个（相对重算结果丢失）：")
        for (k, c), n in list(missing.items())[:6]:
            lines.append(f"      - [{k}] {str(c)[:80]}")
    if extra:
        ok = False
        lines.append(f"  x 契约多块 {sum(extra.values())} 个（相对重算结果多余 / 过期）：")
        for (k, c), n in list(extra.items())[:6]:
            lines.append(f"      - [{k}] {str(c)[:80]}")

    # ② 图片完整性（figure_index 独立真值）
    fp = os.path.join(ext, "figure_index.json")
    if os.path.exists(fp):
        with open(fp, encoding="utf-8") as f:
            idx = json.load(f)
        start, end = int(ch_node.get("page_start") or 0), int(ch_node.get("page_end") or 0)
        want = collections.Counter(
            os.path.join(ac._extract_rel_prefix(ext), e.get("file") or "").replace("\\", "/")
            for e in (idx if isinstance(idx, list) else [])
            if start <= int(e.get("page") or 0) <= end)
        got = collections.Counter(b["image"] for b in ac._iter_blocks(saved)
                                  if "image" in b)
        miss_img = want - got
        extra_img = got - want
        if miss_img:
            ok = False
            lines.append(f"  x 图片缺失 {sum(miss_img.values())} 张："
                         f"{sorted(miss_img)[:4]}")
        if extra_img:
            lines.append(f"  ? 图片多出 {sum(extra_img.values())} 张（不在 figure_index "
                         f"页区间内，多为跨页图）：{sorted(extra_img)[:4]}")

    # ③ 证明覆盖审计（尽力而为，WARN 不阻断）
    proof_nodes = _nodes_by_type(saved).get("proof", 0)
    missed = []
    for n in _walk_nodes(saved):
        for b in n.get("sub_sec") or []:
            # 只审「普通条目正文的文本块」——proof / description 内的文本已被收编
            if not ("text" in b and n.get("type") not in ("proof", "description",
                                                          "exercise", "chapter",
                                                          "section")):
                continue
            t = b.get("text") or ""
            if ac._PROOF_MARKER.match(t) or ac._CN_INLINE_PROOF.search(t):
                missed.append((n.get("key"), _norm_text(t)[:60]))
    if missed:
        lines.append(f"  ? 疑似未拆分证明 {len(missed)} 处（标记命中但未成 proof 节点，"
                     f"agent 调整时留意）：")
        for k, t in missed[:5]:
            lines.append(f"      - 条目 {k}: {t}")

    lines.insert(0, f"ch{ch_key}: text={stats['text']} formula={stats['formula']} "
                    f"image={stats['image']} proof={stats['proof']} "
                    f"description={stats['description']} "
                    f"noise_dropped={stats['noise_dropped']} | "
                    f"{'PASS' if ok else 'FAIL'}")
    return ok, lines


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    ext = argv[0]
    try:
        chapters = [int(x) for x in argv[1:]]
    except ValueError:
        chapters = argv[1:]
    if not os.path.exists(os.path.join(ext, "_extraction_done.json")):
        print("[check_content_completeness] BLOCKED: 缺 _extraction_done.json。")
        return 2
    keys = ac.list_chapter_keys(ext)
    if chapters:
        want = {str(c) for c in chapters}
        keys = [k for k in keys if k in want]
    if not keys:
        print("[check_content_completeness] 无分章契约（ch*.json / appendix*.json）。")
        return 2
    all_ok = True
    for k in keys:
        with open(ac.out_path(ext, k), encoding="utf-8") as f:
            node = json.load(f)
        ok, lines = check_chapter(ext, node)
        all_ok = all_ok and ok
        for ln in lines:
            print(ln)
    print("CONTENT GATE:", "PASS" if all_ok else "FAIL")
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
