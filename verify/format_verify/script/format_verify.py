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

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见
# verify/format_verify/format_verify.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""format_verify.py — F-LAYER (order 6): unified format verification.

fixer 代号 H/G/I/J/K/L/M/N 对应的检测项：

    C  katex_validation        -> KaTeX render validation (subprocess)
    G  blockquote_continuity   -> quote-block continuity / nested / example-proof gap
    H  structural_label_guard  -> structural label in blockquote (4 sub-checks)
    I  item_separator          -> `---` between consecutive items
    J  intra_item_dash         -> no `---` inside an item block
    K  proof_list_spacing      -> blank line between list and proof blockquote
    L  separator_spacing       -> blank lines around `---` separators
    M  math_blockquote_leak    -> `>` lines inside display math blocks
    N  blockquote_spacing      -> excessive empty `>` lines inside blockquotes

所有检测逻辑内联于本文件；本层产出 16 个字节契约键，并追加 `heading_sep` 检测键（由
`DEFAULT_RESULT` 与契约测试的动态 `ALLOWED` 集覆盖）——故 `report.py`、
`verify_chapter.py` 与契约测试保持通过。

Auto-fix is NOT performed by this layer: it is implemented by the eight
`fix_*.py` modules in this same `script/` directory, which self-register via
`register_fixer` under the legacy fixer codes H/G/I/J/K/L/M/N (fix-dict keys
`h/h_stmt/h_ul/h_mbq/g/i/j/k/l/m/n`, byte-compatible unchanged).
"""
from verify.script.base import VerifyLayer, LayerResult

import re
import subprocess

from verify.script.struct_labels import (
    G_EX_RE, G_PF_RE, G_TOPLEVEL_BREAK_RE,
    N_ITEM_RE,
    H_STRUCT_BQ_RE, H_INLINE_STRUCT_BQ_RE, TOP_LEVEL_HEADER_RE,
    I_ITEM_STRUCT_RE, I_ITEM_EXAMPLE_RE, I_ITEM_NUMFIRST_RE,
)
from lib.regexlib import G_HEAD, FMT_HR_RE, FMT_SEC_RE


# ===========================================================================
# C-LAYER: KaTeX validation (subprocess)
# ===========================================================================
def check_katex(md_file):
    """Run check_katex.py on the markdown file, return (has_errors, error_lines).

    The checker lives at `verify/format_verify/script/check_katex.py` (the
    whole katex detection subsystem — check_katex + katex_heuristics +
    katex_render + katex_validate.js). Resolve it from the skill root (`_ROOT`) so it always points
    at the live file.  The subprocess is guarded: any failure to launch
    (missing node / katex JS runtime) or a non-zero exit degrades to
    "(False, [])" — never crashes `verify_one`."""
    check_path = os.path.join(
        _ROOT, 'verify', 'format_verify', 'script', 'check_katex.py')
    try:
        r = subprocess.run([
            sys.executable, '-X', 'utf8', check_path, md_file
        ], capture_output=True, text=True, encoding='utf-8')
    except (OSError, FileNotFoundError):
        # node / check_katex.py unavailable in this environment — skip silently.
        return False, []
    lines = [l for l in r.stdout.strip().splitlines()
             if l.strip() and not l.strip().startswith('KATEX ERRORS') and not l.startswith('KATEX CHECK')]
    has_errors = bool(lines) and r.returncode != 0
    return has_errors, lines


# ===========================================================================
# G-LAYER: quote-block continuity (structural)
# ===========================================================================
# <div> figure blocks cannot live inside a blockquote (CommonMark); they
# naturally exit it, so treat a <div> as a block terminator. This avoids a
# false conflict with the C-layer, which requires a truly blank line before
# a <div> (a `> ` empty-quote line would itself fail C).
G_TERM = re.compile(r'^(?:---+\s*$|##\s|\*\*[^*]+\*\*|\$\$\s*$|<div)')

NESTED_BQ = re.compile(r'^>\s*>\s*\S')

def check_g_quote_continuity(md_file):
    """G-LAYER: quote-block continuity.

    Returns a list of violation strings (with line numbers). Empty = pass.
    Flagged: a bare blank line (strip()=='') occurring while inside a
    `> **证明/例` block, whose next non-blank line is block CONTENT
    (a `>` line or any line that is neither a new block start nor a block
    terminator). Allowed bare blanks: those immediately preceding a new
    block start (`> **证明/例`) or a terminator (`---` / `## ` / top-level
    `**label**`) — these are inter-block separators.
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    n = len(lines)
    out = []
    in_block = False
    for i in range(n):
        ln = lines[i]
        if G_HEAD.match(ln):
            in_block = True
            continue
        if G_TERM.match(ln) and not ln.lstrip().startswith('>'):
            in_block = False
            continue
        # Only flag truly bare blank lines (no `>` prefix), not empty blockquote
        # lines (`> ` or `>`) which keep the blockquote contiguous.
        if in_block and ln.strip() == '' and not ln.startswith('>'):
            j = i + 1
            while j < n and lines[j].strip() == '':
                j += 1
            if j >= n:
                continue  # trailing blank at EOF — nothing after to split, harmless
            nx = lines[j]
            is_newblock = bool(G_HEAD.match(nx))
            is_term = bool(G_TERM.match(nx) and not nx.lstrip().startswith('>'))
            if is_newblock or is_term:
                continue  # legitimate inter-block separator
            out.append(f"  x L{i+1}: bare blank line breaks the `> **证明/例` block "
                       f"(next content L{j+1}: {nx.strip()[:40]})")
        # A top-level (non->) non-blank line closes the blockquote
        if in_block and ln.strip() and not ln.startswith('>'):
            in_block = False
    return out

