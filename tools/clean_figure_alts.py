# -*- coding: utf-8 -*-
r"""tools/clean_figure_alts.py — 按「同图他处已写净的 alt → 登记表题注」改写**脏 alt**。

为什么要它（MSDA ch10/ch14 实测形态）：`embed_figures.short_caption()` 把 OCR 题注
`[:40]` 硬截，既不去图号拆字（`FIG U RE 10.4`）也不补号后空格，于是单元正文里落下
`alt="Figure FIG U RE 10.4An additive treatment effec"`——碎字＋粘连＋半词截断三样齐全，
而交付侧反而是完整题注。老链条没人管 alt **文本**（改名波只管 `src`）⇒ 这类缺陷只在
「重拼==交付」普查里以 IMG-ALT 段的形态露头，且和写手合法的缩写混在一起。

判据形状（p1082/p1083 三轮误判换来的，改动前请先读）：
  · ❌「≥17 字母无空格」判粘连 ⇒ 误伤 `compactifications` / `indistinguishable`。
  · ❌「alt 的 token 出现在 caption 全词粘连串里」判粘连 ⇒ **方向反了**：Koopman /
    数值分析 / Modern Robotics 的**登记 caption 本身**是 OCR 粘连稿（`betweenthe`、
    `poly-nomial`），那样只会把写手已改对的一侧判脏（实测 500 行全在这一侧）。
  · ✅ 互为参照：判某串的粘连词时，参照词表 = **其余各处**（同图在交付/另一单元侧/登记
    题注）的 token 并集，且**跳过与本轮串完全相同的腿**——同腿挂同一份碎字时它是「同案
    被告」，不是「证人」（units 与 units-translate 逐字同源，MSDA 28 行全是这一形）。
    参照表**两种词形都进**：并 `x-y`（印面行末断词 `approxi-mated` 会把写对的
    `approximated` 反判成粘连——数值分析 ch1/9/11 三枪）＋不并（`least-squares` 并完
    只剩 `leastsquares`，别处没写过 ⇒ 又反判粘连——数值分析 ch13、statistical-inference
    ch12 两枪）。🔴 判的一侧（本轮串）**只按不并词形**取 token：连字符是人写的复合词
    标记，不是 OCR 粘连标记，真粘连 `betweenthe` / `thatinvolves` 本来就没有分隔符。
  · 号后粘连（`10.4An`）用「尾字母 ≥2 且与题注首词互为前缀」认定 ⇒ `3.4A`/`2.1a` 这类
    🔴 单子标号（尾长 1）一律不算。
  · 🔴 `strip_lead` 只剥登记表给的那个号，且剥号时**不吃紧跟其后的第一个字母**
    （`Fig. 5.3Smooth` 若按「可选一个字母的子标号」剥，会写出 `mooth …` 这种新碎字；
    Lee ISM ch5 正是这一形的控件）。

改写分三档（A/B 顺序即裁定；C 只在 `--align-stale` 下生效）：
  A **原地去脏**（`in_place`）：本轮串自己已是**完整**题注，脏的只是前导图号形制或
    词间粘连 ⇒ 只重挂前导 + 插空格，散文零改写。交付侧的粘连必须走这一档：登记
    caption 常是**缩略题注**（MSDA 图 9.7 印面 `…of 500 pseudorandom variables…`，
    登记侧丢了 `pseudorandom`），搬过来就是把印面内容改短。
  B **来源腿重组**：本轮串被截断（`short_caption()` 的 `[:40]` 半词）时才搬别的腿。
    次序 交付 alt → 另一单元侧 → 同侧其他 alt → 登记 caption。理由：交付 alt 通常是
    写手按印面核过的完整稿，caption 是 OCR 原始题注，两者会差在真内容上。
  🔴 A/B 两档都只保证「形制」净，不保证「内容」对：实测交付 alt 自身也会带写手笔误
    （MSDA 图 10.4 交付/单元 alt 写 `C(y) = F(y - h)`，印面与登记 caption 都写
    `G(y) = F(y − h)`）⇒ 写完必须跑印面回检（p1090 一类探针：新 alt 逐字出现在
    PDF 文字层里吗），内容分叉另行按印面裁定。

  C **跨腿对齐（`--align-stale`，默认关）**：本轮串**净**但与登记题注装配不同也改写。
    为什么另开一档而不是把 A/B 放宽：alt 的语义身份是**印面题注**，而写手起稿时抄的是
    老 OCR 视图 ⇒ 净串可以整片陈旧（MSDA 实测 604 行里 302 行＝一半：`lambda`↔`λ`、
    `union`↔`∪`、`Delta`↔`Δ`、丢尾句点、把正文散文 `in the unit square` 串进题注）。
    这一半在 A/B 档里**永远量不到**（判据只认四种脏形），于是「重拼==交付」的 alt 漂移
    只能靠人工逐行镜像，而跨腿不一致本身无人记账。
    目标形只有一种：登记腿的**未截断**装配（`cands_from_caption(...)[-1]`）——不取截断
    稿（那是把印面改短），不取别的腿的串（别的腿与本轮串同源同错的形态 MSDA 28 行实测）。
    ⇒ 本档的正当性完全押在「登记 caption == 印面」这一条上：开火前必须对该书的 caption
    做过印面抽检（MSDA 20 张逐字坐实：p1127/p1143/p1144/p1145），抽检不过的书不许开。
    放行条件与 A/B 同一条（闸③目标自证净、闸⑤不跨语种、闸⑧禁改短），另加一条
    **体不许被清空**：登记题注只剩标签词时装配出的正形体为空 ⇒ 拒（那是登记侧欠账，
    不是这张图该没题注）。

放行闸（全满足才写；任一不满足 ⇒ 只报告，拒因打印）：
  ① `src` 末段在本章 `figure_index.json` 登记；登记 label 是纯编号形时走 A/B 两档（开
     档 C 时再加一档），非纯编号形（unnamed 的 `''`、字母号 `F.1`）**只**由登记腿出厂
     装配裁决；
  ② 本轮 alt 按上述判据**确实脏**（不脏不动）；开 `--align-stale` 时档 C 豁免这一条，
     触发条件换成「净但与登记腿未截断装配逐字不同」，且**不消费 ⑥ 的前导写法**（目标形
     整条来自出厂装配，没有可自造体例的机会）；
  ③ 来源串自身在同一判据下干净（脏 caption ⇒ 禁回写，须先印面取证）；
  ④ 来源串开头若带号，必须带的就是本章登记的那个号（不跨图搬题注）；
  ⑤ 改写后 alt 干净，且与本轮 alt 语种同形（中文 notes 对英文题注 ⇒ 拒，不代翻译）；
  ⑥ 前缀写法三档：该章**多数净 alt** 的形 → 该章**脏 alt 的标签词 ∩ 本书声明形** →
     按行拒（碎字形永远不作证据）；不自造；
  ⑦ 只换 `alt` 的值：`src` / `width` / `height` / 缩进 / 行数 / 换行符逐字节不动。
 ⑧ **禁改短**（`shortens`）：改写后的体不许是任一**已写全的 alt**（含本轮串自己）的体
    的严格前缀。搬来的来源串自己可能就是旧版 `short_caption()` 的 `[:40]` 截断稿——
    MSDA 图 14.26 交付腿实测「新」比「旧」短 98 字符＝工具亲手删印面内容。登记腿装配
    同受此锁，但 **caption 不作长度证人**（OCR 原始题注的长度不算「已核内容」，否则
    每条长题注的出厂截断稿都被判改短，闸⑪「修完 == 将来重 merge」当场作废）；截断稿
    被拦时退到未截断的全题注形（`cands_from_caption`），两种都不行 ⇒ 拒并打印拒因。

安全闸：默认 dry-run；`--commit` 才写；写前整文件备份到
  `_extract/_bak_clean_figure_alts/<stamp>/`；同文件多条一次**并行 splice**（串行
  find/replace 会把刚写进去的那条再改回去）；写完三重自证——复跑同一判据须归零、
  非 `<img>` 行逐字节相同、行数与换行符守恒；单元正文被改 ⇒ 结尾提醒跑
  `tools/resync_src_hash.py`（译侧 src_hash 会漂）。

用法：python tools/clean_figure_alts.py <book_root> <ch> [ch …]
              [--target units|delivery|both] [--side units|units-translate]
              [--align-stale] [--commit] [--list]
  🔴 `--align-stale` 是**按书裁定**的开关：只有对该书 `figure_index.json` 的 caption 做过
     印面抽检（逐字坐实）才许开；否则档 C 会把「登记侧的 OCR 欠账」当成真值刷进所有腿。
"""
import argparse
import io
import os
import re
import shutil
import sys
import time
from collections import Counter, defaultdict

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import lib.boot as boot  # noqa: E402
boot.setup()

