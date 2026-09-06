# -*- coding: utf-8 -*-
"""scan_long_formulas.py — 检测「显示公式过长 → KaTeX \\tag 被挤离公式」的候选。

通用工具（跨书复用），只读不修改。

🔴 度量口径（2026-09-06 修正，勿退回旧写法）
--------------------------------------------
旧实现是**逐源码行**取 max(vis_len)，这有一个致命缺陷：

    $$                                    ← 一个 aligned 行在源码里被折成 6 行书写
    \\begin{aligned}
    ... \\
    &= \\sum_{m=1}^{\\infty} U^{t}\\phi(x(0))     ← 源行 vis=21
    \\begin{bmatrix} a \\\\ b \\end{bmatrix}              ← 源行 vis=30
    = \\sum \\exp(\\lambda t)\\phi(x(0))           ← 源行 vis=23
    ...
    \\end{aligned}
    \\tag{18.11}
    $$

它量到的"最长源行"只有 39，**远低于阈值 100**，于是肉眼明显过宽的公式被判为合格。
只有恰好写成单行的公式（如 18.20 的 vis=166）才会被抓到——漏报是系统性的。

修正后的口径：
1. **按渲染行测量**：先把 `$$` 块按顶层 `\\\\` 切成渲染行（跳过 `bmatrix`/`cases`
   等嵌套环境内部的分隔符），把被折行的源码拼接回一整行，再逐行量宽。
2. **环境名不再当可见字符**：`\\begin{bmatrix}` 旧算法会残留 `bmatrix`（7 字符×2）。
3. **堆叠结构按竖向取 max、不横向累加**：列向量 `[a; b]` 的渲染宽度是 max(a,b)
   而非 a+b；`\\frac{num}{den}` 同理。（旧算法对矩阵/分式**高估**宽度。）
4. **符号计宽**：`\\sum`/`\\int` 等旧算法整条删掉（计 0，低估），现按 1 个字形计；
   具名算子 `\\exp`/`\\sin` 按其名字长度计；字体/间距命令（`\\mathbf`/`\\,`）计 0。
5. **增加高度维度**：块高 = 各渲染行高之和（含矩阵/分式的竖向展开）。超高块会把
   `\\tag` 推得很远，作为**辅助 WARN**（默认阈值 8 行，不阻断）。

阈值标定（以 Koopman 书为准，用户实际判决锚定）
----------------------------------------------
* 18.20 单行原版：用户判"太长" → 新宽 106
* 18.11 二行版：用户判"太长" → 新宽 71（旧算法 39，漏报）
* 18.20 折行后：新宽 52（合格）／18.11 折行后：新宽 28（合格）
⇒ 默认宽度阈值取 **60**（落在"已折行合格 52"与"未折行超长 71"之间）。
  不同查看器版心不同，用第 2 个位置参数微调。

用法:
    python tools/scan_long_formulas.py <book_dir> [width_threshold] [--height N]
输出:
    控制台按文件汇总命中数 + 最宽公式；明细写 <book>/_extract/long_formula_scan.json
后续: 折行计划请用 tools/wrap_long_formulas.py（只读规划器，不落盘）。
"""
import glob
import json
import os
import re
import sys

# 纯标准库脚本，无 skill 内部依赖

DEFAULT_W = 60      # 渲染行可视宽度阈值（见模块 docstring 标定）
DEFAULT_H = 8       # 块高（渲染行数）辅助 WARN 阈值

TAG = re.compile(r'\\tag\{[^}]*\}')
CMD = re.compile(r'\\(?:[a-zA-Z]+)')
DELIM = re.compile(r'^\s*(?:>\s*)?\$\$\s*$')
BEGIN_RE = re.compile(r'\\begin\s*\{[^}]*\}')
END_RE = re.compile(r'\\end\s*\{[^}]*\}')
BEGIN_CAP_RE = re.compile(r'\\begin\s*\{([^}]*)\}')
FRAC_RE = re.compile(r'\\[dtc]?frac\s*\{')

# 字体/样式命令：只修饰后续字符，不额外占宽
STYLE = {
    'mathbf', 'mathrm', 'mathit', 'mathcal', 'mathbb', 'mathfrak', 'boldsymbol',
    'bm', 'tilde', 'hat', 'bar', 'vec', 'dot', 'ddot', 'overline', 'underline',
    'widehat', 'widetilde', 'rm', 'bf', 'it', 'sf', 'tt', 'em',
    'displaystyle', 'textstyle', 'scriptstyle', 'scriptscriptstyle',
    'limits', 'nolimits', 'left', 'right', 'big', 'Big', 'bigg', 'Bigg',
    'dfrac', 'tfrac', 'cfrac', 'color', 'textcolor', 'nonumber', 'notag',
    'label', 'phantom', 'mathstrut', 'mathopen', 'mathclose', 'mathbin',
    'mathrel', 'mathop', 'substack', 'overbrace', 'underbrace',
}
# 具名算子：渲染为文字，按其名字长度计宽
OPS = {
    'exp', 'log', 'ln', 'lg', 'sin', 'cos', 'tan', 'cot', 'sec', 'csc',
    'arcsin', 'arccos', 'arctan', 'max', 'min', 'sup', 'inf', 'lim', 'det',
    'dim', 'ker', 'arg', 'deg', 'gcd', 'hom', 'Pr', 'tr', 'rank', 'diag',
}
# 间距命令（近似 em）
SPACES = {',': 0.2, ':': 0.3, ';': 0.4, '!': -0.2, ' ': 0.3,
          'quad': 1.0, 'qquad': 2.0, 'enspace': 0.5, 'thinspace': 0.2,
          'medspace': 0.3, 'thickspace': 0.4, 'negthinspace': -0.2}
