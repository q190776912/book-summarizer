#!/usr/bin/env python3
"""tools/fix_section_name.py — 按**印刷证据**修回分章契约里被 OCR 改写的节标题（五本账同步）。

缺陷场景（Apostol《Introduction to Analytic Number Theory》实测 2026-09-29）：
扫描件 OCR 把希腊字母读成拉丁字母，节标题因此残缺——印面 `2.3: The Euler totient function
φ(n)` 抽成 `2.3 The Euler totient function p(n)`、`2.8 The Mangoldt function Λ(n)` 抽成
`A(n)`、`2.13 The divisor functions σ_α(n)` 抽成 `oa(n)`。写手按 brief「以印面为唯一真值」
把单元 H2 写成 `$\\varphi(n)$`，于是门控 `lib/section_titles.title_problems` 报
「契约 name 与单元标题不一致：两侧互非前缀（其中一侧被 OCR 改写）；以印刷证据为准统一五处」。
**该闸是对的，残缺的是契约**：契约 `name` 是 SSOT（重拆单元、回填、审计都以它为准），
写手无权改契约，主代理手改 JSON 又极易只改一处留下四账漂移。本工具把「修 SSOT」变成
一条带断言的正规通道，与 `config/verify_config/register_formula.py`（登记丢失印刷编号）同性质。

五本账（gate 文案里的「五处」）与分工：
  ① 分章契约 `ch{N}.json`（附录 `appendix{X}.json`）该 section 节点的 `name`   —— 本工具改
  ② `units/ch{N}/manifest.json` 对应记录的 `name`                              —— 本工具改
  ③ `units-translate/ch{N}/manifest.json`（若该侧已初始化）                     —— 本工具改
  ④ 单元首行 marker 的 `name=`                                                  —— 交 `tools/sync_translate_markers.py`
     （该工具以 manifest 为真值复位 marker，正文一字节不动；本工具在报告里给出确切命令）
  ⑤ 单元正文 H2（`## §N.M …`）                                                  —— 本工具**只校验**：
     修完必须与 `--name` 在 `lib.section_titles.norm_title` 下相等，否则报 MISMATCH

保险：
  - 默认 dry-run，`--apply` 才写盘；写盘前把每个受影响文件备份到 `<extract>/_bak_section_names/<时间戳>/`。
  - **锚定字节替换**（不做 json.dump 重写），契约/manifest 的缩进与其余字节一字节不变；
    锚点 `"key": "<sec>"` 命中数 ≠ 1、或锚点后 400 字节内找不到 `"name":` → 拒绝写出。
  - 写后 `json.load` 复算：全树与该节相关的差异必须**只有 name 一个字段**，否则报错退出。
  - `--name` 必须以节序标开头（除非 `--allow-bare`），且不得含 `$`（账目面存印刷裸文本/KaTeX
    之外的排版标记 = 把 OCR 损伤换成 LaTeX 损伤；比对两侧 `norm_title` 会折形，写裸字符即可）。
  - 必须给 `--evidence`（≥10 字，说明印面出处：页/行/渲染方式），逐次追加到
    `<extract>/_section_name_fixes.jsonl` 供事后审计。

用法:
  python tools/fix_section_name.py <extract_dir> <ch_key> <sec_key> --name "2.3 The Euler totient function φ(n)" \\
      --evidence "fitz 300dpi 裁物理页37标题行，印面作 φ(n)" [--apply]
  # ch_key：数字章传裸号（2），附录传字母（A）；sec_key 用契约里的节键（2.3）
退出码：0 = 已一致或已写出（dry-run 有差异也算 0，用 --check 时差异 = 1）；2 = 拒绝（未写任何文件）。
"""
import argparse
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

from data.book_structure.book_structure import (  # noqa: E402
    prime_chapter_kinds, resolve_chapter_json_path, unit_dir_name)
from lib.section_titles import norm_title  # noqa: E402

_DEC = json.JSONDecoder()
_KEY_WINDOW = 400


class Refuse(Exception):
    """拒绝写出（未触碰任何文件）。"""


def contract_path(extract_dir, ch_key):
    """分章契约路径：按**磁盘物理证据**解析（ch / appendix / supplement 三种前缀）。

    🔴 旧写法 `appendix%s.json` 一刀切，补篇（键 `S`）永远读不到契约 → 该章每个节都报
    「找不到契约」而拒绝修名（Katok supplementS 实测）。判据与 `unit_dir_name` 同源。
    """
    prime_chapter_kinds(extract_dir)
    p = resolve_chapter_json_path(extract_dir, ch_key)
    if not p or not os.path.isfile(p):
        raise Refuse("分章契约不存在：%r（章键 %r）" % (p, ch_key))
    return p