from data.book_structure.book_structure import prime_chapter_kinds  # noqa: E402

# 🔴 判据与「剥标签词+号」的唯一真源在 `lib/figure_alt.py`：写手（embed_figures /
# render_draft）与校验（gate_units）也 import 同一份，本工具不许自带正则副本。
from lib.figure_alt import (  # noqa: E402
    CJK, LBL, RE_DUP_LABEL, RE_FIGURE, RE_FIGURE_REV, RE_LABELJUNK,
    RE_STUCK, RE_TAG_ONLY, RE_ZONE_NUM, _nospace, build_alt, dirty, judge,
    lead_of, lead_junk, strip_caption_lead, strip_lead, unescape, witness_toks, why)
from lib.figure_io import FIGURE_LABELS_DEFAULT, load_fig_labels  # noqa: E402
# 🔴 取数（本章文件池 / 题注真值 / 腿名）的唯一入口：门控 `gate_units` 与本工具都从
# `lib.figure_alt_audit` 读，两边不可能给出两个不同的「谁写脏了」集合。
from lib.figure_alt_audit import (  # noqa: E402
    DELIV, UNIT_SIDES as SIDES, alt_rows, chapter_files, read_text)
# 登记腿的 alt 一律走**出厂写手**那一次装配（`embed_figures.short_caption` 是写手的体
# 规则，含中文 `图中/中的→示意图`）⇒ 修完的 alt 与将来重 merge 逐字相同。
from embed_figures import short_caption as writer_body  # noqa: E402


