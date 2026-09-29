# -*- coding: utf-8 -*-
"""register_content_override.py — `verify_config.content_overrides` 的唯一登记入口.

登记的是「**印面裁定**让磁盘契约合理地偏离纯管线重算」的内容块操作（`drop` 噪声
块 / `retag` 把 `(C.N)` 挪回印面上那条式）。① 复算闸
（`verify/script/check_content_completeness.py`）按 `attach_content` 重算与磁盘对账，
没有这本账时它会把这些偏离报成「契约缺块 / 多块」假 FAIL，后续会话重跑步骤 4 就
只能再判一次——与闸门 ⑭ 的 `formula.known_book` 同构（见 `register_formula.py`）。

🔴 能机械判定的**不要登记**：节题被 OCR 重抄（`Q(VD)` vs `Q(√D)`）产生的标题残块由
`attach_content._drop_heading_residue` 按几何拼行自动消化；只有「印面上这个 `(C.N)`
属于哪条式」这类**必须目视**的裁定才进本账本。

本 CLI 机械执行的纪律：
1. **`--evidence` 必填**（≥10 字，说清印面看到什么）；连同页码/时间写进登记项，
   事后能复核是谁在哪页依据什么判的；
2. **登记必须落在磁盘上**：新登记项对该章**磁盘契约**跑 `disk_audit` —— `drop` 要
   磁盘已无该块，`retag` 要磁盘该块的 tag 已等于登记值。磁盘还没改成就不许登记
   （登记不是「打算改」的占位符）；
3. **登记必须是活账**：拿**未叠加登记**的管线重算核对，新登记项须命中 ≥1 块；命中
   0 块即拒（否则一条死登记会让 ① 两侧同时看不见该块 → 假 PASS，而 `disk_audit`
   对 drop 只会「无匹配 = 已剔除」地假绿）；
4. **不得手写/手改 `verify_config.json`**（`_provenance.warning` 已声明）：本 CLI
   只做「读→改 `content_overrides` 一键→原子写回」，保留原换行风格；
   `make_config --force` 经 `_MANUAL_DECLARED_FLAGS` 保留该键，重生成不清空登记
   （回归测试 `tests/test_force_preserves_manual_flags.py`）。

用法：
    python config/verify_config/register_content_override.py <书目录或 _extract> \\
        --ch 1 --op retag --kind formula --tag 1.100 \\
        --match 'c ( \\mathcal { P } ) = ...' --page 36 \\
        --evidence "fitz 裁页 p.36：(1.100) 印在 c(P)=… 式右缘"
    python config/verify_config/register_content_override.py <同上> --list --ch 1
"""
import argparse
import json
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
import lib.boot as _boot  # noqa: E402
_boot.setup()
sys.stdout.reconfigure(encoding="utf-8")

from lib import content_overrides as co  # noqa: E402


def _die(msg):
    print("[register-override] REFUSED: %s" % msg, file=sys.stderr)
    raise SystemExit(2)


def _resolve_extract(arg):
    p = os.path.abspath(arg)
    for c in (p, os.path.join(p, "_extract")):
        if os.path.exists(os.path.join(c, "verify_config.json")):
            return c
    _die("找不到 verify_config.json（须先由 make_config.py 生成配置）：" + arg)


def _section_holder(cfg):
    """Return the dict that owns this book's chapter config (`ch` or flat)."""
    if isinstance(cfg.get("ch"), dict):
        return cfg["ch"]
    if isinstance(cfg.get("ordinal"), list):
        return cfg
    _die("配置里找不到分章（`ch`）段，也不是扁平格式——请先跑 config 子流程")


