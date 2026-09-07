# -*- coding: utf-8 -*-
r"""wrap_long_formulas.py — 把「超长显示公式行」折成 aligned 多行，避免 \tag 与公式重叠。

通用工具（跨书复用）。规则见 docs/writing-rules.md「超长显示公式折行」小节。
原则（不改数学语义、不改 \\tag、可重跑）：
* 只在**顶层**（花括号深度 0、圆括号深度 0、不在 \\left..\\right 之间）的二元
  运算符（= + -）处断行；绝不切进分数/矩阵/指数/\\text 内部。
* 折成 `\\begin{aligned}`：首行保留左侧对齐，续行 `& \\qquad <op> ...`。
* 整块是不可折环境（matrix/array/cases/CD/多行分段）或无安全断点 → SKIP 并说明
  （这类只能靠查看器横向滚动兜底，不做硬折行）。

用法:
    # 规划器（默认，只读不写）：列出待折行公式（文件 + \tag + 渲染宽度）
    python tools/wrap_long_formulas.py <dir> [threshold_chars]
    python tools/wrap_long_formulas.py <dir> 60 --json <out.json>              # 计划写 JSON
    # 折行落盘：把超长带 \tag 显示块折成 aligned，原地改写 <dir> 下的 *.md
    python tools/wrap_long_formulas.py <units_dir> --apply [--tgt 45] [--dry] [--tags 5.1,5.5]
说明:
    · <dir> 传**源单元目录**（units/chN，或 units-translate/chN），不要传成品所在的书
      根目录——成品 md 由 merge_units 再生，直接改会被覆盖（先改单元再重拼）。
    · 断行点只在顶层二元运算符（= + - 及关系命令），绝不切进分数/矩阵/指数/\text；
      \left..\right、\big 家族、\| 范数定界符内部视为整体不许断。
    · 落盘守卫（任一不满足即跳过，宁可不折）：折后必须 w ≤ 阈值(60) 且 h ≤ 8、
      确有改善、\tag 原样、数学内容逐字保真（剥排版标记后相等）、定界符配对。
      不可折案例按 docs/writing-rules.md #18 靠查看器横向滚动兜底。
    · 每章校验时的同款检测已内置于 verify F 层（long_formula_rows, WARN）。
"""
import glob
import json
import os
import re
import sys

# 🔴 长度度量统一复用 scan_long_formulas 的实现，勿在本文件另写一份
# （两份度量一旦分叉，planner 的折行目标宽度与 detector 的判定阈值就对不上。）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scan_long_formulas import (row_metrics, rendered_rows, _split_top_rows,
                                DEFAULT_W, DEFAULT_H)

THRESH = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else DEFAULT_W
BOOK = sys.argv[1] if len(sys.argv) > 1 else '.'
JSON_OUT = None
if '--json' in sys.argv:
    k = sys.argv.index('--json')
    if k + 1 < len(sys.argv):
        JSON_OUT = sys.argv[k + 1]

DELIM = re.compile(r'^\s*(?:>\s*)?\$\$\s*$')
TAG_RE = re.compile(r'\\tag\{[^}]*\}')


def vis_len(latex):
    """渲染宽度（🔴 与 scan_long_formulas 同口径）。

    旧实现是「去掉 \\tag / 命令名 / 花括号后数字符」，与 scan 的旧 vis_len 一样：
    逐源码行测量、环境名（`bmatrix`）当可见字符、矩阵与分式按横向累加、
    `\\sum`/`\\int` 等符号计 0 —— 对「一个 aligned 行被折成多行书写」的公式
    （如 18.11）系统性漏报。现统一走 row_metrics。
    """
    return row_metrics(latex)[0]


# ---------------------------------------------------------------- 断点探测
# 命令形式的二元关系/运算符：与 '=' '+' '-' 等价，可作为断行点
# （🔴 旧实现只认字符 '='，导致 `\lim ... \leq \zeta` 这类公式被判"无安全断点"）
REL_RE = re.compile(
    r'\\(leq|geq|neq|ne|equiv|approx|simeq|propto|to|rightarrow|Rightarrow|'
    r'leftarrow|Leftarrow|mapsto|implies|iff|triangleq|in|notin|subset|'
    r'subseteq|supset|supseteq|setminus|times|cdot|circ|otimes|oplus|wedge|vee|'
    r'pm|mp|mid|parallel|perp)(?![a-zA-Z])')