def _read(path):
    return read_text(path)


def cap_table(ext):
    u"""登记题注表（体在 `lib.figure_alt_audit`）；本工具缺 figure_index 时**硬失败**——
    没有题注真值就没有「谁写脏了」可判，静默返回空表会让一次「全绿」成为假确证。"""
    p = os.path.join(ext, "figure_index.json")
    if not os.path.isfile(p):
        raise SystemExit(u"[clean_figure_alts] 缺 figure_index.json：%s（无题注真值）" % p)
    from lib.figure_alt_audit import cap_table as _shared
    return _shared(ext)


def _write(path, text):
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def splice(raw, edits):
    """`edits = [(start, end, text)]` 一次并行落（按起点降序切）。"""
    out = raw
    for s, e, t in sorted(edits, key=lambda x: x[0], reverse=True):
        out = out[:s] + t + out[e:]
    return out


def in_place(text, label, tag, legs):
    u"""原地去脏：只重挂前导图号 + **插空格**，散文一个字母不改。→ 新串或 None。

    为什么必须有这一档：交付侧的 alt 是写手按印面核过的**完整**题注，脏的常常只是
    一处粘连（MSDA 图 9.7 `doubleexponential`、图 14.22 `andcatheter` —— 都是 PDF
    行末断词并回时漏掉空格）。这时「来源腿重组」只会拿到登记 caption，而 caption
    是**缩略题注**（印面 `…of 500 pseudorandom variables…`，登记侧丢了
    `pseudorandom`）⇒ 重组等于把印面内容改短。p1090 的印面回检就是为这一形设的。

    适用性四道锁：
      ① 剥前导后的新体**去空白**与旧体去空白逐字相等 ⇒ 除插空格外零改写；
      ② 任一证人的体若**严格以本轮体为前缀**（更长）⇒ 本轮串是 `short_caption()`
         的 `[:40]` 半词截断稿，原地修只会留下截断 ⇒ 交回来源腿重组；
      ③ 每个粘连词都要能在参照词表里切成两个相邻真词，切点不唯一/找不到 ⇒ None；
      ④ 重挂后的串复检必须**判净**。
    """
    body = strip_lead(text, label)
    if not body:
        return None
    others = [v for (n, v) in legs if (n, v) != ("C", None)
              and (v or "").strip() != (text or "").strip()]
    ref = set()
    for v in others:
        ref |= witness_toks(strip_lead(v, label))
    d = judge(text, label, legs)
    cuts = []
    for m in RE_STUCK.finditer(text or u""):          # 号后粘连 `10.4An`
        if m.group(1).lower() == label.lower() and \
                body[:len(m.group(2))].lower() == m.group(2).lower():
            cuts.append(len(m.group(2)))
            break
    for t in d["jam"]:                                # 粘连词：每次出现都切
        sp = None
        for i in range(3, len(t) - 2):
            if t[:i] in ref and t[i:] in ref:
                if sp is None:
                    sp = i
                elif sp != i:
                    return None                       # 切点不唯一 ⇒ 不猜
        if sp is None:
            return None
        for mm in re.finditer(u"(?<![A-Za-z0-9])" + re.escape(t) +
                              u"(?![A-Za-z0-9])", body, re.I):
            cuts.append(mm.start() + sp)
    out = body
    for pos in sorted(set(cuts), reverse=True):
        out = out[:pos] + u" " + out[pos:]
    # 补的空格可能正落在原有空格上（`5.3Smooth compatibility` 的号后粘连）⇒ 收成单空格；
    # 锁①按「去空白逐字相等」核，收空白不越界。
    out = re.sub(r"\s{2,}", u" ", out).strip()
    if _nospace(out) != _nospace(body):
        return None
    # 前导：本轮串自己写的标签词形（`图`/`Fig.`/`Figure`）优先，碎字前导才换章内多数形
    # 号必须**真在本串里**：strip_lead 的标签词与号都可省，号缺失时它照样返回整串 ⇒
    # 若不拦，这里会拿「号之前那段」当全串前导，拼出「Figure 10.4 <原串里又含 10.4>」的
    # 重复号形（数值分析 ch13–16 实测即此形，之前直接 None.start() 崩）。缺号交来源腿。
    m_lab = re.search(re.escape(label) + u"(?![0-9.])", text or u"", re.I)
    if m_lab is None:
        return None
    lead = (text or u"")[:m_lab.start()]
    own = RE_TAG_ONLY.match(lead)
    use = own.group(1).strip() if own else tag
    if bool(CJK.search(out)) != bool(CJK.search(use)):
        return None                                   # 不跨语种改前导
    fixed = u"%s %s %s" % (use, label, out.strip())
    nb = _nospace(strip_lead(fixed, label))
    if nb != _nospace(body):
        return None
    if any(_nospace(strip_lead(v, label)).startswith(nb) and
           len(_nospace(strip_lead(v, label))) > len(nb) for v in others):
        return None                                   # 锁②：半词截断交回来源腿
    if dirty(judge(fixed, label, legs)):
        return None
    return fixed


