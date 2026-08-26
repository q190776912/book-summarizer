"""config/verify_config/verify_config.py — single source of truth for ALL per-book verify configuration.

This module replaces the old `ManagerConfig` (verify/registry.py) +
`BNumberingConfig` (verify/item_numbering_integrity/script/item_numbering_integrity.py) and the scattered inline reads of
`chapter_map.json` / `figure_index.json`.  Every layer reads its configuration
through a `ConfigLoader` instance (constructed ONCE per run), never by
re-reading files or by receiving config field-by-field through a context object.

Config schema (see config/config_schema.md §配置字段说明):

  * `ordinal` is a LIST of `GroupConfig` — each group is a set of entry labels
    (定理/定义/练习/Example/...) that share ONE merged counter.  This replaces
    the old single-integer `ordinal` + `separate_types` (SEP_COMBINED/
    SEP_PER_TYPE) switch: different groups NEVER merge, an unmatched label
    falls into the `uncat` fallback group.  Group fields: `type` (ORDINAL_* 1..6 / 8 / 9),
    `name` (label categories), `depth` (numeric components), `scope` (1 book /
    2 chapter / 3 section — the counter reset boundary).  Values for `type`:
        1 single | 2 two_level(CN) | 3 three_level(CN, default)
        4 en (EN two-level) | 5 roman | 6 gm
  * `language` (cn/en) is an orthogonal axis, defaulted from `ordinal`.
  * `ignore` is ONE unified list merging the old `known_gaps` + `ignore_keys`
    + `ignore_fig` semantics (the user chose a single suppression set).
  * `manual` is a path to the extraction-override JSON (structured data, kept
    separate from the flat `ignore` set — merging a file path into an ignore
    set would break extraction overrides).
  * `disable` is GONE — every layer always runs; suppression is via `ignore`
    + the warning gate, never by skipping.
"""
import json
import os
import re
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Set, Union


class ConfigError(Exception):
    """Raised when the per-book verify configuration is incomplete/invalid.

    Used by `ConfigLoader.require_complete()` to enforce the mandatory book
    config gate (rule H in SKILL.md). Callers (verify_chapter.py / scan_skeleton.py)
    catch it and exit non-zero with a clear message.
    """


# --- grouping scope (per GroupConfig) --------------------------------------
# Replaces the old SEP_COMBINED / SEP_PER_TYPE `separate_types` switch.  Each
# GroupConfig now carries its own `scope` (the counter reset boundary), so a
# book can mix e.g. a depth-3 theorem group (chapter scope) with a depth-2
# exercise group (chapter scope) without a global binary toggle.
SCOPE_BOOK, SCOPE_CHAPTER, SCOPE_SECTION = 1, 2, 3

# --- ordinal style codes (single integer selector) -------------------------
# ONE integer encodes BOTH the numbering depth and the structural style.
# This ABSORBS the old `levels` (depth 1/2/3) and the old `scheme` family
# (single / two_level / three_level / en / gm / roman) into a
# single field.  `language` (cn/en) is an orthogonal axis.
ORDINAL_SINGLE = 1
ORDINAL_TWO_LEVEL = 2      # CN two-level (N.M, section-first); no chapter filter
ORDINAL_THREE_LEVEL = 3    # CN three-level (N.M.K) — default
ORDINAL_EN = 4             # EN two-level (N.M, chapter-first; rich EN labels)
ORDINAL_ROMAN = 5          # three-level with ROMAN chapter (e.g. I.2.3)
ORDINAL_GM = 6             # two-level, bare per-section ordinals (no chapter)
ORDINAL_VAKIL = 8          # EN three-level, number-first (N.M.item + N.M.A exercises), e.g. Vakil
ORDINAL_EN3 = 9             # EN three-level, LABEL-FIRST dots (Label C.S.N), e.g. Lasota & Mackey
                          #   《Chaos, Fractals, and Noise》. 条目形如 `Remark 1.1.1` /
                          #   `Definition 2.3.4` / `Theorem 3.2.1`，编号三段 C.S.N；与 type 3
                          #   (CN 三级虚线键 `C.S-N`) 不同：要求显式英文标签词，因此天然
                          #   排除 `FIGURE 1.1.1` / `(1.1.1)` 等图号/公式号（避免键碰撞）。
ORDINAL_CN3LAB = 10         # CN three-level, LABEL-FIRST dots (标签C.S.N), e.g. 孙文祥《遍历论》.
                          #   条目形如 `定理1.1.1` / `定义2.3.4` / `例2.1.6`，三段 C.S.N 且
                          #   **每类标签各自独立计数、每节重置**（定义1.1.1 与 定理1.1.1 并存）。
                          #   与 type 3（CN 三级裸键 `C.S-N`，共享计数器）不同：键内嵌规范中文
                          #   标签（`定理1.1.1`，与 type 9 的 `评注1.1.1` 同构），要求块首显式
                          #   标签词，天然排除三级小节标题（`2.3.1 Birkhoff遍历定理的陈述`——
                          #   数字在前）与裸 `C.S.N` 图号/公式号，避免键碰撞。

ORDINAL_ROSS = 11           # EN section-scoped LETTER-numbered (S. Ross《A First Course in
                          #   Probability》). 条目形如 `Example 2a`（节号+小写字母，节内独立计数）、
                          #   `Proposition 4.1` / `Theorem 7.1` / `Lemma 2.1` / `Corollary 4.1`
                          #   （节号.节内序号）、`Axiom 1`（纯单数字）。键保留原书印刷形态
                          #   （"Example 2a"），md/契约规范键 = 规范中文标签 + 原编号（例2a /
                          #   命题4.1 / 公理1）。章末习题块（Problems / Theoretical Exercises /
                          #   Self-Test Problems and Exercises）以 exercise_region_headings
                          #   配置驱动扫描闩。

