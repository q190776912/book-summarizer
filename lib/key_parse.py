"""
key_parse.py — key/label regexes + canon maps + parsing/canonization helpers.

Single home for ALL key/label parsing logic used across the skill (extract
flows, verify layers, and config tools): the three-level / two-level / English
key regexes, the label canonicalization maps (_LABEL_CANON etc.), `normkey`,
`keys_in_md`, `sortkey` and `_first_num`. It has NO heavy dependencies (no
cv2 / torch) so it can be imported standalone in a bare environment.

This module is a shared `lib/` primitive (not owned by any single flow or the
verify engine), so it is importable anywhere via the bare name `key_parse`
(boot injects `lib/` into sys.path). It must NOT import anything from
`flows.*` or `verify.*` (other than the already-shared `lib.regexlib` and the
`config/verify_config` model), to keep the extract/verify boundary clean.

The inter-component separator policy lives in `lib/regexlib`
(SEP_TIGHT / SEP_WIDE / canon helpers).  This module imports SEP_TIGHT and
rebuilds every label-embedded regex with it, and re-exports the label-FREE
shared regexes (KEY_RE / ENTRY_RE) so all callers stay unchanged.
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

import re, sys, os


from lib.regexlib import (
    SEP_TIGHT, SEP_SPLIT_RE, KEY_RE, ENTRY_RE,
)
from verify_config import (
    ORDINAL_TWO_LEVEL,
    ORDINAL_THREE_LEVEL, ORDINAL_SINGLE,
    ORDINAL_HUM, ORDINAL_APP, ORDINAL_APP2,
    GroupConfig, _LABEL_CANON, EN_LABEL_KINDS,
    _canon_label,
)

# --- three-level (default) key parsing ---
# KEY_RE / ENTRY_RE are imported from lib.regexlib (label-FREE, built from
# SEP_TIGHT). They match both dash (N.S-N) and dot (N.S.N) numbering — the
# extractor canonicalizes everything to dash, but the .md may keep the book's
# dot style.

# --- two-level key parsing (中文二级标签) ---
# Bold entries:  **定义1.1**： / **定理1.1**：
# NOTE: labels MUST be an alternation, not a char class. A char class
# [定义定理...] matches a SINGLE cjk char, so `**定义1.1**` (label is 2 chars)
# would never match — every entry then silently degrades to "mentioned-only".
ENTRY_RE_2 = re.compile(
    r'\*\*(定义|定理|引理|推论|命题|例|示例'
    r'|Definition|Theorem|Lemma|Corollary|Proposition|Example'
    r'|公理|Axiom'
    r'|问题|Problem'
    r'|注记|评注|注|Remark'
    # 🔴 练习家族：与 COMBINED_LABEL_KINDS 的 练习/Exercise 对齐。ENTRY_RE_2 是手写
    # 子集字面量（不随 COMBINED 自动派生），两边不同步会让 type 2 的 md 抽键与
    # 新层级 _LABEL_ALT 口径不一致。
    r'|练习|Exercise)\s*(\d+)' + SEP_TIGHT + r'(\d+)\s*(?:' + SEP_TIGHT + r')?\s*\*+')
# 🔴 三段号截断守卫（幻影前缀键）。二级正则最长按「标签+两段数字」匹配，遇到三级
# 条头 `**定义2.1.1**` / 正文引用「见定义 2.1.1」会同时吐出真键 `定义2.1.1` 和**被截
# 断的幻影键** `定义2.1`。契约侧三级条目登记为裸 dash 键 `2.1-1`，`_norm_path` 只能
# 折回三段式，幻影二级键无人认领 → B 层把它列进 EXTRA-ENTRY（「md 有条头而契约无此
# 条目」），Lasota & Mackey《Chaos, Fractals and Noise》实测每章每（类别,节）都刷一
# 条（ch2 11 条 / ch3 10 条 …），把**真的契约漏登记**淹没在噪声里。
# 守卫 = 数字后紧跟「分隔符+数字」即判定这不是二级号，整条匹配让位给三级正则
# （ENTRY_RE_EN3_C / `_norm_path`）。与 ENTRY_RE_EN_SINGLE_C 用同样手法拒绝把
# `**Label N.N**` 截成 `Label N` 一脉相承。
# 🔴 两道缺一不可：`(?!\d)` 拦**同段数字回退**（`**定义5.10.1**` 里 `(\d+)` 若只吞
# `1`，后面紧跟的是 `0` 而非分隔符，只靠 SEP 断言会被绕过 → 幻影键 `定义5.1`；
# Lasota & Mackey ch5 §5.10 实测），`(?!SEP\d)` 拦**跨段截断**（`2.1` ⊂ `2.1.1`）。
# 与 ENTRY_RE_EN_SINGLE_C 的 `(\d+)(?!\d)(?!\s*SEP\s*\d)` 同一手法。
_NOT_DEEPER = r'(?!\d)' + r'(?!' + SEP_TIGHT + r'\s*\d)'
# 🔴 **节限定字母条目的引用**（2026-10-20 Rice《Mathematical Statistics and Data
# Analysis》ch8 实测）：印面引用写 `例 8.4A` / `例 8.5A`，意思是「§8.4 / §8.5 的
# Example A」——本书条目是字母序标（Example A/B/C），`8.4` 是**节号**不是条目号。
# 二级 prose 正则把号截到 `8.4` 后照收，于是 all_keys 里凭空出现 `例8.4`/`例8.5`：
# ① B 层每章刷 EXTRA-MENTION 幻影（错误键形，无从处置）；
# ② 更糟：若契约真登记了编号例 8.4（别章/别书形态），这个幻影提及会让
#    `truly_missing` 误判「已提及」——静默掩盖真缺项。
# 守卫 = 号后紧跟**单个大写字母**（前后都不是字母/数字）即整条让位：该实体是节内
# 字母条目，键空间里没有节号+字母的条目形，不参与提及对账。Ross 式 `Example 2a`
# （单号+字母）由 ROSS 分支负责，不走本支，零影响。
_LETTER_SLOT_TAIL_RE = re.compile(r'[A-Z](?![A-Za-z0-9])')


def _is_letter_slot_tail(line, end):
    """prose 匹配尾巴是「单个大写字母」→ 节限定字母条目引用（`例 8.4A`）。"""
    return bool(_LETTER_SLOT_TAIL_RE.match(line, end))

# 🔴 **裸三段号扫描**（`keys_in_md` 三级分支的 `KEY_RE`）同一族缺陷的**区间形态**
# （2026-10-04 动力系统书架根治）：`KEY_RE` 两端无守卫，而 `finditer` 只产出**不重叠**
# 匹配，于是印面/交付里的**小节区间写法** `第 10.4-10.6 节` / `Sections 7.2-7.4`
# 被切成一个假三段键 `10.4-10` / `7.2-7`（`10.4` + `-` + `10`，尾巴 `.6` 白送）。
# 该号契约永不可能在册 → B 层每一处区间引用都刷一条 EXTRA-MENTION（实测 chaos ch10
# 中英 2 行、nonlinear ch7·ch10 4 行；与上面「标签+三段截断成二级」是同一类幻影，
# 只是这次由**无标签**的裸号正则造成，且在 md 侧）。
# 🔴 **左守卫缺一不可**：只加右守卫时正则会**错位重切**——`10.4-10.6` 在 idx0 被右侧
# `.6` 挡下后，退到 `4-10.6` 仍能凑出三段 → 造出更假的键 `4.10-6`。故左端同样要求
# 起点前既不是数字、也不是任何分隔符（即本号是一段**独立号码 token** 的开头）。
# 左守卫里的 `/ _ ~` 顺带把**文件名/路径**里的号（`ch05_1.2.3.png`）排除在条目键之外
# ——那是图像域，本来就不作契约条目。
_KEY_DEEP_RE = re.compile(
    r'(?<![\d' + SEP_TIGHT[1:-1] + r'])'
    + r'(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)'
    + _NOT_DEEPER)
# 与 `_NOT_DEEPER` 同源的另一收益：`1.2.3.4`（更深一层号）不再被截成 `1.2-3`。
# 🔴 只作用于 `keys_in_md` 的这一处调用点：共享件 `KEY_RE` 模式与其余消费者逐字节不动。

# Prose / cross-reference mentions:  定义1.3, 由定理5.2 / by Theorem 5.2 ...
# 2026-08-27 补齐 例/Example/公理/Axiom/问题/Problem/示例 的 ENTRY_RE_2+PROSE_RE_2 覆盖
# （之前仅含 定义|定理|引理|推论|命题|注记|评注|注|Remark，中文书籍的
# 例1.X 等条目长期被静默略过成 missing，与 verify_config 里已配置的
# type=example/example ordinal group 完全脱节）。
PROSE_RE_2 = re.compile(
    r'(定义|定理|引理|推论|命题|例|示例'
    r'|Definition|Theorem|Lemma|Corollary|Proposition|Example'
    r'|公理|Axiom'
    r'|问题|Problem'
    r'|注记|评注|注|Remark'
    r'|练习|Exercise)\s*(\d+)' + SEP_TIGHT + r'(\d+)' + _NOT_DEEPER)

def normkey(s):
    """Canonicalize a key to N.S-N dash form (N.S.N -> N.S-N, N·S·N -> N.S-N).
    Wildcard-aware: any separator run normalizes via SEP_SPLIT_RE."""
    parts = [p for p in SEP_SPLIT_RE.split(s) if p]
    if len(parts) == 3:
        return f'{parts[0]}.{parts[1]}-{parts[2]}'
    return s

# _LABEL_CANON / EN_LABEL_KINDS / _canon_label are imported from config
# (single source of truth) so the md-side parser and the extractor agree on
# bilingual label canonicalization (e.g. Example -> 练习, matching the
# 练习/习题/Example exercise group).  Do NOT redefine them here.

# Chinese label synonyms that appear in bilingual-book .md files.
# 🔴 `问题` 必须与 EN 的 `Problem` 配对：config 的 _LABEL_CANON 已把
# Problem 正名为「问题」（TYPE_TO_LABEL_CN: problem -> 问题），EN_LABEL_KINDS
# 收 `Problem`，CN 侧漏收 `问题` 会让 CN 合并 md 的 `**问题1-1**` 条头完全
# 解析不出 → 章末 Problems 在 CN 侧整族报「truly missing」（Lee 2e 实测：
# ch1–22 CN 各缺 8–31 条，全部是章末问题）。
# 🔴 `练习` 在此收录：`_LABEL_CANON` 的 Exercise / 习题 都正名为 `练习`，exercise
# group 的契约键就是 `练习N…`；CN 词表不收它就等于 CN 侧 md 条头整族解析不出。
# (`习题` 暂不收：与 `练习` 同义但正名相同，收录面待评估，见 book 侧回归。)
CN_LABEL_KINDS = ['定义', '定理', '引理', '推论', '命题', '例', '示例', '评注', '注释',
                  '注', '注记', '公理', '断言', '猜想', '条件', '假设', '算法', '性质',
                  '问题', '练习']
# Combined (used when ordinal == ORDINAL_EN so either language matches).
COMBINED_LABEL_KINDS = EN_LABEL_KINDS + CN_LABEL_KINDS
ENTRY_RE_EN = re.compile(
    r'\*\*(?:' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*(\d+)' + SEP_TIGHT + r'(\d+)\s*\*+')
PROSE_RE_EN = re.compile(
    # CJK-aware boundaries: \b never fires after a CJK char (由定理X.Y / 见命题X.Y
    # are all \w on both sides), which hid every Chinese cross-reference that
    # directly followed CJK text and surfaced them as false "truly missing".
    # (?<![A-Za-z0-9]) keeps the old protection against matches inside Latin
    # words (reTheorem); (?![A-Za-z]) still rejects the plural "Theorems" while
    # ALLOWING a digit right after the label (CN no-space form 定理14.15).
    r'(?<![A-Za-z0-9])(?:' + '|'.join(COMBINED_LABEL_KINDS) + r')(?![A-Za-z])\s*(\d+)' + SEP_TIGHT + r'(\d+)')

# Capturing variants of the EN regexes (label as group(1)) — used by
# keys_in_md('en'), which needs the label to canonicalize (Definition->定义...).
# PREFIX match only: real entries look like `**Definition 1.1 (Title)**：` or
# `**定义 5.1（级联系统）**：` — the number is immediately after the label but a
# parenthetical + closing `**` follows, so we must NOT require `*` right after
# the number. The label IS captured (group 1) so we can canonicalize it.
# re.IGNORECASE: English books (e.g. Apostol) print headings in UPPERCASE
# (THEOREM 8.16. / COROLLARY 8.3.) or OCR-mangled mixed case (THEoREM /
# CoROLLARY); without it the md-side parser misses those entries and they
# surface as false "truly missing". Mirrors extract_items_en (EN_LAB_RE).
ENTRY_RE_EN_C = re.compile(
    r'\*\*(' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*(\d+)' + SEP_TIGHT + r'(\d+)'
    + _NOT_DEEPER,
    re.IGNORECASE)
# Number-FIRST English entries (Fraleigh《A First Course in Abstract Algebra》
# prints "0.12 Definition", "0.20 Example" — number before label). The label-FIRST
# regexes above never match these, so an entire number-first English book extracts
# ZERO md items and every contract item surfaces as falsely "truly missing".
# Mirror of ENTRY_RE_EN_C with the number/label swapped; emits the SAME canonical
# key (`定义0.12`) so the md side and the OCR truth set (extract_items_en's
# EN_LAB_RE_NF) compare apples-to-apples. "Figure"/"Table" are NOT in
# COMBINED_LABEL_KINDS, so `**0.15 Figure**` is correctly excluded (figures are an
# E-layer concern, not B-layer items).
ENTRY_RE_EN_NF_C = re.compile(
    r'\*\*(\d+)' + SEP_TIGHT + r'(\d+)\s*(' + '|'.join(COMBINED_LABEL_KINDS) + r')',
    re.IGNORECASE)

# ORDINAL_HUM (Humphreys GTM 9): bold entries without section numbers.
# Matches **Theorem**, **Corollary A**, **Corollary A (Lie's Theorem)**,
# **Lemma A**, **Definition**, **Example 1**, etc.
_HUM_LABELS = (r'Theorem|Proposition|Corollary|Lemma|Example|Remark|Definition'
               r'|定理|命题|推论|引理|例|评注|注|定义')
ENTRY_RE_HUM = re.compile(
    r'\*\*(' + _HUM_LABELS + r')'
    r'(?:\s+([A-Z]))?'   # optional letter suffix (A, B, C)
    r'(?:\s+(\d+))?'      # optional number (for Example 1, Example 2)
    r'(?:\.?)'            # optional trailing period
    r'(?:\s*\([^)]*\))?'  # optional parenthetical
    r'\s*\*\*')
# 两级书的**纯字母序标**条头（Shafarevich《Basic Algebraic Geometry 1》I ch3 §3.4
# Chevalley 定理 A–D 实测）：条目既无点分号也无章内单数字，type 2 分支的
# ENTRY_RE_2 / ENTRY_RE_EN_C / ENTRY_RE_EN_SINGLE_C 全部扫不到（它们都要求后随数字），
# 于是契约里已登记的四条定理在 md 侧永不出键 → A 层判 TRULY MISSING（阻断）。
# 键形与 ORDINAL_HUM 分支逐字一致：规范中文标签 + **一个空格** + 大写字母（`定理 A`），
# 与契约侧 structure_io 的字母分支（`f"{label} {letter}"`）1:1 相交。
# 🔴 三道守卫缺一不可：
#   * `(?![A-Za-z0-9])` 拒 `**Theorem An affine variety…**`（A 后紧跟 n = 散文冠词）；
#   * `\s*` + 字母必须**独立成项**，`**Theorem 3.14**` 由数字正则负责，不重复收录；
#   * 不加 IGNORECASE——字母只认大写，小写命中即散文（`**Remark a posteriori…**`）。
ENTRY_RE_TWO_LETTER_C = re.compile(
    r'\*\*(' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*([A-Z])(?![A-Za-z0-9])')
PROSE_RE_EN_C = re.compile(
    # Same CJK-aware boundaries as PROSE_RE_EN (see note there): \b fails after
    # CJK chars (「由命题 14.17」) and before digits in no-space form (命题14.17).
    r'(?<![A-Za-z0-9])(' + '|'.join(COMBINED_LABEL_KINDS) + r')(?![A-Za-z])\s*(\d+)' + SEP_TIGHT + r'(\d+)'
    + _NOT_DEEPER,
    re.IGNORECASE)
# Single-level English entries (e.g. `**Example 1**`, `**Remark 2**`) where the
# item carries ONE numeric component only (no section/item split).  This is the
# ORDINAL_EN counterpart of ENTRY_RE_EN_C for books that number some entry kinds
# chapter-wide with a single digit (Karlin & Taylor numbers its Examples 1, 2,
# … within the chapter).  The negative lookahead rejects a genuine two-level
# `**Label N.N**` (already captured by ENTRY_RE_EN_C) so it is NOT also emitted
# as a spurious single-level key `Label N`.
ENTRY_RE_EN_SINGLE_C = re.compile(
    r'\*\*(' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*(\d+)(?!\d)(?!\s*' + SEP_TIGHT + r'\s*\d+)(?![A-Za-z])',
    re.IGNORECASE)

# --- Ross（ORDINAL_ROSS = 11）：节内作用域编号，例题带字母位 ----------------
# S. Ross《A First Course in Probability》：`**Example 2a**` / `**Axiom 1**` /
# `**Proposition 4.1**`。点分两段形态由 ENTRY_RE_EN_C 覆盖；此处补两类：
#   * 字母位键 `Label N<letter>`——必须先于单数字形态匹配，否则
#     ENTRY_RE_EN_SINGLE_C 会把 "**Example 2a**" 截成 幻影键 "例2"；
#     （2026-10-09 落实：给 ENTRY_RE_EN_SINGLE_C 末尾补 `(?![A-Za-z])` 负向断言，
#       与 ENTRY_RE_ROSS_SINGLE_C 同构。只删幻影键，绝不新增键。）
#   * 单数字键 `Label N`——负向断言同时拒绝 后随字母（那是字母键）与
#     后随分隔符+数字（那是点分键），避免同一物理条目被重复/错形收录。
ROSS_LAB = '|'.join(COMBINED_LABEL_KINDS)
_SEP_CHARS = SEP_TIGHT[1:-1]      # 类内字符集（已转义）：.\-–·/．－〜
ENTRY_RE_ROSS_LETTER_C = re.compile(
    r'\*\*(' + ROSS_LAB + r')\s*(\d{1,2})\s*([A-Za-z])\b', re.IGNORECASE)
ENTRY_RE_ROSS_SINGLE_C = re.compile(
    r'\*\*(' + ROSS_LAB + r')\s*(\d{1,2})(?![\d' + _SEP_CHARS + r'A-Za-z])',
    re.IGNORECASE)
PROSE_RE_ROSS_LETTER = re.compile(
    r'(?<![A-Za-z0-9])(' + ROSS_LAB + r')(?![A-Za-z])\s*(\d{1,2})\s*([A-Za-z])(?![A-Za-z0-9])')
PROSE_RE_ROSS_SINGLE = re.compile(
    r'(?<![A-Za-z0-9])(' + ROSS_LAB + r')(?![A-Za-z])\s*(\d{1,2})(?![' + _SEP_CHARS + r'\dA-Za-z])')


def _ross_canon(label, num, suffix=''):
    """Ross 规范键：规范中文标签 + 原编号（例2a / 公理1 / 命题4.1）。"""
    return f"{_canon_label(label)}{num}{suffix}"

# EN3 (ORDINAL_EN3 / type 9): English three-level, LABEL-FIRST dots (Label C.S.N),
# e.g. Lasota & Mackey《Chaos, Fractals, and Noise》.  Items are numbered three
# deep (Remark 1.1.1 / Definition 2.3.4 / Theorem 3.2.1).  IDENTICAL in spirit to
# ORDINAL_EN but with a THIRD numeric component.  The label is captured (group 1)
# so keys_in_md can canonize it to the Chinese structure key (Remark -> 评注,
# Example -> 例, Definition -> 定义, ...) aligning with the per-chapter contract.  The
# bold `**` prefix naturally excludes FIGURE 1.1.1 / (1.1.1) figure/formula numbers
# (no label word), avoiding key collisions with the item set.
ENTRY_RE_EN3_C = re.compile(
    r'\*\*\s*(' + '|'.join(COMBINED_LABEL_KINDS) + r')\s*'
    r'(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)',
    re.IGNORECASE)
PROSE_RE_EN3_C = re.compile(
    r'(?<![A-Za-z0-9])(' + '|'.join(COMBINED_LABEL_KINDS) + r')(?![A-Za-z])'
    r'\s*(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)',
    re.IGNORECASE)

# Appendix letter-led entries in three-level EN books: "**Lemma A.1**".
# group(1)=label, group(2)=letter (A-Z), group(3)=arabic number.
ENTRY_RE_EN3_APP_C = re.compile(
    r'\*\*(' + '|'.join(COMBINED_LABEL_KINDS) + r')'
    r'\s*([A-Z])' + SEP_TIGHT + r'(\d+)',
    re.IGNORECASE)

# --- 节内无前缀单号 Example/Corollary 条头（Vakil《Rising Sea》体例）--------
# 书内把 §3.2 下的例子写成 `**Example 1**`…`**Example 8**`（不带头节的
# 三段号），而结构探测按「节内顺序」把它们登记为 `3.2-1`…`3.2-8`（type-8
# uncat 节点）。`keys_in_md` 须沿用行级「当前节号」上下文 cur_sec 把无前缀
# 单号头规整成 `标签C.S.N`（点式），交给 B 层 `_norm_path` 剥标签并折成
# `C.S-N`，与契约 1:1 对齐。仅作用于「确处于某节内」的情形；不在任何节内的
# 单号头（如章节级单号书 Karlin & Taylor 例题全章单号）退化为旧行为（裸
# `例1`），零回归。
# 节头：`**3.2.3 ...**`（裸号起始，区别于 `**Example 3.1.1**` 这类带标签
# 条头）。`>` 前缀与 `**` 之间允许空白，兼容引用块。
_SEC_HEAD_RE = re.compile(r'^\s*>*\s*\*\*(\d+)\.(\d+)')
# 无前缀单号 Example/Corollary 家族（其余标签如 Definition/Theorem 在
# Rising Sea 里始终带节号，不会落进此正则）。`(?!\d)(?!\s*SEP\s*\d+)` 拒绝
# 后随数字/分隔符数字，于是 `Example 3.1.1`（三段号）由 EN3_C 处理、不被本
# 正则误截成单号。
_SEC_SINGLE_EX_LABELS = ('Example', 'Corollary', '例', '推论')
_SEC_SINGLE_EX_RE = re.compile(
    r'\*\*\s*(' + '|'.join(_SEC_SINGLE_EX_LABELS) + r')\s*(\d+)'
    r'(?!\d)(?!\s*' + SEP_TIGHT + r'\s*\d+)',
    re.IGNORECASE)
# Figure-only 组（name ⊆ 此集）不应再用「单号 EN 正则」抓非图条头：Rising
# Sea 书 type-2 组 name=['Fig','Figure']，却被 ENTRY_RE_EN_SINGLE_C 把
# `**Example 1**` 当成两级单号条目抓成 `例1`，而契约把该例登记为 `3.2-1`
# （三级 uncat）→ md 侧凭空多一个与契约对不上的 `例1` 键。figure-only 组跳过
# 单号 EN 正则（两段 ENTRY_RE_2 / ENTRY_RE_EN_C 本就不含 Fig/Figure，跳过零损失）。
_FIGURE_LABELS = {'fig', 'figure', '图', '图形'}

# --- ORDINAL_APP (type 13)：附录字母章号三级体例 --------------------------------
# 附录标签集 = COMBINED_LABEL_KINDS（含 Exercise / 练习）去重后的元组：附录练习
# 常印成 `Exercise A.4.1`（字母章位），本表为其提供与正文同等宽的收录面。
# dict.fromkeys 去重 —— 拼接出的正则 alternation 不得带重复分支。
APP_LABEL_KINDS = tuple(dict.fromkeys(tuple(COMBINED_LABEL_KINDS) + ('Exercise',)))
# 附录的章位是**单个字母**而非数字，条目形如
#   `Definition A.1.1` / `Examples A.1.3` / `Theorem A.6.2`   （标签在前）
#   `A.1.5` / `A.4.3`                                          （裸号，原书只印编号）
# 节标题形如 `A.1 Categories` / `A.6 Adjoint Functors`。
# 规范键 = 规范中文标签 + `A.S-N`（如 `定义A.1-1`）；裸号条目键 = `A.1-5`。
# 附录章位是**单字母**（可含 C/D/M 等与罗马字符同形的字母），与罗马数字串章位
# （`[IVXLCDM]+`，可多字符）刻意分开：二者正则不可混用。
ENTRY_RE_APP_C = re.compile(
    r'\*\*(' + '|'.join(APP_LABEL_KINDS) + r')'
    r'\s*([A-Za-z])' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)',
    re.IGNORECASE)
PROSE_RE_APP_C = re.compile(
    r'(?<![A-Za-z0-9])(' + '|'.join(APP_LABEL_KINDS) + r')(?![A-Za-z])'
    r'\s*([A-Za-z])' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)',
    re.IGNORECASE)
# 裸号条目（原书只印 `A.1.5`）：md 写 `**A.1.5**`。刻意不收裸号**散文引用**——
# 正文里 `A.1.1` 这类零散大写字母+数字组合（矩阵元 / 习题号 / 公式号）太多，
# 放进 all_keys 只会给 A 层 EXTRA 刷屏。
ENTRY_RE_APP_BARE_C = re.compile(
    r'\*\*([A-Za-z])' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)')

# 两段式附录条目（附录级编号，无节号）：`**Theorem D.1**` / `**Example A.5**`
# ——Lee ISM 附录实测（Theorem D.1-D.6 / Example A.5 等）。规范键 = 规范中文标签
# + `D.1`（保留字母章位，与三段式 `定义A.1-1` 同族）；负向断言排除三段前缀
# （`A.1.1` 的 `A.1` 不得截成两段键）。裸号两段（`**D.1**`）刻意不收：
# 与公式号 `(D.1)` / 小节标题无形态区别（宁缺毋滥）。
ENTRY_RE_APP2_C = re.compile(
    r'\*\*(' + '|'.join(APP_LABEL_KINDS) + r')'
    r'\s*([A-Za-z])' + SEP_TIGHT + r'(\d+)(?!' + SEP_TIGHT + r'\d)',
    re.IGNORECASE)
PROSE_RE_APP2_C = re.compile(
    r'(?<![A-Za-z0-9])(' + '|'.join(APP_LABEL_KINDS) + r')(?![A-Za-z])'
    r'\s*([A-Za-z])' + SEP_TIGHT + r'(\d+)(?!' + SEP_TIGHT + r'\d)',
    re.IGNORECASE)



# _canon_label is imported from config (see import above) — single source
# of truth for bilingual label canonicalization.  The local copy was removed to
# avoid divergence (e.g. Example must canonize to 练习 on BOTH the md side and
# the extractor side so the exercise group routes correctly).

def _first_num(key):
    """Return the first integer found in a key string (e.g. leading chapter
    number of '定义1.1' -> 1). Returns -1 if none."""
    m = re.search(r'\d+', key)
    return int(m.group()) if m else -1

# --- 显式异章限定词（cross-chapter qualifier）---
# 正文交叉引用常带显式章限定："Proposition 5.4 of Chap. 0" / "第9章的引理 3.8" /
# "（第9章，推论 3.10）"。这类 mention 指向**别的章**的条目，不属于本章契约，
# 若进入 all_keys 会在 A 层 EXTRA（仅参考）中反复刷屏。keys_in_md 收到
# `chapter` 参数时，把「限定词章号 != 本章」的正文提及剔除；条目（加粗标签）
# 永不过滤。限定词识别：AFTER 型 "… of Chap.(ter) X"（匹配点后 20 字符内）、
# BEFORE 型 "第X章[的，、：:；]" 与 "Chap.(ter) X[,，]"（紧贴匹配点之前）。
_CHAP_QUAL_AFTER_RE = re.compile(r'[Cc]hap(?:ter|\.)?\s*(\d{1,3})')
_CHAP_QUAL_BEFORE_CN_RE = re.compile(r'第\s*(\d{1,3})\s*章\s*[的，、：:；]?\s*$')
_CHAP_QUAL_BEFORE_EN_RE = re.compile(r'[Cc]hap(?:ter|\.)\s*(\d{1,3})\s*[,，]\s*$')


def _is_foreign_chapter_ref(line, start, end, chapter):
    """该正文提及是否带「指向异章」的显式章限定词（chapter=None 时恒 False）。"""
    if chapter is None:
        return False
    m = _CHAP_QUAL_AFTER_RE.search(line, end, min(len(line), end + 20))
    if m and int(m.group(1)) != chapter:
        return True
    before = line[max(0, start - 16):start]
    mb = _CHAP_QUAL_BEFORE_CN_RE.search(before)
    if mb and int(mb.group(1)) != chapter:
        return True
    mb = _CHAP_QUAL_BEFORE_EN_RE.search(before)
    if mb and int(mb.group(1)) != chapter:
        return True
    return False


# --- 复合词尾巴守卫（单字标签 `注` 的散文幻影键）------------------------------
# 缺陷形态（2026-10-23 茆诗松《概率论与数理统计教程》ch2 实测）：正文
# 「甲、乙两赌徒赌技不相上下，各出赌注 50 法郎」里的 `注` 被
# `PROSE_RE_ROSS_SINGLE` 当成分节标签，配上后面的数量 `50` → 幻影键 `评注50`
# （`注` 经 `_canon_label` 正名为 评注）。它一边给 B 层 EXTRA-MENTION 刷出
# 需要人判的噪声，一边**能掩盖真实缺写**：若某书契约确有 `评注50` 而 md 漏写
# 条头，这条散文幻影会让缺写蒙混过关。
# 为什么不能靠「前字是中文」收窄：既有左守卫 `(?<![A-Za-z0-9])` 只管拉丁侧
# （`reTheorem`），CJK 前字必须放行——`由定理5.2`、`的例 2`、`回顾注 4.5.5`
# 全是真引用。58 本书 / 1933 个交付 md 的普查：单号散文正则的 CJK 紧邻前字命中
# 2817 处（粗体内 545 / 粗体外 2272），逐条读上下文后确认其中绝大多数由限定词或
# 动词带出（`由例 1`、`在例 2 中`、`仍以例 2`、`第 3 章例 3.2`…）。只有**前字与
# `注` 本身构成一个词**时，`注` 才不是标签。
# 表内每个词都是普查中**实际出现**过的形态，非推测：
#   赌注（数量短语，纯幻影）· 脚注 / 附注 / 旁注 / 备注（指向笔记的引用或笔记条
#   本身；契约从不按 `评注N` 登记，落在 EXTRA-MENTION 侧 = 噪声）
# 刻意**不收**（普查确证其后的 `注` 就是标签，前字属动词/名词的另一成分）：
#   回顾注 4.5.5 · 笑话题注 1.3.11 · 蕴含注 23.1.1 · 考虑例… · 见注 / 由注 /
#   的注 / 下注 / 按注 / 如注 / 及注 / 和注 / 使注 / 节注 / 章注（均为真引用）
# 🔴 两道豁免缺一不可（两侧都有实测样本）：
#   * **粗体条头内不豁免即断链**：Leinster《BCT》中文侧把 Remark 印作「备注」，
#     `**备注2.1.2**` 的键**只能**由散文正则产出——条头正则要求标签紧跟 `**`，
#     而该行 `**` 之后第一个字符是 `备`。一律拦下 = 该书 remark 全族假 truly missing。
#   * **行首条头位不豁免即误伤**：笔记条本身可以**不带粗体**直接起行——
#     Weibel《An Introduction to Homological Algebra》ch5 的 `附注 1　$H_0(B)=…`、
#     `脚注 7：回忆 spectral sequence…`，以及 数学物理方程《…》ch2 §2.3 的
#     `附注 1　本教材…` / `评注 2　本教材…`（2026-10-20 该书的修法是把这两个键
#     **登记进契约**，md 侧一直是裸行首形态）。此处「行首」按**复合词整体**判定
#     （前字之前的文本只剩引用块 / 标题 / 空白等修饰符）：若按「标签之前」判定，
#     `附注 1` 的前字 `附` 会让它显得在句中，收官书立刻新增假 truly missing。
_NOTE_WORD_TAILS = frozenset({'赌注', '备注', '脚注', '附注', '旁注'})
_NOTE_LABEL = '注'
_CJK_CHAR_RE = re.compile('[一-鿿]')
# 匹配点之前只剩引用块 / 标题 / 空白等修饰符 → 该提及是**行首条头**。
_HEAD_POSITION_RE = re.compile(r'^[\s>#*]*$')


def _in_bold_span(line, pos):
    """`pos` 是否落在粗体区间内——按 `**` 的**奇偶**走趟判定，不用「前面有 `**`」的正则。

    🔴 正则版（`\\*\\*[^*\\n]*$`）在一行里已有**闭合**粗体段时必然误判：茆诗松 ch2
    「`**例2.2.1（分赌本问题）**` …各出赌注 50 法郎」的标签位于该粗体段**之后**，
    正则仍能把「最后一个 `**` 到行尾」匹配上 → 被当成粗体内 → 守卫形同虚设。
    奇偶走趟与本项目其它围栏扫描（`_norm_text` / V-E 家族）同一口径。
    """
    return line[:pos].count("**") % 2 == 1


def _is_note_word_tail(line, label_start, label):
    """该散文命中的 `注` 是否是一个**复合词的尾巴**（赌注/脚注/…），而非条目标签。

    仅对单字标签 `注` 生效（`例`「条件」「性质」等在前字为中文时普查无一例幻影：
    它们要么本身就是完整词，要么其后的数字确实指代该词——`行列式性质 6`、
    `检验条件 2` 都是真引用）。粗体条头内、行首条头位一律不判（见上方注释）。
    """
    if label != _NOTE_LABEL or label_start <= 0:
        return False
    prev = line[label_start - 1]
    if not _CJK_CHAR_RE.match(prev):
        return False
    if prev + label not in _NOTE_WORD_TAILS:
        return False
    if _in_bold_span(line, label_start):
        return False
    # 「行首」按复合词**整体**判：前字之前的文本只剩修饰符（见上方注释）。
    if _HEAD_POSITION_RE.match(line[:label_start - 1]):
        return False
    return True


def _prose_ms(rx, line):
    """`rx` 在 `line` 上的散文提及命中，滤掉「复合词尾巴」幻影后再逐条产出。

    只包 `PROSE_*` 的调用点（条头正则 `ENTRY_*` 有 `**` 锚定，本就不可能命中
    散文短语，不经此缝）。要求各正则的**标签是 group(1)**（现状全部如此）。
    判据只此一份，避免十个调用点各写一遍而漂移。
    """
    for m in rx.finditer(line):
        if _is_note_word_tail(line, m.start(1), m.group(1)):
            continue
        yield m


def keys_in_md(path, ordinal=ORDINAL_THREE_LEVEL, groups=None,
               chapter=None):
    """Entries/all_keys from an .md file.

    `groups` is the BookConfig.ordinal GroupConfig array (new v2 form).  When
    given, EVERY group contributes its branch's keys so a multi-group config
    (e.g. 定理/定义 + 练习) parses BOTH numbering styles and unions them —
    the exercise group's two-level keys are captured alongside the theorem
    group's three-level keys.  When only `ordinal` (int) is supplied it is
    treated as a single group (back-compat shortcut).  `chapter`（可选）为该 md
    所属章号：给出时，带显式异章限定词（of Chap. X / 第X章…，X != chapter）的
    正文提及不进入 all_keys（条目标签不受影响）；缺省 None 保持旧行为。
    """
    if groups is None:
        groups = [GroupConfig(type=int(ordinal) if ordinal is not None else ORDINAL_THREE_LEVEL)]
    entries, allk = set(), set()
    try:
        lines = open(path, 'r', encoding='utf-8').readlines()
    except Exception:
        return entries, allk
    for g in groups:
        t = g.type
        cur_sec = None
        _fig_only = bool(getattr(g, 'name', None)) and set(
            x.lower() for x in g.name) <= _FIGURE_LABELS
        for line in lines:
            msec = _SEC_HEAD_RE.match(line)
            if msec:
                cur_sec = f"{msec.group(1)}.{msec.group(2)}"
            if t == ORDINAL_TWO_LEVEL:
                for m in ENTRY_RE_2.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}"
                    entries.add(key); allk.add(key)
                for m in _prose_ms(PROSE_RE_2, line):
                    if _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        continue
                    if _is_letter_slot_tail(line, m.end()):
                        continue
                    allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
                # EN 两级（原 ORDINAL_EN=4，已并入 type 2）：标签在前 / 数字在前 /
                # 章内单数字三种形态，键同 type 2 规范键，保证 4→2 重映射书 md 解析一致。
                for m in ENTRY_RE_EN_C.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}"
                    entries.add(key); allk.add(key)
                for m in ENTRY_RE_EN_SINGLE_C.finditer(line):
                    if _fig_only:
                        continue
                    key = f"{_canon_label(m.group(1))}{m.group(2)}"
                    entries.add(key); allk.add(key)
                for m in ENTRY_RE_EN_NF_C.finditer(line):
                    if _fig_only:
                        continue
                    key = f"{_canon_label(m.group(3))}{m.group(1)}.{m.group(2)}"
                    entries.add(key); allk.add(key)
                # 纯字母序标条头（`**Theorem A (Chevalley's theorem)**` → `定理 A`）：
                # 见 ENTRY_RE_TWO_LETTER_C 注释；键形须与契约侧 structure_io 的字母分支
                # 完全一致（标签 + 空格 + 大写字母）。
                for m in ENTRY_RE_TWO_LETTER_C.finditer(line):
                    key = f"{_canon_label(m.group(1))} {m.group(2).upper()}"
                    entries.add(key); allk.add(key)
                for m in _prose_ms(PROSE_RE_EN_C, line):
                    if _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        continue
                    if _is_letter_slot_tail(line, m.end()):
                        continue
                    allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
            elif t == ORDINAL_SINGLE:
                # Single-level EN book (e.g. Silverman "A Friendly Introduction to
                # Number Theory" 4th ed — ordinal type 1): items carry ONE
                # numeric component ("Theorem 1", "Lemma 1"); there is no
                # section/item split.  Previously this ordinal fell through to
                # the three-level `else` branch (ENTRY_RE / KEY_RE expecting a
                # "C.S-N" form), so NOTHING was extracted from the md and every
                # contract item surfaced as falsely truly-missing.  Reuse the
                # single-number EN regex (ENTRY_RE_EN_SINGLE_C, already applied by
                # the ORDINAL_EN branch for chapter-wide single-digit entries);
                # COMBINED_LABEL_KINDS makes it match both EN ("Theorem 2") and
                # CN ("定理2") bold heads, canonicalized to the Chinese key
                # ("定理2") that read_structure_items emits, so EN+CN both match.
                for m in ENTRY_RE_EN_SINGLE_C.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}"
                    entries.add(key); allk.add(key)
                # Ross 单级字母后缀（原 ORDINAL_ROSS=11，已并入 type 1）：
                # **Example 2a** 字母位键 + **Axiom 1** / **Proposition 4.1** 两段
                # 形态；规范键 = 规范中文标签 + 原编号（例2a / 公理1 / 命题4.1），
                # 与 read_structure_items 对齐，保证 11→1 重映射书 md 解析一致。
                for m in ENTRY_RE_ROSS_LETTER_C.finditer(line):
                    key = _ross_canon(m.group(1), m.group(2), m.group(3).lower())
                    entries.add(key); allk.add(key)
                for m in ENTRY_RE_EN_C.finditer(line):
                    entries.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
                    allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
                for m in ENTRY_RE_ROSS_SINGLE_C.finditer(line):
                    entries.add(_ross_canon(m.group(1), m.group(2)))
                    allk.add(_ross_canon(m.group(1), m.group(2)))
                for m in _prose_ms(PROSE_RE_ROSS_LETTER, line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(_ross_canon(m.group(1), m.group(2), m.group(3).lower()))
                for m in _prose_ms(PROSE_RE_EN_C, line):
                    if _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        continue
                    if _is_letter_slot_tail(line, m.end()):
                        continue
                    allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
                for m in _prose_ms(PROSE_RE_ROSS_SINGLE, line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(_ross_canon(m.group(1), m.group(2)))
            elif t == ORDINAL_APP:
                # 附录字母章号三级（type 13）：`**Definition A.1.1**` → `定义A.1-1`；
                # 裸号 `**A.1.5**` → `A.1-5`。与契约侧
                # `structure_io.read_structure_items` 的附录分支同构。
                for m in ENTRY_RE_APP_C.finditer(line):
                    key = (f"{_canon_label(m.group(1))}{m.group(2).upper()}"
                           f".{m.group(3)}-{m.group(4)}")
                    entries.add(key); allk.add(key)
                for m in ENTRY_RE_APP_BARE_C.finditer(line):
                    key = f"{m.group(1).upper()}.{m.group(2)}-{m.group(3)}"
                    entries.add(key); allk.add(key)
                for m in _prose_ms(PROSE_RE_APP_C, line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(f"{_canon_label(m.group(1))}{m.group(2).upper()}"
                                 f".{m.group(3)}-{m.group(4)}")
                # 两段式附录条目（附录级编号 `**Theorem D.1**` / `**Example A.5**`）
                # → `定理D.1` / `例A.5`（与 read_structure_items 的两段式分支同构）。
                # 🔴 宽容回退：探测层已按段数分流（两段书 → ORDINAL_APP2 走下
                # 一分支），本分支的两段正则仅供「type14 落地前误判 13」的
                # 历史 config 兼容，不再有新写入。
                for m in ENTRY_RE_APP2_C.finditer(line):
                    key = (f"{_canon_label(m.group(1))}{m.group(2).upper()}"
                           f".{m.group(3)}")
                    entries.add(key); allk.add(key)
                for m in _prose_ms(PROSE_RE_APP2_C, line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(f"{_canon_label(m.group(1))}{m.group(2).upper()}"
                                 f".{m.group(3)}")
            elif t == ORDINAL_APP2:
                # 附录字母章位两段（type 14，Lee ISM `Label B.N`）：`**Theorem B.2**`
                # → `定理B.2`；键无节段（计数器跨全附录连续）。
                for m in ENTRY_RE_APP2_C.finditer(line):
                    key = (f"{_canon_label(m.group(1))}{m.group(2).upper()}"
                           f".{m.group(3)}")
                    entries.add(key); allk.add(key)
                for m in _prose_ms(PROSE_RE_APP2_C, line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(f"{_canon_label(m.group(1))}{m.group(2).upper()}"
                                 f".{m.group(3)}")
            elif t == ORDINAL_HUM:
                for m in ENTRY_RE_HUM.finditer(line):
                    label = _canon_label(m.group(1))
                    letter = m.group(2) or ''
                    number = m.group(3) or ''
                    if letter:
                        key = f"{label} {letter.upper()}"
                    elif number:
                        key = f"{label}{number}"
                    else:
                        key = label
                    entries.add(key); allk.add(key)
                for m in _prose_ms(PROSE_RE_2, line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}")
            else:
                # 🔴 Figure-only 组（type 0 及任何非条目类型）在此 catch-all 分支无
                # 专用分支可落，会误跑通用「三级条目」正则（ENTRY_RE / _KEY_DEEP_RE /
                # ENTRY_RE_EN3_C / ENTRY_RE_EN3_APP_C / _SEC_SINGLE_EX_RE）。这些正则
                # 只认条目标签（Theorem/Definition…），与本组 name=['Figure'] 无关，
                # 于是与真条目组并排的 figure 组会把每个条目头**重复**抠一遍；更糟的是
                # 对字母序标附录头 `**Theorem A.1**`，ENTRY_RE_EN3_APP_C 还额外拆出
                # 兄弟伪键 `定理 A.1`（带空格）与 `定理1`（纯数字残迹）——契约规范键是
                # `定理A.1`（type14 分支产出，无空格），两侧永不对齐 → 假 EXTRA-ENTRY
                # （Teschl《Topics…》附录 A 实测 2 键）。figure 组本就只该产图号（而图号
                # 依 V 规则不作条目登记，见 193–194 注释），在通用分支里没有任何合法产出，
                # 故整支跳过：真条目键由其所属的条目类型分支照常抠出，绝不丢失。
                # 单调安全：只删 md 侧幻影 EXTRA 候选，不触碰任何契约对账键，
                # truly_missing / 阻断判据逐字节不变。
                if _fig_only:
                    continue
                for m in ENTRY_RE.finditer(line):
                    entries.add(normkey(m.group(1)))
                # 🔴 带深度守卫的三段号扫描（判据见 `_KEY_DEEP_RE` 上方注释）：
                # 区间写法 `第 10.4-10.6 节` / 更深一层 `1.2.3.4` 不再被截成假三段键。
                for m in _KEY_DEEP_RE.finditer(line):
                    allk.add(normkey(f'{m.group(1)}.{m.group(2)}-{m.group(3)}'))
                # EN3 / CN3LAB（原 ORDINAL_EN3=9 / ORDINAL_CN3LAB=10，已并入 type 3）：
                # 标签在前三段式 Label C.S.N（如 Lasota & Mackey `Remark 1.1.1` /
                # 孙文祥《遍历论》`定理1.1.1`），键 = 规范中文标签 + 点分三段，
                # 保证 9/10→3 重映射书 md 解析一致。
                for m in ENTRY_RE_EN3_C.finditer(line):
                    key = f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}.{m.group(4)}"
                    entries.add(key); allk.add(key)
                for m in _prose_ms(PROSE_RE_EN3_C, line):
                    if not _is_foreign_chapter_ref(line, m.start(), m.end(), chapter):
                        allk.add(f"{_canon_label(m.group(1))}{m.group(2)}.{m.group(3)}.{m.group(4)}")
                # Appendix letter-led items ("**Lemma A.1**") in three-level
                # books: read_structure_items normalizes 'A.1' to canon-label +
                # trailing number (e.g. 引理1); mirror that here so the md side
                # can match.  (2026-08-30, Leinster App A.)
                for m in ENTRY_RE_EN3_APP_C.finditer(line):
                    _cn = _canon_label(m.group(1))
                    entries.add(f"{_cn}{m.group(3)}")
                    allk.add(f"{_cn}{m.group(3)}")
                    entries.add(f"{_cn} {m.group(2)}.{m.group(3)}")
                    allk.add(f"{_cn} {m.group(2)}.{m.group(3)}")
                # 🔴 节内无前缀单号 Example/Corollary 条头（Vakil《Rising Sea》）
                # 见 _SEC_SINGLE_EX_RE 上方注释。仅当当前组是 uncat（Rising Sea
                # type-8 三级 uncat 组）且确处于某节内（cur_sec 非空）时，把
                # `**Example 1**` 规整成 `例C.S.1`（点式）→ B 层 `_norm_path` 剥
                # 标签折成 `C.S-N`，与契约的 `C.S-N` uncat 节点 1:1 对齐。其余书/
                # 情形（cur_sec 空、或非 uncat 组）不触发，退化为旧行为（裸 `例1`），
                # 对「章节级单号书」零回归。
                if cur_sec and 'uncat' in (g.name or []):
                    for m in _SEC_SINGLE_EX_RE.finditer(line):
                        key = f"{_canon_label(m.group(1))}{cur_sec}.{m.group(2)}"
                        entries.add(key); allk.add(key)
                else:
                    # 「退化为旧行为（裸 `例1`）」此前从未落地——只有 if、没有 else：
                    # 非 uncat 组（或不在任何节内）的裸单号条头 `**例1**` 会被**整体丢弃**，
                    # 契约侧忠于印面登记的键 `例1` 在 md 侧永不产出 → A 层判
                    # TRULY MISSING（阻断）。微分遍历论 ch2 §2.2.2 的 例1/例2 正是此形态：
                    # 书的例子在 §2.2.2 里按印面原生顺序编号 例1/例2，不属 C.S-N 三级体系。
                    # 兑现上方注释所述语义：产出印面原生的裸单号键（规范标签 + 数字）。
                    for m in _SEC_SINGLE_EX_RE.finditer(line):
                        key = f"{_canon_label(m.group(1))}{m.group(2)}"
                        entries.add(key); allk.add(key)
    return entries, allk

def sortkey(k):
    return tuple(int(x) for x in re.findall(r'\d+', k))
