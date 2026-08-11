#!/usr/bin/env python3
"""kreyszig_map.py — boundary adapter for Kreyszig renumber / reconcile maps.

Kreyszig-specific formula renumber / reconcile outputs (``renumber_map.json``,
``recon_chN.json``, ``recon_all.json``). Book-specific, not a modelled product,
so this is a thin anti-corruption layer: load / dump / accessors only; the raw
dict passes through in ``.data``.

Design rule: every read/write of these maps in ``flows/`` and ``verify/`` must
go through this adapter — no bare ``json.load`` / ``json.dump``.
"""
import json
from typing import Any, Dict


class KreyszigMap:
    """Boundary adapter wrapping a Kreyszig renumber / reconcile map."""

    def __init__(self, data: Dict[str, Any]):
        self.data: Dict[str, Any] = data

    @classmethod
    def load(cls, path: str) -> "KreyszigMap":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def dump(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
