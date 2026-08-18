"""lib/figure_io.py — shared reader for ``figure_index.json``.

Consumed by both the figure-assignment package (write-source/figures) and the
verify figure layer (E, unified figure completeness + validity) (write-source step 3 / derive-translate). Both callers only ever test truthiness or
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


# Mirrors config/verify_config/verify_config.py::ORDINAL_DEPTH so figure_io
# stays import-clean (no config-module import). A figure group's `type`
# encodes its numbering depth (= number of numeric components = the former
# `figure.components`).  🔴 `components` IS `depth`.
ORDINAL_DEPTH = {1: 1, 2: 2, 3: 3, 4: 2, 5: 3, 6: 2, 8: 3, 9: 3}

# Figure-label keywords that identify a figure group inside `ordinal`.  CJK 图
# is matched separately (it carries no ASCII letters).
_FIG_KW = ("fig", "figure")


def _is_fig_kw(name):
    """True iff `name` is a figure-label keyword (Fig / Figure / 图)."""
    s = str(name)
    if "图" in s:
        return True
    return re.sub(r"[^a-z]", "", s.lower()) in _FIG_KW


def _figure_group(data):
    """Return the `ordinal` group whose `name` contains a figure-label keyword,
    or None.  Figures are NO LONGER a separate `figure` config block — they live
    in `ordinal` like any other counter, and their `type` (-> ORDINAL_DEPTH)
    carries the component count (= `depth` = former `figure.components`)."""
    for g in data.get("ordinal", []):
        if any(_is_fig_kw(nm) for nm in g.get("name", [])):
            return g
    return None


def load_fig_labels(out_dir):
    """Return the book's figure-label prefixes (list of keywords).

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
                fg = _figure_group(data)
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


def load_fig_components(out_dir):
    """Return the figure-number COMPONENT COUNT for this book:

      1 = global integer sequence   (e.g. Kreyszig "Fig. 1", "Fig. 23", … up to ~270)
      2 = chapter.figure            (e.g. "Fig. 3.1", "图 3.1")   ← DEFAULT / historical
      3 = chapter.section.figure    (e.g. "Fig. 3.1.2", "图 3.1.2")

    🔴 DERIVED from the `ordinal` figure group's `type` (-> ORDINAL_DEPTH):
    `components` IS the ordinal `depth`, NOT a separate `figure.components` key.
    Falls back to the legacy `figure.components` block (transitional) and then
    to the historical default 2, so no existing book regresses.  A book whose
    figures are numbered by a single global integer (Kreyszig) declares its
    figure group with `type: 1` (depth 1); without it "Fig. 23" would be
    mis-read as a non-label and left unnamed.
    """
    candidates = [os.path.join(out_dir, "verify_config.json"),
                  os.path.join(os.path.dirname(os.path.abspath(out_dir)), "verify_config.json")]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                fg = _figure_group(data)
                if fg is not None:
                    t = fg.get("type")
                    if isinstance(t, int) and t in ORDINAL_DEPTH:
                        return ORDINAL_DEPTH[t]
                # transitional: legacy block
                fig = data.get("figure")
                if isinstance(fig, dict) and isinstance(fig.get("components"), int):
                    return max(1, min(3, fig["components"]))
            except Exception:
                pass
    return 2


def build_fig_label_re(labels, components=2):
    r"""Compiled regex that finds a figure caption label (图 X.X / Figure X.X / …)
    in text and captures its sequential number (group 1). Driven by BOOK-SPECIFIC
    `labels` AND `components`, so each book's OWN figure numbering is honored.
    Returns a never-matching regex when `labels` is empty (explicit no-figure-labels
    marker).

    `components` controls how many number segments a label may have:
      1 -> ``([0-9]+)``                       (global integer, e.g. "Fig. 23")
      2 -> ``([0-9]+(?:\.|-)[0-9]+){1,2}``    (chapter.figure / chapter.section.figure)
      3 -> ``([0-9]+(?:\.|-)[0-9]+){2,3}``    (chapter.section.figure, stricter)
    """
    if not labels:
        return _NEVER_RE
    components = max(1, min(3, int(components)))
    if components == 1:
        num = r"([0-9]+)"
    elif components == 2:
        num = r"([0-9]+(?:(?:\.|-)[0-9]+){1,2})"
    else:  # 3
        num = r"([0-9]+(?:(?:\.|-)[0-9]+){2,3})"
    return re.compile(rf"(?:{fig_label_alt(labels)})\s*{num}", re.IGNORECASE)


def load_fig_label_re(out_dir):
    """One-call convenience: compiled figure-label regex honoring BOTH the book's
    `labels` and `components`. Prefer this over ``build_fig_label_re(load_fig_labels(...))``
    so the component count is never forgotten at a call site."""
    return build_fig_label_re(load_fig_labels(out_dir), load_fig_components(out_dir))


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
