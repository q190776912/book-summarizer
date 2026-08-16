import os
import sys
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
from page_json import PageJson

import os, sys

import json, re
from lib.regexlib import SEP_TIGHT

# ---------------------------------------------------------------------------
# ENGLISH three-level extraction (LABEL-FIRST dots):  Label C.S.N
# For English textbooks that number entries as `Remark 1.1.1`,
# `Definition 2.3.4`, `Theorem 3.2.1`, ...  (three numeric components, the
# label word precedes the number).  Differs from the CN three-level path
# (extract_items, type 3) in TWO critical ways:
#   1. The label word is REQUIRED immediately before the number, so bare
#      figure captions (`FIGURE 1.1.1`) and parenthesised formula refs
#      (`(1.1.1)`) are NEVER captured as items — they share the same C.S.N
#      numbering space as the entries in books like Lasota & Mackey, and the
#      CN path's bare-number regex collides with them (key `1.1-1` overlaps
#      both `Remark 1.1.1` and `FIGURE 1.1.1`).
#   2. Keys are emitted WITH the label and DOTS (`Remark 1.1.1`), matching the
#      written `**Remark 1.1.1**` heading, so the B-layer / data_provider match
#      by (comps, label) separator-agnostically.
# ---------------------------------------------------------------------------
EN3_LABELS = ["Definition", "Theorem", "Lemma", "Proposition", "Corollary",
              "Example", "Remark", "Exercise", "Assertion", "Conjecture", "Fact"]
# OCR 易错变体归一：Definition 在本OCR中常被识为 `Defnition`（漏 i，全书 22 处 /
# 20 页），必须识别并归一为 Definition，否则这些定义条目整条漏抽（见
# §2.2 的 Definition 2.2.3 / 2.2.4 被识为 Defnition 而漏网）。Definition 还可能
# 被识为 Defintion（i/n 转置），一并覆盖。
EN3_LABEL_CANON = {
    'definition': 'Definition', 'defnition': 'Definition', 'defintion': 'Definition',
    'theorem': 'Theorem', 'lemma': 'Lemma', 'proposition': 'Proposition',
    'corollary': 'Corollary', 'example': 'Example', 'remark': 'Remark',
    'exercise': 'Exercise', 'assertion': 'Assertion', 'conjecture': 'Conjecture',
    'fact': 'Fact',
}
EN3_LABEL_ALT = '|'.join([
    '(?:Definition|Defnition|Defintion)', 'Theorem', 'Lemma', 'Proposition',
    'Corollary', 'Example', 'Remark', 'Exercise', 'Assertion', 'Conjecture', 'Fact',
])
EN3_LAB_RE = re.compile(
    r'\b(' + EN3_LABEL_ALT + r')s?\b\s*(?:\([^)]*\))?\s*'
    r'(\d+)\s*' + SEP_TIGHT + r'\s*(\d+)\s*' + SEP_TIGHT + r'\s*(\d+)',
    re.IGNORECASE,
)


def extract_items_en3(extract_dir, chapter, start, end, want_examples=True):
    """Extract EN three-level `Label C.S.N` entries for one chapter.

    `chapter` filters by the FIRST numeric component (the chapter number), so a
    stray `Remark 2.3.4` inside chapter 1 is dropped.  Returns items shaped like
    the other extractors: {key, label, page, text}.
    """
    items = []
    for p in range(start, end + 1):
        fp = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        with open(fp, "r", encoding="utf-8") as f:
            data = PageJson.load(os.path.join(extract_dir, f"page_{p:03d}.json")).data
        for t in data.get("text", []):
            txt = t.get("text", "")
            if not txt:
                continue
            for m in EN3_LAB_RE.finditer(txt):
                label = EN3_LABEL_CANON.get(m.group(1).lower(), m.group(1).title())
                if label == "Example" and not want_examples:
                    continue
                # Heading vs prose reference: a real entry heading starts the
                # text block (e.g. "REMARK 1.1.1. Map (1.1.1) ...").  A
                # cross-reference like "by Lemma 11.26" / "satisfy Theorem 2.3"
                # sits mid-block and is skipped.
                if txt[:m.start()].strip():
                    continue
                c, s, n = int(m.group(2)), int(m.group(3)), int(m.group(4))
                if c != chapter:
                    continue
                # Sanity bounds (avoid OCR garbage like 1.99.1).
                if s > 20 or n > 60:
                    continue
                key = f"{label} {c}.{s}.{n}"
                snippet = txt[max(0, m.start() - 5):m.end() + 90].replace("\n", " ")
                items.append({"key": key, "label": label,
                              "page": p, "text": snippet})
    seen = {}
    for it in items:
        if it["key"] not in seen:
            seen[it["key"]] = it
    out = sorted(seen.values(), key=lambda x: (x["page"], x["key"]))
    return out


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(description="Extract EN three-level Label C.S.N items.")
    ap.add_argument("pos", nargs="*", help="<ch> <start> <end> <extract_dir>")
    ns = ap.parse_args()
    if len(ns.pos) < 4:
        ap.error("needs: <ch> <start> <end> <extract_dir>")
    ch, start, end, extract_dir = int(ns.pos[0]), int(ns.pos[1]), int(ns.pos[2]), ns.pos[3]
    items = extract_items_en3(extract_dir, ch, start, end)
    print(f"=== Ch{ch} EN3 ITEMS ({len(items)}) ===")
    for it in items:
        print(f"{it['key']:18s} p{it['page']:3d}  {it['text'][:80]}")
