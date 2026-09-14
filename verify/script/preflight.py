"""preflight.py — 围栏/公式块前置检查表（PREFLIGHT，只读不改）。

2026-08《复变函数论 第五版》修复复盘的落地件（机制与事故复盘见
verify/format_verify/format_verify.md「前置守卫与 --preflight」一节）：

  * `$$` 围栏不配对（奇数个 `$$` 标记）时，一切「按块」作用域的判断都不可信
    ——Q 层 `_BLOCK_RE` 为顺序非贪婪配对，一个落单 `$$` 会让其后所有块的
    奇偶归属整体翻转、`\\tag` 全部被挤出块外；邻接启发式 fixer（G 层等）
    此时运行会静默污染正文。
  * 本模块输出三数不变量（fences / blocks / \\tag in-block vs outside）作为
    修复顺序的第 0 步：fences 为偶且 outside 为空，才允许进入块作用域修复。
  * CLI 集成：`verify_chapter.py --preflight ...`（单章或 `--all` 均可，输出
    检查表后退出，不配对时 exit 1）；`--fix` 在 fences 不配对时拒绝运行
    （exit 2），需显式 `--fix-force` 越过。
"""
import os
import re

_TAG_RE = re.compile(r'\\tag\{([^}]+)\}')
_BLOCK_RE = re.compile(r'\$\$(.*?)\$\$', re.S)
_PFX_RE = re.compile(r'^((?:>[ \t]*)*)(.*)$')


def normalize_fences(raw):
    """Fold the two repairable display-fence damage shapes for the invariant.

    * escaped fence  ``\\$\\$`` -> ``$$``   (a regex escape pass hides every
      ``\\tag`` in the block from the non-greedy pairing below);
    * doubled fence  ``$$`` immediately followed by ``$$`` with the same
      blockquote prefix -> a single ``$$`` (an empty display block is never
      legal, and the extra fence shifts the pairing so the body's ``\\tag``
      lands "outside" and the file would be wrongly reported unpaired).

    Returns ``(text, escaped, collapsed)``.  Read-only helper: used only for
    the invariant, so a file blocked for a REAL fence defect still blocks.
    """
    escaped = 0
    collapsed = 0
    out = []
    prev_fence_pfx = None
    for ln in raw.replace('\r\n', '\n').split('\n'):
        m = _PFX_RE.match(ln)
        pfx, core = (m.group(1), m.group(2)) if m else ('', ln)
        if core.strip() == '\\$\\$':
            escaped += 1
            core = core.replace('\\$\\$', '$$')
        if core.strip() == '$$':
            if prev_fence_pfx == pfx:
                collapsed += 1
                continue
            prev_fence_pfx = pfx
        else:
            prev_fence_pfx = None
        out.append(pfx + core)
    return '\n'.join(out), escaped, collapsed


def preflight_md(md_file):
    """Compute the fence/tag invariant triple for one markdown file.

    Returns dict:
      fences       — number of `$$` marks
      escaped      — number of `\\$\\$` marks (escaped fences; repairable)
      collapsed    — doubled adjacent fences folded away (repairable)
      balanced     — fences % 2 == 0
      blocks       — number of non-greedy paired $$...$$ spans
      tags_total   — number of \\tag{...} occurrences
      tags_in      — unique tags inside paired blocks
      tags_outside — sorted list of tags NOT inside any paired block

    Escaped and doubled fences are folded first (see `normalize_fences`) —
    both are damage that `format_verify` Pattern 11 repairs.  Counting them
    raw would report such a file unpaired / with outside `\\tag`s and make the
    guard refuse to run the very fixer that repairs it.
    """
    with open(md_file, encoding='utf-8') as f:
        raw = f.read()
    t, escaped, collapsed = normalize_fences(raw)
    fences = t.count('$$')
    tags_total = _TAG_RE.findall(t)
    in_block = set()
    for m in _BLOCK_RE.finditer(t):
        in_block.update(_TAG_RE.findall(m.group(1)))
    outside = sorted(set(tags_total) - in_block)
    return {
        'file': md_file,
        'fences': fences,
        'escaped': escaped,
        'collapsed': collapsed,
        'balanced': fences % 2 == 0,
        'blocks': len(_BLOCK_RE.findall(t)),
        'tags_total': len(tags_total),
        'tags_in': len(in_block),
        'tags_outside': outside,
    }


def print_preflight(md_files, label=''):
    """Print the preflight checklist for one or more markdown files.

    Returns True when ALL files are fence-balanced (safe to run block-scope
    repair), False otherwise.  Read-only: never modifies any file.
    """
    if isinstance(md_files, str):
        md_files = [md_files]
    all_ok = True
    for fp in md_files:
        pf = preflight_md(fp)
        if not pf['balanced']:
            all_ok = False
        outside = ''
        if pf['tags_outside']:
            shown = ','.join(pf['tags_outside'][:8])
            if len(pf['tags_outside']) > 8:
                shown += ',…'
            outside = '; OUTSIDE=' + shown
        esc = ''
        if pf.get('escaped'):
            esc += ' escaped=%d' % pf['escaped']
        if pf.get('collapsed'):
            esc += ' doubled=%d' % pf['collapsed']
        print('[PREFLIGHT]%s %s: fences=%d balanced=%s blocks=%d tags=%d (in=%d%s)%s'
              % ((' ' + label) if label else '', os.path.basename(fp),
                 pf['fences'], 'YES' if pf['balanced'] else 'NO',
                 pf['blocks'], pf['tags_total'], pf['tags_in'], outside, esc))
        if pf.get('escaped') or pf.get('collapsed'):
            print('  ~~ 围栏损伤（转义 %d / 重复 %d）：已按归一形态计入配对；'
                  'format_verify Pattern 11 会还原为 `$$`'
                  % (pf.get('escaped', 0), pf.get('collapsed', 0)))
        if not pf['balanced']:
            print('  !! 围栏不配对：先修复 $$ 围栏再运行 --fix 或任何块作用域修复'
                  '（步骤见 verify/format_verify/format_verify.md「前置守卫」）')
        elif pf['tags_outside']:
            print('  !! 有 \\tag 落在配对块外（见 OUTSIDE）：先以公式行/\\tag 为锚点'
                  '整体重建公式块（引用块内保留 '> ' 前缀），再跑邻接类 fixer')
    return all_ok
