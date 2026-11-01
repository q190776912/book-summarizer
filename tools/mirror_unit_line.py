"""tools/mirror_unit_line.py — 把**单元**里某一行的正文机械镜像到交付 md 的对应行（不重 merge）。

场景：已收官书的交付 md 与单元正文**单行**脱钩——U 层报「正文读不到」，逐行差分证明整块
只差一行（2026-10-30 数值分析实测 36 处：单元写 `> **例1 求解线性方程组**：`，交付写
`> **例1：求解线性方程组**：`，标签后被多插一个 `：`，而印面是 `例2设有矩阵序列` 这种
「标签直正文」形）。这类书**禁止重 merge**（交付是读者已拿到的成品，重拼会带动全书其他章），
合法出口 = 只改那一行。

真值方向固定为 **单元 → 交付**。动手前必须先按印面取证确认单元侧是真相；若真相在交付侧
（单元过期/带 OCR 残渣），本工具会把过期内容印上去——那种行要走「改单元正文 + 重同步
manifest 摘要」，不是这里。

每条镜像必须同时满足，任一不满足 = 该条拒绝（其他条照常、绝不半写）：
 ① 对齐唯一：单元正文行与目标 md 文件的**非空行序列**之间，只有一个偏移量能做到
   「除一处外逐行相等」，且相等行数 ≥ ``_MIN_MATCHED``（单元块跨节文件时偏移会出界 → 拒绝）；
 ② 差异段数：那一行的**原文**（非归一化）difflib 默认只剩 1 段 op——对齐用归一化空间
   （交付做过空行整理），落笔用原文，所以两侧多余的空格/缩进会把它逼成多段而拒绝。
   多段而整块仍唯一对齐（如 GM 一行里两处 `(1.1)` 同形回指，2026-10-31 实测）时，
   须显式加 ``--multi-hunk``：它不放宽 ①③，只把「一行里改多处」从拒绝改为**逐段打印后照单元整行覆写**；
 ③ 只改那一行：写盘前后比对，其余每一行必须逐字节相同，行数与换行风格守恒。
``--commit`` 后立刻用同一判据复核，mismatch 必须归 0（否则报异常非 0 退出）。

用法：
    python tools/mirror_unit_line.py <extract_dir> <ch> <unit_file> [...] [--commit]
            [--side units|units-translate] [--book-dir DIR] [--backup-dir DIR]
            [--delete-line | --delete-blank-line | --delete-tag-line N [--delete-tag-line M …]
             | --fill-tag-line] [--multi-hunk]
默认 dry-run（只打印将要改的行与差异段）。退出码：dry-run 有拒绝 = 1；写盘后残差 ≠ 0 = 1。

``--delete-line`` 是另一种形：单元侧那一行**已经整行消失**（``deregister_formula_tags``
摘掉独占一行的 ``\\tag{}`` 时连同该行一起删），交付必须跟着**少一行**而不是改一行。
判据见 :func:`align_deletes`：交付比单元多的每一行都必须是「整行只有一个 ``\\tag``」且
前后都接得上单元行，全部候选偏移须指向同一组行，删完后须与单元逐行相等，否则整条拒。
一个单元里摘掉**多行**独占 ``\\tag`` 是一等形态（2026-10-31 数学分析 ch18 实测两行），
由 :func:`mirror_delete_all` 一次算全组、计划期先复核再落笔。
写盘后复核「行数 −N、其余每行逐字节相同、再用 :func:`align` 归零」。

``--delete-tag-line N`` 是 :func:`align_deletes` **结构性拿不到齐**时的定点出口（2026-10-31
Fraleigh ch23 英文侧实测：块的 ``>`` 围栏与单元不同形 → 候选偏移 37 个，那条路要求「除 tag
行外逐行相等」，永远凑不平）。它**放弃整块对齐**，改由三件独立证据定死待删行，缺一即拒：
 ① 本章摘除台账 ``_extract/_formula_tag_deregistrations.jsonl`` 里记着 ``N``
   （:func:`ledger_deregistrations`）——没有「单元侧确实摘过这个号」的账，就没有删交付的资格；
 ② 传入的单元文件正文**任意位置**都不再写 ``\\tag{N}``（:func:`units_still_hold_tag`）；
 ③ 该章该语种的全部交付文件里，「整行只有 ``\\tag{N}``」的行**恰好一处**
   （:func:`tag_delete_plan`；0 处 = 已删过、幂等不写，≥2 处 = 位置不唯一、真拒）。
删除仍走 :func:`apply_delete`（备份先于写、行数 −1、其余每行逐字节相同），写后按 ③ 复核归零。
块里残留的**非 tag** 漂移由 :func:`residual_drift` 打印出来并报「本模式不改」——别让一次
成功的删除盖住「这块交付整体还和单元不同形」这个更大的欠账。

``--fill-tag-line`` 是 ``--delete-line`` 的**反向**形：单元有独占一行的 ``\\tag``、交付**没有**
（2026-10-31 Gelfand–Manin ch1 ``0050_item_1_4-1.md`` 的 ``\\tag{2}``：印面 p24 右栏确有其号、
契约与 manifest 都在账，交付里那一行被拼接期吃掉，只留一个空行占位）。判据见
:func:`align_fills`：单元比交付多的每一行都必须是「整行只有一个 ``\\tag``」且前后都接得上交付行，
且交付在那个位置**恰好一个空行**可落（行数守恒是本工具的硬不变量，插不进第二行 → 拒），
全部候选偏移须指向同一组落笔点，补完后须与单元逐行相等。
"""
import argparse
import difflib
import io
import json
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lib.boot as boot  # noqa: E402
boot.setup()

from data.book_structure.book_structure import prime_chapter_kinds, unit_dir_name  # noqa: E402
from lib.unit_markers import is_unit_marker_line  # noqa: E402
from lib.unit_order import norm_text  # noqa: E402  （与 U 层同一个归一化空间）

