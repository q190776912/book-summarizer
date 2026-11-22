# -*- coding: utf-8 -*-
"""section_boundary.py — 章节边界内容错位检测（S 层核心实现）。

检测「上一节正文尾巴挂到下一节标题之后」「下一节开头留在上一节末尾」
「同一段内容在边界两侧重复」等**单元/页粒度切分留下的边界缺陷**。
这类缺陷不会被 D 层（节连续性）或 B 层（条目编号）发现：节头都在、
编号也连续，只是正文块跨过了节头。

判据分两类，全部只读、绝不改文件：

1. **文本信号**（任何书都可跑）：拆句、标题前进 / 后移、下节以小写 /
   回指 / 数学片段开头、跨节重复、节内重复、孤立证明、迟到导语、
   条目编号倒退。
2. **页面几何信号**（仅当 `_extract/page_*.json` 与章契约可用时）：
   把「上一节最后一个正文块」「本节第一个正文块」的文本回查到 PDF
   页面块坐标，若某块印在节头**后面**（上一节尾巴）或**前面**
   （本节开头），则判 `heading_late` / `heading_early`。运行页眉
   （y < 140）一律排除，节头匹配要求标题精确相等。

页面几何是**证据**而不是新判据：匹配不到就跳过，绝不猜。
`scan_text()` 是纯函数，便于测试；`scan_chapter()` / `scan_verify_target()`
负责按章发现交付文件并把合并行号映射回真实文件行号。
"""
import difflib
import glob
import json
import os
import re
from dataclasses import dataclass

HEADING_RE = re.compile(r'^(#{1,6})\s+(.*\S)\s*$')
BOLD_LEAD_RE = re.compile(r'^\s*(?:>\s*)?\*\*(?P<t>.+?)\*\*(?P<rest>.*)$')
ITEM_LABELS = (
    'Theorem|Lemma|Proposition|Corollary|Definition|Example|Exercise|Remark|'
    'Conjecture|Axiom|Assertion|Assumption|Condition|Property|Problem|'
    '定理|引理|命题|推论|定义|例|练习|习题|评注|注|猜想|公理|性质|问题')
ITEM_HEAD_RE = re.compile(
    r'^\s*(?:>\s*)?\*{0,2}\s*(?P<label>' + ITEM_LABELS + r')\s*'
    r'(?P<num>\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\b', re.I)
BOLD_ITEM_RE = re.compile(
    r'^\s*(?:>\s*)?\*\*\s*(?P<label>' + ITEM_LABELS + r')\s*'
    r'(?P<num>\d{1,2}\.\d{1,2}(?:\.\d{1,2})?)\b', re.I)
# 印刷体证明块一律是 `> **Proof...**` / `> **证明...**` 的粗体标签行。
# 旧正则允许无粗体的裸 Proof/证明，会把「证明留给读者」「Proof of (4.2)」
# 这类普通散文当证明块，制造孤立证明误报。只认粗体标签是保守收紧：只会少报。
PROOF_RE = re.compile(r'^\s*(?:>\s*)?\*\*\s*(?:Proof|证明)\b', re.I)
FIG_RE = re.compile(r'^\s*(?:<div\b|</div>|<img\b|!\[)', re.I)
INTRO_RE = re.compile(
    r'^\s*(?:In this section|This section|In the remainder of this section|'
    r'In the rest of this section|Our goal in this section|The goal of this section|'
    r'The purpose of this section|We now|Now we|We begin|We turn|Here we|This chapter|'
    r'本节|这一节|在本节|下面我们|接下来我们|我们现在|我们将|本章)', re.I)
TERMINAL = set('。．.!?！？…:：')
OPENERS = set('，,；;：:、=+（(-–—')
CONT_WORDS = {
    'and', 'but', 'or', 'nor', 'so', 'yet', 'which', 'where', 'when', 'while',
    'because', 'since', 'if', 'then', 'thus', 'hence', 'therefore', 'however',
    'moreover', 'furthermore', 'also', 'for', 'with', 'of', 'to', 'from', 'on',
    'at', 'by', 'as', 'that', 'this', 'these', 'those', 'it', 'its', 'their',
    'we', 'is', 'are', 'was', 'were', 'has', 'have', 'had', 'can', 'may',
    'might', 'must', 'will', 'would', 'should', 'one', 'there', 'in',
}

# 运行页眉 / 页码块在页面顶部，不是正文证据。绝对 y 阈值只是历史下限：
# 不同扫描件的页眉从 y≈50 到 y≈270 都有（an-intro y≈197、rising-sea
# "draft" 水印 y≈263），单靠阈值会把页眉当成真节头 → 假 heading_late，
# 甚至把邻章页眉当成本章节头（跨章误判）。因此额外按**本页最顶行**做
# 相对带识别：带内纯页码 / 跨页同文行判为页眉，一律不作几何证据。
PAGE_HEADER_Y = 140
PAGE_HEADER_TOL = 12.0


def top_band_header_keys(blocks):
    """blocks: [(page, y, norm_text), ...] → 判为页眉/页码的块键集合。

    只用于**排除证据**，宁漏勿错：带内块须是纯页码，或同一归一化文本
    出现在 ≥2 页的页顶带（running head），才判页眉。页顶真节头（无页码、
    不跨页重复）保留，避免把「节起于新页顶」的正当形态一刀切掉。
    """
    items = [(p, float(y), n) for (p, y, n) in blocks]
    tops = {}
    for p, y, _n in items:
        if p not in tops or y < tops[p]:
            tops[p] = y
    band = [(p, y, n) for p, y, n in items if y <= tops[p] + PAGE_HEADER_TOL]
    by_text = {}
    for p, _y, n in band:
        by_text.setdefault(n, set()).add(p)
    nums = [(p, y) for p, y, n in band if re.fullmatch(r'\d{1,5}', n)]
    out = set()
    for b in band:
        p, y, n = b
        numeric = re.fullmatch(r'\d{1,5}', n) is not None
        # 页眉标题常与页码同行（an-intro p55: 标题 y197 / 页码 y199）；
        # 同页 y 邻近有页码 → 该页顶行是跑马标题而非真节头。
        with_page_no = any(pp == p and abs(yy - y) <= PAGE_HEADER_TOL
                           for pp, yy in nums)
        repeated = len(n) >= 4 and len(by_text.get(n, ())) >= 2
        if numeric or with_page_no or repeated:
            out.add(b)
    return out


