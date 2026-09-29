"""契约内容块的**人工裁定**登记（① 确定性复算闸的管线输入）。

`verify/script/check_content_completeness.py` 的 ① 项把磁盘契约与
`attach_content.build_chapter_contract` 的内存重算做**内容块多重集比对**，
不等即 FAIL。但有两类**印面裁定**天然会让磁盘偏离纯重算，且都不可让磁盘就范：

  * **噪声残块**——扫描件 OCR 把 `x).` / `(VD).` / `(Ω).` / 折行节题残块切成独立
    text 块，管线照收，人工按印面把它们从契约里剔掉。复算仍会吐出这些块 →
    「契约缺块」假 FAIL；
  * **编号挪位**——`(C.N)` 由 OCR 的 y 序挂到**隔壁**展示式上（Iwaniec–Kowalski
    ch1 实测：`(1.100)` 印在 $c(\\mathcal P)$ 式右缘，管线挂到 $f(n)=\\sum$ 式；
    `(1.104)` 则整块丢失）。人工按印面把 tag 挪到正确的式上 → 同一式
    「缺块 + 多块」对称假 FAIL。

旧处置是「登记为人工裁定偏离、不再跑 ①」——偏离账本挡不住闸，任何后续会话重跑
步骤 4 都会撞回同一地 FAIL，且没人知道那 8 处是核过的。本模块把裁定**变成管线
输入**：登记在 `verify_config.json` 的 `content_overrides`，由
`attach_content.build_chapter_contract` 在**统计之前**执行（写入侧与复算侧同一
函数、同一谓词），于是「重算 = 磁盘」由构造成立，① 重新可用。

登记格式（列表，每项一笔；`ch` = 章键字符串）::

    {"ch": "9",  "op": "drop",  "kind": "text", "match": "x).",
     "page": 240, "reason": "OCR 噪声残块（印面无此独立行）"}
    {"ch": "1",  "op": "retag", "kind": "formula", "match": "f ( n ) = ...",
     "tag": "", "page": 36, "reason": "(1.100) 印在 c(P)=… 式右缘，挪走"}

判据纪律：
  * `match` 用 **① 残差行打印的归一化文本**（`_norm` 只压空白、不改字符），
    全等匹配，不做子串——防止一笔登记顺手吞掉别的正文；
  * 一笔登记**必须落在磁盘上**（`disk_audit`）：`drop` 后磁盘不得再有该块，
    `retag` 后磁盘必须有该块且 tag 等于登记值。登记腐烂（管线改版后块变了、
    磁盘却还留着）由 ① 直接 FAIL，而不是静默失效；
  * 未登记的偏离照旧 FAIL——本模块是**账本**，不是豁免开关。

负向测试见 ``lib/tests/test_content_overrides.py``。
"""

import json
import os
import re

KEY = "content_overrides"
_KIND_KEY = {"text": "text", "formula": "formula", "image": "image"}

__all__ = ["KEY", "norm", "load", "ops_for", "apply_overrides", "disk_audit"]


def norm(s):
    """① 残差行的口径：只压空白，不动字符（登记值可直接从 FAIL 行复制）。"""
    return re.sub(r"\s+", " ", (s if isinstance(s, str) else "")).strip()


def load(ext):
    """``verify_config.json`` 的 ``content_overrides`` → ``{ch_key: [op, ...]}``。

    兼容扁平（顶层键）与分组（``ch`` / ``appendix`` / ``supplement``）两种配置
    形状；缺文件 / 坏 JSON / 形状不符 → 空 dict（判据退回既往行为，绝不抛）。
    """
    path = os.path.join(str(ext), "verify_config.json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8-sig") as f:
            cfg = json.load(f)
    except Exception:
        return {}
    out = {}

    def harvest(node):
        if not isinstance(node, dict):
            return
        ops = node.get(KEY)
        if not isinstance(ops, list):
            return
        for op in ops:
            if isinstance(op, dict) and op.get("ch") is not None:
                out.setdefault(str(op["ch"]), []).append(op)

    if isinstance(cfg, dict):
        harvest(cfg)
        for k in ("ch", "appendix", "supplement"):
            harvest(cfg.get(k))
    return out


def ops_for(ext, ch_key):
    return load(ext).get(str(ch_key)) or []


def _iter_blocks(node):
    """契约树 → (parent, block) 对，深度优先（块 = 带 text/formula/image 的叶子）。"""
    kids = node.get("sub_sec")
    if not isinstance(kids, list):
        return
    for c in kids:
        if not isinstance(c, dict):
            continue
        if any(k in c for k in _KIND_KEY.values()):
            yield node, c
        else:
            yield from _iter_blocks(c)


def _matches(block, op):
    key = _KIND_KEY.get(str(op.get("kind") or ""))
    if not key or key not in block:
        return False
    return norm(block.get(key)) == norm(op.get("match"))


def _apply_one(tree, op):
    op_kind = str(op.get("op") or "")
    hit = 0
    if op_kind == "drop":
        for parent, blk in list(_iter_blocks(tree)):
            if _matches(blk, op):
                parent["sub_sec"].remove(blk)
                hit += 1
        return hit
    if op_kind == "retag":
        want = norm(op.get("tag"))
        for _parent, blk in _iter_blocks(tree):
            if _matches(blk, op):
                if want:
                    blk["tag"] = want
                else:
                    blk.pop("tag", None)
                hit += 1
        return hit
    return 0


def apply_overrides(tree, ops):
    """就地执行登记；返回 ``[(op, 命中块数), ...]``（调用方用于自证）。"""
    return [(op, _apply_one(tree, op)) for op in (ops or [])]


def disk_audit(tree, ops):
    """登记是否**真的落在磁盘契约上** → 问题清单（空 = 全部生效）。

    ① 用它把「登记腐烂」变成 FAIL 而不是静默通过：管线改版后块消失时，
    磁盘上要么找不到该块（drop 之外 / retag），要么 tag 不等于登记值。
    """
    problems = []
    for op in (ops or []):
        op_kind = str(op.get("op") or "")
        hits = [b for _p, b in _iter_blocks(tree) if _matches(b, op)]
        if op_kind == "drop":
            if hits:
                problems.append("drop 未生效：磁盘仍有 %d 个匹配块 %r"
                                % (len(hits), norm(op.get("match"))[:60]))
        elif op_kind == "retag":
            want = norm(op.get("tag"))
            if not hits:
                problems.append("retag 失配：磁盘无匹配块 %r"
                                % norm(op.get("match"))[:60])
            elif any(norm(b.get("tag")) != want for b in hits):
                got = sorted({norm(b.get("tag")) for b in hits})
                problems.append("retag 未生效：期望 tag=%r，磁盘=%s（%r）"
                                % (want, got, norm(op.get("match"))[:40]))
        else:
            problems.append("未知 op=%r（只支持 drop / retag）" % op_kind)
    return problems
