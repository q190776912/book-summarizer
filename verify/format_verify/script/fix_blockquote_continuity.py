"""fix_blockquote_continuity.py — G-LAYER (code 'G', fix_order 5) auto-fix.

Separation of concerns: DETECTION logic (check_g_*) lives in
format_verify.py; this module holds ONLY the auto-fix logic.  The G-LAYER
owns the whole blockquote-continuity family (per format_verify.py's
docstring: "blockquote_continuity -> quote-block continuity / nested /
example-proof gap").  So this single fixer repairs ALL of:

  * bare blank lines inside blockquotes  -> `> `   (quote_gaps)
  * orphan bare `>` lines                -> removed (quote_gaps)
  * nested blockquotes `> > **`          -> `> **`  (nested_bq)
  * example + proof not in one blockquote-> merged  (ex_proof_gaps)
  * same-line `> **例…**…**证明…**`       -> split   (ex_proof_gaps same-line form)

All sub-fixes are idempotent and run in one in-memory pass + single write.
Self-registers via register_fixer('G', 5, apply_fix).
Fix-dict key: {g}.
"""
import os
import sys
import re
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

from verify.script.base import LayerFixResult, register_fixer
from lib.regexlib import G_HEAD
from format_verify import G_TERM
from verify.script.struct_labels import G_PF_RE

# Broad example-head match for the MERGE step: covers `> **例**`, `> **例2.1-1**`
# (no space, the legacy bq_core.merge_example_block format), `> **例 2.1-1**`
# (space) and `> **Example 1.2**`.  Slightly broader than the detector's
# G_EX_RE (which requires a word boundary after `例` and thus misses
# `例2.1-1`) so the fix also resolves the legacy numeric example heads.
_EX_HEAD_RE = re.compile(r'> \*\*(?:例[^*]*?|Example\b[^*]*?)\*\*')


# ---------------------------------------------------------------------------
# (1) blockquote continuity: convert intra-block bare blanks to `> `,
#     drop trailing/orphan empty blockquote lines.  Built as a NEW list
#     (not in-place) so orphan removal truly DELETES the line instead of
#     leaving a blank that the next pass would re-convert to `> ` (which
#     caused an idempotency oscillation).
# ---------------------------------------------------------------------------
def _near_bq_content(lines, i, direction):
    """Return True if the nearest non-blank line in `direction` (+1 / -1)
    is a `>` line that carries real content (not itself `>` / `> `).
    A top-level line (incl. terminators) is NOT blockquote content."""
    k = i + direction
    while 0 <= k < len(lines) and lines[k].strip() == '':
        k += direction
    if not (0 <= k < len(lines)):
        return False
    lk = lines[k]
    if lk.lstrip().startswith('>'):
        return lk.strip() not in ('>', '> ')
    return False


def _fix_quote_gaps(lines):
    """Fix blockquote continuity on a list of lines.  Rules (all deletion-based,
    so the result is stable across repeated passes):

      * bare blank inside a blockquote, next non-blank is a `>` line
        -> convert to `> ` (maintain continuity)
      * bare blank inside a blockquote, next non-blank is a block head
        (`> **证明/例`) or a terminator (`---` / `## ` / top `**label**`)
        -> keep (legitimate inter-block / pre-separator blank)
      * bare blank inside a blockquote, next non-blank is top-level text
        or EOF -> DROP (trailing blank, not a real separator)
      * explicit empty blockquote line (`>` / `> `) that is NOT between two
        blockquote-content lines -> DROP (orphan / leading / trailing)

    Returns (new_lines, n_changes)."""
    n = len(lines)
    # per-line in_block, computed on the ORIGINAL lines (forward scan).
    # A blockquote (in the CommonMark sense) is open for ANY `>` content
    # line -- including NESTED ones (`> > **例**`) that G_HEAD does NOT match.
    # Opening only on G_HEAD previously left the trailing blank after a
    # nested block un-dropped on pass 1 (it gets dropped only after flatten
    # turns `> >` into `>` on pass 2) -> a 1-pass-late oscillation. So we
    # open/continue the block on every real `>` content line, and close it on
    # a terminator or a top-level non-`>` line.  Empty `>` / `> ` lines keep
    # the current state (handled separately below).
    in_block = [False] * n
    cur = False
    for i in range(n):
        ln = lines[i]
        s = ln.strip()
        if ln.lstrip().startswith('>') and s not in ('>', '> '):
            cur = True                       # any real blockquote content line
        elif ln.lstrip().startswith('>') and s in ('>', '> '):
            pass                             # keep current state
        elif G_TERM.match(ln) and not ln.lstrip().startswith('>'):
            cur = False
        elif s and not ln.lstrip().startswith('>'):
            cur = False                      # top-level content closes block
        in_block[i] = cur

    out = []
    changes = 0
    for i in range(n):
        ln = lines[i]
        stripped = ln.strip()
        if in_block[i] and stripped == '' and not ln.startswith('>'):
            # bare blank inside a blockquote
            j = i + 1
            while j < n and lines[j].strip() == '':
                j += 1
            if j >= n:
                changes += 1          # trailing blank at EOF -> drop
                continue
            nx = lines[j]
            is_newblock = bool(G_HEAD.match(nx))
            is_term = bool(G_TERM.match(nx) and not nx.lstrip().startswith('>'))
            if is_newblock or is_term:
                out.append(ln)       # keep as legitimate separator
            elif nx.lstrip().startswith('>'):
                if ln != '> ':
                    changes += 1
                out.append('> ')      # maintain continuity
            else:
                changes += 1          # next is top-level text -> drop (trailing)
                continue
        elif in_block[i] and stripped in ('>', '> '):
            # explicit empty blockquote line: keep only between two bq contents
            if _near_bq_content(lines, i, -1) and _near_bq_content(lines, i, +1):
                out.append(ln)        # intra-block empty line (allowed)
            else:
                changes += 1          # orphan / leading / trailing -> drop
                continue
        else:
            out.append(ln)
    return out, changes


