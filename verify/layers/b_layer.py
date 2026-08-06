# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 references/layers/b.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""
b_layer.py — B-LAYER (order 3): 缺号检测（忠于原文）。

权威检测落在 agent 写出的 .md 上，按「每本书的编号编排类型」(BNumberingConfig，
由 B 层脚本直接从 _extract/ 读 JSON，不依赖任何编排层透传) 正确分组后，
对组内序号做首项/连续性检查。

md 内部的缺号默认是「硬 BLOCKING」（严格模式，不允许遗漏）：任何序号不连续
都会要求核对。很多书定理/引理类条目本就稀疏（如某章只有 `Lemma 2.5`），这些
经核对确认是书本身编号、非遗漏的，应在配置文件 `known_gaps` 中登记，以免误报。
配置 `strict: false` 才降级为非阻塞警示。硬阻塞也来自提取侧契约（若已接线）。
语义 / 分组 / 契约键等详见 references/layers/b.md（SSOT）。
"""
import json
import os
import re
import functools
from collections import defaultdict
from dataclasses import dataclass, field

from verify.layers.base import VerifyLayer, LayerResult
from verify.key_parse import sortkey, _canon_label
from lib.regexlib import SEP_TIGHT, SEP_SPLIT_RE
from lib.config import SEP_COMBINED, SEP_PER_TYPE

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
    # every book. Mirrors ENTRY_RE_EN_C in key_parse.py (same fix applied there).
    label_first = re.compile(r'^(?:' + _ENTRY_LABELS + r')\s*' + cap.pattern,
                             re.IGNORECASE)
    num_first = re.compile(r'^' + cap.pattern + r'\s+(.*)$')
    return exact, cap, label_first, num_first

# Structural entry labels (Chinese + English).  These open a numbered item.
_ENTRY_LABELS = (
    r'定理|定义|引理|推论|命题|例|注|公理|问题|练习|习题|引例|附注'
    r'|Theorem|Definition|Lemma|Corollary|Proposition|Example|Remark'
    r'|Exercise|Problem|Note|Axiom'
)
# Label-first:  LABEL  NUMPATH   (e.g. "定理 4.1", "Definition 2.1")

# Normalize a CN entry label to its EN canonical so that `known_gaps` entries
# written in English also suppress the CN (or any-language) counterpart.
_LABEL_NORM = {
    '定理': 'Theorem', '定义': 'Definition', '引理': 'Lemma', '推论': 'Corollary',
    '命题': 'Proposition', '例': 'Example', '注': 'Remark', '公理': 'Axiom',
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


def _is_reference_tail(tail):
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
        return True
    if '一' <= c <= '鿿' and c in _PARTICLES:
        return True
    return False


def _parse_entry(inner, levels):
    """Return (comps, label) for a real numbered entry header, else None.

    comps is the list of exactly `levels` integer components (the numbering
    level is driven by cfg.levels, NOT a hardcoded cap).  Handles both
    label-first ('定理 4.1') and number-first ('8.1-6 例') forms, and rejects
    citation spans and references (see _is_header_boundary)."""
    inner = inner.strip()
    if _CITE_RE.match(inner):
        return None
    _exact, _cap, re_label_first, re_num_first = _numpath_regexes(levels)
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
        if tail and not _is_reference_tail(tail):
            comps = [int(x) for x in SEP_SPLIT_RE.split(numpath)]
            return comps, 'uncat'
        return None
    return None


def _source_item_comps_label(it, levels):
    """Map an extraction item (ctx.items, the source contract) to (comps, label)
    using the SAME wildcard separator and `levels` as the MD parse, so source +
    md groups align 1:1 for the tail check.

    * EN / two-level normalized keys carry the label inline:
      '定理1.1' / 'Definition 1.1'  -> label-first parse.
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
    _exact, _cap, re_label_first, _nf = _numpath_regexes(levels)
    m = re_label_first.match(key)
    if m:
        comps = [int(x) for x in SEP_SPLIT_RE.split(m.group(1))]
        label = re.match(r'^(?:' + _ENTRY_LABELS + r')', key).group(0)
        return comps, label
    comps = _split_numpath(key, levels)
    lab = it.get('label')
    if comps is not None and lab and lab != 'uncat':
        return comps, lab
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
    gpl = cfg.group_prefix_len()
    known = ctx.ignore
    ignore = ctx.ignore

    # source max per (canon_label, prefix_tuple)
    src_max = {}
    for it in items:
        cl = _source_item_comps_label(it, cfg.depth)
        if not cl:
            continue
        comps, label = cl
        if not comps:
            continue
        gpl_e = min(gpl, len(comps) - 1)
        prefix = tuple(comps[:gpl_e])
        num = comps[gpl_e] if gpl_e < len(comps) else 0
        if num <= 0:
            continue
        clabel = _canon_label(label)
        key = (clabel, prefix)
        if num > src_max.get(key, 0):
            src_max[key] = num

    warnings = []
    for gk, pairs in sorted(groups.items()):
        # `gk` is now the sole grouping key; derive prefix_str / label.
        if gk.startswith('file'):
            label = gk.split(':', 1)[1] if ':' in gk else 'uncat'
            prefix_str = ''
        elif ':' in gk:
            prefix_str, label = gk.rsplit(':', 1)
        else:
            prefix_str = gk
            label = 'uncat'
        last = max(n for n, _ in pairs)
        clabel = _canon_label(label)
        prefix = tuple(int(x) for x in prefix_str.split('.')) if prefix_str else ()
        smax = src_max.get((clabel, prefix), 0)
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
            token_norm = f"{clabel} {full}"
            if (token in known or token_norm in known
                    or f"{gk}:{n}" in known or f"{gk}:{n}" in ignore):
                continue
            warnings.append(
                f"  ~ TAIL {gk} 缺尾部号 {n}（md 最大 {last}，源最大 {smax} — "
                f"请核实章/节是否即止；疑似尾部漏项）")
    return warnings