def shortens(cand, label, legs):
    u"""档 B 的「禁改短」锁：候选的体若是任一**alt 证人**的体的严格前缀 ⇒ 候选是截断稿。

    为什么来源腿也要这一道：`in_place` 的锁②只拦「原地把半词截断修成半词截断」，而
    搬来的来源串自己就可能就是旧版 `short_caption()` 的 `[:40]` 截断稿。MSDA 图 14.26
    实测：交付腿脏在二次转义（原地档补空格改不动）⇒ 走来源腿，`donor_order(D)` 第一条
    证人就是单元那条 47 字符的截断稿 ⇒ 「新」比「旧」短 98 个字符＝工具亲手删印面内容。

    口径三条，都各有实测依据：
      · **登记 caption 不进证人**：caption 是 OCR 原始题注，长度不是「已核内容」的证据；
        拿它当证人会让每条长题注的出厂截断稿都被判「改短」，闸⑪（修完 == 将来重 merge）
        当场作废。只有**别处真写出来的 alt** 才算「会被删掉的内容」。
      · 本轮串自己也在 `legs` 里 ⇒ 「新串比旧串短」这一最直白的删内容同样被拦。
      · 转义层数是形制不是内容 ⇒ 两边都剥到不动点再比，否则同一句话能量出三个长度。

    🔴 已知上限（不作判据，只登记）：证人串自己的前导若脏到 `strip_lead` 剥不动
    （`Figure FIGURE F.1.` 那类重复号 + 字母号），它的「体」里会留着整条前导 ⇒ 前缀比
    不出来 ⇒ 锁漏。MSDA 实测被拦的几形前导都能剥动，故先按现状收；要再宽就得给
    `strip_lead` 加「重复标签词」档，那是判据侧的事，另波再改。
    🔴 第二条上限：**前缀比只认「严格前缀」**⇒ 目标体的尾巴带句点、而证人在这句点
    之后还有内容（登记题注是印面题注的**截短**句，印面后面还有一句）时，目标体不是
    证人体的严格前缀 ⇒ 锁漏（实测：题注 `Normal probability plot.` + 证人
    `…plot. A normal curve is fitted…` ⇒ 目标体被判「没改短」而实际删掉一句）。
    反方向（题注缺尾句点、证人带句点）会**误拒**：证人以目标体为严格前缀 ⇒ 判改短。
    这两条都偏保守侧（宁可拒不可删），但误拒会挡路 ⇒ 档 C 的正当性另押在
    「该书 caption 已做过印面抽检」上（见模块 docstring 档 C 段）。
    """
    cb = _nospace(unescape(strip_lead(cand, label)))
    if not cb:
        return False
    for (n, v) in legs:
        if n == u"C":
            continue
        vb = _nospace(unescape(strip_lead(v or u"", label)))
        if vb.startswith(cb) and len(vb) > len(cb):
            return True
    return False


def full_body(cap, label, labels):
    u"""登记腿的**未截断**体：与 `writer_body` 同一条剥前导，只差最后那一下 `clip_words`。"""
    return strip_caption_lead(cap, label, labels)