# 箭头族：可在其前断行，但**不得**落在 `\quad \text{if ...}` 这类尾随条件从句内部
# （否则会把 "if φ: X → C" 劈成两半，见 Koopman 4.10）
ARROWS = {'to', 'mapsto', 'rightarrow', 'Rightarrow', 'leftarrow', 'Leftarrow',
          'implies', 'iff'}

# 末段短于此宽度视为"孤儿续行"，并回上一段（见 _greedy_segments）
ORPHAN_MIN = 10

# `\big` / `\Big` / `\bigg` / `\Bigg` 家族定界符（可带 l/r/m 后缀）
# 🔴 必须配对跟踪：`\big|A - B \circ C\big|` 这类式子若允许在组内断行，
#    会把开闭定界符分到两行（观感上是"半边竖线"，见 Koopman 5.45 / 5.82）
BIG_RE = re.compile(r'\\(?:big|Big|bigg|Bigg)(l|r|m)?')


def _in_trailing_cond(s, i):
    """位置 i 是否落在行尾 `\\quad \\text{if/where/...}` 条件从句内部。"""
    pre = s[:i]
    k = max(pre.rfind('\\quad'), pre.rfind('\\qquad'))
    if k < 0:
        return False
    return '\\text{' in pre[k:]


def _top_level_split_positions(s):
    """返回可在其【前】断行的字符位置集合（顶层二元运算符/关系符位置）。"""
    cand = set()
    depth = 0          # 花括号深度
    pdepth = 0         # 圆括号/方括号深度
    lr = 0             # \\left..\\right 深度
    norm = False       # `\\| .. \\|` 范数定界符内
    big = 0            # `\\big` 家族定界符深度
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if s.startswith('\\left', i):
            lr += 1
            i += 5
            continue
        if s.startswith('\\right', i):
            lr = max(0, lr - 1)
            i += 6
            continue
        # 🔴 范数/绝对值定界符 `\|`（成对出现）内部不许断行，
        #    否则会把 `\|A - \lambda z\|_2` 从中间劈开（见 Koopman 7.28）
        if s.startswith('\\|', i):
            norm = not norm
            i += 2
            continue
        mb = BIG_RE.match(s, i)
        if mb:
            suf = mb.group(1)
            if suf == 'l':
                big += 1
            elif suf == 'r':
                big = max(0, big - 1)
            else:
                big = 0 if big else 1        # 裸 `\big|` 成对出现 → 开关
            i = mb.end()
            continue
        if depth == 0 and pdepth == 0 and lr == 0 and not norm and big == 0:
            m = REL_RE.match(s, i)
            if m:
                if m.group(1) not in ARROWS or not _in_trailing_cond(s, i):
                    cand.add(i)
                i = m.end()
                continue
        if s.startswith('\\', i):
            i += 1
            continue
        if c == '{':
            depth += 1
        elif c == '}':
            depth = max(0, depth - 1)
        elif c in '([':
            pdepth += 1
        elif c in ')]':
            pdepth = max(0, pdepth - 1)
        elif depth == 0 and pdepth == 0 and lr == 0 and not norm and big == 0:
            if c == '=':
                # 🔴 `:=` / `=:` 是整体，不许从中间劈开（见 Koopman 8.21）
                if (i > 0 and s[i - 1] == ':') or (i + 1 < n and s[i + 1] == ':'):
                    pass
                else:
                    cand.add(i)
            elif c == ':' and i + 1 < n and s[i + 1] == '=':
                cand.add(i)          # 断点落在 ':=' 之前
            elif c == '+':
                cand.add(i)
            elif c == '-':
                # 仅当看上去是二元减（前一非空字符为空白/}/)/] 之类收尾）
                if i > 0 and s[i - 1] in ' \t}])':
                    cand.add(i)
        i += 1
    return cand


def _split_by_positions(s, positions):
    """把 s 按候选位置切成多段；候选处前切开，运算符留给下一段开头。"""
    pos = sorted(positions)
    out = []
    prev = 0
    for p in pos:
        if p <= prev:
            continue
        out.append(s[prev:p])
        prev = p
    out.append(s[prev:])
    return [x for x in out if x.strip()]


