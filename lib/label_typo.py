# -*- coding: utf-8 -*-
"""类型词（Theorem/Lemma/…）OCR 形近残字的归一——抽取器与查漏校验的**单一真源**。

为什么需要：印刷条头「Theorem 2.7 …」被 OCR 读成「Theorerm 2.7 …」
（Apostol《Introduction to Analytic Number Theory》ch2 p42 实测 2026-09-28）时，
按正字构造的类型词正则**整体失配**：条目既不入分章契约，也不在源侧候选集里，
闸门只剩 B 层「序列 1..27 缺号 7」的死锁（差集为空，回填无从下手）。

为什么必须共用：此前只有 `check_structure_completeness` 侧有补救，抽取器
（`extract_items_en`）没有 → 校验看得见、契约看不见，于是每次重建契约都要重跑
一次 `--backfill` 才绿（数据修补，不是根治）。两处调同一判据后，抽取器自己就能
把条目收进契约，闸门一次通过。

判据（四重，宁缺毋滥）：① 块首是一个 ≥5 字母的纯字母词；② 该词**不是**词表正字，
也**不是**正字的复数形（复数只出现在交叉引用/眉题，永不是条头）；③ 与词表中
**恰好一个**类型词编辑距离恰为 1；④ 其后紧跟条目序标数字（``2.7`` / ``2.7.1``
形态）——条头版式的必要条件，散文里孤立的近似词（"These 2.7 …"）不触发。
只改块首这一个词，其余字符逐字保留、偏移量不变（调用方可沿用原 match 位置）。
"""
import re

__all__ = ["edit_dist_1", "label_typo_normalize"]

# 条头版式：类型词之后紧跟点分序标（一级/二级/三级）。分隔符容忍 OCR 的
# 中英标点混用（. - · ，．,）。
_LABEL_ORD_AFTER_RE = re.compile(r"^\s*[0-9]+(?:[.\-·，．,][0-9]+){1,2}")


def edit_dist_1(a, b):
    """a、b 是否恰为一次插入/删除/替换（编辑距离 1）。「theorerm」↔「theorem」即此形。"""
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la == lb:
        return sum(1 for x, y in zip(a, b) if x != y) == 1
    if la > lb:
        a, b, la, lb = b, a, lb, la
    i = 0
    while i < la and a[i] == b[i]:
        i += 1
    return a[i:] == b[i + 1:]


def label_typo_normalize(txt, labels):
    """把块首**形近残缺的类型词**归一为 ``labels`` 中的正字，返回改写后的文本；
    无需改写（或不满足四重判据）返回 None。"""
    m = re.match(r"^\s*([A-Za-z]{5,})\b", txt or "")
    if not m:
        return None
    word = m.group(1).lower()
    canon = {w.lower(): w for w in (labels or []) if w}
    if not canon or word in canon or word.rstrip("s") in canon:
        return None
    if not _LABEL_ORD_AFTER_RE.match(txt[m.end():]):
        return None
    hits = [canon[w] for w in canon if edit_dist_1(word, w)]
    if len(hits) != 1:
        return None
    return txt[:m.start(1)] + hits[0] + txt[m.end(1):]
