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
import page_json
from lib.page_dir import resolve_page_dir

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 verify/item_numbering_integrity/item_numbering_integrity.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""
item_numbering_integrity.py — B-LAYER (order 3): 缺号检测（忠于原文）。

权威检测落在 agent 写出的 .md 上，按 `ctx.config.ordinal` 决定的编号编排类型
（由 ConfigLoader 从 verify_config.json 读入，挂在 ctx.config，不依赖任何编排层透传）正确分组后，
对组内序号做首项/连续性检查。

md 内部的缺号默认是「硬 BLOCKING」（严格模式，不允许遗漏）：任何序号不连续
都会要求核对。很多书定理/引理类条目本就稀疏（如某章只有 `Lemma 2.5`），这些
经核对确认是书本身编号、非遗漏的，应在配置文件 `ignore` 中登记，以免误报。
配置 `strict: false` 才降级为非阻塞警示。硬阻塞也来自提取侧契约（若已接线）。
语义 / 分组 / 契约键等详见 verify/item_numbering_integrity/item_numbering_integrity.md（SSOT）。
"""
import json
import os
import re
import functools
from collections import defaultdict
from dataclasses import dataclass, field

from verify.script.base import VerifyLayer, LayerResult
from key_parse import sortkey, _canon_label
from lib.regexlib import SEP_TIGHT, SEP_SPLIT_RE
from verify_config import ORDINAL_THREE_LEVEL

# 与 audit_ignore.py 的 _EVIDENCE_TOKENS 对齐：ignore 理由含下列任一证据标记时，
# 视为 agent 已核对源书、确为共享计数器 / 作者稀疏编号（非真实缺项）。
_EVIDENCE_TOKENS = ("VERIFIED-SPARSE", "已核实跳号", "源书真实跳号", "sparse numbering")


def _load_evidenced_ignore(ext):
    """返回已附 VERIFIED-SPARSE 证据的 ignore 键集合（含 _norm_sep 形态），
    供 B 层 IGNORE-SUSPECT 与 audit_ignore.py 的 ACCEPTED 判定保持一致——
    已核实的稀疏跳号不再重复告警（未附证据的 ignore 仍照常告警，护栏不弱化）。
    """
    ev = set()
    if not ext or not os.path.isdir(ext):
        return ev
    for name in os.listdir(ext):
        if ((name.startswith("ignore_ch") or name.startswith("ignore_appendix"))
                and name.endswith(".json")):
            fp = os.path.join(ext, name)
            try:
                data = json.load(open(fp, encoding="utf-8"))
            except Exception:
                continue
            if isinstance(data, dict):
                for k, v in data.items():
                    reason = v if isinstance(v, str) else ""
                    if any(tok in reason for tok in _EVIDENCE_TOKENS):
                        ev.add(k)
                        ev.add(_norm_sep(k))
    vc = os.path.join(ext, "verify_config.json")
    if os.path.exists(vc):
        try:
            cfg = json.load(open(vc, encoding="utf-8"))
        except Exception:
            cfg = {}
        for field in ("ignore", "known_gaps", "ignore_keys"):
            for k in cfg.get(field, []) or []:
                if isinstance(k, dict):
                    for kk, vv in k.items():
                        if any(tok in str(vv) for tok in _EVIDENCE_TOKENS):
                            ev.add(kk)
                            ev.add(_norm_sep(kk))
    return ev


# Tail-check tolerance: source max minus md max beyond this is treated as a
# likely OCR phantom / alien-numbering and collapses to ONE summary warning
# instead of a per-number flood (mirrors D-layer's TAIL_GAP_THRESHOLD=5).
_TAIL_GAP_CAP = 5

# A bold **...** span. We parse the inner text to decide if it is a real item
# header (vs a citation like "**见 4.11-5**").
# 注意：inner 允许出现 '*'（如 $X^*$ 内的星号），否则带数学的标题会被整段拆断、
# 其编号解析不到 -> 误报「首项缺失」。约束改为「不跨行」([^\n])，仍由下一个 '**' 收尾。
_SPAN_RE = re.compile(r'\*\*([^\n]*?)\*\*')
_CITE_RE = re.compile(r'^[（(]*(见|由|根据|参考|参见|据|依照|按|Cf\.|cf\.)')

# 证明标题（"X.Y-Z 的证明" / "X.Y-Z Proof."）是证明小节，不是被定义的条目，
# 不得计入条目序列（既会污染缺号 present 集合，也会在顺序校验里制造伪回归）。
_PROOF_RE = re.compile(r'^(证明|的证明|proof|beweis|demonstration|dem\b)', re.IGNORECASE)
# 证明标题条目的**尾部**证明词（「N.M.K 定理 N.M.J 的证明。」/ '… Proof.'）：
# 专名/引用号在前、证明词收尾 → 该条目本身是印刷的证明项（Vakil 共享计数器
# 把「X 的证明」列为条目），不得按引用丢弃。
_PROOF_TAIL_RE = re.compile(r'(?:的证明|之证明|证明|proof)\s*[。.．]?\s*$', re.IGNORECASE)

# EXTRA-MENTION 收窄：下列「题集」类标签在正文 / 交叉引用中出现时，必为对
# consolidated 习题块的合法引用（练习 / 习题 / Problem / 问题 / Question 在 skill 设计里
# 从不作为契约条目登记，load_contract 对 exercise/problem 直接 return），非漏登记条目
# → 从提及桶剔除，避免误报。个别非题集的外部引用（如 Euclid 命题）由 per-book
# verify_config.json 的 mention_ignore 显式豁免。
_EXM_DROP_RE = re.compile(
    r'(练习|习题|Exercise|exercise|Problem|problem|问题|Question|question)\s*[\d.]+')

# 🔴 无标签习题序列的契约真值路由（2026-10-02 Katok 根治）。
#   印面把某些书的节后习题**不冠任何标签词**直接排成裸号条头：Katok《Modern
#   Theory》每节后段就是 `2.9.1.` / `2.9.2.` / `2.9.3.`（fitz 目视 + 契约
#   `book_structure/ch2.json` 里 §2.9 的三个 `type: "exercise"` 节点为证），
#   而该书条目计数器**跨类型共享且按节重启**（Definition 2.9.1 → Theorem 2.9.2
#   → … → Proposition 2.9.5，单一 ordinal 组、`separate_types` 未开）。
#   于是 md 里 `**Definition 2.9.1**` 与 `**2.9.1.**` 是**两条不同的印刷序列**，
#   却被现有的「按条头标签词路由 ex 窗」判据看成同一窗（裸号头没有标签词可读）
#   → 阅读顺序窗出现 同号二现 [1,2,3]，全书 81 条「疑似幽灵重复节点」WARN。
#   后果不是难看：该 WARN 正是 B 层用来区分「重复节点伪影」与「真条目错位
#   (BLOCKING 顺序错乱)」的那一支，把真序列碰撞说成伪影 = 错位信号被稀释。
#   修法 = 让**契约类型**（标签无关的真值）参与路由，但只作**候选**：条头无标签词而
#   该键在契约里登记为 exercise / problem 者，还要过一道「同号二现」碰撞判据
#   （`_resolve_bare_ex_candidates`）才真开窗。Weibel 类书每节只有一条 1..N 共享
#   计数器，裸号头 `**10.2.3（疏解…）**` 本身就是序列成员，抢先开窗会把主窗挖成
#   假缺号（跨书普查 2026-10-02：Weibel ch1–10 BLOCKING 0→79）。
#   `exercise_node_windows` 已按设计排除 `consolidated` 成堆块（writing-rules 规定
#   集中习题块不进总结，md 里本就没有）。
#   两道既有守卫照旧生效：`is_uncat` 合并计数器（Vakil）与
#   `exercise_shared_numbering`（Lee / Etingof）下**不得**另开窗，否则主窗假缺号。
def _norm_ex_key_form(raw):
    """契约习题节点键 → md 键形：最后一段之前用短横（`2.9.1` → `2.9-1`）。

    非纯数字尾段（`问题1` / `Example A`）原样返回，绝不凭空造号。
    """
    s = str(raw or '').strip()
    parts = [p for p in SEP_SPLIT_RE.split(s) if p]
    if len(parts) >= 2 and parts[-1].isdigit():
        return '.'.join(parts[:-1]) + '-' + parts[-1]
    return s


def _contract_exercise_keys(ext_dir, ch):
    """本章契约里登记为 exercise / problem 的节点键（md 键形集合）。

    契约缺失 / 读不出 → 返回空集（不路由，行为逐字节回到改前）。
    🔴 路径按**磁盘物理证据**解析（`resolve_chapter_json_path`）而非只信
    `chapter_json_path`：后者的章型前缀取自进程级注册表，可被同进程另一本书污染，
    于是 `ch3.json` 被算成 `appendix3.json` → 契约「读不到」→ 本判据静默失明
    （实测教训见该函数 docstring）。
    """
    if not ext_dir or ch is None:
        return set()
    try:
        from data.book_structure.book_structure import (
            exercise_node_windows, norm_chapter_key, resolve_chapter_json_path)
        fp = resolve_chapter_json_path(ext_dir, norm_chapter_key(ch))
        if not os.path.isfile(fp):
            return set()
        with open(fp, encoding='utf-8') as f:
            root = json.load(f)
        return {_norm_ex_key_form(k)
                for k, _ps, _pe, _nc, _nm in exercise_node_windows(root)}
    except Exception:
        return set()


def _exercise_window_routing(label, prefix_str, key, contract_ex_keys, *,
                             combined, shared, stays_main, demoted_word=False):
    r"""该条头要不要并入**独立习题窗**（gk 中段插 `ex`）。

    返回 ``(routed, bare_candidate)`` 两条腿，身份来源不同、处置时机也不同：
      ① ``routed``：条头自带习题标签词（``_EXERCISE_LABELS``）——身份自证，
         调用处**立即**开窗（原行为）；
      ② ``bare_candidate``：条头**无标签词**（裸号 `**2.9.1.**`）但该键在**契约**里
         登记为 exercise / problem（``contract_ex_keys``，Katok 体例，见
         `_contract_exercise_keys` 注记）——2026-10-02 新增。裸号头**不在此处**开窗：
         它没有自证的标签，必须再过一道「同号二现」碰撞判据
         （`_resolve_bare_ex_candidates`），否则会把共享计数器书的裸号头从主窗挖走
         造成假缺号（Weibel 实测，见该函数注记）。
    放行方向只改「同一个号属于哪条印刷序列」的归属，不改任何计数判据。

    守卫缺一不可（各拦一次实测假缺号）：
      · ``combined``（Vakil uncat 合并计数器）：练习本身就是主序列成员；
      · ``shared``（Lee / Etingof ``exercise_shared_numbering``）下**裸号头**不得
        另开窗——它没有标签词可自证身份，挪走就是把主序列的号凭空抹掉；带习题标签词
        的共享头由调用方折算进 ``stays_main``（同源判据，两条路径都留在主窗）；
      · ``stays_main``：共享计数器下与条目同形（点号多段）的 Problem；
      · ``prefix_str`` 为空：gk 是 `gi:file` 形态，另开窗会被 body 解析读成
        prefix='file'，故裸文件窗一律不动；
      · ``demoted_word``：条头里**本就写着**习题词、只是被行首难度标记 `\*` 挡住了
        标签解析（Intro-to-Dyn-Systems ch3 实测 `**\\*习题 3.2.2.**`，label 落
        'uncat'）。该头的归属由既有的两步法（`_resolve_demoted_entries` 按习题词
        所在组回补真习题窗）裁决；裸号腿若抢先，就会把它并进**内容组**的 ex 窗
        （`0:ex:3.2`），真习题窗 `1:ex:3.2` 反而被挖出假「缺号 2」。
    """
    _lab = (label or '').strip().lower().rstrip('*')
    routed = bool(_lab in _EXERCISE_LABELS and not combined and not stays_main)
    bare = bool(prefix_str and _lab in ('', 'uncat')
                and not demoted_word
                and not combined and not shared and not stays_main
                and key in (contract_ex_keys or set()))
    return routed, bare


def _resolve_bare_ex_candidates(entries, pending):
    r"""裸号习题头的**碰撞判据**：仅当同一条主窗里**另有具名条头占着同一个键**时，
    才把它并入 ex 窗；否则留在原地。

    跨书普查 2026-10-02（623 单元 old/new 对拍，脚本 = chaos 书
    `_extract/_census_b_ab_routing.py`）实测两侧形态：
      · Katok：印面并存**两条**序列（`**Definition 2.9.1**` 与 `**2.9.1.**` 同窗
        同号二现）→ 必须搬走，否则「疑似幽灵重复节点」把真错位信号稀释成伪影；
      · Weibel：每节**只有一条** 1..N 共享计数器，裸号头 `**10.2.3（疏解…）**`
        本身就是该序列的成员（契约把它登记成 exercise 也不改变这一点），搬走就把
        主窗挖成假「缺号」——普查里 Weibel ch1–10 一次 BLOCKING 0→79。
    碰撞 = 同 `(gk, key)` 由**非候选**条目的具名头登记过。
    """
    if not pending:
        return entries
    idxs = {i for i, _gk, _key in pending}
    claims = {(gk, key) for i, (gk, _n, key, *_r) in enumerate(entries)
              if i not in idxs}
    for i, gk, key in pending:
        if (gk, key) not in claims:
            continue
        _gh, _gb = gk.split(':', 1)      # 候选必有节前缀（见路由函数 prefix_str 守卫）
        entries[i] = (f"{_gh}:ex:{_gb}",) + tuple(entries[i][1:])
    return entries

# The inter-component separator is now SEP_TIGHT, defined ONCE in lib.regexlib
# and reused everywhere so every book's punctuation variant normalizes the same
# way.  Different books use '.' or '-' (or fullwidth variants) interchangeably
# (e.g. '4.11-5' vs '4.11.5' vs '4·11-5'); the wildcard is built-in, so the
# per-book config need NOT specify separators.
# Numeric "path" length is DRIVEN BY cfg.levels — NOT a hardcoded {0,2}.
# A 2-level book matches exactly '4.1' / '4-1'; a 3-level book exactly
# '4.11-5'.  Building the regex per `levels` keeps the parse honest to the
# per-book config instead of silently over-matching (a 2-level book could
# otherwise grab a spurious 3rd component) or under-matching.
#   lv=1 -> \d+                 (whole-file / per-chapter sequential)
#   lv=2 -> \d+(?:SEP_TIGHT\d+)      (chapter.section)
#   lv=3 -> \d+(?:SEP_TIGHT\d+){2}   (chapter.section-item)
@functools.lru_cache(maxsize=16)
def _numpath_regexes(levels):
    """Return (exact, cap, label_first, num_first) compiled patterns for a
    numbering of `levels` numeric components.  Cached per `levels` so the
    per-span parse does not recompile."""
    lv = max(1, int(levels))
    rep = '{' + str(lv - 1) + '}'               # {0}/{1}/{2} for 1/2/3 levels
    numpath = r'[A-Za-z]?\d+(?:' + SEP_TIGHT + r'\d+)' + rep
    exact = re.compile(r'^' + numpath + r'$')
    cap = re.compile(r'(' + numpath + r')')
    # re.IGNORECASE: English books (e.g. Apostol) print headings in UPPERCASE
    # (LEMMA 11.1. / THEOREM 8.16.) or OCR-mangled mixed case (THEoREM /
    # CoROLLARY). Without it the label-first match fails -> the B-layer parses
    # ZERO bold entries for the EN .md and silently reports no gaps (false
    # pass). Chinese labels are case-insensitive anyway, so this is safe for
    # every book. Mirrors ENTRY_RE_EN_C in lib/key_parse.py (same fix applied there).
    label_first = re.compile(r'^(?:' + _ENTRY_LABELS + r')\s*' + cap.pattern,
                             re.IGNORECASE)
    num_first = re.compile(r'^' + cap.pattern + r'\s+(.*)$')
    return exact, cap, label_first, num_first

# Structural entry labels (Chinese + English).  These open a numbered item.
# NOTE: extended forms (例子/例题/注记/评注) MUST precede their short stem
# (例/注) so the regex matches the longest label first.  Otherwise a header
# like "7.6-2 例子（…）" matches only "例" and the trailing Han char ("子")
# is then treated as prose by _after_label_boundary and the entry is dropped
# (this silently broke combined 定义/定理/例 counters).  See _parse_entry.
_ENTRY_LABELS = (
    r'系|定理|定义|引理|推论|命题|例子|例题|例|注记|评注|注|公理|问题|练习题|练习|习题|引例|附注'
    # 🔴 Iwaniec-Kowalski 2026-09-28 实测：`猜想`/`Conjecture`（及断言/假设/条件）
    # 是 _LABEL_CANON 已正名的标准条目类型，但不在本词表 → 合成 md 条头
    # `**猜想7.32**` 只剩裸号 `7.32` 走 num-first、tail 空 → 被丢弃 →
    # 共享计数器窗假「缺号 32」（BLOCKING、整章卡结构闸门）。
    r'|猜想|断言|假设|假定|条件'
    r'|算法|性质|构造|应用|变式|警告|记号|术语|要求'
    # 🔴 Plurals MUST precede their singular ('Remarks|Remark'): the alternation
    # is first-match, so with the singular first a header '8. Remarks' matched
    # 'Remark' and left 's' behind — which _after_label_boundary reads as a
    # word boundary violation, so the real entry was dropped and the B-layer
    # manufactured 缺号 for it (Gelfand–Manin ch1-ch5, EN md only).
    r'|Theorems|Theorem|Definitions|Definition|Lemmas|Lemma|Corollaries|Corollary'
    r'|Propositions|Proposition|Examples|Example|Remarks|Remark'
    # 🔴 Kreyszig「4.11-2 Requirement / **要求 4.11-2。**」：以「要求」命名的条目。
    # 缺该词时 CN 条头 label-first 无词可配 → 整条不被计数 → 假「§4.11 缺号 2」
    # （EN 版因编号在前走 num-first 兜底而侥幸通过，两版判定不一致即是证据）。
    r'|Requirements|Requirement'
    r'|Exercises|Exercise|Problems|Problem|Notes|Note|Axioms|Axiom|Warnings|Warning'
    r'|Constructions|Construction|Notations|Notation|Terminology'
    r'|Applications|Application|Variations|Variation|Porisms|Porism'
    # 🔴 同 CN 侧「猜想」缺失的同源 bug（Iwaniec-Kowalski 实测）：EN 词表无
    # Conjecture/Assertion/Assumption/Condition 时 `**Conjecture 7.32**` 解析失败
    # → 假缺号。Plurals 同样须排在单数前。
    r'|Conjectures|Conjecture|Assertions|Assertion|Assumptions|Assumption'
    r'|Conditions|Condition'
    r'|Calculations|Calculation'
)
# 🔴 Weibel「Calculation 6.2.1」这类以计算命名的条目：缺该类型词时条头解析
# 不出编号 → 假「缺号」（实测 ch6 §6.2 报缺 1）。
# Labels that open the independent exercise window (see bucket routing below).
_EXERCISE_LABELS = ('exercise', 'exercse', 'problems', 'problem', '习题', '练习', '问题')
# Label-first:  LABEL  NUMPATH   (e.g. "定理 4.1", "Definition 2.1")

# Normalize a CN entry label to its EN canonical so that `known_gaps` entries
# written in English also suppress the CN (or any-language) counterpart.
_LABEL_NORM = {
    '定理': 'Theorem', '定义': 'Definition', '引理': 'Lemma', '推论': 'Corollary',
    '命题': 'Proposition', '例子': 'Example', '例题': 'Example', '例': 'Example',
    '注记': 'Remark', '评注': 'Remark', '注': 'Remark', '公理': 'Axiom',
    '问题': 'Problem', '练习': 'Exercise', '习题': 'Exercise', '引例': 'Example',
    '附注': 'Remark', '算法': 'Algorithm', '性质': 'Property',
    '应用': 'Application', '变式': 'Variation', 'Application': 'Application',
    '系': 'Porism', '警告': 'Warning', '记号': 'Notation', '术语': 'Terminology',
    '要求': 'Requirement', 'Requirement': 'Requirement',
    '猜想': 'Conjecture', '断言': 'Assertion', '假设': 'Assumption',
    '假定': 'Assumption', '条件': 'Condition',
    'Variation': 'Variation', 'Porism': 'Porism',
}


def _norm_label(label):
    return _LABEL_NORM.get(label, label)


# Normalize the inter-component separator inside a gap token's numeric part so
# that `known_gaps` written with '.' ("Theorem 12.3") match emit tokens built
# with '-' ("Theorem 12-3") — the B-layer emits the dash form (C.S-N / C-N),
# while users naturally write the dot form.  Only separators BETWEEN two digits
# are touched.
_SEP_BETWEEN_DIGITS = re.compile(r'(?<=\d)' + SEP_TIGHT + r'(?=\d)')
def _norm_sep(s):
    return _SEP_BETWEEN_DIGITS.sub('.', s)

# label-first / number-first regexes are now built per `levels` inside
# _numpath_regexes() (the path length must track cfg.levels, see above), so
# there are no module-level _RE_LABEL_FIRST / _RE_NUM_FIRST anymore.


def _split_numpath(s, levels):
    """Parse a bare key like '4.1' / '4.1-2' / '5' into a list of int
    components, or None if it is not a valid `levels`-level numeric path.
    `levels` drives the required component count (see _numpath_regexes)."""
    s = s.strip()
    exact, _cap, _lf, _nf = _numpath_regexes(levels)
    if exact.match(s):
        return _comps_of(s)
    return None


def _comps_of(numpath):
    """Integer components of a captured numpath, or None when it is not all
    digits.

    🔴 `_numpath_regexes` deliberately allows a leading letter (appendix-style
    "A3"), so a captured path can be alphanumeric — e.g. Gelfand–Manin ch2
    `**2.5-2 2. Axiom A1**`, where the "label + numpath" fallback captures
    "A1" out of the axiom's own NAME.  Every consumer of a parsed entry wants
    ints, so a non-numeric component must mean "this span is not an item path"
    rather than raising ValueError and killing the whole verify run.
    """
    parts = SEP_SPLIT_RE.split(numpath.strip())
    if not all(p.isdigit() for p in parts):
        return None
    return [int(p) for p in parts]


def _is_header_boundary(tail):
    """After the numeric path, the bold span must terminate the *header*
    (colon / paren / period / end-of-span) — not run into prose such as
    '的证明' or ' and', which would indicate a *reference* rather than a
    defined entry."""
    s = tail.lstrip()
    if not s:
        return True
    c = s[0]
    if c in ':.。():（）)，,；;*':
        # 🔴 FIX ⑧（Vakil ch25 实测幽灵窗）：'.'/'。' 之后紧跟数字 = **更深层
        # 编号被浅级 cap 截断**的残段（2 级回退把「定理 25.2.2 的证明」啃成
        # [25,2]），不是条头终止符。真正的结尾句号后不会直接再跟数字。
        if c in '.。．' and s[1:2].isdigit():
            return False
        return True
    if c in '-–—·/~〜' and s[1:2].isdigit():
        # 分隔符型 SEP_TIGHT 成员（dash 系）后接数字同理 = 截断残段
        return False
    if c.isalpha():          # latin letter -> 'Theorem 4.1 and ...' prose
        return False
    if '一' <= c <= '鿿':
        # A Han-char continuation after the number is normally a DESCRIPTIVE
        # TITLE of the entry (e.g. '定理1 设 λ 为…', '例8 求 √115：'), which IS a
        # real numbered entry header.  Only explicit possessive / citation openers
        # mark a cross-reference ('定理 4.1 的证明', '由定理…') and must stay
        # rejected.  This mirrors the _is_reference_tail philosophy: a Han-start
        # descriptive title is a REAL entry, not a reference — rejecting it
        # silently drops legitimate entries and manufactures false 缺号 (BLOCKING).
        if re.match(r'^(?:的|之)?(?:证明|应用|推论|推广|逆|特例|注|说明|扩展|上界|下界|估计|逼近|表示|等价|形式)', s):
            return False
        if s[:1] in _CN_CITATION_STARTERS or (len(s) >= 2 and s[:2] in _CN_CITATION_STARTERS):
            return False
        return True
    return True


# After a matched label in a NUMBER-FIRST header ("4.3-1 定理 …"), the text that
# follows the label must terminate the *header* (paren/colon/end), not run into
# another numberpath ("定理 4.1 …" = cross-reference) or Han/latin prose
# ("定理 的应用" = reference).  See _is_header_boundary for the label-first case.
def _after_label_boundary(after):
    s = after.lstrip()
    if not s:
        return True
    c = s[0]
    if c in ':.。():（）)，,；;*':
        return True
    if c.isdigit() or c.isalpha():      # another numberpath or latin prose
        return False
    if '一' <= c <= '鿿':                 # Han char -> prose/reference
        return False
    return True


# A number-first header with NO standard label word (e.g. "4.11-2 必要条件")
# is a descriptive title, not a reference, ONLY if its tail does not start with
# a citation/function word or latin prose.  Otherwise it is prose/reference and
# must NOT be counted as an entry (avoids false gaps AND false entries).
_PARTICLES = set('的 和 与 及 以 由 见 据 按 因 若 当 但 且 或 等 也 仍 可 不 在 '
                '对 从 把 被 让 设 则 故 即 如 其 该 此 这 那 中 上 下 后 前 内 '
                '外 之 而 并 将 已 为 使 给 向 到 自 经 比 较 证 推 应'.split())


# A printed enumerator that precedes an item's own type word inside a bold
# header: '8. Remarks', 'b) Define …'.  Only after such a prefix (or at the very
# head of the tail) is a matched type word the HEADER's label, as opposed to a
# word quoted inside a cross-reference sentence.
_ENUM_HEAD_RE = re.compile(r'^\s*(?:\d+|[ivxlcdm]+|[a-zA-Z])[.)、]\s*$')


def _han_glued_word(raw_after):
    """True when the text glued (no space) straight onto a matched type word
    continues it as a Han WORD rather than describing it: '系' in 系数系统, '注记' in
    注记与例子.  Such a match is a stem inside a compound, not the item's label."""
    return bool(raw_after) and '一' <= raw_after[0] <= '鿿'


