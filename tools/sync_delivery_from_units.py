"""tools/sync_delivery_from_units.py — 把交付章 md 复位成 ``merge(units)``（逐段打印后整文件覆写）。

交付的**形态**有两种，本工具都接：合并件（一章一件 md）与按节拆分件（一章多件 md，
读者成品就是那些节文件）。拆分形态下拼接文本先过**工厂拆分器**拆成节文件，再按文件名
精确配对后逐件复位。

场景：已收官书的**单元**在拼接之后又被改过（闸收紧逼出来的机械修、⑭ 摘/挂 tag、G 层块引用
补围栏、tier-2 照抄改写……），交付 md 还停在旧形 ⇒ 交付不再由单元可复现（「重拼 == 交付」破）。
这类账以前只能一条一条走 :mod:`tools/mirror_unit_line`（它要求「整块除一行外逐行相等」，所以
**一次删除 + 一次插入**的移动形、以及块引用围栏形一律拒改），或干脆违规重 merge。

本工具是那条路的**收口**：不落中间产物（拆分形态只写系统临时目录），直接在内存里跑拼接器
（``merge_units._assemble``，与真实合并**同一个函数**、默认**同样强制门控**），拿拼接结果与
交付逐行差分，把**每一段**差异连同「该行归属哪个单元文件」一起打印出来，`--commit` 时备份在先、
整文件覆写、写后逐字节复核、落账。

🔴 与 mirror_unit_line 的分工：差一行 → 用那个工具（改动面最小）；差多段/移动形/围栏形 →
用本工具，但**必须先读它打印的每一段**并确认单元侧是印面真值。本工具不判断真值方向，它只保证
「交付 == merge(units)」，所以**判错方向时会把错的东西整章印上去**。

安全边界（任一不满足 = 该章拒绝，绝不半写）：
 ① 交付**形态**要对得上：同章前缀下只有一件 md ⇒ 合并件形态，直接对合并件复位；
    匹配到 >1 件 ⇒ 按节拆分形态，把拼接文本喂**工厂拆分器**（``tools/split_chapters.py``）
    拆成节文件，再按**文件名精确配对**（对不上即拒：绝不猜名、绝不改名），逐件复位；
    合并件与节件混放 ⇒ 拒（读者成品形态不唯一）。
 ② 被删除的交付行里的**图 src 必须在新拼接侧仍然存在**（按 src 多重集比，不按整行比）——
    拼接器注入的图单元侧没有 ⇒ 覆写真丢图，拒；同一张图只是被 `> ` 围栏重新包裹（整行形变了、
    src 没变）⇒ 放行，否则「块引用补围栏」这一类账永远复位不了（复变函数论 ch6 例6.20 实测）；
 ③ 门控默认必过（``require_gate=True``；``--no-gate`` 须显式放弃并打印警告）；
 ④ 写盘后逐字节比对 ``交付 == 拼接结果``，不等即非 0 退出（备份仍在）；
 ⑤ 换行风格守恒：按交付文件**自身**的 CRLF/LF 写回，不做全书换行符翻转；
 ⑥ F 层围栏回归守卫：新拼接侧**不得净增** F 层违规（同判据按「去掉行号后的签名」配对，
    份数不够才算新增）—— 整章覆写最怕把别处的排版违规带进来。

落账：每次 ``--commit`` 往 ``<extract>/_delivery_sync_from_units.jsonl`` 追加一行
（章、语种、交付路径、增删行数、每段差异的交付行号与归属单元、备份路径）；
按节拆分形态下**每个节文件一行**。

用法：
    python tools/sync_delivery_from_units.py <extract_dir> <ch> [...] [--all]
            [--side units|units-translate] [--book-dir DIR] [--backup-dir DIR]
            [--no-gate] [--commit]
默认 dry-run（只打印差异段）。退出码：0 = 全部 SAME（或 --commit 后无 REFUSE）；1 = 有差异
（dry-run）/ 拒绝 / 拼接失败 / 复核失败。
"""
import argparse
import difflib
import io
import json
import os
import re
import shutil
import sys
import tempfile
import time
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))
sys.path.insert(0, _HERE)
import lib.boot as boot  # noqa: E402
boot.setup()

