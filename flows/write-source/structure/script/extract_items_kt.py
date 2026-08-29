"""extract_items_kt.py — K&T《A First Course in Stochastic Processes》专用提取/骨架。

该书结构（Karlin & Taylor, 2nd ed.）：
  - 节 (section):    "N. Title"        （章内从 1 重编）
  - 子节 (subsection): "X. TITLE"        （字母 A,B,C…，位于某节之下）
  - 编号陈述:         "Theorem 1.1." / "Definition 5.1." / "Lemma 5.1." /
                     "Corollary 4.1." / "Proposition 7.2." / "Remark 1.2." /
                     "Example 1.1." 等（章内 Number.Number）
  - 章末整块:         "Problems" / "Notes" / "References" / "Exercises" /
                     "Exercises and Complements" / "Complements" —— 习题/文献块，省略。

输出（写入 <extract_dir>）：
  ch{N}_extract.json : {"sections":[(num,title,page)], "statements":[(label,num,page,text)]}

用法:
  python extract_items_kt.py <extract_dir> <ch> <start> <end>
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
import ch_extract
import chapter_map
from page_json import PageJson

import json
import os
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

LABELS = ['Theorem', 'Definition', 'Lemma', 'Corollary', 'Proposition',
          'Remark', 'Example']

NUM_STMT = re.compile(
    r'^(Theorem|Definition|Lemma|Corollary|Proposition|Remark)\s+'
    r'(\d{1,2}\.\d{1,2})\.?\s*(.*)$')
# 例子：顺序整数编号 "Example 1." / "Example 2."（OCR 常把 1 误读为 l/I）
EXAMPLE_INT = re.compile(r'^Example\s+([0-9lI]{1,2})\.\s*(.*)$')
EXAMPLE_INT_NORM = str.maketrans('lI', '11')
# 不编号的陈述头（仅 "Example." / "EXAMPLE" / "Definition." 等无号头），作为必录项
BARE_STMT = re.compile(
    r'^(Theorem|Definition|Lemma|Corollary|Proposition|Remark|Example)'
    r'[\.\:\s]+([A-Z].{0,80})$')
SEC = re.compile(r'^(\d{1,2})\s*[:．\.]\s+([A-Z][A-Za-z].{2,72})$')
LETSUB = re.compile(r'^([A-Z])\.\s+([A-Za-z].{2,72})$')
ENDBLOCK = re.compile(
    r'^(Problems|Notes|References|Exercises and Complements|Exercises|'
    r'Complements)\b')
# 字母子节第二词若是这些句子词，判定为普通句子而非子节标题
SENTENCE_WORDS = {'we', 'the', 'to', 'of', 'is', 'are', 'was', 'were', 'this',
                  'that', 'these', 'those', 'following', 'prepared', 'prove',
                  'let', 'suppose', 'consider', 'now', 'note', 'see', 'if',
                  'when', 'then', 'a', 'an', 'it', 'in', 'on', 'for', 'by'}
# 练习题/题干常以这些动词开头，非节标题
PROBLEM_VERBS = {'determine', 'consider', 'show', 'prove', 'find', 'compute',
                 'let', 'suppose', 'calculate', 'given', 'assume', 'verify',
                 'construct', 'explain', 'discuss', 'what', 'which', 'how',
                 'derive', 'evaluate', 'estimate', 'does', 'do', 'is', 'are'}

# 过滤：书目/文献行如 "1. Taylor, Howard M.," 或 "2. Author (year)."
BIBLIO = re.compile(r'^\d{1,2}\.\s+[A-Z][a-z]+,\s')


def lines_of(page_json):
    for it in page_json.get('text', []):
        for ln in (it.get('text') or '').split('\n'):
            yield ln.strip()


def extract(extract_dir, ch, start, end):
    # 读取本章标题，用于剔除页眉（running header = "N. <章标题>"）
    chapter_title = ''
    cm_path = os.path.join(extract_dir, 'chapter_map.json')
    if os.path.exists(cm_path):
        try:
            cm = chapter_map.load_chapter_map_raw(cm_path)
            v = cm.get(str(ch)) or cm.get(ch)
            if isinstance(v, dict):
                chapter_title = (v.get('name_en') or v.get('name') or '').lower()
        except Exception:
            pass

    def norm(s):
        return re.sub(r'[^a-z0-9]', '', s.lower())

    blocks = []
    for p in range(start, end + 1):
        fp = os.path.join(extract_dir, 'page_%03d.json' % p)
        if not os.path.exists(fp):
            continue
        with open(fp, encoding='utf-8') as fh:
            d = PageJson.load(os.path.join(extract_dir, 'page_%03d.json' % p)).data
        for t in d.get('text', []):
            txt = (t.get('text') or '').strip()
            if not txt:
                continue
            poly = t.get('poly', [])
            y = poly[1] if poly and len(poly) >= 8 else 0
            blocks.append((p, y, txt))
    blocks.sort(key=lambda x: (x[0], x[1]))

    raw_secs = []        # (num, title, page, kind)  kind in {'SEC','SUB'}
    statements = []      # (label, num, page, text)
    in_endblock = False
    cur_sec = None
    seen_stmt = set()

    for p, y, txt in blocks:
        if ENDBLOCK.match(txt):
            in_endblock = True
        if in_endblock:
            continue

        # 节标题 "N. Title"
        m = SEC.match(txt)
        if m and not BIBLIO.match(txt) and len(txt) < 75:
            num = m.group(1)
            title = m.group(2).strip()
            raw_secs.append((num, title, p, 'SEC'))
            cur_sec = num
            continue

        # 字母子节 "X. TITLE" —— 记作 SUB。原书用纯字母标号（如
        # "A. JOINT DISTRIBUTION FUNCTIONS"），父节靠位置确定；summary
        # 只写 "§A"，不投影父节号（尊重原书：不给小节编造 "N.A" 复合编号）。
        m = LETSUB.match(txt)
        if m and len(txt) < 75:
            title = m.group(2).strip()
            # 第二词若是句子词则视为普通句子，跳过
            words = title.split()
            second = words[0].lower() if words else ''
            if second in SENTENCE_WORDS:
                continue
            letter = m.group(1)              # 纯字母标号 A/B/C…
            num = letter                     # 不拼父节号 → "A" 而非 "1.A"
            # 同章不同父节都可能以 A 起头（1.A / 2.A …），按 (父节,字母)
            # 去重，避免纯字母 key 跨父节碰撞丢小节。
            raw_secs.append((num, title, p, 'SUB', cur_sec or ''))
            continue

        # 编号陈述 "Theorem 1.1."
        m = NUM_STMT.match(txt)
        if m:
            label = m.group(1)
            num = m.group(2)
            text = (m.group(3) or '').strip()
            key = (label, num)
            if key not in seen_stmt:
                seen_stmt.add(key)
                statements.append((label, num, p, text[:90]))
            continue

        # 例子顺序整数 "Example 1." / "Example 2."（OCR 1→l/I 归一）
        m = EXAMPLE_INT.match(txt)
        if m:
            num = m.group(1).translate(EXAMPLE_INT_NORM)
            text = (m.group(2) or '').strip()
            key = ('Example', num, p)
            if key not in seen_stmt:
                seen_stmt.add(key)
                statements.append(('Example', num, p, text[:90]))
            continue

        # 无号陈述头（如 "Example." "EXAMPLE" 起头的一段）
        m = BARE_STMT.match(txt)
        if m:
            label = m.group(1)
            title = m.group(2).strip()
            key = ('BARE', label, title[:30], p)
            if key not in seen_stmt:
                seen_stmt.add(key)
                statements.append((label, '?', p, title[:90]))
            continue

    # ---- 清理 + 去重 ----
    sections = []
    seen_sec_num = set()      # SEC 去重（数字节号全局唯一）
    seen_subsec = set()       # SUB 去重（按 (父节,字母)，纯字母 key 跨父节会撞）
    for entry in raw_secs:
        num, title, p, kind = entry[:4]
        parent = entry[4] if len(entry) > 4 else ''
        if kind == 'SEC':
            nt = norm(title)
            if chapter_title and (nt == norm(chapter_title)
                                  or nt in norm(chapter_title)
                                  or norm(chapter_title) in nt):
                continue  # running header
            first = title.split()[0].lower() if title.split() else ''
            if first in PROBLEM_VERBS:
                continue
            if '?' in title or len(title) > 60:
                continue
            if num in seen_sec_num:
                continue
            seen_sec_num.add(num)
            sections.append((num, title, p, 'SEC'))
        else:  # SUB
            key = (parent, num)
            if key in seen_subsec:
                continue
            seen_subsec.add(key)
            sections.append((num, title, p, 'SUB'))

    return {'sections': sections, 'statements': statements}


def write_outputs(extract_dir, ch, data):
    suffix = '%d' % ch if isinstance(ch, int) else str(ch)
    out_json = os.path.join(extract_dir, 'ch%s_extract.json' % suffix)
    ch_extract.ChExtract(data=data).dump(out_json)

    return out_json


def main():
    extract_dir = sys.argv[1]
    ch = sys.argv[2]
    start = int(sys.argv[3])
    end = int(sys.argv[4])
    data = extract(extract_dir, ch, start, end)
    oj = write_outputs(extract_dir, int(ch) if ch.isdigit() else ch, data)
    print('ch%s -> sections=%d statements=%d'
          % (ch, len(data['sections']), len(data['statements'])))
    print('  wrote', os.path.basename(oj))


if __name__ == '__main__':
    main()
