import json, glob, os

ORDINAL_DEPTH = {1: 1, 2: 2, 3: 3, 4: 2, 5: 3, 6: 2, 7: 2, 8: 3, 9: 3}
base = r"D:/study/book"
files = sorted(glob.glob(os.path.join(base, "**", "verify_config.json"), recursive=True))
files = [f for f in files if "node_modules" not in f]

total_removed = 0
type_fixes = []

for f in files:
    with open(f, encoding="utf-8") as fh:
        cfg = json.load(fh)
    rel = os.path.relpath(f, base)
    changed = False

    # ordinal groups
    for i, g in enumerate(cfg.get("ordinal", []) or []):
        if "depth" in g:
            old_depth = g.pop("depth")
            total_removed += 1
            changed = True
            # desync repair: depth 1 + type(=>2) means single-integer intent -> type 1
            deriv = ORDINAL_DEPTH.get(g.get("type"))
            if old_depth != deriv:
                # only the known Example single-integer case: force to single (type 1)
                if old_depth == 1 and g.get("name") == ["Example"] and g.get("type") == 4:
                    g["type"] = 1
                    type_fixes.append((rel, f"ordinal[{i}]", "Example", "type 4->1 (single-integer)"))
                else:
                    type_fixes.append((rel, f"ordinal[{i}]", str(g.get("name")),
                                       f"WARNING desync depth={old_depth} type={g.get('type')} derived={deriv}"))

    # formula block
    fm = cfg.get("formula")
    if isinstance(fm, dict) and "depth" in fm:
        old_depth = fm.pop("depth")
        total_removed += 1
        changed = True
        deriv = ORDINAL_DEPTH.get(fm.get("type"))
        if old_depth != deriv:
            type_fixes.append((rel, "formula", "-",
                               f"WARNING desync depth={old_depth} type={fm.get('type')} derived={deriv}"))

    if changed:
        with open(f, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        print(f"[FIXED] {rel}")

print(f"\nTotal 'depth' fields removed: {total_removed}")
if type_fixes:
    print("Type corrections / warnings:")
    for t in type_fixes:
        print("  ", t)
else:
    print("No desync found; all depth values were consistent with type.")
