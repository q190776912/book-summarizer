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
    falls into the `uncat` fallback group.  Group fields: `type` (ORDINAL_* 1..7),
    `name` (label categories), `depth` (numeric components), `scope` (1 book /
    2 chapter / 3 section — the counter reset boundary).  Values for `type`:
        1 single | 2 two_level(CN) | 3 three_level(CN, default)
        4 en (EN two-level) | 5 roman | 6 gm | 7 fraleigh
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
from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional, Set


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
# (single / two_level / three_level / en / gm / roman / fraleigh) into a
# single field.  `language` (cn/en) is an orthogonal axis.
ORDINAL_SINGLE = 1
ORDINAL_TWO_LEVEL = 2      # CN two-level (N.M, section-first); no chapter filter
ORDINAL_THREE_LEVEL = 3    # CN three-level (N.M.K) — default
ORDINAL_EN = 4             # EN two-level (N.M, chapter-first; rich EN labels)
ORDINAL_ROMAN = 5          # three-level with ROMAN chapter (e.g. I.2.3)
ORDINAL_GM = 6             # two-level, bare per-section ordinals (no chapter)
ORDINAL_FRALEIGH = 7       # two-level, section-based numbering (no chapter)
ORDINAL_VAKIL = 8          # EN three-level, number-first (N.M.item + N.M.A exercises), e.g. Vakil

ORDINAL_CODES = (1, 2, 3, 4, 5, 6, 7, 8)
ORDINAL_NAME = {
    1: 'single', 2: 'two_level', 3: 'three_level',
    4: 'en', 5: 'roman', 6: 'gm', 7: 'fraleigh',
}
# Numbering depth (numeric components) per ordinal code.
ORDINAL_DEPTH = {1: 1, 2: 2, 3: 3, 4: 2, 5: 3, 6: 2, 7: 2, 8: 3}
# Structural style per ordinal code (None = common depth-driven parsing).
ORDINAL_STRUCTURE = {1: None, 2: None, 3: None, 4: None, 5: 'roman', 6: 'gm', 7: 'fraleigh'}
# Default language per ordinal code (common CN families -> cn, EN families -> en).
ORDINAL_LANGUAGE_DEFAULT = {1: 'cn', 2: 'cn', 3: 'cn', 4: 'en', 5: 'en', 6: 'en', 7: 'en', 8: 'en'}
# Default figure-label prefixes (used when verify_config.json has no
# `figure.labels`). Mirrors lib.figure_io.FIGURE_LABELS_DEFAULT — duplicated on
# purpose to keep verify_config.py import-clean (no figure-module import).
FIGURE_LABELS_DEFAULT = ["图", "Figure", "Fig"]
# Back-compat: legacy STRING ordinal values -> int code (with a warning).
_LEGACY_ORDINAL_STR = {
    'single': 1, 'two_level': 2, 'two-level': 2, 'three_level': 3, 'three-level': 3,
    'en': 4, 'roman': 5, 'gm': 6, 'fraleigh': 7,
}

# --- section role codes (1..4) for the nested section hierarchy ------------
# Each level in the D-layer section hierarchy carries a ROLE. These codes are
# stable identifiers stored in `section_types`; `section_depths` stores the
# matching numeric component count per level (e.g. role 3 = subsection carried
# by a 3-component number C.S.K).
SECTION_ROLE_CHAPTER       = 1
SECTION_ROLE_SECTION       = 2
SECTION_ROLE_SUBSECTION    = 3
SECTION_ROLE_SUBSUBSECTION = 4
SECTION_ROLE_CODES = (1, 2, 3, 4)

