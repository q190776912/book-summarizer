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
from page_json import PageJson

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 verify/formula_tag/formula_tag.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""formula_tag.py — Q-LAYER (order 17): FORMULA SEQUENCE-LABEL audit.

Self-contained implementation.  Verifies that every numbered display formula
in the chapter summary (`$$ ... \tag{X} $$`) maps 1:1 to a formula number that
actually exists in the book source (the set S extracted from
`page_{start..end:03d}.json` `text[].text` via per-book regex patterns derived
from the `formula` map in verify_config.json).

Two kinds of checks:

  * SEQUENCE-LABEL check (automatic FAIL):
      - FABRICATED  : a summary `\tag` number not in S (invented / mis-copied).
      - INCONSISTENT: duplicate `\tag` number, or cross-chapter number
                      (first component != current chapter when scope == 2).
  * CONTENT check (human reconciliation):
      - the summary formula LaTeX and the book-source text fragment are dumped
        side-by-side into `<extract_dir>/formula_audit.md` by `verify_all`;
        the machine does NOT judge content correctness.

Opt-in: the whole layer is a no-op (returns neutral `q_*` metadata, emits no
report, never contributes to FAIL) unless `BookConfig.formula` is a non-None
map — so the 16 legacy layers and already-finished books are untouched until a
book opts in.

