#!/usr/bin/env python3
"""figure_detect.py — boundary adapter for ``figure_detect.json`` (MFD output).

This skill *consumes* ``figure_detect.json`` but does **not** own its schema:
the file is produced by an external figure-detection model (MFD /
PDF-Extract-Kit) and is the stage-1 detection record.  This module is a thin
anti-corruption layer at the ingestion boundary — it does NOT model the
detector's fields, it only centralises load/dump and exposes the records the
pipeline reads.  The top-level JSON is a **list**; unknown entries pass through.

Design rule: every read/write of ``figure_detect.json`` in ``flows/`` and
``verify/`` must go through this adapter — no bare ``json.load`` / ``json.dump``.
"""
import json
from typing import Any, Iterator, List


class FigureDetect:
    """Boundary adapter wrapping a ``figure_detect.json`` detection list."""

    def __init__(self, data: List[dict]):
        # Raw detector output (a list of detection entries). Pass-through.
        self.data: List[dict] = data if isinstance(data, list) else []

    # ---- construction / (de)serialisation ----
    @classmethod
    def from_engine_output(cls, data: List[dict]) -> "FigureDetect":
        return cls(data)

    @classmethod
    def load(cls, path: str) -> "FigureDetect":
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
