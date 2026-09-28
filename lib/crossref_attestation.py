"""**散文交叉引用**对账（闸门 ⑲，纯函数）——印面回指了式 `(N)`，笔记里却没人再提它。

步骤 5 允许压缩 Tier-2 散文，但**公式编号是原书正文携带的信息**：Strogatz 3e 实测，写手
把 `Equation (2) is the governing equation in the rotating frame` 写成 `That is the
governing equation…`，那个 `(2)` 就消失了。⑭/⑱ 两个 tag 对账只保证**展示式**编号不漏，
管不到**散文回指别的公式**的那一次。本书全书复算：13 章共 66 个「节 × 号」站点被丢，
且英文源与中文译**成对丢失**，读者按号找不到公式。

判据（保守优先，宁漏报不误报——五重收紧，缺一不报）：
⓪ 散文块**所属契约节点须有单元记录**——内容没收进笔记（本章习题条目整条缺席等）时无处
   补号，硬判 FAIL 只会逼出「为过闸自撰一段概览」的编造（实测 Strogatz ch13 §13.6）；
① 引用号出现在契约**散文块**（`text`）里且**句中**——行首 `(1) …` 是列表序标、
   `(1)-(3)` 的右端是范围尾巴，都不算回指；
② 编号形态干净（`^[1-9][0-9]{0,2}[a-z]?$`）：`(0)` 多是 `x(0)` 一类函数自变量、四位
   数字是文献年份，均不参与；扫描前先剥掉数学片段（`$$…$$` / `$…$` / `\\tag{…}`），
   免得把 `O ( 1 )` 这类行内式当成引用；且 `(` 前不得紧贴字母/数字/点（`4.4(1)` 是
   实验误差记法、`In(1)` 是 OCR 把 `ln` 认成 `In`，都不是回指）；
③ 该号须在**同节单元正文的 `\\tag` 池**里在账——目标公式确实还在笔记里，回指才有意义；
   跨节引用因目标不在本节池中自动豁免；
④ 该号在本节单元正文的**散文引用池**里一次都没出现（写手换句式保留了引用的不算丢）。

修法在**写手侧**：在对应句子里补回 `(N)`（EN）/`式 (N)`（CN），不改公式、不动编号。
负向测试见 `lib/tests/test_crossref_attestation.py`。
"""

import re

__all__ = ["prose_ref_numbers", "contract_prose_by_section", "dropped_crossref_problems"]

_SEC_RE = re.compile(r"^[0-9]{1,3}\.[0-9]{1,3}$")
_EMBED_SEC_RE = re.compile(r"^([0-9]{1,3}\.[0-9]{1,3})[ \t]+"
                           r"[A-Z\u4e00-\u9fff]")
_CLEAN_NUM_RE = re.compile(r"^[1-9][0-9]{0,2}[a-z]?$")
_REF_RE = re.compile(r"(?<![0-9A-Za-z_.])[（(]\s*([1-9][0-9]{0,2}[a-z]?)\s*[)）]")
# 🔴 回指的 `(` **前面不能是字母/数字/点**：印面写 `use (3)` / `式（3）`（空格或中文隔开），
# 而 `4.4(1)`（实验误差记法，Table 10.6.1）、`In(1) = 0`（OCR 把 `ln` 认成 `In`，剥数学剥不掉）
# 都是「紧贴式」写法。缺这条收紧时本书 ch10 §10.6 一次误报 3 处（表格里 `4.4(1)`/`4.3(1)`/
# `4.5(3)` 撞上同节 `\tag` 池 1/2/4），把写手指向根本不存在的丢失。
# 🔴 ``\tag`` 在正则里必须**双写**反斜杠：源码写 ``"\\tag"``（正则 = 一个字面反斜杠），
# 若误写成 ``"\t"+"ag"`` 则被 re 当成 TAB + "ag"，整条判据静默 0 命中（⑱ 开发时实测）。
_TAG_NUM_RE = re.compile(r"\\tag\s*\{\s*([0-9]{1,3}[a-z]?)\s*\}")
_DISPLAY_RE = re.compile(r"\$\$.*?\$\$", re.S)
_INLINE_MATH_RE = re.compile(r"\$[^$]*\$")
_TAG_SPAN_RE = re.compile(r"\\tag\s*\{[^}]*\}")


