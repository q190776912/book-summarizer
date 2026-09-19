#!/usr/bin/env python3
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib"),
           os.path.join(_ROOT, "flows", "write-source", "script")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

# -*- coding: utf-8 -*-
"""rename_units.py — 把某书已拆的 unit 文件重命名为 ``NNNN_<type>_<key>.md`` 规约。

命名真源 = ``flows/write-source/script/split_draft_units._unit_filename``；本工具
**直接复用**该函数，规则变更时自动跟随，绝不另写一份正则。

只做三件事，**绝不改正文**：
  1. 重命名单元文件为规约名（``NNNN`` = manifest 顺序位，4 位零填充）；
  2. 同步 manifest 每个单元的 ``id`` / ``file``；
  3. 同步单元首行 marker 的 ``id=``（``DRAFT`` / ``DONE`` 均处理）。

**崩溃安全 / 幂等**：每个单元按 ``new → __ren__old → old`` 顺序探测当前文件，
因此半途中断（存在 ``__ren__*`` 或已到新名）也能续跑；两段式 rename
（src→``__mig__k``→new）防互相覆盖。无 manifest 的目录跳过。

用法:
  python tools/rename_units.py <extract_dir> [--dry-run] [--units-sub units|units-translate|both]
"""
import argparse
import json
import os
import re

import split_draft_units as _split

_MARK_RE = re.compile(r'(<!-- book-summarizer (?:DRAFT|DONE) unit: )id=\S+( type=.*?-->)', re.S)
_STAGE = "__mig__"


def _set_marker_id(raw, new_id):
    m = _MARK_RE.match(raw)
    if not m:
        return raw, False
    return m.group(1) + "id=" + new_id + m.group(2) + raw[m.end():], True


def _locate(d, old, new):
    """返回当前文件相对名（new / __ren__old / old），找不到返回 None。"""
    for cand in (new, "__ren__" + old, old):
        if os.path.exists(os.path.join(d, cand)):
            return cand
    return None


def migrate_dir(d, dry):
    """返回 (n_rename, n_marker, error)。"""
    mp = os.path.join(d, "manifest.json")
    if not os.path.exists(mp):
        return None
    try:
        man = json.load(open(mp, encoding="utf-8"))
    except Exception as e:
        return (0, 0, "manifest 读取失败: %s" % e)
    units = man.get("units") or []
    plan = []
    for i, u in enumerate(units):
        new_id = "%04d" % (i + 1)
        old = u.get("file") or ""
        new = _split._unit_filename(i + 1, u.get("type") or "",
                                    u.get("key") or "", u.get("name") or "")
        src = _locate(d, old, new)
        if src is None:
            return (0, 0, "找不到单元文件: old=%s new=%s" % (old, new))
        plan.append((new_id, old, new, src))

    news = [p[2] for p in plan]
    dup = sorted({n for n in news if news.count(n) > 1})
    if dup:
        return (0, 0, "新文件名冲突: %s" % dup)
    n_rename = sum(1 for (_, _, new, src) in plan if src != new)
    if dry:
        return (n_rename, len(plan), None)

    # 两段式：src -> __mig__k -> new
    staged = []
    for k, (new_id, old, new, src) in enumerate(plan):
        if src == new:
            staged.append((new, None))
            continue
        t = _STAGE + "%05d" % k
        os.rename(os.path.join(d, src), os.path.join(d, t))
        staged.append((new, t))
    for new, t in staged:
        if t is not None:
            os.rename(os.path.join(d, t), os.path.join(d, new))

    n_marker = 0
    for u, (new_id, old, new, src) in zip(units, plan):
        raw = open(os.path.join(d, new), encoding="utf-8").read()
        raw2, ok = _set_marker_id(raw, new_id)
        if ok and raw2 != raw:
            open(os.path.join(d, new), "w", encoding="utf-8").write(raw2)
            n_marker += 1
        u["id"] = new_id
        u["file"] = new
    with open(mp, "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=2)
    return (n_rename, n_marker, None)


def main():
    argv = sys.argv[1:]
    dry = "--dry-run" in argv
    argv = [a for a in argv if a != "--dry-run"]
    sub = "both"
    if "--units-sub" in argv:
        i = argv.index("--units-sub")
        sub = argv[i + 1]
        argv = argv[:i] + argv[i + 2:]
    if not argv:
        print(__doc__)
        return 2
    ext = argv[0]
    subs = ["units", "units-translate"] if sub == "both" else [sub]
    total_r = total_m = 0
    for s in subs:
        root = os.path.join(ext, "book_structure", s)
        if not os.path.isdir(root):
            continue
        for name in sorted(os.listdir(root)):
            d = os.path.join(root, name)
            if not os.path.isdir(d):
                continue
            res = migrate_dir(d, dry)
            if res is None:
                continue
            nr, nm, err = res
            if err:
                print("  [ERROR] %s/%s: %s" % (s, name, err), flush=True)
                continue
            if nr or not dry:
                print("  [%s] %s/%s: rename=%d marker=%s%s" %
                      ("RENAME" if nr else "ok", s, name, nr, nm, " (dry)" if dry else ""),
                      flush=True)
            total_r += nr
            total_m += 0 if dry else nm
    print("[rename_units] %s total_rename=%d total_marker=%d" %
          ("DRY-RUN" if dry else "DONE", total_r, total_m), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