ORDINAL_HUM = 12             # EN subsection-keyed BARE/LETTER items (Humphreys《Introduction
                          #   to Lie Algebras and Representation Theory》GTM 9,
                          #   config_setting 规则5 增量扩展). 原书正文条目头只印裸标签
                          #   （"Lemma." / "Theorem (Cartan's Criterion)."）或节内大写字母号
                          #   （"Lemma A" / "Corollary A (Lie's Theorem)"），编号由【所在小节】
                          #   隐式给出——书中交叉引用写作 "Lemma 7.2"（§7.2 的那条引理）/
                          #   "Lemma 10.2B"（§10.2 的引理 B）。契约键因此取「标签 + 所在小节 +
                          #   字母」的唯一化形态并注入 § 记号使其【故意不可被数字解析】：
                          #   "Lemma §10.2B" / "Lemma §7.2"（裸）/ "Example §22.4-1"
                          #   （§22.4 的 Example 1./2.）/"Table §11.4-1"。理由：引用号继承
                          #   小节网格、天然稀疏（§4 有 4.1 与 4.3 的定理但没有 4.2 的定理），
                          #   若可解析 B 层会按连续计数器误报海量假断号；不可解析则与
                          #   Ross/Karlin 字母项同路径优雅跳过（完整性靠抽取器 + 源侧回填 +
                          #   D 层 + 计数审计兜底）。md 标签照原书印刷：**Lemma A** / **Lemma**。
                          #   节为全书全局单序标 §1..§27（section_types=[1,1] +
                          #   sections_global=true），节头原书印裸 "9. Axiomatics" 形态
                          #   （无 § 前缀），由 scan_skeleton 的 SEC_GLOBAL_PLAIN 分支识别。

ORDINAL_CODES = (1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12)
ORDINAL_NAME = {
    1: 'single', 2: 'two_level', 3: 'three_level',
    4: 'en', 5: 'roman', 6: 'gm', 8: 'vakil', 9: 'en3', 10: 'cn3lab', 11: 'ross',
    12: 'hum',
}
# Numbering depth (numeric components) per ordinal code.
ORDINAL_DEPTH = {1: 1, 2: 2, 3: 3, 4: 2, 5: 3, 6: 2, 8: 3, 9: 3, 10: 3, 11: 2, 12: 2}
# Structural style per ordinal code (None = common depth-driven parsing).
ORDINAL_STRUCTURE = {1: None, 2: None, 3: None, 4: None, 5: 'roman', 6: 'gm', 9: None, 10: None,
                     11: None, 12: None}
# Default language per ordinal code (common CN families -> cn, EN families -> en).
ORDINAL_LANGUAGE_DEFAULT = {1: 'cn', 2: 'cn', 3: 'cn', 4: 'en', 5: 'en', 6: 'en', 8: 'en', 9: 'en',
                            10: 'cn', 11: 'en', 12: 'en'}
# Back-compat: legacy STRING ordinal values -> int code (with a warning).
_LEGACY_ORDINAL_STR = {
    'single': 1, 'two_level': 2, 'two-level': 2, 'three_level': 3, 'three-level': 3,
    'en': 4, 'roman': 5, 'gm': 6,
}

# --- section role codes = ORDINAL-DEPTH codes for the nested `## §` hierarchy -
# The code stored in `section_types` is NOT a "chapter/section/subsection"
# role name — it is the NUMBER OF NUMERIC COMPONENTS (ordinal depth) carried by
# that heading level's `## §` token:
#     type 1 -> a 1-component ordinal  `## §N`          (一级序标)
#     type 2 -> a 2-component ordinal  `## §N.M`        (二级序标，两段均数字)
#     type 3 -> a 3-component ordinal  `## §N.M.K`      (三级序标)
#     type 4 -> a 4-component ordinal  `## §N.M.K.L`    (四级序标)
#     type 5 -> LETTER-LABELED subsec  `### §A`         (纯字母标号 A/B/C…；原书印
#            "A. TITLE"，父节靠位置确定，summary 只写 "§A"，不投影父节数字)
#     type 0 -> UNNUMBERED `## § <标题>` (no ordinal at all)
# The names CHAPTER/SECTION/SUBSECTION below are just the TYPICAL meaning these
# depths take in a standard (normally-nested) book — they are NOT enforced
# semantics.  A book may legitimately declare e.g. `section_types: [1, 1, 1]`
# (every heading level uses a bare 1-component ordinal) or `section_types: [0]`
# (the only `## §` level is unnumbered).  The matching numeric component count
# per level is DERIVED via the SECTION_TYPE_DEPTH map — it is NOT a stored field.
SECTION_ROLE_CHAPTER       = 1   # 一级序标 `## §N`      (标准书里通常是章前缀)
SECTION_ROLE_SECTION       = 2   # 二级序标 `## §N.M`    (标准书里通常是节)
SECTION_ROLE_SUBSECTION    = 3   # 三级序标 `## §N.M.K`  (标准书里通常是小节)
SECTION_ROLE_SUBSUBSECTION = 4   # 四级序标 `## §N.M.K.L`
SECTION_ROLE_LETTERSUB    = 5   # 字母标号子节 `### §A`（纯字母标号 A/B/C…，父节位置确定）
# SECTION_ROLE_LETTERSUB: 字母标号子节（如 Karlin & Taylor 原书
#   `A. JOINT DISTRIBUTION FUNCTIONS`，md 中写作 `### §A`，其中 `A` 是字母标号、
#   父节（最近的 `## §N`）靠位置确定，**不**把父节数字投影进标题）。它**不是**
#   `## §N.M` 双数字二级序标（type 2）——第二分量是「字母」而非「数字」，因此
#   永不可能被通用的数字 `_project` / `_split_num` 机制匹配（`int('A')` 会抛错）。
#   字母子节一律由**专用字母感知正则**在 chapter-local D 层分支与 build_structure
#   中识别，绝不走通用数字扫描。此处登记的 depth（1）仅用于 `max_level` 计数
#   （字母子节是「章→数字节→字母子节」的第 3 级），不被数字 `_project` 路径消费。
#   仅 chapter-local 书（Karlin 式，原书印 `A. Title` 子节）声明；其它书不出现。
# SECTION_ROLE_UNNUMBERED: a section-hierarchy LEVEL that carries NO ordinal in
# the original book.  It corresponds to `type 0` / `depth 0` (0 `## §`
# components) and is written as a `0` in the `section_types` array.  A `0`
# appears at WHICHEVER level(s) are unnumbered — it is NOT restricted to the
# in-file `## §` tier.  Silverman is `[0, 0]`: element 0 = the CHAPTER (the
# file `# 第N章`, no `## §` number) and element 1 = its `## § <标题>`
# subsections, BOTH unnumbered.  The `## §` gate matches an unnumbered level by
# POSITION (never fabricating a number).  `section_types` is a PER-LEVEL list
# ordered chapter → deepest; its LENGTH must equal the number of hierarchy
# levels, so a single-level book is `[0]` while a chapter+subsection book is
# `[0, 0]` (two levels — never collapse them into one).
SECTION_ROLE_UNNUMBERED = 0
# SECTION_ROLE_CODES spans 0..5: role 0 = unnumbered, 1..4 = 1/2/3/4-component
# ordinal depths, 5 = letter-labeled subsection (Karlin-style `A. Title` written
# `### §A` in the md).  No real book nests deeper than a 4-component heading
# (`## §5.4.2.1`).  Raise this cap AND extend SECTION_TYPE_DEPTH together if a
# deeper book appears.
SECTION_ROLE_CODES = tuple(range(0, 6))

