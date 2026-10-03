"""book-summarizer shared separator / numbering regex library.

Single source of truth for the inter-component separator policy used across the
verify pipeline and the extractors.  Previously every module hardcoded its own
``[.\\-]`` / ``[.．]`` / ``.`` separator set, which broke on books that use a
slightly different punctuation between numbering components.  Here the
separator is WILDCARDED:

  * ``SEP_TIGHT`` — used by *matching* regexes (character-class, no space, no
    comma) so an unanchored ``finditer`` never swallows prose like "1, 2, 3"
    or "Eq. 2.3".
  * ``SEP_WIDE``  — used ONLY by ``re.split`` / ``canon_sep`` where the input is
    already anchor-bounded, so a broader set (spaces, fullwidth commas …) is
    safe and makes any separator style normalize to one canonical form before
    comparison.

This module depends only on ``re`` / ``functools`` (standalone, no cv2/torch),
and contains NO label knowledge — label-embedded regexes stay in
``lib/key_parse.py``.

Imported as ``from lib.regexlib import ...`` (the skill root is on sys.path).

.. warning::
   WILDCARDING happens ONLY at the *matching* stage: extractors building a key,
   and verify layers detecting one.  Once a key is canonicalized it is stored as
   a literal ``C.S-N`` string and consumed by ``key.split('.')`` / ``split('-')``
   / ``split(':')`` in many downstream modules (item_numbering_integrity,
   data_provider, extract_items*, b_layer, gen_contract, …).  Those splits MUST
   NOT be widened to the SEP sets — doing so would break the canonical-key
   contract.  Keep literal ``'.'`` / ``'-'`` splits on already-normalized keys.
"""

import re
import functools

# --- separator policy -------------------------------------------------------
# Matching-class separator: real digit-to-digit separators only (no whitespace,
# no comma) so unanchored scans stay precise.
SEP_TIGHT = r'[.\-–·/．－〜_~]'

# Wide separator: any punctuation/whitespace that can separate numeric
# components in a *bounded* context (re.split / canon). Includes the fullwidth
# comma "，" and ASCII comma so Chinese/English prose separators normalize too.
SEP_WIDE = r'[\s._\-–·/：:／~～_＋+，,;；、．－〜]+'
SEP_SPLIT_RE = re.compile(SEP_WIDE)

# Numeric separator: used by the *number matchers* in the extractors
# (num_re / lab_re / fr_re / EN_LAB_RE / fallback_re).  Like
# SEP_WIDE it tolerates whitespace + fullwidth comma, but deliberately EXCLUDES
# the more dangerous colon / plus / semicolon / ideographic-comma / slash so a
# decimal "3.14", a formula "a:b" or a date "4/7/2001" is never misread as a
# numbering path.  Adds the fullwidth period/hyphen (．/－) that OCR frequently
# emits — the gap the original hardcoded ``[\.\-\·\，\s]`` set left open.
SEP_NUMERIC = r'[\s.\-–·．－〜，,]'


# --- item-head leading noise (OCR 行首粘连标点) -----------------------------
# 中文扫描版式里，上一句的句末标点常被 OCR 粘在下一行条头之前（实测 Arnold
# 《经典力学的数学方法》page_078 行 '．例9考虑k个铰接杆所成的封闭链条这个力学系'
# —— 印面「例 9」前粘了上条的句号「．」），行首锚定的条头正则因此整条漏识，
# 契约缺项、B 层只报出一个「缺号」而不暴露根因。
# 所有「行首条目头」检测在匹配前一律调用 ``strip_head_noise``：判据只此一份，
# 抽取侧与查漏/回填侧共用（豁免只写在一侧 = `--fix` 静默毁数据的旧病）。
# 字符集刻意只含**标点/引用符号**，绝不含数字或汉字，故只会放行「前面粘了
# 噪声」的真条头，不会把句中引用变成行首命中。
HEAD_NOISE_RE = re.compile(r'^[\s>\*_．。·、，,;；:：!！?？~～\-–—]+')


def strip_head_noise(text):
    """去掉 OCR 行首粘连的标点/引用符号，返回可用于「行首条头」匹配的前缀。

    🔴 只用于**检测**（判断这一行是不是条目头 / 小节头）。返回值不得写回正文或
    契约内容——正文快照一律取原始行，避免把真标点删掉。
    """
    return HEAD_NOISE_RE.sub('', text or '')


def canon_sep(s):
    """Normalize any run of separators in ``s`` to a single '.' and strip ends."""
    parts = [p for p in SEP_SPLIT_RE.split(s) if p]
    return '.'.join(parts)


