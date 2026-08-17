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
    'q_order_mismatch': [],
    'q_misplaced': [],
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
# Letter/Roman-LED formula numbering (e.g. `(A.3)` / `（I.2）` / `(II.5)` /
# `(App.2)`) — RESERVED.  The digit-led `norm()` / `build_formula_patterns()`
# below cannot capture a number whose first component is a letter / Roman
# numeral, so a book using such numbering is surfaced (WARN) rather than
# silently validated.  This regex is the *detection* probe.
#
# 🔴 TIGHTENED (2026-08-16): it now matches ONLY genuine letter-led formula
# numbers so it no longer misfires on algebraic parentheticals (`(n-1)` /
# `(p-1)` / `(k-1)`) or cross-reference labels (`(Fig. 19)` / `(Chap. 9)` /
# `(Prob. 10)`).  The OLD pattern `[A-Za-z]{1,4}[.\-·,]\d+` matched all of those
# and made EVERY chapter of a digit-led book (Kreyszig) spuriously BLOCK.  A real
# letter-led formula number is: opening paren + SHORT prefix (single capital
# letter / Roman numeral / `App`/`Ap`) + `.` or `·` separator (NEVER `-` or `,`)
# + digits + optional trailing letter + closing paren.  Reference words
# (Fig/Chap/Sec/Eq/Prob/...) are excluded via negative lookahead.
_LETTER_LED_RE = re.compile(
    r'[（(]\s*'
    r'(?!(?:Fig|Chap|Sec|Eq|Prob|Ex|Def|Lem|Thm|Cor|Prop|Rem|Alg|Sol|Note|'
    r'Lec|Part|Vol|Appx|Tbl|Tab|Exa|Exs|Thms|Lems|Cors|Props|Defs|Rmk|Remk)\b)'
    r'(?:[A-Z]|[IVXLCDM]{1,5}|App|Ap)'
    r'\s*[.·]\s*'
    r'\d+(?:[a-zA-Z])?'
    r'\s*[）)]')
# Root fix (2026-08-16): numbered ITEM labels (Definition/Theorem/Remark/
# Example/Proposition/Corollary/Exercise/Lemma N.N.N — including common OCR
# misspellings "Defnition"/"Exercse") are NOT formula tags.  A bare (non-strong)
# pattern hit that sits immediately after one of these keywords is the item
# label, not a displayed equation; it must be skipped so it cannot pollute the
# source formula set S and force a spurious `\tag` in the summary (false green).
_ITEM_LABEL_RE = re.compile(
    r'(definition|theorem|remark|example|proposition|corollary|'
    r'exercise|lemma|defnition|exercse)\b', re.IGNORECASE)
# Number token: 2 or 3 components (e.g. 1.17 / 11.1-1 / 3,4), optional trailing
# letter suffix (e.g. 2.3a).
_TAG_RE = re.compile(r'\\tag\{([^}]*)\}')
_BLOCK_RE = re.compile(r'\$\$(.*?)\$\$', re.S)

# ORDINAL style code -> default component count, used when the `formula` map
# supplies `type` but no explicit `depth`.  Mirrors config.ORDINAL_SECTION_TYPES
# lengths so the formula config aligns with the entry-ordinal config shape.
# Canonical `type` -> numbering-depth map.  SINGLE source of truth, shared with
# config/verify_config/verify_config.py (ORDINAL_DEPTH).  `depth` is NOT an
# independent config field in the `formula` map — it is always derived from
# `type`, so we reuse ORDINAL_DEPTH directly instead of a second, drift-prone map.
try:
    from verify_config import ORDINAL_DEPTH as _DEFAULT_DEPTH_BY_TYPE
except Exception:  # pragma: no cover — boot normally injects config/verify_config
    _DEFAULT_DEPTH_BY_TYPE = {1: 1, 2: 2, 3: 3, 4: 2, 5: 3, 6: 2, 7: 2, 8: 3, 9: 3}

# Heading regex used to assign a book-source formula its enclosing section.
# Matches a SHORT numbered line like "2.3.2 Preliminaries" / "§2.2 Stability ...".
# Attribution rule: a formula's enclosing section is the nearest preceding
# numbered heading line (the canonical convention carried over when the
# formula-manifest subsystem's capability was merged into this Q layer).
_HEAD_RE = re.compile(r'^\s*(?:§\s*)?(\d+(?:\.\d+)+)\b')