def _greedy_segments(s, positions, tgt, depth=0):
    """贪心：累计可视长度到 ~tgt 时在最近候选处切开，保证每段 ≤ tgt。

    🔴 `positions` 必须是 **s 自身内部** 的索引（不要把外层字符串的坐标传进来，
       旧实现把在 rhs 上算出的位置再减外层偏移，导致切进 `\\Bigr)` 内部）。
    """
    cands = sorted(p for p in positions if 0 < p < len(s))
    segs, prev = [], 0
    for p in cands:
        if vis_len(s[prev:p]) >= tgt:
            # 🔴 切点吸附：若切点前紧贴一个"纯运算符"候选（典型是 '= ' 后紧跟 '-'），
            #    改在运算符处断，让关系符出现在续行行首；否则会在行尾留下悬空的 '='。
            q = None
            for qq in cands:
                if prev < qq < p and vis_len(s[qq:p]) <= 3:
                    q = qq
            cut = q if q is not None else p
            segs.append(s[prev:cut])
            prev = cut
    segs.append(s[prev:])
    segs = [x for x in segs if x.strip()]
    # 🔴 贪心失灵兜底：只有一个候选、且首段远短于 tgt 时（如 `A = B = C` 里
    #    唯一的候选在中点、前半只有 12 宽），"累计到 tgt 才切"永远不触发 →
    #    整体仍是一段超长。此时强制在最均衡的候选处切一刀，再各自递归。
    if len(segs) == 1 and cands and vis_len(s) > tgt and depth < 4:
        best = max(cands, key=lambda p: min(vis_len(s[:p]), vis_len(s[p:])))
        a = _greedy_segments(s[:best], _top_level_split_positions(s[:best]), tgt, depth + 1)
        b = _greedy_segments(s[best:], _top_level_split_positions(s[best:]), tgt, depth + 1)
        segs = [x for x in a + b if x.strip()]
    else:
        # 兜底：仍有段超长 → 在该段内部【重新探测】断点再切（递归，限深）
        if depth < 4:
            out = []
            for sg in segs:
                if vis_len(sg) > tgt:
                    sub = _greedy_segments(sg, _top_level_split_positions(sg), tgt,
                                           depth + 1)
                    out.extend(sub if len(sub) > 1 else [sg])
                else:
                    out.append(sg)
            segs = out
    # 🔴 孤儿续行守卫：末段过短（如 `\in \{2,\ldots,n\}.`）说明把 `i \in S` 这类短
    #    尾巴切下来了，语义与观感都差 → 并回上一段；但若末段以二元运算符开头
    #    （`= + -`），它是合法的「续关系行」（如 `..., \phi_{i+1} = \overline{\phi}_i.`），
    #    保留不并回——否则会误杀 4.10 这类本可折的行（只因尾段 `= \overline{...}` 偏短）。
    if len(segs) > 1 and vis_len(segs[-1]) < ORPHAN_MIN:
        tail = segs[-1].lstrip()
        if tail[:1] not in '=+-':
            segs = [x for x in segs[:-2] + [segs[-2] + segs[-1]] if x.strip()]
    return segs


# ---------------------------------------------------------------- 折行组装
def _wrap_plain(content, tgt, is_bq):
    """单行纯公式（不含环境、不含 &、含可选 \\tag）：折成 aligned。返回 rows 列表。"""
    cands = _top_level_split_positions(content)   # 🔴 就是 content 自身坐标
    if not cands:
        return None, 'no-split'
    eqs = sorted(p for p in cands if content[p] == '=')
    if eqs:
        p0 = eqs[0]
        lhs = content[:p0].rstrip()
        rhs = content[p0 + 1:].lstrip()
        if not rhs.strip():
            return None, 'no-split'
        # rhs 内部继续断行；目标宽度要扣掉 lhs 与对齐符已占的宽
        tgt_eff = max(12, tgt - vis_len(lhs + '&='))
        segs = _greedy_segments(rhs, _top_level_split_positions(rhs), tgt_eff)
        if len(segs) <= 1:
            # 🔴 rhs 无内部断点：仍可在 lhs/rhs 的 `=` 处折成两行
            #    （首行 lhs、续行 &= rhs）——只要折后每行 ≤ 阈值（由 apply_dir
            #    的 w1>max_w 守卫兜底）。否则会错失 5.5 这类最基础的折法
            #    （原式 81，折后 max(lhs≈38, rhs≈43) ≤ 60）。
            segs = [rhs]
        # 🔴 首行只放 lhs，续行以 `&=` 起头（中间 \\ 断行）；绝不能把
        #    `lhs &= rhs` 拼进同一行——否则渲染宽度仍是整行（5.5：81→81 无效）。
        rows = [lhs, '&= ' + segs[0]]
        for sg in segs[1:]:
            rows.append('& \\qquad ' + sg)
        return rows, None
    # 无 '='：普通折行
    segs = _greedy_segments(content, cands, tgt)
    if len(segs) <= 1:
        return None, 'no-split'
    rows = [segs[0]]
    for sg in segs[1:]:
        rows.append('& \\qquad ' + sg)
    return rows, None