_MIN_MATCHED = 2          # 少于 2 行相等不足以钉住位置（= 短块的「结构上量不到」，别猜）
_MIN_UNIQUE_CHARS = 24    # 只有一行相等时，该行归一化须够长且全篇唯一才可信
_SEP_RE = re.compile(r"^-{3,}$")   # `merge_units` 的分隔线：结构件，不是正文


def _seq(lines):
    """→ [(原行号, 归一化文本)]：压掉空行**与 `---` 分隔线**。

    两侧都不是正文行，所以都不进比较序列（交付块内被插入 `---` 是拼接期的结构动作，
    单元文件里没有那一行；把它当正文差，整块就永远「不止差一行」——2026-10-30 数值分析
    ch7 例16 实测：唯一真差是条头多一个 `：`，却因为块内一条 `---` 被判成差 2 行而拒改）。
    """
    out = []
    for i, l in enumerate(lines):
        n = norm_text(l)
        if not n or _SEP_RE.match(n):
            continue
        out.append((i, n))
    return out


def _lang_of_manifest(man):
    """manifest `language` → md 语种（cn/en）。认不出来 = None（调用方拒绝，不猜文件）。

    交付侧只有两种命名形（`第N章_*` / `ChapterN_*`，见 `verify_chapter.chapter_md_groups`），
    所以语种也只认这两档；`ja`/`ru` 之类的原书侧返回 None = 本工具不接（宁可不调）。
    """
    v = str((man or {}).get("language") or "").strip().lower()
    if v.startswith(("zh", "cn", "中", "chi")):
        return "cn"
    if v.startswith(("en",)):
        return "en"
    return None


def read_text(path):
    with io.open(path, encoding="utf-8", newline="") as f:
        return f.read()


def split_eol(text):
    """→ (lines, eol)：按文件**自己的**换行符切，CRLF 文件不掺入 \\r。"""
    eol = "\r\n" if "\r\n" in text else "\n"
    return text.split(eol), eol


def unit_lines(units_dir, fname):
    """→ 单元正文（首行标记剥掉；空行保留原样，归一化序列由调用方现算）。

    取数口径与 U 层 :func:`unit_order._unit_bodies` 一致：标记行识别走
    ``lib.unit_markers.is_unit_marker_line``，比较空间走 ``lib.unit_order.norm_text``。
    """
    path = os.path.join(units_dir, fname)
    if not os.path.isfile(path):
        raise SystemExit("[mirror_unit_line] 单元文件不存在：%s" % path)
    raw, _eol = split_eol(read_text(path))
    if raw and is_unit_marker_line(raw[0]):
        raw = raw[1:]
    return [l.rstrip("\r\n") for l in raw]


def chapter_md_files(book_dir, ch, lang):
    """该章该语种的交付 md 文件列表（走 verify 的组识别入口，按节拆分也认）。"""
    from verify.script import verify_chapter as VC
    prime_chapter_kinds(os.path.join(book_dir, "_extract"))
    hit = []
    for grp in VC.chapter_md_groups(book_dir, ch) or []:
        if VC._group_lang(grp) == lang:
            hit.extend(grp)
    return hit


def _pinned(hit, keep):
    """相等行是否足以钉住位置：≥2 行，或**恰好 1 行**但该行够长且全文件唯一。

    2 行正文的短块永远凑不出「2 行相等」——其中一行正是漂移行，于是「只差一行」这个
    判定对这类块结构性失效（2026-10-30 数值分析 ch3 性质5：条头被多插一个 `：`，第二行
    219 个字符与交付逐字相同，却因 `_MIN_MATCHED` 被拒）。长行 + 唯一出现本身就是位置
    证据（比「两行都相等」更硬），所以放行；短行（`$$` 那种）或重复行照旧拒。
    """
    if len(hit) >= _MIN_MATCHED:
        return True
    if len(hit) != 1:
        return False
    n = hit[0]
    return (len(n) >= _MIN_UNIQUE_CHARS
            and sum(1 for _i, t in keep if t == n) == 1)


def align(unit_raw, md_raw):
    """单元正文 ↔ 交付正文行序列（无空行/无 `---`）→ ``(diff, same, why)``。

    🔴 两侧都先经 :func:`_seq` **压掉空行与分隔线**再按「正文行序号」对齐：交付做过
    V-A 空行整理、拼接期还会在块间插 `---`，两侧结构行本来就不同；若拿单元**原始行号**
    当步长，每多一个空行/分隔线就多算一处 mismatch，「只差一行」永远凑不齐
    （2026-10-30 数值分析首跑实测 32/50 条被这样假拒，含 5 条只差条头数字的行）。
    ``diff`` 里仍回**原行号**，落笔用的是原文行。

    候选偏移从「相等行」反推，再逐个整块打分（``diff`` = 该偏移下对不上的行，
    ``same`` = 逐行相等的行数）。``diff`` 为空 = **已完全对齐**（幂等重跑走这条，
    不再写盘）；恰 1 处且 ``same`` 达标 = 可镜像；多处 / 一个候选都没有 = 拒绝。
    出现两个都能做到「只差一行」的候选即位置歧义 → ``why``（宁可不改，不猜位置）。
    """
    un = _seq(unit_raw)
    keep = _seq(md_raw)
    idx = {}
    for pos, (ri, n) in enumerate(keep):
        idx.setdefault(n, []).append(pos)
    cand = set()
    for p, (k, n) in enumerate(un):
        for pos in idx.get(n, ()):
            cand.add(pos - p)
    good = []
    scored = []
    for off in sorted(cand):
        diff, hit = [], []
        for p, (k, n) in enumerate(un):
            j = off + p
            if j < 0 or j >= len(keep) or keep[j][1] != n:
                diff.append((k, keep[j][0] if 0 <= j < len(keep) else None))
            else:
                hit.append(n)
        same = len(hit)
        scored.append((len(diff), same))
        if not _pinned(hit, keep):
            continue
        if len(diff) == 1:
            good.append((off, diff, same))
        elif not diff:
            return [], same, None
    if good:
        if len(good) > 1:
            return None, 0, "对齐不唯一：%d 个偏移都只差一行（交付里有同形块）" % len(good)
        return good[0][1], good[0][2], None
    worst = min(scored)[0] if scored else len(un)
    return None, 0, ("单元正文在交付里拿不到「只差一行」的对齐（最好偏移仍差 %d 行；"
                     "候选 %d 个）" % (worst, len(cand)))


