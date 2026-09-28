"""scan_skeleton.py — 扫描原书某章的【真实结构骨架】（SEC/EXER 行）。

现主要作为 `build_structure.py` 的内部依赖（被 `import` 调用 `scan()` / `_mode_for_ordinal()`
供其拼装分章契约 `book_structure/ch{N}.json`）；其 standalone CLI 仅向 stdout 打印扫描结果（诊断用），不写任何文件。

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
import collections
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
from lib.numbering import (ordinal_depth, resolve_ordinal_code,
                           has_exercise_word, is_exercise_head_text)
from verify_config import (ORDINAL_LANGUAGE_DEFAULT,
                       ConfigLoader, ConfigError)

# 节标题：可带 Vakil 的可选标记（★ 被 OCR 成 + / * / x），标题也可能以单字母词开头
# （"3.5 A base of ..."），故只要求首字符大写、长度 4~72。
SEC_3 = re.compile(r'^(\d{1,2})\.(\d{1,2})\s+[+*x\u00d7\u2605\u2606]?\s*([A-Z].{3,72})$')
ITEM_3 = re.compile(r'^(\d{1,2})\.(\d{1,2})\.(\d{1,3})\.\s*(.{0,90})')
EXER_3 = re.compile(r'^(\d{1,2})\.(\d{1,2})\.([A-Z])\.\s*(.{0,90})')
# 🔴 空格分隔变体（Rising Sea 实测 57 处）：「印刷 C.S.X 后接空格而非句点」
# （'4.3.F IMPORTANT EASY EXERCISE…' / '14.2.F EXERCISE…'）——EXER_3 要求
# 字母后紧跟 `.` 整行失配；SEC_3（`N.M` + 大写词）反而先命中，条头被伪造
# 成节行、去重时连同真习题一起消失。本变体 `C.S.X + 空白 + 大写词` 须在
# SEC_3 之前判，且**必须**命中习题题头词形（is_exercise_head_text），
# 否则与真节头 '10.1 Separated morphisms' 无法区分。
EXER_3_SV = re.compile(r'^(\d{1,2})\.(\d{1,2})\.([A-Z])\s+([A-Z].{0,90})')
# 字母练习号字形乱码恢复（Vakil《Rising Sea》全书实测 58 处）：OCR 把字母
# 练习号 C.S.O / C.S.I 读成数字 0 / 1（该体例无 0 号、且 "C.S.1" 与真条目
# 10.1.1 撞键被去重吞掉）。仅当 0/1 位后的同行为【练习头形态】（修饰词 +
# EXERCISE + 边界标点，SSOT lib.numbering.is_exercise_head_text）才升回字母，
# 真条目头（"10.1.1. Motivation."）与跨引用行不受影响。
EXER_3_GARBLE = re.compile(r'^(\d{1,2})\.(\d{1,2})\.([01])\.\s*(.{0,110})')
_EXER_GARBLE_LETTER = {'0': 'O', '1': 'I'}

# Two-level section: "2 Riemannian Metrics" / "1. Introduction".  Allow an
# OPTIONAL leading noise char before the number — do Carmo's OCR mis-reads the
# section sign (§) / dagger as an apostrophe, producing "'1. Introduction", which
# a strict `^\d` anchor would miss.  Also allow an OPTIONAL dot after the number
# ("2. Riemannian Metrics" — do Carmo prints sections as `N. Title` with a dot,
# while its page-number RUNNING HEADERS are printed as `N Title` WITHOUT a dot,
# so the optional dot lets us match real dotted sections while the page-number
# guard below still rejects the headers).  The noise set is tiny and a prose
# line never starts with "'N.", so this is benign for other books.
# 🔴 Title may also start with a DIGIT or '&': Hilton & Stammbach GTM 4 prints
# sections like "3. ℤ-Satellites" whose blackboard-bold ℤ OCRs variously as
# "8" / "6" / "&" ("3. 8-Satellites", "2. &-Derived Functors") — a strict
# `[A-Z]` start silently dropped those sections from the skeleton.  Pure-number
# titles are still rejected below (`_sec2_title_ok`).
SEC_2 = re.compile(r"^(?:['\u2019\u00b6\u00a7\u2020\*]\s*)?(\d{1,2})\.?\s+[+*x\u00d7\u2605\u2606]?\s*([A-Z0-9&].{3,72})$")


def _sec2_title_ok(title: str) -> bool:
    """Reject SEC_2 titles that are pure numbering/math fragments ("2.3", "8 12")."""
    t = title.strip()
    if not t:
        return False
    if re.fullmatch(r"\d{1,2}(?:[.\uFF0E]\d{1,3})*[.．]?", t):
        return False
    return bool(re.search(r"[A-Za-z\u4e00-\u9fff]", t))

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
from lib.util import blk_text

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
# SPACED-prefix global § heads (Arnold《Ordinary Differential Equations》2e 实测):
# 真节头印「§ + 空格 + 数字 + (可选「.」) + 空格 + 英文标题」，如
#   '§ 1. Phase Spaces' / '$ 21. The Classification…' / 'S 11. First-order…'
#   / '§ 26 Quasi-polynomials'（§26 数字后【无句点】）/ '§ 18.Complexification…'
#   （句点后无空格、且粘连页码）。既有 SEC_GLOBAL 要求前缀字符【紧贴】数字
#   （不允许中间空格），本书几乎每处都带空格 → 整批 § 漏检，仅极少数粘连页眉
#   '§6. Symmetries' 侥幸命中（实测全书只抓到 §1/§6）。本变体允许前缀与数字间
#   零或多空格、数字后分隔符可选，靠【强制 §-族前缀 + 标题首字母大写】两道闸
#   把真节头与噪声干净区分：
#   * 前缀类收紧为 [§$S]（§ 及其 OCR 变形 $/S），剔除 8/s/6——它们会与页码
#     '88 Chapter…'、正文 'S1 there are…' 碰撞（放宽时空格+可选题号分隔符放大误报）；
#   * 标题必须 [A-Z] 开头——本书全部真节题首字母大写；小写开头的 'S1 there are
#     points…'（公式行）被杀；汉字节题（Arnold《数学方法》'§12．变分法'）本变体
#     不触发、仍由 SEC_GLOBAL 消费 → 对既有 global_sec 书零回归；
#   * 号后 `(?!\d)` 防吃进多位号；`[．.]?` 兼容 §26 无点与 §1 有点两形态。
SEC_GLOBAL_SPACED = re.compile(
    r'^([§$S])\s*(\d{1,2})(?!\d)[．.]?\s*([A-Z][^\n]{1,60})$')
# Trailing OCR page-number glued/space-separated to an English section title
# ('Phase Flows 57' / 'Complexification and Realification177'): strip for the
# contract name. English math section titles never end in bare digits.
_SEC_SPACED_TRAIL_PAGE = re.compile(r'(?:\s{1,3}\d{1,4}|\d{2,4})\s*$')
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

# 🔴 页眉带（running-head band）判据（Apostol《Introduction to Analytic Number
# Theory》实测 2026-09-28）：印刷把当前习题块标题**作为页眉**重复印在每页页首
# **右侧**（p155 页眉 "Exercises for Chapter 7" x0=721 y=59，而正文块左边界
# x0≈71、正文起始 y≈155）。习题区闩锁一旦被页眉复本在页首抢先激活，同页其后的
# 正文条目（该页真身是 Theorem 7.10）就被 ITEM 抑制整条吞掉——抽取器漏条目、
# 闸门只能靠源侧回填兜底。判据两条都要：① 块顶落在页首带内（y < 100）；
# ② 块首 x 明显右移（> 本页左边界 + 1/4 页宽）——真节/习题块标题恒在左边界，
# 只有页眉跑马行右对齐。缺 poly 时返回 False（fail-open，宁闩不漏）。
# 🔴 页首带**按本页自己的最顶文本行**放宽（Arnold《经典力学的数学方法》实测
# 2026-09-28）：本书扫描页幅大，页眉印在 y≈119，绝对阈值 100 一律漏网；于是
# p162 页眉「§36．外微分」(x0=572, y=119) 被当成 §36 的窗口左界，而 §35 的尾条
# 问题13/14 正印在同一页页眉**之下**（y=604/745，真 §36 节头在更下的 y=1053），
# 两条被判给 §36（契约里挂错节）。`top + _HEAD_TOP_TOL` 与绝对阈值取大者：既有
# 书（页眉恒 <100）行为逐字不变，只把带下界推到「本页第一行印刷」这一页相对位置。
_HEAD_BAND_Y = 100.0
_HEAD_TOP_TOL = 12.0
_GLUE_MAX_WIDTH = 1000.0


def page_x_extent(blocks):
    """本页文本块的 (左边界, 页宽跨度)；无 poly 时返回 (None, None)。"""
    polys = _polys(blocks)
    if not polys:
        return None, None
    left = min(float(q[0]) for q in polys)
    right = max(float(q[2]) for q in polys)
    return left, (right - left)


def _polys(blocks):
    """带可用 poly（≥8 个坐标）的块多边形列表。"""
    return [b.get('poly') for b in blocks
            if isinstance(b.get('poly'), (list, tuple)) and len(b.get('poly')) >= 8]


def page_top_y(blocks):
    """本页最顶文本行的 y（页眉相对带用，见 `is_running_head`）；无 poly 时 None。"""
    ys = _polys(blocks)
    return min(float(q[1]) for q in ys) if ys else None


def is_running_head(x, y, left, span, top=None):
    """块是否页眉带复本（页首 + 明显右移），见 _HEAD_BAND_Y 注释。

    scan_skeleton 的习题区闩锁、build_structure 的习题区起点
    （`_exercise_region_start`）与节/字母块窗口左界（`_demote_head_band_rows`）
    共用本判据：三处都拿标题行当信号，页眉每页重印一遍，任一处在页首抢先采纳，
    同页其后的正文条目就被吞。带下界 = max(绝对 100, 本页最顶行 y + 容差)，
    `top` 由调用方按 `page_top_y` 传入。缺几何信息返回 False（fail-open，宁闩不漏）。
    """
    band = _HEAD_BAND_Y if top is None else max(_HEAD_BAND_Y, float(top) + _HEAD_TOP_TOL)
    return (x is not None and y is not None and left is not None
            and span is not None and span > 0
            and y < band and x > left + 0.25 * span)


def block_xy(poly):
    """块首 (x, y)；poly 缺失/畸形时 (None, None)。"""
    try:
        if len(poly or []) < 8:
            return None, None
        return float(poly[0]), float(poly[1])
    except Exception:
        return None, None


def demote_head_band_rows(rows, head_band):
    """删掉「同号在本页还有更靠下的行」的页眉带 SEC/SUB 行，返回 (新 rows, 删除数)。

    窗口左边界按「页 + 块首 y」分桶后，页眉复本会把本节左界推到页顶，于是**上一页
    末尾仍在续的条目**被判给本节（Arnold p162 案：§35 尾条 问题13/14 挂到 §36）。
    判据保守，两条都要满足才删：
      ① 该行落在 `is_running_head` 命中的页眉带线上（`head_band` = 扫描时按页记录
        的 (页, 页眉行 y) 集合，谓词与习题区闩锁同源）；
      ② 同一 (页, 节键) 在本页还有 y 更靠下的行（= 真节头在这一页，页眉只是复本）。
    本页只有页眉一行时**照旧保留**（页中无真节头时页眉是该节在这一页的唯一锚点），
    因此节起始页码、sec_pages 与 dedup「先到者胜出」一概不受影响。
    """
    if not head_band:
        return rows, 0
    grp = {}
    for i, r in enumerate(rows):
        if r[1] not in ('SEC', 'SUB') or len(r) < 5 or r[4] is None:
            continue
        grp.setdefault((r[0], str(r[2])), []).append((i, float(r[4])))
    kill = {i for (p, _k), lst in grp.items()
            for i, y in lst
            if (p, y) in head_band and any(y2 > y for _j, y2 in lst)}
    if not kill:
        return rows, 0
    return [r for i, r in enumerate(rows) if i not in kill], len(kill)


# ---------------------------------------------------------------------------
# 节头标题**跨行印刷**的悬挂续行（Apostol《Introduction to Analytic Number
# Theory》实测 2026-09-28：§3.2 印成两块——
#   块 i   [66, 899, 719]  '3.2 The big oh notation. Asymptotic equality'
#   块 i+1 [126, 936, 302] 'of functions'
#   块 i+2 [68, 992, 597]  'Definition If g(x) > 0 …'（正文栏归位）
# 同型还有 §4.8/§7.2/§8.5/§8.10/§10.2/§13.3。扫描只取节头块首行 ⇒ 两个后果：
#   ① 契约节名丢掉标题尾巴，拼进最终 md 的 `## §3.2 …` 少半截（保真缺陷）；
#   ② 奇偶页页眉印的是**完整**标题，于是 ②c 正文守恒闸把页眉复本判成
#      「印面收集到、契约里没有」的丢失正文块（假丢失，实为①的下游）。
# 判据全部是**几何 + 形态**，不点名书、不查词表；续行须同时满足：
#   · 悬挂缩进——左边界比节头行靠右 ≥ _SEC_CONT_MIN_INDENT（实测 56-78pt）；
#   · 相邻——行距在 _SEC_CONT_MIN_GAP.._SEC_CONT_MAX_GAP（实测 37-46pt，
#     新段落的段前空行使间距跳到 ≥80）；
#   · 短且窄——≤ _SEC_CONT_MAX_LEN 字符，且**比节头行本身窄**（正文首行恒为
#     整栏宽，这一条就把它挡掉；中文书的首行缩进段同理被此条拦截）；
#   · 非新头——自身不是节头 / 条目头 / 习题头形态，不以句读收尾；
#   · **三明治归位**——续行之后的块左边界回到节头行的左边界（容差
#     _SEC_CONT_RESUME_TOL）且不低于续行宽度，即「两行悬挂标题 + 正文重新起栏」。
# 判据测试：flows/write-source/structure/script/tests/test_heading_continuation.py
# （正例 7 条取本书实测几何，反例覆盖正文首行 / 条目头 / 段前空行 / 宽续行）。
# ---------------------------------------------------------------------------
_SEC_CONT_MAX_LEN = 60
_SEC_CONT_MIN_INDENT = 30.0
_SEC_CONT_MIN_GAP = 8.0
_SEC_CONT_MAX_GAP = 72.0
_SEC_CONT_RESUME_TOL = 20.0
_SEC_CONT_MERGED_MAX = 100
_SEC_CONT_TAIL_PUNCT = ".,;:，；：、"
# 🔴 **归位锚点须是可信正文块**（Apostol 2026-09-28 §2.7 实测）：印刷节头
#   '2.7 Dirichlet inverses and the Mobius' / 'inversion formula' 之后紧接的是
#   OCR 碎片 '2.8 If f'（score 0.18，宽 94pt），它左边界 253 既不对齐节头左边界
#   140 也不构成「回栏正文」，旧逻辑把它当唯一锚点 → 三明治判据不成立 → 标题尾巴
#   丢失。碎片不可信却占据锚点位，是这一类漏判的共性根因。
#   判据：锚点候选顺延至多 _SEC_CONT_RESUME_PROBE 块，**跳过**低置信（score <
#   _SEC_CONT_RESUME_MIN_SCORE）或过窄（宽 < 节头宽 × _SEC_CONT_RESUME_MIN_FRAC）
#   的块；第一个可信块仍不满足归位则照旧不补（保守，宁漏勿误）。
_SEC_CONT_RESUME_MIN_SCORE = 0.60
_SEC_CONT_RESUME_MIN_FRAC = 0.45
_SEC_CONT_RESUME_PROBE = 3


def _resume_anchor_trustworthy(blk, head_w):
    """归位锚点候选是否可信（非低置信 / 非过窄碎片）。"""
    try:
        score = float(blk.get("score"))
    except (TypeError, ValueError):
        score = 1.0
    if score < _SEC_CONT_RESUME_MIN_SCORE:
        return False
    r = block_rect(blk.get("poly") or [])
    if not r:
        return False
    if head_w and (r[2] - r[0]) < head_w * _SEC_CONT_RESUME_MIN_FRAC:
        return False
    return True


def block_rect(poly):
    """块的 (x0, y0, x1)；poly 缺失/畸形时 None。"""
    try:
        if len(poly or []) < 4:
            return None
        return float(poly[0]), float(poly[1]), float(poly[2])
    except Exception:
        return None


def heading_continuation(blocks, bi, title):
    """节头块 `blocks[bi]` 的印刷标题跨行续行文本；无续行时返回 None。

    见上方 `_SEC_CONT_*` 注释的判据。只做**只读几何/形态判定**，不改任何块。
    """
    if not title or blocks is None:
        return None
    if bi + 2 >= len(blocks):
        return None
    cur, nxt = blocks[bi], blocks[bi + 1]
    if not all(isinstance(b, dict) for b in (cur, nxt)):
        return None
    r0 = block_rect(cur.get("poly") or [])
    if not r0:
        return None
    head_w = r0[2] - r0[0]
    res = None
    for _j in range(bi + 2, min(bi + 2 + _SEC_CONT_RESUME_PROBE, len(blocks))):
        cand = blocks[_j]
        if not isinstance(cand, dict):
            break
        if not _resume_anchor_trustworthy(cand, head_w):
            continue
        res = cand
        break
    if res is None:
        return None
    cont = blk_text(nxt).strip()
    if not cont or "\n" in cont or len(cont) > _SEC_CONT_MAX_LEN:
        return None
    if cont[-1] in _SEC_CONT_TAIL_PUNCT:
        return None
    if not re.search(r"[A-Za-z\u4e00-\u9fff]", cont):
        return None
    # 续行不得自己是条头（'Theorem 7.1 There are…' / 裸号习题 '4. Let …'）
    if re.match(r"^[0-9]", cont):
        return None
    if re.match(r"^[A-Za-z][A-Za-z'.]*[ \t]+[0-9]", cont):
        return None
    if _section_header_info(cont, depths=None) is not None:
        return None
    if len(title) + 1 + len(cont) > _SEC_CONT_MERGED_MAX:
        return None
    r0, r1, r2 = (block_rect(cur.get("poly") or []),
                  block_rect(nxt.get("poly") or []),
                  block_rect(res.get("poly") or []))
    if not (r0 and r1 and r2):
        return None
    cx0, cy0, cx1 = r0
    nx0, ny0, nx1 = r1
    rx0, ry0, rx1 = r2
    if nx0 < cx0 + _SEC_CONT_MIN_INDENT:
        return None
    gap = ny0 - cy0
    if not (_SEC_CONT_MIN_GAP <= gap <= _SEC_CONT_MAX_GAP):
        return None
    if (nx1 - nx0) >= (cx1 - cx0):
        return None
    if abs(rx0 - cx0) > _SEC_CONT_RESUME_TOL:
        return None
    if rx1 < nx1 or ry0 <= ny0:
        return None
    return cont


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


# ---------------------------------------------------------------------------
# 🔴 全局单号节书（sections_global）的「幻一节头」闸（Arnold《经典力学的数学
# 方法》中译本实测 2026-09-28）。
# 印刷体例：节头 `§N．标题` **居中**，且每页页眉重印当前/下一节的节名。OCR 常把
# 页眉行与其下**正文行**粘成一行，产出形如
#   p19  '4黄上成事件堂宙A4电的平移构成一大重宝同八：'   （真身：§2 页眉 + 正文残句）
#   p34  '22平面上就给出了所求的轨道，称为利萨如图形.'   （§5 页眉带 + 正文句）
#   p174 '2n个数组成 T*V上点的局部坐标.'                （§37 页眉带 + 正文句）
#   p210 '9 光线的方向' / p232 '2 n个常微分方程'         （正文行首的数字碎片）
# 这类行命中 SEC_GLOBAL_GLUE（数字 + 直接粘连字母/汉字）→ 发出假 SEC 行，
# build_structure 落成假节节点，其**印刷节号与本已存在的书内 § 序列自相矛盾**
# （§1,§2,「§4」,§3 —— §4 真身在 ch2 p26），完整性闸门报「节序逆序」BLOCKING。
#
# 判据是**全书体例级**的，不点名书、不查词表：
#   ① 体例事实：`sections_global` 书的 § 号全书严格递增 ⇒ 一章（连续页区间）
#      内按阅读序取出的 § 号序列也必须严格递增。逆序点必有一侧是幻影。
#   ② 决定性判据：对**去重后的首次出现序**求最长严格递增子序列（LIS）。
#      某个号**不在任何**极大 LIS 上 ⇒ 它是「单调性硬冲突」，剔除后保留的节
#      严格更多 → 无条件剔除（ch2 的 22 / ch8 的 2 / ch9 的 9 / ch10 的 2）。
#   ③ 平局判据（LIS 长度相同、二选一，如 ch1 的 [1,2,4] vs [1,2,3]）：
#      只在**输家余文读起来不像标题**时才剔除。像标题（`_sec_title_shaped`
#      通过）的冲突号一律**不动**——把歧义留给闸门与人工，绝不自作主张删节。
#      标题形态判据：不得以句读/运算符起头、句中不得含子句标点（，,；;？！）、
#      不得以句点/冒号/分号等收尾（正文句的标志）。`、`（顿号）合法——
#      真节题「方程的导出、定解条件」用它并列。
#   ④ 附带修复：幻影节在扫描时已把 `cur_global_sec` 带偏，其后裸字母子块头
#      会被记成 `<幻影号>.<字母>` 父键；剔除时按阅读序把这些 SUB 行**重新挂到
#      该页之前最近的真节**（无真节则退化为无父键 `.<字母>`，与附录章同型）。
# 仅对 `global_sec` 生效、仅对**单数字节键**生效（点分小节键/字母键不参与），
# 其余书逐字节零回归。判据测试：
#   flows/write-source/structure/script/tests/test_global_sec_intruder_heads.py
# ---------------------------------------------------------------------------
_SEC_SINGLE_KEY_RE = re.compile(r'^\d{1,2}$')
# 句中子句标点：真节标题（名词短语）不含，正文句普遍含有。
_SEC_TITLE_SENT_INNER = re.compile(r'[，,；;？!]')
# 收尾句读：正文句以句号/冒号收尾，真节标题不带尾点。
_SEC_TITLE_SENT_TAIL = re.compile(r'[.．。:：;,、！!]$')
# 起头须是字母/数字/汉字（页眉粘连残句常以标点或运算符起头）。
_SEC_TITLE_HEAD_OK = re.compile(r'^[0-9A-Za-z\u4e00-\u9fff]')


def _sec_title_shaped(title):
    """单号节候选的**余文**是否读起来像节标题（False = 正文句/页眉粘连残句）。"""
    t = (title or '').strip()
    if not t:
        return False
    if not _SEC_TITLE_HEAD_OK.match(t):
        return False
    if _SEC_TITLE_SENT_INNER.search(t):
        return False
    if _SEC_TITLE_SENT_TAIL.search(t):
        return False
    return True


def _global_sec_intruders(seq):
    """阅读序单号 § 清单 -> 应剔除的节号集合。见上方「幻一节头」闸注释。

    `seq` = [(num, title), ...]（同一次扫描 = 同一章的页区间，按阅读序）。
    返回 `set[int]`；无冲突 / 冲突不可判定时返回空集（保守：宁留待人工）。
    """
    nums, shaped = [], []
    for num, title in seq or []:
        try:
            n = int(num)
        except (TypeError, ValueError):
            continue
        ok = _sec_title_shaped(title)
        if n in nums:
            i = nums.index(n)
            shaped[i] = shaped[i] or ok   # 同号二现（页眉复本）：任一模样像标题即算像
            continue
        nums.append(n)
        shaped.append(ok)
    m = len(nums)
    if m < 2:
        return set()
    # g[i] / f[i]：以 i 结尾 / 以 i 开头的最长**严格递增**子序列长度。
    g = [1] * m
    for i in range(m):
        for j in range(i):
            if nums[j] < nums[i] and g[j] + 1 > g[i]:
                g[i] = g[j] + 1
    f = [1] * m
    for i in range(m - 1, -1, -1):
        for j in range(i + 1, m):
            if nums[i] < nums[j] and f[j] + 1 > f[i]:
                f[i] = f[j] + 1
    L = max(g)
    if L == m:
        return set()          # 已单调：无需裁决
    on_max = [i for i in range(m) if f[i] + g[i] - 1 == L]

    # 极大 LIS 中「保留像标题的号」最多的那一条（平局判据的择路）。
    memo = {}

    def dp(i, left):
        """以 i 为起点、长度恰为 left 的递增子序列可保留的最大「像标题」数。
        不可能（f[i] < left）时返回 -1。"""
        if f[i] < left:
            return -1
        key = (i, left)
        if key in memo:
            return memo[key]
        mine = 1 if shaped[i] else 0
        if left == 1:
            res = mine
        else:
            best = -1
            for j in range(i + 1, m):
                if nums[j] > nums[i]:
                    v = dp(j, left - 1)
                    if v > best:
                        best = v
            res = mine + best if best >= 0 else -1
        memo[key] = res
        return res

    chosen = set()
    starts = [i for i in on_max if f[i] == L]
    best_i, best_v = None, -1
    for i in starts:
        v = dp(i, L)
        if v > best_v:
            best_i, best_v = i, v
    if best_i is not None:
        i, left = best_i, L
        while True:
            chosen.add(i)
            if left == 1:
                break
            target = dp(i, left) - (1 if shaped[i] else 0)
            nxt = None
            for j in range(i + 1, m):
                if nums[j] > nums[i] and dp(j, left - 1) == target:
                    nxt = j
                    break
            if nxt is None:
                break
            i, left = nxt, left - 1
    drop = set()
    for i in range(m):
        if i in chosen:
            continue
        if i not in on_max:
            drop.add(nums[i])              # 判据②：不在任何极大 LIS 上 → 硬冲突
        elif not shaped[i]:
            drop.add(nums[i])              # 判据③：平局 + 余文不成标题
    return drop


# 英文书「章内局部编号」单分量节头（Shafarevich《Basic Algebraic Geometry 1》
# 体例，2026-09-28 实测）：每章节头印裸 `N Title`（"1 Definition and Basic
# Properties"@p249，N 每章从 1 重起），小节印局部 `N.M Title`（"1.1 The Class
# Group"）。与 GLUE 正则的**空格兼容**（`(\d)[.]?\s*` + 大写起题），但丘维声
# 通道的 _glue_title_ok 要求 ≥2 汉字 → 英文书整章 sections=0（本分支的立项根
# 因）。误报由下列判据拦（页眉带 y≤98 复本**不能**压制——真节头就印在新页
# 页眉位）：
#   * Title-Case 名词短语：首词大写，其余词大写或虚词白名单——散文/习题行
#     （"9 If D C C1 x C2 is a divisor, prove…"、"3 Suppose that f : …"）的
#     功能词（if/that/prove）不在白名单 → 拒；
#   * 禁句点/数字混排（"1.7 and命题"、"2.1的第4题"型粘连）、禁数学运算符、
#     禁尾句读、禁条目标题（"3 Theorem 12"）、长度 ≤60；
#   * 标题归一 == 章名 → 页眉/书名页复本（"4 Intersection Numbers"@页眉）。
# 终极防线仍是 scan() 里的「首现必须为 1 + 此后 N==当前节+1」序列闩锁。
_CLN_EN_MAX_LEN = 60


def _cln_en_title_ok(title, ch_title_norm=''):
    t = (title or '').strip()
    if not t or len(t) > _CLN_EN_MAX_LEN:
        return False
    if not re.match(r"^[A-Z][A-Za-z]", t):
        return False
    if t[-1] in '.,;:!?':
        return False
    if re.search(r'[.]|\d', t):
        return False
    if _SUB_MATH_OP_RE.search(t):
        return False
    if _SEC_TITLE_LABEL_NUM_RE.match(t):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'\-]*", t)
    if not words:
        return False
    if len(words) == 1:
        # 单词真节题（Shafarevich ch4 §4 "Singularities"）合法；散文粘连行
        # 恒为多词，由下方 Title-Case 判据拒。
        return _norm_title_txt(t) != ch_title_norm
    for i, w in enumerate(words):
        if w[0].isupper():
            continue
        if i > 0 and w.lower() in _SEC_TITLE_FUNC_WORDS:
            continue
        return False
    if ch_title_norm and _norm_title_txt(t) == ch_title_norm:
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
# 判别靠：标题以汉字起始，或以「数字/小写字母 + 连字符 + 短汉字」起始的数学
# 名词复合词（§32「B.2-形式」「C.k-形式」，见 _sub_global_title_ok；杂讯如
# "SDiffD上的右不变黎曼度量"/"R上的每一个k-形式…"以大写拉丁开头）+ 禁句读标点
# （真标题无 ，。；？！、）+ 装配期字母序列过滤兜底。
SUB_GLOBAL_MAX_WIDTH = 720


def _sub_global_title_ok(title):
    """Validate a SUB_GLOBAL candidate title (see the block comment above)."""
    t = (title or '').strip()
    if not t:
        return False
    # 真头标题以汉字起头（「D.两个1-形式的外乘积」），或以「数字/小写字母 + 连
    # 字符 + 汉字」起头——Arnold《经典力学的数学方法》§32 实测 2026-09-28：字母块
    # 题就是「B.2-形式」「C.k-形式」这种**数学名词复合词**，首字符不是汉字。旧判据
    # 把它们整块丢弃 → §32 只登记到 D/E 两块，B/C 两块的 例1..例3 挤进同一计数器
    # 桶，跨块重号被吞（ANCHOR-SANITY FAIL）。放行形态极窄：连字符后紧跟汉字且整
    # 题短（散文噪声如「R上的每一个k-形式…」以大写拉丁开头、「m-1 个向量满足…」
    # 含空格/句读，均被后续守卫与本式拦住）。
    if not re.match(r'[一-鿿]', t):
        if not re.match(r'^[0-9a-z][\-—－][一-鿿]{1,6}$', t):
            return False
    if _SUB_MATH_OP_RE.search(t):
        return False
    if re.search(r'[，。；？！、]', t):
        return False
    return True

# --- NUMERIC local sub-block heads inside a global §N ----------------------
# Arnold《Ordinary Differential Equations》(2e) prints, INSIDE every global
# section `§ N. Title`, a run of **bare single-number** subsection heads that
# RESTART at 1 for each §:
#   `1. Examples of Evolutionary Processes`, `2. Phase Spaces`,
#   `3.The Integral Curves of a Direction Field` (no space after the dot!),
#   `6.Example:The Equation of Normal Reproduction` (colon, no space!), …
# These are the book's genuine level-2 subsections.  They are NOT a two-dotted-
# component `C.S` header (so `_detect_section_hierarchy`, which needs >=2
# components, cannot see them) and NOT a letter sub-block (SUB_GLOBAL only
# matches `[A-Z]`).  Structurally they are the NUMERIC cousin of the letter
# sub-block: a one-component ordinal that nests under the enclosing `## §N`.
# Detection is enabled ONLY when the caller passes `local_num_sec=True`
# (build_structure, from the config flag `numeric_local_sections`), so every
# other book is byte-for-byte unchanged.
#
# Guards (all fail-closed — a rejected candidate just falls through, it can
# never fabricate a subsection):
#   * number MUST be immediately followed by a separator (`.`/`．`/`:`/`：`/
#     `、`/`。`): kills footnote markers (`1 Isac Barrow…`, `2 Example: Such is…`
#     — number + SPACE, no separator) and running heads (`16  Chapter 1. Basic
#     Concepts` — page number + spaces + "Chapter", no separator after digits).
#   * space after the separator is OPTIONAL (`\s*`): catches `3.The…` / `6.Example:`.
#   * title must start with an UPPER-CASE Latin letter and be 2..61 chars: real
#     Arnold subsection titles are Title-Case English.  Kills prose/numbered-list
#     fragments starting lowercase and math residue.
#   * title must NOT contain math-operator chars (`= <> → …`): kills formula
#     fragments (`1 = 2, 2 = 0,` — though the leading `1 =` already fails the
#     separator test, this guards mixed lines).
#   * title must NOT look like a running head (contains "Chapter"/"§"/"Appendix"/
#     "Index"): second belt against page headers.
#   * per-§ CONTINUITY LATCH (enforced in scan(), not here): a match is accepted
#     ONLY if its number == (previous accepted local number within THIS §) + 1,
#     seeded at 1.  This is the decisive disambiguator: a stray `1.` prose line
#     inside body text cannot masquerade as subsection 1 unless it is literally
#     the first numbered head of the §, and any mid-paragraph list restart at a
#     non-next number is rejected.
SEC_LOCAL_NUM = re.compile(
    r'^(\d{1,2})[.．:：、。]\s*([A-Z][^\n]{1,60})$')


def _local_num_title_ok(title):
    """Validate a bare-numeric local sub-block candidate title (guards above)."""
    t = (title or '').strip()
    if not t:
        return False
    if _SUB_MATH_OP_RE.search(t):
        return False
    if re.search(r'\b(Chapter|CHAPTER|Appendix|APPENDIX|Index|§)', t):
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
# 🔴 尾随边界用前瞻 `(?![0-9.])` 而非 `(?:\s+\S|$)`（两处实测缺陷）：
#   * 旧 `\s+\S` 消费标题首字符——`ln[m.end():]` 切片把 "3.11. Two cards" 切成
#     "wo cards"（首字母被吃）；
#   * OCR/印刷把题号与题干粘连（"1.12It was noted..."）时 `\s+\S` 直接失配，
#     整条习题丢失（Casella & Berger ch1 实测 1.12/1.29/1.35）。
# 前瞻零宽：题号后不允许数字/点（防 "1.12" 误切成 1.1、防吃进三级号 "1.1.5"），
# 大写/小写/空白/行尾均放行（粘连与带空格两种形态统一覆盖）。
STICKY_EXER_RE = re.compile(r'^(\d{1,2})\.(\d{1,2})\.?(?![0-9.])')
# 章末裸单号习题行："4. Let S be any infinite subset of A(h, k)…"（Apostol 体例，
# 见下方 `bare_exer_idx` 分支注释）。点号或右括号后**必须**是空白 + 大写字母或
# 小题括号起头（"3. (a) Find all positive integers…" 实测），因此 C.S / C.S-N 体例
# 的题号（点后紧跟数字）天然不匹配，公式残行 "1 = A(k) +"、"(20)" 也一律不匹配。
STICKY_EXER_BARE = re.compile(r'^(\d{1,2})[.)][ \t]+(?=[A-Z(])')
# (?![0-9]) tail (was \b): OCR/print glues the title onto the number
# ('2.2.10Let A', '2.3.9State the dual') - \b fails digit->letter, losing
# whole exercises (Leinster 2014 measured). Inside the exercise-region
# latch, requiring only not-a-digit is safe.
EXER_3N = re.compile(r'^(\d{1,2})\.(\d{1,2})\.(\d{1,3})(?![0-9])')

# 🔴 题号第三段的「1 被 OCR 成 i/l/I」修复（Strogatz 3e ch5 实测）：习题 5.1.13 印作
# "5.1.13 Why do you think a 'saddle point'…"，OCR 给出 `5.1.i3 …` → EXER_3N 失配，
# 落到两段题号兜底分支被发成**假习题 5.1**（真号 13 丢失、契约多出一条与节号同形的
# 条目）。只在「数字.数字.」之后、且第三段是 `[lIi]` + 数字时把该字母换成 1：
# 罗马数字/字母分部（"10.3.A"、"5.1.i"）后面不接数字，一律不受影响。
EXER_OCR_ONE = re.compile(r'^(\d{1,2}\.\d{1,2}\.)[lIi](\d{1,3}(?![0-9]))')

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
# 2026-09-22 常庚哲《数学分析教程》实测：节头脚注/破折号被 OCR 粘到行首
# （`-2.6无穷小与无穷大`，§2.6 因前导 `-` 被 universal 检测器整节漏检）——前缀
# 类扩为「零或多」并纳入连字符族（ASCII `-`、en/em dash、全角 `－`）、项目符号
# `•`/`·` 与空白，覆盖「空白+破折号+编号」等行首装饰形态；数字本体判据不变。
_SEC_HEAD_RE = re.compile(
    r'^(?:[§8Ss$\*\-–—－•·\s])*(\d+(?:[.\-–·/．－〜]\d+)*)')
_SEC_TITLE_LABEL_RE = re.compile(
    r'(定义|定理|引理|命题|推论|例|公理|练习|评注|准则|图|表|'
    r'Definition|Theorem|Lemma|Proposition|Corollary|Example|Axiom|Exercise|'
    r'Remark|Figure|Fig|Table)')
# 标题首字符白名单：真小节标题可能以数学符号开头（Brin & Stuck §5.3
# "∈-Orbits"——∈ 不是 alnum，旧 isalnum 检查整节漏检）。
_SEC_TITLE_SYMBOLS = set('∈∗*×→←↦∀∃∈⊂⊆∩∪∞δΔ')
# 句首虚词/祈使动词守卫（Casella & Berger 实测）：以这类词开头的「编号+标题」
# 行是散文句（公式引用行被 OCR 掉括号后粘连："4.5.4 Hence the correlation…",
# "9.2.14 Notice that…", "10.1.12 We assume…"），不是节标题。真节标题以名词
# 短语开头（"Set Theory" / "The Delta Method" / "Does the MGF…"——'Does' 是
# 真标题首词，不在表内；'Itô' 因 Unicode 连字不匹配 \bIt\b 而安全）。
_SEC_TITLE_SENTENCE_STARTS = re.compile(
    r'^(?:Hence|Thus|Therefore|Then|So|Also|Since|Because|Now|It|This|These|'
    r'Those|There|Here|We|But|And|Or|If|When|While|Suppose|Let|Assume|Recall|'
    r'Notice|Observe|Consider|Prove|Show|Verify|Explain|Describe|Derive|'
    r'Compute|Calculate|However|Although|Moreover|Furthermore|Next|Similarly|'
    r'Indeed)\b')
# 🔴 Proof 冠头判据（Rosen《Discrete Mathematics》8e 实测 2026-09-25）：旧规则
# `Proof\b(?! of\b)` 一刀切拦「Proof 起头」，误杀 Rosen 三个真节标题
# "1.7.6 Proof by Contraposition"、"1.8.5 Proof Strategies"、
# "1.8.7 Proof Strategy in Action"（整节从骨架消失）。Rising Sea 散文证明行
# （"Proof." / "Proof by induction is…" / "Proof:"）与真节标题的**通用**形态差
# 别是：真节标题是 Title-Case 名词短语，Proof 后必带大写实词；散文行全小写虚
# 词延续。故判据改为：Proof 之后若不存在「大写开头的非停用词」→ 散文，拦；
# 存在 → 标题，放行。`Proof of Krull's …`（Rising Sea 旧豁免）是本规则特例
# （Krull 大写），行为不变；"Proof by induction"（小写延续）照旧拦。
_PROOF_STEM_RE = re.compile(r'^Proof(?![a-zA-Z])')
_PROOF_STOPWORDS = {'of', 'by', 'in', 'and', 'or', 'the', 'a', 'an', 'on', 'to',
                    'for', 'with', 'that', 'this', 'is', 'are', 'be', 'as',
                    'at', 'from', 'not', 'it', 'we', 'their'}
# 小写首词虚词/代词表（「技术术语首词豁免」的负名单，见 _validate 小写守卫）：
# 真节标题首词若是这些功能词，必是 OCR 粘连散文行；技术名词（n-ary/gcds/ip 等）
# 不在表内。大写形态（And/If/…）已由 _SEC_TITLE_SENTENCE_STARTS 拦截。
_SEC_TITLE_FUNC_WORDS = {
    'a', 'an', 'and', 'as', 'at', 'but', 'by', 'for', 'from', 'if', 'in',
    'into', 'is', 'it', 'its', 'nor', 'not', 'of', 'on', 'or', 'over', 'so',
    'see', 'than', 'that', 'the', 'their', 'them', 'then', 'there', 'these',
    'this', 'those', 'to', 'we', 'were', 'when', 'where', 'which', 'while',
    'with', 'without', 'also', 'thus', 'hence'}


def _proof_title_is_prose(rest_stripped):
    """True = rest begins with the stub 'Proof' and carries NO capitalized
    content word after it (prose proof line); False = 'Proof <Title Case …>'
    heading (or the rest does not start with Proof at all)."""
    if not _PROOF_STEM_RE.match(rest_stripped):
        return False
    for w in re.findall(r"[A-Za-z][A-Za-z'\-]*", rest_stripped[5:]):
        if w[0].isupper() and w.lower() not in _PROOF_STOPWORDS:
            return False
    return True

# 标签词 + 后随数字 = 条目标题；仅含标签词（无数字）是合法章节标题。
_SEC_TITLE_LABEL_NUM_RE = re.compile(
    r'(定义|定理|引理|命题|推论|例|公理|练习|评注|准则|图|表|'
    r'Definition|Theorem|Lemma|Proposition|Corollary|Example|Axiom|Exercise|'
    r'Remark|Figure|Fig|Table)\s*\d')


# 习题区闩锁内的「真节标题」判据（配合 scan() 的闩锁守卫使用）：
# 真节标题短（Casella & Berger 全部节标题 ≤ 41 字符，闩锁后首节 Miscellanea
# 仅 11 字符）且从不以句读收尾；习题行是成句散文（普遍 > 40 字符或以句点
# 收尾，OCR 行尾截断的也远超 40）。
_EXER_SEC_TITLE_MAX = 40


def _sec_like_title(title):
    """True if `title` looks like a REAL section title (short, no sentence
    punctuation at the end); False = prose-y exercise line inside a latched
    exercise region."""
    t = str(title or '').strip()
    if not t:
        return True  # 标题剥空（running head 残粒）交由上层守卫处理
    if len(t) > _EXER_SEC_TITLE_MAX:
        return False
    if t[-1] in '.,;:，；：':
        return False
    return True


def _expected_next_sec(last_num, ch):
    """紧随 `last_num` 之后应出现的印刷节号（同前缀、末段 +1）。

    章内尚无节头时返回 `ch.1`（章首第一节）。用于「序位豁免」判据（见
    `_section_header_info` 的 `successor_num`）——只描述号码接续，不做校验。
    """
    if last_num:
        m = re.match(r'^(.*?)([.\-–·/．－〜]?)(\d+)$', str(last_num))
        if not m:
            return None
        return '%s%s%d' % (m.group(1), m.group(2), int(m.group(3)) + 1)
    if ch is None:
        return None
    return '%s.1' % ch


def _section_header_info(ln, ch=None, depths=None, max_depth=6,
                         allow_cjk_comma=False, successor_num=None,
                         section_whitelist=None):
    """Return ``(num_str, depth, title)`` for a genuine section header, else
    None.

    `ch` restricts to headers whose first numeric component == `ch` (used when
    scanning inside a chapter).  `depths` (set[int]) restricts to the declared
    section depths (>= 2); when None, any depth in ``[2, max_depth]`` is
    accepted.  `max_depth` bounds the hierarchy search (default 6 = chapter +
    5 nested levels).  `allow_cjk_comma` relaxes the CJK 粘连句读守卫（标题内
    「，+汉字」）——真中文节题合法地含全角逗号（丘维声《解析几何》
    "4.2向量的外积的几何意义，平面的定向"，2026-09-26 实测 6 整节被该守卫
    漏发），仅在 `chapter_local_numbering` 模式打开，其余书零影响。
    `successor_num` 为「本章上一个节号 +1」（`_expected_next_sec`）：命中的
    候选行获得**序位豁免**，绕过两条散文形态守卫（成句散文体例的书，见下方
    注释）。不传即无豁免，行为与历史一致。
    `section_whitelist` 为本章目录真值小节号集合（agent 依 TOC 写出的
    `_section_whitelist.json`，见 scan() 的 `section_whitelist` 参数）：非空且
    命中号在册时，**序位豁免**升级为「序位 + 白名单」双确认豁免（`_waive`），
    追加绕过三条历史无条件守卫（句读尾、Proof 冠头、小写首词）——Serre《Linear
    Representations of Finite Groups》实测 2026-09-27，这几类真节题恰被三道守卫
    批量否决（"5.1 The cyclic group C," / "17.3 Proof of theorem 33" /
    "10.1 p-regular elements…"）。白名单缺失的书该组合恒 False，零回归。
    """
    def _validate(num_str, m_end):
        # 🔴 星标装饰串否决（Rising Sea 2026-09-24 实测）：真节头打印为
        # `C.S ⋆⋆Title`，⋆ 被 OCR 成 '+'——而 '+' 恰是数字分隔符，_SEC_HEAD_RE
        # 贪婪捕获会把装饰吃进号（"11.5 + + Proof" → num '11.5+1' depth3、
        # "29.8 ++ Proof" → num '29.8+2'）。捕获串一旦含 '+'，其"分量"必是
        # 装饰符而非数字（真数字分量绝不以 '+' 起头）→ 截回 '+' 前重验。
        _pl = num_str.find('+')
        if _pl > 0:
            num_str = num_str[:_pl].rstrip(' .-–·/．－〜_~')
        comps = [x for x in _SEC_SEP_RE.split(num_str) if x]
        if len(comps) < 2 or len(comps) > max_depth:
            return None
        if ch is not None and comps[0].isdigit() and int(comps[0]) != ch:
            return None
        depth = len(comps)
        if depths is not None and depth not in depths:
            return None
        # 🔴 三级条/练习头否决（Rising Sea 实测 57 处）：印刷体例「编号紧跟
        # 题头」的书，`C.S.` 后若直接粘连大写字母（'10.1.E.EXERCISE …' /
        # '4.3.F IMPORTANT …'）——`.`+大写+`.` 是三级字母条头（练习）形态，
        # 真节标题从不以「单字母+句点」起头。旧逻辑 _SEC_HEAD_RE 只吃数字
        # '10.1'，余下 'E.EXERCISE (…' 被当成节标题 → 伪 SEC 行 + 错误重置
        # 习题闩锁，真练习头整条丢失（10.1.E/F 在 p283/284 实测）。
        _r0 = ln[m_end:]
        if _r0.startswith('.') and re.match(r'^\.[A-Z]\.', _r0):
            return None
        rest = _r0.lstrip()
        # Tolerate an optional dot right after the number ("1-2. Parametrized
        # Curves", do Carmo) — a real header may print `C.S. Title`; strip the
        # punctuation run before the alnum check below.
        rest = rest.lstrip('.．。').lstrip()
        # 前导装饰符（Rising Sea 2026-09-24 实测）：星标节的印刷 ⋆/⋆⋆ 被 OCR
        # 成 '+' 或 'xx'（"12.7 + Valuative criteria…"、"11.5 xx Proof of
        # Krull…"）粘在编号与标题之间 → rest[0] 非字母数字，整节被通用检测器漏发
        # （§12.7/12.8/12.9/11.5/29.8 全部如此，靠 D 层回填也只是空壳节）。剥掉
        # 装饰串后再验题（真节标题从不以 ⋆+*×x 起头，SEC_3 模式分支早已同款容错
        # `[+*x×⋆☆]?`；剥后若以小写起头仍被下方散文守卫拒）。
        rest = re.sub(r'^[⋆★☆*+x×\u2726\s]+', '', rest)
        # 🔴 括号起头的真节标题（Rising Sea §18.1 实测）：印刷标题
        # "18.1 (Desired) properties of cohomology" 以 '(' 起头——只要括号内
        # 首个字母字符是**大写或 CJK**（Title-Case 名词短语）即放行；
        # "(the proof…)" 型小写散文仍拒。
        _ok_head = bool(rest) and (rest[0].isalnum()
                                   or rest[0] in _SEC_TITLE_SYMBOLS)
        if not _ok_head and rest and rest[0] in '([':
            _fa = next((c for c in rest if c.isalnum()), '')
            _ok_head = bool(_fa) and (_fa.isupper() or '一' <= _fa <= '鿿')
        if not _ok_head:
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
            # 🔴 全大写缩写豁免（Rosen 8e 实测 2026-09-25）：真节标题就是
            # "9.2.5 SQL"——3 字母缩写整词大写，与 'A'/'B' 型 OCR 图示残粒
            # （"5-6.A"）形态不同（残粒恒为 1–2 字母）。
            if not re.fullmatch(r'[A-Z]{3}[.,;:]?', _rest_stripped):
                return None  # too short to be a title ("A"/"B" junk from OCR'd
                # section-dependency diagrams like "5-6.A") — real titles have words
        if not re.search(r'[A-Za-z一-鿿∈∗\*]', title):
            return None
        # 🔴 纯节号串否决（do Carmo ch5 实测 2026-09-26）：章首目录/图示依赖
        # 行把一串裸节号印成「标题」（"5-2 5-3 5-4 5-5 5-6,A5-6,B 5-7 …"），
        # OCR 合并成一行后命中检测 → §5-2 被锚到目录行、真条头被首现去重压掉。
        # 判据：首词本身就是节号形态且全行 ≥3 个这样的裸节号 token——真节标题
        # 从不以「自身编号 + 另一编号」开头（跨节引用句 "Secs. 8.3 and 8.4"
        # 同理被拦，且其 token 无分隔符粘连形态亦不满足真标题特征）。
        _num_tok = re.findall(r'\b\d{1,2}[.\-–]\d{1,3}[.,]?[A-Za-z]?\b',
                              _rest_stripped)
        if (len(_num_tok) >= 3
                and re.match(r'^\d{1,2}[.\-–]\d{1,3}', _rest_stripped)):
            return None
        # 序位豁免（Etingof《Introduction to representation theory》实测
        # 2026-09-27）：该书节题**本身就是成句散文**——"1.1 What is
        # representation theory?" 与 "3.6 Unitary representations. Another
        # proof of Maschke's theorem for complex representations" 被下方的
        # 「小写连词动词闸」与「句中句界守卫」整节否决，契约与骨架双双漏节
        # （§1.1 / §3.6 整节消失）。豁免判据不看书名、不看词表，只看**序位
        # 接续**：该行编号恰为「本章上一个节号 +1」（章首节即 `ch.1`）。真节头
        # 必然逐个接续印刷，而散文粘连行恰好命中「下一个节号」的概率极低；
        # 且仍受「首词小写散文」「句首虚词」「Proof 冠头」三道守卫约束。
        # 调用方不传 successor_num 时恒 False，其余书零影响。
        _succ = (successor_num is not None and num_str == successor_num)
        # 「序位 + 目录白名单」双确认（Serre 实测 2026-09-27）：命中号既是本章
        # 印刷上应接续的下一节、又在 agent 依 TOC 写出的真节号册内 → 下方三条
        # 历史无条件守卫（句读尾 / Proof 冠头 / 小写首词）改为有条件放行。
        # 双条件缺一不可：白名单单用会被「同号练习/散文行」骗过，序位单用则
        # 对 OCR 掉点的真节题（"16. 1 …"）无能为力；白名单缺失（绝大多数书）
        # 时 `_wl_ok` 恒 False，全路径零回归。
        _wl_ok = bool(section_whitelist) and num_str in section_whitelist
        _waive = _succ and _wl_ok
        # 句读尾守卫（Casella & Berger 实测）：真节标题从不以逗号/分号/冒号收尾；
        # 以句读收尾的「编号+短词」行是散文碎片（OCR 掉括号的公式引用行
        # "1.5.3. First,"——原书 "(1.5.3). First, ..."）不是节头。句号收尾
        # 不拒：部分书真节头带句点（do Carmo 同款守卫亦只堵逗号类）。
        # 🔴 只拦短碎片（Rising Sea §5.5 实测）：真节标题可以是长名词短语且
        # 合法地以冒号收尾——"5.5 The crucial points of a scheme that control
        # everything:"（印刷原样）；散文残粒恒为短行，长度 >= 40 放行。
        # 🔴 分号尾 Title-Case 多词豁免（do Carmo《Differential Geometry of
        # Curves and Surfaces》实测 2026-09-26）：本书节题跨行印刷、首行以
        # 分号收尾——"2-2. Regular Surfaces;"（续行 "and Differentiable
        # Structures"），6 个真节头（2-2/2-3/2-4/4-7/5-6/5-10）被旧守卫整批
        # 否决 → 契约漏节、条目跨节错挂。判据保守：仅分号、>=2 词、每词首
        # 字符非小写才豁免；散文粘连行（含小写虚词/单短词）不受豁免影响。
        _semi_tc = False
        if _rest_stripped[-1:] == ';':
            _sw = _rest_stripped[:-1].split()
            _stop = {"of", "and", "the", "or", "a", "an", "in", "on", "to",
                     "for", "with", "by", "at", "as", "from", "per", "via",
                     "vs", "etc", "nor", "but", "ets"}
            _semi_tc = (len(_sw) >= 2
                        and all((not w[0].isalpha()) or w[0].isupper()
                                or w.lower().strip(".,:;()-") in _stop
                                for w in _sw))
        if (_rest_stripped[-1:] in (',', ';', ':', '，', '；', '：')
                and len(_rest_stripped) < 40 and not _semi_tc and not _waive):
            return None
        # 句中句界守卫：标题内部出现「句号+空格+大写/汉字」= 多句散文
        # （"8.3.21 The UIT built up … LRT. This"），真节标题是单个名词短语。
        # 🔴 收紧为「散文标记才拦」（Kreyszig 2e 实测 2026-09-26）：本书节题
        # 体例是「两个名词短语用句号并置」——"1.5 Examples. Completeness
        # Proofs" / "2.2 Normed Space. Banach Space" / "11.2 Momentum
        # Operator. Heisenberg Uncertainty Principle"，旧一刀切把 5 个真节头
        # （1.5/2.2/2.10/3.1/11.2）整批否决、章节骨架漏节。现只在句界形态
        # 叠加散文证据（小写虚词连跑 ≥3 词、或超长 >56）时拒；真节头
        # （Title-Case 名词短语、长度 ≤56）放行。负例 "The UIT built up the
        # kernel of LRT. This" 含 3 连小写词仍拦。
        if re.search(r'[.;；]\s+[A-Z一-鿿]', _rest_stripped):
            _lc_run = re.search(
                r"\b[a-z][A-Za-z'\-]*(?:\s+[a-z][A-Za-z'\-]*){2,}\b",
                _rest_stripped)
            if (_lc_run or len(_rest_stripped) > 56) and not _succ:
                return None
        # 🔴 小写连词动词闸（Kreyszig 章首导语实测 2026-09-26）：p17
        # "1.6. Another concept of theoretical and practical interest **is**
        # separability"、p420 "8.4. The Riesz-Schauder theory **is** based on
        # Secs. 8.3 and 8.4"——章首编号导语与节号同形，OCR 断块后整行命中
        # universal 检测 → 幻影节头抢先把 §N.M 锚到导语页（节序 BLOCKING +
        # 真节头被首现去重压掉）。Title-Case 真节标题从不含**小写**连词动词
        # （系词/完成助动词），散文句恒有；大小写敏感匹配，"What Is…" 类
        # 大写标题不受影响。
        # 🔴 同「序位豁免」（见上）：本书首节节题就是一个问句
        # "1.1 What is representation theory?"——恰为章首应出现的 `ch.1`，
        # 系词是标题自身的词而非散文证据。
        if (re.search(r'\b(?:is|are|was|were|been|being)\b', _rest_stripped)
                and not _succ):
            return None
        # CJK 粘连句读守卫：真中文节标题是**无句读**的短名词短语（"无穷小与无穷大"
        # /"函数的上极限和下极限"）；若标题内部出现「句点/逗号/分号（半角或全角）
        # + 汉字」（OCR 把跨行引用行首的编号+散文残片粘成一行），判为散文碎片。
        # 常庚哲《数学分析教程》实测：引理 2.12.3 的正文跨行「2.12.3的要求都满足.
        # 因此…」被当作三级小节伪节头 → 契约凭空多出 §2.12.3。枚举顿号 `、` 不在
        # 本类，真节标题（含"、"者）不受影响。
        if not allow_cjk_comma and re.search(r'[。，,；;]\s*[一-鿿]',
                                             _rest_stripped):
            return None
        # 句首虚词守卫（见 _SEC_TITLE_SENTENCE_STARTS 注释）。
        if _SEC_TITLE_SENTENCE_STARTS.match(_rest_stripped):
            return None
        # Proof 冠头判据（见 _proof_title_is_prose 注释）：只拦无大写实词的
        # 散文证明行，Title-Case 的 "Proof by Contraposition" / "Proof Strategies"
        # 真节标题放行。序位+白名单双确认（"17.3 Proof of theorem 33" 恰是
        # Serre §17.3/17.4/17.6 节题）时放行。
        if _proof_title_is_prose(_rest_stripped) and not _waive:
            return None
        # A genuine section title is Title-Case / Han / starts with a digit — reject
        # prose that begins with a lowercase word (e.g. "20.6 and it is stated...",
        # "14-1-0359 and W911NF..." grant numbers glued to text).  Only a leading
        # lowercase ASCII letter is rejected; Han / digit / uppercase are kept.
        first = next((c for c in rest if c.isalnum()), None)
        if first is not None and 'a' <= first <= 'z':
            # 容忍「小写符号变量 + 连字 + 大写词」型标题：Brin & Stuck §5.3
            # "∈-Orbits" 被 OCR 读成 'e-Orbits'——首字符小写但非散文。
            _accept_lc = bool(re.match(r"[a-z][-–—][A-Z]", rest))
            if not _accept_lc and _waive:
                # 序位+白名单双确认：Serre §10.1 节题 "p-regular elements;
                # p-elementary subgroups" 以小写技术术语起头且全行无大写字母，
                # 旧「技术术语首词豁免」要求其后必有 Title-Case 延续词 → 整节
                # 漏发。命中目录真值号且恰为接续节时放行。
                _accept_lc = True
            if not _accept_lc:
                # 🔴 技术术语首词豁免（Rosen 8e 实测）：真节标题首词可以是
                # 小写技术名词（"9.2 n-ary Relations and Their Applications"、
                # "4.3.8 gcds as Linear Combinations"），判据 = 首词**不是**
                # 常用虚词/代词 且 其后存在 Title-Case 大写延续词（名词短语
                # 形态）。散文粘连行（"20.6 and it is stated…"、"14-1-0359 and
                # W911NF…"）首词恒为虚词 → 仍拒；"valuative criteria for…"型
                # 全小写延续无大写词 → 仍拒（Rising Sea 旧负例不变）。
                _w0 = re.match(r"[a-z][a-zA-Z'\-]*", rest.strip())
                if (_w0 and _w0.group(0).lower() not in _SEC_TITLE_FUNC_WORDS
                        and re.search(r'\b[A-Z][a-zA-Z]',
                                      rest.strip()[_w0.end():])):
                    _accept_lc = True
            if not _accept_lc:
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
    # Fallback: OCR 把节号内部打成「16. 1 Title」（数字与小数点间插空格，
    # Serre §16.1 实测 2026-09-27：`16. 1 Properties of the cde triangle`）。
    # _SEC_HEAD_RE / m2 都要求分隔符后紧跟数字 → 整节漏发。该形态极窄（真
    # 书节号印刷无空格），故**双闸**收窄：解析出的号既须 = 序位接续号、又须在
    # 目录白名单内才走全量校验；白名单缺失的书永不进入（零回归）。
    m3 = re.match(r'^\s*(\d{1,2})\s*[.\-–·/．]\s*(\d{1,3})\b', ln)
    if m3:
        _num = '%s.%s' % (m3.group(1), m3.group(2))
        if (successor_num is not None and _num == successor_num
                and section_whitelist and _num in section_whitelist):
            v = _validate(_num, m3.end())
            if v:
                return v
    return None


# Map an integer `ordinal` (config) to scan_skeleton's parsing mode.
# Returns one of 'three-level' (default western 3-level), 'two-level'
# (western/EN/GM 2-level), or 'cn' (Chinese 3-level).
def _mode_for_ordinal(ordinal, language=None):
    o = int(ordinal)
    depth = ordinal_depth(resolve_ordinal_code(o))
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


_CHAP_TITLE_CACHE = {}


def _norm_title_txt(s: str) -> str:
    """Normalise a title for equality checks: keep alnum only, lowercase."""
    return re.sub(r'[^a-z0-9\u4e00-\u9fff]', '', str(s or '').lower())


def _chap_title_norm(extract_dir: str, ch) -> str:
    """Normalised chapter title from chapter_map.json (running-head guard)."""
    key = (extract_dir, ch)
    if key not in _CHAP_TITLE_CACHE:
        title = None
        try:
            fp = os.path.join(extract_dir, 'chapter_map.json')
            with open(fp, encoding='utf-8-sig') as fh:
                cm = json.load(fh)
            for e in cm.get('chapters', []):
                if int(e.get('ch', -1)) == int(ch):
                    title = e.get('name_en') or e.get('name')
                    break
        except Exception:
            title = None
        _CHAP_TITLE_CACHE[key] = _norm_title_txt(title)
    return _CHAP_TITLE_CACHE[key]


# 🔴 数字/标题分块粘连回收（Rosen 8e 实测 2026-09-25）：OCR 常把节头的编号与
# 标题拆成左右/上下相邻两个块（"9.6.1" + "Introduction"、"8.4.4" + "Using
# Generating Functions to Solve…"），逐行检测对「裸编号行」因无标题恒拒 →
# 15+ 个真节头（含 §7.4.7/§10.3.5/§11.3.3/§12.3.4/§13.5.3 与多个节父号）从
# 骨架消失。回收判据极窄：本行**恰为纯编号**（\d+\.\d+…），下一文本块首行为
# 短标题形态（字母/CJK 起头、无数字、无数学/括号字符、≤80 字符），且两块
# 几何相邻（同页同行右侧，或下方 ≤250pt）；合并串仍交 `_section_header_info`
# 全量校验（章号过滤 + 深度声明 + 散文守卫），表行（"3.88 Adams"/"0.0817 N"）
# 由首分量≠章号或标题形态约束恒拒。
_BARE_SEC_NUM_RE = re.compile(r'^\d+\.\d+(?:\.\d+)*$')
_MERGE_TITLE_BAD_CHARS = set('0123456789=+*/()<>[]{}$\\_,;:.')


def _poly_tl(blk):
    try:
        p = blk.get('poly') or []
        return float(p[0]), float(p[1])
    except Exception:
        return None


def _merge_bare_num_head(ln, bi, blocks):
    """Return `'<num> <title>'` if line `ln` (bare section number, block `bi`)
    is horizontally/vertically adjacent to a short title-looking next block."""
    if not _BARE_SEC_NUM_RE.match(ln) or bi + 1 >= len(blocks):
        return None
    nxt_raw = (blocks[bi + 1].get('text') or '').split('\n')[0].strip()
    nxt = nxt_raw.rstrip('$').strip()
    if not (2 <= len(nxt) <= 80):
        return None
    c0 = nxt[0]
    # 字母（大小写）/ CJK 起头才尝试（'n-ary' 型小写技术术语交由校验器裁决）
    if not (('a' <= c0 <= 'z') or ('A' <= c0 <= 'Z') or '一' <= c0 <= '鿿'):
        return None
    if any(ch in _MERGE_TITLE_BAD_CHARS for ch in nxt):
        return None
    a, b = _poly_tl(blocks[bi]), _poly_tl(blocks[bi + 1])
    if a is None or b is None:
        return None
    dy = b[1] - a[1]
    if dy < -40 or dy > 250:
        return None
    if dy <= 40 and b[0] <= a[0]:
        return None  # 同行形态必须右邻；上下形态允许左缘微漂
    return f"{ln} {nxt}"


def scan(extract_dir, ch, start, end, mode, section_depths=None, chapter_first=None,
         exercise_headings=None, plain_sec_heads=False, sections_global=None,
         local_num_sec=False, chapter_local_numbering=False, section_whitelist=None,
         language='cn'):
    rows = []
    # 目录真值小节号（agent 依 TOC 写出的 `_section_whitelist.json` 本章清单，
    # 归一为 "N.M" 字符串集合）。仅用于「闩锁内真节头放行」判据（见下方
    # `_wl_nums` 使用处）；文件缺失 / 本章未登记 → None，走原启发式，零回归。
    _wl_nums = ({str(x) for x in section_whitelist} if section_whitelist else None)
    # Exercise-region state: once "EXERCISES" / "EXERCISES FOR CHAPTER N" is seen,
    # all subsequent bare `C.S.N` numbers (three-level mode) are exercises, and in
    # two-level mode we also suppress SEC_2 / ITEM_2 so single-number "N. Problem"
    # exercise lines (do Carmo) are NOT mistaken for sections/items.
    in_exercise = False
    # 习题区计数器（Casella & Berger 体例守卫）：闩锁内已发出的习题最大号。
    # 习题章内连续编号（C.S 2 段），真节号（同 C.S 空间）必然已被习题序列
    # 越过（C&B 每章习题数 19–55 ≥ 节数 5–8）→ 闩锁内「短标题 + 号 < 计数器」
    # 才可能是闩锁后的真节（"1.8 Miscellanea"）；号 ≥ 计数器的短标题行
    # （"2.9 If the random variable X has pdf" / "2.40 Prove"）是习题。
    last_exer_num = 0
    # 锥点时的当前节号（'universal 节检测同号守卫'用）：由于 scan()
    # 逐页扫描时不知道当前节，用最近一次发出的 SEC 行号维护。
    cur_exer_sec = None
    # 本章已发出的全部 SEC 节号（闩锁内「重复节号 = 习题分组头」判据用，见
    # universal 节检测处的 `_sec_emitted` 守卫）。
    _sec_emitted = set()
    # 裸单号习题行在 `rows` 中的下标（体例仲裁用，见 return 前的 `bare_exer_idx`）。
    bare_exer_idx = set()
    # 本章最近发出的节号（「序位豁免」的锚点，见 _section_header_info）。
    last_sec_num = None
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
    # 🔴 CHAPTER-LOCAL single-segment sections (Hilton & Stammbach "1. Modules"
    # reset every chapter; section_types [1, 1] too) are INDISTINGUISHABLE from
    # book-global ones by depth alone — both are a single number at the level
    # under the chapter.  The pure-depth heuristic below therefore wrongly flags
    # them global and (via `not global_sec`) suppresses the SEC_2 branch that is
    # the ONLY detector catching bare "N. Title" heads → 0 sections.  The
    # authoritative signal is the config flag `sections_global` (default False,
    # set True only for Humphreys/Arnold-type global books), already used by the
    # D-layer (`section_continuity`) and structure builder.  When the caller
    # passes it explicitly, honor it; fall back to the depth heuristic only for
    # legacy callers that do not (zero regression for global books, which set the
    # flag).
    if sections_global is not None:
        global_sec = bool(sections_global)
    else:
        global_sec = bool(section_depths) and any(
            isinstance(d, int) and d == 1 for d in section_depths[1:])
    if chapter_local_numbering:
        # 🔴 章内三层体例（丘维声）强制关闭全局 § 家族（2026-09-26 实测）：
        # 本模式的 §N 由下方专用分支检测（无 y 下限 + cur+1 闩锁），而全局
        # 家族若开启会 ① 用带 y≥170 守卫的无闩锁 GLUE 抢先吃掉 § 行并伪造
        # 节号（ch1 伪 SEC 6 "个数）…"）；② 其点号 SEC 尾过滤（见 scan 末尾
        # `if global_sec:` 区）删掉**全部真小节**（22/22 被吞）。深度启发式
        # 对 [1,1,2]（含单分量 role 1）必然误判 global，故以本旗标兜底。
        global_sec = False
    # Current global §N while scanning (for SUB letter-head parentship).
    cur_global_sec = None
    # Numeric local sub-block latch (only used when local_num_sec): track which
    # § the current 1..N restart run belongs to and the last accepted number so
    # a candidate is only promoted when it is exactly prev+1 (seeded at 1).  The
    # run RESETS automatically when cur_global_sec changes (new § → parent≠
    # cur_local_parent → restart expecting 1).
    cur_local_parent = None
    cur_local_sub = None
    # Exact SEC keys emitted via the local_num_sec path.  The global_sec
    # dotted-SEC post-filter below drops "C.S" SEC rows as prose false
    # positives, but legitimate numeric-local subsections are also "C.S";
    # record them here so the filter can exempt only the ones we intentionally
    # emitted (key-set membership, not a loose pattern → no FP leakage).
    local_sec_keys = set()
    # 🔴 Only enable the universal (depth-agnostic) detector when there is at
    # least one depth>=2 section to find.  A book whose sections are single
    # numbers (`## §N`, e.g. do Carmo) has `depths_set == set()` (empty) — the
    # universal detector REJECTS single-number headings (`len(comps) < 2`), so
    # leaving it on would silently detect ZERO sections and force every item to
    # page-proximity.  `bool(depths_set)` falls back to the mode's SEC regex
    # (SEC_2 for two-level) which correctly catches single-number sections.
    use_universal_sec = bool(depths_set)
    # 页眉带线 (页, y)：扫描时按 `is_running_head` 记录，供行后
    # `demote_head_band_rows` 把抢当窗口左界的页眉复本行降级。
    _head_band = set()
    for p in range(start, end + 1):
        fp = os.path.join(extract_dir, 'page_%03d.json' % p)
        if not os.path.exists(fp):
            continue
        with open(fp, encoding='utf-8') as fh:
            d = PageJson.load(os.path.join(extract_dir, 'page_%03d.json' % p)).data
        _blocks = d.get('text', []) or []
        # 本页文本块的 x 极值（页眉带判据的左边界/页宽，见 _HEAD_BAND_Y 注释）。
        _m_left, _m_span = page_x_extent(_blocks)
        _m_top = page_top_y(_blocks)
        for _bi, it in enumerate(_blocks):
            poly = it.get('poly') or []
            try:
                ln_w = (float(poly[2]) - float(poly[0])) if len(poly) >= 3 else None
            except Exception:
                ln_w = None
            ln_x, ln_y = block_xy(poly)
            # 页眉带复本（页首 + 右对齐）：不得激活习题区闩锁，见 _HEAD_BAND_Y。
            _run_head = is_running_head(ln_x, ln_y, _m_left, _m_span, _m_top)
            if _run_head:
                _head_band.add((p, ln_y))       # 供 demote_head_band_rows 降级窗口左界
            for _raw in (it.get('text') or '').split('\n'):
                ln = _raw.rstrip('$').strip()
                if ln:
                    ln = EXER_OCR_ONE.sub(r'\g<1>1\g<2>', ln)
                else:
                    continue
            # Exercise-region detection (case-insensitive, space-optional so it
            # survives OCR like `EXERCISESFORCHAPTER3`).  Once seen, the chapter
            # is in its exercise block through to the next genuine section
            # header (multi-section books like do Carmo run an EXERCISES block
            # at the END OF EVERY SECTION, so the latch must reset on SEC).
            if ex_head_re is not None and not in_exercise and ex_head_re.match(ln) \
                    and not _run_head:
                # Ross 体例章末习题块头（"Problems" 等）：STICKY 闩锁激活，
                # 其后直到章末不再有正文/节。
                in_exercise = True
                continue
            if (EXER_HEADING.match(ln) and not ln.strip().rstrip('. ．·').islower()
                    and not _run_head):
                # 🔴 全小写散文碎屑不闩（Vakil《Rising Sea》ch10 p293 实测）：OCR 把
                # 「…prove this as an / exercise.」断成独立一行 "exercise."，IGNORECASE
                # 锚定正则整行命中 → 错误激活习题区闩锁，其后真条目（10.3.1 Definition
                # 等）被 EXER_3N 改判成数字习题、字母习题头 10.3.A 被压成裸节号 10.3。
                # 真习题块标题排版为大写族（EXERCISES / Exercises），全小写只可能是
                # 句尾散文词 → 拒绝闩锁与补发 SEC。
                # 🔴 无 `not in_exercise` 前置（Casella & Berger 实测）：本书页眉
                # 印「Section 1.7 ／ EXERCISES」两行——页首的裸 "EXERCISES" 已把
                # 闩锁激活，随后页中的真节头 "1.7 Exercises" 若因 `not in_exercise`
                # 被跳过，就会落进 universal 节检测：短标题通过 sec_like → 发 SEC
                # 并【错误重置闩锁】，同页其后习题全部泄漏成节。EXER_HEADING 是
                # 全行锚定的习题区标题形态，重复命中只会重设闩锁 + 补发节头 SEC，
                # 无副作用 → 无条件重闩。
                # 🔴 但 `_run_head` 例外（Apostol 实测）：页首**右对齐**的页眉复本
                # 不是「进入习题区」的信号（同页其后还有正文条目），见 _HEAD_BAND_Y。
                in_exercise = True
                # 记录锥点时当前节：同号节的 running-header 复本
                # （如 Leinster 2014 p48 '1.3Naturaltransformations'）不应解锁
                # 习题区（见下方 universal 检测处的同号守卫）。
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
                # chapter_local_numbering：两分量均章内（`4.2` 首分量≠章号），
                # 关闭 `== ch` 守卫；并放行标题内全角逗号（见函数 docstring）。
                # 🔴 该模式的「序位豁免」由**闩锁状态**给出（旧版直接设 None ⇒
                #   `_section_header_info` 的「小写连词动词闸」在 chapter_local_
                #   numbering 书上**没有任何豁免通道**）。Shafarevich《Basic
                #   Algebraic Geometry 1》ch1 实测：印面节头 "5.2 The Image of a
                #   Projective Variety is Closed" 含小写系词 `is` → 整节从骨架与
                #   内容契约双双消失，而节号恰是闩锁意义上的「下一个子节」
                #   （A==当前节 5、B==上个子节 1 +1），正是真节头最强的位置证据。
                #   豁免强度与其余书同源：只放行**恰好接续**的号，且仍受
                #   「首词小写散文」「句首虚词」「Proof 冠头」三道守卫约束。
                if chapter_local_numbering:
                    _succn = ('%d.%d' % (cur_global_sec, (cur_local_sub or 0) + 1)
                              if cur_global_sec else None)
                else:
                    _succn = _expected_next_sec(last_sec_num, ch)
                sec = _section_header_info(
                    ln, ch=None if chapter_local_numbering else ch,
                    depths=depths_set,
                    allow_cjk_comma=chapter_local_numbering,
                    successor_num=_succn,
                    section_whitelist=_wl_nums)
                if sec is None:
                    # 数字/标题分块粘连回收（见 _merge_bare_num_head 注释）：
                    # 裸编号行 + 紧邻短标题块 → 合并串重新走全量校验。
                    _mg = _merge_bare_num_head(ln, _bi, _blocks)
                    if _mg is not None:
                        sec = _section_header_info(
                            _mg, ch=None if chapter_local_numbering else ch,
                            depths=depths_set,
                            allow_cjk_comma=chapter_local_numbering,
                            successor_num=_succn,
                            section_whitelist=_wl_nums)
                if sec is not None and chapter_local_numbering:
                    # 「A == 当前节 + B 单调」闩锁：杀章内交叉引用/公式行
                    # （"6.1所示" p216、"2.1的第4题可知" p346——彼时当前节是
                    # 1/6，A 不等即拒）与后续重号；B 上限杀 "3.17所示"。
                    # B 允许跳号（OCR 偶发吞行不至于闷死整节后续小节）。
                    # 标题不得再含一个 N.M 数字（ch6 实测散文行
                    # "1.7和命题1.4，得" A==当前节通过——真小节标题永不含
                    # 点分数字，交叉引用形态一票否决）。
                    _cln = re.match(r'^(\d{1,2})\.(\d{1,2})$', sec[0])
                    _ok = False
                    if _cln:
                        _a, _b = int(_cln.group(1)), int(_cln.group(2))
                        _ok = (_a <= 12 and _b <= 8
                               and _a == cur_global_sec
                               and _b > (cur_local_sub or 0)
                               and not re.search(r'\d+\.\d+', sec[2]))
                        if _ok:
                            cur_local_parent = _a
                            cur_local_sub = _b
                    if not _ok:
                        sec = None
                if sec is not None:
                    num_str, _depth, title = sec
                    # 🔴 闩锁内「本章已发过的节号」不是新节（Strogatz《Nonlinear
                    # Dynamics and Chaos》3e 实测）：章末习题区按节分组，印
                    # 「2.1 A Geometric Way of Thinking」等小标题，与正文真节头
                    # **逐字同形**，旧逻辑在此发 SEC 并解除闩锁 → 其后三段题号
                    # 习题（2.1.1 / 2.2.1 …）不再走 EXER_3N，全书习题 0 收录。
                    # 真节号一章内不可能印刷两次，故闩锁内的重复节号必是习题分组
                    # 头（或摘要/页眉复本）：不发节、不解锁。
                    if in_exercise and num_str in _sec_emitted:
                        # 🔴 同号「习题行」不得连行丢弃（Serre 实测 2026-09-27）：
                        # 本书习题与节共用号空间（习题 10.1–10.6 ↔ §10.1–§10.5），
                        # 真节 10.3 发出后，习题行 "10.3. Extend lemma 6 to class
                        # functions…" 落在本守卫 → 整行丢弃 ⇒ 契约缺习题 10.3。
                        # 判据：行形态是**成句散文题干**（_sec_like_title False，
                        # >40 字符或句读尾）才按题号收作 EXER；Strogatz 型习题
                        # 分组头 / 页眉复本是短 Title-Case 标题 → 照旧整行跳过。
                        _m3 = STICKY_EXER_RE.match(ln)
                        if (_m3 and int(_m3.group(1)) == ch
                                and not _sec_like_title(title)):
                            try:
                                _en3 = int(_m3.group(2))
                            except ValueError:
                                _en3 = 0
                            last_exer_num = max(last_exer_num, _en3)
                            rows.append((p, 'EXER', '%s.%s' % _m3.group(1, 2),
                                         ln[_m3.end():].strip()[:90], None))
                        continue
                    if in_exercise and num_str == cur_exer_sec:
                        # 同号节 running-header 复本：不发 SEC 行、不解锁
                        # 习题区（真正的新节号必不同于锥点时的节号）。
                        continue
                    if in_exercise:
                        # 🔴 闩锁内解锁判据（双信号，Casella & Berger 实测）：
                        # (1) 标题须像真节标题（短、无句读尾）——习题行是成句
                        #     散文（普遍 > 40 字符或句点收尾）；
                        # (2) 节号须 < 习题计数器——习题章内连续编号必然越过
                        #     真节号空间（ch1 习题到 1.55 才遇 §1.8；ch2 习题
                        #     2.33 后才遇 §2.6）。号 ≥ 计数器的短标题行仍是
                        #     习题（"2.9 If the random variable X has pdf" /
                        #     "2.40 Prove"——跟在 EXER 2.8 / 2.39 之后）。
                        #     计数器为 0（闩锁以来未见习题行，OCR 全吞）时退回
                        #     旧行为放行解锁，防真节被永久闷死。
                        _try_exer = False
                        # 🔴 目录白名单 + 序位接续的真节头（Serre《Linear
                        # Representations of Finite Groups》实测 2026-09-27）：
                        # 本书习题与小节共用同一号空间（习题 2.1–2.10 与
                        # §2.1–§2.7 同形，习题计数常**低于**其后真节号——§2.4
                        # 节头之前刚印完习题 2.5/2.6）→ 下方「尾号 ≥ 习题计数
                        # 器」判据把真节头判成习题、`continue` 吞掉，整节从
                        # 骨架消失（§2.4/§2.7/§5.4… 全书十余节）。
                        # 三条件缺一不可：① agent 依目录写出的
                        # `_section_whitelist.json` 含该号（文件缺失 = 零回归）；
                        # ② 正是上一节接续的下一节号（习题号永不可能撞上，
                        # 因为它落后于当前节位）；③ 标题非句首虚词、非句读收尾。
                        if (_wl_nums and num_str in _wl_nums
                                and _succn is not None and num_str == _succn
                                and title
                                and not _SEC_TITLE_SENTENCE_STARTS.match(title)
                                and title[-1] not in '.,;:，；：'):
                            _try_exer = False
                        elif _sec_like_title(title):
                            try:
                                _sec_tail = int(num_str.split('.')[-1])
                            except ValueError:
                                _sec_tail = None
                            if last_exer_num and _sec_tail is not None \
                                    and _sec_tail >= last_exer_num:
                                _try_exer = True
                        else:
                            _try_exer = True
                        if _try_exer:
                            _m2 = STICKY_EXER_RE.match(ln)
                            if _m2 and int(_m2.group(1)) == ch:
                                try:
                                    _en = int(_m2.group(2))
                                except ValueError:
                                    _en = 0
                                last_exer_num = max(last_exer_num, _en)
                                rows.append((p, 'EXER', '%s.%s' % _m2.group(1, 2),
                                             ln[_m2.end():].strip()[:90], None))
                                continue
                            # 非 2 段题号形态：维持旧行为（发 SEC 解锁）防兜底死锁。
                    _cont = heading_continuation(_blocks, _bi, title)
                    if _cont:
                        # 印刷节头跨行（悬挂续行）：标题补全，否则契约节名丢尾巴，
                        # 且页眉里的完整标题被 ②c 判成丢失正文（见 _SEC_CONT_* 注释）。
                        title = (title + " " + _cont).strip()
                    rows.append((p, 'SEC', num_str, title, ln_y))
                    _sec_emitted.add(num_str)
                    last_sec_num = num_str  # 序位豁免的接续锚点
                    cur_exer_sec = num_str
                    in_exercise = False  # new section ends the exercise region
                    last_exer_num = 0
                    continue
                elif in_exercise:
                    # 🔴 闩锁内被节校验整行拒绝的 2 段题号行（Casella & Berger
                    # 实测 "1.35Prove that ... P(B) > 0,"——题干以逗号收尾被
                    # _validate 拒绝 + 题号粘连进不了上方 sec-not-None 回落）：
                    # 旧逻辑整行丢失 → 习题缺号。按 2 段题号兜回 EXER。
                    _m2 = STICKY_EXER_RE.match(ln)
                    if _m2 and int(_m2.group(1)) == ch:
                        try:
                            _en = int(_m2.group(2))
                        except ValueError:
                            _en = 0
                        last_exer_num = max(last_exer_num, _en)
                        rows.append((p, 'EXER', '%s.%s' % _m2.group(1, 2),
                                     ln[_m2.end():].strip()[:90], None))
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
            # --- 章末裸单号习题（Apostol《Introduction to Analytic Number Theory》
            # 体例实测 2026-09-28）：块头 "Exercises for Chapter N" 之后习题印成裸号
            # "4. Let S be any infinite subset …"，STICKY_EXER_RE（要求 C.S 两段）与
            # EXER_3N（三段）都收不到 → 整章习题 0 收录、契约无练习节点。
            # 三重判据：① 习题区闩锁已开（只有真习题块标题能开）；② 行首 `N.`/`N)`
            # + 空白 + **大写字母**起头（公式残行 "1 = A(k) +"、"(20)" 一律不匹配）；
            # ③ N 恰等于计数器 +1（章内习题严格连号，断号不收 = 宁缺毋滥，
            # 也绝不误收 C.S 体例书的题号——那点号后紧跟数字）。
            if in_exercise:
                mb = STICKY_EXER_BARE.match(ln)
                if mb and int(mb.group(1)) == last_exer_num + 1:
                    last_exer_num = int(mb.group(1))
                    bare_exer_idx.add(len(rows))
                    rows.append((p, 'EXER', str(last_exer_num),
                                 ln[mb.end():].strip()[:90], None))
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
                # SPACED-prefix global § heads (Arnold ODE 2e: '§ N. Title' with a
                # space between § and the number, which SEC_GLOBAL cannot match —
                # see SEC_GLOBAL_SPACED comment).  Guarded to English (title starts
                # [A-Z]) + forced §-family prefix, so Chinese global_sec books
                # (Arnold《数学方法》) never enter here -> zero regression.  Strip a
                # trailing OCR page number glued/space-separated to the title.
                m = SEC_GLOBAL_SPACED.match(ln)
                if m and int(m.group(2)) <= 60:
                    _title = _SEC_SPACED_TRAIL_PAGE.sub('', m.group(3)).strip()
                    rows.append((p, 'SEC', m.group(2), _title, ln_y))
                    in_exercise = False
                    cur_global_sec = int(m.group(2))
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
                # Numeric local sub-block head ("1. Examples of Evolutionary
                # Processes" restarting per §) — the bare-numeric cousin of the
                # letter SUB_GLOBAL below, gated behind local_num_sec (Arnold
                # ODE).  Emitted as a SEC row keyed "<§>.<local>" so build_structure
                # turns it into a REAL level-2 section node (it nests under the
                # single-number § parent via the dotted-depth machinery).  The
                # per-§ +1 continuity latch is the decisive disambiguator.
                if local_num_sec and cur_global_sec is not None:
                    if cur_local_parent != cur_global_sec:
                        cur_local_parent = cur_global_sec
                        cur_local_sub = None
                    _mn = SEC_LOCAL_NUM.match(ln)
                    if (_mn and _local_num_title_ok(_mn.group(2))
                            and int(_mn.group(1)) <= SEC_MAX_NUMBER
                            and int(_mn.group(1)) == (cur_local_sub or 0) + 1):
                        cur_local_sub = int(_mn.group(1))
                        _lkey = f"{cur_global_sec}.{cur_local_sub}"
                        local_sec_keys.add(_lkey)
                        rows.append((p, 'SEC', _lkey,
                                     _mn.group(2).strip(), ln_y))
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
                    # 🔴 第 5 元带块首 y（与 SEC 行同槽位）：字母块的**窗口边界**必须
                    # 精确到页内位置。§32 实测（2026-09-28）：B 块尾条 例2/例3 与
                    # C 块起重 例1 **印在同一页**，页粒度的桶把 C 的 例1 归进 B 之后
                    # （其后继 例2 又落在 D 桶），三条续接判据全落空 → 真条目被当
                    # 回指吞掉。y 让抽取器把桶边界切在块头本身。
                    rows.append((p, 'SUB', parent + m.group(1),
                                 m.group(2).strip(), ln_y))
                    continue
            # --- chapter-local §N heads（丘维声《解析几何》体例）-------------
            # 节号每章重起，OCR 三形态：`81向量…`（§→8）、`S1映射`（§→S）、
            # 裸 `1平面的仿射坐标变换`（§ 丢失）。复用 SEC_GLOBAL_GLUE 形态但
            # **无 y 下限**：节起于新页顶时节头就在页眉带（ch2 §2 p78 y73，
            # y≥170 会整节漏掉并连带闷死其下全部小节）。误报由三道闸拦：
            # ① 号须 == 当前节+1（首现播种须为 1）——页眉页码行（"26第一章…"/
            # "54第二章…"）与公式行（"2x+3y…"）不在序列上；② 标题 ≥2 汉字、
            # 无数学运算符（_glue_title_ok）；③ 标题不含章名（页眉复本形态
            # "…第一章几何空间的线性结构和度量结构…"）。粘连页码剥尾
            # （"…向量的混合积39"）。同号重复行由下游 sec_best 首现去重吸收，
            # 首现必是真节头（节题先于其页眉复本出现在页序中）。
            if chapter_local_numbering:
                m = SEC_GLOBAL_GLUE.match(ln)
                if (m and ln_w is not None and ln_w <= _GLUE_MAX_WIDTH
                        and _glue_title_ok(m.group(2))):
                    _n = int(m.group(1))
                    _t = _SEC_SPACED_TRAIL_PAGE.sub('', m.group(2)).strip()
                    _seed = (cur_global_sec is None and _n == 1)
                    _adv = (cur_global_sec is not None
                            and _n == cur_global_sec + 1)
                    if ((_seed or _adv) and _n <= SEC_MAX_NUMBER and _t
                            and not re.search(r'第[一二三四五六七八九十\d]+章',
                                              _t)
                            and not re.search(r'\d+\.\d+', _t)):
                        rows.append((p, 'SEC', str(_n), _t, ln_y))
                        cur_global_sec = _n
                        cur_local_parent = None
                        cur_local_sub = None
                        continue
                # 英文局部编号通道（Shafarevich 体例，见 _cln_en_title_ok）：
                # 节头印 `N Title`（允许数字后一个句点 + 空格），N 每章从 1
                # 重起；同款「首现=1 + cur+1 序列」闩锁，但**无 y 下限**（本节
                # 头常印在新页页眉位）。GLUE 的 `(\d)([A-Z汉字]…)` 要求数字后
                # 零分隔符，英文带空格形态到不了上面的 CJK 通道。
                _mce = re.match(r'^(\d{1,2})[.]?\s+([A-Z][^\n]{1,%d})$'
                                % _CLN_EN_MAX_LEN, ln)
                if (language == 'en' and _mce and ln_w is not None
                        and ln_w <= _GLUE_MAX_WIDTH
                        and _cln_en_title_ok(
                            _mce.group(2),
                            _chap_title_norm(extract_dir, ch))):
                    _n = int(_mce.group(1))
                    _t = _SEC_SPACED_TRAIL_PAGE.sub('', _mce.group(2)).strip()
                    _seed = (cur_global_sec is None and _n == 1)
                    _adv = (cur_global_sec is not None
                            and _n == cur_global_sec + 1)
                    if (_seed or _adv) and _n <= SEC_MAX_NUMBER:
                        rows.append((p, 'SEC', str(_n), _t, ln_y))
                        cur_global_sec = _n
                        cur_local_parent = None
                        cur_local_sub = None
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
                # 🔴 Running-head guard (Hilton & Stammbach ch2 实测)：本书页眉
                # 交替印「页码 | N. 章题」——罗马章号 "II." 被 OCR 读成 "11."，
                # 恰好命中 SEC_2，伪造成 §11 "Categories and Functors"（节题 ==
                # 章题）。节题与章题同名、编号>1、且位于页眉带（y<300，本书真节头
                # y≥950 或章首页顶——ch4 §5 "Derived Functors" 与章同名但 y=1795，
                # 不得误杀）→ 只可能是页眉，拒绝。
                _rh_ok = (m is None or int(m.group(1)) <= 1
                          or ln_y is None or ln_y >= 300
                          or _norm_title_txt(m.group(2))
                          != _chap_title_norm(extract_dir, ch))
                if (not use_universal_sec and not in_exercise and not plain_sec_heads
                        and not global_sec
                        and m and _sec_ch_ok and _rh_ok
                        and _sec2_title_ok(m.group(2))
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
                    htxt = (m.group(4) or '').strip()
                    # 🔴 幻影条头压制（Rising Sea ch4 p149 / ch8 p233 实测）：跨页
                    # 散文「…Exercises 4.5.K and / 4.5.L. If you prefer that, by all
                    # means do so.)」与句尾回指「…in Exercises 8.2.A and / 8.2.F.」被
                    # OCR 切成独立行后整行命中 EXER_3，凭空多出与真习题同键的幻影
                    # 节点。判据保守：本行不含 EXERCISE 关键词，且题面为空或以 ')' 收
                    # 尾（真条头恒含关键词；全书 1362 条字母条头实测仅这 2 条例外）
                    # → 丢弃。含关键词的同号二现不在此拦（交 dedup / 人工核）。
                    # 🔴 I↔1 混淆闸（Rising Sea §0.0 实测）：字母 I 与条目号 1
                    # 同形，"0.0.I. The importance of exercises." 实为印刷条目
                    # "0.0.1. …"（句中散文词 exercises 不得当成习题关键词）——
                    # I 号头未命中习题题头词形时按条目 "C.S.1" 收回（真条目
                    # 常只以这一种形态出现，落空就整条丢失）。其余字母无混淆。
                    if (m.group(3) == 'I' and htxt
                            and not is_exercise_head_text(htxt)):
                        rows.append((p, 'ITEM', '%s.%s.1' % m.group(1, 2), htxt))
                        continue
                    elif (has_exercise_word(htxt)
                            or not (htxt == '' or htxt.endswith(')'))):
                        rows.append((p, 'EXER', '%s.%s.%s' % m.group(1, 2, 3), htxt))
                        continue
                mG = EXER_3_GARBLE.match(ln)
                if mG and int(mG.group(1)) == ch and is_exercise_head_text(mG.group(4)):
                    rows.append((p, 'EXER',
                                 '%s.%s.%s' % (mG.group(1), mG.group(2),
                                               _EXER_GARBLE_LETTER[mG.group(3)]),
                                 mG.group(4).strip()))
                    continue
                mSV = EXER_3_SV.match(ln)
                if (mSV and int(mSV.group(1)) == ch
                        and is_exercise_head_text(mSV.group(4))):
                    rows.append((p, 'EXER', '%s.%s.%s' % mSV.group(1, 2, 3),
                                 mSV.group(4).strip()))
                    continue
                m = ITEM_3.match(ln)
                if m and int(m.group(1)) == ch:
                    rows.append((p, 'ITEM', '%s.%s.%s' % m.group(1, 2, 3), m.group(4).strip()))
    # 🔴 页眉带复本不得充当节/字母块的窗口左界（判据见 demote_head_band_rows）：
    # 抽取器按「页 + 块首 y」分桶后，页顶那行页眉会把本节左界推到页首，同页页眉
    # 之下仍在续的**上一节尾条**就被判给本节（Arnold ch7 p162 实测 2026-09-28）。
    rows, _nhb = demote_head_band_rows(rows, _head_band)
    if _nhb:
        print('[scan_skeleton] ch%s 页眉带复本行降级 %d 条（同号在本页有更靠下的真行）'
              % (ch, _nhb), file=sys.stderr)
    # global_sec（单级节号书）的节键必为单一数字：mode 正则（SEC_CN/SEC_2…）
    # 捕获的 "C.S" 形态在此类书里只可能是图号/页码粘连等散文误报（谷超豪
    # 《数学物理方程》ch7 实测 "7.7 所示"），一律剔除。
    if global_sec:
        rows = [r for r in rows
                if r[1] != 'SEC' or '.' not in str(r[2])
                or str(r[2]) in local_sec_keys]
        # 🔴 幻一节头闸（判据见 _global_sec_intruders 注释）：全局单号 § 在本章
        # 阅读序上必须严格递增；逆序号中「不在任何极大递增子序列上」的必是幻影
        # （页眉与正文粘连行），平局时只剔除余文不成标题的一方。剔除后把被带偏
        # 的裸字母子块父键按页码重新挂回最近的真节。
        _drop = _global_sec_intruders(
            [(r[2], r[3]) for r in rows
             if r[1] == 'SEC' and _SEC_SINGLE_KEY_RE.match(str(r[2]))])
        if _drop:
            _drop_str = {str(n) for n in _drop}
            # 剔除后仍存活的单号 § (页码, 号)，按阅读序（rows 本身即阅读序）。
            _kept = [(r[0], str(r[2])) for r in rows
                     if r[1] == 'SEC' and _SEC_SINGLE_KEY_RE.match(str(r[2]))
                     and str(r[2]) not in _drop_str]
            rows = [r for r in rows
                    if not (r[1] == 'SEC' and str(r[2]) in _drop_str)]
            _fixed = []
            for r in rows:
                if r[1] != 'SUB':
                    _fixed.append(r)
                    continue
                _par, _sep, _let = str(r[2]).rpartition('.')
                if _par not in _drop_str:
                    _fixed.append(r)
                    continue
                # 幻影号当时污染了 cur_global_sec：改挂该页之前最近的真节，
                # 章内无前置真节时退化为无父键（与附录字母头同型）。
                _new = ''
                for _pg, _n in _kept:
                    if _pg > r[0]:
                        break
                    _new = _n
                _fixed.append((r[0], 'SUB', _new + _sep + _let, r[3], *r[4:]))
            rows = _fixed
            print('[scan_skeleton] ch%s 幻一节头剔除：§%s（与本章 § 阅读序矛盾 / '
                  '余文不成标题）' % (ch, ','.join(sorted(_drop_str, key=int))),
                  file=sys.stderr)
    # 🔴 C.S.1 二现冲突破解（Rising Sea 实测 35+ 节）：印刷字母习题 I 被
    # OCR 读成数字 1（"10.1.I. EXERCISE." p285 → "10.1.1. ExERCISE. …"），
    # 与该节真条目 "10.1.1. Motivation…" 撞键。数字条目在同节内不可能
    # 印刷两次同号 → 二现必有一假，按头形态裁决：真习题头（大写修饰词 +
    # EXERCISE + 边界，条头行必以题头起）者改回字母 I；两者皆/皆非题头
    # 形态时不动（宁缺勿滥，交审计暴露）。
    _one_occ = {}
    for _i, _r in enumerate(rows):
        if _r[1] == 'ITEM':
            _k = str(_r[2])
            _c = re.match(r'^(\d{1,2})\.(\d{1,2})\.1$', _k)
            if _c:
                _one_occ.setdefault(_k[:_c.end(2)], []).append(_i)
    _exer_keys = {str(r[2]) for r in rows if r[1] == 'EXER'}
    for _sec, _idxs in _one_occ.items():
        if len(_idxs) != 2:
            continue
        _ik = _sec + '.I'
        if _ik in _exer_keys:
            continue
        _heads = [is_exercise_head_text(str(rows[_i][3] or '')) for _i in _idxs]
        if sum(_heads) == 1:
            _bad = _idxs[_heads.index(False)]
            _r = rows[_bad]
            rows[_bad] = (_r[0], 'EXER', _ik, _r[3], _r[4] if len(_r) > 4 else None)
    # 🔴 字母序列位修正（Rising Sea 16.7 实测）：字母习题在一节内严格递增
    # 排布（A,B,C,…，同号不可能印刷两次）→ 「同节同字母二现 + 下一字母
    # 缺席」时二现必是相邻字形误读（F→E，OCR 把 '16.7.F.' 读成 '16.7.E.'）。
    # 把第二次出现改判为缺失的下一字母。仅限无数字混淆的字母（I/O 已由
    # 上方词形裁决处理）。
    _lseq = {}
    for _i, _r in enumerate(rows):
        if _r[1] == 'EXER':
            _mm = re.match(r'^(\d{1,2}\.\d{1,2})\.([A-Z])$', str(_r[2]))
            if _mm:
                _lseq.setdefault(_mm.group(1), []).append((_i, _mm.group(2)))
    for _sec, _its in _lseq.items():
        _lets = [l for _, l in _its]
        _cnt = collections.Counter(_lets)
        _have = set(_lets)
        for _l, _n in _cnt.items():
            if _n < 2 or _l in ('I', 'O'):
                continue
            _nxt = chr(ord(_l) + 1)
            if _nxt in _have or _nxt > 'Z':
                continue
            _seen1 = False
            for _i, _lt in _its:
                if _lt != _l:
                    continue
                if _seen1:
                    _r = rows[_i]
                    rows[_i] = (_r[0], 'EXER', _sec + '.' + _nxt, _r[3],
                                _r[4] if len(_r) > 4 else None)
                    break
                _seen1 = True
    # 🔴 裸单号体例仲裁：同一章里「带点题号」习题（C.S / C.S-N，由 STICKY_EXER_RE /
    # EXER_3N 在闩锁内收录）与「裸单号」习题（Apostol 体例）不可能同真——两种形态
    # 互斥。只要本章存在带点题号习题，上方按裸号收的行就是别的东西（正文列举、
    # 公式续行、他章题号），整体退回，保证对既有书零回归。
    if bare_exer_idx and any(r[1] == 'EXER' and '.' in str(r[2]) for r in rows):
        rows = [r for i, r in enumerate(rows) if i not in bare_exer_idx]
    # 统一 5 元组 (p, kind, num, title, y)：SEC 行发射处已带块顶 y（页眉压制的
    # glue 变体与同页 y 感知归都依赖它）；EXER/ITEM/SUB 行 y=None。
    rows = [r if len(r) == 5 else (r[0], r[1], r[2], r[3], None) for r in rows]
    return rows


def numeric_local_subsection_probe(ranges, *, mode, default_dir=None,
                                   chapter_first=False,
                                   plain_sec_heads=False,
                                   min_parents=2, min_sections=6):
    """Detect the Arnold-ODE shape: single-number global § heads whose bodies
    contain bare ``N. Title`` sub-heads restarting at 1 inside every §.

    ``ranges`` is a list of ``(ch, start, end[, page_dir])`` tuples where
    ``start``/``end`` are PAGE NUMBERS (ints) and ``page_dir`` is the directory
    holding that chapter's ``page_*.json`` (falls back to ``default_dir``).  We
    run the PRODUCTION scanner (``scan``) with ``sections_global=True`` +
    ``local_num_sec=True`` on each chapter so the detector sees EXACTLY what
    ``build_structure`` will later build (no second regex → no drift).  The §
    heads require a literal ``§`` glyph (SEC_GLOBAL_SPACED), so a dotted-heading
    book (which prints ``20.5 Title``) yields ZERO single-number § here and
    cannot false-fire; a global-§ book without numeric sub-blocks yields § but no
    dotted children.  Both fall below the thresholds and return ``False``.

    Returns ``(fire, info)`` where ``fire`` is the boolean verdict and ``info``
    is a diagnostic dict (``parents`` / ``children``).  ``fire`` is True only
    when there are >= ``min_parents`` § that EACH carry a clean ``1..k`` run and
    the total number of subsections >= ``min_sections`` — the conservative
    fingerprint of a genuine third structural level, not stray OCR.
    """
    sec_parents = set()
    children = {}                      # parent § -> set(local number str)
    for tup in ranges:
        if len(tup) >= 4:
            ch, start, end, page_dir = tup[0], tup[1], tup[2], tup[3]
        else:
            ch, start, end = tup[0], tup[1], tup[2]
            page_dir = None
        if start is None or end is None:
            continue
        scan_dir = page_dir or default_dir
        if not scan_dir:
            continue
        rows = scan(scan_dir, ch, start, end, mode,
                    chapter_first=chapter_first,
                    plain_sec_heads=plain_sec_heads,
                    sections_global=True, local_num_sec=True)
        for r in rows:
            if r[1] != 'SEC':
                continue
            k = str(r[2])
            if '.' in k:
                parent = k.split('.', 1)[0]
                children.setdefault(parent, set()).add(k.split('.', 1)[1])
            else:
                sec_parents.add(k)
    # A parent counts only if its children form a contiguous run starting at 1.
    good_parents = {p for p, s in children.items()
                    if s and s == {str(i) for i in range(1, len(s) + 1)}}
    total_children = sum(len(children[p]) for p in good_parents)
    fire = (len(good_parents) >= min_parents
            and len(good_parents & sec_parents) >= min_parents
            and total_children >= min_sections)
    return fire, {
        "sec_parents": sorted(sec_parents, key=lambda x: int(x) if x.isdigit() else x),
        "good_parents": sorted(good_parents, key=lambda x: int(x) if x.isdigit() else x),
        "total_children": total_children,
    }


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]

    if not args:
        print(__doc__)
        return 2
    extract_dir = args[0]
    # 章号归一：数字章 → int，附录字母章（"A"/"B"…）保留原串；排序用
    # chapter_sort_key（数字章在前按数值、附录字母章排末尾）。
    from data.book_structure.book_structure import (norm_chapter_key,
                                                    chapter_sort_key,
                                                    chapter_label)
    want = [norm_chapter_key(x) for x in args[1:]]

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
            rng[norm_chapter_key(k)] = (int(c['start']), int(c['end']))
    else:
        for c in chapters:
            n = c.get('num', c.get('ch', c.get('chapter', c.get('n'))))
            rng[norm_chapter_key(n)] = (int(c['start']), int(c['end']))

    for ch in (want or sorted(rng, key=chapter_sort_key)):
        if ch not in rng:
            print('%-9s SKIP (not in chapter_map)' % chapter_label(ch))
            continue
        start, end = rng[ch]
        rows = scan(extract_dir, ch, start, end, mode, section_depths=section_depths,
                    chapter_local_numbering=getattr(
                        loader.book, 'chapter_local_numbering', False))
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
        print('%-9s | secs=%s items=%d exercises=%d'
              % (chapter_label(ch), secs, n_item, n_ex))
    return 0


if __name__ == '__main__':
    sys.exit(main())
