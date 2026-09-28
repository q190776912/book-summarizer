#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""flow_runner.py — book-summarizer 流程编排器（强制顺序执行的总入口）

这是推进任何流程步骤的**唯一 sanctioned 入口**。它保证：
  · 进入 flow X 的 step S 前，flow X 内 S 之前的所有步骤必须已 done（顺序闸）；
  · 进入某 flow 前，其上游 flow 的末步必须已完成（主干闸）；
  · 一个步骤只有在「物理证据复核通过」后才被标记 done（禁止手填账本）；
  · mark/run 之前先复演**已完成步**的证据：账上做完的东西被误删时立即拒绝并给出
    快照回滚提示（lib/snapshot_guard，2026-09-28 一次子代理 rm -rf 抹掉整棵书树后加）；
  · 每次成功 mark 自动在 ``<extract_dir>/_snapshots/`` 留一份 tar.gz 快照
    （契约 + units + 章 md + 台账；``extract.mm_repair`` 另含 page_*.json 与图像）；
  · 历史已合规完成之书用 ``bootstrap`` 一次性回填账本 + 补写 _extraction_done.json。

用法
----
  python tools/flow_runner.py status <book_dir> [--extract <extract_dir>]
  python tools/flow_runner.py next   <book_dir> [--extract <extract_dir>]
  python tools/flow_runner.py verify <book_dir> <flow> <step> [--extract <extract_dir>]
  python tools/flow_runner.py mark   <book_dir> <flow> <step> [--extract <extract_dir>]
  python tools/flow_runner.py run    <book_dir> <flow> <step> [--pdf <pdf>] [--extract <extract_dir>]
  python tools/flow_runner.py audit  <book_dir> [--extract <extract_dir>]
  python tools/flow_runner.py bootstrap <book_dir> [--extract <extract_dir>]

约定：book_dir 为本书工作目录（含最终 .md）。extract_dir 默认 = <book_dir>/_extract；
多册书每册传 --extract <book_dir>/_extract/<册>，账本即分册隔离
（lib/flow_gate.ledger_path，单卷书路径与历史一致）。

