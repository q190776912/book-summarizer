import json, sys, os

extract = sys.argv[1]
ch = sys.argv[2]
unit_keys = sys.argv[3:]  # if empty, all

base = os.path.join(extract, "book_structure")
struct = json.load(open(os.path.join(base, f"ch{ch}.json"), encoding="utf-8"))
units_dir = os.path.join(base, "units", f"ch{ch}")
manifest = json.load(open(os.path.join(units_dir, "manifest.json"), encoding="utf-8"))

# map structure key -> manifest entry (id, file, type)
key2man = {}
for u in manifest["units"]:
    key2man[u["key"]] = u

def walk(node, out):
    # collect text/formula in document order from this node and descendants
    for item in node.get("sub_sec", []):
        if "sub_sec" in item and ("type" in item and item.get("type") in ("description","section","proposition","definition","lemma","theorem","corollary","exercise","problem","chapter","remark","proof")):
            # it's a child node (e.g. proof). Recurse but mark depth via indent
            walk(item, out)
        else:
            if "text" in item:
                out.append(("T", item["text"]))
            elif "formula" in item:
                out.append(("F", item["formula"]))
            else:
                pass

def find_node(key):
    # recursive search the structure tree for a node with matching key
    stack = [struct]
    while stack:
        n = stack.pop()
        if n.get("key") == key:
            return n
        for c in n.get("sub_sec", []):
            if isinstance(c, dict):
                stack.append(c)
    return None

# order by manifest
for u in manifest["units"]:
    if unit_keys and u["key"] not in unit_keys:
        continue
    node = find_node(u["key"])
    print("="*80)
    print(f"UNIT id={u['id']} file={u['file']} type={u['type']} key={u['key']}")
    print("MARK:", u["name"])
    print("-"*80)
    if node is None:
        print("(no structure node found)")
        continue
    out = []
    walk(node, out)
    for kind, val in out:
        if kind == "T":
            print("T:", val)
        else:
            print("F:", val)
    print()
