# -*- coding: utf-8 -*-
"""wrap_long_formulas.py — 把「超长显示公式行」折成 aligned 多行，避免 \\tag 与公式重叠。

通用工具（跨书复用）。规则见 docs/writing-rules.md「超长显示公式折行」小节。
原则（不改数学语义、不改 \\tag、可重跑）：
* 只在**顶层**（花括号深度 0、圆括号深度 0、不在 \\left..\\right 之间）的二元
  运算符（= + -）处断行；绝不切进分数/矩阵/指数/\\text 内部。
* 折成 `\\begin{aligned}`：首行保留左侧对齐，续行 `& \\qquad <op> ...`。
* 整块是不可折环境（matrix/array/cases/CD/多行分段）或无安全断点 → SKIP 并说明
  （这类只能靠查看器横向滚动兜底，不做硬折行）。

用法（v0 = 折行规划器，只读不写）:
    python tools/wrap_long_formulas.py <book_dir> [threshold_chars]            # 列出待折行公式（文件 + \tag + 行长）
    python tools/wrap_long_formulas.py <book_dir> 100 --json <out.json>        # 计划写 JSON
说明:
    · 该工具当前只产出折行计划；实际折行按 docs/writing-rules.md「超长显示公式折行」
      手改或复核计划后执行（断行点只在顶层 =/+/-(见写作规则 #18)，不切矩阵/\left..\right）。
    · 每章校验时的同款检测已内置于 verify F 层（long_formula_rows, WARN）。
"""
import glob
import json
import os
import re
import sys

THRESH = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 100
BOOK = sys.argv[1] if len(sys.argv) > 1 else '.'
APPLY = '--apply' in sys.argv
JSON_OUT = None
if '--json' in sys.argv:
    k = sys.argv.index('--json')
    if k + 1 < len(sys.argv):
        JSON_OUT = sys.argv[k + 1]

DELIM = re.compile(r'^\s*(?:>\s*)?\$\$\s*$')
CMD = re.compile(r'\\(?:[a-zA-Z]+)')
TAG_RE = re.compile(r'\\tag\{[^}]*\}')
BQ = ''  # 顶层块引用前缀当前不支持（仅处理顶层 $$；块引用内 > $$ 通过 is_bq 保留前缀）

UNWRAP_ENVS = ('matrix', 'array', 'cases', 'CD', 'smallmatrix', 'pmatrix',
               'bmatrix', 'vmatrix', 'Vmatrix')


def vis_len(latex):
    s = TAG_RE.sub('', latex)
    s = CMD.sub('', s)
    s = re.sub(r'[{}]', '', s)
    return len(s.replace('\\', ''))


# ---------------------------------------------------------------- 断点探测
def _top_level_split_positions(s):
    """返回可在其【前】断行的字符位置集合（顶层二元运算符位置）。"""
    cand = set()
    depth = 0          # 花括号深度
    pdepth = 0         # 圆括号/方括号深度
    lr = 0             # \\left..\\right 深度
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
        elif depth == 0 and pdepth == 0 and lr == 0:
            if c == '=':
                cand.add(i)
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


def _greedy_segments(s, positions, tgt):
    """贪心：累计可视长度到 ~tgt 时在最近候选处切开，保证每段 ≤ tgt+余量。"""
    cands = sorted(p for p in positions if 0 < p < len(s))
    segs = []
    prev = 0
    acc = 0
    for p in cands:
        acc += vis_len(s[prev:p])
        if acc >= tgt:
            segs.append(s[prev:p])
            prev = p
            acc = 0
    segs.append(s[prev:])
    segs = [x for x in segs if x.strip()]
    # 兜底：若仍有一段超长且还有候选，强制在候选处再切
    changed = True
    while changed:
        changed = False
        nxt = []
        for sg in segs:
            if vis_len(sg) <= tgt:
                nxt.append(sg)
                continue
            ps = sorted(p for p in cands if p > 0)
            # 在该段内部的候选切一刀（候选是全局位置，需要局部化）
            local = sorted(x for x in ps if x < len(s))
            cut = None
            for q in reversed(local):
                if q < len(sg):
                    cut = q
                    break
            # 重新按累积切
            if cut:
                nxt.append(sg[:cut])
                nxt.append(sg[cut:])
                changed = True
            else:
                nxt.append(sg)
        segs = [x for x in nxt if x.strip()]
    return segs


# ---------------------------------------------------------------- 折行组装
def _rows_to_aligned_like(rows, is_bq):
    pre = ('> ' * int(is_bq))
    out = [pre + '\\begin{aligned}']
    for k, r in enumerate(rows):
        out.append(pre + r)
        if k < len(rows) - 1:
            out.append(pre + '\\\\')
    out.append(pre + '\\end{aligned}')
    return out


