"""j_layer.py — J-LAYER (order 10, fix_order 7): no `---` inside an item block.

Self-contained implementation (bodies relocated from the deleted structure_layers.py during the per-layer split)."""

from verify.registry import VerifyLayer, LayerResult, LayerFixResult

import re

from verify.layers._struct_labels import TOP_LEVEL_HEADER_RE

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

def fix_item_header_dash(md_file):
    """J-LAYER auto-fix: remove every `---` that sits INSIDE an item block.

    Uses the same `in_item` span-tracker as check_item_header_dash, so it
    catches a `---` between a header and its first `**(N)**` sub-point AND a
    `---` between two `**(i)**`/`**(i+1)**` sub-points, even when a sub-point
    spans multiple lines (continuation text / `$$` formula directly above the
    `---`). Also collapses the single blank immediately after the `---` so the
    parts stay tight (matching the no-`---` style of `**引理3.3**`).
    Returns number of lines removed."""
    try:
        with open(md_file, encoding='utf-8') as f:
            lines = f.read().split('\n')
    except Exception:
        return 0
    n = len(lines)
    remove = set()
    in_item = False
    for i in range(n):
        s = lines[i]
        st = s.strip()
        if st == '':
            continue
        if st.startswith('>'):
            in_item = False
            continue
        if re.match(r'^#{1,6}\s', s):
            in_item = False
            continue
        if TOP_LEVEL_HEADER_RE.match(s) or _J_SUBPOINT_RE.match(s):
            in_item = True
            continue
        if _J_DASH_RE.match(s):
            ni = i + 1
            while ni < n and lines[ni].strip() == '':
                ni += 1
            if ni < n and not lines[ni].lstrip().startswith('>'):
                nxt = lines[ni]
                if in_item and _J_SUBPOINT_RE.match(nxt):
                    remove.add(i)  # the `---`
                    if i + 1 < n and lines[i + 1].strip() == '':
                        remove.add(i + 1)  # the blank line right after the `---`
            continue
    if remove:
        new = [ln for idx, ln in enumerate(lines) if idx not in remove]
        with open(md_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(new))
        return len(remove)
    return 0

class JLayer(VerifyLayer):
    code = 'J'
    order = 10
    fix_order = 7
    auto_fixable = True

    def run(self, ctx):
        return LayerResult(code=self.code, metadata={
            'j_header_dash': check_item_header_dash(ctx.md_file),
        })

    def fix(self, ctx):
        return LayerFixResult(fix_dict={'j': fix_item_header_dash(ctx.md_file)})
