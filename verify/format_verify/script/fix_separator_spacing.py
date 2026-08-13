"""fix_separator_spacing.py — L-LAYER (code 'L', fix_order 9) auto-fix.

Owns separator hygiene:
  * insert blank lines around every `---` missing them  (legacy l_sep_blanks)
  * remove a `---` that sits directly under a section heading (`## `/`###` …),
    which is never a legitimate separator per the format convention
    (legitimate separators are only: below a lead-in paragraph, or between
    adjacent items).  -> heading_sep

The under-heading `---` is removed FIRST, then blank-line spacing is applied
to the remaining separators, so a stray separator under a heading is taken
out rather than merely padded.  Both operations are idempotent.
Self-registers via register_fixer('L', 9, apply_fix).
Fix-dict key: {l}.
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


def apply_fix(ctx) -> LayerFixResult:
    """Run L auto-fix (remove under-heading `---` first, then blank-line
    spacing on the remaining separators) and return the byte-compatible
    fix dict {l}."""
    md = ctx.md_file
    try:
        with open(md, encoding='utf-8') as f:
            text = f.read()
    except Exception:
        return LayerFixResult(fix_dict={'l': 0})
    lines = text.split('\n')
    lines, c1 = _remove_heading_seps(lines)
    lines, c2 = _fix_separator_blank_lines(lines)
    total = c1 + c2
    if total > 0:
        with open(md, 'w', encoding='utf-8') as f:
            f.write('\n'.join(lines))
    return LayerFixResult(fix_dict={'l': total})


register_fixer('L', 9, apply_fix)