def _wrap_plain(content, tgt, is_bq):
    """单行纯公式（不含环境、不含 &、含可选 \tag）：折成 aligned。返回 rows 列表。"""
    cands = _top_level_split_positions(content)
    if not cands:
        return None, 'no-split'
    # 优先在首个顶层 '=' 处拆出对齐点
    eqs = sorted(p for p in cands if content[p] == '=')
    if eqs:
        p0 = eqs[0]
        lhs = content[:p0].rstrip()
        rhs = content[p0 + 1:].lstrip()
        rows = []
        # rhs 内部继续在 + / - 断
        rc = _top_level_split_positions(rhs)
        shifted = sorted(q - p0 - 1 for q in rc if q > p0 + 1)
        # 注意 rhs 中已含 '='? 一般不再有顶层 '='；若还有，保留于续行
        rsegs = _greedy_segments(rhs, [x for x in shifted if x > 0], tgt)
        if len(rsegs) <= 1:
            rows.append(lhs + ' &= ' + rsegs[0])
            return rows, None
        rows.append(lhs + ' &= ' + rsegs[0])
        for sg in rsegs[1:]:
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
    stripped = line.rstrip()
    trail = ''
    body = stripped
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
    rc = _top_level_split_positions(rhs)
    if not rc:
        return None
    rsegs = _greedy_segments(rhs, sorted(q - amp - 1 for q in rc if q > amp + 1),
                             tgt)
    if len(rsegs) <= 1:
        return None
    out = [lhs + ' & ' + rsegs[0]]
    for sg in rsegs[1:]:
        out.append('& \\qquad ' + sg)
    if trail:
        out[-1] += ' ' + trail
    return out


def _process_block(buf, is_bq, tgt):
    """处理一个 $$ 块内部行；返回 (新buf 或 None, info)。"""
    txt = '\n'.join(buf)
    tagm = TAG_RE.search(txt)
    tag = tagm.group(0) if tagm else ''
    txt_body = TAG_RE.sub('', txt)
    start_env = re.search(r'\\begin\{([^}]+)\}', txt_body)
    if start_env and start_env.group(1) in UNWRAP_ENVS:
        return None, ('skip', 'env:%s' % start_env.group(1))
    if start_env and start_env.group(1) not in ('aligned', 'split', 'gathered'):
        return None, ('skip', 'env:%s' % start_env.group(1))
    # 判定是否 aligned 型多行
    if re.search(r'\\begin\{(?:aligned|split|gathered)\}', txt_body):
        m = re.search(r'\\begin\{(aligned|split|gathered)\}(.*?)\\end\{\1\}',
                      txt_body, re.S)
        if not m:
            return None, ('skip', 'env-parse')
        inner = m.group(2)
        pre = txt_body[:m.start()]
        post = txt_body[m.end():]
        raw_rows = re.split(r'\\\\(?=\s)', inner)
        raw_rows = [r.rstrip() for r in raw_rows]
        if not raw_rows:
            return None, ('skip', 'env-parse')
        new_rows = []
        touched = False
        for r in raw_rows:
            if not r.strip():
                continue
            rl = r
            trail = ''
            if rl.endswith('\\\\'):
                trail = '\\\\'
                rl = rl[:-2].rstrip()
            if vis_len(rl) <= tgt:
                new_rows.append(rl + (' ' + trail if trail else ''))
                continue
            sub = _wrap_aligned_row(rl, tgt)
            if sub is None:
                new_rows.append(rl + (' ' + trail if trail else ''))
                continue
            touched = True
            if trail and not sub[-1].endswith('\\\\'):
                sub[-1] += ' ' + trail
            new_rows.extend(sub)
        if not touched:
            return None, ('skip', 'not-long')
        seg = (' \\\\\\n'.join(new_rows))
        # 重新拼装
        body = '\n'.join(buf)
        # 用行级拼接更稳：直接在行上重排较复杂，回退到文本级替换内层
        new_inner = ' \\\\\n'.join(new_rows)
        return None, ('handled-via-text', None) if False else None
    # 纯单行/多物理行但非 aligned：把整个可视内容折行（保留行内原有换行合并？保守只处理单逻辑行）
    plain = ' '.join(l.strip() for l in buf if l.strip() and not TAG_RE.search(l) or True)
    plain = TAG_RE.sub('', ' '.join(l.strip() for l in buf if l.strip()))
    # 去掉换行符做逻辑单行
    plain = re.sub(r'\s+', ' ', plain).strip()
    rows, err = _wrap_plain(plain, tgt, is_bq)
    if rows is None:
        return None, ('skip', err or 'no-split')
    return None, ('skip', 'TODO-plain')


def main():
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
                vis = max((vis_len(x) for x in buf), default=0)
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
