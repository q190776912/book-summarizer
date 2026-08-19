#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""flow_runner.py — book-summarizer 流程编排器（强制顺序执行的总入口）

这是推进任何流程步骤的**唯一 sanctioned 入口**。它保证：
  · 进入 flow X 的 step S 前，flow X 内 S 之前的所有步骤必须已 done（顺序闸）；
  · 进入某 flow 前，其上游 flow 的末步必须已完成（主干闸）；
  · 一个步骤只有在「物理证据复核通过」后才被标记 done（禁止手填账本）；
  · 历史已合规完成之书用 ``bootstrap`` 一次性回填账本 + 补写 _extraction_done.json。

用法
----
  python tools/flow_runner.py status <book_dir> [--extract <extract_dir>]
  python tools/flow_runner.py next   <book_dir> [--extract <extract_dir>]
  python tools/flow_runner.py verify <book_dir> <flow> <step> [--extract <extract_dir>]
  python tools/flow_runner.py mark   <book_dir> <flow> <step> [--extract <extract_dir>]
  python tools/flow_runner.py run    <book_dir> <flow> <step> [--pdf <pdf>] [--extract <extract_dir>]
  python tools/flow_runner.py bootstrap <book_dir> [--extract <extract_dir>]

约定：book_dir 为本书工作目录（含最终 .md）。extract_dir 默认 = <book_dir>/_extract；
多册书每册传 --extract <book_dir>/_extract/<册>，账本即分册隔离
（lib/flow_gate.ledger_path，单卷书路径与历史一致）。

注意：agent 驱动的步（环境检查 / 归位 / mm_repair 视觉 / config 含 chapter_map 建映射 /
写作 / 翻译）无法被机械跑完——flow_runner 会打印该步的文档说明，agent 按文档做完后，
用 ``verify`` 复核、``mark`` 落账。scripted 步（extract_text/figure/structure/embed/
verify）由 ``run`` 直接执行。
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)
if SKILL_ROOT not in sys.path:
    sys.path.insert(0, SKILL_ROOT)

import lib.boot as _boot  # noqa: E402
_boot.setup()

from lib.flow_gate import (FLOW_ORDER as FG_FLOW_ORDER,  # noqa: E402
                           require_ordered, require_flow_prereqs, mark, unmark,
                           is_done, status as gate_status, bootstrap as gate_bootstrap,
                           ledger_path, FlowGateError)
from flows._flow_contract import RUN_COMMANDS, EVIDENCE, check_evidence  # noqa: E402


def _extract_dir(book_dir, override=None):
    return override or os.path.join(book_dir, "_extract")


def _print_status(book_dir, extract_dir):
    st = gate_status(book_dir, extract_dir)
    print(f"账本: {ledger_path(book_dir, extract_dir)}\n")
    print(f"{'FLOW':<12} {'STEP':<18} {'DONE'}")
    print("-" * 40)
    for flow, steps in FG_FLOW_ORDER.items():
        for s in steps:
            flag = "✅" if st[flow][s] else "⬜"
            print(f"{flow:<12} {s:<18} {flag}")
    # 找下一个未完成
    nxt = _next_step(book_dir, extract_dir)
    if nxt:
        print(f"\n下一个可执行: {nxt[0]}.{nxt[1]}")
    else:
        print("\n所有步骤已完成 ✅")


def _next_step(book_dir, extract_dir=None):
    for flow, steps in FG_FLOW_ORDER.items():
        # flow 前置
        try:
            require_flow_prereqs(book_dir, flow, extract_dir)
        except FlowGateError:
            continue
        for s in steps:
            try:
                require_ordered(book_dir, flow, s, extract_dir)
            except FlowGateError:
                continue
            if not is_done(book_dir, flow, s, extract_dir):
                return (flow, s)
    return None


def cmd_status(book_dir, extract_dir):
    _print_status(book_dir, extract_dir)
    return 0


def cmd_next(book_dir, extract_dir):
    nxt = _next_step(book_dir, extract_dir)
    if not nxt:
        print("所有步骤已完成 ✅")
        return 0
    flow, step = nxt
    kind, spec = RUN_COMMANDS.get(f"{flow}.{step}", ("agent", ""))
    print(f"下一个可执行步骤: {flow}.{step}  [{kind}]")
    print(f"说明: {spec}")
    return 0


def cmd_verify(book_dir, flow, step, extract_dir=None):
    ok, detail = check_evidence(flow, step, book_dir, extract_dir)
    mark_state = "✅ 通过" if ok else "❌ 不通过"
    print(f"证据复核 {flow}.{step}: {mark_state}")
    print(f"  详情: {detail}")
    if not ok:
        print("  → 该步骤尚未真正完成，禁止 mark。先按 flow 文档完成工作。")
        return 1
    return 0


def cmd_mark(book_dir, flow, step, extract_dir=None):
    # 标记前先复核证据
    ok, detail = check_evidence(flow, step, book_dir, extract_dir)
    if not ok:
        print(f"❌ 拒绝标记 {flow}.{step}：证据未通过（{detail}）。"
              f"先完成该步工作，勿手填账本。")
        return 1
    mark(book_dir, flow, step, evidence={"detail": detail}, extract_dir=extract_dir)
    print(f"✅ 已标记 {flow}.{step} 完成（{detail}）。")
    return 0


