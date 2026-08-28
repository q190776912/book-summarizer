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
    python scan_skeleton.py <corpus_root>/<书名>/_extract
    # 指定章
    python scan_skeleton.py <corpus_root>/<书名>/_extract 1 2 3

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

# Two-level section: "2 Riemannian Metrics" / "1. Introduction".  Allow an
# OPTIONAL leading noise char before the number — do Carmo's OCR mis-reads the
# section sign (§) / dagger as an apostrophe, producing "'1. Introduction", which
# a strict `^\d` anchor would miss.  Also allow an OPTIONAL dot after the number
# ("2. Riemannian Metrics" — do Carmo prints sections as `N. Title` with a dot,
# while its page-number RUNNING HEADERS are printed as `N Title` WITHOUT a dot,
# so the optional dot lets us match real dotted sections while the page-number
# guard below still rejects the headers).  The noise set is tiny and a prose
# line never starts with "'N.", so this is benign for other books.
SEC_2 = re.compile(r"^(?:['\u2019\u00b6\u00a7\u2020\*]\s*)?(\d{1,2})\.?\s+[+*x\u00d7\u2605\u2606]?\s*([A-Z].{3,72})$")
# Section numbers are small (a chapter rarely has > ~30 flat `N. Title`
# sections).  A much larger number is a PAGE-NUMBER RUNNING HEADER (e.g. do
# Carmo's "36 Riemannian Metrics" printed at the top of every page), never a
# real section — reject it so it isn't fabricated into the structure contract.
SEC_MAX_NUMBER = 30
ITEM_2 = re.compile(r'^(\d{1,2})\.(\d{1,3})\.\s*(.{0,90})')
EXER_2 = re.compile(r'^(\d{1,2})\.([A-Z])\.\s*(.{0,90})')

# Chapter-LOCAL sections (Karlin-style: "§1" resets per chapter, printed in
# source as "1. Review of Basic…") are NOT scanned from the OCR here — the
# source "N. Title" form is ambiguous with numbered PROBLEMS and REFERENCES, so
# a greedy detector would fabricate dozens of false sections.  The authoritative
# section list for such books is the md `## §N` transcription, handled in
# build_structure (md-derived) + the D-layer (source cross-check).  See
# lib.regexlib.SEC_LOCAL for the (intersection-gated) source matcher.

# Chinese-scheme section headings — patterns shared from lib/regexlib.py
from lib.regexlib import SEC_CN, SECBARE_CN, SECGLUE_CN

# Global single-number section heads (Arnold《数学方法》-style "§12．变分法"):
# sections carry ONE number and are numbered GLOBALLY across the book
# (§1..§52 spanning all chapters), so the leading number is NOT the chapter.
# Declared via section_types having a depth-1 level BELOW the chapter level
# (e.g. [1, 1]); standard books ([1, 2] / [1, 2, 3]) never enter this branch
# (zero regression).  OCR noise: § mis-read as $/S/8 ("84．" = §4, "827．" =
# §27), so the prefix class is [§$S8]; a separator ([．.、。:]) is REQUIRED
# (prose like "85 年" has none and is rejected), and the title must start with
# a Han char / letter (never a digit — rejects "810.15元" style decimals).
# No label-word guard: Arnold's real titles legitimately contain 定理/例
# ("§20．E.诺特定理").  Titleless running heads ("§4.") are rejected (no title).
SEC_GLOBAL = re.compile(
    r'^[§$S8Ss6](\d{1,2})[．.、。:]\s*([A-Za-z\u4e00-\u9fff][^\n]{1,60})$')
# § mis-read as 9 and GLUED to the number ("99.三维空间…" = §9, "948.生成函数"
# = §48; the only two instances in this book, found by full-book scan).  The
# plain [§$S8] class cannot cover these (prefix '9' is itself a digit), so a
# second alternative with the same title/separator guards.
SEC_GLOBAL_9 = re.compile(
    r'^9(\d{1,2})[．.、。:]\s*([A-Za-z\u4e00-\u9fff][^\n]{1,60})$')
