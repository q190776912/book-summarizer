"""scan_skeleton.py — 扫描原书某章的【真实结构骨架】，产出写作契约 ch{N}_skeleton.txt

为什么需要它
------------
`ch{N}_items.txt`（extract_items*.py 的产物）只包含 **verifier 的必备条目键**，
它不含节标题、不含练习、不含条目的印刷标题。写章总结的 agent 若只拿到 items.txt，
手上就没有「这一章到底有哪几节、每节有哪些条目和练习、按什么顺序排、每条印刷标题
叫什么」的权威清单 —— 于是必然出现：漏节、节序颠倒、条目丢标题、练习被随手归拢。

本脚本直接从 `page_*.json` 扫出这份清单，**按页码顺序**输出，作为写作时的结构契约：
骨架里有几节就必须写几节、顺序照抄、每个 ITEM 都要落地、印刷标题必须进标签。`EXER`（练习）按 `references/formatting.md` 的「习题收录规则」处理：穿插习题原位落地，章末整块习题省略（不强制落地）。

用法
----
    python extract/scan_skeleton.py <extract_dir> [ch ...] [--scheme three-level|two-level]

    # 全书
    python extract/scan_skeleton.py D:/study/book/<书名>/_extract
    # 指定章
    python extract/scan_skeleton.py D:/study/book/<书名>/_extract 1 2 3

输出
----
`<extract_dir>/ch{N}_skeleton.txt`，每行一条，形如：

    SEC   1.2         p25   Categories and functors
    ITEM  1.2.1       p25   Categories.
    EXER  1.2.A       p26   UNIMPORTANT EXERCISE. A category in which ...
    ITEM  1.2.4       p27   Example: abelian groups.

体例说明
--------
three-level（默认，如 Vakil《The Rising Sea》）：
    节   "1.2 Categories and functors"
    条目 "1.2.1. Categories."      —— 编号在前、句点标题在后
    练习 "1.2.A. EXERCISE."        —— 字母编号
two-level（如 "§2 标题" + 条目 "2.3."）：
    节   "2 Some title"
    条目 "2.3. Title."
    练习 "2.C. Exercise."
"""
import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

# 节标题：可带 Vakil 的可选标记（★ 被 OCR 成 + / * / x），标题也可能以单字母词开头
# （"3.5 A base of ..."），故只要求首字符大写、长度 4~72。
SEC_3 = re.compile(r'^(\d{1,2})\.(\d{1,2})\s+[+*x\u00d7\u2605\u2606]?\s*([A-Z].{3,72})$')
ITEM_3 = re.compile(r'^(\d{1,2})\.(\d{1,2})\.(\d{1,3})\.\s*(.{0,90})')
EXER_3 = re.compile(r'^(\d{1,2})\.(\d{1,2})\.([A-Z])\.\s*(.{0,90})')

SEC_2 = re.compile(r'^(\d{1,2})\s+[+*x\u00d7\u2605\u2606]?\s*([A-Z].{3,72})$')
ITEM_2 = re.compile(r'^(\d{1,2})\.(\d{1,3})\.\s*(.{0,90})')
EXER_2 = re.compile(r'^(\d{1,2})\.([A-Z])\.\s*(.{0,90})')

# Chinese-scheme books (e.g. 高等代数学): "1.5行列式的计算" / "定理1.4.1 ..." /
# "(1.1.3)" / "习题 1.3". 条目标签在编号之前，节标题可带 § 或 * + x × ★ 记号。
SEC_CN = re.compile(r'^[§Ss8*+x$\u00d7\u2605\u2606\s]*[.．·]?(\d{1,2})[\.\．·](\d{1,2})[\.\．·。]?(?!\s+[\u4e00-\u9fff])(?=[^\d.．·。]*[\u4e00-\u9fff]).{0,24}$')
SECBARE_CN = re.compile(r'^[§Ss8*+x$\u00d7\u2605\u2606\s]*[.．·]?(\d{1,2})[\.\．·](\d{1,2})$')
SECGLUE_CN = re.compile(r'^[§Ss8*+x$\u00d7\u2605\u2606\s]*[Ss8§](\d{1,2})[\.\．·]?(\d{1,2})[^\s\d](?=[^\d.．·。]*[\u4e00-\u9fff]).{0,24}$')
ITEM_CN = re.compile(
    r'^(?:定理|定义|引理|推论|命题|性质|例|注|表|图)\s*[（(]?(\d{1,2})[\.\．·。](\d{1,2})[\.\．·。](\d{1,3})[）)]?(?!\d)\s*(.{0,90})')
