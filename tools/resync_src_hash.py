"""tools/resync_src_hash.py — 源单元定稿后再修过时，把 `units-translate/manifest.json` 里的
`src_hash` 快照重同步到**当前**源正文哈希（定点行替换，不重跑 init、不 re-dump JSON）。

为什么需要它：`check_translate_parity` 判据 6 拿「源单元当前哈希」比记录的 `src_hash`，
不等即 FAIL（= 派生后源被改，译文可能基于旧源）。已收官/已交付的书做**形态类**返修
（补 `---`、把标签包进 `>`、公式粘连形归一）时正文必然变，而 `init_translate_units`
这条路走不通：它要求源章门控全绿（返修期常有其他欠账未清）且会把 `final_md` 清零、
重写整份清单。于是唯一正确姿势 = 承认「源仍是真值、译文结构不必跟着变」，只把快照对齐。

🔴 边界：本工具**只**用于「源侧改动不动语义内容」的机械返修。若源正文改了**内容**
（补公式、改数值、重写照抄段），译文与源已真不同步，必须重译该单元，本工具会帮你
掩盖欠账——不要用。判据 6 的 FAIL 正是那件事的告警器。

`hash` 字段（init 时 = src_hash 的另一份快照）没有任何消费者，保持为派生时刻的原样不动；
只改 `src_hash`，审计面最小。清单是 CRLF、无尾换行，故逐行定点替换，禁止整份 re-dump。

用法：
    python tools/resync_src_hash.py <extract_dir> [--ch 1 2 A ...] [--commit]
默认 dry-run（列出漂移单元）。退出码：dry-run 下有漂移 = 1；`--commit` 写盘后仍有残差 = 1。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lib.boot as boot  # noqa: E402
boot.setup()

from data.book_structure.book_structure import (  # noqa: E402
    list_chapter_keys, prime_chapter_kinds, unit_dir_name)
import gate_units as _gate  # noqa: E402  （boot 已把 flows/write-source/script 注入 sys.path）

SRC_SUB, TGT_SUB = "units", "units-translate"
_FILE_RE = re.compile(r'^\s*"file":\s*"(.*)",?\s*$')
# 尾形须容「该键是记录最后一个键（无逗号）」——否则清单里最后一条永远替换不到。
_SRC_RE = re.compile(r'^(\s*"src_hash":\s*")([0-9a-f]{40})(".*)$')


def chapter_drift(src_dir, tgt_dir):
    """→ (drift=[(file, old, new)], errs=[str])：按译侧 manifest 记录逐条比源侧当前哈希。"""
    drift, errs = [], []
    mpath = os.path.join(tgt_dir, "manifest.json")
    if not os.path.exists(mpath):
        return [], []
    with open(mpath, encoding="utf-8") as f:
        man = json.load(f)
    for rec in man.get("units") or []:
        fname = rec.get("file") or ""
        sp = os.path.join(src_dir, fname)
        if not os.path.exists(sp):
            errs.append("源单元文件缺失：%s" % fname)
            continue
        if not rec.get("src_hash"):
            errs.append("单元 %s manifest 无 src_hash 快照（该重跑 init_translate_units，"
                        "本工具不补建）" % fname)
            continue
        now = _gate._read_unit(sp)[5]
        if now != rec["src_hash"]:
            drift.append((fname, rec["src_hash"], now))
    return drift, errs


def rewrite_manifest(tgt_dir, new_by_file):
    """逐行定点替换 `src_hash` 值；返回实际替换处数。正文/其他字段/换行风格一概不动。"""
    mpath = os.path.join(tgt_dir, "manifest.json")
    with open(mpath, encoding="utf-8", newline="") as f:
        raw = f.read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.split(nl)
    cur, done, miss = None, 0, set(new_by_file)
    for i, ln in enumerate(lines):
        m = _FILE_RE.match(ln)
        if m:
            cur = m.group(1)
            continue
        sm = _SRC_RE.match(ln)
        if sm and cur in new_by_file:
            lines[i] = sm.group(1) + new_by_file[cur] + sm.group(3)
            done += 1
            miss.discard(cur)
            cur = None
    if miss:
        raise SystemExit("[resync_src_hash] 🔴 这些漂移记录里没找到可替换的 src_hash 行，"
                         "拒绝半写：%s" % sorted(miss))
    with open(mpath, "w", encoding="utf-8", newline="") as f:
        f.write(nl.join(lines))
    return done


def resync_chapter(src_dir, tgt_dir, commit=False):
    """单章：算漂移 → 校验可替换 → （--commit 时）写盘并复核。返回 (drift, errs)。"""
    drift, errs = chapter_drift(src_dir, tgt_dir)
    if not drift or errs:
        return drift, errs
    by_file = {f: new for f, _o, new in drift}
    if not commit:
        return drift, errs
    rewrite_manifest(tgt_dir, by_file)
    left, errs2 = chapter_drift(src_dir, tgt_dir)
    return left, errs + errs2


def main(argv=None):
    ap = argparse.ArgumentParser(prog="resync_src_hash.py")
    ap.add_argument("extract_dir")
    ap.add_argument("--ch", nargs="*", default=None, help="限定章键（默认全部）")
    ap.add_argument("--commit", action="store_true", help="写盘（默认 dry-run）")
    a = ap.parse_args(argv)
    ext = a.extract_dir
    prime_chapter_kinds(ext)
    keys = a.ch if a.ch else list_chapter_keys(ext)
    total = bad = 0
    for ch in keys:
        src_dir = os.path.join(ext, "book_structure", SRC_SUB, unit_dir_name(ch))
        tgt_dir = os.path.join(ext, "book_structure", TGT_SUB, unit_dir_name(ch))
        if not os.path.isdir(tgt_dir):
            continue
        drift, errs = resync_chapter(src_dir, tgt_dir, a.commit)
        for f, o, n in drift:
            print("%s %s  src_hash %s… → %s…" % (unit_dir_name(ch), f, o[:8], n[:8]))
        for e in errs:
            print("!! %s %s" % (unit_dir_name(ch), e))
        total += len(drift)
        bad += len(errs)
    print(("[resync_src_hash] %s：src_hash 漂移 %d 处 / 异常 %d 处"
           % ("已写盘" if a.commit else "dry-run", total, bad)))
    return 1 if (total or bad) else 0


if __name__ == "__main__":
    sys.exit(main())
