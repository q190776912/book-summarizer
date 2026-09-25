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
from page_json import PageJson

import os, sys

import bisect
import json, re
from lib.regexlib import SEP_TIGHT
from item_dedup import dedup_items

# ---------------------------------------------------------------------------
# ENGLISH-aware extraction (two-level English numbering)
# For English textbooks with two-level numbering (Theorem 1.1, Definition 1.1,
# Example 1.25, ...). Returns items shaped like the CN path: {key, label, page, text}.
# ---------------------------------------------------------------------------
# NOTE: "Assertion" is intentionally EXCLUDED. It is semantically a Proposition
# claim and is never a tracked ordinal group in any verify_config (the config
# groups are Theorem/Algorithm/Lemma/Conjecture/Proposition/Example/Question/
# Figure). Treating it as a contract item fabricates phantom "Assertion N"
# entries that can never match the md's "Assertion N" / "断言 N" (which the
# config does not require) — surfacing as false truly-missing. Per the user's
# ignore_ch7.json intent, Assertion items are non-blocking noise, so they must
# not enter the contract at all.
EN_LABELS = ["Definition", "Theorem", "Lemma", "Proposition", "Corollary", "Example",
             "Conjecture", "Remark"]
# Extended to ALSO capture single-number EN headings ("Theorem 1", used per
# chapter by Silverman's "A Friendly Introduction to Number Theory" 4th ed).
# The second numeric component is optional; single-number keys become
# "Theorem 1", two-level remain "Theorem 1.2".
#
# OCR-digit tolerance: mirror verbatim the OCR_DIGIT map used by
# verify/script/check_structure_completeness.py so the extractor recovers items
# the cross-scanner finds but a strict \d+ would miss — e.g. OCR reads
# "Theorem 7.l" (letter l instead of digit 1).  Without this, those items are
# silently dropped from the contract while scan_raw_items still catches them,
# which surfaces as false "missing_items" in the completeness gate.
OCR_DIGIT = {'O': 0, 'o': 0, 'Q': 0, 'D': 0, '0': 0,
             'I': 1, 'l': 1, 'i': 1, '1': 1,
             'Z': 2, 'z': 2, '2': 2,
             'E': 3, 'e': 3, '3': 3,
             'S': 5, 's': 5, '5': 5,
             'G': 6, '6': 6,
             'T': 7, 't': 7, '7': 7,
             'B': 8, 'b': 8, '8': 8,
             'g': 9, '9': 9}

def _ocr_int(tok):
    """Normalize an OCR-tolerant numeric token to int (letters mapped via
    OCR_DIGIT). Returns None if any char cannot resolve to a digit."""
    s = ''.join(str(OCR_DIGIT.get(c, c)) for c in tok)
    return int(s) if s.isdigit() else None


# 合法的「OCR 数字字符」= 数字 + OCR_DIGIT 的键（**区分大小写**）。出现集合外的
# 字母即说明编号 token 被散文污染（详见 ``_ocr_int_glue``）。
_VALID_OCR_CHARS = set("0123456789") | set(OCR_DIGIT)


# 前瞻 / 回溯**交叉引用**的谓语动词。块首就出现 "Example 5.16 will illustrate
# why…" 这类引用句时，形态与真条头完全一致（块首 + 标签 + 编号），抓住它会在真
# 条目之前插入同号幻影 → B 层报「顺序错乱」。编号后紧跟下列**小写**词即为引用。
# 🔴 below/above 必收（Lee 2e 实测）：前向引用 "Proposition 11.26 below that…" /
# "Example 15.38 below), …" 若不拒，幻影还会**毒化单调守卫的 max**——同号真条目
# 及其后续小号真条目全被误杀（ch15 六条 Example 因此漏抽）。
MENTION_VERBS = {
    "will", "would", "can", "could", "may", "might", "must", "should", "shall",
    "shows", "show", "illustrates", "illustrate", "implies", "imply",
    "gives", "give", "says", "say", "states", "state", "follows", "follow",
    "is", "are", "was", "were", "has", "have", "had", "and", "or", "then",
    "to", "in", "of", "by", "with", "for", "see", "cf", "using", "used",
    "applies", "apply", "tells", "tell", "asserts", "assert", "also",
    "below", "above",
}


