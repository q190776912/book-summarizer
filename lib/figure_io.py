"""lib/figure_io.py — shared reader for ``figure_index.json``.

Consumed by both the figure-assignment package (write-source/figures) and the
verify figure layer (E, unified figure completeness + validity) (write-source step 2). Both callers only ever test truthiness or
iterate the result, so a uniform empty-list return on missing/corrupt file is
safe for all of them.
"""
import json
import os
import re


# Default figure-label prefixes (used ONLY when verify_config.json has no
# `figure` block or no `labels` key at all). Each book declares its OWN
# figure-number prefix in verify_config.json `figure.labels`; an EXPLICIT empty
# array `{"labels": []}` is the "no figure ordinal label" marker and yields a
# zero-match set (NOT the default) — see `load_fig_labels`.
FIGURE_LABELS_DEFAULT = ["图", "Figure", "Fig"]

# A regex that can never match. Used when a book explicitly declares NO figure
# labels (empty `figure.labels` array — the "no ordinal label" marker), so
# callers never strip/match anything (returning the default here would wrongly
# match stray `Figure`/`图` words in a label-less book).
_NEVER_RE = re.compile(r"[^\s\S]")

# `ordinal` Figure 组的 `type` 中，首分量为**字母章位**的两个码（附录 `Figure B.1`
# = 14 两段 / `Figure C.2.3` = 13 三段）。见 lib.numbering.ORDINAL_DEPTH。
LETTER_CH_FIG_TYPES = frozenset({13, 14})


# A figure group's `type` encodes its numbering depth (= number of numeric
# components = the former `figure.components`).  🔴 `components` IS `depth`.
# 🔴 唯一真源在 `lib.numbering`（勿在本处复制镜像副本）：
# 副本会与 config 侧漂移，缺条目会让 CN-三段标 figure group 静默回落默认值。
from lib.numbering import ordinal_depth, OrdinalDepthError
# `ConfigError` 来自 verify_config —— lib -> config 的反向导入是既有安全模式
# （见 lib/key_parse.py:43），boot 阶段已将 verify_config 注册为顶层可导入名。
from verify_config import ConfigError

# Figure-label keywords that identify a figure group inside `ordinal`.  CJK 图
# is matched separately (it carries no ASCII letters).  🔴 SSOT 在
# lib/numbering.is_fig_label_name（primary_group 判据同源），此处仅别名。
from lib.numbering import _FIG_LABEL_KW as _FIG_KW, is_fig_label_name as _is_fig_kw


def _segment_keys_for_ch(ch):
    """Config-segment keys to try for chapter `ch`, most specific first.

    A book may declare DIFFERENT figure families per segment: the body numbers
    figures `Figure N.M` (two numeric components) while an appendix numbers them
    `Figure B.1` (letter chapter slot).  Callers that know the chapter must ask
    for THAT segment's figure group first — otherwise a letter-chapter appendix
    is matched with the body's digit-only shape and every appendix figure stays
    UNNAMED (Modern Robotics measured: appendixB 4/0 named, appendixC 5/0).

    Returns ``()`` for ``ch is None`` so the historic global scan is used
    verbatim (zero regression for every existing caller).
    """
    if ch is None:
        return ()
    s = str(ch)
    if s.isdigit():
        return ("ch",)
    # 非数字章键 = 附录/补篇（与 ConfigLoader._resolve_kind 同判据）
    return ("appendix", "supplement", "ch")


