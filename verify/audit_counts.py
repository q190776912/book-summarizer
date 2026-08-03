#!/usr/bin/env python3
# verify/audit_counts.py
# 按节核对「定义/定理/引理/推论/命题/公理」条数是否与原书 OCR 一致。
# 这是 skill 的强制校验环节：每章写完、verify PASS 之后，必须跑本脚本确认
# 「各节每种条目标签数 == 原书该节该类型条数」，有缺漏必须补全后再算完成。
#
# 用法:
#   python verify/audit_counts.py <ch> <start> <end> <md_file> <extract_dir>
#     <ch>            章号（仅用于展示）
#     <start> <end>   该章在 PDF 中的起止页（与 verify_chapter.py 同义）
#     <md_file>       章节 markdown（中文或英文皆可，按文件内标签判定）
#     <extract_dir>   _extract 目录（内含 page_NNN.json OCR 数据）
#
# 退出码: 0 = 各节条数与书中一致; 1 = 有缺漏/多余/编号不连续（必须修正）
#
# 注意：OCR 章节标题识别是启发式的（匹配 `N.M Title` 或 `§N.M`）。
# 若某节因 OCR 噪声未被识别为标题，其条目会并入上一节计数，可能出误报；
# 此时应人工核对该节实际条数，必要时在 _extract/ 下用 ignore 机制或手工修正。

import sys, re, os, json

TYPE_MAP = {
    '定义': 'def', '定理': 'theorem', '引理': 'lemma', '推论': 'corollary',
    '命题': 'prop', '公理': 'axiom', '断言': 'assertion',
    'Definition': 'def', 'Theorem': 'theorem', 'Lemma': 'lemma',
    'Corollary': 'corollary', 'Proposition': 'prop', 'Axiom': 'axiom',
    'Assertion': 'assertion',
}

# 条目标签（行首或行内粗体）：类型 + 数字（支持 N 或 N.M 三级编号）
LABEL_RE = re.compile(
    r'^\**\s*((?:定义|定理|引理|推论|命题|公理|断言|'
    r'Definition|Theorem|Lemma|Corollary|Proposition|Axiom|Assertion))'
    r'\s*([0-9]+(?:\.[0-9]+)?)', re.I)
# 章节标题：行首 `N.M Title`（Title 以大写字母开头）
SEC_RE = re.compile(r'^\s*(\d+\.\d+)\s+([A-Z][A-Za-z].{1,40})')
SEC_RE2 = re.compile(r'§\s*(\d+\.\d+)')
# 章节标题（冒号格式）：行首 `N: Title`（如 `1:Definitions`）→ 归入本章第 N 节
SEC_RE3 = re.compile(r'^\s*(\d+):\s*([A-Z][A-Za-z].{1,40})')


def texts_of_page(p, ext):
    fn = os.path.join(ext, 'page_%03d.json' % p)
    if not os.path.exists(fn):
        return []
    try:
        data = json.load(open(fn, encoding='utf-8'))
    except Exception:
        return []
    blocks = []
    for e in data.get('text', []):
        if isinstance(e, dict):
            blocks.append((e.get('poly'), e.get('text', '')))
        elif isinstance(e, str):
            blocks.append((None, e))
    def keyf(b):
        poly = b[0]
        if poly and len(poly) >= 2:
            return (poly[1], poly[0])
        return (1e9, 1e9)
    blocks.sort(key=keyf)
    return [s for _, s in blocks]


def parse_md(path):
    secs = {}
    cur = None
    for ln in open(path, encoding='utf-8'):
        m = re.match(r'#{2,3}\s*§?\s*(\d+\.\d+)', ln)
        if m:
            cur = m.group(1)
        if cur:
            m2 = LABEL_RE.search(ln.strip())
            if m2:
                t = TYPE_MAP.get(m2.group(1))
                if t:
                    g = m2.group(2)
                    num = int(g.split('.')[1]) if '.' in g else int(g)
                    secs.setdefault(cur, {}).setdefault(t, []).append(num)
    return secs


def parse_book(start, end, ext, chnum=None):
    secs = {}
    cur = None
    for p in range(start, end + 1):
        for s in texts_of_page(p, ext):
            st = s.strip()
            cand = None
            ms = SEC_RE.match(st)
            if ms:
                cand = ms.group(1)
            else:
                ms2 = SEC_RE2.search(st)
                if ms2:
                    cand = ms2.group(1)
            if not cand:
                ms3 = SEC_RE3.match(st)
                if ms3:
                    cand = '%s.%s' % (chnum, ms3.group(1)) if chnum else None
            # 只认「本章」的 N.M 节：消除书内「见 2.1 节」之类交叉引用造成的误报
            if cand and (chnum is None or cand.split('.')[0] == str(chnum)):
                cur = cand
            ml = LABEL_RE.match(st)
            if ml and cur:
                t = TYPE_MAP.get(ml.group(1))
                if t:
                    g = ml.group(2)
                    num = int(g.split('.')[1]) if '.' in g else int(g)
                    secs.setdefault(cur, {}).setdefault(t, []).append(num)
    return secs


def main():
    ch, start, end, md, ext = (int(sys.argv[1]), int(sys.argv[2]),
                               int(sys.argv[3]), sys.argv[4], sys.argv[5])
    md_secs = parse_md(md)
    book_secs = parse_book(start, end, ext, ch)
    all_secs = sorted(set(md_secs) | set(book_secs),
                      key=lambda x: [int(z) for z in x.split('.')])
    problems = 0
    print('=== 条数核对: %s (ch%d, pages %d-%d) ===' % (md, ch, start, end))
    for sec in all_secs:
        md_t = md_secs.get(sec, {})
        bk_t = book_secs.get(sec, {})
        types = sorted(set(md_t) | set(bk_t))
        for t in types:
            mc = len(md_t.get(t, []))
            bc = len(bk_t.get(t, []))
            if mc != bc:
                problems += 1
                print('  [MISMATCH] §%s %s: 书中 %d 条, 总结 %d 条'
                      % (sec, t, bc, mc))
            mdnums = sorted(md_t.get(t, []))
            if mdnums and (mdnums[0] != 1 or mdnums != list(range(1, len(mdnums) + 1))):
                problems += 1
                print('  [GAP]      §%s %s: 总结编号不连续 %s' % (sec, t, mdnums))
    if problems == 0:
        print('  PASS: 各节条数与书中一致')
        sys.exit(0)
    else:
        print('  FAIL: %d 处问题（必须补全/修正后再算该章完成）' % problems)
        sys.exit(1)


if __name__ == '__main__':
    main()
