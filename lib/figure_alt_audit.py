# -*- coding: utf-8 -*-
r"""lib/figure_alt_audit.py — 图 alt 的**只读取数 + 审计**（门控与回写工具共用同一份取数）。

为什么单独一个 lib 模块：alt 卫生有三个消费者——写手侧装配（`flows/script/embed_figures.py`
→ `build_alt`）、回写工具（`tools/clean_figure_alts.py`）、门控
（`flows/write-source/script/gate_units.py` 章级项）。判据的 SSOT 早就在 `lib.figure_alt`，
但**取数**（本章哪些文件算证人、题注真值怎么读、腿名怎么标）原先只长在工具里：门控若自己
再写一遍，两边的「谁写脏了」就能漂——p1100 的分母对账（unregistered + clean + dirty = 行）
能闭合，靠的正是「探针与 plan 同一套取数」。本模块把取数上提成唯一入口，工具改为从这里
import，门控与工具因此**不可能**给出两个不同的脏集。

审计口径（只有 ① 让门控 FAIL）：
  ① **脏 alt**（`judge` 四档任一：图号碎字 / 号后粘连 / 粘连词 / 二次转义）→ FAIL，处方 = 回写工具；
  ② **未登记的 src**（正文 `<img src>` 末段不在本章 `figure_index`）→ 只报数：那是图改名波
     的账（归 `resync_figure_refs`），alt 侧没有题注真值可判，判了就是猜；
  ③ **非纯编号 / 空 label** 的脏行（unnamed 图、字母号 `F.1`）→ 照常 FAIL，但注明「只能由
     登记腿出厂装配裁决」——门控不复制那套装配判定；
  ④ **登记题注自己就脏** → 只报数：alt 是题注的派生品，题注欠账要回印面取证清（本档
     p1093 的「登记侧脏」桶），门控不许逼写手凭空改字。
🔴 已知失明（照实写在这里，别把本模块当成覆盖-full）：**alt 自己**带词内标点
（`configura.tions` 且与登记题注同形）时，粘连词候选被标点切成短碎片 ⇒ 三档全不报；
这种串只能由印面回检抓到。同理，「体除了标签词什么都不剩」的题注欠账由 `build_alt`
的 A1 档处理，不在本模块判定。
"""
import io
import json
import os
import re
from collections import defaultdict

from lib.figure_alt import RE_PLAIN_LABEL, dirty, img_pairs, judge, why

UNIT_SIDES = ("units", "units-translate")
DELIV = u"D"

# 一条脏 alt 的处方：只指 SSOT 工具，不在这里复述修法（复述=第二套规则）
PRESCRIPTION = (u"跑 `python tools/clean_figure_alts.py <书根目录> <章键> "
                u"--target units --commit`（默认 dry-run，先看旧/新串；两半区加 "
                u"`--side units --side units-translate`）。工具**拒**的行会打印拒因"
                u"（如「本章无可参照的 alt 前缀写法」/「src 未在本章登记」/跨语种）"
                u"⇒ 按拒因回印面取证后手改该行 `alt`，禁止凭空编题注、禁止改散文")


def read_text(path):
    u"""与工具逐字相同的读法：`utf-8-sig` + `newline=""`（BOM 与换行符都不许被改写）。"""
    return io.open(path, encoding="utf-8-sig", newline=u"").read()


def cap_table(ext):
    u"""`文件末段 -> [(章key, label, caption)]`；同名多章时全留，按章筛。"""
    p = os.path.join(ext, "figure_index.json")
    out = defaultdict(list)
    for e in json.loads(read_text(p)):
        f = os.path.basename(e.get("file") or u"")
        if f:
            out[f].append((str(e.get("chapter")).lower(),
                           str(e.get("label") or u""),
                           (e.get("caption") or u"").strip()))
    return out


def chapter_caps(caps, chkey):
    u"""本章登记：文件末段 -> (label, caption)。跨章串名的条目按章 key 滤掉。"""
    out = {}
    for f, lst in (caps or {}).items():
        for (ck, lab, cap) in lst:
            if ck == str(chkey).lower():
                out[f] = (lab, cap)
    return out


def chapter_files(ext, book, chkey):
    u"""本章**全部**可读文件 `[(腿名, 相对名, 绝对路径)]`（参照池与可写面解耦）。

    延迟 import：`data.book_structure` 与 `verify.script` 反过来会 import lib，
    放在模块顶就是环依赖。
    """
    from data.book_structure.book_structure import unit_dir_name
    out = []
    for sd in UNIT_SIDES:
        ud = os.path.join(ext, "book_structure", sd, unit_dir_name(chkey))
        if not os.path.isdir(ud):
            continue
        for fn in sorted(os.listdir(ud)):
            if fn.endswith(".md"):
                out.append((sd, u"%s/%s" % (sd, fn), os.path.join(ud, fn)))
    from verify.script import verify_chapter as VC
    for grp in (VC.chapter_md_groups(book, chkey) or []):
        for g in grp:
            out.append((DELIV, os.path.relpath(g, book).replace("\\", u"/"), g))
    return out


