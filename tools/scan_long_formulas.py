# -*- coding: utf-8 -*-
"""scan_long_formulas.py — 检测「显示公式行过宽 → KaTeX \\tag 与公式重叠」的候选。

通用工具（跨书复用），只读不修改。近似用「可视字符数」代理渲染宽度：
* 去掉 \\tag{..}、\\command 名、花括号/反斜杠后剩的字符数
* 渲染宽度 ≈ 0.5–0.6 em/字符；默认阈值 100 可视字符 ≈ 版心 60–70 em
  （按查看器实际版心用第 2 个参数微调）。

用法:
    python tools/scan_long_formulas.py <book_dir> [threshold_chars]
输出:
    控制台按文件汇总命中数 + 最宽公式；明细写 <book>/_extract/long_formula_scan.json
后续: 折行请用 tools/wrap_long_formulas.py（--dry-run 先看计划）。
"""
import glob
import json
import os
import re
import sys

for _c in [os.path.dirname(os.path.abspath(__file__))]:
    pass  # 纯标准库脚本，无 skill 内部依赖

THRESH = int(sys.argv[2]) if len(sys.argv) > 2 else 100
BOOK = sys.argv[1] if len(sys.argv) > 1 else '.'
EXT = os.path.join(BOOK, '_extract')

DELIM = re.compile(r'^\s*(?:>\s*)?\$\$\s*$')
CMD = re.compile(r'\\(?:[a-zA-Z]+)')
TAG = re.compile(r'\\tag\{[^}]*\}')


def vis_len(latex):
    s = TAG.sub('', latex)
    s = CMD.sub('', s)
    s = re.sub(r'[{}]', '', s)
    s = s.replace('\\', '')
    return len(s)


def iter_display_blocks(lines):
    """yield (start_idx_of_open_$$, inner_lines, end_idx_of_close_$$) for 顶层 $$ 块。"""
    i, n = 0, len(lines)
    while i < n:
        if DELIM.match(lines[i]):
            j = i + 1
            buf = []
            while j < n and not DELIM.match(lines[j]):
                buf.append(lines[j])
                j += 1
            if j < n:
                yield i, buf, j
                i = j + 1
                continue
        i += 1


def scan(book, thresh):
    out = {}
    for fp in sorted(glob.glob(os.path.join(book, '*.md'))):
        lines = open(fp, encoding='utf-8').read().split('\n')
        name = os.path.basename(fp)
        hits = []
        for _o, buf, _c in iter_display_blocks(lines):
            body = '\n'.join(buf)
            tm = re.search(r'\\tag\{([^}]+)\}', body)
            if not tm:
                continue
            tag = tm.group(1)
            m = 0
            for ln in buf:
                t = TAG.sub('', ln).rstrip()
                if t.strip() == '':
                    continue
                v = vis_len(t)
                if v > m:
                    m = v
            if m > thresh:
                hits.append({'tag': tag, 'row_chars': m})
        if hits:
            out[name] = hits
    return out


def main():
    res = scan(BOOK, THRESH)
    tot = sum(len(v) for v in res.values())
    print('THRESHOLD(可视字符) = %d | files = %d | flagged = %d'
          % (THRESH, len(res), tot))
    for name in sorted(res, key=lambda k: -len(res[k])):
        tags = sorted(res[name], key=lambda x: -x['row_chars'])
        top = ', '.join('%s(%d)' % (t['tag'], t['row_chars']) for t in tags[:6])
        print('  %-64s %3d   e.g. %s' % (name, len(tags), top))
    os.makedirs(EXT, exist_ok=True)
    jp = os.path.join(EXT, 'long_formula_scan.json')
    with open(jp, 'w', encoding='utf-8') as f:
        json.dump({'threshold': THRESH, 'files': res}, f,
                  ensure_ascii=False, indent=1)
    print('written:', jp)


if __name__ == '__main__':
    main()
