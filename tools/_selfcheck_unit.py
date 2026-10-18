#!/usr/bin/env python3
"""写手逐单元自检入口：对单个单元跑**章门控的同一套装配**（步骤 5）。

    python tools/_selfcheck_unit.py "<单元文件绝对路径>"

🔴 本脚本只做一件事：把单元路径反解成 `(extract_dir, 章键, units_sub, 文件名)`，
再调 `gate_units.gate_chapter(..., only_unit=<文件名>)`。判据本体在门控里，这里
**不得**再自己组一次 `check_body` 调用。

成因（Lehmann《Elements of Large-Sample Theory》ch1，2026-10-16）：本脚本原来是另起
一次 `check_body(...)`，参数只给了 `expected_tags/expected_images/content_blocks`，
少给 `ext_dir`/`ch` ⇒ 第 19 项「顶层散文照抄」整个缺席（该项按这两参数开关），
`source_text`/`node_type`/`ord_keys`/#23 标签对账/真实 KaTeX 渲染同样不在场。写手据此
打印 `RESULT OK` 翻 DONE，章门控再把**同一单元**打回（0013 / 0026 / 0035 三例），
平白多一轮返工。「自检比门控松」是结构性假绿：入口必须由门控自己提供，
让两者共用同一行调用点（判据测试
`flows/write-source/script/tests/test_gate_unit_mode.py`）。

输出契约（写手作业单按这些 token 判断，勿改）：`MARK <DRAFT|DONE>` / `PROB …` /
`RESULT OK|FAIL`；退出码 0 = 该单元 DONE 且门控放行。

🔴 DRAFT 态另给一行 `BODY OK|FAIL`（正文预判，`tolerate_draft` 通道）：门控默认在
「标记仍为 DRAFT」这条判据处就 `continue`，**正文质量判据根本不跑**，于是写手在改正文
的阶段永远只能拿到 `RESULT FAIL`，与作业纪律「没拿到 OK 不许写 DONE」字面冲突
（Lehmann 2026-10-17/18 三个批次独立上报，其中一个只能先翻 DONE 才暴露出真实内容缺陷
= 先落账后验收）。正文判据看 `BODY`，标记状态看 `RESULT`：`BODY OK` → 翻 DONE →
再跑一次须见 `RESULT OK`。
"""
import os
import re
import sys
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

sys.stdout.reconfigure(encoding="utf-8")

import gate_units
from data.book_structure.book_structure import (  # noqa: E402
    list_chapter_keys, prime_chapter_kinds, unit_dir_name)

MARK_RE = re.compile(r"<!-- book-summarizer (DRAFT|DONE) unit:")


def _fail(msg):
    print("PROB %s" % msg)
    print("RESULT FAIL")
    return 1


def main():
    if len(sys.argv) != 2:
        return _fail("用法：python tools/_selfcheck_unit.py <单元文件绝对路径>")
    unit_path = os.path.abspath(sys.argv[1])
    if not os.path.isfile(unit_path):
        return _fail("单元文件不存在：%s" % unit_path)
    d = os.path.dirname(unit_path)
    fname = os.path.basename(unit_path)
    units_sub = os.path.basename(os.path.dirname(d))
    ext = os.path.dirname(os.path.dirname(os.path.dirname(d)))
    # 🔴 布局不符即拒绝，绝不退回「弱一点的自检」：静默降级就是下一个假绿。
    if units_sub not in ("units", "units-translate"):
        return _fail("路径形态不是 <extract>/book_structure/%s/<章目录>/<文件>：%s"
                     % ("units|units-translate", unit_path))
    if not os.path.isfile(os.path.join(d, "manifest.json")):
        return _fail("该单元目录缺 manifest.json（登记处不在场，无法对账）：%s" % d)
    with open(unit_path, encoding="utf-8") as f:
        head = f.readline()
    m = MARK_RE.match(head)
    if not m:
        return _fail("首行标记缺失/损坏（须含 `<!-- book-summarizer DRAFT|DONE unit: ...`）")
    print("MARK %s" % m.group(1))
    prime_chapter_kinds(ext)
    unit_dir = os.path.basename(d)
    ch_key = next((k for k in list_chapter_keys(ext)
                   if unit_dir_name(k) == unit_dir), None)
    if ch_key is None:
        return _fail("目录 %s 对不上本章任何分章契约的单元目录名（章键无法归属，"
                     "自检不可用）" % unit_dir)
    ok, detail = gate_units.gate_chapter(ext, ch_key, units_sub=units_sub,
                                        only_unit=fname)
    lines = [ln.strip() for ln in (detail or "").splitlines() if ln.strip()]
    if lines:
        print(lines[0])
    for line in lines[1:]:
        print("PROB %s" % line)
    print("RESULT %s" % ("OK" if ok else "FAIL"))
    if m.group(1) == "DRAFT":
        ok_b, det_b = gate_units.gate_chapter(ext, ch_key, units_sub=units_sub,
                                             only_unit=fname, tolerate_draft=True)
        for line in [ln.strip() for ln in (det_b or "").splitlines()
                     if ln.strip()][1:]:
            print("PROB-BODY %s" % line)
        print("BODY %s（正文预判，标记仍是 DRAFT；见 BODY OK 才翻 DONE，"
              "翻完须再见 RESULT OK）" % ("OK" if ok_b else "FAIL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