# Glued / prefix-lost single-number section heads (谷超豪《数学物理方程》3ed 实测):
# 「§N 标题」的 § 被 OCR 整个丢掉或读成 S/8，且数字与标题直接粘连、分隔符
# [．.、。:] 一并丢失（"1方程的导出、定解条件"、"83初边值问题的分离变量法"、
# "81热传导方程及其定解问题的导出"、"S5基本解"），SEC_GLOBAL 因要求分隔符而
# 全部漏检。本变体允许【无分隔符】，靠多重守卫压误报（仅 global_sec 书启用；
# Arnold 分隔符形态已被上方 SEC_GLOBAL 消费并 continue，不会到达此处）：
#   * 标题必须紧跟数字后【无任何分隔符】且以汉字/字母起始——带分隔符的
#     小节头/小节内子块头（"1．弦振动方程的导出"）、枚举项（"1）…"）、
#     公式碎片（"0:u"、"4π小"）均不匹配；
#   * 块顶 y ≥ _GLUE_MIN_Y：排除页眉区的重复节名（页眉每页重复当前节名，
#     真节头首现即正文页中部，去重取首现，故页眉命中必须整体压掉）;
#   * 行宽 ≤ _GLUE_MAX_WIDTH：真节头是居中短行（谷超豪《数学物理方程》实测
#     457–906px）；章首导语的通栏散文行（"1中导出了一维波动方程…"）≥1150px，
#     被宽度闸杀掉（通栏散文实测 ≥1200px）。注意不能用 SUB_GLOBAL_MAX_WIDTH=720：
#     长标题节头（"82两个自变量的一阶线性偏微分方程组的特征理论"）达 906px。
SEC_GLOBAL_GLUE = re.compile(
    r'^[§$S8Ss6*·]?\s*(\d{1,2})([A-Za-z\u4e00-\u9fff][^\n]{1,60})$')
# Plain prefix-LESS single-number section heads（Humphreys GTM 9 体例，config_setting
# 规则5 增量扩展）：原书节头印裸 "9. Axiomatics" / "12. Construction of root
# systems and automorphisms"——数字后一个点、无 § 前缀，上方 SEC_GLOBAL（要求
# [§$S8Ss6] 前缀）与 SEC_GLOBAL_GLUE（无分隔符粘连）均不覆盖。仅当 scan() 收到
# plain_sec_heads=True（build_structure 依 primary_type==ORDINAL_HUM 传入）时启用，
# 其余书零回归。守卫：
#   * 标题必须大写字母起始、总长 3..62——习题行 "5. Verify the assertions made in
#     (1.2) about t(n, F)..." 超长被杀；"2. Verify Table 2." 这类短习题行靠下方
#     「cur+1 门闩」拒绝（见 scan() 内注释）；
#   * 标题不得以句点结尾（真标题不带尾点；引用/残句常带）；
#   * 块顶 y ≥ _GLUE_MIN_Y：压制页眉带（本书页眉为 "Basic Concepts4" 词粘页码
#     形态，本就不会命中，此处仍统一防线）。
# 🔴 顺序门闩（防未来号污染）：全书 §1..§27 严格递增且每章连续。启用时只接受
# num == cur_global_sec + 1 的命中（cur 由首个命中播种），习题区里重排的小号
# （§8 习题 "1.".."6."）与「未来节号」的习题行（§12 习题 "13. ..." 若存在）
# 都会被拒绝——否则 §8 习题行 "9. ..." 会抢在真 §9（下一章扫描区间）之前
# 注册垃圾 SEC 9，下游 dedup 首现胜出 → 真节头永远丢标题。
SEC_GLOBAL_PLAIN = re.compile(
    r'^(\d{1,2})[．.、。:]\s*([A-Z][^\n]{2,61})$')
_GLUE_MIN_Y = 170.0
_GLUE_MAX_WIDTH = 1000.0


def _glue_title_ok(title):
    """Validate a SEC_GLOBAL_GLUE candidate title (guards above)."""
    t = (title or '').strip()
    if not t:
        return False
    if len(re.findall(r'[一-鿿]', t)) < 2:
        return False
    if _SUB_MATH_OP_RE.search(t):
        return False
    return True
