"""lib/figure_io.py — shared reader for ``figure_index.json``.

Consumed by both the figure-assignment package (write-source/figures) and the
verify E/F layers (verify-source). Both callers only ever test truthiness or
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


def load_fig_labels(out_dir):
    """Return the book's figure-label prefixes (list of keywords) from
    <out_dir>/verify_config.json -> figure.labels. Also checks the book root
    (parent dir).

    🔴 Two DISTINCT fallbacks — do NOT conflate:
      * `figure` block / `labels` key **absent**  -> FIGURE_LABELS_DEFAULT
        (backward compatible; the book simply never declared a figure style).
      * `figure.labels` present but **explicitly empty `[]`** -> `[]`
        (the "no figure ordinal label" MARKER: the book genuinely has no
        figure numbers, so return a true zero-match set, NOT the default).
    """
    candidates = [os.path.join(out_dir, "verify_config.json"),
                  os.path.join(os.path.dirname(os.path.abspath(out_dir)), "verify_config.json")]
    for p in candidates:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
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
    marker), so callers that build `^(?:{alt})...` never strip/match anything."""
    if not labels:
        return r"[^\s\S]"
    return "|".join(re.escape(lbl) + r"\.?" for lbl in labels)


def build_fig_label_re(labels):
    """Compiled regex that finds a figure caption label (图 X.X / Figure X.X / …)
    in text and captures its sequential number (group 1). Driven by BOOK-SPECIFIC
    `labels`, so each book's OWN figure numbering is honored. Returns a never-
    matching regex when `labels` is empty (explicit no-figure-labels marker)."""
    if not labels:
        return _NEVER_RE
    return re.compile(rf"(?:{fig_label_alt(labels)})\s*([0-9]+(?:(?:\.|-)[0-9]+){{1,2}})", re.IGNORECASE)


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
