#!/usr/bin/env python3
"""chapter_map.py — model + constructor for ``chapter_map.json``.

The chapter map is the page<->chapter index shared by every downstream
stage (extractor, figure pipeline, book-formula manifest, ...). On disk it is
keyed by chapter number as a string:

    {"1": {"name", "name_en", "start", "end"}, ...}

Model (subclass of :class:`JsonData`):
    Chapter      — one chapter entry (a leaf record, plain dataclass)
    ChapterMap   — the whole document (the JSON subclass)

Usage:
    python chapter_map.py <extract_dir>
"""
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

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
class Chapter:
    """One entry of ``chapter_map.json`` (keyed by chapter number as string)."""
    ch: str
    name: str
    name_en: str
    start: int
    end: int

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "name_en": self.name_en,
            "start": self.start,
            "end": self.end,
        }


@dataclass
class ChapterMap(JsonData):
    """The ``chapter_map.json`` document — a JSON subclass with constructors.

    Constructors:
        default()           — the bundled do Carmo map (used when none exists)
        from_dict(d)        — build from a raw ``{ch: {...}}`` mapping
        load(path)          — build from an existing chapter_map.json
    Export:
        to_dict() / dump(path)
    """
    chapters: List[Chapter] = field(default_factory=list)

    # ---- constructors ----
    @classmethod
    def default(cls) -> "ChapterMap":
        raw = {
            "1": {"name": "曲线", "name_en": "Curves", "start": 9, "end": 58},
            "2": {"name": "正则曲面", "name_en": "Regular Surfaces", "start": 59, "end": 141},
            "3": {"name": "高斯映射的几何", "name_en": "The Geometry of the Gauss Map", "start": 142, "end": 224},
            "4": {"name": "曲面的内蕴几何", "name_en": "The Intrinsic Geometry of Surfaces", "start": 225, "end": 322},
            "5": {"name": "全局微分几何", "name_en": "Global Differential Geometry", "start": 323, "end": 478},
        }
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, d: dict) -> "ChapterMap":
        chapters = [
            Chapter(ch=k, name=v["name"], name_en=v["name_en"],
                    start=v["start"], end=v["end"])
            for k, v in d.items()
        ]
        return cls(chapters=sorted(chapters, key=lambda c: int(c.ch)))

    # ---- export ----
    def to_dict(self) -> dict:
        return {c.ch: c.to_dict() for c in self.chapters}


def load_chapter_map_raw(path: str) -> dict:
    """Load ``chapter_map.json`` and return the parsed dict AS-IS (no shape
    normalisation), so callers that consume either the ``{"chapters": [...]}``
    list form or the ``{"1": {...}}`` flat-dict form keep working.

    This is the single read boundary for ``chapter_map.json`` in ``flows/`` and
    ``verify/`` — no bare ``json.load`` of that file should appear elsewhere.
    """
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


# ── 双形态归一化（🔴 消费方统一走这里，不要裸 json.load） ─────────────────
# on-disk 存在两种形态：
#   A（canonical，chapter_map.md 记载）：{"chapters": [{"ch":1,"name":…,…}]}
#   B（legacy flat dict，ChapterMap.to_dict() 产出）：{"1": {"name":…,…}, …}
# 只认其一的工具会在另一形态上直接报 "chapter N not found"
# （实测：dump_chapter_source.py 只认 B、dump_chapter_ocr.py 只认 A）。
def iter_chapter_records(raw: dict) -> List[dict]:
    """把任一形态的 chapter_map 归一化成 `[{ch,name,name_en,start,end}, …]`。"""
    if not isinstance(raw, dict):
        return []
    out: List[dict] = []
    if isinstance(raw.get("chapters"), list):
        for c in raw["chapters"]:
            if not isinstance(c, dict):
                continue
            out.append({"ch": c.get("ch"), "name": c.get("name", ""),
                        "name_en": c.get("name_en", ""),
                        "start": c.get("start"), "end": c.get("end")})
        return out
    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        out.append({"ch": k, "name": v.get("name", ""),
                    "name_en": v.get("name_en", ""),
                    "start": v.get("start"), "end": v.get("end")})
    return out


def load_chapter_records(path_or_dir) -> List[dict]:
    """从文件路径或 extract_dir 读 chapter_map.json，返回归一化记录列表。"""
    p = str(path_or_dir)
    if os.path.isdir(p):
        p = os.path.join(p, "chapter_map.json")
    if not os.path.exists(p):
        raise SystemExit(f"chapter_map.json not found: {p}")
    return iter_chapter_records(load_chapter_map_raw(p))


def find_chapter(path_or_dir, chapter) -> dict:
    """按章号取一条归一化记录；找不到直接 SystemExit。"""
    recs = load_chapter_records(path_or_dir)
    for c in recs:
        if str(c.get("ch")) == str(chapter):
            return c
    raise SystemExit(f"chapter {chapter} not found in {path_or_dir}")


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python chapter_map.py <extract_dir>")
        sys.exit(1)
    out_dir = sys.argv[1]
    cm = ChapterMap.default()
    out = os.path.join(out_dir, "chapter_map.json")
    cm.dump(out)
    print(f"chapter_map.json written to {out}")


if __name__ == "__main__":
    main()