# Bare-LETTER sub-block heads (Arnold《数学方法》: inside a §N the book prints
# "A.变分" / "D. 相流" — ONE capital letter + separator + SHORT Han title,
# parent section determined by POSITION).  Context decides the tier: under a
# numeric global §N it is a subsection (SUB row "<N>.<L>"); in an APPENDIX
# chapter (no numeric § heads) the same print IS the chapter's section
# ("<appendix letter>" promoted to SEC at assembly).  Guards kill the observed
# FP classes (full-book probe, 1059 loose candidates):
#   * title must contain ≥1 Han char      -> kills pure-formula lines
#     ("U=-#," / "E=" / "J Mo" / "F(Gx,G)=GF(c,).");
#   * no math-operator chars in title     -> kills "G：R→R…”是…", "M(t)=g*M.",
#     "RN）和初速度（c(to）∈R）…", "Mn,n=[e1,e2]…";
#   * title must NOT start lowercase latin -> kills glued-word fragments
#     ("Jxo", "Jan", "An中两点的距离：");
#   * nonempty title                      -> kills titleless running heads ("§4.").
# EN letter-headed books (Karlin) are NOT served here — they have their own
# D_LETTER_SEC_LOCAL / extract_items_kt machinery with uppercase-title guards.
SUB_GLOBAL = re.compile(r'^([A-Z])[．.、。:]?\s*([^\n]{0,60})$')
_SUB_MATH_OP_RE = re.compile(r'[=<>≤≥≠±×÷→←↔⇒∫∑√∂∇∈∋⊂⊃⊆⊇∪∩∞|‖\[\]{}]')
# 真子块头块宽实测 101–650px（长标题如附录 G 的多行头可达 ~700）；通栏散文
# /公式行 540–1036px 与之重叠，故宽度只做粗闸（≤720px 挡掉纯公式行），精确
# 判别靠：标题必须以汉字起始（真头全部汉字开头；杂讯如 "SDiffD上的右不变黎
# 曼度量"/"R上的每一个k-形式…"以大写拉丁开头）+ 禁句读标点（真标题无 ，。；
# ？！、）+ 装配期字母序列过滤兜底。
SUB_GLOBAL_MAX_WIDTH = 720


def _sub_global_title_ok(title):
    """Validate a SUB_GLOBAL candidate title (see the block comment above)."""
    t = (title or '').strip()
    if not t:
        return False
    if not re.match(r'[一-鿿]', t):
        return False
    if _SUB_MATH_OP_RE.search(t):
        return False
    if re.search(r'[，。；？！、]', t):
        return False
    return True
ITEM_CN = re.compile(
    r'^(?:定理|定义|引理|推论|命题|性质|例|注|表|图)\s*[（(]?(\d{1,2})[\.\．·。](\d{1,2})[\.\．·。](\d{1,3})[）)]?(?!\d)\s*(.{0,90})')
BARE_CN = re.compile(r'^[（(](\d{1,2})[\.\．·。](\d{1,2})[\.\．·。](\d{1,3})[）)](?!\d)\s*(.{0,90})')
EXER_CN = re.compile(r'^习题\s*(\d{1,2})[\.\．·](\d{1,2})')

# Exercise-region heading + numeric exercise detection.
# Many EN textbooks (e.g. Strogatz) number exercises `3.1.1` (DOT) with NO label
# word, so they are missed by EXER_3 (which requires a letter suffix `3.1.A.`) and
# by ITEM_3's trailing-dot requirement.  We detect the "EXERCISES FOR CHAPTER N"
# heading (case-insensitive, space-optional so it survives OCR like
# `EXERCISESFORCHAPTER3`) and, once inside that region, treat bare `C.S.N` numbers
# as exercises (EXER) rather than items.  do Carmo prints a BARE `EXERCISES`
# heading (no "FOR CHAPTER N") — the optional capture group lets both forms start
# the exercise region so its single-number "N. Problem" lines are NOT mistaken for
# sections/items.
# 🔴 ANCHORED (bug fix): the heading must BE the line (optional leading section
# number / § glyph; only dots/spaces may trail).  The old unanchored
# `.search()` latched the exercise region on ANY prose line merely CONTAINING
# "exercise(s)" ("We shall exercise caution…"), and in two-level mode without
# declared depths nothing but a SEC could reset the latch — one stray mention
# then suppressed every remaining SEC/ITEM row of the chapter.
EXER_HEADING = re.compile(
    r'^[§8Ss$\s]*(?:\d{1,2}(?:[.\-–·]\d{1,3})?[.\s]*)?'
    r'EXERCISES?(?:\s*FOR\s*CHAPTER\s*(\d+))?[.\s]*$', re.IGNORECASE)

