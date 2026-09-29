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

🔴 **PHANTOM 有两种根因，必须先分诊再处置**（Iwaniec–Kowalski 实测 4 处）：
  * **判据漏（词表缺项）**——标题行其实**在** OCR 里，只是某一个字母被读歪
    （ch4 Ex4 = `ExFRCISE 4.Derive (4.23) fron1 (4.21)`），字符类整体失配。
    这类**改判据**（见 `printed_label`），不许登记；
  * **印面真值集缺行**——扫描书的小字粗体标题**整行连展示式一起被 OCR 漏掉**
    （实测剩 3 处：ch1 Ex2 = extract p29、ch4 Ex7 = p85、ch5 Ex6 = p115，全部
    fitz 裁剪目视坐实印面确有该练习，且页上相邻条目都在）。机器无从复算，
    只能由人看渲染页 → 与闸门 ⑭ 的 `formula.known_book` 同理，必须有**账**：
    `--attest` 登记进 `verify_config.json` 的 `exercise_printed_attested`
    （章 / 号 / 页 / 证据 / 时间），比对时并入印面真值集。
纪律：**先渲染印面目视，再登记**；未坐实不得登记（登记不等于判据）。登记页码必须
落在本章扫描区间内、该号必须**尚未**被机械扫到、且该号必须**真的存在于单元里**
（否则一条「印面确证」会把真缺失永久掩盖），三条不满足 `--attest` 直接拒绝。