def _strip_math(text):
    """剥掉行间/行内数学与 `\\tag{}`，只留散文，供回指扫描。"""
    s = str(text or "")
    s = _DISPLAY_RE.sub(" ", s)
    s = _INLINE_MATH_RE.sub(" ", s)
    return _TAG_SPAN_RE.sub(" ", s)


def _cited(s, pos):
    """`s[pos]` 起的 `(N)` 是否算**句中回指**（非列表序标、非范围右端）。"""
    head = s[:pos]
    if not head.strip():
        return False
    if head.rstrip().endswith(("-", "–", "—")):
        return False
    return True


def prose_ref_numbers(text):
    """→ 正文中作为回指出现的编号集合（已剥数学、只认句中）。"""
    s = _strip_math(text)
    return {m.group(1) for m in _REF_RE.finditer(s)
            if _CLEAN_NUM_RE.match(m.group(1)) and _cited(s, m.start())}


def _has_text(d):
    return isinstance(d, dict) and isinstance(d.get("text"), str)


def _embedded_section_head(text, sec_keys):
    """文本块是否是一行**印面小节标题**（`4.8 An asymptotic formula …`）→ 节键或 None。

    实测根因（Apostol ch4 §4.7/§4.8）：小节标题排在该节第一段之前，OCR 流里它和标题后
    的续行一起被挂进了**上一节**的条目节点；于是「本节散文回指了式 (27)」被判给 §4.7，
    而 (27) 的引用其实完好地留在 §4.8 的单元里。硬判会逼写手在 §4.7 的单元里凭空补一句
    「见式 (27)」= 用编造内容喂闸门。
    🔴 认条件（宁窄勿宽）：`line_start` 行首、`N.M` 后紧跟空格 + **大写/非 ASCII** 词
    （`4.8 shows that …` 这类叙述句不认），且 `N.M` 必须是契约里真实存在的小节键。
    """
    if not isinstance(text, str):
        return None
    m = _EMBED_SEC_RE.match(text.strip())
    if not m or m.group(1) not in sec_keys:
        return None
    return m.group(1)


def _all_section_keys(tree):
    keys = set()

    def collect(node):
        if isinstance(node, dict):
            k = node.get("key")
            if k is not None and _SEC_RE.match(str(k)):
                keys.add(str(k))
            for v in node.values():
                collect(v)
        elif isinstance(node, list):
            for v in node:
                collect(v)

    collect(tree)
    return keys


def contract_prose_blocks(tree):
    """契约树 → `[(节键或 None, 所属节点键, 散文块)]`（文档序）。

    「节」= 键形如 `N.M` 的节点（与 ⑱ 的 `_sec_index` 同判据）；节内 desc/item/proof
    子节点的散文都归该节。「所属节点键」= 向上最近一个带 `key` 的祖先（`D7` / `13.6.1`
    等原样保留），用来判断这块内容在笔记里**有没有落点单元**。

    🔴 溢出小节标题（:func:`_embedded_section_head`）会**就地改判**其后各块的归属节，
    同一列表内继续生效（文档序），真实小节节点进入时照常覆盖。
    """
    sec_keys = _all_section_keys(tree)
    out = []

    def head_of(node):
        if isinstance(node, dict) and _has_text(node) and node.get("line_start"):
            return _embedded_section_head(node["text"], sec_keys)
        return None

    def walk(node, sec, owner):
        if isinstance(node, dict):
            k = node.get("key")
            ks = str(k) if k is not None else None
            cur = ks if (ks and _SEC_RE.match(ks)) else sec
            cur_owner = ks or owner
            if _has_text(node):
                bleed = head_of(node)
                if bleed:
                    cur = bleed
                out.append((cur, cur_owner, node["text"]))
            running = cur
            for c in (node.get("sub_sec") or []):
                walk(c, running, cur_owner)
                nxt = head_of(c)
                if nxt:
                    running = nxt
        elif isinstance(node, list):
            running = sec
            for v in node:
                walk(v, running, owner)
                nxt = head_of(v)
                if nxt:
                    running = nxt

    walk(tree, None, None)
    return out