# 堆叠环境：子行竖向排列 → 宽取 max、高累加
STACK_ENVS = {
    'bmatrix', 'pmatrix', 'matrix', 'vmatrix', 'Vmatrix', 'Bmatrix',
    'smallmatrix', 'array', 'cases', 'dcases', 'rcases', 'subarray',
    'aligned', 'align', 'alignat', 'alignedat', 'gathered', 'gather',
    'split', 'multline', 'eqnarray',
}


# ---------------------------------------------------------------- 宽度/高度
def _read_brace(s, i):
    """s[i] == '{' 时返回 (花括号内内容, 右括号后索引)；否则 (None, i)。"""
    if i >= len(s) or s[i] != '{':
        return None, i
    depth, j = 0, i
    while j < len(s):
        if s[j] == '{':
            depth += 1
        elif s[j] == '}':
            depth -= 1
            if depth == 0:
                return s[i + 1:j], j + 1
        j += 1
    return None, i


def _split_top_rows(s):
    """按顶层 `\\\\` 切行；🔴 跳过多行环境（bmatrix/cases…）内部的 `\\\\`。

    朴素按 `\\\\` 切会把 `\\begin{bmatrix} a \\\\ b \\end{bmatrix}` 里的分隔符也切开，
    使一个渲染行碎成数段、宽度被严重低估。
    """
    rows, cur, i = [], '', 0
    while i < len(s):
        if s.startswith('\\\\', i):
            rows.append(cur)
            cur = ''
            i += 2
            continue
        m = BEGIN_RE.match(s, i)
        if m:
            depth, j, endpos = 0, m.end(), None
            while j < len(s):
                mb = BEGIN_RE.match(s, j)
                me = END_RE.match(s, j)
                if mb:
                    depth += 1
                    j = mb.end()
                    continue
                if me:
                    if depth == 0:
                        endpos = j
                        break
                    depth -= 1
                    j = me.end()
                    continue
                j += 1
            if endpos is not None:
                stop = END_RE.match(s, endpos).end()
                cur += s[i:stop]
                i = stop
                continue
        cur += s[i]
        i += 1
    rows.append(cur)
    return rows


def _find_innermost_env(s):
    """返回最内层 \\begin{env}...\\end{env} 的 (start, end, env, inner)；无则 None。"""
    for m in BEGIN_CAP_RE.finditer(s):
        env = m.group(1)
        depth, i, endpos = 0, m.end(), None
        while i < len(s):
            mb = BEGIN_RE.match(s, i)
            me = END_RE.match(s, i)
            if mb:
                depth += 1
                i = mb.end()
                continue
            if me:
                if depth == 0:
                    endpos = i
                    break
                depth -= 1
                i = me.end()
                continue
            i += 1
        if endpos is None:
            continue
        inner = s[m.end():endpos]
        if BEGIN_RE.search(inner):
            continue  # 非最内层
        return m.start(), END_RE.match(s, endpos).end(), env, inner
    return None


def flat_width(s):
    """无环境、无 frac 的片段的可视宽度（近似字形数）。"""
    total, i = 0.0, 0
    while i < len(s):
        if s[i] == '\\':
            m = re.match(r'\\([a-zA-Z]+)', s[i:])
            if m:
                name = m.group(1)
                if name in STYLE:
                    total += 0
                elif name in OPS:
                    total += len(name)
                elif name in SPACES:
                    total += SPACES[name]
                else:
                    total += 1
                i += m.end()
                continue
            m2 = re.match(r'\\[,:;! ]', s[i:])
            if m2:
                total += SPACES.get(m2.group(0)[1], 0.25)
                i += m2.end()
                continue
            i += 2
            continue
        # `_` / `^` 只是上下标标记，本身不占宽
        if s[i] in '{}&$^_' or s[i].isspace():
            i += 1
            continue
        total += 1
        i += 1
    return total


