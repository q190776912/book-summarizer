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
from lib.page_dir import resolve_page_dir
from lib.util import norm_secnum

# 本层的语义 / 阈值 / --fix 范围 / 字节契约键 的权威说明见 verify/formula_tag/formula_tag.md（SSOT）；本文件仅含实现，勿在此复述叙事。
"""formula_tag.py — Q-LAYER (order 17): FORMULA SEQUENCE-LABEL audit.

Self-contained implementation.  Verifies that every numbered display formula
in the chapter summary (`$$ ... \tag{X} $$`) maps 1:1 to a formula number that
actually exists in the book source (the set S extracted from
`page_{start..end:03d}.json` `text[].text` via per-book regex patterns derived
from the `formula` map in verify_config.json).

Two kinds of checks:

  * SEQUENCE-LABEL check (automatic FAIL):
      - FABRICATED  : a summary `\tag` number not in S (invented / mis-copied).
      - INCONSISTENT: duplicate `\tag` number, or cross-chapter number
                      (first component != current chapter when scope == 2).
  * CONTENT check (human reconciliation):
      - the summary formula LaTeX and the book-source text fragment are dumped
        side-by-side into `<extract_dir>/formula_audit.md` by `verify_all`;
        the machine does NOT judge content correctness.

Opt-in: the whole layer is a no-op (returns neutral `q_*` metadata, emits no
report, never contributes to FAIL) unless `BookConfig.formula` is a non-None
map — so the 16 legacy layers and already-finished books are untouched until a
book opts in.

S-empty degradation: if S is empty (the derived patterns matched nothing —
usually a mis-configured `formula` map), the layer only runs the structural
checks (duplicate / chapter-prefix / normalization) and emits one WARN asking
to fix the config; it does NOT judge FABRICATED / MISSING.
"""
import os
import re
import sys
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from verify.script.base import VerifyLayer, LayerResult
from lib.numbering import formula_num_core, resolve_formula_type


# Neutral no-op metadata returned when `formula` is None.  Mirrors the
# DEFAULT_RESULT defaults so report.py / verify_all always see consistent keys.
_EMPTY_Q: Dict[str, object] = {
    'q_checked': False,
    'q_fabricated': [],
    'q_inconsistent': [],
    'q_missing': [],
    'q_order_mismatch': [],
    'q_misplaced': [],
    'q_tag_mismatch': [],
    'q_rows': [],
}


def _summary_has_tags(md_file: str) -> bool:
    """True iff the chapter summary contains at least one numbered formula
    (``\\tag{...}``).  Used by the opt-in gate below to distinguish a book that
    legitimately has no labeled formulas from one whose operator simply forgot
    to configure the `formula` map."""
    try:
        with open(md_file, encoding='utf-8') as f:
            data = f.read()
    except Exception:
        return False
    return bool(_TAG_RE.search(data))

# Separator characters that any book may use between number components.
_SEP_CLASS = r'[.\-·,]'
# Letter/Roman-LED formula numbering (e.g. `(A.3)` / `（I.2）` / `(II.5)` /
# `(App.2)`) — DETECTION probe only.  Letter-led `(A.3)` (formula type 15 /
# legacy `letter_ch`) and Roman-led `(II.5)` (formula type 16, `lead='roman'`)
# ARE now captured by `norm()` / `build_formula_patterns()`, so a book that
# CONFIGURES such a family is validated normally and this probe is skipped
# (`run()` only probes digit-configured books).  The probe therefore surfaces a
# MIS-CONFIG hint: a digit book carrying letter/Roman equation numbers in its
# source gets a WARN asking the operator to select the right lead.  Only the
# multi-LETTER-WORD prefixes (`App.2` / `Ap.3`) belong to no lead family and
# stay genuinely unsupported (WARN + human reconciliation).
#
# 🔴 TIGHTENED (2026-08-16): it now matches ONLY genuine letter-led formula
# numbers so it no longer misfires on algebraic parentheticals (`(n-1)` /
# `(p-1)` / `(k-1)`) or cross-reference labels (`(Fig. 19)` / `(Chap. 9)` /
# `(Prob. 10)`).  The OLD pattern `[A-Za-z]{1,4}[.\-·,]\d+` matched all of those
# and made EVERY chapter of a digit-led book (Kreyszig) spuriously BLOCK.  A real
# letter-led formula number is: opening paren + SHORT prefix (single capital
# letter / Roman numeral / `App`/`Ap`) + `.` or `·` separator (NEVER `-` or `,`)
# + digits + optional trailing letter + closing paren.  Reference words
# (Fig/Chap/Sec/Eq/Prob/...) are excluded via negative lookahead.
#
# 🔴 2026-10-03 false-positive guard (Hogg–McKean《Introduction to Mathematical
# Statistics》): a lone capital `O` before the separator is NOT a chapter letter
# — it is the reserved big-O asymptotic-order symbol and a canonical OCR
# confusion for zero (`OCR_DIGIT` below already maps O→0).  Raw page prose such
# as the unit interval `(0,1)` and `0.1`, OCR-rendered as `(O. 1)`/`(O.0)`, was
# being mis-detected as a letter-led equation number and surfacing a spurious
# `letter_ch` mis-config WARN.  No textbook numbers a chapter "O", so we reject
# `O\s*[.·]` leads while keeping every legitimate single-letter / Roman / App
# lead (A.3, I.2, II.5, …) fully detectable.
_LETTER_LED_RE = re.compile(
    r'[（(]\s*'
    r'(?!(?:Fig|Chap|Sec|Eq|Prob|Ex|Def|Lem|Thm|Cor|Prop|Rem|Alg|Sol|Note|'
    r'Lec|Part|Vol|Appx|Tbl|Tab|Exa|Exs|Thms|Lems|Cors|Props|Defs|Rmk|Remk)\b)'
    r'(?!(?:O)\s*[.·])'
    r'(?:[A-Z]|[IVXLCDM]{1,5}|App|Ap)'
    r'\s*[.·]\s*'
    r'\d+(?:[a-zA-Z])?'
    r'\s*[）)]')
# Root fix (2026-08-16): numbered ITEM labels (Definition/Theorem/Remark/
# Example/Proposition/Corollary/Exercise/Lemma N.N.N — including common OCR
# misspellings "Defnition"/"Exercse") are NOT formula tags.  A bare (non-strong)
# pattern hit that sits immediately after one of these keywords is the item
# label, not a displayed equation; it must be skipped so it cannot pollute the
# source formula set S and force a spurious `\tag` in the summary (false green).
_ITEM_LABEL_RE = re.compile(
    r'(definition|theorem|remark|example|proposition|corollary|'
    r'exercise|lemma|defnition|exercse|figure|fig|problem|section|'
    r'equation|eq|chapter)\b'
    # 谢启鸿《高等代数》2026-09-29：中文条目标签（定义/定理/…）与中文散文
    # 交叉引用（「由推论3.6.5 可得」）此前不被识别，裸数字全部混入 S 制造
    # 假 MISSING。中文词不加 \b（CJK 与数字/汉字相邻不存在 \w 边界）。
    r'|(定义|定理|引理|推论|命题|例题|例|习题|注记|注|证明)',
    re.IGNORECASE)
# 形态③（左缘编号粘连，Apostol IANT 2026-09-28）：块首的 `(N)`，编号后可有可无
# 空白（`(16)x(a) = …` 是 OCR 无空白粘连），但后面必须还有内容（纯编号走形态①）。
_FORM3_HEAD_RE = re.compile(r'\s*[（(]\s*(\d+[a-zA-Z]?)\s*[）)]\s*[.。]?\s*(?=\S)')
# 编号之后的剩余算「数学」的证据：关系/运算符/求积符号/LaTeX 命令，或一个自括号
# 的函数群 `(n)` / `(x)`（OCR 把 |f(n)| 读成 `If(n)l` 时整块没有运算符）。
# 刻意不含裸字母词——`(12) gives us` 这类散文回指必须留在门外。
_FORM3_MATHISH_RE = re.compile(
    r'[=≤≥≠∑∫√∂∏±×÷\\^_]|[(（][^()（）\s][^()（）]{0,11}[)）]')
# 🔴 形态② 的 **latex 侧**入口（2026-09-29 阿诺尔德《经典力学的数学方法》ch10
# `(8)` 实测）：视觉/MM 修复把展示式**连同其右缘编号**一起识别成
# `formulas[].latex`（`\|w\|_C < c_1, … (8)`），于是该印刷编号从未出现在
# `text[]` 里。plain 路径的 Leading-number guard 只放行**开头**编号，
# sectioned 路径此前根本不读 `formulas[]` → 两条抽取路都漏收真实印刷号，
# 总结忠实的 `\tag{8}` 反被误判 FABRICATED。两条路改为共用下面这一个判据
# （判据只此一份；收下后仍走各自的 形态② 尾号提取，块内其余括号数字不污染 S）。
_LATEX_TAIL_NUM_RE = re.compile(r'[（(]\s*\d{1,3}[a-zA-Z]?\s*[）)]\s*[.。]?\s*$')
_LATEX_HEAD_NUM_RE = re.compile(
    r'^[（(]\s*\d{1,3}(?:[.\-·,]\d{1,3})+\s*[）)]'
    r'|^[（(]\s*[A-Z]\s*[.·]\s*\d{1,3}\s*[）)]')


def _tail_pre_guard(raw_pre: str) -> bool:
    r"""行尾 token 左侧守卫：区分「右缘印刷编号」与「数学内部的参数表」。

    🔴 入参是**未剥尾随空白**的左邻原文——「括号左边有没有空格」本身就是判据，
    剥掉就丢了这一维（Kreyszig 判据回归实测 2026-09-29：`a = 1 (1)` 与 `c_1(2)`
    在剥空白的口径下不可区分，一刀切拒数字把整章右缘标签全判掉）。

    拒收（不是标签）：
      · 与括号**黏着**的左邻字符是字母/数字/CJK/`\`（`f(x)`、`c_1(2)`、`式(3)`、
        `SO(3)`、`\sin(2)`）——印刷标签与式子之间必有空白；
      · 剥空白后以 **CJK / `\`** 收尾（`见式 (3)` 型中文交叉引用）；
      · 左侧是 **≥2 个连续的单大写字母 token**（`\boldsymbol { X }` 之类字体壳
        按一个字母计）—— 那是 `S O ( 3 )` / `T S O ( 3 )` 型李群记号
        （2026-09-29 阿诺尔德《经典力学的数学方法》ch8 + 附录E 实测：33 条以
        群记号收尾的 latex 被收进 S，制造两处假 MISSING）。
    放行：号与左侧**隔空白**的单个 token —— `f(x) \le M (9)`（单字母）、
    `b = 2 (2)`（数字）都是合法的右缘标签。
    🔴 取舍：latex **命令名**隔空白（`\phi ( 2 )`）也在放行侧——它与真空标签
    `\quad (8)`、`\circ (3)` 形态不可分，而实测噪声（上面那 33 条）里没有这种
    形态，故不为它加一张函数名白名单（命令**黏着**括号时由 ① 拒收）。
    """
    if not raw_pre or not raw_pre.strip():
        return True
    if raw_pre[-1] not in ' \t\u3000　':
        return False
    pre = raw_pre.rstrip()
    if re.search(r'[\u4e00-\u9fff\\]$', pre):
        return False
    _run = 0
    s = pre
    while True:
        m = re.search(r'(?:\\(?:boldsymbol|mathbf|mathit|mathrm|mathsf|mathtt|pmb|bm)'
                      r'\s*\{\s*[A-Z]\s*\}|[A-Z])\s*$', s)
        if not m:
            break
        _run += 1
        s = s[:m.start()].rstrip()
        if _run >= 2:
            return False
    return True


def tail_label_match(txt: str):
    r"""块尾那枚「印刷公式编号」的**唯一**判据（形态②，`text[]` 与 `formulas[].latex` 共用）。

    两个条件缺一不可：

    ① 剥掉尾随空白后，块以 `(N)`（可带句点）收尾；
    ② 那对括号**不是函数/群的参数表**——见 ``_tail_pre_guard``（判据吃**未剥空白**
       的左邻原文：`b = 2 (2)`、`f(x) \le M (9)` 这类「隔空白」的右缘标签放行，
       `c_1(2)`、`SO(3)` 这类黏着形态与 `S O ( 3 )` 型多字母群记号一律拒收）。

    返回 Match（span 覆盖 token，供调用方做 `_tail_only_span`）或 None。
    """
    s = (txt or '').rstrip()
    m = _LATEX_TAIL_NUM_RE.search(s)
    if not m:
        return None
    if not _tail_pre_guard(s[:m.start()]):
        return None
    return m


def formula_latex_text(fblk) -> str:
    """把一个 `formulas[]` 条目解包成 latex 字符串（嵌套块逐层取 text/latex/formula）。

    提取趟里 `formulas[].latex` 可能是裸字符串，也可能是 `{"text": …}` 之类的
    嵌套块；旧实现把这段解包代码写死在 plain 路径里，sectioned 路径没有它，
    两处口径因此漂移。
    """
    lx = (fblk.get('latex') or fblk.get('formula') or '') \
        if isinstance(fblk, dict) else ''
    _unw = 0
    while isinstance(lx, dict) and _unw < 4:
        lx = (lx.get('text') or lx.get('latex') or lx.get('formula') or '')
        _unw += 1
    return (lx or '').strip()


def latex_tail_token(ls: str):
    """latex 串**结尾**那枚印刷编号 token（如 `… (8)` → `'(8)'`），无则 None。"""
    m = tail_label_match(ls)
    return m.group(0) if m else None


def latex_label_candidates(ls: str) -> list:
    r"""该 latex 串是否携带「被吞进公式串里的印刷编号」？返回可消费的候选串列表。

    开头编号（Han–Lin `(4.3) \quad …`）交整条 latex（后续管线自行取号）；
    结尾编号（阿诺尔德 `… (8)`）只交**尾部那一个 token**，避免把数学内部的
    括号数字（`\varphi ( 2 )` 之类）混进 S。
    """
    if not ls:
        return []
    if _LATEX_HEAD_NUM_RE.match(ls):
        return [ls]
    tok = latex_tail_token(ls)
    return [tok] if tok else []

# Number token: 2 or 3 components (e.g. 1.17 / 11.1-1 / 3,4), optional trailing
# letter suffix (e.g. 2.3a).
_TAG_RE = re.compile(r'\\tag\{([^}]*)\}')
_BLOCK_RE = re.compile(r'\$\$(.*?)\$\$', re.S)

# ORDINAL style code -> default component count, used when the `formula` map
# supplies `type` but no explicit `depth`.  Mirrors config.ORDINAL_SECTION_TYPES
# lengths so the formula config aligns with the entry-ordinal config shape.
# Canonical `type` -> numbering-depth map.  SINGLE source of truth in
# `lib.numbering.ORDINAL_DEPTH`; depth is always derived from `type` via
# `lib.numbering.ordinal_depth`, never a second, drift-prone local copy.
from lib.numbering import (ORDINAL_DEPTH, ordinal_depth, OrdinalDepthError)

# Heading regex used to assign a book-source formula its enclosing section.
# Matches a SHORT numbered line like "2.3.2 Preliminaries" / "§2.2 Stability ..."
# / do Carmo-style dash headings "2-2 Regular Surfaces".  Separators '.', '-',
# '–' are all accepted at capture time and NORMALIZED TO '.' by _head_norm()
# so book-side (dash-printing) and summary-side (dotted) section ids compare
# equal.  Attribution rule: a formula's enclosing section is the nearest
# preceding numbered heading line (the canonical convention carried over when
# the formula-manifest subsystem's capability was merged into this Q layer).
# OCR §-glitch tolerance (2026-08, 遍历论 孙文祥): scanned math books frequently
# render the section glyph "§" as "8" / "S" / "s" ("84.1 条件期望" = "§4.1",
# "S4.2 SMB定理" = "§4.2").  The heading prefix group therefore also accepts a
# glued [Ss8] when a plausible section number follows — mirroring the D-layer's
# `^(?:§|8)` precedent (section_continuity.D_SEC_HEAD_A).  A genuine heading
# that simply starts with digit 8 ("8.4 Exercises") is untouched: the prefix
# alternative fails its lookahead and backtracks to the bare-number capture.
_HEAD_RE = re.compile(
    r'^\s*(?:§\s*|[Ss8](?=\d{1,3}[.\u2013]\d))?(\d+(?:[.\-\u2013]\d+)+)(?!\d)')


def _head_norm(s: str) -> str:
    """Normalize a captured heading number to dot-separated form."""
    return re.sub(r'[.\-\u2013]+', '.', s or '')


def _heading_num(s: str) -> Optional[str]:
    """A short numbered line's section number, or None when it is NOT a heading
    (cross-reference fragment / prose line).

    Single source of truth for "is this block a section heading?".  Consumed by
    ``_track_heading`` (advance the running heading) **and** by ``_scan_text``
    (a heading block must never anchor a formula label's position/section): the
    heading's own number is not a formula number — ch4 OCR "4.4图变换原理"
    otherwise became the definition site of ``(4.4)`` and produced ORDER +
    MISPLACED against the real label on p121.

    Also accepts a BARE section marker carrying only ``§N.N`` (no title tail):
    OCR routinely splits a heading into a number block and a title block (p49
    renders "§2.4" alone and puts the title in the following block).  Without
    this branch the running heading stays on the *previous* section and the
    next formula is attributed there (ch2 ``\\tag{2.3}`` false MISPLACED).
    """
    s = s.strip()
    hm = _HEAD_RE.match(s)
    if not hm or len(s) >= 80:
        return None
    # 🔴 例外（IDDS ch5 实测 2026-10-02）：印面 `§5.3 ε-orbits` 被 OCR 读成拉丁
    # 字母 `5.3 e-Orbits` / `5.3. e-Orbits`（本书 p124 是前形、p125/p127 是后形，
    # 三种印面同一节）。该形态恰好撞上两道「散句/OCR 残迹」守卫：
    #   ① 字母后缀残迹守卫 `\d[-.][A-Za-z]`——`6.A` / `3.4.B` 这类图号子标；
    #   ② 小写起头的尾巴判散句。
    # 于是该节标题**全书永不识别**，`_cur_heading` 永远停在 §5.2，印在 p126 的
    # (5.2)…(5.6) 五枚忠实 `\tag` 整批误判 MISPLACED。
    # 判别只认这个形状：**无内部空格**的 `小写缩写-大写字母词` 单 token。散文续行
    # 必含空格（"and it is stated…"），字母残迹必是**单**字母（`.A`/`.B`），
    # 都不满足 `[a-z]{1,5}-[A-Z][A-Za-z]{2,}`，故两道守卫一并放行的面极窄、
    # 不影响其余判据强度。
    _tail_pre = s[hm.end():].strip().strip('.').strip()
    _greek_runin = bool(re.fullmatch(r'[a-z]{1,5}-[A-Z][A-Za-z]{2,}', _tail_pre))
    if re.search(r'\d\s*[-.\u2013]\s*[A-Za-z]\b', s) and not _greek_runin:
        return None
    # 编号后紧跟闭括号/逗号/分号 = OCR 断行的引用残行，绝非标题。
    if s[hm.end():hm.end() + 1] in (')', '）', ',', '，', ';', '；'):
        return None
    tail = s[hm.end():]
    if not tail.strip() and s.startswith('§'):
        return _head_norm(hm.group(1))
    tail2 = tail.strip().strip('.').strip()
    # 小写起头的尾巴（"20.6 and it is stated…"）必为散句，非标题——
    # 唯一放行的是上面的希腊字母节题单 token 形态。
    if tail2[:1].isascii() and tail2[:1].islower() and not _greek_runin:
        return None
    if re.search(r'[A-Za-z\u4e00-\u9fff]{2}', tail2):
        return _head_norm(hm.group(1))
    return None


def _norm_anchor(s) -> str:
    """Collapse a text to an alphanumeric-only lowercase prefix for block↔node
    matching (the consolidated-exercise tail anchor).  OCR spacing differs
    between the contract's stored item text and the page block, so only letters
    and digits are compared."""
    return re.sub(r'[^0-9a-z\u4e00-\u9fff]+', '', str(s or '').lower())

# Figure-caption leader prefixes (Bug #22).  A text block whose stripped content
# STARTS with one of these keywords is a figure caption, NOT a formula-bearing
# line.  Captions may embed math (e.g. `|Φλ|`) and sub-labels like "Fig. 2.2A" /
# "Fig. 2.3(a)"; the embedded `N.N` must NOT be mistaken for a numbered display
# formula (which would fabricate a spurious source number and trigger a q-miss).
# The leading-prefix heuristic is deliberately book-agnostic.
_CAPTION_LEAD_RE = re.compile(r'^\s*(?:figure|fig\.?\b|图)', re.IGNORECASE)


