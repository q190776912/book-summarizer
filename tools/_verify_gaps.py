"""Temporary diagnostic: verify B-layer gaps against raw OCR source.

For each problematic chapter, loosely scan page_*.json text (EN labels,
OCR-tolerant) and report per label the set of (number, first_page) actually
present in the source vs the contract (book_structure.json). Distinguishes
real extraction omissions (source has it, contract doesn't) from genuine
sparsity (source lacks it too). Also reveals true reading order (page order)
to judge the ch4 ordering-disorder flag.
"""
import os, sys, re, json
from pathlib import Path

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
import page_json
from data.book_structure.book_structure import BookStructure

EXT = "D:/study/book/基础/a-first-course-in-stochastic-processes/_extract"
cm = json.load(open(os.path.join(EXT, "chapter_map.json"), encoding="utf-8"))
RANGES = {int(k): (v["start"], v["end"]) for k, v in cm.items()}

LABELS = ["Theorem", "Corollary", "Lemma", "Proposition", "Definition",
          "Example", "Remark"]

OCR_DIGIT = {'O': 0, 'o': 0, 'Q': 0, 'D': 0, '0': 0,
             'I': 1, 'l': 1, 'i': 1, '1': 1,
             'Z': 2, 'z': 2, '2': 2,
             'A': 4, 'a': 4, '4': 4,
             'S': 5, 's': 5, '5': 5,
             'G': 6, 'g': 6, '6': 6,
             'T': 7, 't': 7, '7': 7,
             'B': 8, 'b': 8, '8': 8,
             'g': 9, '9': 9}


def _ocr_int(tok):
    s = ''.join(str(OCR_DIGIT.get(c, c)) for c in tok)
    return int(s) if s.isdigit() else None


def loose_scan(ch, start, end):
    """Return {label_lower: {num: first_page}} scanned loosely from source."""
    found = {}
    for p in range(start, end + 1):
        fp = os.path.join(EXT, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        try:
            data = page_json.PageJson.load(fp).data
        except Exception:
            continue
        for blk in data.get("text", []):
            t = blk.get("text", "")
            for lab in LABELS:
                # label first:  "Theorem 6.3" / "Theorem 6,3"
                for m in re.finditer(
                        r'(?i)\b' + re.escape(lab) + r'\b[^\n]{0,25}?\b'
                        + str(ch) + r'\s*[.\-·，,]\s*([0-9A-Za-z]+)', t):
                    n = _ocr_int(m.group(1))
                    if n is None:
                        continue
                    d = found.setdefault(lab.lower(), {})
                    if n not in d or p < d[n]:
                        d[n] = p
                # number first:  "6.3 Theorem"
                for m in re.finditer(
                        r'(?i)\b' + str(ch) + r'\s*[.\-·，,]\s*([0-9A-Za-z]+)'
                        + r'[^\n]{0,25}?\b' + re.escape(lab) + r'\b', t):
                    n = _ocr_int(m.group(1))
                    if n is None:
                        continue
                    d = found.setdefault(lab.lower(), {})
                    if n not in d or p < d[n]:
                        d[n] = p
    return found


TYPE_TO_EN = {
    "theorem": "Theorem", "definition": "Definition", "lemma": "Lemma",
    "corollary": "Corollary", "proposition": "Proposition",
    "example": "Example", "remark": "Remark", "exercise": "Exercise",
}
STRIP_CN = re.compile(r'^(定理|定义|引理|推论|命题|例|评注|注)')


def contract_nums(bs, ch):
    node = bs.find_chapter(ch)
    out = {}
    if node is None:
        return out

    def walk(n):
        if n.type in ("chapter", "section"):
            for k in n.sub_sec:
                walk(k)
            return
        if n.type == "exercise":
            return
        lab = TYPE_TO_EN.get(n.type)
        if lab is None:
            return
        key = str(n.key)
        rest = STRIP_CN.sub("", key).strip()
        nums = re.findall(r'\d+', rest)
        if not nums:
            return
        if len(nums) >= 2:
            num = int(nums[1])          # two-level: chapter.num
        else:
            num = int(nums[0])          # single-level example
        out.setdefault(lab.lower(), set()).add(num)
    walk(node)
    return out


def main():
    bs = BookStructure.load(EXT)
    for ch in (2, 3, 4, 6, 8, 9):
        s, e = RANGES[ch]
        src = loose_scan(ch, s, e)
        con = contract_nums(bs, ch)
        print("=" * 70)
        print(f"CHAPTER {ch}  (pages {s}-{e})")
        for lab in [l.lower() for l in LABELS]:
            src_nums = src.get(lab, {})
            con_nums = con.get(lab, set())
            if not src_nums and not con_nums:
                continue
            # source present sorted with pages
            src_sorted = sorted(src_nums.items())
            src_set = set(src_nums.keys())
            only_src = src_set - con_nums      # in source but not contract
            only_con = con_nums - src_set      # in contract but not source
            gaps = sorted(src_set - con_nums)  # candidate real omissions
            print(f"  [{lab}]")
            print(f"    source nums(pages): {src_sorted}")
            print(f"    contract nums:      {sorted(con_nums)}")
            if only_src:
                print(f"    >>> IN SOURCE NOT CONTRACT (real omission?): {sorted(only_src)}")
            if only_con:
                print(f"    <<< IN CONTRACT NOT SOURCE (phantom?): {sorted(only_con)}")


if __name__ == "__main__":
    main()
