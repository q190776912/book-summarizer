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

import os, re, sys, json

# ---------------------------------------------------------------------------
# VAKIL-aware extraction (ordinal = ORDINAL_VAKIL = 8).
#
# Ravi Vakil, "The Rising Sea": number-first three-level western numbering.
#   * Section : "1.2 Categories and functors"        (N.M, title starts uppercase)
#   * Item    : "1.2.1. Definition. ..."             (N.M.K numeric, item counter
#               resets PER SECTION -> verifier key "1.2-1")
#   * Exercise: "1.2.A. EXERCISE. ..."              (N.M.A lettered; INTERSPERSED,
#               kept in the .md but NOT counted as items -> excluded here)
#   * Chapter-end "Exercises" / "1.2 Exercises" blocks -> omitted entirely.
#
# The default three-level extractor is too noisy for this scheme (it mislabels
# lettered exercises as numeric items and emits phantoms like "1.1-0" / "练习1.2"
# from the chapter-end exercise heading), so this dedicated extractor returns
# ONLY the numbered items with canonical keys "N.S-N", matching the MD-side
# keys_in_md output so the A/B layers compare cleanly.
# ---------------------------------------------------------------------------

VAKIL_ITEM = re.compile(r'^(\d{1,2})\.(\d{1,2})\.(\d{1,3})\.\s*(.{0,110})')
VAKIL_EXER = re.compile(r'^(\d{1,2})\.(\d{1,2})\.([A-Z])\.\s*(.{0,110})')
LABEL_RE = re.compile(r'^\d+\.\d+\.\d+\.\s*([A-Za-z][A-Za-z]*)')


def extract_items_vakil(extract_dir, chapter, start_page, end_page, manual_overrides=None):
    items = []
    seen = set()
    for p in range(start_page, end_page + 1):
        fp = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        with open(fp, encoding='utf-8') as f:
            d = PageJson.load(os.path.join(extract_dir, f"page_{p:03d}.json")).data
        for t in d.get('text', []):
            txt = (t.get('text') or '').strip()
            if not txt:
                continue
            for ln in txt.split('\n'):
                ln = ln.strip()
                if not ln:
                    continue
                low = ln.lower()
                # Skip chapter-end exercise headings ("Exercises", "1.2 Exercises").
                if low.startswith('exercise') or re.match(r'^\d{1,2}\.\d{1,2}\s+exercises?\.?$', low):
                    continue
                # Numbered item (anchored -> avoids prose references like "see 1.2.3").
                m = VAKIL_ITEM.match(ln)
                if m:
                    c, s, n = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    if c != chapter:
                        continue
                    key = f"{c}.{s}-{n}"
                    if key in seen:
                        continue
                    seen.add(key)
                    label = ''
                    ml = LABEL_RE.match(ln)
                    if ml:
                        label = ml.group(1)
                    items.append({'key': key, 'label': label, 'page': p,
                                  'text': ln[:120]})
                    continue
                # Lettered exercise -> not a counted item, skip silently.
                if VAKIL_EXER.match(ln):
                    continue
    items.sort(key=lambda x: (x['page'], x['key']))
    if manual_overrides:
        existing = {it['key']: idx for idx, it in enumerate(items)}
        for mo in manual_overrides:
            rec = {'key': mo['key'], 'page': mo.get('page', 0),
                   'label': mo.get('label', ''), 'text': mo.get('text', ''),
                   'agent_recovered': True}
            if mo['key'] in existing:
                items[existing[mo['key']]] = rec
            else:
                items.append(rec)
        items.sort(key=lambda x: (x['page'], x['key']))
    return items, [], []


if __name__ == '__main__':
    import sys
    ex = sys.argv[1]
    ch = int(sys.argv[2]); sp = int(sys.argv[3]); ep = int(sys.argv[4])
    its, w, b = extract_items_vakil(ex, ch, sp, ep)
    print('total items:', len(its))
    for it in its:
        print(it['key'], '|', it.get('label', ''), '| p', it['page'])