S-empty degradation: if S is empty (the derived patterns matched nothing —
usually a mis-configured `formula` map), the layer only runs the structural
checks (duplicate / chapter-prefix / normalization) and emits one WARN asking
to fix the config; it does NOT judge FABRICATED / MISSING.
"""
import os
import re
import sys
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from verify.script.base import VerifyLayer, LayerResult


# Neutral no-op metadata returned when `formula` is None.  Mirrors the
# DEFAULT_RESULT defaults so report.py / verify_all always see consistent keys.
_EMPTY_Q: Dict[str, object] = {
    'q_checked': False,
    'q_fabricated': [],
    'q_inconsistent': [],
    'q_missing': [],
    'q_rows': [],
}


def _summary_has_tags(md_file: str) -> bool:
    """True iff the chapter summary contains at least one numbered formula
    (``\\tag{...}``).  Used by the opt-in gate below to distinguish a book that
    legitimately has no labeled formulas from one whose operator simply forgot
    to configure the `formula` map."""
    try:
        with open(md_file, encoding='utf-8') as f:
            data = f.read()
    except Exception:
        return False
    return bool(_TAG_RE.search(data))

# Separator characters that any book may use between number components.
_SEP_CLASS = r'[.\-·,]'
# Number token: 2 or 3 components (e.g. 1.17 / 11.1-1 / 3,4), optional trailing
# letter suffix (e.g. 2.3a).
_TAG_RE = re.compile(r'\\tag\{([^}]*)\}')
_BLOCK_RE = re.compile(r'\$\$(.*?)\$\$', re.S)

# ORDINAL style code -> default component count, used when the `formula` map
# supplies `type` but no explicit `depth`.  Mirrors config.ORDINAL_SECTION_TYPES
# lengths so the formula config aligns with the entry-ordinal config shape.
_DEFAULT_DEPTH_BY_TYPE = {1: 1, 2: 2, 3: 3, 4: 2, 5: 3, 6: 2, 7: 2, 8: 3}


def build_formula_patterns(ncomp: int) -> List[str]:
    """Build source-extraction regexes from a formula key's component count.

    `ncomp` is the number of numeric components (the `depth` field): 2 -> `1.17`,
    3 -> `11.1-1`, 1 -> `7`.  Each returned pattern has exactly ONE capture
    group returning the raw number token; SourceFormulaIndex.norm() then
    canonicalises it.  Variants cover the common CN/EN wrappers so books with
    non-standard numbering rarely need to override the `formula` map.
    """
    if ncomp is None or ncomp < 1:
        ncomp = 1
    # Capture the optional trailing letter suffix (e.g. `8.11a`) so that
    # sub-formula numbers extracted from the book source match the summary's
    # `\tag{8.11a}`.  Without this, `norm()` keeps the suffix on the summary
    # side but the source side drops it, producing FALSE FABRICATED for every
    # lettered sub-equation.  The suffix is optional, so plain `8.11` still
    # matches unchanged.
    group = r'(\d+' + (r'[.\-·,]\d+') * (ncomp - 1) + r'(?:[a-zA-Z])?)'
    if ncomp == 1:
        # Per-section bare numbering (Kreyszig): genuine formula numbers appear
        # as a STANDALONE `(N)` / `（N）` attached to a displayed equation.
        # We must NOT capture textual *references* (`式（N）`, `Eq. N`,
        # `Equation N`) nor function-call-like parentheses (`x(0)`, `p(0)`,
        # `f(0)`), which are the dominant source of false formula numbers.
        # The negative lookbehind blocks a `(` immediately preceded by a word
        # or CJK character, so `x(0)` no longer matches while a standalone
        # `(6)` / `（7a）` still does.
        return [r'(?<![\w\u4e00-\u9fff])[（(]\s*' + group + r'\s*[）)]']
    pats = [
        r'[（(]\s*' + group + r'\s*[）)]',   # （1.17） / (1.17)
        r'\bEq\.?\s+' + group,                # Eq. 1.17
        r'\bEquation\s+' + group,             # Equation 1.17
        r'式\s*[（(]?\s*' + group,            # 式（1.17）
    ]
    # The bare `group` variant catches standalone multi-component numbers
    # (`1.17`); it is not used for the 1-level case above.
    if ncomp != 1:
        pats.append(group)                     # bare 1.17
    return pats


@dataclass
class FormulaTag:
    """One `$$...$$` block that carries a `\tag` (or records an empty tag)."""
    latex: str            # the full $$...$$ block
    raw_tag: str          # raw content inside \tag{...}
    normalized: str       # normed number; '' when the block has no usable tag


def _is_digit_tail(s: str) -> bool:
    """True if `s` is non-empty and consists only of digits / dots — i.e. a
    plausible OCR-truncated trailing part of a section number."""
    return bool(s) and all(c.isdigit() or c == '.' for c in s)


def _section_match(cs: str, md_sections: List[str], cur: int) -> int:
    """Greedy FORWARD match of a parsed book-section string `cs` (e.g. '2.1',
    possibly OCR-truncated like '2.1' for '2.10') to the earliest summary
    section at index >= `cur` whose number is compatible.

    Compatible = exact equality, or one string is a digit/dot prefix of the
    other (handles OCR trailing-digit drop both ways).  Returns `cur` if
    nothing matches.  Monotonicity (only advancing, never jumping back) is what
    makes the truncated-'2.10'->'2.1' case resolve correctly: by the time the
    garbled '2.1-1' (really §2.10) appears, §2.1..§2.9 have already consumed
    their markers, so the greedy pick lands on §2.10 instead of re-hitting §2.1.
    """
    n = len(md_sections)
    for j in range(cur, n):          # exact first
        if md_sections[j] == cs:
            return j
    for j in range(cur, n):          # digit-drop prefix match
        ms = md_sections[j]
        if (ms.startswith(cs) and _is_digit_tail(ms[len(cs):])) or \
           (cs.startswith(ms) and _is_digit_tail(cs[len(ms):])):
            return j
    return cur


class SourceFormulaIndex:
    """Builds the book-source formula-number set S for a chapter.

    Only reads `text[].text` from each `page_*.json` (never the scanned
    `formulas[].latex`), applies each derived pattern, normalises the captured
    token, and groups the results under the chapter key.
    """

    def __init__(self, extract_dir: str, patterns: List[str],
                 chapter_prefix: bool = True,
                 ignore: Optional[Set[str]] = None) -> None:
        self.extract_dir = extract_dir
        self.patterns = [re.compile(p) for p in (patterns or [])]
        self.chapter_prefix = chapter_prefix
        self.ignore = set(ignore or set())
        self._by_chapter: Dict[int, Set[str]] = {}
        # normalized number -> first source text snippet (for the audit report)
        self._source_text: Dict[str, str] = {}

    # -- public API ---------------------------------------------------------
    def build(self, ch: int, start: int, end: int) -> None:
        """Scan page_{start:03d}.json .. page_{end:03d}.json and collect S."""
        self._by_chapter = {}
        self._source_text = {}
        nums: Set[str] = set()
        for pg in range(int(start), int(end) + 1):
            fp = os.path.join(self.extract_dir, f'page_{pg:03d}.json')
            if not os.path.exists(fp):
                continue
            try:
                with open(fp, encoding='utf-8') as f:
                    data = PageJson.load(os.path.join(self.extract_dir, f'page_{pg:03d}.json')).data
            except Exception:
                continue
            for block in data.get('text', []) or []:
                txt = block.get('text', '') if isinstance(block, dict) else ''
                if not txt:
                    continue
                self._scan_text(txt, nums)
        self._by_chapter[ch] = nums

    def build_sectioned(self, ch: int, start: int, end: int,
                        md_sections: List[str]) -> Dict[str, Set[str]]:
        """Per-section variant for books that number formulas within each
        section (Kreyszig: every section restarts at (1)).

        Walks the source pages in order and assigns each extracted formula
        number to the *current* section.  The current section is tracked from
        entry numbers (`C.S-K`, which explicitly carry their section) — far more
        OCR-robust than trying to parse section *titles*.  Returns a mapping
        ``section_key -> set(normalised numbers)`` plus the chapter-wide union.
        """
        sectioned: Dict[str, Set[str]] = {s: set() for s in md_sections}
        cur = 0  # index into md_sections
        for pg in range(int(start), int(end) + 1):
            fp = os.path.join(self.extract_dir, f'page_{pg:03d}.json')
            if not os.path.exists(fp):
                continue
            try:
                with open(fp, encoding='utf-8') as f:
                    data = PageJson.load(os.path.join(self.extract_dir, f'page_{pg:03d}.json')).data
            except Exception:
                continue
            for block in data.get('text', []) or []:
                txt = block.get('text', '') if isinstance(block, dict) else ''
                if not txt:
                    continue
                # Advance the current section using the "section-start" signal:
                # an entry number `C.S-1` (the first definition/theorem heading
                # of a section).  Kreyszig numbers every section's first entry as
                # `C.S-1`, so this is the reliable marker across chapters.
                # Robustness against OCR digit-drop (e.g. `2.10` scanned as
                # `2.1`): instead of an exact-string lookup we do a MONOTONIC
                # GREEDY match (_section_match) — map the parsed `C.S` to the
                # earliest as-yet-unreached summary section whose number is
                # compatible (exact, or digit-prefix of the other).  Because
                # sections appear in order in the book, by the time the garbled
                # `2.1-1` (really §2.10) shows up, §2.1..§2.9 have already
                # consumed their markers, so the greedy match lands on §2.10
                # (fixes the prior drift where §2.10's numbers piled into §2.1).
                for mm in re.finditer(r'(\d{1,3}\.\d{1,3})-(\d{1,3})', txt):
                    if mm.group(2) != '1':
                        continue
                    after = txt[mm.end():mm.end() + 1]
                    if after in '）)':
                        continue  # forward cross-reference, not a heading
                    cs = mm.group(1)
                    j = _section_match(cs, md_sections, cur)
                    if j > cur:
                        cur = j
                sec = md_sections[cur] if cur < len(md_sections) else md_sections[-1]
                # Only count `(N)` from display-formula blocks (short standalone
                # numbers or math-bearing blocks); reject CJK-prose reference
                # blocks ("由(3)式…") which would otherwise create false
                # MISSING rows.
                if not self._block_has_math(txt):
                    continue
                # extract formula numbers and attach to the current section
                for pat in self.patterns:
                    for mm in pat.finditer(txt):
                        raw = mm.group(1)
                        n = self.norm(raw)
                        if not n or n in self.ignore or not self._plausible(n):
                            continue
                        sectioned[sec].add(n)
                        # capture a short book-source snippet for the audit so
                        # MISSING rows can be judged real-vs-OCR-noise
                        if n not in self._source_text:
                            span = mm.group(0)
                            idx = txt.find(span)
                            if idx < 0:
                                idx = 0
                            snippet = txt[max(0, idx - 20): idx + len(span) + 20]
                            self._source_text[n] = snippet[:60]
        # chapter-wide union (used for FABRICATED so source-section misalignment
        # can never produce a false FABRICATED)
        union: Set[str] = set()
        for s in sectioned.values():
            union |= s
        return {'_sectioned': sectioned, '_union': union}

    def numbers_for_chapter(self, ch: int) -> Set[str]:
        return set(self._by_chapter.get(ch, set()))

    def all_numbers(self) -> Set[str]:
        out: Set[str] = set()
        for s in self._by_chapter.values():
            out |= s
        return out

    def source_text(self, n: str) -> str:
        return self._source_text.get(n, '')

    # -- helpers ------------------------------------------------------------
    def _scan_text(self, txt: str, nums: Set[str]) -> None:
        for pat in self.patterns:
            for m in pat.finditer(txt):
                raw = m.group(1)
                n = self.norm(raw)
                if not n or n in self.ignore or not self._plausible(n):
                    continue
                nums.add(n)
                if n not in self._source_text:
                    span = m.group(0)
                    idx = txt.find(span)
                    if idx < 0:
                        idx = 0
                    snippet = txt[max(0, idx - 20): idx + len(span) + 20]
                    self._source_text[n] = snippet[:60]

    @staticmethod
    def _block_has_math(txt: str) -> bool:
        """Heuristic: is `txt` a DISPLAY-formula block (whose trailing `(N)`
        is a genuine numbered formula) rather than CJK prose containing an
        inline reference like "由(3)式可得"?  Genuine formula blocks are either
        very short (a standalone `(N)` / `（N）` number) or contain math
        markers (`=`, `∑`, LaTeX commands, Greek letters, …).  Pure prose
        blocks are rejected so inline references don't inflate the source
        formula set and produce false MISSING rows.
        """
        s = txt.strip()
        if len(s) <= 8:
            return True
        if re.search(r'[=∑∫√∂∏≤≥±×÷^_{}\\]', txt):
            return True
        if re.search(r'\\(frac|sqrt|lim|sup|max|inf|sum|int|alpha|beta|'
                     r'gamma|delta|theta|lambda|mu|pi|sigma|phi|psi|'
                     r'omega|cdot|dots|partial)', txt):
            return True
        if re.search(r'[αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ]', txt):
            return True
        return False

    @staticmethod
    def _plausible(n: Optional[str]) -> bool:
        """Reject normalised numbers that cannot be genuine per-section
        formula labels: `0` (function-at-zero artifacts like `x(0)` survive
        the lookbehind only as a bare `(0)`) and any integer > 99 (Kreyszig
        sections never carry that many numbered formulas — such values are
        OCR artifacts / misreads, e.g. a stray `(96)`/`(106)`/`(146)`).
        Lettered sub-formulas (`7a`) keep their digit core and pass.
        """
        if not n:
            return False
        if n == '0':
            return False
        core = re.sub(r'[a-zA-Z]$', '', n)
        if core.isdigit() and int(core) > 99:
            return False
        return True

    @staticmethod
    def norm(raw: Optional[str]) -> Optional[str]:
        """Canonicalise a raw formula-number token.

        Strips whitespace, removes an outer `（）()` wrapper and any leading
        `Eq.` / `Equation` / `式` prefix, then folds every separator in
        `[. - · ,]` to `.` while keeping a trailing letter suffix (e.g. `a`).
        Returns None when the token cannot be parsed.

        Examples:
            '（11.1-1）' -> '11.1.1'
            'Eq. 2.3'    -> '2.3'
            '式（3,4）'  -> '3.4'
            '2.3a'       -> '2.3a'
        """
        if not raw:
            return None
        s = str(raw).strip()
        # strip leading EN/CN prefix (case-insensitive).  Handle the full word
        # `equation` BEFORE the `eq`/`eq.` prefix so the latter's optional `n`
        # does not greedily eat `eq` off `equation` and corrupt it to `uation`.
        s = re.sub(r'(?i)^equation\s+', '', s)
        s = re.sub(r'(?i)^eqn?\.?\s+', '', s)
        s = re.sub(r'^式\s*', '', s)
        s = s.strip()
        # peel a single outer parenthesis pair (handles （）and ())
        while s and s[0] in '（(' and s[-1] in '）)':
            s = s[1:-1].strip()
        m = re.match(r'(\d+(?:' + _SEP_CLASS + r'\d+){0,2})([a-zA-Z]?)$', s)
        if not m:
            return None
        core = m.group(1)
        suffix = m.group(2)
        return re.sub(_SEP_CLASS, '.', core) + suffix


def _extract_summary_tags(md_file: str) -> List[FormulaTag]:
    """Extract every `$$...$$` block; record its `\tag` (empty when absent)."""
    try:
        with open(md_file, encoding='utf-8') as f:
            md = f.read()
    except Exception:
        return []
    out: List[FormulaTag] = []
    for block in _BLOCK_RE.finditer(md):
        body = block.group(1)
        mtag = _TAG_RE.search(body)
        raw = mtag.group(1) if mtag else ''
        normalized = SourceFormulaIndex.norm(raw) if raw else ''
        out.append(FormulaTag(
            latex=block.group(0), raw_tag=raw, normalized=normalized))
    return out


def _first_component(n: str) -> str:
    """First numeric component of a normalised number (e.g. '3.1.1' -> '3')."""
    return n.split('.')[0] if '.' in n else n


def _validate_formula_config(ctx, formula, ncomp, patterns):
    """Pre-flight sanity check of the `formula` map against the actual book.

    Runs BEFORE the structural compare loop.  Returns ``None`` when the config
    is consistent with the book, or an ERROR string describing a fatal
    depth/scope mismatch.  The caller prints it to stderr and returns a
    ``q_inconsistent=[err_row]`` result so report.py FAILs the chapter instead
    of letting a mis-config silently mis-judge every ``\\tag`` (the Kreyszig
    type4/depth2/scope2 vs real type1/depth1/scope3 case).

    Agnostic probe: a UNION of the 1- and 2-component patterns, so it finds
    formula numbers regardless of how the book actually numbers them.
    """
    def _count_shapes(ext_dir, start, end):
        # Count OCCURRENCES (not distinct numbers) of single-component (N) vs
        # two-component (C.N) formula shapes across the chapter's pages.
        # Occurrence counts survive the per-section restart of single-component
        # books (every section repeats (1)..(N)), so a single-component book is
        # correctly seen as single-dominated — unlike a distinct-number SET,
        # which collapses to a handful of values and lets a few stray dotted
        # matches flip the classification.
        single_re = re.compile(r'(?<![\w\u4e00-\u9fff])[（(]\s*(\d+)\s*[）)]')
        dotted_paren = re.compile(r'[（(]\s*(\d+\.\d+)\s*[）)]')
        dotted_eq = re.compile(r'\b(?:Eq\.?|Equation)\s+(\d+\.\d+)')
        dotted_cn = re.compile(r'式\s*[（(]?\s*(\d+\.\d+)')
        single = dotted = 0
        for pg in range(int(start), int(end) + 1):
            fp = os.path.join(ext_dir, f'page_{pg:03d}.json')
            if not os.path.exists(fp):
                continue
            try:
                with open(fp, encoding='utf-8') as f:
                    data = PageJson.load(os.path.join(ext_dir, f'page_{pg:03d}.json')).data
            except Exception:
                continue
            for b in data.get('text', []) or []:
                t = b.get('text', '') if isinstance(b, dict) else ''
                if not t:
                    continue
                single += len(single_re.findall(t))
                dotted += (len(dotted_paren.findall(t))
                           + len(dotted_eq.findall(t))
                           + len(dotted_cn.findall(t)))
        return single, dotted

    # 1) Configured patterns extract nothing but the book clearly HAS formulas.
    agnostic = SourceFormulaIndex(
        ctx.ext_dir,
        build_formula_patterns(1) + build_formula_patterns(2),
        chapter_prefix=False)
    agnostic.build(ctx.ch, ctx.start, ctx.end)
    agnostic_nums = agnostic.all_numbers()

    configured = SourceFormulaIndex(ctx.ext_dir, patterns, chapter_prefix=False)
    configured.build(ctx.ch, ctx.start, ctx.end)
    configured_nums = configured.all_numbers()

    if len(configured_nums) == 0 and len(agnostic_nums) > 0:
        return (f"`formula` 配置 (type={formula.get('type')}, "
                f"depth={formula.get('depth')}, scope={formula.get('scope', 2)}) "
                f"在本章书源中抽不到任何公式编号，但 agnostic 探测抽到 "
                f"{len(agnostic_nums)} 个编号；depth/scope 与书实际公式形态不符，"
                f"请按书源真实编号重配 formula（例如单分量节级重排书应 "
                f"type=1/depth=1/scope=3）。")

    # 2) Summary \tag are all single-component but config asks for multi-component.
    tags = _extract_summary_tags(ctx.md_file)
    tag_ncomps = [len(t.normalized.split('.')) for t in tags if t.normalized]
    max_tag_ncomp = max(tag_ncomps) if tag_ncomps else 0
    if max_tag_ncomp == 1 and ncomp >= 2:
        return (f"总结中的 \\tag 编号均为单分量（如 (N)），但 formula.depth={ncomp} "
                f"（多分量）；公式应配置为 type=1/depth=1/scope=3 "
                f"（节级单分量编号，每节从 1 重排）。")

    # 3) scope == 2 (chapter-wide cross-chapter guard) but the book's formulas
    #    are single-component -> every \tag{N} would be mis-judged cross-chapter
    #    INCONSISTENT.  Decide single- vs multi-component by OCCURRENCE counts
    #    (robust to the per-section restart), NOT by the distinct-number set.
    scope = formula.get('scope', 2)
    if scope == 2:
        s, d = _count_shapes(ctx.ext_dir, ctx.start, ctx.end)
        if s > d and s > 0:
            return (f"书源公式为单分量编号（如 (N)，单分量 {s} ≫ 多分量 {d}），"
                    f"但 formula.scope=2（章级跨章守卫）会把每个 \\tag{{N}} 误判为"
                    f"跨章 INCONSISTENT；应改为 scope=3（节级重置）。"
                    f"请按书实际编号重配 formula。")

    return None


def _compare(tags: List[FormulaTag], src: 'SourceFormulaIndex', ch: int,
             chapter_prefix: bool = True,
             ignore: Optional[Set[str]] = None) -> tuple:
    """Compare summary tags against the book-source set S.

    Returns (fab, inc, miss, rows) where fab/inc/miss are lists of row dicts
    (the subset with that status) and rows is the full audit list, each row:
        {'number', 'status', 'summary_latex'(<=60), 'source_text'(<=60)}
    status ∈ {OK, FABRICATED, INCONSISTENT, MISSING, WARN}.

    `ignore` is a set of normalised formula numbers to SKIP entirely (neither
    flagged FABRICATED nor MISSING) — mirrors the `formula.ignore` map entry.
    """
    ignore = set(ignore or set())
    S = src.numbers_for_chapter(ch)
    s_empty = len(S) == 0

    fab: List[Dict[str, str]] = []
    inc: List[Dict[str, str]] = []
    miss: List[Dict[str, str]] = []
    rows: List[Dict[str, str]] = []
    # `fab`/`inc` hold one row per DISTINCT number (clean report); `rows` keeps
    # one entry per tagged formula (full per-formula audit, incl. duplicates).
    seen_fab: Set[str] = set()
    seen_inc: Set[str] = set()

    numbered = [t for t in tags if t.normalized]
    counts: Dict[str, int] = {}
    for t in numbered:
        counts[t.normalized] = counts.get(t.normalized, 0) + 1

    for t in numbered:
        n = t.normalized
        if n in ignore:
            continue
        prefix_ok = (not chapter_prefix) or (
            _first_component(n) == str(ch))
        if counts[n] > 1:
            status = 'INCONSISTENT'          # duplicate \tag number
        elif not prefix_ok:
            status = 'INCONSISTENT'          # cross-chapter number
        elif s_empty:
            status = None                    # S-empty: structural-only, no OK/FAB
        elif n in S:
            status = 'OK'
        else:
            status = 'FABRICATED'            # invented / mis-copied number
        if status is None:
            continue
        row = {
            'number': n,
            'status': status,
            'summary_latex': t.latex[:60],
            'source_text': (src.source_text(n)[:60]
                            if status != 'FABRICATED' else ''),
        }
        rows.append(row)
        if status == 'FABRICATED' and n not in seen_fab:
            seen_fab.add(n)
            fab.append(row)
        elif status == 'INCONSISTENT' and n not in seen_inc:
            seen_inc.add(n)
            inc.append(row)

    # MISSING: S numbers belonging to this chapter with no matching summary tag.
    if not s_empty:
        covered = {t.normalized for t in numbered}
        for n in sorted(S):
            if n in ignore:
                continue
            prefix_ok = (not chapter_prefix) or (
                _first_component(n) == str(ch))
            if not prefix_ok:
                continue
            if n in covered:
                continue
            row = {
                'number': n,
                'status': 'MISSING',
                'summary_latex': '',
                'source_text': src.source_text(n)[:60],
            }
            rows.append(row)
            miss.append(row)

    # S-empty degradation: structural checks already ran; emit one WARN.
    if s_empty:
        rows.append({
            'number': '',
            'status': 'WARN',
            'summary_latex': '',
            'source_text': '书源公式编号未抽到，请检查 verify_config.json 的 formula 配置',
        })

    return fab, inc, miss, rows


def _extract_summary_tags_sectioned(md_file: str) -> List[tuple]:
    """Like `_extract_summary_tags` but also records the section each tagged
    `$$...$$` block belongs to, by walking `## §C.S` headings in order.

    Returns a list of ``(section_key, FormulaTag)``.  Blocks appearing before
    the first section heading are attached to the first section (rare; keeps
    them from being silently dropped).
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            md = f.read()
    except Exception:
        return []
    sec_re = re.compile(r'^##\s*§?\s*(\d+\.\d+)', re.M)
    md_sections = sec_re.findall(md)
    if not md_sections:
        return []
    parts = re.split(r'(^##\s*§?\s*\d+\.\d+.*$)', md, flags=re.M)
    out: List[tuple] = []
    cur = md_sections[0]
    for part in parts:
        hm = re.match(r'^##\s*§?\s*(\d+\.\d+)', part)
        if hm:
            cur = hm.group(1)
            continue
        for block in _BLOCK_RE.finditer(part):
            body = block.group(1)
            mtag = _TAG_RE.search(body)
            raw = mtag.group(1) if mtag else ''
            normalized = SourceFormulaIndex.norm(raw) if raw else ''
            out.append((cur, FormulaTag(
                latex=block.group(0), raw_tag=raw, normalized=normalized)))
    return out