def build_formula_patterns(ncomp: int, allow_bare: bool = True,
                           letter: bool = False, lead=None) -> List[str]:
    """Build source-extraction regexes from a formula key's component count.

    `allow_bare` (default True, the historical behaviour) also emits the bare
    ``N.M`` variant — any bare number token found in the source text counts as a
    formula number.  Books that sprinkle NUMBERED CROSS-REFERENCES through the
    prose (Lee: ``(Fig. 1.2)`` everywhere, plus ``1-11`` Problem labels) get a
    huge phantom source set from that variant and report every reference as a
    MISSING formula.  Such books set ``formula_bare_number: false``; only
    explicitly-marked forms — ``(N.M)`` / ``Eq. N.M`` / ``Equation N.M`` /
    ``式（N.M）`` — are then collected.

    `letter=True`（`formula.letter_ch: true`）是 `lead='letter'` 的兼容别名；
    `lead`（`digit` / `letter` / `roman`）为现代入口（派生自 `resolve_formula_type`），
    两者都缺省 → `digit`（旧行为逐字节不变）。alpha-led 编号（letter `(A.3)` /
    roman `（II.5）`，Lee ISM appendices / 罗马章位书）。The token core comes from the
    SAME single source (`lib.numbering.formula_num_core(..., lead=...)`);
    the **bare variant is never emitted** in this mode — a bare `A.3` / `II.5` is
    indistinguishable from `Fig. A.3` / section headings like `C.1` / prose roman
    counts, so only parenthesised / `Eq.`-prefixed forms are collected (宁缺勿滥).
    罗马多字母前缀（`II.5`）不再是 RESERVED——现由 formula type 码 16（`lead='roman'`）
    实现；单字母罗马头（`I.`/`V.`/`X.`…既是字母又是罗马）的重叠由整书只配一个 lead +
    `make_config.detect_formula` 保守择族消解。

    `ncomp` is the number of numeric components (the `depth` field): 2 -> `1.17`,
    3 -> `11.1-1`, 1 -> `7`.  Each returned pattern has exactly ONE capture
    group returning the raw number token; SourceFormulaIndex.norm() then
    canonicalises it.  Variants cover the common CN/EN wrappers so books with
    non-standard numbering rarely need to override the `formula` map.
    """
    if lead is None:
        lead = 'letter' if letter else 'digit'
    if ncomp is None or ncomp < 1:
        ncomp = 1
    # Capture the optional trailing letter suffix (e.g. `8.11a`) so that
    # sub-formula numbers extracted from the book source match the summary's
    # `\tag{8.11a}`.  Without this, `norm()` keeps the suffix on the summary
    # side but the source side drops it, producing FALSE FABRICATED for every
    # lettered sub-equation.  The suffix is optional, so plain `8.11` still
    # matches unchanged.
    # 🔴 编号 token 的正则核与 `lib.numbering.formula_num_core` 同源（唯一真源）：
    # attach_content 挂 tag、本层抽书源编号、完整性闸门做独立真值，三处必须读
    # 同一套形态（段数 / 分隔符 / 字母后缀 / 字母章位），否则口径漂移会互相判
    # 对方"漏/编造"。
    group = '(' + formula_num_core(ncomp, letter=letter, lead=lead) + ')'
    if lead in ('letter', 'roman'):
        # Alpha-chapter-led (letter `(A.3)` / roman `(II.5)`): parenthesised +
        # Eq.-prefixed forms only (no bare — 裸排与图注/小节标题/散文计数不可分).
        return [
            r'[（(]\s*' + group + r'\s*[）)]',   # （A.3） / (B.12) / （II.5）
            r'\bEq\.?\s+' + group,                # Eq. A.3 / Eq. II.5
            r'\bEquation\s+' + group,             # Equation A.3 / Equation II.5
        ]
    if ncomp == 1:
        # Per-section bare numbering (Kreyszig): genuine formula numbers appear
        # as a STANDALONE `(N)` / `（N）` attached to a displayed equation.
        # We must NOT capture textual *references* (`式（N）`, `Eq. N`,
        # `Equation N`) nor function-call-like parentheses (`x(0)`, `p(0)`,
        # `f(0)`), which are the dominant source of false formula numbers.
        # The negative lookbehind blocks a `(` immediately preceded by a word
        # or CJK character, so `x(0)` no longer matches while a standalone
        # `(6)` / `（7a）` still does.
        return [r'(?<![\w\u4e00-\u9fff])[（(]\s*' + group + r'\s*[）)]']
    pats = [
        r'[（(]\s*' + group + r'\s*[）)]',   # （1.17） / (1.17)
        r'\bEq\.?\s+' + group,                # Eq. 1.17
        r'\bEquation\s+' + group,             # Equation 1.17
        r'式\s*[（(]?\s*' + group,            # 式（1.17）
    ]
    # The bare `group` variant catches standalone multi-component numbers
    # (`1.17`); it is not used for the 1-level case above.
    # 🔴 Katok 2026-09-13：bare 变体此前无词边界——「Lemma 13.4.2」中段会切出
    # '3.4.2'（首数字被吞），伪造 S 条目制造假 MISSING。加数字/点负向断言。
    if ncomp != 1 and allow_bare:
        pats.append(r'(?<![\d.])' + group)     # bare 1.17（词边界保护）
    return pats


@dataclass
class FormulaTag:
    """One `$$...$$` block that carries a `\tag` (or records an empty tag)."""
    latex: str            # the full $$...$$ block
    raw_tag: str          # raw content inside \tag{...}
    normalized: str       # normed number; '' when the block has no usable tag


def _is_digit_tail(s: str) -> bool:
    """True if `s` is non-empty and consists only of digits / dots — i.e. a
    plausible OCR-truncated trailing part of a section number."""
    return bool(s) and all(c.isdigit() or c == '.' for c in s)


def _section_match(cs: str, md_sections: List[str], cur: int) -> int:
    """Greedy FORWARD match of a parsed book-section string `cs` (e.g. '2.1',
    possibly OCR-truncated like '2.1' for '2.10') to the earliest summary
    section at index >= `cur` whose number is compatible.

    Compatible = exact equality, or one string is a digit/dot prefix of the
    other (handles OCR trailing-digit drop both ways).  Returns `cur` if
    nothing matches.  Monotonicity (only advancing, never jumping back) is what
    makes the truncated-'2.10'->'2.1' case resolve correctly: by the time the
    garbled '2.1-1' (really §2.10) appears, §2.1..§2.9 have already consumed
    their markers, so the greedy pick lands on §2.10 instead of re-hitting §2.1.
    """
    n = len(md_sections)
    for j in range(cur, n):          # exact first
        if md_sections[j] == cs:
            return j
    for j in range(cur, n):          # digit-drop prefix match
        ms = md_sections[j]
        if (ms.startswith(cs) and _is_digit_tail(ms[len(cs):])) or \
           (cs.startswith(ms) and _is_digit_tail(cs[len(ms):])):
            return j
    return cur


def known_book_scopes(formula_cfg):
    """``formula.known_book`` → ``{归一号: 登记章集合 or None}``（注入判据真值）。

    登记入口 `register_formula.py` 要求逐号 `--chapter` + 印面证据，账本
    ``known_book_audit`` 因此**知道这个号印在哪一章**。旧的注入判据只看「号的首段
    == 章号」，对**编号按节重启**的书（首段是小节号，如丘维声《解析几何》ch1 §3 的
    (3.11)）必然注错章：登记在 ch1 的真号被当成 ch3 的真编号去要求 → 假 MISSING，
    运维只能把它塞进 ``ignore``（跨章污染）。
    值为 ``None`` = 该号无账本可依（存量配置）→ 判据退回「首段 == 章号」旧行为。
    """
    out: Dict[str, Optional[Set[int]]] = {}
    for x in ((formula_cfg or {}).get("known_book") or []):
        n = SourceFormulaIndex.norm(str(x))
        if n:
            out.setdefault(n, None)
    for e in ((formula_cfg or {}).get("known_book_audit") or []):
        if not isinstance(e, dict):
            continue
        n = SourceFormulaIndex.norm(str(e.get("number") or ""))
        try:
            ch = int(e.get("chapter"))
        except (TypeError, ValueError):
            continue
        if not n:
            continue
        if out.get(n) is None:
            out[n] = {ch}
        else:
            out[n].add(ch)
    return out


