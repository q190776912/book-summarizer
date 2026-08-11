#!/usr/bin/env python3
"""figure_noise.py — boundary adapter for ``fig_noise.json`` (noise records).

This skill *consumes* ``fig_noise.json`` but does **not** own its schema: the
file is produced by an external figure-detection / noise-judgement tool (or
referenced by the verify stage via ``--ignore-figure fig_noise.json``) and is a
diagnostic aid only.  This module is a thin anti-corruption layer at the
ingestion boundary — it does NOT model the tool's fields, it only centralises
load/dump and exposes the records.  The top-level JSON is a **list**; unknown
entries pass through.

Design rule: every read/write of ``fig_noise.json`` in ``flows/`` and ``verify/``
must go through this adapter — no bare ``json.load`` / ``json.dump``.
"""
import json
from typing import Any, Iterator, List


class FigureNoise:
    """Boundary adapter wrapping a ``fig_noise.json`` noise-record list."""

    def __init__(self, data: List[dict]):
        # Raw noise-judgement output (a list of records). Pass-through.
        self.data: List[dict] = data if isinstance(data, list) else []

    # ---- construction / (de)serialisation ----
    @classmethod
    def from_engine_output(cls, data: List[dict]) -> "FigureNoise":
        return cls(data)

    @classmethod
    def load(cls, path: str) -> "FigureNoise":
        with open(path, encoding="utf-8") as f:
            return cls(json.load(f))

    def dump(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)

    # ---- the fields the pipeline actually reads ----
    @property
    def records(self) -> List[dict]:
        return self.data

    def iter_records(self) -> Iterator[dict]:
        for r in self.data:
            yield r