def one_op(a, b):
    """→ None（多段差异）或 (tag, 单元段, 交付段)。原文比较：多余空格也算一段，逼出拒绝。"""
    ops = hunks(a, b)
    return ops[0] if len(ops) == 1 else None


def hunks(a, b):
    """单元行 ↔ 交付行的**全部**差异段 ``[(tag, 单元段, 交付段), …]``（原文比较）。"""
    return [(t, a[i1:i2], b[j1:j2])
            for t, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes()
            if t != "equal"]


def fmt_hunks(ops, width=40):
    """差异段逐条排版（多段时让人一眼看全，别只看见第一段就下笔）。"""
    return "\n".join("     %s: 交付 %r ← 单元 %r" % (t, m[:width], u[:width])
                     for t, u, m in ops)


_TAG_ONLY_RE = re.compile(r"^>?\\tag\{([^{}]*)\}$")   # 归一化后的「整行只有一个 \tag」形
_FENCE_ONLY_RE = re.compile(r"^>+$")                  # 归一化后的「整行只有块引用围栏」形


def _is_tag_line(norm):
    """归一化行是否为**独占一行**的 ``\\tag{…}``（可带块引用 ``>`` 前缀）。

    待删行必须长成这样，才谈得上是 :func:`deregister_formula_tags.unit_edit` 的独占一行分支
    在交付里留下的痕迹。多出来的**数学行/正文行**不是待删候选（那是整块搬移或改判单元的事），
    所以「删哪几行」由行形状定死，不靠位置猜测。
    """
    return bool(_TAG_ONLY_RE.match(norm))


def _tag_line_number(norm):
    """独占一行 ``\\tag{X}`` 的归一化行 → ``X``；其余形 → ``None``（:func:`_is_tag_line` 的形状档）。"""
    m = _TAG_ONLY_RE.match(norm)
    return m.group(1) if m else None


def _is_blank_fence_line(norm):
    """归一化行是否**整行只剩块引用围栏**（``>`` / ``>>``，正文为空）。

    拼接期偶发在 display 块里多留一行空围栏（2026-10-31 Gelfand–Manin 实测 3 处：
    单元 ``> \\end{CD}`` / ``> $$`` 相邻，交付中间夹一行 ``> ``）。它渲染为空，不是正文，
    但 :func:`norm_text` 把 ``> `` 折成 ``>``（非空）⇒ 它进得了 :func:`_seq` 比较空间，
    于是 :func:`align` 永远「多差一行」。:func:`align_deletes` 的 ``blank`` 档只认这一形，
    数学行/正文行照旧不删。
    """
    return bool(_FENCE_ONLY_RE.match(norm))


_SHAPES = {"tag": _is_tag_line, "blank": _is_blank_fence_line}


def _shape_pred(shapes):
    """形状档名 → 判定函数；认不出来 = 直接崩（不降级成「什么都算」，那等于没有形状闸）。"""
    bad = [s for s in shapes if s not in _SHAPES]
    if bad or not shapes:
        raise SystemExit("[mirror_unit_line] 未知形状档 %r（可选：%s）"
                         % (bad or shapes, " ".join(sorted(_SHAPES))))
    fs = [_SHAPES[s] for s in shapes]
    return lambda n: any(f(n) for f in fs)


def ledger_deregistrations(ext):
    """``<extract>/_formula_tag_deregistrations.jsonl`` → ``{章键: set(号)}``（本册摘过的号）。

    只读、缺文件 = 空表（:func:`_run_tag_delete` 会把「台账无记录」判成拒绝，不是放行）。
    """
    path = os.path.join(ext, "_formula_tag_deregistrations.jsonl")
    out = {}
    if not os.path.isfile(path):
        return out
    with io.open(path, encoding="utf-8") as f:
        for ln in f:
            ln = ln.strip()
            if not ln:
                continue
            try:
                rec = json.loads(ln)
            except ValueError:
                continue
            out.setdefault(str(rec.get("ch_key")), set()).update(
                str(x) for x in (rec.get("numbers") or []))
    return out


def residual_drift(unit_raw, md_lines):
    """剥掉交付里所有「整行只有一个 ``\\tag``」的行后，这块单元 ↔ 交付还差几行 → ``(n, 明细)``。

    :func:`align_deletes` 之所以拒（2026-10-31 Fraleigh ch23 英文侧实测「候选偏移 37 个」），
    正是因为块里**另有**非 ``\\tag`` 的行差异（该书的英文交付是旧流水线拼的，`>` 围栏与单元
    不同形）。定点删行只解决 tag 那一行，其余漂移必须**照印面另行处置**，所以这里把残差打出来，
    别让它被一次成功的删除盖掉。

    口径与 :func:`align` 同源（同 :func:`_seq` 比较空间、同「从相等行反推候选偏移」），但只取
    **差得最少**的那个偏移做报告，不参与放行判定——它是给人看的证据，不是第二道闸。
    """
    un = _seq(unit_raw)
    stripped = [(i, l) for i, l in enumerate(md_lines) if not _is_tag_line(norm_text(l))]
    keep = _seq([l for _i, l in stripped])
    idx = {}
    for pos, (_ri, n) in enumerate(keep):
        idx.setdefault(n, []).append(pos)
    cand = set()
    for p, (_k, n) in enumerate(un):
        for pos in idx.get(n, ()):
            cand.add(pos - p)
    if not cand:
        return len(un), ["     （单元正文在该交付里一行都对不上，须按印面逐行判）"]
    best = None
    for off in sorted(cand):
        rows = []
        for p, (k, n) in enumerate(un):
            j = off + p
            if j < 0 or j >= len(keep) or keep[j][1] != n:
                rows.append("     U｜%s\n     M｜%s" % (
                    unit_raw[k][:84],
                    stripped[keep[j][0]][1][:84] if 0 <= j < len(keep) else "（落在该文件之外）"))
        if best is None or len(rows) < len(best):
            best = rows
    return len(best), best[:6]