def cmd_run(book_dir, flow, step, pdf=None, extract_dir=None):
    # 1) 主干前置闸
    try:
        require_flow_prereqs(book_dir, flow, extract_dir)
    except FlowGateError as e:
        print(str(e))
        return 2
    # 2) 顺序闸
    try:
        require_ordered(book_dir, flow, step, extract_dir)
    except FlowGateError as e:
        print(str(e))
        return 2
    # 3) 若该步已 done，提示而非重复
    if is_done(book_dir, flow, step, extract_dir):
        print(f"⚠️ {flow}.{step} 已标记完成；如需重做先 unmark（未提供）。")
        return 0

    kind, spec = RUN_COMMANDS.get(f"{flow}.{step}", ("agent", "(无命令，按文档手动)"))
    if kind == "cmd":
        cmd = spec.format(pdf=pdf or "", book_dir=book_dir,
                          extract_dir=extract_dir or os.path.join(book_dir, "_extract"))
        print(f"▶ 执行 [{flow}.{step}]:\n  {cmd}\n")
        rc = os.system(cmd)
        if rc != 0:
            print(f"❌ 命令返回非零 {rc}；步骤未完成，未标记。先排查后重试 run。")
            return rc
        # 4) 执行后证据复核
        ok, detail = check_evidence(flow, step, book_dir, extract_dir)
        if not ok:
            print(f"❌ 命令已跑但证据未通过（{detail}）；未标记，请检查输出。")
            return 1
        mark(book_dir, flow, step, evidence={"detail": detail, "cmd": cmd},
             extract_dir=extract_dir)
        print(f"✅ {flow}.{step} 完成并标记（{detail}）。")
        return 0
    else:
        print(f"▶ [{flow}.{step}] 需 agent 手动完成（{kind}）:")
        print(f"  {spec}")
        print("  完成后运行:")
        print(f"    python tools/flow_runner.py verify {book_dir} {flow} {step}")
        print(f"    python tools/flow_runner.py mark   {book_dir} {flow} {step}")
        return 0


def cmd_bootstrap(book_dir, extract_dir=None):
    ex = _extract_dir(book_dir, extract_dir)
    if not os.path.isdir(ex):
        print(f"❌ 找不到 _extract 目录: {ex}")
        return 2
    ok, gaps = gate_bootstrap(book_dir, ex)
    if ok:
        print(f"✅ 历史书回填完成（依据物理证据）。账本: {ledger_path(book_dir, ex)}")
        return 0
    print("⚠️ 部分步骤物理证据不满足，仅回填满足的部分；缺口如下：")
    for step, detail in gaps:
        print(f"  ❌ {step}: {detail}")
    print("  请先真正完成这些步骤（尤其是 MM Repair），再 bootstrap。")
    return 1


USAGE = """\
用法:
  flow_runner.py status  <book_dir> [--extract <extract_dir>]
  flow_runner.py next    <book_dir> [--extract <extract_dir>]
  flow_runner.py verify  <book_dir> <flow> <step> [--extract <extract_dir>]
  flow_runner.py mark    <book_dir> <flow> <step> [--extract <extract_dir>]
  flow_runner.py run     <book_dir> <flow> <step> [--pdf <pdf>] [--extract <extract_dir>]
  flow_runner.py bootstrap <book_dir> [--extract <extract_dir>]

多册书：每册操作时传 --extract <book_dir>/_extract/<册>，账本分册隔离。
"""


def _pop_extract(rest):
    """从参数列表取 --extract 后的值（默认 None）；不存在的键时原样返回。"""
    ex = None
    if "--extract" in rest:
        i = rest.index("--extract")
        ex = rest[i + 1] if i + 1 < len(rest) else None
        del rest[i:i + 2]
    return ex


def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(USAGE)
        return 0
    cmd = args[0]
    rest = args[1:]

    if cmd == "status":
        if not rest:
            print(USAGE); return 2
        ex = _pop_extract(rest)
        return cmd_status(rest[0], ex)
    if cmd == "next":
        if not rest:
            print(USAGE); return 2
        ex = _pop_extract(rest)
        return cmd_next(rest[0], ex)
    if cmd == "verify":
        if len(rest) < 3:
            print(USAGE); return 2
        ex = _pop_extract(rest)
        return cmd_verify(rest[0], rest[1], rest[2], extract_dir=ex)
    if cmd == "mark":
        if len(rest) < 3:
            print(USAGE); return 2
        ex = _pop_extract(rest)
        return cmd_mark(rest[0], rest[1], rest[2], extract_dir=ex)
    if cmd == "run":
        if len(rest) < 3:
            print(USAGE); return 2
        book_dir, flow, step = rest[0], rest[1], rest[2]
        ex = _pop_extract(rest)
        pdf = None
        if "--pdf" in rest:
            i = rest.index("--pdf"); pdf = rest[i + 1] if i + 1 < len(rest) else None
        return cmd_run(book_dir, flow, step, pdf=pdf, extract_dir=ex)
    if cmd == "bootstrap":
        if not rest:
            print(USAGE); return 2
        book_dir = rest[0]
        ex = _pop_extract(rest)
        return cmd_bootstrap(book_dir, ex)
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main())