def _label_heads_tail(tail, start):
    """True when the type word found at `tail[start:]` is the header's own label
    (it opens the tail or only the printed enumerator stands before it)."""
    return start == 0 or bool(_ENUM_HEAD_RE.match(tail[:start]))


def _is_citation_starter(s):
    """True if `s` opens with an explicit cross-reference marker.  Lets the EN
    relaxation below still drop genuine references like 'see Theorem 4.1' /
    'cf. Example 2' while counting descriptive titles that start with a content
    word ('Space', 'Banach', 'A space', 'The open mapping theorem')."""
    head = re.match(r'[A-Za-z]+', s)
    if not head:
        return False
    return head.group(0).lower() in ('see', 'cf', 'viz', 'ibid')


# Explicit cross-reference starters for CJK (Han-start) tails.  A descriptive
# item title may start with ANY other Han char — including negation '不' ("不完备的
# 赋范空间" = Incomplete normed spaces) or '由' ("由...定义的度量") — so only these
# unambiguous citation words mark a reference; everything else is a REAL entry.
_CN_CITATION_STARTERS = ('见', '据', '按', '参', '依', 'cf')


def _is_reference_tail(tail, lang=None):
    s = tail.lstrip()
    if not s:
        return True
    c = s[0]
    # Latin letters ONLY — CJK chars are .isalpha() too, but a descriptive title
    # that starts with a Han char (e.g. "必要条件", "收敛性") is a REAL entry,
    # not a reference.  It must fall through to the particle check below, and if
    # it is not a known connective it is counted as 'uncat'.  Treating every
    # Han-starting tail as a reference silently drops legitimate entries and
    # manufactures false "缺号".
    if c.isascii() and c.isalpha():     # English prose / latin citation
        # EN books carry descriptive item titles in English (Latin-start), e.g.
        # "2.2-3 Space l^p".  These are REAL entries, not references — only drop
        # them when the tail opens with an explicit citation marker.  CN books
        # keep the legacy behaviour (any Latin-start tail = reference) because
        # their descriptive titles start with Han chars, so a Latin-start in a
        # CN md is almost always a citation / English-term reference.
        if lang == 'en':
            return _is_citation_starter(s)
        return True
    if '一' <= c <= '鿿':
        # Only an EXPLICIT cross-reference marker marks a reference.  A
        # descriptive title may start with any other Han char — including
        # negation '不' ("不完备的赋范空间") or '由' ("由...定义的度量") — so
        # anything that is not a citation word is a REAL entry (uncat), never a
        # silently-dropped reference.  This mirrors the EN branch above.
        if lang != 'en' and c in _CN_CITATION_STARTERS:
            return True
        return False
    return False


