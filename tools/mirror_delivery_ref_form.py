#!/usr/bin/env python3
"""把交付 md 里**陈旧的回指号形**镜像成契约账本里的号形（收官书禁重 merge 时的正解）。

**为什么需要它**：给一章整体换号形（如 GM 印面页边列是罗马 `(I.12)`，早期笔记把账本/单元写成
阿拉伯 `(1.12)`）时，`tools/` 里没有「只改交付散文回指」的入口：单元侧改写是一次性脚本，交付侧
本应走 :mod:`tools/mirror_unit_line.py`，但那个入口的前提是**整块只差一行**；换号形是一章里几十
处同行差，块永远拿不到唯一偏移 ⇒ 全部拒改，交付就永久停在旧号形（2026-10-31 GM 实测：单元/契约
已全罗马，10 份交付 md 仍写着 `(1.1)`/`(1.12)`/`(2.24)`…，而 gate 与 verify 都不看散文回指，
所以整章全绿隐形）。

**号集不是拍脑袋的正则**：旧形只对「源侧已经写成目标形的号」派生，两处取并集——① 该章契约 tag
账；② 该章**单元正文**里已写成的目标形回指（prose 交叉引用 + `\tag`）。只靠 ① 会漏：GM ch1 的
`(1.1)`/`(1.6)`/`(1.9)` 印面印着、单元写着 `(I.1)`，但那条 display 不是我们笔记里的编号块 ⇒ 不在
账 ⇒ 交付永不清零。源侧没写过的号**永不改**，所以小数、坐标对（`(1.3, 2.4)`：`3` 后面不是 `)`，
形状上就匹配不上）不会被当成回指。旧阿拉伯形有两种历史写法都派生：`"1" × 章序`（把罗马章号当数字
抄：GM 早期 ch2 = `11.24`、ch3 = `111.7`）与 `str(章序)`（`2.24`）；同一旧形撞出两个目标 = 拒。

安全闸（任一不过 = 整条拒）：① dry-run 默认，`--commit` 才落盘；② 每个被改文件先按时间戳备份
（同名不覆盖，留首轮真身）；③ 行数守恒；④ 把两侧**所有** `(任意章号形.N)` 抹掉后必须逐字节相同
（= 只动了回指号；不能用「新→旧反查」，文件里本来就印着新形回指，反查会连它们一起改造出假不还原）；
⑤ 写后逐行 diff，改动行必须全部落在取证清单里。

用法：
    python tools/mirror_delivery_ref_form.py <extract_dir> <ch> [--side cn|en|both]
                                            [--commit] [--book-dir DIR] [--backup-dir DIR]
"""
import argparse
import io
import json
import os
import re
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import lib.boot as boot  # noqa: E402
boot.setup()

from data.book_structure.book_structure import prime_chapter_kinds  # noqa: E402
from lib.unit_markers import is_unit_marker_line  # noqa: E402
sys.path.insert(0, _HERE)
from mirror_unit_line import chapter_md_files  # noqa: E402  （交付 md 命名形的唯一入口，别另算）