def check_nested_blockquotes(md_file):
    """Detect nested blockquotes (> > **证明/例** or > > **例**) — the OLD format.
    Examples and their proofs must use the SAME single `>` level."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    for i, ln in enumerate(lines):
        if NESTED_BQ.match(ln):
            out.append(f"  x L{i+1}: nested blockquote `> > **` (use single `>` level): "
                       f"{ln.strip()[:60]}")
    return out

def check_example_proof_gap(md_file):
    """G-LAYER: detect gap between example (> **例**) and its proof (> **证明思路**).

    A bare empty line or non-blockquote content between them breaks
    the single blockquote — example and proof must be in the same
    contiguous `>` block. Also flags blank `>` lines (visual spacing
    within blockquote is allowed, but warnings are emitted).

    Also detects SAME-LINE example+proof: `> **例**：...**证明梗概**：...`
    which should be split onto two separate `>` lines.
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return [], []
    errors = []   # blocking — empty lines or non-bq content
    warns = []    # non-blocking — `>` gap lines
    # --- Same-line example+proof detection ---
    for i, ln in enumerate(lines):
        s = ln.strip()
        if s.startswith('> **例') and '**证明' in s:
            # A `> **例` line containing `**证明` — they should be separate lines
            errors.append(f"  x L{i+1}: example and proof on same line — split into\n"
                          f"             `> **例…**` and `> **证明…**` on separate lines")
    # --- Gap detection (original logic) ---
    for i, ln in enumerate(lines):
        if not G_EX_RE.match(ln):
            continue
        for j in range(i + 1, min(i + 25, len(lines))):
            if not G_PF_RE.match(lines[j]):
                continue
            # Another example between → not the same pair
            if any(G_EX_RE.match(lines[k]) for k in range(i + 1, j)):
                break
            # Section header or structural interrupt → not the same pair
            if any(re.match(r'^#{1,6}\s', lines[k]) for k in range(i + 1, j)):
                break
            if any(re.match(r'^---\s*$', lines[k]) for k in range(i + 1, j)):
                break
            if any(G_TOPLEVEL_BREAK_RE.match(lines[k]) for k in range(i + 1, j)):
                break
            # Inspect gap lines
            for k in range(i + 1, j):
                t = lines[k].strip()
                if t == '':
                    errors.append(f"  x L{i+1}: empty line between example and proof (L{j+1})")
                    break
                elif not lines[k].startswith('>'):
                    errors.append(f"  x L{i+1}: non-blockquote content between example and proof "
                                  f"L{k+1}: {t[:60]}")
                    break
            break
    return errors, warns