# 裸号条头尾部的「难度星号」残留：印面 `3.1.6*` 写成 md 后是 `**3.1.6\***.`，
# 而 _SPAN_RE 的非贪婪闭合会把 `\*` 的星号吞进闭合 `**`，传进 _parse_entry 的
# inner 只剩 `3.1.6\`。判据 = 尾部**只**由空白 / 反斜杠 / 星号组成（即纯难度标记
# 残段），剥掉后才允许参与裸号匹配——其余形态字节不变。
_BARE_STAR_TAIL_RE = re.compile(r'[\\\*\s]+$')


def _bare_head_core(inner):
    """裸号条头的可比内核：剥掉句末点号与尾部的转义难度星号。

    先剥 ``.．。``（既有行为，Vakil 无标题条目 ``3.2.1.`` 靠它），再剥纯星号
    尾巴（Katok 打星习题），最后再剥一次点号——三种尾巴以任何
    顺序混现都能归一。整个字符串本身就是星号/空白时返回空串（裸 ``**\\***``
    不成条目）。
    """
    s = inner.rstrip().rstrip('.．。').strip()
    t = _BARE_STAR_TAIL_RE.search(s)
    if t and t.start() > 0:
        s = s[:t.start()].rstrip().rstrip('.．。').rstrip().strip()
    return s


def _parse_entry(inner, levels, lang=None):
    """Return (comps, label) for a real numbered entry header, else None.

    comps is the list of exactly `levels` integer components (the numbering
    level is driven by cfg.levels, NOT a hardcoded cap).  Handles both
    label-first ('定理 4.1') and number-first ('8.1-6 例') forms, and rejects
    citation spans and references (see _is_header_boundary)."""
    inner = inner.strip()
    if _CITE_RE.match(inner):
        return None
    # 🔴 证明标题守卫（2026-09-09，Han–Lin 实测）：**Proof of Theorem 3.8**
    # 以 "Proof" 开头、不含数字前缀，re_label_first 不中——但下方 m3 回退
    # （label 任意位置搜索）会命中的 "Theorem 3.8"，把该证明标题当成条目 3.8
    # 的**又一次出现**。本书证明排在 Remark 3.12 之后（源书 p63 原版顺序），
    # 于是去重后 8 落到 12 后面 → 假性「顺序错乱」BLOCKING。凡以证明词开头
    # 的 span 都是证明标题而非条目，任何语言一律在此直接拒绝。
    if _PROOF_RE.match(inner):
        # 🔴 例外（Vakil CN 实测，FIX ⑤）：译文中「**证明 11.2.7（定理 11.2.1：…）。**」
        # 是共享计数器里的**真实条目**（印刷的 X 的证明 = 条目 11.2.7），只把证明词
        # 挪到了条头开头。判据 = 证明词（+可选 of/的 连接词）之后**紧跟完整 levels
        # 段自身编号**；「证明 定理 3.8」「Proof of Theorem 3.8」（类型词挡在号前）
        # 与裸「证明。」块头仍一律排除。
        _rest = inner[_PROOF_RE.match(inner).end():].lstrip(' 　')
        # 🔴 FIX ⑤b（Vakil ch20「证明（Hodge 指标定理 20.2.11），步骤 20.2.12。」/
        # EN「Proof (of the Hodge Index Theorem 20.2.11), step 20.2.12.」实测）：
        # 印刷书把多步证明的各步列为共享计数器条目——证明词先跟一个**括号引用**
        # （被证明的定理），再用「步骤 N / step N」给出本条自身号。依次跳过可选
        # 前置介词、括号引用、逗号+「步骤/step」连接词后才匹配自身号；无自身号
        # （裸「证明（定理 X）。」）仍按证明块排除。
        _rest = re.sub(r'^(?:of|的|pour|de)\s+', '', _rest, count=1,
                       flags=re.IGNORECASE)
        _rest = re.sub(r'^[（(][^）)]*[)）]\s*', '', _rest, count=1)
        _rest = re.sub(r'^[，,]?\s*(?:步骤|step\.?)?\s*', '', _rest, count=1,
                       flags=re.IGNORECASE)
        _own_m = re.match(
            (r'^(\d+(?:' + SEP_TIGHT + r'\d+){%d})(?!' + SEP_TIGHT + r'\d)(?!\d)')
            % max(0, int(levels) - 1), _rest)
        if _own_m:
            comps = _comps_of(_own_m.group(1))
            if comps is not None and len(comps) == int(levels):
                return comps, 'uncat'
        return None
    _exact, _cap, re_label_first, re_num_first = _numpath_regexes(levels)
    # Three-level books: a bare numpath with NO trailing text and NO label
    # (e.g. "**1.5-4**") is a real item header whose type is implied — count it
    # as 'uncat'.  This is REQUIRED for combined-numbering uncat counters
    # (Kreyszig §1.5's bare keys) to be visible to the B-layer; otherwise the
    # layer silently drops them and manufactures a false "缺号" (it would see
    # §1.5 = [1,2,3,5,6,7,8,9] and report 缺号 4).  Two-level books keep bare
    # numbers non-entries, because a bare "C.S" is ambiguous (section vs item);
    # the guard `levels == 3` scopes this fallback to three-level books only.
    # Vakil prints UNTITLED items as a bare number header ('**3.2.1.** The set
    # …' → bold span is just '3.2.1.'): the printed trailing period must not
    # defeat the bare-numpath check, or the item vanishes and the B layer
    # reports a false 缺号 for it.
    _bare = _bare_head_core(inner)
    if levels == 3 and _exact.match(_bare):
        comps = _comps_of(_bare)
        if comps is None:
            return None
        return comps, 'uncat'
    m = re_label_first.match(inner)
    if m:
        numpath = m.group(1)
        # 🔴 FIX ⑧b（Vakil 字母习题实测）：「练习 25.2.A」在 lv=2 回退轮被截成
        # [25,2] 灌进「章」级习题窗（节号冒充条目号，制造假「ex:25 缺号 1」）。
        # numpath 之后紧跟 SEP+字母 = 字母序标习题位，本层解析必须整体让位。
        if re.match(r'[' + SEP_TIGHT[1:-1] + r']?[A-Za-z]', inner[m.end():].lstrip()):
            return None
        if not _is_header_boundary(inner[m.end():]):
            return None
        comps = _comps_of(numpath)
        if comps is None:
            return None
        # MUST use re.IGNORECASE here too: line 68's re_label_first matches
        # UPPERCASE EN headings (LEMMA 11.1. / THEOREM 8.16.) via IGNORECASE,
        # so this label re-extract must agree or it returns None and crashes.
        label = re.match(r'^(?:' + _ENTRY_LABELS + r')', inner, re.IGNORECASE).group(0)
        return comps, label
    m = re_num_first.match(inner)
    if m:
        numpath = m.group(1)
        tail = m.group(2).strip()
        # 证明标题「X.Y-Z 的证明 / Proof.」→ 非定义条头，直接排除。
        # 例外（Vakil 实测）：印刷书把证明本身列为共享计数器条目
        # 「**3.6.19 Proof of the Hilbert Basis Theorem 3.6.17.**」——条头自带
        # 编号且证明标题引用**另一个**编号，这就是真实条目（uncat）；
        # 引用号等于自身号或无引用号（裸「证明」块头）仍按证明块排除。
        if _PROOF_RE.match(tail):
            own = _comps_of(numpath)
            mref = _cap.search(tail)
            if own is not None and mref and _comps_of(mref.group(1)) != own:
                return own, 'uncat'
            # 🔴 FIX ②b（Vakil「12.4.3 Proof of Bertini's Theorem, continued」实测）：
            # 证明词开头但引用的是**有名字、无编号**的定理 → 这是被列进共享计数器
            # 的证明步骤条目（uncat）。仅当去证明词/介词后仍留有**不含数字**的描述
            # 才算条目；「Proof of Theorem 3.8」（浅号引用）与裸「证明」块仍排除。
            if own is not None and not mref:
                _res = tail[_PROOF_RE.match(tail).end():]
                _res = re.sub(r'^(?:of|的|pour|de)\s+', '', _res.strip(),
                              count=1, flags=re.IGNORECASE)
                if _res and len(_res) > 1 and not re.search(r'\d', _res):
                    return own, 'uncat'
            return None
        # 类型词可能在专名之后（「2.5-4 黎斯引理」「5.1-2 巴拿赫不动点定理」）；
        # 在余串里搜索首个类型词当 label，边界检查放到类型词之后。
        lm = re.search(r'(?:' + _ENTRY_LABELS + r')', tail)
        if lm:
            _w = lm.group(0)
            if lm.start() > 0 and _w.strip().lower() in _EXERCISE_LABELS:
                # 🔴 专名内嵌习题词（「6.6.2 扩张问题 (Extension Problem)」）：
                # 不是习题环境标记，降级候选 '~Word'，由窗算术两步法最终裁决。
                comps = _comps_of(numpath)
                if comps is None:
                    return None
                return comps, '~' + _w
            if _after_label_boundary(tail[lm.end():]):
                comps = _comps_of(numpath)
                if comps is None:
                    return None
                return comps, _w
            _after = tail[lm.end():].lstrip()
            # A further number path after the type word ('定理 4.1 的应用') is a
            # cross-reference — the old verdict, unchanged.  BUT this only holds
            # when the type word HEADS the tail: Vakil prints descriptive titles
            # carrying parenthetical cross-refs ('1.2.18 Topological example
            # (cf. Example 1.2.13; ...)') — there the match sits inside a cited
            # span and the header is still a real (uncat) entry; dropping it
            # manufactured a false 缺号 for every such item.
            if not _after or _after[0].isdigit():
                if _label_heads_tail(tail, lm.start()):
                    # 🔴 FIX ⑨（Vakil「9.1.5 定理 9.1.1 证明背后的想法」/「10.2.3 推论 1。」
                    # /「23.3.3 练习 23.3.C 的提示」实测）：类型词居余串开头、其后紧跟编号
                    # ——旧判据一律按交叉引用丢弃，但印刷书常以「被引用条目」为题命名自己
                    # 的条目（证明梗概 / 提示 / 后续 / 应用），这类条头自带完整段自身号，是
                    # 真实 uncat 条目。判据：类型词后的编号若构成**完整 levels 段引用**
                    # （数字满 levels 段，或 levels-1 段数字 + 字母习题位）且 ≠ 自身号 → 条目；
                    # 引用号 == 自身号 → 回指证明块（None）。**浅号**（段数不足）只有在其后
                    # 无任何描述文字时（裸「推论 1」题名）才算条目，否则维持「定理 4.1 的应用」
                    # 式交叉引用 → None。负向锁死见 test_b_layer_descriptive_header。
                    own = _comps_of(numpath)
                    if own is None:
                        return None
                    refm = re.match(
                        r'\d+(?:' + SEP_TIGHT + r'\d+)*(?:' + SEP_TIGHT + r'[A-Za-z])?',
                        _after)
                    if refm:
                        tok = refm.group(0)
                        num_tok = re.match(
                            r'\d+(?:' + SEP_TIGHT + r'\d+)*', tok).group(0)
                        cited = _comps_of(num_tok)
                        nc = len(cited) if cited else 0
                        has_letter = bool(re.search(SEP_TIGHT + r'[A-Za-z]$', tok))
                        is_full = ((nc == int(levels))
                                   or (has_letter and nc == int(levels) - 1))
                        if is_full:
                            if cited == own:
                                return None
                            return own, 'uncat'
                        rest2 = _after[refm.end():].strip().strip(
                            '。.．，,；;）)（( *')
                        if not rest2:
                            return own, 'uncat'
                        return None
            if _label_heads_tail(tail, lm.start()) and not _han_glued_word(tail[lm.end():]):
                # The type word opens the title and runs straight on into its own
                # name: '4. Examples of Categories from Chapter I' (EN), or
                # '3. 注记 与例子'-style spacing.  Real header, real label.
                comps = _comps_of(numpath)
                if comps is None:
                    return None
                return comps, _w
            # 🔴 The type word is only QUOTED inside a descriptive title — either
            # mid-title ('2. About Notations', '9. More Examples of Functors') or
            # as the stem of a compound ('7. 系数系统 …', '9. 注记与例子', where '系'
            # would otherwise be read as 系/Porism).  It is still the item's own
            # header: fall through to the label-free descriptive branch below,
            # which re-applies _is_reference_tail (so citations stay dropped).
            # Dropping it instead manufactured 缺号 for every such item (Gelfand–
            # Manin ch1 §1.4: 7/9/10 present in the md, absent from the window).
        # 无标准类型词：描述性标题（「4.11-2 必要条件」）→ 归 uncat，
        # combined 下并入节序列一起计连续性（仍是真实条目，不应漏计）。
        if tail and not _is_reference_tail(tail, lang):
            comps = _comps_of(numpath)
            if comps is None:
                return None
            return comps, 'uncat'
        return None
    # Fallback: number-first with a header-boundary open paren directly after
    # the numpath and no explicit label word (e.g. "2.6-1（线性算子）").
    # Require the paren content not to be a citation so references like
    # "2.6-1（见定理）" are still rejected.
    paren_re = re.compile(r'^' + _cap.pattern + r'\s*[（(]')
    m2 = paren_re.match(inner)
    if m2:
        numpath = m2.group(1)
        tail = inner[m2.end():].strip()
        if tail and not _is_reference_tail(tail, lang):
            comps = _comps_of(numpath)
            if comps is None:
                return None
            return comps, 'uncat'
    # Fallback: label preceded by a name/attribution (e.g.
    # "黎斯 (Riesz) 引理2.5-4（Riesz's lemma）").  Search for LABEL numpath
    # anywhere in the span; the header-boundary check after numpath rejects
    # prose references that happen to contain a label-number pair.
    # 🔴 FIX ⑦（Vakil lv 回退误捡实测）：span 以**比 levels 更深**的自身编号开头
    # （如 2 级回退时面对「18.3.2 定理 18.1.3 的证明」）——该 label+numpath 只可能
    # 是条头内引用的交叉参照，归因搜索回退（m3）不得把它复活成条目。
    if re.match(r'^\d+(?:' + SEP_TIGHT + r'\d+){%d,}' % max(1, int(levels)), inner):
        return None
    m3 = re.search(r'(?:' + _ENTRY_LABELS + r')\s*' + _cap.pattern, inner)
    if m3:
        # 🔴 The label+numpath must not sit INSIDE a parenthetical opened in the
        # span: Vakil prints exercise headers like 'Exercise 9.5.H (promised in
        # Remark 3.6.13)' — 'Remark 3.6.13' is a quoted cross-ref, and counting
        # it manufactured phantom 3.6 items in ch9's window (假「缺号 4..12」+
        # 「顺序错乱」).  Attribution parens before the label ('黎斯 (Riesz) 引理
        # 2.5-4') are balanced, so this keeps the documented m3 purpose intact.
        _depth = 0
        for _ch in inner[:m3.start()]:
            if _ch in '(（':
                _depth += 1
            elif _ch in ')）':
                _depth -= 1
        if _depth > 0:
            return None
        numpath = m3.group(1)
        if _is_header_boundary(inner[m3.end():]):
            comps = _comps_of(numpath)
            if comps is None:
                return None
            label = re.match(r'^(?:' + _ENTRY_LABELS + r')', inner[m3.start():], re.IGNORECASE).group(0)
            # 🔴 专名内嵌的 exercise/Problem 词不是习题环境标记（Weibel 条目
            # 「Extension Problem 6.6.2」被误路由进习题窗 → 条目窗假「缺号 2」）。
            # 仅当类型词在条头开头（re_label_first 路径）才直接开习题窗；
            # 非开头时降级为候选 '~Word'，由窗算术两步法裁决归属窗。
            if m3.start() > 0 and label.strip().lower() in _EXERCISE_LABELS:
                label = '~' + label
            return comps, label
    return None


