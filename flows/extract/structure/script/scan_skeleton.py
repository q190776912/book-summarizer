"""scan_skeleton.py — 扫描原书某章的【真实结构骨架】（SEC/EXER 行）。

现主要作为 `build_structure.py` 的内部依赖（被 `import` 调用 `scan()` / `_mode_for_ordinal()`
供其拼装 `book_structure.json` 书对象）；其 standalone CLI 仅向 stdout 打印扫描结果（诊断用），不写任何文件。

为什么需要它
------------
抽取器产出的**裸条目键**只包含 verifier 的必备条目键，
它不含节标题、不含练习、不含条目的印刷标题。写章总结的 agent 若只拿到抽取器的裸条目键，
手上就没有「这一章到底有哪几节、每节有哪些条目和练习、按什么顺序排、每条印刷标题
叫什么」的权威清单 —— 于是必然出现：漏节、节序颠倒、条目丢标题、练习被随手归拢。

本脚本直接从 `page_*.json` 扫出这份清单，**按页码顺序**输出，作为写作时的结构契约：
骨架里有几节就必须写几节、顺序照抄、每个 ITEM 都要落地、印刷标题必须进标签；`EXER`（练习）行同样被扫描标记并纳入结构契约。

用法
----
    python scan_skeleton.py <extract_dir> [ch ...]

    # 全书
    python scan_skeleton.py D:/study/book/<书名>/_extract
    # 指定章
    python scan_skeleton.py D:/study/book/<书名>/_extract 1 2 3

    # 编号模式（three-level / two-level / cn）由 <extract_dir>/verify_config.json
    # 的 `ordinal` 字段自动判定，无需任何 --scheme 之类的命令行 override。
    # 小节（SEC）扫描则额外由 `section_depths` 驱动，采用「深度无关通用检测」：
    # 无论书里是 20.5 还是 20.5.1（甚至更深），只要是小节头（数字+非标签标题）
    # 就会被识别，不再受单一模式只能匹配固定深度所限。

输出
----
每行一条，形如（打印到 stdout，不落盘）：

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
cn（中文三级，标签在前，如 "定理1.4.1 ..."）：
    节   "1.5 行列式的计算"
    条目 "定理1.4.1 ..."（标签 + 章.节.号）
    练习 "习题 1.3"
"""
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
import chapter_map
from page_json import PageJson

import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')
from verify_config import (ORDINAL_DEPTH, ORDINAL_LANGUAGE_DEFAULT, ORDINAL_THREE_LEVEL,
                       ConfigLoader, ConfigError)

# 节标题：可带 Vakil 的可选标记（★ 被 OCR 成 + / * / x），标题也可能以单字母词开头
# （"3.5 A base of ..."），故只要求首字符大写、长度 4~72。
SEC_3 = re.compile(r'^(\d{1,2})\.(\d{1,2})\s+[+*x\u00d7\u2605\u2606]?\s*([A-Z].{3,72})$')
ITEM_3 = re.compile(r'^(\d{1,2})\.(\d{1,2})\.(\d{1,3})\.\s*(.{0,90})')
EXER_3 = re.compile(r'^(\d{1,2})\.(\d{1,2})\.([A-Z])\.\s*(.{0,90})')

SEC_2 = re.compile(r'^(\d{1,2})\s+[+*x\u00d7\u2605\u2606]?\s*([A-Z].{3,72})$')
ITEM_2 = re.compile(r'^(\d{1,2})\.(\d{1,3})\.\s*(.{0,90})')
EXER_2 = re.compile(r'^(\d{1,2})\.([A-Z])\.\s*(.{0,90})')

# Chinese-scheme section headings — patterns shared from lib/regexlib.py
from lib.regexlib import SEC_CN, SECBARE_CN, SECGLUE_CN
ITEM_CN = re.compile(
    r'^(?:定理|定义|引理|推论|命题|性质|例|注|表|图)\s*[（(]?(\d{1,2})[\.\．·。](\d{1,2})[\.\．·。](\d{1,3})[）)]?(?!\d)\s*(.{0,90})')
BARE_CN = re.compile(r'^[（(](\d{1,2})[\.\．·。](\d{1,2})[\.\．·。](\d{1,3})[）)](?!\d)\s*(.{0,90})')
EXER_CN = re.compile(r'^习题\s*(\d{1,2})[\.\．·](\d{1,2})')