# ------------------------------------------------------------------ config
# Separation modes for `BookConfig.separate_types` (single source of truth:
#
# ALWAYS compare with `==` against these NAMED constants — never `>=`.
# A greater number must NOT silently inherit the per-type behavior; each new
# mode MUST get its own explicit branch, so introducing one later forces a code
# change here instead of quietly mis-grouping.  Unknown values fall back to
# SEP_COMBINED (the safe default) WITH a loud warning — see from_dict().





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
        return [], [], set()
    try:
        txt = open(ctx.md_file, encoding='utf-8').read()
    except Exception:
        return [], [], set()

    gpl = cfg.group_prefix_len()
    entries = []  # (group_key, item_num, unique_key, label, prefix_str)
    for span in _SPAN_RE.finditer(txt):
        inner = span.group(1).strip()
        parsed = _parse_entry(inner, cfg.depth)
        if not parsed:
            continue
        comps, label = parsed
        if not comps:
            continue
        # Per-entry cap so a mismatched `levels` can never index out of range.
        gpl_e = min(gpl, len(comps) - 1)
        prefix = tuple(comps[:gpl_e])
        item_num = comps[gpl_e] if gpl_e < len(comps) else 0
        prefix_str = '.'.join(str(c) for c in prefix)
        if cfg.separate_types == SEP_PER_TYPE and label and label != 'uncat':
            # `gk` MUST carry the JOINED prefix string (not the tuple repr), so
            # downstream code that re-derives prefix_str/label from `gk` (the
            # grouping loop + tail check) gets a clean "C.S" form, never "(1,)".
            gk = f"{prefix_str}:{label}" if prefix else f"file:{label}"
        else:
            gk = prefix_str if prefix else "file"
        # present_md key uses the dash form ("C.S-N") so the extraction-side
        # OCR-suppression filter (which builds "sec-num") can match it.
        key = f"{prefix_str}-{item_num}" if prefix_str else str(item_num)
        entries.append((gk, item_num, key, label, prefix_str))

    groups = defaultdict(list)
    present_md = set()
    for gk, num, key, label, prefix_str in entries:
        # Group by `gk` ONLY.  `gk` already encodes the separation decision:
        # per-type mode embeds the label ("C.S:LABEL"), combined mode does not
        # ("C.S").  Re-adding `label` here would split a combined section into
        # per-type sub-sequences -> false "缺号" (the original bug).
        groups[gk].append((num, key))
        present_md.add(key)

    ignore = ctx.ignore
    # Normalize known_gaps separators (dot <-> dash) so user-written dot form
    # matches the dash-form emit tokens.
    known = {_norm_sep(x) for x in ctx.ignore}
    blocking, warnings = [], []

    for gk, pairs in sorted(groups.items()):
        # `gk` is now the sole grouping key.  Derive prefix_str / label:
        #   per-type keys embed the label  ("C.S:LABEL")
        #   combined keys / the prefix-less "file" key carry no label.
        if gk.startswith('file'):
            label = gk.split(':', 1)[1] if ':' in gk else 'uncat'
            prefix_str = ''
        elif ':' in gk:
            prefix_str, label = gk.rsplit(':', 1)
        else:
            prefix_str = gk
            label = 'uncat'
        nums = sorted(n for n, _ in pairs)
        present = {n for n, _ in pairs}
        first, last = nums[0], nums[-1]
        size = len(nums)

        def emit(n):
            # Human-readable token used for known_gaps / ignore matching, e.g.
            # "Theorem 12.3".  Both the raw token (original label language) and
            # the EN-normalized token are accepted, so a known_gaps entry
            # written in English also suppresses its Chinese counterpart.
            full = (prefix_str + '-' if prefix_str else '') + str(n)
            token = f"{label} {full}" if label and label != 'uncat' else full
            token_norm = f"{_norm_label(label)} {full}" if label and label != 'uncat' else full
            if (_norm_sep(token) in known or _norm_sep(token_norm) in known
                    or _norm_sep(f"{gk}:{n}") in known
                    or f"{gk}:{n}" in ignore):
                return
            msg = (f"{gk} 缺号 {n}（序列 {first}..{last} 不连续 — "
                   f"严格模式：请核对源书确认是稀疏编号(登记 known_gaps)还是确有遗漏(应补写)）")
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

    # 尾部校验：.md 最大号 vs 提取契约（源）同组最大号（非阻断）
    tail_warnings = _md_tail_warnings(ctx, cfg, groups)

    return blocking, warnings, present_md, tail_warnings


class BLayer(VerifyLayer):
    code = 'B'
    order = 3
    auto_fixable = False

    def run(self, ctx):
        blocking = list(ctx.extraction_blocking or [])
        ignored_hit = list(ctx.ignored_hit or [])
        ignore_keys = ctx.ignore

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
                mm = re.search(r'(\d+\.\d+)\s+missing items\s+([-\d,\s]+)', msg)
                if mm:
                    sec = mm.group(1)
                    # 消息中每个号已带前导 '-'（"missing items -4"），直接拼接即可。
                    bkeys = {f"{sec}{n.strip()}" for n in mm.group(2).split(',') if n.strip()}
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
            'b_gap_warnings': md_warnings,
            'b_tail_warnings': md_tail,
            'ignored_hit': ignored_hit,
        })
