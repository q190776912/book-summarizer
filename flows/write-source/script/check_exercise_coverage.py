"""check_exercise_coverage.py — 章末/行内练习的「印面 vs 单元」覆盖审计（建议性）

背景：结构阶段（build_structure）只在识别到 `exercise` 节点时才把练习写进契约；
本书（Iwaniec–Kowalski GTM207）的练习是嵌在正文里的小字标题 `EXERCISE n.`，
契约里几乎没有 `exercise` 节点 → 没有练习单元 → 整章练习可能被静默丢掉。
verify 的 B 层只报「自家 md 内部缺号」，看不见整章丢失（tail loss），故补此审计。

判据全部来自可机械复算的两份事实：
  1) `page_*.json` 的 text block 里形如 `EXERCISE n.` / `ExERCisE n.` 的行首标题（容忍 OCR 大小写/空格）；
  2) 单元 md 里行首的 `Exercise n.` / `**Exercise n**` / `练习 n`。

输出三类：
  MISSING  印面有、单元无  → 需目视印面后回补（或证实为假阳）
  PHANTOM  单元有、印面标题扫描无 → 多为 OCR 漏扫，需目视确认编号没记错
  OCR-EMPTY 该章印面一个练习标题都没扫到，但单元里有 → 提醒 OCR 盲区，别把「无命中」当「无练习」

默认 exit 0（只报告，不阻断）；`--strict` 时 MISSING 非空则 exit 1。
本脚本**不**替代 B 层，也不改写任何文件。
"""
import argparse
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# 印面练习标题：OCR 里词形可为 EXERCISE / ExERCisE / EXERCISIV / EXERCiSE …
PRINTED = re.compile(r'^[A-Z]{0,2}ERC[A-Z]{1,4}[.:]?(\d{1,2})\b')
# 我们自己写的单元里。行首允许引用块前缀（`> **Exercise 1.**` 是本书练习的常见排法）
# 与加粗/裸行两种体例；跨行引用（`> >`）一并容忍。
MD_HEAD = re.compile(r'(?im)^(?:>[ \t]*)*\**[ \t]*(?:exercise|练习)[ \t]*([0-9]{1,2})[ \t]*[.。]?\**')


def _norm(s):
    return re.sub(r'\s+', '', s.upper())


# 页眉里的章号：GTM 印面页眉是「10.ZERO-DENSITY ESTIMATES」（偶数页页码在前）或
# 扉页「CHAPTER 11 / SUMS OVER FINITE FIELDS」。章节标题「11.1. Introduction.」
# 不会命中——数字后必须紧跟字母。
_HDR_CHAP = re.compile(r'^CHAPTER\s*(\d{1,2})(?![\d])')
_HDR_NUM = re.compile(r'^(\d{1,2})[.\-]?[A-Z]')


def page_chapter(texts):
    """Return the chapter number named by the page's running header, or None."""
    for s in texts[:3]:
        n = _norm(s)
        if len(n) > 45:
            continue
        m = _HDR_CHAP.match(n) or _HDR_NUM.match(n)
        if m:
            return int(m.group(1))
    return None


def page_texts(extract, page):
    fp = os.path.join(extract, 'page_%03d.json' % page)
    if not os.path.exists(fp):
        return []
    try:
        with open(fp, encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return []
    out = []
    for b in data.get('text') or []:
        if isinstance(b, dict):
            s = (b.get('text') or '').replace('\n', ' ').strip()
            if s:
                out.append(s)
    return out


def printed_heads(extract, ch, start, end, foreign=frozenset()):
    """{num: page} for exercise headings seen on the printed pages.

    边界页会被相邻两章的 padding 同时抓到（实测：ch10/ch11 之间的 p267-268、
    ch20/ch21 之间的 p484 被两章同时认领），故两层排除：
      1) ``foreign``——他章契约严格页；
      2) 页眉章号：印面页眉点名了别的章（含契约区间之间的空隙页），该页不算本章。"""
    found = {}
    for p in range(int(start) - 1, int(end) + 3):
        if p in foreign:
            continue
        texts = page_texts(extract, p)
        owner = page_chapter(texts)
        if owner is not None and owner != ch:
            continue
        for s in texts:
            if len(s) > 130:
                continue
            m = PRINTED.match(_norm(s))
            if m:
                found.setdefault(int(m.group(1)), p)
    return found


def md_heads(units_dir):
    found = set()
    for fp in glob.glob(os.path.join(units_dir, '*.md')):
        try:
            with open(fp, encoding='utf-8') as f:
                text = f.read()
        except Exception:
            continue
        for m in MD_HEAD.finditer(text):
            found.add(int(m.group(1)))
    return found


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('extract')
    ap.add_argument('chapters', nargs='*', type=int)
    ap.add_argument('--units-dir', default='units')
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    bs = os.path.join(a.extract, 'book_structure')
    files = sorted(glob.glob(os.path.join(bs, 'ch*.json')),
                   key=lambda x: int(re.search(r'ch(\d+)', os.path.basename(x)).group(1)))
    contracts = []
    for fp in files:
        with open(fp, encoding='utf-8') as f:
            c = json.load(f)
        contracts.append((int(re.search(r'ch(\d+)', os.path.basename(fp)).group(1)), c, fp))
    strict = {ch: set(range(int(c.get('page_start', 1)), int(c.get('page_end', 1)) + 1))
              for ch, c, _ in contracts}
    rows = []
    for ch, c, fp in contracts:
        if a.chapters and ch not in a.chapters:
            continue
        foreign = set().union(*[s for k, s in strict.items() if k != ch]) if strict else set()
        pr = printed_heads(a.extract, ch, c.get('page_start', 1), c.get('page_end', 1), foreign)
        md = md_heads(os.path.join(bs, a.units_dir, 'ch%d' % ch))
        missing = sorted(n for n in pr if n not in md)
        phantom = sorted(n for n in md if n not in pr)
        rows.append({
            'ch': ch, 'printed': sorted(pr), 'md': sorted(md),
            'missing': [(n, pr[n]) for n in missing], 'phantom': phantom,
            'ocr_empty': not pr and bool(md),
        })

    if a.json:
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        print('ch | printed ex | md ex | MISSING(printed page) | PHANTOM')
        for r in rows:
            flag = ''
            if r['ocr_empty']:
                flag = '  [OCR-EMPTY: 印面标题零命中，不可当「无练习」]'
            print('%-3d| %-12s| %-12s| %-22s| %s%s' % (
                r['ch'], r['printed'], r['md'],
                [n for n, _ in r['missing']], r['phantom'], flag))
            for n, p in r['missing']:
                print('     - ch%d Exercise %d 疑似整条缺失，印面在 extract p%d' % (r['ch'], n, p))

    n_missing = sum(len(r['missing']) for r in rows)
    n_empty = sum(1 for r in rows if r['ocr_empty'])
    print('SUMMARY missing=%d phantom=%d ocr-empty-chapters=%d' % (n_missing,
          sum(len(r['phantom']) for r in rows), n_empty))
    if a.strict and n_missing:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
