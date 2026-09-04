"""item_dedup.py — shared item-dedup helpers for every scheme extractor.

The problem
-----------
A single numbered item (Definition / Theorem / Proposition / …) is typically
mentioned on several pages: its genuine definition heading plus various
forward/backward references.  We must coalesce those mentions down to the ONE
definition entry (so write-source fetches the correct anchor page), but we must
NOT drop a *second* genuinely different item that merely shares the same
(label, number) with an earlier one.

The latter happens when the source book itself prints the same number twice —
a printing off-by-one.  Example: Lasota & Mackey, *Chaos, Fractals, and Noise*,
prints ``Proposition 12.8.3`` on p.452 **and** again on p.454 with a *different*
heading (the second one is logically 12.8.4).  A naive dedup keyed only on
(label, number) silently discards the second proposition, losing a real item
from the per-chapter contract (``book_structure/ch{N}.json``).

The fix
-------
Group by (label, number).  On a same-key collision, keep the new occurrence as
a SEPARATE entry only when it is itself a genuine heading AND its heading text
differs from the already-kept genuine heading.  Same key + same heading text
(a restatement / duplicate match) is coalesced.  This honours both the *page*
(the two genuine headings sit on different pages) and the *name* (heading text)
discriminants the user asked for, while still collapsing true reference mentions.
"""
import re
from collections import OrderedDict


def _after_of(it):
    key = it['key']
    mstart = it.get('mstart', 0)
    ko = 5 if mstart >= 5 else mstart   # offset of key start within text slice
    return it['text'][ko + len(key):]


_REF_AFTER_NEG = re.compile(
    r'^\.'                                              # 1. period right after number → sentence fragment
    r'|\(below\)|\(above\)'                             # 2. (below)/(above)
    r'|in the next|in the following|in §|in sec'          # 3. forward/backward section ref
    r'|this\s+(?:theorem|lemma|space|definition|result|operator)\b'  # 4. "this X"
    r'|\b(?:states?|shows?|proves?|implies?|follows?)\s+that'        # 5a. 3c verbs + that
    r'|\bwe\s+have\b'                                   # 5b
    r'|\bsee\s+(?:also\s+)?'                            # 5c
    r'|cf\.|\b(?:below|above)\b'                        # 5d
    r'|\bas\s+in\b'                                     # 5e
    r'|\bby\s+(?-i:[A-Z])',                             # 5f. case-sensitive "by Banach"
    re.IGNORECASE)
_TYPE_POS = re.compile(
    r'^(?:Definition|Theorem|Lemma|Corollary|Proposition|Example)\b',
    re.IGNORECASE)


def _is_genuine(it):
    """Heuristic: is this occurrence a genuine item *heading* (definition page)
    rather than a prose reference?

    Items that carry an ``mstart`` (the generic three-level extractor) are
    classified by whether the number sits at the block head and what follows it.

    Items that lack ``mstart`` (the en / en3 extractors) have ALREADY been
    pre-filtered to block-start headings, so every surviving occurrence is a
    genuine heading — return True directly.  (Without this, the ``^\\.`` branch
    of ``_REF_AFTER_NEG`` would wrongly mark a standard English heading such as
    "Proposition 12.8.3. Assume …" — whose text after the number starts with a
    period — as a prose reference, and the dedup would then drop a legitimate
    second occurrence of the same number.)
    """
    if 'mstart' not in it:
        # en/en3 系抽取器：匹配已锚定块首，但 Koopman 书实测仍有块首散文
        # 提及幸存（"Proposition 2.1 is very general, but difficult…" 整块以
        # 引用开头）。判据：key 之后紧跟 ≥2 个小写英文字母开头的词（"is very
        # general"）= 句中延续，非条目头。真条目头在号后是： glued 标题
        # （"2.1Theattractor"，大写）、句点、"(Title)"、大写动词
        # （"Suppose that…"）；数学开头（"e^{iπ}"）第二字符非小写字母，不误伤。
        s = it.get('text', '')
        key = str(it.get('key', ''))
        idx = s.find(key)
        after = re.sub(r'\s+', ' ', s[idx + len(key):]).lstrip() if idx >= 0 else ''
        if re.match(r'^[a-z]{2,}', after):
            return False
        return True
    mstart = it.get('mstart', 0)
    at_head = mstart <= 1
    after = _after_of(it).lstrip()
    if _REF_AFTER_NEG.search(after):
        return False
    positive = (at_head
                or bool(_TYPE_POS.match(after))
                or (after.startswith('(')
                    and '(below)' not in after[:20]
                    and '(above)' not in after[:20]))
    return positive


