import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json, re
from lib.regexlib import SEP_TIGHT

# ---------------------------------------------------------------------------
# ENGLISH-aware extraction (merged from extract_items_en.py)
# For English textbooks with two-level numbering (Theorem 1.1, Definition 1.1,
# Example 1.25, ...). Returns items shaped like the CN path: {key, label, page, text}.
# ---------------------------------------------------------------------------
EN_LABELS = ["Definition", "Theorem", "Lemma", "Proposition", "Corollary", "Example",
             "Assertion", "Conjecture", "Remark"]
EN_LAB_RE = re.compile(
    r'\b(' + '|'.join(EN_LABELS) + r')\b\s*(?:\([^)]*\))?\s*'
    r'(\d+)\s*' + SEP_TIGHT + r'\s*(\d+)',
    re.IGNORECASE,
)

def extract_items_en(extract_dir, start, end, want_examples=True):
    items = []
    for p in range(start, end + 1):
        fp = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        for t in data.get("text", []):
            txt = t.get("text", "")
            if not txt:
                continue
            for m in EN_LAB_RE.finditer(txt):
                label = m.group(1)
                if label == "Example" and not want_examples:
                    continue
                # Heading vs prose reference: a real entry heading starts the
                # text block (e.g. "THEOREM 8.4. Let k >= 2."); a cross-reference
                # like "by Lemma 11.26" / "satisfy Theorem 11.1" sits mid-block.
                # Skip mid-block matches to avoid false-positive phantom items
                # (Apostol prints headings in UPPERCASE / OCR-mangled case, so
                # IGNORECASE is needed above, but it also widens prose capture).
                if txt[:m.start()].strip():
                    continue
                key = f"{label} {m.group(2)}.{m.group(3)}"
                snippet = txt[max(0, m.start() - 5):m.end() + 90].replace("\n", " ")
                items.append({"key": key, "label": label,
                              "page": p, "text": snippet})
    seen = {}
    for it in items:
        if it["key"] not in seen:
            seen[it["key"]] = it
    out = sorted(seen.values(), key=lambda x: (x["page"], x["key"]))
    return out