# Figure-caption leader prefixes (Bug #22).  A text block whose stripped content
# STARTS with one of these keywords is a figure caption, NOT a formula-bearing
# line.  Captions may embed math (e.g. `|Φλ|`) and sub-labels like "Fig. 2.2A" /
# "Fig. 2.3(a)"; the embedded `N.N` must NOT be mistaken for a numbered display
# formula (which would fabricate a spurious source number and trigger a q-miss).
# The leading-prefix heuristic is deliberately book-agnostic.
_CAPTION_LEAD_RE = re.compile(r'^\s*(?:figure|fig\.?\b|图)', re.IGNORECASE)


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
    # TODO(letter-led): books whose formula numbers START with a letter / Roman
    # numeral (e.g. `(A.3)` / `（I.2）`) are NOT supported yet.  To add support,
    # prepend an optional leading prefix `([A-Za-z]{1,4}[.\-·,])?` to `group`
    # below (and mirror it in norm()), then add a `letter` branch to
    # `_validate_formula_config` so the pre-flight stops treating them as a
    # mis-config.  Until then, `_detect_letter_led_formulas` surfaces a WARN.
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
                 ignore: Optional[Set[str]] = None,
                 ncomp: Optional[int] = None,
                 keep_cross_refs: bool = True) -> None:
        self.extract_dir = extract_dir
        self.patterns = [re.compile(p) for p in (patterns or [])]
        self.chapter_prefix = chapter_prefix
        self.ignore = set(ignore or set())
        # keep_cross_refs (default True, backward-compatible): when True, a
        # parenthesised `(C.N)` is ALWAYS kept in S even in math-free prose
        # (treated as a possible cross-reference the summary might reproduce,
        # so a summary `\tag{C.N}` is never falsely FABRICATED).  When False
        # (section-numbered books that never reproduce cross-chapter formulas),
        # parenthesised `(C.N)` inside a math-free prose block is filtered out,
        # so stray cross-references ("By (3.2) …") no longer pollute S and
        # produce false q-miss rows.  Real numbered display formulas (in a
        # math-bearing block) are still kept either way.
        self.keep_cross_refs = keep_cross_refs
        # ncomp (depth) enables the Bug #18 source-noise gate in _scan_text:
        # only multi-component books (ncomp>=2) need it, because their bare
        # `N.N` pattern otherwise matches section headings / cross-references /
        # figure sub-numbers / bibliography page numbers as "formula numbers".
        self._ncomp = ncomp
        self._by_chapter: Dict[int, Set[str]] = {}
        # normalized number -> first source text snippet (for the audit report)
        self._source_text: Dict[str, str] = {}
        # ORDER_MISMATCH / MISPLACED support (populated during build / build_sectioned):
        #   _primary_pos  : normalized number -> earliest (page, y) occurrence
        #   _book_section : normalized number -> book-side enclosing section (first occurrence)
        #   _cur_heading  : running "nearest preceding heading" during a scan
        self._primary_pos: Dict[str, tuple] = {}
        self._book_section: Dict[str, str] = {}
        # Per-(section, number) membership in the book source. Unlike the global
        # `_book_section` (which only keeps the FIRST occurrence and is useless
        # for per-section-restart numbering where every section repeats (1)..(N)),
        # this maps `(sec, n) -> sec` so a formula `\tag{n}` under section `sec`
        # is "correctly placed" iff `(sec, n)` actually exists in the book.
        self._book_section_sec: Dict[tuple, str] = {}
        self._cur_heading: Optional[str] = None

    # -- public API ---------------------------------------------------------
    def build(self, ch: int, start: int, end: int) -> None:
        """Scan page_{start:03d}.json .. page_{end:03d}.json and collect S."""
        self._by_chapter = {}
        self._source_text = {}
        self._primary_pos = {}
        self._book_section = {}
        self._cur_heading = None
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
                # Bug #22: figure captions embed math + sub-labels that look
                # like formula numbers ("Fig. 2.2A"); skip them entirely.
                if self._is_figure_caption(txt):
                    continue
                y = None
                if isinstance(block, dict):
                    poly = block.get('poly') or []
                    if len(poly) >= 2:
                        y = poly[1]
                self._track_heading(txt)
                self._scan_text(txt, nums, pg, y)
        self._by_chapter[ch] = nums

    def build_sectioned(self, ch: int, start: int, end: int,
                        md_sections: List[str],
                        ncomp: int = 1) -> Dict[str, Set[str]]:
        """Per-section variant for books that number formulas within each
        section (Kreyszig: every section restarts at (1)).

        Walks the source pages in order and assigns each extracted formula
        number to the *current* section.  The current section is tracked from
        entry numbers (`C.S-K`, which explicitly carry their section) — far more
        OCR-robust than trying to parse section *titles*.  Returns a mapping
        ``section_key -> set(normalised numbers)`` plus the chapter-wide union.
        """
        sectioned: Dict[str, Set[str]] = {s: set() for s in md_sections}
        self._primary_pos = {}
        self._book_section = {}
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
                # Bug #22: skip figure-caption lines (they embed math + sub-labels
                # that look like formula numbers, e.g. "Fig. 2.2A").
                if self._is_figure_caption(txt):
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
                # Strogatz-style section advance: the book carries clean section
                # TITLES ("4.1 Examples and Definitions", "4.6 Superconducting
                # Josephson Junctions") instead of Kreyszig's `C.S-1` entry
                # markers.  Advance `cur` ONLY to the *immediate next* summary
                # section when a source heading matches it exactly (sequential
                # progression).  This prevents out-of-order section *mentions*
                # (chapter roadmaps, cross-references) on early pages from
                # jumping `cur` forward and sweeping later pages' numbers into
                # the wrong section.  A 3-level heading like `7.2.1` reduces to
                # `7.2` and still confirms the next section.  Monotonic by
                # construction (cur only ever +1).  For Kreyszig this is
                # redundant with the dash markers above and lands on the same
                # section, so behaviour is unchanged.  Without any advance
                # signal, `cur` would stick at 0 and every book number would
                # pile into the first section, producing mass false MISSING.
                _hm = _HEAD_RE.match(txt.strip())
                if _hm and len(txt.strip()) < 80:
                    _hs = _hm.group(1)
                    _hp = _hs.split('.')
                    _h2 = '.'.join(_hp[:2]) if len(_hp) >= 2 else _hs
                    if cur + 1 < len(md_sections) and _h2 == md_sections[cur + 1]:
                        cur = cur + 1
                sec = md_sections[cur] if cur < len(md_sections) else md_sections[-1]
                y = None
                if isinstance(block, dict):
                    poly = block.get('poly') or []
                    if len(poly) >= 2:
                        y = poly[1]
                # Only count `(N)` from genuine display-formula blocks.
                #
                # For per-section *standalone* numbering (Kreyszig, ncomp==1)
                # the only authoritative source of a numbered formula is a
                # STANDALONE bare label block — `(N)` / `（N）` optionally
                # followed by `.` or a space — i.e. the canonical formula tag
                # sitting on its own line beneath a displayed equation.  A
                # longer block that merely *contains* `(N)` inside running prose
                # ("the last sum in (13)", "From (1), with r→∞", an OCR stray
                # "(1) (b) B(x₀;r)=…") is a cross-reference / definition marker,
                # NOT a numbered formula, and must be rejected — otherwise it
                # pollutes S and produces false MISSING rows ("13"/"1") for
                # numbers the book never labels.  The general `_block_has_math`
                # heuristic (which also admits math-bearing blocks) is too loose
                # for the standalone case, so we apply the stricter bare-label
                # gate here; for multi-component books (ncomp>=2) the standalone
                # pattern rarely fires on prose and the old heuristic is kept.
                if ncomp == 1:
                    if not re.fullmatch(r'\s*[（(]\s*\d+[a-zA-Z]?\s*[）)]\s*[.。]?\s*', txt):
                        continue
                elif not self._block_has_math(txt):
                    continue
                # extract formula numbers and attach to the current section
                for pat in self.patterns:
                    for mm in pat.finditer(txt):
                        raw = mm.group(1)
                        n = self.norm(raw)
                        if not n or n in self.ignore or not self._plausible(n):
                            continue
                        sectioned[sec].add(n)
                        # first occurrence's section == book-side definition section
                        if n not in self._book_section:
                            self._book_section[n] = sec
                        # (sec, n) membership — authoritative for per-section books
                        self._book_section_sec[(sec, n)] = sec
                        self._record_pos(n, pg, y)
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

    def primary_pos(self, n: str):
        """Earliest (page, y) occurrence of `n` (definition site), or None."""
        return self._primary_pos.get(n)

    def book_section(self, n: str):
        """Book-side enclosing section of `n`'s definition, or None."""
        return self._book_section.get(n)

    def source_numbers(self) -> Set[str]:
        """All book-source formula numbers this index extracted (works for both
        the plain `build()` and the sectioned `build_sectioned()` paths — neither
        relies on `_by_chapter`, which only the plain path populates)."""
        return set(self._primary_pos.keys())

    # -- helpers ------------------------------------------------------------
    def _track_heading(self, txt: str) -> None:
        """Update the running nearest-preceding-heading from a short numbered
        line (e.g. "2.3.2 Preliminaries").  A formula's enclosing section is the
        nearest preceding numbered heading line.
        """
        s = txt.strip()
        hm = _HEAD_RE.match(s)
        if hm and len(s) < 80:
            self._cur_heading = hm.group(1)

    def _record_pos(self, n: str, pg, y) -> None:
        """Record the earliest (page, y) occurrence of `n` (its definition site)."""
        if n not in self._primary_pos or (pg, y) < self._primary_pos[n]:
            self._primary_pos[n] = (pg, y)

    def _update_pos(self, n: str, pg, y) -> None:
        """Record earliest position AND anchor the book-side section to the
        first occurrence's enclosing heading (the definition location)."""
        self._record_pos(n, pg, y)
        if n not in self._book_section and self._cur_heading is not None:
            self._book_section[n] = self._cur_heading

    def _scan_text(self, txt: str, nums: Set[str], pg=None, y=None) -> None:
        # 🔴 Bug #18 修复（增强）：多分量编号 (ncomp>=2) 的 bare `N.N` pattern
        # 会命中节标题 ("1.1 Introduction")、图号子图 ("Fig. 1.1a")、参考文献
        # 页码 ("pp. 1-34") 等散文数字串——这些非公式编号须被拦截，否则污染
        # 书源集合 S，制造假 MISSING。但「括号包裹的公式编号」`(C.N)` 是书源
        # 与 summary 共用的强信号：既用于标注公式，也用于散文交叉引用
        # ("By (3.1) we get A.")。一刀切门禁会把散文里的 `(3.1)` 漏抽，导致
        # summary 合法的 \tag{3.1} 被误判 FABRICATED、且 S 不全。
        # 策略：仅对「裸 / 无强前缀」命中施加 _block_has_math 门禁；带括号或
        # 带 Eq./Equation/式 前缀的命中（强信号）无条件保留。ncomp==1 不门禁。
        need_gate = (self._ncomp is not None and self._ncomp >= 2)
        has_math = self._block_has_math(txt) if need_gate else True
        for pat in self.patterns:
            for m in pat.finditer(txt):
                span = m.group(0)
                if need_gate and not has_math and (
                        not self.keep_cross_refs or not self._is_strong_signal(span)):
                    continue
                raw = m.group(1)
                # Root fix (2026-08-16): a figure sub-caption label such as
                # "Figure 1.1.1b" / "Fig. 2.2A" matches the lettered-sub-equation
                # pattern but is NOT a numbered formula.  Real formula sub-
                # equations appear as a STANDALONE `(8.11a)` (no adjacent
                # "Figure" keyword) and stay captured.  Skip the figure-anchored
                # case so it cannot fabricate a spurious source number
                # (false q-miss).  Book-agnostic: only fires when the figure
                # keyword directly precedes the numbered sublabel.
                if re.search(r'\bfig\w*\.?\s+\d+[.\-·,]\d+[.\-·,]\d+[a-zA-Z]', txt,
                             re.IGNORECASE):
                    continue
                # Root fix (2026-08-16): a numbered ITEM label ("Definition
                # 2.1.2.") is not a displayed-formula tag.  Bare (non-strong)
                # hits immediately preceded by an item-label keyword are skipped
                # so they do not pollute S (and thus do not force a spurious
                # `\tag` in the summary — the "false green" the user forbids).
                if not self._is_strong_signal(span):
                    _pre = txt[max(0, m.start() - 24):m.start()]
                    if _ITEM_LABEL_RE.search(_pre):
                        continue
                n = self.norm(raw)
                if not n or n in self.ignore or not self._plausible(n):
                    continue
                nums.add(n)
                if n not in self._source_text:
                    idx = txt.find(span)
                    if idx < 0:
                        idx = 0
                    snippet = txt[max(0, idx - 20): idx + len(span) + 20]
                    self._source_text[n] = snippet[:60]
                if pg is not None:
                    self._update_pos(n, pg, y)

    @staticmethod
    def _is_figure_caption(txt: str) -> bool:
        """True if `txt` is a figure-caption line (starts with a figure-label
        keyword).  Such lines must be excluded from formula-number extraction
        (Bug #22): their embedded math (`|Φλ|`) trips the `_block_has_math`
        gate and their sub-labels ("Fig. 2.2A") would otherwise be misread as a
        numbered display formula, fabricating a spurious source number."""
        if not txt:
            return False
        return bool(_CAPTION_LEAD_RE.match(txt))

    @staticmethod
    def _block_has_math(txt: str) -> bool:
        """Heuristic: is `txt` a DISPLAY-formula block (whose trailing `(N)`
        is a genuine numbered formula) rather than prose containing an
        inline reference like "由(3)式可得" / "the last sum in (13)" / an OCR
        artifact like "(1) (b) B(x₀;r)="?

        Genuine formula blocks are either very short (a standalone `(N)` /
        `（N）` number — the canonical Kreyszig formula label) or contain real
        math (an `=`/relation, a sum/integral, a Greek letter, a LaTeX
        command, …).  A longer block is treated as PROSE-REFERENCE (rejected)
        unless it carries a math marker, because genuine numbered formulas in
        this book are either a bare `(N)` or sit next to a displayed equation.
        This prevents prose/reference noise from entering the source formula
        set S and producing false MISSING rows (e.g. "(13)" in "the last sum
        in (13)", which the book never labels as a numbered formula).
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
    def _is_strong_signal(span: str) -> bool:
        """True if a matched number token is a STRONG formula-number signal:
        parenthesized `(C.N)` / `（C.N）`, or prefixed by `Eq.` / `Equation` /
        `式`. Strong signals are ALWAYS kept, even in math-free prose (they also
        serve as cross-references, e.g. "By (3.1) we get A."). Bare `C.N`
        tokens are NOT strong and stay subject to the _block_has_math gate
        (they cover section headings, figure numbers, reference pages, etc.)."""
        s = span.strip()
        if not s:
            return False
        if s[0] in ('(', '（') and s[-1] in (')', '）'):
            return True
        if re.match(r'(?i)^(eq\.?|equation|式)', s):
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
            # TODO(letter-led): tokens like `A.3` / `I.2` (letter / Roman
            # prefix) fall through here and return None.  When support lands,
            # extend this regex with an optional leading `([A-Za-z]{1,4}
            # [.\-·,])?` group and normalise it.  Until then such numbers are
            # intentionally un-validated (see `_detect_letter_led_formulas`).
            return None
        core = m.group(1)
        suffix = m.group(2)
        # Fold separators to '.' and strip leading zeros per component so that
        # `(02)` / `(02.5)` normalise to `2` / `2.5` and match `\tag{2}` /
        # `\tag{2.5}`.  Pure-digit components only, so int() is safe.
        norm_core = re.sub(_SEP_CLASS, '.', core)
        norm_core = '.'.join(str(int(p)) for p in norm_core.split('.'))
        return norm_core + suffix


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
        #
        # 🔴 噪声门禁（Bug #17 修复）：原始实现用裸正则直接数所有 `(N)` / `(C.N)`
        # 出现次数，把函数调用 `f(0)`、交叉引用散文 `(1)`、行内 `x(0)` 等噪声也
        # 计入，导致「单分量出现次数 ≫ 多分量」误判（如 Koopman Ch1：真实公式
        # 编号全是章级两段 `(1.1)`，但噪声把单分量次数抬到 90 > 68，pre-flight
        # 错误地强制 scope=3 并阻断整章）。这里复用真实抽取用的「真公式编号」门禁：
        #   * 单分量只计「独立成行的标签块」 `(N)` / `（N）`（与 build_sectioned
        #     对 ncomp==1 的 fullmatch 门禁一致）；
        #   * 两段只计「含数学的块」（`_block_has_math`，与 ncomp>=2 门禁一致），
        #     散文里的 `(1.2) 暗示` 不计入。
        # 这样 Kreyszig（真·单分量每段重置，标签独立成行）仍被正确识别为单分量主导，
        # 而 Koopman（标签为章级两段、噪声为函数/散文括号）不再被误判。
        single_re = re.compile(r'(?<![\w\u4e00-\u9fff])[（(]\s*(\d+)\s*[）)]')
        dotted_paren = re.compile(r'[（(]\s*(\d+\.\d+)\s*[）)]')
        # 3-component (C.S.N) numbers are also genuine multi-component formula
        # labels; the original dotted_paren only matched 2 components, so
        # chapter-wide 3-component books (e.g. Lasota-Mackey 5.7.21) were wrongly
        # diagnosed as single-component and failed the pre-flight. Count them as
        # dotted too.
        dotted_paren3 = re.compile(r'[（(]\s*(\d+\.\d+\.\d+)\s*[）)]')
        dotted_eq = re.compile(r'\b(?:Eq\.?|Equation)\s+(\d+\.\d+)')
        dotted_cn = re.compile(r'式\s*[（(]?\s*(\d+\.\d+)')
        _standalone = re.compile(r'\s*[（(]\s*\d+[a-zA-Z]?\s*[）)]\s*[.。]?\s*')
        _has_math = SourceFormulaIndex._block_has_math
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
                # Bug #22: figure captions embed math + sub-labels that look like
                # formula numbers; exclude them so they don't skew the shape count.
                if SourceFormulaIndex._is_figure_caption(t):
                    continue
                ts = t.strip()
                if _standalone.fullmatch(ts):
                    # Genuine standalone formula label on its own line.
                    if dotted_paren.search(t) or dotted_eq.search(t) or dotted_cn.search(t) or dotted_paren3.search(t):
                        dotted += (len(dotted_paren.findall(t))
                                   + len(dotted_eq.findall(t))
                                   + len(dotted_cn.findall(t))
                                   + len(dotted_paren3.findall(t)))
                    elif single_re.search(t):
                        single += len(single_re.findall(t))
                    continue
                # Non-standalone: only count two-component numbers inside a
                # math-bearing block (genuine displayed-equation labels).  Bare
                # prose references / function-call parens are rejected so they
                # never inflate the single count.
                if _has_math(t):
                    dotted += (len(dotted_paren.findall(t))
                               + len(dotted_eq.findall(t))
                               + len(dotted_cn.findall(t))
                               + len(dotted_paren3.findall(t)))
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
                f"depth={_DEFAULT_DEPTH_BY_TYPE.get(formula.get('type'), 3)}, "
                f"scope={formula.get('scope', 2)}) "
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


def _detect_letter_led_formulas(ext_dir: str, start, end) -> Set[str]:
    """RESERVED probe: find letter / Roman-led formula numbers in the book
    source (e.g. `(A.3)` / `（I.2）`).

    These are NOT yet validated by the Q layer (norm() / build_formula_patterns
    are digit-led).  Detecting them lets `run()` emit a clear WARN instead of
    silently degrading to a false-green S-empty pass.  Scans the same
    `page_*.json` `text[]` the real extractor reads.  Returns the raw matched
    tokens (for the surfaced message), or an empty set when none are found.
    """
    found: Set[str] = set()
    for pg in range(int(start), int(end) + 1):
        fp = os.path.join(ext_dir, f'page_{pg:03d}.json')
        if not os.path.exists(fp):
            continue
        try:
            data = PageJson.load(fp).data
        except Exception:
            continue
        for b in data.get('text', []) or []:
            t = b.get('text', '') if isinstance(b, dict) else ''
            if not t:
                continue
            for m in _LETTER_LED_RE.finditer(t):
                found.add(m.group(0).strip())
    return found


def _letter_led_note(found: Set[str]) -> Optional[str]:
    """Build the (non-blocking) WARN note for letter / Roman-led formula numbers.

    Returns the note string when `found` is non-empty, else None.  The Q layer
    cannot yet *validate* such numbering (norm() / build_formula_patterns are
    digit-led — see TODO(letter-led) anchors).  Per the Q-layer SSOT
    (formula_tag.md), this is a **WARN + downgrade**, NOT a blocking FAIL: the
    layer skips 1:1 validation of those numbers and asks for human
    reconciliation via formula_audit.md, instead of silently degrading to a
    false-green pass OR spuriously blocking a digit-led book (the old behaviour
    misfired on algebraic `(n-1)` / reference `(Fig. 19)` parentheticals).
    """
    if not found:
        return None
    return (
        f"书源含字母/罗马开头公式编号（如 {sorted(found)[:3]}…），"
        f"但 Q 层公式序标校验的 norm()/build_formula_patterns() 目前**仅支持数字开头**编号，"
        f"此类编号的 1:1 真实性逻辑尚未实现，故**降级为 WARN（不阻断）**：该部分公式序标"
        f"未经机器校验，请人工核对 <extract>/formula_audit.md。待实现「可选首段字母/罗马前缀」"
        f"支持（见代码 TODO(letter-led) 锚点）后可恢复校验。")


def _compare(tags: List[FormulaTag], src: 'SourceFormulaIndex', ch: int,
             chapter_prefix: bool = True,
             ignore: Optional[Set[str]] = None,
             s_empty_note: Optional[str] = None) -> tuple:
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
            'source_text': (
                s_empty_note
                or '书源公式编号未抽到（可能是 formula 的 depth/scope 配错，'
                   '或书源采用字母/罗马开头编号 (A.3)/(I.2) 这类 Q 层暂不支持的'
                   '形态——预留待实现）；公式序标校验对本章降级，不可报"通过"。'),
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


def _section_prefix_compatible(a: str, b: str) -> bool:
    """True if section strings `a`, `b` are component-prefix-compatible
    (one is an ancestor of the other).  Resolves the spurious MISPLACED that
    arose whenever the summary's heading granularity differed from the book's:
    e.g. the summary emits only `## §1.3` while the book defines the formula
    under `§1.3.1` / `§1.3.2` — those are descendants of §1.3, NOT misplaced.
    A genuine misplacement (book §1.4 but summary §1.3, or book §1.3.5 but
    summary §1.3.2) shares no prefix and is still flagged."""
    try:
        ca = [int(x) for x in a.split('.')]
        cb = [int(x) for x in b.split('.')]
    except ValueError:
        return a == b
    if not ca or not cb:
        return a == b
    short, long = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
    return short == long[:len(short)]


def _compute_order_and_section(tags_sec: List[tuple], src: 'SourceFormulaIndex',
                                 ignore: Optional[Set[str]] = None,
                                 reset_on_section: bool = True) -> tuple:
    """Derive ORDER_MISMATCH + MISPLACED (both WARN, non-blocking) from the
    same data Q already has — no three-stage manifest pipeline needed.

    * ORDER_MISMATCH: for formula numbers present in BOTH the summary and the
      book-source set, the summary's document order must follow the book's
      reading order (primary occurrence position).  Any inversion is flagged.
      When ``reset_on_section`` is True (per-section-restart books, scope==3)
      the order window resets on each new ``## §N.M`` so the repeated numbers
      across sections don't false-positive; when False (chapter / book scope,
      globally-unique numbers) the window spans sections so cross-section
      inversions are also caught.
    * MISPLACED: a summary formula's enclosing ``## §N.M`` section must equal
      the book-source formula's definition section (``book_section``).

    Returns ``(om_list, mp_list)``; each row:
        ``{'number', 'status', 'summary_latex'(<=60), 'source_text': ''}``.

    Only numbers actually extracted from the book source are considered
    (FABRICATED / MISSING are reported by the existing compare functions and
    are never double-counted here).
    """
    ignore = set(ignore or set())
    om: List[Dict[str, str]] = []
    mp: List[Dict[str, str]] = []
    seen_om: Set[str] = set()
    seen_mp: Set[str] = set()

    union = src.source_numbers()
    prev_sec = None
    prev_pos = None
    for sec, t in tags_sec:
        if not t.normalized or t.normalized in ignore:
            continue
        n = t.normalized
        if n not in union:
            continue  # FABRICATED handled elsewhere; skip here
        # ORDER-window reset on summary-section change (only for per-section
        # restart books, where numbers repeat across sections).
        if reset_on_section and sec != prev_sec:
            prev_pos = None
        prev_sec = sec
        # ORDER_MISMATCH: summary lists n AFTER a formula whose book position is
        # later than n's -> the sequence got offset / shuffled.
        cur = src.primary_pos(n)
        if cur is not None and prev_pos is not None and cur < prev_pos:
            if n not in seen_om:
                seen_om.add(n)
                om.append({
                    'number': n,
                    'status': 'ORDER_MISMATCH',
                    'summary_latex': t.latex[:60],
                    'source_text': '',
                })
        if cur is not None:
            prev_pos = cur
        # MISPLACED: summary section != book definition section.
        # For per-section-restart numbering (scope==3) the global
        # `book_section` only records the FIRST occurrence of `n` across the
        # whole chapter (every section repeats (1)..(N)), so comparing it to the
        # summary's section produces 10 false MISPLACED.  Use the per-(sec, n)
        # membership instead: a `\tag{n}` is correctly placed iff the book source
        # actually carries `(n)` inside `sec`.  Fall back to the global
        # `book_section` only when per-section tracking recorded nothing (e.g.
        # chapter-scope books where a number is globally unique).
        if (sec, n) in src._book_section_sec:
            bsec = src._book_section_sec[(sec, n)]
        else:
            bsec = src.book_section(n)
        if bsec is not None and not _section_prefix_compatible(bsec, sec):
            if n not in seen_mp:
                seen_mp.add(n)
                mp.append({
                    'number': n,
                    'status': 'MISPLACED',
                    'summary_latex': t.latex[:60],
                    'source_text': '',
                })
    return om, mp


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
                    "      \"formula\": {\"type\": <风格码>, \"scope\": 2, "
                    "\"ignore\": []}\n"
                    "    type 已包含编号段数：C.N(如 2.6)→type 4；C.S.N / C.S-N"
                    "(如 11.1-1)→type 3；单分量 (N)→type 1。\n"
                    "    scope 默认 2（章级编号，开启跨章守卫）；全局编号书用 1。\n"
                    "    不确定段数时，先扫该书 page_*.json 的 text[] 实测公式标签。",
                    file=sys.stderr,
                )
            return LayerResult(code='Q', metadata=dict(_EMPTY_Q))

        formula = ctx.config.formula
        ftype = formula.get('type')
        # `depth` is DERIVED from `type` via ORDINAL_DEPTH — it is NOT read from
        # the config (any stale `depth` key is ignored on purpose).
        fignore = set(formula.get('ignore') or [])
        fkeep = formula.get('keep_cross_refs', True)
        scope = formula.get('scope', 2)
        # Per-section formula numbering (Kreyszig: every section restarts at
        # (1)).  FABRICATED/INCONSISTENT are checked section-locally; the
        # chapter-prefix cross-chapter guard is OFF.
        section_scoped = (scope == 3)
        # Cross-chapter guard (first component == current chapter) is ON iff
        # scope == 2 (chapter-level numbering); book/section scope disables it.
        chapter_prefix = (scope == 2)
        ncomp = _DEFAULT_DEPTH_BY_TYPE.get(ftype, 3)
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
                src = SourceFormulaIndex(ctx.ext_dir, patterns, False, fignore,
                                          keep_cross_refs=fkeep)
                built = src.build_sectioned(ctx.ch, ctx.start, ctx.end,
                                            md_sections, ncomp=ncomp)
                src_sec = built['_sectioned']
                union = built['_union']
                fab, inc, miss, rows = _compare_sectioned(
                    tags_sec, src_sec, md_sections, union, fignore, src)
                om, mp = _compute_order_and_section(
                    tags_sec, src, fignore, reset_on_section=True)
                # RESERVED letter/Roman-led: same BLOCKING probe as the chapter
                # path — a letter-led book must not silently pass via section
                # scope either.
                _ll_sec = _detect_letter_led_formulas(ctx.ext_dir, ctx.start, ctx.end)
                ll_note_sec = _letter_led_note(_ll_sec)
                if ll_note_sec is not None:
                    print(f"[Q-LAYER LETTER-LED *WARN*] {ll_note_sec}",
                          file=sys.stderr)
                return LayerResult(code='Q', metadata={
                    'q_checked': True,
                    'q_fabricated': fab,
                    'q_inconsistent': inc,
                    'q_missing': miss,
                    'q_order_mismatch': om,
                    'q_misplaced': mp,
                    'q_letter_led': [ll_note_sec] if ll_note_sec is not None else [],
                    'q_rows': rows,
                })

        tags = _extract_summary_tags(ctx.md_file)
        src = SourceFormulaIndex(ctx.ext_dir, patterns, chapter_prefix, fignore,
                                 ncomp=ncomp, keep_cross_refs=fkeep)
        src.build(ctx.ch, ctx.start, ctx.end)

        # RESERVED: letter / Roman-led formula numbering (e.g. (A.3)/(I.2)).
        # norm()/patterns are digit-led, so such numbering is NEVER validated by
        # the Q layer.  Whenever the book source actually contains letter-led
        # formula numbers — regardless of whether S is empty — surface a BLOCKING
        # FAIL (via q_letter_led): the verification is incomplete and must not
        # pass until the supporting logic lands.  This is the "implement the
        # logic before this book can validate" guarantee that prevents the
        # false-green case (prose like "3.1 Theorem" can populate S with
        # digit-led numbers while the letter-led ones stay silently un-validated).
        _ll = _detect_letter_led_formulas(ctx.ext_dir, ctx.start, ctx.end)
        ll_note = _letter_led_note(_ll)
        if ll_note is not None:
            print(f"[Q-LAYER LETTER-LED *WARN*] {ll_note}", file=sys.stderr)

        tags_sec = _extract_summary_tags_sectioned(ctx.md_file)
        om, mp = _compute_order_and_section(
            tags_sec, src, fignore, reset_on_section=False)
        fab, inc, miss, rows = _compare(
            tags, src, ctx.ch, chapter_prefix, fignore, s_empty_note=ll_note)
        return LayerResult(code='Q', metadata={
            'q_checked': True,
            'q_fabricated': fab,
            'q_inconsistent': inc,
            'q_missing': miss,
            'q_order_mismatch': om,
            'q_misplaced': mp,
            'q_letter_led': [ll_note] if ll_note is not None else [],
            'q_rows': rows,
        })