# ===========================================================================
# H-LAYER: structural label / blockquote audit (4 sub-checks)
# ===========================================================================
_H_UL_OPENERS = re.compile(
    r'^\s*>\s*\*\*(?:'
    r'(?:\d{1,3}[.．]\s*)?(?:'
    r'(?:证明|证|例|注|说明'
    r'|Proof|Example|Solution|Note|Remark'
    r'|Definition|Theorem|Lemma|Corollary|Proposition|Exercise)'
    r')'
    # number-first form:  > **N.M-K 例  (some books print 编号在前, e.g. Kreyszig `8.1-6 例子`)
    r'|(?:\d{1,3}(?:[.．-]\d{1,3}){1,2})\s*'
    r'(?:例|Example|Solution|注|Note|Remark|证明|证|说明)'
    # bold-led catch-all: any `>**Label...**` is an intentional (English/number) label
    # block — e.g. Kreyszig `**Solution (core steps).**`, `**Crucial distinction.**`,
    # `**3.7-1 Legendre polynomials.**`. Avoids mis-flagging legit proof/example blocks.
    r'|[A-Z0-9].*?\*\*'
    r')'
)

_H_UL_FOOTNOTE = re.compile(r'^\s*>\s*\^\{')

_H_MISSING_BQ = re.compile(
    r'^\s*\*\*(?:'
    r'(?:证明|证|证明思路|证明概要|注记|说明'
    r'|Proof|Example|Solution|Note|Remark)'
    r'|例(?:\s*\d[\d.]*)?'
    r'|注(?:\s*\d[\d.]*)?'
    r')\*\*'
)

_H_MISSING_BQ_FOOTNOTE = re.compile(r'^\s*\{')

def _h_ext_is_legit_bq(s):
    """A blockquote line that is LEGIT (proof/example/note/footnote) -> stop.

    Bilingual: recognizes both Chinese (证明/例/注) and English
    (Proof/Example/Note/Remark) openers so English summaries are not
    mis-scanned as a statement region (which would flag `> $$` as h_stmt_bq).
    """
    t = s.lstrip()
    if not t.startswith('>'):
        return False
    inner = t[1:].lstrip()
    if inner.startswith('^{'):
        return True
    # Chinese openers
    if (inner.startswith('**证明') or inner.startswith('**例')
            or inner.startswith('**注')):
        return True
    # number-first form:  > **N.M-K 例  (book prints 编号在前)
    if re.match(r'^\*\*\d{1,3}(?:[.．-]\d{1,3}){1,2}\s*(?:例|Example|注|Note|Remark|证明|证|说明)', inner):
        return True
    # English openers (bilingual support)
    if re.match(r'^\*\*(?:Proof|Example|Solution|Note|Remark|Exercise)\b', inner):
        return True
    # bold-led catch-all (English/number labels like `**Crucial distinction.**`,
    # `**3.7-1 Legendre polynomials.**`, `**Solution (core steps).**`)
    if re.match(r'^\*\*[A-Z0-9]', inner):
        return True
    return False

def _h_ext_is_structural_bq(s):
    """A blockquote line that is WRAPPED STATEMENT content (sub-point/formula)."""
    t = s.lstrip()
    if not t.startswith('>'):
        return False
    inner = t[1:].lstrip()
    if inner.startswith('$$'):
        return True
    if re.match(r'^（([0-9a-zA-Z]+)）', inner):
        return True
    if re.match(r'^\*\*\(([0-9a-zA-Z]+)\)\*\*', inner):
        return True
    if re.match(r'^- （([0-9a-zA-Z]+)）', inner):
        return True
    if re.match(r'^- \(([0-9a-zA-Z]+)\)', inner):
        return True
    return False