class SourceFormulaIndex:
    """Builds the book-source formula-number set S for a chapter.

    Only reads `text[].text` from each `page_*.json` (never the scanned
    `formulas[].latex`), applies each derived pattern, normalises the captured
    token, and groups the results under the chapter key.
    """

    def __init__(self, extract_dir: str, patterns: List[str],
                 chapter_prefix: bool = True,
                 ignore: Optional[Set[str]] = None,
                 ncomp: Optional[int] = None,
                 keep_cross_refs: bool = True,
                 known_book: object = None,
                 sections_global: bool = False) -> None:
        self.extract_dir = extract_dir
        self.patterns = [re.compile(p) for p in (patterns or [])]
        self.chapter_prefix = chapter_prefix
        self.ignore = set(ignore or set())
        # sections_global (2026-09, Loring Tu): the book numbers formulas by
        # GLOBAL section (e.g. §18 of ch5 → `(18.x)`), NOT chapter-scoped, and a
        # chapter spans several consecutive sections.  In that regime the FIRST
        # component of a formula number is a *section*, not a chapter, so the
        # chapter-first cross-chapter guard (keep iff first-comp == ch) is wrong:
        # it strips a chapter's own tags (2.1 in ch1, since 2 is another chapter
        # key) → mass false FABRICATED.  When True, build_sectioned instead keeps
        # a number iff its first component is one of THIS chapter's section keys.
        self._sections_global = sections_global
        # keep_cross_refs (default True, backward-compatible): when True, a
        # parenthesised `(C.N)` is ALWAYS kept in S even in math-free prose
        # (treated as a possible cross-reference the summary might reproduce,
        # so a summary `\tag{C.N}` is never falsely FABRICATED).  When False
        # (section-numbered books that never reproduce cross-chapter formulas),
        # parenthesised `(C.N)` inside a math-free prose block is filtered out,
        # so stray cross-references ("By (3.2) …") no longer pollute S and
        # produce false q-miss rows.  Real numbered display formulas (in a
        # math-bearing block) are still kept either way.
        self.keep_cross_refs = keep_cross_refs
        # known_book (2026-09-14): a set of normalised formula numbers that are
        # GENUINE book labels the source page-scan missed (OCR-merged into an
        # equation line, cross-reference mis-read, etc.).  These are NOT noise —
        # they are real, and the summary faithfully carries them as \tag — so
        # they must be registered as real book formulas (in S) rather than
        # hidden behind `ignore` (which would violate no-fabrication: a real
        # number must never be suppressed).  Mirrors the audit_ignore.py
        # "manual_overrides 补回真实缺项" recommendation.  Populated from
        # verify_config.json `formula.known_book` via the Q-layer run().
        self._known_book = set()
        # {号: 登记章集合}；缺登记章 → 退回「首段 == 章号」旧判据（见 known_book_scopes）
        self._known_book_scopes: Dict[str, Set[int]] = {}
        if isinstance(known_book, dict):
            for _n, _chs in known_book.items():
                if not _n:
                    continue
                self._known_book.add(_n)
                if _chs:
                    self._known_book_scopes[_n] = set(_chs)
        else:
            self._known_book = {
                SourceFormulaIndex.norm(str(x))
                for x in (known_book or [])
                if SourceFormulaIndex.norm(str(x))
            }
        # ncomp (depth) enables the Bug #18 source-noise gate in _scan_text:
        # only multi-component books (ncomp>=2) need it, because their bare
        # `N.N` pattern otherwise matches section headings / cross-references /
        # figure sub-numbers / bibliography page numbers as "formula numbers".
        self._ncomp = ncomp
        self._by_chapter: Dict[int, Set[str]] = {}
        # normalized number -> first source text snippet (for the audit report)
        self._source_text: Dict[str, str] = {}
        # 书源里**逐字带字母后缀**印过的编号（`norm_full` 值，如 `8.11a`）。
        # 集合成员用 `norm`（丢后缀，见下）以便 `(8a)` 与 `\tag{8}` 对账，但
        # 位置/定义节证据也按丢后缀的键登记，于是一本**按节重启的裸号书**
        # （depth 1，pattern 核 `\d+` 根本匹配不到 `(8a)`）里总结写
        # `\tag{8a}`/`\tag{8b}` 时，两枚后缀标签的比较对象成了别处那枚真 `(8)`
        # → 整批假 MISPLACED（nonlin ch3 实测 2026-10-02，page_090.json 印面
        # 确有 `(8a)`/`(8b)` 两个独立标签块）。豁免判据：总结标签带后缀且书源
        # 从未**逐字**印过该后缀形态 → 抽取器对它无位置证据，「无证据不判」。
        self._full_keys: Set[str] = set()
        # ORDER_MISMATCH / MISPLACED support (populated during build / build_sectioned):
        #   _primary_pos  : normalized number -> earliest (page, y) occurrence
        #   _book_section : normalized number -> book-side enclosing section (first occurrence)
        #   _cur_heading  : running "nearest preceding heading" during a scan
        self._pos_strong: Dict[str, bool] = {}
        self._sec_strong: Dict[str, bool] = {}
        # 🔴 强弱分级（IDDS ch2 实测 2026-10-02）：**强信号**（带括号 `(2.1)` /
        # `Eq. 2.1` 前缀）才是印刷标签本身；裸命中（`B(w, 2-1)` 这类数学内容经
        # 分隔符归一得到的 `2.1`）只是同形的散文/坐标。旧写法「首个命中即锚定」，
        # 于是一处行内噪声把定义位置从 §2.4 的真标签抢到了 §2.3 的散文页，忠实
        # `\tag{2.1}` 被误判 MISPLACED。规则：已有强证据时弱证据一律不得改写；
        # 强证据到来则覆盖既有弱证据（即便页码更晚）。全书只有弱证据时行为与
        # 旧写法逐字节一致（不比大小写，全按「最早」）。
        self._primary_pos: Dict[str, tuple] = {}
        self._book_section: Dict[str, str] = {}
        # Per-(section, number) membership in the book source. Unlike the global
        # `_book_section` (which only keeps the FIRST occurrence and is useless
        # for per-section-restart numbering where every section repeats (1)..(N)),
        # this maps `(sec, n) -> sec` so a formula `\tag{n}` under section `sec`
        # is "correctly placed" iff `(sec, n)` actually exists in the book.
        self._book_section_sec: Dict[tuple, str] = {}
        # Per-(section, number) earliest (page, y): for per-section-restart books
        # the GLOBAL first position of a repeated `(n)` always comes from the
        # earliest section that carries an `(n)`, so comparing global positions
        # inside a LATER section's ORDER window is meaningless noise.  The
        # sectioned ORDER walk must use the position of `n` WITHIN `sec`.
        self._pos_sec: Dict[tuple, tuple] = {}
        # Evidence support for scope==3 WARN gates (populated by build_sectioned):
        #   _sec_start_page : sec -> first page at which the walk entered `sec`
        #   _n_pages        : n -> every page carrying a standalone `(n)` label
        #   _walk_last_page : last page scanned
        # A summary `\tag{n}` under `sec` counts as correctly placed iff the
        # book recorded `(n)` somewhere inside sec's page range; absence of any
        # in-range record means the label was OCR-merged (benefit of doubt) or
        # genuinely misplaced.
        self._sec_start_page: Dict[str, int] = {}
        self._n_pages: Dict[str, Set[int]] = {}
        # 书源「同一编号被真印几次」的证据：key = (sec|None, 归一编号) -> 出现过的
        # 页集（按页去重，避免同一页的 text/formulas 双通道重复计数）。INCONSISTENT
        # 重复检测以此数为允许上限（label_limit），于是原书确实重印同一编号的两处
        # （Apostol §3.11 在印刷页 66、67 各印一次 (17)）不再被误判，而总结凭空多写
        # 一个 \tag 仍会被判。见 label_limit 的「未知即 1 = 维持原严格度」。
        self._label_pages: Dict[tuple, Set[int]] = {}
        self._walk_last_page: int = 0
        self._cur_heading: Optional[str] = None
        # Section keys of the chapter being scanned (see _load_sec_keys /
        # _repair_heading): OCR repair of a glitched heading number.
        self._sec_keys: Optional[Set[str]] = None
        # First page of the chapter-end CONSOLIDATED exercise block (see
        # _load_sec_keys): its printed numbers are excluded from S because
        # writing-rules drop that block wholesale.
        self._tail_exer_page: Optional[int] = None

    # -- public API ---------------------------------------------------------
    def build(self, ch: int, start: int, end: int) -> None:
        """Scan page_{start:03d}.json .. page_{end:03d}.json and collect S."""
        self._by_chapter = {}
        self._source_text = {}
        self._primary_pos = {}
        self._book_section = {}
        self._pos_strong = {}
        self._sec_strong = {}
        self._full_keys = set()
        self._pos_sec = {}
        self._sec_start_page = {}
        self._n_pages = {}
        self._label_pages = {}
        self._walk_last_page = 0
        self._scan_label_nums: Set[str] = set()
        self._cur_heading = None
        self._load_sec_keys(ch)
        nums: Set[str] = set()
        _pdir = resolve_page_dir(self.extract_dir, ch)
        for pg in range(int(start), int(end) + 1):
            if self._tail_page_skip(pg):
                continue
            fp = os.path.join(_pdir, f'page_{pg:03d}.json')
            if not os.path.exists(fp):
                continue
            try:
                with open(fp, encoding='utf-8') as f:
                    data = PageJson.load(fp).data
            except Exception:
                continue
            for block in data.get('text', []) or []:
                txt = block.get('text', '') if isinstance(block, dict) else ''
                if not txt:
                    continue
                # Bug #22: figure captions embed math + sub-labels that look
                # like formula numbers ("Fig. 2.2A"); skip them entirely.
                if self._is_figure_caption(txt):
                    continue
                y = None
                if isinstance(block, dict):
                    poly = block.get('poly') or []
                    if len(poly) >= 2:
                        y = poly[1]
                # 章末集中习题块：起始页只做块级剔除（锚点以上仍是正文，见
                # _locate_tail_anchor），其余页整页剔除。
                if self._in_exercise_tail(pg, y):
                    continue
                self._track_heading(txt)
                self._scan_text(txt, nums, pg, y)
                # 🔴 Number-in-latex guard（2026-09-09 Han–Lin / 2026-09-29 阿诺尔德）：
                # OCR 有时把显示公式**连同其编号**一起捕获进 `formulas[].latex`，
                # 此时编号从未出现在 `text[]`，S 漏收该真实显示编号，总结忠实的
                # \tag 反被误判 FABRICATED。补救：判据统一在 `latex_label_candidates`
                # （开头 `(C.N)` 交整条 latex，交给同一 `_scan_text` 管线复用同一
                # pattern + 归一化；结尾 `(N)` 只交那一个 token）。普通数学内容
                # 不会以 "(\d+.\d+)" 开头，也不会**只**以一枚裸括号数字收尾，
                # 故代数噪声混不进 S。letter-chapter-led `(A.3)` 开头同理放行。
                for fblk in data.get('formulas', []) or []:
                    for cand in latex_label_candidates(formula_latex_text(fblk)):
                        if self._in_exercise_tail(pg, None):
                            continue  # latex 块无 y 可判：习题起始页一律不采
                        self._scan_text(cand, nums, pg, None)
        self._by_chapter[ch] = nums
        # 🔧 known_book supplement (2026-09-14): register genuine book formula
        # numbers the source scan missed, so Q-layer no longer false-FABRICATEs
        # them.  Only numbers whose first component == ch are injected.  This is
        # the plain-path S used by _compare for FABRICATED / MISSING membership.
        if self._known_book:
            _kb = self._by_chapter.setdefault(ch, set())
            for _n in self._known_book:
                if self._kb_applies(_n, ch, _n.split('.')[0] == str(ch)):
                    _kb.add(_n)

    def build_sectioned(self, ch: int, start: int, end: int,
                        md_sections: List[str],
                        ncomp: int = 1) -> Dict[str, Set[str]]:
        """Per-section variant for books that number formulas within each
        section (Kreyszig: every section restarts at (1)).

        Walks the source pages in order and assigns each extracted formula
        number to the *current* section.  The current section is tracked from
        entry numbers (`C.S-K`, which explicitly carry their section) — far more
        OCR-robust than trying to parse section *titles*.  Returns a mapping
        ``section_key -> set(normalised numbers)`` plus the chapter-wide union.
        """
        sectioned: Dict[str, Set[str]] = {s: set() for s in md_sections}
        self._primary_pos = {}
        self._book_section = {}
        self._pos_strong = {}
        self._sec_strong = {}
        self._full_keys = set()
        self._pos_sec = {}
        self._sec_start_page = {}
        self._n_pages = {}
        self._label_pages = {}
        self._walk_last_page = int(start)
        # 🔴 谢启鸿《高等代数》2026-09-29：本书的显示公式**不另带编号**，公式
        # 的「书编号」就是所属条目号（Newton 公式 = (5.9.1)，命题两个分支各
        # 一条显示式）。条目标签的裸编号因此在 _label_pages 登记（出现证据）
        # 的同时也属于 S——总结挂 \tag{5.9.1} 完全忠实。这里先记下扫描期间
        # 收集的 item-label 编号（_scan_label_nums），build 结束后并入 union。
        self._scan_label_nums: Set[str] = set()
        # 🔴 右缘独立编号块（本卷统计书 ch11/ch12 实测）：排版把显示公式与其
        # 编号切成两个 text 块——公式块含数学记号、编号块**只有** `(11.3.10)`
        # 这类纯编号（无任何数学记号）。sectioned 路径此前对 `not _block_has_math`
        # 的块一律 continue（line 910），于是这类真实印刷编号从未进 S，忠实的
        # `\tag` 反被误判 FABRICATED（plain 路径靠 `_is_strong_signal` 保留括号
        # 号，故无此问题——两路口径不一致）。补救：把「整块就是一个公式编号」
        # （strip 尾点后对任一 pattern **fullmatch**）的号收进 _standalone_labels，
        # build 末尾并入**章级 union**（供 FABRICATED 免疫），但**不进**分节 S
        # （不新增 MISSING / 不动 ORDER·MISPLACED 证据）——最小侵入、零回归。
        self._standalone_labels: Set[str] = set()
        if md_sections:
            self._sec_start_page[md_sections[0]] = int(start)
        cur = 0  # index into md_sections
        self._load_sec_keys(ch)
        _pdir = resolve_page_dir(self.extract_dir, ch)
        for pg in range(int(start), int(end) + 1):
            if self._tail_page_skip(pg):
                continue
            fp = os.path.join(_pdir, f'page_{pg:03d}.json')
            if not os.path.exists(fp):
                continue
            try:
                with open(fp, encoding='utf-8') as f:
                    data = PageJson.load(fp).data
            except Exception:
                continue
            # Bug #23 (2026-08, Ross): chapter-opening CONTENTS pages list every
            # section title ("2.1 Introduction", ..., "2.7 ..."), and each line
            # matched the Strogatz heading advance below — sweeping `cur` to the
            # LAST section before any real content, so every formula number in
            # the chapter piled into one bucket (mass false MISSING).  Detect a
            # TOC signature page (>= 4 titled section-heading-like blocks) and
            # skip both the advance logic and number extraction on it; genuine
            # content pages virtually never start >= 4 sections.
            # title.  Fraleigh-style books print EVERY numbered item as such a
            # short heading ("3.8 Figure", "3.11 Example Find all solutions …"),
            # so a single ordinary content page easily reaches 4 of them and the
            # whole page — including its standalone `(5)` formula label — used to
            # be skipped, making a faithful `\tag{5}` read as FABRICATED.  A real
            # contents entry has a prose title, never an item-type keyword, so
            # heads whose tail starts with one do not count toward the signature.
            # 🔴 Apostol IANT ch5 p121 (2026-09-29)：签名必须**按去重后的节号**计数。
            # 该页有 80 个显示公式块（纯正文页），却因 OCR 把同一个 §5.2 节头读成
            # 两遍（`5.2:Residue classes…` 冒号形 + `5.2 Residue classes…`）再叠上
            # 两条散文回指（`5.7 If` / `5.8 We`）而凑满 4 个「带标题短头」→ 整页被判
            # 目录页跳过。真正的代价不是少收几个号，而是**节游标永远停在 §5.1**：
            # 标题推进支只认「紧邻下一节」（防路线图/回指页把 cur 提前，见上 Bug #23），
            # 于是错过唯一一次 0→1 推进后，后面每一节的节头都只能落回同一 bucket，
            # `_sec_start_page` 只有首节 → 全章 24 条 `\tag` 一律 MISPLACED。
            # 真目录页列的是**互不相同**的节，去重后仍 ≥4 → 判据强度不降。
            _titled_secs = set()
            for _b0 in data.get('text', []) or []:
                _txt = _b0.get('text', '') if isinstance(_b0, dict) else ''
                if not _txt or len(_txt.strip()) >= 80:
                    continue
                _hm0 = _HEAD_RE.match(_txt.strip())
                if _hm0:
                    _tail0 = _txt.strip()[_hm0.end():].strip().strip('.').strip()
                    if _ITEM_LABEL_RE.match(_tail0):
                        continue
                    if re.search(r'[A-Za-z\u4e00-\u9fff]{2}', _tail0):
                        _titled_secs.add(_head_norm(_hm0.group(1)))
            _is_toc_page = len(_titled_secs) >= 4
            # 🔴 编号被吞进 formulas[].latex 的兜底（与 plain 路径共用
            # `latex_label_candidates`，判据只此一份）：把「以印刷编号收尾」的
            # latex 作为**等价文本块**追加到本页趟尾——正文趟已推进过 `cur`，
            # 故该号归入它所属的节；随后走同一段 形态①/②/③ 门禁与四道守卫，
            # 不在这里复制第二套判据。
            _blocks = list(data.get('text', []) or [])
            for _fb in data.get('formulas', []) or []:
                _tok = latex_tail_token(formula_latex_text(_fb))
                if _tok:
                    _blocks.append({"text": _tok})
            for block in _blocks:
                txt = block.get('text', '') if isinstance(block, dict) else ''
                if not txt or _is_toc_page:
                    continue
                # Bug #22: skip figure-caption lines (they embed math + sub-labels
                # that look like formula numbers, e.g. "Fig. 2.2A").
                if self._is_figure_caption(txt):
                    continue
                # Advance the current section using the "section-start" signal:
                # an entry number `C.S-1` (the first definition/theorem heading
                # of a section).  Kreyszig numbers every section's first entry as
                # `C.S-1`, so this is the reliable marker across chapters.
                #
                # Bug (2026-08, Kreyszig): the marker was previously accepted
                # ANYWHERE in the text block, so chapter-opening OUTLINE pages
                # full of forward cross-references ("(cf. 9.9-1)", "theorem
                # 4.2-1 (variants 4.3-1", "(cf. 2.10-1), which is denoted")
                # dragged `cur` to a late section on page 1 of the chapter and
                # every subsequent standalone `(N)` label piled into the wrong
                # bucket — mass false MISPLACED/ORDER rows for Ch2/4/5/6/7/8/9/11.
                # A real entry heading ALWAYS *starts* its text block with the
                # marker followed by whitespace + a capitalised title
                # ("9.3-1 Definition (Monotone sequence). ..."), whereas every
                # observed prose reference either embeds the marker mid-line or
                # has ')' / ',' glued right after it (OCR line-splits keep the
                # closing paren attached: "9.2-1), and eigenvectors ...").
                # Hence: anchor at stripped-start AND require `\s` after.
                _mm_head = re.match(
                    r'\(?\s*(\d{1,3}\.\d{1,3})-(\d{1,3})(?=\s)', txt.strip())
                if _mm_head and _mm_head.group(2) == '1':
                    cs = _mm_head.group(1)
                    j = _section_match(cs, md_sections, cur)
                    if j > cur:
                        # record the start page of every newly-reached section
                        # (jumped-over sections inherit the same page — they
                        # carry no detectable heading of their own)
                        for _k in range(cur + 1, j + 1):
                            self._sec_start_page.setdefault(md_sections[_k], pg)
                        cur = j
                # Strogatz-style section advance: the book carries clean section
                # TITLES ("4.1 Examples and Definitions", "4.6 Superconducting
                # Josephson Junctions") instead of Kreyszig's `C.S-1` entry
                # markers.  Advance `cur` ONLY to the *immediate next* summary
                # section when a source heading matches it exactly (sequential
                # progression).  This prevents out-of-order section *mentions*
                # (chapter roadmaps, cross-references) on early pages from
                # jumping `cur` forward and sweeping later pages' numbers into
                # the wrong section.  A 3-level heading like `7.2.1` reduces to
                # `7.2` and still confirms the next section.  Monotonic by
                # construction (cur only ever +1).  For Kreyszig this is
                # redundant with the dash markers above and lands on the same
                # section, so behaviour is unchanged.  Without any advance
                # signal, `cur` would stick at 0 and every book number would
                # pile into the first section, producing mass false MISSING.
                # Bug #23b (Ross): starred-section headings OCR as "* 1.6 The
                # Number of ..." — leading bullet glyphs defeat _HEAD_RE.
                # Strip leading non-alphanumeric markers before matching.
                _head_src = txt.strip().lstrip('*•·◦‣-–— \t')
                _hm = _HEAD_RE.match(_head_src)
                if _hm and len(txt.strip()) < 80 and _head_src[_hm.end():_hm.end() + 1] not in (')', '）', ',', '，', ';', '；'):
                    # Title-text guard: a genuine section heading carries a
                    # textual title after the number ("5-11. Hilbert's
                    # Theorem").  Bare numeric tokens (dependence-table cells,
                    # TOC column entries like "5-11") must NOT advance cur.
                    _tail_txt = txt.strip()[_hm.end():].strip().strip('.').strip()
                    _has_title = bool(re.search(r'[A-Za-z\u4e00-\u9fff]{2}', _tail_txt))
                    # OCR junk guard: lines like "5-6.A" / "3-4.B" (letter
                    # suffix glued to the number) are figure/table artifacts,
                    # not section headings — never advance on them.
                    _junk = re.search(r'\d\s*[-.\u2013]\s*[A-Za-z]\b', txt.strip())
                    # Kreyszig-style entry markers ("1.2-3 Definition ...",
                    # OCR line-splits like "1.2-3 in the next section.) ...")
                    # start with `N.M-K`; a real section TITLE never carries
                    # the `-K` suffix.  Reject those so the sequential +1
                    # advance cannot fire on garbled entry continuations.
                    _not_entry = not re.match(
                        r'\s*\d{1,3}\.\d{1,3}\s*-\s*\d', txt.strip())
                    _hs = _head_norm(_hm.group(1))
                    _hp = _hs.split('.')
                    _h2 = '.'.join(_hp[:2]) if len(_hp) >= 2 else _hs
                    if (_not_entry and not _junk and _has_title
                            and cur + 1 < len(md_sections)
                            and _h2 == md_sections[cur + 1]):
                        cur = cur + 1
                        self._sec_start_page.setdefault(md_sections[cur], pg)
                sec = md_sections[cur] if cur < len(md_sections) else md_sections[-1]
                y = None
                if isinstance(block, dict):
                    poly = block.get('poly') or []
                    if len(poly) >= 2:
                        y = poly[1]
                # 章末集中习题块：起始页按锚点做块级剔除（锚点以上仍属正文）。
                if self._in_exercise_tail(pg, y):
                    continue
                # Only count `(N)` from genuine display-formula blocks.
                #
                # For per-section *standalone* numbering (Kreyszig, ncomp==1)
                # the only authoritative source of a numbered formula is a
                # STANDALONE bare label block — `(N)` / `（N）` optionally
                # followed by `.` or a space — i.e. the canonical formula tag
                # sitting on its own line beneath a displayed equation.  A
                # longer block that merely *contains* `(N)` inside running prose
                # ("the last sum in (13)", "From (1), with r→∞", an OCR stray
                # "(1) (b) B(x₀;r)=…") is a cross-reference / definition marker,
                # NOT a numbered formula, and must be rejected — otherwise it
                # pollutes S and produces false MISSING rows ("13"/"1") for
                # numbers the book never labels.  The general `_block_has_math`
                # heuristic (which also admits math-bearing blocks) is too loose
                # for the standalone case, so we apply the stricter bare-label
                # gate here; for multi-component books (ncomp>=2) the standalone
                # pattern rarely fires on prose and the old heuristic is kept.
                _tail_only_span = None
                if ncomp == 1:
                    if not re.fullmatch(r'\s*[（(]\s*\d+[a-zA-Z]?\s*[）)]\s*[.。]?\s*', txt):
                        # 形态②（与 _scan_text 的 plain 路径一致）：OCR 把右缘
                        # 编号并进公式行时，块「含数学记号且以 `(N)` 结尾」——
                        # 只放行块尾那一个匹配（_tail_only_span），块内部的括号
                        # 数字（因子/生成元记号等）仍被拒绝，不污染 S。
                        _rtxt = txt.rstrip()
                        _m_tail = (tail_label_match(_rtxt)
                                   if self._block_has_math(txt) else None)
                        if _m_tail is not None:
                            _tail_only_span = (_m_tail.start(), _m_tail.end())
                        else:
                            # 形态③（Apostol IANT 2026-09-28 实测）：**左缘**编号的
                            # 书把编号粘在公式行**开头**——`(12) B(x) = \sum...`。
                            # 只放行块首那一个匹配（同 _tail_only_span 机制），
                            # 于是 15 处忠实继承印刷号的 `\tag` 不再被误判
                            # FABRICATED（此前这些章因页池被 `_rehearsal` 劫持而
                            # S 全空，掩盖了本形态从未被采集的事实）。
                            # 必要条件：① 编号在块**最开头**（strip 前导空白后）；
                            # ② 编号后是公式正文而非另一段散文——判据 =
                            #   `_block_has_math(整块)` 或「编号之后的剩余里出现数学
                            #   记号 / 一个自括号的函数群」（`(16)x(a) = x(b)…` 无
                            #   空格粘连、`(26) If(n)l`＝|f(n)| 被 OCR 读成字母，
                            #   两者都过不了 `_block_has_math`，但剩余含 `=` 或 `(n)`
                            #   即足以与 `(12) gives us` 这类散文回指区分）。
                            _m_head = _FORM3_HEAD_RE.match(txt)
                            if _m_head is None:
                                continue
                            if not (self._block_has_math(txt)
                                    or _FORM3_MATHISH_RE.search(txt[_m_head.end():])):
                                continue
                            _tail_only_span = (_m_head.start(), _m_head.end())
                elif not self._block_has_math(txt):
                    # 🔴 右缘独立编号块（本卷统计书 ch11/ch12）：整块就是一个
                    # 公式编号 `(11.3.10)`（公式正文在另一块），本块无数学记号。
                    # 收下它（并入 _standalone_labels → 章级 union），否则忠实的
                    # `\tag` 被误判 FABRICATED。ncomp==1 由上面独立分支处理，这里
                    # 只管多分量书；判据=去尾点后对任一 pattern fullmatch，即「整块
                    # 除一个编号外别无他物」，散文/标题/交叉引用块不会整块等于编号。
                    if self._ncomp is None or self._ncomp >= 2:
                        _sa = txt.strip().rstrip('.。').strip()
                        for _pat_sa in self.patterns:
                            _mm_sa = _pat_sa.fullmatch(_sa)
                            if _mm_sa:
                                _n_sa = self.norm(_mm_sa.group(1))
                                if (_n_sa and _n_sa not in self.ignore
                                        and self._plausible(_n_sa,
                                                            _mm_sa.group(1))):
                                    self._standalone_labels.add(_n_sa)
                                break
                    # 🔴 谢启鸿《高等代数》2026-09-29：纯散文块里的条目标签
                    # 「定义5.9.1设…」也是一次印刷编号出现，须登记进
                    # _label_pages（按当前节分桶）供 label_limit 放宽重复检测；
                    # 只是不进 S（非公式号）。与 plain 路径 patch 同口径。
                    if self._ncomp is None or self._ncomp >= 2:
                        for _pat_lbl in self.patterns:
                            for _m_lbl in _pat_lbl.finditer(txt):
                                if not self._is_strong_signal(_m_lbl.group(0)):
                                    _pre_lbl = txt[max(0, _m_lbl.start() - 24):_m_lbl.start()]
                                    if _ITEM_LABEL_RE.search(_pre_lbl):
                                        _n_lbl = self.norm(_m_lbl.group(1))
                                        if (_n_lbl and _n_lbl not in self.ignore
                                                and self._plausible(_n_lbl, _m_lbl.group(1))):
                                            self._count_label(_n_lbl, pg, sec)
                                            getattr(self, '_scan_label_nums', set()).add(_n_lbl)
                    continue
                # extract formula numbers and attach to the current section
                for pat in self.patterns:
                    for mm in pat.finditer(txt):
                        if _tail_only_span is not None and not (
                                mm.start() >= _tail_only_span[0]
                                and mm.end() <= _tail_only_span[1]):
                            continue
                        # 🔴 双括号 OCR 残迹（Apostol ch11 p253 `'((40)'`）：编号
                        # 左缘再套一个括号 = 数学内容 `ζ(2s)` 被读成 `(20)`/`(40)`
                        # 后粘上的碎片。收下即造出一条假 MISSING（40 根本不是本书
                        # 该章的编号）。真正的编号列不会写成 `((N)`。
                        if mm.start() > 0 and txt[mm.start() - 1] in '(（':
                            continue
                        # 🔴 Katok 2026-09-13：sectioned 内联提取此前缺 _scan_text
                        # plain 路径的条目词守卫——「Proposition 1.3.3. If α is
                        # irrational」（定理头）、「0.4.1. Give an example of」
                        # （习题头：条目号后跟祈使句）、「1.9.11 Theorem1.9.11.」
                        # （OCR 复写头）、「(2.5.1), we consider」（括号散文引用）
                        # 全部混入 S，制造 729 条假 MISSING。补四道门（与 plain
                        # 路径同口径）：
                        _pre = txt[max(0, mm.start() - 24):mm.start()]
                        if _ITEM_LABEL_RE.search(_pre):
                            # 🔴 谢启鸿《高等代数》2026-09-29：条目标签
                            # 「命题 5.9.1(Newton 公式)」的裸编号不进 S（不是公
                            # 式号），但原书确实在此印刷了该编号；同一编号同章
                            # 多处分印时，总结按书逐处挂 \tag 忠实，须登记「真
                            # 标签出现」供 label_limit 放宽（与 plain 路径同口径）。
                            _n_lbl = self.norm(mm.group(1))
                            if (_n_lbl and _n_lbl not in self.ignore
                                    and self._plausible(_n_lbl, mm.group(1))):
                                self._count_label(_n_lbl, pg, sec)
                            continue  # ① 条目词前缀（Proposition 1.3.3 / (cf. Definition 1.9.3)）
                        _rest = txt[mm.end():mm.end() + 48]
                        # ①' 块首裸号 + 紧跟句点 = 条目/习题头（Katok 实测 2026-10-03：
                        #     「2.4.7. If f is close to Ek」「2.9.3. For w E S2 let」
                        #     「15.2.2. Given e > 0」——③的动词表枚举不完，见
                        #     `_bare_item_head`）。与 ②③ 同口径：不进 S、不锚位。
                        if self._bare_item_head(txt, mm.start(), mm.end(),
                                                self._is_strong_signal(mm.group(0))):
                            continue
                        if re.match(
                                r'[\.\。]?\s*(?:definition|theorem|remark|example|proposition|corollary|exercise|lemma|定义|定理|引理|推论|命题|例|习题|注)\b',
                                _rest, re.IGNORECASE):
                            continue  # ② 编号后紧跟条目词（OCR 复写头「1.9.11 Theorem1.9.11.」）
                        if re.match(
                                r'[\.\。]\s*(?:Give|Prove|Show|Define|Let|Suppose|Consider|Find|Construct|Formulate|Describe|Generalize|Disprove|Every|Each)[A-Za-z]*\b',
                                _rest, re.IGNORECASE):
                            continue  # ③ 条目号 + 祈使句 = 习题头（「0.4.1. Give an example of」；
                            #     词尾用 `[A-Za-z]*` 而非 `\b`：否则变形「Given e > 0 construct…」
                            #     这类最常见习题起句因词干后失配而漏网。
                        if _rest[:1] in (',', ';', '，', '；'):
                            continue  # ④ 括号号后紧跟逗号/分号 = 散文交叉引用（「(2.5.1), we consider」）
                        raw = mm.group(1)
                        n = self.norm(raw)
                        if not n or n in self.ignore or not self._plausible(n, raw):
                            continue
                        sectioned[sec].add(n)
                        self._full_keys.add(self.norm_full(raw) or n)
                        # first occurrence's section == book-side definition section
                        # （嵌入引用不作为定义节证据 —— 见 _embedded_ref）
                        if not self._embedded_ref(txt, mm.start(), mm.end()):
                            if n not in self._book_section:
                                self._book_section[n] = sec
                            # 「真标签出现」计数：与 plain 路径 _scan_text 同一
                            # 谓词（非嵌入引用），供 label_limit 放宽重复检测。
                            self._count_label(n, pg, sec)
                            self._record_pos(n, pg, y,
                                             strong=self._is_strong_signal(mm.group(0)))
                        # (sec, n) membership — authoritative for per-section books
                        self._book_section_sec[(sec, n)] = sec
                        # per-(sec, n) earliest position — the ORDER window of a
                        # per-section-restart book must compare positions WITHIN
                        # the section, not global first occurrences (which for a
                        # repeated `(n)` always come from the earliest section).
                        _pk = (sec, n)
                        if not self._embedded_ref(txt, mm.start(), mm.end()):
                            _pp = self._pos_sec.get(_pk)
                            if _pos_better((pg, y), _pp):
                                self._pos_sec[_pk] = (pg, y)
                        self._n_pages.setdefault(n, set()).add(pg)
                        if pg > self._walk_last_page:
                            self._walk_last_page = pg
                        # capture a short book-source snippet for the audit so
                        # MISSING rows can be judged real-vs-OCR-noise
                        if n not in self._source_text:
                            span = mm.group(0)
                            idx = txt.find(span)
                            if idx < 0:
                                idx = 0
                            snippet = txt[max(0, idx - 20): idx + len(span) + 20]
                            self._source_text[n] = snippet[:60]
        # 🔴 Katok 2026-09-13：en3 体例（标签首组件=章号）下，跨章引用（如 ch5
        # 引用 ch1 的 (1.5.6)）会混入本章 S，按节对账判假 MISSING。两道过滤：
        # ①确定性（优先）：首组件 ∈ 书章号集且 ≠ 当前章 → 跨章引用，剔除
        #   （多数决在自有公式少的章会失效——ch11/ch16/ch19 实测）；
        # ②多数决兜底：书章号集不可用时，首组件多数 == 当前章才启用同款过滤。
        # 🔴 该过滤仅在**多分量**编号（ncomp>=2，如 Katok "(1.5.6)"、en3 体例
        # 标签首组件=章号）下有意义：此时 n.split('.')[0] 才是「章位」token，
        # 可用来剔除跨章引用。对**单分量节级编号**（ncomp==1，如 Kreyszig /
        # 常庚哲史济怀《数学分析教程》每节从 (1) 重排的裸号）而言，编号本就没有
        # 章位分量，n.split('.')[0] == 整个编号，与「章号」毫无关系；若照常过滤，
        # 会把所有恰好等于某个合法章号的真实公式号（裸 "1".."18"）当作跨章引用误删，
        # 只留下与当前章号巧合相等的那一个，导致大面积假 FABRICATED。故 ncomp==1
        # 时整段跳过。
        _is_multi = (ncomp is None or ncomp >= 2)
        if self._sections_global and _is_multi:
            # Global-section numbering: the leading component of a number is a
            # SECTION, not a chapter. Keep a number iff its leading integer is
            # one of THIS chapter's section keys (from the summary md_sections);
            # drop cross-section refs + DOI/footer noise. This is the sections_
            # global analogue of the chapter-first guard below (which is wrong
            # here and would mass-false-FABRICATE the chapter's own tags).
            _seckeys = set()
            for _s in (md_sections or []):
                _m = re.match(r'(\d+)', str(_s))
                if _m:
                    _seckeys.add(_m.group(1))
            if _seckeys:
                for _s in sectioned:
                    sectioned[_s] = {
                        n for n in sectioned[_s]
                        if n.split('.')[0] in _seckeys
                    }
        elif _is_multi:
            from collections import Counter as _C
            _cnt = _C(n.split('.')[0] for s in sectioned.values() for n in s)
            _book_chs = {str(k) for k in (getattr(self, '_book_chapter_keys', None)
                                          or set())}
            _majority = (bool(_cnt)
                         and _cnt.get(str(ch), 0) * 2 > sum(_cnt.values()))
            if _majority or _book_chs:
                for _s in sectioned:
                    sectioned[_s] = {
                        n for n in sectioned[_s]
                        if n.split('.')[0] == str(ch)
                        or (n.split('.')[0] not in _book_chs and not _majority)
                    }
        # chapter-wide union (used for FABRICATED so source-section misalignment
        # can never produce a false FABRICATED)
        union: Set[str] = set()
        for s in sectioned.values():
            union |= s
        # 🔧 known_book supplement (2026-09-14): genuine book formula numbers the
        # source scan missed — inject into the chapter-wide union so FABRICATED
        # (which tests against this union) no longer false-flags them.  MISSING
        # is already suppressed per-section via the summary's covered_anywhere.
        if self._known_book:
            _kb_multi = (ncomp is None or ncomp >= 2)
            # For sections_global books the leading component of a known_book
            # number is a SECTION, not the chapter number, so matching it
            # against `str(ch)` would wrongly skip it.  Collect this chapter's
            # section keys and accept a known_book number whose leading
            # integer is one of them (Tu: §9.3/§9.4 live in ch3 §8-14).
            _kb_secs = set()
            if self._sections_global:
                for _s in (md_sections or []):
                    _m = re.match(r'(\d+)', str(_s))
                    if _m:
                        _kb_secs.add(_m.group(1))
            for _n in self._known_book:
                _lead = _n.split('.')[0]
                if self._kb_applies(_n, ch, (not _kb_multi) or _lead == str(ch) or (
                        self._sections_global and _lead in _kb_secs)):
                    union.add(_n)
                    self._by_chapter.setdefault(ch, set()).add(_n)
        # 🔴 谢启鸿《高等代数》2026-09-29：条目标签编号（_scan_label_nums，
        # 如 Newton 公式 (5.9.1)）是本书对显示公式自身的编号——并入 union，
        # 使总结忠实的 \tag 不被误判 FABRICATED；同时 MISSING 语义保持一致
        # （书印了编号而总结整条公式未写 → 仍应报 MISSING）。
        for _n in getattr(self, '_scan_label_nums', set()) or set():
            union.add(_n)
            self._by_chapter.setdefault(ch, set()).add(_n)
        # 🔴 右缘独立编号块（本卷统计书 ch11/ch12）：并入章级 union 供 FABRICATED
        # 免疫，但**不进**分节 S——因此不新增 MISSING、不动 ORDER·MISPLACED 证据。
        for _n in getattr(self, '_standalone_labels', set()) or set():
            union.add(_n)
            self._by_chapter.setdefault(ch, set()).add(_n)
        return {'_sectioned': sectioned, '_union': union}

    def _kb_applies(self, num: str, ch, legacy_ok: bool) -> bool:
        """known_book 号是否该注入本章 S：登记章优先，无账本则用旧判据。"""
        chs = self._known_book_scopes.get(num)
        if chs:
            try:
                return int(ch) in chs
            except (TypeError, ValueError):
                return False
        return legacy_ok

    def numbers_for_chapter(self, ch: int) -> Set[str]:
        return set(self._by_chapter.get(ch, set()))

    def all_numbers(self) -> Set[str]:
        out: Set[str] = set()
        for s in self._by_chapter.values():
            out |= s
        return out

    def source_text(self, n: str) -> str:
        return self._source_text.get(n, '')

    def _count_label(self, n: str, pg, sec=None) -> None:
        """Record one occurrence of a **printed label** (not a prose ref).

        Deduplicated per page so the same typeset number cannot be counted
        twice through the two extraction channels (`text[]` and a leading-label
        `formulas[].latex`).
        """
        if not isinstance(pg, int):
            return
        self._label_pages.setdefault((sec, n), set()).add(pg)

    def label_limit(self, n: str, sec=None) -> int:
        """How many summary ``\\tag``\\ s for ``n`` are source-faithful.

        Returns the number of distinct source pages carrying that label in that
        bucket, and **1 when the source has no record for the key** — i.e. a
        number with no counted occurrence keeps the pre-existing strict
        duplicate behaviour, so this can only ever relax false positives, never
        tighten.  ``sec=None`` is the chapter-scoped (plain path) key.
        """
        pages = self._label_pages.get((sec, n))
        return len(pages) if pages else 1

    def primary_pos(self, n: str):
        """Earliest (page, y) occurrence of `n` (definition site), or None."""
        return self._primary_pos.get(n)

    def book_section(self, n: str):
        """Book-side enclosing section of `n`'s definition, or None."""
        return self._book_section.get(n)

    def source_numbers(self) -> Set[str]:
        """All book-source formula numbers this index extracted (works for both
        the plain `build()` and the sectioned `build_sectioned()` paths — neither
        relies on `_by_chapter`, which only the plain path populates)."""
        return set(self._primary_pos.keys())

    # -- helpers ------------------------------------------------------------
    def _track_heading(self, txt: str) -> None:
        """Update the running nearest-preceding-heading from a short numbered
        line (e.g. "2.3.2 Preliminaries").  A formula's enclosing section is the
        nearest preceding heading line.
        """
        h = _heading_num(txt)
        if h is None:
            return
        self._cur_heading = self._repair_heading(h)

    def _load_sec_keys(self, ch) -> None:
        """Section keys of THIS chapter (plus the consolidated-exercise tail
        page) from the structure contract.

        Populated per build; ``None`` when the contract is unavailable, which
        makes ``_repair_heading`` a no-op (identical to the pre-repair
        behaviour).
        """
        self._sec_keys = None
        self._tail_exer_page = None
        self._tail_exer_anchor_y = None
        try:
            from data.book_structure.book_structure import chapter_json_path
            fp = chapter_json_path(self.extract_dir, ch)
            if not fp or not os.path.exists(fp):
                return
            with open(fp, encoding='utf-8') as f:
                tree = json.load(f)
            keys: Set[str] = set()
            # (page_start, norm_name) of every consolidated node.
            cons: List[tuple] = []
            # Last page covered by ANY section of this chapter: a consolidated
            # node qualifies as the chapter-end tail block ONLY if it begins
            # strictly beyond every section's coverage.  谢启鸿《高等代数》
            # 2026-09-29: some contracts mark the PER-SECTION "习题 N.S" blocks
            # consolidated too (scattered through the chapter); taking
            # min(page_start) over ALL of them amputated the whole chapter body
            # from S from the first mid-chapter exercise page onward -> mass
            # false FABRICATED.  A page_start threshold alone is still too
            # eager: ch4/7/8/9 per-section exercise pages start after the last
            # section's page_start yet INSIDE the section flow (contract page
            # ranges overlap section bodies) and carry real printed formulas
            # ((9.10.4) etc).  Compare against the last section's page_END
            # (fall back to its page_start): only blocks starting beyond every
            # section's coverage are chapter-end tails.  Mid-chapter
            # consolidated nodes are therefore never tail candidates (old
            # pre-tail-gate behaviour = no exclusion).  With no section nodes
            # at all, keep the legacy min-over-all behaviour.
            last_sec_end: Optional[int] = None
            stack = [tree]
            while stack:
                node = stack.pop()
                if not isinstance(node, dict):
                    continue
                if node.get('type') == 'section' and node.get('key'):
                    keys.add(str(node['key']))
                    _p0 = node.get('page_start')
                    _pe = node.get('page_end')
                    _pe = _pe if isinstance(_pe, int) else (
                        _p0 if isinstance(_p0, int) else None)
                    if _pe is not None and (last_sec_end is None
                                            or _pe > last_sec_end):
                        last_sec_end = _pe
                if node.get('consolidated'):
                    p = node.get('page_start')
                    if isinstance(p, int):
                        cons.append((p, _norm_anchor(node.get('name'))))
                stack.extend(node.get('sub_sec') or [])
            tail: Optional[int] = None
            tail_names: Set[str] = set()
            _cand = [c for c in cons
                     if last_sec_end is None or c[0] > last_sec_end]
            _pool = _cand if (_cand or last_sec_end is not None) else cons
            for _p, _nm in _pool:
                if tail is None or _p < tail:
                    tail = _p
                    tail_names = set()
                if _p == tail and _nm:
                    tail_names.add(_nm)
            self._sec_keys = keys or None
            self._tail_exer_page = tail
            # 🔴 尾块锚点按**块**而非按**页**界定（Apostol IANT 2026-09-28 实测）：
            # 章末集中习题块的起始页往往**同时**载有该章最后几个显示公式——
            # ch6 (12)@y415、ch7 (20)(21)、ch13 (36) 都在习题起始页的上半部，
            # 旧的「pg >= tail 整页剔除」把这几条真实印刷编号一起丢掉，忠实的
            # `\tag` 反被误判 FABRICATED。补救：在该页里用习题条目自身的文本
            # （契约 consolidated 节点 name 的归一前缀，且块长 >=40 以避开页眉
            # 重复的「Exercises for Chapter N」running head）定位首个习题块，记下
            # 它的 y 作为锚点；锚点之上的块照常入 S，之下（含其后整页）仍剔除。
            # 找不到锚点时 `_tail_exer_anchor_y` 保持 None → 退回旧行为（整页剔除），
            # 不会给任何书新放开一页习题噪声。
            self._tail_exer_anchor_y = self._locate_tail_anchor(ch, tail, tail_names)
        except Exception:
            self._sec_keys = None
            self._tail_exer_page = None
            self._tail_exer_anchor_y = None

    def _locate_tail_anchor(self, ch, tail: Optional[int],
                            tail_names: Set[str]) -> Optional[float]:
        """y of the first exercise-item block on the tail page, or None."""
        if not isinstance(tail, int) or not tail_names:
            return None
        fp = os.path.join(resolve_page_dir(self.extract_dir, ch),
                          f'page_{tail:03d}.json')
        if not os.path.exists(fp):
            return None
        try:
            with open(fp, encoding='utf-8') as f:
                data = PageJson.load(fp).data
        except Exception:
            return None
        best: Optional[float] = None
        for block in data.get('text', []) or []:
            txt = block.get('text', '') if isinstance(block, dict) else ''
            if not txt or len(txt.strip()) < 40:
                continue
            poly = block.get('poly') or []
            if len(poly) < 2:
                continue
            _n = _norm_anchor(txt)
            # 窗口比较：块文本可能带习题序号前缀（"1.LetG…"），OCR 字形残损也
            # 只发生在前缀之后，故取 name 归一后的前 22 个字母数字判「在块内」。
            if any(len(tn) >= 16 and tn[:22] in _n for tn in tail_names):
                y = poly[1]
                if isinstance(y, (int, float)) and (best is None or y < best):
                    best = float(y)
        return best

    def _tail_page_skip(self, pg) -> bool:
        """Page-level tail test: skip the whole page only when NO block of it
        can survive the tail gate (beyond the tail page, or the tail page
        itself while the exercise anchor is still unknown)."""
        tail = self._tail_exer_page
        if tail is None or not isinstance(pg, int) or pg < tail:
            return False
        return pg > tail or getattr(self, '_tail_exer_anchor_y', None) is None

    def _in_exercise_tail(self, pg, y=None) -> bool:
        """Is this block (page `pg`, top-y `y`) inside the chapter-end
        CONSOLIDATED exercise block?

        Strogatz 3e ch13 (2026-09-27 实测)：题 13.6.5 (Ott-Antonsen) 里的
        `(13)`/`(14)` 是**印刷编号**，而 writing-rules「有专门习题小标题的集中
        习题块一律省略」+ `unit_node_entries` 对 ``consolidated`` 节点不出单元
        → 该块内容**按设计**不进总结。此前 S 仍收这些号，MISSING 硬闸反过来
        要求写手把习题答案写成正文公式。故：契约标了 consolidated 的起始页
        及其后一律不入 S。非集中块书（无该标记）行为零改动。

        ``y`` 非空时判**块**不判页：起始页上半部仍属正文（章末最后几个显示
        公式与习题块同居一页），只有锚点及以下才剔除；无锚点（或调用方没给
        y）时退回旧的整页剔除。
        """
        tail = self._tail_exer_page
        if tail is None or not isinstance(pg, int) or pg < tail:
            return False
        if pg > tail:
            return True
        anchor = getattr(self, '_tail_exer_anchor_y', None)
        if anchor is None or y is None:
            return True
        return float(y) >= anchor

    def _repair_heading(self, h: str) -> str:
        """OCR repair of a heading number against THIS chapter's real section
        keys.

        A section glyph mis-read as a digit glues onto the number
        ("56.4周期点" = "§6.4周期点") and would otherwise become the enclosing
        section of every following formula → false MISPLACED (ch6 ``\\tag{6.1}``).
        Only rewrites when the FULL number is not a section of this chapter AND
        a leading-digit-trimmed variant IS: a genuine ``56.4`` (a book that
        really has §56.4) matches the contract and is kept verbatim.
        """
        known = self._sec_keys
        if not known or h in known:
            return h
        cand = h
        while len(cand) > 1 and cand[0].isdigit():
            cand = cand[1:]
            if cand in known:
                return cand
        return h

    def _record_pos(self, n: str, pg, y, strong: bool = False) -> None:
        """Record the earliest (page, y) occurrence of `n` (its definition site).

        「None = 页级/无锚点证据」的处理与 `_pos_sec` 写路径共用 `_pos_better`
        一个判据（原内联的分支表与它等价，此处收敛以免再出现「一处修 None、
        另一处照旧裸比较元组」的漏网）。

        🔴 强弱分级（IDDS ch2 实测 2026-10-02）：**强信号**（带括号 `(2.1)` /
        `Eq. 2.1` 前缀）才是印刷标签本身；裸命中（`B(w, 2-1)` 这类数学内容经
        分隔符归一得到的 `2.1`）只是同形的散文/坐标。旧写法「首个命中即锚定」，
        于是一处行内噪声把定义位置从 §2.4 的真标签抢到了 §2.3 的散文页，忠实
        `\tag{2.1}` 被误判 MISPLACED。规则：已有强证据时弱证据一律不得改写；
        强证据到来则覆盖既有弱证据（即便页码更晚）。全书只有弱证据时行为与
        旧写法逐字节一致（不比大小写，全按「最早」）。
        """
        prev_strong = self._pos_strong.get(n)
        if prev_strong and not strong:
            return
        if _pos_better((pg, y), self._primary_pos.get(n)) or (strong and not prev_strong):
            self._primary_pos[n] = (pg, y)
            self._pos_strong[n] = bool(strong)

    def _update_pos(self, n: str, pg, y, strong: bool = False) -> None:
        """Record earliest position AND anchor the book-side section to the
        first occurrence's enclosing heading (the definition location).

        定义节证据与位置证据同一强弱分级（见 `_record_pos`）：弱命中不得再
        抢占已登记的节，强标签可覆盖弱登记。
        """
        self._record_pos(n, pg, y, strong=strong)
        if self._cur_heading is None:
            return
        if self._sec_strong.get(n) and not strong:
            return
        if n not in self._book_section or (strong and not self._sec_strong.get(n)):
            self._book_section[n] = self._cur_heading
            self._sec_strong[n] = bool(strong)

    def _scan_text(self, txt: str, nums: Set[str], pg=None, y=None) -> None:
        # 单分量书（ncomp==1，Kreyszig/Fraleigh 式裸 `(N)`）的 plain-path 门禁：
        # 真公式编号只有两种形态——①「独立成行的标签块」`(N)` / `（N）`
        # （fullmatch，与 build_sectioned 对 ncomp==1 的门禁一致）；②OCR 把右缘
        # 编号并进公式行时的「含数学记号且以 `(N)` 结尾」的块（Kreyszig 夹具
        # `'3.1-1 Theorem. We define a = 1 (1).'` 即此形态）。②形态**只提取块尾
        # 那一个匹配**——否则块内部的括号数字（阶乘 `n!=n(n-1)…(3)(2)(1)` 的
        # 因子、习题 `H=(4)` 的生成元记号等）会全部混入 S 制造假 MISSING
        # （2026-08 Fraleigh 案例）。其余——散文交叉引用 ("By (3) ...")、习题
        # 列表、函数调用结尾等——一律拒绝。（此前 plain 路径对 ncomp==1 完全不设
        # 门禁，仅依赖 scope==3 的 sectioned 路径兜底；对无 `## §` 扁平结构的
        # 稀疏编号书会整章失守。）
        _tail_only_span = None
        if self._ncomp == 1:
            _t = (txt or '').strip()
            if not re.fullmatch(
                    r'\s*[（(]\s*\d+[a-zA-Z]?\s*[）)]\s*[.。]?\s*', _t):
                _m_tail = None
                if self._block_has_math(_t):
                    _m_tail = tail_label_match(_t)
                if _m_tail is None:
                    return
                # 只放行块尾这一个匹配：把它的原始 txt 坐标区间记下来。
                _off = len(txt) - len(txt.lstrip()) if txt else 0
                _tail_only_span = (_off + _m_tail.start(),
                                   _off + _m_tail.end())
        # 🔴 Bug #18 修复（增强）：多分量编号 (ncomp>=2) 的 bare `N.N` pattern
        # 会命中节标题 ("1.1 Introduction")、图号子图 ("Fig. 1.1a")、参考文献
        # 页码 ("pp. 1-34") 等散文数字串——这些非公式编号须被拦截，否则污染
        # 书源集合 S，制造假 MISSING。但「括号包裹的公式编号」`(C.N)` 是书源
        # 与 summary 共用的强信号：既用于标注公式，也用于散文交叉引用
        # ("By (3.1) we get A.")。一刀切门禁会把散文里的 `(3.1)` 漏抽，导致
        # summary 合法的 \tag{3.1} 被误判 FABRICATED、且 S 不全。
        # 策略：仅对「裸 / 无强前缀」命中施加 _block_has_math 门禁；带括号或
        # 带 Eq./Equation/式 前缀的命中（强信号）无条件保留。ncomp==1 不门禁。
        need_gate = (self._ncomp is not None and self._ncomp >= 2)
        has_math = self._block_has_math(txt) if need_gate else True
        # 🔴 锚点分级用的「这块像不像一枚印出来的标签」：
        #   ①整块**就是一个编号**（右缘标签被 OCR 切成独立块）——`_block_has_math`
        #     的短块豁免只到 8 字符，那是为 Kreyszig 式单分量 `(N)` 设的，多分量
        #     书的 `(11.1.15)` 有 10 字符、且不含任何数学记号，**不被它认作数学块**
        #     （Lasota-Mackey ch11 实测：真标签 p356 y=1605 因此被降级成弱证据，
        #     反倒让 p358 那句含 `>` 的散文回指以「强信号」取胜 → 顺序假阳）；
        #   ②该块含数学记号（标签并进公式行尾/行首）。
        # 二者取并集，与 `build_sectioned` 的「standalone 或 has_math」同一口径。
        _t_alone = (txt or '').strip().rstrip('.。').strip()
        _standalone_blk = bool(_t_alone) and any(
            _p.fullmatch(_t_alone) for _p in self.patterns)
        _label_grade = has_math or _standalone_blk
        for pat in self.patterns:
            for m in pat.finditer(txt):
                if _tail_only_span is not None and not (
                        m.start() >= _tail_only_span[0]
                        and m.end() <= _tail_only_span[1]):
                    continue
                span = m.group(0)
                raw = m.group(1)
                # 🔴 谢启鸿《高等代数》2026-09-29（ItemLabelExampleExemption
                # 同源）：条目标签「命题 5.9.1(Newton 公式)」「定义5.9.1设…」的
                # 裸编号不进 S（不是公式号），但**原书确实在此印刷了该编号**——
                # 同一编号在同章多处分印（Newton 公式 k≤n-1 / k≥n 两个分支各印
                # 一次）时，总结按书逐处挂 \tag 是忠实的，须把条目标签本身登记
                # 为一次「真标签出现」，label_limit 才会放宽到印刷次数；否则第二
                # 个 \tag 被误判 INCONSISTENT。判定先于 has_math 门禁：条目标签
                # 行的余文常是纯散文（无数学记号），先被数学门禁吞掉就连「标签
                # 出现过」都登记不上。未知即 1 的严格度不变。
                if not self._is_strong_signal(span):
                    _pre = txt[max(0, m.start() - 24):m.start()]
                    if _ITEM_LABEL_RE.search(_pre):
                        _n_lbl = self.norm(raw)
                        if (_n_lbl and _n_lbl not in self.ignore
                                and self._plausible(_n_lbl, raw)):
                            self._count_label(_n_lbl, pg)
                            getattr(self, '_scan_label_nums', set()).add(_n_lbl)
                        continue
                # 与 sectioned 路径 ①' 同口径：块首裸号 + 紧跟句点 = 条目/习题头，
                # 既不进 S 也不锚位（Katok 2026-10-03：一处习题头就能把真标签
                # 顶成 ORDER_MISMATCH 假阳）。
                if self._bare_item_head(txt, m.start(), m.end(),
                                        self._is_strong_signal(span)):
                    continue
                if need_gate and not has_math and (
                        not self.keep_cross_refs or not self._is_strong_signal(span)):
                    continue
                # Root fix (2026-08-16): a figure sub-caption label such as
                # "Figure 1.1.1b" / "Fig. 2.2A" matches the lettered-sub-equation
                # pattern but is NOT a numbered formula.  Real formula sub-
                # equations appear as a STANDALONE `(8.11a)` (no adjacent
                # "Figure" keyword) and stay captured.  Skip the figure-anchored
                # case so it cannot fabricate a spurious source number
                # (false q-miss).  Book-agnostic: only fires when the figure
                # keyword directly precedes the numbered sublabel.
                if re.search(r'\bfig\w*\.?\s+\d+[.\-·,]\d+[.\-·,]\d+[a-zA-Z]', txt,
                             re.IGNORECASE):
                    continue
                # Root fix (2026-08-16): a numbered ITEM label ("Definition
                # 2.1.2.") is not a displayed-formula tag.  Bare (non-strong)
                # hits immediately preceded by an item-label keyword are skipped
                # so they do not pollute S (and thus do not force a spurious
                # `\tag` in the summary — the "false green" the user forbids).
                n = self.norm(raw)
                if not n or n in self.ignore or not self._plausible(n, raw):
                    continue
                nums.add(n)
                self._full_keys.add(self.norm_full(raw) or n)
                if n not in self._source_text:
                    idx = txt.find(span)
                    if idx < 0:
                        idx = 0
                    snippet = txt[max(0, idx - 20): idx + len(span) + 20]
                    self._source_text[n] = snippet[:60]
                if pg is None or self._embedded_ref(txt, m.start(), m.end()):
                    continue
                # 定位/定义节证据的两条「非公式标签」守卫（集合 S 成员资格不受
                # 影响 —— nums.add 已在上方执行）：
                # ① 节标题块的编号不是公式编号：OCR 常把标题切成纯编号块 +
                #    纯标题块（ch4 p106 「4.4图变换原理」其上一行是 "§4.4"），
                #    若让标题块锚定 pos/_book_section，则真标签（p121 的
                #    `(4.4)`，位于 §4.5 内）被判 ORDER + MISPLACED。
                if _heading_num(txt) is not None:
                    continue
                # ② 逗号派生的「数」是坐标/列表经 norm 的产物，不是标签：
                #    ch1 p13 坐标块 `(1,2)` 会顶替 p21 的真标签 `(1.2)`。
                if ',' in raw or '，' in raw:
                    continue
                # 「真标签出现」计数（与位置证据同一谓词，勿另立判据）：INCONSISTENT
                # 重复检测按此放宽，见 label_limit。
                self._count_label(n, pg)
                # 🔴 锚点强度须再叠一层「标签证据等级」`_label_grade`（standalone
                # 编号块 或 含数学记号的块，见其定义处）。
                # `keep_cross_refs=True` 下，纯散文块里的括号命中**必须进 S**
                # （否则总结里忠实转写的 `\tag{3.1}` 被误判 FABRICATED），但
                # 「进了 S」≠「是位置证据」：一行注释/图注续行里的 `(N.M)` 只是
                # **提及**。旧写法把「带括号」当成无条件强信号，于是一处散文块
                # 就能把定义位置从真标签手里抢走（Lasota-Mackey ch1
                # 实测：FIGURE 1.2.2 的图注被 OCR 切成 5 块，第 4 块以
                # `(1.2.11) (shown as a dashed line)…` 开头，其 y=648 早于
                # 真标签 `(1.2.11)`（y=1173）、也早于上一号 `(1.2.10)`（y=948）
                # → 顺序倒挂假阳）。降级为**弱证据**即可：无强证据时行为逐字节
                # 同旧写法（`_record_pos` 的强弱分级），有真标签时由它覆盖。
                self._update_pos(n, pg, y,
                                 strong=self._is_strong_signal(span) and _label_grade)

    @staticmethod
    def _bare_item_head(txt: str, start: int, end: int, strong: bool) -> bool:
        """True 当该命中是「条目/习题头」的排版形状，而非印在行尾的公式标签。

        形状判据（不是词表）：**裸号**（无括号/`Eq.` 前缀）+ 编号就是块的**首个
        记号** + 编号后**紧跟句点**。印面上这正是 `2.4.7. If f is close to Ek…`、
        `2.9.3. For w E S2 let Φ(w) = …`、`15.2.2. Given e > 0 …` 的条目头（Katok
        实测 2026-10-03，三枚都曾因旧词表短一个词而抢到定义位置，把后面的真标签
        判成 ORDER_MISMATCH）。公式标签在印面上要么带括号、要么位于行尾，**不会**
        顶在块首后又跟一个句点。

        只用作位置/集合证据的门禁；括号形态（strong）一律放过，行为与旧写法一致。
        """
        if strong:
            return False
        if (txt or '')[:start].strip():
            return False
        return (txt or '')[end:end + 1] in ('.', '。')

    @staticmethod
    def _embedded_ref(txt: str, start: int, end: int) -> bool:
        """True 当该命中是「条目引用 / 更长编号链」而非独立公式标签。

        例：("例3.1.2" 中的 "3.1"、"命题3.1.1" 中的 "3.1"、"§3.1"/"S4.2" 节号
        mention)。仅用于 ORDER/MISPLACED 的位置与定义节证据门禁——集合 S 的
        成员资格（FABRICATED / MISSING）不受影响（`nums.add` / `sectioned.add`
        在调用侧先行、不经过本门禁），因此不会把真实存在的编号错判为
        FABRICATED。若某编号的所有书源出现都是嵌入引用，则其位置/定义节证据
        记为缺失，ORDER/MISPLACED 按既有设计「无可信证据 → 跳过不判」。
        """
        rest = txt[end:]
        if rest[:1] == '.' and rest[1:2].isdigit():
            return True          # 更长编号链的头部（3.1 ⊂ 3.1.2）
        # 集合 / 表格里被 { } [ ] 包裹的元素（如 Koopman 模态表单元 "{18,19}"
        # 逗号归一为 18.19）——绝非带括号显示的公式标签，跳过位置锚定。
        if rest[:1] in ('}', ']'):
            return True
        # 前导引用关键词 "Eq./Equation/Section/Fig./Formula"（可带点与开括号），
        # 例如 "Eq. (5.39)" / "Eq.(18.1)" 散文交叉引用；真实显示标签是独立
        # "(N.M)"，前面只有空白或行首，不含这些词。
        if re.search(r'(?:\b(?:eq(?:uation)?s?|sec(?:tion)?|fig(?:ure)?s?|'
                     r'formula(?:e)?)\b)\s*[.、．]?\s*[\(\[（［]?\s*$',
                     txt[:start], re.IGNORECASE):
            return True
        j = start - 1
        while j >= 0 and txt[j] in ' \u3000':
            j -= 1
        if j < 0:
            return False
        c = txt[j]
        if c in ('(', '（'):
            # 🔴 开括号属于**编号本身**，不是左边界。印刷公式标签的形态就是
            # `(N.M)`，于是 `allow_bare` 带进来的裸号 pattern 在同一块文字里匹配
            # 到的命中，其左邻永远是那枚开括号——照旧返回 False 就等于让
            # 「Further, by (11.1.4),」「and from (12.7.4) with」这类**散文回指**
            # 抢到定义位置（Lasota-Mackey 实测：ch11 的 11.1.4、ch12 的 12.7.4
            # 都只作为回指出现，其括号形态命中已被 `_embedded_ref` 正确拒掉，
            # 裸号形态却漏网 → 把后面的真标签顶成 ORDER_MISMATCH 假阳）。
            # 判据=**跨过这层括号再走一遍同一谓词**：括号左边是文字/条目词 → 引用；
            # 括号左边是行首或运算符（`= (N)`、行首 `(N)`）→ 标签。递归每次严格
            # 左移一个非空字符，必然终止。
            return SourceFormulaIndex._embedded_ref(txt, j, end)
        if c in '例义理题论质习节章图表§Ss':
            return True          # 紧邻条目词 / 节字形（定义3.1、§3.1、S4.2）
        if c in '{[':
            return True          # 集合 / 列表括号左边界（{18,19}）
        # 紧邻 CJK 汉字或拉丁字母（如 OCR 数学碎片 "的2·2-1"、"为2·3n"、"x2.1"）
        # ——独立公式标签的左边界只会是行首/空白/开括号/标点，绝不可能是文字
        if ('\u4e00' <= c <= '\u9fff') or c.isascii() and c.isalpha():
            return True
        return False

    @staticmethod
    def _is_figure_caption(txt: str) -> bool:
        """True if `txt` is a figure-caption line (starts with a figure-label
        keyword).  Such lines must be excluded from formula-number extraction
        (Bug #22): their embedded math (`|Φλ|`) trips the `_block_has_math`
        gate and their sub-labels ("Fig. 2.2A") would otherwise be misread as a
        numbered display formula, fabricating a spurious source number."""
        if not txt:
            return False
        return bool(_CAPTION_LEAD_RE.match(txt))

    @staticmethod
    def _block_has_math(txt: str) -> bool:
        """Heuristic: is `txt` a DISPLAY-formula block (whose trailing `(N)`
        is a genuine numbered formula) rather than prose containing an
        inline reference like "由(3)式可得" / "the last sum in (13)" / an OCR
        artifact like "(1) (b) B(x₀;r)="?

        Genuine formula blocks are either very short (a standalone `(N)` /
        `（N）` number — the canonical Kreyszig formula label) or contain real
        math (an `=`/relation, a sum/integral, a Greek letter, a LaTeX
        command, …).  A longer block is treated as PROSE-REFERENCE (rejected)
        unless it carries a math marker, because genuine numbered formulas in
        this book are either a bare `(N)` or sit next to a displayed equation.
        This prevents prose/reference noise from entering the source formula
        set S and producing false MISSING rows (e.g. "(13)" in "the last sum
        in (13)", which the book never labels as a numbered formula).
        """
        s = txt.strip()
        if len(s) <= 8:
            return True
        if re.search(r'[=∑∫√∂∏≤≥±×÷^_{}\\]', txt):
            return True
        if re.search(r'\\(frac|sqrt|lim|sup|max|inf|sum|int|alpha|beta|'
                     r'gamma|delta|theta|lambda|mu|pi|sigma|phi|psi|'
                     r'omega|cdot|dots|partial)', txt):
            return True
        if re.search(r'[αβγδεζηθικλμνξπρστυφχψωΓΔΘΛΞΠΣΦΨΩ]', txt):
            return True
        return False

    @staticmethod
    def _is_strong_signal(span: str) -> bool:
        """True if a matched number token is a STRONG formula-number signal:
        parenthesized `(C.N)` / `（C.N）`, or prefixed by `Eq.` / `Equation` /
        `式`. Strong signals are ALWAYS kept, even in math-free prose (they also
        serve as cross-references, e.g. "By (3.1) we get A."). Bare `C.N`
        tokens are NOT strong and stay subject to the _block_has_math gate
        (they cover section headings, figure numbers, reference pages, etc.)."""
        s = span.strip()
        if not s:
            return False
        if s[0] in ('(', '（') and s[-1] in (')', '）'):
            return True
        if re.match(r'(?i)^(eq\.?|equation|式)', s):
            return True
        return False

    @staticmethod
    def _plausible(n: Optional[str], raw: Optional[str] = None) -> bool:
        """Reject normalised numbers that cannot be genuine per-section
        formula labels: `0` (function-at-zero artifacts like `x(0)` survive
        the lookbehind only as a bare `(0)`) and any integer > 99 (Kreyszig
        sections never carry that many numbered formulas — such values are
        OCR artifacts / misreads, e.g. a stray `(96)`/`(106)`/`(146)`).
        Lettered sub-formulas (`7a`) keep their digit core and pass.
        """
        if not n:
            return False
        if n == '0':
            return False
        core = re.sub(r'[a-zA-Z]$', '', n)
        # 🔴 前导零永不可能是印刷公式号，但**归一化会把它折掉**（`norm('（A.03）')
        # = 'A.3'`），所以判据必须看**原始串**：裸数字且 ≥3 位仍以 0 开头 =
        # OCR 把列向量矩阵 (0,0,1) 转写成的独立块 `(001)`（Etingof《群表示论》
        # 2026-09-27 实测假 MISSING）。两位以内（'03'）不动，避免误伤
        # `（A.03）` 这类「字母章号 + 折零」既有语义。
        if raw:
            m2 = re.search(r'\d+(?:[.\-]\d+)*[a-zA-Z]?', str(raw))
            if m2:
                for comp in re.split(r'[.\-]',
                                     re.sub(r'[a-zA-Z]$', '', m2.group(0))):
                    if comp.isdigit() and len(comp) >= 3 and comp[0] == '0':
                        return False
        if any(p.isdigit() and len(p) > 1 and p[0] == '0'
               for p in re.split(r'[.\-]', core)):
            return False
        if core.isdigit() and int(core) > 99:
            return False
        return True

    @staticmethod
    def norm(raw: Optional[str]) -> Optional[str]:
        """Canonicalise a raw formula-number token.

        Strips whitespace, removes an outer `（）()` wrapper and any leading
        `Eq.` / `Equation` / `式` prefix, then folds every separator in
        `[. - · ,]` to `.` and DROPS the trailing letter suffix (e.g. `a`).
        Returns None when the token cannot be parsed.

        The suffix is dropped so that lettered sub-parts in the source
        (e.g. `(8a)`, `(8b)`) reconcile with a curated summary that groups
        them under one `\tag{8}` (avoids false MISSING).  For the INCONSISTENT
        *duplicate* check — where distinct lettered sub-equations must remain
        distinct — use `norm_full()` instead.

        Examples:
            '（11.1-1）' -> '11.1.1'
            'Eq. 2.3'    -> '2.3'
            '式（3,4）'  -> '3.4'
            '2.3a'       -> '2.3'   (trailing letter suffix dropped)
            '（A.03）'   -> 'A.3'   (letter-chapter-led; leading zero folded)
            '（II.5）'   -> 'II.5'  (roman-chapter-led; multi-char head kept)
        """
        if not raw:
            return None
        s = str(raw).strip()
        # strip leading EN/CN prefix (case-insensitive).  Handle the full word
        # `equation` BEFORE the `eq`/`eq.` prefix so the latter's optional `n`
        # does not greedily eat `eq` off `equation` and corrupt it to `uation`.
        s = re.sub(r'(?i)^equation\s+', '', s)
        s = re.sub(r'(?i)^eqn?\.?\s+', '', s)
        s = re.sub(r'^式\s*', '', s)
        s = s.strip()
        # peel a single outer parenthesis pair (handles （）and ())
        while s and s[0] in '（(' and s[-1] in '）)':
            s = s[1:-1].strip()
        # Optional leading capital-letter head + separator — `A.3` / `A.03`
        # (letter-chapter-led) or `II.5` / `IV.3` (roman-chapter-led).  `[A-Z]+`
        # keeps a **multi-char Roman head intact** (the old `[A-Z]` matched only
        # one char, so `II.5` fell through to None and every roman tag broke).
        # The head group swallows its trailing separator.  Pure-digit tokens
        # never have it, so digit-led books are unaffected — norm() only ever
        # sees tokens the configured patterns captured.
        m = re.match(r'([A-Z]+[.\-·,])?(\d+(?:' + _SEP_CLASS + r'\d+){0,2})([a-zA-Z]?)$', s)
        if not m:
            return None
        head, core, suffix = m.group(1), m.group(2), m.group(3)
        # Fold separators to '.' and strip leading zeros per component so that
        # `(02)` / `(02.5)` normalise to `2` / `2.5` and match `\tag{2}` /
        # `\tag{2.5}`.  Pure-digit components only, so int() is safe — the
        # optional letter head is re-prepended verbatim.
        norm_core = re.sub(_SEP_CLASS, '.', core)
        norm_core = '.'.join(str(int(p)) for p in norm_core.split('.'))
        parts = ([head[:-1]] if head else []) + [norm_core]
        # Drop the trailing letter suffix (e.g. `8a` -> `8`).  Books such as
        # Strogatz number sub-parts of a single displayed equation as
        # `(8a)`, `(8b)`, while the curated summary groups them under one
        # `\tag{8}`.  Keeping the suffix would flag every sub-part as MISSING;
        # folding it to the digit base lets the source sub-parts and the
        # summary's single group tag reconcile.  This is safe for books without
        # trailing-letter numbering (e.g. Kreyszig's `11.1-1` style) because
        # their tokens carry no suffix to begin with.
        #
        # NOTE: the INCONSISTENT *duplicate* detection does NOT use this
        # suffix-dropped key — see `norm_full()` below.  Folding the suffix
        # here is purely for S-membership / MISSING / FABRICATED reconciliation;
        # collapsing distinct lettered sub-equations into one key would
        # falsely flag them as duplicate \tag numbers.
        return '.'.join(parts)

    @staticmethod
    def norm_full(raw: Optional[str]) -> Optional[str]:
        """Suffix-AWARE canonicalisation of a raw formula-number token.

        Identical to `norm()` except it KEEPS the trailing letter suffix
        (e.g. `5.1.3a` -> `5.1.3a`, `8.2.6c` -> `8.2.6c`).  Used exclusively
        for the INCONSISTENT *duplicate* detection in `_compare()` so that
        lettered sub-equations — which are genuinely distinct tags in the book
        source (e.g. Lasota & Mackey number (5.1.3a) and (5.1.3b) as two
        separate displayed equations) — are NOT collapsed into one key and
        falsely reported as a duplicate \tag number.

        The suffix-DROPPED `norm()` remains the key for S-membership /
        MISSING / FABRICATED, preserving the book-source (8a),(8b) + curated
        summary (8) reconciliation path.  Books without trailing letters are
        unaffected (norm_full == norm for them, since there is no suffix to
        keep), so this change is strictly non-regressing for digit-led books.
        """
        if not raw:
            return None
        s = str(raw).strip()
        s = re.sub(r'(?i)^equation\s+', '', s)
        s = re.sub(r'(?i)^eqn?\.?\s+', '', s)
        s = re.sub(r'^式\s*', '', s)
        s = s.strip()
        while s and s[0] in '（(' and s[-1] in '）)':
            s = s[1:-1].strip()
        # Optional leading capital-letter / roman head + separator — mirrors norm()
        # (`[A-Z]+` keeps multi-char Roman heads like `II` intact).
        m = re.match(r'([A-Z]+[.\-·,])?(\d+(?:' + _SEP_CLASS + r'\d+){0,2})([a-zA-Z]?)$', s)
        if not m:
            return None
        head, core, suffix = m.group(1), m.group(2), m.group(3)
        norm_core = re.sub(_SEP_CLASS, '.', core)
        norm_core = '.'.join(str(int(p)) for p in norm_core.split('.'))
        norm_full = '.'.join(([head[:-1]] if head else []) + [norm_core])
        return norm_full + (suffix.lower() if suffix else '')


