"""tools/sync_unit_from_delivery.py — 把**交付 md 的对应跨度**机械回灌进过期单元（不重 merge）。

场景与真值方向都和 :mod:`tools/mirror_unit_line.py` 相反：那一支修「单元对、交付错」的单行；
本支修「交付对、单元错」的整块。实测形态（2026-10-30 数值分析 11 处）——单元正文留着**写源期
的 OCR 残渣或串挂**（`宝理6（选代法收敛的充分条件）设有线性万栓组`、`sln10 11.99, R(B。)即取k=`、
`**例9 已知一组实验数据如表3-1，求它的拟合曲线**：表3-1实验数据2 4 1 5 $x_{i}$…`），而交付 md
后来按印面做过清理与回补。这种行**禁止**用 mirror_unit_line 反向往交付上印（那会把残渣印进成品），
合法出口 = 只改单元正文，让单元重新成为交付的逐字镜像。

为什么值得单独一条通道：收官书禁重 merge，单元与交付从此只能一对一地手工对齐；单元侧留着
残渣＝下一个人重拼/重译时把错的东西印回去，且 U 层「正文读不到」永远销不掉。

🔴 动手前必须**印面取证确认交付侧是真相**（`--evidence` 记进台账）。判据不替你取证，只拦
「把单元独有内容抹掉」这一种不可逆伤害：单元里出现、而**跨度圈不住**的实质行（归一化后 ≥
``_MIN_LOSS_CHARS`` 字符）= 候选内容丢失，未给 ``--evidence`` 一律拒绝。对照集取**跨度**而不是
整份交付——写盘写的是跨度，拿整份交付当对照集时「交付别处还有这句」会放行一次静默截断。
命中但**在交付别处找得到**的行会额外标出处，那是 `--span` 取短了的信号（该改跨度而不是补证据）。

跨度边界（默认按条头自动定，也可 `--span <md文件名>:<起>:<止>` 人工给，用于 `desc` 伪键）：
 ① 起点 = 交付里第一条归一形匹配 `^>?\\*\\*<key>(?!\\d)` 的行（`(?!=\\d)` 防 `定理1` 命中 `定理10`）；
 ② 终点 = 下一条该章条头（按 manifest 全部 `item` 键）或独立 `---` 分隔线；
 ③ 起点必须**恰落在一个交付文件**里——0 个 = 拒绝（键/交付条头形不符），多个 = 拒绝（位置不唯一）；
 ④ 复制时剥掉块内 `---`（`merge_units` 的结构件，不是正文；留在单元里会被再插一遍）。

写盘前后各一道复核：首行标记逐字节不变、除该单元外不写任何文件、写后单元非空行序列与跨度
（同样剥 `---`）逐行归一相等。manifest 的 `name`/`content` 是**契约派生值**、`hash` 无消费方，
本工具都不动（动了就是假账）。默认 dry-run。退出码：拒绝 > 0 = 1；写后复核不过 = 1。

用法：
    python tools/sync_unit_from_delivery.py <extract_dir> <ch> <unit_file> [...] \\
            --evidence "印面取证结论" [--span md.md:L1:L2] [--side units] \\
            [--book-dir DIR] [--backup-dir DIR] [--commit]
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

_MIN_LOSS_CHARS = 12          # 短于 12 个归一字符的行 = 数学碎片/残渣，不算「实质内容」
_SEP_RE = re.compile(r"^-{3,}$")   # `merge_units` 的分隔线：结构件，不是正文


def _lang_of_manifest(man):
    """manifest `language` → md 语种（cn/en）。认不出来 = None（调用方拒绝，不猜文件）。

    交付侧只有 `第N章_*` / `ChapterN_*` 两种命名形（见 `verify_chapter.chapter_md_groups`），
    所以语种也只认这两档；`ja`/`ru` 之类返回 None = 本工具不接（宁可不调）。
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