def alt_rows(ext, book, chkey, units_sub=None):
    u"""→ 本章 alt 行清单（dict：leg/rel/path/src/alt/span/label/caption/d/registered）。

    `units_sub` 给定时只返回该侧的行（门控按被门控的那半边报），但**参照腿永远建自
    本章全部文件**——只修一侧时另一侧与交付仍是证人，这与工具的口径必须一致。
    """
    caps = cap_table(ext)
    cc = chapter_caps(caps, chkey)
    files = chapter_files(ext, book, chkey)
    pairs = {}
    for (_leg, _rel, p) in files:
        try:
            pairs[p] = img_pairs(read_text(p))
        except (IOError, OSError):
            pairs[p] = []
    pool = defaultdict(lambda: defaultdict(set))
    for leg, _rel, p in files:
        for f, a, _sp in pairs[p]:
            pool[f][leg].add(a)
    rows = []
    for leg, rel, p in files:
        if units_sub is not None and leg != units_sub:
            continue
        for f, alt, sp in pairs[p]:
            ent = cc.get(f)
            label, cap = ent if ent else (u"", u"")
            legs = [(u"C", cap)]
            for lg in sorted(pool[f]):
                for v in sorted(pool[f][lg]):
                    legs.append((lg, v))
            d = judge(alt, label, legs) if ent is not None else None
            rows.append({"leg": leg, "rel": rel, "path": p, "src": f, "alt": alt,
                         "span": sp, "label": label, "caption": cap, "legs": legs,
                         "registered": ent is not None, "d": d,
                         "plain": bool(RE_PLAIN_LABEL.match(label or u""))})
    return rows


def chapter_alt_problems(ext, chkey, units_sub=u"units", book=None, only_unit=None):
    u"""→ `(problems, note)`：门控用的章级 alt 卫生审计。

    `problems` 只收 ① 脏 alt（附腿名/文件/图号/脏形与 `PRESCRIPTION`）；其余四桶进
    `note`（**永远打印**，含全 0 时的「无 img 行」），这样「量不到」不会变成「没报」。
    无 `figure_index.json`（知识库输入的书）⇒ `problems` 空、note 说明未启用。
    `only_unit`：只看该文件名（写手**逐单元自检**用，判据一字不动）。alt 是逐单元属性，
    自检不跑它 ⇒ 写手按自检翻 DONE、章门控再把同一文件打回，白多一轮返工。参照腿仍建自
    本章全部文件：只报这一行，但证人还是别的腿。
    """
    book = book or os.path.dirname(os.path.abspath(ext))
    idx = os.path.join(ext, "figure_index.json")
    if not os.path.isfile(idx):
        return [], u"alt 审计未启用（无 figure_index.json，题注真值不存在）"
    try:
        rows = alt_rows(ext, book, chkey, units_sub)
    except Exception as exc:                              # 取数坏 != 内容脏
        return [], u"alt 审计读不到（%s: %s）" % (type(exc).__name__, exc)
    if only_unit:
        rows = [r for r in rows if os.path.basename(r["rel"]) == only_unit]
    dirty_rows = [r for r in rows if r["registered"] and dirty(r["d"])]
    unreg = [r for r in rows if not r["registered"]]
    nonplain = [r for r in dirty_rows if not r["plain"]]
    capdirty = [r for r in dirty_rows
                if dirty(judge(r["caption"], r["label"], [(u"alt", r["alt"])]))]
    problems = []
    for r in dirty_rows[:8]:
        problems.append(
            u"图 alt 卫生：%s 的 `%s`（图 %s）%s" % (
                r["rel"], r["src"], r["label"] or u"(未登记)", why(r["d"])))
        if not r["plain"]:
            problems[-1] += (u"　｜该图号非纯编号形，修法只能走**登记腿出厂装配**"
                             u"（工具的那一档会照 `build_alt` 产物落，别自己拼）")
    if problems:
        # 处方按**章**给一次，不按行复读：8 行 × 200 字的同一句话会把别处的真 FAIL 挤出视野
        problems.append(u"　→ " + PRESCRIPTION)
    if len(dirty_rows) > 8:
        problems.append(u"图 alt 卫生：另有 %d 行同判据脏（--list 全列）"
                        % (len(dirty_rows) - 8))
    note = u"alt 审计：行 %d ｜ 脏 %d ｜ 非纯编号 %d ｜ 登记题注同脏 %d ｜ 未登记 src %d" % (
        len(rows), len(dirty_rows), len(nonplain), len(capdirty), len(unreg))
    if unreg:
        note += u"（未登记图名：%s；那是图改名波的账，归 resync_figure_refs）" % u"、".join(
            sorted(set(r["src"] for r in unreg))[:4])
    if capdirty:
        note += u"　🔴 登记题注自己脏的 %d 行别在 alt 侧改字——题注欠账按印面取证清" % len(capdirty)
    if not rows:
        note = u"alt 审计：本章无 img 行"
    return problems, note