@dataclass
class Block:
    start: int          # 1-based first line (in the merged chapter view)
    end: int            # 1-based last line
    lines: list
    text: str
    norm: str
    bold_title: str = ''


@dataclass
class Heading:
    level: int
    line: int           # 1-based
    title: str
    norm_title: str


def norm_text(s):
    s = re.sub(r'^\s*(?:>\s*)+', '', s)
    s = s.strip()
    s = s.replace('**', '').replace('__', '')
    s = re.sub(r'[*_`]', '', s)
    s = re.sub(r'\s+', ' ', s)
    return s.strip()


def norm_alnum(s):
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', norm_text(s).lower())


def norm_title(s):
    s = norm_text(s)
    s = s.lstrip('§').strip()
    s = re.sub(r'^\d+(?:\.\d+)*[.、]?\s*', '', s)
    s = s.strip(' .:：。')
    return norm_alnum(s)


def base_title(s):
    s = norm_text(s)
    if '(' in s:
        s = s.split('(', 1)[0]
    return norm_title(s)


# 编号条目陈述在印面上的合法形态远多于旧 BOLD_ITEM_RE 认的「标签 + X.Y」：
# 字母附录号 (Lemma A.1)、编号在前 (8.3.1 (Lemma/Definition)、9.4.9 Barr 引理)、
# 人名前缀 (Krull's Theorem 6.11.1)、无编号标签行 (**Definition**: ...)。
# 孤立证明 / 迟到导语 / run-in 标题三处共用同一判据，避免把合法陈述误判为缺失。
_ORDINAL_LEAD_RE = re.compile(
    r'^\s*(?:[^\w]{0,4})?(?:\d{1,3}(?:\.\d{1,3}){0,2}|[A-Za-z]\.?\d{1,3}(?:\.\d{1,3})?)(?!\w)')


def _is_item_statement_text(t, raw_line=False):
    """粗体文本是否为编号/带标签的条目陈述。

    raw_line=True 时 t 是**原始行**（可能只是普通散文）——必须先见到粗体起标记
    才认，否则普通散文里出现 'definition' 等词就会被误当成条目陈述。
    raw_line=False 时 t 来自 `Block.bold_title`（已去 `**`），直接看标签/编号。
    """
    if raw_line:
        m = re.match(r'^\s*(?:>\s*)?\*\*\s*', t)
        if not m:
            return False
        s = t[m.end():].split('**', 1)[0]
    else:
        s = t.split('**', 1)[0]
    if re.search(r'\b(?:' + ITEM_LABELS + r')\b', s[:70], re.I):
        return True
    return bool(_ORDINAL_LEAD_RE.match(s))


_MATH_INLINE_RE = re.compile(r'\$[^$\n]+\$')


def _math_tokens(s):
    """块内行内数学 token 列表——用于区分「模板相同但公式不同」的平行命题。"""
    return _MATH_INLINE_RE.findall(s)


def is_prose(s):
    t = s.strip()
    if not t or t == '---':
        return False
    if HEADING_RE.match(t):
        return False
    if re.match(r'^\$\$|^\$\$?$|^\\\[|^\\\]', t):
        return False
    if t.startswith('|') or FIG_RE.match(t):
        return False
    return bool(re.search(r'[0-9A-Za-z\u4e00-\u9fff]', t))


def content_blocks(lines, lo, hi):
    """lo/hi are 0-based inclusive-exclusive line indices."""
    blocks = []
    cur = []

    def flush():
        nonlocal cur
        if cur:
            text = ' '.join(norm_text(x[1]) for x in cur)
            if text.strip():
                blocks.append(Block(cur[0][0], cur[-1][0],
                                    [x[1] for x in cur], text, norm_alnum(text)))
            cur = []

    i = lo
    while i < hi:
        raw = lines[i]
        s = raw.strip()
        if not s or s == '---':
            flush()
            i += 1
            continue
        if HEADING_RE.match(s):
            flush()
            i += 1
            continue
        # standalone figure container lines stay attached to surrounding block
        cur.append((i + 1, s))
        i += 1
    flush()
    for b in blocks:
        m = BOLD_LEAD_RE.match(b.lines[0])
        if m:
            b.bold_title = norm_text(m.group('t'))
    return blocks


def parse_headings(lines):
    """Section / subsection headings.

    Level 1 is the chapter title (one per file) and is not a section
    boundary.  Headings whose title starts with an item label
    (``### Theorem 1.2``) are statement containers, not sections.
    Both ``## § 1.2 Title`` and plain ``## 1.2 Title`` are accepted, so the
    layer is not tied to one book's section-marker style.
    """
    out = []
    for i, raw in enumerate(lines):
        m = HEADING_RE.match(raw.strip())
        if not m:
            continue
        level = len(m.group(1))
        if level < 2:
            continue
        text = m.group(2)
        text = re.sub(r'^§\s*', '', text).strip()
        if not text:
            continue
        if re.match(r'^(?:' + ITEM_LABELS + r')\b', text, re.I):
            continue
        out.append(Heading(level, i + 1, text, norm_title(text)))
    return out