def _figure_group(data, ch=None):
    """Return the `ordinal` group whose `name` contains a figure-label keyword,
    or None.  Figures are NO LONGER a separate `figure` config block — they live
    in `ordinal` like any other counter, and their `type` (-> ORDINAL_DEPTH)
    carries the component count (= `depth` = former `figure.components`).

    Handles BOTH config shapes produced by make_config:
      * legacy FLAT  : top-level ``{"ordinal": [...]}``
      * current NESTED: ``{"ch": {"ordinal":[...]}, "appendix": {"ordinal":[...]},
        "supplement": {"ordinal":[...]}}`` — the figure group declared inside a
        chapter/appendix segment must still be found (otherwise the figure gate
        aborts all verification with "缺少 figure 配置").

    🔴 按章路由（`ch`，2026-10-19）：`ch` 非 None 时**先**只看该章所属段
    （`:func:_segment_keys_for_ch`），取不到才回退全局扫描。这样段间体例不同的书
    各段各用自己的图号形态；`ch is None` 的调用方行为与改造前**逐字节等价**。
    """
    # 0) chapter-scoped lookup FIRST (per-segment figure families)
    for seg_key in _segment_keys_for_ch(ch):
        seg = data.get(seg_key)
        if isinstance(seg, dict):
            for g in seg.get("ordinal", []):
                if any(_is_fig_kw(nm) for nm in g.get("name", [])):
                    return g
    # 1) legacy flat shape: top-level `ordinal`
    for g in data.get("ordinal", []):
        if any(_is_fig_kw(nm) for nm in g.get("name", [])):
            return g
    # 2) current nested segment shape (make_config: ch / appendix / supplement)
    for seg_key in ("ch", "appendix", "supplement"):
        seg = data.get(seg_key)
        if isinstance(seg, dict):
            for g in seg.get("ordinal", []):
                if any(_is_fig_kw(nm) for nm in g.get("name", [])):
                    return g
    # 3) generic fallback: any dict value carrying its own `ordinal`
    for seg in data.values():
        if isinstance(seg, dict) and "ordinal" in seg:
            for g in seg.get("ordinal", []):
                if any(_is_fig_kw(nm) for nm in g.get("name", [])):
                    return g
    return None


def load_fig_labels(out_dir, ch=None):
    """Return the book's figure-label prefixes (list of keywords).

    `ch` (optional) selects the config SEGMENT to read first — see
    :func:`_segment_keys_for_ch`; omit it for the historic book-wide answer.

    🔴 Figure labels/depth now live in `ordinal`, NOT a separate `figure` block.
    Derivation order:
      1. The `ordinal` group whose `name` contains a figure keyword
         (Fig / Figure / 图) — only its figure-keyword names are returned, so a
         merged text+figure group (e.g. Fraleigh's) is filtered and the text
         labels are NOT mistaken for figure prefixes.
      2. Legacy `figure.labels` block (transitional; the explicit empty-array
         `[]` "no figure ordinal label" MARKER is honored -> []).
      3. `FIGURE_LABELS_DEFAULT`.
    """
    candidates = [os.path.join(out_dir, "verify_config.json"),
                  os.path.join(os.path.dirname(os.path.abspath(out_dir)), "verify_config.json")]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                fg = _figure_group(data, ch)
                if fg is not None:
                    fig_only = [str(nm) for nm in fg.get("name", []) if _is_fig_kw(nm)]
                    if fig_only:
                        return fig_only
                # transitional: explicit legacy block (may be the [] marker)
                fig = data.get("figure")
                if isinstance(fig, dict) and "labels" in fig and isinstance(fig["labels"], list):
                    return [str(x) for x in fig["labels"]]  # explicit, may be []
            except Exception:
                pass
    return list(FIGURE_LABELS_DEFAULT)


def fig_label_alt(labels):
    """Alternation of the given label prefixes, each allowing an optional
    trailing '.' (so 'Fig.'/'Figure.' with period and '图' without all match).
    Returns a never-matching token when `labels` is empty (explicit no-label
    marker), so callers that build `^(?:{alt})...` never strip/match anything.

    OCR robustness: the lowercase 'i' in a prefix is a very common misread as
    'l' (e.g. "Fig." -> "Flg." in Kreyszig's scan), which would otherwise leave
    those captions unnamed. For any label containing 'i'/'I' we also emit the
    same prefix with 'i' -> '[il]', so "Flg." matches the "Fig" prefix. Scoped
    to labels that actually contain 'i', so 图-only books are unaffected."""
    if not labels:
        return r"[^\s\S]"
    alts = []
    for lbl in labels:
        esc = re.escape(lbl)
        alts.append(esc + r"\.?")            # exact prefix, optional trailing .
        if "i" in lbl.lower():               # tolerate Fig -> Flg (i read as l)
            conf = re.escape(lbl).replace("i", "[il]").replace("I", "[il]")
            alts.append(conf + r"\.?")
    return "|".join(alts)


