# -*- coding: utf-8 -*-
"""只读普查：回填闸 ⑭ 的**邻接判据按语种分叉**在跨语料上改写了哪些站点（2026-10-31，#25）。

动因：`anchor_adjacency` 里「遇散文即停」原本只有一套**拉丁**词形启发式（≥1 个 5+ 字母词
或 2 个 4+ 字母词）。中文契约的正文句子（「在这两个公式中，f 是连续的」）一个 4+ 字母词都
没有 → 被当碎片**跨过去**命中远处展示式（假配）；反过来中文公式的续行碎片
（`cos uxdu f(t)cos utdt.` 恰好两个 4+ 字母词）被当句子**拦停** → 真邻接判不出来（假拒，
数学分析 ch17 D21 (11)-(16) 六处只能靠 `--confirm-non-adjacent` 人工放行）。
修法 = 散文判据按**该章 manifest 的 `language`** 分叉，并只给中文书加一条「锚点**向前**的
第一条展示式」腿。

本工具量的是**出厂判据自身的 A/B**，两侧都调 `anchor_adjacency`，零自算口径：
旧档 = `cjk_prose=False`（分叉前的唯一实现，即拉丁档），新档 = `cjk_prose=True`。

    RELAX  旧 False → 新 True   = 分叉**新增放行**，须逐条能解释（见下三桶）
    TIGHT  旧 True  → 新 False  = 闸**变严**，今后这类回填要走 `--confirm-non-adjacent`

RELAX 按目标 display **现有 tag** 分三桶：
    SELFPROOF    目标块已挂的 tag 就等于该号 → **复现账里既成配对**（同一对锚点/公式被旧档
                 判「不挨」、新档判「挨」）——这是本工具的 known_true 通道：🔴 语料正常时它
                 必须**非零**，读到 0 要停下来查工具或语料，不能当「书很干净」（本判据改版前
                 这些配对是人工放行入账的，它们在，就说明向前腿落在真形上）；
    TAGGED_OTHER 目标块挂着别的号 → 新档会把它判成「这个号挨的是已挂别号的式子」，是**线索**
                 不是判据（逐条要印面裁定，工具不替人改账）；
    UNTAGGED     目标块无 tag → 潜在的真漏网回填位点（同样须印面确证后才动账）。

拉丁书侧单列一档：分叉开关若**失效**（把汉字档误套到英文章）会新增放行多少处——这是
「语种开关不可省」的成本证据。2026-10-31 实测：Lehmann《elements-of-large-sample-theory》
里 2026-10-16 已 `deregister_formula_tags.py --mispaired` 摘回的两笔**真错挂**
`(6.5.10)`（锚点块 67 → 倒退落到块 49 的概率表展示式）与 `(3.2.26)`（→ 块 65 的
`I_j` 展示式）正是这一档会放行的形，所以本工具对英文章只报「假想腿」计数、
**出厂路径从不执行它**（`main()` 的 `cjk_prose` 取该章 manifest `language`）。

🔴 2026-10-31 出厂判据基线（供下次读数对照，`--corpus D:/study/book`）：
中文书章 158 ｜ (锚点 × display) 站点 29893 ｜ RELAX **716**
（SELFPROOF 14 / TAGGED_OTHER 12 / UNTAGGED 690）｜ TIGHT **1277**
＝净**更严**。SELFPROOF 14 处 = 数学分析 ch17 D21 (11)(12)(14)、appendixA DA4/DA5/DA6
(1)(2)(3)(4)/DA8 (2)(3)(4)、周民强 appendix 引理3 (4)、数值分析 ch8 定理22 (4.3)。
拉丁书章 622 ｜ 站点 28452 ｜ **假想** RELAX 2223 ｜ TIGHT 2 —— 开关失效一次就等于给
英文书新开 2223 处「锚点倒退认领展示式」，其中含上面两笔已证伪挂；这就是语种开关的价签。

用法：
    python tools/census_adjacency_language_fork.py [--corpus DIR] [--filter 书名子串]
        [--limit N] [--lang cn|en|all] [--show-relax N] [--dump flips.jsonl]
"""
import argparse
import json
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[1])
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot  # noqa: E402
_boot.setup()

