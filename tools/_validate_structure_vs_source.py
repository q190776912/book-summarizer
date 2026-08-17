#!/usr/bin/env python3
"""Validate book_structure.json entry keys against the actual book source.

For each chapter (page range from chapter_map.json), extract the entry labels
that genuinely appear in the source text (Theorem/Corollary/Lemma/Definition/
Remark/Proposition as two-level N.N; Example as single-level N or N.N) and
report any book_structure key whose (kind, number) does NOT appear in the
source. Such keys are likely spurious extraction artifacts that would
otherwise block the B-layer with a false TRULY-MISSING.

OCR-tolerant: a source match is accepted if the number string appears anywhere
in the source for that kind (loose), so we only flag keys that are clearly
absent. Flagged items need manual review (some may be real but OCR-mangled).
"""
import os, re, json, glob

EXT = r"D:\study\book\基础\a-first-course-in-stochastic-processes\_extract"
BS = os.path.join(EXT, "book_structure.json")
CM = os.path.join(EXT, "chapter_map.json")

EN_TO_CN = {
    "Theorem": "定理", "Corollary": "推论", "Lemma": "引理",
    "Definition": "定义", "Remark": "评注", "Proposition": "命题",
    "Example": "例",
}
TWO_LEVEL = ["Theorem", "Corollary", "Lemma", "Definition", "Remark", "Proposition"]

OCR_MAP = str.maketrans({"l": "1", "I": "1", "i": "1", "O": "0", "o": "0", "S": "5", "Z": "2"})

def ocr_norm(s):
    return s.translate(OCR_MAP)

def collect_source(ch_start, ch_end):
    """Return dict cn_kind -> set of OCR-normalized number strings found in source."""
    found = {cn: set() for cn in EN_TO_CN.values()}
    pats = {}
    for en in TWO_LEVEL:
        pats[en] = re.compile(r"(?i)\b" + en + r"\s+(\d+)\.(\d+)")
    ex_pat = re.compile(r"(?i)\bExample\s+(\d+)(?:\.(\d+))?")
    for pg in range(ch_start, ch_end + 1):
        fp = os.path.join(EXT, f"page_{pg:03d}.json")
        if not os.path.exists(fp):
            continue
        data = json.load(open(fp, encoding="utf-8"))
        for blk in data.get("text", []):
            t = blk.get("text", "")
            if not t:
                continue
            for en in TWO_LEVEL:
                for m in pats[en].finditer(t):
                    found[EN_TO_CN[en]].add(ocr_norm(f"{m.group(1)}.{m.group(2)}"))
            for m in ex_pat.finditer(t):
                if m.group(2):
                    found["例"].add(ocr_norm(f"{m.group(1)}.{m.group(2)}"))
                else:
                    found["例"].add(ocr_norm(m.group(1)))
    return found

def collect_bs_keys(ch):
    keys = set()
    def walk(node):
        if isinstance(node, dict):
            k = node.get("key")
            if isinstance(k, str):
                keys.add(k)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(ch)
    return keys

def main():
    book = json.load(open(BS, encoding="utf-8"))
    cmap = json.load(open(CM, encoding="utf-8"))
    # map chapter number -> (start,end)
    ranges = {int(k): (v["start"], v["end"]) for k, v in cmap.items()}

    for ch in book["sub_sec"]:
        cid = int(ch["key"]) if str(ch["key"]).isdigit() else ch["key"]
        if cid not in ranges:
            continue
        start, end = ranges[cid]
        src = collect_source(start, end)
        bs_keys = collect_bs_keys(ch)
        # separate entry keys (those starting with a known CN kind prefix)
        entry_prefixes = list(EN_TO_CN.values())
        bs_entries = {k for k in bs_keys if any(k.startswith(p) for p in entry_prefixes)}
        missing_in_src = []
        for k in sorted(bs_entries):
            # split prefix and number
            for p in entry_prefixes:
                if k.startswith(p):
                    num = k[len(p):]
                    if ocr_norm(num) not in src[p]:
                        missing_in_src.append((k, p, num))
                    break
        if missing_in_src:
            print(f"\n=== Chapter {cid} ({start}-{end}) : book_structure keys NOT in source ===")
            for k, p, num in missing_in_src:
                print(f"   {k:12s}  [kind={p} num={num}]  source-has-{p}={sorted(src[p])[:8]}")
        else:
            print(f"Chapter {cid}: all {len(bs_entries)} entry keys present in source.")

if __name__ == "__main__":
    main()
