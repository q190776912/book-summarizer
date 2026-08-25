
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
import manual_overrides_chN
import chapter_map
from page_json import PageJson

import os, sys

import json, re, os, sys

from extract_items_en import extract_items_en
from lib.regexlib import SEP_TIGHT, SEP_NUMERIC
from verify_config import (ORDINAL_TWO_LEVEL, ORDINAL_THREE_LEVEL,
                        ORDINAL_DEPTH, BookConfig, GroupConfig)

# ---------------------------------------------------------------------------
# Label word -> semantic label (canonical CN).  Case-insensitive so English
# keywords captured lowercase by OCR (e.g. "Zorn's lemma") still map correctly.
# Priority: 练习/习题 > 例/example > 定义/definition > 定理/theorem >
# 引理/lemma > 推论/corollary > 命题/proposition.
# ---------------------------------------------------------------------------
_LABEL_MAP = [
    (r'练习|习题', '练习'),
    (r'例|example', '例'),
    (r'定义|definition', '定义'),
    (r'定理|theorem', '定理'),
    (r'引理|lemma', '引理'),
    (r'推论|corollary', '推论'),
    (r'命题|proposition', '命题'),
]


def _label_from_raw(raw):
    raw = (raw or '').lower()
    for pat, lab in _LABEL_MAP:
        if re.search(pat, raw):
            return lab
    return 'uncat'


def _first_label_pos(s):
    """Return the label of the type word closest to the START of s (i.e.
    closest to the item number), or None. Used to prefer an item's own
    heading label over a type word merely mentioned later as a cross-reference.
    """
    best = None
    for pat, lab in _LABEL_MAP:
        for mm in re.finditer(pat, s, re.IGNORECASE):
            if best is None or mm.start() < best[0]:
                best = (mm.start(), lab)
    return best[1] if best else None


