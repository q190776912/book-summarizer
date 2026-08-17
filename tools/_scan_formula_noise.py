#!/usr/bin/env python3
"""Scan all page_*.json text for formula numbers and flag OCR-ambiguous
trailing-letter noise (l/I/i/o/O -> digit confusions) whose digit-corrected
sibling already exists in the same chapter. Depth-2 numbering: N.M, where N
is the chapter. Self-contained (mirrors formula_tag.build_formula_patterns(2)).
"""
import os, re, glob, json
from collections import defaultdict

EXT = r"D:\study\book\基础\a-first-course-in-stochastic-processes\_extract"
START, END = 62, 552  # chapter 2-9 page range (inclusive)

# depth-2 group: \d+.\d+ optionally followed by a single trailing letter
GROUP = r"\d+\.\d+(?:[a-zA-Z])?"
PATS = [
    r"[（(]\s*" + GROUP + r"\s*[）)]",   # (1.17) / （1.17）
    r"\bEq\.?\s+" + GROUP,                # Eq. 1.17
    r"\bEquation\s+" + GROUP,             # Equation 1.17
    r"式\s*[（(]?\s*" + GROUP,            # 式（1.17）
    GROUP,                                # bare 1.17
]
COMPILED = [re.compile(p) for p in PATS]

OCR_LETTERS = set("lIoOi")  # classic digit-confusion letters

def norm(tok):
    return tok.replace(" ", "").replace("．", ".").replace("－", "-")

def main():
    by_ch = defaultdict(set)
    for pg in range(START, END + 1):
        fp = os.path.join(EXT, f"page_{pg:03d}.json")
        if not os.path.exists(fp):
            continue
        with open(fp, encoding="utf-8") as f:
            data = json.load(f)
        for blk in data.get("text", []):
            txt = blk.get("text", "")
            if not txt:
                continue
            for pat in COMPILED:
                for m in pat.finditer(txt):
                    tok = m.group(1) if m.lastindex else m.group(0)
                    tok = norm(tok)
                    # keep only the captured group if present
                    # (some patterns have no group; take whole match minus parens)
                    mm = re.match(r"[（(]\s*(" + GROUP + r")\s*[）)]", tok)
                    if mm:
                        tok = mm.group(1)
                    # chapter = first component
                    first = tok.split(".")[0]
                    if first.isdigit():
                        by_ch[int(first)].add(tok)

    print("=== Formula-number OCR-noise candidates (chapters 2-9) ===")
    any_found = False
    for ch in sorted(by_ch):
        nums = by_ch[ch]
        # digit-corrected siblings present in this chapter
        base_exists = lambda n: n in nums
        candidates = []
        for n in sorted(nums):
            if n[-1] in OCR_LETTERS and n[-1].isalpha():
                # corrected forms: replace trailing letter with 0-9
                stem = n[:-1]
                corr = [stem + d for d in "0123456789"]
                sib = [c for c in corr if base_exists(c)]
                candidates.append((n, sib))
        if candidates:
            any_found = True
            print(f"\n-- Chapter {ch} --")
            for n, sib in candidates:
                verdict = "NOISE (digit sibling exists)" if sib else "REVIEW (no sibling)"
                print(f"   {n:10s} -> corrected siblings {sib}  [{verdict}]")
    if not any_found:
        print("No OCR-letter formula-number candidates found in chapters 2-9.")

if __name__ == "__main__":
    main()