from data.book_structure.book_structure import (  # noqa: E402
    chapter_json_path, list_chapter_keys, norm_chapter_key,
    prime_chapter_kinds, unit_dir_name)

sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "flows/write-source/script"))
import merge_units as mu  # noqa: E402
import split_chapters as SC  # noqa: E402

LEDGER = "_delivery_sync_from_units.jsonl"
_IMG_RE = re.compile(r"<img\b", re.I)
_IMG_SRC_RE = re.compile(r'src="([^"]+)"', re.I)
_SHOW = 12          # 每段最多打印多少行（超出只报计数）

# 🔴 F 层围栏回归守卫用判据（20+ 档里取「整件覆写会新增」的 6 档）
# 第 6 档 2026-11-02 补进（Fraleigh《A First Course in Abstract Algebra》ch25 实测）：
# 复位把**交付里有、单元拼接侧没有**的 `---` 删掉，前五档全是围栏 `>` 判据 ⇒ 量不到
# 「`>` 块结束 → 顶层散文缺 `---`」（writing-rules V-F），事后整书 verify 报 `F:2`、rc=1。
# 单元层同样拦不住：那块 `> **Example…**` 的尾行在 `0006_section_25_2.md`、紧跟的散文在
# `0007_desc_D2.md`，`check_unit_quality` 按**单文件**跑 ⇒ 跨单元的这条违规只在**整章
# 上下文**现形（与 `_f_findings` 里记的 `> $$` 同一现象、同一根治口径）。
# ⚠️ 译本侧的「结构继承源本」豁免（`inherited_structure_exemptions`，判据 `i_prose_sep`）
# 需要**配对源 md**，本守卫只看单侧文本 ⇒ 对「删 `---` 后与源本计数相等、verify 本会豁免」
# 的复位偏保守。保守是有意取向：REFUSE 只是分流器（一个字节都不写），拦下后人工裁定，
# 不许为了放行把这一档删掉。
_FV_DIR = os.path.join(os.path.dirname(_HERE), "verify", "format_verify", "script")
_F_BQ_CHECKS = ("check_h_statement_in_blockquote",   # 陈述内容误包 `>`（`> $$` / `> （N）`）
                "check_unlabeled_blockquotes",       # 无合法标签的自由 `>` 块
                "check_excessive_bq_empty_lines",    # 块内连续空 `>` 行 > 1
                "check_displaymath_gt",              # `$$…$$` 内混进 `>`
                "check_nested_blockquotes",          # 嵌套 `> >`
                "check_i_prose_separator")           # `>` 块 → 顶层散文缺 `---`（V-F）