def chapter_md_files(book_dir, ch, lang):
    """该章该语种的交付 md 文件列表（走 verify 的组识别入口，按节拆分也认）。"""
    from verify.script import verify_chapter as VC
    prime_chapter_kinds(os.path.join(book_dir, "_extract"))
    hit = []
    for grp in VC.chapter_md_groups(book_dir, ch) or []:
        if VC._group_lang(grp) == lang:
            hit.extend(grp)
    return hit


def item_keys(man):
    """该章全部 `item` 条头键，按 manifest 顺序（= 印面顺序），长的排前面供交替正则用。"""
    ks = []
    for u in man.get("units") or []:
        if u.get("type") == "item":
            k = norm_text(str(u.get("key") or ""))
            if k and k not in ks:
                ks.append(k)
    return sorted(ks, key=len, reverse=True)


def head_key(line, keys):
    """交付行 → 它开头的条头键（不是条头给 None）。`(?<!\\d)` 防 `定理1` 认上 `定理10`。"""
    n = norm_text(line)
    if _SEP_RE.match(n):
        return None
    for k in keys:
        if re.match(r"^>?\*\*%s(?!\d)" % re.escape(k), n):
            return k
    return None


def find_span(md_paths, keys, key):
    """→ (path, 起始行号(1-based), 结束行号(1-based, 不含), 行) 或 (None, 原因)。

    起点按 `key` 认，终点按「下一条条头或 `---`」认；块内空行原样带走（写手排版属交付侧事实）。
    """
    nk = norm_text(str(key))
    hits = []
    for mp in md_paths:
        lines, _eol = split_eol(read_text(mp))
        start = None
        for i, l in enumerate(lines):
            if head_key(l, keys) == nk and nk in norm_text(l):
                start = i
                break
        if start is None:
            continue
        j = start + 1
        while j < len(lines):
            s = norm_text(lines[j])
            if _SEP_RE.match(s):
                break
            hk = head_key(lines[j], keys)
            if hk and hk != nk:
                break
            j += 1
        hits.append((mp, start, j, lines[start:j]))
    if len(hits) == 1:
        mp, a, b, blk = hits[0]
        return {"path": mp, "no": a + 1, "end": b, "lines": blk, "n": len(hits)}
    if not hits:
        return {"err": "交付里没有以条头 `%s` 开头的行（键名与交付条头形不符 → 用 --span 人工给区间）"
                        % nk}
    return {"err": "条头 `%s` 在 %d 个交付文件里都认到起点，位置不唯一" % (nk, len(hits))}


def manual_span(md_paths, spec):
    """`--span <md文件名>:<起>:<止>`（行号 1-based，含两端）→ 同 find_span 的 dict。"""
    name, a, b = spec.rsplit(":", 2)
    a, b = int(a), int(b)
    mp = [p for p in md_paths if os.path.basename(p) == name]
    if len(mp) != 1:
        return {"err": "--span 的 md 文件名在该章交付组里认不到/不唯一：%s" % name}
    lines, _eol = split_eol(read_text(mp[0]))
    if not (1 <= a <= b <= len(lines)):
        return {"err": "--span 行区间越界：%s %d..%d（文件 %d 行）"
                        % (name, a, b, len(lines))}
    return {"path": mp[0], "no": a, "end": b, "lines": lines[a - 1:b], "n": 1}


def body_lines(unit_path):
    """单元正文行（首行标记剥掉，其余原样，含空行）。"""
    raw, _eol = split_eol(read_text(unit_path))
    if raw and is_unit_marker_line(raw[0]):
        raw = raw[1:]
    return raw


def strip_sep(lines):
    """跨度 → 进单元的行：独立 `---` 剥掉（merge 的结构件），尾部空行剥掉。"""
    out = [l for l in lines if not _SEP_RE.match(norm_text(l))]
    while out and not out[-1].strip():
        out.pop()
    return out


