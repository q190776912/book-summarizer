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
from collections import defaultdict
from dataclasses import dataclass, field

from verify.registry import VerifyLayer, LayerResult
from verify.key_parse import sortkey, _canon_label

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

# Level separator between numeric components: dot / hyphen / en-dash / middle-dot
# / slash, plus their fullwidth CJK forms.  Deliberately NOT hardcoded to a
# single symbol — different books use '.' or '-' (or fullwidth variants)
# interchangeably (e.g. '4.11-5' vs '4.11.5' vs '4·11-5').  This wildcard is
# built-in, so the per-book config need NOT specify separators.
_SEP = r'[.\-–·/．－〜]'
# A numeric "path" of 1..3 components:
#   1-level: 5          (whole-file / per-chapter sequential numbering)
#   2-level: 4.1 / 4-1  (chapter.section)
#   3-level: 4.11-5     (chapter.section-item)
# each component separated by _SEP.  {0,2} caps the path at three levels.
_NUMPATH_RE = re.compile(r'^\d+(?:' + _SEP + r'\d+){0,2}$')
_NUMPATH_CAP = re.compile(r'(\d+(?:' + _SEP + r'\d+){0,2})')

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

_RE_LABEL_FIRST = re.compile(r'^(?:' + _ENTRY_LABELS + r')\s*' + _NUMPATH_CAP.pattern)
# Number-first: NUMPATH  LABEL   (e.g. "8.1-6 例", "4.3 注")
_RE_NUM_FIRST = re.compile(r'^' + _NUMPATH_CAP.pattern + r'\s+(?:' + _ENTRY_LABELS + r')')


def _split_numpath(s):
    """Parse a bare key like '4.1' / '4.1-2' / '5' into a list of int
    components, or None if it is not a valid 1..3-level numeric path."""
    s = s.strip()
    if _NUMPATH_RE.match(s):
        return [int(x) for x in re.split(_SEP, s)]
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


def _parse_entry(inner):
    """Return (comps, label) for a real numbered entry header, else None.

    comps is the list of 1..3 integer components (variable numbering level).
    Handles both label-first ('定理 4.1') and number-first ('8.1-6 例') forms,
    and rejects citation spans and references (see _is_header_boundary)."""
    inner = inner.strip()
    if _CITE_RE.match(inner):
        return None
    m = _RE_LABEL_FIRST.match(inner)
    if m:
        numpath = m.group(1)
        if not _is_header_boundary(inner[m.end():]):
            return None
        comps = [int(x) for x in re.split(_SEP, numpath)]
        label = re.match(r'^(?:' + _ENTRY_LABELS + r')', inner).group(0)
        return comps, label
    m = _RE_NUM_FIRST.match(inner)
    if m:
        numpath = m.group(1)
        if not _is_header_boundary(inner[m.end():]):
            return None
        comps = [int(x) for x in re.split(_SEP, numpath)]
        label = re.match(r'^(?:' + _ENTRY_LABELS + r')', inner[m.end():].strip()).group(0)
        return comps, label
    return None