def main(argv=None):
    ap = argparse.ArgumentParser(description="登记 content_overrides（印面裁定账本）")
    ap.add_argument("target", nargs="?", help="书目录或 _extract 目录")
    ap.add_argument("--ch", dest="ch")
    ap.add_argument("--op", choices=["drop", "retag"])
    ap.add_argument("--kind", choices=["text", "formula", "image"])
    ap.add_argument("--match", default=None,
                    help="块内容（① 残差行打印的归一化文本，全等匹配）")
    ap.add_argument("--tag", default=None,
                    help="retag 目标 tag；清空登记用 `--tag ''`")
    ap.add_argument("--page", type=int, default=None, help="印面证据所在 extract 页")
    ap.add_argument("--evidence", default="", help="印面目视证据（必填）")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    if not args.target:
        ap.error("需要 <书目录或 _extract>")
    ext = _resolve_extract(args.target)
    cfg_path = os.path.join(ext, "verify_config.json")
    raw = open(cfg_path, "rb").read()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    cfg = json.loads(raw.decode("utf-8-sig"))
    holder = _section_holder(cfg)
    ops = holder.get(co.KEY)
    if not isinstance(ops, list):
        ops = []

    if args.list:
        sel = [o for o in ops if not args.ch or str(o.get("ch")) == str(args.ch)]
        print(json.dumps(sel, ensure_ascii=False, indent=2))
        print("# 共 %d 笔（本章 %d 笔）" % (len(ops), len(sel)))
        return 0

    if not args.ch or not args.op or not args.kind or args.match is None:
        _die("--ch / --op / --kind / --match 都是必填")
    if args.op == "retag" and args.tag is None:
        _die("retag 必须给 --tag（清空用 --tag ''）")
    if args.op == "drop" and args.tag is not None:
        _die("drop 不接受 --tag")
    if not co.norm(args.match):
        _die("--match 归一化后为空（不可能唯一匹配任何块）")
    if len(args.evidence.strip()) < 10:
        _die("`--evidence` 必填且要说清印面证据（先 fitz 裁页目视，再登记）")
    if not isinstance(holder.get("_provenance"), dict):
        _die("verify_config.json 缺 `_provenance`（手写/手改配置不被接受），"
             "请先跑 make_config.py")

    sys.path.insert(0, os.path.join(_ROOT, "flows", "write-source",
                                    "structure", "script"))
    import attach_content as ac
    from data.book_structure.book_structure import prime_chapter_kinds
    prime_chapter_kinds(ext)
    disk_path = ac.out_path(ext, str(args.ch))
    if not os.path.exists(disk_path):
        _die("该章无内容化契约 %s（先跑 attach_content）" % disk_path)
    with open(disk_path, encoding="utf-8") as f:
        saved = json.load(f)

    op = {"ch": str(args.ch), "op": args.op, "kind": args.kind,
          "match": co.norm(args.match)}
    if args.op == "retag":
        op["tag"] = co.norm(args.tag)
    if args.page is not None:
        op["page"] = int(args.page)
    op["evidence"] = args.evidence.strip()
    op["registered_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")

    for old in ops:
        if str(old.get("ch")) == op["ch"] and old.get("op") == op["op"] \
                and co.norm(old.get("match")) == op["match"] \
                and str(old.get("tag") or "") == str(op.get("tag") or ""):
            print("[register-override] 已在册，不重复登记：%r" % op["match"][:60])
            return 0

    # ── 闸 ①：登记必须已经落在磁盘契约上 ──────────────────────────────────
    problems = co.disk_audit(saved, [op])
    if problems:
        _die("磁盘契约尚未体现该裁定（登记不是占位符）：\n  - "
             + "\n  - ".join(problems))

    # ── 闸 ②：登记必须是活账（未叠加登记的管线重算里确有该块） ────────────
    real_ops_for = co.ops_for
    co.ops_for = lambda *_a, **_k: []          # 取「纯管线」重算
    try:
        built, _st = ac.build_chapter_contract(ext, saved)
    finally:
        co.ops_for = real_ops_for
    from lib.tag_attestation import (dir_page_loader as _dpl,
                                     strip_unattested as _strip,
                                     attested_numbers as _attested)
    from lib.page_dir import node_page_dir as _npd
    _strip(built, _dpl(_npd(ext, saved, str(args.ch)), ext),
           attested=_attested(ext))
    hits = [b for _p, b in co._iter_blocks(built) if co._matches(b, op)]
    if not hits:
        _die("未叠加登记的管线重算里没有该块 → 这条登记是**死账**（命中 0 块）。"
             "① 会因它两侧同时失明而假 PASS。请重核印面与契约，别登记")

    holder[co.KEY] = ops + [op]
    print("[register-override] 章 %s 登记 %s/%s：%r%s"
          % (args.ch, op["op"], op["kind"], op["match"][:60],
             " → tag=%r" % op["tag"] if args.op == "retag" else ""))
    print("[register-override] 磁盘已体现、重算命中 %d 块、证据已入账本" % len(hits))
    if args.dry_run:
        print("[register-override] --dry-run：未写回")
        return 0
    text = json.dumps(cfg, ensure_ascii=False, indent=2)
    if newline != "\n":
        text = text.replace("\n", newline)
    tmp = cfg_path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(text.encode("utf-8"))
    os.replace(tmp, cfg_path)
    print("[register-override] 已写回 verify_config.json；请重跑 "
          "check_content_completeness.py / verify_chapter.py 复核该章")
    return 0


if __name__ == "__main__":
    sys.exit(main())