from data.book_structure.book_structure import (  # noqa: E402
    list_chapter_keys, prime_chapter_kinds, resolve_chapter_json_path)
import backfill_formula_tags as _bft  # noqa: E402


def books(corpus):
    """语料下的书目录（`<corpus>/*/<book>/_extract/book_structure` 存在者）。"""
    out = []
    for sub in sorted(os.scandir(corpus), key=lambda e: e.name):
        if not sub.is_dir():
            continue
        for bk in sorted(os.scandir(sub.path), key=lambda e: e.name):
            if not bk.is_dir():
                continue
            if os.path.isdir(os.path.join(bk.path, "_extract", "book_structure")):
                out.append(bk.path)
    return out


def chapter_language(ext, ch_key):
    """该章**出厂口径**的正文语种：units 侧 manifest 的 `language`。

    🔴 必须走 `manifest_paths()`（与 `backfill_formula_tags.main()` 喂 `cjk_prose` 时
    同一入口、同一侧序：units 先、units-translate 后），不要自己拼 `units/<stem>/…`：
    分章目录名由 `unit_dir_name` 判（`ch17` / `appendixA` / 无号附录裸 `appendix`），
    手拼会把附录章一律判成「读不到语种」→ 分叉档静默不生效（2026-10-31 实测过这个坑：
    自算路径时 58 本全回 None，普查一度「零翻转」，看着像语料干净）。
    """
    try:
        paths = _bft.manifest_paths(ext, ch_key)
    except _bft.Refuse:
        return None
    try:
        with open(paths[0][1], encoding="utf-8") as fh:
            return json.load(fh).get("language")
    except Exception:
        return None


def _anchors_and_displays(seq):
    """同一内容序列里的 (整块锚点号, display 块下标) 两列。"""
    nums = [(i, _bft.standalone_anchor(seq[i])) for i in range(len(seq))
            if isinstance(seq[i], dict) and _bft.standalone_anchor(seq[i])]
    disp = [i for i in range(len(seq))
            if isinstance(seq[i], dict) and _bft._is_display(seq[i])]
    return nums, disp


def ab_chapter(tree, cjk):
    """该章每个 (锚点号 × display) 站点的两档取值 → [flip 记录]（只记不一致的）。"""
    _tag_dom, sec_of = _bft.contract_tag_domains(tree)
    rows = []
    sites = 0

    def walk(node):
        seq = node.get("sub_sec") or []
        for c in seq:
            if isinstance(c, dict) and c.get("key"):
                walk(c)
        nums, disp = _anchors_and_displays(seq)
        if not nums or not disp:
            return
        ukey = str(node.get("key"))
        own = sec_of.get(ukey)
        for _aidx, num in nums:
            for di in disp:
                blk = seq[di]
                sites = walk.sites + 1
                walk.sites = sites
                old = _bft.anchor_adjacency(tree, blk, num, sec_of=sec_of,
                                            own_dom=own, cjk_prose=False)
                new = _bft.anchor_adjacency(tree, blk, num, sec_of=sec_of,
                                            own_dom=own, cjk_prose=cjk)
                if old[0] == new[0]:
                    continue
                rows.append({"num": num, "display_idx": di,
                             "key": ukey, "tag_on_target": blk.get("tag"),
                             "flip": ("RELAX" if old[0] is False and new[0] is True
                                      else "TIGHT" if old[0] is True and new[0] is False
                                      else "OTHER-%s->%s" % (old[0], new[0])),
                             "note": (new[1] or "")[:200]})
    walk.sites = 0
    walk(tree)
    return rows, walk.sites