def _fold(s):
    """递归折叠 frac / 堆叠环境，返回 (width, height_in_rendered_lines)。"""
    s = TAG.sub('', s)
    # 1) \frac{a}{b}：分子分母竖向堆叠 → 宽取 max，高仍算 1 行
    while True:
        m = FRAC_RE.search(s)
        if not m:
            break
        i = m.end() - 1
        a, i = _read_brace(s, i)
        if a is None:
            break
        b, i = _read_brace(s, i)
        if b is None:
            break
        w = max(_fold(a)[0], _fold(b)[0])
        s = s[:m.start()] + ('#' * int(round(w))) + s[i:]
    # 2) 堆叠环境：子行竖向排列 → 宽取 max、高累加
    e = _find_innermost_env(s)
    if e:
        st, en, env, inner = e
        widths, hsum = [], 0
        for r in _split_top_rows(inner):
            rw, rh = _fold(r)
            widths.append(rw)
            hsum += rh
        w = max(widths) if widths else 0.0
        h = max(1, hsum)
        if env not in STACK_ENVS:
            h = 1  # 非堆叠环境（如 \boxed）不计高
        s2 = s[:st] + ('#' * int(round(w))) + s[en:]
        w2, h2 = _fold(s2)
        return w2, max(h, h2)
    return flat_width(s), 1


def row_metrics(row):
    """单个渲染行 → (width, height)。"""
    return _fold(row)


def legacy_vis_len(latex):
    """旧口径（逐源码行、环境名残留、符号计 0）的可视字符数。

    仅为对照/兼容保留。🔴 不要用它判断公式是否过长（系统性漏报）。
    """
    s = TAG.sub('', latex)
    s = CMD.sub('', s)
    s = re.sub(r'[{}]', '', s)
    return len(s.replace('\\', ''))


# ---------------------------------------------------------------- 块切分
def iter_display_blocks(lines):
    """yield $$ 块的内部行列表。"""
    i, n = 0, len(lines)
    while i < n:
        if DELIM.match(lines[i]):
            j, buf = i + 1, []
            while j < n and not DELIM.match(lines[j]):
                buf.append(lines[j])
                j += 1
            if j < n:
                yield buf
                i = j + 1
                continue
        i += 1


def rendered_rows(body):
    """把 $$ 块内容切成【渲染行】：先剥离 \\tag，按顶层 \\\\ 切分（跳过嵌套环境
    内部的分隔符），再把被折行的源码拼接回一整行。"""
    s = TAG.sub('', body).strip()
    if not s:
        return []
    m = re.match(r'^\\begin\{([^}]*)\}(.*)\\end\{\1\}$', s, re.S)
    inner = m.group(2) if (m and m.group(1) in STACK_ENVS) else s
    out = []
    for r in _split_top_rows(inner):
        joined = ' '.join(x.strip() for x in r.split('\n') if x.strip())
        if joined:
            out.append(joined)
    return out or [s]


# ---------------------------------------------------------------- 扫描
def scan(book, thresh_w=DEFAULT_W, thresh_h=DEFAULT_H):
    out = {}
    for fp in sorted(glob.glob(os.path.join(book, '*.md'))):
        lines = open(fp, encoding='utf-8').read().split('\n')
        name = os.path.basename(fp)
        hits = []
        for buf in iter_display_blocks(lines):
            body = '\n'.join(buf)
            tm = re.search(r'\\tag\{([^}]+)\}', body)
            if not tm:
                continue
            rows = rendered_rows(body)
            if not rows:
                continue
            w = h = 0.0
            for r in rows:
                rw, rh = row_metrics(r)
                w = max(w, rw)
                h += rh
            # 旧口径（逐源码行），仅供对照
            legacy = 0
            for ln in buf:
                t = TAG.sub('', ln).rstrip()
                if t.strip():
                    legacy = max(legacy, legacy_vis_len(t))
            if w > thresh_w or h > thresh_h:
                hits.append({'tag': tm.group(1), 'width': round(w, 1),
                             'height': int(h), 'rows': len(rows),
                             'legacy_row_chars': legacy})
        if hits:
            out[name] = hits
    return out


def main():
    argv = [a for a in sys.argv[1:]]
    height = DEFAULT_H
    if '--height' in argv:
        k = argv.index('--height')
        height = int(argv[k + 1])
        del argv[k:k + 2]
    if not argv:
        print(__doc__)
        return 2
    book = argv[0]
    thresh = int(argv[1]) if len(argv) > 1 else DEFAULT_W

    res = scan(book, thresh, height)
    tot = sum(len(v) for v in res.values())
    only_tall = sum(1 for v in res.values()
                    for x in v if x['width'] <= thresh)
    print('THRESHOLD 宽度=%d 高度=%d | files=%d | flagged=%d (其中仅超高 %d)'
          % (thresh, height, len(res), tot, only_tall))
    for name in sorted(res, key=lambda k: -len(res[k])):
        tags = sorted(res[name], key=lambda x: -x['width'])
        top = ', '.join('%s(w%.0f/h%d)' % (t['tag'], t['width'], t['height'])
                        for t in tags[:6])
        print('  %-64s %3d   e.g. %s' % (name, len(tags), top))
    ext = os.path.join(book, '_extract')
    os.makedirs(ext, exist_ok=True)
    jp = os.path.join(ext, 'long_formula_scan.json')
    with open(jp, 'w', encoding='utf-8') as f:
        json.dump({'threshold_width': thresh, 'threshold_height': height,
                   'files': res}, f, ensure_ascii=False, indent=1)
    print('written:', jp)


if __name__ == '__main__':
    main()
