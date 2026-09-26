"""契约公式编号的**印刷锚点**审计（闸门 ⑭，纯函数）。

契约 tag 是步骤 5 门控的对账真值：契约里多一个原书**根本没印过**的编号，写手就被
逼着凭空 ``\\tag{}``（「编造」），删了又报「漏写」——两头堵。实测 Kreyszig 五个毒
tag 全属此类：``22``（display 里两个 ε/2 的分母被 OCR 成独立数字块）、``50``/``25``
（``= 0.50`` 的小数尾巴）、``18751A``/``12818A``（波长 ``18 751 Å``）。

判据（保守优先——漏报可接受，误报会把写手卡在门外）：
① tag 在本章页窗内**既无** ``(N)`` 形态的印刷编号、**也无**独立成块的裸 ``N`` →
   无锚点，判毒；
② 本章编号以 ``(N)`` 为主（parenthesized 占比 ≥90% 且 ≥5 个）时，只有裸排锚点的
   tag 判毒——带括号的书里，裸数字块几乎总是公式内部碎片而不是编号列。

负向测试见 ``lib/tests/test_tag_attestation.py``。
"""

import re

__all__ = ["collect_contract_tags", "tag_attestation_problems"]


def _norm(tag):
    s = str(tag if tag is not None else "").strip()
    return s


def collect_contract_tags(tree):
    """契约树 → [(节点 key, tag 字符串)]，按文档序；``tags`` 列表展开在 ``tag`` 之后。"""
    out = []

    def walk(node):
        if isinstance(node, dict):
            blk = node.get("formula")
            if blk is not None:
                for t in ([node.get("tag")] if not node.get("tags")
                          else [node.get("tag")] + list(node.get("tags") or [])):
                    n = _norm(t)
                    if n:
                        out.append((node.get("key"), n))
            for c in node.get("sub_sec") or []:
                walk(c)
        elif isinstance(node, list):
            for c in node:
                walk(c)

    walk(tree)
    seen, uniq = set(), []
    for k, n in out:
        if n in seen:
            continue
        seen.add(n)
        uniq.append((k, n))
    return uniq


_LABEL_TAIL = r"[A-Za-z]*[\*'’′]*"
_PAREN_LABEL_RE = re.compile(r"[（(]\s*(\d+(?:[.．]\d+)*%s)\s*[)）]" % _LABEL_TAIL)
_BARE_LABEL_RE = re.compile(r"\d+(?:[.．]\d+)*%s" % _LABEL_TAIL)
_LATEX_NOISE_RE = re.compile(r"\\[a-zA-Z]+\s*")


def _label_forms(raw):
    """一个页内块 → 它可能承载编号的**书写形态**。

    MFD 把左缘印刷编号当公式检测出来时，`(7c')` 长成 ``( 7 \\mathbf { c } ^ { \\prime } )``、
    `(7*)` 长成 ``( 7 ^ { * } )``——不还原成扁平形态就永远「查无锚点」，闸门会把**真实**
    印刷编号判成噪声（反向误伤）。故对含反斜杠的块额外给一份去掉宏名/花括号/空格/上标
    符的形态（`\\prime`→`'`）。
    """
    s = str(raw or "").strip()
    if not s:
        return
    yield s
    if re.search(r"\\|\^|[{}]", s):
        t = s.replace("\\prime", "'")
        t = _LATEX_NOISE_RE.sub("", t)
        t = re.sub(r"[{}\s^]", "", t)
        if t and t != s:
            yield t


def _label_index(page_loader, lo, hi):
    """页窗 → (parenthesized 集合, 裸排集合)。

    ``paren`` 收**任意块内**出现的 ``(N)``（编号被 OCR 粘进公式行、或被 MFD 当公式
    检测出来都认），``bare`` 只收**整块就是一个数**的块。
    """
    paren, bare = set(), set()
    for pg in range(int(lo), int(hi) + 1):
        blocks = page_loader(pg)
        if not blocks:
            continue
        for raw in blocks:
            for t in _label_forms(raw):
                tt = t.replace("．", ".")
                if _BARE_LABEL_RE.fullmatch(tt):
                    bare.add(tt)
                for m in _PAREN_LABEL_RE.finditer(tt):
                    paren.add(m.group(1).replace("．", "."))
    return paren, bare


def tag_attestation_problems(tree, page_loader, chapter_label=""):
    """→ 问题描述列表（空 = 全部 tag 有印刷锚点）。

    ``tree`` 分章契约（dict，需 ``page_start``/``page_end``）；``page_loader(pg)``
    给该页文本块内容列表或 None（缺页文件时**跳过不判**，fail-open 于缺数据、
    判毒只依据「有页而找不到锚点」）。
    """
    try:
        lo, hi = int(tree.get("page_start")), int(tree.get("page_end"))
    except (TypeError, ValueError):
        return []
    tags = collect_contract_tags(tree)
    if not tags:
        return []
    avail = [p for p in range(lo, hi + 1) if page_loader(p)]
    if not avail:
        return []
    paren, bare = _label_index(page_loader, lo, hi)

    paren_hits = [n for _k, n in tags if n in paren]
    bare_only = [n for _k, n in tags if n not in paren and n in bare]
    unattested = [n for _k, n in tags if n not in paren and n not in bare]

    out = []
    for n in unattested:
        out.append("契约编号 %s 在本章页窗 p%d–p%d 内找不到任何印刷锚点"
                   "（既无 `(N)` 也无独立成块的裸 N）—— 疑似 OCR 噪声"
                   "（公式内部数字 / 小数尾巴 / 带单位的量），须在收割处剔除，"
                   "不得由写手凭空 \\tag" % (n, lo, hi))
    if len(paren_hits) >= 5 and len(paren_hits) >= 0.9 * (len(paren_hits) + len(bare_only)):
        pct = 100.0 * len(paren_hits) / (len(paren_hits) + len(bare_only))
        for n in bare_only:
            out.append("契约编号 %s 只有裸排锚点，而本章编号 %d%% 印作 `(N)`"
                       "—— 裸数字块多半是公式内部碎片而非编号列，须在收割处剔除"
                       % (n, round(pct)))
    if chapter_label and out:
        out = ["[%s] %s" % (chapter_label, p) for p in out]
    return out