def canon_token_numeric(s):
    """Canonicalize a numbering token's numeric part to '.'-separated form,
    preserving an optional leading label word.

    'Theorem 12-3' -> 'Theorem 12.3'
    '定理 4。11-5'  -> '定理 4.11.5'
    '4·11·5'       -> '4.11.5'
    """
    s = s.strip()
    m = re.match(r'^([A-Za-z\u4e00-\u9fff]+)\s*(.*)$', s)
    if m:
        label = m.group(1)
        num = canon_sep(m.group(2))
        return f"{label} {num}" if num else label
    return canon_sep(s)


def split_numpath(s, levels):
    """Split a bare key into ``levels`` ints using the wide separator (robust to
    runs like '4..5' / '4--5'); return None if component count != levels."""
    parts = [p for p in SEP_SPLIT_RE.split(s.strip()) if p]
    if len(parts) != levels:
        return None
    try:
        return [int(p) for p in parts]
    except ValueError:
        return None


# --- shared label-FREE compiled regexes (all built from SEP_TIGHT) ----------
# Label-embedded regexes (FR_*, ENTRY_RE_2, ENTRY_RE_EN*, ENTRY_RE_APP* …)
# live in lib/key_parse.py, which imports SEP_TIGHT from here and rebuilds
# them with the wildcard separator.
KEY_RE = re.compile(r'(\d+)' + SEP_TIGHT + r'(\d+)' + SEP_TIGHT + r'(\d+)')
ENTRY_RE = re.compile(r'\*\*[^*]*?(\d+' + SEP_TIGHT + r'\d+' + SEP_TIGHT + r'\d+)[^*]*\*+')


# --- shared label-bearing / domain regexes (centralised 2026-08-09) --------
# Only BYTE-IDENTICAL, same-semantics duplicates across packages are merged
# here.  Semantically divergent duplicates (e.g. the #{1,6} vs #{2,6} SEC_RE
# in wrap_examples_bq) are intentionally left local — blind merging would
# change behaviour.
# Consumers import with `as` aliases to keep local call-sites untouched.

# Chinese-scheme section-heading detectors (extract.scan_skeleton +
# verify.script.audit_counts).  OCR noise: §→8, glue of §/number, no space before title.
SEC_CN = re.compile(
    r'^[§Ss8*+x$\u00d7\u2605\u2606\s\-\u2013\u2014\uFF0D]*[.．·]?(\d{1,2})[\.\．·](\d{1,2})'
    r'[\.\．·。]?(?!\s+[\u4e00-\u9fff])(?=[^\d.．·。]*[\u4e00-\u9fff]).{0,24}$')
SECBARE_CN = re.compile(
    r'^[§Ss8*+x$\u00d7\u2605\u2606\s\-\u2013\u2014\uFF0D]*[.．·]?(\d{1,2})[\.\．·](\d{1,2})$')
SECGLUE_CN = re.compile(
    r'^[§Ss8*+x$\u00d7\u2605\u2606\s\-\u2013\u2014\uFF0D]*[Ss8§](\d{1,2})[\.\．·]?(\d{1,2})'
    r'[^\s\d](?=[^\d.．·。]*[\u4e00-\u9fff]).{0,24}$')

# Chapter-LOCAL single-number section header (Karlin-style: sections RESET per
# chapter and are printed as ``"1. Review of Basic…"`` / ``"2: Two Simple
# Examples…"`` — a bare NUMBER followed by a TITLE, NOT a global ``C.S``).
# IMPORTANT: in the source, ``"N. Title"`` is AMBIGUOUS with numbered PROBLEMS
# (``"6. Show that the sums…"``) and REFERENCES (``"1. W. Feller…"``), so this
# regex is NEVER used as a standalone section detector.  It is only consumed by
# the D-layer chapter-local source rescan, which intersects the detected ``N``
# against the md ``## §N`` set (the authoritative section list) — so a problem /
# reference numbered line can never masquerade as a section.  The heading TITLE
# must start with a letter / Han char and must NOT be an item label (so
# ``"1. Definition"`` — a number-first item — is left to the item detector).
_SEC_LOCAL_SEP = r'[.\uFF1A\u2236:]'
SEC_LOCAL = re.compile(r'^(\d{1,2})' + _SEC_LOCAL_SEP + r'\s*([A-Za-z\u4e00-\u9fff].{2,72})$')

# Blockquote head line (verify.g_layer / format_verify).
G_HEAD = re.compile(r'^\s*>+\s*\*?(?:\*{0,2})(?:证明|证|例)')