def contract_prose_by_section(tree):
    """契约树 → `{节键或 None: [该节散文块, …]}`（无 § 祖先的文本归 `None` 池）。"""
    out = {}
    for sec, _owner, text in contract_prose_blocks(tree):
        out.setdefault(sec, []).append(text)
    return out


def dropped_crossref_problems(tree, unit_bodies, chapter_label=""):
    """→ 闸门 ⑲ 问题列表（判据见模块文档）。

    ``unit_bodies`` = ``{契约节点 key: [该节点的单元正文, …]}``，与 ⑱ 同签名，由
    ``gate_units`` 从 manifest 组装；源/译两目录复用同一判据。
    """
    from lib.tag_attestation import _sec_index      # 「节」归属判据 SSOT，勿另起炉灶

    sec_map = _sec_index(tree)
    sec_tags, sec_refs = {}, {}
    chap_tags, chap_refs = set(), set()
    for key, texts in (unit_bodies or {}).items():
        s = sec_map.get(str(key))
        for t in texts or []:
            if t is None:
                continue
            tags = set(_TAG_NUM_RE.findall(t))
            refs = prose_ref_numbers(t)
            sec_tags.setdefault(s, set()).update(tags)
            sec_refs.setdefault(s, set()).update(refs)
            chap_tags |= tags
            chap_refs |= refs

    unit_keys = {str(k) for k in (unit_bodies or {})}
    out = []
    by_sec = {}
    for sec, owner, text in contract_prose_blocks(tree):
        # 🔴 收紧 ⓪：这块散文**所属节点没有单元记录** = 该内容在笔记里没有落点（典型：
        # 本章习题条目 13.6.1… 整条未收进笔记）。此时「在对应句子里补回」根本无从下手，
        # 判它 FAIL 只会逼写手凭空造一段「概览」（实测 Strogatz ch13：为过闸新增了一段
        # 罗列 (1)…(13) 的自撰衔接句 = 用编造内容喂闸门，比丢号更糟）。跳过，另由
        # 内容覆盖闸门（⑩/⑫）负责「该收没收」。
        if owner is None or owner not in unit_keys:
            continue
        by_sec.setdefault(sec, []).append(text)
    for sec, texts in by_sec.items():
        tags = sec_tags.get(sec) if sec is not None else chap_tags
        refs = sec_refs.get(sec) if sec is not None else chap_refs
        if tags is None or refs is None:
            continue                       # 该节没有单元落点 = V-I 省略，不判
        cited = set()
        for t in texts:
            cited |= prose_ref_numbers(t)
        for num in sorted(cited - refs, key=lambda x: (len(x), x)):
            if not _CLEAN_NUM_RE.match(num) or num not in tags:
                continue                   # ③ 目标公式不在本节笔记里 → 跨节引用，豁免
            frag = ""
            for t in texts:
                s = _strip_math(t)
                for m in _REF_RE.finditer(s):
                    if m.group(1) == num and _cited(s, m.start()):
                        frag = " ".join(s[max(0, m.start() - 45):m.end() + 20].split())
                        break
                if frag:
                    break
            out.append("契约散文在本节回指了式 (%s)（…%s…），但该号在本节单元正文里"
                       "一次都没出现——改写时把交叉引用编号丢掉了，须在对应句子里补回"
                       " (以 \\tag 之外的散文引用形态；编号本身不改)" % (num, frag))
    if chapter_label and out:
        out = ["[%s] %s" % (chapter_label, p) for p in out]
    return out