# ---------------------------------------------------------------------------
# (2) flatten nested blockquotes  > > **  ->  > **
# ---------------------------------------------------------------------------
def _flatten_nested(lines):
    """Flatten any run of leading `>` on a line to a single `> `.
    Returns (lines, n_changed). Idempotent."""
    changes = 0
    for i, ln in enumerate(lines):
        new = re.sub(r'^(?:\s*>\s*)+', '> ', ln)
        if new != ln:
            lines[i] = new
            changes += 1
    return lines, changes


# ---------------------------------------------------------------------------
# (3) merge `> **例**` with its following `> **证明思路/证明/证明梗概/证明概要**`
#     into ONE contiguous blockquote (eliminates gaps that break the block).
# ---------------------------------------------------------------------------
def _merge_example_proof(text):
    """Merge an example block with its proof sketch into a single blockquote.
    Mirrors the legacy bq_core.merge_example_block, but uses the SAME
    G_EX_RE / G_PF_RE the detector uses so the fix resolves exactly the
    violations check_example_proof_gap reports.

    IDENTITY-SAFE: a merge is performed ONLY when there is a real GAP between
    the example head and its proof (a bare blank line, or a non-`>` line).  If
    the example head and proof are already in one contiguous `>` block (no
    gap), nothing is touched and n_merged stays 0 -- this keeps the fixer
    idempotent (an already-merged block must not be "merged" again on the next
    pass).  Returns (text, n_merged)."""
    lines = text.split('\n')
    result = list(lines)
    i = 0
    merged = 0
    while i < len(result):
        if not _EX_HEAD_RE.match(result[i]):
            i += 1
            continue
        # find the proof line within the next 25 lines, without another
        # example / structural interrupt / heading / `---` between.
        proof_idx = None
        has_gap = False
        for j in range(i + 1, min(i + 25, len(result))):
            if G_PF_RE.match(result[j]):
                mid = result[i+1:j]
                if any(_EX_HEAD_RE.match(l) for l in mid):
                    break
                if any(re.match(r'^#{1,6}\s', l) for l in mid):
                    break
                if any(re.match(r'^\*\*(?:定义|定理|引理|推论|命题|断言)\b', l) for l in mid):
                    break
                if any(re.match(r'^---\s*$', l) for l in mid):
                    break
                # real gap = a bare blank OR a non-`>` line between them.
                # (An intra-block `> ` empty line is NOT a gap -- it keeps the
                # blockquote contiguous, so no merge is needed.)
                if any(l.strip() == '' or not l.lstrip().startswith('>') for l in mid):
                    has_gap = True
                proof_idx = j
                break
        if proof_idx is None or not has_gap:
            i += 1
            continue
        # build merged block: drop fully-empty lines, prefix non-> lines with '> '
        new_block = [result[i]]
        for k in range(i + 1, proof_idx):
            ln = result[k]
            if ln.strip() == '':
                continue
            if ln.startswith('> '):
                new_block.append(ln)
            elif ln == '>':
                new_block.append(ln)
            else:
                new_block.append('> ' + ln)
        new_block.append(result[proof_idx])
        result[i:proof_idx + 1] = new_block
        merged += 1
        i += len(new_block)
    if merged:
        return '\n'.join(result), merged
    return text, 0


# ---------------------------------------------------------------------------
# (4) split same-line example+proof  > **例…**…**证明…**  ->  two `>` lines
# ---------------------------------------------------------------------------
_SAME_LINE_EX_PROOF_RE = re.compile(
    r'^(> \*\*例(?:\d[\d.]*-[0-9]+|\d+)?\*\*[^>]*?)'
    r'(\*\*(?:证明思路|证明|证明梗概|证明概要)\*\*[^>]*)$'
)

def _split_inline_ex_proof(text):
    """Split a line that carries both an example head and a proof head into
    two separate `>` lines. Returns (text, n_split). Idempotent."""
    lines = text.split('\n')
    out = []
    split = 0
    for ln in lines:
        m = _SAME_LINE_EX_PROOF_RE.match(ln)
        if m:
            split += 1
            out.append(m.group(1).rstrip())
            out.append('> ' + m.group(2))
        else:
            out.append(ln)
    if split:
        return '\n'.join(out), split
    return text, 0


def apply_fix(ctx) -> LayerFixResult:
    """Run the full G auto-fix and return the byte-compatible fix dict {g}."""
    md = ctx.md_file
    try:
        with open(md, encoding='utf-8') as f:
            text = f.read()
    except Exception:
        return LayerFixResult(fix_dict={'g': 0})
    total = 0
    lines = text.split('\n')
    lines, c1 = _fix_quote_gaps(lines); total += c1
    lines, c2 = _flatten_nested(lines); total += c2
    text = '\n'.join(lines)
    text, c3 = _merge_example_proof(text); total += c3
    text, c4 = _split_inline_ex_proof(text); total += c4
    if total > 0:
        with open(md, 'w', encoding='utf-8') as f:
            f.write(text)
    return LayerFixResult(fix_dict={'g': total})


register_fixer('G', 5, apply_fix)