# Figure OCR markers (figure.build_figure_index + figure.build_precise_anchors).
FIG_ITEM_SEC_RE = re.compile(r'^\s*(\d{1,2})\.(\d{1,2})\b\s*[:.]?\s*[A-Za-z]')
FIG_PAGE_RE = re.compile(r'=====\s*PAGE\s*(\d+)\s*=====')

# Format-package section heading / horizontal rule (#{2,6} variant; the
# #{1,6} variant in wrap_examples_bq is kept local on purpose).
FMT_SEC_RE = re.compile(r'^#{2,6}\s')
FMT_HR_RE = re.compile(r'^\s*---\s*$')

# Formula-number detectors (make_config + config/verify_config/tests +
# verify.formula_tag via FMT_* names).  Half/full-width parens both matched;
# negative lookbehind rejects function-call parens like x(0)/f(0).
F_SINGLE_RE = re.compile(r'(?<![\w\u4e00-\u9fff])[（(]\s*(\d+)\s*[）)]')
F_DOT_RE = re.compile(r'(?<![\w\u4e00-\u9fff])[（(]\s*(\d+\.\d+)\s*[）)]')
F_EQ_RE = re.compile(r'\b(?:Eq\.?|Equation)\s+(\d+\.\d+)')
F_CN_EQ_RE = re.compile(r'式\s*[（(]?\s*(\d+\.\d+)')
# Letter-chapter-led formula number `(A.3)` / `（B.12）` (Lee ISM appendices):
# single capital letter + dot/interpunct + digits, parenthesised.  The single-
# letter requirement keeps reference words out (`(Fig. 19)` — `F` is followed
# by `i`, not a separator).  make_config uses this for whole-range formula
# detection of appendix page ranges (letter_ch).  Single-char ROMAN heads
# (`I`/`V`/`X`/`L`/`C`/`D`/`M`) are indistinguishable from letters and are
# therefore left to this probe (conservative election keeps them as letter).
F_LETTER_RE = re.compile(
    r'(?<![\w\u4e00-\u9fff])[（(]\s*([A-Z])\s*[.·]\s*(\d+)\s*[）)]')
# Roman-chapter-led formula number `(II.5)` / `（IV.12）` (formula type 16,
# lead='roman').  Requires a MULTI-CHARACTER roman head ([IVXLCDM]{2,5}) so it
# yields only unambiguous positive Roman evidence — `(II.5)`/`(IX.3)` cannot be
# a letter head.  Same parens / lookbehind / (head, num) capture shape as
# F_LETTER_RE.
F_ROMAN_RE = re.compile(
    r'(?<![\w\u4e00-\u9fff])[（(]\s*([IVXLCDM]{2,5})\s*[.·]\s*(\d+)\s*[）)]')
# --- 三段 alpha-led 公式序标 `(A.2.1)` / `（II.1.3）` ------------------------
# 🔴 上面的 F_LETTER_RE / F_ROMAN_RE 在**第一个**数字段后就要求闭括号，故对三段
# 体例 `(A.2.1)` 一个也匹配不到（`A.2` 后面是 `.` 不是 `)`）。实测成因：
# Katok《现代动力系统导论》附录A 印 `(A.2.1)`…`(A.4.1)`、补篇S 印 `(S.2.1)`…
# `(S.4.2)`（每节从 1 重启），两段探针全零 → 该段 `verify_config.json` 无
# `formula` 键 → Q 层 no-op，公式序标从未校验。
# 判据与两段**完全同纪律**：必须带半/全角括号（裸排 `A.2.1` 与小节标题、
# 条目号 `A.2.6.` 不可分，宁缺勿滥）、负向后顾排除词内/汉字粘连。
# 消费方：`config/verify_config/make_config.detect_formula`（择族）、
# `tools/census_alpha3_formula.py`（跨书普查）。捕获组 (head, section, number)。
_F3_SEP = r'[.·]'
F_LETTER3_RE = re.compile(
    r'(?<![\w\u4e00-\u9fff])[（(]\s*([A-Z])\s*' + _F3_SEP + r'\s*'
    r'(\d+)\s*' + _F3_SEP + r'\s*(\d+)\s*[）)]')
F_ROMAN3_RE = re.compile(
    r'(?<![\w\u4e00-\u9fff])[（(]\s*([IVXLCDM]{2,5})\s*' + _F3_SEP + r'\s*'
    r'(\d+)\s*' + _F3_SEP + r'\s*(\d+)\s*[）)]')