def align_deletes(unit_raw, md_raw, shapes=("tag",)):
    """**交付比单元多 K 行**（形状由 ``shapes`` 定）时的对齐 → ``(待删原行号元组, 相等行数, why, 歧义)``。

    动机（2026-10-30 遍历论_孙文祥 ch6 `\\tag{6.2}`；2026-10-31 数学分析 ch18
    `0036_item_18_2-10.md` 同一次摘掉 `1D` **与** `2p`）：`deregister_formula_tags` 摘掉
    独占一行的 `\\tag` 时是**整行删除**，单元少了 K 行，交付必须跟着少 K 行——这不是
    「改一行」，:func:`align` 的常数偏移永远凑不平（差一行 = 后面每行都错位）。早先只许
    跳一次的版本在 K=2 时**给不出合法出口**：走查在第二个多余行上判死，于是闸把收官书的
    唯一修法堵掉，逼出的下一步就是「重 merge」（禁）或手改交付（无复核）。

    判据与 :func:`align` 同族、同样保守，每个候选偏移走一趟「单元序列 ↔ 交付序列」的
    顺序匹配，只接受两种动作：① 逐行相等；② 跳过一个**形状在 ``shapes`` 档内**且**下一行
    立刻接上单元行**的交付行。``shapes`` 取值见 :data:`_SHAPES`：``tag``（默认）= 整行只有一个
    ``\\tag``，``blank`` = 整行只剩块引用围栏。三个不变量：
     · 每个待删行都有局部见证（前一行相等 + 后一行相等）与全局见证（删完后逐行相等）；
     · 单元序列须**全部**匹配（``_pinned`` 达标），相等行数不足以钉位置就整条拒；
     · 所有候选偏移只能指向**同一组**待删行，否则位置歧义 → ``歧义=True``（真拒，
       不能被「已一致」幂等分支吞掉：交付里同时存在带 tag 与不带 tag 的块时，
       后者会让 :func:`align` 报干净）。

    🔴 待删行必须在**走查途中**被发现，不接受「单元全部匹配完之后交付还剩几行」：
    那些行没有位置证据说明它们属于本块——块在交付里重复出现时（2026-10-30 遍历论_孙文祥
    ``第6章_变分原理.md`` 的 D23 display 印了两遍，第二遍无 `\\tag`），干净的第二次出现
    会把**下一块的开头**当候选删掉。
    """
    un = _seq(unit_raw)
    keep = _seq(md_raw)
    pred = _shape_pred(shapes)
    idx = {}
    for pos, (ri, n) in enumerate(keep):
        idx.setdefault(n, []).append(pos)
    cand = set()
    for p, (k, n) in enumerate(un):
        for pos in idx.get(n, ()):
            cand.add(pos - p)
    good = []
    for off in sorted(cand):
        q, skips, hit = off, [], []
        ok = True
        for _p, (k, n) in enumerate(un):
            while q < len(keep) and keep[q][1] != n and pred(keep[q][1]):
                skips.append(keep[q][0])
                q += 1
            if q >= len(keep) or keep[q][1] != n:
                ok = False
                break
            hit.append(n)
            q += 1
        if not ok or not skips or not _pinned(hit, keep):
            continue
        good.append((tuple(skips), len(hit)))
    if not good:
        return None, 0, ("交付里没有「比单元多 %s 行」的唯一对齐（候选偏移 %d 个；"
                         "多出的行若不成这个形状，本工具不删）"
                         % ("/".join(shapes), len(cand))), False
    if len({g[0] for g in good}) > 1:
        return None, 0, "待删行位置不唯一：%d 组候选（%s）" % (
            len(good), " / ".join(" ".join(str(s + 1) for s in g[0]) for g in good[:6])), True
    return good[0][0], good[0][1], None, False


def mirror_delete_all(md_path, unit_raw, shapes=("tag",)):
    """→ (ok, "clean" | [pass, ...] | str)。只判定，不写盘；``pass`` = dict(orig/line/same)。

    一次拿到 :func:`align_deletes` 的全部待删行，在**内存副本**里删完再用 :func:`align`
    复核「逐行相等」；不齐 = **整条拒**（零写入）。这道计划期复核不只是形式：
    写盘是按行逐条删的，若计划本身不成立，逐条删到一半才由 :func:`apply_delete` 的后置
    断言崩掉，会留下半改的文件。

    ``orig`` 是**运行前**文件里的行号（0 基），既是报给人的行号，也是写盘下标——
    按 ``orig`` **从大到小**删，删后面的行不会移动前面行的下标。

    ``"clean"`` = 交付已与单元逐行相等，且文件里**没有任何**待删候选（幂等重跑走这条）。
    """
    md_lines, _eol = split_eol(read_text(md_path))
    skips, same, why, ambiguous = align_deletes(unit_raw, md_lines, shapes)
    if ambiguous:
        return False, why
    if why:
        diff, _s, why2 = align(unit_raw, md_lines)
        if not why2 and not diff:
            return True, "clean"
        return False, why
    work = list(md_lines)
    for i in sorted(skips, reverse=True):
        del work[i]
    diff, _s, why2 = align(unit_raw, work)
    if why2 or diff:
        detail = why2 or ("第 %d 行仍有差异" % (diff[0][1] + 1)
                          if diff[0][1] is not None else "有单元行落在该文件之外（块跨节文件）")
        return False, ("删掉 %d 行后交付仍与单元不齐（%s）：差异不止 tag 行"
                       % (len(skips), detail))
    return True, [{"orig": i, "line": md_lines[i], "same": same} for i in sorted(skips)]