def _f_findings(text):
    """整章文本 → ``{判据名: [违规串]}``（候选与现交付都喂同一批判据）。

    🔴 必须在**整章**上下文里跑：`_h_ext_items` 以 `#` 标题划条目区间，单元文件没有
    标题行 ⇒ 同一处 `> $$` 在单元层**量不到**，合进章以后才现形（2026-10-31 数值分析
    ch6/0030 实测：单元 gate PASS，交付覆写后 verify F 层报 2 处）。
    """
    if _FV_DIR not in sys.path:
        sys.path.insert(0, _FV_DIR)
    import format_verify as fv  # noqa: E402
    fd = tempfile.mkdtemp(prefix="syncf_")
    p = os.path.join(fd, "cand.md")
    out = {}
    try:
        for name in _F_BQ_CHECKS:
            fn = getattr(fv, name, None)
            if fn is None:
                continue
            with io.open(p, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            try:
                out[name] = list(fn(p))
            except Exception as exc:                  # 判据跑不动 ≠ 有回归
                out[name] = []
                print("  ! F 层判据 %s 跑不动（%s），本档不参与回归比对" % (name, exc))
    finally:
        shutil.rmtree(fd, ignore_errors=True)
    return out


def _f_norm(s):
    """去掉**全部**行号再比：覆写会让别处的既有违规整体位移，按原始串比会造出一堆假回归。

    只去第一处行号是不够的——`check_excessive_bq_empty_lines` 的串是
    ``x L12–L15: 2 consecutive …``，第二处行号照样随位移变 ⇒ 同一处违规被误判成「新��」。
    """
    return re.sub(r"L\d+", "L", s)


def _f_new_findings(old_fd, new_fd):
    """新拼接侧**净增**的违规（同判据内按签名逐份消耗，份数不够才算新增）。"""
    delta = []
    for name, items in new_fd.items():
        left = Counter(_f_norm(s) for s in (old_fd.get(name) or []))
        for s in items:
            k = _f_norm(s)
            if left[k] > 0:
                left[k] -= 1
                continue
            delta.append((name, s))
    return delta


def _f_guard(old_text, new_text, label):
    """新拼接侧相对现交付**净增**的 F 层违规。→ [说明串]（空 = 通过）。

    整章/整件覆写最怕把别处的排版违规带进来 ⇒ 写盘前必须过这一关。
    旧侧与新侧喂**同一批判据**，按去掉行号后的签名配对，份数不够才算新增。
    """
    delta = _f_new_findings(_f_findings(old_text), _f_findings(new_text))
    return ["%s ｜ %s: %s" % (label, name, s.strip()) for name, s in delta]


def _norm_ch(raw):
    """``"ch3"`` / ``"appendixA"`` / ``3`` → 契约章键（与 ``merge_units.main`` 同一容错）。"""
    ch = str(raw).strip()
    m = re.match(r"^(?:ch|appendix)(.+)$", ch, re.I)
    if m:
        ch = m.group(1)
    return norm_chapter_key(ch)


def _rb(path):
    with io.open(path, "rb") as f:
        return f.read()


def delivery_target(ext, ch_key, book_dir, units_sub):
    """按拼接器自己的优先级算「merge 会写到哪」：manifest.final_md > 按语种+章名自动生成。

    → (绝对路径 | None, language)
    """
    mpath = os.path.join(ext, mu._ac.OUT_DIR_NAME, units_sub,
                         unit_dir_name(ch_key), "manifest.json")
    if not os.path.isfile(mpath):
        return None, None
    manifest = json.loads(_rb(mpath).decode("utf-8"))
    language = manifest.get("language") or "cn"
    want = (manifest.get("final_md") or "").strip()
    if want:
        return (want if os.path.isabs(want)
                else os.path.join(book_dir, want)), language
    try:
        with open(chapter_json_path(ext, ch_key), encoding="utf-8") as f:
            chapter_name = (json.load(f).get("name") or "")
    except Exception:
        chapter_name = ""
    name = mu._final_md_name(ch_key, language, chapter_name, mu._map_name_en(ext, ch_key))
    return os.path.join(book_dir, name), language


def split_hits(book_dir, target):
    """交付目录下与 ``target`` 同章前缀的 md（>1 个 = 按节拆分形态）。"""
    stem = os.path.basename(target)[:-3]
    pref = stem.split("_", 1)[0] + "_" if "_" in stem else stem
    return [os.path.join(book_dir, n) for n in sorted(os.listdir(book_dir))
            if n.endswith(".md") and n.startswith(pref)]


def _print_hunks(hs):
    for h in hs:
        print("   %s ｜ %s ｜ 拼接侧 %d 行 ｜ 单元 %s"
              % (h["op"], h["where"], len(h["resplice"]),
                 ",".join(h["units"]) or "?"))
        for l in h["resplice"][:_SHOW]:
            print("      + %s" % l[:100])
        if len(h["resplice"]) > _SHOW:
            print("      + …（共 %d 行）" % len(h["resplice"]))
        for l in h["delivery"][:_SHOW]:
            print("      - %s" % l[:100])
        if len(h["delivery"]) > _SHOW:
            print("      - …（共 %d 行）" % len(h["delivery"]))


def hunks(delivery_lines, splice_lines, owners):
    """→ 逐段差异：交付行号、两侧内容、拼接侧各行归属的单元文件名（供人工读真值方向）。

    ``owners[k]`` = 拼接结果第 k 行的归属单元（``merge_units._assemble`` 返回，与正文逐行对齐；
    被 ``merge:false`` 跳过的单元不出现在拼接结果里，故归属只能从拼接侧读）。
    """
    out = []
    sm = difflib.SequenceMatcher(a=delivery_lines, b=splice_lines, autojunk=False)
    for tag, d1, d2, s1, s2 in sm.get_opcodes():
        if tag == "equal":
            continue
        out.append({"op": tag, "delivery_lines": [d1 + 1, d2],
                    "where": ("交付 L%d 之后" % d1 if d1 == d2
                              else "交付 L%d-%d" % (d1 + 1, d2)),
                    "delivery": delivery_lines[d1:d2],
                    "resplice": splice_lines[s1:s2],
                    "units": sorted({u for u in owners[s1:s2] if u})})
    return out


def _img_srcs(lines):
    """行集里的图 ``src`` 多重集（只看含 `<img` 的行；一行多图则各计一次）。

    闸按 **src** 比而不是按整行比：块引用补围栏（`> ` 前缀）会让 `<img` 整行变形而图没丢，
    按整行比会把这类合法复位一律拒死（复变函数论 ch6 例6.20 实测）。
    """
    out = []
    for l in lines:
        if _IMG_RE.search(l):
            out.extend(_IMG_SRC_RE.findall(l))
    return out


def _norm_read(path):
    """读交付件并归一到 ``\\n``。→ (text, sep)；sep = 该文件**自身**的换行风格。"""
    raw = _rb(path)
    sep = "\r\n" if raw.count(b"\r\n") * 2 >= raw.count(b"\n") and b"\r\n" in raw else "\n"
    return raw.decode("utf-8").replace(sep, "\n"), sep


def _delivery_lang(target):
    """合并件名 → 交付语种（``第N章`` / ``附`` / ``补`` → zh，否则 en）。"""
    base = os.path.basename(target)
    return "zh" if base.startswith((u"第", u"附", u"补")) else "en"


def _split_layout(hits):
    """现存拆分件的文件名 → ``(lang, num)``；任一件不是工厂节文件命名 ⇒ None。"""
    langs, nums = set(), set()
    for h in hits:
        k = SC.section_file_key(os.path.basename(h))
        if not k:
            return None
        langs.add(k[0])
        nums.add(k[1])
    if len(langs) != 1 or len(nums) != 1:
        return None
    return langs.pop(), nums.pop()


def _split_candidates(book_dir, target, ch_key):
    """该章的按节拆分件清单。→ (清单, 来源说明)

    主路径：与拼接器会写的合并件**同前缀**的 md（工厂命名 ``第N章_M_…`` / ``ChapterN_M_…``）。
    兜底：合并件名算不出前缀时（契约章名与交付名不一致），按节文件的 ``(语种, 章号)``
    反查（``split_chapters.section_file_key``）。
    """
    hits = split_hits(book_dir, target)
    if len(hits) > 1:
        return hits, u"同前缀"
    try:
        num = int(str(ch_key))
    except (TypeError, ValueError):
        num = None
    if num is not None:
        lang = _delivery_lang(target)
        alt = []
        for n in sorted(os.listdir(book_dir)):
            if not n.endswith(".md"):
                continue
            k = SC.section_file_key(n)
            if k and k[0] == lang and k[1] == num:
                alt.append(os.path.join(book_dir, n))
        if len(alt) > 1:
            return alt, u"节号反查"
    return hits, u"同前缀"


def split_by_factory(merged_text, num, lang):
    """把拼接文本交给**工厂拆分器**拆成节文件。→ ``{文件名: 文本}``（只落临时目录）。

    🔴 不自己实现拆节规则：节界/命名/章首引语归属全归 ``tools/split_chapters.py``
    （那是出厂拆分器），本工具只负责把它的产物与现存交付件**按文件名**对上。
    """
    fd = tempfile.mkdtemp(prefix="sdfu_split_")
    try:
        src_name = ((u"第%d章_合并.md" % num) if lang == "zh"
                    else (u"Chapter%d_merge.md" % num))
        src = os.path.join(fd, src_name)
        with io.open(src, "w", encoding="utf-8", newline="\n") as f:
            f.write(merged_text)
        SC.split_one_file(src, 1, num, lang, dry_run=False, force=True)
        out = {}
        for n in sorted(os.listdir(fd)):
            if n.endswith(".md") and n != src_name:
                with io.open(os.path.join(fd, n), encoding="utf-8", newline=None) as f:
                    out[n] = f.read()
        return out
    finally:
        shutil.rmtree(fd, ignore_errors=True)


def _line_owners(src_lines, src_owners, dst_lines):
    """产出件行 → 归属单元（按行级 diff 把产出件行映射回拼接文本行）。

    拆分器切的是**连续行段**，故归属可由行级匹配块直接读出；匹配不上的行
    （章首 H1 标题、补的空行）归属为空。
    """
    out = [None] * len(dst_lines)
    sm = difflib.SequenceMatcher(a=src_lines, b=dst_lines, autojunk=False)
    for i1, j1, n in sm.get_matching_blocks():
        for k in range(n):
            if i1 + k < len(src_owners):
                out[j1 + k] = src_owners[i1 + k]
    return out


def _write_delivery(path, new_text, sep):
    """按该文件自身的换行风格写回并逐字节复核。→ True/False"""
    with io.open(path, "w", encoding="utf-8", newline=sep) as f:
        f.write(new_text)
    return _rb(path) == (new_text.replace("\n", sep)).encode("utf-8")


def sync_chapter(ext, ch_key, book_dir, side="units", require_gate=True,
                 commit=False, backup_dir=None):
    """→ (状态, 说明)。状态：SAME / DIFF / WRITTEN / REFUSE。"""
    prime_chapter_kinds(ext)
    target, language = delivery_target(ext, ch_key, book_dir, side)
    if target is None:
        return "REFUSE", ("缺 %s/%s/manifest.json（拼接器无从判定交付名）"
                          % (mu._ac.OUT_DIR_NAME, os.path.join(side, unit_dir_name(ch_key))))
    hits, _how = _split_candidates(book_dir, target, ch_key)
    if len(hits) > 1:
        return sync_chapter_split(ext, ch_key, book_dir, side, hits, target,
                                  language, require_gate=require_gate,
                                  commit=commit, backup_dir=backup_dir)
    if not os.path.isfile(target):
        return "REFUSE", "找不到交付 md：%s" % target

    lines, owners = mu._assemble(ext, ch_key, side, clean_cjk=None,
                                 require_gate=require_gate)
    new = "\n".join(lines).rstrip() + "\n"
    old, sep = _norm_read(target)
    if new == old:
        return "SAME", target
    hs = hunks(old.split("\n"), new.split("\n"), owners)
    removed = [l for h in hs for l in h["delivery"]]
    added = [l for h in hs for l in h["resplice"]]
    lost_imgs = Counter(_img_srcs(removed)) - Counter(_img_srcs(added))
    if lost_imgs:
        return "REFUSE", ("要删掉的交付行里的图在新拼接侧不再出现（%s）——单元侧没有这些图，"
                          "覆写会真丢内容" % "、".join(sorted(lost_imgs)))
    bad = _f_guard(old, new, os.path.basename(target))
    if bad:
        return "REFUSE", ("F 层围栏回归守卫拦下（新拼接侧净增违规）：%s" % "；".join(bad[:5]))
    print("%s  %s  %s  (+%d/-%d 行，%d 段，换行=%r)"
          % ("写" if commit else "差", mu.chapter_label(ch_key), os.path.basename(target),
             sum(len(h["resplice"]) for h in hs), len(removed), len(hs), sep))
    _print_hunks(hs)
    if not commit:
        return "DIFF", target

    bdir = backup_dir or os.path.join(ext, "_bak_sync_delivery_from_units")
    stamp = time.strftime("%Y%m%dT%H%M%S")
    dst = os.path.join(bdir, stamp, unit_dir_name(ch_key), os.path.basename(target))
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copy2(target, dst)
    if not _write_delivery(target, new, sep):
        return "REFUSE", ("写后逐字节复核不等（备份 %s）——交付已不是拼接产物，"
                          "请人工比对备份件" % dst)
    rec = {"ts": stamp, "extract": ext, "ch": str(ch_key), "side": side,
           "language": language, "md": os.path.basename(target),
           "newline": sep, "hunks": len(hs),
           "added": sum(len(h["resplice"]) for h in hs), "removed": len(removed),
           "sites": [[h["op"], h["delivery_lines"], h["units"]] for h in hs],
           "backup": dst}
    with io.open(os.path.join(ext, LEDGER), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return "WRITTEN", target


def sync_chapter_split(ext, ch_key, book_dir, side, hits, target, language,
                        require_gate=True, commit=False, backup_dir=None):
    """按节拆分形态的交付复位。→ (状态, 说明)。状态：SAME / DIFF / WRITTEN / REFUSE。

    🔴 与合并件形态的差别只在**产物是节文件**：拼接文本先过工厂拆分器
    （``tools/split_chapters.py``）拆成节文件，再按**文件名精确配对**——
    对不上即拒（绝不猜名、绝不改名：猜名等于悄悄换掉读者的成品文件名）。
    """
    if os.path.isfile(target):
        return "REFUSE", ("该章既有合并件（%s）又有 %d 个节件——形态不唯一，拒绝覆写"
                          % (os.path.basename(target), len(hits)))
    layout = _split_layout(hits)
    if layout is None:
        return "REFUSE", ("拆分件文件名不是工厂节文件命名（%s …）——节号/语种读不出，不猜名"
                          % os.path.basename(hits[0]))
    lang, num = layout

    lines, owners = mu._assemble(ext, ch_key, side, clean_cjk=None,
                                 require_gate=require_gate)
    merged = "\n".join(lines).rstrip() + "\n"
    merged_lines = merged.split("\n")
    produced = split_by_factory(merged, num, lang)
    exist = set(os.path.basename(h) for h in hits)
    got = set(produced)
    if got != exist:
        return "REFUSE", ("工厂拆分产物与现存交付件**文件名对不上**（缺：%s ／ 多：%s）"
                          "——不猜名不改名，请人工核对后再来"
                          % ("、".join(sorted(exist - got)) or "无",
                             "、".join(sorted(got - exist)) or "无"))

    # 第一遍：全部件先过闸 —— 任一件不过 ⇒ 整章拒，绝不半写。
    plan = []
    for name in sorted(produced):
        path = os.path.join(book_dir, name)
        old, sep = _norm_read(path)
        new = produced[name]
        if new == old:
            continue
        owners_f = _line_owners(merged_lines, owners, new.split("\n"))
        hs = hunks(old.split("\n"), new.split("\n"), owners_f)
        removed = [l for h in hs for l in h["delivery"]]
        added = [l for h in hs for l in h["resplice"]]
        lost = Counter(_img_srcs(removed)) - Counter(_img_srcs(added))
        if lost:
            return "REFUSE", ("%s：要删掉的交付行里的图在新拼接侧不再出现（%s）——"
                              "单元侧没有这些图，覆写会真丢内容"
                              % (name, "、".join(sorted(lost))))
        bad = _f_guard(old, new, name)
        if bad:
            return "REFUSE", ("F 层围栏回归守卫拦下 %s（新拼接侧净增违规）：%s"
                              % (name, "；".join(bad[:5])))
        plan.append((name, path, old, new, sep, hs, removed, added))
    if not plan:
        return "SAME", hits[0]

    for name, _path, _old, _new, sep, hs, removed, _added in plan:
        print("%s  %s  %s  (+%d/-%d 行，%d 段，换行=%r)"
              % ("写" if commit else "差", mu.chapter_label(ch_key), name,
                 sum(len(h["resplice"]) for h in hs), len(removed), len(hs), sep))
        _print_hunks(hs)
    if not commit:
        return "DIFF", plan[0][1]

    bdir = backup_dir or os.path.join(ext, "_bak_sync_delivery_from_units")
    stamp = time.strftime("%Y%m%dT%H%M%S")
    for name, path, _old, _new, _sep, _hs, _removed, _added in plan:
        dst = os.path.join(bdir, stamp, unit_dir_name(ch_key), name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(path, dst)
    for name, path, old, new, sep, hs, removed, added in plan:
        dst = os.path.join(bdir, stamp, unit_dir_name(ch_key), name)
        rec = {"ts": stamp, "extract": ext, "ch": str(ch_key), "side": side,
               "language": language, "md": name, "form": "split",
               "newline": sep, "hunks": len(hs),
               "added": sum(len(h["resplice"]) for h in hs),
               "removed": len(removed),
               "sites": [[h["op"], h["delivery_lines"], h["units"]] for h in hs],
               "backup": dst}
        if not _write_delivery(path, new, sep):
            return "REFUSE", ("写后逐字节复核不等（备份 %s）——交付已不是拼接产物，"
                              "请人工比对备份件" % dst)
        with io.open(os.path.join(ext, LEDGER), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return "WRITTEN", plan[0][1]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("extract_dir")
    ap.add_argument("chs", nargs="*", help="章键（数字或字母附录，可带 ch 前缀）；配 --all 可省")
    ap.add_argument("--all", action="store_true", help="按契约章序处理全部章")
    ap.add_argument("--side", default="units", choices=["units", "units-translate"])
    ap.add_argument("--book-dir", default=None, help="交付所在目录（默认 extract 的上一级）")
    ap.add_argument("--backup-dir", default=None)
    ap.add_argument("--no-gate", action="store_true",
                    help="跳过拼接前的单元门控（默认必过）")
    ap.add_argument("--commit", action="store_true", help="写盘（默认 dry-run）")
    a = ap.parse_args()
    ext = os.path.abspath(a.extract_dir)
    book = os.path.abspath(a.book_dir or os.path.dirname(ext))
    if a.no_gate:
        print("!! --no-gate：未跑单元门控就比对，可能把没改好的单元印进成品")
    prime_chapter_kinds(ext)
    chs = [_norm_ch(c) for c in a.chs]     # 容错 "ch3"/"appendixA" → 契约键，同 merge_units
    if a.all:
        chs = list_chapter_keys(ext)
    if not chs:
        sys.exit("给章键或 --all")
    tally = {}
    for ch in chs:
        if a.side != "units" and not os.path.isfile(os.path.join(
                ext, mu._ac.OUT_DIR_NAME, a.side, unit_dir_name(ch), "manifest.json")):
            tally["NO-UNITS"] = tally.get("NO-UNITS", 0) + 1
            continue
        try:
            st, note = sync_chapter(ext, ch, book, a.side,
                                    require_gate=not a.no_gate,
                                    commit=a.commit, backup_dir=a.backup_dir)
        except (SystemExit, Exception) as e:  # 门控拒拼 / 契约缺件：单章失败不拖垮批次
            st, note = "SPLICE-FAIL", "%r" % (e,)
        tally[st] = tally.get(st, 0) + 1
        if st in ("REFUSE", "SPLICE-FAIL"):
            print("!! %s %s：%s" % (st, mu.chapter_label(ch), note))
        elif st == "SAME":
            print("ok SAME %s：%s" % (mu.chapter_label(ch), os.path.basename(note)))
    print("\n== %s：%s" % (a.side, "  ".join("%s=%d" % kv for kv in sorted(tally.items()))))
    clean = tally.get("SAME", 0) + tally.get("NO-UNITS", 0) == len(chs)
    return 0 if (clean or (a.commit and not tally.get("REFUSE")
                           and not tally.get("SPLICE-FAIL"))) else 1


if __name__ == "__main__":
    sys.exit(main())