def _is_terminal(line):
    t = norm_text(line).rstrip()
    if not t:
        return True
    if re.search(r'\\end\{[a-zA-Z*]+\}$', t):
        return True
    t = re.sub(r'[\s"\'”’)\]}]+$', '', t)
    if not t:
        return True
    return t[-1] in TERMINAL


def _starts_continuation(line):
    t = norm_text(line).lstrip()
    if not t:
        return False
    if t[0] in ',;.)]}':
        return True
    if t.startswith('$') or re.match(r'^\\[\(\[]', t):
        return True
    m = re.match(r'^([A-Za-z]+)', t)
    if m and t[0].islower():
        return True
    return False


def _split_signal(prev_blocks, next_blocks):
    if not prev_blocks or not next_blocks:
        return None
    last = None
    for b in reversed(prev_blocks):
        for ln in reversed(b.lines):
            if is_prose(ln):
                last = ln
                break
        if last is not None:
            break
    first = None
    for b in next_blocks:
        for ln in b.lines:
            if is_prose(ln):
                first = ln
                break
        if first is not None:
            break
    if not last or not first:
        return None
    if re.match(r'^\$\$|^\\\[', norm_text(first)):
        return None
    if _is_terminal(last):
        return None
    if _starts_continuation(first):
        return ('split_sentence', 'prev ends without terminal punctuation; next continues: %r -> %r'
                % (norm_text(last)[-70:], norm_text(first)[:70]))
    # comma/semicolon/colon/equals tail is enough on its own
    tail = norm_text(last).rstrip()
    if tail and tail[-1] in OPENERS:
        return ('split_sentence', 'prev ends with %r; next starts %r'
                % (tail[-1], norm_text(first)[:70]))
    return None


def _bare_label_title(norm_title):
    """True when a heading's whole title is just a generic item label
    (``Definition`` / ``例`` / ``Theorem`` ...), i.e. not a substantive title.
    Such headings must not anchor the stranded-opening detector: their label
    word begins many ordinary prose paragraphs, so matching it would produce
    false positives (e.g. ``§1.12 Definition`` vs a ``Definition 1.11 ...``
    paragraph in the previous section)."""
    wt = tuple(re.findall(r'[a-z0-9\u4e00-\u9fff]+', norm_title.lower()))
    labels = set(w.lower() for w in re.findall(r'[A-Za-z\u4e00-\u9fff]+', ITEM_LABELS))
    return len(wt) == 1 and wt[0] in labels


def _stranded_opening(heading, prev_blocks, next_blocks):
    """错挂：下一节开头的正文被错挂在上一节末尾（BLOCKING）。

    Printed form: a section heading ``§N Title`` is followed by text that
    continues a sentence from the previous section (lowercase / punctuation /
    math start), AND the previous section's tail contains the SAME substantive
    title as a run-in (``Title. Let us ...``) — i.e. the heading plus its opening
    paragraph were extracted into the wrong (previous) section.  This is a real
    misattribution that must be fixed by moving the whole block across the unit
    boundary, not a cosmetic warning.

    Conservative on purpose (0 fires across the 20-book corpus after the real
    case was fixed): requires a substantive (non-bare-label) heading title, a
    continuation-style next-opening, and a whole-word title prefix in one of the
    previous section's last three content blocks.
    """
    if not prev_blocks or not next_blocks:
        return None
    wt = tuple(re.findall(r'[a-z0-9\u4e00-\u9fff]+', heading.norm_title.lower()))
    if not wt or _bare_label_title(heading.norm_title):
        return None
    next_first = norm_text(next_blocks[0].lines[0])
    # The next section's opening is a continuation: either a classic lowercase /
    # punctuation / math start (Latin), OR it repeats a substantive sentence from
    # the previous section's tail (language-independent — covers CJK where there
    # is no lowercase).  In the concrete bug both sides begin with the identical
    # "whenever $1\leq...$" / "只要 $1\leq...$" sentence.
    cont = _starts_continuation(next_blocks[0].lines[0])
    if not cont:
        for pb in reversed(prev_blocks):
            pn = norm_text(pb.lines[-1])
            if len(pn) >= 30 and (next_first.startswith(pn[:40]) or pn.startswith(next_first[:40])):
                cont = True
                break
    if not cont:
        return None
    for b in prev_blocks[-3:]:
        head_words = tuple(re.findall(r'[a-z0-9\u4e00-\u9fff]+', norm_text(b.lines[0]).lower()))
        if head_words[:len(wt)] == wt:
            return ('stranded_opening',
                    '错挂：下一节「%s」的开头正文被挂在上一节末尾——上一节尾块以本节标题起首 '
                    '(%r)，而本节首段是承接上段的续句 (%r)；须把整块正文搬回本节单元并同步 '
                    'units/manifest' % (heading.title,
                                        norm_text(b.lines[0])[:60],
                                        norm_text(next_blocks[0].lines[0])[:60]))
        if b.bold_title:
            bold_words = tuple(re.findall(r'[a-z0-9\u4e00-\u9fff]+', norm_text(b.bold_title).lower()))
            if bold_words[:len(wt)] == wt:
                return ('stranded_opening',
                        '错挂：上一节尾块含本节标题的 run-in（%r），本节首段为续句；须整块搬回'
                        % norm_text(b.bold_title)[:60])
    return None


def _title_match(a, b):
    """Whole-word title equality / prefix match.

    Substring matching is deliberately NOT used: ``Linear Equations`` must not
    match ``Quasilinear Equations`` (a real false positive on this book).
    """
    if not a or not b:
        return False
    if a == b:
        return True
    wa = tuple(re.findall(r'[a-z0-9\u4e00-\u9fff]+', norm_text(a).lower()))
    wb = tuple(re.findall(r'[a-z0-9\u4e00-\u9fff]+', norm_text(b).lower()))
    if not wa or not wb:
        return False
    if wa == wb:
        return True
    # Allow one title to be a whole-word prefix of the other (e.g. a subtitle).
    if len(wa) >= 2 and len(wb) >= 2:
        if wa == wb[:len(wa)] or wb == wa[:len(wb)]:
            return min(len(wa), len(wb)) / max(len(wa), len(wb)) >= 0.5
    return False


