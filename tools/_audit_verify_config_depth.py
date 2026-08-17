import json, glob, os

ORDINAL_DEPTH = {1: 1, 2: 2, 3: 3, 4: 2, 5: 3, 6: 2, 7: 2, 8: 3, 9: 3}
base = r"D:/study/book"
files = sorted(glob.glob(os.path.join(base, "**", "verify_config.json"), recursive=True))
files = [f for f in files if "node_modules" not in f]

problems = []
for f in files:
    with open(f, encoding="utf-8") as fh:
        cfg = json.load(fh)
    rel = os.path.relpath(f, base)
    for i, g in enumerate(cfg.get("ordinal", []) or []):
        t = g.get("type")
        d = g.get("depth")
        if d is not None:
            deriv = ORDINAL_DEPTH.get(t)
            status = "OK" if deriv == d else "DESYNC"
            problems.append((rel, f"ordinal[{i}] name={g.get('name')}", f"type={t}", f"depth={d}", f"derived={deriv}", status))
    fm = cfg.get("formula")
    if isinstance(fm, dict) and "depth" in fm:
        t = fm.get("type")
        d = fm.get("depth")
        deriv = ORDINAL_DEPTH.get(t)
        status = "OK" if deriv == d else "DESYNC"
        problems.append((rel, "formula", f"type={t}", f"depth={d}", f"derived={deriv}", status))

if not problems:
    print("NO depth fields found in any file.")
else:
    print(f"{'FILE':52} {'LOC':30} {'SPEC':10} {'DEPTH':7} {'DERIV':7} STATUS")
    for rel, loc, ty, d, der, st in problems:
        print(f"{rel[:51]:52} {loc[:29]:30} {ty:10} {d:7} {der:7} {st}")
