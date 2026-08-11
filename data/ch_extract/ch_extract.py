#!/usr/bin/env python3
"""ch_extract.py — boundary adapter for ``ch<N>_extract.json`` (per-chapter extract).

This skill *produces and consumes* ``ch<N>_extract.json`` but does **not** own
a fixed schema: the file is the serialised per-chapter extraction result and its
exact fields vary per ``extract_items_*`` variant (K&T, hom, gm, vakil, ...).
The construction logic lives in the extract pipeline (``flows/extract/...``,
per user convention) — this module is only a thin anti-corruption layer that
centralises load/dump and exposes the two universal keys (``sections`` /
``statements``).  Unknown fields pass through in ``.data``.

Design rule: every read/write of ``ch<N>_extract.json`` in ``flows/`` and
``verify/`` must go through this adapter — no bare ``json.load`` / ``json.dump``.
"""
import json
from typing import Any, Dict, List


class ChExtract:
    """Boundary adapter wrapping one ``ch<N>_extract.json`` extract result."""

    def __init__(self, data: Dict[str, Any]):
        # Raw extract result. Schema varies per extract_items_* variant; keep
        # it intact.
        self.data: Dict[str, Any] = data

    # ---- construction / (de)serialisation ----
    @classmethod
    def from_extract(cls, data: Dict[str, Any]) -> "ChExtract":
        return cls(data)

    @classmethod
    def load(cls, path: str) -> "ChExtract":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def dump(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=1)

    # ---- the two universal keys every variant shares ----
    @property
    def sections(self) -> List[Any]:
        return self.data.get("sections", [])

    @property
    def statements(self) -> List[Any]:
        return self.data.get("statements", [])