def _wrap_aligned_row(line, tgt):
    """aligned 内单行（可能带 '&' 与行尾 \\\\）过长时拆分。返回 [lines] 或 None。"""
    body = line.rstrip()
    trail = ''
    if body.endswith('\\\\'):
        trail = '\\\\'
        body = body[:-2].rstrip()
    if not body.strip():
        return None
    amp = body.find('&')
    if amp < 0:
        return None  # 无对齐点的行不自动拆（避免破坏对齐结构）
    lhs = body[:amp].rstrip()
    rhs = body[amp + 1:].strip()
    # `&=` 的 '=' 留在对齐点上（旧实现写成 `& =`，既丑又多占宽）
    lead = ''
    if rhs.startswith('='):
        lead = '='
        rhs = rhs[1:].lstrip()
    # 🔴 断点在 rhs 上重新探测，坐标即 rhs 自身坐标（勿再减偏移）
    tgt_eff = max(12, tgt - vis_len(lhs + '&' + lead))
    segs = _greedy_segments(rhs, _top_level_split_positions(rhs), tgt_eff)
    if len(segs) <= 1:
        return None
    out = [lhs + ' &' + (lead + ' ' if lead else ' ') + segs[0]]
    for sg in segs[1:]:
        out.append('& \\qquad ' + sg)
    if trail:
        out[-1] += ' ' + trail
    return out


# ---------------------------------------------------------------- 落盘（--apply）
BQ_LEAD = re.compile(r'^((?:\s*>\s*)+)')   # 块引用前缀，如 "> " / "> > "

# 排版标记（折行允许插入/重排的东西）；剥掉后数学内容必须逐字相等
LAYOUT_RE = re.compile(r'\\begin\{aligned\}|\\end\{aligned\}|\\\\|&|\\qquad|\\quad|\s+')


def canon(s):
    """剥排版标记后的数学内容指纹——折行前后必须相等（内容保真硬闸）。"""
    return LAYOUT_RE.sub('', s)


def delim_ok(s):
    """输出块悬空定界符检查：\\left..\\right、\\begin..\\end、\\bigl/\\bigr、花括号配对。"""
    if s.count('\\left') != s.count('\\right'):
        return False
    for env in set(re.findall(r'\\begin\{([a-zA-Z]+)\}', s)):
        if s.count('\\begin{%s}' % env) != s.count('\\end{%s}' % env):
            return False
    if (s.count('\\bigl') + s.count('\\Bigl') + s.count('\\biggl') + s.count('\\Biggl')) != \
       (s.count('\\bigr') + s.count('\\Bigr') + s.count('\\biggr') + s.count('\\Biggr')):
        return False
    return s.count('{') == s.count('}')


def _bq_lead(s):
    m = BQ_LEAD.match(s)
    return m.group(1) if m else ''


def _bq_level(s):
    """块引用层级（数 '>' 的个数）。

    🔴 必须按【层级】而不是前缀字符串比较：markdown 里空引用行常写成裸 '>'
    （无尾随空格），与内容行的 '> ' 字符串不等；按字符串比较会误判成
    "前缀不一致" 而放弃剥离，把 '>' 混进公式里。
    """
    return _bq_lead(s).count('>')