# --- role code -> nesting depth (number of `## §...` components) -----------
# Each role has a FIXED segmentation => FIXED depth.  Depth is NOT inferred
# from the role *number* (a future non-positional role e.g. code 10 must
# declare its real depth here, not inherit `depth == code`).  Built-in roles
# happen to be positional (role N == depth N); that is a coincidence, not an
# invariant.  ALWAYS resolve depth through this map; never write `depth = role_code`.
SECTION_TYPE_DEPTH = {
    SECTION_ROLE_UNNUMBERED:    0,  # ## § <标题> 无数字（type 0 / depth 0）
    SECTION_ROLE_CHAPTER:       1,  # ## §N
    SECTION_ROLE_SECTION:       2,  # ## §N.M
    SECTION_ROLE_SUBSECTION:    3,  # ## §N.M.K
    SECTION_ROLE_SUBSUBSECTION: 4,  # ## §N.M.K.L
    SECTION_ROLE_LETTERSUB:     1,  # ### §A（纯字母标号；父节由位置确定，不进数字 _project）
}

# Default section-types (role codes) per ordinal code. BACK-COMPAT fallback
# used only when a verify_config.json does not explicitly declare
# `section_types`.  The verified section hierarchy is ORTHOGONAL to the
# item-numbering depth: it describes how many NESTED SECTION levels the book's
# markdown / source actually has (## §N, ## §N.M, ## §N.M.K), NOT how many
# components an item key carries.  For the historic three-level CN families
# (type 3 / 5 / 8) the convention is that the book genuinely nests sections
# three deep (chapter / section / subsection 1.1.1), so the default is
# [1, 2, 3] — item keys such as ``1.3-4`` whose deepest component is an ITEM
# counter (NOT a subsection) are the Kreyszig-shaped exception and must declare
# ``"section_types": [1, 2]`` explicitly (i.e. only chapter + section, no
# subsection verification); make_config.py detects this automatically so the
# fallback is only reached by genuine 3-level books.  Depth is DERIVED from each
# role code via SECTION_TYPE_DEPTH and is NEVER a separate config field.
# Two-level families verify chapter + section only ([1, 2]); single-level
# verifies the chapter prefix ([1]).
ORDINAL_SECTION_TYPES = {
    1: [1], 2: [1, 2], 3: [1, 2, 3], 4: [1, 2],
    5: [1, 2, 3], 6: [1, 2], 8: [1, 2, 3],
    9: [1, 2], 10: [1, 2, 3], 11: [1, 2, 3],
    # Humphreys GTM 9：章=文件一级、节=全书全局单序标 §1..§27（原书印裸
    # "9. Axiomatics" 无 § 前缀）、小节 N.M 不作契约层级（条目键内嵌小节定位）。
    12: [1, 1],
}

# --- formula sequence-label (Q-LAYER) config ------------------------------
# Source extraction patterns are DERIVED from the `formula` map in
# verify_config.json (`type`/`depth` -> component count), not hand-listed.
# See the `formula:` field doc on the dataclass below for the map shape.


@dataclass
class GroupConfig:
    """One numbering group: a set of entry labels sharing ONE merged counter.

    Replaces the old `separate_types` (SEP_COMBINED/SEP_PER_TYPE) switch.  Items
    whose label matches `name` share a counter; different groups NEVER merge; an
    item whose label matches no group falls into the `uncat` fallback group.
    """
    type: int = ORDINAL_THREE_LEVEL          # ORDINAL_* style code (1..9)
    name: List[str] = field(default_factory=lambda: ["uncat"])  # label categories
    scope: int = SCOPE_CHAPTER               # 1=book / 2=chapter / 3=section

    @property
    def is_uncat(self) -> bool:
        return "uncat" in self.name

    @property
    def depth(self) -> int:
        """Numeric components of an item key (e.g. ``1.1-2`` -> 3).

        DERIVED from `type` via the canonical `ORDINAL_DEPTH` map — `depth`
        is NOT an independent config field.  `type` already encodes BOTH the
        numbering depth AND the structural style, so a separate `depth` field
        only invites the two to drift out of sync.  Treat `depth` as a read-only
        projection of `type`; it is never serialized and is ignored on load."""
        return ORDINAL_DEPTH.get(self.type, 3)

    def group_prefix_len(self) -> int:
        """Number of leading numeric components that form the counter's
        reset-prefix (e.g. chapter for scope=chapter).  Mirrors the old
        BookConfig.group_prefix_len() but computed per-group."""
        sp = {SCOPE_BOOK: 0, SCOPE_CHAPTER: 1, SCOPE_SECTION: 2}.get(self.scope, 1)
        return min(sp, max(0, self.depth - 1))


# --- label canonicalization (shared by config + key_parse) ---------------
# Maps a raw label (CN or EN, any case) to a canonical Chinese label so that
# `group_for_label` can match group `name` entries against item labels across
# languages.  This is the SINGLE SOURCE OF TRUTH — key_parse imports it from
# here (lib/ stays import-clean; key_parse depends on lib, never the reverse).
_LABEL_CANON = {
    'Definition': '定义', '定理': '定理', '定义': '定义',
    'Theorem': '定理',
    'Lemma': '引理', '引理': '引理',
    'Corollary': '推论', '推论': '推论',
    'Proposition': '命题', '命题': '命题',
    'Example': '例', '例': '例', '示例': '例',
    'Remark': '评注', '评注': '评注', '注释': '评注', '注': '评注', '注记': '评注',
    'Commentary': '评注',
    'Axiom': '公理', '公理': '公理',
    'Assertion': '断言', '断言': '断言',
    'Conjecture': '猜想', '猜想': '猜想',
    'Condition': '条件', '条件': '条件',
    'Assumption': '假设', '假设': '假设', '假定': '假设',
    'Algorithm': '算法', '算法': '算法',
    'Property': '性质', '性质': '性质',
    # exercise-family labels canonize to 练习; Example canonizes to 例
    # (例子 ≠ 练习). A book that checks examples uses a group named
    # ["Example"] (canon -> 例); a book that checks exercises uses
    # ["练习","习题"] (canon -> 练习). The two are distinct on purpose.
    'Exercise': '练习', '习题': '练习',
}