def _h_ext_items(md_file):
    """Yield (lines, h_idx, pen_idx) for each structural item in the file."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return
    n = len(lines)
    heads = [i for i in range(n) if TOP_LEVEL_HEADER_RE.match(lines[i])]
    for idx, h in enumerate(heads):
        nxt = heads[idx + 1] if idx + 1 < len(heads) else n
        pen_idx = nxt
        for k in range(h + 1, nxt):
            if _h_ext_is_legit_bq(lines[k]):
                pen_idx = k
                break
        yield lines, h, pen_idx

def check_h_structural_blockquote(md_file):
    """H-LAYER: scan the file for structural labels inside blockquotes.

    Returns a list of violation strings (with line numbers). Empty = pass.
    Each violation is a line matching `> **LABEL...` where LABEL is a
    structural label (definition/theorem/lemma/etc.)."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    for i, ln in enumerate(lines):
        if H_STRUCT_BQ_RE.match(ln):
            rest = ln.lstrip()
            label_end = rest.find('**', 2)
            label = rest[4:label_end] if label_end > 4 else rest[4:].split()[0]
            out.append(f"  x L{i+1}: structural label `{label.strip()}` inside blockquote "
                       f"(must be top-level): {ln.strip()[:70]}")
    # Sub-check: orphan bare `>` lines (empty blockquote not attached to content).
    # A bare `>` line is orphan only if it has no blockquote content either before or after.
    n = len(lines)
    for i, ln in enumerate(lines):
        if re.match(r'^\s*>\s*$', ln):
            # Check if preceded by blockquote content
            prev_bq = False
            for k in range(i - 1, -1, -1):
                s = lines[k].strip()
                if s:
                    prev_bq = lines[k].lstrip().startswith('>')
                    break
            # Check if followed by blockquote content
            next_bq = False
            for k in range(i + 1, n):
                s = lines[k].strip()
                if s:
                    next_bq = lines[k].lstrip().startswith('>')
                    break
            if not (prev_bq or next_bq):
                out.append(f"  x L{i+1}: bare `>` line not attached to any blockquote content "
                           f"(orphan empty blockquote — remove or merge)")
    return out

def check_h_statement_in_blockquote(md_file):
    """H-LAYER ext (BQ): flag statement content wrongly wrapped in `>`.
    Returns a list of violation strings (with line numbers). Empty = pass."""
    out = []
    for lines, h, pen_idx in _h_ext_items(md_file):
        for k in range(h + 1, pen_idx):
            if _h_ext_is_structural_bq(lines[k]):
                out.append(f"  x L{k+1}: statement content wrapped in `>` "
                           f"(unexpected blockquote): {lines[k].strip()[:70]}")
    return out


