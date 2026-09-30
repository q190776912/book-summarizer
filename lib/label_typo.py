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

🔴 同一函数还负责**断词型**残字（2026-09-30 Evans《PDE》2ed 附录 C p720 实测）：
印刷「THEOREM 1 (Gauss-Green Theorem)」被 OCR 从词中间断开成「THEO REM 1 …」，
正字正则同样整体失配 → 附录 C 只剩定理 2..8，B 层报缺号 1、闸门 FAIL 而无从回填
（`scan_raw_items` 源侧同样看不见）。判据（同样四重，比形近型更严）：① 块首是
**两个**各 ≥2 字母的纯字母词、以空白分隔；② 首词本身**不是**正字（正字条头无需补救）；
③ 两词字母**逐字拼接后恰好等于**词表中某个正字（全等，不是编辑距离，且只容一次断点）；
④ 其后紧跟序标数字（**允许裸单号** ``1``，附录/章内计数器书页就印 "THEOREM 2"）。
全书目普查（53 本 / 含分册目录，2026-09-30）该形态**只命中 1 处**，就是这条真条头，
零假阳——所以本补救不会给别的书凭空造条目。与形近型同样只改块首、其余逐字保留。
"""
import re

__all__ = ["edit_dist_1", "label_typo_normalize"]

# 条头版式：类型词之后紧跟点分序标（一级/二级/三级）。分隔符容忍 OCR 的
# 中英标点混用（. - · ，．,）。
_LABEL_ORD_AFTER_RE = re.compile(r"^\s*[0-9]+(?:[.\-·，．,][0-9]+){1,2}")
# 断词型的序标判据放宽到「至少一段数字」：附录/章内重启的书就印裸单号条头。
_SPLIT_ORD_AFTER_RE = re.compile(r"^\s*[0-9]+(?:[.\-·，．,][0-9]+){0,2}")
_SPLIT_HEAD_RE = re.compile(r"^\s*([A-Za-z]{2,})\s+([A-Za-z]{2,})(?![A-Za-z])")


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
    """把块首**残缺的类型词**归一为 ``labels`` 中的正字，返回改写后的文本；
    无需改写（或不满足判据）返回 None。两类形态：形近型（Theorerm）与断词型（THEO REM）。"""
    canon = {w.lower(): w for w in (labels or []) if w}
    if not canon:
        return None
    return _typo_normalize(txt, canon) or _split_word_normalize(txt, canon)


def _typo_normalize(txt, canon):
    """形近型：块首单个近似词 ↔ 词表恰好一个正字编辑距离 1，其后紧跟点分序标。"""
    m = re.match(r"^\s*([A-Za-z]{5,})\b", txt or "")
    if not m:
        return None
    word = m.group(1).lower()
    if word in canon or word.rstrip("s") in canon:
        return None
    if not _LABEL_ORD_AFTER_RE.match(txt[m.end():]):
        return None
    hits = [canon[w] for w in canon if edit_dist_1(word, w)]
    if len(hits) != 1:
        return None
    return txt[:m.start(1)] + hits[0] + txt[m.end(1):]


def _split_word_normalize(txt, canon):
    """断词型：块首两个纯字母词逐字拼接**恰等于**某个正字，其后紧跟序标数字。"""
    m = _SPLIT_HEAD_RE.match(txt or "")
    if not m:
        return None
    a, b = m.group(1).lower(), m.group(2).lower()
    if a in canon:                       # 首词已是正字 = 无需补救
        return None
    word = a + b
    if word not in canon:                # 全等，不是近似
        return None
    if not _SPLIT_ORD_AFTER_RE.match(txt[m.end():]):
        return None
    return txt[:m.start(1)] + canon[word] + txt[m.end(2):]