def iter_blocks_with_idx(lines):
    """yield (open_idx, close_idx, buf, prefix) —— 带行号，便于原地替换。

    `prefix` 是块引用前缀（形如 '> '）；块内各行**引用层级**一致时才处理，
    否则 prefix 为 None 让调用方跳过（避免把 '>' 混进公式）。
    """
    i, n = 0, len(lines)
    while i < n:
        if DELIM.match(lines[i]):
            j, buf = i + 1, []
            while j < n and not DELIM.match(lines[j]):
                buf.append(lines[j])
                j += 1
            if j < n:
                lv = {_bq_level(x) for x in buf}
                if len(lv) != 1:
                    yield i, j, buf, None
                    i = j + 1
                    continue
                pfx = '> ' * lv.pop()
                buf = [x[len(_bq_lead(x)):] for x in buf]
                yield i, j, buf, pfx
                i = j + 1
                continue
        i += 1


def metrics_of(body):
    """整块 (最宽渲染行, 渲染行总数)——与 scan_long_formulas 同口径。"""
    w = h = 0
    for r in rendered_rows(body):
        rw, rh = row_metrics(r)
        w = max(w, rw)
        h += rh
    return w, h


def fold_block(body, tgt):
    """给定 $$ 块内容（含 \tag），返回折行后的新内容；不可折返回 None。"""
    tagm = TAG_RE.search(body)
    if not tagm:
        return None
    tag = tagm.group(0)
    txt = TAG_RE.sub('', body).strip()

    m = re.match(r'^\\begin\{(aligned|split|gathered)\}(.*)\\end\{\1\}$', txt, re.S)
    if m:
        env, inner = m.group(1), m.group(2)
        rows = _split_top_rows(inner)
        new_rows, touched = [], False
        for r in rows:
            rr = r.strip()
            trail = ''
            if rr.endswith('\\\\'):
                trail = '\\\\'
                rr = rr[:-2].rstrip()
            if not rr.strip() or metrics_of(rr)[0] <= tgt:
                new_rows.append(rr + (' ' + trail if trail else ''))
                continue
            sub = _wrap_aligned_row(rr, tgt)
            if sub is None:
                new_rows.append(rr + (' ' + trail if trail else ''))
                continue
            touched = True
            if trail and not sub[-1].endswith('\\\\'):
                sub[-1] = sub[-1] + ' ' + trail
            new_rows.extend(sub)
        if not touched:
            return None
        return '\\begin{%s}\n%s\n\\end{%s}\n%s' % (env, ' \\\\\n'.join(new_rows), env, tag)

    # 非 aligned：整体折成 aligned
    plain = re.sub(r'\s+', ' ', txt).strip()
    rows, _err = _wrap_plain(plain, tgt, False)
    if rows is None:
        return None
    return '\\begin{aligned}\n%s\n\\end{aligned}\n%s' % (' \\\\\n'.join(rows), tag)


def apply_dir(book_dir, tgt=45, dry=True, wanted=None, show=False,
              max_w=None, max_h=None):
    """对 book_dir 下全部 *.md 原地折行（wanted 为 \tag 白名单，None=全部）。

    返回 (applied, skipped) 计数；逐条打印 APPLY/SKIP 报告。
    """
    max_w = THRESH if max_w is None else max_w
    max_h = DEFAULT_H if max_h is None else max_h
    applied = skipped = 0
    for fp in sorted(glob.glob(os.path.join(book_dir, '*.md'))):
        lines = open(fp, encoding='utf-8').read().split('\n')
        out = list(lines)
        edits = []        # [(oi, ci, new_lines)]，🔴 最后逆序应用（正序会让后续行号失效）
        rep = []
        for oi, ci, buf, pfx in iter_blocks_with_idx(lines):
            if pfx is None:
                continue          # 块内引用层级不一致 → 不碰
            body = '\n'.join(buf)
            tagm = re.search(r'\\tag\{([^}]+)\}', body)
            if not tagm:
                continue
            tag = tagm.group(1)
            if wanted and tag not in wanted:
                continue
            w0, h0 = metrics_of(body)
            # 🔴 前置闸门：本来就没超阈值 → 绝不动手（否则会把短公式硬套成 aligned，反而变高）
            if w0 <= max_w and h0 <= max_h:
                continue
            new_body = fold_block(body, tgt)
            if new_body is None:
                skipped += 1
                rep.append((tag, 'SKIP', '无安全断点/切不出多段 (w=%.0f h=%d)' % (w0, h0)))
                continue
            w1, h1 = metrics_of(new_body)
            if w1 > max_w or h1 > max_h:
                skipped += 1
                rep.append((tag, 'SKIP', '折后仍超 w=%.1f h=%d (原 w=%.0f)' % (w1, h1, w0)))
                continue
            # 🔴 必须真的变窄，且高度不许恶化到超标以上（宁可不折）
            if w1 >= w0 and h1 >= h0:
                skipped += 1
                rep.append((tag, 'SKIP', '折后无改善 w=%.0f->%.1f h=%d->%d'
                            % (w0, w1, h0, h1)))
                continue
            if canon(TAG_RE.sub('', body)) != canon(TAG_RE.sub('', new_body)):
                skipped += 1
                rep.append((tag, 'SKIP', '内容保真校验未过（bug，请报告）'))
                continue
            if not delim_ok(new_body):
                skipped += 1
                rep.append((tag, 'SKIP', '定界符不配对（bug，请报告）'))
                continue
            if not dry:
                edits.append((oi + 1, ci,
                              [pfx + x if x else x for x in new_body.split('\n')]))
            applied += 1
            rep.append((tag, 'APPLY', 'w %.0f -> %.1f, h %d -> %d' % (w0, w1, h0, h1),
                        new_body))
        if not dry and edits:
            for a, b, new in reversed(edits):
                out[a:b] = new
            open(fp, 'w', encoding='utf-8').write('\n'.join(out))
        if rep:
            print('  %s %s' % ('(dry) ' if dry else 'WRITE', os.path.basename(fp)))
            for item in rep:
                tag, st, det = item[0], item[1], item[2]
                print('      %-8s %-6s %s' % (tag, st, det))
                if show and st == 'APPLY':
                    for ln in item[3].split('\n'):
                        print('        | ' + ln)
    print('mode=%s tgt=%d | applied=%d skipped=%d'
          % (('DRY-RUN' if dry else 'WRITE'), tgt, applied, skipped))
    return applied, skipped