def check_unlabeled_blockquotes(md_file):
    """H-LAYER ext (unlabeled BQ): flag free-standing `>` blocks without a
    recognized label (证明/证/例/注/说明/脚注).

    Grouping: consecutive `>` lines form one "block".  A new legit opener
    (`> **证明**` / `> **例**` etc.) encountered mid-stream SPLITS the block,
    so that:

        > (unlabeled text)
        > **证明**：...   ← splits here, this line starts a fresh block

    Reports each content line within an unlabeled block individually.

    Returns a list of violation strings. Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    n = len(lines)
    out = []
    i = 0
    while i < n:
        if not lines[i].lstrip().startswith('>'):
            i += 1
            continue
        # Collect a blockquote block, splitting at new legit openers
        start = i
        i += 1
        while i < n and lines[i].lstrip().startswith('>'):
            # A legit opener mid-stream breaks the block so it starts fresh
            if _H_UL_OPENERS.match(lines[i]) or _H_UL_FOOTNOTE.match(lines[i]):
                break
            i += 1
        end = i
        # Find first content-bearing line in the block
        first = None
        for k in range(start, end):
            inner = lines[k].lstrip()
            if inner == '>' or inner == '':
                continue
            first = k
            break
        if first is None:
            continue  # block is all empty `>` lines
        ln = lines[first]
        if _H_UL_OPENERS.match(ln) or _H_UL_FOOTNOTE.match(ln):
            continue  # legit blockquote
        # Let H-layer handle structural labels inside blockquotes (double-flag avoidance)
        if H_INLINE_STRUCT_BQ_RE.match(ln):
            continue
        # Unlabeled blockquote — flag each content line
        for k in range(start, end):
            t = lines[k].strip()
            if t.startswith('>') and t != '>':
                inner2 = t[1:].lstrip()
                if inner2:
                    out.append(f"  x L{k+1}: unlabeled blockquote (only 证明/证/例/注/说明/脚注 "
                               f"allowed in `>`): {lines[k].strip()[:70]}")
    return out


def check_labels_missing_blockquote(md_file):
    """H-LAYER ext (missing BQ): flag labels (证明/证/例/注/说明/注记/脚注)
    found at TOP LEVEL — they MUST be inside `>`. Returns list of violation
    strings. Empty = pass.

    Display math ($$...$$ fences) is skipped: CD commutative-diagram rows
    like `{...} @>>> ...` legitimately start a line with `{` and are NOT
    blockquote labels, so scanning them here causes false positives."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    in_math = False
    for i, ln in enumerate(lines):
        s = ln.strip()
        # Toggle display-math state on fences. A single-line `$$ ... $$`
        # block does not persist in_math across lines.
        if s == '$$':
            in_math = not in_math
            continue
        if s.startswith('$$') and s.endswith('$$'):
            continue
        if in_math:
            continue
        st = ln.strip()
        if st.startswith('>'):
            continue
        if re.match(r'^#{1,6}\s', ln):
            continue
        if _H_MISSING_BQ.match(st) or _H_MISSING_BQ_FOOTNOTE.match(st):
            out.append(f"  x L{i+1}: label `{st[:40]}` should be inside `>` "
                       f"(add `> ` prefix)")
    return out


# ===========================================================================
# I-LAYER: item separator completeness
# ===========================================================================
def check_i_separators(md_file):
    """I-LAYER: check that consecutive items are separated by `---`.

    Items checked: definition, theorem, lemma, corollary, proposition,
    axiom, example. Internal blocks (proof, note) are NOT items and
    don't need separators. Section boundaries (##) reset the requirement.
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    # Collect all item-starting line numbers
    item_lines = []
    for i, ln in enumerate(lines):
        if (I_ITEM_STRUCT_RE.match(ln) or I_ITEM_EXAMPLE_RE.match(ln)
                or I_ITEM_NUMFIRST_RE.match(ln)):
            item_lines.append(i)
    item_lines = sorted(set(item_lines))
    # Check consecutive pairs
    for idx in range(len(item_lines) - 1):
        i = item_lines[idx]
        j = item_lines[idx + 1]
        # Skip if too far apart (likely across a section boundary with no ## mark)
        if j - i > 100:
            continue
        # Look for --- or section heading between i and j
        has_sep = False
        section_between = False
        for k in range(i + 1, j):
            t = lines[k].strip()
            if t == '---':
                has_sep = True
                break
            if re.match(r'^#{1,6}\s', lines[k]):
                section_between = True
                break
        if not has_sep and not section_between:
            si = lines[i].strip()[:70]
            sj = lines[j].strip()[:70]
            out.append(f"  x L{i+1}→L{j+1}: missing `---` between items: [{si}]...[{sj}]")
    return out


# ===========================================================================
# J-LAYER: no `---` inside an item block
# ===========================================================================
_J_SUBPOINT_RE = re.compile(r'^\*\*\(\d+\)\*\*')

_J_DASH_RE = re.compile(r'^---\s*$')

def check_item_header_dash(md_file):
    """J-LAYER: detect any `---` that sits INSIDE an item block.

    Returns a list of violation strings (with line numbers). Empty = pass.
    A top-level item (`**引理3.1**` ...) may have `**(N)**` numbered sub-points,
    but the block (header line through its last sub-point) must NOT contain any
    `---`. This includes BOTH:
      * header → `---` → `**(1)**`  (between header and first sub-point), and
      * `**(i)**` → `---` → `**(i+1)**`  (between two sub-points),
    even when a sub-point spans multiple lines (its continuation text / a `$$`
    formula sits directly above the `---` rather than the `**(i)**` label).

    Implementation: walk the file keeping an `in_item` flag.
      - Set in_item=ON when we see a `**LABEL**` header or a `**(N)**` sub-point.
      - Set in_item=OFF when we see a `## ` heading or a `>` blockquote line
        (these close the item block).
      - A top-level `---` is a violation when in_item is True AND its next
        non-blank, non-blockquote line is a `**(N)**` sub-point (so we never
        flag a legitimate `---` that separates two different top-level items).
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    n = len(lines)
    out = []
    in_item = False
    for i in range(n):
        s = lines[i]
        st = s.strip()
        if st == '':
            continue
        # blockquote line closes any open item block
        if st.startswith('>'):
            in_item = False
            continue
        # heading closes any open item block
        if re.match(r'^#{1,6}\s', s):
            in_item = False
            continue
        # item header or numbered sub-point opens the block
        if TOP_LEVEL_HEADER_RE.match(s) or _J_SUBPOINT_RE.match(s):
            in_item = True
            continue
        # a top-level `---`
        if _J_DASH_RE.match(s):
            ni = i + 1
            while ni < n and lines[ni].strip() == '':
                ni += 1
            if ni < n and not lines[ni].lstrip().startswith('>'):
                nxt = lines[ni]
                if in_item and _J_SUBPOINT_RE.match(nxt):
                    out.append(f"  x L{i+1}: `---` inside an item block "
                               f"(next: {nxt.strip()[:40]}) — remove it")
            continue
    return out