def _name_sig(it):
    """Normalised heading signature used to tell apart two *distinct* items that
    happen to share the same (label, number).

    We compare the heading text *after* the number, lowercased and
    whitespace-collapsed (truncated).  This is stable for a given item's heading
    while differing between two real but same-numbered items (e.g. a printing
    off-by-one).  Items captured by the en / en3 extractors have no ``mstart``,
    so we anchor at the start of the snippet — identical headings then produce an
    identical signature and are coalesced.
    """
    # 🔴 直接在 snippet 里定位 key 再取其后文本：en/en3 系抽取器的 snippet 是
    # txt[max(0, m.start()-5):…] 截出来的——key 前可能带 0~5 个上下文字符，
    # 且这类条目没有 mstart 字段。旧的固定偏移（ko=5 或 ko=0）会因前缀长度
    # 漂移把同一标题切成不同签名，同号真双印被误判为「不同条目」保留两份。
    s = it.get('text', '')
    key = str(it.get('key', ''))
    idx = s.find(key)
    tail = s[idx + len(key):] if idx >= 0 else s
    tail = re.sub(r'\s+', ' ', tail).strip().lower()
    return tail[:60]


def dedup_items(raw_matches, unique_keys=False):
    """Collapse a single item's many mentions/references down to its definition
    entry, but KEEP two genuinely different items that share a (label, number).

    ``unique_keys`` (section-scoped books): the first numeric key component is
    the SECTION number, so within one chapter the same (label, number) can only
    ever be printed once as a genuine heading.  Any same-key collision is a
    reference whose line wrap left it at a block start (e.g. a trailing
    "Theorem 2.4." fragment) — coalesce to the earliest genuine occurrence,
    never keep a second entry.

    Returns items sorted by (page, key).

    See the module docstring for the full rationale (printing off-by-one where
    the source book prints the same number twice, and both headings must be
    retained).
    """
    groups = OrderedDict()   # key -> list[it]
    for it in raw_matches:
        k = it['key']
        g = _is_genuine(it)
        if k not in groups:
            groups[k] = [it]
            continue
        grp = groups[k]
        if unique_keys:
            # 🔴 section-scoped：章内同 key 必为引用幻影，保留首个真头（有非空
            # 标题签名者优先），其余丢弃。真条目头在本书每号只出现一次。
            genuines = [x for x in grp if _is_genuine(x)]
            if not genuines:
                grp.append(it)          # 首个真头到达：追加为该组真头
            elif g and not _name_sig(genuines[0]) and _name_sig(it):
                grp[grp.index(genuines[0])] = it   # 裸者让位给带标题者
            continue
        # Same-page collision: two occurrences of the same (label, number) on the
        # SAME page can only be a duplicate match (the heading captured twice, or
        # a same-page reference) — never two genuinely distinct items.  Always
        # coalesce to the earliest, regardless of heading text.  This also restores
        # the pre-fix behaviour for same-page duplicates.
        if any(x['page'] == it['page'] for x in grp):
            continue
        genuines = [x for x in grp if _is_genuine(x)]
        # 🔴 裸标签碎片并入（谷超豪《数学物理方程》ch6 §3 实测）：OCR 把同一
        # 条目拆成「带标题的块」与近邻页的「裸标签块」（"性质1" 单独一行，陈述
        # 在相邻显示公式里）。同 key、近页（≤2 页）、且一方签名为空 → 视为同一
        # 条目的 OCR 断裂双读，合并（保留带标题者）。跨节真实重起不受影响：
        # 平行条目双方签名非空且常距 ≥3 页。
        if (g and genuines and abs((it['page'] or 0) - (genuines[0]['page'] or 0)) <= 2
                and ((not _name_sig(it)) or (not _name_sig(genuines[0])))):
            if _name_sig(it) and not _name_sig(genuines[0]):
                grp[grp.index(genuines[0])] = it   # 升级：裸者让位给带标题者
            continue
        if g and genuines and _name_sig(it) != _name_sig(genuines[0]):
            # same key, second genuine heading on a *different* page, different
            # heading text → DISTINCT item (e.g. a source book printing the same
            # number twice).  Keep it.
            grp.append(it)
        elif g and genuines and abs((it['page'] or 0) - (genuines[0]['page'] or 0)) >= 3:
            # 🔴 同号同名但相距 ≥3 页（2026-08-25 Evans 实测）：scope-3 节级重置书
            # 的「平行条目」——不同节复用同号甚至同名（Evans §7.1/§7.2 平行结构各有
            # THEOREM 5 (Improved regularity) / THEOREM 6 (Higher regularity)），
            # 是真实重起而非同一条的重复提及，必须保留。旧逻辑按同名合并把 §7.2 的
            # THEOREM 5/6/7 整批吞掉。真引用提及（block-start 幸存者）几乎不带括号
            # 名，同名概率趋零；近页（<3 页）同名仍按重复双读合并。
            grp.append(it)
        elif g and not genuines:
            # upgrade the earliest non-genuine mention to this genuine definition
            for idx, x in enumerate(grp):
                if not _is_genuine(x):
                    grp[idx] = it
                    break
        # else: duplicate mention of an already-kept item → ignore (keep earliest)
    items = [it for grp in groups.values() for it in grp]
    items.sort(key=lambda x: (x['page'], x['key']))
    return items