def _extract_summary_tags(md_file: str) -> List[FormulaTag]:
    """Extract every `$$...$$` block; record its `\tag` (empty when absent)."""
    try:
        with open(md_file, encoding='utf-8') as f:
            md = f.read()
    except Exception:
        return []
    out: List[FormulaTag] = []
    for block in _BLOCK_RE.finditer(md):
        body = block.group(1)
        mtag = _TAG_RE.search(body)
        raw = mtag.group(1) if mtag else ''
        normalized = SourceFormulaIndex.norm(raw) if raw else ''
        out.append(FormulaTag(
            latex=block.group(0), raw_tag=raw, normalized=normalized))
    return out


def _first_component(n: str) -> str:
    """First numeric component of a normalised number (e.g. '3.1.1' -> '3')."""
    return n.split('.')[0] if '.' in n else n


_EVID_TAIL_ANY_RE = re.compile(
    r'[（(]\s*(\d{1,4}(?:\s*[.,，\-·]\s*\d{1,4})*)\s*[）)]\s*[.。]?\s*$')
_EVID_STANDALONE_RE = re.compile(
    r'^\s*[（(]\s*\d{1,4}(?:\s*[.,，\-·]\s*\d{1,4})*\s*[）)]\s*[.。]?\s*$')


def agnostic_label_evidence(ext_dir: str, ch, start, end, nums) -> bool:
    """``nums``（agnostic 并集探测到的号）里有没有一枚**印在公式编号位置上**？

    预检判据①「配置抽不到 + agnostic 抽得到 = depth/scope 配错」依赖 agnostic 的
    并集模式，而该并集含**裸 N.M**形态（`bare_number` 默认开），于是 OCR 粘连串
    （`p2j-1926-2+…` → 1926.2）、坐标 / 参数表（`(1,0)`、`(5,9g`）都会被记成
    「编号」。2026-09-29 阿诺尔德《经典力学的数学方法》附录F/J 实测：F 的 3 个
    命中里唯一的真印刷号 `(2)` 黏在数学行**中间**（`c=∑∑(2j- 1)n,(2) +`），J 的
    5 个命中全是噪声——两侧都抽不到标签形态的号时，Q 层本该走「S 为空降级」
    （结构检查照跑 + WARN 请人工对账），却因噪声被抬成阻断 ERROR。

    位置门与抽取侧同一口径（形态① 独立标签块 / 形态② 数学块行尾，行尾守卫共用
    ``_tail_pre_guard``），块中间的括号数字一律不算证据。
    """
    want = {str(n) for n in (nums or set())}
    if not want:
        return False
    _pdir = resolve_page_dir(ext_dir, ch)
    for pg in range(int(start), int(end) + 1):
        fp = os.path.join(_pdir, f'page_{pg:03d}.json')
        if not os.path.exists(fp):
            continue
        try:
            data = PageJson.load(fp).data
        except Exception:
            continue
        blocks = [((b.get('text') if isinstance(b, dict) else '') or '')
                  for b in (data.get('text') or [])]
        blocks += [formula_latex_text(fb) for fb in (data.get('formulas') or [])]
        for t in blocks:
            ts = (t or '').strip()
            if not ts or SourceFormulaIndex._is_figure_caption(ts):
                continue
            cand = []
            if _EVID_STANDALONE_RE.fullmatch(ts):
                cand.append(ts)
            elif SourceFormulaIndex._block_has_math(ts):
                m = _EVID_TAIL_ANY_RE.search(ts)
                if m and _tail_pre_guard(ts[:m.start()]):
                    cand.append(m.group(0))
            for c in cand:
                n = SourceFormulaIndex.norm(c)
                if n and n in want:
                    return True
    return False


