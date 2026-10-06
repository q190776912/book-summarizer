#!/usr/bin/env python3
"""O-LAYER TAIL 行的**印面确证豁免**登记 CLI（判据 SSOT：同目录上层的
verify/subitem_continuity/subitem_continuity.md）。

O 层 TAIL 行长这样：
    ~ L1379: [Then:] TAIL gap — md max = (3), but OCR shows higher number(s): (4, 5)
判据拿「含同一上下文关键词的整页 OCR」找更大编号，于是**同页另一张清单**的号必然
命中（Katok 实测两条假阳：Theorem 5.5.21 的 `Then: (1)(2)(3)` 被同页习题 5.5.3 的
`(4)` 判尾缺；补篇 Definition S.3.3 的 `Remarks (1)(2)(3)` 被 Theorem S.3.1 的 `(4)`
判尾缺）。回源 PDF 逐页核对确认印面无第 (4) 项后，用本工具将「签名 -> 印面取证」
登记进 `<extract_dir>/ignore_o_tail_{chapter_label}.json`，该行此后静默豁免。

🔴 真尾缺一律**补写正文**，禁止用本工具消音。

用法：
    python verify/subitem_continuity/script/attest_o_tail.py <extract_dir> <ch> --list
    python verify/subitem_continuity/script/attest_o_tail.py <extract_dir> <ch> \\
        --sig "Then|3|4,5" --reason "印面 p.227-228（物理 248-249）Theorem 5.5.21 的 Then: 只有 (1)(2)(3)；(4)(5) 来自同页习题 5.5.3 列表"
    # <ch>：数字章 5 / 附录 appendixA / 补篇 supplementS（侧车文件名段与 chapter_label 同源）
"""
import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[3])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

import json

from data.book_structure.book_structure import prime_chapter_kinds
from subitem_continuity import o_tail_ignore_path, load_o_tail_exemptions


def _opt(argv, name):
    return argv[argv.index(name) + 1] if name in argv else None


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or "--help" in argv or "-h" in argv:
        print(__doc__)
        return 2
    ext, ch = argv[0], argv[1].strip()
    prime_chapter_kinds(ext)
    fp = o_tail_ignore_path(ext, ch)

    if "--list" in argv:
        table = load_o_tail_exemptions(ext, ch)
        if not table:
            print("[attest_o_tail] ch=%s 无生效豁免（侧车：%s）。" % (ch, fp))
            return 0
        print("[attest_o_tail] ch=%s 已登记豁免 %d 条（%s）：" % (ch, len(table), fp))
        for sig, reason in sorted(table.items()):
            print("  %s\n      %s" % (sig, reason))
        return 0

    sig = (_opt(argv, "--sig") or "").strip()
    reason = (_opt(argv, "--reason") or "").strip()
    if not sig or not reason:
        print("[attest_o_tail] 🔴 需要 --sig 与 --reason（理由须写明印面页码取证；"
              "空理由不生效，本工具拒绝登记）。")
        return 2
    data = {}
    if os.path.exists(fp):
        try:
            with open(fp, encoding="utf-8-sig") as f:
                raw = f.read()
            data = json.loads(raw) if raw.strip() else {}
        except Exception as e:
            print("[attest_o_tail] 侧车已存在但解析失败（%s），拒绝覆盖：%s" % (e, fp))
            return 1
        if not isinstance(data, dict):
            print("[attest_o_tail] 侧车不是 {签名: 理由} 字典，拒绝改写：%s" % fp)
            return 1
    if data.get(sig) == reason:
        print("[attest_o_tail] 已登记（内容相同，未改写）：%s" % sig)
        return 0
    data[sig] = reason
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print("[attest_o_tail] 已登记豁免 -> %s\n  签名：%s\n  现共 %d 条；"
          "复验该章时此 ~ 行不再出现。" % (fp, sig, len(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
