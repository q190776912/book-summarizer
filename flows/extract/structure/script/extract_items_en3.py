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
from item_dedup import dedup_items

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
    'proposltlon': 'Proposition',
    'corollary': 'Corollary', 'example': 'Example', 'remark': 'Remark',
    'exercise': 'Exercise', 'assertion': 'Assertion', 'conjecture': 'Conjecture',
    'fact': 'Fact',
}
EN3_LABEL_ALT = '|'.join([
    '(?:Definition|Defnition|Defintion)', 'Theorem', 'Lemma',
    # OCR 常把 i 误读为 l（PROPOslTloN），加模糊分支容忍
    '(?:Proposition|Propos[l1]t[l1]on)',
    'Corollary', 'Example', 'Remark',
    'Exercise', 'Assertion', 'Conjecture', 'Fact',
])
EN3_LAB_RE = re.compile(
    # 🔴 尾界用 `(?![A-Za-z])` 而非 `\b`：OCR 常把标签与编号粘连成
    # `PROPOsITiON2.7.2`（无空格），而 `\b` 在「字母→数字」之间永不成立
    # （两者都是 \w），粘连形态整条漏抽；负向前瞻既容忍粘连又排除
    # `Propositional` 这类单词延伸。
    r'\b(' + EN3_LABEL_ALT + r')s?(?![A-Za-z])\s*(?:\([^)]*\))?\s*'
    r'(\d+)\s*' + SEP_TIGHT + r'\s*(\d+)\s*' + SEP_TIGHT + r'\s*(\d+)',
    re.IGNORECASE,
)


def extract_items_en3(extract_dir, chapter, start, end, want_examples=True):
    """Extract EN three-level `Label C.S.N` entries for one chapter.

    `chapter` filters by the FIRST numeric component (the chapter number), so a
    stray `Remark 2.3.4` inside chapter 1 is dropped.  Returns items shaped like
    the other extractors: {key, label, page, text}.
    """
    # 块首装饰字符（Brin & Stuck 用 * 标记难题："*Exercise 1.2.4 ..."），
    # 不剥离会被「块首判定」整条漏抽；括号 ( 不在白名单——"(Exercise 2.1.3)"
    # 是交叉引用，必须保持拒绝。
    _DECOR = "*\u00b7\u2022\u2192'\u201d\u201c\""

    def _emit(txt, m, p):
        # 标题判别：真条目头在 C.S.N 后是句点（或「(定理名/人名)」括注再句点）。
        # OCR 断行会把 'by Proposition' 留在上块，使行首引用伪装成条目头
        # （实测：'PROPOSITION 2.1.2, Zorn's lemma...' / 'LEMMA 6.1.1 are
        # satisfied...' / 'PROPOSITION 9.2.1(6), H(...'）——按后随标点拒绝。
        rest = txt[m.end():].lstrip()
        if rest and not (rest[0] == "." or rest[0] == "\u3002" or
                         re.match(r"\(([^)]*[A-Za-z][^)]*)\)\s*[.\s]", rest)):
            return
        label = EN3_LABEL_CANON.get(m.group(1).lower(), m.group(1).title())
        if label == "Example" and not want_examples:
            return
        c, s, n = int(m.group(2)), int(m.group(3)), int(m.group(4))
        if c != chapter:
            return
        # Sanity bounds (avoid OCR garbage like 1.99.1).
        if s > 20 or n > 60:
            return
        key = f"{label} {c}.{s}.{n}"
        snippet = txt[max(0, m.start() - 5):m.end() + 90].replace("\n", " ")
        items.append({"key": key, "label": label, "page": p, "text": snippet})

    items = []
    for p in range(start, end + 1):
        fp = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        with open(fp, "r", encoding="utf-8") as f:
            data = PageJson.load(os.path.join(extract_dir, f"page_{p:03d}.json")).data
        blocks = [t.get("text", "") for t in data.get("text", [])]
        prev = ""
        for txt in blocks:
            if not txt:
                continue
            for m in EN3_LAB_RE.finditer(txt):
                # Heading vs prose reference: a real entry heading starts the
                # text block (e.g. "REMARK 1.1.1. Map (1.1.1) ...").  A
                # cross-reference like "by Lemma 11.26" / "satisfy Theorem 2.3"
                # sits mid-block and is skipped.
                if txt[:m.start()].strip(_DECOR + " \t"):
                    continue
                _emit(txt, m, p)
            # 跨块连字标签：OCR 把 "Proposi-" 留在上块末尾、下块以
            # "tion 4.10.3." 开头（实测 p112→p113 Proposition 4.10.3 整条漏抽）。
            # 取上块尾部字母段与下块拼接（有连字则去连字直拼）后锚定重试。
            tailm = re.search(r"([A-Za-z]{2,})([-\u00ad])?\s*$", prev)
            if tailm:
                frag = tailm.group(1)
                joined = (frag + txt.lstrip()) if tailm.group(2) \
                    else (frag + " " + txt.lstrip())
                jm = EN3_LAB_RE.match(joined)
                if jm:
                    _emit(joined, jm, p)
            prev = txt or prev
    # Collapse reference mentions but KEEP two genuinely different items that
    # share a (label, number) — e.g. a source book printing the same number
    # twice (a printing off-by-one, like Lasota & Mackey's Proposition 12.8.3
    # appearing on two pages).  Genuine headings are already pre-filtered above
    # (only block-start matches survive), so any same-key collision with a
    # different heading text is a distinct item.
    out = dedup_items(items)
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