def _validate_formula_config(ctx, formula, ncomp, patterns):
    """Pre-flight sanity check of the `formula` map against the actual book.

    Runs BEFORE the structural compare loop.  Returns ``None`` when the config
    is consistent with the book, or an ERROR string describing a fatal
    depth/scope mismatch.  The caller prints it to stderr and returns a
    ``q_inconsistent=[err_row]`` result so report.py FAILs the chapter instead
    of letting a mis-config silently mis-judge every ``\\tag`` (the Kreyszig
    type4/depth2/scope2 vs real type1/depth1/scope3 case).

    Agnostic probe: a UNION of the 1- and 2-component patterns, so it finds
    formula numbers regardless of how the book actually numbers them.
    """
    def _count_shapes(ext_dir, start, end):
        # Count OCCURRENCES (not distinct numbers) of single-component (N) vs
        # two-component (C.N) formula shapes across the chapter's pages.
        # Occurrence counts survive the per-section restart of single-component
        # books (every section repeats (1)..(N)), so a single-component book is
        # correctly seen as single-dominated — unlike a distinct-number SET,
        # which collapses to a handful of values and lets a few stray dotted
        # matches flip the classification.
        #
        # 🔴 噪声门禁（Bug #17 修复）：原始实现用裸正则直接数所有 `(N)` / `(C.N)`
        # 出现次数，把函数调用 `f(0)`、交叉引用散文 `(1)`、行内 `x(0)` 等噪声也
        # 计入，导致「单分量出现次数 ≫ 多分量」误判（如 Koopman Ch1：真实公式
        # 编号全是章级两段 `(1.1)`，但噪声把单分量次数抬到 90 > 68，pre-flight
        # 错误地强制 scope=3 并阻断整章）。这里复用真实抽取用的「真公式编号」门禁：
        #   * 单分量只计「独立成行的标签块」 `(N)` / `（N）`（与 build_sectioned
        #     对 ncomp==1 的 fullmatch 门禁一致）；
        #   * 两段只计「含数学的块」（`_block_has_math`，与 ncomp>=2 门禁一致），
        #     散文里的 `(1.2) 暗示` 不计入。
        # 这样 Kreyszig（真·单分量每段重置，标签独立成行）仍被正确识别为单分量主导，
        # 而 Koopman（标签为章级两段、噪声为函数/散文括号）不再被误判。
        single_re = re.compile(r'(?<![\w\u4e00-\u9fff])[（(]\s*(\d+)\s*[）)]')
        dotted_paren = re.compile(r'[（(]\s*(\d+\.\d+)\s*[）)]')
        # Letter / roman-chapter-led `(A.3)` / `(II.5)` counts as two-component
        # too (Lee ISM appendices / roman type 16) — without it such a book's
        # scope-2 pre-flight sees dotted==0 and wrongly demands a scope change.
        # `[A-Z]+` keeps a multi-char Roman head (`II`, `IV`, …) intact.
        dotted_paren_letter = re.compile(r'[（(]\s*[A-Z]+[.·]\d+\s*[）)]')
        # 3-component (C.S.N) numbers are also genuine multi-component formula
        # labels; the original dotted_paren only matched 2 components, so
        # chapter-wide 3-component books (e.g. Lasota-Mackey 5.7.21) were wrongly
        # diagnosed as single-component and failed the pre-flight. Count them as
        # dotted too.
        dotted_paren3 = re.compile(r'[（(]\s*(\d+\.\d+\.\d+)\s*[）)]')
        dotted_eq = re.compile(r'\b(?:Eq\.?|Equation)\s+(\d+\.\d+)')
        dotted_cn = re.compile(r'式\s*[（(]?\s*(\d+\.\d+)')
        _standalone = re.compile(r'\s*[（(]\s*\d+[a-zA-Z]?\s*[）)]\s*[.。]?\s*')
        _has_math = SourceFormulaIndex._block_has_math
        single = dotted = 0
        _pdir = resolve_page_dir(ext_dir, ctx.ch)
        for pg in range(int(start), int(end) + 1):
            fp = os.path.join(_pdir, f'page_{pg:03d}.json')
            if not os.path.exists(fp):
                continue
            try:
                with open(fp, encoding='utf-8') as f:
                    data = PageJson.load(fp).data
            except Exception:
                continue
            for b in data.get('text', []) or []:
                t = b.get('text', '') if isinstance(b, dict) else ''
                if not t:
                    continue
                # Bug #22: figure captions embed math + sub-labels that look like
                # formula numbers; exclude them so they don't skew the shape count.
                if SourceFormulaIndex._is_figure_caption(t):
                    continue
                ts = t.strip()
                if _standalone.fullmatch(ts):
                    # Genuine standalone formula label on its own line.
                    if (dotted_paren.search(t) or dotted_eq.search(t)
                            or dotted_cn.search(t) or dotted_paren3.search(t)
                            or dotted_paren_letter.search(t)):
                        dotted += (len(dotted_paren.findall(t))
                                   + len(dotted_eq.findall(t))
                                   + len(dotted_cn.findall(t))
                                   + len(dotted_paren3.findall(t))
                                   + len(dotted_paren_letter.findall(t)))
                    elif single_re.search(t):
                        single += len(single_re.findall(t))
                    continue
                # Non-standalone: only count two-component numbers inside a
                # math-bearing block (genuine displayed-equation labels).  Bare
                # prose references / function-call parens are rejected so they
                # never inflate the single count.
                if _has_math(t):
                    dotted += (len(dotted_paren.findall(t))
                               + len(dotted_eq.findall(t))
                               + len(dotted_cn.findall(t))
                               + len(dotted_paren3.findall(t))
                               + len(dotted_paren_letter.findall(t)))
        return single, dotted

    # 1) Configured patterns extract nothing but the book clearly HAS formulas.
    agnostic = SourceFormulaIndex(
        ctx.ext_dir,
        build_formula_patterns(1) + build_formula_patterns(2),
        chapter_prefix=False)
    agnostic.build(ctx.ch, ctx.start, ctx.end)
    agnostic_nums = agnostic.all_numbers()

    configured = SourceFormulaIndex(ctx.ext_dir, patterns, chapter_prefix=False,
                                    ncomp=ncomp)
    configured.build(ctx.ch, ctx.start, ctx.end)
    configured_nums = configured.all_numbers()

    if len(configured_nums) == 0 and len(agnostic_nums) > 0:
        # 稀疏编号书（如 Fraleigh：全书仅少数章有编号公式，其余章合法地没有）：
        # agnostic 探测的命中多半是条目标签（"7.5 Theorem"）而非公式编号，
        # 不能据此断言 depth/scope 配错。只有本章总结里确实出现 \tag 编号
        # 公式、而 configured 又一无所获时，才存在"配错导致无法校验"的风险。
        # 无 tag 的章按 SSOT「S 为空降级」放行（结构检查照常，不判 FAIL）。
        if not _summary_has_tags(ctx.md_file):
            return None
        # 🔴 噪声门（Arnold 附录F/J 实测 2026-09-29，见 agnostic_label_evidence）：
        # agnostic 并集含裸 N.M 形态，坐标 `(1,0)` / OCR 粘连 `1926.2` 都会命中。
        # 命中里没有一枚站在印刷标签位置（独立标签块 / 数学块行尾）时，本判据
        # 的「书里明明有编号」前提不成立 → 不阻断，交后面的 S-empty 降级出 WARN。
        if not agnostic_label_evidence(ctx.ext_dir, ctx.ch, ctx.start, ctx.end,
                                       agnostic_nums):
            return None
        _ft = formula.get('type')
        try:
            _fd = ordinal_depth(_ft)
        except OrdinalDepthError:
            _fd = '未登记'
        return (f"`formula` 配置 (type={_ft}, "
                f"depth={_fd}, "
                f"scope={formula.get('scope', '未配置')}) "
                f"在本章书源中抽不到任何公式编号，但 agnostic 探测抽到 "
                f"{len(agnostic_nums)} 个编号；depth/scope 与书实际公式形态不符，"
                f"请按书源真实编号重配 formula（例如单分量节级重排书应 "
                f"type=1/depth=1/scope=3）。")

    # 2) Summary \tag are all single-component but config asks for multi-component.
    tags = _extract_summary_tags(ctx.md_file)
    tag_ncomps = [len(t.normalized.split('.')) for t in tags if t.normalized]
    max_tag_ncomp = max(tag_ncomps) if tag_ncomps else 0
    if max_tag_ncomp == 1 and ncomp >= 2:
        return (f"总结中的 \\tag 编号均为单分量（如 (N)），但 formula.depth={ncomp} "
                f"（多分量）；公式应配置为 type=1/depth=1/scope=3 "
                f"（节级单分量编号，每节从 1 重排）。")

    # 3) scope == 2 (chapter-wide cross-chapter guard) but the book's formulas
    #    are single-component -> every \tag{N} would be mis-judged cross-chapter
    #    INCONSISTENT.  Decide single- vs multi-component by OCCURRENCE counts
    #    (robust to the per-section restart), NOT by the distinct-number set.
    #    🔴 同①口径：仅当总结确有 \tag 时才可能误判——总结无编号公式（如纯证明
    #    附录章，其单分量号已登记 formula.ignore / 不打算打 tag）时静默放行。
    #    🔴 追加口径（ch5 实测）：本判据是「书源单分量 vs 配置 scope=2」的冲突，
    #    只有当**算子自己打的 \\tag 也是单分量**（max_tag_ncomp<=1，与②同量）时才
    #    真正矛盾。若总结里的 \\tag 本就是多分量 (C.N)（如 ch5 唯一 tag \\tag{5.1}），
    #    那它与 scope=2 的章级守卫完全自洽；此时源页 OCR 偶发的裸 (1)/(100)（页边
    #    数字、习题计数、括号列表）把 s 顶过 d 只是噪声，绝不能据此改判 scope=3。
    #    故再加 max_tag_ncomp<=1 前置门——只会抑制假阳性，绝不新增报错（回归安全）。
    scope = formula.get('scope')
    if scope == 2 and _summary_has_tags(ctx.md_file):
        s, d = _count_shapes(ctx.ext_dir, ctx.start, ctx.end)
        if s > d and s > 0 and max_tag_ncomp <= 1:
            return (f"书源公式为单分量编号（如 (N)，单分量 {s} ≫ 多分量 {d}），"
                    f"但 formula.scope=2（章级跨章守卫）会把每个 \\tag{{N}} 误判为"
                    f"跨章 INCONSISTENT；应改为 scope=3（节级重置）。"
                    f"请按书实际编号重配 formula。")

    return None