def unit_lines_outside(rows, norm_set):
    """单元里出现、而 `norm_set` 里找不到的**实质行**（归一后 ≥ ``_MIN_LOSS_CHARS`` 字符）。

    同步写盘的是跨度，所以判据的对照集也必须是跨度——拿整份交付当对照集时，一条只存在于
    跨度之外的行会「找得到」→ 闸放行 → 写盘把它从单元里抹掉（2026-10-30 数值分析 ch6
    定理12 实测：`--span` 少取 4 行，`$$…<0$$` 与收尾散文都不在跨度内，dry-run 照样通过）。
    """
    out = []
    for l in rows:
        n = norm_text(l)
        if not n or _SEP_RE.match(n) or len(n) < _MIN_LOSS_CHARS:
            continue
        if n not in norm_set:
            out.append(l)
    return out


def write_unit(unit_path, new_body, backup_dir):
    """备份 → 只重写正文（首行标记逐字节保留）→ 写后复核标记未动、行数与跨度一致。"""
    raw, eol = split_eol(read_text(unit_path))
    marker = raw[0] if (raw and is_unit_marker_line(raw[0])) else None
    tail_eol = eol if raw and raw[-1] == "" else ""     # 保留原文件末尾换行形
    parts = ([marker] if marker is not None else []) + list(new_body)
    if not os.path.isdir(backup_dir):
        os.makedirs(backup_dir)
    dst = os.path.join(backup_dir, os.path.basename(unit_path))
    if not os.path.exists(dst):
        shutil.copy2(unit_path, dst)
    with io.open(unit_path, "w", encoding="utf-8", newline="") as f:
        f.write(eol.join(parts) + tail_eol)
    after, _e2 = split_eol(read_text(unit_path))
    if marker is not None and after[0] != marker:
        raise SystemExit("[sync_unit_from_delivery] 🔴 首行标记被改动：%s" % unit_path)
    got = after[1:] if marker is not None else after
    if [norm_text(x) for x in got if norm_text(x)] != \
       [norm_text(x) for x in new_body if norm_text(x)]:
        raise SystemExit("[sync_unit_from_delivery] 🔴 写后复核非空行序列不等：%s" % unit_path)
    return dst


