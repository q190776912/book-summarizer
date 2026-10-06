#!/usr/bin/env python3
"""B 层 EXTRA-MENTION / EXTRA-ENTRY 的**印面确证豁免**登记 CLI。
（判据 SSOT：同目录上层的 verify/item_numbering_integrity/item_numbering_integrity.md）

B 层的非阻断报告行长这样：
    ~ 引理20.3   （EXTRA-MENTION: keys in .md prose/cross-refs only…）
    + 定义5.6.5  （EXTRA-ENTRY: .md carries a standalone bold entry head…）

判据能机械归域的（`\tag{}` 名册、图表号、题集、书目、跨章、小节标题、`untyped`、`xref`）
都已由 `domain_suppressed_mentions` 收走并留痕。剩下这一族**形状**与「正文提到一个条目
而本章契约无记录」完全相同，放宽任何一支都会洗掉真漏登记（Apostol IANT ch9 例1 的教训），
因此唯一的正路是**逐页回源核对 + 签名举证**。2026-10-04 动力系统书架实测三例：
  · Koopman ch20 `引理 20.3`——印面 p.541/542 只印出引理 20.1/20.2，正文两回
    「Based on Lemma 20.3」（物理 p.547、p.549）确为**原书自己的笔误**；
  · chaos ch5 `定义 5.6.5`——印面 §5.6 只有 Definition 5.6.1/5.6.2，p.138 的
    「(Definition 5.6.5)」指向的是 p.122 的编号公式 (5.6.5)（模恒等式）= **原书误指**；
  · Arnold 附录M `定理 3.1`——p.374 的英译者脚注「Givental 指出，本文定理 3.1 不正确」
    里的号属于**另一篇论文**，本书任何计数器都不含它。

登记后该键从 EXTRA 三桶剔除，并**照旧逐条打印**（EXTRA-MENTION · 印面确证，带理由），
不静默消失；`truly_missing` / `mentioned_only` / `blocking` 一概不受影响。

🔴 真漏登记一律**补登记契约节点 / 补写正文**，禁止用本工具消音；空理由不生效。

用法：
    python verify/item_numbering_integrity/script/attest_b_mention.py <extract_dir> <ch> --list
    python verify/item_numbering_integrity/script/attest_b_mention.py <extract_dir> <ch> \\
        --key "引理20.3" --reason "印面 p.541/542 仅有引理 20.1/20.2；正文两回 Lemma 20.3（物理 547、549）系原书笔误，交付加注已说明"
    # <ch>：数字章 5 / 附录 appendixA / 补篇 supplementS（侧车文件名段与 chapter_label 同源）
    # 一次可给多个 --key（同一理由登记多键）
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
from item_numbering_integrity import b_mention_ignore_path, load_b_mention_exemptions


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or "--help" in argv or "-h" in argv:
        print(__doc__)
        return 2
    ext, ch = argv[0], argv[1].strip()
    prime_chapter_kinds(ext)
    fp = b_mention_ignore_path(ext, ch)

    if "--list" in argv:
        table = load_b_mention_exemptions(ext, ch)
        if not table:
            print("[attest_b_mention] ch=%s 无生效豁免（侧车：%s）。" % (ch, fp))
            return 0
        print("[attest_b_mention] ch=%s 已登记豁免 %d 条（%s）：" % (ch, len(table), fp))
        for k, reason in sorted(table.items()):
            print("  %s\n      %s" % (k, reason))
        return 0

    keys = [argv[i + 1].strip() for i, a in enumerate(argv)
            if a == '--key' and i + 1 < len(argv)]
    reason = ""
    for i, a in enumerate(argv):
        if a == '--reason' and i + 1 < len(argv):
            reason = argv[i + 1].strip()
    if not keys:
        print("[attest_b_mention] 🔴 需要至少一个 --key（报告行里打印的那个键形）。")
        return 2
    if not reason:
        print("[attest_b_mention] 🔴 需要 --reason（理由须写明印面页码取证；"
              "空理由不生效，本工具拒绝登记）。")
        return 2

    data = {}
    if os.path.exists(fp):
        try:
            with open(fp, encoding="utf-8-sig") as f:
                raw = f.read()
            data = json.loads(raw) if raw.strip() else {}
        except Exception as e:
            print("[attest_b_mention] 侧车已存在但解析失败（%s），拒绝覆盖：%s" % (e, fp))
            return 1
        if not isinstance(data, dict):
            print("[attest_b_mention] 侧车不是 {键: 理由} 字典，拒绝改写：%s" % fp)
            return 1
    changed = []
    for k in keys:
        if data.get(k) == reason:
            print("[attest_b_mention] 已登记（内容相同，未改写）：%s" % k)
            continue
        data[k] = reason
        changed.append(k)
    if changed:
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("[attest_b_mention] 已登记豁免 -> %s\n  键：%s\n  现共 %d 条；"
              "复验该章时这些键改在「EXTRA-MENTION · 印面确证」块打印（带理由）。"
              % (fp, "、".join(changed), len(data)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