def _blank_above(md_raw, at):
    """交付原文里 ``at`` 之上**恰好一个空行**时返回它的下标，否则 ``None``。

    这是补行的唯一落笔点：行数守恒（:func:`apply_write` 的硬不变量）意味着只能把单元多出的
    那一行**填进**拼接期留下的空位。两个空行 = 填哪个都是猜，且交付仍比单元多一行空结构；
    零个空行 = 真要插行，本工具不接。
    """
    i = at - 1
    while i >= 0 and not md_raw[i].strip():
        i -= 1
    return at - 1 if i + 1 == at - 1 else None


def align_fills(unit_raw, md_raw):
    """**单元比交付多 K 行独占 ``\\tag``、且交付在那儿正好留了一个空行** → ``([(单元行号, 落笔下标)], 相等行数, why, 歧义)``。

    动机（2026-10-31 Gelfand–Manin ch1 ``0050_item_1_4-1.md`` 的 ``\\tag{2}``）：
    :func:`align_deletes` 管的是「单元摘过 ⇒ 交付跟着少一行」，反方向是**拼接期掉的行**——
    交付里 display 块写成 ``$$`` / 数学行 / 空行 / ``$$``，单元里那个位置是 ``\\tag{2}``。
    :func:`align` 的比较空间压掉了空行，所以交付比单元**少**一行，常数偏移同样凑不平
    （实测「最好偏移仍差 4 行」= 1 个真差 + 3 个连锁错位），于是收官书唯一合法出口被堵。

    判据与 :func:`align_deletes` 同族、同样保守，每个候选偏移走一趟「单元序列 ↔ 交付序列」
    顺序匹配，只接受两种动作：① 逐行相等；② 跳过一个**形状为独占 ``\\tag``** 且**下一条
    单元行立刻接上当前交付行**的单元行，落笔点由 :func:`_blank_above` 定死。三个不变量：
     · 单元序列须全部匹配（:func:`_pinned` 达标），相等行数不足以钉位置就整条拒；
     · 每个落笔点都是**恰好一个**空行，且空行两侧都接得上单元行（局部见证）；
     · 所有候选偏移只能指向**同一组**落笔点，否则位置歧义 → ``歧义=True``（真拒，
       不能被「已一致」幂等分支吞掉）。
    """
    un = _seq(unit_raw)
    keep = _seq(md_raw)
    idx = {}
    for pos, (ri, n) in enumerate(keep):
        idx.setdefault(n, []).append(pos)
    cand = set()
    for p, (k, n) in enumerate(un):
        for pos in idx.get(n, ()):
            cand.add(pos - p)
    good = []
    for off in sorted(cand):
        q, hit, fills, ok = off, [], [], True
        for p, (k, n) in enumerate(un):
            if q < len(keep) and keep[q][1] == n:
                hit.append(n)
                q += 1
                continue
            if (_is_tag_line(n) and q < len(keep) and p + 1 < len(un)
                    and un[p + 1][1] == keep[q][1]):
                tgt = _blank_above(md_raw, keep[q][0])
                if tgt is None:
                    ok = False
                    break
                fills.append((k, tgt))
                continue
            ok = False
            break
        if not ok or not fills or not _pinned(hit, keep):
            continue
        good.append((tuple(fills), len(hit)))
    if not good:
        return None, 0, ("交付里没有「单元多独占 \\tag 行、交付留一个空行」的唯一对齐"
                         "（候选偏移 %d 个；多出的行若不是整行 \\tag、或那个位置不是恰好一个空行，"
                         "本工具不补）" % len(cand)), False
    if len({g[0] for g in good}) > 1:
        return None, 0, "落笔点不唯一：%d 组候选（%s）" % (
            len(good), " / ".join(" ".join(str(t + 1) for _k, t in g[0]) for g in good[:6])), True
    return good[0][0], good[0][1], None, False


def mirror_fill_all(md_path, unit_raw):
    """→ (ok, "clean" | [pass, ...] | str)。一次算全组落笔点，计划期先复核再落笔（零半写）。

    ``pass`` = dict(orig=交付落笔下标 / line=单元整行 / old=交付原空行 / same)。
    """
    md_lines, _eol = split_eol(read_text(md_path))
    fills, same, why, ambiguous = align_fills(unit_raw, md_lines)
    if ambiguous:
        return False, why
    if why:
        diff, _s, why2 = align(unit_raw, md_lines)
        if not why2 and not diff:
            return True, "clean"
        return False, why
    work = list(md_lines)
    for k, tgt in fills:
        work[tgt] = unit_raw[k].rstrip()
    diff, _s, why2 = align(unit_raw, work)
    if why2 or diff:
        detail = why2 or ("第 %d 行仍有差异" % (diff[0][1] + 1)
                          if diff[0][1] is not None else "有单元行落在该文件之外（块跨节文件）")
        return False, ("补进 %d 行后交付仍与单元不齐（%s）：差异不止 tag 行"
                       % (len(fills), detail))
    return True, [{"orig": t, "line": unit_raw[k].rstrip(), "old": md_lines[t], "same": same}
                  for k, t in fills]


