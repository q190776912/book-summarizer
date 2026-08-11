#!/usr/bin/env python3
"""figure_embed_overrides.py — model + constructor for ``figure_embed_overrides.json``.

Historically emitted by ``build_figure_index.py``; per the one-JSON-one-directory
rule it now lives in its own directory.  The generator in ``figure_index/``
imports :class:`FigureEmbedOverrides` to produce this file.

Usage (indirect): the figure_index generator calls
``FigureEmbedOverrides.from_figures(figures)`` then ``.dump(path)``.
"""
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

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
from json_data import JsonData


@dataclass
class FigureEmbedOverrides(JsonData):
    """The ``figure_embed_overrides.json`` document (manual embed anchors)."""
    overrides: Dict[str, dict] = field(default_factory=dict)

    @classmethod
    def from_figures(cls, figures: List) -> "FigureEmbedOverrides":
        ov = {fig.file.split("/")[-1]: {"anchors": [f"## {fig._sec} "],
                                        "is_proof": False}
              for fig in figures}
        return cls(overrides=ov)

    @classmethod
    def from_dict(cls, d: dict) -> "FigureEmbedOverrides":
        return cls(overrides=d if isinstance(d, dict) else {})

    def to_dict(self) -> dict:
        return self.overrides

    def dump(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)


def write_figure_embed_overrides(overrides: Dict[str, dict], path: str) -> None:
    """Instantiate ``figure_embed_overrides.json`` from a
    ``{filename: {"anchors": [...], "is_proof": bool}}`` mapping and write it.

    The anchor *computation* lives in ``build_precise_anchors.py`` (it needs
    PyMuPDF + flow-specific regex); this module owns the JSON shape + write,
    per the one-JSON-one-directory rule.
    """
    FigureEmbedOverrides(overrides=overrides).dump(path)
