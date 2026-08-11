#!/usr/bin/env python3
"""mm_repair_manifest.py — boundary adapter for ``manifest.json`` (mm_repair run-state).

Produced and consumed by the mm_repair pipeline (apply / text_compare / audit).
It is run-state, not a modelled product, so this is a thin anti-corruption layer:
load / dump / accessors only; the raw dict passes through in ``.data``.

Design rule: every read/write of ``manifest.json`` in ``flows/`` and ``verify/``
must go through this adapter — no bare ``json.load`` / ``json.dump``.
"""
import json
from typing import Any, Dict


class MmRepairManifest:
    """Boundary adapter wrapping one ``manifest.json`` mm-repair run-state file."""

    def __init__(self, data: Dict[str, Any]):
        self.data: Dict[str, Any] = data

    @classmethod
    def load(cls, path: str) -> "MmRepairManifest":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def dump(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