def _detect_letter_led_formulas(ext_dir: str, start, end, ch=None) -> Set[str]:
    """Letter / Roman-led probe: find alpha-led formula numbers in the book
    source (e.g. `(A.3)` / `（II.5）`).

    🔴 Only meaningful for a **digit-configured** book: `run()` skips this probe
    whenever the config already selects an alpha-led family (letter via
    `letter_ch` / type 15, roman via type 16) — those forms ARE validated by the
    normal `norm()` / `build_formula_patterns` path now.  When a *digit* book's
    source nonetheless carries letter- or roman-led numbers, the probe lets
    `run()` emit a clear mis-config WARN instead of silently degrading to a
    false-green S-empty pass.  Scans the same `page_*.json` `text[]` the real
    extractor reads.  Returns the raw matched tokens (for the surfaced message),
    or an empty set when none are found.
    """
    found: Set[str] = set()
    _pdir = resolve_page_dir(ext_dir, ch) if ch is not None else ext_dir
    for pg in range(int(start), int(end) + 1):
        fp = os.path.join(_pdir, f'page_{pg:03d}.json')
        if not os.path.exists(fp):
            continue
        try:
            data = PageJson.load(fp).data
        except Exception:
            continue
        for b in data.get('text', []) or []:
            t = b.get('text', '') if isinstance(b, dict) else ''
            if not t:
                continue
            for m in _LETTER_LED_RE.finditer(t):
                found.add(m.group(0).strip())
    return found


def _letter_led_note(found: Set[str]) -> Optional[str]:
    """Build the (non-blocking) WARN note for alpha-led formula numbers that a
    **digit-configured** book carries in its source (mis-config hint; `run()`
    skips the probe entirely once an alpha-led family is selected).

    Returns the note string when `found` is non-empty, else None.  Branches:

    * ONLY single-letter tokens (`(A.3)`) → letter-chapter-led numbering, but the
      config has NOT enabled `letter_ch` — hint: set `"letter_ch": true`
      (equivalently formula type 15).  The numbering itself is supported.
    * Roman-led tokens (`(II.5)` / `（IV.3）`, multi-char `[IVXLCDM]{2,5}` head) →
      roman-chapter-led numbering IS supported now via formula **type=16**
      (`lead='roman'`); hint the operator to set `type` to 16 and re-run verify.
    * Residual multi-LETTER tokens (`App.2` / `Ap.2`) belonging to no lead
      family → genuinely unsupported: WARN + downgrade (NOT a blocking FAIL),
      asking for human reconciliation via formula_audit.md, instead of silently
      degrading to a false-green pass OR spuriously blocking a digit-led book.
    """
    if not found:
        return None
    single = {f for f in found
              if re.fullmatch(r'[（(]\s*[A-Z]\s*[.·]\s*\d+[a-zA-Z]?\s*[）)]', f)}
    roman = {f for f in found - single
             if re.fullmatch(
                 r'[（(]\s*[IVXLCDM]{2,5}\s*[.·]\s*\d+[a-zA-Z]?\s*[）)]', f)}
    if single and single == set(found):
        return (
            f"书源含字母章位公式编号（如 {sorted(found)[:3]}…），但 verify_config.json 的"
            f" formula 未启用 \"letter_ch\": true → 此类编号本轮未经机器校验。"
            f"请在对应段（正文 \"ch\" / 附录 \"appendix\"）的 formula 配置加"
            f" \"letter_ch\": true 后重跑 verify。")
    if roman:
        return (
            f"书源含罗马章位公式编号（如 {sorted(roman)[:3]}…），该形态 Q 层已支持"
            f"（formula type=16 / lead='roman'），但当前配置未选用 → 此类编号本轮未经"
            f"机器校验。请在对应段的 formula 配置把 \"type\" 设为 16 后重跑 verify。")
    return (
        f"书源含多字母开头公式编号（如 {sorted(found - single)[:3] if sorted(found - single) else sorted(found)[:3]}…），"
        f"该形态（多字母前缀，如 App/Ap）无对应 lead 家族，Q 层暂不支持，降级为 WARN"
        f"（不阻断）：该部分公式序标未经机器校验，请人工核对 <extract>/formula_audit.md。"
        f"单字母章位（letter_ch / type 15）、罗马章位（type 16）及其**三段**形态"
        f"`(A.2.1)`/`(II.1.3)`（type 17 / 18）均已支持。")


def _dup_beyond_source(src, counts: Dict[str, int], key: str, n: str,
                       sec=None) -> bool:
    """True when the summary repeats one tag number MORE often than the book
    prints it in the same bucket.

    Single predicate shared by `_compare` (chapter key, `sec=None`) and
    `_compare_sectioned` (per-section key) so the detection and the
    relaxation can never drift apart.  `label_limit` returns 1 whenever the
    source has no counted occurrence, so an unrecorded number keeps the
    original strict duplicate behaviour.
    """
    limit = getattr(src, 'label_limit', None)
    return counts[key] > (limit(n, sec) if callable(limit) else 1)


def _compare(tags: List[FormulaTag], src: 'SourceFormulaIndex', ch: int,
             chapter_prefix: bool = True,
             ignore: Optional[Set[str]] = None,
             s_empty_note: Optional[str] = None) -> tuple:
    """Compare summary tags against the book-source set S.

    Returns (fab, inc, miss, rows) where fab/inc/miss are lists of row dicts
    (the subset with that status) and rows is the full audit list, each row:
        {'number', 'status', 'summary_latex'(<=60), 'source_text'(<=60)}
    status ∈ {OK, FABRICATED, INCONSISTENT, MISSING, WARN}.

    `ignore` is a set of normalised formula numbers to SKIP entirely (neither
    flagged FABRICATED nor MISSING) — mirrors the `formula.ignore` map entry.
    """
    ignore = set(ignore or set())
    S = src.numbers_for_chapter(ch)
    s_empty = len(S) == 0

    fab: List[Dict[str, str]] = []
    inc: List[Dict[str, str]] = []
    miss: List[Dict[str, str]] = []
    rows: List[Dict[str, str]] = []
    # `fab`/`inc` hold one row per DISTINCT number (clean report); `rows` keeps
    # one entry per tagged formula (full per-formula audit, incl. duplicates).
    seen_fab: Set[str] = set()
    seen_inc: Set[str] = set()

    numbered = [t for t in tags if t.normalized]
    # INCONSISTENT duplicate detection is SUFFIX-AWARE: lettered sub-equations
    # such as (5.1.3a) / (5.1.3b) are genuinely distinct tags and must NOT
    # collapse to one key (which would falsely flag INCONSISTENT).  We key the
    # duplicate count on the suffix-inclusive normalisation (norm_full) while
    # the suffix-DROPPED `n` below is still used for S-membership / cross-
    # chapter checks, preserving the book-source (8a),(8b) + curated summary
    # (8) reconciliation path.  Books without trailing letters are unaffected
    # (norm_full == norm for them), so this is strictly non-regressing.
    counts: Dict[str, int] = {}
    for t in numbered:
        ik = SourceFormulaIndex.norm_full(t.raw_tag) if t.raw_tag else t.normalized
        counts[ik] = counts.get(ik, 0) + 1

    for t in numbered:
        n = t.normalized
        if n in ignore:
            continue
        prefix_ok = (not chapter_prefix) or (
            _first_component(n) == str(ch))
        ik = SourceFormulaIndex.norm_full(t.raw_tag) if t.raw_tag else t.normalized
        if _dup_beyond_source(src, counts, ik, n):
            status = 'INCONSISTENT'          # duplicate \tag number
        elif not prefix_ok:
            status = 'INCONSISTENT'          # cross-chapter number
        elif s_empty:
            status = None                    # S-empty: structural-only, no OK/FAB
        elif n in S:
            status = 'OK'
        else:
            status = 'FABRICATED'            # invented / mis-copied number
        if status is None:
            continue
        row = {
            'number': n,
            'status': status,
            'summary_latex': t.latex[:60],
            'source_text': (src.source_text(n)[:60]
                            if status != 'FABRICATED' else ''),
        }
        rows.append(row)
        if status == 'FABRICATED' and n not in seen_fab:
            seen_fab.add(n)
            fab.append(row)
        elif status == 'INCONSISTENT' and n not in seen_inc:
            seen_inc.add(n)
            inc.append(row)

    # MISSING: S numbers belonging to this chapter with no matching summary tag.
    if not s_empty:
        covered = {t.normalized for t in numbered}
        for n in sorted(S):
            if n in ignore:
                continue
            prefix_ok = (not chapter_prefix) or (
                _first_component(n) == str(ch))
            if not prefix_ok:
                continue
            if n in covered:
                continue
            row = {
                'number': n,
                'status': 'MISSING',
                'summary_latex': '',
                'source_text': src.source_text(n)[:60],
            }
            rows.append(row)
            miss.append(row)

    # S-empty degradation: structural checks already ran; emit one WARN.
    # 🔴 仅当总结确有非空 \tag 而 S 为空时才告警（那才是配置错/字母编号的信号）；
    # 若总结本章没有任何带编号的 \tag 且书源也未抽到编号——两侧一致为空，说明
    # 该章本就无编号公式（如 Evans SDE 附录 C 的纯证明单元），静默放行。
    # （_extract_summary_tags 会为每个 $$ 块返回空 tag 占位，须按 normalized/
    #  raw_tag 非空判定"真 tag"。）
    if s_empty and any(t.normalized or t.raw_tag for t in tags):
        rows.append({
            'number': '',
            'status': 'WARN',
            'summary_latex': '',
            'source_text': (
                s_empty_note
                or '书源公式编号未抽到（多为 formula 的 type/scope/lead 配错——例如'
                   '把字母章位 (A.3)（type 15 / letter_ch）、罗马章位 (I.2)/(II.5)'
                   '（type 16 / lead=roman）或三段章位 (A.2.1)/(II.1.3)'
                   '（type 17 / 18）的书按纯数字家族配置，则括号内核匹配不到、'
                   'S 为空）；请核对本书实际编号家族后重跑。公式序标校验对本章降级，'
                   '不可报"通过"。'),
        })

    return fab, inc, miss, rows