def tag_delete_plan(mds, num):
    """该章该语种全部交付文件里「整行只有一个 ``\\tag{num}``」的唯一命中 → ``(ok, [(路径, 行号, 原文)] | str)``。

    零命中算 ``(True, [])``（幂等：已删过）；**两处及以上 = 真拒**——同形行可能分属两个块，
    没有单元侧对齐当位置证据时，本模式只认「全章该语种就这一行」。
    """
    hits = []
    for mp in mds:
        raw, _eol = split_eol(read_text(mp))
        for i, l in enumerate(raw):
            if _tag_line_number(norm_text(l)) == num:
                hits.append((mp, i, l))
    if not hits:
        return True, []
    if len(hits) > 1:
        return False, ("交付里「整行只有 \\tag{%s}」有 %d 处（%s）：没有单元侧对齐当位置证据，"
                      "本模式不猜哪一处是待删的"
                      % (num, len(hits),
                         " ".join("%s L%d" % (os.path.basename(p), i + 1) for p, i, _l in hits[:6])))
    return True, hits


def units_still_hold_tag(units_dir, files, num):
    """单元正文里是否仍写着 ``\\tag{num}``（任意位置）→ 命中文件名列表（空 = 单元确实已摘）。

    🔴 这是本模式的**前提检查**而不是可选项：台账说摘了、单元里却还写着，说明账与数据不一致
    （或摘的是别的号），此时删交付就等于「交付比单元少一行」——方向反了，必须拒。
    """
    pat = re.compile(r"\\tag\s*\{\s*%s\s*\}" % re.escape(num))
    bad = []
    for fn in files:
        for l in unit_lines(units_dir, fn):
            if pat.search(l):
                bad.append(fn)
                break
    return bad


def _run_tag_delete(ext, a, mds, udir, backup_dir):
    """``--delete-tag-line N`` 的主循环 → 退出码。三把闸：台账在账、单元已摘、交付唯一命中。

    与 :func:`mirror_delete_all` 的分工：那条走「单元 ↔ 交付逐行对齐」，块里**另有**非 tag
    漂移时结构性拿不齐（Fraleigh ch23 英文侧：候选偏移 37 个）；本模式**放弃整块对齐**，
    改用「台账（号确实被摘过）+ 行形状（整行只有一个 ``\\tag``）+ 全章唯一命中」三件定死
    待删行，删除本身仍走 :func:`apply_delete` 的逐字节后置复核，并**打印**残留漂移。
    """
    acc = ledger_deregistrations(ext)
    rc = 0
    deleted = 0
    for num in a.delete_tag_line:
        if num not in acc.get(str(a.ch), set()):
            print("!! \\tag{%s}：台账（%s）里章 %s 没有摘除记录 → 拒绝。"
                  "先跑 tools/deregister_formula_tags.py 摘单元/契约侧，再来镜像交付。"
                  % (num, os.path.join(ext, "_formula_tag_deregistrations.jsonl"), a.ch))
            rc = 1
            continue
        bad = units_still_hold_tag(udir, a.files, num)
        if bad:
            print("!! \\tag{%s}：单元正文里仍写着这个号（%s）→ 前提不成立（该删的是单元，不是交付）"
                  % (num, " ".join(bad)))
            rc = 1
            continue
        ok, plan = tag_delete_plan(mds, num)
        if not ok:
            print("!! \\tag{%s}：%s" % (num, plan))
            rc = 1
            continue
        if not plan:
            print("     \\tag{%s} 已不在交付里（%d 个交付文件零命中），不写" % (num, len(mds)))
            continue
        mp, mi, line = plan[0]
        unit_raw = unit_lines(udir, a.files[0])
        n_diff, rows = residual_drift(unit_raw, split_eol(read_text(mp))[0])
        print("%s \\tag{%s} → %s L%d ｜ 待删：%r"
              % (("已删" if a.commit else "拟删"), num, os.path.basename(mp), mi + 1, line[:60]))
        if n_diff:
            print("   ⓘ 该块交付与单元另有 %d 处**非 tag** 行差异（本模式不改，须按印面另行处置）："
                  % n_diff)
            for r in rows:
                print(r)
        if a.commit:
            apply_delete(mp, mi, line, backup_dir)
            ok2, plan2 = tag_delete_plan([mp], num)
            if not ok2 or plan2:
                raise SystemExit("[mirror_unit_line] 🔴 删除后 \\tag{%s} 仍在/又出现多处：%s（备份 %s）"
                                 % (num, mp, backup_dir))
            deleted += 1
    print(("[mirror_unit_line] %s：定点删 tag 行 %s ｜ 落笔 %d 行%s"
           % ("已写盘" if a.commit else "dry-run", " ".join(a.delete_tag_line), deleted,
              ("　备份 " + backup_dir) if a.commit and deleted else "")))
    return rc


def apply_delete(md_path, mi, expect, backup_dir):
    """删第 mi 行；备份先于写；写后复核「行数 −1 且其余每一行逐字节相同」。"""
    raw, eol = split_eol(read_text(md_path))
    before = list(raw)
    if mi < 0 or mi >= len(raw):
        raise SystemExit("[mirror_unit_line] 行号越界：%s L%d" % (md_path, mi + 1))
    if raw[mi].strip() != expect.strip():
        raise SystemExit("[mirror_unit_line] 🔴 待删行与取证文本不符（并发会话改过？）：%s L%d"
                         % (md_path, mi + 1))
    del raw[mi]
    if not os.path.isdir(backup_dir):
        os.makedirs(backup_dir)
    dst = os.path.join(backup_dir, os.path.basename(md_path))
    if not os.path.exists(dst):
        shutil.copy2(md_path, dst)
    with io.open(md_path, "w", encoding="utf-8", newline="") as f:
        f.write(eol.join(raw))
    after, _e2 = split_eol(read_text(md_path))
    if len(after) != len(before) - 1:
        raise SystemExit("[mirror_unit_line] 🔴 行数应 −1（%d→%d）：%s"
                         % (len(before), len(after), md_path))
    rebuilt = before[:mi] + before[mi + 1:]
    if rebuilt != after:
        raise SystemExit("[mirror_unit_line] 🔴 除待删行外还有改动：%s" % md_path)
    return dst