def load_fig_components(out_dir, ch=None):
    """Return the figure-number COMPONENT COUNT (== ordinal `depth`) for this book,
    or raise `ConfigError` if figure numbering is not explicitly declared.

    `ch` (optional) selects the config SEGMENT to read first — see
    :func:`_segment_keys_for_ch`; omit it for the historic book-wide answer.

      1 = global integer sequence   (e.g. Kreyszig "Fig. 1", "Fig. 23", …)
      2 = chapter.figure            (e.g. "Fig. 3.1", "图 3.1")
      3 = chapter.section.figure    (e.g. "Fig. 3.1.2", "图 3.1.2")
      0 = UNNUMBERED / 无图编号      (figure group 显式 `type: 0`) -> 不匹配任何图题

    🔴 DERIVED from the `ordinal` figure group's `type` (-> ORDINAL_DEPTH):
    `components` IS the ordinal `depth`, NOT a separate `figure.components` key.
    声明的 `type` 必须是已登记码（ordinal_depth 守卫）；未登记即抛
    `OrdinalDepthError`。🔴 本书**必须显式声明** figure 配置——无图声明 `type: 0`，
    有图声明 `type: 1/2/3` 等；**禁止任何静默默认**（旧 `return 2` 已移除）。
    遗留 `figure.components` 块仍作过渡兼容。
    """
    candidates = [os.path.join(out_dir, "verify_config.json"),
                  os.path.join(os.path.dirname(os.path.abspath(out_dir)), "verify_config.json")]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                fg = _figure_group(data, ch)
                if fg is not None:
                    t = fg.get("type")
                    if isinstance(t, int):
                        # 🔴 声明 figure group `type` 必须登记 depth；未登记即
                        # 注册/配置 bug（ordinal_depth 抛 OrdinalDepthError），
                        # type:0 (UNNUMBERED) = 显式「无图编号」-> depth 0。
                        # 🔴 本函数直读 raw JSON：配置里的 type 必须是规范码（弃用
                        # 码 4/9/10/11 已彻底退役，存量 config 已全部改写为规范码），
                        # 否则 ordinal_depth 直接抛 OrdinalDepthError，不做静默兜底。
                        return ordinal_depth(t)
                    # figure group 存在但缺 `type`：缺失即报错，不得默认。
                    raise ConfigError(
                        "figure group 已声明但缺 `type`：无图请显式声明 `type: 0`，"
                        "有图声明 `type: 1/2/3` 等已登记体例")
                # transitional: legacy block（旧 `figure.components`）
                fig = data.get("figure")
                if isinstance(fig, dict) and isinstance(fig.get("components"), int):
                    return max(1, min(3, fig["components"]))
            except (ConfigError, OrdinalDepthError):
                raise
            except Exception:
                pass
    # 🔴 无任何 figure 配置（无 figure group、无 legacy block）-> 缺失即报错，
    # 禁止静默默认 2。请显式声明 ordinal 中的 figure group：无图 `type: 0` /
    # 有图 `type: 1/2/3` 等已登记体例。
    raise ConfigError(
        "缺少 figure 配置：请显式声明 ordinal 中的 figure group"
        "（无图 `type: 0` / 有图 `type: 1/2/3` 等已登记体例），"
        "禁止依赖无配置的 2-分量默认。重跑 `make_config.py --force`"
        "（现自动探测图题并显式补组）或按 verify_config.md 手工补声明。")


def build_fig_label_re(labels, components=2, letter_ch=False):
    r"""Compiled regex that finds a figure caption label (图 X.X / Figure X.X / …)
    in text and captures its sequential number. Driven by BOOK-SPECIFIC
    `labels` AND `components`, so each book's OWN figure numbering is honored.
    Returns a never-matching regex when `labels` is empty (explicit no-figure-labels
    marker).

    Supports both prefix-style captions ("Figure 12.15") and suffix-style
    captions ("12.15 Figure") — the latter is used by Fraleigh's *A First
    Course in Abstract Algebra*.  The number is in group 1 for prefix matches
    and group 2 for suffix matches; use ``fig_label_from_match`` to retrieve it.

    `components` controls how many number segments a label may have:
      1 -> ``([0-9]+)``                       (global integer, e.g. "Fig. 23")
      2 -> ``([0-9]+(?:\.|-)[0-9]+){1,2}``    (chapter.figure / chapter.section.figure)
      3 -> ``([0-9]+(?:\.|-)[0-9]+){2,3}``    (chapter.section.figure, stricter)
      None / 0 -> ``_NEVER_RE``               (无图编号：type:0 或显式 None，不匹配任何图题)

    🔴 `letter_ch`（2026-10-19）：True 时**首分量是字母**（附录字母章位体例
    `Figure B.1` / `Figure C.2.3`），数字核改为 ``[A-Za-z]`` 打头、后接
    ``components-1`` 个数字段。默认 False ⇒ 与改造前逐字节等价。
    """
    if not labels:
        return _NEVER_RE
    if components is None or components == 0:
        # type:0 (UNNUMBERED) 或显式 None = 无图编号分量 -> 不匹配任何图题
        # （与 `{"labels": []}` 的「无图标签」标记一致，返回 _NEVER_RE）。
        return _NEVER_RE
    components = max(1, min(3, int(components)))
    if letter_ch and components >= 2:
        # 字母章位：首分量单字母，其余 components-1 段为数字。
        num = r"([A-Za-z](?:(?:\.|-)[0-9]+){%d,%d})" % (components - 1, components)
        alt = fig_label_alt(labels)
        return re.compile(rf"(?:{alt})\s*{num}|{num}\s*(?:{alt})", re.IGNORECASE)
    if components == 1:
        num = r"([0-9]+)"
    elif components == 2:
        num = r"([0-9]+(?:(?:\.|-)[0-9]+){1,2})"
    else:  # 3
        num = r"([0-9]+(?:(?:\.|-)[0-9]+){2,3})"
    alt = fig_label_alt(labels)
    # prefix: "Figure 12.15"; suffix: "12.15 Figure"
    return re.compile(rf"(?:{alt})\s*{num}|{num}\s*(?:{alt})", re.IGNORECASE)