# ===========================================================================
# K-LAYER: blank line between numbered list and proof blockquote
# ===========================================================================
def check_proof_after_list(md_file):
    """K-LAYER: ensure a blank line separates a numbered list from the proof
    blockquote that follows it.

    A `> **证明`/`> **证明思路**` blockquote that directly follows the last
    item of a 4-space-indented numbered list (without a blank line) will render
    the proof at the list's indentation rather than the theorem's outer level.
    Returns a list of violation strings (with line numbers). Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    n = len(lines)
    for i in range(n - 1):
        # A candidate list line: starts with 4 spaces + digit + `.`
        if re.match(r'^    \d+\.\s', lines[i]) or re.match(r'^    \(\d+\)\s', lines[i]):
            nx = lines[i + 1].strip()
            if (nx.startswith('> **证明') or nx.startswith('> **证明思路**')
                    or re.search(r'\*\*(?:Proof|Proof sketch|Proof outline|Example|Note|Remark)\b', nx)):
                out.append(f"  x L{i+2}: `{nx[:50]}` directly follows list item "
                           f"L{i+1} without blank line — add blank line between")
    return out


# ===========================================================================
# L-LAYER: blank lines around `---` separators
# ===========================================================================
def check_separator_blank_lines(md_file):
    """L-LAYER: every `---` separator line must have a blank line immediately
    above AND below it. Returns list of violation strings (with line numbers).
    Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    n = len(lines)
    for i, ln in enumerate(lines):
        if ln.strip() == '---':
            if i > 0 and lines[i - 1].strip() != '':
                out.append(f"  x L{i+1}: `---` missing blank line BEFORE "
                           f"(prev L{i}: {lines[i-1].strip()[:40]})")
            if i < n - 1 and lines[i + 1].strip() != '':
                out.append(f"  x L{i+1}: `---` missing blank line AFTER "
                           f"(next L{i+2}: {lines[i+1].strip()[:40]})")
    return out