def mirror_one(md_path, unit_raw, allow_multi=False):
    """→ (ok, 说明 dict | str)。只做判定与替换文本构造，不写盘（写盘在 apply_write）。

    说明 dict 的 ``status``：``clean`` = 这块本来就逐行相等（无需写），``fix`` = 有一行要镜像。
    ``allow_multi=True``（CLI ``--multi-hunk``）才放行「同一行差多段」：:func:`align` 已经要求
    整块**唯一**偏移、除这一行外逐行相等、且 :func:`_pinned` 达标，所以「拿不准是不是同一行」
    的多段风险已经被它挡在外面；留在这里的风险是**覆写幅度**（一行里改好几处），
    故默认仍拒，并把**全部**差异段打出来让人看完再决定。
    """
    md_lines, _eol = split_eol(read_text(md_path))
    diff, same, why = align(unit_raw, md_lines)
    if why:
        return False, why
    if not diff:
        return True, {"status": "clean", "same": same}
    k, mi = diff[0]
    if mi is None:
        return False, "差异行落在该文件之外（单元块跨节文件，单行镜像不适用）"
    ops = hunks(unit_raw[k].rstrip(), md_lines[mi].rstrip())
    if len(ops) > 1 and not allow_multi:
        return False, ("交付第 %d 行与单元第 %d 行差 %d 段，需人工逐字判"
                       "（确认整行照单元覆写请加 --multi-hunk）：\n%s\n     U｜%s\n     M｜%s"
                       % (mi + 1, k + 1, len(ops), fmt_hunks(ops),
                          unit_raw[k][:90], md_lines[mi][:90]))
    return True, {"status": "fix", "unit_line": k, "md_line": mi, "md_no": mi + 1,
                  "op": ops[0], "ops": ops, "unit": unit_raw[k].rstrip(),
                  "old": md_lines[mi].rstrip(), "same": same}


def apply_write(md_path, mi, new_line, backup_dir):
    """只替换第 mi 行；备份先于第一个写动作；写后复核「其余行逐字节不变 + 行数守恒」。"""
    raw, eol = split_eol(read_text(md_path))
    before = list(raw)
    if mi < 0 or mi >= len(raw):
        raise SystemExit("[mirror_unit_line] 行号越界：%s L%d" % (md_path, mi + 1))
    indent = raw[mi][:len(raw[mi]) - len(raw[mi].lstrip())]
    raw[mi] = indent + new_line.strip()
    if not os.path.isdir(backup_dir):
        os.makedirs(backup_dir)
    dst = os.path.join(backup_dir, os.path.basename(md_path))
    if not os.path.exists(dst):
        shutil.copy2(md_path, dst)      # 同一文件多次镜像：留首轮真身，不覆盖
    with io.open(md_path, "w", encoding="utf-8", newline="") as f:
        f.write(eol.join(raw))
    after, _e2 = split_eol(read_text(md_path))
    if len(after) != len(before):
        raise SystemExit("[mirror_unit_line] 🔴 行数变了（%d→%d）：%s"
                         % (len(before), len(after), md_path))
    touched = [i for i in range(len(before)) if before[i] != after[i]]
    if touched != [mi]:
        raise SystemExit("[mirror_unit_line] 🔴 除目标行外还有 %d 行被改动：%s %s"
                         % (len(touched), md_path, touched[:5]))
    return dst


