#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""resync_figure_refs.py — 把单元正文 / manifest.images / 契约 image 三处的图名对齐到 figure_index 的真名。

**为什么需要它**（2026-10-31 全架普查实测，见 `_scratch/.../p1062_dead_img_census.py`）：
图号指派波（`flows/script/assign_figures.py` 把 `chNN_unnamed_K.png` 改名成
`chNN_figX.X.png` 并回写 `figure_index.json`）只更新了**交付 md**，没回写契约
`book_structure/chN.json` 的 `{"image": …}`、单元清单 `manifest.json` 的 `images`、
以及单元正文里的 `<img src>`。三处停留在旧名 ⇒
  · gate ③b 拿单元正文对 `manifest.images`：**同为旧名 ⇒ 自洽通过**（全架 58 本里
    mathematical-statistics-and-data-analysis 实测 200 条引用指向盘上不存在的文件，门控仍 PASS）；
  · verify E 层只看交付 md 对 figure_index：新名 ⇒ 绿；
  · 只有「重拼 == 交付」普查把两侧放上同一张桌，才量出每章 `-N +N` 的 src 行。
所以这不是形制差，是**单元层不再是可信源**：一旦有人重 merge，图全断。

**真值取哪一侧**：`figure_index.json`（章 + 图号 → 文件），且文件必须真在 `figure/` 下。
定位锚 = 单元 `<img>` 的 `alt` 里的图号（写手按印面 caption 写的）。该锚的正当性由
**交付自身标定**：MSDA 双语交付 302 条 img 行里，alt 带号的 292 条**全部**满足
「alt 号 == figure_index 号 == 文件名内嵌号」，零反例 ⇒ alt 号是语义身份，与顺序无关
（位置锚不可用：同书按位自证就有 18 处活链错位，ch10 单元 18 张 vs 交付 17 张）。
顺带修掉的不止死链：alt=11.4 而 src=`ch11_fig11.3.png` 这类**原名在盘的真错嵌**也一并改对。

改哪三处（①②成对，缺一即半写；③尽力回写）：
  ① 单元正文 `<img … src="figure/旧">` —— 只换 `src` 的值，`alt`/`width` 逐字节不动；
  ② 该单元 manifest 记录的 `images` 数组 —— 按 `file` 定位记录后**定点替换旧名**，
     不重 dump JSON（守恒缩进/换行符/键序）；
  ③ 该章契约 `chN.json` 的 `{"image": "figure/旧"}` —— 量不到**不拦**①②：要修的真值是
     **交付 md**，契约旧名不影响「重拼 == 交付」（E 层拿 figure_index 对交付，本就绿）。

**所有替换按字符区间一次并行落**（`splice`）：串行 find/replace 在两处坏得一样明显 ——
同文件两条**互换**旧名时先命中刚写进去的那条（MSDA ch3 `3.9↔3.10` 首轮实测：计数报改了、
磁盘留着互换态），以及新名长度不同会让后续锚失效（manifest 多记录同病）。

安全闸（任一不过 = 该条跳过并列账，绝不猜）：
  · dry-run 默认，`--commit` 才落盘；每个被改文件先按时间戳备份到
    `_extract/_bak_resync_figure_refs/<stamp>/`（同名不覆盖）；
  · alt 无号 / 号在本章 index 无档且交付 alt 也量不到 / 一号多文件且交付 alt 不消歧 ⇒ 只报告；
  · manifest 里该单元无记录、或旧名在同记录出现多次（无法定位哪条对应本 img）⇒ **整条不改**；
  · 行数守恒；改动行必须全部含 `<img`；
  · 唯一允许的**删除**是 `figure_pins.json` 里写明 `"drop": true` 的人工裁定（印面只有一张、
    单元连挂两遍）：删正文整行 + manifest 同序号那格 + 契约同序号那个单键 image 块，
    `content` 同步减 1；三处任一验不过（数组与正文不同序 / 不是整行 / 块非单键 / 改后 JSON
    不合法）⇒ 整条不落，绝不只删一处。
  · 写后自证：逐侧比较「单元图多重集 == 同语种交付图多重集」，差集直接印出。

**契约独占对账**（单元侧零活也要看得见，MSDA ch3/ch11 实测形态）：改名波有时只回写到
单元/manifest/交付，**契约单独停在旧名** ⇒ 同一文件挂两槽、真名零槽，gate ③b 一次报两条红
（「单元嵌契约外图 X」+「契约重复引用 Y（2 块）」）。老版本一见 `jobs` 空就 `continue`，
契约腿根本跑不到 ⇒ 这类账工具全瞎。现在放行须同时满足 `contract_only_repair` 的五条：
1:1 文档序、两侧「正文==manifest」多重集同向、`seq_repair(ordered=True)` 唯一升序裁定、
新名在 figure_index 本章登记且盘上活着、旧名在契约挂 ≥2 处。升序即印面定序（每个图块紧跟
自己的题注），改错槽立刻破坏单调 ⇒ 歧义自动拒。

单元正文变 ⇒ 源侧哈希快照漂移，收官书按 :mod:`tools.resync_src_hash` 补（本工具不碰哈希）。

用法：
    python tools/resync_figure_refs.py <book_dir> <ch> [ch…] [--side units|units-translate|both]
                                       [--commit] [--list]
