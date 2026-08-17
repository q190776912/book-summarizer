import os, sys, re, json
from pathlib import Path
for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c); break
else:
    _ROOT = str(Path(__file__).resolve().parents[2])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path: sys.path.insert(0, _p)
import lib.boot as _boot; _boot.setup()
import page_json

EXT = "D:/study/book/基础/a-first-course-in-stochastic-processes/_extract"
for p in range(255, 357):
    fp = os.path.join(EXT, f"page_{p:03d}.json")
    if not os.path.exists(fp): continue
    try: data = page_json.PageJson.load(fp).data
    except: continue
    for blk in data.get("text", []):
        t = blk.get("text", "")
        if re.search(r'(?i)\btheorem\b', t):
            print(f"--- p{p}: {t[:160]!r}")
