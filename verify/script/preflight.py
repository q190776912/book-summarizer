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


def preflight_md(md_file):
    """Compute the fence/tag invariant triple for one markdown file.

    Returns dict:
      fences       — number of `$$` marks
      balanced     — fences % 2 == 0
      blocks       — number of non-greedy paired $$...$$ spans
      tags_total   — number of \\tag{...} occurrences
      tags_in      — unique tags inside paired blocks
      tags_outside — sorted list of tags NOT inside any paired block
    """
    with open(md_file, encoding='utf-8') as f:
        t = f.read()
    fences = t.count('$$')
    tags_total = _TAG_RE.findall(t)
    in_block = set()
    for m in _BLOCK_RE.finditer(t):
        in_block.update(_TAG_RE.findall(m.group(1)))
    outside = sorted(set(tags_total) - in_block)
    return {
        'file': md_file,
        'fences': fences,
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
        print('[PREFLIGHT]%s %s: fences=%d balanced=%s blocks=%d tags=%d (in=%d%s)'
              % ((' ' + label) if label else '', os.path.basename(fp),
                 pf['fences'], 'YES' if pf['balanced'] else 'NO',
                 pf['blocks'], pf['tags_total'], pf['tags_in'], outside))
        if not pf['balanced']:
            print('  !! 围栏不配对：先修复 $$ 围栏再运行 --fix 或任何块作用域修复'
                  '（步骤见 verify/format_verify/format_verify.md「前置守卫」）')
        elif pf['tags_outside']:
            print('  !! 有 \\tag 落在配对块外（见 OUTSIDE）：先以公式行/\\tag 为锚点'
                  '整体重建公式块（引用块内保留 '> ' 前缀），再跑邻接类 fixer')
    return all_ok
