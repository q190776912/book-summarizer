import json, glob, os, sys

# boot: inject skill config/verify_config into sys.path
SKILL = r"C:/Users/ye190/.workbuddy/skills/book-summarizer"
sys.path.insert(0, os.path.join(SKILL, "config", "verify_config"))
from verify_config import GroupConfig, ORDINAL_DEPTH

base = r"D:/study/book"
files = sorted(f for f in glob.glob(os.path.join(base, "**", "verify_config.json"), recursive=True) if "node_modules" not in f)

ok = True
for f in files:
    cfg = json.load(open(f, encoding="utf-8"))
    rel = os.path.relpath(f, base)
    groups = []
    for g in cfg.get("ordinal", []) or []:
        gc = GroupConfig.from_dict({"ordinal": [g]}) if False else GroupConfig(
            type=g["type"], name=g.get("name", ["uncat"]), scope=g.get("scope", 2))
        groups.append((g.get("name"), gc.type, gc.depth))
    fm = cfg.get("formula")
    if isinstance(fm, dict):
        fg = GroupConfig(type=fm["type"], name=["formula"], scope=fm.get("scope", 2))
        groups.append(("formula", fg.type, fg.depth))
    print(f"\n{rel}")
    for nm, t, d in groups:
        print(f"   {str(nm)[:30]:30} type={t} -> depth={d}")
print("\nAll files loaded without error.")