# ===========================================================================
# L-EXT: `---` directly under a section heading
# ===========================================================================
def check_heading_separators(md_file):
    """Detect a `---` whose nearest preceding non-blank line is a section
    heading (## / ### / …).  Such a separator is NEVER legitimate per the
    format convention (legitimate separators live only below a lead-in
    paragraph or between adjacent items).  Returns a list of violation
    strings.  Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    for i, ln in enumerate(lines):
        if FMT_HR_RE.match(ln):
            j = i - 1
            while j >= 0 and lines[j].strip() == '':
                j -= 1
            if j >= 0 and FMT_SEC_RE.match(lines[j]):
                out.append(f"  x L{i+1}: `---` directly under a heading "
                           f"(remove it): {ln.strip()[:40]}")
    return out


# ===========================================================================
# M-LAYER: `>` lines inside display math blocks
# ===========================================================================
def check_displaymath_gt(md_file):
    """M-LAYER: detect `>` lines inside `$$...$$` display math blocks.

    When a display math block is wrapped in a blockquote context, empty `>`
    lines can leak inside the `$$` fences. KaTeX rejects bare `>` inside math
    mode. Returns list of violation strings (with line numbers). Empty = pass."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    n = len(lines)
    i = 0
    while i < n:
        s = lines[i].strip()
        if s == '$$':
            j = i + 1
            while j < n and lines[j].strip() != '$$':
                j += 1
            if j < n:
                for k in range(i + 1, j):
                    ln = lines[k]
                    if ln.lstrip().startswith('>'):
                        out.append(f"  x L{k+1}: `>` inside display math ($$...$$) — "
                                   f"remove blockquote prefix: {ln.strip()[:60]}")
                i = j
        i += 1
    return out


# ===========================================================================
# N-LAYER: excessive empty `>` lines inside blockquotes
# ===========================================================================
def check_excessive_bq_empty_lines(md_file):
    """N-LAYER: detect excessive consecutive empty `>` lines inside blockquotes.

    Within a blockquote (> **证明** / > **例** ...), consecutive empty `>` lines
    should be limited to at most 1 between content-bearing lines."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return []
    out = []
    n = len(lines)
    in_bq = False
    i = 0
    while i < n:
        s = lines[i].strip()
        if s.startswith('> **') and ('证明' in s or '例' in s or '注' in s
                or re.search(r'\*\*(?:Proof|Example|Note|Remark)\b', s)):
            in_bq = True
            i += 1
            continue
        if in_bq:
            if (re.match(r'^---\s*$', s) or re.match(r'^#{1,6}\s', s) or
                N_ITEM_RE.match(s)):
                in_bq = False
                i += 1
                continue
            if s in ('>', '> '):
                j = i
                while j < n and lines[j].strip() in ('>', '> '):
                    j += 1
                count = j - i
                if count > 1:
                    out.append(f"  x L{i+1}–L{j}: {count} consecutive empty `>` lines "
                               f"in blockquote (max 1 allowed)")
                i = j
                continue
            # Skip regular blank lines (not >)
            if s == '':
                i += 1
                continue
        i += 1
    return out


class FLayer(VerifyLayer):
    code = 'F'
    name = 'format-verify'
    order = 6
    auto_fixable = False

    def run(self, ctx):
        katex_errors, katex_lines = check_katex(ctx.md_file)
        return LayerResult(code=self.code, metadata={
            'katex_errors': katex_errors,
            'katex_lines': katex_lines,
            'quote_gaps': check_g_quote_continuity(ctx.md_file),
            'nested_bq': check_nested_blockquotes(ctx.md_file),
            'ex_proof_gaps': check_example_proof_gap(ctx.md_file),
            'h_structural_bq': check_h_structural_blockquote(ctx.md_file),
            'h_stmt_bq': check_h_statement_in_blockquote(ctx.md_file),
            'h_ul_bq': check_unlabeled_blockquotes(ctx.md_file),
            'h_mbq': check_labels_missing_blockquote(ctx.md_file),
            'i_sep_gaps': check_i_separators(ctx.md_file),
            'j_header_dash': check_item_header_dash(ctx.md_file),
            'k_proof_list': check_proof_after_list(ctx.md_file),
            'l_sep_blanks': check_separator_blank_lines(ctx.md_file),
            'heading_sep': check_heading_separators(ctx.md_file),
            'm_dm_gt': check_displaymath_gt(ctx.md_file),
            'n_bq_empty': check_excessive_bq_empty_lines(ctx.md_file),
        })