# ---------------------------------------------------------------------------
# Universal, DEPTH-AGNOSTIC section-header detection.
#
# The per-mode SEC_* regexes above can only match ONE fixed depth (SEC_2 -> a
# single chapter number; SEC_3 -> exactly two components).  That misses
# MIXED-depth and deeper subsections (e.g. Koopman's `20.5` AND `20.5.1`) and
# silently forces every book into at most two section levels.  The detector
# below catches genuine section headers of ANY declared depth, independent of
# the item-numbering style, so a book may number its items one way (EN two-
# level `Theorem 20.4`) yet nest its sections arbitrarily deep.
#
# A genuine section header is a dotted number (>= 2 components — the chapter
# number alone is the chapter itself, not a section) followed by a NON-LABEL
# TITLE.  It deliberately excludes labeled items (`Theorem 20.4`), formula
# numbers (`(20.53)`), figure/table labels (`Figure 20.1`), and bare numbers
# without a title.  `scan()` activates it (instead of the mode's SEC regex)
# whenever the book declares `section_types` (depth derived via SECTION_TYPE_DEPTH).
# ---------------------------------------------------------------------------
_SEC_SEP_RE = re.compile(r'[.\-–·/．－〜]')
_SEC_HEAD_RE = re.compile(r'^(?:§|8)?\s*(\d+(?:[.\-–·/．－〜]\d+)*)')
_SEC_TITLE_LABEL_RE = re.compile(
    r'(定义|定理|引理|命题|推论|例|公理|练习|评注|准则|图|表|'
    r'Definition|Theorem|Lemma|Proposition|Corollary|Example|Axiom|Exercise|'
    r'Remark|Figure|Fig|Table)')


def _section_header_info(ln, ch=None, depths=None, max_depth=6):
    """Return ``(num_str, depth, title)`` for a genuine section header, else
    None.

    `ch` restricts to headers whose first numeric component == `ch` (used when
    scanning inside a chapter).  `depths` (set[int]) restricts to the declared
    section depths (>= 2); when None, any depth in ``[2, max_depth]`` is
    accepted.  `max_depth` bounds the hierarchy search (default 6 = chapter +
    5 nested levels).
    """
    m = _SEC_HEAD_RE.match(ln)
    if not m:
        return None
    comps = [x for x in _SEC_SEP_RE.split(m.group(1)) if x]
    if len(comps) < 2 or len(comps) > max_depth:
        return None
    if ch is not None and comps[0].isdigit() and int(comps[0]) != ch:
        return None
    depth = len(comps)
    if depths is not None and depth not in depths:
        return None
    rest = ln[m.end():].lstrip()
    if not rest or not rest[0].isalnum():
        return None  # number with no following title -> not a header
    title = rest[:12]
    if _SEC_TITLE_LABEL_RE.search(title):
        return None  # labeled item / figure / table, not a section
    if not re.search(r'[A-Za-z一-鿿]', title):
        return None
    # A genuine section title is Title-Case / Han / starts with a digit — reject
    # prose that begins with a lowercase word (e.g. "20.6 and it is stated...",
    # "14-1-0359 and W911NF..." grant numbers glued to text).  Only a leading
    # lowercase ASCII letter is rejected; Han / digit / uppercase are kept.
    first = next((c for c in rest if c.isalnum()), None)
    if first is not None and 'a' <= first <= 'z':
        return None
    return m.group(1), depth, rest.strip()


# Map an integer `ordinal` (config) to scan_skeleton's parsing mode.
# Returns one of 'three-level' (default western 3-level), 'two-level'
# (western/EN/GM/Fraleigh 2-level), or 'cn' (Chinese 3-level).
def _mode_for_ordinal(ordinal, language=None):
    o = int(ordinal)
    depth = ORDINAL_DEPTH.get(o, ORDINAL_THREE_LEVEL)
    # Explicit book `language` (from verify_config.json) wins: a three-level
    # EN book (e.g. Vakil, ordinal=8 / 3 + language=en) numbers western-style
    # (number-first, N.S.item) and must use the `three-level` parser, NOT the
    # `cn` parser (which expects Chinese labels like 定义1.4.1).
    if language == 'en':
        return 'three-level' if depth >= 3 else 'two-level'
    if language == 'cn':
        return 'cn'
    # No explicit language: fall back to the type's default language.
    lang = ORDINAL_LANGUAGE_DEFAULT.get(o, 'cn')
    if lang == 'cn':
        return 'cn'
    if depth >= 3:
        return 'three-level'
    return 'two-level'


def lines_of(page_json):
    for it in page_json.get('text', []):
        for ln in (it.get('text') or '').split('\n'):
            yield ln.strip()


