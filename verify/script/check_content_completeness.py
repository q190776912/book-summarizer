"""check_content_completeness.py — 内容化分章契约的完整性闸门（write-source 步骤 4）。

结构完整性（章节 / 定理定义等缺项）由 structure 子流程第 2–4 步闸门保证；本脚本
补上**内容完整性**——保证所有描述信息（description 节点）、证明（proof 子节点）、
图片（image 内容块）与全部文字 / 公式块都进入内容化分章契约，无遗漏、无多余：

  1. **确定性复算比对**：`attach_content.build_chapter_contract` 是纯函数——按同一
     管线（收集 → 噪声过滤 → 行内公式拼接 → 几何标记 → 锚点分派 → 证明拆分 → 描述
     聚合）在内存中重建该章契约，与磁盘上的 `book_structure_{N}.json` 做**内容块
     多重集比对**（text 按归一化文字、formula 按 latex + display + **tag**、
     image 按路径）。不一致 = 磁盘契约相对管线过期 / 被手改 → FAIL。
     ⚠️ 本项是**幂等自证**（同管线重算 vs 磁盘），只能发现"磁盘与管线不一致"，
     发现不了"管线本身漏抓"——后者必须靠下面的独立真值项。
  2. **图片完整性（独立真值）**：`figure_index.json` 中落在该章页码区间内的每张图
     必须以 image 块出现在契约中（按路径多重集比对）→ 缺图 FAIL。
  2b. **公式序标完整性（独立真值）**：`page_*.json` 中**独立成块**的公式编号
     （形态由本书 `formula.type` 经 `ORDINAL_DEPTH` 派生，**不是**写死的
     `(C.N)`；章级编号书要求首分量等于本章章号）必须在该章契约中被“交代”：
       * 挂在某个公式块的 `tag` 上 —— 正常；
       * 编号仍在契约正文中（未挂上，作为散落的 `(C.N)` 文本块保留）—— **WARN**
         （信息未丢，但序标没挂到公式上，agent 调整时须手工补 `\tag`）；
       * 两者都没有（编号随文本块一起被噪声过滤/丢弃）—— **FAIL**（编号真丢了）。
  3. **证明覆盖审计（尽力而为）**：重算保留文本块中未被 proof 子节点收编的证明
     标记命中（内联「证…」漏检等）→ WARN 列出（供 agent 定位补拆，不阻断）。

用法
----
    python verify/script/check_content_completeness.py <extract_dir> [ch ...]
退出码：0 = 全部通过；1 = 存在 FAIL。write-source 步骤 4 以此为闸（拆分单元前执行）。
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
    """内容块 → 可比对的签名 (kind, content)。

    ⚠️ 公式块的签名必须含 ``tag``：否则「契约里全部 tag 被抹掉 / 管线漏挂 tag」
    在复算比对两侧同样缺失，闸门会误报 PASS（2026-08-29 Koopman 书实测）。
    """
    if "image" in b:
        return ("image", _norm_text(b.get("image")))
    if "formula" in b:
        return ("formula", (_norm_text(b.get("formula")), bool(b.get("display")),
                            _norm_text(b.get("tag"))))
    return ("text", _norm_text(b.get("text")))


def _source_formula_tags(ext, start, end, ch_prefix, ncomp=None):
    """书源独立公式编号块（独立真值，不经 attach 管线）。

    遍历页区间内 ``page_*.json`` 的 ``text``，取**整块恰为一个编号**的块，返回
    **裸编号集合**。编号形态（段数 / 括号 / 分隔符 / 字母后缀）由 ``ncomp``
    派生于本书 ``verify_config.json`` 的 ``formula.type``——🔴 **不可硬编码成
    ``(C.N)`` 一种**：实测各书还有 ``(1)`` 节级重置、``(11.1-1)`` 连字符三段、
    ``(8.11a)`` 字母后缀，以及近半数书右缘编号**不带括号**。

    ``ch_prefix`` 非空时只收首分量等于该章号的编号（排除跨章引用）。
    """
    from page_json import PageJson
    from lib.numbering import formula_tag_number
    out = set()
    for p in range(int(start), int(end) + 1):
        fp = os.path.join(ext, "page_%03d.json" % p)
        if not os.path.exists(fp):
            continue
        try:
            pg = PageJson.load(fp)
        except Exception:
            continue
        for t in pg.text_blocks:
            raw = t.get("text")
            if isinstance(raw, dict):          # MM 修复可能嵌套一层
                raw = raw.get("text")
            if not isinstance(raw, str):
                continue
            key = formula_tag_number(raw.strip(), ncomp)
            if key is None:
                continue
            if ch_prefix and re.split(r'[.\-·,]', key)[0] != ch_prefix:
                continue
            out.add(key)
    return out


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

    # ②b 公式序标完整性（page_*.json 独立真值，不经 attach 管线）
    got_tags = {b["tag"] for b in ac._iter_blocks(saved) if b.get("tag")}
    ncomp, scope = ac.formula_cfg(ext)
    # 🔴 与 Q 层一致**opt-in**：书未配 `formula` 时整项跳过。否则段数兜底正则
    # （段数不限、含裸排）会把页眉页脚的**页码**当成公式编号，而页码已被
    # _filter_noise 从契约剔除 → 每章凭空报「公式编号丢失」并阻断渲染。
    if ncomp is None:
        lines.append("    公式序标：本书未配置 `formula`（Q 层同源 opt-in）→ 跳过序标比对")
    else:
        # 只有「章级编号」（scope=2）才能用「首分量 == 章号」筛编号：book 级全书
        # 连续号（scope=1）与节级重置（scope=3）的首分量都与章号无关，筛了清零。
        ch_key_s = str(ch_node.get("key") or "")
        prefix = ch_key_s if (scope == 2 and ch_key_s.isdigit()) else ""
        want_tags = _source_formula_tags(ext, ch_node.get("page_start"),
                                         ch_node.get("page_end"), prefix, ncomp)

        def _ord(k):
            return [int(y) for y in re.split(r'[.\-·,]', k) if y.isdigit()]

        unattached = sorted(want_tags - got_tags, key=_ord)
        if want_tags:
            all_text = "\n".join((b.get("text") or "")
                                 for b in ac._iter_blocks(saved) if "text" in b)
            lost_tags = [t for t in unattached if t not in all_text]
            if lost_tags:
                ok = False
                lines.append(f"  x 公式编号丢失 {len(lost_tags)} 个（书源独立成块、契约"
                             f"既未挂 tag 也无该文本）：{lost_tags[:8]}")
            if unattached and not lost_tags:
                lines.append(f"  ? 公式编号未挂到公式 {len(unattached)} 个（编号仍在正文，"
                             f"但没成为任何公式块的 tag，调整时须手工补 \\tag）："
                             f"{unattached[:8]}")
            lines.append(
                f"    公式序标：书源={len(want_tags)} 已挂tag={len(want_tags & got_tags)}"
                f" 未挂={len(unattached)}")

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
                    f"formula_tag={len(got_tags)} "
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