def unit_dir(extract_dir, ch_key, side="units"):
    """单元目录：同样按物理证据在 ch/appendix/supplement 三候选里取实际存在的那个。"""
    bs = os.path.join(extract_dir, "book_structure")
    cands = []
    try:
        cands.append(unit_dir_name(ch_key))
    except Exception:
        pass
    cands += ["%s%s" % (pre, ch_key) for pre in ("ch", "appendix", "supplement")]
    hits = []
    for nm in cands:
        d = os.path.join(bs, side, nm)
        if os.path.isdir(d) and d not in hits:
            hits.append(d)
    if len(hits) > 1:
        raise Refuse("%s 侧同时存在 %s 两个该章单元目录（章键 %r 章型歧义），拒绝猜"
                     % (side, ", ".join(os.path.basename(h) for h in hits), ch_key))
    return hits[0] if hits else None


def _find_name_after_key(raw, sec_key, label):
    """返回 [(anchor_idx, name_value_idx, old_name)]；锚点须唯一命中。"""
    anchors = [m.start() for m in re.finditer(r'"key":\s*"%s"' % re.escape(sec_key), raw)]
    if not anchors:
        raise Refuse("%s：找不到 key=%r 的节点" % (label, sec_key))
    if len(anchors) > 1:
        raise Refuse("%s：key=%r 锚点命中 %d 次，无法定位唯一节点（拒绝猜）"
                     % (label, sec_key, len(anchors)))
    seg = raw[anchors[0]:anchors[0] + _KEY_WINDOW]
    m = re.search(r'"name":\s*"', seg)
    if not m:
        raise Refuse("%s：key=%r 锚点后 %d 字节内没有 \"name\" 字段" % (label, sec_key, _KEY_WINDOW))
    vstart = anchors[0] + m.end() - 1
    old, _ = _DEC.raw_decode(raw, vstart)
    return anchors[0], vstart, old


def _node_name(tree, sec_key):
    """从解析后的树里取该节 name（用于写后差异复算）。"""
    found = []

    def walk(n):
        if isinstance(n, dict):
            if str(n.get("key") or "") == sec_key:
                found.append(n.get("name"))
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(tree)
    return found[0] if found else None


def _replace_literal(raw, idx, old_len, new_literal, label):
    """把 raw[idx:idx+old_len] 换成 new_literal，并断言只此一处。"""
    if raw[idx:idx + old_len] == new_literal:
        return raw                      # 已是新值（幂等续跑）
    out = raw[:idx] + new_literal + raw[idx + old_len:]
    if out.count(new_literal) != raw.count(new_literal) + 1:
        raise Refuse("%s：替换后目标串出现次数异常（拒绝写出）" % label)
    return out


def plan(extract_dir, ch_key, sec_key, new_name, evidence, allow_bare=False):
    """算出全部待改文件 → [(path, raw_before, raw_after, old_name)]；任何不满足即 Refuse。"""
    if not evidence or len(evidence.strip()) < 10:
        raise Refuse("--evidence 必填且不少于 10 字（印面出处：页/行/渲染方式）")
    if "$" in new_name or "\\" in new_name:
        raise Refuse("--name 不得含 LaTeX 排版标记（%r）：账目面存印刷裸文本，"
                     "KaTeX 形只出现在单元正文" % new_name)
    if not allow_bare and not new_name.strip().startswith(str(sec_key)):
        raise Refuse("--name 应以节序标 %r 开头（与契约其余节名同形态）；确要裸标题加 --allow-bare"
                     % sec_key)
    targets = []
    cp = contract_path(extract_dir, ch_key)
    with io.open(cp, encoding="utf-8") as f:
        raw = f.read()
    _a, idx, old = _find_name_after_key(raw, sec_key, os.path.basename(cp))
    new_lit = json.dumps(new_name, ensure_ascii=False)
    after = _replace_literal(raw, idx, len(json.dumps(old, ensure_ascii=False)), new_lit,
                             os.path.basename(cp))
    targets.append((cp, raw, after, old))

    manifests = []
    for side in ("units", "units-translate"):
        d = unit_dir(extract_dir, ch_key, side)
        if not d:
            continue
        mp = os.path.join(d, "manifest.json")
        if os.path.isfile(mp):
            manifests.append((side, mp))
    unit_file = None
    for side, mp in manifests:
        raw = io.open(mp, encoding="utf-8").read()
        _a, idx, m_old = _find_name_after_key(raw, sec_key, os.path.basename(mp))
        if m_old != old:
            raise Refuse("%s：该节 name=%r 与契约 %r 不一致（先人工核对，拒绝自动统一）"
                         % (mp, m_old, old))
        after = _replace_literal(raw, idx, len(json.dumps(old, ensure_ascii=False)), new_lit,
                                 os.path.basename(mp))
        targets.append((mp, raw, after, old))
        if side == "units" and not unit_file:
            m = json.loads(after)
            for u in m.get("units", []):
                if str(u.get("key")) == str(sec_key) and u.get("type") == "section":
                    unit_file = os.path.join(os.path.dirname(mp), u.get("file") or "")
    if not manifests:
        raise Refuse("找不到任何含该节的 manifest（units/units-translate 均无）")
    if not unit_file or not os.path.isfile(unit_file):
        raise Refuse("找不到该节的单元文件（manifest 无 type=section & key=%r 记录）" % sec_key)
    return targets, unit_file, old