def _compare_sectioned(tags_sec: List[tuple], src_sectioned: Dict[str, Set[str]],
                       md_sections: List[str], chapter_union: Set[str],
                       ignore: Optional[Set[str]] = None,
                       src: Optional['SourceFormulaIndex'] = None) -> tuple:
    """Per-section comparison for formula numbering.

    * FABRICATED : a summary ``\\tag`` number not in the chapter-wide union S
      (genuinely invented / mis-copied).  Uses the union (not the per-section
      set) so source-section misalignment can never false-flag.
    * INCONSISTENT: duplicate ``\\tag`` number *within the same section*
      (legitimate for per-section numbering across sections, so must be local).
    * MISSING    : a book-source formula number for this section absent from
      the summary (WARN only; uses the per-section set).
    """
    ignore = set(ignore or set())
    fab: List[Dict[str, str]] = []
    inc: List[Dict[str, str]] = []
    miss: List[Dict[str, str]] = []
    rows: List[Dict[str, str]] = []
    seen_fab: Set[str] = set()
    seen_inc: Set[str] = set()

    md_by_sec: Dict[str, list] = {s: [] for s in md_sections}
    for sec, t in tags_sec:
        if sec in md_by_sec:
            md_by_sec[sec].append(t)

    for sec in md_sections:
        S = src_sectioned.get(sec, set())
        s_empty = len(S) == 0
        tags = md_by_sec[sec]
        counts: Dict[str, int] = {}
        for t in tags:
            if t.normalized:
                counts[t.normalized] = counts.get(t.normalized, 0) + 1
        for t in tags:
            n = t.normalized
            if not n or n in ignore:
                continue
            if counts[n] > 1:
                status = 'INCONSISTENT'
            elif n not in chapter_union:
                status = 'FABRICATED'
            else:
                status = 'OK'
            row = {
                'number': n,
                'status': status,
                'summary_latex': t.latex[:60],
                'source_text': '',
            }
            rows.append(row)
            if status == 'FABRICATED' and n not in seen_fab:
                seen_fab.add(n)
                fab.append(row)
            elif status == 'INCONSISTENT' and n not in seen_inc:
                seen_inc.add(n)
                inc.append(row)
        # MISSING (per-section, WARN)
        if not s_empty:
            covered = {t.normalized for t in tags
                       if t.normalized and t.normalized not in ignore}
            for n in sorted(S):
                if n in ignore or n in covered:
                    continue
                row = {
                    'number': n,
                    'status': 'MISSING',
                    'summary_latex': '',
                    'source_text': (src.source_text(n)[:60]
                                    if src else ''),
                }
                rows.append(row)
                miss.append(row)

    if all(len(src_sectioned.get(s, set())) == 0 for s in md_sections):
        rows.append({
            'number': '',
            'status': 'WARN',
            'summary_latex': '',
            'source_text': '书源公式编号未抽到，请检查 verify_config.json 的 formula 配置',
        })
    return fab, inc, miss, rows