def cands_from_caption(cap, label, labels_ch):
    u"""登记腿的两种装配，**顺序即裁定**：先出厂截断稿（修完 == 将来重 merge 的产物），
    只有当它比某条已写全的 alt 短（= 会删内容）时才退到未截断的全题注形。

    体例来源不是这里定的：`short_caption()` 的 40 词边界截断是**写手起稿时**的体规则，
    而 `tools/resync_figure_refs.py` 的印面题注回补通道往单元 alt 里写的是**完整**题注
    （MSDA 单元绝大多数 alt 就是整条 caption）⇒ 两条腿的「该多长」本来就不同，登记腿
    装配只保证「不比任何 alt 证人短」，不在这里发明第三种长度。
    """
    out = [build_alt(cap, label, labels_ch, writer_body)]
    full = build_alt(cap, label, labels_ch, full_body)
    if full not in out:
        out.append(full)
    return out


RE_ANY_LABEL = re.compile(
    r"^\s*((?:图\s*)?(?:FIG\s{1,3}U\s{1,3}RE|fig(?:ure|\.)?|图|表))\s*"
    r"(?:[0-9]|[A-Za-z][.\-][0-9])", re.I)
# 🔴 号位允许**字母章位**（附录 `Figure F.1` / `图 A.1`）：只认「紧跟数字」时，字母号
# 一章里一个标签词都匹配不上 ⇒ 前导写法判不出、整章在行级之前就拒（Katok 附录实测）。
# 但字母位必须带 `.数字` 尾巴，否则 `Figure of speech` 这种散文首词也会被当成体例证据。


def tag_form(alts):
    """该章多数**形制合规 alt** 的前缀写法（`Figure` / `Fig.` / `图`），无则 None。"""
    c = Counter()
    for a in alts:
        m = RE_ANY_LABEL.match(a or "")
        if not m:
            continue
        if lead_junk(a) or RE_DUP_LABEL.match(a) or RE_STUCK.search(a):
            continue
        c[m.group(1).strip()] += 1
    if not c:
        return None
    return c.most_common(1)[0][0]


def chapter_tag(alts, labels):
    u"""本章前导写法：① 多数**净 alt** 的形 → ② 多数**脏 alt** 号前那个标签词，但只认
    本书**已声明**的形 → ③ 拒。

    为什么要第②档：Fraleigh 实测 40 条交付 alt 全是 `Figure 3.10 Figure`（登记题注
    本身就写成 `'3.10 Figure'`）⇒ 本章一个净 alt 都没有 ⇒ 旧判据整章拒（p1093 普查里
    Fraleigh 56 行全落「本章无可参照的 alt 前缀写法」＝**静默失明**：脏得越彻底越修不了）。
    第②档不放宽到「随便什么词」：**词形仍须与本书声明一致**（同一个 `verify_config`
    ordinal 组，也正是写手 `label_prefix` 的兜底源），且**碎字形不作证据**——
    否则就是工具自造体例。三档都不成立时照旧拒，拒因打印。
    """
    t = tag_form(alts)
    if t:
        return t, u"本章净alt"

    def norm(s):
        return re.sub(r"[.\s]", u"", (s or u"")).lower()

    declared = {}
    for x in (labels or []):
        s = str(x)
        if s and not s.isspace():
            declared[norm(s)] = s
    c = Counter()
    for a in alts:
        if lead_junk(a or u""):
            continue                          # `FIG U RE` 这类碎字不配当体例证据
        m = RE_ANY_LABEL.match(a or u"")
        if not m:
            continue
        w = norm(m.group(1))
        if w in declared:
            c[declared[w]] += 1
    if c:
        return c.most_common(1)[0][0], u"本章脏alt∩声明形"
    return None, u"无声明形"


def writable(files, sides, target):
    keep = []
    for leg, rel, p in files:
        if leg == DELIV and target in ("delivery", "both"):
            keep.append((leg, rel, p))
        elif leg != DELIV and target in ("units", "both") and leg in sides:
            keep.append((leg, rel, p))
    return keep


