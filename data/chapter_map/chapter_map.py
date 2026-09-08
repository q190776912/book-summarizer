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
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional

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


# ═══════════════════════════════════════════════════════════════════════════
# 章类语义（kind）—— 与「序标（num）」正交的**唯一真源**
# ═══════════════════════════════════════════════════════════════════════════
# 历史包袱：chapter_map 曾以 `ch` 键承载章号，字母值（A/S…）被全链路一律解释为
# 「附录」。这对 Katok《Introduction to the Modern Theory of Dynamical Systems》
# 不成立——它的 Supplement（S.x.y 编号）不是附录。（2026-09-08 用户裁定：弃用
# `ch` 键，改用显式 `kind` + `num`。）
#
#   kind = 1  章（chapter）        num = 数字（0/1/2…；罗马见于少数书）
#   kind = 2  附录（appendix）     num = 字母 A/B/…（个别书用数字）
#   kind = 3  补篇（supplement）   num = 字母 S/…（个别书用数字）
#
# 🔴 `kind` 是语义，`num` 是印刷序标：二者不可互推。Supplement 与 Appendix 的
# 目录名 / 文件名 / H1 标题 / 配置路由一律按 kind 分流，不再按「是否数字」猜。
KIND_CHAPTER = 1
KIND_APPENDIX = 2
KIND_SUPPLEMENT = 3

KIND_NAME = {KIND_CHAPTER: "chapter", KIND_APPENDIX: "appendix",
             KIND_SUPPLEMENT: "supplement"}
KIND_BY_NAME = {"chapter": KIND_CHAPTER, "ch": KIND_CHAPTER,
                "appendix": KIND_APPENDIX, "app": KIND_APPENDIX,
                "supplement": KIND_SUPPLEMENT, "suppl": KIND_SUPPLEMENT,
                "sup": KIND_SUPPLEMENT}

_SUPPLEMENT_RE = re.compile(r"\b(supplement|supplementary|补篇|增补)\b", re.I)
_APPENDIX_RE = re.compile(r"\b(appendix|appendices|附录|附\s*录)\b", re.I)


def normalize_kind(raw_kind: Any, num: Any, *names: str) -> int:
    """把任意写法的 kind 归一为 KIND_*；缺省时**按书-infected 证据推断**。

    优先级：显式 `kind`（整数码或名字串）> 章名/'num' 语义信号 > 形态回退
    （非数字 num 一律视为附录，保持历史书零回归）。
    """
    if raw_kind is not None and raw_kind != "":
        if isinstance(raw_kind, (int, float, bool)) and not isinstance(raw_kind, bool):
            try:
                k = int(raw_kind)
                if k in KIND_NAME:
                    return k
            except (TypeError, ValueError):
                pass
        elif isinstance(raw_kind, str):
            k = KIND_BY_NAME.get(raw_kind.strip().lower())
            if k is not None:
                return k
    blob = " ".join(str(n or "") for n in names)
    if _SUPPLEMENT_RE.search(blob):
        return KIND_SUPPLEMENT
    if _APPENDIX_RE.search(blob):
        return KIND_APPENDIX
    s = str(num if num is not None else "").strip()
    return KIND_APPENDIX if (s and not s[:1].isdigit()) else KIND_CHAPTER


def normalize_num(raw_num: Any) -> Any:
    """nun 归一：数字串 → int；其余（字母/罗马/其它序标）→ 原串去空白。"""
    s = str(raw_num if raw_num is not None else "").strip()
    if s.isdigit():
        return int(s)
    return s


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
def _canon_record(num: Any, kind: Any, name: Any, name_en: Any, start: Any, end: Any,
                  extra: Optional[dict] = None) -> dict:
    """构造一条规范记录（`# ruff: noqa` 见下方字段契约）。

    返回字段（🔴 单一真源，消费方不得自行拼 ['ch']）：
      num        int|str   印刷序标（数字章为 int，字母/罗马为 str）
      num_str    str       num 的字符串形态（文件名 / 键比较用）
      kind       int       KIND_CHAPTER / KIND_APPENDIX / KIND_SUPPLEMENT
      kind_name  str       "chapter" / "appendix" / "supplement"
      is_appendix / is_supplement   bool
      name / name_en / name_cn / start / end
      ch         int|str   ⚠️ **遗留别名**（= num），仅供未迁移的旧消费方读取；
                           新写的 on-disk chapter_map.json **不再出现这个键**。
    """
    n = normalize_num(num)
    k = normalize_kind(kind, n, name, name_en, (extra or {}).get("name_cn"), str(num))
    rec = {
        "num": n,
        "num_str": str(n),
        "kind": k,
        "kind_name": KIND_NAME[k],
        "is_appendix": k == KIND_APPENDIX,
        "is_supplement": k == KIND_SUPPLEMENT,
        "name": name or "",
        "name_en": name_en or "",
        "name_cn": (extra or {}).get("name_cn", "") or "",
        "start": start,
        "end": end,
    }
    rec["ch"] = n  # legacy alias
    return rec


def iter_chapter_records(raw: dict) -> List[dict]:
    """把任一形态的 chapter_map 归一化成规范记录列表。

    on-disk 允许三种形态：
      A（canonical，2026-09-08 起）  {"chapters": [{"kind":1,"num":4,…}, …]}
      B（legacy list）              {"chapters": [{"ch":4,…}, …]}
      C（legacy flat dict）         {"1": {"name":…}, "A": {"name":…}, …}
    🔴 A 是唯一推荐形态：`kind` + `num` 显式区分「章 / 附录 / 补篇」与「印刷序标」；
    B/C 因缺 `kind` 只能推断（字母 num → 附录），仅为旧书读取兼容保留。
    """
    if not isinstance(raw, dict):
        return []
    out: List[dict] = []
    if isinstance(raw.get("chapters"), list):
        for c in raw["chapters"]:
            if not isinstance(c, dict):
                continue
            num = c.get("num", c.get("ch", c.get("chapter")))
            start = c.get("start", c.get("start_page", c.get("pdf_start")))
            end = c.get("end", c.get("end_page", c.get("pdf_end")))
            out.append(_canon_record(
                num, c.get("kind"), c.get("name", ""),
                c.get("name_en", c.get("title", "")), start, end, c))
        return out
    for k, v in raw.items():
        if not isinstance(v, dict):
            continue
        out.append(_canon_record(v.get("num", k), v.get("kind"), v.get("name", ""),
                                 v.get("name_en", ""), v.get("start"), v.get("end"), v))
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
        if str(c.get("num")) == str(chapter):
            return c
    raise SystemExit(f"chapter {chapter} not found in {path_or_dir}")


def kind_of(path_or_dir, chapter) -> int:
    """某章的 kind（KIND_*）。未知章回退 KIND_CHAPTER。"""
    try:
        return int(find_chapter(path_or_dir, chapter).get("kind", KIND_CHAPTER))
    except SystemExit:
        return KIND_CHAPTER


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