def _runin_before(heading, blocks):
    """Bold run-in with the section's own title, before the heading."""
    cands = []
    for bi, b in enumerate(blocks):
        if not b.bold_title:
            continue
        bt = b.bold_title
        if _is_item_statement_text(bt):
            continue
        if _title_match(norm_title(bt), heading.norm_title) or _title_match(base_title(bt), heading.norm_title):
            after = blocks[bi + 1:]
            # The run-in title usually shares its paragraph with the body text
            # ("**Title.** Body ...").  Count that inline body too; otherwise the
            # most common late-heading shape is invisible to this signal.
            inline = max(0, len(b.norm) - len(norm_title(bt)))
            body_chars = inline + sum(len(x.norm) for x in after)
            if body_chars >= 120 and (after or inline >= 120):
                cands.append((b, body_chars))
    if not cands:
        return None
    b, chars = cands[-1]
    return ('heading_late', 'run-in title at line %d, %d chars of body precede the heading (line %d)'
            % (b.start, chars, heading.line))


def _block_is_figure(b):
    return bool(FIG_RE.match(b.lines[0].strip()))


def _first_content_block(blocks):
    for b in blocks:
        if not _block_is_figure(b):
            return b
    return None


def _lowercase_start(blocks):
    b = _first_content_block(blocks)
    if not b:
        return None
    # A very short lowercase paragraph is typically the tail of a proof that
    # straddled a printed page/section boundary (e.g. "for some matrices A,B,C
    # of sizes ... respectively."), not a displaced fragment.  On this book
    # such a desc unit is printed before the heading on the same page.  Only
    # flag lowercase starts of substantive paragraphs.
    if len(b.norm) < 80:
        return None
    t = norm_text(b.lines[0]).lstrip()
    if t and 'a' <= t[0] <= 'z':
        return ('lowercase_start', 'first text after the heading begins lowercase: %r' % t[:90])
    return None


BACKREF_RE = re.compile(
    r'^(Thus|Therefore|Hence|Then|But|However|So|And|Moreover|Furthermore|'
    r'Similarly|Consequently|On the other hand|By the same token|In particular|'
    r'It follows|This shows|This implies|We have already|We have seen)\b', re.I)
BACKREF_CN_RE = re.compile(
    r'^(因此|所以|于是|但是|然而|而且|并且|此外|同样地?|由此|这说明|'
    r'我们已经|我们知道|另一方面)')


def _backref_opening(blocks):
    b = _first_content_block(blocks)
    if not b:
        return None
    t = norm_text(b.lines[0]).lstrip()
    m = BACKREF_RE.match(t) or BACKREF_CN_RE.match(t)
    if m:
        return ('backref_opening', 'section opens with a backward reference %r: %r'
                % (m.group(1), t[:90]))
    return None


MATH_FRAG_RE = re.compile(
    r'^\$[^$]{1,80}\$\s*(be|with|and|or|then|that|which|has|have)\b', re.I)


def _math_fragment(blocks):
    b = _first_content_block(blocks)
    if not b:
        return None
    t = norm_text(b.lines[0]).lstrip()
    m = MATH_FRAG_RE.match(t)
    if m:
        return ('math_fragment', 'section opens mid-sentence after math: %r' % t[:90])
    return None


def _runin_after_content(heading, blocks):
    """Own run-in bold title appears only after other content => heading too early."""
    before = []
    for bi, b in enumerate(blocks):
        if _block_is_figure(b):
            continue
        bt = b.bold_title
        if bt and not _is_item_statement_text(bt):
            if _title_match(norm_title(bt), heading.norm_title) or _title_match(base_title(bt), heading.norm_title):
                if before:
                    chars = sum(len(x.norm) for x in before)
                    if chars >= 80:
                        after = [x for x in blocks[bi + 1:] if not _block_is_figure(x)][:3]
                        before_text = ' '.join(x.norm for x in before)
                        ref = _shingles(before_text)
                        # If any text after the run-in title is itself a copy of
                        # the text before it, this is an intra-section duplicate,
                        # not a previous-section tail; let dup_within report it.
                        if ref and any(_coverage(x.norm, ref) >= 0.5 for x in after):
                            return None
                        return ('heading_early',
                                'section run-in title appears at line %d, after %d chars of other content (heading line %d)'
                                % (b.start, chars, heading.line))
                return None
        before.append(b)
    return None


def _dup_prev_first(prev_blocks, next_blocks):
    if not prev_blocks:
        return None
    prev_text = ' '.join(b.norm for b in prev_blocks if not _block_is_figure(b))
    ref = _shingles(prev_text)
    if not ref:
        return None
    b = _first_content_block(next_blocks)
    if not b or len(b.norm) < 40:
        return None
    cov = _coverage(b.norm, ref)
    if cov >= 0.9:
        return ('dup_prev', 'first paragraph after the heading (%d chars, line %d) is %.0f%% identical to text in the previous section'
                % (len(b.norm), b.start, cov * 100))
    return None


def _dup_earlier(earlier_blocks, next_blocks):
    """First paragraph repeats text from a section before the previous one."""
    b = _first_content_block(next_blocks)
    if not b or len(b.norm) < 80:
        return None
    for e in earlier_blocks:
        if _block_is_figure(e) or len(e.norm) < 80:
            continue
        ratio = min(len(b.norm), len(e.norm)) / max(len(b.norm), len(e.norm))
        if ratio < 0.45:
            continue
        cov = _coverage(b.norm, _shingles(e.norm))
        if cov >= 0.8:
            return ('dup_earlier', 'first paragraph after the heading repeats earlier chapter text at line %d (%.0f%% match, %d chars)'
                    % (e.start, cov * 100, len(b.norm)))
    return None