# Config-driven end-of-chapter exercise-block headings（Ross《A First Course in
# Probability》体例："Problems" / "Theoretical Exercises" / "Self-Test Problems
# and Exercises"，可按书在 verify_config.json 的 exercise_region_headings 声明）。
# 与 EXER_HEADING（do Carmo/Strogatz 每节/每章 EXERCISES 块，SEC 可解除闩锁）
# 不同：章末习题块一旦进入就直到章末——闩锁 STICKY，其后任何「像节头」的行
# （如习题行 "3.11 Two cards..." 恰好通过 universal 节检测）都不再重置。
# 标题行匹配允许 OCR 大小写漂移与标题内部空白折叠；标题前允许页眉碎屑
# （§/8/S/$ 与可选编号），与 EXER_HEADING 同构。
def _exercise_headings_re(headings):
    parts = []
    for h in headings or []:
        h = str(h).strip()
        if not h:
            continue
        parts.append(r'\s+'.join(re.escape(w) for w in h.split()))
    if not parts:
        return None
    return re.compile(
        r'^[§8Ss$\s]*(?:\d{1,2}(?:[.\-–·]\d{1,3})?[.\s]*)?'
        r'(?:' + '|'.join(parts) + r')[.\s:.]*$', re.IGNORECASE)

# 章末习题块内的数字题号行："3.11. Two cards are ..." / "3.7 The king ..."。
# 仅当本书声明了 exercise_region_headings（opt-in）且闩锁已激活时捕获为 EXER。
STICKY_EXER_RE = re.compile(r'^(\d{1,2})\.(\d{1,2})\.?(?:\s+\S|$)')
EXER_3N = re.compile(r'^(\d{1,2})\.(\d{1,2})\.(\d{1,3})\b')

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
# 前缀容错与 D 层 sec_re（D_SEC_HEAD_A）对齐：§ 的 OCR 变形 §/S/s/8 之外，
# 孙文祥《遍历论》实测还有 `$6.3熵映射`（§→$），一并容忍。
# 2026-08-26 Ross 体例实测：节头脚注星号被 OCR 提到行首（`* 1.6 The Number…` /
# `* 6.6 Order statistics`）——前缀类补 `\*`，否则整节漏检。
_SEC_HEAD_RE = re.compile(r'^(?:[§8Ss$\*])?\s*(\d+(?:[.\-–·/．－〜]\d+)*)')
_SEC_TITLE_LABEL_RE = re.compile(
    r'(定义|定理|引理|命题|推论|例|公理|练习|评注|准则|图|表|'
    r'Definition|Theorem|Lemma|Proposition|Corollary|Example|Axiom|Exercise|'
    r'Remark|Figure|Fig|Table)')
# 标题首字符白名单：真小节标题可能以数学符号开头（Brin & Stuck §5.3
# "∈-Orbits"——∈ 不是 alnum，旧 isalnum 检查整节漏检）。
_SEC_TITLE_SYMBOLS = set('∈∗*×→←↦∀∃∈⊂⊆∩∪∞δΔ')
# 标签词 + 后随数字 = 条目标题；仅含标签词（无数字）是合法章节标题。
_SEC_TITLE_LABEL_NUM_RE = re.compile(
    r'(定义|定理|引理|命题|推论|例|公理|练习|评注|准则|图|表|'
    r'Definition|Theorem|Lemma|Proposition|Corollary|Example|Axiom|Exercise|'
    r'Remark|Figure|Fig|Table)\s*\d')


