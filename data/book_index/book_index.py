#!/usr/bin/env python3
"""book_index.py — boundary adapter for the make_summary cross-book index (``p1``/``p2``).

``make_summary.py`` keeps a ``{"books": {...}}`` cross-book index that summarises
every finished book. Thin anti-corruption layer: load / dump / accessors only;
the raw dict passes through in ``.data``.

Design rule: every read/write of the book index in ``flows/`` and ``verify/``
must go through this adapter — no bare ``json.load`` / ``json.dump``.
"""
import json
from typing import Any, Dict


class BookIndex:
    """Boundary adapter wrapping the make_summary ``{"books": {...}}`` index."""

    def __init__(self, data: Dict[str, Any]):
        self.data: Dict[str, Any] = data

    @classmethod
    def load(cls, path: str) -> "BookIndex":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def dump(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