# Summary-side section patterns.  Two-level `## §C.S` is the historical (and
# still dominant) form that activates Q's per-section comparison.  A subset of
# books instead reset equation numbering INSIDE a SINGLE-level `## §N` section
# (Arnold ODE: continuous §1..§27 across the book, each § restarting formulas at
# (1)).  Their merged chapter carries no `## §C.S` heading, so the sectioned
# path never activated and the chapter-union duplicate check falsely reported
# the SAME number recurring in a LATER section as INCONSISTENT — making it
# impossible to tag each section's equations faithfully.  `_MD_SEC_ONE` lets
# run() fall back to single-level `## §N` buckets, but ONLY for scope==3 books
# that have no two-level headings.  This is a pure RELAXATION of the
# INCONSISTENT duplicate check (dupes become section-local): no currently-
# passing book gets stricter, so the change is regression-safe.  The
# negative lookahead `(?![.\d])` guarantees a single-level match can never fire
# on a two-level `1.2` heading, so the two forms never overlap.
_MD_SEC_TWO = (re.compile(r'^#{2,4}\s*§?\s*(\d+[.\-]\d+)(?![\d.\-])', re.M),
               re.compile(r'(^#{2,4}\s*§?\s*\d+[.\-]\d+(?![\d.\-]).*$)', re.M))
_MD_SEC_ONE = (re.compile(r'^#{2,4}\s*§?\s*(\d+)(?![.\d])', re.M),
               re.compile(r'(^#{2,4}\s*§?\s*\d+(?![.\d]).*$)', re.M))


def _detect_summary_sections(md_text: str):
    """Return ``(md_sections, find_re, split_re)``.

    Two-level `## §C.S` headings win (preserving every existing book's exact
    behaviour).  Only when NONE are present do we fall back to single-level
    `## §N` buckets.  The caller gates this fallback by scope==3, so non-reset
    (chapter/book-scope) books keep the plain path untouched.
    """
    find_re, split_re = _MD_SEC_TWO
    secs = [norm_secnum(s) for s in find_re.findall(md_text)]
    if secs:
        return secs, find_re, split_re
    find_re, split_re = _MD_SEC_ONE
    return [norm_secnum(s) for s in find_re.findall(md_text)], find_re, split_re


def _extract_summary_tags_sectioned(md_file: str, find_re=None, split_re=None) -> List[tuple]:
    """Like `_extract_summary_tags` but also records the section each tagged
    `$$...$$` block belongs to, by walking section headings in order.

    `find_re` / `split_re` come from `_detect_summary_sections` so the SAME
    heading form (two-level, or the single-level `## §N` fallback) drives both
    bucketing here and source windowing in `run()`.  When omitted they default
    to the two-level form — preserving the plain-path caller (which computes
    WARN-only order/misplaced for standard two-level books) unchanged.

    Returns a list of ``(section_key, FormulaTag)``.  Blocks appearing before
    the first section heading are attached to the first section (rare; keeps
    them from being silently dropped).
    """
    try:
        with open(md_file, encoding='utf-8') as f:
            md = f.read()
    except Exception:
        return []
    if find_re is None or split_re is None:
        find_re, split_re = _MD_SEC_TWO
    md_sections = [norm_secnum(s) for s in find_re.findall(md)]
    if not md_sections:
        return []
    parts = re.split(split_re, md)
    out: List[tuple] = []
    cur = md_sections[0]
    for part in parts:
        hm = find_re.match(part)
        if hm:
            cur = norm_secnum(hm.group(1))
            continue
        for block in _BLOCK_RE.finditer(part):
            body = block.group(1)
            mtag = _TAG_RE.search(body)
            raw = mtag.group(1) if mtag else ''
            normalized = SourceFormulaIndex.norm(raw) if raw else ''
            out.append((cur, FormulaTag(
                latex=block.group(0), raw_tag=raw, normalized=normalized)))
    return out


def _compare_sectioned(tags_sec: List[tuple], src_sectioned: Dict[str, Set[str]],
                       md_sections: List[str], chapter_union: Set[str],
                       ignore: Optional[Set[str]] = None,
                       src: Optional['SourceFormulaIndex'] = None,
                       scoped_ignore: Optional[Set[tuple]] = None) -> tuple:
    """Per-section comparison for formula numbering.

    * FABRICATED : a summary ``\\tag`` number not in the chapter-wide union S
      (genuinely invented / mis-copied).  Uses the union (not the per-section
      set) so source-section misalignment can never false-flag.
    * INCONSISTENT: duplicate ``\\tag`` number *within the same section*,
      (legitimate for per-section numbering across sections, so must be local)
      and MORE often than the book prints that label in the section — a source
      that genuinely re-prints a number (Apostol §3.11 prints (17) twice) makes
      the faithful second tag legal, see ``label_limit``.
    * MISSING    : a book-source formula number for this section absent from
      the summary (WARN only; uses the per-section set).
    """
    ignore = set(ignore or set())
    fab: List[Dict[str, str]] = []
    inc: List[Dict[str, str]] = []
    miss: List[Dict[str, str]] = []
    rows: List[Dict[str, str]] = []
    seen_fab: Set[str] = set()
    seen_inc: Set[str] = set()
    # MISSING is emitted once per chapter even in the sectioned path: a source
    # number can sit in several sections' sets (loose per-section assignment),
    # and the row carries no section, so re-emitting it per section only
    # inflated the reported count (observed 5x) without adding information.
    seen_miss: Set[str] = set()

    md_by_sec: Dict[str, list] = {s: [] for s in md_sections}
    for sec, t in tags_sec:
        if sec in md_by_sec:
            md_by_sec[sec].append(t)

    for sec in md_sections:
        S = src_sectioned.get(sec, set())
        s_empty = len(S) == 0
        # S-empty degradation (mirrors `_compare`, chapter-scoped path): when
        # the WHOLE-book union is empty the patterns matched nothing — usually
        # a mis-configured `formula` map.  Structural checks (duplicate /
        # section-local) still run, but FABRICATED must NOT be judged (every
        # tag would false-flag); the trailing WARN row asks for a config fix.
        s_empty_book = len(chapter_union) == 0
        tags = md_by_sec[sec]
        # INCONSISTENT duplicate detection is SUFFIX-AWARE: lettered sub-
        # equations such as (1a) / (1b) are genuinely distinct tags and must
        # NOT collapse to one key (which would falsely flag INCONSISTENT).
        # Key the duplicate count on the suffix-inclusive norm_full while the
        # suffix-DROPPED `n` is still used for S-membership / FABRICATED checks,
        # mirroring `_compare` (chapter-scoped path).  This only affects
        # per-section-restart books (scope==3, e.g. Kreyszig) whose source AND
        # summary both carry lettered sub-parts; digit-led books are unaffected
        # (norm_full == norm for them).
        counts: Dict[str, int] = {}
        for t in tags:
            if t.normalized:
                ik = SourceFormulaIndex.norm_full(t.raw_tag) if t.raw_tag else t.normalized
                counts[ik] = counts.get(ik, 0) + 1
        for t in tags:
            n = t.normalized
            if not n or n in ignore or (sec, n) in (scoped_ignore or set()):
                continue
            ik = SourceFormulaIndex.norm_full(t.raw_tag) if t.raw_tag else t.normalized
            if _dup_beyond_source(src, counts, ik, n, sec):
                status = 'INCONSISTENT'
            elif s_empty_book:
                continue                 # S-empty: structural-only, no OK/FAB
            elif n not in chapter_union:
                status = 'FABRICATED'
            else:
                status = 'OK'
            row = {
                'number': n,
                'status': status,
                'summary_latex': t.latex[:60],
                'source_text': '',
            }
            rows.append(row)
            if status == 'FABRICATED' and n not in seen_fab:
                seen_fab.add(n)
                fab.append(row)
            elif status == 'INCONSISTENT' and n not in seen_inc:
                seen_inc.add(n)
                inc.append(row)
        # MISSING (per-section, WARN)
        if not s_empty:
            covered = {t.normalized for t in tags
                       if t.normalized and t.normalized not in ignore}
            # 🔴 Katok 2026-09-13：游离编号块（OCR 把右缘编号切成孤立 text 块）
            # 常被节推进逻辑分进相邻节，而总结的 \tag 在正确节——按节比对会把
            # 「他节已 tag」误报为本节 MISSING（阻断）。改为：章内任何节已 tag
            # 即不算 MISSING（跨节归属差异由 q-mp / ORDER 机制以 WARN 报告）；
            # 全章都未 tag 的编号才是真漏写，维持阻断。
            covered_anywhere = {t.normalized for _s0, _tags in md_by_sec.items()
                                for t in _tags
                                if t.normalized and t.normalized not in ignore}
            for n in sorted(S):
                if (n in ignore or n in covered
                        or n in covered_anywhere
                        or n in seen_miss
                        or (sec, n) in (scoped_ignore or set())):
                    continue
                seen_miss.add(n)
                row = {
                    'number': n,
                    'status': 'MISSING',
                    'summary_latex': '',
                    'source_text': (src.source_text(n)[:60]
                                    if src else ''),
                }
                rows.append(row)
                miss.append(row)

    # 🔴 与 _compare 的 S-empty WARN 同一语义：仅当总结确有非空 \tag 而书源各节
    # 全都抽不到编号时才告警（配置错信号）。总结无任何带编号 \tag 且书源为空 =
    # 两侧一致为空（如 Evans SDE 附录 C 纯证明单元），静默放行。
    _any_real_tag = any(t.normalized or getattr(t, 'raw_tag', '')
                        for tags_list in md_by_sec.values() for t in tags_list)
    if _any_real_tag and \
            all(len(src_sectioned.get(s, set())) == 0 for s in md_sections):
        rows.append({
            'number': '',
            'status': 'WARN',
            'summary_latex': '',
            'source_text': '书源公式编号未抽到，请检查 verify_config.json 的 formula 配置',
        })
    return fab, inc, miss, rows


def _section_prefix_compatible(a: str, b: str) -> bool:
    """True if section strings `a`, `b` are component-prefix-compatible
    (one is an ancestor of the other).  Resolves the spurious MISPLACED that
    arose whenever the summary's heading granularity differed from the book's:
    e.g. the summary emits only `## §1.3` while the book defines the formula
    under `§1.3.1` / `§1.3.2` — those are descendants of §1.3, NOT misplaced.
    A genuine misplacement (book §1.4 but summary §1.3, or book §1.3.5 but
    summary §1.3.2) shares no prefix and is still flagged."""
    try:
        ca = [int(x) for x in a.split('.')]
        cb = [int(x) for x in b.split('.')]
    except ValueError:
        return a == b
    if not ca or not cb:
        return a == b
    short, long = (ca, cb) if len(ca) <= len(cb) else (cb, ca)
    return short == long[:len(short)]


def _pos_before(a, b):
    """Is book position ``a`` strictly before ``b``?  ``True`` / ``False`` /
    ``None`` (= 证据不足，不作判定)。

    位置元组是 ``(page, y)``，而 ``y`` 可以是 ``None``——``_record_pos`` 允许
    「页已知、行内纵坐标未知」的页级证据（formulas 通道无 poly / text 块缺 poly，
    Iwaniec–Kowalski ch5 的 5.114 实测）。旧代码直接 ``cur < prev_pos`` 比较元组，
    同页时退化成 ``None < 560.0`` → TypeError 把整个 verify 崩掉（2026-09-28 实测）。
    页号不同的先后仍可信；同页且任一侧缺 y 时不下结论（宁漏不误报）。
    """
    if a is None or b is None:
        return None
    pa, ya = a
    pb, yb = b
    if pa is None or pb is None:
        return None
    if pa != pb:
        return pa < pb
    if ya is None or yb is None:
        return None
    return ya < yb


def _pos_better(a, b):
    """记录锚点判据：``a`` 是否应取代 ``b`` 成为 ``(page, y)`` 记录位。

    与 `_pos_before` **同一个谓词**（先后结论由它给出），只补两条记录侧专属约定：
    证据不足时「已知」优于「未知」——缺页侧让位，同页缺 y 侧让位，两边都缺则保留
    既有（不抖动）。

    🔴 根治（Apostol IANT 2026-09-29 实测）：`build_sectioned` 的 `_pos_sec` 写路径
    当年是手搓的裸元组比较 ``if _pp is None or (pg, y) < _pp``。formulas 通道合成的
    标签块（`_blocks.append({"text": _tok})`）**没有 poly**，于是 ``y=None``；同页已
    有一条带 y 的记录时比较退化成 ``None < 560.0`` → TypeError，merge 后的
    ``verify --all`` 整趟崩在 Q 层。2026-09-28 只在**读侧**（`_pos_before`）修了同一
    形态，写侧漏网 = 检测趟与记录趟没共用谓词。现两处（`_record_pos` 与本函数调用方）
    一律走此判据。测试 `verify/tests/test_q_layer_order_pos_y_none.py`。
    """
    if a is None:
        return False
    if b is None:
        return True
    verdict = _pos_before(a, b)
    if verdict is not None:
        return verdict
    pa, ya = a
    pb, yb = b
    if pa is None:
        return False
    if pb is None:
        return True
    if ya is None:
        return False
    if yb is None:
        return True
    return False


def _compute_order_and_section(tags_sec: List[tuple], src: 'SourceFormulaIndex',
                                 ignore: Optional[Set[str]] = None,
                                 reset_on_section: bool = True,
                                 scoped_ignore: Optional[Set[tuple]] = None) -> tuple:
    """Derive ORDER_MISMATCH + MISPLACED (both WARN, non-blocking) from the
    same data Q already has — no three-stage manifest pipeline needed.

    * ORDER_MISMATCH: for formula numbers present in BOTH the summary and the
      book-source set, the summary's document order must follow the book's
      reading order (primary occurrence position).  Any inversion is flagged.
      When ``reset_on_section`` is True (per-section-restart books, scope==3)
      the order window resets on each new ``## §N.M`` so the repeated numbers
      across sections don't false-positive; when False (chapter / book scope,
      globally-unique numbers) the window spans sections so cross-section
      inversions are also caught.  A number the book **reprints** (same label
      typeset twice, e.g. a restated identity) is exempt from the inversion
      test on its 2nd..limit-th summary occurrence — the exemption ceiling is
      the same ``label_limit`` ledger the duplicate check relaxes against.
    * MISPLACED: a summary formula's enclosing ``## §N.M`` section must equal
      the book-source formula's definition section (``book_section``).
      Both paths are **evidence-driven**: absence of placement evidence (no
      page span recorded for that summary section, or no page recorded for
      that number anywhere in the book source) means "cannot tell", NOT
      "misplaced" — such tags are skipped, exactly like the ORDER path above.

    Returns ``(om_list, mp_list)``; each row:
        ``{'number', 'status', 'summary_latex'(<=60), 'source_text': ''}``.

    Only numbers actually extracted from the book source are considered
    (FABRICATED / MISSING are reported by the existing compare functions and
    are never double-counted here).
    """
    ignore = set(ignore or set())
    om: List[Dict[str, str]] = []
    mp: List[Dict[str, str]] = []
    seen_om: Set[str] = set()
    seen_mp: Set[str] = set()
    # per-bucket running count of how often the SUMMARY emitted each number
    # (key = (sec, n) for sectioned books, n for chapter-scoped) — feeds the
    # reprint exemption in the ORDER branch below.
    _occ: Dict = {}

    union = src.source_numbers()
    prev_sec = None
    prev_pos = None
    for sec, t in tags_sec:
        if not t.normalized or t.normalized in ignore:
            continue
        n = t.normalized
        if n not in union:
            continue  # FABRICATED handled elsewhere; skip here
        if (sec, n) in (scoped_ignore or set()):
            continue
        # ORDER-window reset on summary-section change (only for per-section
        # restart books, where numbers repeat across sections).
        if reset_on_section and sec != prev_sec:
            prev_pos = None
        prev_sec = sec
        # ORDER_MISMATCH: summary lists n AFTER a formula whose book position is
        # later than n's -> the sequence got offset / shuffled.
        # For per-section-restart books (reset_on_section=True) use the position
        # of `n` WITHIN `sec` (`_pos_sec`): the global first occurrence of a
        # repeated `(n)` always comes from the earliest section carrying an
        # `(n)`, which made every later section's window compare apples to
        # oranges.  A tag without in-section evidence carries no trustworthy
        # local position (label OCR-merged or genuinely misplaced), so neither
        # flagging nor anchoring prev_pos is fair — skip it entirely.
        # 🔴 后缀标签的「逐字印刷证据」豁免（nonlin ch3 实测 2026-10-02）：
        # 集合成员用 `norm`（丢尾字母，见 `norm` 文档），于是总结的 `\tag{8a}`
        # 与 `\tag{8b}` 都折成键 `8`；而**单分量**书（`ncomp==1`）的抽取 pattern
        # 核是 `\d+`，`formulas`/`text` 里印面的 `(8a)`/`(8b)` 独立标签块**根本
        # 匹配不到**，S 里的 `8` 只可能来自别处那枚真 `(8)`（本节 = §3.7，`8` 印在
        # §3.6）→ 两枚忠实标签被误判 MISPLACED（顺序支同样拿到的是别人的位置）。
        # 规则：总结标签带后缀，而书源从未**逐字**印过该后缀形态（`_full_keys`
        # 无记录）= 抽取器对这一枚标签没有任何位置证据 → 按「无证据不判」跳过
        # 两支。多分量书（`(8.11a)` 能被 pattern 捕获）照常判定，集合成员
        # FABRICATED / MISSING 一律不受影响（本豁免只可能少报，不会多报）。
        _full = SourceFormulaIndex.norm_full(getattr(t, 'raw_tag', '') or '')
        if (_full and _full != n
                and _full not in getattr(src, '_full_keys', set())):
            continue
        cur = None
        if reset_on_section:
            cur = getattr(src, '_pos_sec', {}).get((sec, n))
        else:
            cur = src.primary_pos(n)
        # 🔴 原书**重印同一编号**时，第二次出现不得回指该号的首次位置
        # （2026-09-29 Apostol IANT ch3 §3.11 实测）：印面 (16)(17)(18) 之后，
        # Theorem 3.13 的推导结尾又原样重排 identity (17) 并**再次印出右缘
        # `(17)`**（物理页 79 = 印面 67，fitz 300dpi 目视 + `page_079.json`
        # block 9 独立标签块确证），总结忠实挂两个 `\tag{17}`（重复检测已由
        # `label_limit` 放宽，故 Q:0/0/0）。旧顺序支把第二枚 17 与**首次**位置
        # （页 78 block 8）比较，游标此时已推进到 (18)（页 78 block 26）→
        # 必然倒挂 → 一条 ORDER_MISMATCH 假阳。
        # 判据复用重复支的同一谓词 `_dup_beyond_source`（= 同一 `label_limit`
        # 账，检测与放宽永不漂移）：仅当「本章节内该号的出现次序 ≤ 书里印过的
        # 不同页数」时视为印面确有其事，跳过次序比较**且不回退游标**。
        # 无重印记录的书 `label_limit` 返回 1 → 第二次出现仍按原严格度比较，
        # 逐字节行为不变（本改动只可能少报，不可能多报）。
        _ok = (sec, n) if reset_on_section else n
        _occ[_ok] = _occ.get(_ok, 0) + 1
        _reprint = (_occ[_ok] > 1
                    and not _dup_beyond_source(src, _occ, _ok, n,
                                               sec if reset_on_section else None))
        if cur is not None and not _reprint:
            if _pos_before(cur, prev_pos):
                if n not in seen_om:
                    seen_om.add(n)
                    om.append({
                        'number': n,
                        'status': 'ORDER_MISMATCH',
                        'summary_latex': t.latex[:60],
                        'source_text': '',
                    })
            prev_pos = cur
        # MISPLACED: summary section != book definition section.
        #
        # Plain path (chapter/book-scope numbering): compare against the global
        # first-occurrence section (`book_section`).
        #
        # Per-section-restart path (scope==3): `(sec, n)` membership alone is
        # NOT enough — the standalone-label gate legitimately misses labels
        # that OCR merged into their equation line, so an honest `\tag{n}`
        # would be flagged whenever its source label happened to be merged.
        # Evidence gate: flag only when the book recorded `(n)` NOWHERE inside
        # sec's own page span `[start(sec), start(next)-1]`; any in-range hit
        # proves correct placement.
        # 🔴 「无证据不判」（2026-09-29，与上方 ORDER 支同一约定）：证据有两种缺法——
        #   ① `rng is None`：节游标从未推进到该节（OCR 节头不匹配/该页被判目录），
        #      该节的页跨根本未知；
        #   ② `npages` 为空：该号在书中只作为**回指/行内**出现（或来自
        #      `formula.known_book` 白名单——人工登记的真号，抽取器查无载体页），
        #      没有任何位置记录可比。
        # 两者都属「无法证明放错」而非「证明放错」，一律**跳过不判**。旧写法把它
        # 当成 `not in_range = True` 直接开报，于是节游标一卡就整章刷屏（Apostol ch5
        # 24/24、Lee ch7 16/16 全为此类假 MISPLACED）。plain 支早就是同款约定
        # （`bsec is not None` 才判），本节级支是唯一的例外，现已对齐。
        flagged = False
        # 🔴 层级自述编号豁免（Katok ch1 实测 2026-10-02）：三级标签 `C.S.i`
        # 的**中段本身就写明它属于哪一节**。总结把 `(1.2.2)` 写在 `## §1.2` 之下
        # = 标签自己作证，谈不上「放错节」；而书侧两条证据都受 OCR 滞后支配——
        # plain 支的 `_cur_heading` 游标（Katok 的 §1.2 节头从未被 `_heading_num`
        # 认出，于是 `(1.2.2)` 挂在 §1.1）、sectioned 支的整页页跨（§1.2 起始页判成
        # p42，标签印在 p41）——据其开报只会造出整批假阳（本书 ch1 5/5 全属此类）。
        # 真正的错位 = 总结把标签挂在**别的节**下（chaos ch8 把 `8.8.*` 九枚挂在
        # `## §8.7`），前缀不等 → 照判，一条不放过。本豁免只动 MISPLACED；
        # 集合成员（FABRICATED/MISSING）与顺序（ORDER_MISMATCH）两支不受影响。
        _self_reported = bool(sec) and n.startswith(sec + '.')
        if reset_on_section:
            rng = _section_page_range(src, sec)
            npages = getattr(src, '_n_pages', {}).get(n) or set()
            # ①最强证据：趟本身把 (n) 归在 sec 这一桶（块序 + 节头推进，能分辨
            #   「节在页中间起头」）→ 书与总结同判，谈不上放错。
            # ②回退：标签被 OCR 并进公式行而漏记 (sec, n) 时，用整页页跨宽松核。
            # ③两者都无 → 无证据不判（见上）。
            if (not _self_reported
                    and getattr(src, '_pos_sec', {}).get((sec, n)) is None):
                if rng is not None and npages:
                    flagged = not any(rng[0] <= p <= rng[1] for p in npages)
        else:
            bsec = src._book_section_sec.get((sec, n)) or src.book_section(n)
            flagged = (bsec is not None and not _self_reported
                       and not _section_prefix_compatible(bsec, sec))
        if flagged and n not in seen_mp:
            seen_mp.add(n)
            mp.append({
                'number': n,
                'status': 'MISPLACED',
                'summary_latex': t.latex[:60],
                'source_text': '',
            })
    return om, mp