def _section_header_info(ln, ch=None, depths=None, max_depth=6):
    """Return ``(num_str, depth, title)`` for a genuine section header, else
    None.

    `ch` restricts to headers whose first numeric component == `ch` (used when
    scanning inside a chapter).  `depths` (set[int]) restricts to the declared
    section depths (>= 2); when None, any depth in ``[2, max_depth]`` is
    accepted.  `max_depth` bounds the hierarchy search (default 6 = chapter +
    5 nested levels).
    """
    def _validate(num_str, m_end):
        comps = [x for x in _SEC_SEP_RE.split(num_str) if x]
        if len(comps) < 2 or len(comps) > max_depth:
            return None
        if ch is not None and comps[0].isdigit() and int(comps[0]) != ch:
            return None
        depth = len(comps)
        if depths is not None and depth not in depths:
            return None
        rest = ln[m_end:].lstrip()
        # Tolerate an optional dot right after the number ("1-2. Parametrized
        # Curves", do Carmo) — a real header may print `C.S. Title`; strip the
        # punctuation run before the alnum check below.
        rest = rest.lstrip('.．。').lstrip()
        if not rest or not (rest[0].isalnum() or rest[0] in _SEC_TITLE_SYMBOLS):
            return None  # number with no following title -> not a header
        title = rest[:20]
        # 标签词只有后随数字才是条目标题（"2.1 Definition of ..."）；纯含标签词的
        # 章节标题（"4.4 Examples"、"5.11 Axiom A and Structural Stability"）是
        # 真小节，不得据此拒绝（Brin & Stuck 实测整节漏检根因）。
        # 🔴 锚定改为「标题起始」：条目标题的标签词必在编号紧后（标题起点），
        # 而真小节标题中部的「定理+页码粘连」（孙文祥《遍历论》实测
        # "82.4Poincaré回复定理43"——页眉页码 43 粘在「定理」后构成
        # "定理43" 假条目形态）不应触发拒绝，否则整节漏检。
        if _SEC_TITLE_LABEL_NUM_RE.match(title.lstrip()):
            return None  # labeled item / figure / table, not a section
        # 短标题守卫：拉丁字母 1-3 字（"A"/"B" OCR 图示残粒）拒；含 CJK 的
        # 2-3 字真标题（孙文祥《遍历论》"熵映射"/"平衡态"）保留。
        _rest_stripped = rest.strip()
        if len(_rest_stripped) < 4 and not re.search(r'[一-鿿]', _rest_stripped):
            return None  # too short to be a title ("A"/"B" junk from OCR'd
            # section-dependency diagrams like "5-6.A") — real titles have words
        if not re.search(r'[A-Za-z一-鿿∈∗\*]', title):
            return None
        # A genuine section title is Title-Case / Han / starts with a digit — reject
        # prose that begins with a lowercase word (e.g. "20.6 and it is stated...",
        # "14-1-0359 and W911NF..." grant numbers glued to text).  Only a leading
        # lowercase ASCII letter is rejected; Han / digit / uppercase are kept.
        first = next((c for c in rest if c.isalnum()), None)
        if first is not None and 'a' <= first <= 'z':
            # 容忍「小写符号变量 + 连字 + 大写词」型标题：Brin & Stuck §5.3
            # "∈-Orbits" 被 OCR 读成 'e-Orbits'——首字符小写但非散文。
            if not re.match(r"[a-z][-–—][A-Z]", rest):
                return None
        rest = rest.strip()
        # 印刷页码右缘粘连清尾：「…极限点25」型——CJK 后紧跟 1–3 位数字收尾，
        # 是页眉/页脚页码粘进节标题的 OCR 形态（周民强《实变函数论》实测），
        # 去掉尾部数字恢复干净标题。
        _glue_pg = re.match(r'^(.*[一-鿿])(\d{1,3})$', rest)
        if _glue_pg and len(_glue_pg.group(1)) > 4:
            rest = _glue_pg.group(1)
        return num_str, depth, rest

    m = _SEC_HEAD_RE.match(ln)
    if m:
        v = _validate(m.group(1), m.end())
        if v:
            return v
    # Fallback: § glyph OCR'd into a GLUED LEADING DIGIT (周民强《实变函数论》
    # 实测 §5.1 → "55.1单调函数的可微性"，§→5 重复首数)。形态＝一个散落数字
    # （可再夹一个 §/8/S/s/$ 垃圾符）后跟真正的 C.S 头。该变体只在捕捉到的
    # 首分量 == 当前章号时才放行（_validate 内强制），且普通正文行极少以
    # 「重复章号+小节号」开头，误报风险低。
    m2 = re.match(r'^\s*\d\s*[§8Ss$\*]?\s*(\d{1,2}(?:[.\-–·/．－〜]\d{1,3})*)', ln)
    if m2:
        v = _validate(m2.group(1), m2.end())
        if v:
            return v
    return None


# Map an integer `ordinal` (config) to scan_skeleton's parsing mode.
# Returns one of 'three-level' (default western 3-level), 'two-level'
# (western/EN/GM 2-level), or 'cn' (Chinese 3-level).
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