注意：agent 驱动的步（环境检查 / 归位 / mm_repair 视觉 / config 含 chapter_map 建映射 /
写作 / 翻译）无法被机械跑完——flow_runner 会打印该步的文档说明，agent 按文档做完后，
用 ``verify`` 复核、``mark`` 落账。scripted 步（extract_text/figure/structure/embed/
verify）由 ``run`` 直接执行。
"""
import glob
import os
import subprocess
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
from lib import snapshot_guard  # noqa: E402

# 需要连 OCR / 图像一起归档的步（重跑代价最大，且此后再不会变）
FULL_SNAPSHOT_STEPS = {"extract.mm_repair"}


def _guard_existing_evidence(book_dir, extract_dir):
    """落账新步之前复演**已完成步**的证据谓词：产物消失（误删/挪走/截断）即拒绝。

    判据与当初 mark 用的完全同一套（``flows._flow_contract.EVIDENCE``），所以这里
    FAIL 的含义只有一个：账上已经做完的东西，盘上不存在了。
    """
    ex = _extract_dir(book_dir, extract_dir)
    bad = snapshot_guard.audit(book_dir, ex, gate_status, EVIDENCE, check_evidence)
    if bad:
        print("❌ 拒绝继续：台账里已完成的步骤，其物理证据已不在位（疑似误删/挪动）：")
        for step, detail in bad:
            print(f"  🔴 {step}: {detail}")
        print("  " + snapshot_guard.restore_hint(ex))
        print("  先从快照回滚或重做对应步骤，再回来 mark/run。")
    return bad


def _after_mark(book_dir, extract_dir, flow, step):
    ex = _extract_dir(book_dir, extract_dir)
    tag = "%s.%s%s" % (flow, step,
                       ".full" if f"{flow}.{step}" in FULL_SNAPSHOT_STEPS else "")
    try:
        path = snapshot_guard.snapshot(book_dir, ex, tag)
    except Exception as e:  # 快照失败不阻塞落账，但必须喊出来
        print(f"⚠️ 快照失败（{e}）——本次落账没有留底。")
        return
    if path:
        print(f"   📦 快照: {os.path.relpath(path, ex)}")


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
    ex = _extract_dir(book_dir, extract_dir)
    bad = snapshot_guard.audit(book_dir, ex, gate_status, EVIDENCE, check_evidence)
    if bad:
        print("\n🔴 证据复演（已完成步的产物是否仍在位）:")
        for step, detail in bad:
            print(f"   ❌ {step}: {detail}")
        print("   " + snapshot_guard.restore_hint(ex))
    return 1 if bad else 0


def cmd_audit(book_dir, extract_dir):
    """只跑证据复演：台账说做完了，盘上还在不在。"""
    ex = _extract_dir(book_dir, extract_dir)
    bad = snapshot_guard.audit(book_dir, ex, gate_status, EVIDENCE, check_evidence)
    if not bad:
        print(f"✅ 证据复演通过：{ex}")
        return 0
    print(f"🔴 证据复演失败（{len(bad)} 步的产物已不在位）:")
    for step, detail in bad:
        print(f"   ❌ {step}: {detail}")
    print("   " + snapshot_guard.restore_hint(ex))
    return 1


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
    # 🔴 未知步骤拒绝：FG_FLOW_ORDER 之外的 (flow, step)（含拼写错误）一旦
    # 入账，就是一条永不参与顺序闸的僵尸记录——真实步骤仍显示未完成。
    if step not in FG_FLOW_ORDER.get(flow, ()):
        known = ", ".join(f"{f}.{s}" for f, ss in FG_FLOW_ORDER.items() for s in ss)
        print(f"✘ 拒绝标记 {flow}.{step}：不是已注册的流程步骤。\n"
              f"  已注册: {known}")
        return 1
    # 🔴 先复演已完成步的证据：产物被误删时绝不允许继续往前落账
    if _guard_existing_evidence(book_dir, extract_dir):
        return 1
    # 标记前先复核证据
    ok, detail = check_evidence(flow, step, book_dir, extract_dir)
    if not ok:
        print(f"❌ 拒绝标记 {flow}.{step}：证据未通过（{detail}）。"
              f"先完成该步工作，勿手填账本。")
        return 1
    mark(book_dir, flow, step, evidence={"detail": detail}, extract_dir=extract_dir)
    print(f"✅ 已标记 {flow}.{step} 完成（{detail}）。")
    _after_mark(book_dir, extract_dir, flow, step)
    return 0


def _default_pdf(book_dir):
    """未显式 ``--pdf`` 时取书目录里的 PDF，避免契约里 ``{pdf}`` 占位为空。"""
    try:
        cands = sorted(glob.glob(os.path.join(book_dir, "*.pdf")))
    except Exception:
        cands = []
    return cands[0] if cands else ""


def cmd_run(book_dir, flow, step, pdf=None, extract_dir=None):
    # 0) 🔴 已完成步的证据复演——上游产物被误删时，任何新脚本步都不许起跑
    if _guard_existing_evidence(book_dir, extract_dir):
        return 1
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
        cmd = spec.format(pdf=pdf or _default_pdf(book_dir), book_dir=book_dir,
                          extract_dir=extract_dir or os.path.join(book_dir, "_extract"))
        # 🔴 契约里的命令以技能根为基准书写（``flows/...``、``tools/...``、
        # ``config/...`` 都是相对路径），必须在 SKILL_ROOT 下执行；否则从任意 cwd
        # 调用都会 "can't open file '<cwd>/flows/script/xxx.py'"。
        # 同时把裸 ``python`` 换成当前解释器，避免子命令落到另一个 Python 环境。
        run_cmd = cmd
        if run_cmd.startswith("python "):
            run_cmd = '"%s" %s' % (sys.executable, run_cmd[len("python "):])
        print(f"▶ 执行 [{flow}.{step}]:\n  {run_cmd}\n")
        rc = subprocess.call(run_cmd, shell=True, cwd=SKILL_ROOT)
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
        _after_mark(book_dir, extract_dir, flow, step)
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
  flow_runner.py audit   <book_dir> [--extract <extract_dir>]   # 已完成步的证据复演（产物是否仍在位）
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
    if cmd == "audit":
        if not rest:
            print(USAGE); return 2
        ex = _pop_extract(rest)
        return cmd_audit(rest[0], ex)
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