def _shingles(s, n=24):
    s = re.sub(r'\s+', '', s)
    if len(s) <= n:
        return {s} if s else set()
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def _coverage(text, ref):
    a = _shingles(text)
    if not a:
        return 0.0
    return len(a & ref) / len(a)


def _dup_across(prev_blocks, next_blocks):
    prev_text = ' '.join(b.norm for b in prev_blocks if not _block_is_figure(b))
    ref = _shingles(prev_text)
    if not ref:
        return None
    hits = []
    n = len(next_blocks)
    # windows of 1..3 blocks
    for i in range(min(n, 30)):
        for k in (1, 2, 3):
            win = next_blocks[i:i + k]
            if not win or i + k > n:
                continue
            if all(_block_is_figure(x) for x in win):
                continue
            text = ' '.join(b.norm for b in win if not _block_is_figure(b))
            if len(text) < 150:
                continue
            cov = _coverage(text, ref)
            if cov >= 0.62:
                hits.append((i, k, cov, len(text), win[0].start, win[-1].end))
    if not hits:
        return None
    # keep maximal, non-overlapping windows
    hits.sort(key=lambda x: (-x[3], x[0]))
    picked = []
    used = set()
    for h in hits:
        idxs = set(range(h[0], h[0] + h[1]))
        if idxs & used:
            continue
        used |= idxs
        picked.append(h)
    picked.sort(key=lambda x: x[0])
    total = sum(h[3] for h in picked)
    if total < 200:
        return None
    rng = ', '.join('%d-%d' % (h[4], h[5]) for h in picked[:6])
    return ('dup_across', 'duplicated block(s) after heading match the previous section (delivery lines %s; %d chars)'
            % (rng, total))


def _dup_within(blocks):
    blocks = [b for b in blocks
              if not _block_is_figure(b) and any(is_prose(ln) for ln in b.lines)]
    n = min(len(blocks), 80)
    if n < 4:
        return None
    hits = []
    for i in range(n):
        for j in range(i + 2, n):
            a, b = blocks[i], blocks[j]
            if not a.norm or not b.norm:
                continue
            if len(a.norm) < 100 or len(b.norm) < 100:
                continue
            sm = difflib.SequenceMatcher(None, a.norm, b.norm)
            if sm.ratio() < 0.9:
                continue
            # 数学文本里大量平行命题（如 Hom(A,-) vs Hom(-,B) 的对偶定理）
            # 模板散文几乎逐字相同、只差公式里的变量名，字符级相似度可 >0.97。
            # 两段都带行内数学时，再要求公式 token 也基本一致，否则不是重复。
            ma, mb = _math_tokens(a.text), _math_tokens(b.text)
            if ma and mb:
                sa, sb = set(ma), set(mb)
                if len(sa & sb) / len(sa | sb) < 0.6:
                    continue
            hits.append((a, b))
            break
    if not hits:
        return None
    a, b = hits[0]
    return ('dup_within', 'paragraph at line %d repeats at line %d within the same section'
            % (a.start, b.start))


def _orphan_proof(blocks):
    for b in blocks[:4]:
        if PROOF_RE.match(b.lines[0]):
            return ('orphan_proof', 'section opens with a proof block (line %d) and no statement precedes it' % b.start)
        if _is_item_statement_text(b.lines[0], raw_line=True):
            break
    return None


def _delayed_intro(blocks):
    # If the very first content block after the heading is already ordinary
    # introductory prose (not an item/proof/figure and not a bold run-in label),
    # the section opening is intact.  Any later INTRO_RE paragraph ("Now we",
    # "本节", "接下来我们", ...) is a transition into a sub-topic, not a
    # displaced section intro.  Scanning the first 14 blocks unconditionally
    # used to flag those transitions as late_start (9 of 11 real cases on this
    # book), which forced content edits against a correct section opening.
    if blocks:
        b0 = blocks[0]
        if (len(b0.norm) >= 40 and not b0.bold_title
                and not BOLD_ITEM_RE.match(b0.lines[0])
                and not PROOF_RE.match(b0.lines[0])
                and not FIG_RE.match(b0.lines[0])):
            return None
    seen_chars = 0
    seen_blocks = 0
    has_struct = False
    for b in blocks[:14]:
        if INTRO_RE.match(b.text):
            # If several structural blocks (theorems/proofs) already precede
            # the INTRO_RE paragraph, it is a discussion paragraph following
            # those items (e.g. "Next we apply the theorem..."), not a section
            # intro displaced from the top.  On this book the two remaining
            # late_start alarms had 7 and 9 preceding blocks (real displaced
            # intros have 1-3).  Do not fight the printed order over that.
            if seen_blocks >= 5 and has_struct:
                return None
            if seen_blocks >= 1 and seen_chars >= 120 and has_struct:
                return ('late_start', 'explicit section intro at line %d is preceded by %d chars of foreign item/proof content'
                        % (b.start, seen_chars))
            return None
        seen_chars += len(b.norm)
        seen_blocks += 1
        if BOLD_ITEM_RE.match(b.lines[0]) or PROOF_RE.match(b.lines[0]) or FIG_RE.match(b.lines[0]):
            has_struct = True
    return None


def _item_num(line):
    m = BOLD_ITEM_RE.match(line)
    if not m:
        return None
    return tuple(int(x) for x in m.group('num').split('.'))