def scan(extract_dir, ch, start, end, mode, section_depths=None, chapter_first=None,
         exercise_headings=None, plain_sec_heads=False):
    rows = []
    # Exercise-region state: once "EXERCISES" / "EXERCISES FOR CHAPTER N" is seen,
    # all subsequent bare `C.S.N` numbers (three-level mode) are exercises, and in
    # two-level mode we also suppress SEC_2 / ITEM_2 so single-number "N. Problem"
    # exercise lines (do Carmo) are NOT mistaken for sections/items.
    in_exercise = False
    # Ross-style STICKY chapter-end exercise region（exercise_region_headings 声明）：
    # 一旦进入章末习题块就直到章末——SEC 检测不再解除闩锁（习题行
    # "3.11 Two cards..." 恰好长得像节头，绝不能把它当「新节」重置）。
    ex_head_re = _exercise_headings_re(exercise_headings) if exercise_headings else None
    sticky_exer = ex_head_re is not None
    # Depth-agnostic section detection (config-driven).  When the book declares
    # `section_depths`, we use the universal detector for SEC rows (it catches
    # genuine section headers at ANY declared depth, including mixed depth like
    # 20.5 + 20.5.1) and skip the mode's single-depth SEC regex.  Item/exercise
    # detection still uses the per-mode regexes below.  When `section_depths`
    # is absent (legacy / no config) we fall back to the old per-mode SEC regex
    # for back-compatibility.
    depths_set = (set(d for d in section_depths if isinstance(d, int) and d >= 2)
                  if section_depths else None)
    # Global single-number sections (Arnold-style "§12．变分法", section_types
    # like [1, 1]): enabled iff a section level BELOW the chapter level has
    # depth 1.  Standard books ([1, 2]...) have no such level -> branch off.
    global_sec = bool(section_depths) and any(
        isinstance(d, int) and d == 1 for d in section_depths[1:])
    # Current global §N while scanning (for SUB letter-head parentship).
    cur_global_sec = None
    # 🔴 Only enable the universal (depth-agnostic) detector when there is at
    # least one depth>=2 section to find.  A book whose sections are single
    # numbers (`## §N`, e.g. do Carmo) has `depths_set == set()` (empty) — the
    # universal detector REJECTS single-number headings (`len(comps) < 2`), so
    # leaving it on would silently detect ZERO sections and force every item to
    # page-proximity.  `bool(depths_set)` falls back to the mode's SEC regex
    # (SEC_2 for two-level) which correctly catches single-number sections.
    use_universal_sec = bool(depths_set)
    for p in range(start, end + 1):
        fp = os.path.join(extract_dir, 'page_%03d.json' % p)
        if not os.path.exists(fp):
            continue
        with open(fp, encoding='utf-8') as fh:
            d = PageJson.load(os.path.join(extract_dir, 'page_%03d.json' % p)).data
        for it in d.get('text', []):
            poly = it.get('poly') or []
            try:
                ln_w = (float(poly[2]) - float(poly[0])) if len(poly) >= 3 else None
            except Exception:
                ln_w = None
            try:
                ln_y = float(poly[1]) if len(poly) >= 8 else None
            except Exception:
                ln_y = None
            for _raw in (it.get('text') or '').split('\n'):
                ln = _raw.rstrip('$').strip()
                if not ln:
                    continue
            # Exercise-region detection (case-insensitive, space-optional so it
            # survives OCR like `EXERCISESFORCHAPTER3`).  Once seen, the chapter
            # is in its exercise block through to the next genuine section
            # header (multi-section books like do Carmo run an EXERCISES block
            # at the END OF EVERY SECTION, so the latch must reset on SEC).
            if ex_head_re is not None and not in_exercise and ex_head_re.match(ln):
                # Ross 体例章末习题块头（"Problems" 等）：STICKY 闩锁激活，
                # 其后直到章末不再有正文/节。
                in_exercise = True
                continue
            if not in_exercise and EXER_HEADING.match(ln):
                in_exercise = True
                # 编号习题节标题（"2.6 Exercises"）同时是真实小节：在声明了
                # section_types 的书里补发 SEC 行进骨架，避免该节从骨架中消失。
                # （P 层对习题专属节本就豁免必写，但 D 层连续性/骨架仍需要它。）
                if depths_set is not None:
                    _secinfo = _section_header_info(ln, ch=ch, depths=depths_set)
                    if _secinfo is not None:
                        rows.append((p, 'SEC', _secinfo[0], _secinfo[2], ln_y))
                continue
            # --- universal, depth-agnostic section detection ---
            # Runs BEFORE (not gated by) the exercise latch: a real section
            # header after an exercise block must be detected AND end that
            # block.  Bare `N.M` exercise lines are single/double-component
            # numbers without label titles and are rejected by
            # `_section_header_info`, so they cannot fake a section.
            # 🔴 STICKY 例外：声明了 exercise_region_headings 的书，章末习题块
            # 之后不再有正文——闩锁激活后跳过 universal 节检测（习题长句
            # "3.11 Two cards..." 会被 universal 检测误判为真节头并错误解除闩锁）。
            if depths_set is not None and not (sticky_exer and in_exercise):
                sec = _section_header_info(ln, ch=ch, depths=depths_set)
                if sec is not None:
                    num_str, _depth, title = sec
                    rows.append((p, 'SEC', num_str, title, ln_y))
                    in_exercise = False  # new section ends the exercise region
                    continue
            # --- sticky exercise-region numeric problem lines -----------------
            # "3.11. Two cards are ..." / "3.7 The king ..." → EXER 行
            # （键=印刷题号 "3.11"；Problems 与 Self-Test 两块题号各自从 1 重排，
            # 同号去重由 build_structure 的 _exer_seen 处理）。
            if sticky_exer and in_exercise:
                m = STICKY_EXER_RE.match(ln)
                if m and int(m.group(1)) == ch:
                    rows.append((p, 'EXER', '%s.%s' % m.group(1, 2),
                                 ln[m.end():].strip()[:90], None))
                    continue
            # --- global single-number section heads (Arnold-style) -----------
            # The § number is book-global, so NO `== ch` guard: scan() already
            # runs inside the chapter's page range, so every §N found here
            # belongs to this chapter.  Running heads repeat per page and are
            # deduped downstream (sec_best keeps the best title).
            if global_sec:
                # Plain prefix-less heads（Humphreys GTM 9，plain_sec_heads=True 时）：
                # 首个命中播种 cur_global_sec（章扉页到真节头之间无编号行，安全），
                # 其后严格 num == cur+1 —— 习题区重排小号与未来节号的习题行一律拒绝。
                if plain_sec_heads:
                    _m = SEC_GLOBAL_PLAIN.match(ln)
                    if (_m
                            and (cur_global_sec is None
                                 or int(_m.group(1)) == cur_global_sec + 1)
                            and int(_m.group(1)) <= SEC_MAX_NUMBER
                            and not _m.group(2).rstrip().endswith('.')):
                        # 无 y 下限守卫：本书页眉为「词+粘连页码」形态（词首，
                        # 永不匹配本正则），而真节头可起于新页顶 y≈80-90。
                        rows.append((p, 'SEC', _m.group(1), _m.group(2).strip(), ln_y))
                        in_exercise = False
                        cur_global_sec = int(_m.group(1))
                        continue
                m = SEC_GLOBAL.match(ln) or SEC_GLOBAL_9.match(ln)
                if m:
                    rows.append((p, 'SEC', m.group(1), m.group(2).strip(), ln_y))
                    in_exercise = False
                    cur_global_sec = int(m.group(1))
                    continue
                # Glued / separator-less variant（谷超豪《数学物理方程》体例，见
                # SEC_GLOBAL_GLUE 注释）。守卫：页眉区 y 压制 + 短行宽闸 + 标题校验。
                # 🔴 plain_sec_heads 书（Humphreys GTM 9）禁用本变体：glue 正则的
                # § 前缀可选、数字后紧跟任意字母/汉字即命中——本书权重表行
                # "4入1 -3入2" 恰好命中并被伪造成节，还会抢走后续条目挂接。
                m = None if plain_sec_heads else SEC_GLOBAL_GLUE.match(ln)
                if (m and int(m.group(1)) <= SEC_MAX_NUMBER
                        and _glue_title_ok(m.group(2))
                        and (ln_y is None or ln_y >= _GLUE_MIN_Y)
                        and (ln_w is None or ln_w <= _GLUE_MAX_WIDTH)):
                    rows.append((p, 'SEC', m.group(1), m.group(2).strip(), ln_y))
                    in_exercise = False
                    cur_global_sec = int(m.group(1))
                    continue
                # 节末习题块头（"习题"独占一行；谷超豪《数学物理方程》每节末
                # 印习题块，TOC 亦记 "习题(N)"）：记为该节的 EXER 行（键=当前节
                # 号），供写作契约标注习题块位置。练习节点不强制落地，缺失无害。
                if cur_global_sec is not None and re.match(r'^习\s*题\s*$', ln):
                    rows.append((p, 'EXER', str(cur_global_sec), '习题'))
                    continue
                # Bare-letter sub-block head ("A.变分"): parented under the
                # current global §N when one is active ("<N>.<L>"), parentless
                # (".<L>") otherwise — appendix chapters have no numeric §
                # heads, so their letter sections scan as parentless and are
                # promoted to SEC rows by build_structure at assembly time.
                m = SUB_GLOBAL.match(ln)
                if (m and _sub_global_title_ok(m.group(2))
                        and (ln_w is None or ln_w <= SUB_GLOBAL_MAX_WIDTH)):
                    parent = f"{cur_global_sec}." if cur_global_sec else "."
                    rows.append((p, 'SUB', parent + m.group(1),
                                 m.group(2).strip()))
                    continue
            if mode == 'two-level':
                m = SEC_2.match(ln)
                # 🔴 chapter_first gate: for section-scoped books (do Carmo,
                # chapter_first=False) section numbers restart per chapter and
                # are INDEPENDENT of the chapter number, so the `== ch` guard
                # must be disabled (otherwise "2. Riemannian Metrics" inside
                # chapter 1 would be rejected).  Chapter-first books keep the
                # guard; legacy callers (chapter_first=None) also keep it.
                _sec_ch_ok = ((chapter_first is False) or m is None
                              or (int(m.group(1)) == ch))
                if (not use_universal_sec and not in_exercise and not plain_sec_heads
                        and m and _sec_ch_ok
                        and int(m.group(1)) <= SEC_MAX_NUMBER
                        and not m.group(2).endswith('.')):
                    rows.append((p, 'SEC', m.group(1), m.group(2).strip(), ln_y))
                    continue
                m = EXER_2.match(ln)
                if not in_exercise and m and int(m.group(1)) == ch:
                    rows.append((p, 'EXER', '%s.%s' % m.group(1, 2), m.group(3).strip()))
                    continue
                m = ITEM_2.match(ln)
                if not in_exercise and m and int(m.group(1)) == ch:
                    rows.append((p, 'ITEM', '%s.%s' % m.group(1, 2), m.group(3).strip()))
            elif mode == 'cn':
                m = SEC_CN.match(ln)
                if not use_universal_sec and m and int(m.group(1)) == ch:
                    if m.group(1).startswith('0') or m.group(2).startswith('0') or int(m.group(2)) == 0:
                        continue
                    rows.append((p, 'SEC', '%s.%s' % m.group(1, 2),
                                 ln[m.end(2):].lstrip(' \u00a7.．·。').strip(), ln_y))
                    continue
                m = SECBARE_CN.match(ln)
                if not use_universal_sec and m and int(m.group(1)) == ch:
                    if m.group(1).startswith('0') or m.group(2).startswith('0') or int(m.group(2)) == 0:
                        continue
                    rows.append((p, 'SEC', '%s.%s' % m.group(1, 2), '', ln_y))
                    continue
                m = SECGLUE_CN.match(ln)
                if not use_universal_sec and m and int(m.group(1)) == ch:
                    if m.group(1).startswith('0') or m.group(2).startswith('0') or int(m.group(2)) == 0:
                        continue
                    rows.append((p, 'SEC', '%s.%s' % m.group(1, 2),
                                 ln[m.end(2):].lstrip(' \u00a7.．·。').strip(), ln_y))
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
                if in_exercise:
                    m = EXER_3N.match(ln)
                    if m and int(m.group(1)) == ch:
                        rows.append((p, 'EXER', '%s.%s.%s' % m.group(1, 2, 3),
                                     ln[m.end():].strip()[:90]))
                        continue
                m = SEC_3.match(ln)
                if not use_universal_sec and m and int(m.group(1)) == ch and not m.group(3).endswith('.'):
                    rows.append((p, 'SEC', '%s.%s' % m.group(1, 2), m.group(3).strip(), ln_y))
                    continue
                m = EXER_3.match(ln)
                if m and int(m.group(1)) == ch:
                    rows.append((p, 'EXER', '%s.%s.%s' % m.group(1, 2, 3), m.group(4).strip()))
                    continue
                m = ITEM_3.match(ln)
                if m and int(m.group(1)) == ch:
                    rows.append((p, 'ITEM', '%s.%s.%s' % m.group(1, 2, 3), m.group(4).strip()))
    # global_sec（单级节号书）的节键必为单一数字：mode 正则（SEC_CN/SEC_2…）
    # 捕获的 "C.S" 形态在此类书里只可能是图号/页码粘连等散文误报（谷超豪
    # 《数学物理方程》ch7 实测 "7.7 所示"），一律剔除。
    if global_sec:
        rows = [r for r in rows if r[1] != 'SEC' or '.' not in str(r[2])]
    # 统一 5 元组 (p, kind, num, title, y)：SEC 行发射处已带块顶 y（页眉压制的
    # glue 变体与同页 y 感知归都依赖它）；EXER/ITEM/SUB 行 y=None。
    rows = [r if len(r) == 5 else (r[0], r[1], r[2], r[3], None) for r in rows]
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
        for row in rows:
            p, kind, num, title = row[0], row[1], row[2], row[3]
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