# Default section-types (role codes) per ordinal code. BACK-COMPAT fallback
# used only when a verify_config.json does not explicitly declare
# `section_types`/`section_depths`.  The verified section hierarchy is
# ORTHOGONAL to the item-numbering depth: it describes how many NESTED SECTION
# levels the book's markdown / source actually has (## §N, ## §N.M, ## §N.M.K),
# NOT how many components an item key carries.  For the historic three-level CN
# families (type 3 / 5 / 8) the convention is that the book genuinely nests
# sections three deep (chapter / section / subsection 1.1.1), so the default is
# [1, 2, 3] — item keys such as ``1.3-4`` whose deepest component is an ITEM
# counter (NOT a subsection) are the Kreyszig-shaped exception and must declare
# ``"section_depths": [1, 2]`` explicitly; make_config.py detects and emits
# this automatically so the fallback is only reached by genuine 3-level books.
# Two-level families verify chapter + section only ([1, 2]); single-level
# verifies the chapter prefix ([1]).
ORDINAL_SECTION_TYPES = {
    1: [1], 2: [1, 2], 3: [1, 2, 3], 4: [1, 2],
    5: [1, 2, 3], 6: [1, 2], 7: [1, 2], 8: [1, 2, 3],
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
    type: int = ORDINAL_THREE_LEVEL          # ORDINAL_* style code (1..7)
    name: List[str] = field(default_factory=lambda: ["uncat"])  # label categories
    depth: int = 3                           # numeric components of an item key
    scope: int = SCOPE_CHAPTER               # 1=book / 2=chapter / 3=section

    @property
    def is_uncat(self) -> bool:
        return "uncat" in self.name

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
    ch: int = 0
    start: int = 0
    end: int = 0
    name: str = ''
    name_en: str = ''
    name_cn: str = ''

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> 'ChapterInfo':
        return cls(
            ch=int(d.get('ch', d.get('num', d.get('chapter', 0)) or 0)),
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
    ignore: List[str] = field(default_factory=list)
    manual: Optional[str] = None
    # --- nested section hierarchy (D-layer, orthogonal to grouping) ----------
    # `section_types`  : role code per level   (e.g. [1, 2, 3] = chapter/section/subsection)
    # `section_depths`: numeric component count per level (parallel to section_types;
    #                   always starts at 1 so level 1 is the chapter prefix).
    # Both default to []; `from_dict` populates them from verify_config.json or,
    # when absent, from ORDINAL_SECTION_TYPES (back-compat).
    section_types: List[int] = field(default_factory=list)
    section_depths: List[int] = field(default_factory=list)

    # --- formula sequence-label audit (Q-LAYER) ----------------------------
    # Opt-in via a SINGLE `formula` map in verify_config.json (mirrors the
    # entry-ordinal `ordinal` groups — NOT flat fields). When `formula` is
    # None the whole Q-LAYER is a pure no-op (neutral `q_*` metadata, no
    # report, never contributes to FAIL), so the 16 legacy layers and already
    # finished books are completely untouched.  Map shape:
    #   {"type": 3, "depth": 3, "scope": 2, "ignore": []}
    #   type  : ORDINAL_* style code (1..8); selects the DEFAULT depth (from
    #           ORDINAL_SECTION_TYPES) when `depth` is absent.
    #   depth : numeric component count of a formula key (2 -> 1.17,
    #           3 -> 11.1-1). Drives the derived source-extraction regex.
    #   scope : 1=book / 2=chapter / 3=section — number reset window; the
    #           cross-chapter guard (first component == current chapter) is
    #           ON iff scope == 2.
    #   ignore: list of normalized formula numbers to SKIP in the 1:1
    #           comparison (neither flagged FABRICATED nor MISSING).
    formula: Optional[dict] = None

    # --- figure sequential-label convention (book-specific) ---------------
    # Opt-in `figure` map in verify_config.json: {"labels": ["图", "Figure",
    # "Fig"]} lists the prefix keywords that precede a figure's sequential
    # number. Drives extract_figures.parse_fig_label + assign_figures.gather_refs
    # so each book's OWN Figure/图/Fig. convention is honored (NOT a hardcoded
    # list). The figure scripts read verify_config.json directly; this field
    # just surfaces it for ConfigLoader-based consumers.
    figure: Optional[dict] = None

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

    @property
    def figure_labels(self) -> List[str]:
        """Book-specific figure-label prefixes (verify_config.json `figure.labels`).
        Honors each book's OWN Figure / 图 / Fig. convention; defaults ONLY when
        the `figure` block or `labels` key is absent. An explicit empty
        `{"labels": []}` is the "no figure ordinal label" marker and returns `[]`
        (zero-match), NOT the default — so a label-less book is not mis-matched."""
        fig = self.figure
        if isinstance(fig, dict) and "labels" in fig and isinstance(fig.get("labels"), list):
            return [str(x) for x in fig["labels"]]
        return list(FIGURE_LABELS_DEFAULT)

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
        """Numeric component count for hierarchy level `level` (1-based)."""
        return self.section_depths[level - 1]

    def section_role(self, level: int) -> int:
        """Role code (SECTION_ROLE_*) for hierarchy level `level` (1-based)."""
        return self.section_types[level - 1]

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
            # No ordinal / empty array -> default single uncat group (let
            # require_complete() decide whether to hard-fail or use the default).
            groups = [GroupConfig()]
        else:
            groups = []
            for i, g in enumerate(raw):
                if not isinstance(g, dict):
                    raise ConfigError(f"[CONFIG] ordinal[{i}] 必须是对象（GroupConfig）")
                t = int(g.get('type', ORDINAL_THREE_LEVEL))
                if t not in ORDINAL_CODES:
                    raise ConfigError(f"[CONFIG] ordinal[{i}].type={t} 非法（应 1..8）")
                nm = g.get('name') or ["uncat"]
                if not isinstance(nm, list) or not all(isinstance(x, str) for x in nm):
                    raise ConfigError(f"[CONFIG] ordinal[{i}].name 必须是字符串数组")
                dp = int(g.get('depth', ORDINAL_DEPTH.get(t, 3)))
                if dp < 1:
                    raise ConfigError(f"[CONFIG] ordinal[{i}].depth={dp} 必须 >=1")
                sc = int(g.get('scope', SCOPE_CHAPTER))
                if sc not in (SCOPE_BOOK, SCOPE_CHAPTER, SCOPE_SECTION):
                    raise ConfigError(f"[CONFIG] ordinal[{i}].scope={sc} 非法（应 1/2/3）")
                groups.append(GroupConfig(type=t, name=list(nm), depth=dp, scope=sc))

        rep = groups[0].type

        # --- nested section hierarchy (D-layer, orthogonal) --------------------
        # Backward compatible: when `section_types` is absent, derive it from the
        # primary group's type via ORDINAL_SECTION_TYPES.
        st = data.get('section_types') or ORDINAL_SECTION_TYPES.get(rep, [1])
        st = [int(x) for x in st if int(x) in SECTION_ROLE_CODES] or [1]
        sd = data.get('section_depths')
        if sd:
            sd = [int(x) for x in sd]
            if len(sd) != len(st) or any(d < 1 for d in sd):
                sd = list(st)
        else:
            sd = list(st)
        if sd[0] != 1:
            sd[0] = 1

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
            ignore=ignore,
            manual=manual,
            section_types=st,
            section_depths=sd,
            # --- Q-LAYER (formula sequence-label) opt-in: single `formula` map ---
            formula=dict(data['formula']) if data.get('formula') else None,
            # --- figure sequential-label convention (book-specific) ----------
            figure=dict(data['figure']) if data.get('figure') else None,
        )


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
        self.extract_dir = extract_dir
        self.book_dir = book_dir
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
        return BookConfig.from_dict(data)

    def require_complete(self, allow_absent: bool = True) -> None:
        """Validate per-book verify-config completeness (rule H gate).

        Rules:
          * File absent:
              - allow_absent=True  -> WARNING + keep default (ordinal=3, back-compat).
              - allow_absent=False -> raise ConfigError.
          * File present but `ordinal` missing/illegal -> raise ConfigError (hard error).
          * `section_types` / `section_depths` explicitly given but inconsistent
            (length mismatch / component < 1 / bad role code / depth[0] != 1)
            -> raise ConfigError.

        `BookConfig.from_dict` already does most sanitising/inference, so this is
        a backstop consistency check mainly guarding hand-written mistakes.
        """
        import warnings

        cfg = self.book

        # --- file presence ---
        if self.verify_config_path is None:
            if allow_absent:
                warnings.warn(
                    "[CONFIG] 未找到 verify_config.json，沿用默认 ordinal=3（向后兼容）。"
                    "新流程要求在源语言全部初稿完成后，用 config/verify_config/make_config.py 生成 "
                    "<book>/_extract/verify_config.json（至少含 ordinal）。",
                    stacklevel=2,
                )
                return
            raise ConfigError(
                "[CONFIG] 未找到 verify_config.json，且 allow_absent=False。"
                "请先创建 <book>/_extract/verify_config.json（至少含 ordinal）。"
            )

        # --- ordinal array present & every group legal (1..7) ---
        # `from_dict` already rejects the old int/str/levels formats and appends a
        # default uncat group, so `verify_config_has_ordinal` (== "ordinal is a
        # non-empty list") is the reliable "was it declared" signal.
        if not self.verify_config_has_ordinal:
            raise ConfigError(
                f"[CONFIG] {self.verify_config_path} 未声明 ordinal 数组"
                f"（应为 GroupConfig 数组，例如 "
                f'[{{"type": 3, "name": ["uncat"], "depth": 3, "scope": 2}}]）。'
                f" 旧版整型 ordinal 已废弃，请运行 "
                f"python config/verify_config/make_config.py --force <book>/_extract 重新生成。"
            )
        for gi, g in enumerate(cfg.ordinal):
            if g.type not in ORDINAL_CODES:
                raise ConfigError(
                    f"[CONFIG] {self.verify_config_path} ordinal[{gi}].type={g.type}"
                    f" 非法（应 1..8）。")
            if g.depth < 1:
                raise ConfigError(
                    f"[CONFIG] {self.verify_config_path} ordinal[{gi}].depth={g.depth}"
                    f" 必须 >=1。")
            if g.scope not in (SCOPE_BOOK, SCOPE_CHAPTER, SCOPE_SECTION):
                raise ConfigError(
                    f"[CONFIG] {self.verify_config_path} ordinal[{gi}].scope={g.scope}"
                    f" 非法（应 1/2/3）。")
        # --- section_types / section_depths (only when explicitly given) ---
        if cfg.section_types or cfg.section_depths:
            if len(cfg.section_types) != len(cfg.section_depths):
                raise ConfigError(
                    f"[CONFIG] {self.verify_config_path} section_types 与 section_depths "
                    f"长度不等（{len(cfg.section_types)} vs {len(cfg.section_depths)}）。"
                )
            if any(d < 1 for d in cfg.section_depths):
                raise ConfigError(
                    f"[CONFIG] {self.verify_config_path} section_depths 含非法分量（<1）。"
                )
            for code in cfg.section_types:
                if code not in SECTION_ROLE_CODES:
                    raise ConfigError(
                        f"[CONFIG] {self.verify_config_path} section_types 含非法角色码 "
                        f"{code}（应在 {SECTION_ROLE_CODES}）。"
                    )
            if cfg.section_depths[0] != 1:
                raise ConfigError(
                    f"[CONFIG] {self.verify_config_path} section_depths[0] 必须为 1"
                    f"（章首分量）。"
                )

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
        if isinstance(cm, dict) and 'chapters' in cm:
            entries = cm['chapters']
            for e in entries:
                info = ChapterInfo.from_dict(e)
                if info.ch:
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
                if info.ch:
                    out[info.ch] = info
        elif isinstance(cm, list):
            for e in cm:
                info = ChapterInfo.from_dict(e)
                if info.ch:
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