def relax_bucket(r):
    t = r["tag_on_target"]
    if str(t) == str(r["num"]):
        return "SELFPROOF"
    return "UNTAGGED" if t in (None, "") else "TAGGED_OTHER"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--corpus", default="D:/study/book")
    ap.add_argument("--filter", default=None, help="只跑目录名含该子串的书")
    ap.add_argument("--limit", type=int, default=0, help="最多跑 N 本（校准用）")
    ap.add_argument("--lang", choices=("cn", "en", "all"), default="all",
                    help="cn=中文书章（出厂会开分叉）/ en=拉丁书章（只量假想腿的成本）")
    ap.add_argument("--show-relax", type=int, default=20,
                    help="打印前 N 条 SELFPROOF RELAX（known_true 通道）")
    ap.add_argument("--dump", default=None, help="逐站点明细写 jsonl（改版前后各 dump 一次再 diff）")
    a = ap.parse_args(argv)

    if not os.path.isdir(a.corpus):
        print("[census_adj] 语料目录不存在：%s" % a.corpus)
        return 2
    paths = books(a.corpus)
    if a.filter:
        paths = [p for p in paths if a.filter in os.path.basename(p)]
    if a.limit:
        paths = paths[:a.limit]

    flips, n_ch = [], {}
    print("[census_adj] 书 %d 本" % len(paths))
    for bp in paths:
        ext = os.path.join(bp, "_extract")
        prime_chapter_kinds(ext)
        rel = bp.replace("\\", "/").split("book/")[-1]
        for key in list_chapter_keys(ext):
            jp = resolve_chapter_json_path(ext, key)
            if not jp or not os.path.isfile(jp):
                continue
            lang = str(chapter_language(ext, key) or "").strip().lower()
            cjk = _bft.cjk_prose_lang(lang)
            side = "cn" if cjk else "en"
            if a.lang != "all" and a.lang != side:
                continue
            try:
                with open(jp, encoding="utf-8") as fh:
                    tree = json.load(fh)
            except Exception as exc:
                print("  [skip] %s %s: %s" % (rel, key, exc))
                continue
            # 中文章：出厂档 = cjk_prose=True；英文章：出厂档 = False，
            # 这里跑 True 只量「开关失效的代价」，出厂从不执行。
            rows, sites = ab_chapter(tree, True)
            st = n_ch.setdefault(side, [0, 0, 0])
            st[0] += 1
            st[1] += sites
            st[2] += len([r for r in rows if r["flip"] == "RELAX"])
            for r in rows:
                r.update(book=rel, ch=key, side=side)
                flips.append(r)

    for side, label in (("cn", "中文书章（出厂开分叉）"),
                        ("en", "拉丁书章（假想腿＝开关失效的代价）")):
        st = n_ch.get(side)
        if not st:
            print("%s：本轮未跑" % label)
            continue
        print("%s：章 %d ｜ 站点 %d ｜ RELAX %d ｜ TIGHT %d"
              % (label, st[0], st[1], st[2],
                 len([r for r in flips if r["side"] == side
                      and r["flip"] == "TIGHT"])))
    cn = [r for r in flips if r["side"] == "cn" and r["flip"] == "RELAX"]
    buck = {}
    for r in cn:
        buck[relax_bucket(r)] = buck.get(relax_bucket(r), 0) + 1
    print("cn RELAX 分桶：" + ", ".join("%s=%d" % kv for kv in sorted(buck.items())))
    sp = [r for r in cn if relax_bucket(r) == "SELFPROOF"]
    print("\nSELFPROOF（known_true：复现账里既成配对，须非零）%d 条：" % len(sp))
    for r in sp[:max(0, a.show_relax)]:
        print("  %-24s %-10s %s (%s) display@%d | %s"
              % (r["book"].split("/")[-1][:24], r["ch"], r["key"], r["num"],
                 r["display_idx"], r["note"][:80]))
    if not sp:
        print("  🔴 零命中：分叉没落在任何已确证配对上 = 先查工具/语料，"
              "不要读成「语料干净」（见模块 docstring 的 known_true 段）")

    if a.dump:
        with open(a.dump, "w", encoding="utf-8") as fh:
            for r in flips:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print("\n明细 %d 条 → %s" % (len(flips), os.path.abspath(a.dump)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