def _stranded_item(prev_blocks, next_blocks):
    prev_max = None
    for b in prev_blocks:
        for ln in b.lines:
            num = _item_num(ln)
            if num and len(num) == 2:
                prev_max = num if prev_max is None else max(prev_max, num)
    first = None
    for b in next_blocks[:8]:
        for ln in b.lines:
            num = _item_num(ln)
            if num:
                first = num
                break
        if first:
            break
    if first and prev_max and len(first) == len(prev_max) and first <= prev_max:
        return ('stranded_item', 'first item after heading is %s, not after previous section max %s'
                % ('.'.join(map(str, first)), '.'.join(map(str, prev_max))))
    return None


def _dup_heading(headings):
    """Return set of heading lines that repeat an earlier title."""
    seen = {}
    out = set()
    for h in headings:
        key = h.norm_title
        if not key:
            continue
        if key in seen:
            out.add(h.line)
        else:
            seen[key] = h.line
    return out


def scan_text(lines, page_ctx=None):
    """Scan one chapter's markdown lines; return a list of finding dicts.

    Each finding has ``section`` / ``line`` (1-based in `lines`) / ``kinds`` /
    ``severity`` / ``detail``.  This function is pure: it never touches disk.
    """
    headings = parse_headings(lines)
    findings = []
    dup_head = _dup_heading(headings)
    all_blocks = content_blocks(lines, 0, len(lines))
    for idx, h in enumerate(headings):
        prev_lo = headings[idx - 1].line if idx else 0
        next_hi = headings[idx + 1].line - 1 if idx + 1 < len(headings) else len(lines)
        prev_blocks = content_blocks(lines, prev_lo, h.line - 1)
        next_blocks = content_blocks(lines, h.line, next_hi)
        earlier_blocks = [b for b in all_blocks if b.start < prev_lo] if idx else []
        if not next_blocks:
            continue
        kinds = []
        details = []
        severity = 'medium'

        if h.line in dup_head:
            kinds.append('dup_heading')
            details.append('section heading repeats an earlier heading in this chapter')
            severity = 'high'

        sig = _split_signal(prev_blocks, next_blocks)
        if sig:
            kinds.append(sig[0])
            details.append(sig[1])

        sig = _runin_before(h, prev_blocks)
        if sig:
            kinds.append(sig[0])
            details.append(sig[1])
            severity = 'high'

        sig = _runin_after_content(h, next_blocks)
        if sig:
            kinds.append(sig[0])
            details.append(sig[1])

        sig = _lowercase_start(next_blocks)
        if sig:
            kinds.append(sig[0])
            details.append(sig[1])

        sig = _backref_opening(next_blocks)
        if sig:
            kinds.append(sig[0])
            details.append(sig[1])

        sig = _math_fragment(next_blocks)
        if sig:
            kinds.append(sig[0])
            details.append(sig[1])

        sig = _dup_prev_first(prev_blocks, next_blocks)
        if sig:
            kinds.append(sig[0])
            details.append(sig[1])
            severity = 'high'

        sig = _dup_earlier(earlier_blocks, next_blocks)
        if sig:
            kinds.append(sig[0])
            details.append(sig[1])
            severity = 'high'

        sig = _dup_across(prev_blocks, next_blocks)
        if sig:
            kinds.append(sig[0])
            details.append(sig[1])
            severity = 'high'

        sig = _dup_within(next_blocks)
        if sig:
            kinds.append(sig[0])
            details.append(sig[1])

        sig = _orphan_proof(next_blocks)
        if sig:
            kinds.append(sig[0])
            details.append(sig[1])

        sig = _delayed_intro(next_blocks)
        if sig:
            kinds.append(sig[0])
            details.append(sig[1])

        sig = _stranded_item(prev_blocks, next_blocks)
        if sig:
            kinds.append(sig[0])
            details.append(sig[1])

        sig = _stranded_opening(h, prev_blocks, next_blocks)
        if sig:
            kinds.append(sig[0])
            details.append(sig[1])
            severity = 'blocking'   # 错挂是实质错误，必须修，不是 WARN

        if page_ctx is not None:
            sig = page_ctx.check(h, prev_blocks, next_blocks)
            if sig:
                # Printed-page geometry alone is weak evidence: a legitimate
                # long proof can straddle a heading, leaving a tail snippet
                # printed after it.  On a 26-chapter book this produced 23
                # false heading_late alarms out of 27 (confirmed by manual
                # review), while every real misplacement also carried a text
                # signal -- a bold run-in with the section's own title,
                # reported by _runin_before / _runin_after_content.  Keep
                # geometry as a diagnostic detail unless text already
                # confirmed the boundary error; otherwise do not raise it to
                # a finding (do not fight a correct section over page layout).
                if sig[0] in ('heading_late', 'heading_early') and sig[0] not in kinds:
                    details.append('[page-geometry only] ' + sig[1])
                else:
                    kinds.append(sig[0])
                    details.append(sig[1])
                    if sig[0] == 'heading_late':
                        severity = 'high'

        if kinds:
            findings.append({
                'section': h.title,
                'line': h.line,
                'kinds': sorted(set(kinds)),
                'severity': severity,
                'detail': '; '.join(details),
            })
    return findings


