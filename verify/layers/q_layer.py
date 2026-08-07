# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 references/layers/q.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""q_layer.py — Q-LAYER (order 17): FORMULA SEQUENCE-LABEL audit.

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
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from verify.layers.base import VerifyLayer, LayerResult


# Neutral no-op metadata returned when `formula` is None.  Mirrors the
# DEFAULT_RESULT defaults so report.py / verify_all always see consistent keys.
_EMPTY_Q: Dict[str, object] = {
    'q_checked': False,
    'q_fabricated': [],
    'q_inconsistent': [],
    'q_missing': [],
    'q_rows': [],
}

# Separator characters that any book may use between number components.
_SEP_CLASS = r'[.\-·,]'
# Number token: 2 or 3 components (e.g. 1.17 / 11.1-1 / 3,4), optional trailing
# letter suffix (e.g. 2.3a).
_TAG_RE = re.compile(r'\\tag\{([^}]*)\}')
_BLOCK_RE = re.compile(r'\$\$(.*?)\$\$', re.S)

# ORDINAL style code -> default component count, used when the `formula` map
# supplies `type` but no explicit `depth`.  Mirrors lib.config.ORDINAL_SECTION_TYPES
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
    group = r'(\d+' + (r'[.\-·,]\d+') * (ncomp - 1) + r')'
    return [
        r'[（(]\s*' + group + r'\s*[）)]',   # （1.17） / (1.17)
        r'\bEq\.?\s+' + group,                # Eq. 1.17
        r'\bEquation\s+' + group,             # Equation 1.17
        r'式\s*[（(]?\s*' + group,            # 式（1.17）
        group,                                 # bare 1.17
    ]


@dataclass
class FormulaTag:
    """One `$$...$$` block that carries a `\tag` (or records an empty tag)."""
    latex: str            # the full $$...$$ block
    raw_tag: str          # raw content inside \tag{...}
    normalized: str       # normed number; '' when the block has no usable tag


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
                    data = json.load(f)
            except Exception:
                continue
            for block in data.get('text', []) or []:
                txt = block.get('text', '') if isinstance(block, dict) else ''
                if not txt:
                    continue
                self._scan_text(txt, nums)
        self._by_chapter[ch] = nums

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
                if not n or n in self.ignore:
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
        m = re.match(r'(\d+(?:' + _SEP_CLASS + r'\d+){1,2})([a-zA-Z]?)$', s)
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


class QLayer(VerifyLayer):
    code = 'Q'
    order = 17               # current max layer is P (order 16); Q runs after it
    auto_fixable = False     # audit-only layer; no --fix

    def run(self, ctx) -> LayerResult:
        # GATE: opt-in via the `formula` map.  When absent the layer is a pure
        # no-op so the 16 legacy layers and already-finished books are
        # completely unaffected.
        if ctx.config.formula is None:
            return LayerResult(code='Q', metadata=dict(_EMPTY_Q))

        formula = ctx.config.formula
        ftype = formula.get('type')
        fdepth = formula.get('depth')
        fignore = set(formula.get('ignore') or [])
        scope = formula.get('scope', 2)
        # Cross-chapter guard (first component == current chapter) is ON iff
        # scope == 2 (chapter-level numbering); book/section scope disables it.
        chapter_prefix = (scope == 2)
        ncomp = fdepth or _DEFAULT_DEPTH_BY_TYPE.get(ftype, 3)
        patterns = build_formula_patterns(ncomp)

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
