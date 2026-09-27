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

本模块同时提供闸门 ⑭ 的**对偶** —— 闸门 **⑱**「收割漏号」
``unharvested_anchor_tags``（印面 `(N)` 锚点在契约里在档、其展示式却没登记 tag）+
``unharvested_anchor_problems``（四条收紧判据：有单元记录 / 同节正文里该号整体消失 /
编号形态干净 / 印刷序列有邻居，全语料 477 章实测 491→22）。判据与用法见函数文档。
"""

import re

__all__ = ["collect_contract_tags", "tag_attestation_problems",
           "unattested_tags", "strip_unattested", "dir_page_loader",
           "unharvested_anchor_tags", "unharvested_anchor_problems",
           "rendered_numbers"]


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


def dir_page_loader(*dirs):
    """→ ``load(pdf_page)``：该页**可能承载印刷编号**的全部块文本（正文 + MFD 公式
    latex），找不到页文件返回 None。

    ⑭ / 剔除 / 事后修复三处共用同一读页口径（旧实现只住在 `gate_units` 里，
    `build_structure` 想在落盘前剔除就得复制一份——两份读页逻辑必然分叉）。
    MM 修复后的页里 ``text`` 可能再套一层 ``{"text": {"text": ...}}``，一并摊平。
    """
    import json
    import os

    cache = {}

    def _flat(s):
        if isinstance(s, dict):
            s = s.get("text")
        return str(s or "")

    def load(pg):
        if pg in cache:
            return cache[pg]
        val = None
        for d in dirs:
            if not d:
                continue
            for name in ("page_%03d.json" % pg, "page_%d.json" % pg,
                         "page_%04d.json" % pg):
                p = os.path.join(d, name)
                if os.path.exists(p):
                    try:
                        with open(p, encoding="utf-8") as f:
                            d_ = json.load(f)
                    except Exception:
                        d_ = {}
                    val = ([_flat(b.get("text")) for b in (d_.get("text") or [])]
                           + [str(b.get("latex") or "")
                              for b in (d_.get("formulas") or [])])
                    break
            if val is not None:
                break
        cache[pg] = val
        return val

    return load


_LETTER_RE = re.compile(r"[A-Za-z]")


def _condemned(tree, page_loader):
    """→ (tags, kinds)；``kinds`` = {判毒 tag: 理由码}。页窗不可判时返回 (tags, {})。

    理由码：
    * ``unattested`` —— 页窗内既无 `(N)` 也无独立裸块锚点；
    * ``bare-only`` —— 只有裸排锚点，而本章编号以 `(N)` 为主；
    * ``lettered`` —— tag 含字母，而本章编号绝大多数是纯整数（字母尾巴 = 公式碎片 /
      换行粘连，如 Strogatz 3e ch7 的 `2n` 来自 `2` + 下一行 `n ?`）。
    """
    tags = collect_contract_tags(tree)
    if not tags:
        return tags, {}
    try:
        lo, hi = int(tree.get("page_start")), int(tree.get("page_end"))
    except (TypeError, ValueError):
        return tags, {}
    avail = [p for p in range(lo, hi + 1) if page_loader(p)]
    if not avail:
        return tags, {}
    paren, bare = _label_index(page_loader, lo, hi)
    paren_hits = [n for _k, n in tags if n in paren]
    bare_only = [n for _k, n in tags if n not in paren and n in bare]
    unattested = [n for _k, n in tags if n not in paren and n not in bare]
    kinds = {n: "unattested" for n in unattested}
    if len(paren_hits) >= 5 and len(paren_hits) >= 0.9 * (len(paren_hits) + len(bare_only)):
        for n in bare_only:
            kinds.setdefault(n, "bare-only")
    lettered = [n for _k, n in tags if _LETTER_RE.search(n)]
    numeric = [n for _k, n in tags if not _LETTER_RE.search(n)]
    if (len(numeric) >= 5 and lettered
            and len(lettered) <= 0.10 * (len(numeric) + len(lettered))):
        for n in lettered:
            kinds.setdefault(n, "lettered")
    return tags, kinds


def unattested_tags(tree, page_loader):
    """契约里**无印刷锚点 / 形态与本章体例矛盾**的 tag 集合（收割处剔除的判据）。

    与 :func:`tag_attestation_problems` 同一套判据（共用 :func:`_condemned`），
    只换成「集合」出口，供两处消费：① `build_structure` 落盘前剔除（毒 tag 不进契约）；
    ② 老契约的事后修复（步骤 5 单元已写毕、不能重建契约的书）。
    """
    return set(_condemned(tree, page_loader)[1])


def strip_unattested(tree, page_loader):
    """**就地**删除 ``tree`` 内被判毒的公式 tag（``tag`` 字段与 ``tags`` 列表元素）。

    → 被删除的 tag 字符串列表（去重、按文档序）。删除后公式块仍在（正文不丢），
    只是不再声称自己带编号 —— 单元侧因此既不该写 `\tag{}`，也不该因缺它被判漏写。
    """
    tags, kinds = _condemned(tree, page_loader)
    condemned = set(kinds)
    if not condemned:
        return []
    removed = []

    def walk(node):
        if isinstance(node, dict):
            if node.get("formula") is not None:
                t = _norm(node.get("tag"))
                if t and t in condemned:
                    removed.append(t)
                    node["tag"] = ""
                    node.pop("tags", None)
                elif node.get("tags"):
                    keep = [x for x in node["tags"] if _norm(x) not in condemned]
                    if len(keep) != len(node["tags"]):
                        removed.extend(_norm(x) for x in node["tags"] if _norm(x) in condemned)
                        node["tags"] = keep
            for c in node.get("sub_sec") or []:
                walk(c)
        elif isinstance(node, list):
            for c in node:
                walk(c)

    walk(tree)
    seen, out = set(), []
    for t in removed:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def tag_attestation_problems(tree, page_loader, chapter_label=""):
    """→ 问题描述列表（空 = 全部 tag 有印刷锚点）。

    ``tree`` 分章契约（dict，需 ``page_start``/``page_end``）；``page_loader(pg)``
    给该页文本块内容列表或 None（缺页文件时**跳过不判**，fail-open 于缺数据、
    判毒只依据「有页而找不到锚点」）。
    """
    tags, kinds = _condemned(tree, page_loader)
    if not kinds:
        return []
    try:
        lo, hi = int(tree.get("page_start")), int(tree.get("page_end"))
    except (TypeError, ValueError):
        return []
    paren, bare = _label_index(page_loader, lo, hi)
    paren_hits = [n for _k, n in tags if n in paren]
    bare_only = [n for _k, n in tags if n not in paren and n in bare]
    lettered = [n for _k, n in tags if _LETTER_RE.search(n)]
    numeric = [n for _k, n in tags if not _LETTER_RE.search(n)]
    out = []
    for n in kinds:
        if kinds[n] == "unattested":
            out.append("契约编号 %s 在本章页窗 p%d–p%d 内找不到任何印刷锚点"
                       "（既无 `(N)` 也无独立成块的裸 N）—— 疑似 OCR 噪声"
                       "（公式内部数字 / 小数尾巴 / 带单位的量），须在收割处剔除，"
                       "不得由写手凭空 \\tag" % (n, lo, hi))
        elif kinds[n] == "bare-only":
            pct = 100.0 * len(paren_hits) / max(1, len(paren_hits) + len(bare_only))
            out.append("契约编号 %s 只有裸排锚点，而本章编号 %d%% 印作 `(N)`"
                       "—— 裸数字块多半是公式内部碎片而非编号列，须在收割处剔除"
                       % (n, round(pct)))
        else:
            out.append("契约编号 %s 含字母，而本章 %d 个编号里 %d 个是纯整数"
                       "—— 字母尾巴多半是公式碎片 / 换行粘连（如 `2` + 下行 `n…`），"
                       "须在收割处剔除" % (n, len(numeric) + len(lettered), len(numeric)))
    if chapter_label and out:
        out = ["[%s] %s" % (chapter_label, p) for p in out]
    return out


# ── 闸门 ⑭ 的**对偶**：印面有编号、契约却没挂上（收割漏号）────────────────────
_ANCHOR_ONLY_RE = re.compile(r"^\(\s*([0-9]{1,3}[a-z]?)\s*\)[.。]?$")
# 🔴 ``\\tag`` 在正则里必须**双写**反斜杠：``"\t"+"ag"`` 会被 re 当成 TAB + "ag"，
# 整条判据静默 0 命中（本模块开发时实测：单元正文有 9 个 \tag，findall 返回 []）。
_UNIT_TAG_RE = re.compile(r"\\tag\s*\{\s*([0-9]{1,3}[a-z]?)\s*\}")
_UNIT_PAREN_RE = re.compile(r"\(\s*([0-9]{1,3}[a-z]?)\s*\)")
_SEC_RE = re.compile(r"^[0-9]{1,3}\.[0-9]{1,3}$")
_CLEAN_NUM_RE = re.compile(r"^[1-9][0-9]{0,2}[a-z]?$")
_NUM_HEAD_RE = re.compile(r"^[0-9]+")


def _content_seq(node):
    """节点**自己的**内容块序列（按文档序，剔除子节点壳）。"""
    return [b for b in (node.get("sub_sec") or [])
            if isinstance(b, dict) and ("text" in b or "formula" in b)]


def unharvested_anchor_tags(tree):
    """契约树 → [(节点 key, 编号, 公式片段)]：`(N)` 锚点在档、其公式块却无 tag。

    闸门 ⑭ 管「契约多挂了原书没印的号」（毒 tag）；本函数管**反方向**——收割把
    印面编号弄丢，契约不登记，写手按契约对账永远看不见自己少写一个号，章级
    tag 集合比较又常被同章别处的同号掩盖（实测 Strogatz 3e ch13 §13.5：印面
    `(1)` 紧跟展示式 `r e^{i\\psi} = \\langle e^{i\\theta} \\rangle`，而契约该块
    无 `tag`，单元从 `\\tag{2}` 起写；`(1)` 在 §13.4 也在账 → 章级闸放行）。

    判据（保守，宁漏报不误报）：同一节点的内容块序列里，一个「整块只有 `(N)`」
    的文本锚点，其**前一个内容块**是 `display` 公式，且该公式块既无 `tag`、
    编号也不在其 `tags` 列表里 → 判漏挂。锚点前允许再夹若干同类锚点（多行公式
    组逐行编号时，收割会把若干号一并挂到相邻块上）。**不判**：锚点前是散文块
    （OCR 把公式切成多块，无从断定归属）、公式块已带 `tag`、裸排编号（无括号）。
    """
    out = []

    def visit(node):
        if isinstance(node, list):
            for c in node:
                visit(c)
            return
        if not isinstance(node, dict):
            return
        seq = _content_seq(node)
        for i, blk in enumerate(seq):
            txt = blk.get("text")
            if txt is None:
                continue
            m = _ANCHOR_ONLY_RE.match(txt.strip())
            if not m:
                continue
            num = m.group(1)
            j = i - 1
            while j >= 0 and _ANCHOR_ONLY_RE.match((seq[j].get("text") or "").strip()):
                j -= 1
            if j < 0:
                continue
            prev = seq[j]
            if prev.get("formula") is None or not prev.get("display"):
                continue
            have = [_norm(prev.get("tag"))] + [_norm(x) for x in (prev.get("tags") or [])]
            if num in [h for h in have if h]:
                continue
            out.append((node.get("key"), num, str(prev.get("formula"))[:60]))
        for c in node.get("sub_sec") or []:
            if isinstance(c, dict) and c.get("key") is not None:
                visit(c)

    visit(tree)
    seen, uniq = set(), []
    for k, n, f in out:
        if (k, n) in seen:
            continue
        seen.add((k, n))
        uniq.append((k, n, f))
    return uniq


def rendered_numbers(text):
    """单元正文里**已按印刷形态出现过**的编号集合。

    ``\\tag{N}`` 与裸 ``(N)`` 都收：⑱ 只抓「整号凭空消失」，同一号的排版形态差异
    （``\\qquad (N)`` / ``\\tag{N}``）属另一判据，不能在这里制造误报。
    """
    s = str(text or "")
    out = set(m.group(1) for m in _UNIT_TAG_RE.finditer(s))
    out |= set(m.group(1) for m in _UNIT_PAREN_RE.finditer(s))
    return out


def _sec_index(tree):
    """契约树 → ({节点 key: 最近 §N.M 祖先或 None}, 全章是否含二级节的任一信号)。

    「节」= 键形如 ``N.M`` 的祖先（三级 ``N.M.K`` 与 ``chN`` 都向上找）。用于把
    逃逸池限定在同一节的单元正文并集——Strogatz 3e ch13 实测：漏的 `(1)` 在
    §13.4 也在账，章级集合比较因此失明，按节取池才既能定位真漏、又不被别处同号掩盖。
    """
    sec = {}

    def walk(node, chain):
        if isinstance(node, dict):
            k = node.get("key")
            nk = chain + [str(k)] if k is not None else chain
            if k is not None:
                sec.setdefault(str(k), _nearest_sec(nk))
            for c in node.get("sub_sec") or []:
                walk(c, nk)
        elif isinstance(node, list):
            for c in node:
                walk(c, chain)

    walk(tree, [])
    return sec


def _nearest_sec(chain):
    for k in reversed(chain):
        if _SEC_RE.match(k):
            return k
    return None


def unharvested_anchor_problems(tree, unit_bodies, chapter_label=""):
    """→ 闸门 ⑱ 问题列表：印面 `(N)` 在契约在档、其展示式无 tag、**且本章正文里
    整个号消失了**。

    ``unit_bodies`` = ``{契约节点 key: [该节点的单元正文, …]}``（manifest 已登记的
    节点；未登记的节点 = 无落点，属 V-I 省略，不判）。

    四条收紧判据（全语料 477 章实测：只用「相邻 + 有单元记录」报 491 处、再加号
    形态与逃逸池报 96 处，本函数四条后剩 22 处且逐处抽检为真漏 —— 判据保守，宁漏
    报不误报）：
    ① 节点须在 ``unit_bodies`` 里（无落点不判）；
    ② 该号在**同节**（无 § 祖先时退全章）单元正文里既不以 ``\\tag`` 也不以 ``(N)``
       出现过 —— 写手以别的排版形态渲染过 = 不算丢失；
    ③ 编号形态干净（``^[1-9][0-9]{0,2}[a-z]?$``）：``(00)``/``(000)`` 一类是 OCR
       碎片，不参与判漏；
    ④ 该号在印刷序列里**有邻居**（``N-1`` 或 ``N+1`` 出现在同一逃逸池里）：真漏的
       号总是连续号段里的一个洞；散文里的交叉引用 ``(3)``（"…use (3) also in
       connection with…"）自成一块却无邻居，据此排除。键含 ``-``（习题条目）一并
       排除——题号与公式号不同源。

    修法在**收割/回填**（给该公式块补 `tag` + manifest `tags`，再让单元补
    `\\tag{}`），**不是**让写手凭空编号——那会被「契约 ↔ 单元 tag 对账」判成编造。
    """
    bodies = {str(k): [t for t in (v or []) if t is not None]
              for k, v in (unit_bodies or {}).items()}
    node_pool = {k: set() for k in bodies}
    for k, texts in bodies.items():
        for t in texts:
            node_pool[k] |= rendered_numbers(t)
    sec_map = _sec_index(tree)
    sec_pool, chapter_pool = {}, set()
    for k, pool in node_pool.items():
        chapter_pool |= pool
        s = sec_map.get(k)
        if s is not None:
            sec_pool.setdefault(s, set()).update(pool)
    out = []
    for key, num, frag in unharvested_anchor_tags(tree):
        k = str(key)
        if k not in bodies:
            continue
        if not _CLEAN_NUM_RE.match(num):
            continue
        if "-" in k:
            continue
        s = sec_map.get(k)
        pool = sec_pool.get(s) if s is not None else chapter_pool
        if pool is None:
            pool = set()
        pool |= node_pool.get(k, set())
        if num in pool:
            continue
        try:
            base = int(_NUM_HEAD_RE.match(num).group(0))
            tail = num[len(str(base)):]
            nbr = {"%d%s" % (base - 1, tail), "%d%s" % (base + 1, tail)}
        except (AttributeError, ValueError):
            nbr = set()
        if not (pool & nbr):
            continue
        out.append("印面编号 (%s) 在契约节点 %s 里以锚点文本块在档，但其展示式未登记 tag"
                   "（`%s…`），且该号在本节单元正文里整体消失（相邻号 %s 在账）"
                   "—— 收割漏号，须回填契约 tag + manifest 后由单元补 \\tag{%s}"
                   % (num, key, frag,
                      "/".join(sorted(x for x in (pool & nbr) if x)), num))
    if chapter_label and out:
        out = ["[%s] %s" % (chapter_label, p) for p in out]
    return out