def donor_order(leg):
    """证人优先序：交付 → 另一单元侧 → 本章同侧其它写法 → 登记 caption。"""
    seq = [DELIV]
    seq += [s for s in SIDES if s != leg]
    seq += [leg]
    seq.append("C")
    seen, out = set(), []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def plan(book, chs, sides, target, verbose=False, align_stale=False):
    """→ (jobs, refus)。jobs=(path, rel, leg, ch, src, old, new, span)

    `align_stale`＝档 C：净 alt 也按登记腿的未截断装配对齐（默认关，正当性见模块 docstring）。
    """
    ext = os.path.join(book, "_extract")
    cap_table(ext)                                   # 缺 figure_index 时在这里硬失败
    prime_chapter_kinds(ext)
    jobs, refus = [], []
    for chkey in chs:
        # 🔴 行清单与 `judge` 结果一律取自 `lib.figure_alt_audit.alt_rows`（门控走同一
        # 入口）：这里再数一遍 `img_pairs`、再拼一次 `legs`，门控与工具就能给出两个
        # 「谁写脏了」的集合——p1100 分母对账能闭合靠的正是「两侧同一套取数」。
        rows = alt_rows(ext, book, chkey)
        files = chapter_files(ext, book, chkey)
        targets = writable(files, sides, target)
        pool = defaultdict(lambda: defaultdict(set))     # src -> leg -> {alt}
        by_path = defaultdict(list)
        for r in rows:
            pool[r["src"]][r["leg"]].add(r["alt"])
            by_path[r["path"]].append(r)
        all_alts = [r["alt"] for r in rows]
        # 与写手同一条取数（`embed_figures` 用的是**全书** labels，不带章 key）：
        # 修完的 alt 要能逐字等于将来重 merge 的产物，取数口径就不许自己发明。
        labels_ch = load_fig_labels(ext)
        tag, tag_src = chapter_tag(all_alts, labels_ch)
        # 🔴 前导写法**不在章级拦**：非纯编号形的行走登记腿装配，根本不消费 `tag`，
        # 章级 bail-out 会把它们一起拒掉（Katok 附录实测：alt 全是 `Figure FIGURE F.1.`
        # 时 `RE_ANY_LABEL` 匹配不上「标签词紧贴号」⇒ 整章在行级之前就拒＝静默失明）。
        # 判不出写法的行按行拒，拒因照旧打印。
        if tag and verbose and tag_src != u"本章净alt":
            print(u"    ch%s 前导写法退到%s：%r（本章无净 alt 可参照）" % (chkey, tag_src, tag))
        for leg, rel, p in targets:
            for row in by_path.get(p, ()):
                f, alt, span = row["src"], row["alt"], row["span"]
                if not row["registered"]:
                    refus.append((chkey, u"src 未在本章登记", rel, f))
                    continue
                label, cap, legs, d = (row["label"], row["caption"],
                                       row["legs"], row["d"])
                plain = row["plain"]
                if not dirty(d):
                    if not align_stale:
                        continue
                    if not plain:
                        # 非纯编号形（unnamed 的 `''`、字母号 `F.1`）不许跨腿对齐：登记腿
                        # 的出厂装配对这类 label 不可靠（MSDA 附录B 实测：无名条目是**表**
                        # 附录，装配出的目标是裸标签词 `Figure`，体被清空）。
                        refus.append((chkey, u"登记 label 非纯编号形 ⇒ 不许跨腿对齐",
                                      rel, f))
                        continue
                    # 档 C：串**净**但整片陈旧（写手抄的是老 OCR 视图）⇒ 统一到登记腿的
                    # **未截断**装配。目标形只有一种：不取截断稿（那是把印面改短），不取
                    # 别的腿的串（别的腿与本轮串常常同源同错）。
                    cand = cands_from_caption(cap, label, labels_ch)[-1]
                    if not cand or cand == alt:
                        continue
                    cd = judge(cand, label,
                               [x for x in legs + [("self", alt)]
                                if x[0] != "C"
                                and (x[1] or "").strip() != cand.strip()])
                    if dirty(cd):
                        refus.append((chkey, u"登记腿装配自身脏(%s) ⇒ 先印面取证"
                                      % why(cd), rel, f))
                    elif shortens(cand, label, legs):
                        refus.append((chkey, u"登记腿装配比证人短 ⇒ 禁改短", rel, f))
                    elif bool(CJK.search(strip_lead(cand, label))) != \
                            bool(CJK.search(strip_lead(alt, label))):
                        refus.append((chkey, u"登记腿题注与本轮 alt 语种不同 "
                                             u"⇒ 不跨语种改写", rel, f))
                    elif not strip_lead(cand, label) and strip_lead(alt, label):
                        # 登记题注只剩标签词 ⇒ 装配出的正形体为空。那是**登记侧欠账**，
                        # 不是这张图该没题注 ⇒ 拒（档 C 只许换写法，不许删内容）。
                        refus.append((chkey, u"登记题注只剩标签词 ⇒ 对齐会把体清空", rel, f))
                    else:
                        if verbose:
                            print(u"    %s ch%s ← 档C 登记腿对齐（label=%r）"
                                  % (f, chkey, label))
                        jobs.append((p, rel, leg, chkey, f, alt, cand, span))
                    continue
                if not plain:
                    # 非纯编号形（unnamed 的 `''`、字母号 `F.1`）只有登记腿能裁决：
                    # 出厂写手对着同一个 label 也是这么装配的，所以不违反闸①的初衷
                    # （闸①禁的是「拿别处的散文往这张图上搬」）。
                    # 装配有两种（截断稿 → 全题注），按「禁改短」锁取第一个可用的。
                    cand, cut = None, False
                    for c in cands_from_caption(cap, label, labels_ch):
                        if not c or c == alt or \
                                dirty(judge(c, label, [(u"self", alt)])):
                            continue
                        if shortens(c, label, legs):
                            cut = True
                            continue
                        cand = c
                        break
                    if cand and bool(CJK.search(strip_lead(cand, label))) != \
                            bool(CJK.search(strip_lead(alt, label))):
                        refus.append((chkey, u"登记腿题注与本轮 alt 语种不同 "
                                             u"⇒ 不跨语种改写", rel, f))
                    elif cand:
                        if verbose:
                            print(u"    %s ch%s ← 登记腿出厂装配（label=%r）｜ %s"
                                  % (f, chkey, label, why(d)))
                        jobs.append((p, rel, leg, chkey, f, alt, cand, span))
                    elif cut:
                        refus.append((chkey, u"登记腿装配比证人短 ⇒ 禁改短"
                                             u"（题注本身欠账：先印面取证）", rel, f))
                    else:
                        refus.append((chkey, u"登记 label 非纯编号形(%r)" % label, rel, f))
                    continue
                if not tag:
                    # 原地档与「搬别处 alt」两档都要拿本章前导写法重组串；写法判不出时
                    # 工具**不自造**体例 ⇒ 按行拒（登记腿那一档在上面已经试过，不需要它）。
                    refus.append((chkey, u"本章无可参照的 alt 前缀写法", rel, f))
                    continue
                picked, picked_from, pdef, lang_only = None, None, None, False
                cut = False
                ip = in_place(alt, label, tag, legs)
                if ip is not None:
                    picked, picked_from = ip, u"原地"
                if picked is None:                    # 原地修不适用才去搬来源腿
                    for lg in donor_order(leg):
                        vals = ([cap] if lg == "C" else sorted(pool[f].get(lg, ())))
                        for v in vals:
                            if not v or v == alt:
                                continue
                            num = lead_of(v)
                            if num and num != label:
                                continue      # 号不是本章这张 ⇒ 不搬
                            # 闸③：来源串的**散文**必须先自证清白（粘连词＝OCR 稿，禁回写）；
                            # 图号形制（碎字 / 号后无空格）由下面的重组修掉，不是拒因。
                            if judge(v, label, legs)["jam"]:
                                if pdef is None:
                                    pdef = judge(v, label, legs)
                                continue
                            if lg == "C":
                                # 登记腿＝出厂写手对同一条 caption 的装配 ⇒ 修完 == 将来重
                                # merge；截断稿会改短时退到未截断形（闸⑧）。
                                cands = cands_from_caption(v, label, labels_ch)
                            else:
                                cand = u"%s %s %s" % (tag, label, strip_lead(v, label))
                                # 「搬来的串剥完号什么都不剩」＝来源腿自己没写体，不搬；
                                # 登记腿没这一说：caption 只有标签词时装配出的正形就是
                                # `Figure 10.4`（体为空），Fraleigh 图 3.10 实测那一档。
                                if not strip_lead(cand, label):
                                    continue
                                cands = [cand]
                            # 评来源串时，**它自己**不能进参照表：cand 与 v 是同一名被告
                            # （caption 里的 `betweenthe` 若给自己作证，OCR 粘连稿就顺着
                            # 回写进笔记——p1082 教训②的 500 行全在这一形）。
                            ref_legs = [x for x in legs + [("self", alt)]
                                        if (x[1] or "").strip() != v.strip()]
                            for cand in cands:
                                cd = judge(cand, label, ref_legs)
                                if dirty(cd):
                                    if pdef is None:
                                        pdef = cd
                                    continue
                                if shortens(cand, label, legs):
                                    cut = True
                                    continue      # 闸⑧：搬来的就是截断稿 ⇒ 换下一个来源
                                if bool(CJK.search(strip_lead(alt, label))) != \
                                        bool(CJK.search(strip_lead(v, label))):
                                    lang_only = True
                                    break         # 不跨语种改写（换来源串）
                                picked, picked_from = cand, lg
                                break
                            if picked:
                                break
                        if picked:
                            break
                if picked is None:
                    refus.append((chkey,
                                  u"来源与本轮 alt 语种不同 ⇒ 不跨语种改写" if lang_only
                                  else u"来源腿均是截断稿 ⇒ 禁把印面内容改短"
                                  if cut else
                                  u"无净来源（caption 亦脏：%s）⇒ 先印面取证"
                                  % (u"?" if pdef is None else why(pdef)), rel, f))
                    continue
                if verbose:
                    print(u"    %s ch%s ← 来源腿 %s ｜ %s"
                          % (f, chkey, picked_from, why(d)))
                jobs.append((p, rel, leg, chkey, f, alt, picked, span))
    return jobs, refus