def _add_match(m, txt, p, i, all_blocks, raw_matches, active_section_label, chapter, label_re, cite_re, cite_re_tail, num_re):
    """Helper: process a regex match and append to raw_matches if valid."""
    ch_num = int(m.group(1))
    if ch_num != chapter:
        return
    sec = int(m.group(2))
    num = int(m.group(3))
    if sec > 15 or num > 50:
        return
    key = f"{ch_num}.{sec}-{num}"
    before = txt[max(0, m.start()-25):m.start()]
    after = txt[m.end():m.end()+50]

    key_esc = re.escape(m.group())

    # 0. Citation words directly before the number (same OCR block)
    if cite_re.search(before):
        return
    # 0b. Citation words at the END of the PREVIOUS OCR block. OCR often splits a
    #     sentence such as "因此，据" | "9.5-1知P是一个投影" into two blocks, so the
    #     cite word ("据") sits at the tail of the prior block, one block away.
    #     但若当前编号是「独立真条头」（位于块首且其后紧跟定义陈述，而非引用语言），
    #     则前块尾的引用词只是上一句的完整结尾（如 "…Cf. 2.6-2."），不应误杀本块
    #     的真定义（2.7-4 "Zero operator" 因此被误删）。故仅当当前匹配本身是交叉
    #     引用（编号在块中部，或编号后紧跟引用语言）时才跳过。
    if i > 0:
        prev_tail = all_blocks[i-1][2][-15:].strip()
        if cite_re_tail.search(prev_tail):
            _after0b = txt[m.end():m.end() + 30].lstrip()
            _is_xref = (m.start() > 0) or re.match(
                r'(states?|shows?|proves?|implies?|follows?|知|见|据|由|根据|参考|参见)\b',
                _after0b, re.IGNORECASE)
            if _is_xref:
                return

    # 0c. Parenthesized number -> cross-reference, NOT an item definition.
    #     A genuine Kreyszig heading never wraps its own number in parentheses
    #     (it writes "8.4-2 Lemma (Ranges).", never "(8.4-2) Lemma"). Forms like
    #     "(8.3-4, below)" or "(Lemma 8.4-2)" are references where the citation
    #     cue sits AFTER the number, so the before-only cite_re (step 0) cannot
    #     catch them. Skip when an opening paren sits within 12 chars BEFORE the
    #     number AND a closing paren within 12 chars AFTER it (number enclosed).
    #     Genuine "N.S-N Lemma (Title)" headings have the '(' only AFTER the
    #     number, so they are preserved. "(谱定理) 9.9-1" has its ')' BEFORE the
    #     number, so it is also preserved.
    _opn = txt.rfind('(', 0, m.start());  _opn = _opn if _opn != -1 else txt.rfind('（', 0, m.start())
    if _opn != -1 and (m.start() - _opn) <= 12:
        _clo = txt.find(')', m.end());  _clo = _clo if _clo != -1 else txt.find('）', m.end())
        if _clo != -1 and (_clo - m.end()) <= 12:
            return

    # 1. A FULL label word (定理/定义/引理/推论/命题/例) immediately before the number,
    #    optionally separated by whitespace or parens (e.g. 定理4.3-1 / 定理(3.3-1) /
    #    （谱定理）9.9-1 / 定义2.1-7). It is a real item ONLY when the number starts the
    #    block or the block is a standalone label heading; otherwise it is a
    #    cross-reference. Forward direction only — a "NUMBER 标签" real header
    #    (e.g. "4.3-1 汉恩-巴拿赫定理") is left untouched so genuine items are never
    #    dropped. (Must match the full 2-char label word, not just 例/定/引/推/命,
    #    otherwise 定理4.3-1 slips through because 理 sits between 定 and the number.)
    local = txt[max(0, m.start()-8):m.end()+4]
    if re.search(r'(?:定理|定义|引理|推论|命题|例)[\s（）()]*' + key_esc, local):
        prefix = txt[:m.start()].strip()
        if re.match(r'^(?:定义|定理|引理|推论|命题|例)$', prefix) or prefix.startswith(m.group()):
            pass
        else:
            return

    # 2. Number sits inside a parenthetical span that lists TWO OR MORE numbered
    #    items -> it is an enumeration of references, not an item definition.
    #    e.g. "（4.5，4.6)"  "（变形4.3-1，4.3-2）"  "（7.5-3，7.5-4，7：5-5）"
    op = txt.rfind('（', 0, m.start());  op = op if op != -1 else txt.rfind('(', 0, m.start())
    cl = txt.find('）', m.end());        cl = cl if cl != -1 else txt.find(')', m.end())
    if op != -1 and cl != -1 and op < m.start() < cl:
        if len(num_re.findall(txt[op:cl+1])) >= 2:
            return

    # 3. Range marker with another number nearby (e.g. "例子（1.1-2到1.2-3）")
    after_ctx = txt[m.end():m.end()+40]
    if re.search(r'[例定引推]', before):
        if num_re.search(before) or num_re.search(after_ctx) or re.search(r'[到至～]', before + after_ctx):
            return

    # 3b. Cross-reference / fragment guard. A genuine item heading places the
    #     number at (or very near) the start of its OCR block. If the number is
    #     mid-block AND the text immediately before it contains a lowercase
    #     preposition/citation AND there is no type word and no inherited
    #     section label nearby, it is a cross-reference ("...in 3.4-5..." /
    #     "In Def. 4.7-1 we state ... Baire's theorem"), not an item
    #     definition — skip it. This prevents phantom items and the
    #     mis-classification they cause when nearby prose mentions a different
    #     type word (e.g. "Baire's theorem" flipping 4.7-1 to theorem).
    if m.start() > 0:
        _pre = txt[max(0, m.start() - 15):m.start()]
        _near = txt[max(0, m.start() - 12):m.end() + 12]
        _has_type = re.search(
            r'(?:定理|定义|引理|推论|命题|例|Definition|Theorem|Lemma|Corollary|Proposition|Example)',
            _near, re.IGNORECASE)
        if (not _has_type and not active_section_label and
                re.search(r'\b(in|to|of|by|for|with|that|this|as|at|from|into|onto)\b',
                          _pre, re.IGNORECASE)):
            return

    # 3c. 编号紧跟「引用动词 / 引用结构」→ 交叉引用（引用他人结论），不是本条目定义。
    #     仅在编号紧后方（去掉前导空白/标点后）的「起始位置」出现才算，避免误伤真
    #     定义（"2.6-6 Multiplication by t" 里的 "by t" 小写，不匹配）。
    #     真条头编号后是定义陈述（术语 / "(…)"），不会以 states/shows/we have/see/
    #     cf./below/above/as in 或 "by <大写专有名词>"（如 "by Banach"）开头。引用读作
    #     "Theorem 2.7-9 states that…" / "(cf. 2.7-9)" / "as in 2.7-9" /
    #     "4.7-3 … by Banach and Steinhaus"。这些绝不能成为条目，否则会把交叉引用
    #     页（章首页）当成定义页，污染 page_start 与总结内容。
    #     「by [A-Z]」必须大小写敏感（(?-i:)），否则 "by t"（乘法 by t）会被误判。
    _after_ref = txt[m.end():m.end() + 30].lstrip()
    if re.match(
        r'(states?|shows?|proves?|implies?|follows?)\s+that'
        r'|we\s+have'
        r'|see\s+(also\s+)?'
        r'|cf\.|below|above'
        r'|as\s+in'
        r'|by\s+(?-i:[A-Z])', _after_ref, re.IGNORECASE):
        return

    label = 'uncat'
    # 编号是否位于「块首附近」——这是「真条头」的位置特征。交叉引用/习题里的
    # 编号通常埋在块中部（如 "9. In 2.6-8, write…" / "Theorem 2.7-9 states…"），
    # m.start() 明显 > 1。下面只允许真条头位置的匹配继承标签，阻断交叉引用
    # 借相邻块/章节标签「伪装」成条目并去重覆盖真定义（2.6-8 锚到习题页、
    # 2.7-9 锚到交叉引用页 的根因）。
    at_head = m.start() <= 1
    ctx_self = (before[-90:] if len(before) > 90 else before) + after[:160]
    # A type word IMMEDIATELY adjacent to the number is the item's own heading
    # label and outranks type words mentioned later in the same block as
    # cross-references (e.g. "8.3-4 Corollary (...). In Theorem 8.3-3" must be
    # Corollary, not Theorem). Prefer the occurrence closest to the number.
    near_after = after[:30]
    near_before = before[-12:] if before else ""
    la = _first_label_pos(near_after)
    if la:
        label = la
    elif near_before:
        lb = _first_label_pos(near_before)
        if lb:
            label = lb
    if label == 'uncat':
        lm = label_re.search(ctx_self)
        if lm:
            label = _label_from_raw(lm.group())

    if label == 'uncat' and active_section_label and at_head:
        label = active_section_label

    if label == 'uncat':
        if i > 0:
            prev_txt = all_blocks[i-1][2]
            prev_label = label_re.search(prev_txt[-120:])
            if prev_label and at_head:
                label = _label_from_raw(prev_label.group())
        if label == 'uncat' and i < len(all_blocks) - 1:
            next_txt = all_blocks[i+1][2]
            next_label = label_re.search(next_txt[:120])
            if next_label and at_head:
                label = _label_from_raw(next_label.group())

    text_preview = txt[max(0, m.start()-5):m.end()+80].replace('\n', ' ')
    raw_matches.append({'key': key, 'page': p, 'label': label,
                        'text': text_preview, 'mstart': m.start()})