def main():
    if '--apply' in sys.argv:
        tgt = int(sys.argv[sys.argv.index('--tgt') + 1]) if '--tgt' in sys.argv else 45
        wanted = None
        if '--tags' in sys.argv:
            wanted = set(sys.argv[sys.argv.index('--tags') + 1].split(','))
        apply_dir(BOOK, tgt=tgt, dry='--dry' in sys.argv, wanted=wanted,
                  show='--show' in sys.argv)
        return
    plan = {}
    for fp in sorted(glob.glob(os.path.join(BOOK, '*.md'))):
        name = os.path.basename(fp)
        lines = open(fp, encoding='utf-8').read().split('\n')
        hits = []
        i, n = 0, len(lines)
        while i < n:
            if DELIM.match(lines[i]):
                j = i + 1
                buf = []
                while j < n and not DELIM.match(lines[j]):
                    buf.append(lines[j])
                    j += 1
                if j >= n:
                    i = j
                    continue
                body = '\n'.join(buf)
                if not TAG_RE.search(body):
                    i = j + 1
                    continue
                # 🔴 按【渲染行】取最宽：逐源码行取 max 会漏掉「一个长行被折成
                #    多行书写」的公式（如 18.11：源行最长 39，整行渲染宽度 71）。
                rows = rendered_rows(body)
                vis = max((row_metrics(r)[0] for r in rows), default=0)
                if vis > THRESH:
                    hits.append((i, j, buf, vis))
                i = j + 1
            else:
                i += 1
        if hits:
            plan[name] = hits
    # 汇总
    apply_cnt = 0
    skip_cnt = 0
    detail = []
    for name, hits in plan.items():
        for (o, c, buf, vis) in hits:
            tm = re.search(r'\\tag\{([^}]+)\}', '\n'.join(buf))
            tag = tm.group(1) if tm else '?'
            detail.append({'file': name, 'tag': tag, 'vis': vis})
            apply_cnt += 1
    print('THRESHOLD=%d | files=%d | planned=%d | mode=planner(no write)'
          % (THRESH, len(plan), apply_cnt))
    for d in sorted(detail, key=lambda x: -x['vis']):
        print('  %-62s tag=%s vis=%d' % (d['file'], d['tag'], d['vis']))
    if JSON_OUT:
        with open(JSON_OUT, 'w', encoding='utf-8') as f:
            json.dump(detail, f, ensure_ascii=False, indent=1)
        print('written:', JSON_OUT)
    sys.exit(0 if apply_cnt else 0)


if __name__ == '__main__':
    main()