EN_LABEL_KINDS = ['Definition', 'Theorem', 'Lemma', 'Corollary', 'Proposition',
                  'Example', 'Remark', 'Axiom', 'Assertion', 'Conjecture',
                  'Assumption', 'Algorithm', 'Commentary']


def _canon_label(lbl):
    """Canonicalize a raw item label (CN/EN, any case) to a stable Chinese label."""
    if not lbl:
        return lbl
    if lbl in _LABEL_CANON:
        return _LABEL_CANON[lbl]
    low = lbl.lower()
    if low in ('cor.', 'def.'):
        low = {'cor.': 'corollary', 'def.': 'definition'}[low]
    if low.endswith('s') and len(low) > 1 and low[:-1] in (k.lower() for k in EN_LABEL_KINDS):
        low = low[:-1]
    for k in EN_LABEL_KINDS:
        if k.lower() == low:
            return _LABEL_CANON.get(k, lbl)
    return lbl


def ordinal_depth(ordinal: int) -> int:
    """@deprecated: numeric component count for an ordinal code.  Depth is now
    per-group (GroupConfig.depth); this helper only survives for make_config's
    default.  Do NOT add new callers."""
    return ORDINAL_DEPTH.get(int(ordinal), 3)


def _load_ignore_file(path: str) -> List[str]:
    """Read a JSON list/dict of confirmed-noise keys; return a list.

    Mirrors the legacy `verify.script.ignore_files.load_ignore` semantics but is
    self-contained (no dependency on the verify package) so ConfigLoader can
    live in lib/.  Missing/broken file -> [].
    """
    if not path or not os.path.exists(path):
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except Exception:
        return []
    if isinstance(data, list):
        return [str(x) for x in data]
    if isinstance(data, dict):
        # Accept either {"keys": [...]} or a bare dict of key->reason.
        if 'keys' in data and isinstance(data['keys'], list):
            return [str(x) for x in data['keys']]
        return [str(k) for k in data.keys()]
    return []


@dataclass
class ChapterInfo:
    ch: Union[int, str] = 0
    start: int = 0
    end: int = 0
    name: str = ''
    name_en: str = ''
    name_cn: str = ''

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ChapterInfo':
        raw_ch = d.get('ch', d.get('num', d.get('chapter', 0)) or 0)
        try:
            ch: Union[int, str] = int(raw_ch)
        except (TypeError, ValueError):
            # 字母章号（附录 A/B…）：保留字符串，与 build_structure 的既有兼容一致
            ch = str(raw_ch).strip() or 0
        return cls(
            ch=ch,
            start=int(d.get('start', d.get('start_page', d.get('pdf_start', 0)) or 0)),
            end=int(d.get('end', d.get('end_page', d.get('pdf_end', 0)) or 0)),
            name=str(d.get('name', '') or ''),
            name_en=str(d.get('name_en', '') or ''),
            name_cn=str(d.get('name_cn', '') or ''),
        )