_ANY_REF = re.compile(r"\(\s*[0-9IVXLCivxlc]{1,4}\s*\.\s*[0-9]{1,3}\s*\)")
_TAG_INSIDE = re.compile(r"\\tag\s*\{[^{}]*\}")
# 源侧正文里已写成的目标形回指：`(I.12)` 与 `\tag{I.12}` 两种壳
_SRC_PAREN = re.compile(r"\(\s*([IVXLC]{1,4})\s*\.\s*([0-9]{1,3})\s*\)")
_SRC_BRACE = re.compile(r"\\tag\s*\{\s*([IVXLC]{1,4})\s*\.\s*([0-9]{1,3})\s*\}")
_ROMAN = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
          (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")]


def roman(n):
    """1..3999 → 罗马；其余 None。"""
    if not isinstance(n, int) or not 0 < n < 4000:
        return None
    out, v = "", int(n)
    for val, sym in _ROMAN:
        while v >= val:
            out += sym
            v -= val
    return out


def contract_tags(extract_dir, ch):
    """该章契约里全部非空 tag（递归 sub_sec；叶子块 key 为 None 也照收）。"""
    p = os.path.join(extract_dir, "book_structure", "ch%s.json" % ch)
    if not os.path.isfile(p):
        raise SystemExit("[ref-form] 缺契约文件：%s" % p)
    data = json.load(io.open(p, encoding="utf-8"))
    out = set()

    def walk(node):
        if isinstance(node, dict):
            for k in ("tag", "tags"):
                v = node.get(k)
                if v is None:
                    continue
                for t in (v if isinstance(v, list) else [v]):
                    if t is None:
                        continue     # `tags: ["7", null]` 的 null 不是「非空 tag」，别收成 "None"
                    s = str(t).strip()
                    if s:
                        out.add(s)
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    return out


def unit_tags(extract_dir, ch):
    """该章**单元侧**已写成的号（EN+CN 两侧：prose 交叉回指 + `\\tag`）——交付要镜像的真源。

    契约 tag 账只覆盖「带号的那几条 display」；散文交叉回指（GM ch1 引 `(I.1)`、ch3 引
    `(III.56)`，那些 display 不是我们笔记里的编号块）不在账上，但印面印着、单元也确实写成目标形。
    """
    out = set()
    for side in ("units", "units-translate"):
        d = os.path.join(extract_dir, "book_structure", side, "ch%s" % ch)
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if not fn.endswith(".md"):
                continue
            txt = io.open(os.path.join(d, fn), encoding="utf-8").read()
            for rx in (_SRC_PAREN, _SRC_BRACE):
                for m in rx.finditer(txt):
                    out.add("%s.%s" % (m.group(1), m.group(2)))
    return out


def build_map(tags, ch_int):
    """`{旧形正则: 目标串}`，只对「章前缀 = 本章」的号派生（跨章回指交 :func:`merged_map`）。

    目标串**照源侧字面形**回写（`I.12` 就写 `(I.12)`，不把里的空格吞掉）；旧形侧容忍空白。
    """
    head = roman(ch_int)
    if head is None:
        raise SystemExit("[ref-form] 章序 %r 认不出罗马形" % ch_int)
    mp = {}
    for t in tags:
        s = str(t)
        m = re.fullmatch(r"\s*(%s)\s*\.\s*(\d{1,3})\s*" % head, s)
        if not m:
            continue           # 跨章回指（如 ch3 账里引 I.5）不参与本章旧形派生
        dst = "(%s)" % s.strip()
        for arab in ("1" * ch_int, str(ch_int)):
            src = r"\(\s*%s\s*\.\s*%s\s*\)" % (arab, m.group(2))
            if src in mp and mp[src] != dst:
                raise SystemExit("[ref-form] 🔴 ch%s 旧形 %s 在同章内撞两个目标（%s / %s）"
                                 % (ch_int, src, mp[src], dst))
            mp[src] = dst
    return mp


def rewrite(old, mp):
    """→ (新文本, [(行号, 印面旧串, 目标串)])。逐行做 ⇒ 行号天生准确；只判定构造，不写盘。

    `\tag{}` 段先藏起来再换（块号归 dereg / backfill 管），该行真有替换才还原。
    """
    order = sorted(mp, key=len, reverse=True)      # 长形先换，避免前缀吃掉短形
    hits, out_lines = [], []
    for ln, line in enumerate(old.split("\n"), 1):
        stash = []

        def hide(mo):
            stash.append(mo.group(0))
            return "\x00TAG%d\x00" % (len(stash) - 1)

        prot = _TAG_INSIDE.sub(hide, line)
        cur = prot
        for src in order:
            rx = re.compile(src)
            for m in rx.finditer(cur):
                hits.append((ln, m.group(0), mp[src]))
            cur = rx.sub(lambda mo: mp[src], cur)
        if cur != prot:
            cur = re.sub(r"\x00TAG(\d+)\x00", lambda mo: stash[int(mo.group(1))], cur)
            out_lines.append(cur)
        else:
            out_lines.append(line)
    if not hits:
        return old, []
    new = "\n".join(out_lines)
    if len(new.split("\n")) != len(old.split("\n")):
        raise SystemExit("[ref-form] 🔴 行数变了")
    if _ANY_REF.sub("", old) != _ANY_REF.sub("", new):
        raise SystemExit("[ref-form] 🔴 动了回指以外的字节")
    for ln, _o, _d in hits:
        if is_unit_marker_line(out_lines[ln - 1]):
            raise SystemExit("[ref-form] 🔴 回指落在单元 marker 行 L%d" % ln)
    return new, hits


def process(path, mp, commit, backup_dir):
    old = io.open(path, encoding="utf-8", newline="").read()
    new, hits = rewrite(old, mp)
    if not hits:
        return 0, []
    if commit:
        os.makedirs(backup_dir, exist_ok=True)
        dst = os.path.join(backup_dir, os.path.basename(path))
        if not os.path.exists(dst):
            with io.open(dst, "wb") as f:
                f.write(old.encode("utf-8"))
        with io.open(path, "w", encoding="utf-8", newline="") as f:
            f.write(new)
        after = io.open(path, encoding="utf-8", newline="").read()
        if after != new:
            raise SystemExit("[ref-form] 🔴 写后回读不一致：%s" % path)
    return len(hits), hits


def all_contract_chs(extract_dir):
    d = os.path.join(extract_dir, "book_structure")
    out = []
    for fn in sorted(os.listdir(d)):
        m = re.fullmatch(r"ch([0-9]+)\.json", fn)
        if m:
            out.append(m.group(1))
    return out


def merged_map(extract_dir, chs, use_units=True):
    """多章合并的 `旧形正则 → 目标串`（跨章回指是常态：ch2 交付里也写 `(1.12)` 指 I.12）。"""
    mp = {}
    for c in chs:
        tags = set(contract_tags(extract_dir, c))
        if use_units:
            tags |= unit_tags(extract_dir, c)
        for src, dst in build_map(tags, int(c)).items():
            if src in mp and mp[src] != dst:
                raise SystemExit("[ref-form] 🔴 旧形 %s 撞两条目标形（%s / %s）——"
                                 "先人工定谁是对的，别批量改" % (src, mp[src], dst))
            mp[src] = dst
    return mp


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mirror_delivery_ref_form.py")
    ap.add_argument("extract_dir")
    ap.add_argument("ch")
    ap.add_argument("--side", default="both", choices=["cn", "en", "both"])
    ap.add_argument("--from-ch", action="append", dest="from_ch", default=[],
                    help="参与派生旧形的章键（可重复）；默认 = book_structure 里全部 chN.json")
    ap.add_argument("--contract-only", action="store_true", dest="contract_only",
                    help="号集只取契约 tag 账（默认还并上单元正文里已写成的目标形回指）")
    ap.add_argument("--book-dir", default=None)
    ap.add_argument("--backup-dir", default=None)
    ap.add_argument("--commit", action="store_true")
    a = ap.parse_args(argv)

    prime_chapter_kinds(a.extract_dir)
    book = a.book_dir or os.path.dirname(os.path.normpath(a.extract_dir))
    ch_int = int(re.sub(r"[^0-9]", "", str(a.ch)) or 0)
    if not ch_int:
        raise SystemExit("[ref-form] 章键 %r 拿不到章序（字母章不适用本工具）" % a.ch)
    src_chs = a.from_ch or all_contract_chs(a.extract_dir)
    mp = merged_map(a.extract_dir, src_chs, use_units=not a.contract_only)
    if not mp:
        print("[ref-form] %s 号集为空（不写）" % ",".join(src_chs))
        return 0
    langs = {"cn": ["cn"], "en": ["en"], "both": ["en", "cn"]}[a.side]
    mds = [(lg, p) for lg in langs for p in chapter_md_files(book, a.ch, lg)]
    if not mds:
        raise SystemExit("[ref-form] ch%s 语种 %s 没有交付 md（检查章键/书名/是否未拼）"
                         % (a.ch, langs))
    backup_dir = a.backup_dir or os.path.join(
        a.extract_dir, "_bak_delivery_ref_form", time.strftime("%Y%m%dT%H%M%S"))
    total = 0
    for lg, p in mds:
        n, hits = process(p, mp, a.commit, backup_dir)
        total += n
        print("%-3s %-58s %d 处" % (lg, os.path.basename(p), n))
        for ln, src, dst in hits:
            print("      L%-6s %s → %s" % (ln, src, dst))
    print("[ref-form] %s：共 %d 处  备份 %s"
          % ("已写盘" if a.commit else "dry-run", total,
             backup_dir if a.commit and total else "—"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