def main(argv=None):
    ap = argparse.ArgumentParser(prog="mirror_unit_line.py")
    ap.add_argument("extract_dir")
    ap.add_argument("ch")
    ap.add_argument("files", nargs="+", help="单元文件名（该章 units 目录内）")
    ap.add_argument("--side", default="units", choices=["units", "units-translate"])
    ap.add_argument("--book-dir", default=None, help="交付 md 所在目录（默认 extract 的父目录）")
    ap.add_argument("--backup-dir", default=None)
    ap.add_argument("--commit", action="store_true", help="写盘（默认 dry-run）")
    ap.add_argument("--delete-line", action="store_true",
                    help="交付比单元多整行 \\tag（单元侧删过，一行或多行）→ 镜像成删除，不是替换")
    ap.add_argument("--fill-tag-line", action="store_true", dest="fill_tag_line",
                    help="单元比交付多整行独占 \\tag、交付在那个位置留了一个空行（拼接期掉的行）"
                         "→ 把单元那一行填进空行，行数不变")
    ap.add_argument("--delete-blank-line", action="store_true", dest="delete_blank_line",
                    help="交付比单元多「整行只剩块引用围栏」的空行（拼接期残留）→ 同 --delete-line 的走查，"
                         "只把形状档从 \\tag 换成空围栏")
    ap.add_argument("--delete-tag-line", metavar="N", action="append", dest="delete_tag_line",
                    default=[],
                    help="台账驱动定点删：只删交付里「整行只有 \\tag{N}」的唯一那一行，"
                         "要求 N 在本章摘除台账里、且 N 个单元文件正文都不再写 \\tag{N}"
                         "（用于 :func:`align_deletes` 因块内另有非 tag 漂移而拿不齐的书）")
    ap.add_argument("--multi-hunk", action="store_true", dest="multi_hunk",
                    help="同一行差多段时也照单元整行覆写（默认拒；dry-run 会把每一段都打出来）")
    a = ap.parse_args(argv)

    ext = a.extract_dir
    prime_chapter_kinds(ext)          # 🔴 先灌注章 kind 注册表，否则字母章位被算成 appendixX
    book = a.book_dir or os.path.dirname(os.path.normpath(ext))
    udir = os.path.join(ext, "book_structure", a.side, unit_dir_name(a.ch))
    man_path = os.path.join(udir, "manifest.json")
    if not os.path.isfile(man_path):
        raise SystemExit("[mirror_unit_line] 缺 manifest：%s" % man_path)
    with io.open(man_path, encoding="utf-8") as f:
        lang = _lang_of_manifest(json.load(f))
    if not lang:
        raise SystemExit("[mirror_unit_line] manifest 无 language，拿不到交付侧（不猜文件）")
    mds = chapter_md_files(book, a.ch, lang)
    if not mds:
        raise SystemExit("[mirror_unit_line] 章 %s 语种 %s 没有交付 md（检查章键/书名/是否未拼）"
                         % (a.ch, lang))
    backup_dir = a.backup_dir or os.path.join(
        ext, "_bak_mirror_unit_line", time.strftime("%Y%m%dT%H%M%S"))

    if a.delete_tag_line:
        if a.delete_line:
            raise SystemExit("[mirror_unit_line] --delete-tag-line 与 --delete-line 互斥："
                             "前者按台账定点删一行，后者按单元对齐删一组")
        a.delete_tag_line = [str(x).strip() for x in a.delete_tag_line if str(x).strip()]
        return _run_tag_delete(ext, a, mds, udir, backup_dir)

    if a.delete_line and a.delete_blank_line:
        raise SystemExit("[mirror_unit_line] --delete-line 与 --delete-blank-line 互斥："
                         "同一条走查，只是形状档不同，请只给一个")
    if a.fill_tag_line and (a.delete_line or a.delete_blank_line):
        raise SystemExit("[mirror_unit_line] --delete-line/--delete-blank-line 与 --fill-tag-line"
                         " 互斥：前者是交付多一行、后者是交付少一行，方向相反")
    del_walk = a.delete_line or a.delete_blank_line
    shapes = ("blank",) if a.delete_blank_line else ("tag",)

    fixed = clean = rej = 0

    def probe(mp, ur):
        if del_walk:
            return mirror_delete_all(mp, ur, shapes)
        if a.fill_tag_line:
            return mirror_fill_all(mp, ur)
        return mirror_one(mp, ur, allow_multi=a.multi_hunk)

    def recheck(mp, ur):
        return mirror_one(mp, ur, allow_multi=a.multi_hunk)
    for fn in a.files:
        unit_raw = unit_lines(udir, fn)
        if len(_seq(unit_raw)) <= 1:
            print("!! %s：正文行不足，无法钉位置" % fn)
            rej += 1
            continue
        hits = []
        for mp in mds:
            ok, info = probe(mp, unit_raw)
            if ok:
                hits.append((mp, info))
            elif len(mds) == 1:
                print("!! %s：%s" % (fn, info))
        if len(hits) != 1:
            if len(hits) > 1:
                print("!! %s：%d 个交付文件都能对齐，位置不唯一" % (fn, len(hits)))
            elif len(mds) > 1:
                print("!! %s：在 %d 个交付文件里都没拿到「只差一行」对齐" % (fn, len(mds)))
            rej += 1
            continue
        mp, info = hits[0]
        if del_walk or a.fill_tag_line:
            fill = a.fill_tag_line
            if info == "clean":
                print("%-4s %s 已一致（交付与单元逐行相等，不写）" % ("", fn))
                clean += 1
                continue
            for p in info:                              # 按 orig 升序 = 文件从上到下
                if fill:
                    print("%s %s → %s L%d ｜ 相等 %d 行 ｜ 空行 %r ← 单元 %r"
                          % (("已补" if a.commit else "拟补"), fn, os.path.basename(mp),
                             p["orig"] + 1, p["same"], p["old"][:40], p["line"][:40]))
                else:
                    print("%s %s → %s L%d ｜ 相等 %d 行 ｜ 待删：%r"
                          % (("已删" if a.commit else "拟删"), fn, os.path.basename(mp),
                             p["orig"] + 1, p["same"], p["line"][:60]))
            if a.commit:
                for p in reversed(info):                # 先动后面的行，前面行的下标不动
                    if fill:
                        apply_write(mp, p["orig"], p["line"], backup_dir)
                    else:
                        apply_delete(mp, p["orig"], p["line"], backup_dir)
                ok2, info2 = recheck(mp, unit_raw)
                if not (ok2 and info2.get("status") == "clean"):
                    raise SystemExit("[mirror_unit_line] 🔴 %s后复核未归零：%s（备份 %s）→ %s"
                                     % ("补行" if fill else "删除", mp, backup_dir, info2))
            fixed += len(info)
            continue
        if info["status"] == "clean":
            print("%-4s %s 已一致（%d 行逐行相等，不写）"
                  % ("", fn, info["same"]))
            clean += 1
            continue
        for t, us, ms in info["ops"]:
            print("%s %s → %s L%d ｜ 相等 %d 行 ｜ %s: 交付 %r ← 单元 %r"
                  % (("已改" if a.commit else "拟改"), fn, os.path.basename(mp),
                     info["md_no"], info["same"], t, ms[:36], us[:36]))
        if a.commit:
            dst = apply_write(mp, info["md_line"], info["unit"], backup_dir)
            ok2, info2 = recheck(mp, unit_raw)
            if not (ok2 and info2.get("status") == "clean"):
                raise SystemExit("[mirror_unit_line] 🔴 写后复核未归零：%s（备份 %s）→ %s"
                                 % (mp, dst, info2))
        fixed += 1
    print(("[mirror_unit_line] %s：落笔 %d 行 / 已一致 %d 条 / 拒绝 %d 条%s"
           % ("已写盘" if a.commit else "dry-run", fixed, clean, rej,
              ("　备份 " + backup_dir) if a.commit and fixed else "")))
    return 1 if rej else 0


if __name__ == "__main__":
    sys.exit(main())