def backup(path, book, stamp, written):
    rel = os.path.relpath(path, book).replace("\\", "/")
    d = os.path.join(book, "_extract", "_bak_clean_figure_alts", stamp)
    os.makedirs(d, exist_ok=True)
    dst = os.path.join(d, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst):
        shutil.copyfile(path, dst)
    written.add(rel)


def selfcheck(book, chs, sides, target, perfile, stamp, align_stale=False):
    """复跑同一判据须归零；改动行只许落在 `<img>` 行；行数与换行符守恒。"""
    left, _ = plan(book, chs, sides, target, align_stale=align_stale)
    bad = 0
    for p, edits in perfile.items():
        rel = os.path.relpath(p, book).replace("\\", "/")
        bak = _read(os.path.join(book, "_extract",
                                 "_bak_clean_figure_alts", stamp, rel))
        now = _read(p)
        if bak.count("\r\n") != now.count("\r\n") or \
                bak.count("\n") != now.count("\n") or \
                len(bak.split("\n")) != len(now.split("\n")):
            bad += 1
            print(u"  自检失败（行数/换行符漂移）：%s" % rel)
            continue
        lb, ln = bak.split("\n"), now.split("\n")
        diff = [i for i, (x, y) in enumerate(zip(lb, ln)) if x != y]
        if len(diff) > len(edits) or any("<img" not in lb[i] for i in diff):
            bad += 1
            print(u"  自检失败（改动面超出 alt 值行）：%s 改动行=%s" % (rel, diff[:6]))
    return len(left), bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book")
    ap.add_argument("chs", nargs="+")
    ap.add_argument("--target", default="units",
                    choices=("units", "delivery", "both"))
    ap.add_argument("--side", action="append", choices=SIDES)
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--align-stale", action="store_true",
                    help=u"档 C：净 alt 也按登记腿未截断装配对齐（须先对该书 caption 印面抽检）")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    book = os.path.abspath(a.book)
    sides = tuple(a.side or SIDES)
    chs = [re.sub(r"^ch", "", c) for c in a.chs]
    jobs, refus = plan(book, chs, sides, a.target, verbose=a.list,
                       align_stale=a.align_stale)
    print(u"命中 %d 处%s alt ｜ 拒 %d 条（target=%s side=%s）"
          % (len(jobs), u"脏或陈旧" if a.align_stale else u"脏",
             len(refus), a.target, u"+".join(sides)))
    per = Counter(u"ch%s/%s" % (j[3], j[2]) for j in jobs)
    print(u"  分布：" + u"  ".join(u"%s=%d" % (k, v) for k, v in sorted(per.items())))
    cap = len(jobs) if a.list else 20
    for j in jobs[:cap]:
        print(u"  %s ch%s %s\n     旧 %r\n     新 %r"
              % (j[1], j[3], j[4], j[5][:110], j[6][:110]))
    if len(jobs) > cap:
        print(u"  … 另 %d 处（--list 全列）" % (len(jobs) - cap))
    rr = Counter(r[1].split(u"（")[0] for r in refus)
    print(u"  拒因分布：" + u"  ".join(u"%s=%d" % (k, v) for k, v in rr.most_common()))
    for r in (refus if a.list else refus[:12]):
        print(u"  拒 ch%s %s ｜ %s ｜ %s" % (r[0], r[1], r[2], r[3]))
    if len(refus) > 12 and not a.list:
        print(u"  … 另 %d 条" % (len(refus) - 12))
    if not jobs:
        print(u"无可写项。")
        return 0
    if not a.commit:
        print(u"（dry-run，未写盘；--commit 才落）")
        return 0
    stamp = time.strftime("%Y%m%d_%H%M%S")
    written, perfile = set(), defaultdict(list)
    for p, rel, leg, ch, f, old, new, span in jobs:
        perfile[p].append((span, new))
    for p, edits in perfile.items():
        backup(p, book, stamp, written)
        _write(p, splice(_read(p), [(s, e, t) for (s, e), t in edits]))
    left, bad = selfcheck(book, chs, sides, a.target, perfile, stamp, a.align_stale)
    print(u"落盘：改写 %d 处 ｜ 文件 %d 个 ｜ 备份 %d 文件"
          u"（_extract/_bak_clean_figure_alts/%s）｜ 复跑残留 %d ｜ 形制自检失败 %d"
          % (len(jobs), len(perfile), len(written), stamp, left, bad))
    if left or bad:
        print(u"自检未过：还原 = 把备份目录同名文件拷回原位，勿继续复验。")
        return 1
    if a.target in ("units", "both"):
        print(u"提醒：单元正文已变 ⇒ 译侧 src_hash 会漂，跑 "
              u"`tools/resync_src_hash.py <book> <ch>` 再复验 parity。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