def _ocr_int_glue(tok, nxt):
    """OCR 容错取号，带「粘连散文剥离」守卫。

    EN_OCR_NUM 字符类含易混字母，OCR 粘连会把散文首词粘到编号上：
    "Proposition 2.1The…" → 第二段 token 匹配成 "1T"（T→7 → 幻影 2.17）、
    "Theorem 12.5System…" → "5S"（S→5 → 幻影 12.55）。判据：token 混有
    数字与字母、且紧跟 token 的仍是字母（粘连词在继续，如 "1T|he"）→
    尾部字母是散文，剥离后取号。纯字母 token（如 "7.l" 的 "l"）是真
    OCR 数字混淆，原样保留。

    🔴 另有一种粘连：粘连词**整词**被吞进 token，token 之后紧跟的是空格
    （Bass《Real Analysis》实测 "Proposition 20.8Let E be a subset…" →
    token = "8Let"）。此时旧判据（只看 nxt 是否字母）失效，token 里含
    OCR_DIGIT 之外的字母（'L'）导致 ``_ocr_int`` 返回 None，**整条条目被丢弃**
    ——表现为 B 层「缺号 8」，且查漏扫描也补不回来。
    新判据：尾部字母串里出现**任何非 OCR 易混字母**（区分大小写，如 'L'/'y'/'h'）
    → 该串必是粘连的散文，剥离。纯由易混字母组成的尾串（"1OO" → 100）保留。
    """
    s = tok
    if s and any(c.isdigit() for c in s) and any(c.isalpha() for c in s):
        _tail = re.search(r"[A-Za-z]+$", s)
        if _tail:
            _contaminated = any(c not in _VALID_OCR_CHARS for c in _tail.group(0))
            if _contaminated or (nxt and nxt.isalpha()):
                s = re.sub(r'[A-Za-z]+$', '', s)
    return _ocr_int(s)