class PageCtx:
    """Printed-page geometry for one chapter (evidence for boundary checks).

    ``blocks`` are ``(page, y, norm, text)`` tuples read from
    ``page_*.json``.  Top-margin blocks (``y < PAGE_HEADER_Y``) and per-page
    running heads / page numbers identified by :func:`top_band_header_keys`
    are excluded — headers must never anchor a cross-section/cross-chapter
    judgement.  The class can also be constructed directly with
    ``blocks=[...]`` for tests.
    """

    def __init__(self, ext_dir=None, ch=None, start=None, end=None,
                 page_dir=None, blocks=None):
        if blocks is not None:
            raw = [tuple(b) for b in blocks]
            hdr = top_band_header_keys([(b[0], b[1], b[2]) for b in raw])
            self.blocks = [b for b in raw if b[:3] not in hdr]
            return
        raw = []
        if ext_dir is None or start is None or end is None:
            self.blocks = []
            return
        pdir = page_dir
        if pdir is None:
            try:
                from lib.page_dir import resolve_page_dir
                pdir = resolve_page_dir(ext_dir, ch)
            except Exception:
                pdir = ext_dir
        for p in range(int(start), int(end) + 1):
            fp = os.path.join(pdir, 'page_%03d.json' % p)
            if not os.path.exists(fp):
                fp = os.path.join(pdir, 'page_%d.json' % p)
            if not os.path.exists(fp):
                continue
            try:
                with open(fp, encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                continue
            for b in data.get('text') or []:
                t = b.get('text') if isinstance(b, dict) else ''
                if isinstance(t, dict):
                    t = t.get('text', '')
                if not isinstance(t, str):
                    continue
                poly = b.get('poly') or [0, 0]
                y = poly[1] if len(poly) > 1 else 0
                nm = norm_alnum(t)
                if nm and y >= PAGE_HEADER_Y:
                    raw.append((p, y, nm, t))
        hdr = top_band_header_keys([(b[0], b[1], b[2]) for b in raw])
        self.blocks = [b for b in raw if b[:3] not in hdr]

    def find_heading(self, title):
        key = norm_alnum(title)
        if not key:
            return None
        best = None
        for (p, y, nm, t) in self.blocks:
            if nm == key or (nm.startswith(key) and len(nm) <= len(key) + 6):
                if best is None or p < best[0] or (p == best[0] and y < best[1]):
                    best = (p, y)
        return best

    def _occurrences(self, snippet, near_page=None):
        key = norm_alnum(snippet)
        if len(key) < 20:
            return []
        out = []
        # Match the head of the block only.  Do NOT fall forward to later
        # blocks: that is how a page check silently picks up foreign text.
        for cut in (80, 60, 45, 30, 25, 20):
            part = key[:cut]
            if len(part) < 20:
                continue
            found = []
            for (p, y, nm, t) in self.blocks:
                if near_page is not None and abs(p - near_page) > 4:
                    continue
                if part in nm:
                    found.append((p, y))
            if found:
                out = found
                break
        return out

    def check(self, heading, prev_blocks, next_blocks):
        hp = self.find_heading(heading.title)
        if not hp:
            return None
        hp_page, hp_y = hp
        # next content: first non-figure block only; missing match => no evidence
        nxt_b = _first_content_block(next_blocks)
        if nxt_b and len(nxt_b.norm) >= 30:
            occ = self._occurrences(nxt_b.norm, hp_page)
            if occ:
                after = [c for c in occ
                         if c[0] > hp_page or (c[0] == hp_page and c[1] >= hp_y - 25)]
                if not after:
                    np, ny = max(occ, key=lambda c: (c[0], c[1]))
                    return ('heading_early',
                            'first body text after the heading is printed on PDF p%d y=%.0f, before the heading (p%d y=%.0f)'
                            % (np, ny, hp_page, hp_y))
        # prev content: last non-figure prose block only
        prv_b = None
        for b in reversed(prev_blocks):
            if _block_is_figure(b):
                continue
            if len(b.norm) < 30 or not is_prose(b.lines[-1]):
                continue
            prv_b = b
            break
        if prv_b:
            occ = self._occurrences(prv_b.norm, hp_page)
            if occ:
                before = [c for c in occ
                          if c[0] < hp_page or (c[0] == hp_page and c[1] <= hp_y + 25)]
                if not before:
                    pp, py = min(occ, key=lambda c: (c[0], c[1]))
                    return ('heading_late',
                            'last body text before the heading is printed on PDF p%d y=%.0f, after the heading (p%d y=%.0f)'
                            % (pp, py, hp_page, hp_y))
            # A desc unit can weld several printed paragraphs together.  The
            # block start may be legitimately before the heading while its tail
            # (the next section's opening) is printed after it.
            for snip in self._tail_snippets(prv_b)[:4]:
                occ = self._occurrences(snip, hp_page)
                if not occ:
                    continue
                before = [c for c in occ
                          if c[0] < hp_page or (c[0] == hp_page and c[1] <= hp_y + 25)]
                if not before:
                    pp, py = min(occ, key=lambda c: (c[0], c[1]))
                    return ('heading_late',
                            'tail of the last body block before the heading is printed on PDF p%d y=%.0f, after the heading (p%d y=%.0f)'
                            % (pp, py, hp_page, hp_y))
                break
        return None

    @staticmethod
    def _strip_math(s):
        s = re.sub(r'\$\$.*?\$\$', ' ', s, flags=re.S)
        s = re.sub(r'\$[^$]*\$', ' ', s)
        s = re.sub(r'\\[a-zA-Z]+', ' ', s)
        s = re.sub(r'[^0-9A-Za-z\u4e00-\u9fff ]+', ' ', s)
        return re.sub(r'\s+', ' ', s).strip()

    def _tail_snippets(self, b):
        cands = []
        t = b.text
        for n in (160, 100, 60):
            if len(t) > n:
                cands.append(t[-n:])
        st = self._strip_math(t)
        for n in (160, 100, 60):
            if len(st) > n:
                cands.append(st[-n:])
        out = []
        seen = set()
        for c in cands:
            k = norm_alnum(c)
            if len(k) < 20 or k in seen:
                continue
            seen.add(k)
            out.append(c)
        return out


# ---------------------------------------------------------------------------
# delivery-file discovery / merged-view line mapping
# ---------------------------------------------------------------------------

def _contract_path(ext_dir, ch):
    try:
        from data.book_structure.book_structure import chapter_json_path
        p = chapter_json_path(ext_dir, ch)
        if p:
            return p
    except Exception:
        pass
    p = os.path.join(ext_dir, 'book_structure', 'ch%s.json' % ch)
    return p if os.path.exists(p) else None


def chapter_page_ctx(ext_dir, ch):
    """PageCtx for `ch` from its contract page range, or None if unavailable."""
    if not ext_dir:
        return None
    p = _contract_path(ext_dir, ch)
    if not p:
        return None
    try:
        with open(p, encoding='utf-8') as f:
            d = json.load(f)
        start, end = int(d['page_start']), int(d['page_end'])
    except Exception:
        return None
    ctx = PageCtx(ext_dir, ch, start, end)
    return ctx if ctx.blocks else None


def _read_group_lines(files):
    """Merge section files exactly like ``verify_chapter._merge_section_files``.

    Returns ``(lines, origins)`` where ``origins[i] = (basename, line_no)``
    for the merged line ``i`` (0-based).  The duplicate chapter-title rule is
    replicated so merged line numbers match the temp view verify consumes.
    """
    merged = []
    title_seen = False
    for fp in files:
        # OSError propagates: an unreadable chapter is "no evidence", and the
        # layer turns that into a hard error instead of a silent empty PASS.
        with open(fp, encoding='utf-8-sig') as f:
            raw = f.read().split('\n')
        base = os.path.basename(fp)
        for j, line in enumerate(raw):
            if j == 0 and line.startswith('# '):
                if title_seen:
                    continue
                title_seen = True
            merged.append((line, base, j + 1))
    return [m[0] for m in merged], [(m[1], m[2]) for m in merged]


def _discover_groups_fallback(book_dir, ch):
    groups = []
    for pattern, lang in (
            ('Chapter%d_*.md' % ch, 'en'),
            ('第%d章_*.md' % ch, 'cn')):
        files = glob.glob(os.path.join(book_dir, pattern))
        if not files:
            continue

        def _key(p):
            b = os.path.basename(p)
            m = re.search(r'_(\d+)_', b)
            return int(m.group(1)) if m else 0

        files.sort(key=_key)
        groups.append((lang, files))
    return groups


def discover_chapter_groups(book_dir, ch):
    """Return ``[(lang, [md_file, ...]), ...]`` for chapter `ch`.

    Uses ``verify_chapter.chapter_md_groups`` as the SSOT when importable
    (handles merged/split/appendix/supplement naming), with a small filename
    fallback so the lib stays usable outside the verify runner.
    """
    try:
        from verify.script.verify_chapter import chapter_md_groups, _group_lang
        groups = chapter_md_groups(book_dir, ch)
        out = [(_group_lang(g), g) for g in groups if g]
        if out:
            return out
    except Exception:
        pass
    return _discover_groups_fallback(book_dir, ch)


def scan_chapter_files(files, page_ctx=None):
    """Scan one language's chapter files; map findings back to real files.

    Returns ``(findings, stats)``.  `files` may be a single merged delivery
    md or the ordered section files of one chapter.
    """
    lines, origins = _read_group_lines(files)
    findings = scan_text(lines, page_ctx)
    out = []
    for f in findings:
        rec = dict(f)
        idx = f['line'] - 1
        if 0 <= idx < len(origins):
            rec['file'], rec['file_line'] = origins[idx]
        else:
            rec['file'], rec['file_line'] = None, None
        out.append(rec)
    headings = parse_headings(lines)
    stats = {
        'files': [os.path.basename(p) for p in files],
        'lines': len(lines),
        'headings': len(headings),
        'findings': len(out),
        'high': len([f for f in out if f.get('severity') == 'high']),
        'page_geometry': bool(page_ctx is not None and page_ctx.blocks),
    }
    return out, stats


def resolve_md_group(book_dir, ch, md_file):
    """Pick the delivery group that produced `md_file`, else ``[md_file]``.

    verify hands split chapters a temporary merged view; mapping findings back
    to the real section files requires rebuilding that same group.  A group is
    accepted only when its merged text equals the bytes of `md_file`, so a
    stale/ambiguous group can never shift line numbers.
    """
    target = [md_file]
    try:
        with open(md_file, encoding='utf-8-sig') as f:
            target_text = f.read().rstrip('\n')
    except OSError:
        return target
    try:
        from verify.script.verify_chapter import _group_lang
        want_lang = _group_lang([md_file])
    except Exception:
        want_lang = None
    for lang, files in discover_chapter_groups(book_dir, ch):
        if want_lang and lang and lang != want_lang:
            continue
        try:
            lines, _origins = _read_group_lines(files)
        except OSError:
            continue
        if '\n'.join(lines).rstrip('\n') == target_text:
            return files
    return target


def scan_verify_target(md_file, ext_dir, ch, start=None, end=None):
    """Entry point for the verify S layer.

    `start`/`end` are the contract page range from ``ctx``; when omitted the
    chapter contract is consulted.  Page geometry is optional evidence.
    """
    book_dir = os.path.dirname(os.path.abspath(md_file))
    files = resolve_md_group(book_dir, ch, md_file)
    page_ctx = None
    if ext_dir and start is not None and end is not None:
        page_ctx = PageCtx(ext_dir, ch, start, end)
        if not page_ctx.blocks:
            page_ctx = None
    elif ext_dir:
        page_ctx = chapter_page_ctx(ext_dir, ch)
    return scan_chapter_files(files, page_ctx)


def scan_chapter(book_dir, ext_dir, ch, lang=None):
    """Standalone audit entry: scan every (or one) language group of `ch`."""
    page_ctx = chapter_page_ctx(ext_dir, ch)
    out = []
    for glang, files in discover_chapter_groups(book_dir, ch):
        if lang and glang != lang:
            continue
        findings, stats = scan_chapter_files(files, page_ctx)
        out.append({
            'chapter': ch,
            'lang': glang,
            'files': [os.path.basename(p) for p in files],
            'findings': findings,
            'stats': stats,
        })
    return out
