"""
context.py — VerifyContext: the immutable-per-run, dependency-injected carrier
passed to every VerifyLayer.

Design rules (ADR-VERIFY-001 §3.5):
  * No module-level mutable state anywhere in the verify package.
  * Layers read from `ctx` and (for .md checks) re-read the file each call
    via `read_md_lines()` — so a `--fix` mutation followed by a re-check sees
    the freshest bytes (idempotent, matches old behaviour).
  * Derived fields (items / entry_keys / all_keys / ignored_hit /
    extraction_blocking / extraction_warnings / label_warns) are populated by
    the EXTRACT provider + B layer, never by globals.
  * `figure_index` is lazily loaded once (None if absent / broken).
"""
import os
import json

_SENTINEL = object()


def load_figure_index(ext):
    """Return list from figure_index.json, or None if absent/broken.

    Mirrors the helper that used to live in fig_layers.py so the context has no
    import dependency on the relocated legacy module.
    """
    p = os.path.join(ext, 'figure_index.json')
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


class VerifyContext:
    def __init__(self, ch, start, end, md_file, ext_dir, manual_path=None,
                 ignore_keys=None, ignore_fig=None, scheme='three-level', numbering='combined'):
        self.ch = ch
        self.start = start
        self.end = end
        self.md_file = md_file
        self.ext_dir = ext_dir
        self.manual_path = manual_path
        self.ignore_keys = ignore_keys or set()      # canonical dash-form keys
        self.ignore_fig = ignore_fig or set()
        self.scheme = scheme
        self.numbering = numbering                    # 'combined' | 'per-type' (item numbering convention)

        # --- derived (populated by EXTRACT provider + B layer) ---
        self.items = None
        self.entry_keys = None
        self.all_keys = None
        self.extracted = None                        # item keys minus ignore_keys
        self.ignored_hit = None                      # final (stage1 ∪ bkeys)
        self.extraction_blocking = None               # original (pre-suppression)
        self.extraction_warnings = None
        self.label_warns = None

        self._figure_index = _SENTINEL
        self.provided = set()
        self.skipped = set()

    def read_md_lines(self):
        """Read the .md fresh from disk (UTF-8). Called by structural layers."""
        with open(self.md_file, encoding='utf-8') as f:
            return f.read().split('\n')

    @property
    def figure_index(self):
        if self._figure_index is _SENTINEL:
            self._figure_index = load_figure_index(self.ext_dir)
        return self._figure_index
