#!/usr/bin/env python3
import os
import sys
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
import page_json

# verify/script/audit_counts.py
# 按节核对「定义/定理/引理/推论/命题/公理」条数是否与原书 OCR 一致。
# 这是 skill 的强制校验环节：每章写完、verify PASS 之后，必须跑本脚本确认
# 「各节每种条目标签数 == 原书该节该类型条数」，有缺漏必须补全后再算完成。
#
# 用法:
#   python verify/script/audit_counts.py <ch> <start> <end> <md_file> <extract_dir>
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

# 条目标签（行首或行内粗体）：类型 + 数字（支持 N / N.M / N.M.K 三级编号；
# OCR 可能把分隔符识别为 。．·，也可能出现 类型（数字） 形态。
# 额外容忍三种 OCR 变体：行首多余点号（`．定义10.2.1…`）、类型与编号之间的
# 点号（`引理.7.2.1…`）、末段数字被识别成小写 l（`定义9.2.l…`）。
LABEL_RE = re.compile(
    r'^[.．·。]*\**\s*((?:定义|定理|引理|推论|命题|公理|断言|'
    r'Definition|Theorem|Lemma|Corollary|Proposition|Axiom|Assertion))'
    r'\s*[.．·。]?\s*[（(]?\s*([0-9]+(?:[.．·。][0-9l]+){0,2})\s*[）)]?', re.I)
# 数字前置标签（Vakil 惯例）：`**12.2.1（定理 …）：**`；书内 OCR 为 `12.2.1. Theorem.`
# —— 编号在前，类型在 `（`/`（`/`.` 之后
LABEL_RE_NF = re.compile(
    r'^\**\s*([0-9]+(?:\.[0-9]+){0,2})\s*[.．。（(]\s*'
    r'((?:定义|定理|引理|推论|命题|公理|断言|'
    r'Definition|Theorem|Lemma|Corollary|Proposition|Axiom|Assertion))', re.I)
# 章节标题：行首 `N.M Title`（Title 以大写字母开头；容忍 OCR 把破折号误识为 xx）
SEC_RE = re.compile(r'^\s*(\d+\.\d+)\s*(?:[—–\-–—]+\s*|xx\s*)?([A-Z][A-Za-z].{1,40})')
# §N.M 仅当位于行首才算章节标题；行内 `in §11.3` 是交叉引用，不能作为标题
SEC_RE2 = re.compile(r'^\s*§\s*(\d+\.\d+)')
# 章节标题（冒号格式）：行首 `N: Title`（如 `1:Definitions`）→ 归入本章第 N 节
SEC_RE3 = re.compile(r'^\s*(\d+):\s*([A-Z][A-Za-z].{1,40})')
# 中文书籍章节标题（模式见 lib/regexlib.py：SEC_CN / SECBARE_CN / SECGLUE_CN）
from lib.regexlib import SEC_CN, SECBARE_CN, SECGLUE_CN


def texts_of_page(p, ext):
    fn = os.path.join(ext, 'page_%03d.json' % p)
    if not os.path.exists(fn):
        return []
    try:
        data = page_json.PageJson.load(fn).data
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


def _label_type(ln):
    """返回 (type_word, num_str) 或 None。兼容「类型前置」与「数字前置」两种标签。"""
    m = LABEL_RE.match(ln)
    if m:
        return m.group(1), m.group(2)
    m = LABEL_RE_NF.match(ln)
    if m:
        return m.group(2), m.group(1)
    return None


def _norm_num(g):
    """把 OCR 常见分隔符  。．·  统一为 . 再取末段数字；末段若被识别为 l 当作 1。"""
    seg = g.replace('。', '.').replace('．', '.').replace('·', '.').split('.')[-1]
    return int(seg.replace('l', '1'))


def parse_md(path):
    secs = {}
    cur = None
    for ln in open(path, encoding='utf-8'):
        m = re.match(r'#{2,3}\s*§?\s*(\d+\.\d+)', ln)
        if m:
            cur = m.group(1)
        if cur:
            r = _label_type(ln.strip())
            if r:
                t = TYPE_MAP.get(r[0])
                if t:
                    secs.setdefault(cur, {}).setdefault(t, []).append(_norm_num(r[1]))
    return secs


def parse_book(start, end, ext, chnum=None):
    secs = {}
    cur = None
    for p in range(start, end + 1):
        for block in texts_of_page(p, ext):
            for ln in block.split('\n'):
                st = ln.strip()
                if not st:
                    continue
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
                if not cand:
                    mcn = SEC_CN.match(st)
                    if mcn and not mcn.group(1).startswith('0') and not mcn.group(2).startswith('0') and int(mcn.group(2)) != 0:
                        cand = '%s.%s' % mcn.group(1, 2)
                    else:
                        mgl = SECGLUE_CN.match(st)
                        if mgl and not mgl.group(1).startswith('0') and not mgl.group(2).startswith('0') and int(mgl.group(2)) != 0:
                            cand = '%s.%s' % mgl.group(1, 2)
                        else:
                            mbb = SECBARE_CN.match(st)
                            if mbb and not mbb.group(1).startswith('0') and not mbb.group(2).startswith('0') and int(mbb.group(2)) != 0:
                                cand = '%s.%s' % mbb.group(1, 2)
                # 只认「本章」的 N.M 节：消除书内「见 2.1 节」之类交叉引用造成的误报
                if cand and (chnum is None or cand.split('.')[0] == str(chnum)):
                    cur = cand
                # OCR 变体归一化：p216「引I理4.4.1」；p320「论 7.2.1」（推论被截断，
                # 仅当编号属于当前节时归一，避免把「论5.3.2即得…」这类跨节引用误判）
                st2 = re.sub(r'^引[Il1]?理', '引理', st)
                if cur:
                    st2 = re.sub(r'^论(?=\s*%s[.．·。])' % re.escape(cur), '推论', st2)
                ml = _label_type(st2)
                # 无分隔符的纯数字标签（如正文引用「命题29」）不是正式条目，跳过
                if ml and cur and re.search(r'[.．·。]', ml[1]):
                    t = TYPE_MAP.get(ml[0])
                    if t:
                        secs.setdefault(cur, {}).setdefault(t, []).append(_norm_num(ml[1]))
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
            bc = len(set(bk_t.get(t, [])))  # 书内同一条目常以「N.M.K. Type.」与「Type N.M.K」两种形态出现，去重
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