默认 exit 0（只报告，不阻断）；`--strict` 时 MISSING 非空则 exit 1。
本脚本**不**替代 B 层；除 `--attest` 显式登记外不改写任何文件。
"""
import argparse
import glob
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))

# 印面练习标题：OCR 里词形可为 EXERCISE / ExERcisE / EXERCISIV / EXERCiSE …
PRINTED = re.compile(r'^[A-Z]{0,2}ERC[A-Z]{1,4}[.:]?(\d{1,2})\b')
# 🔴 折叠词表补漏（2026-09-29 Iwaniec–Kowalski 实测）：小字粗体标题的**某一个字母**
# 被 OCR 读成别的（ch4 Ex4 印面 `EXERCISE 4.` → `ExFRCISE 4.`），上述字符类就整体失效。
# 逐 spelling 枚举是补不完的，故再加一条**编辑距离 ≤1** 的判据。
# ⚠️ 跨 51 本书普查（1954 条旧命中）：只要求「词首 + 数字」会顺手把**正文里的互相
# 引用**当成标题行——`Exercise 6 shows that R is nonsingular`、`Exercises 13 and 14.`、
# 书眉 `EXERCISES   113`（词形 + 页码）等 100+ 处假阳，方向上是把对的单元报成 MISSING。
# 所以数字后面必须紧跟**终止符**（`.` / `:` / 行尾）才算标题，与旧正则的 `\b` 同口径。
_LABEL = 'EXERCISE'
_LABEL_HEAD = re.compile(r'^([A-Z]{5,11})(\d{1,2})[.:]')


def _near_label(word):
    """Levenshtein(word, 'EXERCISE') <= 1（只做 0/1 判定，不需要全表）。"""
    a, b = (word, _LABEL) if len(word) >= len(_LABEL) else (_LABEL, word)
    if len(a) - len(b) > 1:
        return False
    if len(a) == len(b):
        return sum(1 for x, y in zip(a, b) if x != y) <= 1
    i = 0
    while i < len(b) and a[i] == b[i]:
        i += 1
    return a[i + 1:] == b[i:]


def printed_label(text):
    """一行 OCR 文本 → 练习号（int）或 None。判据 = 旧正则 ∪ 编辑距离 ≤1 + 终止符。"""
    n = _norm(text)
    m = PRINTED.match(n)
    if m:
        return int(m.group(1))
    h = _LABEL_HEAD.match(n)
    if h and _near_label(h.group(1)):
        return int(h.group(2))
    return None

# 我们自己写的单元里。行首允许引用块前缀（`> **Exercise 1.**` 是本书练习的常见排法）
# 与加粗/裸行两种体例；跨行引用（`> >`）一并容忍。
MD_HEAD = re.compile(r'(?im)^(?:>[ \t]*)*\**[ \t]*(?:exercise|练习)[ \t]*([0-9]{1,2})[ \t]*[.。]?\**')

ATTEST_KEY = "exercise_printed_attested"


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
            raw = b.get('text')
            if not isinstance(raw, str):
                # 跨书普查实测：有的书 page_*.json 的 text 项是嵌套 dict，
                # 直接 .replace 会崩掉整本审计
                continue
            s = raw.replace('\n', ' ').strip()
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
            num = printed_label(s)
            if num is not None:
                found.setdefault(num, p)
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


def merge_printed(pr, att):
    """印面真值 = 机械扫描 ∪ 人工坐实（后者位置记成 ``('p<页>', 'attested')``）。

    检测（`printed_heads`）、登记（`write_attestation`）、比对（`main`）共用这一个
    函数，登记才不可能在某一侧被绕过。
    """
    printed = dict(pr)
    for n, e in (att or {}).items():
        if n not in printed:
            printed[n] = ('p%s' % e.get('page'), 'attested')
    return printed


def _load_cfg(extract):
    fp = os.path.join(extract, 'verify_config.json')
    if not os.path.exists(fp):
        return {}
    try:
        with open(fp, encoding='utf-8-sig') as f:
            cfg = json.load(f)
    except Exception:
        return {}
    return cfg if isinstance(cfg, dict) else {}


def attested_printed(extract, ch=None):
    """人工印面确证台账 → ``{ch: {num: entry}}``（``ch=None`` 时返回全部章）。

    兼容扁平（顶层 ``exercise_printed_attested``）与分组（``ch``/``appendix``/
    ``supplement`` 下）两种配置形状；缺键 / 坏项一律跳过，绝不抛。
    """
    cfg = _load_cfg(extract)
    lists = [cfg.get(ATTEST_KEY)]
    for grp in ('ch', 'appendix', 'supplement'):
        node = cfg.get(grp)
        if isinstance(node, dict):
            lists.append(node.get(ATTEST_KEY))
    out = {}
    for lst in lists:
        if not isinstance(lst, list):
            continue
        for e in lst:
            if not isinstance(e, dict):
                continue
            try:
                c, n = int(e.get('ch')), int(e.get('ex'))
            except (TypeError, ValueError):
                continue
            out.setdefault(c, {})[n] = e
    return out if ch is None else out.get(int(ch), {})


def write_attestation(extract, ch, ex, page, evidence, units_dir='units'):
    """唯一的登记写入口：校验 → 合并进 ``verify_config.json`` → 原子回写。

    登记的是**机器扫不出来**的印面事实，所以三件事必须机械地成立，否则拒绝：
    页在本章扫描区间内、该号**尚未**被 OCR 扫到（否则登记多余）、该号在单元里
    **确实存在**（否则一条「印面确证」会把真缺失的 MISSING 永久掩盖）。
    """
    if len((evidence or '').strip()) < 10:
        return 2, 'evidence 太短（<10 字）：须写明印面所见，登记不是占位符'
    bs = os.path.join(extract, 'book_structure')
    fp = os.path.join(bs, 'ch%d.json' % ch)
    if not os.path.exists(fp):
        return 2, '章契约不存在：%s' % fp
    with open(fp, encoding='utf-8') as f:
        c = json.load(f)
    lo, hi = int(c.get('page_start', 1)) - 1, int(c.get('page_end', 1)) + 2
    if not (lo <= page <= hi):
        return 2, '页码 %d 不在 ch%d 扫描区间 [%d, %d] 内' % (page, ch, lo, hi)
    strict = {}
    for j in glob.glob(os.path.join(bs, 'ch*.json')):
        m = re.search(r'ch(\d+)', os.path.basename(j))
        if not m:
            continue
        try:
            with open(j, encoding='utf-8') as f:
                cc = json.load(f)
            strict[int(m.group(1))] = set(range(int(cc.get('page_start', 1)),
                                               int(cc.get('page_end', 1)) + 1))
        except Exception:
            continue
    foreign = set().union(*[s for k, s in strict.items() if k != ch]) if strict else set()
    pr = printed_heads(extract, ch, c.get('page_start', 1), c.get('page_end', 1), foreign)
    if ex in pr:
        return 2, ('ch%d Exercise %d 印面已能机械扫到（extract p%d），登记多余'
                   % (ch, ex, pr[ex]))
    md = md_heads(os.path.join(bs, units_dir, 'ch%d' % ch))
    if ex not in md:
        return 2, ('ch%d Exercise %d 单元里没有：先回补单元，登记只会把真 MISSING 永久掩盖'
                   % (ch, ex))

    cfg_fp = os.path.join(extract, 'verify_config.json')
    cfg = _load_cfg(extract)
    holder = cfg
    if not isinstance(cfg.get(ATTEST_KEY), list):
        for grp in ('ch', 'appendix', 'supplement'):
            node = cfg.get(grp)
            if isinstance(node, dict):
                holder = node
                break
    ledger = holder.get(ATTEST_KEY)
    if not isinstance(ledger, list):
        ledger = []
    for e in ledger:
        if isinstance(e, dict) and str(e.get('ch')) == str(ch) and \
                str(e.get('ex')) == str(ex):
            return 2, 'ch%d Exercise %d 已登记（页 %s）：改判须先人工重核印面' % (
                ch, ex, e.get('page'))
    entry = {'ch': str(ch), 'ex': int(ex), 'page': int(page),
             'evidence': evidence.strip(),
             'registered_at': time.strftime('%Y-%m-%d %H:%M:%S')}
    ledger.append(entry)
    holder[ATTEST_KEY] = ledger
    text = json.dumps(cfg, ensure_ascii=False, indent=2)
    old = ''
    if os.path.exists(cfg_fp):
        with open(cfg_fp, encoding='utf-8') as f:
            old = f.read()
    if '\r\n' in old:
        text = text.replace('\n', '\r\n')
    tmp = cfg_fp + '.tmp'
    with open(tmp, 'w', encoding='utf-8', newline='') as f:
        f.write(text)
    os.replace(tmp, cfg_fp)
    return 0, '已登记 ch%d Exercise %d（印面页 %d）' % (ch, ex, page)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('extract')
    ap.add_argument('chapters', nargs='*', type=int)
    ap.add_argument('--units-dir', default='units')
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--json', action='store_true')
    ap.add_argument('--attest', metavar='CH:EX',
                    help='登记一处人工印面确证（须同时给 --page/--evidence）')
    ap.add_argument('--page', type=int)
    ap.add_argument('--evidence', default='')
    a = ap.parse_args()

    if a.attest:
        if not a.page:
            print('--attest 须同时给 --page N（印面目视所在页）')
            return 2
        try:
            ch_s, ex_s = a.attest.split(':')
            code, msg = write_attestation(a.extract, int(ch_s), int(ex_s),
                                          a.page, a.evidence, a.units_dir)
        except ValueError:
            code, msg = 2, '--attest 形如 CH:EX'
        print(msg)
        return code

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
    attested_all = attested_printed(a.extract)
    rows = []
    for ch, c, fp in contracts:
        if a.chapters and ch not in a.chapters:
            continue
        foreign = set().union(*[s for k, s in strict.items() if k != ch]) if strict else set()
        pr = printed_heads(a.extract, ch, c.get('page_start', 1), c.get('page_end', 1), foreign)
        att = attested_all.get(ch, {})
        # 印面真值 = OCR 扫到 ∪ 人工坐实（后者只能来自渲染页目视，见 --attest 校验）
        printed = merge_printed(pr, att)
        att_redundant = sorted(set(att) & set(pr))
        md = md_heads(os.path.join(bs, a.units_dir, 'ch%d' % ch))
        missing = sorted(n for n in printed if n not in md)
        phantom = sorted(n for n in md if n not in printed)
        rows.append({
            'ch': ch, 'printed': sorted(printed), 'md': sorted(md),
            'missing': [(n, printed[n]) for n in missing], 'phantom': phantom,
            'attested': sorted(att), 'attested_redundant': att_redundant,
            'ocr_empty': not printed and bool(md),
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
                if isinstance(p, tuple):
                    print('     - ch%d Exercise %d 疑似整条缺失，印面经人工坐实（extract %s）'
                          % (r['ch'], n, p[0]))
                else:
                    print('     - ch%d Exercise %d 疑似整条缺失，印面在 extract p%d'
                          % (r['ch'], n, p))
            for n in r['attested']:
                print('     * ch%d Exercise %d 印面靠人工确证（OCR 未扫到标题行）'
                      % (r['ch'], n))
            for n in r['attested_redundant']:
                print('     ! ch%d Exercise %d 登记已多余：OCR 如今能机械扫到该标题行，'
                      '人工重核后可从 exercise_printed_attested 删除' % (r['ch'], n))

    n_missing = sum(len(r['missing']) for r in rows)
    n_empty = sum(1 for r in rows if r['ocr_empty'])
    n_att = sum(len(r['attested']) for r in rows)
    n_red = sum(len(r['attested_redundant']) for r in rows)
    print('SUMMARY missing=%d phantom=%d ocr-empty-chapters=%d attested=%d redundant=%d'
          % (n_missing, sum(len(r['phantom']) for r in rows), n_empty, n_att, n_red))
    if a.strict and n_missing:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
