"""lib/config.py — single source of truth for ALL per-book verify configuration.

This module replaces the old `ManagerConfig` (verify/registry.py) +
`BNumberingConfig` (verify/layers/b_layer.py) and the scattered inline reads of
`chapter_map.json` / `figure_index.json`.  Every layer reads its configuration
through a `ConfigLoader` instance (constructed ONCE per run), never by
re-reading files or by receiving config field-by-field through a context object.

Config schema (per the 2026-08-06 refactor decision):

  * `ordinal` is the ONE numbering-style selector, encoded as a single INTEGER
    (see the ORDINAL_* constants below).  It ABSORBS the old `levels` numeric
    depth (1/2/3) AND the old `scheme` family (single/two_level/three_level/
    en/gm/roman/fraleigh) into one field.  The old `scheme` field is GONE —
    it is no longer read.  Values (integer codes):
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


# --- separation modes for `separate_types` ---------------------------------
# ALWAYS compare with `==` against these NAMED constants — never `>=`.
# A greater number must NOT silently inherit the per-type behaviour; each new
# mode MUST get its own explicit branch.
SEP_COMBINED = 0   # 0: all entry types share ONE counter per scope
SEP_PER_TYPE = 1   # 1: each entry type (Thm/Lem/Def/Ex/...) its own counter

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

ORDINAL_CODES = (1, 2, 3, 4, 5, 6, 7)
ORDINAL_NAME = {
    1: 'single', 2: 'two_level', 3: 'three_level',
    4: 'en', 5: 'roman', 6: 'gm', 7: 'fraleigh',
}
# Numbering depth (numeric components) per ordinal code.
ORDINAL_DEPTH = {1: 1, 2: 2, 3: 3, 4: 2, 5: 3, 6: 2, 7: 2}
# Structural style per ordinal code (None = common depth-driven parsing).
ORDINAL_STRUCTURE = {1: None, 2: None, 3: None, 4: None, 5: 'roman', 6: 'gm', 7: 'fraleigh'}
# Default language per ordinal code (common CN families -> cn, EN families -> en).
ORDINAL_LANGUAGE_DEFAULT = {1: 'cn', 2: 'cn', 3: 'cn', 4: 'en', 5: 'en', 6: 'en', 7: 'en'}
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

# Default section-types (role codes) per ordinal code. This is the BACK-COMPAT
# fallback when a verify_config.json does not explicitly declare `section_types`.
# It mirrors the historical D-layer behaviour exactly:
#   * ordinals 2/4/6/7 only verified the section level (2-part numbers);
#   * ordinal 3/5 verified subsections (3-part numbers, 1.1.1) — previously via
#     the dead D_MD_NESTED_SEC_RE, now live for the first time;
#   * ordinal 1 is single-level (chapter only).
ORDINAL_SECTION_TYPES = {
    1: [1], 2: [1, 2], 3: [1, 2, 3], 4: [1, 2],
    5: [1, 2, 3], 6: [1, 2], 7: [1, 2],
}


def ordinal_depth(ordinal: int) -> int:
    """Numeric component count for an ordinal code (old `levels` value)."""
    return ORDINAL_DEPTH.get(int(ordinal), 3)


def _load_ignore_file(path: str) -> List[str]:
    """Read a JSON list/dict of confirmed-noise keys; return a list.

    Mirrors the legacy `verify.ignore_files.load_ignore` semantics but is
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
      * `ordinal` (int) — the ONE numbering-style selector.  Encodes both the
        depth (1/2/3) and the structural style (cn/en/roman/gm/fraleigh) as a
        single integer code (see ORDINAL_* constants).  The old `levels`
        (numeric depth) and `scheme` (family) fields are GONE — folded in here.
      * `language` (cn/en) is an orthogonal axis, defaulted from `ordinal`.
      * `ignore` is ONE unified list merging the old `known_gaps` +
        `ignore_keys` + `ignore_fig` semantics.
      * `manual` is a path to the extraction-override JSON (kept separate from
        the flat `ignore` set).
      * `disable` is GONE — every layer always runs; suppression is via
        `ignore` + the warning gate.
    """
    ordinal: int = ORDINAL_THREE_LEVEL
    language: str = 'cn'
    scope: str = 'chapter'
    separate_types: int = SEP_PER_TYPE
    strict: bool = True
    ignore: List[str] = field(default_factory=list)
    manual: Optional[str] = None
    # --- nested section hierarchy (D-layer) -----------------------------------
    # `section_types`  : role code per level   (e.g. [1, 2, 3] = chapter/section/subsection)
    # `section_depths`: numeric component count per level (parallel to section_types;
    #                   always starts at 1 so level 1 is the chapter prefix).
    # Both default to []; `from_dict` populates them from verify_config.json or,
    # when absent, from ORDINAL_SECTION_TYPES (back-compat).
    section_types: List[int] = field(default_factory=list)
    section_depths: List[int] = field(default_factory=list)

    # --- derived helpers (kept as methods so grouping logic stays config-side) ---
    @property
    def depth(self) -> int:
        return ORDINAL_DEPTH.get(self.ordinal, 3)

    @property
    def structure(self) -> Optional[str]:
        # Internal derived helper (NOT a config field) — selects the structural
        # variant parser for roman/gm/fraleigh. Common books return None.
        return ORDINAL_STRUCTURE.get(self.ordinal)

    @property
    def family(self) -> str:
        return self.structure or ('en' if self.language == 'en' else 'cn')

    def group_prefix_len(self) -> int:
        sp = {'book': 0, 'chapter': 1, 'section': 2}.get(self.scope, 1)
        return min(sp, max(0, self.depth - 1))

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
        import warnings
        if not isinstance(data, dict):
            data = {}

        # --- ordinal: single integer selector (depth + structural style) ---
        # The old `scheme` field is NO LONGER READ.  The old `levels` (numeric
        # depth 1/2/3) is accepted as a graceful fallback (maps directly to
        # ordinal 1/2/3).  Legacy STRING ordinal values are mapped with a warning.
        if 'ordinal' in data:
            v = data['ordinal']
            if isinstance(v, str):
                ordinal = _LEGACY_ORDINAL_STR.get(v)
                if ordinal is None:
                    warnings.warn(
                        f"verify_config: unknown ordinal string '{v}'; "
                        f"falling back to {ORDINAL_THREE_LEVEL} (three_level).")
                    ordinal = ORDINAL_THREE_LEVEL
                else:
                    warnings.warn(
                        f"verify_config: numeric ordinal expected; "
                        f"mapped string '{v}' -> {ordinal}.")
            else:
                ordinal = int(v)
        elif 'levels' in data:
            lv = int(data['levels'])
            if lv not in (1, 2, 3):
                warnings.warn(
                    f"verify_config: levels={lv} out of range; "
                    f"falling back to {ORDINAL_THREE_LEVEL}.")
                lv = ORDINAL_THREE_LEVEL
            ordinal = lv
        else:
            ordinal = ORDINAL_THREE_LEVEL
        if ordinal not in ORDINAL_CODES:
            warnings.warn(
                f"verify_config: unknown ordinal {ordinal}; "
                f"falling back to {ORDINAL_THREE_LEVEL}.")
            ordinal = ORDINAL_THREE_LEVEL

        # --- nested section hierarchy (D-layer) -------------------------------
        # Backward compatible: when `section_types` is absent, derive it from the
        # ordinal via ORDINAL_SECTION_TYPES. `section_depths` defaults to a copy
        # of `section_types` (role code == component count) unless explicitly
        # given with the same length and all entries >= 1. Level 1 (chapter) must
        # always have depth 1.
        st = data.get('section_types') or ORDINAL_SECTION_TYPES.get(ordinal, [1])
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

        # --- language (orthogonal; default derived from ordinal) ---
        language = str(data.get('language', ORDINAL_LANGUAGE_DEFAULT.get(ordinal, 'cn')))

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

        # --- separation mode (named constants, never `>=`) ---
        sep = int(data.get('separate_types', SEP_PER_TYPE))
        if sep not in (SEP_COMBINED, SEP_PER_TYPE):
            warnings.warn(
                f"BookConfig: unknown separate_types={sep!r}; "
                f"falling back to SEP_COMBINED (0). Add an explicit branch "
                f"for this mode in b_layer.py (grouping + _group_key).")
            sep = SEP_COMBINED

        return cls(
            ordinal=ordinal,
            language=language,
            scope=str(data.get('scope', 'chapter')),
            separate_types=sep,
            strict=bool(data.get('strict', True)),
            ignore=ignore,
            manual=manual,
            section_types=st,
            section_depths=sd,
        )


class ConfigLoader:
    """Reads ALL per-book configuration from disk ONCE and exposes it.

    Sources (all under <book>/_extract/ unless noted):
      * verify_config.json  — main per-book config (-> BookConfig)
      * chapter_map.json    — per-chapter page ranges + names
      * figure_index.json   — figure index (for figure layers)
      * ignore_ch{N}.json / ignore_fig_ch{N}.json — per-chapter noise (auto)
      * manual_overrides_ch{N}.json        — per-chapter extraction overrides

    Previously these were read inline in several places (registry.py,
    verify_chapter.py, context.py); now they are consolidated here so layers
    never re-read files or receive config field-by-field.
    """

    def __init__(self, extract_dir: str, book_dir: str,
                 extra_ignore: Optional[List[str]] = None):
        self.extract_dir = extract_dir
        self.book_dir = book_dir
        self.book_config_path: Optional[str] = None
        self.book_config_has_ordinal: bool = False
        self.book = self._load_book_config()
        self.chapters = self._load_chapter_map()
        self.figure_index = self._load_figure_index()
        # Optional extra ignore entries supplied via CLI (--ignore / --ignore-figure);
        # merged into every chapter's resolved ignore set.
        self.extra_ignore: Set[str] = set(extra_ignore or [])

    # ---- verify_config.json ----
    def _load_book_config(self) -> BookConfig:
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
        # raw data explicitly declared an ordinal (the old `levels` count counts
        # as an ordinal declaration). `require_complete()` needs these to tell
        # "file present but no ordinal" (hard error) from "file absent"
        # (warning + default) — `BookConfig.from_dict` silently defaults ordinal
        # to 3, so we cannot infer absence from the resolved value alone.
        self.book_config_path = hit_path
        self.book_config_has_ordinal = ('ordinal' in data) or ('levels' in data)
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
        if self.book_config_path is None:
            if allow_absent:
                warnings.warn(
                    "[CONFIG] 未找到 verify_config.json，沿用默认 ordinal=3（向后兼容）。"
                    "新流程要求在源语言全部初稿完成后，用 verify/make_config.py 生成 "
                    "<book>/_extract/verify_config.json（至少含 ordinal）。",
                    stacklevel=2,
                )
                return
            raise ConfigError(
                "[CONFIG] 未找到 verify_config.json，且 allow_absent=False。"
                "请先创建 <book>/_extract/verify_config.json（至少含 ordinal）。"
            )

        # --- ordinal present & legal (1..7) ---
        # `from_dict` clamps an illegal ordinal to 3, so the `has_ordinal` flag is
        # the reliable "was it declared" signal; the ORDINAL_CODES check is a
        # defensive backstop for any future path that bypasses clamping.
        if not self.book_config_has_ordinal:
            raise ConfigError(
                f"[CONFIG] {self.book_config_path} 未声明 ordinal"
                f"（应在 1..7）。请显式填写，例如 {{\"ordinal\": 3}}。"
            )
        if cfg.ordinal not in ORDINAL_CODES:
            raise ConfigError(
                f"[CONFIG] {self.book_config_path} 未声明合法 ordinal"
                f"（应在 1..7）。请显式填写，例如 {{\"ordinal\": 3}}。"
            )

        # --- section_types / section_depths (only when explicitly given) ---
        if cfg.section_types or cfg.section_depths:
            if len(cfg.section_types) != len(cfg.section_depths):
                raise ConfigError(
                    f"[CONFIG] {self.book_config_path} section_types 与 section_depths "
                    f"长度不等（{len(cfg.section_types)} vs {len(cfg.section_depths)}）。"
                )
            if any(d < 1 for d in cfg.section_depths):
                raise ConfigError(
                    f"[CONFIG] {self.book_config_path} section_depths 含非法分量（<1）。"
                )
            for code in cfg.section_types:
                if code not in SECTION_ROLE_CODES:
                    raise ConfigError(
                        f"[CONFIG] {self.book_config_path} section_types 含非法角色码 "
                        f"{code}（应在 {SECTION_ROLE_CODES}）。"
                    )
            if cfg.section_depths[0] != 1:
                raise ConfigError(
                    f"[CONFIG] {self.book_config_path} section_depths[0] 必须为 1"
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