def _norm_entry_label(label):
    """归一条头类型词。专名内嵌习题词被 _parse_entry 降级为 '~Word' 形态，
    此处统一还原为内容标签 'uncat' 并回传原习题词，供两步法窗算术裁决。"""
    if label and label.startswith('~'):
        return 'uncat', label[1:]
    return label, None


# 🔴 带撇条目号（Serre《Linear Representations of Finite Groups》2026-09-29 实测
# ch18 p.152：Theorem 42 之后印 **Theorem 35'**，ch11 甚至排到 Theorem 23'''）：
# 撇号项是原书对**已陈述定理的重述/加强**，按定义不占主计数器席位，所以它合法地
# 出现在更大编号之后。`_parse_entry` 会把撇号剥掉 → 35' 解析成 35 落进同一阅读
# 序列 [42, 42, 35, 43] → 假「顺序错乱」BLOCKING（本书 ch10/11/18 共 8 处）。
# 判据 = 条头**自身编号**之后紧跟撇号（' ’ ′ ` ´，可裹在 $…$ 里）且撇号不接单词
# （`Definition 7 'the norm'` 这种引号式标题不是撇号项）。这类条目**不进阅读顺序
# 窗**（section_order），但照常计入 groups/present_md，故它所重述的号与自身都不
# 会被误报缺号——只豁免「顺序」这一项，不豁免「存在」这一项。
_OWN_NUM_RUN_RE = re.compile(r'\d+(?:' + SEP_TIGHT + r'\d+)*')
_PRIME_GLYPHS = "'’′`´"
_PRIME_AFTER_NUM_RE = re.compile(
    r'^\s?\$?[' + _PRIME_GLYPHS + r']{1,3}(?![A-Za-z0-9\u4e00-\u9fff])')


def _own_number_primed(inner):
    """条头自身编号后是否紧跟撇号（'Theorem 35'' / '35' 定理'）。

    只取 `inner` 里**第一个**编号段——条头总是以「类型词+自身号」或「自身号+…」
    开头，其后的编号才可能是交叉引用（'Theorem 5 (cf. 3'' )' 的自身号是 5）。
    """
    m = _OWN_NUM_RUN_RE.search(inner or '')
    if not m:
        return False
    return bool(_PRIME_AFTER_NUM_RE.match(inner[m.end():]))


def _resolve_demoted_entries(entries, demoted):
    """两步法窗算术：专名内嵌习题词的条头（'~Exercise'/'~Problem'/ '~问题'）先
    按内容窗登记（entries 里 label 即 '~Word'）；随后，仅当其目标习题窗已存在
    且窗内恰缺该号时，才把该条改路由回习题窗。

    Weibel 实测双向案例：ch6「Extension Problem 6.6.2」是内容条目（习题窗 6.6
    的 2 号已有真习题头 → 不回补，留在内容窗）；ch10「Topology Exercise 10.9.2」
    是真习题（习题窗 10.9 缺 2 号且 10.9.2 内容另有其头 → 回补）。"""
    ex_present = {}
    for _e in entries:
        gk, num = _e[0], _e[1]
        if 'ex' in gk.split(':'):
            ex_present.setdefault(gk, set()).add(num)
    for idx, gi, prefix_str, item_num in demoted:
        ex_gk = f"{gi}:ex:{prefix_str}"
        have = ex_present.get(ex_gk)
        if have is not None and item_num not in have:
            entries[idx] = (ex_gk,) + tuple(entries[idx][1:])
            have.add(item_num)
    return entries


def _merge_orphan_ex_windows(entries):
    """窗算术第二步：把「其实属于条目计数器」的 problem 窗并回主窗。

    label 强制路由（`problem`/`exercise` 一律进 `:ex:` 窗）对这一类书是错的：
    书中 Problem 与 Theorem/Lemma **共用同一条章内计数器**——Iwaniec–Kowalski
    ch7 印 Theorem 7.18 → **Problem 7.19** → Theorem 7.20（序标同形、同序、
    7.1..7.35 一条序列；Etingof ch1 同形态，只是那本书恰好开了
    `exercise_shared_numbering` 才没暴露）。后果是**双向**假 BLOCKING：主窗把
    19/25/29 报成「缺号」，`:ex:` 窗把 1..18、20..28 报成「缺号」，ch7 一次 29 条。

    判据（机械可验，只在「并回去正好把主窗补平」时触发，宁漏不误并）：
      ① 独立习题计数器一定从 1 起号 → 窗内最小号 > 1 才可疑；
      ② 窗内每个号都必须是主窗在 [min,max] 区间里的**洞**；
      ③ 并入后主窗在该区间连续无洞。
    Katok / Lee / Weibel 的按节重排窗 min=1 或 body 非数字前缀，天然不触发。
    """
    main_nums = {}
    ex_nums = {}
    for _e in entries:
        gk, num = _e[0], _e[1]
        if 'ex' in gk.split(':'):
            ex_nums.setdefault(gk, set()).add(num)
        else:
            main_nums.setdefault(gk, set()).add(num)
    for ex_gk in sorted(ex_nums):
        parts = ex_gk.split(':')
        if len(parts) != 3:
            continue                      # 只处理 "{gi}:ex:{数字前缀}" 窗
        gi, _ex, body = parts
        if not re.fullmatch(r'\d+(?:\.\d+)*', body):
            continue                      # file / file:label 窗不参与
        main_gk = f"{gi}:{body}"
        M = main_nums.get(main_gk)
        nums = ex_nums[ex_gk]
        if not M or min(nums) <= 1:
            continue
        E = {n for n in nums if n not in M}
        if not E:
            continue
        lo, hi = min(M), max(M)
        holes = set(range(lo, hi + 1)) - M
        if not E <= holes or (set(range(lo, hi + 1)) - (M | E)):
            continue                      # 并不平主窗 → 维持原路由
        for i, _e in enumerate(entries):
            if _e[0] == ex_gk and _e[1] in E:
                entries[i] = (main_gk,) + tuple(_e[1:])
        M |= E
    return entries


def _source_item_comps_label(it, cfg):
    """Map an extraction item (ctx.items, the source contract) to
    (comps, label, group) using the SAME wildcard separator and the item's
    OWN group depth (from cfg.group_for_label) — so source + md groups align
    1:1 for the tail check regardless of which group the item belongs to.

    `levels` is replaced by `cfg` so each item is parsed at its group's depth
    (a two-level 练习 item is parsed at depth 2, a three-level 定理 at depth 3).
    * EN / two-level normalized keys carry the label inline ('定理1.1' /
      'Definition 1.1') -> label-first parse.
    * three-level keys are bare numpaths ('4.1-5') with the category in the
      separate `label` field -> use it['label'].
    * keys whose chapter slot is not an integer only（如字母章位 'A.1-1'）cannot
      be split by the integer-only _SEP -> return None (tail check gracefully
      skips those).
    """
    if not isinstance(it, dict):
        return None
    key = (it.get('key') or '').strip()
    if not key:
        return None
    lab = it.get('label')
    g = cfg.group_for_label(lab) if lab and lab != 'uncat' else cfg.uncat_group()
    _exact, _cap, re_label_first, _nf = _numpath_regexes(g.depth)
    m = re_label_first.match(key)
    if m:
        comps = _comps_of(m.group(1))
        if comps is not None:
            label = re.match(r'^(?:' + _ENTRY_LABELS + r')', key).group(0)
            return comps, label, g
    comps = _split_numpath(key, g.depth)
    if comps is not None and lab and lab != 'uncat':
        return comps, lab, g
    return None


def _md_tail_blocking(ctx, cfg, groups):
    """B-LAYER 尾部校验（阻断）.

    对每个 md 编号组，取 .md 内最大号 `last`；再在提取契约（源, ctx.items）中
    按同一分组方案（levels/scope/separate_types）找该组最大号 `smax`。若
    `smax > last` 且中间号源有而 md 无 -> 疑似尾部漏项，报 blocking。

    agent 核实后确认该节确实到此为止，可在 ignore_ch{N}.json 中登记
    ``"TAIL:{gk}"``（如 ``"TAIL:0:1.7"``）标记尾部已检查通过，suppress 该组
    所有尾部阻断。

    OCR 幻影可能抬高 smax，故差距过大(>_TAIL_GAP_CAP)时只给一条汇总提示而非
    逐号轰炸；已知稀疏号(known_gaps)/已忽略键(ignore_keys)跳过。
    """
    items = ctx.items
    if not items:
        return []
    known = ctx.ignore
    ignore = ctx.ignore

    # source max per (group_index, prefix_tuple) — keyed by GROUP, not label,
    # so a merged (combined) counter aligns correctly regardless of item label.
    src_max = {}
    for it in items:
        cl = _source_item_comps_label(it, cfg)
        if not cl:
            continue
        comps, label, g = cl
        if not comps:
            continue
        gpl = g.group_prefix_len()
        gpl_e = min(gpl, len(comps) - 1)
        prefix = tuple(comps[:gpl_e])
        num = comps[gpl_e] if gpl_e < len(comps) else 0
        if num <= 0:
            continue
        gi = cfg.ordinal.index(g)
        key = (gi, prefix)
        if num > src_max.get(key, 0):
            src_max[key] = num

    blocking = []
    for gk, pairs in sorted(groups.items()):
        # 🔴 练习/问题独立窗（ex:）不做 TAIL 比对：源侧 ctx.items 的分组尚未按
        # ex 窗拆分（源侧练习与条目同 (gi,prefix) 混窗，smax 被条目号抬高——
        # Katok §1.1 实测 源最大 6 vs md 3）。ex 窗仅做顺序/缺号校验，TAIL 交由
        # 人工或后续源侧分组适配。
        if ':ex:' in gk:
            continue
        # `gk` is "{gi}:<body>" where <body> is the numeric prefix string,
        # "file" (uncat), or "file:<label>".
        body = gk.split(':', 1)[1] if ':' in gk else gk
        if body == 'file':
            prefix_str, label = '', 'uncat'
        elif body.startswith('file:'):
            prefix_str, label = '', body[len('file:'):]
        elif body.startswith('ex:'):
            # 🔴 练习/问题独立编号窗（见 entries 构建处 Katok 注记）
            prefix_str, label = body[len('ex:'):], 'exercise'
        else:
            prefix_str, label = body, 'uncat'
        last = max(n for n, _ in pairs)
        try:
            prefix = tuple(int(x) for x in prefix_str.split('.')) if prefix_str else ()
        except ValueError:
            # Non-numeric section anchor (e.g. unnumbered `## § Appendix: ...`
            # heading used as a scope-3 window id): no numeric source-side
            # counterpart exists, so tail comparison is meaningless — skip.
            continue
        gi = int(gk.split(':', 1)[0]) if ':' in gk else 0
        smax = src_max.get((gi, prefix), 0)
        if smax <= last:
            continue
        # TAIL:{gk} in ignore -> agent verified section ends here, suppress all
        if f"TAIL:{gk}" in ignore or f"TAIL:{gk}" in known:
            continue
        gap = smax - last
        if gap > _TAIL_GAP_CAP:
            blocking.append(
                f"  WARN (BLOCKING): TAIL {gk}: 源最大 {smax} 远大于 md 最大 {last}（差距 {gap}）"
                f"— 疑似 OCR 幻影或异源编号，请核实该组是否即止；"
                f"确认无误请登记 \"TAIL:{gk}\" 到 ignore_ch{{N}}.json / ignore_appendix{{X}}.json")
            continue
        for n in range(last + 1, smax + 1):
            full = (prefix_str + '-' if prefix_str else '') + str(n)
            token = f"{label} {full}" if label and label != 'uncat' else full
            token_norm = f"{_norm_label(label)} {full}" if label and label != 'uncat' else full
            if (token in known or token_norm in known
                    or f"{gk}:{n}" in known or f"{gk}:{n}" in ignore):
                continue
            blocking.append(
                f"  WARN (BLOCKING): TAIL {gk} 缺尾部号 {n}（md 最大 {last}，源最大 {smax} — "
                f"请核实章/节是否即止；确认无误请登记 \"TAIL:{gk}\" 到 ignore_ch{{N}}.json / ignore_appendix{{X}}.json）")
    return blocking


def _ignored_num(gk, prefix_str, n, label_candidates, known, ignore):
    """True if item number `n` in group `gk` is a confirmed ignore / known_gap
    entry (same token logic as the gap-emit check, so a single --ignore entry
    suppresses both 缺号 and 顺序错乱 for a confirmed book-order anomaly)."""
    full = (prefix_str + '-' if prefix_str else '') + str(n)
    for lab in label_candidates:
        token = f"{lab} {full}" if lab and lab != 'uncat' else full
        token_norm = f"{_norm_label(lab)} {full}" if lab and lab != 'uncat' else full
        if (_norm_sep(token) in known or _norm_sep(token_norm) in known
                or _norm_sep(f"{gk}:{n}") in known
                or f"{gk}:{n}" in ignore
                or _norm_sep(full) in known or full in ignore):
            return True
    return False


# ------------------------------------------------------------------ grouping
# Grouping is driven by the BookConfig.ordinal GroupConfig array (see
# config.GroupConfig).  Each entry's label is mapped to its group via
# cfg.group_for_label(); the group index namespaces the counter key so
# different groups NEVER merge.  The old `separate_types` (SEP_COMBINED /
# SEP_PER_TYPE) switch is gone.





