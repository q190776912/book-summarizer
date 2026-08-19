"""flow_gate.py — book-summarizer 流程闸控基础设施（强制顺序执行）

设计目标（用户死命令）：上一步没做完，机械上不能进入下一步。

机制
----
1. 单一真源：``FLOW_ORDER`` 定义每个 flow 的有序步骤；``FLOW_PREREQS`` 定义
   flow 之间的主干先后（prep → extract → write_source → derive）。
2. 证明账本（ledger）：``<book_dir>/_extract/.flow_gate.json`` 记录每步完成情况
   （done / ts / iso / evidence）。**仅 flow_runner 在证据复核通过后写 done**，
   禁止任何脚本/agent 手填账本。
3. 顺序闸：
   - ``require_ordered(book_dir, flow, step)`` 断言该 flow 内 step 之前的所有
     步骤均已 done；否则抛 ``FlowGateError``（硬拒绝，非零退出）。
   - ``require_flow_prereqs(book_dir, flow)`` 断言进入某 flow 前其上游 flow 的
     末步已完成。
4. 防御纵深：关键加载器（make_config / ConfigLoader / build_structure /
   verify_chapter）在**启动时就 self-assert 上游完成**，即使 agent 直接调用
   脚本也会被挡——这是"agent 忘记走 flow_runner"时的最后一道墙。
5. ``bootstrap``：对历史已合规完成之书，依据**物理证据**回填账本 +
   写出 ``_extraction_done.json``；物理证据不满足时返回缺口，**绝不伪造**。

为什么能防住 Fraleigh 那次事故
---------------------------------
- 手写 ``verify_config.json`` 不再能被下游消费：ConfigLoader 要求
  ``_extraction_done.json`` 存在，而该文件只能由 ``mm_repair_apply.py`` 在
  「条目全 resolved + 每页有 mm 标记」真完成时写出（或 bootstrap 由物理证据
  回填）。agent 手 touch 不出来。
- ``make_config.py`` 缺 ``_extraction_done.json`` 时**硬退出、绝不写退化默认文件**，
  关掉"绕过护栏"的后门。
"""
import json
import os
import time

GATE_FILE = os.path.join("_extract", ".flow_gate.json")

# 每个 flow 的有序步骤（权威副本见 flows/_flow_contract.py；两者必须对齐）。
FLOW_ORDER = {
    "prep": ["env"],
    "extract": ["place_pdf", "extract_text", "mm_repair",
                "config", "figure_detection", "structure"],
    "write_source": ["write_chapters", "embed_figures", "verify_source"],
    "derive": ["translate", "verify_cn"],
}

# 主干先后：进入某 flow 前必须完成的其它 flow（取其末步判断）。
FLOW_PREREQS = {
    "extract": ["prep"],
    "write_source": ["extract"],
    "derive": ["write_source"],
}


class FlowGateError(RuntimeError):
    """流程违规时抛出（硬拒绝，调用方应以非零退出）。"""


# --------------------------------------------------------------------------
# 账本读写
# --------------------------------------------------------------------------
def ledger_path(book_dir):
    return os.path.join(book_dir, GATE_FILE)


def _load(book_dir):
    p = ledger_path(book_dir)
    if os.path.exists(p):
        try:
            d = json.load(open(p, encoding="utf-8"))
            d.setdefault("steps", {})
            return d
        except Exception:
            return {"steps": {}}
    return {"steps": {}}


def _save(book_dir, data):
    p = ledger_path(book_dir)
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, p)


def _key(flow, step):
    return f"{flow}.{step}"


# --------------------------------------------------------------------------
# 查询 / 标记
# --------------------------------------------------------------------------
def is_done(book_dir, flow, step):
    return bool(_load(book_dir)["steps"].get(_key(flow, step), {}).get("done"))


def mark(book_dir, flow, step, evidence=None):
    """仅由 flow_runner 在证据复核通过后调用；禁止其它路径手填。"""
    data = _load(book_dir)
    data["steps"][_key(flow, step)] = {
        "done": True,
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "evidence": evidence,
    }
    _save(book_dir, data)


