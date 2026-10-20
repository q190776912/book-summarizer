import os
import sys
import time
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

r"""主代理专用的**白名单守卫式清理**工具（用户裁定 2026-10-20；判据见 flows/_flow_gate.md 禁止清单）。

只删「主会话本轮亲手写的一次性脚本 / 探针输出」。四条机械边界，任一不满足即**整批不删**：
  ① 固定白名单：`--files` 逐个给出确切文件名，禁止通配（`*` `?` `[`）、禁止相对上跳（`..`）、
     禁止子目录路径（本工具永不递归、永不删目录）；
  ② 三重 preflight：每项必须存在、必须是**普通文件**、必须直接落在给定目录下；
  ③ 保护名单：交付形态 md、OCR `page_*.json`、契约 / manifest / config / chapter_map /
     完整性报告 / ignore / overrides / 台账 / 快照 / 校验回执日志一律拒删；
  ④ 留证：真删时在目标目录写 `_cleanup_<时间戳>.txt`，逐项记大小与总计数
     （`removed=` / `still_present=`），回执路径打印在最后一行。

用法：
    python tools/cleanup_scratch.py <dir> --files a.py,b_out.txt [--dry-run]

<dir> 通常是某书的 `_extract/`。路径请从列目录结果取得，勿手敲含中文的路径。
"""

PROTECTED = (
    "page_", "manifest.json", "verify_config.json", "chapter_map.json",
    "figure_index.json", "_completeness_report.json", "ignore_", "manual_overrides_",
    "repairs", "_flow_gate.json", "extraction_done", "_extraction_done.json",
    ".flow_gate.json", "formula_audit",
)
PROTECTED_MD_PREFIX = ("第", "Chapter", "Appendix", "附录", "补篇", "Supplement")
RECEIPT_PREFIX = ("_verify", "_audit", "_flow_status", "_status", "_gate_log")


def _protected_reason(name):
    if name.endswith(".md"):
        for p in PROTECTED_MD_PREFIX:
            if name.startswith(p):
                return "deliverable md"
    for p in PROTECTED:
        if p in name:
            return "protected ledger/OCR/contract file"
    base = name.split(".")[0]
    for p in RECEIPT_PREFIX:
        if base.startswith(p):
            return "verification receipt"
    return None


def plan(target, names):
    """返回 (可删绝对路径清单, 拒绝原因清单)。任一拒绝 => 调用方必须放弃整批。"""
    target = os.path.abspath(target)
    if not os.path.isdir(target):
        return [], ["target is not a directory: " + target]
    ok, bad = [], []
    for raw in names:
        name = raw.strip()
        if not name:
            bad.append((raw, "empty name"))
            continue
        if any(c in name for c in "*?["):
            bad.append((name, "wildcard not allowed"))
            continue
        if "\\" in name or "/" in name or name in (".", "..") or name.startswith(".."):
            bad.append((name, "path traversal / subdirectory not allowed"))
            continue
        why = _protected_reason(name)
        if why:
            bad.append((name, why))
            continue
        p = os.path.join(target, name)
        if os.path.dirname(os.path.abspath(p)) != target:
            bad.append((name, "outside target dir"))
            continue
        if not os.path.exists(p):
            bad.append((name, "missing"))
            continue
        if os.path.isdir(p):
            bad.append((name, "is a directory (never recursive)"))
            continue
        if not os.path.isfile(p):
            bad.append((name, "not a plain file"))
            continue
        ok.append(p)
    return ok, bad


def cleanup(target, names, dry_run=False):
    ok, bad = plan(target, names)
    for name, why in bad:
        print("  REFUSED %-40s %s" % (name, why))
    if bad:
        print("[cleanup_scratch] preflight 有 %d 项被拒 => 整批不删（all-or-nothing）。"
              "可删候选 %d 项。" % (len(bad), len(ok)))
        return 2
    if not ok:
        print("[cleanup_scratch] 白名单为空，无事可做。")
        return 0
    if dry_run:
        for p in ok:
            print("  WOULD REMOVE %-40s %d bytes" % (os.path.basename(p), os.path.getsize(p)))
        print("[cleanup_scratch] dry-run：计划删除 %d 项，未动盘。" % len(ok))
        return 0
    lines = []
    total = 0
    for p in ok:
        size = os.path.getsize(p)
        total += size
        os.remove(p)
        lines.append("removed %s (%d bytes)" % (os.path.basename(p), size))
        print("  " + lines[-1])
    still = [os.path.basename(p) for p in ok if os.path.exists(p)]
    stamp = time.strftime("%Y%m%d_%H%M%S")
    receipt = os.path.join(os.path.abspath(target), "_cleanup_%s.txt" % stamp)
    with open(receipt, "w", encoding="utf-8") as f:
        f.write("[cleanup_scratch] target=%s\n" % os.path.abspath(target))
        f.write("授权：用户裁定 2026-10-20 主会话有限清理权（flows/_flow_gate.md 禁止清单）\n")
        f.write("\n".join(lines) + "\n")
        f.write("removed=%d still_present=%d\n" % (len(lines), len(still)))
    print("[cleanup_scratch] removed=%d still_present=%d bytes=%d"
          % (len(lines), len(still), total))
    print("[cleanup_scratch] 留证回执 -> " + receipt)
    return 0 if not still else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or "--files" not in argv:
        print(__doc__)
        return 2
    i = argv.index("--files")
    target = argv[0]
    names = [n for n in argv[i + 1].split(",") if n.strip()]
    dry = "--dry-run" in argv
    return cleanup(target, names, dry_run=dry)


if __name__ == "__main__":
    sys.exit(main())