BARE_CN = re.compile(r'^[（(](\d{1,2})[\.\．·。](\d{1,2})[\.\．·。](\d{1,3})[）)](?!\d)\s*(.{0,90})')
EXER_CN = re.compile(r'^习题\s*(\d{1,2})[\.\．·](\d{1,2})')


def lines_of(page_json):
    for it in page_json.get('text', []):
        for ln in (it.get('text') or '').split('\n'):
            yield ln.strip()


def scan(extract_dir, ch, start, end, scheme):
    rows = []
    for p in range(start, end + 1):
        fp = os.path.join(extract_dir, 'page_%03d.json' % p)
        if not os.path.exists(fp):
            continue
        with open(fp, encoding='utf-8') as fh:
            d = json.load(fh)
        for ln in lines_of(d):
            ln = ln.rstrip('$').strip()
            if not ln:
                continue
            if scheme == 'two-level':
                m = SEC_2.match(ln)
                if m and int(m.group(1)) == ch and not m.group(2).endswith('.'):
                    rows.append((p, 'SEC', m.group(1), m.group(2).strip()))
                    continue
                m = EXER_2.match(ln)
                if m and int(m.group(1)) == ch:
                    rows.append((p, 'EXER', '%s.%s' % m.group(1, 2), m.group(3).strip()))
                    continue
                m = ITEM_2.match(ln)
                if m and int(m.group(1)) == ch:
                    rows.append((p, 'ITEM', '%s.%s' % m.group(1, 2), m.group(3).strip()))
            elif scheme == 'cn':
                m = SEC_CN.match(ln)
                if m and int(m.group(1)) == ch:
                    if m.group(1).startswith('0') or m.group(2).startswith('0') or int(m.group(2)) == 0:
                        continue
                    rows.append((p, 'SEC', '%s.%s' % m.group(1, 2),
                                 ln[m.end(2):].lstrip(' \u00a7.．·。').strip()))
                    continue
                m = SECBARE_CN.match(ln)
                if m and int(m.group(1)) == ch:
                    if m.group(1).startswith('0') or m.group(2).startswith('0') or int(m.group(2)) == 0:
                        continue
                    rows.append((p, 'SEC', '%s.%s' % m.group(1, 2), ''))
                    continue
                m = SECGLUE_CN.match(ln)
                if m and int(m.group(1)) == ch:
                    if m.group(1).startswith('0') or m.group(2).startswith('0') or int(m.group(2)) == 0:
                        continue
                    rows.append((p, 'SEC', '%s.%s' % m.group(1, 2),
                                 ln[m.end(2):].lstrip(' \u00a7.．·。').strip()))
                    continue
                m = ITEM_CN.match(ln)
                if m and int(m.group(1)) == ch:
                    rows.append((p, 'ITEM', '%s.%s.%s' % m.group(1, 2, 3), m.group(4).strip()))
                    continue
                m = BARE_CN.match(ln)
                if m and int(m.group(1)) == ch:
                    rows.append((p, 'ITEM', '%s.%s.%s' % m.group(1, 2, 3), '(%s.%s.%s)' % m.group(1, 2, 3)))
                    continue
                m = EXER_CN.match(ln)
                if m and int(m.group(1)) == ch:
                    rows.append((p, 'EXER', '%s.%s' % m.group(1, 2), '习题 %s.%s' % m.group(1, 2)))
            else:
                m = SEC_3.match(ln)
                if m and int(m.group(1)) == ch and not m.group(3).endswith('.'):
                    rows.append((p, 'SEC', '%s.%s' % m.group(1, 2), m.group(3).strip()))
                    continue
                m = EXER_3.match(ln)
                if m and int(m.group(1)) == ch:
                    rows.append((p, 'EXER', '%s.%s.%s' % m.group(1, 2, 3), m.group(4).strip()))
                    continue
                m = ITEM_3.match(ln)
                if m and int(m.group(1)) == ch:
                    rows.append((p, 'ITEM', '%s.%s.%s' % m.group(1, 2, 3), m.group(4).strip()))
    return rows


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    scheme = 'three-level'
    for a in sys.argv[1:]:
        if a.startswith('--scheme'):
            scheme = a.split('=', 1)[1] if '=' in a else 'three-level'
    if '--scheme' in sys.argv:
        i = sys.argv.index('--scheme')
        if i + 1 < len(sys.argv):
            scheme = sys.argv[i + 1]
            if scheme in args:
                args.remove(scheme)

    if not args:
        print(__doc__)
        return 2
    extract_dir = args[0]
    want = [int(x) for x in args[1:]]

    cm_path = os.path.join(extract_dir, 'chapter_map.json')
    with open(cm_path, encoding='utf-8') as fh:
        cm = json.load(fh)
    if isinstance(cm, dict) and 'chapters' in cm:
        chapters = cm['chapters']
    elif isinstance(cm, dict):
        # chapter_map.json may be a dict-of-dicts: {"1": {"name":..,"start":..,"end":..}, ...}
        chapters = cm
    else:
        chapters = cm
    rng = {}
    if isinstance(chapters, dict):
        # keyed by chapter number (string)
        for k, c in chapters.items():
            rng[int(k)] = (int(c['start']), int(c['end']))
    else:
        for c in chapters:
            n = c.get('num', c.get('ch', c.get('chapter', c.get('n'))))
            rng[int(n)] = (int(c['start']), int(c['end']))

    for ch in (want or sorted(rng)):
        if ch not in rng:
            print('ch%-3d SKIP (not in chapter_map)' % ch)
            continue
        start, end = rng[ch]
        rows = scan(extract_dir, ch, start, end, scheme)
        sec_best = {}
        for row in rows:
            if row[1] == 'SEC':
                if row[2] not in sec_best or (sec_best[row[2]][3] == '' and row[3] != ''):
                    sec_best[row[2]] = row
        deduped, seen = [], set()
        for row in rows:
            if row[1] == 'SEC':
                if row[2] in seen:
                    continue
                seen.add(row[2])
                deduped.append(sec_best[row[2]])
            else:
                deduped.append(row)
        rows = deduped
        out = os.path.join(extract_dir, 'ch%d_skeleton.txt' % ch)
        secs = []
        with open(out, 'w', encoding='utf-8') as f:
            f.write('# Chapter %d skeleton (pages %d-%d, scheme=%s)\n' % (ch, start, end, scheme))
            f.write('# THIS FILE IS A WRITING CONTRACT: emit every SEC in this order,\n')
            f.write('# cover every ITEM in this order, keep every printed title.\n')
            f.write('# EXER (exercises): follow references/formatting.md 习题收录规则\n')
            f.write('#   (interleaved exercises kept in place; chapter-end blocks omitted).\n')
            f.write('# kind  number      page  printed-title\n')
            for p, kind, num, title in rows:
                if kind == 'SEC':
                    secs.append(num)
                    f.write('\n')
                f.write('%-5s %-11s p%-4d %s\n' % (kind, num, p, title))
        n_item = sum(1 for r in rows if r[1] == 'ITEM')
        n_ex = sum(1 for r in rows if r[1] == 'EXER')
        print('ch%-3d -> %s | secs=%s items=%d exercises=%d'
              % (ch, os.path.basename(out), secs, n_item, n_ex))
    return 0


if __name__ == '__main__':
    sys.exit(main())