def unmark(book_dir, flow, step):
    """复核失败 / 回滚时清除标记（flow_runner 使用）。"""
    data = _load(book_dir)
    data["steps"].pop(_key(flow, step), None)
    _save(book_dir, data)


def require(book_dir, flow, step, msg=None):
    if not is_done(book_dir, flow, step):
        raise FlowGateError(
            msg or f"GATE BLOCKED: 必须先完成 {_key(flow, step)} 后才能继续。"
                   f"账本: {ledger_path(book_dir)}"
        )


def require_ordered(book_dir, flow, step):
    """断言 flow 内 step 之前的所有步骤均已 done；否则硬拒绝（禁止跳步）。"""
    steps = FLOW_ORDER.get(flow, [])
    if step not in steps:
        return
    idx = steps.index(step)
    missing = [s for s in steps[:idx] if not is_done(book_dir, flow, s)]
    if missing:
        raise FlowGateError(
            f"GATE BLOCKED: {_key(flow, step)} 要求本 flow 前置步骤完成，"
            f"但以下未完成: {[_key(flow, s) for s in missing]}。"
            f"禁止跳步进入 {_key(flow, step)}（账本 {ledger_path(book_dir)}）。"
        )


def require_flow_prereqs(book_dir, flow):
    """断言进入某 flow 前其上游 flow 的末步已完成。"""
    for pre in FLOW_PREREQS.get(flow, []):
        seq = FLOW_ORDER.get(pre, [])
        last = seq[-1] if seq else None
        if last and not is_done(book_dir, pre, last):
            raise FlowGateError(
                f"GATE BLOCKED: 进入 flow '{flow}' 前必须完成 flow '{pre}'"
                f"（缺 {_key(pre, last)}；账本 {ledger_path(book_dir)}）。"
            )


def status(book_dir):
    """返回 {flow: {step: bool}} 供 status 命令打印。"""
    return {flow: {s: is_done(book_dir, flow, s) for s in steps}
            for flow, steps in FLOW_ORDER.items()}


# --------------------------------------------------------------------------
# 历史书回填（依据物理证据，绝不伪造）
# --------------------------------------------------------------------------
def bootstrap(book_dir, extract_dir):
    """对历史已合规完成之书，按物理证据回填账本。

    **严格按 FLOW_ORDER 顺序、遇缺口即停**：某步物理证据不满足时，它及之后
    所有依赖步骤一律不回填（因为它们本就不应在缺口存在时成立——这正是
    Fraleigh 事故的本质：config/structure 文件虽存在，却是跳步 premature 产物）。
    返回 (ok, gaps) 供调用方提示；绝不伪造。
    """
    from flows._flow_contract import check_evidence

    flow = "extract"
    steps = FLOW_ORDER.get(flow, [])
    # 先清空本 flow 旧标记，保证重跑幂等、不从错误状态累积
    for s in steps:
        unmark(book_dir, flow, s)

    gaps = []
    stopped = False
    for s in steps:
        if stopped:
            gaps.append((f"{flow}.{s}", "前置步骤未满足，不回填（依赖链中断）"))
            continue
        ok, detail = check_evidence(flow, s, book_dir, extract_dir)
        if ok:
            mark(book_dir, flow, s, evidence={"bootstrap": True, "detail": detail})
        else:
            gaps.append((f"{flow}.{s}", detail))
            stopped = True
    # mm_repair 真完成（含 legacy 物理核对通过）则补写规范完成标记，
    # 让历史书也能被下游 ConfigLoader 的上游闸识别。
    if is_done(book_dir, flow, "mm_repair"):
        marker = os.path.join(extract_dir, "_extraction_done.json")
        if not os.path.exists(marker):
            try:
                import json as _json
                _json.dump({
                    "bootstrapped": True,
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                    "note": "由 flow_runner bootstrap 依据物理证据补写；"
                            "非 mm_repair_apply 原生写出。",
                }, open(marker, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
            except Exception:
                pass
    return (len(gaps) == 0), gaps
