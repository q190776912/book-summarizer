#!/usr/bin/env python3
"""figure_index.py — model + constructor for ``figure_index.json``.

When the figure pipeline did NOT emit a ``figure_index.json``, this helper
synthesizes it from the detector output (``figure_detect.json``), and also
emits a manual ``figure_embed_overrides.json`` (see ``figure_embed_overrides/``)
so ``embed_figures.py`` can anchor each figure to the section it sits in.

Why:
- ``figure_detect.json``'s ``chapter`` field is frequently MIS-assigned (it lags
  the real chapter). We re-derive the true chapter from the figure's ``page``
  using ``chapter_map.json`` (the same page->chapter map the extractor uses).
- The detector ``cap_text`` is just "Figure X.Y" (a figure NUMBER, not a
  theorem/example number), so ``embed_figures.py``'s automatic caption->item
  matching finds nothing and would SKIP every figure. We therefore emit a manual
  override anchoring each figure to the SECTION (``## §N.M``) it sits in.

Models (subclass of :class:`JsonData`):
    Figure              — one entry of figure_index.json (leaf record)
    FigureIndex         — the figure_index.json document

The sibling ``FigureEmbedOverrides`` lives in ``figure_embed_overrides/``.

Usage:
    python figure_index.py <book_dir>
"""
import json
import os
import sys
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Dict, List, Optional

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
from figure_embed_overrides import FigureEmbedOverrides
from lib.util import chapter_of_page
from lib.regexlib import FIG_ITEM_SEC_RE as ITEM_SEC_RE, FIG_PAGE_RE as PAGE_RE
from lib.figure_io import load_figure_index


@dataclass
class Figure:
    """One entry of ``figure_index.json``.

    Field set matches the canonical schema documented in
    ``flows/write-source/figures/figures.md``:
    chapter / page / fig_idx / label / bbox / conf / file / caption / source.
    """
    chapter: int
    page: int
    file: str
    fig_idx: int = 0
    label: Optional[str] = None
    bbox: Optional[list] = None
    conf: Optional[float] = None
    caption: Optional[str] = None
    source: str = "detect"

    def to_dict(self) -> dict:
        return {
            "chapter": self.chapter,
            "page": self.page,
            "fig_idx": self.fig_idx,
            "label": self.label,
            "bbox": self.bbox,
            "conf": self.conf,
            "file": self.file,
            "caption": self.caption,
            "source": self.source,
        }


@dataclass
class FigureIndex(JsonData):
    """The ``figure_index.json`` document."""
    figures: List[Figure] = field(default_factory=list)

    @classmethod
    def from_figures(cls, figures: List[Figure]) -> "FigureIndex":
        return cls(figures=figures)

    @classmethod
    def from_records(cls, records: List[dict]) -> "FigureIndex":
        """Build from raw dict entries (e.g. produced by the figure pipeline).

        Only the known :class:`Figure` fields are carried over, so callers may
        pass richer dicts without error.
        """
        known = {f.name for f in fields(Figure)}
        figs = [Figure(**{k: v for k, v in r.items() if k in known}) for r in records]
        return cls(figures=figs)

    @classmethod
    def from_dict(cls, d) -> "FigureIndex":
        if isinstance(d, list):
            return cls.from_records(d)
        if isinstance(d, dict) and "figures" in d:
            return cls.from_records(d["figures"])
        raise TypeError("FigureIndex.from_dict expects a list or {'figures': [...]}")

    def to_dict(self) -> list:
        return [f.to_dict() for f in self.figures]

    def dump(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)


def section_map_for(ext: str, ch: int) -> dict:
    ocr = os.path.join(ext, f"ch{ch}_ocr.txt")
    if not os.path.exists(ocr):
        return {}
    cur = None
    out = {}
    with open(ocr, encoding="utf-8") as f:
        page = None
        for line in f:
            line = line.rstrip("\n")
            m = PAGE_RE.match(line)
            if m:
                page = int(m.group(1))
                continue
            if page is None:
                continue
            sm = ITEM_SEC_RE.match(line)
            if sm:
                cur = f"§{int(sm.group(1))}.{int(sm.group(2))}"
            if cur is not None:
                out[page] = cur
    return out


def collect(ext: str, chaps) -> List[Figure]:
    """Single pass over figure_detect.json -> list of Figure (with derived ``_sec``)."""
    det = json.load(open(os.path.join(ext, "figure_detect.json"), encoding="utf-8"))
    if isinstance(chaps, dict):
        section_maps = {int(k): section_map_for(ext, int(k)) for k in chaps}
    else:
        section_maps = {int(c.get("ch", c) if isinstance(c, dict) else c): section_map_for(ext, int(c.get("ch", c) if isinstance(c, dict) else c)) for c in chaps}
    figures: List[Figure] = []
    for e in det:
        page = e["page"]
        ch = chapter_of_page(page, chaps) or e.get("chapter")
        smap = section_maps.get(int(ch), {})
        cand = [p for p in smap if p <= page]
        sec = smap[max(cand)] if cand else f"§{ch}.1"
        fig = Figure(chapter=ch, page=page, file=e["file"],
                     caption=e.get("cap_text"), bbox=e.get("bbox"))
        fig._sec = sec  # type: ignore[attr-defined]
        figures.append(fig)
    return figures


def merge_index(out_dir, ch, assigned):
    """Merge assigned entries for chapter ``ch`` into figure_index.json,
    preserving manual (``source==manual``) entries for that chapter.

    Delegated from ``flows/.../assign_figures.py`` so the figure_index.json
    instantiation lives with its model (one-JSON-one-directory rule). Returns
    the merged record list.
    """
    idx_path = os.path.join(out_dir, "figure_index.json")
    existing = load_figure_index(out_dir) or []
    # keep manual entries for this chapter; drop this chapter's detect entries
    kept = [e for e in existing
            if not (e.get("chapter") == ch and e.get("source") != "manual")]
    merged = kept + assigned
    merged.sort(key=lambda e: (e.get("chapter", 0), e.get("page", 0), e.get("fig_idx", 0)))
    FigureIndex.from_records(merged).dump(idx_path)
    return merged


def main() -> None:
    book_dir = sys.argv[1] if len(sys.argv) > 1 else "."
    ext = os.path.join(book_dir, "_extract")
    det_path = os.path.join(ext, "figure_detect.json")
    cmap_path = os.path.join(ext, "chapter_map.json")
    if not os.path.exists(det_path):
        print("No figure_detect.json — nothing to build.")
        return
    chaps = json.load(open(cmap_path, encoding="utf-8"))["chapters"]

    figures = collect(ext, chaps)
    FigureIndex.from_figures(figures).dump(os.path.join(ext, "figure_index.json"))
    overrides = FigureEmbedOverrides.from_figures(figures)
    overrides.dump(os.path.join(ext, "figure_embed_overrides.json"))

    print(f"Wrote figure_index.json ({len(figures)} figures) + figure_embed_overrides.json")
    for fig in figures:
        fname = fig.file.split("/")[-1]
        print(f"  p{fig.page:>3} ch{fig.chapter} {fname:<22} -> {overrides.overrides[fname]['anchors'][0]}")


if __name__ == "__main__":
    main()
