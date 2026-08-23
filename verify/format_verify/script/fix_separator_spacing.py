"""fix_separator_spacing.py — L-LAYER (code 'L', fix_order 9) auto-fix.

Owns separator + heading-spacing hygiene:
  * insert blank lines around every `---` missing them  (legacy l_sep_blanks)
  * remove a `---` that sits directly under a section heading (`## `/`###` …),
    which is never a legitimate separator per the format convention
    (legitimate separators are only: below a lead-in paragraph, or between
    adjacent items).  -> heading_sep
  * insert a blank line above every ATX heading missing one
    (heading_blank_above) — a heading directly following a list item /
    paragraph gets absorbed into it by the renderer, indenting the whole
    section instead of rendering flush-left.  Skips file start, ``` / ~~~
    code fences and `$$` math blocks.

The under-heading `---` is removed FIRST, then blank-line spacing is applied
to the remaining separators, then the heading blank-above pass runs LAST so
it sees the settled line stream.  All operations are idempotent.
Self-registers via register_fixer('L', 9, apply_fix).
Fix-dict key: {l} (all three passes counted into the single `l` counter).
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
from lib.regexlib import FMT_HR_RE as HR_RE, FMT_SEC_RE as SEC_RE

_HEADING_ABOVE_RE = re.compile(r'^#{1,6}\s')

_FENCE_RE = re.compile(r'^\s*(?:```|~~~)')


def _remove_heading_seps(lines):
    """Remove `---` whose nearest preceding non-blank line is a section
    heading (## / ### / …).  Returns (lines, n_removed).  Idempotent."""
    out = []
    removed = 0
    for line in lines:
        if HR_RE.match(line):
            j = len(out) - 1
            while j >= 0 and out[j].strip() == '':
                j -= 1
            if j >= 0 and SEC_RE.match(out[j]):
                removed += 1
                continue  # drop this stray separator
        out.append(line)
    if removed:
        # collapse the double blanks left directly under the heading
        text = '\n'.join(out)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.split('\n'), removed
    return lines, 0


def _fix_separator_blank_lines(lines):
    """Insert blank lines above/below every `---` missing them.
    Returns (lines, n_changed)."""
    out = []
    n = len(lines)
    changes = 0
    for i, line in enumerate(lines):
        if line.strip() == '---':
            # Ensure a blank line ABOVE the separator.
            if out and out[-1].strip() != '':
                out.append('')
                changes += 1
            out.append(line)
            # Ensure a blank line BELOW the separator (skip if last line).
            nxt = lines[i + 1] if i + 1 < n else ''
            if nxt.strip() != '':
                out.append('')
                changes += 1
        else:
            out.append(line)
    return out, changes


def _fix_heading_blank_above(lines):
    """Insert a blank line above every ATX heading missing one.
    Skips file start, code fences and `$$` math blocks.
    Returns (lines, n_changed).  Idempotent."""
    out = []
    changes = 0
    in_fence = False
    in_math = False
    for line in lines:
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        if line.strip() == '$$':
            in_math = not in_math
            out.append(line)
            continue
        if in_math:
            out.append(line)
            continue
        # File start (out empty) needs no separator; otherwise require a blank
        # line between the previous block and the heading.
        if _HEADING_ABOVE_RE.match(line) and out and out[-1].strip() != '':
            out.append('')
            changes += 1
        out.append(line)
    return out, changes


def apply_fix(ctx) -> LayerFixResult:
    """Run L auto-fix (remove under-heading `---` first, then blank-line
    spacing on the remaining separators, then heading blank-above last) and
    return the byte-compatible fix dict {l}."""
    md = ctx.md_file
    try:
        with open(md, encoding='utf-8') as f:
            text = f.read()
    except Exception:
        return LayerFixResult(fix_dict={'l': 0})
    lines = text.split('\n')
    lines, c1 = _remove_heading_seps(lines)
    lines, c2 = _fix_separator_blank_lines(lines)
    lines, c3 = _fix_heading_blank_above(lines)
    total = c1 + c2 + c3
    if total > 0:
        with open(md, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return LayerFixResult(fix_dict={'l': total})


register_fixer('L', 9, apply_fix)
