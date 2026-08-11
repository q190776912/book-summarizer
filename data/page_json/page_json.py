#!/usr/bin/env python3
"""page_json.py — boundary adapter for ``page_*.json`` (OCR engine output).

This skill *consumes* ``page_*.json`` but does **not** own its schema: the file
is produced by an external OCR engine (PDF-Extract-Kit / UniMERNet / PaddleOCR)
and is the data source for the whole pipeline.  This module is a thin
anti-corruption layer at the ingestion boundary — it does NOT model the
engine's fields, it only centralises load/dump and exposes the few fields the
pipeline actually reads.  Unknown fields pass through untouched in ``.data``.

Design rule: every read/write of ``page_*.json`` in ``flows/`` and ``verify/``
must go through this adapter — no bare ``json.load`` / ``json.dump``.
"""
import json
from typing import Any, Dict, Iterator, List, Optional


class PageJson:
    """Boundary adapter wrapping one ``page_NNN.json`` OCR file."""

    def __init__(self, data: Dict[str, Any]):
        # Raw engine output. We do not own this schema; keep it intact.
        self.data: Dict[str, Any] = data

    # ---- construction / (de)serialisation ----
    @classmethod
    def from_engine_output(cls, data: Dict[str, Any]) -> "PageJson":
        """Wrap an already-parsed OCR engine dict (the producer side)."""
        return cls(data)

    @classmethod
    def load(cls, path: str) -> "PageJson":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def dump(self, path: str) -> None:
        # Compact: page_*.json is large OCR output; no indent keeps it small,
        # matching the engine producer's format.
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False)

    # ---- the fields the pipeline actually reads ----
    @property
    def text_blocks(self) -> List[Dict[str, Any]]:
        return self.data.get("text", [])

    @property
    def formulas(self) -> List[Dict[str, Any]]:
        return self.data.get("formulas", [])

    def page_text(self) -> str:
        return "\n".join(t.get("text", "") for t in self.text_blocks)

    def iter_text_blocks(self) -> Iterator[Dict[str, Any]]:
        for t in self.text_blocks:
            yield t