@dataclass
class BookConfig:
    """Per-book verify configuration — the single source of truth.

    Replaces the old `ManagerConfig` + `BNumberingConfig`.  All fields are
    plain data; the only IO happens inside `ConfigLoader`.

    Schema:
      * `ordinal` (List[GroupConfig]) — the ONE grouping selector.  Each group
        encodes a numbering style (`type`), the label categories it covers
        (`name`), the key depth (`depth`) and the counter reset scope (`scope`).
        This replaces the old single integer + `separate_types` switch.  See
        GroupConfig and config/config_schema.md §配置字段说明.
      * `language` (cn/en) is an orthogonal axis, defaulted from `ordinal`.
      * `ignore` is ONE unified list merging the old `known_gaps` +
        `ignore_keys` + `ignore_fig` semantics.
      * `manual` is a path to the extraction-override JSON (kept separate from
        the flat `ignore` set).
      * `disable` is GONE — every layer always runs; suppression is via
        `ignore` + the warning gate.
    """
    ordinal: List[GroupConfig] = field(default_factory=lambda: [GroupConfig()])
    language: str = 'cn'
    strict: bool = True
    # Whether the FIRST numeric component of a two/three-level EN item key is the
    # CHAPTER (True, the ORDINAL_EN / ORDINAL_EN3 default: "Theorem 6.1" = ch6
    # item1) or the SECTION (False, section-scoped books where the chapter is
    # implicit and "Theorem 3.1" = §3 item1).  When False, _extract_items /
    # scan_raw_items do NOT discard items whose first number != chapter, because
    # that first number is a valid section of the current chapter, not a
    # cross-chapter reference.  The B-layer already groups two-level items by
    # their section prefix, so it stays correct either way.
    chapter_first: bool = True
    # Section-scoped EN extraction flag: when True, the extractor ALSO captures
    # NUMBER-FIRST headings ("26.4 Lemma", "24.2 Corollary") and numbered
    # graphics ("Table 1.20", "Figure 3.6") as items — needed only for
    # section-based books whose source prints these (e.g. Fraleigh).  Normal
    # chapter-first EN books keep their exact prior behavior (False).
    section_scoped: bool = False
    # Chapter-LOCAL section numbering (e.g. Karlin: sections are ``§1, §2, §3``
    # that RESET every chapter, NOT global ``§C.S``).  The whole structure /
    # verify tooling assumes globally-prefixed ``§C.S`` section numbers, so a
    # chapter-local ``§N`` header is invisible to both build_structure's
    # scan_skeleton and the D-layer source rescan — producing a vacuous
    # section-continuity PASS.  When True, scan_skeleton accepts a bare
    # single-number heading (``1. Review of…`` / ``2: Two Simple…``) and
    # normalizes it to ``C.N``; the D-layer likewise normalizes md ``§N`` and
    # source ``N.`` to ``C.N`` before comparing.  Default False — only books
    # that genuinely use chapter-local sections opt in; ``§C.S`` books are
    # completely unaffected.
    chapter_local_sections: bool = False
    # BOOK-GLOBAL single-number section numbering (Arnold《数学方法》: sections
    # print ``§12．变分法`` and the number runs GLOBALLY across the book,
    # §1..§52 spanning all chapters — the leading number is NOT the chapter).
    # Orthogonal to `chapter_local_sections` (which resets per chapter); both
    # describe a depth-1 level BELOW the chapter level in `section_types`
    # (e.g. [1, 1] / [1, 1, 5]).  When True:
    #   * the D-layer general path drops its `c[0] == ch` prefix requirement
    #     (a global §12 found on ch3's pages IS ch3's section) and instead
    #     intersects detected tokens with the structure contract's section keys
    #     for that chapter, so OCR noise / cross-chapter references can never
    #     fabricate phantom tail sections ("Ch2 §2." FP class);
    #   * bare-letter sub-block heads ("A. 变分", parent = position under the
    #     nearest preceding §N) become verifiable as role-5 subsections.
    # Default False — standard §C.S books are completely unaffected.
    sections_global: bool = False
    # END-OF-CHAPTER exercise-block headings (Ross《A First Course in
    # Probability》体例: "Problems" / "Theoretical Exercises" / "Self-Test
    # Problems and Exercises").  When declared (non-empty), scan_skeleton treats
    # an anchored heading line matching any of these as the START of the
    # chapter-end exercise region: everything from there to the end of the
    # chapter is exercises — SEC/ITEM detection is latched OFF (STICKY: unlike
    # do Carmo per-section blocks, a Ross chapter never returns to prose), and
    # numeric exercise lines ("3.11. Two cards...") are captured as EXER rows.
    # This kills the FP class where exercise lines "C.N <long sentence>" are
    # mistaken for genuine section headers by the universal detector (Ross ch3:
    # 94 pseudo-sections).  Default [] — books without such blocks are untouched.
    exercise_region_headings: List[str] = field(default_factory=list)
    ignore: List[str] = field(default_factory=list)
    manual: Optional[str] = None
    # --- nested section hierarchy (D-layer, orthogonal to grouping) ----------
    # `section_types`: role code per level (e.g. [1, 2, 3] = chapter/section/
    #   subsection).  The depth of each role is FIXED by its segmentation and is
    #   resolved via the SECTION_TYPE_DEPTH map — it is NOT stored as a parallel
    #   `section_depths` field (that would only drift out of sync, and would
    #   wrongly equate `depth == role_code`).  Defaults to []; `from_dict`
    #   populates it from verify_config.json or, when absent, from
    #   ORDINAL_SECTION_TYPES (back-compat).  Read the per-level depths via the
    #   derived `section_depths` property (never assign it).
    section_types: List[int] = field(default_factory=list)

    # --- formula sequence-label audit (Q-LAYER) ----------------------------
    # Opt-in via a SINGLE `formula` map in verify_config.json (mirrors the
    # entry-ordinal `ordinal` groups — NOT flat fields). When `formula` is
    # None the whole Q-LAYER is a pure no-op (neutral `q_*` metadata, no
    # report, never contributes to FAIL), so the 16 legacy layers and already
    # finished books are completely untouched.  Map shape:
    #   {"type": 3, "scope": 2, "ignore": []}
    #   type  : ORDINAL_* style code (1..9); `depth` is DERIVED from `type`
    #           via the canonical ORDINAL_DEPTH map, so it is NOT a separate
    #           field (it can never desync from `type`).
    #   scope : 1=book / 2=chapter / 3=section — number reset window; the
    #           cross-chapter guard (first component == current chapter) is
    #           ON iff scope == 2.
    #   ignore: list of normalized formula numbers to SKIP in the 1:1
    #           comparison (neither flagged FABRICATED nor MISSING).
    formula: Optional[dict] = None

    # 🔴 Figure labels/depth now live in `ordinal` (the Figure group's `type`
    # encodes the component count = `depth` = former `figure.components`).  No
    # separate `figure` block.  figure_io derives labels/components from that
    # group; see lib/figure_io.py.  (A book with no figures simply has no
    # Figure group in `ordinal`.)

    # --- grouping helpers (config-side, so every consumer is consistent) ---
    @property
    def primary_group(self) -> 'GroupConfig':
        """First non-uncat group; falls back to [0] if all are uncat."""
        for g in self.ordinal:
            if not g.is_uncat:
                return g
        return self.ordinal[0]

    @property
    def primary_type(self) -> int:
        return self.primary_group.type

    @property
    def default_depth(self) -> int:
        return max(g.depth for g in self.ordinal)

    def uncat_group(self) -> 'GroupConfig':
        return next((g for g in self.ordinal if g.is_uncat), self.ordinal[0])

    def has_style(self, *codes: int) -> bool:
        return any(g.type in codes for g in self.ordinal)

    def group_for_label(self, label: str) -> 'GroupConfig':
        """Return the group whose `name` matches `label` (CN/EN, any case).

        Uses `_canon_label` so bilingual labels align (定理↔Theorem,
        练习↔Exercise).  Unknown labels fall back to the uncat group."""
        if not label:
            return self.uncat_group()
        canon = _canon_label(label)
        for g in self.ordinal:
            if g.is_uncat:
                continue
            for nm in g.name:
                if _canon_label(nm) == canon:
                    return g
        return self.uncat_group()

    @property
    def structure(self) -> Optional[str]:
        # Driven by the primary group's style code (common books -> None).
        return ORDINAL_STRUCTURE.get(self.primary_type)

    @property
    def family(self) -> str:
        return self.structure or ('en' if self.language == 'en' else 'cn')

    # figure_labels removed: figure prefixes are now derived from the `ordinal`
    # Figure group via lib.figure_io.load_fig_labels (no BookConfig field needed).

    # --- nested section-hierarchy helpers (D-layer) --------------------------
    # NOTE: `max_level` / `section_depth` / `section_role` are ORTHOGONAL to the
    # existing `depth` property. `depth` counts the numeric components of an
    # *item* key (e.g. N.S-N -> depth 3, the ITEM numbering depth). `max_level`
    # counts how many SECTION-hierarchy levels (chapter / section / subsection /
    # sub-subsection) the D-layer verifies. The two are independent axes and must
    # not be conflated.
    @property
    def max_level(self) -> int:
        """Number of verified section-hierarchy levels (>= 1)."""
        return len(self.section_depths)

    def section_depth(self, level: int) -> int:
        """Numeric component count for hierarchy level `level` (1-based).

        Resolved via the SECTION_TYPE_DEPTH map from the role *code* at that
        level.  Depth is NOT inferred from the code number -- an unregistered
        role raises ConfigError so a future non-positional role cannot silently
        inherit `depth == code`.
        """
        code = self.section_types[level - 1]
        if code not in SECTION_TYPE_DEPTH:
            raise ConfigError(
                f"[CONFIG] section_types 含未登记 role {code}；"
                f"请在 SECTION_TYPE_DEPTH 中登记其分段深度。")
        return SECTION_TYPE_DEPTH[code]

    def section_role(self, level: int) -> int:
        """Role code (SECTION_ROLE_*) for hierarchy level `level` (1-based)."""
        return self.section_types[level - 1]

    @property
    def sections_unnumbered(self) -> bool:
        """True iff any declared section level is the UNNUMBERED role (0).

        Drives the P-layer missing-section gate: when True, `## § <title>`
        headings (no number) are matched by POSITION against the structure
        contract, so a book whose original subsections carry no ordinal is
        never forced to fabricate `## §N`. Mirrors the `type 0 / depth 0`
        section convention — see SECTION_ROLE_UNNUMBERED / SECTION_TYPE_DEPTH."""
        return SECTION_ROLE_UNNUMBERED in self.section_types


    @property
    def section_depths(self) -> List[int]:
        """Resolved nesting-depth per level — DERIVED from `section_types`
        via SECTION_TYPE_DEPTH. Depth is NOT stored independently, so it can
        never desync from the authoritative role codes. Consumers that read
        `cfg.section_depths` (D-layer, structure builder, skeleton scanner)
        get a freshly-derived list every time."""
        return [self.section_depth(i + 1) for i in range(len(self.section_types))]

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BookConfig':
        if not isinstance(data, dict):
            data = {}

        # --- ordinal: MUST be a GroupConfig ARRAY (old int/str/levels REJECTED) ---
        raw = data.get('ordinal')
        if isinstance(raw, int):
            raise ConfigError(
                "[CONFIG] verify_config.json 仍使用旧版整型 ordinal，已废弃。"
                "请重新运行：python config/verify_config/make_config.py --force <book>/_extract"
                " 生成数组形式（见 config/config_schema.md §配置字段说明）。")
        if isinstance(raw, str):
            raise ConfigError(
                "[CONFIG] ordinal 必须是 GroupConfig 数组，字符串格式已废弃。")
        if not isinstance(raw, list) or not raw:
            # No ordinal / empty array -> a single UNNUMBERED uncat group.
            # NOTE: deliberately type 0 (unnumbered), NOT the legacy default
            # type 3 — per the "no default type" rule, an absent ordinal must
            # not be silently upgraded to a fabricated three-level scheme.
            # require_complete() still decides whether to hard-fail.
            groups = [GroupConfig(type=0)]
        else:
            groups = []
            for i, g in enumerate(raw):
                if not isinstance(g, dict):
                    raise ConfigError(f"[CONFIG] ordinal[{i}] 必须是对象（GroupConfig）")
                t = int(g.get('type', ORDINAL_THREE_LEVEL))
                if t not in ORDINAL_CODES:
                    raise ConfigError(f"[CONFIG] ordinal[{i}].type={t} 非法（应 {'..'.join(map(str, sorted(ORDINAL_CODES)))}）")
                nm = g.get('name') or ["uncat"]
                if not isinstance(nm, list) or not all(isinstance(x, str) for x in nm):
                    raise ConfigError(f"[CONFIG] ordinal[{i}].name 必须是字符串数组")
                # `depth` is a DERIVED projection of `type` (GroupConfig.depth);
                # it is intentionally NOT read from the config, so a stale or
                # overridden `depth` can never desync from the authoritative type.
                sc = int(g.get('scope', SCOPE_CHAPTER))
                if sc not in (SCOPE_BOOK, SCOPE_CHAPTER, SCOPE_SECTION):
                    raise ConfigError(f"[CONFIG] ordinal[{i}].scope={sc} 非法（应 1/2/3）")
                groups.append(GroupConfig(type=t, name=list(nm), scope=sc))

        rep = groups[0].type

        # --- nested section hierarchy (D-layer, orthogonal) --------------------
        # Backward compatible: when `section_types` is absent, derive it from the
        # primary group's type via ORDINAL_SECTION_TYPES.  `section_depths` is NO
        # LONGER read from config — depth is DERIVED from each `section_types`
        # role code via the SECTION_TYPE_DEPTH map (see BookConfig.section_depths).
        # A stale `section_depths` key in verify_config.json is ignored silently.
        st = data.get('section_types') or ORDINAL_SECTION_TYPES.get(rep, [1])
        st = [int(x) for x in st if int(x) in SECTION_ROLE_CODES] or [1]
        # `section_types` is a PER-LEVEL list, ordered from the CHAPTER level
        # (element 0) down to the deepest `## §` level.  Each element is the
        # number of ordinal components that level carries in the `## §`
        # numbering (1 = `## §N`, 2 = `## §N.M`, 3 = `## §N.M.K`, …) or 0 when
        # that level is UNNUMBERED.  This matches `make_config._detect_section_
        # hierarchy`, which always prepends the chapter prefix (role 1) for a
        # standard book.  Examples: Kreyszig `[1, 2]` = chapter-prefix (1 comp)
        # + section (`## §1.1`, 2 comp); Silverman `[0, 0]` = chapter IS the
        # file (`# 第N章`, no `## §` number) AND its `## § <标题>` subsections
        # are also unnumbered.  The LENGTH of `section_types` must equal the
        # number of section hierarchy levels (chapter INCLUSIVE) — so a
        # chapter + unnumbered-subsection book is `[0, 0]`, NOT `[0]` (which
        # would describe a single level with no subsections).  Coerce
        # defensively so a hand-written config can never start at role 2+;
        # require_complete() also enforces this as a backstop.
        if st[0] not in (0, 1):
            st[0] = 1

        # --- language (orthogonal; default derived from primary type) ---
        language = str(data.get('language', ORDINAL_LANGUAGE_DEFAULT.get(rep, 'cn')))

        # --- ignore: merge known_gaps + ignore_keys + ignore_fig into ONE set ---
        ignore: List[str] = list(data.get('ignore', []) or [])
        ignore += list(data.get('known_gaps', []) or [])
        ignore += list(data.get('ignore_keys', []) or [])
        ignore += list(data.get('ignore_fig', []) or [])
        seen = set()
        deduped = []
        for x in ignore:
            if x not in seen:
                seen.add(x)
                deduped.append(x)
        ignore = deduped

        # --- manual path (manual_path legacy alias) ---
        manual = data.get('manual', data.get('manual_path'))

        return cls(
            ordinal=groups,
            language=language,
            strict=bool(data.get('strict', True)),
            chapter_first=bool(data.get('chapter_first', True)),
            section_scoped=bool(data.get('section_scoped', False)),
            chapter_local_sections=bool(data.get('chapter_local_sections', False)),
            sections_global=bool(data.get('sections_global', False)),
            exercise_region_headings=[
                str(h) for h in (data.get('exercise_region_headings') or [])
                if str(h).strip()
            ],
            ignore=ignore,
            manual=manual,
            section_types=st,
            # --- Q-LAYER (formula sequence-label) opt-in: single `formula` map ---
            formula=dict(data['formula']) if data.get('formula') else None,
            # (figure labels/components now derived from the `ordinal` Figure
            # group via lib.figure_io — no `figure` field on BookConfig.)
        )