def scan(extract_dir, ch, start, end, mode, section_depths=None):
    rows = []
    # Depth-agnostic section detection (config-driven).  When the book declares
    # `section_depths`, we use the universal detector for SEC rows (it catches
    # genuine section headers at ANY declared depth, including mixed depth like
    # 20.5 + 20.5.1) and skip the mode's single-depth SEC regex.  Item/exercise
    # detection still uses the per-mode regexes below.  When `section_depths`
    # is absent (legacy / no config) we fall back to the old per-mode SEC regex
    # for back-compatibility.
    depths_set = (set(d for d in section_depths if isinstance(d, int) and d >= 2)
                  if section_depths else None)
    # When the book declares `section_depths` we use the universal (depth-
    # agnostic) detector for SEC rows and must NOT also run the mode's single-
    # depth SEC regex — that regex would re-emit sections (duplicate) or, in
    # two-level mode, emit the chapter title "20" as a phantom section.
    use_universal_sec = depths_set is not None
    for p in range(start, end + 1):
        fp = os.path.join(extract_dir, 'page_%03d.json' % p)
        if not os.path.exists(fp):
            continue
        with open(fp, encoding='utf-8') as fh:
            d = PageJson.load(os.path.join(extract_dir, 'page_%03d.json' % p)).data
        for ln in lines_of(d):
            ln = ln.rstrip('$').strip()
            if not ln:
                continue
            # --- universal, depth-agnostic section detection ---
            if depths_set is not None:
                sec = _section_header_info(ln, ch=ch, depths=depths_set)
                if sec is not None:
                    num_str, _depth, title = sec
                    rows.append((p, 'SEC', num_str, title))
                    continue
            if mode == 'two-level':
                m = SEC_2.match(ln)
                if not use_universal_sec and m and int(m.group(1)) == ch and not m.group(2).endswith('.'):
                    rows.append((p, 'SEC', m.group(1), m.group(2).strip()))
                    continue
                m = EXER_2.match(ln)
                if m and int(m.group(1)) == ch:
                    rows.append((p, 'EXER', '%s.%s' % m.group(1, 2), m.group(3).strip()))
                    continue
                m = ITEM_2.match(ln)
                if m and int(m.group(1)) == ch:
                    rows.append((p, 'ITEM', '%s.%s' % m.group(1, 2), m.group(3).strip()))
            elif mode == 'cn':
                m = SEC_CN.match(ln)
                if not use_universal_sec and m and int(m.group(1)) == ch:
                    if m.group(1).startswith('0') or m.group(2).startswith('0') or int(m.group(2)) == 0:
                        continue
                    rows.append((p, 'SEC', '%s.%s' % m.group(1, 2),
                                 ln[m.end(2):].lstrip(' \u00a7.．·。').strip()))
                    continue
                m = SECBARE_CN.match(ln)
                if not use_universal_sec and m and int(m.group(1)) == ch:
                    if m.group(1).startswith('0') or m.group(2).startswith('0') or int(m.group(2)) == 0:
                        continue
                    rows.append((p, 'SEC', '%s.%s' % m.group(1, 2), ''))
                    continue
                m = SECGLUE_CN.match(ln)
                if not use_universal_sec and m and int(m.group(1)) == ch:
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
                if not use_universal_sec and m and int(m.group(1)) == ch and not m.group(3).endswith('.'):
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

    if not args:
        print(__doc__)
        return 2
    extract_dir = args[0]
    want = [int(x) for x in args[1:]]

    # Numbering mode is auto-detected from the book's verify_config.json
    # (the single source of truth for `ordinal`); no direct file read / CLI
    # override. We reuse the same ConfigLoader gate as verify_chapter.py so the
    # mandatory book-config rule (H) is enforced consistently: file absent ->
    # warning + default ordinal=3 (back-compat); file present but no ordinal ->
    # ConfigError (exit 2). Either way `loader.book.primary_type` is a valid int
    # default (the v2 `ordinal` is a List[GroupConfig]; primary_type is its int code).
    cfg_path = os.path.join(extract_dir, 'verify_config.json')
    try:
        loader = ConfigLoader(extract_dir,
                              os.path.dirname(extract_dir.rstrip('/')) or extract_dir)
        loader.require_complete()
        ordinal = loader.book.primary_type
    except ConfigError as e:
        print(e)
        return 2
    mode = _mode_for_ordinal(ordinal, loader.book.language)
    section_depths = loader.book.section_depths or None

    cm_path = os.path.join(extract_dir, 'chapter_map.json')
    cm = chapter_map.load_chapter_map_raw(cm_path)
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
        rows = scan(extract_dir, ch, start, end, mode, section_depths=section_depths)
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
        secs = []
        for p, kind, num, title in rows:
            if kind == 'SEC':
                secs.append(num)
            print('%-5s %-11s p%-4d %s' % (kind, num, p, title))
        n_item = sum(1 for r in rows if r[1] == 'ITEM')
        n_ex = sum(1 for r in rows if r[1] == 'EXER')
        print('ch%-3d | secs=%s items=%d exercises=%d'
              % (ch, secs, n_item, n_ex))
    return 0


if __name__ == '__main__':
    sys.exit(main())