def _source_item_comps_label(it):
    """Map an extraction item (ctx.items, the source contract) to (comps, label)
    using the SAME wildcard separator as the MD parse, so source + md groups
    align 1:1 for the tail check.

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
    m = _RE_LABEL_FIRST.match(key)
    if m:
        comps = [int(x) for x in re.split(_SEP, m.group(1))]
        label = re.match(r'^(?:' + _ENTRY_LABELS + r')', key).group(0)
        return comps, label
    comps = _split_numpath(key)
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
    known = set(cfg.known_gaps or [])
    ignore = ctx.ignore_keys or set()

    # source max per (canon_label, prefix_tuple)
    src_max = {}
    for it in items:
        cl = _source_item_comps_label(it)
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
    for (gk, label, prefix_str), pairs in sorted(groups.items()):
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
            full = (prefix_str + '.' if prefix_str else '') + str(n)
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
@dataclass
class BNumberingConfig:
    """Per-book item-numbering scheme.  Read by the B-layer itself from a JSON
    file (NO orchestrator passthrough).  User's framework:
      * levels         : total numeric components (1 / 2 / 3).  '5'=1,
                         '4.1'=2, '4.11-5'=3.
      * scope          : reset boundary / continuity group of the LAST component
                         ('book' whole-file | 'chapter' | 'section').  For a
                         k-level number the *meaningful* scope is the (k-1)
                         leading components; other values are capped at
                         (levels-1) so misconfiguration cannot crash.
      * separate_types : True  -> each entry type (Thm/Lem/Def/Ex/...) its own
                                 counter (group = (prefix, type));
                         False -> all types share one counter per scope.
      * strict         : True  -> md-internal gaps become BLOCKING (hard FAIL);
                         False -> gaps are advisory warnings only.
                         DEFAULT is True (no omissions allowed).
      * known_gaps     : list[str] of human-readable entry tokens that are
                         confirmed book-sparse (NOT omissions), e.g.
                         ["Theorem 12.3", "Lemma 2.5"].  In strict mode these
                         are suppressed so they don't false-FAIL; any OTHER gap
                         still hard-blocks.  Populate after verifying against
                         the source PDF.
    The inter-component separator is a built-in wildcard (_SEP) covering
    '. - – · / ．－〜', so it need not be configured.
    """
    levels: int = 2
    scope: str = 'chapter'
    separate_types: bool = True
    strict: bool = True
    known_gaps: list = field(default_factory=list)

    def group_prefix_len(self) -> int:
        sp = {'book': 0, 'chapter': 1, 'section': 2}.get(self.scope, 1)
        return min(sp, max(0, self.levels - 1))

    @classmethod
    def from_dict(cls, d):
        return cls(
            levels=int(d.get('levels', 2)),
            scope=str(d.get('scope', 'chapter')),
            separate_types=bool(d.get('separate_types', True)),
            strict=bool(d.get('strict', True)),
            known_gaps=list(d.get('known_gaps', [])),
        )

    @classmethod
    def load_for_md(cls, md_file):
        """Locate and read the numbering config from the extract/book folder.
        Candidates (first hit wins):
          <book_dir>/_extract/b_numbering.json
          <book_dir>/_extract/verify_config.json   (key 'b_numbering' or direct)
          <book_dir>/verify_config.json            (key 'b_numbering' or direct)
        Missing/invalid -> BNumberingConfig() defaults (levels=2, chapter,
        separate_types, strict)."""
        book_dir = os.path.dirname(os.path.abspath(md_file))
        candidates = [
            os.path.join(book_dir, '_extract', 'b_numbering.json'),
            os.path.join(book_dir, '_extract', 'verify_config.json'),
            os.path.join(book_dir, 'verify_config.json'),
        ]
        for c in candidates:
            if os.path.exists(c):
                try:
                    d = json.load(open(c, encoding='utf-8'))
                except Exception:
                    continue
                if isinstance(d, dict):
                    if 'b_numbering' in d and isinstance(d['b_numbering'], dict):
                        return cls.from_dict(d['b_numbering'])
                    if 'levels' in d or 'scope' in d or 'separate_types' in d:
                        return cls.from_dict(d)
        return cls()


def _md_gap_blocking(ctx):
    """Return (BLOCKING, WARNING, present_md_keys) for item-number gaps found
    in the written .md, grouped by the per-book numbering scheme read from the
    extract/book config (BNumberingConfig.load_for_md).  The separator is a
    built-in wildcard; numbering level is variable (1/2/3).

    Default is STRICT (no omissions allowed): any discontinuity in a numbering
    group hard-blocks until verified.  Books that legitimately number items
    sparsely (e.g. a chapter with only 'Lemma 2.5') should record the confirmed
    sparse tokens in config `known_gaps` so they are suppressed instead of
    false-FAILing.  `strict: false` downgrades gaps to advisory warnings."""
    cfg = BNumberingConfig.load_for_md(ctx.md_file)
    known = set(cfg.known_gaps or [])
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
        parsed = _parse_entry(inner)
        if not parsed:
            continue
        comps, label = parsed
        if not comps:
            continue
        # Per-entry cap so a mismatched `levels` can never index out of range.
        gpl_e = min(gpl, len(comps) - 1)
        prefix = tuple(comps[:gpl_e])
        item_num = comps[gpl_e] if gpl_e < len(comps) else 0
        if cfg.separate_types and label and label != 'uncat':
            gk = f"{prefix}:{label}" if prefix else f"file:{label}"
        else:
            gk = '.'.join(str(c) for c in prefix) if prefix else "file"
        key = f"{gk}:{item_num}"
        prefix_str = '.'.join(str(c) for c in prefix)
        entries.append((gk, item_num, key, label, prefix_str))

    groups = defaultdict(list)
    present_md = set()
    for gk, num, key, label, prefix_str in entries:
        groups[(gk, label, prefix_str)].append((num, key))
        present_md.add(key)

    ignore = ctx.ignore_keys or set()
    blocking, warnings = [], []

    for (gk, label, prefix_str), pairs in sorted(groups.items()):
        nums = sorted(n for n, _ in pairs)
        present = {n for n, _ in pairs}
        first, last = nums[0], nums[-1]
        size = len(nums)

        def emit(n):
            # Human-readable token used for known_gaps / ignore matching, e.g.
            # "Theorem 12.3".  Both the raw token (original label language) and
            # the EN-normalized token are accepted, so a known_gaps entry
            # written in English also suppresses its Chinese counterpart.
            full = (prefix_str + '.' if prefix_str else '') + str(n)
            token = f"{label} {full}" if label and label != 'uncat' else full
            token_norm = f"{_norm_label(label)} {full}" if label and label != 'uncat' else full
            if token in known or token_norm in known or f"{gk}:{n}" in known or f"{gk}:{n}" in ignore:
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
        ignore_keys = ctx.ignore_keys

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