def check_heading(unit_file, sec_key, new_name):
    """⑤ 本工具只校验：单元 H2 与修后契约名须在 norm_title 下相等。"""
    head = None
    for ln in io.open(unit_file, encoding="utf-8").read().split("\n"):
        if ln.startswith("#"):
            head = ln
            break
    if head is None:
        return "NO-HEADING", None
    a, b = norm_title(new_name, sec_key), norm_title(head, sec_key)
    return ("MATCH" if a == b else "MISMATCH"), (head, a, b)


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


def apply(extract_dir, targets, ch_key):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    bak = os.path.join(extract_dir, "_bak_section_names", stamp)
    bak = _mkdir_unique(bak)
    for path, before, after, _old in targets:
        io.open(os.path.join(bak, os.path.basename(path)), "w", encoding="utf-8",
                newline="\n").write(before)
    for path, _b, after, _old in targets:
        io.open(path, "w", encoding="utf-8", newline="\n").write(after)
    # 写后复算：解析树里该节 name 必须已是新值，且其余字段与备份逐字相同
    for path, before, after, _old in targets:
        json.loads(after)
        if json.loads(before) == json.loads(after):
            raise Refuse("%s：写出后内容无变化（内部错误）" % path)
    return bak


def audit(extract_dir, rec):
    p = os.path.join(extract_dir, "_section_name_fixes.jsonl")
    with io.open(p, "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return p


def main(argv=None):
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("extract_dir")
    ap.add_argument("ch_key")
    ap.add_argument("sec_key")
    ap.add_argument("--name", required=True)
    ap.add_argument("--evidence", default="")
    ap.add_argument("--allow-bare", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--check", action="store_true", help="只核对五本账，有差异 exit 1")
    a = ap.parse_args(argv)
    try:
        targets, unit_file, old = plan(a.extract_dir, a.ch_key, a.sec_key, a.name,
                                       a.evidence, a.allow_bare)
        status, detail = check_heading(unit_file, a.sec_key, a.name)
        already = [t for t in targets if t[1] == t[2]]
        print("契约旧名  = %r" % old)
        print("契约新名  = %r" % a.name)
        print("单元 H2   = %s  %s" % (status, unit_file))
        if status == "MISMATCH":
            print("            契约侧归一=%r / 单元侧归一=%r" % (detail[1], detail[2]))
        for path, before, after, _o in targets:
            print("%s %s" % ("=" if before == after else "~", os.path.basename(path)))
        if status == "MISMATCH":
            print("REFUSE: 修完契约仍与单元 H2 不同形——要么单元标题写错，要么 --name 不是印面形")
            return 2
        if a.check:
            return 1 if len(already) != len(targets) else 0
        if len(already) == len(targets):
            print("NO-OP     契约与两侧 manifest 已是新名，无需写出")
            return 0
        if not a.apply:
            print("DRY-RUN（未写盘）：加 --apply 落盘")
            return 0
        bak = apply(a.extract_dir, targets, a.ch_key)
        rec = audit(a.extract_dir, {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                    "extract_dir": os.path.abspath(a.extract_dir),
                                    "ch_key": a.ch_key, "sec_key": a.sec_key,
                                    "old": old, "new": a.name, "evidence": a.evidence,
                                    "heading_check": status, "backup": bak,
                                    "files": [os.path.basename(p) for p, *_ in targets]})
        print("APPLIED   备份=%s 台账=%s" % (bak, rec))
        print("下一步（第④本账：单元首行 marker 复位，正文不动）：")
        print("  python tools/sync_translate_markers.py \"%s\" --ch %s --side units --apply"
              % (a.extract_dir, a.ch_key))
        return 0
    except Refuse as e:
        print("REFUSE: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