def _section_page_range(src: 'SourceFormulaIndex',
                        sec: str) -> Optional[tuple]:
    """Page span ``(first, last)`` of summary-section `sec` from the walk's
    own bookkeeping (`_sec_start_page` / `_walk_last_page`).  Sections entered
    on the same page share it; the span ends on the page where the NEXT
    distinct section start begins (**inclusive**).

    🔴 尾页含下一节的起始页（2026-09-29 Apostol IANT ch5 实测）：页跨是
    **整页**粒度，而节可以在页中间起头——Apostol 每页页顶还印「`5.4: 节名`」
    形式的**书眉**（奇数页给节名、偶数页给章名），书眉在块序上先于本节最后的
    显示公式，于是 §5.3 的 (8) 印在 §5.4 起始页（物理页 125）的上半部，
    旧写法 `hi = min(later) - 1` 把它判成越界。书眉抢先推进的精确盲区由
    `_pos_sec[(sec, n)]`（按块序推进的节桶）兜底，页跨只作**回退**证据，
    回退证据应当宽松：边界页一律算在跨内。"""
    starts = getattr(src, '_sec_start_page', None)
    if not starts or sec not in starts:
        return None
    lo = starts[sec]
    later = [p for p in starts.values() if p > lo]
    hi = min(later) if later else getattr(src, '_walk_last_page', lo)
    return (lo, hi)


def _split_scoped_ignore(keys) -> tuple:
    """Split ignore keys into ``(global_numbers, scoped_(sec, num)_pairs)``.

    A key may be a bare normalized number (``'13'``) or section-scoped
    (``'9.8#17'`` — ``'<md-section>#<raw tag>'``).  Scoped keys silence a
    number ONLY inside that one summary section: per-section-restart books
    repeat every bare number across all sections, so a chapter-wide ignore
    would blind validation of legitimately tagged `(n)` everywhere else."""
    glob: Set[str] = set()
    scoped: Set[tuple] = set()
    for k in keys or []:
        k = str(k)
        if '#' in k:
            sec, _, num = k.partition('#')
            nn = SourceFormulaIndex.norm(num)
            if sec and nn:
                scoped.add((sec.strip(), nn))
        else:
            nn = SourceFormulaIndex.norm(k)
            if nn:
                glob.add(nn)
    return glob, scoped


def _tag_pairing_rows(ctx, ncomp, lead, ignore) -> list:
    """「同号配错式」探针（`q_tag_mismatch`，非阻断 WARN）。

    实现在同包自包含模块 `tag_formula_pairing.py`：那里按 `page_*.json` 重建
    「印面标签 -> 展示式正文」的书侧真值账，再与总结 `$$\\tag{X}$$` 的正文逐一
    对账。集合成员（FABRICATED/MISSING）、顺序（ORDER_MISMATCH）、归属（MISPLACED）
    三支都只看**号**，章级契约对账同样只看号的**集合**——于是「漏贴一枚印面标签 +
    后续 `\\tag` 整体错位一格 + 给印面无号展示式补一枚号」可以一路全绿（Katok ch2
    §2.6/§2.8、ch4 §4.4 实测）。本族把号与式重新钉在一起。

    🔴 探针自身异常**不阻断 verify**（新判据，跨书形态未普查完），但会把
    「未跑成」打到 stderr——绝不静默吞掉。
    """
    try:
        from tag_formula_pairing import pairing_problems
        return pairing_problems(ctx.ext_dir, ctx.ch, ctx.start, ctx.end,
                                ctx.md_file, ncomp=ncomp, ignore=ignore,
                                lead=lead)
    except Exception as exc:                      # noqa: BLE001
        print(f"[Q-LAYER TAG-PAIRING *WARN*] 配对探针未跑成：{exc!r}",
              file=sys.stderr)
        return []


class QLayer(VerifyLayer):
    code = 'Q'
    name = 'formula-tag'
    order = 17               # current max layer is P (order 16); Q runs after it
    auto_fixable = False     # audit-only layer; no --fix

    def run(self, ctx) -> LayerResult:
        # GATE: opt-in via the `formula` map.  When absent the layer is a pure
        # no-op so the 16 legacy layers and already-finished books are
        # completely unaffected.
        if ctx.config.formula is None:
            # Pre-flight guard (2026-08-08): silently no-op-ing while the
            # summary actually contains numbered formulas would make the agent
            # (and downstream readers of the verify report) believe formula
            # sequence-label verification "passed" when it never ran.  If the
            # chapter has `\tag{...}` formulas, the operator MUST first set up
            # the `formula` config from the book's real numbering — so warn
            # loudly instead of returning a clean no-op.
            if _summary_has_tags(ctx.md_file):
                print(
                    "[Q-LAYER WARN] 总结含带序标公式 (\\tag{...})，但 "
                    "verify_config.json 缺少 `formula` 配置 → Q 层已静默 no-op，"
                    "公式序标**未校验**，不可报\"公式校验通过\"。\n"
                    "  → 请先按书实际公式编号填写 `formula` 配置再跑 verify：\n"
                    "      \"formula\": {\"type\": <风格码>, \"scope\": <1/2/3>, "
                    "\"ignore\": []}\n"
                    "    type 已包含编号段数：两级 (C.N)(如 2.6)→type 2；三级 "
                    "C.S.N / C.S-N(如 11.1-1)→type 3；单分量 (N)→type 1；"
                    "字母章位 (A.3)→type 15（或 legacy type 2 + letter_ch）；"
                    "罗马章位 (II.5)→type 16；三段章位 (A.2.1)→type 17、"
                    "(II.1.3)→type 18。\n"
                    "    scope = 编号重置窗口（1=全书连续 / 2=每章重启 / 3=每节"
                    "重启），必须从书中确定，**无默认值**——缺 scope 或取值非法会在"
                    "加载期直接报错（exit 2），不再静默按章级处理。\n"
                    "    不确定段数时，先扫该书 page_*.json 的 text[] 实测公式标签。",
                    file=sys.stderr,
                )
            return LayerResult(code='Q', metadata=dict(_EMPTY_Q))

        formula = ctx.config.formula
        ftype = formula.get('type')
        # `depth` is DERIVED from `type` via ORDINAL_DEPTH — it is NOT read from
        # the config (any stale `depth` key is ignored on purpose).
        fignore = set(formula.get('ignore') or [])
        # Per-chapter formula noise (cross-chapter references like "(5.9) of
        # Chapter 2", OCR comma-lists such as "k = 1, 2,3" -> 2.3, etc.) is
        # registered by the operator in `ignore_ch{N}.json` — the SAME
        # per-chapter file the B-layer consumes via ConfigLoader.ignore_for_
        # chapter. The Q-layer previously read ONLY the GLOBAL `formula.ignore`,
        # so such per-chapter noise produced spurious q-miss rows that could
        # only be silenced by adding the (often section-reused) number to the
        # GLOBAL ignore — which would also disable validation of genuinely
        # present `\tag` in OTHER chapters (e.g. `\tag{2.3}` recurs in 7
        # chapters). Merging ONLY `ignore_ch{N}.json` (NOT `ignore_fig_ch{N}.json`,
        # whose "Figure 3.2"-style entries would collide with real formula
        # norms like `\tag{3.2}`) gives a per-chapter-scoped, coverage-preserving
        # way to register formula noise without the global-ignore breadth cost.
        from data.book_structure.book_structure import chapter_label
        _pic = os.path.join(ctx.ext_dir, f'ignore_{chapter_label(ctx.ch)}.json')
        if os.path.exists(_pic):
            try:
                _pic_data = json.load(open(_pic, encoding='utf-8'))
                # 两种形状都收：list（纯键）与 dict（键 -> 登记理由，B 层 /
                # IGNORE-AUDIT 惯例形状）。dict 的键即忽略编号，理由仅供人审。
                if isinstance(_pic_data, list):
                    fignore |= {str(x) for x in _pic_data}
                elif isinstance(_pic_data, dict):
                    fignore |= {str(k) for k in _pic_data.keys()}
            except Exception:
                pass
        fkeep = formula.get('keep_cross_refs', True)
        # 🔧 known_book (2026-09-14): genuine book formula numbers the source
        # scan missed, registered as real (not hidden behind ignore).  Wired
        # from verify_config.json `formula.known_book`.  See SourceFormulaIndex.
        fknown = known_book_scopes(formula)
        scope = formula.get('scope')
        # 🔴 scope 无默认值：加载期 `verify_config.from_dict` 已强制任何带 type 的
        # formula 块显式声明 scope；此处再兜一道——若拿到 type 却缺 scope，宁可
        # 硬报错交人工/agent 依书确定，绝不静默按 scope=2（章级守卫）跑，那样会
        # 用错误的体例把合法跨章号误判 INCONSISTENT（伪造守卫 = 宁缺勿滥反面）。
        if scope is None and formula.get('type') is not None:
            raise ValueError(
                "formula 配置缺 `scope`（无默认值）：请依书实际编号体例显式设 "
                "scope（1=全书/2=每章/3=每节）。")
        # Per-section formula numbering (Kreyszig: every section restarts at
        # (1)).  FABRICATED/INCONSISTENT are checked section-locally; the
        # chapter-prefix cross-chapter guard is OFF.
        section_scoped = (scope == 3)
        # Cross-chapter guard (first component == current chapter) is ON iff
        # scope == 2 (chapter-level numbering); book/section scope disables it.
        chapter_prefix = (scope == 2)
        # raw config 的 type 必须是规范码（弃用码 4/9/10/11 已退役、config 已改写）。
        # 🔴 走 `resolve_formula_type` 统一入口：formula-only 码 15（letter 二级）/
        # 16（roman 二级）不在 `ORDINAL_DEPTH` 里，直接 `ordinal_depth(15/16)` 会抛
        # OrdinalDepthError。数字码 1/2/3 + legacy `letter_ch` 经解析器逐字节等价。
        lead, ncomp = resolve_formula_type(
            ftype, letter_ch=bool(formula.get('letter_ch')))
        # `formula.letter_ch` (default False): letter-chapter-led numbering
        # `(A.3)` / `（B.12）`（Lee ISM appendices）；roman type 码 16 → lead='roman'
        # `（II.5）`。Patterns and norm() then accept a leading capital-letter /
        # roman head; the cross-chapter guard (scope 2) compares the head against
        # the chapter key ('A' / 'II'…).
        letter = (lead == 'letter')
        # 🔴 RESERVED 探针跳过条件：只要本书已按 alpha-led 配置（letter 或 roman），
        # 正常路径已在机器校验这类编号——探针只对**数字家族**的书触发（源里冒出
        # 字母/罗马编号=配错提示）。旧写法只看 `letter`，roman 书（lead='roman'、
        # letter=False）会被探针误判「罗马尚未支持」而阻断。
        alpha_led = lead in ('letter', 'roman')
        # `formula.bare_number` (default True): when False, the bare ``N.M``
        # variant is dropped from the source-extraction patterns.  Books whose
        # prose is full of numbered cross-references (Lee: ``(Fig. 1.2)``,
        # ``1-11`` Problem labels) otherwise collect those as phantom formula
        # numbers and report each as MISSING.
        patterns = build_formula_patterns(
            ncomp, allow_bare=bool(formula.get('bare_number', True)),
            letter=letter, lead=lead)

        # Pre-flight: validate the formula config against the actual book BEFORE
        # the structural compare loop.  A depth/scope mismatch would otherwise
        # silently mis-judge every \tag (e.g. Kreyszig mis-set as type4/depth2/
        # scope2 makes each \tag{N} a false cross-chapter INCONSISTENT -> FAIL,
        # which operators "fix" by deleting all \tag).  Surface it as a clear
        # ERROR and FAIL the chapter instead.
        err = _validate_formula_config(ctx, formula, ncomp, patterns)
        if err is not None:
            err_row = {
                'number': '',
                'status': 'ERROR',
                'summary_latex': '',
                'source_text': err,
            }
            print(f"[Q-LAYER ERROR] {err}", file=sys.stderr)
            return LayerResult(code='Q', metadata={
                'q_checked': True,
                'q_fabricated': [],
                'q_inconsistent': [err_row],
                'q_missing': [],
                'q_rows': [err_row],
                'q_error': err,
            })

        if section_scoped:
            md_text = ''
            try:
                with open(ctx.md_file, encoding='utf-8') as f:
                    md_text = f.read()
            except Exception:
                md_text = ''
            md_sections, _sec_find_re, _sec_split_re = _detect_summary_sections(md_text)
            if not md_sections:
                # No section headings (neither two-level `## §C.S` nor the
                # single-level `## §N` fallback) -> the plain chapter path.
                section_scoped = False
            else:
                tags_sec = _extract_summary_tags_sectioned(
                    ctx.md_file, _sec_find_re, _sec_split_re)
                src = SourceFormulaIndex(ctx.ext_dir, patterns, False, fignore,
                                          keep_cross_refs=fkeep,
                                          known_book=fknown,
                                          sections_global=bool(
                                              getattr(ctx.config,
                                                      'sections_global', False)
                                              or formula.get(
                                                  'sections_global', False)))
                # 🔴 书章号集（供跨章引用过滤，见 build_sectioned 尾部注记）
                try:
                    from data.book_structure.book_structure import list_chapter_keys as _lck
                    src._book_chapter_keys = {str(k) for k in _lck(ctx.ext_dir)}
                except Exception:
                    src._book_chapter_keys = set()
                built = src.build_sectioned(ctx.ch, ctx.start, ctx.end,
                                            md_sections, ncomp=ncomp)
                src_sec = built['_sectioned']
                union = built['_union']
                # scoped-ignore support: keys may be bare numbers or
                # '<sec>#<num>' (silences a number in ONE section only)
                fglob, fscoped = _split_scoped_ignore(fignore)
                fab, inc, miss, rows = _compare_sectioned(
                    tags_sec, src_sec, md_sections, union, fglob, src,
                    scoped_ignore=fscoped)
                om, mp = _compute_order_and_section(
                    tags_sec, src, fglob, reset_on_section=True,
                    scoped_ignore=fscoped)
                tm = _tag_pairing_rows(
                    ctx, ncomp, lead,
                    fglob | {nn for (_s, nn) in fscoped})
                # RESERVED letter/Roman-led probe: only meaningful when the
                # config has NOT selected an alpha-led family.  With `letter_ch`
                # (letter) or roman type 16, that numbering IS validated by the
                # normal path; the probe only fires for digit books as a
                # mis-config hint.  A letter-led book must not silently pass.
                _ll_sec = ([] if alpha_led else
                           _detect_letter_led_formulas(ctx.ext_dir, ctx.start, ctx.end, ch=ctx.ch))
                ll_note_sec = _letter_led_note(_ll_sec)
                if ll_note_sec is not None:
                    print(f"[Q-LAYER LETTER-LED *WARN*] {ll_note_sec}",
                          file=sys.stderr)
                return LayerResult(code='Q', metadata={
                    'q_checked': True,
                    'q_fabricated': fab,
                    'q_inconsistent': inc,
                    'q_missing': miss,
                    'q_order_mismatch': om,
                    'q_misplaced': mp,
                    'q_tag_mismatch': tm,
                    'q_letter_led': [ll_note_sec] if ll_note_sec is not None else [],
                    'q_rows': rows,
                })

        tags = _extract_summary_tags(ctx.md_file)
        src = SourceFormulaIndex(ctx.ext_dir, patterns, chapter_prefix, fignore,
                                 ncomp=ncomp, keep_cross_refs=fkeep,
                                 known_book=fknown)
        src.build(ctx.ch, ctx.start, ctx.end)

        # RESERVED probe for letter / Roman-led formula numbering.  Only fires
        # for a **digit-configured** book: with `letter_ch` (letter) or roman
        # type 16 selected, that numbering IS validated by the normal path.  For
        # a digit book the probe surfaces letter-led `(A.3)` / roman-led `(II.5)`
        # numbers sitting in the source as a mis-config hint pointing at the fix.
        # See _letter_led_note for the branches.
        _ll = ([] if alpha_led else
               _detect_letter_led_formulas(ctx.ext_dir, ctx.start, ctx.end, ch=ctx.ch))
        ll_note = _letter_led_note(_ll)
        if ll_note is not None:
            print(f"[Q-LAYER LETTER-LED *WARN*] {ll_note}", file=sys.stderr)

        tags_sec = _extract_summary_tags_sectioned(ctx.md_file)
        om, mp = _compute_order_and_section(
            tags_sec, src, fignore, reset_on_section=False)
        fab, inc, miss, rows = _compare(
            tags, src, ctx.ch, chapter_prefix, fignore, s_empty_note=ll_note)
        tm = _tag_pairing_rows(ctx, ncomp, lead, fignore)
        return LayerResult(code='Q', metadata={
            'q_checked': True,
            'q_fabricated': fab,
            'q_inconsistent': inc,
            'q_missing': miss,
            'q_order_mismatch': om,
            'q_misplaced': mp,
            'q_tag_mismatch': tm,
            'q_letter_led': [ll_note] if ll_note is not None else [],
            'q_rows': rows,
        })