def _section_anchors(txt):
    """扫描 md 的 `##..#### §` 标题，返回 (offsets, anchors) 平行列表。

    Section anchors for prefix-less entries: single-level books (ordinal
    type 1, e.g. do Carmo "Example 4") print NO numeric prefix on items and
    reset their counters PER SECTION (scope==3).  A whole-file window would
    fabricate false 缺号/顺序错乱 (§2-2 Example 6 followed by §2-3 Example 1
    looks like a restart).  When the md carries `## §` headings, use the
    current section as the true window prefix for prefix-less entries of
    scope-3 groups; entries carrying a numeric prefix and non-section-scoped
    groups are untouched (zero regression).  The anchor id is the first token
    after § (numbered "2-2" / appendix-style "2-A" / descriptive word for
    unnumbered sections) so every distinct `## §` heading resets the window.
    🔴 锚点层级感知：裸字母子块标题 `### §A` **继承父节窗口**（不另开一窗）。
    印刷体例里节内计数器横跨 A./B./C. 子块连续编号（Arnold《经典力学的数学方法》
    §32 的 问题1..15 分布在五个字母块中），旧逻辑把 "32.D" 当独立窗口就把连续序列
    切开、假报「缺号 1..3」（字母材料化后 ch7 一次 65 条 blocking，2026-09-29 实测）。
    旧逻辑想防的「不同节下同名字母块并窗」（§24.B 的定理3、4 与 §25.B 的定理1 混成
    seq=[3,4,1]）由父节锚天然区分（"24" vs "25"）。父节未知时仍退化为裸字母锚。
    数字型深层子标题（谷超豪 "### §2"）与节内子小节头（Rosen "### §1.1.3"）行为不变。
    """
    _sec_pos = []   # sorted heading start offsets
    _sec_str = []   # parallel section ids
    _cur_num = None  # 最近一个两级（数字）节的 token，供字母子块拼路径
    for _m in re.finditer(r'^(#{2,4})[ \t]*§[ \t]*([^\n]*)$', txt, re.M):
        _toks = (_m.group(2) or '').strip().split()
        if not _toks:
            continue
        _tok = _toks[0].strip(':.，,；;')[:24]
        if _cur_num and _tok.startswith(_cur_num + '.'):
            # 🔴 标题包含性（Rosen《Discrete Mathematics》8e 实测 2026-09-25）：
            # token "1.1.3" 以当前节号 "1.1" 为前缀 → 这是**节内印刷子小节头**
            # （type1/scope3 书计数器在 §1.1 级重置、不在 1.1.x 级重起），
            # 例10..13 挂在 "## §1.1.3" 下若另开窗口会假报「缺号 1..9」（ch1
            # 实测 141 条 blocking 全由此出）。不注册锚点，父节窗口继续有效。
            # Gu 超豪式「### §2」（token 不以父节号开头）不受影响——它是真重启边界。
            continue
        if _cur_num and re.match(r'^[A-Z]$', _tok):
            # 🔴 字母子块不是计数器窗口边界（Arnold《经典力学的数学方法》ch7 实测
            # 2026-09-29）：印刷体例里 §32 的 问题1..15 横跨 A./B./C./D./E. 五个字母
            # 子块连续编号，把 "32.D" 当独立窗口就切成 4..8 / 9..15 两段，各段都被判
            # 「缺号 1..3」——字母材料化后一章一次假报 65 条 blocking。
            # 旧的「24.A / 25.B」分窗只为了防**跨节**并窗（裸字母 "B" 把 §24.B 与
            # §25.B 混成 seq=[3,4,1]），继承父节锚同样达到该目的（窗 = "24" vs "25"），
            # 且不再切开节内连续计数器。父节未知时（_cur_num 为空）维持旧行为。
            continue
        if len(_m.group(1)) == 2:
            # 🔴 无父节的字母块同样**不是**窗口边界（Arnold《经典力学的数学方法》
            # 附录B 实测 2026-09-29）：附录把字母块升到 `## §A`，而全篇只有**一条**
            # 定理计数器（定理1..6 印在块 D、7..10 在块 F、11..12 在 H、13 在 J、
            # 14..15 在 K），逐字母开窗就把连续序列切开 → 假「1:F 缺号 1..6」
            # （BLOCKING，整章卡死）。不注册锚点 = 整篇共用一个窗（`gi:file`），
            # 与上面「字母子块继承父节」同源；真按字母重启计数的书其条头自带
            # 前缀（`Theorem A.1`）走 prefix_str 分支，本判据碰不到。
            if _cur_num is None and re.match(r'^[A-Z]$', _tok):
                continue
            # 两级节（或任何非单大写字母 token 的标题）：锚 = 自身 token
            _anchor = _tok
            if re.match(r'^\d', _tok):
                _cur_num = _tok
        elif not re.match(r'^[A-Z]$', _tok):
            # 深层（###/####）非单字母 token。数字 token 是「节内计数器重起」
            # 分窗标记（write-source 在印刷小节头/计数器重起处输出 "### §2"；
            # 谷超豪《数学物理方程》ch6 §4 实测：一节内两套 性质1–4 计数器）：
            # 锚 = 父节 + 子 token（"4-2"），避免跨节同号子块并窗成假乱序。
            if re.match(r'^\d', _tok) and _cur_num:
                _anchor = f"{_cur_num}-{_tok}"
                # 父节游标不变：后续同级 ### 锚继续挂在同一 ## § 下
            else:
                _anchor = _tok
        else:
            # 单大写字母子块且**父节未知**（全书无 `## §<数字>` 头）：退化为裸字母锚，
            # 维持旧注册行为（有父节时上面的分支已把它并回父节窗口）。
            _anchor = _tok
        _sec_pos.append(_m.start())
        _sec_str.append(_anchor)
    return _sec_pos, _sec_str


def _subblock_anchors(txt):
    """(offsets, tokens) for EVERY `^##..#### §` heading, letter sub-blocks included.

    与 `_section_anchors` 的分工：那边是**计数器窗口**边界，字母子块必须继承父节
    （Arnold §32 的 问题1..15 横跨 A./B./C./D./E. 连续编号，切开就假报缺号）；
    本表只服务一件判据——区分「同号二现」究竟是**印面重启/并行计数器交错**还是
    真幻影（正文引用被误建成条目节点）。判据要看得见 `### §C` 这一层，所以这里
    一律注册，不做任何继承/包含性豁免。取不到任何标题时返回空表 → 判据退化为
    「全部同子块」，即维持旧行为（fail-closed，宁误报不漏报）。
    """
    pos, tok = [], []
    for m in re.finditer(r'^(#{2,4})[ \t]*§[ \t]*([^\n]*)$', txt, re.M):
        toks = (m.group(2) or '').strip().split()
        if not toks:
            continue
        pos.append(m.start())
        tok.append(toks[0].strip(':.，,；;')[:24])
    return pos, tok