# ---------------------------------------------------------------------------
# TWO-LEVEL numbering scheme (中文二级标签）
#   · 定义 has its OWN per-chapter counter (定义1.1, 定义1.2, ...)
#   · 定理/引理/推论/命题 SHARE one continuous counter (1.1, 1.2, ...)
#   · 例 are renumbered PER SECTION (例1, 例2 ...) — not emitted here; example
#     completeness is handled by build_structure (book_structure.json).
# Produces keys like '定义1.1' / '定理1.1' that match the .md bold entries
# (**定义1.1**：, **定理1.1**：). The three-level N.S-N regex is deliberately
# NOT used here (it manufactures false-positive phantom keys for this scheme).
# ---------------------------------------------------------------------------
def extract_items_two_level(extract_dir, chapter, start_page, end_page, chapter_first=True):
    all_blocks = []
    for p in range(start_page, end_page + 1):
        fpath = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fpath):
            continue
        f = PageJson.load(fpath).data
        for t in f.get("text", []):
            txt = t.get("text", "").strip()
            if not txt:
                continue
            poly = t.get("poly", [])
            y = poly[1] if poly and len(poly) >= 8 else 0
            all_blocks.append((p, y, txt))
    all_blocks.sort(key=lambda x: (x[0], x[1]))

    # 两级 N.M：chapter_first=True 时首数为章号（跨章前向引用过滤）；
    # chapter_first=False（节基书，如数学物理方程）时首数为节号，不做章过滤。
    lab_re = re.compile(r'(定义|定理|引理|推论|命题|注)\s*(\d+)\s*' + SEP_TIGHT + r'\s*(\d+)')
    # 交叉引用守卫（谷超豪《数学物理方程》实测）：正文提及他章/他节条目时，
    # 提及点前紧邻「第X章」「…中的」「不满足」「推出」「利用」等引用语境词
    # （"如果初始资料不满足定理3.1中的正则性要…"、"可立即推出第一章中的引理3.1"）。
    # 真条目头的标签前要么是块首、要么是句号/空行，不含这些词。命中即跳过。
    _cite_ctx_re = re.compile(
        r'第[一二三四五六七八九十0-9]+章[之中\s]*$|中的$'
        r'|(?:不)?满足$|推出$|参见?$|^见|由$|根据$|利用$|应用$|证得$|得$|即$')
    lab_items = []
    for p, y, txt in all_blocks:
        for m in lab_re.finditer(txt):
            c = int(m.group(2)); num = int(m.group(3))
            if chapter_first and c != chapter:
                continue
            if c > 15 or num > 50:
                continue
            if m.start() > 0 and _cite_ctx_re.search(txt[:m.start()].rstrip()):
                continue
            label = m.group(1)
            key = f"{label}{c}.{num}"
            text_preview = txt[max(0, m.start()-5):m.end()+80].replace('\n', ' ')
            lab_items.append({'key': key, 'page': p, 'label': label, 'text': text_preview})

    # 单级条目（推论/例/性质/习题）：块首「标签+数字」，数字后非数字/小数点
    # （排除 "定理2.1" 这类两级号），并拒绝助词紧随的引用形态（"例2和例3"）。
    single_re = re.compile(
        r'^(定义|定理|引理|推论|命题|例|性质|注|习题)\s*(\d+)(?![\d.．·])'
        r'(?![的之中即及时前后都均也是])'
        # 「与/和/或」仅在构成枚举引用（"例2和例3"、"定理1或定理2"）时才拒；
        # 后随非「标签+数字」（如 性质4 的陈述以 "与S(Rⁿ)上的情形类似…" 开头，
        # 谷超豪《数学物理方程》ch6 §4 实测）不拒。
        r'(?!(?:[与和或]\s*(?:定义|定理|引理|推论|命题|例|性质|注)\s*\d))')
    single_raw = []
    for p, y, txt in all_blocks:
        m = single_re.match(txt)
        if not m:
            continue
        label = m.group(1)
        n = int(m.group(2))
        if n <= 0 or n > 50:
            continue
        key = f"{label}{n}"
        text_preview = txt[max(0, m.start()-5):m.end()+80].replace('\n', ' ')
        single_raw.append({'key': key, 'page': p, 'label': label, 'text': text_preview})

    # 两级号（定理2.1…）：finditer 无块首锚定，正文交叉引用提及多，首现即定义页，
    # 沿用 first-wins 去重。
    seen = {}
    for it in lab_items:
        if it['key'] not in seen:
            seen[it['key']] = it
    items = list(seen.values())
    # 单级号（例N / 性质N / 推论N…scope=3 节级重置）：不同节复用同一「标签N」是
    # 真实重起而非重复提及，旧 first-wins 会把后面各节的 例1/例2、性质1-4 整批
    # 吞掉（谷超豪《数学物理方程》实测：ch4 §2 的例1/例2、ch5 §2/§4 的例1-3、
    # ch6 §3/§4 的性质1-4 全部丢失）。改用共享 dedup_items 的页/名判重语义
    # （同页合并；跨页异名保留；≥3 页同名按平行条目保留），与 en 系抽取器同源。
    items += dedup_items(single_raw)
    items.sort(key=lambda x: (x['page'], x['key']))
    # Continuity is verified by build_structure (book_structure.json); no B-layer gap
    # re-scan here (the three-level re-scan logic is N.S-N specific).
    return items, [], []