"""
import argparse
import io
from collections import Counter
import json
import os
import re
import shutil
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import lib.boot as boot  # noqa: E402
boot.setup()

from data.book_structure.book_structure import (  # noqa: E402
    prime_chapter_kinds, reset_chapter_kinds, unit_dir_name,
    resolve_chapter_json_path)

RE_IMG = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)("[^>]*?>)', re.I)
RE_ALT = re.compile(r'\balt="([^"]*)"', re.I)
SIDES = ("units", "units-translate")
# rows/unit_seq 的目标序里，被 `drop` 裁定删掉的那一格用这个哨兵标记（不是文件名，
# 不可能与真名相撞）：`corrected_order` 把它滤掉，契约腿按位置删块。
DROP = u"\x00DROP\x00"


def _read(path):
    return io.open(path, encoding="utf-8-sig", newline="").read()


def _write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def splice(raw, edits):
    """`edits = [(start, end, text)]` 一次并行落（按起点降序切）。

    为什么必须并行：串行「find 再 replace」在**同文件两条互换旧名**时会命中刚写进去
    的那条，计数说改了、实际留着互换态（MSDA ch3 `3.9↔3.10` 首轮实测）；长度变化也会
    让后续锚失效（manifest/契约同病）。
    """
    out = raw
    for s, e, t in sorted(edits, key=lambda x: x[0], reverse=True):
        out = out[:s] + t + out[e:]
    return out


def name_hits(seg, name):
    """seg 里 `name` 作为**完整路径末段**出现的位置（前面是 `"` 或 `/`，后面紧跟 `"`）。"""
    return [m.start() for m in re.finditer(
        r'(?<=["/])%s(?=")' % re.escape(name), seg)]


def index_table(ext):
    """`(章key, 图号) -> {文件名}`，只收 `figure/` 下真实存在的文件。"""
    p = os.path.join(ext, "figure_index.json")
    if not os.path.isfile(p):
        raise SystemExit("[resync_figure_refs] 缺 figure_index.json：%s（无真值可依据）" % p)
    tab = {}
    for e in json.loads(_read(p)):
        f = os.path.basename(e.get("file") or "")
        lab = e.get("label")
        if not f or lab is None:
            continue
        tab.setdefault((str(e.get("chapter")), str(lab)), set()).add(f)
    return tab


def alt_labels(alt, chkey):
    """alt 里属于本章的图号串（`14.6` / `10.11A`；字母章 `B.3`），保持出现序。

    🔴 前缀必须允许**多位数字**：`([0-9A-Za-z])\\.` 会在「14.6」上从 `4` 起匹配，
    量出 `4.6` ≠ 章 key `14` ⇒ 整章图名一条都改不动（两位数章全瞎）。
    """
    out = []
    for m in re.finditer(r"(\d{1,3}|[A-Za-z])\.(\d{1,3}(?:\.\d+)?)([A-Za-z])?",
                         alt or ""):
        pre, num, suf = m.group(1), m.group(2), m.group(3) or ""
        if str(pre).lower() != str(chkey).lower():
            continue
        out.append("%s.%s%s" % (pre, num, suf))
        out.append("%s.%s" % (pre, num))       # 尾字母常被并入下一词（10.5A）
    return out


def _norm_alt(s):
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def delivery_alt_map(book, chkey):
    """`(章, 归一 alt) -> {交付实际嵌的、盘上存在的文件}`（en+cn 两组并集）。

    为什么需要第四通道：`figure_index` 一个 label 可以对应**多个**文件（多联图重裁后
    留 `chNN_figX.Y.png` 与 `chNN_figX.Y_2.png`，MSDA ch3 的 3.10 / ch2 的 2.1 实测），
    也有 alt 根本不写图号（ch14 D2 四张纯描述性题注、ch10 `fig0.25`）——这时图号锚量不到，
    而**交付 alt 与单元 alt 同源**（都抄印面 caption），按 alt 全等即可唯一落到交付用的那张。
    该通道的正当性同 E1 一样由交付标定（302 条 img 行里 alt 号==index 号==文件名内嵌号
    292/292，零反例）。
    """
    out = {}
    try:
        from verify.script import verify_chapter as VC
    except Exception:
        return out
    for grp in (VC.chapter_md_groups(book, chkey) or []):
        txt = (_read(grp[0]) if len(grp) == 1 else VC._merge_section_files(grp))
        for m in RE_IMG.finditer(txt):
            f = os.path.basename(m.group(2))
            if not os.path.isfile(os.path.join(book, "figure", f)):
                continue
            am = RE_ALT.search(m.group(0))
            if am:
                out.setdefault(_norm_alt(am.group(1)), set()).add(f)
    return out


def resolve_target(book, tab, chkey, alt, delmap=None):
    """返回 (目标文件名 或 None, 原因)。图号锚优先；歧义/无号时按交付同 alt 消歧。"""
    na = _norm_alt(alt)
    seen = set()
    for lab in alt_labels(alt, chkey):
        for f in tab.get((chkey, lab), ()):
            if os.path.isfile(os.path.join(book, "figure", f)):
                seen.add(f)
    by_alt = {f for f in (delmap or {}).get(na, ())
              if os.path.isfile(os.path.join(book, "figure", f))}
    if len(seen) == 1 and (not by_alt or by_alt == seen):
        return seen.pop(), ""
    if len(seen) > 1:
        if len(by_alt) == 1:
            return by_alt.pop(), ""          # 同号多档 → 交付 alt 消歧
        return None, "一号多指:%s" % "|".join(sorted(seen))
    if not seen:
        if len(by_alt) == 1:
            return by_alt.pop(), ""          # alt 无号 → 交付 alt 直连
        if len(by_alt) > 1:
            return None, "同alt多指:%s" % "|".join(sorted(by_alt))
        return None, ("alt无号" if not alt_labels(alt, chkey) else "号在index无活档")
    return None, "图号与交付alt冲突"


def load_pins(book, ext, chkey):
    u"""人工裁定档 `<ext>/figure_pins.json`：锚量不到的行由**人**写死映射，工具只负责安全落。

    为什么需要它：图号锚（alt 里的号）和交付 alt 直连两条锚都会「量不到」——写手把题注
    意译了（MSDA ch14 `unnamed_01` alt「peak area versus percentage of dye」对印面
    「…sulfanilic acid peak area to percentage of FD&C Yellow」），或者 src 活着但嵌错
    （ch14 0010 把 Figure 14.7 那张也写成 `ch14_fig14.6_2.png`）。这两种机械判据都猜不得，
    只能由印面裁定后登记。条目：
        {"chapter":"14","file":"0010_desc_D5.md","old":"ch14_fig14.6_2.png",
         "new":"ch14_fig14.7.png","occurrence":2,
         "alt":"Figure 14.7 Residuals from the regression of flow rate on depth.",
         "why":"印面 p552 FIGURE 14.7；正文 37 行回指 (Figure 14.7)，width 47.0% 与 index 同"}
    · `new` 必须真在 `figure/` 下，否则整批拒（写错名 = 造新死链）；
    · `occurrence` = 旧名在该单元里第几次出现（1 起）；旧名出现多次而没写 ⇒ 拒（不猜）；
    · `alt` 只改同一行的 alt 值（照印面补号/修碎字），不碰 src 以外的其它属性；
    · `"drop": true`（不写 `new`）= **印面只有一张、单元连挂了两遍**的人工裁定：删该 occurrence
      那一整行 `<img>`，并同步删 manifest 数组里同序号那一格、契约里同文档序的那个 image 块，
      并把该记录的 `content` 减 1（契约节点少了一个内容块）。必须写 `occurrence`，
      且旧名在该单元须真的出现 ≥2 次；该 img 必须是整行（同行还有别的内容 ⇒ 拒）。
      来源形态：图改名/去重波只回写了交付，单元留着多写的那一遍（MSDA ch10 0027
      Figure 10.11 两遍 66.1%/41.2%，交付只留 66.1%）。
    """
    p = os.path.join(ext, "figure_pins.json")
    if not os.path.isfile(p):
        return []
    out = []
    for n, e in enumerate(json.loads(_read(p))):
        if str(e.get("chapter")) != str(chkey):
            continue
        miss = [k for k in ("file", "old") if not e.get(k)]
        if e.get("drop"):
            if e.get("new"):
                raise SystemExit(u"[resync_figure_refs] figure_pins.json 第 %d 条 "
                                 u"drop 与 new 不能并存（去重没有新名）" % (n + 1))
            if not e.get("occurrence"):
                raise SystemExit(u"[resync_figure_refs] figure_pins.json 第 %d 条 "
                                 u"drop 未写 occurrence（删哪一遍不许猜）" % (n + 1))
        elif not e.get("new"):
            miss.append("new")
        if miss:
            raise SystemExit(u"[resync_figure_refs] figure_pins.json 第 %d 条缺 %s" % (n + 1, miss))
        if not e.get("drop"):
            f = os.path.basename(str(e["new"]))
            if not os.path.isfile(os.path.join(book, "figure", f)):
                raise SystemExit(u"[resync_figure_refs] figure_pins.json 第 %d 条 new=%s 盘上无"
                                 u"（会造出新死链，拒）" % (n + 1, e["new"]))
        out.append(e)
    return out


def pin_for(pins, side, fname, cur, occ, tot):
    u"""→ (pin 或 None, 拒因或 None)。按 (file, old) 选，再用 side/occurrence 收窄。"""
    cand = [p for p in pins if p["file"] == fname and p["old"] == cur
            and (p.get("side") is None or p.get("side") == side)]
    if not cand:
        return None, None
    if len(cand) > 1:
        return None, u"pin 多条同键（%d 条）" % len(cand)
    p = cand[0]
    want_occ = p.get("occurrence")
    if want_occ is None:
        if tot > 1:
            return None, u"pin 未定 occurrence 而旧名出现 %d 次" % tot
        return p, None
    if int(want_occ) != occ:
        return None, None
    return p, None


def row_span(raw, fname):
    """manifest 里 `file: fname` 那条记录的 `{…}` 起止（与 p1060 同法，不重 dump）。"""
    i = raw.find('"%s"' % fname)
    if i < 0:
        return None
    s = raw.rfind("{", 0, i)
    depth = 0
    for j in range(s, len(raw)):
        if raw[j] == "{":
            depth += 1
        elif raw[j] == "}":
            depth -= 1
            if depth == 0:
                return (s, j)
    return None


def plan_chapter(book, ext, chkey, sides):
    """→ (jobs, skipped, rows, altjobs, drops)：jobs = [(side, file, old, new, span, rank)]，按单元序。

    🔴 span = 该条 `src="…"` **值**在文件里的字符区间；rank = 该条在本单元 img 序列里的
    序号（0 起）。改名必须按位置一次性落，不能「拿旧名字符串再 find 一次」：同文件里两张
    图**互换**名字时（MSDA ch3 的 3.9↔3.10、ch11 的 11.3↔11.4），串行 find 会先命中刚写
    进去的那条，量出「已改名」却把两行留在互换态（首轮实测即如此，重跑才暴露）。

    rows = {(side, file): [(现名, 目标名或 None), …]}，按文档序 —— 通道 M/C 靠它重建
    manifest 数组与契约引用（首轮串行写把两处都写成了「同名两遍、另一个零遍」）。

    altjobs = {(side, file): [(start, end, 新 alt, 原 alt), …]}：印面题注回补（只动 alt 值）。
    drops = {(side, file): [(img 文档序 rank, 名, 行起, 行止)]}：`drop` 裁定的整行删除。
    """
    tab = index_table(ext)
    delmap = delivery_alt_map(book, chkey)
    pins = load_pins(book, ext, chkey)
    jobs, skipped = [], []
    rows = {}
    altjobs = {}
    drops = {}
    for side in sides:
        udir = os.path.join(ext, "book_structure", side, unit_dir_name(chkey))
        mp = os.path.join(udir, "manifest.json")
        if not os.path.isfile(mp):
            continue
        man = json.loads(_read(mp))
        for r in man.get("units") or []:
            up = os.path.join(udir, r.get("file") or "")
            if not os.path.isfile(up):
                continue
            uraw = _read(up)
            ms = list(RE_IMG.finditer(uraw))
            tot = Counter(os.path.basename(m.group(2)) for m in ms)
            seq = []
            occ = Counter()
            for rank, m in enumerate(ms):
                cur = os.path.basename(m.group(2))
                occ[cur] += 1
                am = RE_ALT.search(m.group(0))
                alt = am.group(1) if am else ""
                pin, pwhy = pin_for(pins, side, r.get("file"), cur, occ[cur], tot[cur])
                if pwhy:
                    skipped.append((side, r.get("file"), cur, u"pin 拒：" + pwhy, alt[:60]))
                    seq.append((cur, None))
                    continue
                if pin is not None and pin.get("drop"):
                    if tot[cur] < 2:
                        skipped.append((side, r.get("file"), cur,
                                        u"drop 拒：旧名在该单元只出现 1 次", alt[:60]))
                        seq.append((cur, None))
                        continue
                    ls = uraw.rfind("\n", 0, m.start()) + 1
                    le = uraw.find("\n", m.end())
                    tail = len(uraw) if le < 0 else le + 1
                    if uraw[ls:m.start()].strip() or uraw[m.end():le if le >= 0 else len(uraw)].strip():
                        skipped.append((side, r.get("file"), cur,
                                        u"drop 拒：img 不是整行（同行还有别的内容）", alt[:60]))
                        seq.append((cur, None))
                        continue
                    drops.setdefault((side, r["file"]), []).append((rank, cur, ls, tail))
                    seq.append((cur, DROP))
                    continue
                if pin is not None:
                    new = os.path.basename(str(pin["new"]))
                    # 🔴 题注已等于 pin ⇒ 不产生 job：否则「已落位」的 pin 每轮都以 ALT 行
                    #    重现（dry-run 看着像还有活），且 --commit 会写一次净零改动。
                    alt_changed = bool(pin.get("alt")) and am is not None \
                        and str(pin["alt"]) != alt
                    if alt_changed:
                        altjobs.setdefault((side, r["file"]), []).append(
                            (m.start() + am.start(1), m.start() + am.end(1),
                             str(pin["alt"]), alt))
                    seq.append((cur, new))
                    if new != cur:
                        jobs.append((side, r["file"], cur, new, m.span(2), rank))
                    elif not alt_changed:
                        skipped.append((side, r.get("file"), cur,
                                        u"pin 与现状一致（无需改）", alt[:60]))
                    continue
                new, why = resolve_target(book, tab, chkey, alt, delmap)
                seq.append((cur, new))
                if new is None:
                    skipped.append((side, r.get("file"), cur,
                                    (why or "?") + ("" if os.path.isfile(
                                        os.path.join(book, "figure", cur)) else u"[死链]"),
                                    alt[:60]))
                    continue
                if new != cur:
                    jobs.append((side, r["file"], cur, new, m.span(2), rank))
            rows[(side, r["file"])] = seq
    return jobs, skipped, rows, altjobs, drops


def corrected_order(seq):
    """该单元改名落位后的 src 末段序（未解析的保持现名；`drop` 的那一格整条消失）。"""
    return [t if (t and t != DROP) else c for c, t in seq if t != DROP]


def arr_slots(seg):
    """记录文本里 `"images": [ … ]` 每一项 → (段内偏移, 值)。数组顺序不是载荷（闸按 set 比）。"""
    i = seg.find('"images"')
    if i < 0:
        return []
    j, k = seg.find("[", i), seg.find("]", i)
    if j < 0 or k < j:
        return []
    inner = seg[j + 1:k]
    return [(j + 1 + m.start(1), m.group(1)) for m in re.finditer(r'"([^"]*)"', inner)]


def del_slot_edit(raw, rsp, slots, i):
    """删 `images` 数组第 i 格 → (start, end, "")：连引号、分隔逗号与换行缩进一起删，
    剩下的仍是合法 JSON（调用方 `json.loads` 复验）。数组只剩一格时留空数组。"""
    off, v = slots[i]
    s = rsp[0] + off - 1                       # 开引号
    e = rsp[0] + off + len(v) + 1              # 闭引号之后
    if len(slots) == 1:
        return (s, e, u"")
    if i < len(slots) - 1:
        return (s, rsp[0] + slots[i + 1][0] - 1, u"")
    return (rsp[0] + slots[i - 1][0] + len(slots[i - 1][1]) + 1, e, u"")


RE_IMG_BLOCK = re.compile(r'^\s*"image"\s*:\s*"[^"]*"\s*$')


def content_dec_edit(raw, rsp, n):
    """契约节点少了 n 个内容块 ⇒ 该记录 `content` 同步减 n（没这字段/数不够减 ⇒ 不动）。"""
    seg = raw[rsp[0]:rsp[1] + 1]
    m = re.search(r'"content"\s*:\s*(\d+)', seg)
    if not m or int(m.group(1)) < n:
        return None
    return (rsp[0] + m.start(1), rsp[0] + m.end(1), str(int(m.group(1)) - n))


def del_block_edit(raw, val_start, val_end):
    """从 `"image"` 的值区间扩到包住它的块，整块删掉 → (start, end, "") 或 None。

    只认**单键** `{"image": "…"}` 块：块里还挂着别的键就删不掉（那是要人工拆的结构手术，
    不是本工具的量级），宁可不写。
    """
    s = raw.rfind("{", 0, val_start)
    e = raw.find("}", val_end)
    if s < 0 or e < 0 or not RE_IMG_BLOCK.match(raw[s + 1:e]):
        return None
    ls = raw.rfind("\n", 0, s)
    if ls >= 0 and not raw[ls + 1:s].strip():
        s = ls + 1                             # 块独占一行 ⇒ 连缩进一起删
    if raw[e + 1:e + 2] == ",":
        return (s, e + 2, u"")
    c = raw.rfind(",", 0, s)
    return None if c < 0 else (c, e + 1, u"")


def seq_repair(actual, expect, ordered=False):
    """actual 被上一轮串行写写成「同名两遍 / 另一个零遍」时的**唯一机械修法**。

    → ([(槽位, 新名)], 原因或 "")。条件全机械：
      · 长度相同、且多/缺各恰好一处（超出即拒——不修自己没弄坏的账）；
      · `ordered=True`（契约用，节点顺序是载荷：merge/定序闸读它）还要求改完按 expect
        文档序单调，实测 ch11 的 11.4 两槽只有**前一槽**改成 11.3 才升序，歧义即拒；
      · `ordered=False`（manifest 数组，闸只按 set 比，顺序不载荷）取最早的多余槽，
        确定性优先于「猜原序」。
    """
    if len(actual) != len(expect):
        return None, u"长度不等 %d≠%d" % (len(actual), len(expect))
    ca, ce = Counter(actual), Counter(expect)
    if ca == ce:
        return None, u"多重集已一致，无需修"
    surplus = [n for n in ca if ca[n] > ce.get(n, 0)]
    missing = [n for n in ce if ce[n] > ca.get(n, 0)]
    if len(surplus) != 1 or len(missing) != 1 or ca[surplus[0]] - ce.get(surplus[0], 0) != 1 \
            or ce[missing[0]] - ca.get(missing[0], 0) != 1:
        return None, u"多/缺不止一处 surplus=%s missing=%s" % (surplus, missing)
    s, m = surplus[0], missing[0]
    rank = {n: i for i, n in enumerate(expect)}
    cands = []
    for p in [i for i, n in enumerate(actual) if n == s]:
        trial = list(actual)
        trial[p] = m
        if ordered and any(rank[trial[i]] > rank[trial[i + 1]]
                           for i in range(len(trial) - 1)):
            continue
        cands.append(p)
    if not cands:
        return None, u"改任一重复槽都不满足升序"
    if len(cands) > 1 and ordered:
        return None, u"重复槽歧义 %s" % cands
    return [(cands[0], m)], ""


def unit_imgs(ext, chkey, side):
    """该侧该章全部单元正文里的 `<img src>` 末段（含重复，按出现序）。"""
    out = []
    udir = os.path.join(ext, "book_structure", side, unit_dir_name(chkey))
    mp = os.path.join(udir, "manifest.json")
    if not os.path.isfile(mp):
        return out
    for r in (json.loads(_read(mp)).get("units") or []):
        up = os.path.join(udir, r.get("file") or "")
        if not os.path.isfile(up):
            continue
        for m in RE_IMG.finditer(_read(up)):
            out.append(os.path.basename(m.group(2)))
    return out


def delivery_imgs(book, chkey, lang):
    """该章**该语种**交付 md（按节合并）里的 `<img src>` 末段；无该语种交付返回 None。

    🔴 按语种取：`chapter_md_groups` 一次给 en+cn 两组，混着数会把交付图数算成两倍，
    与单侧单元永远对不上（自证会假红）。
    """
    try:
        from verify.script import verify_chapter as VC
    except Exception:
        return None
    out = []
    hit = False
    for grp in (VC.chapter_md_groups(book, chkey) or []):
        if VC._group_lang(grp) != lang:
            continue
        hit = True
        txt = (_read(grp[0]) if len(grp) == 1 else VC._merge_section_files(grp))
        for m in RE_IMG.finditer(txt):
            out.append(os.path.basename(m.group(2)))
    return out if hit else None


def _backup(path, book, stamp, written):
    rel = os.path.relpath(path, book).replace("\\", "/")
    if rel in written:
        return
    d = os.path.join(book, "_extract", "_bak_resync_figure_refs", stamp)
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(path, dst)          # 同名不覆盖：dst 存在即已备份过
    written.add(rel)


def unit_seq(rows, side="units"):
    """该侧全部单元的 (现名序, 目标名序, 被 drop 的位置)，按文档序 —— 通道 C 的镜像真值。

    两个序列**同长**（与 `pos` 逐槽对齐用）；被删的那一格在 `want` 里留 `DROP` 哨兵，
    由契约腿按同一序号删掉那个 image 块。
    """
    cur, want, gone = [], [], set()
    for (sd, _f), seq in rows.items():
        if sd != side:
            continue
        for c, t in seq:
            cur.append(c)
            if t == DROP:
                want.append(DROP)
                gone.add(len(cur) - 1)
            else:
                want.append(t if t else c)
    return cur, want, gone


def seq_keys(rows, side="units"):
    """`unit_seq` 的**同序**展平：章级第 i 槽 ↔ (单元文件, 该单元内 img 序号)。

    去重要按位置删契约块，而位置是跨单元展平的 ⇒ 需要一个把槽号映射回「哪个单元的
    第几遍」的表，才能核「manifest 腿是否接受了这一条」。
    """
    out = []
    for (sd, f), seq in rows.items():
        if sd != side:
            continue
        for rank in range(len(seq)):
            out.append((f, rank))
    return out


def man_body_agree(ext, chkey, side):
    """该侧逐记录核：单元正文 `<img src>` 多重集 == `manifest.images` 多重集。

    → (True, None) 或 (False, 首个不符记录)。两个见证同向才允许判「契约单独 stale」。
    🔴 按**多重集**比不按序：manifest 数组序是契约节点派生序，与正文文档序本就不同
    （MSDA ch3 D4 正文 3.4 在前、数组 3.4 在末），比序会假拒。
    老 manifest 缺 `images` 字段的记录跳过——缺账不是不符。
    """
    udir = os.path.join(ext, "book_structure", side, unit_dir_name(chkey))
    mp = os.path.join(udir, "manifest.json")
    if not os.path.isfile(mp):
        return False, u"缺 manifest.json"
    for r in (json.loads(_read(mp)).get("units") or []):
        imgs = r.get("images")
        if not isinstance(imgs, list):
            continue
        up = os.path.join(udir, r.get("file") or "")
        if not os.path.isfile(up):
            return False, u"%s 单元文件不在盘" % r.get("file")
        body = [os.path.basename(m.group(2))
                for m in RE_IMG.finditer(_read(up))]
        if Counter(body) != Counter([os.path.basename(x) for x in imgs]):
            return False, u"%s 正文=%s / manifest=%s" % (
                r.get("file"), sorted(body),
                sorted(os.path.basename(x) for x in imgs))
    return True, None


def contract_only_repair(book, ext, chkey, rows, sides, craw, tab):
    """单元侧零活、契约单独 stale 时的**契约独占对账**（图改名波只回写单元与交付的形态）。

    gate ③b 在这里报两条红——「单元嵌契约外图 X」+「契约重复引用 Y（2 块）」，而单元、
    manifest、交付三侧都带 X 与 Y 各一次。老版本 `main` 一见 jobs 空就 `continue`，
    契约腿根本跑不到 ⇒ 这类账**工具看不见**。

    → ((槽序号, 新名) | None, 原因)。前置一条不成立即拒（不猜契约的图序）：
      ① 契约 image 槽数 == 该侧单元正文 img 条数（按文档序 1:1，否则位置不载荷）；
      ② 参战两侧「正文 == manifest」逐记录多重集一致（两见证同向，契约才是孤证）；
      ③ `seq_repair(ordered=True)` 成立且唯一（多/缺各一处、改后按单元文档序升序）——
         升序这一条本身就是印面定序：真值块紧跟自己的题注，改错槽立刻破坏单调；
      ④ 新名在 `figure_index` 本章登记 **且** `figure/` 盘上活着（不落空名）；
      ⑤ 旧名在契约挂 ≥2 处（正是「两张图被框成一个区域」的签名，别的形态不归本通道）。
    """
    pos = [(m.start(1), m.end(1), os.path.basename(m.group(1)))
           for m in re.finditer(r'"image"\s*:\s*"([^"]+)"', craw)]
    if not pos:
        return None, u"契约无 image 块"
    side_ref = "units" if "units" in sides else sides[0]
    cur_en, _want_en, gone = unit_seq(rows, side_ref)
    if gone:
        return None, u"本轮含去重裁定 ⇒ 不走独占通道"
    if len(pos) != len(cur_en):
        return None, u"契约 %d 槽 ≠ 单元 %d 条 ⇒ 无法按文档序定位" % (len(pos), len(cur_en))
    for sd in sides:
        ok, bad = man_body_agree(ext, chkey, sd)
        if not ok:
            return None, u"%s 侧正文与 manifest 不同向（%s）⇒ 契约非孤证" % (sd, bad)
    rep, why = seq_repair([p[2] for p in pos], cur_en, ordered=True)
    if not rep:
        return None, why or u"多重集已一致，无需修"
    i, nm = rep[0]
    old = pos[i][2]
    if len(name_hits(craw, old)) < 2:
        return None, u"旧名 %s 在契约只挂 1 处 ⇒ 非并图形态" % old
    if not any(nm in fs for (ck, _l), fs in tab.items() if str(ck) == str(chkey)):
        return None, u"新名 %s 不在 figure_index 本章登记" % nm
    if not os.path.isfile(os.path.join(book, "figure", nm)):
        return None, u"新名 %s 在 index 有而盘上没有" % nm
    return (i, nm), ""


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("book")
    ap.add_argument("chapters", nargs="*")
    ap.add_argument("--side", default="both",
                    choices=["both", "units", "units-translate"])
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--list", action="store_true",
                    help="dry-run 打印全部 job（默认每文件只列 3 条）")
    a = ap.parse_args()
    book = os.path.abspath(a.book)
    ext = os.path.join(book, "_extract")
    # 🔴 本 CLI 一次只处理一本书：先清掉进程里其它书残留的章型，再按当前
    # `ext` 灌注。否则跨书/跨测试连续调用时 `_PRIMED_KINDS` 会把上一本书的
    # kind 串到本书，`unit_dir_name` 算出 `appendixN` 而非 `chN` → 整章 0 job
    # （pytest 全量跑 ch14 实测）。见 `reset_chapter_kinds` docstring。
    reset_chapter_kinds()
    prime_chapter_kinds(ext)
    sides = list(SIDES) if a.side == "both" else [a.side]
    keys = a.chapters or []
    if not keys:
        loader_mod = None
        from verify.script import verify_chapter as VC
        loader_mod = VC._make_loader(ext, book)
        keys = sorted({str(i.ch) for i in loader_mod.chapters.values()},
                      key=lambda x: (len(x), x))
    stamp = time.strftime("%Y%m%dT%H%M%S")
    written = set()
    tab = index_table(ext)
    tot = {"unit": 0, "man": 0, "con": 0, "alt": 0, "drop": 0}
    for k in keys:
        jobs, skipped, rows, altjobs, drops = plan_chapter(book, ext, k, sides)
        nalt = sum(len(v) for v in altjobs.values())
        ndrop = sum(len(v) for v in drops.values())
        print(u"== 章 %s ｜ 改名 %d 处 ｜ 去重 %d 处 ｜ 题注回补 %d 处 ｜ 跳过（人工档）%d"
              % (k, len(jobs), ndrop, nalt, len(skipped)))
        for s in skipped[:12]:
            print(u"   SKIP %-16s %-22s %-24s %s" % (s[0], s[2], s[1], s[3]))
        if len(skipped) > 12:
            print(u"   … 另 %d 条" % (len(skipped) - 12))
        # 🔴 先全部**在内存里**算好并验完，再一次性落盘：任一环节验不过就整章不写，
        #    绝不留「正文新名 + manifest 旧名」的半写态（gate ③b 会由 PASS 翻 FAIL）。
        cp = resolve_chapter_json_path(ext, k)
        craw = _read(cp) if os.path.isfile(cp) else ""
        # 单元侧无活不代表契约无账：图改名波可能只回写单元/manifest/交付，契约单独停在
        # 旧名（gate ③b 同章两红「契约外图」+「重复引用」）。这里只做**契约独占对账**的
        # 预检，成立才放行进契约腿；不成立照旧跳过（账不成立的章绝不动契约）。
        contract_only = not (jobs or altjobs or drops)
        if contract_only:
            hit, co_why = contract_only_repair(book, ext, k, rows, sides, craw, tab)
            if hit is None:
                if craw:
                    print(u"   契约独占对账不落：%s" % co_why)
                continue
            cn = [os.path.basename(m.group(1))
                  for m in re.finditer(r'"image"\s*:\s*"([^"]+)"', craw)]
            co_old = cn[hit[0]]
            print(u"   契约独占对账（单元侧无活）：第 %d 槽 %s ← %s ｜ 新名在 index 且盘上活着"
                  % (hit[0] + 1, co_old, hit[1]))
            co_slot = hit
        else:
            co_slot = co_old = None
        touched = set()
        for _s, _u, old, new, _p, _r in jobs:
            touched.update((old, new))
        mraws, mwants, man_edits = {}, {}, {}
        byunit = {}
        for side, uf, old, new, usp, rank in jobs:
            byunit.setdefault((side, uf), []).append((old, new, usp, rank))
        accepted, manref = [], []
        accepted_drops = {}
        for (side, uf) in sorted(set(byunit) | set(drops)):
            js = byunit.get((side, uf)) or []
            dl = drops.get((side, uf)) or []
            udir = os.path.join(ext, "book_structure", side, unit_dir_name(k))
            mp = os.path.join(udir, "manifest.json")
            if mp not in mraws:
                mraws[mp] = _read(mp)
            mraw = mraws[mp]
            rsp = row_span(mraw, uf)
            slots = arr_slots(mraw[rsp[0]:rsp[1] + 1]) if rsp else []
            names = [os.path.basename(v) for _o, v in slots]
            srows = rows.get((side, uf)) or []
            want = corrected_order(srows)
            cur = [c for c, _t in srows]
            edits, how = [], u"逐条定位"
            if dl and js:
                manref.append((side, uf, u"同单元既有改名又有去重 ⇒ 分两轮落"))
                continue
            if dl:
                # 去重通道：删槽不可逆 ⇒ 数组必须与正文**同序同长**，按正文序号落。
                if names != cur:
                    manref.append((side, uf, u"drop：manifest 数组与正文 img 序不同 ⇒ 不敢删槽"))
                    continue
                if any(rank >= len(names) or names[rank] != nm for rank, nm, _a, _b in dl):
                    manref.append((side, uf, u"drop：正文序号在数组里对不上同名槽"))
                    continue
                edits = [del_slot_edit(mraw, rsp, slots, rank) for rank, _n, _a, _b in dl]
                ced = content_dec_edit(mraw, rsp, len(dl))
                if ced:
                    edits.append(ced)
                how = u"去重删槽 ×%d%s" % (len(dl), u"＋content 回退" if ced else u"")
                accepted_drops[(side, uf)] = dl
                man_edits.setdefault(mp, []).extend(edits)
                mwants.setdefault(mp, []).append((uf, want))
                print(u"   manifest %-16s %-24s %s" % (side, uf, how))
                continue
            if names == cur:
                # 数组与正文**同序** ⇒ 按正文序号落（唯一能正确落到「同名两遍」里的那一遍）
                for old, new, _u, rank in js:
                    if rank >= len(names) or names[rank] != old:
                        edits = None
                        break
                    off, v = slots[rank]
                    edits.append((rsp[0] + off + len(v) - len(old),
                                  rsp[0] + off + len(v), new))
                how = u"按正文序号落"
            elif Counter(names) != Counter(cur):
                edits = None              # 数组不是正文的镜像 ⇒ 不许逐条改，走通道 M 判定
            else:
                for old, new, _u, _r in js:
                    hit = [i for i, n in enumerate(names) if n == old]
                    if len(hit) != 1:
                        edits = None
                        break
                    i = hit[0]
                    off, v = slots[i]
                    edits.append((rsp[0] + off + len(v) - len(old),
                                  rsp[0] + off + len(v), new))
            if edits is None:                 # 通道 M：数组被上一轮写成「同名两遍/零遍」
                rep, why = seq_repair(names, want)
                if rep is None:
                    manref.append((side, uf, u"manifest 对不上账：%s" % why))
                    continue
                i, nm = rep[0]
                if names[i] not in touched or nm not in touched:
                    manref.append((side, uf, u"manifest 多/缺 %s↔%s 不在本次改名范围，不越界修"
                                   % (names[i], nm)))
                    continue
                off, v = slots[i]
                edits = [(rsp[0] + off + len(v) - len(names[i]),
                          rsp[0] + off + len(v), nm)]
                how = u"通道 M（重复槽 %s ← 缺失名 %s）" % (names[i], nm)
            man_edits.setdefault(mp, []).extend(edits)
            mwants.setdefault(mp, []).append((uf, want))   # 只验**已接受**的单元
            print(u"   manifest %-16s %-24s %s" % (side, uf, how))
            for old, new, usp, rank in js:
                accepted.append((side, uf, old, new, usp, rank))
        refused = set((s, u) for s, u, _m in manref)
        for r in manref[:12]:
            print(u"   三处不齐，整条不改：%s %s ← %s" % (r[0], r[1], r[2]))
        if len(manref) > 12:
            print(u"   … 另 %d 条" % (len(manref) - 12))
        accepted_drops = dict((kk, vv) for kk, vv in accepted_drops.items()
                              if kk not in refused)
        if (not accepted and not (set(altjobs) - refused) and not accepted_drops
                and not contract_only):
            # 🔴 契约独占对账（单元侧零活）也得进写相：老这里一句 `continue` 就是
            #    「契约单独 stale」全瞎的根因（gate ③b 两红无人修）。
            continue
        if not a.commit:
            shown = accepted if a.list else accepted[:3]
            for side, uf, old, new, _u, _r in shown:
                print(u"   DRY  %-16s %-24s %s -> %s" % (side, uf, old, new))
            if len(accepted) > len(shown):
                print(u"   … 另 %d 条（--list 全列）" % (len(accepted) - len(shown)))
            for (side, uf), alist in sorted(altjobs.items()):
                for _s, _e, txt, oldtxt in (alist if a.list else alist[:2]):
                    print(u"   ALT  %-16s %-24s %r -> %r" % (side, uf, oldtxt[:40], txt[:40]))
            for (side, uf), dlist in sorted(accepted_drops.items()):
                for rank, nm, _s, _e in dlist:
                    print(u"   DROP %-16s %-24s 第 %d 遍 %s（整行删 + 数组/契约同序号）"
                          % (side, uf, rank + 1, nm))
            if contract_only:
                print(u"   DRY  契约独占对账 %s：第 %d 槽 %s -> %s（只改契约，单元/manifest 不动）"
                      % (os.path.relpath(cp, book).replace("\\", "/"),
                         co_slot[0] + 1, co_old, co_slot[1]))
            continue
        staged = {}                       # path -> (原文, 改后文)
        # ① 单元正文：src 与 alt 都按 span 一次并行落
        perfile = {}
        for side, uf, old, new, usp, rank in accepted:
            perfile.setdefault((side, uf), []).append((old, new, usp))
        for key in sorted(set(perfile) | (set(altjobs) - refused) | set(accepted_drops)):
            side, uf = key
            up = os.path.join(ext, "book_structure", side, unit_dir_name(k), uf)
            uraw = _read(up)
            uedits = []
            ndel_nl = 0
            for old, new, (st, en) in perfile.get(key, []):
                val = uraw[st:en]
                if not val.endswith(old):
                    raise SystemExit(u"[resync_figure_refs] 计划与磁盘不符：%s src=%r 旧名=%s"
                                     % (up, val, old))
                uedits.append((st, en, val[:len(val) - len(old)] + new))
            for st, en, txt, oldtxt in sorted(altjobs.get(key, [])):
                if uraw[st:en] != oldtxt:
                    raise SystemExit(u"[resync_figure_refs] 题注锚与磁盘不符：%s alt=%r"
                                     % (up, uraw[st:en][:60]))
                uedits.append((st, en, txt))
            for rank, nm, ls, tail in accepted_drops.get(key, []):
                line = uraw[ls:tail]
                # 🔴 删行不可逆 ⇒ 落盘前再按**形状**核一遍：这一行必须正好是一条含该名的 img，
                #    多一条 img 或夹着正文都算计划与磁盘不符（计划是几毫秒前算的，书可能被并发改过）。
                if line.count("<img") != 1 or nm not in line:
                    raise SystemExit(u"[resync_figure_refs] 去重锚与磁盘不符：%s 第 %d 遍 %s\n  %r"
                                     % (up, rank + 1, nm, line[:120]))
                uedits.append((ls, tail, ""))
                ndel_nl += line.count("\n")
            if not uedits:
                continue
            uout = splice(uraw, uedits)
            assert uout.count("\n") == uraw.count("\n") - ndel_nl, u"行数不守恒：%s" % up
            keep = [l for l in uraw.split("\n") if "<img" not in l.lower()]
            kept = [l for l in uout.split("\n") if "<img" not in l.lower()]
            assert len(keep) == len(kept), \
                u"非 img 行数变了（去重只许删 img 整行）：%s" % up
            bad = [(x, y) for x, y in zip(keep, kept) if x != y]
            assert not bad, u"改到了非 img 行：%s ｜ %s" % (up, bad[:2])
            staged[up] = (uraw, uout, len(uedits), u"单元")
            tot["unit"] += len(perfile.get(key, []))
            tot["alt"] += len(altjobs.get(key, []))
            tot["drop"] += len(accepted_drops.get(key, []))
        # ② manifest：整侧一次并行落，再逐记录验多重集
        for mp, eds in man_edits.items():
            mraw = mraws[mp]
            mout = splice(mraw, eds)
            dnl = sum(mraw[s:e].count("\n") for s, e, _t in eds)
            assert mout.count("\n") == mraw.count("\n") - dnl, u"manifest 行数不守恒：%s" % mp
            try:
                json.loads(mout)
            except ValueError as ex:
                raise SystemExit(u"[resync_figure_refs] manifest 改后不是合法 JSON：%s ｜ %r"
                                 % (mp, ex))
            for uf, want in mwants.get(mp, []):
                rsp = row_span(mout, uf)
                got = [os.path.basename(v) for _o, v in arr_slots(mout[rsp[0]:rsp[1] + 1])]
                if Counter(got) != Counter(want):
                    raise SystemExit(u"[resync_figure_refs] manifest 验账不过：%s ｜ %s\n"
                                     u"  改后=%s\n  应为=%s" % (mp, uf, got, want))
            staged[mp] = (mraw, mout, len(eds), u"manifest")
            tot["man"] += len(eds)
        # ③ 契约（尽力回写，不参与拦①②）：契约的图序列**就是**单元正文序列的镜像，
        #    所以按文档序逐槽对账；两者不同长（老契约有额外节点引用同一张图）才退回逐名。
        if craw:
            side_ref = "units" if "units" in sides else sides[0]
            cur_en, want_en, gone_en = unit_seq(rows, side_ref)
            if not cur_en and "units" not in sides:
                _j, _s, rows_u, _a, _d = plan_chapter(book, ext, k, ["units"])
                cur_en, want_en, gone_en = unit_seq(rows_u)
                rows, side_ref = rows_u, "units"
            # 只有 manifest 腿**接受**的去重才许动契约（删一块不可逆，两侧必须同进退）
            ids = set((s, uf, rk) for (s, uf), dl in accepted_drops.items()
                      for rk, _n, _a, _b in dl)
            keys = seq_keys(rows, side_ref)
            gone_ok = set(i for i in gone_en
                          if i < len(keys) and (side_ref,) + tuple(keys[i]) in ids)
            want_en = [c if (i in gone_en and i not in gone_ok) else t
                       for i, t in enumerate(want_en)]
            gone_en = gone_ok
            pos = [(m.start(1), m.end(1), os.path.basename(m.group(1)))
                   for m in re.finditer(r'"image"\s*:\s*"([^"]+)"', craw)]
            cedits, done = [], set()
            if pos and len(pos) == len(cur_en):
                for i, ((cs, ce, nm), c_now, t_now) in enumerate(zip(pos, cur_en, want_en)):
                    if i in gone_en:
                        b = None if nm != c_now else del_block_edit(craw, cs, ce)
                        if b is None:
                            print(u"   契约去重不落第 %d 槽 %s：与正文序号不符 / 不是单键 image 块"
                                  % (i + 1, nm))
                            want_en[i] = nm
                            gone_en.discard(i)
                        else:
                            cedits.append(b)
                            done.add(i)
                            print(u"   契约去重：删第 %d 槽 %s 整块" % (i + 1, nm))
                        continue
                    if nm != c_now:        # 该槽自己就与正文不符 ⇒ 不落，留给通道 C 裁定
                        continue
                    if t_now and t_now != c_now:
                        cedits.append((ce - len(c_now), ce, t_now))
                        done.add(i)
                if cedits:
                    print(u"   契约按文档序逐槽落位 %d 处（与单元同长 %d 槽）" % (len(cedits), len(pos)))
            elif pos and gone_en:
                print(u"   契约去重不落：契约 %d 槽 vs 单元 %d 条不同序 ⇒ 无法按文档序定位"
                      % (len(pos), len(cur_en)))
                for i in sorted(gone_en):
                    if i < len(want_en):
                        want_en[i] = cur_en[i]
                gone_en = set()
            elif pos:
                byold = {}
                for _s, _u, old, new, _p, _r in jobs:
                    byold.setdefault(old, set()).add(new)
                for old, news in sorted(byold.items()):
                    if len(news) != 1:
                        print(u"   契约跳过 %s：同名对应多个新名，无法定名" % old)
                        continue
                    new = next(iter(news))
                    hits = name_hits(craw, old)
                    njob = len([1 for _s, _u, o, _n, _p, _r in jobs if o == old])
                    # 同名挂多处（两节点引用同一图）⇒ 全部换成同一个新名：位置各自唯一，不是猜。
                    # 🔴 但旧名**在盘上活着**而挂处数 ≠ 单元条数时不许全落：那是上一轮串行写
                    #    把两槽写成同名（MSDA ch14 `fig14.6_2` 两遍，正文只该改第二遍），
                    #    全落会把好的一半也毁掉 ⇒ 交给通道 C 按升序裁定改哪一槽。
                    if len(hits) != njob and os.path.isfile(
                            os.path.join(book, "figure", old)):
                        print(u"   契约 %s：活名挂 %d 处、单元 %d 条 ⇒ 不越界，交通道 C"
                              % (old, len(hits), njob))
                        continue
                    cedits += [(p, p + len(old), new) for p in hits]
            after = ([DROP if i in gone_en else (want_en[i] if i in done else pos[i][2])
                      for i in range(len(pos))] if len(pos) == len(cur_en)
                     else [p[2] for p in pos])
            after = [x for x in after if x != DROP]
            want_flat = [x for x in want_en if x != DROP]
            # 单元侧无活时**不重跑** seq_repair，直接用预检那份裁定：预检除升序外还核了
            # 「正文==manifest 两见证同向 / 新名在 index 且盘上活着 / 旧名在契约挂 ≥2 处」，
            # 走同一份结果才不会让「有证据的裁定」与「落盘的编辑」分叉。
            rep, why = (([co_slot], u"") if contract_only
                        else seq_repair(after, want_flat, ordered=True))
            if rep:
                i, nm = rep[0]
                if i not in done and not any(
                        s < pos[i][1] and e > pos[i][0] for s, e, _t in cedits):
                    cedits.append((pos[i][1] - len(pos[i][2]), pos[i][1], nm))
                    print(u"   契约%s：第 %d 槽 %s ← %s（改后按单元文档序升序）"
                          % (u"独占对账" if contract_only else u"通道 C",
                             i + 1, pos[i][2], nm))
            elif Counter(after) != Counter(want_flat):
                print(u"   契约未回写：通道 C 不成立（%s）" % why)
            if cedits:
                cout = splice(craw, cedits)
                dnl = sum(craw[s:e].count("\n") for s, e, _t in cedits)
                assert cout.count("\n") == craw.count("\n") - dnl, u"契约行数不守恒：%s" % cp
                try:
                    json.loads(cout)
                except ValueError as ex:
                    raise SystemExit(u"[resync_figure_refs] 契约改后不是合法 JSON：%s ｜ %r"
                                     % (cp, ex))
                staged[cp] = (craw, cout, len(cedits), u"契约")
                tot["con"] += len(cedits)
        for path, (praw, pout, n, kind) in staged.items():
            _backup(path, book, stamp, written)
            _write(path, pout)
            print(u"   落 %s ×%d %s" % (kind, n, os.path.relpath(path, book).replace("\\", "/")))
        # 写后自证：单元图多重集 vs **同语种**交付图多重集（真值是交付，不是契约）
        if a.commit:
            for side in sides:
                got = unit_imgs(ext, k, side)
                want = delivery_imgs(book, k, "en" if side == "units" else "cn")
                if want is None:
                    print(u"   自证 %s：拿不到该语种交付 md（未判）" % side)
                    continue
                if sorted(got) == sorted(want):
                    print(u"   自证 %s：单元图 %d == 交付图 %d" % (side, len(got), len(want)))
                else:
                    d = Counter(got) - Counter(want)
                    e = Counter(want) - Counter(got)
                    print(u"   自证 %s：仍差 单元独占%s 交付独占%s" % (side, dict(d), dict(e)))
    print(u"落盘：单元 %d 行 ｜ 去重 %d 行 ｜ 题注 %d 处 ｜ manifest 记录 %d 处 ｜ 契约 %d 处"
          u" ｜ 备份 %d 文件 ｜ %s"
          % (tot["unit"], tot["drop"], tot["alt"], tot["man"], tot["con"], len(written),
             "已 --commit" if a.commit else "DRY-RUN（未写）"))
    if not a.commit:
        print(u"（复核用：--commit 后再跑一次本命令应报「改名 0 处」）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
