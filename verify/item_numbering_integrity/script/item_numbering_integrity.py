import os
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()
import page_json

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 verify/item_numbering_integrity/item_numbering_integrity.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""
item_numbering_integrity.py — B-LAYER (order 3): 缺号检测（忠于原文）。

权威检测落在 agent 写出的 .md 上，按 `ctx.config.ordinal` 决定的编号编排类型
（由 ConfigLoader 从 verify_config.json 读入，挂在 ctx.config，不依赖任何编排层透传）正确分组后，
对组内序号做首项/连续性检查。

md 内部的缺号默认是「硬 BLOCKING」（严格模式，不允许遗漏）：任何序号不连续
都会要求核对。很多书定理/引理类条目本就稀疏（如某章只有 `Lemma 2.5`），这些
经核对确认是书本身编号、非遗漏的，应在配置文件 `ignore` 中登记，以免误报。
配置 `strict: false` 才降级为非阻塞警示。硬阻塞也来自提取侧契约（若已接线）。
语义 / 分组 / 契约键等详见 verify/item_numbering_integrity/item_numbering_integrity.md（SSOT）。
"""
import json
import os
import re
import functools
from collections import defaultdict
from dataclasses import dataclass, field

from verify.script.base import VerifyLayer, LayerResult
from key_parse import sortkey, _canon_label
from lib.regexlib import SEP_TIGHT, SEP_SPLIT_RE
from verify_config import ORDINAL_THREE_LEVEL

# Tail-check tolerance: source max minus md max beyond this is treated as a
# likely OCR phantom / alien-numbering and collapses to ONE summary warning
# instead of a per-number flood (mirrors D-layer's TAIL_GAP_THRESHOLD=5).
_TAIL_GAP_CAP = 5

# A bold **...** span. We parse the inner text to decide if it is a real item
# header (vs a citation like "**见 4.11-5**").
# 注意：inner 允许出现 '*'（如 $X^*$ 内的星号），否则带数学的标题会被整段拆断、
# 其编号解析不到 -> 误报「首项缺失」。约束改为「不跨行」([^\n])，仍由下一个 '**' 收尾。
_SPAN_RE = re.compile(r'\*\*([^\n]*?)\*\*')
_CITE_RE = re.compile(r'^[（(]*(见|由|根据|参考|参见|据|依照|按|Cf\.|cf\.)')

# 证明标题（"X.Y-Z 的证明" / "X.Y-Z Proof."）是证明小节，不是被定义的条目，
# 不得计入条目序列（既会污染缺号 present 集合，也会在顺序校验里制造伪回归）。
_PROOF_RE = re.compile(r'^(证明|的证明|proof|beweis|demonstration|dem\b)', re.IGNORECASE)

# The inter-component separator is now SEP_TIGHT, defined ONCE in lib.regexlib
# and reused everywhere so every book's punctuation variant normalizes the same
# way.  Different books use '.' or '-' (or fullwidth variants) interchangeably
# (e.g. '4.11-5' vs '4.11.5' vs '4·11-5'); the wildcard is built-in, so the
# per-book config need NOT specify separators.
# Numeric "path" length is DRIVEN BY cfg.levels — NOT a hardcoded {0,2}.
# A 2-level book matches exactly '4.1' / '4-1'; a 3-level book exactly
# '4.11-5'.  Building the regex per `levels` keeps the parse honest to the
# per-book config instead of silently over-matching (a 2-level book could
# otherwise grab a spurious 3rd component) or under-matching.
#   lv=1 -> \d+                 (whole-file / per-chapter sequential)
#   lv=2 -> \d+(?:SEP_TIGHT\d+)      (chapter.section)
#   lv=3 -> \d+(?:SEP_TIGHT\d+){2}   (chapter.section-item)
@functools.lru_cache(maxsize=16)
def _numpath_regexes(levels):
    """Return (exact, cap, label_first, num_first) compiled patterns for a
    numbering of `levels` numeric components.  Cached per `levels` so the
    per-span parse does not recompile."""
    lv = max(1, int(levels))
    rep = '{' + str(lv - 1) + '}'               # {0}/{1}/{2} for 1/2/3 levels
    numpath = r'\d+(?:' + SEP_TIGHT + r'\d+)' + rep
    exact = re.compile(r'^' + numpath + r'$')
    cap = re.compile(r'(' + numpath + r')')
    # re.IGNORECASE: English books (e.g. Apostol) print headings in UPPERCASE
    # (LEMMA 11.1. / THEOREM 8.16.) or OCR-mangled mixed case (THEoREM /
    # CoROLLARY). Without it the label-first match fails -> the B-layer parses
    # ZERO bold entries for the EN .md and silently reports no gaps (false
    # pass). Chinese labels are case-insensitive anyway, so this is safe for
    # every book. Mirrors ENTRY_RE_EN_C in lib/key_parse.py (same fix applied there).
    label_first = re.compile(r'^(?:' + _ENTRY_LABELS + r')\s*' + cap.pattern,
                             re.IGNORECASE)
    num_first = re.compile(r'^' + cap.pattern + r'\s+(.*)$')
    return exact, cap, label_first, num_first

# Structural entry labels (Chinese + English).  These open a numbered item.
# NOTE: extended forms (例子/例题/注记/评注) MUST precede their short stem
# (例/注) so the regex matches the longest label first.  Otherwise a header
# like "7.6-2 例子（…）" matches only "例" and the trailing Han char ("子")
# is then treated as prose by _after_label_boundary and the entry is dropped
# (this silently broke combined 定义/定理/例 counters).  See _parse_entry.
_ENTRY_LABELS = (
    r'定理|定义|引理|推论|命题|例子|例题|例|注记|评注|注|公理|问题|练习|习题|引例|附注'
    r'|Theorem|Definition|Lemma|Corollary|Proposition|Example|Remark'
    r'|Exercise|Problem|Note|Axiom'
)
# Label-first:  LABEL  NUMPATH   (e.g. "定理 4.1", "Definition 2.1")

# Normalize a CN entry label to its EN canonical so that `known_gaps` entries
# written in English also suppress the CN (or any-language) counterpart.
_LABEL_NORM = {
    '定理': 'Theorem', '定义': 'Definition', '引理': 'Lemma', '推论': 'Corollary',
    '命题': 'Proposition', '例子': 'Example', '例题': 'Example', '例': 'Example',
    '注记': 'Remark', '评注': 'Remark', '注': 'Remark', '公理': 'Axiom',
    '问题': 'Problem', '练习': 'Exercise', '习题': 'Exercise', '引例': 'Example',
    '附注': 'Remark',
}


def _norm_label(label):
    return _LABEL_NORM.get(label, label)


# Normalize the inter-component separator inside a gap token's numeric part so
# that `known_gaps` written with '.' ("Theorem 12.3") match emit tokens built
# with '-' ("Theorem 12-3") — the B-layer emits the dash form (C.S-N / C-N),
# while users naturally write the dot form.  Only separators BETWEEN two digits
# are touched.
_SEP_BETWEEN_DIGITS = re.compile(r'(?<=\d)' + SEP_TIGHT + r'(?=\d)')
def _norm_sep(s):
    return _SEP_BETWEEN_DIGITS.sub('.', s)

# label-first / number-first regexes are now built per `levels` inside
# _numpath_regexes() (the path length must track cfg.levels, see above), so
# there are no module-level _RE_LABEL_FIRST / _RE_NUM_FIRST anymore.


def _split_numpath(s, levels):
    """Parse a bare key like '4.1' / '4.1-2' / '5' into a list of int
    components, or None if it is not a valid `levels`-level numeric path.
    `levels` drives the required component count (see _numpath_regexes)."""
    s = s.strip()
    exact, _cap, _lf, _nf = _numpath_regexes(levels)
    if exact.match(s):
        return [int(x) for x in SEP_SPLIT_RE.split(s)]
    return None


def _is_header_boundary(tail):
    """After the numeric path, the bold span must terminate the *header*
    (colon / paren / period / end-of-span) — not run into prose such as
    '的证明' or ' and', which would indicate a *reference* rather than a
    defined entry."""
    s = tail.lstrip()
    if not s:
        return True
    c = s[0]
    if c in ':.。():（）)，,；;*':
        return True
    if c.isalpha():          # latin letter -> 'Theorem 4.1 and ...' prose
        return False
    if '一' <= c <= '鿿':     # Han char -> '定理 4.1 的证明' prose
        return False
    return True


# After a matched label in a NUMBER-FIRST header ("4.3-1 定理 …"), the text that
# follows the label must terminate the *header* (paren/colon/end), not run into
# another numberpath ("定理 4.1 …" = cross-reference) or Han/latin prose
# ("定理 的应用" = reference).  See _is_header_boundary for the label-first case.
def _after_label_boundary(after):
    s = after.lstrip()
    if not s:
        return True
    c = s[0]
    if c in ':.。():（）)，,；;*':
        return True
    if c.isdigit() or c.isalpha():      # another numberpath or latin prose
        return False
    if '一' <= c <= '鿿':                 # Han char -> prose/reference
        return False
    return True


# A number-first header with NO standard label word (e.g. "4.11-2 必要条件")
# is a descriptive title, not a reference, ONLY if its tail does not start with
# a citation/function word or latin prose.  Otherwise it is prose/reference and
# must NOT be counted as an entry (avoids false gaps AND false entries).
_PARTICLES = set('的 和 与 及 以 由 见 据 按 因 若 当 但 且 或 等 也 仍 可 不 在 '
                '对 从 把 被 让 设 则 故 即 如 其 该 此 这 那 中 上 下 后 前 内 '
                '外 之 而 并 将 已 为 使 给 向 到 自 经 比 较 证 推 应'.split())


def _is_citation_starter(s):
    """True if `s` opens with an explicit cross-reference marker.  Lets the EN
    relaxation below still drop genuine references like 'see Theorem 4.1' /
    'cf. Example 2' while counting descriptive titles that start with a content
    word ('Space', 'Banach', 'A space', 'The open mapping theorem')."""
    head = re.match(r'[A-Za-z]+', s)
    if not head:
        return False
    return head.group(0).lower() in ('see', 'cf', 'viz', 'ibid')


# Explicit cross-reference starters for CJK (Han-start) tails.  A descriptive
# item title may start with ANY other Han char — including negation '不' ("不完备的
# 赋范空间" = Incomplete normed spaces) or '由' ("由...定义的度量") — so only these
# unambiguous citation words mark a reference; everything else is a REAL entry.
_CN_CITATION_STARTERS = ('见', '据', '按', '参', '依', 'cf')


def _is_reference_tail(tail, lang=None):
    s = tail.lstrip()
    if not s:
        return True
    c = s[0]
    # Latin letters ONLY — CJK chars are .isalpha() too, but a descriptive title
    # that starts with a Han char (e.g. "必要条件", "收敛性") is a REAL entry,
    # not a reference.  It must fall through to the particle check below, and if
    # it is not a known connective it is counted as 'uncat'.  Treating every
    # Han-starting tail as a reference silently drops legitimate entries and
    # manufactures false "缺号".
    if c.isascii() and c.isalpha():     # English prose / latin citation
        # EN books carry descriptive item titles in English (Latin-start), e.g.
        # "2.2-3 Space l^p".  These are REAL entries, not references — only drop
        # them when the tail opens with an explicit citation marker.  CN books
        # keep the legacy behaviour (any Latin-start tail = reference) because
        # their descriptive titles start with Han chars, so a Latin-start in a
        # CN md is almost always a citation / English-term reference.
        if lang == 'en':
            return _is_citation_starter(s)
        return True
    if '一' <= c <= '鿿':
        # Only an EXPLICIT cross-reference marker marks a reference.  A
        # descriptive title may start with any other Han char — including
        # negation '不' ("不完备的赋范空间") or '由' ("由...定义的度量") — so
        # anything that is not a citation word is a REAL entry (uncat), never a
        # silently-dropped reference.  This mirrors the EN branch above.
        if lang != 'en' and c in _CN_CITATION_STARTERS:
            return True
        return False
    return False


def _parse_entry(inner, levels, lang=None):
    """Return (comps, label) for a real numbered entry header, else None.

    comps is the list of exactly `levels` integer components (the numbering
    level is driven by cfg.levels, NOT a hardcoded cap).  Handles both
    label-first ('定理 4.1') and number-first ('8.1-6 例') forms, and rejects
    citation spans and references (see _is_header_boundary)."""
    inner = inner.strip()
    if _CITE_RE.match(inner):
        return None
    _exact, _cap, re_label_first, re_num_first = _numpath_regexes(levels)
    # Three-level books: a bare numpath with NO trailing text and NO label
    # (e.g. "**1.5-4**") is a real item header whose type is implied — count it
    # as 'uncat'.  This is REQUIRED for combined-numbering uncat counters
    # (Kreyszig §1.5's bare keys) to be visible to the B-layer; otherwise the
    # layer silently drops them and manufactures a false "缺号" (it would see
    # §1.5 = [1,2,3,5,6,7,8,9] and report 缺号 4).  Two-level books keep bare
    # numbers non-entries, because a bare "C.S" is ambiguous (section vs item);
    # the guard `levels == 3` scopes this fallback to three-level books only.
    if levels == 3 and _exact.match(inner):
        comps = [int(x) for x in SEP_SPLIT_RE.split(inner)]
        return comps, 'uncat'
    m = re_label_first.match(inner)
    if m:
        numpath = m.group(1)
        if not _is_header_boundary(inner[m.end():]):
            return None
        comps = [int(x) for x in SEP_SPLIT_RE.split(numpath)]
        # MUST use re.IGNORECASE here too: line 68's re_label_first matches
        # UPPERCASE EN headings (LEMMA 11.1. / THEOREM 8.16.) via IGNORECASE,
        # so this label re-extract must agree or it returns None and crashes.
        label = re.match(r'^(?:' + _ENTRY_LABELS + r')', inner, re.IGNORECASE).group(0)
        return comps, label
    m = re_num_first.match(inner)
    if m:
        numpath = m.group(1)
        tail = m.group(2).strip()
        # 证明标题「X.Y-Z 的证明 / Proof.」→ 非定义条头，直接排除
        if _PROOF_RE.match(tail):
            return None
        # 类型词可能在专名之后（「2.5-4 黎斯引理」「5.1-2 巴拿赫不动点定理」）；
        # 在余串里搜索首个类型词当 label，边界检查放到类型词之后。
        lm = re.search(r'(?:' + _ENTRY_LABELS + r')', tail)
        if lm:
            if not _after_label_boundary(tail[lm.end():]):
                return None
            comps = [int(x) for x in SEP_SPLIT_RE.split(numpath)]
            return comps, lm.group(0)
        # 无标准类型词：描述性标题（「4.11-2 必要条件」）→ 归 uncat，
        # combined 下并入节序列一起计连续性（仍是真实条目，不应漏计）。
        if tail and not _is_reference_tail(tail, lang):
            comps = [int(x) for x in SEP_SPLIT_RE.split(numpath)]
            return comps, 'uncat'
        return None
    # Fallback: number-first with a header-boundary open paren directly after
    # the numpath and no explicit label word (e.g. "2.6-1（线性算子）").
    # Require the paren content not to be a citation so references like
    # "2.6-1（见定理）" are still rejected.
    paren_re = re.compile(r'^' + _cap.pattern + r'\s*[（(]')
    m2 = paren_re.match(inner)
    if m2:
        numpath = m2.group(1)
        tail = inner[m2.end():].strip()
        if tail and not _is_reference_tail(tail, lang):
            comps = [int(x) for x in SEP_SPLIT_RE.split(numpath)]
            return comps, 'uncat'
    # Fallback: label preceded by a name/attribution (e.g.
    # "黎斯 (Riesz) 引理2.5-4（Riesz's lemma）").  Search for LABEL numpath
    # anywhere in the span; the header-boundary check after numpath rejects
    # prose references that happen to contain a label-number pair.
    m3 = re.search(r'(?:' + _ENTRY_LABELS + r')\s*' + _cap.pattern, inner)
    if m3:
        numpath = m3.group(1)
        if _is_header_boundary(inner[m3.end():]):
            comps = [int(x) for x in SEP_SPLIT_RE.split(numpath)]
            label = re.match(r'^(?:' + _ENTRY_LABELS + r')', inner[m3.start():], re.IGNORECASE).group(0)
            return comps, label
    return None


def _source_item_comps_label(it, cfg):
    """Map an extraction item (ctx.items, the source contract) to
    (comps, label, group) using the SAME wildcard separator and the item's
    OWN group depth (from cfg.group_for_label) — so source + md groups align
    1:1 for the tail check regardless of which group the item belongs to.

    `levels` is replaced by `cfg` so each item is parsed at its group's depth
    (a two-level 练习 item is parsed at depth 2, a three-level 定理 at depth 3).
    * EN / two-level normalized keys carry the label inline ('定理1.1' /
      'Definition 1.1') -> label-first parse.
    * three-level keys are bare numpaths ('4.1-5') with the category in the
      separate `label` field -> use it['label'].
    * gm / roman keys (chapter is a roman numeral) cannot be split by the
      integer-only _SEP -> return None (tail check gracefully skips those).
    """
    if not isinstance(it, dict):
        return None
    key = (it.get('key') or '').strip()
    if not key:
        return None
    lab = it.get('label')
    g = cfg.group_for_label(lab) if lab and lab != 'uncat' else cfg.uncat_group()
    _exact, _cap, re_label_first, _nf = _numpath_regexes(g.depth)
    m = re_label_first.match(key)
    if m:
        comps = [int(x) for x in SEP_SPLIT_RE.split(m.group(1))]
        label = re.match(r'^(?:' + _ENTRY_LABELS + r')', key).group(0)
        return comps, label, g
    comps = _split_numpath(key, g.depth)
    if comps is not None and lab and lab != 'uncat':
        return comps, lab, g
    return None


def _md_tail_warnings(ctx, cfg, groups):
    """B-LAYER 尾部校验（SSOT b.md §尾部校验，非阻断）.

    对每个 md 编号组，取 .md 内最大号 `last`；再在提取契约（源, ctx.items）中
    按同一分组方案（levels/scope/separate_types）找该组最大号 `smax`。若
    `smax > last` 且中间号源有而 md 无 -> 疑似尾部漏项，写进 `b_tail_warnings`
    （仅提示，请人工核实章/节是否即止）。

    OCR 幻影可能抬高 smax，故差距过大(>_TAIL_GAP_CAP)时只给一条汇总提示而非
    逐号轰炸；已知稀疏号(known_gaps)/已忽略键(ignore_keys)跳过。
    """
    items = ctx.items
    if not items:
        return []
    known = ctx.ignore
    ignore = ctx.ignore

    # source max per (group_index, prefix_tuple) — keyed by GROUP, not label,
    # so a merged (combined) counter aligns correctly regardless of item label.
    src_max = {}
    for it in items:
        cl = _source_item_comps_label(it, cfg)
        if not cl:
            continue
        comps, label, g = cl
        if not comps:
            continue
        gpl = g.group_prefix_len()
        gpl_e = min(gpl, len(comps) - 1)
        prefix = tuple(comps[:gpl_e])
        num = comps[gpl_e] if gpl_e < len(comps) else 0
        if num <= 0:
            continue
        gi = cfg.ordinal.index(g)
        key = (gi, prefix)
        if num > src_max.get(key, 0):
            src_max[key] = num

    warnings = []
    for gk, pairs in sorted(groups.items()):
        # `gk` is "{gi}:<body>" where <body> is the numeric prefix string,
        # "file" (uncat), or "file:<label>".
        body = gk.split(':', 1)[1] if ':' in gk else gk
        if body == 'file':
            prefix_str, label = '', 'uncat'
        elif body.startswith('file:'):
            prefix_str, label = '', body[len('file:'):]
        else:
            prefix_str, label = body, 'uncat'
        last = max(n for n, _ in pairs)
        prefix = tuple(int(x) for x in prefix_str.split('.')) if prefix_str else ()
        gi = int(gk.split(':', 1)[0]) if ':' in gk else 0
        smax = src_max.get((gi, prefix), 0)
        if smax <= last:
            continue
        gap = smax - last
        if gap > _TAIL_GAP_CAP:
            warnings.append(
                f"  ~ TAIL {gk}: 源最大 {smax} 远大于 md 最大 {last}（差距 {gap}）"
                f"— 疑似 OCR 幻影或异源编号，请重点核实该组是否即止")
            continue
        for n in range(last + 1, smax + 1):
            full = (prefix_str + '-' if prefix_str else '') + str(n)
            token = f"{label} {full}" if label and label != 'uncat' else full
            token_norm = f"{_norm_label(label)} {full}" if label and label != 'uncat' else full
            if (token in known or token_norm in known
                    or f"{gk}:{n}" in known or f"{gk}:{n}" in ignore):
                continue
            warnings.append(
                f"  ~ TAIL {gk} 缺尾部号 {n}（md 最大 {last}，源最大 {smax} — "
                f"请核实章/节是否即止；疑似尾部漏项）")
    return warnings


# ------------------------------------------------------------------ grouping
# Grouping is driven by the BookConfig.ordinal GroupConfig array (see
# config.GroupConfig).  Each entry's label is mapped to its group via
# cfg.group_for_label(); the group index namespaces the counter key so
# different groups NEVER merge.  The old `separate_types` (SEP_COMBINED /
# SEP_PER_TYPE) switch is gone.





def _md_gap_blocking(ctx):
    """Return (BLOCKING, WARNING, present_md_keys) for item-number gaps found
    in the written .md, grouped by the per-book numbering convention carried on
    `ctx.config` (built once by the ConfigLoader from
    <book>/_extract/verify_config.json — no ad-hoc file IO here).  The
    separator is a built-in wildcard; numbering level is variable (1/2/3).

    Default is STRICT (no omissions allowed): any discontinuity in a numbering
    group hard-blocks until verified.  Books that legitimately number items
    sparsely (e.g. a chapter with only 'Lemma 2.5') should record the confirmed
    sparse tokens in config `known_gaps` so they are suppressed instead of
    false-FAILing.  `strict: false` downgrades gaps to advisory warnings."""
    cfg = ctx.config
    known = ctx.ignore
    if not ctx.md_file:
        return [], [], set(), []
    try:
        txt = open(ctx.md_file, encoding='utf-8').read()
    except Exception:
        return [], [], set(), []

    # Grouping is now driven by the BookConfig.ordinal GroupConfig array.  For
    # each entry we parse its (comps, label) at the MOST SPECIFIC depth that
    # matches (descending over the distinct group depths), then map the label
    # to its group and use THAT group's prefix length.  Parsing at the highest
    # depth first means a three-level "4.1-5" is captured fully even when a
    # two-level 练习 group also declares depth 2.
    _depth_candidates = sorted({g.depth for g in cfg.ordinal}, reverse=True)
    entries = []  # (group_key, item_num, unique_key, label, prefix_str)
    for span in _SPAN_RE.finditer(txt):
        inner = span.group(1).strip()
        parsed = None
        for lv in _depth_candidates:
            parsed = _parse_entry(inner, lv, ctx.language)
            if parsed:
                break
        if not parsed:
            continue
        comps, label = parsed
        if not comps:
            continue
        g = cfg.group_for_label(label)
        gi = cfg.ordinal.index(g)
        gpl = g.group_prefix_len()
        # Per-entry cap so a mismatched `levels` can never index out of range.
        gpl_e = min(gpl, len(comps) - 1)
        prefix = tuple(comps[:gpl_e])
        item_num = comps[gpl_e] if gpl_e < len(comps) else 0
        prefix_str = '.'.join(str(c) for c in prefix)
        if prefix_str:
            gk = f"{gi}:{prefix_str}"
        elif label and label != 'uncat':
            gk = f"{gi}:file:{label}"
        else:
            gk = f"{gi}:file"
        # present_md key uses the dash form ("C.S-N") so the extraction-side
        # OCR-suppression filter (which builds "sec-num") can match it.
        key = f"{prefix_str}-{item_num}" if prefix_str else str(item_num)
        entries.append((gk, item_num, key, label, prefix_str))

    groups = defaultdict(list)
    # 🔴 顺序错乱检测必须按 (prefix, type) 分组，不能仅按 prefix_str 混排所有类型。
    # 许多书（如 Koopman Ch1）每个条目环境在章内独立编号（Definition 1.1 /
    # Proposition 1.1 / Example 1.1 / Remark 1.1 同为 ".1"），类型重置导致 "1"
    # 出现在更大编号之后——这是合法重置，非错位。仅按 prefix_str 混排会把这种
    # 合法重置误判为 BLOCKING 顺序错乱。gk 已编码类型(group index)，与「缺号」
    # 检查保持一致地按 gk 分组即可正确按类型隔离顺序校验。
    section_order = defaultdict(list)   # gk -> [item_num,...] 阅读顺序（按类型隔离，用于顺序错乱检测）
    present_md = set()
    for gk, num, key, label, prefix_str in entries:
        # Group by `gk` ONLY.  `gk` already encodes the separation decision:
        # per-type mode embeds the label ("C.S:LABEL"), combined mode does not
        # ("C.S").  Re-adding `label` here would split a combined section into
        # per-type sub-sequences -> false "缺号" (the original bug).
        groups[gk].append((num, key))
        present_md.add(key)
        # 阅读顺序记录（无论 per-type/combined，同一节前缀 §C.S 的编号按出现先后入列，
        # 用于跨类型顺序错乱检测：例如 2.6-8 这种 Example 掉到 2.6-11 这种 Lemma 之后）。
        section_order[gk].append(num)

    ignore = ctx.ignore
    # Normalize known_gaps separators (dot <-> dash) so user-written dot form
    # matches the dash-form emit tokens.
    known = {_norm_sep(x) for x in ctx.ignore}
    blocking, warnings = [], []

    for gk, pairs in sorted(groups.items()):
        # `gk` is "{gi}:<body>" where <body> is the numeric prefix string,
        # "file" (prefix-less, uncat label), or "file:<label>" (prefix-less,
        # labelled).  The group index `gi` namespaces counters so different
        # groups never merge.
        body = gk.split(':', 1)[1] if ':' in gk else gk
        if body == 'file':
            prefix_str, label = '', 'uncat'
        elif body.startswith('file:'):
            prefix_str, label = '', body[len('file:'):]
        else:
            prefix_str, label = body, 'uncat'
        # Recover the human-readable label(s) carried by this group so the emit
        # token matches `ignore` / `known_gaps` entries written as e.g.
        # "Theorem 12.3".  v2 groups by `gi:prefix` (the group index `gi`
        # encodes the label via group_for_label), so the label is NOT part of
        # the grouping key and must be re-derived here.  Without this, per-type
        # groups emit a bare "12-3" token that never matches a "Theorem 12.3"
        # ignore entry -> confirmed-sparse numbers false-BLOCK (regression vs
        # the old label-bearing token from separate_types:1 mode).
        label_candidates = [label]
        try:
            gi = int(gk.split(':', 1)[0])
            g = cfg.ordinal[gi]
            if not g.is_uncat:
                label_candidates = list(g.name)
        except (ValueError, IndexError):
            pass
        nums = sorted(n for n, _ in pairs)
        present = {n for n, _ in pairs}
        first, last = nums[0], nums[-1]
        size = len(nums)

        def emit(n):
            # Human-readable token used for known_gaps / ignore matching, e.g.
            # "Theorem 12.3".  Both the raw token (original label language) and
            # the EN-normalized token are accepted, so a known_gaps entry
            # written in English also suppresses its Chinese counterpart.  For
            # per-type groups the label is re-derived from the group index
            # (label_candidates) so an ignore entry "Theorem 12.3" matches the
            # emitted token even though the grouping key only carries `gi`.
            full = (prefix_str + '-' if prefix_str else '') + str(n)
            matched = False
            for lab in label_candidates:
                token = f"{lab} {full}" if lab and lab != 'uncat' else full
                token_norm = f"{_norm_label(lab)} {full}" if lab and lab != 'uncat' else full
                if (_norm_sep(token) in known or _norm_sep(token_norm) in known
                        or _norm_sep(f"{gk}:{n}") in known
                        or f"{gk}:{n}" in ignore
                        or _norm_sep(full) in known or full in ignore):
                    matched = True
                    break
            if matched:
                # 审核护栏：ignore 只应抑制「.md 中真实存在、但属 OCR 乱码」的条头，
                # 不得用于掩盖「源侧序列洞」（被忽略的编号在 .md 中本就不存在）。
                # 若 n 不在 present（是洞而非现令牌头），抑制它等于隐藏真实缺项 →
                # 改为发出 IGNORE-SUSPECT 警告，交由 agent 复核
                # （补 manual_overrides 或举证稀疏），而非静默放行。
                if n not in present:
                    warnings.append(
                        f"  [IGNORE-SUSPECT] {gk} 缺号 {n}（序列 {first}..{last}）："
                        f"ignore 条目掩盖了一个源侧序列洞（{full} 在 .md 中并不存在），"
                        f"疑似隐藏真实缺项。请核对源书：若确为稀疏编号请在 ignore 注明举证；"
                        f"若 .md 本应含 {full} 请用 manual_overrides 补回，勿用 ignore 隐藏。")
                return
            msg = (f"{gk} 缺号 {n}（序列 {first}..{last} 不连续 — "
                   f"严格模式：请核对源书确认是稀疏编号(登记 ignore)还是确有遗漏(应补写)）")
            if cfg.strict:
                blocking.append("  WARN (BLOCKING): " + msg)
            else:
                warnings.append(msg)

        # 中间缺号（序列内部的洞）：最可疑，总是提示
        for n in range(first + 1, last):
            if n not in present:
                emit(n)
        # 首项缺失（first>1）：仅当序列较长(>=3)时提示，避免单发条目的噪声
        if first > 1 and size >= 3:
            for n in range(1, first):
                if n not in present:
                    emit(n)

    # --- 顺序校验 (ORDERING, 始终 BLOCKING) ---
    # 同「节前缀(prefix_str)」内，阅读顺序中的编号必须单调不减；若某编号出现在
    # 更大编号之后（如 §2.6 阅读顺序 …7,9,10,11,8），即为「编号错位」（8 号掉到
    # 后面），属确定性错误：只依赖 markdown 自身编号序列，与契约 page_start 无关
    # （即使契约被习题/交叉引用污染也会命中，因为只比对 .md 自身的编号顺序）。
    # 此类"靠后的号跑到前面之后"必须硬阻断、不得 PASS（用户明确要求：不能要）。
    # 去重：同编号只保留最后一次"真实定义"出现，排除章首目录/TOC 与证明标题
    # "X.Y-Z 的证明"（已被 _parse_entry 过滤）造成的伪回归。
    for gk_key, seq in sorted(section_order.items()):
        if len(seq) < 2:
            continue
        # gk = "{gi}:{prefix_str}"（类型已编码在 gi 中）；还原展示用的前缀。
        _parts = gk_key.split(':', 1)
        pref = _parts[1] if len(_parts) > 1 else gk_key
        if pref == 'file' or pref.startswith('file:') or pref == '':
            pref = '<章级>'
        last_pos = {}
        for i, num in enumerate(seq):
            last_pos[num] = i
        ordered = [num for num, _ in sorted(last_pos.items(), key=lambda kv: kv[1])]
        for i in range(1, len(ordered)):
            if ordered[i] < ordered[i - 1]:
                blocking.append(
                    f"  WARN (BLOCKING): 顺序错乱 @{pref}: 编号 {ordered[i]} "
                    f"出现在更大编号 {ordered[i-1]} 之后（去重后阅读顺序 {ordered}）→ "
                    f"疑似条目错位（如 2.6-8 被排到 2.6-11 之后）。请核源书真实顺序，"
                    f"将 {pref}-{ordered[i]} 移到正确位置。")
                break  # 每节只报一次，避免洪水

    # 尾部校验：.md 最大号 vs 提取契约（源）同组最大号（非阻断）
    tail_warnings = _md_tail_warnings(ctx, cfg, groups)

    return blocking, warnings, present_md, tail_warnings


# ---------------------------------------------------------------------------
# 提取侧查漏：整类首项缺失 (Q) + over-mark 守卫。
# EXTRACT 侧只供给数据（items/entry_keys/all_keys/label_warns），查漏逻辑统一由 B 层处理；
# 复用 B 现有 `blocking` / `warnings` 键，不加新契约键。
# ---------------------------------------------------------------------------
CAT_WORDS = ['定义', '定理', '引理', '推论', '命题']
EN_TO_CN = {'Definition': '定义', 'Theorem': '定理', 'Lemma': '引理',
            'Corollary': '推论', 'Proposition': '命题'}
# OCR 字母↔数字容错（章号首位）：扫描 raw page JSON 时把 A→4, B→8, O→0 …
OCR_DIGIT = {'O': 0, 'o': 0, 'Q': 0, 'D': 0, '0': 0,
             'I': 1, 'l': 1, 'i': 1, '1': 1,
             'Z': 2, 'z': 2, '2': 2,
             'A': 4, 'a': 4, '4': 4,
             'S': 5, 's': 5, '5': 5,
             'G': 6, 'g': 6, '6': 6,
             'T': 7, 't': 7, '7': 7,
             'B': 8, 'b': 8, '8': 8,
             'g': 9, '9': 9}


def _norm_ch(s):
    if s.isdigit():
        return int(s)
    return OCR_DIGIT.get(s)


# raw-text OCR-tolerant heading patterns (block-anchored with ^):
_CH = r'([0-9A-Za-z])'
_BOOK_LABEL_RES = [
    re.compile(r'^\s*(定义|定理|引理|推论|命题)\s*' + _CH + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)\b'),          # 定义4.7-1
    re.compile(r'^\s*(Definition|Theorem|Lemma|Corollary|Proposition)\s*' + _CH + SEP_TIGHT + r'(\d+)(?:' + SEP_TIGHT + r'(\d+))?\b', re.IGNORECASE),  # Definition 4.7[-N]
    re.compile(r'^\s*' + _CH + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)\s*(定义|定理|引理|推论|命题)'),            # 4.7-1 定义
]


def _scan_book_category_items(ch, start, end, ext_dir):
    """Scan raw page JSON text blocks for category-heading items, OCR-tolerant on
    the chapter's first char (A→4 etc). Returns {(sec, cat): sorted[num,]}.
    Block-anchored (^) so cross-references like '由定义 4.7-1' are excluded."""
    by = defaultdict(list)
    for p in range(start, end + 1):
        fp = os.path.join(ext_dir, f'page_{p:03d}.json')
        if not os.path.exists(fp):
            continue
        try:
            d = page_json.PageJson.load(fp).data
        except Exception:
            continue
        for blk in d.get('text', []):
            t = blk.get('text', '').strip()
            if not t:
                continue
            for ri, rgx in enumerate(_BOOK_LABEL_RES):
                m = rgx.match(t)
                if not m:
                    continue
                if ri == 0:                      # 定义4.7-1
                    cat = m.group(1); chc = m.group(2)
                    sec = int(m.group(3)); num = int(m.group(4))
                elif ri == 1:                    # Definition 4.7[-N]
                    cat = EN_TO_CN.get(m.group(1).title(), '定义')
                    chc = m.group(2); sec = int(m.group(3))
                    num = int(m.group(4)) if m.group(4) is not None else 0
                else:                            # 4.7-1 定义
                    chc = m.group(1); sec = int(m.group(2)); num = int(m.group(3))
                    tail = t[m.end():m.end() + 8]
                    tm = re.search(r'(定义|定理|引理|推论|命题)', tail)
                    if not tm:
                        break
                    cat = tm.group(1)
                cc = _norm_ch(chc)
                if cc is None or cc != ch:
                    break
                by[(sec, cat)].append(num)
                break
    return {k: sorted(set(v)) for k, v in by.items()}


def _merged_category_first_missing(ctx, all_keys, blocking):
    """Q 逻辑并入 B：整类首项缺失检测。仅 three_level 方案启用（ordinal=3）。"""
    if ctx.config.primary_type != ORDINAL_THREE_LEVEL:
        return
    ch = ctx.ch
    book_cat = _scan_book_category_items(ch, ctx.start, ctx.end, ctx.ext_dir)
    if not book_cat:
        return
    # md 中各节已出现的编号（任何重要概念类别都算，避免同号异类误报）。
    # 注意：three-level 方案的 .md 键是数字型（如 3.3-2），不含类别前缀，
    # 故此处用数字型正则解析，不能套用带类别前缀的 _BOOK_LABEL_RES。
    md_by_sec = defaultdict(set)
    for k in all_keys:
        m = re.match(r'^(\d+)\.(\d+)-(\d+)$', k)
        if m and int(m.group(1)) == ch:
            md_by_sec[int(m.group(2))].add(int(m.group(3)))
    for (sec, cat), nums in book_cat.items():
        bmin = nums[0]
        if bmin in md_by_sec.get(sec, set()):
            continue                        # 该编号在总结中已出现（任何类别）→ 非首项缺失
        blocking.append(
            f"  ! §{ch}.{sec} 书中含「{cat}」{len(nums)} 条（首项 {cat}{ch}.{sec}-{bmin}），"
            f"但总结未含任何「{cat}」条目（编号 {bmin} 在总结中不存在）→ 疑似缺失首项 {cat}{ch}.{sec}-{bmin}")


def _merged_ocr_overmark_guard(ctx, items, warnings):
    """over-mark 守卫：.md 中带（OCR无法识别）的条目，若其编号已被 book 抽取识别
    → 误标警告（书中其实有该条目，不应标 OCR无法识别）。"""
    try:
        mdtext = open(ctx.md_file, encoding='utf-8').read()
    except Exception:
        return
    mark_re = re.compile(r'\*\*([^*]*?(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)[^*]*?)\*\*')
    md_mark = set()
    for m in mark_re.finditer(mdtext):
        if 'OCR无法识别' in m.group(0) or 'OCR无法识别' in m.group(1):
            md_mark.add(f"{int(m.group(2))}.{int(m.group(3))}-{int(m.group(4))}")
    if not md_mark:
        return
    book_num = set()
    for it in items:
        # agent_recovered (manual override) entries are NOT genuinely OCR-recognized;
        # an (OCR无法识别) marker on them is legitimate, so don't误-flag.
        if it.get('agent_recovered'):
            continue
        mm = re.search(r'(\d+)\.(\d+)-(\d+)', it['key'])
        if mm:
            book_num.add(f"{mm.group(1)}.{mm.group(2)}-{mm.group(3)}")
    for k in sorted(md_mark):
        if k in book_num and k not in ctx.ignore:
            warnings.append(
                f"  ? {k} 标注（OCR无法识别）但书中 OCR 已识别该条目 → 可能误标，请复核")


class ItemNumberingIntegrityLayer(VerifyLayer):
    code = 'B'
    name = 'item-numbering-integrity'
    order = 3
    auto_fixable = False

    def run(self, ctx):
        items = ctx.items or []
        entry_keys = ctx.entry_keys or set()
        all_keys = ctx.all_keys or set()
        ignore_keys = ctx.ignore

        # --- A-LAYER 完整性（原独立 A 层，现并入 B）：truly_missing / mentioned_only / extra ---
        # 数据来自 EXTRACT 供给的 ctx.items（书真相集）/ all_keys / entry_keys；
        # B 是查漏的唯一权威，EXTRACT 只供水、不做事。
        extracted_raw = {it['key'] for it in items}
        ignored_hit = sorted(extracted_raw & ignore_keys, key=sortkey)   # stage1：噪声键
        extracted = extracted_raw - ignore_keys                          # 剔噪书集
        truly_missing = sorted(extracted - all_keys)
        mentioned_only = sorted((extracted & all_keys) - entry_keys, key=sortkey)
        extra = sorted(all_keys - extracted, key=sortkey)

        # --- P2：提取侧查漏（Q 类整项缺失 + over-mark 守卫，归 B 层统一处理）---
        blocking = []
        warnings = []
        _merged_category_first_missing(ctx, all_keys, blocking)
        _merged_ocr_overmark_guard(ctx, items, warnings)

        # --- B 层原有逻辑：ignored_hit 第二段 suppression + md 侧查漏 + OCR 误报过滤 ---
        # Suppress extraction-side blocking entries whose referenced item keys
        # are ALL registered as confirmed noise; fold those keys into ignored_hit.
        if ignore_keys and blocking:
            kept = []
            for msg in blocking:
                sec_m = re.search(r'(\d+\.\d+)', msg)
                nums = re.findall(r'-(\d+)', msg)
                if sec_m and nums:
                    sec = sec_m.group(1)
                    bkeys = {f"{sec}-{n}" for n in nums}
                    if bkeys <= ignore_keys:
                        ignored_hit = sorted(set(ignored_hit) | bkeys, key=sortkey)
                        continue
                kept.append(msg)
            blocking = kept

        # Authoritative missing-number detection on the written .md.
        md_blocking, md_warnings, present_md, md_tail = _md_gap_blocking(ctx)

        # 提取侧误报过滤：OCR 漏检但 .md 已正确写出的条目不应 hard-block。
        # 仅当被报缺的键在 .md 中也确实缺失时，才保留为 blocking（此时 MD 与
        # 提取契约双重确认 -> 真漏项，agent 应补）。
        if blocking and present_md:
            kept = []
            for msg in blocking:
                sec = None
                nums_str = None
                mm = re.search(r'(\d+\.\d+)\s+missing items\s+([-\d,\s]+)', msg)
                if mm:
                    sec = mm.group(1)
                    nums_str = mm.group(2)
                else:
                    # Extraction-side head-gap report: "0:2.1 starts at -3, items
                    # -2 still missing after auto-recovery". If the reported
                    # missing numbers are actually present in the written .md,
                    # this is an OCR miss, not a real gap.
                    sm = re.search(r'(\d+\.\d+)\s+starts at -(\d+).*?items\s+([-\d,\s]+)\s+still missing', msg)
                    if sm:
                        sec = sm.group(1)
                        nums_str = sm.group(3)
                if sec and nums_str:
                    # 消息中每个号已带前导 '-'（"missing items -4" 或
                    # "items -2 still missing"），直接拼接即可。
                    bkeys = {f"{sec}{n.strip()}" for n in nums_str.split(',') if n.strip()}
                    if bkeys and bkeys <= present_md:
                        ignored_hit = sorted(set(ignored_hit) | bkeys, key=sortkey)
                        continue
                kept.append(msg)
            blocking = kept

        blocking = blocking + md_blocking

        ctx.ignored_hit = ignored_hit
        ctx.extraction_blocking = blocking

        return LayerResult(code=self.code, metadata={
            'blocking': blocking,
            'warnings': warnings,
            'b_gap_warnings': md_warnings,
            'b_tail_warnings': md_tail,
            'ignored_hit': ignored_hit,
            'truly_missing': truly_missing,
            'mentioned_only': mentioned_only,
            'extra': extra,
        })
