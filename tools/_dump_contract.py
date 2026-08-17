import os, sys, json
from pathlib import Path
for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c); break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot; _boot.setup()
from data.book_structure.book_structure import BookStructure

EXT = "D:/study/book/基础/a-first-course-in-stochastic-processes/_extract"
bs = BookStructure.load(EXT)
for ch in (2, 3, 4, 6, 8, 9):
    node = bs.find_chapter(ch)
    print("=" * 60)
    print(f"CHAPTER {ch}")

    def walk(n, depth=0):
        if n.type in ("chapter", "section"):
            for k in n.sub_sec:
                walk(k, depth + 1)
            return
        if n.type == "exercise":
            return
        print(f"  {'  ' * depth}{n.type}: key={n.key!r}")
    walk(node)