class QLayer(VerifyLayer):
    code = 'Q'
    name = 'formula-tag'
    order = 17               # current max layer is P (order 16); Q runs after it
    auto_fixable = False     # audit-only layer; no --fix

    def run(self, ctx) -> LayerResult:
        # GATE: opt-in via the `formula` map.  When absent the layer is a pure
        # no-op so the 16 legacy layers and already-finished books are
        # completely unaffected.
        if ctx.config.formula is None:
            # Pre-flight guard (2026-08-08): silently no-op-ing while the
            # summary actually contains numbered formulas would make the agent
            # (and downstream readers of the verify report) believe formula
            # sequence-label verification "passed" when it never ran.  If the
            # chapter has `\tag{...}` formulas, the operator MUST first set up
            # the `formula` config from the book's real numbering — so warn
            # loudly instead of returning a clean no-op.
            if _summary_has_tags(ctx.md_file):
                print(
                    "[Q-LAYER WARN] 总结含带序标公式 (\\tag{...})，但 "
                    "verify_config.json 缺少 `formula` 配置 → Q 层已静默 no-op，"
                    "公式序标**未校验**，不可报\"公式校验通过\"。\n"
                    "  → 请先按书实际公式编号填写 `formula` 配置再跑 verify：\n"
                    "      \"formula\": {\"type\": <风格码>, \"depth\": <编号段数>, "
                    "\"scope\": 2, \"ignore\": []}\n"
                    "    depth: C.N(如 2.6)→2；C.S.N / C.S-N(如 11.1-1)→3。\n"
                    "    scope 默认 2（章级编号，开启跨章守卫）；全局编号书用 1。\n"
                    "    不确定段数时，先扫该书 page_*.json 的 text[] 实测公式标签。",
                    file=sys.stderr,
                )
            return LayerResult(code='Q', metadata=dict(_EMPTY_Q))

        formula = ctx.config.formula
        ftype = formula.get('type')
        fdepth = formula.get('depth')
        fignore = set(formula.get('ignore') or [])
        scope = formula.get('scope', 2)
        # Per-section formula numbering (Kreyszig: every section restarts at
        # (1)).  FABRICATED/INCONSISTENT are checked section-locally; the
        # chapter-prefix cross-chapter guard is OFF.
        section_scoped = (scope == 3)
        # Cross-chapter guard (first component == current chapter) is ON iff
        # scope == 2 (chapter-level numbering); book/section scope disables it.
        chapter_prefix = (scope == 2)
        ncomp = fdepth or _DEFAULT_DEPTH_BY_TYPE.get(ftype, 3)
        patterns = build_formula_patterns(ncomp)

        # Pre-flight: validate the formula config against the actual book BEFORE
        # the structural compare loop.  A depth/scope mismatch would otherwise
        # silently mis-judge every \tag (e.g. Kreyszig mis-set as type4/depth2/
        # scope2 makes each \tag{N} a false cross-chapter INCONSISTENT -> FAIL,
        # which operators "fix" by deleting all \tag).  Surface it as a clear
        # ERROR and FAIL the chapter instead.
        err = _validate_formula_config(ctx, formula, ncomp, patterns)
        if err is not None:
            err_row = {
                'number': '',
                'status': 'ERROR',
                'summary_latex': '',
                'source_text': err,
            }
            print(f"[Q-LAYER ERROR] {err}", file=sys.stderr)
            return LayerResult(code='Q', metadata={
                'q_checked': True,
                'q_fabricated': [],
                'q_inconsistent': [err_row],
                'q_missing': [],
                'q_rows': [err_row],
                'q_error': err,
            })

        if section_scoped:
            md_text = ''
            try:
                with open(ctx.md_file, encoding='utf-8') as f:
                    md_text = f.read()
            except Exception:
                md_text = ''
            md_sections = re.findall(r'^##\s*§?\s*(\d+\.\d+)', md_text, re.M)
            if not md_sections:
                # No section headings -> fall back to the plain chapter path.
                section_scoped = False
            else:
                tags_sec = _extract_summary_tags_sectioned(ctx.md_file)
                src = SourceFormulaIndex(ctx.ext_dir, patterns, False, fignore)
                built = src.build_sectioned(ctx.ch, ctx.start, ctx.end,
                                            md_sections)
                src_sec = built['_sectioned']
                union = built['_union']
                fab, inc, miss, rows = _compare_sectioned(
                    tags_sec, src_sec, md_sections, union, fignore, src)
                return LayerResult(code='Q', metadata={
                    'q_checked': True,
                    'q_fabricated': fab,
                    'q_inconsistent': inc,
                    'q_missing': miss,
                    'q_rows': rows,
                })

        tags = _extract_summary_tags(ctx.md_file)
        src = SourceFormulaIndex(ctx.ext_dir, patterns, chapter_prefix, fignore)
        src.build(ctx.ch, ctx.start, ctx.end)

        fab, inc, miss, rows = _compare(tags, src, ctx.ch, chapter_prefix, fignore)
        return LayerResult(code='Q', metadata={
            'q_checked': True,
            'q_fabricated': fab,
            'q_inconsistent': inc,
            'q_missing': miss,
            'q_rows': rows,
        })
