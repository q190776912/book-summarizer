"""
ignore_files.py — load --ignore / --ignore-figure files (per-book config).

Relocated verbatim from verify_chapter.py (load_ignore / load_ignore_fig) so
the deleted fig_layers.py (which used to own `normfig`) is no longer imported
by the CLI. `normfig` lives in verify.script.fig_common.
"""
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

import json
import os

from verify.script.key_parse import normkey
from verify.script.fig_common import normfig


def load_ignore(ignore_path):
    """Load a --ignore file. Accepts a JSON list ["1.1-1", ...] or a dict
    {"1.1-1": "reason", ...}. Returns a set of canonical (dash-form) keys."""
    if not ignore_path or not os.path.exists(ignore_path):
        return set()
    with open(ignore_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict):
        raw = data.keys()
    elif isinstance(data, list):
        raw = data
    else:
        return set()
    return {normkey(str(k)) for k in raw}


def load_ignore_fig(ignore_path):
    """Load --ignore-figure file: JSON list ['6.3.1', ...] or dict. Returns set."""
    if not ignore_path or not os.path.exists(ignore_path):
        return set()
    with open(ignore_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if isinstance(data, dict):
        raw = data.keys()
    elif isinstance(data, list):
        raw = data
    else:
        return set()
    return {normfig(k) for k in raw}
