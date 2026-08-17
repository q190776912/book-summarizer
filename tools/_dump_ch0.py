import json, glob, os

EXTRACT = r"D:/study/book/a-first-course-in-abstract-algebra/_extract"
OUT = r"C:/Users/ye190/.agents/skills/book-summarizer/tools/_ch0_dump.txt"

def bbox_of(poly):
    pts = [(poly[i], poly[i+1]) for i in range(0, len(poly), 2)]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)

def main():
    lines = []
    for pg in range(18, 27):
        fp = os.path.join(EXTRACT, f"page_{pg:03d}.json")
        if not os.path.exists(fp):
            lines.append(f"\n##### PAGE {pg} MISSING #####\n")
            continue
        d = json.load(open(fp, encoding="utf-8"))
        texts = d.get("text", [])
        # reading order: by min-y then min-x
        def keyf(t):
            x0, y0, x1, y1 = bbox_of(t["poly"])
            return (round(y0 / 5) * 5, x0)
        texts_sorted = sorted(texts, key=keyf)
        lines.append(f"\n##### PAGE {pg} (text blocks: {len(texts)}) #####\n")
        for t in texts_sorted:
            x0, y0, x1, y1 = bbox_of(t["poly"])
            lines.append(f"[y={y0:.0f} x={x0:.0f}] {t['text']}")
        forms = d.get("formulas", [])
        if forms:
            lines.append(f"\n--- PAGE {pg} FORMULAS ({len(forms)}) ---")
            for f in forms:
                lines.append(f"[cls={f.get('cls')} conf={f.get('conf')}] {f.get('latex')}")
    open(OUT, "w", encoding="utf-8").write("\n".join(lines))
    print("WROTE", OUT, "chars:", sum(len(l) for l in lines))

if __name__ == "__main__":
    main()
