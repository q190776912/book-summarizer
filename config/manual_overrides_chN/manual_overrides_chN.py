#!/usr/bin/env python3
"""manual_overrides_chN.py — boundary adapter for ``manual_overrides_chN.json``.

Per-chapter extraction overrides (hand fixes for item detection). The skill
produces and consumes it; the loader centralises the read so flow scripts never
do a bare ``json.load``. The parsed JSON (usually a list) is returned as-is so
downstream ``extract_items_*`` behaviour is identical to the old inline read.

Design rule: every read of ``manual_overrides_chN.json`` (or the book-level
``manual`` path from verify_config) in ``flows/`` and ``verify/`` must go through
this loader — no bare ``json.load``.
"""
import json
import os
from typing import Any, Optional


def load_manual_overrides(path: Optional[str]) -> Any:
    """Load a manual-override JSON (per-chapter or book-level) and return it
    as-is. Missing / empty path -> None, matching the old inline ``json.load``
    guard in the extract scripts."""
    if not path or not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