def _levenshtein(a, b):
    """Standard Levenshtein edit distance (case-insensitive already applied
    by callers). Small, dependency-free; only used on short label words."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cost = 0 if ca == cb else 1
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost))
        prev = cur
    return prev[-1]


# Tolerance for OCR-garbled label words in the NUMBER-FIRST (section-scoped)
# path.  do Carmo prints entries as `2.1 DEFINITION` but OCR mangles the label
# (`DEFINrTION`, `DEFINrrION`, `BxAMPLE`, `PROPosrTION`, …) while the `N.M`
# number stays intact.  The number alone is enough to know it IS an entry, but
# we still need the canonical label to key/type it correctly, so we fuzzy-match
# the garbled word against the known label set.  Threshold 2 recovers every
# observed do Carmo garble (all are <= 2 substitutions) without false-positive
# matches against ordinary prose words like `Let`/`Then` (distance >= 3).
_LABEL_FUZZY_THRESHOLD = 2


def _resolve_label(word, labels):
    """Resolve a (possibly OCR-garbled) heading word to its canonical label.

    Tries, in order: exact case-insensitive match, then Levenshtein-fuzzy
    match within `_LABEL_FUZZY_THRESHOLD`, then (fallback) scanning the first
    ~40 chars of the line for any exact label word — this last one catches
    named theorems where the label is NOT the first word, e.g. do Carmo's
    `2.2 Index Theorem.` (label = Theorem, not `Index`).
    Returns the canonical label string (e.g. ``"Definition"``) or None.
    """
    w = (word or "").strip()
    if not w:
        return None
    wl = w.lower()
    # 1) exact
    for lab in labels:
        if lab.lower() == wl:
            return lab
    # 2) fuzzy
    best, best_d = None, 99
    for lab in labels:
        d = _levenshtein(wl, lab.lower())
        if d <= _LABEL_FUZZY_THRESHOLD and d < best_d:
            best, best_d = lab, d
    if best is not None:
        return best
    return None


def _scan_inline_label(text, labels, window=40):
    """Fallback: return the first exact (case-insensitive) label word found in
    the first `window` chars of `text` (so a named theorem's label that appears
    after the entry name is still caught)."""
    head = text[:window]
    toks = re.findall(r"[A-Za-z][A-Za-z]{2,}", head)
    for t in toks:
        for lab in labels:
            if lab.lower() == t.lower():
                return lab
    return None

# Character class: any digit OR any OCR-confusable letter from OCR_DIGIT keys.
# NOTE: must include \d (all 0-9).  OCR_DIGIT only lists the letters it maps
# plus the literal digits that appear as map *values*; the digit "4" (and any
# digit with no letter-confusable) is NOT a key, so a bare key-set class would
# silently drop every item whose number contains such a digit (e.g.
# "Theorem 4.1").  Hence \d + the confusable letters.
_EN_OCR_LETTERS = ''.join(sorted(k for k in set(OCR_DIGIT.keys()) if not k.isdigit()))
EN_OCR_NUM = r'[\d' + _EN_OCR_LETTERS + r']+'

EN_LAB_RE = re.compile(
    r'\b(' + '|'.join(EN_LABELS) + r')\b\s*(?:\([^)]*\))?\s*'
    r'(' + EN_OCR_NUM + r')(?:\s*' + SEP_TIGHT + r'\s*(' + EN_OCR_NUM + r'))?',
    re.IGNORECASE,
)

# Section-scoped EN books (e.g. Fraleigh): the FIRST number is the SECTION, not
# the chapter, and the source additionally prints NUMBER-FIRST headings
# ("26.4 Lemma", "24.2 Corollary") alongside label-first ones, plus numbered
# graphics ("Table 1.20", "Figure 3.6"). The shared EN extractor handles these
# ONLY when `section_scoped=True`, so normal chapter-first EN books (Silverman,
# stochastic-processes, ...) keep their exact prior behavior untouched.
SECTION_LABELS = EN_LABELS + ["Table", "Figure", "表", "图"]
# Number-first headings ("2.1 DEFINITION", "24.2 Corollary") — the label word
# is captured RAW (may be OCR-garbled) and resolved to its canonical form by
# `_resolve_label` in the loop below.  We intentionally do NOT require the label
# to exactly match SECTION_LABELS here, because OCR mangles it
# (`DEFINrTION`, `BxAMPLE`, …); the number `N.M` is the reliable signal that
# this is an entry.  The captured word must be >= 3 letters so we don't grab a
# stray single letter.
EN_LAB_RE_NF = re.compile(
    r'(' + EN_OCR_NUM + r')\s*' + SEP_TIGHT + r'\s*(' + EN_OCR_NUM + r')\s+'
    r'(?:\([^)]*\)\s+)?([A-Za-z][A-Za-z]{2,})',
    re.IGNORECASE,
)


def extract_items_en(extract_dir, start, end, want_examples=True, section_scoped=False,
                     single=False, extra_labels=None, restart_per_section=None):
    """Extract English item headings from OCR pages.

    ``single``: when True (single-level EN books, e.g. Silverman's "A Friendly
    Introduction to Number Theory" 4th ed — ORDINAL_SINGLE / type 1), items carry
    ONE numeric component ("Theorem 1", "Lemma 1"). The regex then MUST NOT
    capture a second component: OCR line-merge noise ("Assertion 1. The number..."
    glued to a later "7") would otherwise fabricate "Assertion 1.7". With
    ``single=False`` (default; two-level EN books like Kreyszig) the optional
    second component is kept ("Theorem 1.1").

    ``extra_labels``: additional label words (config_setting 规则5 incremental
    extension) taken from the book's ``ordinal`` group ``name`` lists — e.g.
    Rosen's "Algorithm N" / "Axiom N" blocks, which base EN_LABELS lacks.
    Purely additive: labels already in the base set are de-duplicated, and
    callers not passing it keep exact prior behavior.

    ``restart_per_section``: ``(lowercase_label_set, [(page, sec_num), ...])``
    for books whose single-component counters RESET AT EVERY SECTION (config
    ordinal group ``scope == 3``, e.g. Rosen: "Example 1..16" in §1.1, then
    "Example 1..11" again in §1.2).  The chapter-wide monotonic / seen-key
    guards (added for Han-Lin) treat every restart as a stale cross-reference
    and collapse the section (Rosen ch1: 138 examples → 28).  For the listed
    labels the guards bucket by *current section window* instead: the
    (page, sec_num) windows are sorted into reset boundaries — a section number
    that merely nests under the previous one ("1.1.1" after "1.1") does NOT
    reset, matching the print convention that restarts happen at the top-level
    section.  Labels not in the set keep chapter-wide behavior.
    """
    items = []
    # 已抓到的条目 key（同一次调用 = 同一章）。用于识别「续行型交叉引用」：
    # 见下方 key 重复处的守卫。
    seen_keys = set()
    # (标签, 章号) -> 该桶已抓到的最大编号元组；同标签编号必须严格递增。
    _max_per_label = {}
    # restart_per_section: fold the (page, sec_num) windows into *reset
    # boundaries* — nested numbers ("1.1.1" right after "1.1") share the
    # parent bucket; any non-nested number opens a fresh bucket.
    _rst_labels, _rst_boundaries = set(), []
    if restart_per_section:
        _rl, _rws = restart_per_section
        _rst_labels = {str(x).strip().lower() for x in (_rl or [])}
        _anchor = None
        for _pg, _num in sorted(_rws or [], key=lambda t: (t[0], str(t[1]))):
            _s = str(_num)
            # nested under the current bucket's anchor section ("1.1.2" inside
            # anchor "1.1") → same reset bucket; anything else opens a new one.
            if _anchor is None or not _s.startswith(_anchor + '.'):
                _rst_boundaries.append((_pg, len(_rst_boundaries)))
                _anchor = _s
    _rst_pages = [pg for pg, _ in _rst_boundaries]

    def _rst_bucket_for(p):
        """Current section-window bucket id for a page (None before the first
        detected section head — caller then keeps chapter-wide behavior)."""
        idx = bisect.bisect_right(_rst_pages, p) - 1
        return _rst_boundaries[idx][1] if idx >= 0 else None
    # Section-scoped books also accept numbered graphics (Table/Figure) as items.
    lab_labels = SECTION_LABELS if section_scoped else EN_LABELS
    if extra_labels:
        lab_labels = list(lab_labels) + [
            l for l in extra_labels if l not in lab_labels]
    # 🔴 OCR merges the label word and its number ("EXAMPLE8", "THEOREM1") in
    # this book's scans; the classic `LABEL\b\s*(NUM)` never matches there
    # because `E|8` is not a \w/non-\w boundary.  Require only "not followed
    # by a letter" after the label so both "EXAMPLE 8" and "EXAMPLE8" match,
    # while prose like "Examples3D"/"Exampletext" still cannot (next char is
    # a letter).
    _lab_tail = r')(?![A-Za-z])\s*(?:\([^)]*\))?\s*'
    # 🔴 标题粘连回退（Rosen 8e 实测 2026-09-25）：真条头被 OCR 粘上标题首词
    # （"EXAMPLE 9Determine …"、"EXAMPLE 9Translate …"），而 EN_OCR_NUM 的
    # 易混字母类（BDEGIOQSTZ+begilostz）贪婪吞进 "9Dete"/"9T" → 键被归一成
    # 垃圾、真实条目消失（§1.3/§1.5 例9 漏抽）。不改正则（IGNORECASE 使
    # [a-z] 前瞻失去大小写区分），改在匹配后对编号串做 `_trim_glued_title_tail`
    # 归约：字母尾巴 >= 2 个，或尾巴 1 个字母且其后仍是字母（标题词延续，
    # 如 "9T"+"ranslate"）→ 砍回前导数字（"9"，标题从 'D'/'T' 起）。合法
    # OCR 形不动："1o "（10 的 OCR，尾 1 字母+后随空格）、"EXAMPLE3"（纯数字）。
    if single:
        lab_re = re.compile(
            r'\b(' + '|'.join(lab_labels) + _lab_tail +
            r'(' + EN_OCR_NUM + r')',
            re.IGNORECASE,
        )
    else:
        lab_re = re.compile(
            r'\b(' + '|'.join(lab_labels) + _lab_tail +
            # 🔴 TIGHT second component (NO whitespace between SEP_TIGHT and the
            # digit).  Two-level EN numbering is ALWAYS printed tight
            # ("Theorem 1.1", "Lemma 2.3") with no space after the separator.
            # Allowing a trailing `\s*` here is catastrophic: a single-number
            # heading like "Example 2. Queueing" / "Example 3. Some Genetic"
            # ends with a SENTENCE period followed by a space and the TITLE
            # word.  EN_OCR_NUM includes OCR-0/5-confusable letters
            # (Q/O/o/D->0, S/s->5, ...), so the greedy `[\d...]+` then swallows
            # the title word's first letters as a phantom sub-number:
            #   "Example 2. Queueing" -> "Example 2.0"  (Q->0)
            #   "Example 3. Some"      -> "Example 3.50" (S->5,o->0)
            #   "Example 1. Suppose"   -> "Example 1.5"  (S->5)
            #   "Example 1. Our"       -> "Example 1.0"  (O->0)
            # Those fabricated keys never match the md's "例2"/"例3"/"例1",
            # surfacing as false TRULY-MISSING (A-layer M failures).  Requiring
            # the digit to be TIGHT against the separator kills the capture for
            # sentence-period+title (space present) while keeping every genuine
            # "1.1" intact.  (The leading `\s*` is kept so "Theorem 1.1" with a
            # separator that may follow the first number without a space still
            # matches — it does; the trailing one is what enabled the bug.)
            r'(' + EN_OCR_NUM + r')(?:\s*' + SEP_TIGHT + r'(' + EN_OCR_NUM + r'))?',
            re.IGNORECASE,
        )
    for p in range(start, end + 1):
        fp = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        with open(fp, "r", encoding="utf-8") as f:
            data = PageJson.load(os.path.join(extract_dir, f"page_{p:03d}.json")).data
        for t in data.get("text", []):
            txt = t.get("text", "")
            if not txt:
                continue
            for m in lab_re.finditer(txt):
                label = m.group(1)
                if label == "Example" and not want_examples:
                    continue
                # Heading vs prose reference: a real entry heading starts the
                # text block (e.g. "THEOREM 8.4. Let k >= 2."); a cross-reference
                # like "by Lemma 11.26" / "satisfy Theorem 11.1" sits mid-block.
                # Skip mid-block matches to avoid false-positive phantom items
                # (Apostol prints headings in UPPERCASE / OCR-mangled case, so
                # IGNORECASE is needed above, but it also widens prose capture).
                if txt[:m.start()].strip():
                    continue
                # 🔴 标题粘连回退（Rosen §1.3/§1.5 例9 实测）：单级模式下
                # EN_OCR_NUM 贪婪吞进标题首词字母（"EXAMPLE 9Determine" → 组
                # "9Dete"；"EXAMPLE 9Translate" → "9T"+"ranslate"），旧守卫链
                # （小写起头=散文）把被截断的标题尾巴当散文拒掉整条。回溯：
                # 编号 token 砍回前导数字并同步 match 终点（合法 OCR 尾字母
                # "1o " 不满足条件，行为不变）。
                _mend = m.end()
                _mend2 = m.end(2)   # 一级数字组的终点（两级模式下 ≠ m.end()）
                _tok_adj = m.group(2)
                if single:
                    _dm2 = re.match(r'^(\d+)([A-Za-z]+)$', m.group(2) or '')
                    if _dm2:
                        _nxt_c = txt[_mend:_mend + 1]
                        if (len(_dm2.group(2)) >= 2
                                or (_nxt_c.isascii() and _nxt_c.isalpha())):
                            _mend = _mend2 = m.start(2) + len(_dm2.group(1))
                            _tok_adj = _dm2.group(1)
                # Reject cross-reference headings: a genuine entry heading is
                # followed by a sentence period / space + title, never a closing
                # delimiter.  do Carmo prints entries NUMBER-FIRST, so a label-
                # first "Example 4.8)" is a reference, not a heading; without this
                # guard it fabricates a phantom item.
                _after = txt[_mend:_mend + 1]
                if _after and _after in ")]},;:":
                    continue
                # 🔴 同族换行残片守卫（Lee《Introduction to Smooth Manifolds》2e
                # ch16/ch22 实测）：OCR 把提示句的换行尾巴独立成块——"…[Hint: use
                # the result of / Problem 16-12.]"、"(… by Problem 22-24.)"——块首
                # 恰是标签+号，但号后紧跟「句点+右括号」（".]" / ".)"），
                # 这是引用残片而非条目头：单字符守卫被句点骗过，不拒则产出
                # 幻影练习节点（16.12 / 22.24，与真 Problem 16-12 / 22-24 并存）。
                if txt[_mend:_mend + 2] in (".]", ".)"):
                    continue
                # 🔴 正文交叉引用守卫（Bass《Real Analysis》实测）：段落本身就是
                # "Example 5.16 will illustrate why this is a less useful theorem
                # than …" 这类**前瞻引用**——块首 + 标签 + 编号的形态与真条头完全
                # 一致，旧守卫（只看块首 / 闭合定界符）拦不住。抓住它会在真条目
                # （同号、后一页）之前插入一个幻影，B 层报「顺序错乱」并阻断闸门。
                # 判据：编号后首个词是**小写**且属于引用动词表 → 引用，非条目。
                # 🔴 粘连还原（Tu《流形导论》8.13 实测）：引用句 "Example 8.13
                # shows that…" 被 OCR 连写成 "Example8.13shows"，而 EN_OCR_NUM
                # 含易混字母（s→5），使编号组吞下动词首字母（组="13s"），仅余
                # "hows"——旧判据只看待选词 "hows" 不在动词表，幻影漏网、且因
                # 页码靠前在 dedup 中吃掉真条头（p108 "Example 8.13 (…)"）。
                # 若编号 token 与后续字母之间**无空白**（粘连），把被吞进数字的
                # 尾随字母拼回候选词再比对；有空白则维持旧行为。真条头后恒为
                # 句点/空格+大写标题或 "( 标题)"，几乎不会是引用动词表里的小写
                # 词，故本还原只多拦引用、不误杀真头。
                _rest = txt[_mend:]
                _wm = re.match(r"\s*([A-Za-z]+)", _rest)
                _wd = _wm.group(1) if _wm else ""
                _glued = bool(_wd) and _rest[:1] not in (" ", "\t", "\n")
                _gnum = ((m.group(3) if m.re.groups >= 3 else None)
                         or _tok_adj or "")
                _tm = re.search(r'(?<=\d)[A-Za-z]+$', _gnum)
                _tail = _tm.group(0) if _tm else ""
                _cand = (_tail + _wd) if _glued else _wd
                if _cand and _cand.lower() in MENTION_VERBS and not _cand[:1].isupper():
                    continue
                # Normalize OCR-tolerant numeric tokens (letter↔digit confusions
                # like l→1, O→0) so the contract carries the canonical number.
                n1 = _ocr_int_glue(_tok_adj, txt[_mend2:_mend2 + 1])
                if n1 is None:
                    continue
                # 🔴 Section-scoped books (chapter_first=False, e.g. Hilton &
                # Stammbach): a real heading is ALWAYS "Label S.N" with an
                # ARABIC section number.  A first token made purely of roman
                # numeral letters ("Theorem IV.4.1") is a cross-CHAPTER
                # reference that a line wrap left at block start — never a
                # heading; and a missing second component ("Theorem 1") is a
                # prose sentence fragment / single-number reference.  Reject
                # both (they would otherwise fabricate phantom items).
                if section_scoped:
                    raw_tok = m.group(2)
                    if raw_tok and re.fullmatch(r"[IVXLCivxlc]+", raw_tok):
                        continue
                    if m.re.groups < 3 or m.group(3) is None:
                        continue
                # single-mode regex has only 2 groups (label + number); the
                # optional second component (group 3) exists ONLY in two-level
                # mode. Guard every group(3) access with `not single`.
                if (not single) and m.group(3) is not None:
                    n2 = _ocr_int_glue(m.group(3), txt[m.end(3):m.end(3) + 1])
                    if n2 is None:
                        continue
                    key = f"{label} {n1}.{n2}"
                else:
                    key = f"{label} {n1}"
                # Reject single-level "Label N" matches that are actually prose
                # sentences (e.g. "Definition 15 is ambiguous..." / "Definition 0
                # of Markov time...") rather than numbered headings.  Genuine
                # two-level EN headings are always "Label N.M"; a bare "Label N"
                # immediately followed by a lowercase word is prose, not a
                # heading, and would otherwise pollute the contract (the B-layer
                # then flags a phantom 0..N gap).  Single-level headings that
                # start the next word with an uppercase letter (e.g. "Theorem 1
                # Let...") are kept.  Applies only to single-component keys
                # (single mode, or a two-level key whose n2 half was absent).
                if single or m.group(3) is None:
                    after = txt[_mend:].lstrip()
                    # 🔴 分部小题号（Rosen 例7 实测 "EXAMPLE 7a) How many cards
                    # must be selected…"）：编号后紧跟 `a)` / `(b)` 这类小题标记，
                    # 首字母小写但不是散文连接词——条目头照收，号仍取 7。
                    if re.match(r'^\(?\s*[a-z]{1,3}\s*\)\s', after):
                        pass
                    elif after and after[0].isascii() and after[0].islower():
                        continue
                # restart_per_section：该标签按节重置 → 两道守卫的桶/键都
                # 折进「当前节窗口」，§1.2 的 Example 1 与 §1.1 的 Example 1
                # 互不压制；页在首个已检出节头之前则维持章级行为。
                _rb = _rst_bucket_for(p) if _rst_labels else None
                _rst_on = _rb is not None and \
                    str(label).strip().lower() in _rst_labels
                _nkey = re.sub(r'\s+', ' ', key).lower()
                _gkey = (_rb, _nkey) if _rst_on else _nkey
                # 🔴 续行型交叉引用守卫（Han-Lin《Elliptic PDEs》实测）：上一行
                # 末是 "…Applying Lemma"、编号与后半句被 OCR 折到块首时，新块以
                # "Lemma 1.26 to any ball B_R(0)…" 开头，形态与真条头完全一致
                # （块首 + 标签 + 编号），但它是上一句的后半截。判据二条同时成立
                # 才拒：① 同一 key 在本章前面**已作为条目抓过**（书不会把同一编号
                # 的条目陈述两遍）；② 编号后的文字以小写字母开头或直接无标题
                # （真陈述以大写/标题词起头，如 "Lemma 1.10 Suppose…"）。
                # 只拒重复且接排的那一处，首次出现与大写起头的重复都不动，
                # 故不会误杀真条目（不同标签共享号段的书按完整 key 判别，
                # "Theorem 1.5" 与 "Lemma 1.5" 互不影响）。
                # 大小写/OCR 噪声归一后再比对（真条头常全大写 "LEMMA 1.26"，
                # 折行续句常是 "Lemma 1.26"，不作归一等于判不出重复）。
                if _gkey in seen_keys:
                    _dup_after = txt[_mend:].lstrip()
                    if (not _dup_after
                            or (_dup_after[0].isascii() and _dup_after[0].islower())):
                        continue
                # 🔴 同标签编号单调守卫（Han-Lin《Elliptic PDEs》实测）：章内计数器
                # 书里同一标签的编号必**严格递增**。凡是编号不高于「该标签本章已抓到
                # 的最大编号」的候选，都是页末句被折行后落在块首的**交叉引用后半截**
                # （"…we may apply THEOREM 6.8 to L+μ" / "COROLLARY 4.2 implies u ∈
                # C^{δ0}"）或同一条目的重复行，不是新条目。按 (标签, 章号) 分桶只比
                # 段内号，故不同标签各自计数（Koopman 型并行计数器）与按节重排的
                # section_scoped 书都不受影响——后者本规则不启用。
                if not section_scoped:
                    _lab_norm = str(label).strip().lower()
                    _bucket = (_lab_norm, n1) if (not single and m.group(3) is not None) \
                        else (_lab_norm,)
                    if _rst_on:
                        _bucket = _bucket + (_rb,)
                    _comp = (n1, n2) if (not single and m.group(3) is not None) else (n1,)
                    if _comp <= _max_per_label.get(_bucket, (-(1 << 30),)):
                        continue
                    _max_per_label[_bucket] = _comp
                seen_keys.add(_gkey)
                snippet = txt[max(0, m.start() - 5):_mend + 90].replace("\n", " ")
                items.append({"key": key, "label": label,
                              "page": p, "text": snippet})
            # Section-scoped EN source also prints NUMBER-FIRST headings
            # ("2.1 DEFINITION", "24.2 Corollary") — always two-level, so no
            # single-level prose ambiguity to guard against.  The label word is
            # OCR-garbled in practice; resolve it to the canonical label via
            # exact/fuzzy/inline scan so the entry is keyed and typed correctly.
            if section_scoped:
                for m in EN_LAB_RE_NF.finditer(txt):
                    raw = m.group(3)
                    if txt[:m.start()].strip():
                        continue
                    n1 = _ocr_int(m.group(1))
                    n2 = _ocr_int(m.group(2))
                    if n1 is None or n2 is None:
                        continue
                    label = _resolve_label(raw, SECTION_LABELS)
                    if label is None:
                        # tertiary: the label may appear just after the entry
                        # name (e.g. "2.2 Index Theorem." -> Theorem).
                        label = _scan_inline_label(
                            txt[m.start():m.start() + 50], SECTION_LABELS)
                    if label is None:
                        continue
                    if label == "Example" and not want_examples:
                        continue
                    key = f"{label} {n1}.{n2}"
                    snippet = txt[max(0, m.start() - 5):m.end() + 90].replace("\n", " ")
                    items.append({"key": key, "label": label,
                                  "page": p, "text": snippet})
    # Collapse reference mentions but KEEP two genuinely different items that
    # share a (label, number) — e.g. a source book printing the same number
    # twice (a printing off-by-one).  Genuine headings are already pre-filtered
    # above (only block-start matches survive), so any same-key collision with a
    # different heading text is a distinct item.
    # 🔴 section_scoped 书例外（Hilton & Stammbach 实测）：编号首段即节号，
    # 同一章内同 key 的第二个"条目头"必是句尾换行恰好落在 "Theorem 2.4." 的
    # 引用残行（其后内容块属前一条目的尾随散文），绝无"同号双印"。故唯一化。
    out = dedup_items(items, unique_keys=section_scoped)
    return out