def _md_gap_blocking(ctx):
    """Return (BLOCKING, WARNING, present_md_keys) for item-number gaps found
    in the written .md, grouped by the per-book numbering convention carried on
    `ctx.config` (built once by the ConfigLoader from
    <book>/_extract/verify_config.json — no ad-hoc file IO here).  The
    separator is a built-in wildcard; numbering level is variable (1/2/3).

    Default is STRICT (no omissions allowed): any discontinuity in a numbering
    group hard-blocks until verified.  Books that legitimately number items
    sparsely (e.g. a chapter with only 'Lemma 2.5') should record the confirmed
    sparse tokens in config `known_gaps` so they are suppressed instead of
    false-FAILing.  `strict: false` downgrades gaps to advisory warnings."""
    cfg = ctx.config
    known = ctx.ignore
    evidenced_ignore = getattr(ctx, 'evidenced_ignore', set())
    if not ctx.md_file:
        return [], [], set(), []
    try:
        txt = open(ctx.md_file, encoding='utf-8').read()
    except Exception:
        return [], [], set(), []

    # Grouping is now driven by the BookConfig.ordinal GroupConfig array.  For
    # each entry we parse its (comps, label) at the MOST SPECIFIC depth that
    # matches (descending over the distinct group depths), then map the label
    # to its group and use THAT group's prefix length.  Parsing at the highest
    # depth first means a three-level "4.1-5" is captured fully even when a
    # two-level 练习 group also declares depth 2.
    #
    # Section anchors for prefix-less entries — see `_section_anchors` above
    # for the full semantics (scope-3 windows / Arnold letter blocks / Rosen
    # containment rule).
    _sec_pos, _sec_str = _section_anchors(txt)

    def _cur_sec(pos):
        import bisect as _bisect
        i = _bisect.bisect_right(_sec_pos, pos) - 1
        return _sec_str[i] if i >= 0 else None

    _sub_pos, _sub_str = _subblock_anchors(txt)

    def _cur_sub(pos):
        import bisect as _bisect
        i = _bisect.bisect_right(_sub_pos, pos) - 1
        return _sub_str[i] if i >= 0 else None

    _depth_candidates = sorted({g.depth for g in cfg.ordinal}, reverse=True)
    entries = []  # (group_key, item_num, unique_key, label, prefix_str, primed, sub_block)
    _demoted = []  # 习题窗两步法候选：(entries 下标, gi, prefix_str, item_num)
    _bare_pending = []  # 裸号习题头候选：(entries 下标, 主窗 gk, key)
    # 🔴 契约习题键（无标签条头的路由真值，判据见 `_contract_exercise_keys`）
    _ex_keys = _contract_exercise_keys(ctx.ext_dir, ctx.ch)
    for span in _SPAN_RE.finditer(txt):
        inner = span.group(1).strip()
        parsed = None
        for lv in _depth_candidates:
            parsed = _parse_entry(inner, lv, ctx.language)
            if parsed:
                break
        if not parsed:
            continue
        comps, label = parsed
        if not comps:
            continue
        label, _demoted_word = _norm_entry_label(label)
        g = cfg.group_for_label(label)
        gi = cfg.ordinal.index(g)
        gpl = g.group_prefix_len()
        # Per-entry cap so a mismatched `levels` can never index out of range.
        gpl_e = min(gpl, len(comps) - 1)
        prefix = tuple(comps[:gpl_e])
        item_num = comps[gpl_e] if gpl_e < len(comps) else 0
        prefix_str = '.'.join(str(c) for c in prefix)
        if prefix_str:
            gk = f"{gi}:{prefix_str}"
        elif g.scope == 3:
            # Section-scoped counters: window by the current `## §` heading
            # (see anchors above); before the first heading keep file window.
            sec_str = _cur_sec(span.start()) if _sec_pos else None
            if sec_str:
                prefix_str = sec_str
                gk = f"{gi}:{prefix_str}"
            elif label and label != 'uncat':
                gk = f"{gi}:file:{label}"
            else:
                gk = f"{gi}:file"
        elif label and label != 'uncat':
            gk = f"{gi}:file:{label}"
        else:
            gk = f"{gi}:file"
        # present_md key uses the dash form ("C.S-N") so the extraction-side
        # OCR-suppression filter (which builds "sec-num") can match it.
        key = f"{prefix_str}-{item_num}" if prefix_str else str(item_num)
        # 🔴 Katok 2026-09-13：练习/问题环境在书中独立于条目计数器按节重排
        # （Exercise 1.1.1 = §1.1 第 1 题，与 Definition 1.1.1 同形不同序），
        # 而 many books 的 config 把 Exercise 与条目词映射进同一 ordinal 组
        # （实测 gi 同为 0）——练习重排的 1 混进条目序列被误判「顺序错乱」
        # （Katok 23 章 md 层 65 处假 BLOCKING）。练习/问题强制独立编号窗：
        # gk 中段插 'ex'（body 解析处识别；组 id 数值不变，cfg.ordinal[gi]
        # 回读不受影响），练习缺号/顺序校验在独立窗内进行。
        _lab = (label or '').strip().lower().rstrip('*')
        # exercise_shared_numbering（Lee 体例）：练习与定理/例共用章内同一条
        # 1..N 序列，此处不得为 exercise 另开窗，否则定理号全被报成「练习缺号」。
        # Problem 无论何种模式都独立开窗——它用 N-M 编号（Lee 章末 Problems
        # 印作 "1-1."），与条目的 N.M 不同形，并入会与 Theorem 1.1 撞号。
        # 🔴 '练习' 是 CN 译版对 Exercise 的常用标签（Weibel 2026-09 实战：漏它
        # 则 CN 侧 练习X.Y.n 落进条目窗造成「同号二现」WARN 一片）。
        _shared = bool(getattr(cfg, 'exercise_shared_numbering', False))
        # 🔴 Vakil（type8 uncat 合并计数器）实测：全书只有一条 C.S.X 共享序列，
        # 练习/问题/习题条头（「20.1.7 练习」「12.1.3 问题」）本身就是该序列的
        # 成员，绝不能另开 ex 窗——否则主窗报假「缺号」。判据 = 该 label 解析到
        # 的组就是 uncat 合并组（g.is_uncat）。真·独立习题计数器（Weibel/Lee 的
        # 具名 Exercise 组，is_uncat False）不受影响，仍照常开窗。
        _combined = bool(getattr(g, 'is_uncat', False))
        # 🔴 共享计数器的书里 **Problem 也可能是同一条序列的成员**（Etingof《群表示论》
        # 2026-09-27 实测）：该书章内只有一条 1..N 计数器，习题印作 "Problem 1.20"
        # （紧接 Definition 1.19 续号、与条目同形）。只按 label 把 Problem 塞进
        # `:ex:` 窗会造成双向假缺号——主窗把练习号当缺号、练习窗把条目号当缺号
        # （ch1 一次 58 条假 BLOCKING）。判据取**序标形态**：点号多段（1.20）=
        # 与条目同形 → 留在主窗；Lee 式 "Problem 1-1"（短横、章末独立题号）
        # 仍照常开窗，不与 Theorem 1.1 撞号。
        _stays_main = _shared and (
            _lab in ('exercise', 'exercse', '习题', '练习')
            or (_lab in ('problem', 'problems', '问题')
                and re.search(r'\d+\.\d+', inner) is not None))
        _routed_ex, _bare_ex = _exercise_window_routing(
            _lab, prefix_str, key, _ex_keys,
            combined=_combined, shared=_shared, stays_main=_stays_main,
            demoted_word=bool(_demoted_word))
        if _bare_ex:
            # 裸号习题头：先按主窗登记，窗算术之后再按「同号二现」碰撞决定去留
            _bare_pending.append((len(entries), gk, key))
        elif _routed_ex:
            if ':' in gk:
                _gh, _gb = gk.split(':', 1)
                gk = f"{_gh}:ex:{_gb}"
            else:
                gk = f"{gk}:ex"
        if _demoted_word and prefix_str and not _routed_ex:
            # 习题词内嵌于专名（'~Word'）：暂存候选，窗算术两步法稍后裁决。
            _dw_norm = _norm_label(_demoted_word)
            _dgi = cfg.ordinal.index(cfg.group_for_label(_dw_norm))
            _demoted.append((len(entries), _dgi, prefix_str, item_num))
        entries.append((gk, item_num, key, label, prefix_str,
                        _own_number_primed(inner), _cur_sub(span.start())))

    _resolve_bare_ex_candidates(entries, _bare_pending)
    _resolve_demoted_entries(entries, _demoted)
    _merge_orphan_ex_windows(entries)

    groups = defaultdict(list)
    # 🔴 顺序错乱检测必须按 (prefix, type) 分组，不能仅按 prefix_str 混排所有类型。
    # 许多书（如 Koopman Ch1）每个条目环境在章内独立编号（Definition 1.1 /
    # Proposition 1.1 / Example 1.1 / Remark 1.1 同为 ".1"），类型重置导致 "1"
    # 出现在更大编号之后——这是合法重置，非错位。仅按 prefix_str 混排会把这种
    # 合法重置误判为 BLOCKING 顺序错乱。gk 已编码类型(group index)，与「缺号」
    # 检查保持一致地按 gk 分组即可正确按类型隔离顺序校验。
    section_order = defaultdict(list)   # gk -> [item_num,...] 阅读顺序（按类型隔离，用于顺序错乱检测）
    # 与 section_order **同序平行**的出现明细 (num, label, sub_block)，专供
    # 「幽灵重复」判据把同号二现归到「同标签 + 同子块」——见下方 WARN 分支。
    section_order_meta = defaultdict(list)
    present_md = set()
    for gk, num, key, label, prefix_str, primed, sub in entries:
        # Group by `gk` ONLY.  `gk` already encodes the separation decision:
        # per-type mode embeds the label ("C.S:LABEL"), combined mode does not
        # ("C.S").  Re-adding `label` here would split a combined section into
        # per-type sub-sequences -> false "缺号" (the original bug).
        groups[gk].append((num, key))
        present_md.add(key)
        # 阅读顺序记录（无论 per-type/combined，同一节前缀 §C.S 的编号按出现先后入列，
        # 用于跨类型顺序错乱检测：例如 2.6-8 这种 Example 掉到 2.6-11 这种 Lemma 之后）。
        # 🔴 撇号重述项（Theorem 35'）不占主计数器席位，不入阅读顺序窗，否则
        # 「35 出现在 42 之后」的合法印面会被误判 BLOCKING 错位（见上 _PRIME 注释）。
        if not primed:
            section_order[gk].append(num)
            section_order_meta[gk].append((num, label, sub))

    # --- route-A: .md 自身引用的 Table/Figure 编号，序列查缺时跳过 -------------
    # Fraleigh 把表/图编入连续章节序号，但 .md 把它们写成正文（如 "Table 1.20
    # defines..."）或加粗条头（**Figure 39.2**），并非定理/例类加粗条目。合并
    # 序列查缺会把表/图号误判为缺失条目。此处直接扫描 .md 文本，凡显式出现
    # "Table/Figure CH.N"（含复数/大小写）的编号，emit 时跳过——它们不是真实缺项。
    # 不依赖（可能不完整的）结构契约，纯从 .md 自身引用判定，书确实编号的
    # 定理/例等不受影响。
    md_uncat = set()
    # 匹配 "Table/Figure CH.N" 及其列表形式（"Tables 32.7 and 32.8" /
    # "Figures 3.9, 3.10" 等），整段内提取所有 CH.N 编号一并排除。
    # 缩写 "Fig." / "Fig" / "Figs." 一并纳入（Fraleigh 正文用 "Fig. 47.4"）。
    for m in re.finditer(
            r'(?i)(?:tables?|figs?\.?|figures?)\s*\d+\.\d+'
            r'(?:(?:\s*(?:,|and|&|，)\s*)\d+\.\d+)*', txt):
        for nm in re.finditer(r'(\d+)\.(\d+)', m.group(0)):
            try:
                md_uncat.add(((int(nm.group(1)),), int(nm.group(2))))
            except ValueError:
                pass

    ignore = ctx.ignore
    # Normalize known_gaps separators (dot <-> dash) so user-written dot form
    # matches the dash-form emit tokens.
    known = {_norm_sep(x) for x in ctx.ignore}
    blocking, warnings = [], []

    for gk, pairs in sorted(groups.items()):
        # `gk` is "{gi}:<body>" where <body> is the numeric prefix string,
        # "file" (prefix-less, uncat label), or "file:<label>" (prefix-less,
        # labelled).  The group index `gi` namespaces counters so different
        # groups never merge.
        body = gk.split(':', 1)[1] if ':' in gk else gk
        if body == 'file':
            prefix_str, label = '', 'uncat'
        elif body.startswith('file:'):
            prefix_str, label = '', body[len('file:'):]
        elif body.startswith('ex:'):
            # 🔴 练习/问题独立编号窗（见 entries 构建处 Katok 注记）
            prefix_str, label = body[len('ex:'):], 'exercise'
        else:
            prefix_str, label = body, 'uncat'
        # Recover the human-readable label(s) carried by this group so the emit
        # token matches `ignore` / `known_gaps` entries written as e.g.
        # "Theorem 12.3".  v2 groups by `gi:prefix` (the group index `gi`
        # encodes the label via group_for_label), so the label is NOT part of
        # the grouping key and must be re-derived here.  Without this, per-type
        # groups emit a bare "12-3" token that never matches a "Theorem 12.3"
        # ignore entry -> confirmed-sparse numbers false-BLOCK (regression vs
        # the old label-bearing token from separate_types:1 mode).
        label_candidates = [label]
        try:
            gi = int(gk.split(':', 1)[0])
            g = cfg.ordinal[gi]
            if not g.is_uncat:
                label_candidates = list(g.name)
        except (ValueError, IndexError):
            pass
        nums = sorted(n for n, _ in pairs)
        present = {n for n, _ in pairs}
        first, last = nums[0], nums[-1]
        size = len(nums)

        def emit(n):
            # route-A: .md 自身以 "Table/Figure CH.N" 引用的编号（Fraleigh 编入
            # 连续序号但写成正文/加粗条头）不是缺失条目，直接跳过，不报缺号。
            if prefix_str:
                try:
                    pref_tuple = tuple(int(x) for x in prefix_str.split('.'))
                except ValueError:
                    pref_tuple = None
            else:
                pref_tuple = ()
            if pref_tuple is not None and (pref_tuple, n) in md_uncat:
                return
            # Human-readable token used for known_gaps / ignore matching, e.g.
            # "Theorem 12.3".  Both the raw token (original label language) and
            # the EN-normalized token are accepted, so a known_gaps entry
            # written in English also suppresses its Chinese counterpart.  For
            # per-type groups the label is re-derived from the group index
            # (label_candidates) so an ignore entry "Theorem 12.3" matches the
            # emitted token even though the grouping key only carries `gi`.
            full = (prefix_str + '-' if prefix_str else '') + str(n)
            matched = False
            matched_token = None
            for lab in label_candidates:
                token = f"{lab} {full}" if lab and lab != 'uncat' else full
                token_norm = f"{_norm_label(lab)} {full}" if lab and lab != 'uncat' else full
                for cand in (token, token_norm, f"{gk}:{n}", full):
                    if _norm_sep(cand) in known or cand in ignore:
                        matched = True
                        matched_token = cand
                        break
                if matched:
                    break
            if matched:
                # 审核护栏：ignore 只应抑制「.md 中真实存在」的条头，不得掩盖
                # 「源侧序列洞」（被忽略的编号在 .md 中本就不存在）。
                # 但若该 ignore 已附 VERIFIED-SPARSE 证据（agent 已核对源书，确认是
                # 共享计数器 / 作者稀疏编号，非真实缺项），则与 audit_ignore.py 的
                # ACCEPTED 判定保持一致 → 不再重复告警；未附证据者仍照常告警，护栏不弱化。
                if n not in present:
                    if (evidenced_ignore
                            and (matched_token in evidenced_ignore
                                 or _norm_sep(matched_token) in evidenced_ignore)):
                        return
                    warnings.append(
                        f"  [IGNORE-SUSPECT] {gk} 缺号 {n}（序列 {first}..{last}）："
                        f"ignore 条目掩盖了一个源侧序列洞（{full} 在 .md 中并不存在），"
                        f"疑似隐藏真实缺项。请核对源书：若确为稀疏编号请在 ignore 注明举证；"
                        f"若 .md 本应含 {full} 请用 manual_overrides 补回，勿用 ignore 隐藏。")
                return
            msg = (f"{gk} 缺号 {n}（序列 {first}..{last} 不连续 — "
                   f"严格模式：请核对源书确认是稀疏编号(登记 ignore)还是确有遗漏(应补写)）")
            if cfg.strict:
                blocking.append("  WARN (BLOCKING): " + msg)
            else:
                warnings.append(msg)

        # 中间缺号（序列内部的洞）：最可疑，总是提示
        for n in range(first + 1, last):
            if n not in present:
                emit(n)
        # 首项缺失（first>1）：仅当序列较长(>=3)时提示，避免单发条目的噪声
        if first > 1 and size >= 3:
            for n in range(1, first):
                if n not in present:
                    emit(n)

    # --- 顺序校验 (ORDERING, 始终 BLOCKING) ---
    # 同「节前缀(prefix_str)」内，阅读顺序中的编号必须单调不减；若某编号出现在
    # 更大编号之后（如 §2.6 阅读顺序 …7,9,10,11,8），即为「编号错位」（8 号掉到
    # 后面），属确定性错误：只依赖 markdown 自身编号序列，与契约 page_start 无关
    # （即使契约被习题/交叉引用污染也会命中，因为只比对 .md 自身的编号顺序）。
    # 此类"靠后的号跑到前面之后"必须硬阻断、不得 PASS（用户明确要求：不能要）。
    # 去重：同编号只保留最后一次"真实定义"出现，排除章首目录/TOC 与证明标题
    # "X.Y-Z 的证明"（已被 _parse_entry 过滤）造成的伪回归。
    for gk_key, seq in sorted(section_order.items()):
        if len(seq) < 2:
            continue
        # gk = "{gi}:{prefix_str}"（类型已编码在 gi 中）；还原展示用的前缀。
        _parts = gk_key.split(':', 1)
        pref = _parts[1] if len(_parts) > 1 else gk_key
        if pref == 'file' or pref.startswith('file:') or pref == '':
            pref = '<章级>'
        # 还原本组的标签候选（与 缺号 emit 同口径），供 ignore 令牌匹配
        # 「Theorem 1.23 / 定理 1.23 / 1.23」等写法。
        label_candidates = ['uncat']
        try:
            gi = int(gk_key.split(':', 1)[0])
            g = cfg.ordinal[gi]
            if not g.is_uncat:
                label_candidates = list(g.name)
        except (ValueError, IndexError):
            pass
        # 🔴 对照契约已知非单调编号：若某编号属已登记 ignore/known_gaps（即已
        # 经 agent 核实确为源书真实印刷顺序，而非我方错位），从本组序列剔除后再
        # 做单调校验——只抑制"确认的书异"，真实错位（未被 ignore 的号）仍照常
        # 报 BLOCKING。这与 缺号 emit 共用同一 _ignored_num 令牌逻辑，保证单条
        # ignore 同时压制 缺号 与 顺序错乱 两类告警。
        seq_f = [n for n in seq
                 if not _ignored_num(gk_key, pref, n, label_candidates, known, ignore)]
        # 与 seq_f 同过滤口径的出现明细（判据只依赖号 n，故两表逐项对齐）。
        meta_f = [(n, lab, sub) for (n, lab, sub) in section_order_meta.get(gk_key, [])
                  if not _ignored_num(gk_key, pref, n, label_candidates, known, ignore)]
        last_pos = {}
        for i, num in enumerate(seq_f):
            last_pos[num] = i
        ordered = [num for num, _ in sorted(last_pos.items(), key=lambda kv: kv[1])]
        # 🔴 Katok 2026-09-13：幽灵重复节点（正文引用被 build_structure 误当条目
        # 头建出同号重节点，如 §1.1 的第二个 定义1.1.1「Thus any such map…」）
        # 使序列出现同号二现。按「保留首次」去重后若单调，则为重复节点伪影而非
        # 真实错位 → 降级为非阻断 WARN（重复编号仍列出供清理）；真实错位
        # （去重后仍非单调）照旧 BLOCKING。
        first_pos = {}
        for i, num in enumerate(seq_f):
            first_pos.setdefault(num, i)
        ordered_first = [num for num, _ in sorted(first_pos.items(), key=lambda kv: kv[1])]
        monotone_first = all(ordered_first[i] >= ordered_first[i - 1]
                             for i in range(1, len(ordered_first)))
        for i in range(1, len(ordered)):
            if ordered[i] < ordered[i - 1]:
                if monotone_first:
                    # 🔴 2026-10-03 判据收窄（跨语料普查 `tools/census_ghost_rows.py`
                    # 实测 49 行 / 8 书，绝大多数不是幻影）：同号二现有两类**印面
                    # 合法的多计数器交错**——
                    #   A. 节内字母子块重启：Arnold §14.B 的 例1..4 与 §14.D 的 例1..2、
                    #      §8.D 与 §8.E 的 问题1..；ODE《常微分方程》ch1 每节 问题N 重启；
                    #   B. 合并窗内跨类型各自起号：Katok §9.2 的 Example 9.2.1 与
                    #      Proposition 9.2.1、Weibel §6.5 的 Definition 6.5.1 与
                    #      Exercises 6.5.1。
                    # 旧判据把整窗的同号一律说成「正文引用误建为条目节点」，既假又
                    # 稀释真信号。现只报**同标签 + 同子块**的同号二现（= 真幻影形态，
                    # Katok §1.1 的第二个 定义1.1.1 正是此形），跨标签/跨子块一律放行。
                    # 🔴 只收窄 WARN 分支：BLOCKING 分支与顺序判据一字未动，真错位
                    # （如 2.6-8 排在 2.6-11 之后，去重后仍非单调）照旧硬阻断。
                    # 子块锚取不到（md 无 `§` 标题）时所有出现落同一锚 → 旧行为不变。
                    _by_key = defaultdict(list)
                    for n, lab, sub in meta_f:
                        _by_key[(lab, sub)].append(n)
                    dups = sorted({n for vals in _by_key.values()
                                   for n in vals if vals.count(n) > 1})
                    if dups:
                        warnings.append(
                            f"  WARN (non-blocking): 疑似幽灵重复节点 @{pref} [gk={gk_key}]: "
                            f"同号二现 {dups}（同标签同子块，保留首次去重后单调）——正文引用"
                            f"被误建为条目节点，请核对源书并清理契约中的重复节点。")
                else:
                    blocking.append(
                        f"  WARN (BLOCKING): 顺序错乱 @{pref} [gk={gk_key} seq={seq_f}]: 编号 {ordered[i]} "
                        f"出现在更大编号 {ordered[i-1]} 之后（去重后阅读顺序 {ordered}）→ "
                        f"疑似条目错位（如 2.6-8 被排到 2.6-11 之后）。请核源书真实顺序，"
                        f"将 {pref}-{ordered[i]} 移到正确位置。")
                break  # 每节只报一次，避免洪水

    # 尾部校验：.md 最大号 vs 提取契约（源）同组最大号（非阻断）
    if os.environ.get('BKS_DEBUG'):
        for gk_key, seq in sorted(section_order.items()):
            print(f"  [DEBUG] order {gk_key}: {seq}", file=sys.stderr)
    # 尾部校验已在 run() 层通过 _md_tail_blocking 统一处理，此处不再重复调用
    tail_warnings = []

    return blocking, warnings, present_md, tail_warnings, groups


