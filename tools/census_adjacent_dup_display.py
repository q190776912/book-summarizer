r"""census_adjacent_dup_display.py — 跨书普查「同一条 display 在交付里就近连印两遍」。

起因（2026-10-31，遍历论_孙文祥 ch6 两处）：印面把「条目标号 + 式子」印在**同一行**
（`引理 6.6.2  lim (1/n)r(P(n))=0.` / `推论 6.4.1  h(T)=sup h_μ(T).`），收割期却切成
**两个契约节点**——一个 `description`（只持那一行的公式块）+ 紧邻的编号项（持同句碎片或
只在 `name` 里留题面）。两个节点各成一个单元 → merge 后同一条式子在交付里印两遍，
写手还会为那条「孤格式」补一句印面并不存在的桥接散文（D18 实测：「推论6.4.1 的结论为」= 臆造）。
交付侧的机械指纹 = **同一归一内核、近距离、中间只剩脚手架**。

两档口径（🔴 只有第二档可点名，第一档只作背景量）：
  档一 `GAP`：同内核两次出现行距 ≤ `--gap`（默认 20）。跨 58 书实测 **105 条**，逐条读下来
       多数是**合法复述**（定理在证明末尾再写一遍、推导链里同一式子隔几句出现）——
       所以「近距离」本身不是判据，把它做成闸门会把正确交付判违规（同 `merge_units` 手修
       不能与单元逐字对齐那条死规则同理）。
  档二 `SHAPE`：两份之间**只有**空行 / `---` / `#` 标题 / 粗体条头（`**xxx**：`），
       即「一条无主式子」紧跟着「同一条式子作为某条目的题面」。跨 58 书基线见 SKILL.md。

🔴 本工具**只报不拦**（exit 恒 0）：它是交付侧症状探测器，真修在**收割处**
（`attach_content` / `lib.numbering`：公式与条目号同一行时须归同一节点，不得另起
description）。收官书的交付禁重 merge，故本工具的输出是「逐处印面取证 → 四本账定点手术」的
工单来源，不是批量豁免清单。

known_true 控件（`--control <md 路径>`，零命中不可信）：把**手术前**的交付备份件
（`_extract/_bak_d23_dedup/*/第6章_变分原理.md`、`_bak_d18_dedup/*`）喂进来，SHAPE 档
必须点名同一处；控件抓不到 = 判据失明，报告里的其余「0 命中」不算证据。
两份快照的预期不同（快照有先后）：D23 那份点名 **2 处**（当时 D18 还没修），D18 那份只点名
**1 处**（D23 已修好，不得再报）—— 同时验证「抓得到」和「已修的不再抓」。

回归：`tools/tests/test_census_adjacent_dup_display.py`（负向锁死「中间有一句散文 ⇒ 只落
GAP 不落 SHAPE」「前后任一份带 `>` ⇒ 不配」「多行块的配对基准是结束行」；改 `_FILLER`
或配对口径必须先跑该测试，其 quoted 用例在 2026-10-31 收窄前是实测失败的）。

归一内核走 `census_unit_delivery_coverage` 自己的 `block_core()`（同一函数 = 同一口径），
语料遍历走 `_book_dirs()`（出厂入口，不自算等价口径）。

用法：
    python tools/census_adjacent_dup_display.py <corpus_root|book_dir>
        [--book 子串] [--gap 20] [--control <交付 md 路径>] [--top 40]
"""
import argparse
import io
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib"), os.path.join(_ROOT, "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from census_unit_delivery_coverage import DISPLAY_RE, _book_dirs, block_core

MIN_CORE = 8          # 短内核（`x` / `=0`）没有判别力，不参与配对
# 两份之间允许的内容：空行 / 水平线 / ATX 标题 / 粗体条头（与 2026-10-31 标定逐字同形，
# 收窄/放宽都要重跑 --control 控件与全语料基线）
_FILLER = re.compile(r"^(?:\s*$|-+|#{1,6}\s.*|\*\*[^*]+\*\*[:：]?\s*)$")


def only_scaffold(text_between):
    lines = [l for l in text_between.split("\n")]
    return bool(lines) and all(_FILLER.match(l) for l in lines)


