#!/usr/bin/env python3
"""json_data.py — generic base class for every intermediate-product JSON.

Design rule (one JSON = one directory under ``data/<json_name>/``):

    * each JSON has its own directory containing ``<json_name>.md`` (the spec) and
      ``<json_name>.py`` (the model);
    * every model class subclasses ``JsonData`` — the "one JSON" abstraction
      instantiated once and specialised by each concrete JSON as a subclass.

The base provides the common serialise/deserialise contract.  Subclasses add
their own fields and constructors (``from_dict`` / ``load`` / ``build`` / ...)
and may override ``to_dict`` for non-trivial shapes.
"""
import json
from dataclasses import asdict, is_dataclass


class JsonData:
    """Base for every intermediate-product JSON document."""

    # ---- export ----
    def to_dict(self) -> dict:
        """Default: dataclass -> plain dict. Subclasses may override."""
        if is_dataclass(self):
            return asdict(self)
        raise NotImplementedError(
            f"{type(self).__name__} must implement to_dict()")

    def dump(self, path: str) -> None:
        """Serialise ``to_dict()`` to *path* (UTF-8, indent=2)."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

    # ---- import ----
    @classmethod
    def load(cls, path: str) -> "JsonData":
        """Build an instance from an existing JSON file."""
        with open(path, encoding="utf-8") as f:
            return cls.from_dict(json.load(f))