def fig_label_from_match(m):
    """Return the captured figure-number string from a match produced by
    ``build_fig_label_re``.  The regex has two capture groups (prefix and
    suffix styles), only one of which participates in a given match."""
    if not m:
        return None
    if m.group(1) is not None:
        return m.group(1)
    return m.group(2)


def load_fig_letter_ch(out_dir, ch=None):
    """True iff this book's (`ch`'s) figure numbers use a LETTER chapter slot.

    Derived from the `ordinal` Figure group's `type`: 13 (letter + 2 numeric)
    / 14 (letter + 1 numeric) are the appendix letter-slot families, e.g.
    ``Figure B.1``.  Every other family is digit-led and yields False — which
    is also the answer for books with no figure group at all (their `type`
    cannot be 13/14), so this never raises and needs no silent default.

    `ch` (optional) selects the config SEGMENT to read first — see
    :func:`_segment_keys_for_ch`.
    """
    candidates = [os.path.join(out_dir, "verify_config.json"),
                  os.path.join(os.path.dirname(os.path.abspath(out_dir)),
                               "verify_config.json")]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                fg = _figure_group(data, ch)
                if fg is not None:
                    return fg.get("type") in LETTER_CH_FIG_TYPES
            except Exception:
                pass
    return False


def load_fig_label_re(out_dir, ch=None):
    """One-call convenience: compiled figure-label regex honoring BOTH the book's
    `labels` and `components`. Prefer this over ``build_fig_label_re(load_fig_labels(...))``
    so the component count is never forgotten at a call site.

    `ch` (optional) selects the config SEGMENT to read first — see
    :func:`_segment_keys_for_ch`."""
    return build_fig_label_re(load_fig_labels(out_dir, ch),
                              load_fig_components(out_dir, ch),
                              load_fig_letter_ch(out_dir, ch))


def load_figure_index(path):
    """Load ``figure_index.json`` from ``path`` (extract/output dir).

    Returns the parsed list, or ``[]`` if the file is missing or unreadable.
    """
    p = os.path.join(path, "figure_index.json")
    if not os.path.exists(p):
        return []
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


# ---------------------------------------------------------------------------
# figure 目录统一约定（figure 目录与总结文件同级，位于书根）
# ---------------------------------------------------------------------------
def figure_dir(ext):
    """裁剪图所在目录的**书根绝对路径**：``<book_dir>/figure``（与最终 md 同级）。

    🔴 figure 目录 = 书根 ``<book_dir>/figure/``
    （与总结文件同级），最终 md 里 ``<img src="figure/xxx.png">`` 即为书根相对路径，
    直接可渲染。``ext`` 是 ``<book_dir>/_extract``；多册书子目录同理取该书根。
    """
    return os.path.join(os.path.dirname(os.path.abspath(ext.rstrip("/\\"))), "figure")


def figure_abs(ext, rel):
    """把 ``figure_index.json`` 的 ``file``（``figure/xxx.png``）解析为书根下的
    绝对路径 ``<book_dir>/figure/xxx.png``。

    消费方打开裁剪图文件须经本函数（基准目录 = 书根）；裁剪图统一在
    ``<book_dir>/figure/``（与总结 md 同级）。
    """
    base = os.path.basename((rel or "").replace("\\", "/"))
    return os.path.join(figure_dir(ext), base)