def main(argv=None):
    ap = argparse.ArgumentParser(prog="sync_unit_from_delivery.py")
    ap.add_argument("extract_dir")
    ap.add_argument("ch")
    ap.add_argument("files", nargs="+", help="单元文件名（该章 units 目录内）")
    ap.add_argument("--side", default="units", choices=["units", "units-translate"])
    ap.add_argument("--book-dir", default=None, help="交付 md 所在目录（默认 extract 的父目录）")
    ap.add_argument("--span", default=None, help="人工跨度 `<md文件名>:<起>:<止>`（单次一个文件时用）")
    ap.add_argument("--evidence", default=None, help="印面取证结论（有单元独有实质行时必填）")
    ap.add_argument("--backup-dir", default=None)
    ap.add_argument("--commit", action="store_true", help="写盘（默认 dry-run）")
    a = ap.parse_args(argv)

    if a.span and len(a.files) != 1:
        raise SystemExit("[sync_unit_from_delivery] --span 只配单个单元文件（一次一条）")
    ext = a.extract_dir
    prime_chapter_kinds(ext)
    book = a.book_dir or os.path.dirname(os.path.normpath(ext))
    udir = os.path.join(ext, "book_structure", a.side, unit_dir_name(a.ch))
    man_path = os.path.join(udir, "manifest.json")
    if not os.path.isfile(man_path):
        raise SystemExit("[sync_unit_from_delivery] 缺 manifest：%s" % man_path)
    man = json.load(io.open(man_path, encoding="utf-8"))
    lang = _lang_of_manifest(man)
    if not lang:
        raise SystemExit("[sync_unit_from_delivery] manifest 无 language，拿不到交付侧（不猜文件）")
    mds = chapter_md_files(book, a.ch, lang)
    if not mds:
        raise SystemExit("[sync_unit_from_delivery] 章 %s 语种 %s 没有交付 md" % (a.ch, lang))
    keys = item_keys(man)
    recs = {str(u.get("file")): u for u in (man.get("units") or [])}
    backup_dir = a.backup_dir or os.path.join(
        ext, "_bak_sync_unit_from_delivery", time.strftime("%Y%m%dT%H%M%S"))
    ledger = os.path.join(ext, "_sync_unit_fixes.jsonl")

    done = rej = 0
    for fn in a.files:
        u = recs.get(fn)
        if not u:
            print("!! %s：manifest 里没有这条记录" % fn)
            rej += 1
            continue
        upath = os.path.join(udir, fn)
        if not os.path.isfile(upath):
            print("!! %s：单元文件不存在" % fn)
            rej += 1
            continue
        # ── 跨度
        sp = manual_span(mds, a.span) if a.span else find_span(mds, keys, u.get("key"))
        if sp.get("err"):
            print("!! %s（key=%s）：%s" % (fn, u.get("key"), sp["err"]))
            rej += 1
            continue
        blk = strip_sep(sp["lines"])
        if not blk:
            print("!! %s：跨度 L%d..L%d 是空的" % (fn, sp["no"], sp["end"]))
            rej += 1
            continue
        # ── 内容丢失闸（对照集 = **跨度**；整份交付只用来分辨「跨度取短」与「单元独有」）
        md_at = {}
        for mp in mds:
            for i, l in enumerate(split_eol(read_text(mp))[0], 1):
                n = norm_text(l)
                if n and n not in md_at:
                    md_at[n] = "%s L%d" % (os.path.basename(mp), i)
        body = body_lines(upath)
        blk_norm = set(norm_text(l) for l in blk)
        lost = unit_lines_outside(body, blk_norm)
        if lost and not a.evidence:
            print("!! %s：单元有 %d 条实质行落在跨度之外，同步会抹掉它们——"
                  "先按印面确认这些行确实不该留（或把 --span 取全），再带 --evidence 来"
                  % (fn, len(lost)))
            for l in lost[:6]:
                at = md_at.get(norm_text(l))
                print("     U｜%s%s" % (l[:120], "　←该句在交付 %s，跨度没圈进来" % at if at else ""))
            rej += 1
            continue
        old = [l for l in body if norm_text(l)]
        same = sum(1 for l in old if norm_text(l) in blk_norm)
        print("%s %s（key=%s）← %s L%d..L%d ｜ 单元非空 %d 行 → 跨度非空 %d 行 ｜ 已等 %d 行"
              % ("已改" if a.commit else "拟改", fn, u.get("key"),
                 os.path.basename(sp["path"]), sp["no"], sp["end"], len(old),
                 len([l for l in blk if norm_text(l)]), same))
        if not a.commit:
            done += 1
            continue
        dst = write_unit(upath, blk, backup_dir)
        io.open(ledger, "a", encoding="utf-8").write(json.dumps({
            "ts": time.strftime("%Y%m%dT%H%M%S"), "extract": ext, "ch": a.ch,
            "side": a.side, "file": fn, "id": u.get("id"), "key": u.get("key"),
            "md": os.path.basename(sp["path"]), "span": [sp["no"], sp["end"]],
            "old_lines": len(old), "new_lines": len([l for l in blk if norm_text(l)]),
            "dropped_unit_only": len(lost), "evidence": a.evidence, "backup": dst,
        }, ensure_ascii=False) + "\n")
        done += 1
    print(("[sync_unit_from_delivery] %s：%d 条 / 拒绝 %d 条%s"
           % ("已写盘" if a.commit else "dry-run", done, rej,
              ("　备份 " + backup_dir) if a.commit and done else "")))
    return 1 if rej else 0


if __name__ == "__main__":
    sys.exit(main())
