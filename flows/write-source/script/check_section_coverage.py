"""check_section_coverage.py — 印面目录（TOC）vs 契约/单元「节」覆盖审计（建议性）

背景：结构阶段的节节点靠 OCR 页内粗体标题识别。扫描书（无文字层）里这些标题**常被 OCR
整块漏掉**（实测 Iwaniec–Kowalski GTM207 的 §4.3 "The Poisson summation formula" 在印面
p.69 明晃晃地印着，OCR 却没抓到该块），于是该节在契约里根本没有节点 → 没有 section 单元
→ 合并 md 里既没有节标题、拆分也不会单独成文件。内容多半被并入相邻单元（所以 verify 的
D 层「契约↔单元对账」看不见），而节结构信息静默丢失。

真值来源不是正文页 OCR，而是**书首目录页**：TOC 把每节的 `N.M 标题 页码` 印在同一块里，
OCR 命中率高得多，且可与正文页码交叉验证。

判据：
  1) 从含 "CONTENT" 的前置页解析形如 `N.M. <Title> <page>` 的条目（容忍 § 被 OCR 读成
     `$`/`S`/`§`、标题里的小数点粘连）；
  2) 从 `units/ch{N}/*section_*.md` 读已建节节点；
  3) MISSING = 目录有、单元无；EXTRA = 单元有、目录无（多为附录节 / 章内小节，仅提示）。

⚠ 已知假阳来源：`Chapter18.` 粘连会被读成 `1.8`——已用「前面不得是字母」+ 章号白名单过滤。
默认 exit 0；`--strict` 时 MISSING 非空 exit 1。本脚本不改写任何文件。
"""
import argparse
import glob
import json
import os
import re
import sys

TOC_HINT = re.compile(r'CONTENTS?|TABLE\s*OF\s*CONT')
# 跨页时目录页眉会被 OCR 插在条目中间（实测 "…238 TABLE OF CONTENTS vii $9.6…"），先剥掉
RUNNING_HEAD = re.compile(r'(?i)\b(?:table\s+of\s+)?contents\s+[ivxlcdm]{1,9}(?=\s|$)')
# 目录条目两类 token：
#   章条目 `Chapter N.`（OCR 常把 chapter 读成 Chaptcr/chapter 等，故 `chap\w{0,4}` 宽容）
#   节条目 `§N.M`：印面的 § 被 OCR 读成 `$`/`S`/`s`，且常与数字粘连（`S1.1.Notation`）。
#   标记字符**必须并入匹配**，否则「前面不得是字母」的回看会把整章条目全丢掉；标记也是
#   「这是一条目录条目」的强证据（标题里出现的 "Theorem 26.2" 就没有标记）。
TOK = re.compile(r'(?i)(chap\w{0,4}\s*(\d{1,2})\b)|(?:[$§]|(?:(?<=\d)|(?<=\s))S)\s*(\d{1,2})\.(\d{1,2})(?!\d)')
MARKER = '$§S'
SEC_UNIT = re.compile(r'section_(\d+)_(\d+)')


def toc_pages(extract, limit=20):
    """页码升序返回前置目录页号（含 'CONTENTS' 且不含正文特征）。"""
    out = []
    for pg in range(1, limit + 1):
        fp = os.path.join(extract, 'page_%03d.json' % pg)
        if not os.path.exists(fp):
            continue
        try:
            with open(fp, encoding='utf-8') as f:
                d = json.load(f)
        except Exception:
            continue
        t = ' '.join((b.get('text') or '') for b in (d.get('text') or []))
        if TOC_HINT.search(t.upper()):
            out.append(pg)
    return out


def page_texts_joined(extract, pages):
    parts = []
    for p in pages:
        fp = os.path.join(extract, 'page_%03d.json' % p)
        if not os.path.exists(fp):
            continue
        with open(fp, encoding='utf-8') as f:
            d = json.load(f)
        parts.append(' '.join((b.get('text') or '') for b in (d.get('text') or [])))
    return RUNNING_HEAD.sub(' ', re.sub(r'\s+', ' ', ' '.join(parts)))


def parse_toc(text):
    """{（章, 节): (标题, 印面页码)}。带 § 标记的条目直接采信；无标记的不采信。"""
    out = {}
    toks = list(TOK.finditer(text))
    for i, m in enumerate(toks):
        if m.group(2):
            continue
        if m.group(0)[0] not in MARKER:
            continue
        a, b = int(m.group(3)), int(m.group(4))
        # 条目正文 = 本 token 到下一个 token（章/节）之间；页码 = 段尾最后一段数字，
        # 其后的非数字是下一条目的 §（OCR 成 `$`）
        seg = text[m.end(): toks[i + 1].start() if i + 1 < len(toks) else len(text)]
        # 书末条目（附录 `N.M` 字母节 / Bibliography / Index）不是数字节，但必须**切断**，
        # 否则上一条目的页码会读到它们的数字（实测 §4.6 读到附录页 86、§26.5 读到 Index 611）
        seg = re.split(r'(?i)[\s$§S]*(?:\d{1,2}\.[A-Za-z]\b|\b(?:bibliography|index|preface)\b)', seg)[0]
        pm = re.search(r'(\d{1,3})\D*$', seg.rstrip())
        if not pm:
            continue
        # 只剥标点噪声：`S`/`s` 已在 token 里被当标记吃掉，若混进剥离集会把真标题截尾
        # （实测 "Generating series 10" 被剥成 "Generating serie"）
        title = seg[:pm.start()].strip(' .,·~—-$§')
        pg = int(pm.group(1))
        if not (1 <= b <= 40 and 1 <= pg <= 900 and len(title) >= 2):
            continue
        out.setdefault((a, b), (title[:70], pg))
    return out


def toc_entries(extract, pages):
    return parse_toc(page_texts_joined(extract, pages))


def unit_sections(units_dir):
    out = set()
    for fp in glob.glob(os.path.join(units_dir, 'ch*', '*section_*.md')):
        ch = int(re.search(r'ch(\d+)', os.path.basename(os.path.dirname(fp))).group(1))
        m = SEC_UNIT.search(os.path.basename(fp))
        if m:
            out.add((ch, int(m.group(2))))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('extract')
    ap.add_argument('--units-dir', default='book_structure/units')
    ap.add_argument('--strict', action='store_true')
    a = ap.parse_args()

    pages = toc_pages(a.extract)
    if not pages:
        print('NO-TOC: 前置页里没找到目录（本书无目录页或 OCR 未命中）→ 本审计不适用')
        return 0
    toc = toc_entries(a.extract, pages)
    have = unit_sections(os.path.join(a.extract, a.units_dir))
    missing = sorted(k for k in toc if k not in have)
    extra = sorted(k for k in have if k not in toc)

    print('TOC pages: %s  entries=%d  unit sections=%d' % (pages, len(toc), len(have)))
    for k in missing:
        print('  MISSING  §%d.%d  "%s"  printed p.%d' % (k[0], k[1], toc[k][0][:60], toc[k][1]))
    for k in extra:
        print('  EXTRA    §%d.%d  (单元有、目录未扫到：附录/小节或 OCR 噪声，人工确认)' % k)
    print('SUMMARY missing=%d extra=%d' % (len(missing), len(extra)))
    return 1 if (a.strict and missing) else 0


if __name__ == '__main__':
    sys.exit(main())