# ---------------------------------------------------------------------------
# 提取侧查漏：整类首项缺失 (Q) + over-mark 守卫。
# EXTRACT 侧只供给数据（items/entry_keys/all_keys/label_warns），查漏逻辑统一由 B 层处理；
# 复用 B 现有 `blocking` / `warnings` 键，不加新契约键。
# ---------------------------------------------------------------------------
CAT_WORDS = ['定义', '定理', '引理', '推论', '命题']
EN_TO_CN = {'Definition': '定义', 'Theorem': '定理', 'Lemma': '引理',
            'Corollary': '推论', 'Proposition': '命题'}
# OCR 字母↔数字容错（章号首位）：扫描 raw page JSON 时把 A→4, B→8, O→0 …
OCR_DIGIT = {'O': 0, 'o': 0, 'Q': 0, 'D': 0, '0': 0,
             'I': 1, 'l': 1, 'i': 1, '1': 1,
             'Z': 2, 'z': 2, '2': 2,
             'A': 4, 'a': 4, '4': 4,
             'S': 5, 's': 5, '5': 5,
             'G': 6, '6': 6,
             'T': 7, 't': 7, '7': 7,
             'B': 8, 'b': 8, '8': 8,
             'g': 9, '9': 9}


def _norm_ch(s):
    if s.isdigit():
        return int(s)
    return OCR_DIGIT.get(s)


# raw-text OCR-tolerant heading patterns (block-anchored with ^):
_CH = r'([0-9A-Za-z])'
_BOOK_LABEL_RES = [
    re.compile(r'^\s*(定义|定理|引理|推论|命题)\s*' + _CH + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)\b'),          # 定义4.7-1
    # EN: third component REQUIRED + `(?![0-9])` tail (not `\b`).  Leinster
    # 2014 measured: OCR glues the trailing word onto the number
    # ("Definition 1.2.1Let", "Definition 1.3.17A functor"); the old optional
    # third group + `\b` backtracked to a TWO-component match and recorded a
    # phantom item number 0, which _merged_category_first_missing then
    # reported as a fake "first item 0 missing" BLOCKING.  Requiring the third
    # component and replacing `\b` with a digit negative-lookahead keeps glued
    # letter forms intact and drops bare two-number mentions ("Definition 4.7")
    # instead of registering them as number-0 items.  Heuristic only (Q-into-B
    # category-first gate); strictly fewer false positives, zero regression.
    re.compile(r'^\s*(Definition|Theorem|Lemma|Corollary|Proposition)\s*' + _CH + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)(?![0-9])', re.IGNORECASE),  # Definition 4.7.N (glue-tolerant)
    re.compile(r'^\s*' + _CH + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)\s*(定义|定理|引理|推论|命题)'),            # 4.7-1 定义
]


def _scan_book_category_items(ch, start, end, ext_dir):
    """Scan raw page JSON text blocks for category-heading items, OCR-tolerant on
    the chapter's first char (A→4 etc). Returns {(sec, cat): sorted[num,]}.
    Block-anchored (^) so cross-references like '由定义 4.7-1' are excluded."""
    by = defaultdict(list)
    _pdir = resolve_page_dir(ext_dir, ch)
    for p in range(start, end + 1):
        fp = os.path.join(_pdir, f'page_{p:03d}.json')
        if not os.path.exists(fp):
            continue
        try:
            d = page_json.PageJson.load(fp).data
        except Exception:
            continue
        for blk in d.get('text', []):
            t = blk.get('text', '').strip()
            if not t:
                continue
            for ri, rgx in enumerate(_BOOK_LABEL_RES):
                m = rgx.match(t)
                if not m:
                    continue
                if ri == 0:                      # 定义4.7-1
                    cat = m.group(1); chc = m.group(2)
                    sec = int(m.group(3)); num = int(m.group(4))
                elif ri == 1:                    # Definition 4.7[-N]
                    cat = EN_TO_CN.get(m.group(1).title(), '定义')
                    chc = m.group(2); sec = int(m.group(3))
                    num = int(m.group(4)) if m.group(4) is not None else 0
                else:                            # 4.7-1 定义
                    chc = m.group(1); sec = int(m.group(2)); num = int(m.group(3))
                    tail = t[m.end():m.end() + 8]
                    tm = re.search(r'(定义|定理|引理|推论|命题)', tail)
                    if not tm:
                        break
                    cat = tm.group(1)
                cc = _norm_ch(chc)
                if cc is None or cc != ch:
                    break
                by[(sec, cat)].append(num)
                break
    return {k: sorted(set(v)) for k, v in by.items()}


# 🔴 EXTRA-MENTION 的「领域归属」收窄（2026-10-02 Lasota-Mackey / Strogatz 根治）：
#   提及桶此前把 md 里一切「契约无、正文有」的编号都当成待核对提及，而**公式标签**
#   `\tag{1.2.11}`、**图/表号** `图 1.1.2` / `ch01_fig1.1.2.png`、以及印刷公式回指形态
#   `(1.2.8)` 与条目号在 `keys_in_md` 层长得一模一样（三段号 1.2.11 既可能是公式号
#   也可能是定理号），实测 chaos 634 个提及键里 627 个（99%）、Strogatz 全部 525 个
#   都属于**别的层已负责**的领域 → 真正「契约漏登记条目」的信号被上千行良性噪声淹没。
#   判据：一个提及键**只有在其全部出现位置**都属于下列领域时才从报告桶剔除——
#     tag    : 位于 `\tag{...}` 内部（Q 层 formula_tag 的辖域）；
#     figref : 紧跟 图/表/Figure/Fig./Plate/Table/`…_fig` 文件名（图像域——writing-rules
#              规定图只在正文引用、从不作条目登记，`extracted` 也按 label=='uncat' 剔它们）；
#     eqref  : 被括号包住 `(1.2.8)` / `（1.2.8）`（印刷公式回指形态）；**开括号前是条目词**
#              （`Definition (5.6.5)` / `定理（5.6.5）`）时不算，那正是条目引用形态。
#   任何一处出现在其他上下文（裸号散文提及、条目头、带标签引用）→ 照旧报；md 里根本
#   扫不到该号（跨语言/跨文件带进来的键）→ 不判。
#   🔴 只影响 `extra` / `extra_mention` 两个**非阻断**报告桶；`all_keys` 原样不动，
#   故 truly_missing、整类首项缺失等阻断判据逐字节不变。
_TAG_SPAN_RE = re.compile(r'\\tag\s*\{[^{}]*\}')
_FIGREF_TAIL_RE = re.compile(
    r'(?<![a-z])(?:Figure|Fig\.?|Plate|Table|Tab\.?)\s*[:：.．]?\s*$'
    r'|(?:图|圖|图例|插图|表)\s*[:：.．]?\s*$',
    re.IGNORECASE)
_FIGFILE_TAIL_RE = re.compile(r'(?:fig|figure|img)[-_/]*$', re.IGNORECASE)
_LABEL_BEFORE_PAREN_RE = re.compile(
    # 🔴 `Equation` / `Eq.` 曾在「条目词 → real」表里，于是 EN 的
    # `Equation (4.2.6) follows directly from (4.2.5)` 被判成条目引用而**永不豁免**
    # （同句 CN 侧 `由 (4.2.6)` 判 eqref → 双语不对称，2026-10-02 chaos ch4/ch12 实测）。
    # 公式词不属于条目域：全链（`TYPE_TO_LABEL_CN` / `extract_items` / 契约 `type`）
    # 从不把 equation 登记为条目类型，编号公式一律是 `formula` 块 + `\tag{}`，
    # 对账归 Q 层 formula_tag；`Figure/Table` 同理早已被 `_FIGREF_TAIL_RE` 归图像域。
    r'(?:定义|定理|引理|推论|例|例題|例题|性质|注|评注|练习|习题|命题|算法|证明|观察|问题|'
    r'Definition|Theorem|Lemma|Corollary|Example|Exercise|Proposition|Remark|'
    r'Note|Problem|Algorithm)\s*$',
    re.IGNORECASE)
_OPEN_PAREN_RE = re.compile(r'[(（]\s*$')
_CLOSE_PAREN_RE = re.compile(r'^\s*[)）]')
_NUM_SEP = r'[.\-·．–—]'
_MENTION_DOMAIN_EXPLAINED = frozenset(('tag', 'figref', 'eqref'))


def _mention_num_regex(key):
    """提及键 → 只匹配「该号本身」的正则（分量间分隔符走全书统一通配）。

    非纯数字键（`性质1` / 罗马 / 字母形态）返回 None = 不判，照旧报。
    前后守卫禁邻数字/分隔符，避免 `1.2.11` 被 `11.2.11`、`1.2.115` 里的片段冒充。
    """
    parts = re.split(r'[.\-]', _norm_path(key))
    if len(parts) < 2 or not all(p.isdigit() for p in parts):
        return None
    body = _NUM_SEP.join(re.escape(p) for p in parts)
    return re.compile(r'(?<![\d.])' + body + r'(?![\d.])')


def _mention_occurrence_domain(txt, m, tag_spans):
    s, e = m.start(), m.end()
    if any(ts <= s and e <= te for ts, te in tag_spans):
        return 'tag'
    left = txt[max(0, s - 24):s]
    if _FIGREF_TAIL_RE.search(left) or _FIGFILE_TAIL_RE.search(left):
        return 'figref'
    prev = txt[max(0, s - 8):s]
    pm = _OPEN_PAREN_RE.search(prev)
    if pm and _CLOSE_PAREN_RE.match(txt[e:e + 8]):
        open_idx = s - len(prev) + pm.start()
        before = txt[max(0, open_idx - 24):open_idx]
        if _LABEL_BEFORE_PAREN_RE.search(before):
            return 'real'          # `Definition (5.6.5)`：条目引用形态
        return 'eqref'
    return 'real'


def domain_suppressed_mentions(md_text, keys):
    """返回可归入公式/图像领域的提及键（判据见 `_TAG_SPAN_RE` 上方注释）。"""
    txt = md_text or ''
    tag_spans = [(m.start(), m.end()) for m in _TAG_SPAN_RE.finditer(txt)]
    out = set()
    for k in keys:
        rx = _mention_num_regex(k)
        if rx is None:
            continue
        ms = list(rx.finditer(txt))
        if not ms:
            continue
        doms = {_mention_occurrence_domain(txt, m, tag_spans) for m in ms}
        if doms and doms <= _MENTION_DOMAIN_EXPLAINED:
            out.add(k)
    return out


def _norm_path(k):
    """Label-tolerant key for three-level presence matching.

    A three-level labeled head (``定义1.1.1`` / ``Theorem 1.1.1`` / ``性质6.2.1``)
    and the contract's bare dash key (``1.1-1``) denote the SAME entitity.  Strip
    the leading label and normalize separators to bare dash ``N.S-N`` so the md's
    labeled head is recognized as present against the contract's bare key.

    Bare keys (``3.1-2``) and any other form pass through unchanged.  This is what
    keeps CN/EN three-level books from reporting every labeled md head as spurious
    EXTRA-ENTRY (and keeps a contract type/label mismatch, e.g. registered as
    ``性质`` but printed ``定义``, from surfacing as false truly-missing).
    """
    m = re.match(r'^([^\d]+)(\d+)\.(\d+)\.(\d+)$', k)
    if m:
        return f"{m.group(2)}.{m.group(3)}-{m.group(4)}"
    return k


# 字母章位键（附录 `A.2-1` / `定理A.1-13` / `Proposition A.1.2`）：标签词后面必须
# 紧跟「单个拉丁字母 + 分隔符」，否则 `Fig1.2-3` / `Corollary5.1-2` 一类无从折叠。
_LETTER_SLOT_RE = re.compile(r'^(.*?)([A-Za-z])[.．](\d+)[.\-](\d+)$')


def _norm_path_labelfree(k):
    """A 部分（书真相 ↔ md 在账比较）专用的标签无关归一。

    先走 `_norm_path`（纯数字三段号已有行为，逐字节不变），再对**字母章位**键做
    同一条口径的剥标签：`定义A.2-1` / `A.2-1` / `Proposition A.1.2` 一律折成
    `A.2-1`。缺这一折，附录章的 md 条头与契约键只要标签词不同（Katok 附录印面
    `Definition A.2.1` 而契约登记 `定义A.2-1`，md 裸号头 `**A.2.1**` 亦然）就双双
    落不进 `_ext_norm`，于是每条附录条目都被报成 `extra_entry`（Katok 附录 A 实测
    13 键 × cn/en = 26 行）。

    单调性 = 本函数是**函数**（两侧同折），`k1 == k2 ⇒ f(k1) == f(k2)`：原本匹配
    的照旧匹配，只会多匹配，绝不会新造 `truly_missing` 或新的 EXTRA。代价与
    `_norm_path` 完全同源：同一 `A.2-1` 路径下「定义 vs 定理」的**类型分歧**不再
    由本层暴露（类型对账在闸门⑩ / P 层）。
    """
    s = _norm_path(k)
    m = _LETTER_SLOT_RE.match(s)
    if m:
        return f"{m.group(2)}.{m.group(3)}-{m.group(4)}"
    return s