def scan_text(text, label=u"", gap=20):
    """一章交付 → [(文件, 前一行, 后一行, 间距, 内核, 档位)]；档位含 GAP / SHAPE。

    配对口径（与 2026-10-31 标定普查逐字一致，改动须重跑 --control 控件）：
    · **两份都必须不在证明围栏里**（行首不带 `>`）：正文印一遍、紧跟着 `> **证明**：` 里再写
      一遍是合法的。围栏只挡「块自身的开行」，两块之间只剩空行时前一份的 `>` 不会进
      `only_scaffold` 窗口，所以后一份也得单独判 —— 收窄后跨 58 书基线**一条没变**
      （6 条 / 2 本，实测后一份 quoted 的 SHAPE 站点为 0），属纯假阳防护；
    · 前一份同样跳过 quoted 的（它不配当「上一份正文」）；
    · GAP 档只管行距，SHAPE 档管「中间只剩脚手架」，两者可叠。
    """
    lines = text.replace("\r\n", "\n").split("\n")
    out = []
    seen = defaultdict(list)                    # core -> [(start_ln, end_ln, in_quote)]
    for m in DISPLAY_RE.finditer(text):
        core = block_core(m.group(0))
        if len(core) < MIN_CORE:
            continue
        ln = text.count("\n", 0, m.start()) + 1
        in_quote = lines[ln - 1].lstrip().startswith(">")
        end_ln = ln + m.group(0).count("\n")
        prev = [p for p in seen[core] if not p[2]]
        seen[core].append((ln, end_ln, in_quote))
        if not prev or in_quote:
            continue
        p_ln, p_end, _ = prev[-1]
        d = ln - p_ln
        legs = []
        if d <= gap:
            legs.append(u"GAP")
        if only_scaffold(u"\n".join(lines[p_end:ln - 1])):
            legs.append(u"SHAPE")
        if legs:
            out.append((label, p_ln, ln, d, core, legs))
    return out


def scan_book(book_dir, gap=20):
    hits = []
    for md in sorted(Path(book_dir).glob("*.md")):
        try:
            txt = io.open(str(md), encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        hits.extend(scan_text(txt, md.name, gap))
    return hits


def main():
    ap = argparse.ArgumentParser(description="交付内「同一条 display 就近连印两遍」普查（只读报告）")
    ap.add_argument("root", help="corpus_root 或单本书目录")
    ap.add_argument("--book", default="", help="只跑书名含该子串的书")
    ap.add_argument("--gap", type=int, default=20, help="档一（GAP）的行距上限")
    ap.add_argument("--control", default="", help="known_true 控件：手术前交付备份件路径")
    ap.add_argument("--top", type=int, default=40)
    args = ap.parse_args()

    books = [b for b in _book_dirs(args.root) if not args.book or args.book in str(b)]
    n_gap = n_shape = 0
    shape_rows = []
    for b in books:
        bh = scan_book(str(b), args.gap)
        sh = [h for h in bh if u"SHAPE" in h[5]]
        n_gap += len([h for h in bh if u"GAP" in h[5]])
        n_shape += len(sh)
        if sh:
            shape_rows.append((str(b), sh))
    print("书数 %d ｜ 档一 GAP<=%d 行：%d 条（合法复述占多数，不可当闸门）"
          " ｜ 档二 SHAPE：%d 条 / %d 本" % (len(books), args.gap, n_gap, n_shape, len(shape_rows)))
    printed = 0
    for b, sh in shape_rows:
        print("\n== %s (%d)" % (os.path.basename(b), len(sh)))
        for label, l1, l2, gap, core, legs in sh:
            if printed >= args.top:
                break
            print("   %s L%d→L%d (gap %d) [%s]  %s" % (label, l1, l2, gap, u"+".join(legs), core[:72]))
            printed += 1
    if args.control:
        ctl = io.open(args.control, encoding="utf-8", errors="replace").read()
        ch = [h for h in scan_text(ctl, os.path.basename(args.control)) if h[5]]
        print("\nknown_true 控件 %s：SHAPE 点名 %d 条" % (args.control, len(ch)))
        for label, l1, l2, gap, core, legs in ch:
            print("   %s L%d→L%d (gap %d) [%s]  %s" % (label, l1, l2, gap, u"+".join(legs), core[:72]))
        if not ch:
            print("   🔴 控件零命中 = 判据失明；本报告其余的「0 命中」不可当证据。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
