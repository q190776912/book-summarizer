"""book-summarizer shared path bootstrap.

After the big refactor, the code packages (``extract``, ``figure``, ``format``,
``pipeline``, ``formula``, ``verify``, ``mm_repair``) no longer live directly
under the skill root.  Flow-stage packages live under ``flows/<stage>/script/<pkg>/`` (each stage's scripts are grouped in a ``<pkg>`` subpackage under its ``script/`` directory),
and the shared ``verify`` engine is a proper package at the skill root level
(``verify/``, parallel to ``flows/``), with each validation layer as a
``verify/<semantic_name>/`` subpackage.

Each intermediate-product JSON lives in its **own directory** under ``data/<json_name>/``
(for example ``data/chapter_map/``, ``data/figure_index/``),
each containing a ``<json_name>.md`` (the spec) and ``<json_name>.py`` (the model class,
a subclass of the shared base ``data/lib/json_data.py``).  Each config JSON lives in
its **own directory** under ``config/<json_name>/`` (for example
``config/verify_config/``, ``config/ignore_chN/``), each containing a specific-named
``<json_name>.md`` doc and its model / instantiation script.  To keep
``import chapter_map`` / ``import figure_index`` /
``import json_data`` / ``import verify_config`` / ``import manage_ignore`` / ...
working no matter which script is the entry point, this module adds the skill root,
the ``lib`` package, **every** ``flows/*/script`` directory, and the ``verify``
package (with its per-layer ``<semantic_name>/`` subpackages),
and **every direct child directory of ``data/``** and ``config/``** (so each
``data/<json_name>/`` and ``config/<json_name>/`` package is importable) to
``sys.path``.

Call :func:`setup` once (every entry script does it via the bootstrap snippet at
the top of the file; it is idempotent and cheap).
"""
import os
import sys
from pathlib import Path

_ROOT = None


def root():
    """Return the skill root (the directory containing ``SKILL.md``)."""
    global _ROOT
    if _ROOT is not None:
        return _ROOT
    here = Path(__file__).resolve()
    for cand in (here, *here.parents):
        if (cand / "SKILL.md").exists():
            _ROOT = str(cand)
            return _ROOT
    # Fallback: lib/ lives directly under the skill root.
    _ROOT = str(here.parents[1])
    return _ROOT


def _register_verify_package(r):
    """Expose the verify engine (now a proper package at ``<root>/verify/``) under
    the canonical name ``verify``.

    After the semantic-layout refactor the verify engine is a real package at
    the skill root (``verify/`` containing ``verify_chapter.py``,
    ``register_all.py``, ``report.py`` and the per-layer ``<semantic_name>/``
    subpackages), so ``import verify`` resolves through normal package machinery
    and each validation-layer module is importable by its bare ``<snake>`` name
    (boot injects ``verify/**/script`` into ``sys.path``).  We still register it
    explicitly (guarded by the ``"verify" not in sys.modules`` check) so the
    historical import surface works regardless of which entry script bootstrapped
    first.
    """
    import importlib.util
    pkg_dir = os.path.join(r, "verify")
    init_py = os.path.join(pkg_dir, "__init__.py")
    if os.path.isfile(init_py) and "verify" not in sys.modules:
        spec = importlib.util.spec_from_file_location("verify", init_py)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["verify"] = mod
        spec.loader.exec_module(mod)


def setup():
    """Ensure the skill root, ``lib``, all ``flows/*/script``, ``verify/**/script``,
    ``config/**/script`` dirs, and every direct child of ``data/`` (each
    ``data/<json_name>/`` package + ``data/lib``) and ``config/`` (each
    ``config/<json_name>/`` package) are importable."""
    r = root()
    dirs = [r, os.path.join(r, "lib")]
    for base in ("flows", "verify", "config", "data"):
        top = Path(r) / base
        if top.exists():
            for sd in top.glob("**/script"):
                dirs.append(str(sd))
    # data/: each intermediate-product JSON lives in its own top-level dir
    # (no 'script' subdir) — make every data/<json_name>/ package importable.
    data_top = Path(r) / "data"
    if data_top.exists():
        for sd in sorted(data_top.iterdir()):
            if sd.is_dir():
                dirs.append(str(sd))
    # config/: each config JSON lives in its own top-level dir (e.g.
    # config/verify_config/, config/ignore_chN/) — make every config/<name>/
    # package importable so `import verify_config` / `import manage_ignore` /
    # `import apply_manual_figures` resolve regardless of entry point.
    config_top = Path(r) / "config"
    if config_top.exists():
        for sd in sorted(config_top.iterdir()):
            if sd.is_dir():
                dirs.append(str(sd))
    for d in dirs:
        if d not in sys.path:
            sys.path.insert(0, d)
    _register_verify_package(r)