def _split_extra(all_keys, entry_keys, extracted):
    """把「md 有、契约无」的键分成**条目级**与**提及级**两桶。

    条目级 = md 里以独立加粗条头出现（`entry_keys`）→ 契约很可能漏登记一个印面
    条目；提及级 = 只出现在正文/交叉引用里 → 通常是正确过滤的引用。
    返回 ``(union, entry_bucket, mention_bucket)``；union 保持旧 `extra` 口径，
    两桶是其不切分信息的重述（``entry ∪ mention == union``），pass/fail 语义不变。
    """
    ex = set(all_keys) - set(extracted)
    ent = ex & set(entry_keys)
    return (sorted(ex, key=sortkey), sorted(ent, key=sortkey),
            sorted(ex - ent, key=sortkey))


def _merged_category_first_missing(ctx, all_keys, blocking):
    """Q 逻辑并入 B：整类首项缺失检测。仅 three_level 方案启用（ordinal=3）。"""
    if ctx.config.primary_type != ORDINAL_THREE_LEVEL:
        return
    ch = ctx.ch
    book_cat = _scan_book_category_items(ch, ctx.start, ctx.end, ctx.ext_dir)
    if not book_cat:
        return
    # md 中各节已出现的编号（任何重要概念类别都算，避免同号异类误报）。
    # 注意：three-level 方案的 .md 键是数字型（如 3.3-2），不含类别前缀，
    # 故此处用数字型正则解析，不能套用带类别前缀的 _BOOK_LABEL_RES。
    md_by_sec = defaultdict(set)
    for k in all_keys:
        m = re.match(r'^(\d+)\.(\d+)-(\d+)$', k)
        if m and int(m.group(1)) == ch:
            md_by_sec[int(m.group(2))].add(int(m.group(3)))
    for (sec, cat), nums in book_cat.items():
        bmin = nums[0]
        if bmin in md_by_sec.get(sec, set()):
            continue                        # 该编号在总结中已出现（任何类别）→ 非首项缺失
        blocking.append(
            f"  ! §{ch}.{sec} 书中含「{cat}」{len(nums)} 条（首项 {cat}{ch}.{sec}-{bmin}），"
            f"但总结未含任何「{cat}」条目（编号 {bmin} 在总结中不存在）→ 疑似缺失首项 {cat}{ch}.{sec}-{bmin}")


def _merged_ocr_overmark_guard(ctx, items, warnings):
    """over-mark 守卫：.md 中带（OCR无法识别）的条目，若其编号已被 book 抽取识别
    → 误标警告（书中其实有该条目，不应标 OCR无法识别）。"""
    try:
        mdtext = open(ctx.md_file, encoding='utf-8').read()
    except Exception:
        return
    mark_re = re.compile(r'\*\*([^*]*?(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)[^*]*?)\*\*')
    md_mark = set()
    for m in mark_re.finditer(mdtext):
        if 'OCR无法识别' in m.group(0) or 'OCR无法识别' in m.group(1):
            md_mark.add(f"{int(m.group(2))}.{int(m.group(3))}-{int(m.group(4))}")
    if not md_mark:
        return
    book_num = set()
    for it in items:
        # agent_recovered (manual override) entries are NOT genuinely OCR-recognized;
        # an (OCR无法识别) marker on them is legitimate, so don't误-flag.
        if it.get('agent_recovered'):
            continue
        mm = re.search(r'(\d+)\.(\d+)-(\d+)', it['key'])
        if mm:
            book_num.add(f"{mm.group(1)}.{mm.group(2)}-{mm.group(3)}")
    for k in sorted(md_mark):
        if k in book_num and k not in ctx.ignore:
            warnings.append(
                f"  ? {k} 标注（OCR无法识别）但书中 OCR 已识别该条目 → 可能误标，请复核")


class ItemNumberingIntegrityLayer(VerifyLayer):
    code = 'B'
    name = 'item-numbering-integrity'
    order = 3
    auto_fixable = False

    def run(self, ctx):
        items = ctx.items or []
        entry_keys = ctx.entry_keys or set()
        all_keys = ctx.all_keys or set()
        ignore_keys = ctx.ignore
        ctx.evidenced_ignore = _load_evidenced_ignore(ctx.ext_dir)

        # --- A-LAYER 完整性（原独立 A 层，现并入 B）：truly_missing / mentioned_only / extra ---
        # 数据来自 EXTRACT 供给的 ctx.items（书真相集）/ all_keys / entry_keys；
        # B 是查漏的唯一权威，EXTRACT 只供水、不做事。
        # Figures/Tables (uncat) are referenced in prose only per writing-rules,
        # not as labeled `**...**` entries, so they must not count as
        # truly-missing items. (Definition/Theorem/Example/etc. are kept.)
        extracted_raw = {it['key'] for it in items if it.get('label') != 'uncat'}
        ignored_hit = sorted(extracted_raw & ignore_keys, key=sortkey)   # stage1：噪声键
        extracted = extracted_raw - ignore_keys                          # 剔噪书集
        # Label-tolerant presence matching for three-level items: a contract bare
        # key ('1.1-1') and the md's labeled head ('定义1.1.1') are the same
        # entity.  Normalize both sides so md labeled heads don't show up as
        # spurious EXTRA-ENTRY and contract type/label mismatches don't surface as
        # false truly-missing.  Genuinely-absent entries (their normalized path is
        # found nowhere in the md) are still reported as truly-missing.
        _ext_norm = {_norm_path_labelfree(k) for k in extracted}
        # 🔴 契约里的习题/问题节点键同样算「已在账」（2026-10-02 Katok 264 行
        # EXTRA-ENTRY 根治）。`load_contract` 对 exercise/problem 直接 return，于是
        # `ctx.items` **永不含**习题节点，而 md 照印面写的习题条头（`**练习 0.2.1**` /
        # `**Exercise 0.2.1**`，Katok 每节后段成排）不可能被 `_covered` 折掉 → 每一行
        # 都被报成「契约漏登记印面条目」的真信号（Katok 264 行、
        # Introduction-to-Dynamical-Systems 383 行；上一条 Apostol 例1 的判读文案因此
        # 被假信号淹没）。真值仍只有一份：`book_structure/ch{N}.json` 里
        # type=exercise/problem 的节点（`_contract_exercise_keys`，与裸号开窗判据同源，
        # 键形已按 md 侧 `_norm_ex_key_form` 归一）。
        # 🔴 **只进 `_ext_norm`（EXTRA 覆盖集），绝不进 `extracted`**：后者是
        # `truly_missing` 的书真相集，consolidated 成堆习题块按 writing-rules 不进总结，
        # 塞进去就是拿放宽判据造假的「整条漏写」。习题**内容**是否在账由闸门⑩ /
        # `check_structure_completeness` 负责，本行只声明「该键契约已登记，不是孤儿条头」。
        _ext_norm |= _contract_exercise_keys(ctx.ext_dir, ctx.ch)
        _all_norm = {_norm_path_labelfree(k) for k in all_keys}
        truly_missing = sorted(k for k in extracted
                               if _norm_path_labelfree(k) not in _all_norm)
        mentioned_only = sorted((extracted & all_keys) - entry_keys, key=sortkey)
        # EXTRA: suppress md keys whose normalized path matches a contract key
        # (merely a label-variant of a registered item); keep only genuine orphans.
        _covered = {k for k in all_keys if _norm_path_labelfree(k) in _ext_norm}
        all_keys_eff = set(all_keys) - _covered
        # 🔴 EXTRA 分桶（判据见 `_split_extra`）。混在一行时报告文案
        # "usually correctly-filtered cross-refs" 会把**契约漏登记的真条目**说成
        # 良性噪声：Apostol ch9 §9.6 印面确有 `EXAMPLE 1`（fitz 300dpi 目视，物理页
        # 199），md 也照印面写了条头，只因 OCR 把条头粘进句子
        # （`ExAMPLE1Determinewhether219…`）而契约无节点 → 该 EXTRA 被一路判成
        # 「交叉引用，无需处置」。
        # 跨书普查（51 书全部章，脚本 = Apostol 书 _extract/_census_entry_extra.py）：
        # 条目级 EXTRA 分布在 ≥6 书、数十章，且多数是**体例**而非漏登记
        # （statistical-inference 契约用两段键而 md 条头三段号；Lie 代数 ch1 无号
        # 条头 `**例**`/`**定义**`）→ 一律阻断会打爆已收官书，故**只改可读性、
        # 不改 pass/fail 语义**（`extra` 仍是并集，老消费者逐字节不变）。
        extra, extra_entry, extra_mention = _split_extra(all_keys_eff, entry_keys, extracted)
        # 🔴 EXTRA-MENTION 收窄：练习/习题/Problem/问题/Question 等「题集」类提及
        # 在采用 consolidated 习题块的书里从不作为契约条目登记（load_contract 对
        # exercise/problem 直接 return），故它们在正文/交叉引用中出现必为合法引用，
        # 非漏登记条目 → 从提及桶剔除，避免误报。个别外部引用（如 Euclid 命题）由
        # 本书 verify_config.json 的 mention_ignore 显式豁免。
        _drop = {k for k in extra_mention if _EXM_DROP_RE.search(k)}
        _vc_path = os.path.join(ctx.ext_dir, "verify_config.json")
        if os.path.exists(_vc_path):
            try:
                _vcd = json.load(open(_vc_path, encoding="utf-8"))
                _drop |= set(_vcd.get("mention_ignore", []) or [])
            except Exception:
                pass
        if _drop:
            extra_mention = [k for k in extra_mention if k not in _drop]
            extra = [k for k in extra if k not in _drop]
        # 🔴 领域归属收窄（判据见 `domain_suppressed_mentions` 上方注释）：
        # 公式标签 / 图表号 / 括号公式回指形态的提及键不再占用提及桶。
        # 🔴 同一判据并进**条目桶**（2026-10-02 chaos ch4/ch8/ch12 根治）：
        # `ENTRY_RE` 的粗体跨度以 `\*+` 收尾，于是会在**行内数学的星号上闭合**
        # （`$f^{*}$` / `$\mu_*$` / `^{*}` 的单个 `*`），把 `> **证明**：1. 由 (4.2.6)
        # 与定理 4.2.1 可知 $f^{*}$…` 里的**公式回指**登记成条目键 → 直落 `extra_entry`
        # =「契约漏登记印面条目」最强信号桶（实测该键在 md 里根本没有粗体条头）。
        # 豁免口径与提及侧同函数且更硬：某键在 md 里的**每一处**出现都属
        # tag/figref/eqref 才剔除——真条头（`**定义 4.2.6**`）必然自己贡献一处
        # `real` 出现，故本行不可能洗掉真漏登记。只动非阻断的 EXTRA 三桶，
        # 被剔除的键照旧进 `extra_mention_domain` 清单打印，不静默消失。
        _dom_sup = set()
        if extra_mention or extra_entry:
            try:
                _md_txt = '\n'.join(ctx.read_md_lines())
            except Exception:
                _md_txt = ''
            _dom_sup = domain_suppressed_mentions(
                _md_txt, set(extra_mention) | set(extra_entry))
            if _dom_sup:
                extra_mention = [k for k in extra_mention if k not in _dom_sup]
                extra_entry = [k for k in extra_entry if k not in _dom_sup]
                extra = [k for k in extra if k not in _dom_sup]

        # --- P2：提取侧查漏（Q 类整项缺失 + over-mark 守卫，归 B 层统一处理）---
        blocking = []
        warnings = []
        _merged_category_first_missing(ctx, all_keys, blocking)
        _merged_ocr_overmark_guard(ctx, items, warnings)

        # --- B 层原有逻辑：ignored_hit 第二段 suppression + md 侧查漏 + OCR 误报过滤 ---
        # Suppress extraction-side blocking entries whose referenced item keys
        # are ALL registered as confirmed noise; fold those keys into ignored_hit.
        if ignore_keys and blocking:
            kept = []
            for msg in blocking:
                sec_m = re.search(r'(\d+\.\d+)', msg)
                nums = re.findall(r'-(\d+)', msg)
                if sec_m and nums:
                    sec = sec_m.group(1)
                    bkeys = {f"{sec}-{n}" for n in nums}
                    if bkeys <= ignore_keys:
                        ignored_hit = sorted(set(ignored_hit) | bkeys, key=sortkey)
                        continue
                kept.append(msg)
            blocking = kept

        # Authoritative missing-number detection on the written .md.
        md_blocking, md_warnings, present_md, _md_tail_unused, groups = _md_gap_blocking(ctx)

        # Tail warnings are now BLOCKING: agent must verify each section's tail
        # and register "TAIL:{gk}" in ignore if the section truly ends there.
        md_tail = _md_tail_blocking(ctx, ctx.config, groups)

        # 提取侧误报过滤：OCR 漏检但 .md 已正确写出的条目不应 hard-block。
        # 仅当被报缺的键在 .md 中也确实缺失时，才保留为 blocking（此时 MD 与
        # 提取契约双重确认 -> 真漏项，agent 应补）。
        if blocking and present_md:
            kept = []
            for msg in blocking:
                sec = None
                nums_str = None
                mm = re.search(r'(\d+\.\d+)\s+missing items\s+([-\d,\s]+)', msg)
                if mm:
                    sec = mm.group(1)
                    nums_str = mm.group(2)
                else:
                    # Extraction-side head-gap report: "0:2.1 starts at -3, items
                    # -2 still missing after auto-recovery". If the reported
                    # missing numbers are actually present in the written .md,
                    # this is an OCR miss, not a real gap.
                    sm = re.search(r'(\d+\.\d+)\s+starts at -(\d+).*?items\s+([-\d,\s]+)\s+still missing', msg)
                    if sm:
                        sec = sm.group(1)
                        nums_str = sm.group(3)
                if sec and nums_str:
                    # 消息中每个号已带前导 '-'（"missing items -4" 或
                    # "items -2 still missing"），直接拼接即可。
                    bkeys = {f"{sec}{n.strip()}" for n in nums_str.split(',') if n.strip()}
                    if bkeys and bkeys <= present_md:
                        ignored_hit = sorted(set(ignored_hit) | bkeys, key=sortkey)
                        continue
                kept.append(msg)
            blocking = kept

        blocking = blocking + md_blocking + md_tail

        ctx.ignored_hit = ignored_hit
        ctx.extraction_blocking = blocking

        return LayerResult(code=self.code, metadata={
            'blocking': blocking,
            'warnings': warnings,
            'b_gap_warnings': md_warnings,
            'b_tail_warnings': [],  # tail items already in blocking above
            'ignored_hit': ignored_hit,
            'truly_missing': truly_missing,
            'mentioned_only': mentioned_only,
            'extra': extra,
            'extra_entry': extra_entry,
            'extra_mention': extra_mention,
            'extra_mention_domain': sorted(_dom_sup, key=sortkey),
        })