from item_dedup import dedup_items
def extract_items(extract_dir, chapter, start_page, end_page, manual_overrides=None, cfg=None):
    # `cfg` is the BookConfig (grouping source of truth).  Dispatch on the
    # PRIMARY group's style code.  When omitted, fall back to a default
    # single three-level uncat group (back-compat for direct callers).
    if cfg is None:
        cfg = BookConfig(ordinal=[GroupConfig(type=ORDINAL_THREE_LEVEL)])
    primary = cfg.primary_type
    if primary == ORDINAL_TWO_LEVEL:
        items, warnings, blocking = extract_items_two_level(
            extract_dir, chapter, start_page, end_page,
            chapter_first=getattr(cfg, 'chapter_first', True))
        if manual_overrides:
            existing = {it['key']: idx for idx, it in enumerate(items)}
            for mo in manual_overrides:
                if mo['key'] in existing:
                    items[existing[mo['key']]] = {'key': mo['key'], 'page': mo['page'],
                                                  'label': mo['label'], 'text': mo['text'],
                                                  'agent_recovered': True}
                else:
                    items.append({'key': mo['key'], 'page': mo['page'],
                                  'label': mo['label'], 'text': mo['text'],
                                  'agent_recovered': True})
            items.sort(key=lambda x: (x['page'], x['key']))
        return items, warnings, blocking
    # ---- Step 2: read all JSONs, sort by (page, poly_y) ----
    all_blocks = []  # (page, y, text)
    for p in range(start_page, end_page + 1):
        fpath = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fpath):
            continue
        f = PageJson.load(fpath).data
        for t in f.get("text", []):
            txt = t.get("text", "").strip()
            if not txt:
                continue
            poly = t.get("poly", [])
            # poly = [x1,y1, x2,y1, x2,y2, x1,y2] flattened
            y = poly[1] if poly and len(poly) >= 8 else 0
            all_blocks.append((p, y, txt))
    all_blocks.sort(key=lambda x: (x[0], x[1]))

    # ---- regexes (defined BEFORE the section-scan loop below) ----
    # Step 2: broader pattern (also catches 1.3.9 → 1.3-9)
    num_re = re.compile(r'(\d+)\s*' + SEP_NUMERIC + r'\s*(\d+)\s*' + SEP_NUMERIC + r'\s*(\d+)')
    label_re = re.compile(
        r'(?:定义|定理|引理|推论|命题|练习|习题)\s*（'
        r'|例(?:子)?'
        r'|Example|Exercise'
        r'|\bDefinition\b|\bTheorem\b|\bLemma\b|\bCorollary\b|\bProposition\b',
        re.IGNORECASE
    )
    # Two-level 练习 / 习题 / Example pass (R3): CN three-level books number
    # exercises per chapter.section ("练习 4.1"), which the 3-component num_re
    # above never matches. Kept separate so the cross-ref filter and the
    # 3-component pass stay clean.
    ex_re = re.compile(r'(练习|习题|Example)\s*(\d+)' + SEP_TIGHT + r'(\d+)')
    # Case-insensitive so OCR-mangled lowercase "cf." / "see" / "below" /
    # "Secs." cross-references are caught (previously only the capitalized
    # "Cf." was matched, letting "(cf. 5.1-3)" through as a phantom item).
    # Used for the SAME-block check (step 0), where a genuine item's number is
    # at the block start so `before` is empty and never matches by accident.
    cite_re = re.compile(
        r'(见|由|根据|参考|参见|据|cf\.|see\b|below\b|viz\.|e\.g\.|i\.e\.|Secs?\.)',
        re.IGNORECASE)
    # Narrow set for the PREV-block-tail check (step 0b): only strong
    # cross-reference cues that indicate an OCR split mid-citation. A broad
    # set here wrongly skips the NEXT block's genuine item whenever any prior
    # block happens to end with "Sec." / "see" / "below" (e.g. "...in Sec. 11.3."
    # killed the following "3.7-3 Laguerre polynomials").
    cite_re_tail = re.compile(r'(见|由|根据|参考|参见|据|cf\.)', re.IGNORECASE)
    # Step 3: section heading (e.g. "§1.1 Name", "1.1 Name"). NOT matching "1.1-1" (numbered items).
    sec_heading_re = re.compile(r'^(?:§\s*)?(\d+)' + SEP_TIGHT + r'(\d+)(?:\s{2,}|\s+[^\d\-])')
    # Section-level label: a text block that is a standalone "例子" or "Examples" heading
    sec_label_re = re.compile(r'^(例[子]?|Examples?)$')

    # ---- Pass 0: collect the sections actually present in THIS chapter ----
    # Used to constrain the fallback regex (see below) so that stray "37-40"
    # (exercise range) or "1837-1920" (date range) cannot be mis-read as a
    # phantom "3.7" section. A fallback item c.s-N is only kept when s is a
    # real section of this chapter.
    chapter_sections = set()
    for p, y, txt in all_blocks:
        stripped = txt.strip().rstrip('：:．.，, ')
        sm = sec_heading_re.match(stripped)
        if sm and int(sm.group(1)) == chapter:
            chapter_sections.add(int(sm.group(2)))

    # ---- Step 2a: fallback pattern for garbled numbers (e.g. "21_7" → 2.1-7) ----
    fallback_re = re.compile(r'(\d)(\d)' + SEP_NUMERIC + r'\s*(\d+)')

    # ---- Step 2: collect all number matches with context ----
    raw_matches = []
    active_section_label = None   # label inherited from section heading, persists across pages

    for i, (p, y, txt) in enumerate(all_blocks):
        stripped = txt.strip().rstrip('：:．.，, ')  # remove trailing punctuation that OCR may add

        # Detect section heading → reset section-level label
        if sec_heading_re.match(stripped):
            active_section_label = None

        # Detect section-level label heading (e.g. "例子", "Examples")
        if sec_label_re.search(stripped):
            active_section_label = '例'
            continue

        # Step 4: find all number patterns (primary 3-group N.S-i)
        for m in num_re.finditer(txt):
            _add_match(m, txt, p, i, all_blocks, raw_matches,
                       active_section_label, chapter, label_re, cite_re, cite_re_tail, num_re)

        # Step 4b: fallback 2-group pattern for garbled "21_7" → 2.1-7
        m2 = fallback_re.search(txt)
        if m2:
            c = int(m2.group(1))
            s = int(m2.group(2))
            n = int(m2.group(3))
            # Only accept when s is a section actually present in this chapter,
            # so exercise/date ranges like "37-40" / "1837-1920" cannot be
            # mis-read as a phantom "3.7" section.
            if c == chapter and s <= 15 and n <= 50 and s in chapter_sections:
                key2 = f"{c}.{s}-{n}"
                if key2 not in {rm['key'] for rm in raw_matches}:
                    # Fallback quality filter: require non‑garbage text after the match
                    after_garbled = txt[m2.end():].strip()
                    if len(after_garbled) >= 8 and any('\u4e00' <= ch <= '\u9fff' or ch.isalpha() for ch in after_garbled[:12]):
                        _add_match(m2, txt, p, i, all_blocks, raw_matches,
                                   active_section_label, chapter, label_re, cite_re, cite_re_tail, num_re)

        # ---- Pass: two-level 练习 (R3) ----
        # CN three-level books number 练习 per chapter.section (e.g. 练习 4.1),
        # which the 3-component num_re above never matches. Emit these so the 练习
        # group has a real counter and the A-layer truly_missing check stays honest.
        for m in ex_re.finditer(txt):
            c = int(m.group(2)); s = int(m.group(3))
            if c != chapter or s == 0 or s > 50:
                continue
            key = f"练习{c}.{s}"
            # Skip cross-reference forms ("见 练习 4.1" / "由练习 4.1").
            if cite_re.search(txt[max(0, m.start() - 8):m.start()]):
                continue
            if any(rm['key'] == key for rm in raw_matches):
                continue
            raw_matches.append({'key': key, 'page': p, 'label': '练习',
                                'text': txt[max(0, m.start() - 5):m.end() + 80].replace('\n', ' ')})

    # ---- Dedup: prefer the EARLIEST GENUINE heading -------------------------
    # A single key can be mentioned on several pages: its REAL definition page
    # plus various references/usages.  We must NOT drop a *second* genuine
    # heading that merely shares the same (label, number) with an earlier one —
    # that happens when the source book prints the same number twice (a printing
    # off-by-one).  The full rationale + the page/name-aware split lives in
    # item_dedup.dedup_items (shared module).
    items = dedup_items(raw_matches)

    # ---- Merge manual overrides (e.g. OCR-garbled items recovered by agent) ----
    if manual_overrides:
        existing = {it['key']: idx for idx, it in enumerate(items)}
        for mo in manual_overrides:
            if mo['key'] in existing:
                items[existing[mo['key']]] = {'key': mo['key'], 'page': mo['page'],
                                              'label': mo['label'], 'text': mo['text'],
                                              'agent_recovered': True}
            else:
                items.append({'key': mo['key'], 'page': mo['page'],
                              'label': mo['label'], 'text': mo['text'],
                              'agent_recovered': True})
        items.sort(key=lambda x: (x['page'], x['key']))

    # 源侧缺口恢复逻辑现已剥离到校验层，抽取器只负责抓取 raw 条目：
    # 写书前的「源侧完整性校验 + 混合回填」由 verify/script/check_structure_completeness.py
    # 承担（复用 section_continuity 公共子流程 + 独立标题锚定扫描）。抽取器只负责
    # 把 raw 条目抓出来，不再内嵌校验逻辑。
    # 返回 (items, [], [])：warnings/blocking 不再由抽取器产生（校验层职责）。
    return items, [], []


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description="Extract numbered items from book JSON pages.")
    ap.add_argument("pos", nargs="*", help="CN: <ch> <start> <end> <extract_dir> | EN: <start> <end> <extract_dir>")
    ap.add_argument("--lang", choices=["cn", "en"], default="cn")
    ap.add_argument("--ordinal", dest="ordinal", type=int, default=ORDINAL_THREE_LEVEL,
                        help="integer style code: 1 single | 2 two_level(CN) | "
                             "3 three_level(CN, default) | 4 en | 5 roman | 6 gm")
    ap.add_argument("--manual", default=None, help="path to manual_overrides json (CN only)")
    ap.add_argument("--examples", action="store_true", help="include Example items (EN only)")
    ap.add_argument("--verbose", action="store_true")
    ns = ap.parse_args()
    # Back-compat: `--ordinal N` is a single-group shortcut -> one uncat GroupConfig.
    # The group scope follows the detected depth (1->book / 2->chapter / 3->section)
    # so the extraction-side B-layer resets counters at the right boundary.
    _depth = ORDINAL_DEPTH.get(ns.ordinal, ORDINAL_THREE_LEVEL)
    cfg = BookConfig(ordinal=[GroupConfig(type=ns.ordinal, name=["uncat"],
                                          scope=_depth)])

    if ns.lang == "en":
        if len(ns.pos) < 3:
            ap.error("EN mode needs: <start> <end> <extract_dir>")
        start, end, extract_dir = int(ns.pos[0]), int(ns.pos[1]), ns.pos[2]
        items = extract_items_en(extract_dir, start, end, want_examples=ns.examples)
        print(f"=== ITEMS p{start}-{end} ({len(items)}) ===")
        cur_sec = None
        for it in items:
            sec = it["key"].split(".")[0]
            if sec != cur_sec:
                cur_sec = sec
                print()
            print(f"{it['key']:22s} p{it['page']:3d}  {it['text'][:80]}")
        print(f"\nTotal: {len(items)}")
    else:
        if len(ns.pos) < 4:
            ap.error("CN mode needs: <ch> <start> <end> <extract_dir>")
        ch, start, end, extract_dir = int(ns.pos[0]), int(ns.pos[1]), int(ns.pos[2]), ns.pos[3]
        manual = None
        if ns.manual and os.path.exists(ns.manual):
            manual = manual_overrides_chN.load_manual_overrides(ns.manual)
            print(f"[INFO] Loaded {len(manual)} manual overrides from {ns.manual}")
        items, warnings, blocking = extract_items(extract_dir, ch, start, end, manual_overrides=manual, cfg=cfg)
        print(f"=== Ch{ch} ITEMS ===")
        cur_sec = ""
        for it in items:
            sec_label = '.'.join(it['key'].split('.')[:2])
            if sec_label != cur_sec:
                cur_sec = sec_label
                print()
            print(f"{it['key']:8s} [{it['label']}] p{it['page']:3d}  {it['text']}")
        if warnings:
            print(f"\n=== WARNINGS (B-layer extraction completeness) ===")
            for w in warnings:
                print(w)
        if blocking:
            print(f"\n=== BLOCKING ({len(blocking)}) — extraction incomplete, must resolve before writing ===")
        else:
            print(f"\n=== B-layer: no blocking issues (all boundary/tail re-scans clean) ===")
        print(f"\nTotal: {len(items)}")