def _norm_win(path):
    """Normalize a filesystem path so native Windows Python can stat it.

    Git-bash / MSYS style paths such as ``/d/study/foo`` (leading slash + a
    single drive letter) are NOT understood by ``os.path.exists`` / ``open`` on
    native Windows Python, which expects ``D:/study/foo``.  Convert the prefix
    to a drive letter and return ``os.path.normpath(path)``.  Any other path
    (POSIX absolute, relative, already drive-letter, non-Windows OS) is returned
    unchanged (after normpath).  This is the single choke-point that fixes the
    "未找到 verify_config.json" failure when a user passes a ``/x/...`` path on
    Windows (Bug #21).
    """
    if not path:
        return path
    m = re.match(r'^/([a-zA-Z])/(.*)$', path)
    if m:
        path = f"{m.group(1).upper()}:/{m.group(2)}"
    elif re.match(r'^/([a-zA-Z])$', path):
        # bare drive root, no subpath ("/d")
        path = f"{path[1].upper()}:/"
    return os.path.normpath(path)


class ConfigLoader:
    """Reads ALL per-book configuration from disk ONCE and exposes it.

    Sources (all under <book>/_extract/ unless noted):
      * verify_config.json  — main per-book config (-> BookConfig)
      * chapter_map.json    — per-chapter page ranges + names
      * figure_index.json   — figure index (for figure layers)
      * ignore_ch{N}.json / ignore_fig_ch{N}.json — per-chapter noise (auto)
      * manual_overrides_ch{N}.json        — per-chapter extraction overrides

    Config files are read once here so layers never re-read files or receive
    config field-by-field.
    """

    def __init__(self, extract_dir: str, book_dir: str,
                 extra_ignore: Optional[List[str]] = None):
        # Bug #21: normalize git-bash style paths (/d/...) to Windows drive
        # letters (D:/...) so os.path.exists / open work on native Windows
        # Python.  Idempotent for already-normal paths.
        self.extract_dir = _norm_win(extract_dir)
        self.book_dir = _norm_win(book_dir)
        self.verify_config_path: Optional[str] = None
        self.verify_config_has_ordinal: bool = False
        self.book = self._load_verify_config()
        self.chapters = self._load_chapter_map()
        self.figure_index = self._load_figure_index()
        # Optional extra ignore entries supplied via CLI (--ignore / --ignore-figure);
        # merged into every chapter's resolved ignore set.
        self.extra_ignore: Set[str] = set(extra_ignore or [])

    # ---- verify_config.json ----
    def _load_verify_config(self) -> BookConfig:
        candidates = [
            os.path.join(self.extract_dir, 'verify_config.json'),
            os.path.join(self.book_dir, 'verify_config.json'),
        ]
        data: Dict[str, Any] = {}
        hit_path: Optional[str] = None
        for p in candidates:
            if os.path.exists(p):
                try:
                    with open(p, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    hit_path = p
                except Exception:
                    data = {}
                break
        # Record WHICH candidate (if any) was actually loaded, plus whether the
        # raw data explicitly declared an `ordinal` ARRAY (the new required form).
        # `require_complete()` needs this to tell "file present but no ordinal"
        # (hard error) from "file absent" (warning + default) — `BookConfig.from_dict`
        # silently defaults ordinal to a single uncat group, so we cannot infer
        # absence from the resolved value alone.
        self.verify_config_path = hit_path
        self.verify_config_has_ordinal = (
            isinstance(data.get('ordinal'), list) and len(data.get('ordinal')) > 0
        )
        # 🔒 上游闸（防"agent 手搓 config 当地基"事故）：verify_config.json 只应来自
        # make_config.py 在 MM Repair 完成后生成的版本。若 _extraction_done.json 缺失，
        # 说明 MM Repair 未完成或本文件是手工产物，一律拒绝加载/消费。
        # 历史已合规完成之书用 `flow_runner.py bootstrap <book_dir>` 依据物理证据
        # 补写 _extraction_done.json 后即通过（且建议重新 make_config 以打 _provenance 戳）。
        if hit_path is not None:
            marker = os.path.join(self.extract_dir, '_extraction_done.json')
            if not os.path.exists(marker):
                raise ConfigError(
                    f"[CONFIG] BLOCKED: {self.extract_dir} 缺 _extraction_done.json"
                    f"（MM Repair 未完成标记）。verify_config.json 不能被加载/消费——"
                    f"它只应来自 make_config.py 在 MM Repair 完成后生成的版本。\n"
                    f"  先完成 MM Repair（模式 A+B 写回 page_*.json，apply 真完成写出"
                    f" _extraction_done.json），或对该书运行\n"
                    f"    python tools/flow_runner.py bootstrap <book_dir>\n"
                    f"  依据物理证据补写完成标记后再跑 verify。严禁手写/手改配置绕过。"
                )
        return BookConfig.from_dict(data)

    def require_complete(self, allow_absent: bool = True) -> None:
        """Validate per-book verify-config completeness (rule H gate).

        Rules:
          * File absent:
              - allow_absent=True  -> WARNING + keep default (ordinal=3, back-compat).
              - allow_absent=False -> raise ConfigError.
          * File present but `ordinal` missing/illegal -> raise ConfigError (hard error).
          * `section_types` explicitly given but with an illegal role code (not
            in SECTION_ROLE_CODES) or a non-1 first level (the chapter is always
            role 1) -> raise ConfigError.  Depth is DERIVED from each role code
            via SECTION_TYPE_DEPTH, so there is NO separate depth field to check
            (and a stale `section_depths` key in the JSON is ignored).

        `BookConfig.from_dict` already does most sanitising/inference, so this is
        a backstop consistency check mainly guarding hand-written mistakes.
        """
        import warnings

        cfg = self.book

        # --- file presence ---
        if self.verify_config_path is None:
            if allow_absent:
                warnings.warn(
                    "[CONFIG] 未找到 verify_config.json，沿用默认单个 uncat 组"
                    "（type 0，无默认编号方案——「no default type」规则）。"
                    "新流程要求在源语言全部初稿完成后，用 config/verify_config/make_config.py 生成 "
                    "<book>/_extract/verify_config.json（至少含 ordinal）。",
                    stacklevel=2,
                )
                return
            raise ConfigError(
                "[CONFIG] 未找到 verify_config.json，且 allow_absent=False。"
                "请先创建 <book>/_extract/verify_config.json（至少含 ordinal）。"
            )

        # --- ordinal array present & every group legal (1..6 / 8 / 9) ---
        # `from_dict` already rejects the old int/str/levels formats and appends a
        # default uncat group, so `verify_config_has_ordinal` (== "ordinal is a
        # non-empty list") is the reliable "was it declared" signal.
        if not self.verify_config_has_ordinal:
            raise ConfigError(
                f"[CONFIG] {self.verify_config_path} 未声明 ordinal 数组"
                f"（应为 GroupConfig 数组，例如 "
                f'[{{"type": 3, "name": ["uncat"], "scope": 2}}]）。'
                f" 旧版整型 ordinal 已废弃，请运行 "
                f"python config/verify_config/make_config.py --force <book>/_extract 重新生成。"
            )
        for gi, g in enumerate(cfg.ordinal):
            if g.type not in ORDINAL_CODES:
                raise ConfigError(
                    f"[CONFIG] {self.verify_config_path} ordinal[{gi}].type={g.type}"
                    f" 非法（应 {'..'.join(map(str, sorted(ORDINAL_CODES)))}）。")
            if g.scope not in (SCOPE_BOOK, SCOPE_CHAPTER, SCOPE_SECTION):
                raise ConfigError(
                    f"[CONFIG] {self.verify_config_path} ordinal[{gi}].scope={g.scope}"
                    f" 非法（应 1/2/3）。")
                # --- section_types (only the role codes; depth is derived) ----------
        # `from_dict` already filters codes against SECTION_ROLE_CODES and forces
        # the first to 1, so this is a backstop for hand-written configs.  Depth
        # is NOT a separate field -- it is resolved via SECTION_TYPE_DEPTH from
        # each role code in `section_types`.
        if cfg.section_types:
            for code in cfg.section_types:
                if code not in SECTION_ROLE_CODES:
                    raise ConfigError(
                        f"[CONFIG] {self.verify_config_path} section_types 含非法角色码 "
                        f"{code}（应在 {SECTION_ROLE_CODES}）。"
                    )
            if cfg.section_types[0] not in (0, 1):
                raise ConfigError(
                    f"[CONFIG] {self.verify_config_path} section_types[0] 必须为 0 或 1"
                    f"（0=无序号标书的首层小节，1=章首分量）。"
                )
            # Sanity: every declared role must resolve to a known depth.
            for code in cfg.section_types:
                if code not in SECTION_TYPE_DEPTH:
                    raise ConfigError(
                        f"[CONFIG] {self.verify_config_path} section_types 含未登记角色码 "
                        f"{code}；请在 SECTION_TYPE_DEPTH 中登记其分段深度。")

    # ---- chapter_map.json ----
    def _load_chapter_map(self) -> Dict[int, ChapterInfo]:
        p = os.path.join(self.extract_dir, 'chapter_map.json')
        out: Dict[int, ChapterInfo] = {}
        if not os.path.exists(p):
            return out
        try:
            with open(p, 'r', encoding='utf-8-sig') as f:
                cm = json.load(f)
        except Exception:
            return out
        # Three accepted shapes:
        #   * {"chapters": [ {...}, {...} ]}   Apostol (ch inside each value)
        #   * {"1": {...}, "2": {...}, ...}    Kreyszig / Koopman — chapter
        #                                        number is the DICT KEY; the
        #                                        value has NO 'ch' field.
        #   * [ {...}, {...} ]                 bare list (legacy)
        # NOTE: chapter 0 is legitimate (Fraleigh §0 preliminaries, ...).
        # `ChapterInfo.from_dict` coerces a MISSING chapter key to 0, so a
        # falsy-`ch` guard silently drops genuine ch0 entries; skip only
        # entries that carry no chapter-identifying key at all.
        def _has_ch_key(d):
            return any(k in d for k in ('ch', 'num', 'chapter'))

        if isinstance(cm, dict) and 'chapters' in cm:
            entries = cm['chapters']
            for e in entries:
                if not _has_ch_key(e):
                    continue
                info = ChapterInfo.from_dict(e)
                out[info.ch] = info
        elif isinstance(cm, dict):
            for k, e in cm.items():
                if not isinstance(e, dict):
                    continue
                e = dict(e)
                # Flat dict: the key IS the chapter number; inject it so
                # ChapterInfo.from_dict can pick it up even though the value
                # itself carries no 'ch'/'num'/'chapter' field.
                if 'ch' not in e and 'num' not in e and 'chapter' not in e:
                    e['ch'] = int(k) if str(k).isdigit() else k
                info = ChapterInfo.from_dict(e)
                out[info.ch] = info
        elif isinstance(cm, list):
            for e in cm:
                if not _has_ch_key(e):
                    continue
                info = ChapterInfo.from_dict(e)
                out[info.ch] = info
        return out

    # ---- figure_index.json ----
    def _load_figure_index(self):
        p = os.path.join(self.extract_dir, 'figure_index.json')
        if not os.path.exists(p):
            return None
        try:
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return None

    # ---- accessors ----
    def chapter(self, ch: int) -> Optional[ChapterInfo]:
        return self.chapters.get(ch)

    def ignore_for_chapter(self, ch: int) -> Set[str]:
        """Resolved ignore set for a chapter: book-level ignore + per-chapter
        ignore_ch{N}.json + ignore_fig_ch{N}.json + CLI extra ignore."""
        out: Set[str] = set(self.book.ignore)
        out |= set(_load_ignore_file(os.path.join(self.extract_dir, f'ignore_ch{ch}.json')))
        out |= set(_load_ignore_file(os.path.join(self.extract_dir, f'ignore_fig_ch{ch}.json')))
        out |= self.extra_ignore
        return out

    def manual_for_chapter(self, ch: int) -> List[Dict[str, Any]]:
        """Resolved manual overrides for a chapter: book-level manual file +
        per-chapter manual_overrides_ch{N}.json."""
        out: List[Dict[str, Any]] = []
        if self.book.manual and os.path.exists(self.book.manual):
            try:
                with open(self.book.manual, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    out.extend(data)
            except Exception:
                pass
        per = os.path.join(self.extract_dir, f'manual_overrides_ch{ch}.json')
        if os.path.exists(per):
            try:
                with open(per, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, list):
                    out.extend(data)
            except Exception:
                pass
        return out

    def config_for_chapter(self, ch: int) -> BookConfig:
        """A per-chapter BookConfig with the resolved ignore set applied.

        Used to build each chapter's VerifyContext so the layer sees one
        unified `ignore` (no field-by-field passthrough)."""
        return replace(self.book, ignore=list(self.ignore_for_chapter(ch)))
