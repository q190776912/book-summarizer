# -*- coding: utf-8 -*-
"""基于 OCR 真值图 + 贪心单调门的章节条目重排（通用化，可跨书复用）。

修复场景：write-source 后，B 层（item_numbering_integrity）报 ORDERING BLOCKING ——
即同类型条目（定义/定理/例…）的阅读顺序非单调。根因常是抽取/写源时条目被放进了
错误的 § 子节。本工具以 OCR 源书 page_*.json 派生权威 item→section 真值图，用贪心
单调门把每条目归位到源书真实 §，仅重排+归位、逐字保真、不编造、不改内容。

与 write-source「不得重排条目顺序」规则的关系：本工具不任意重排，而是纠正「条目被
放错 §」这一确定性错误；归位后同 § 内阅读序自然单调，恰好满足 B 层校验要求。

用法:
  python tools/restructure_by_ocr.py <chkey> <pg0> <pg1> <src_md> [--apply]
    chkey : 章 key，如 "2" / "3"
    pg0,pg1: OCR 页码区间（含），取该章在 book_structure.json 的 page_start..page_end
    src_md: 当前真书 md 路径
    --apply: 若给定，自动备份后写回 src_md；否则只写 <extract>/_restructure_<chkey>.out.md 并报告。

依赖: <book>/_extract/ 下须有 book_structure.json 与 page_*.json（脚本按 src_md 同目录的
      _extract 自动定位；找不到时回退脚本同目录，可用 BKS_EXTRACT_DIR 覆盖）。

保险:
  - OCR 目标 § 不在当前 md 的 sec_header 中时回退当前 §（不凭空造 § 头）。
  - HEADER_RE 兼容「带/不带章前缀」(定义2.5 / 定义5)，统一用章内号作键。
  - 逐字保真：仅重排+归位；条目键集合与「去 --- 后的内容行多重集」与源一致（否则报错不写回）。
"""
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

import json
import re
import shutil


# ---- 定位 _extract（book_structure.json / page_*.json 所在）----
# 优先：src_md 同目录下的 _extract；其次：脚本同目录（skill 模式）；再其次：BKS_EXTRACT_DIR。
SRC = sys.argv[4]
SRC_DIR = os.path.dirname(os.path.abspath(SRC))
if os.path.isdir(os.path.join(SRC_DIR, "_extract")):
    EX = os.path.join(SRC_DIR, "_extract")
elif os.path.isdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_extract")):
    EX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_extract")
else:
    EX = os.environ.get("BKS_EXTRACT_DIR", os.path.dirname(os.path.abspath(__file__)))

chkey = sys.argv[1]
pg0, pg1 = int(sys.argv[2]), int(sys.argv[3])
APPLY = "--apply" in sys.argv[5:]
OUT = os.path.join(EX, "_restructure_%s.out.md" % chkey)

# ---------- 1) OCR 真值图 (label,num) -> section ----------
HEADER_RE = re.compile(r'^(定义|定理|引理|推论|命题|例)\s*%s?\.?(\d+)' % chkey)
struct = json.load(open(os.path.join(EX, "book_structure.json"), encoding="utf-8"))
secs = []
def walk(node, level):
    if node.get("type") == "section":
        secs.append((str(node.get("key")), node.get("page_start"), node.get("page_end"), level))
    for v in node.get("sub_sec", []):
        walk(v, level + 1)
for ch in struct.get("sub_sec", []):
    if ch.get("key") == chkey:
        for v in ch.get("sub_sec", []):
            walk(v, 1)
def page_to_sec(pg):
    best = None; bestlv = -1
    for key, ps, pe, lv in secs:
        if ps is None or pe is None: continue
        if ps <= pg <= pe and lv > bestlv:
            bestlv = lv; best = key
    return best
ocr = {}
for pg in range(pg0, pg1 + 1):
    fn = os.path.join(EX, "page_%03d.json" % pg)
    if not os.path.exists(fn): continue
    d = json.load(open(fn, encoding="utf-8"))
    for tb in d.get("text", []):
        t = tb if isinstance(tb, str) else tb.get("text", "")
        if not t: continue
        tn = re.sub(r'\s+', '', t)
        m = HEADER_RE.match(tn)
        if m:
            k = (m.group(1), int(m.group(2)))
            if k not in ocr:
                s = page_to_sec(pg)
                if s: ocr[k] = s
print("[OCR 真值图] %d 项映射" % len(ocr))

# ---------- 2) 解析当前 md ----------
SEC_RE = re.compile(r'^(#{2,6})\s*§\s*(\d+(?:\.\d+)*)\b\s*(.*)$')
ITEM_RE = re.compile(r'^(?:>\s*)?\*\*(定义|定理|引理|推论|命题|例|问题|公理|注记|评注|注)\s*(\d+)(?:\.(\d+))?')
lines = open(SRC, encoding="utf-8").read().split('\n')
n = len(lines)
sec_header = {}
items = []
intro_prose = {}
preamble = []
cur_sec = None
i = 0
while i < n:
    ln = lines[i]
    m = SEC_RE.match(ln.strip())
    if m:
        cur_sec = m.group(2)
        if cur_sec not in sec_header:
            sec_header[cur_sec] = ln.strip()
        i += 1; continue
    if cur_sec is None:
        preamble.append(ln); i += 1; continue
    im = ITEM_RE.match(ln.strip())
    if im:
        label = im.group(1)
        num = int(im.group(3)) if im.group(3) else int(im.group(2))
        itemkey = "%s%d" % (label, num)
        content = [ln]; j = i + 1
        while j < n:
            nxt = lines[j].strip()
            if SEC_RE.match(nxt) or ITEM_RE.match(nxt): break
            content.append(lines[j]); j += 1
        items.append({'key': itemkey, 'label': label, 'num': num,
                      'cur': cur_sec, 'content': content})
        i = j; continue
    intro_prose.setdefault(cur_sec, []).append(ln)
    i += 1

# ---------- 3) 贪心单调门：计算目标 §（保险：目标必须存在于 md） ----------
def sec_tuple(k): return tuple(int(x) for x in k.split('.'))
proposed = {}
for label in set(it['label'] for it in items):
    grp = [it for it in items if it['label'] == label]
    grp.sort(key=lambda x: x['num'])
    maxsec = None
    for it in grp:
        cand = ocr.get((it['label'], it['num']), it['cur'])
        if cand not in sec_header:          # 保险①：目标 § 不在 md 中 -> 留当前
            cand = it['cur']
        ct = sec_tuple(cand); curt = sec_tuple(it['cur'])
        if maxsec is None or ct >= maxsec:
            chosen = cand; maxsec = ct
        else:
            chosen = it['cur'] if curt >= maxsec else '.'.join(str(x) for x in maxsec)
            maxsec = max(maxsec, sec_tuple(chosen))
        proposed[it['key']] = chosen

# ---------- 4) 聚合 + 发射（含 --- 归一化） ----------
secs_d = {}
for k in sec_header:
    secs_d[k] = {'intro': intro_prose.get(k, []), 'items': []}
for it in items:
    tgt = proposed[it['key']]
    secs_d.setdefault(tgt, {'intro': [], 'items': []})
    secs_d[tgt]['items'].append(it)
for k in secs_d:
    secs_d[k]['items'].sort(key=lambda x: x['num'])

def level_of(key): return 2 if key.count('.') == 1 else 3
def canon_sort(keys): return sorted(keys, key=sec_tuple)
out = []
out.extend(preamble)
if preamble and preamble[-1].strip() != '': out.append('')
out.append('')
def emit(key, _depth=0):
    node = secs_d.get(key)
    hdr = sec_header.get(key, "%s §%s" % ('#'*level_of(key), key))
    m = re.match(r'^#{2,6}\s*(§.*)$', hdr)
    body = m.group(1) if m else "§%s" % key
    out.append(('#' * level_of(key)) + ' ' + body)
    if node:
        for lp in node['intro']: out.append(lp)
        its = node['items']
        for idx, it in enumerate(its):
            # 归一化：去尾部空行与尾随 '---'，同节相邻两条目间统一补 '---'
            c = list(it['content'])
            while c and c[-1].strip() == '': c.pop()
            while c and c[-1].strip() == '---': c.pop()
            while c and c[-1].strip() == '': c.pop()
            for cl in c: out.append(cl)
            if idx < len(its) - 1:
                out.append(''); out.append('---'); out.append('')
    out.append('')
    children = [k for k in secs_d if k.startswith(key + '.') and k[len(key)+1:].count('.') == 0]
    for c in canon_sort(children): emit(c, _depth+1)
top = [k for k in secs_d if k.count('.') == 1]
for t in canon_sort(top): emit(t)
result = '\n'.join(out)

# ---------- 5) 保真校验 ----------
def nonempty(p): return [l for l in open(p, encoding="utf-8").read().split('\n') if l.strip()]
def content_lines(p):
    # 去掉 '---' 分隔线与空行后，剩余即真实内容行（定义/定理/证明/公式文本等）
    return [l for l in open(p, encoding="utf-8").read().split('\n')
            if l.strip() and l.strip() != '---']
def itemkeys(p):
    s = set()
    for l in open(p, encoding="utf-8").read().split('\n'):
        mm = ITEM_RE.match(l.strip())
        if mm:
            s.add("%s%d" % (mm.group(1), int(mm.group(3)) if mm.group(3) else int(mm.group(2))))
    return s
open(OUT, 'w', encoding='utf-8').write(result)
src_lines = nonempty(SRC); out_lines = nonempty(OUT)
# 保真 = 条目键完全一致 且 去掉 '---' 后的内容行多重集完全一致
# （归一化会增删节末装饰性 '---'，verify 不要求；仅内容行才是真保真判据）
from collections import Counter
faith_keys = (itemkeys(SRC) == itemkeys(OUT))
faith_content = (Counter(content_lines(SRC)) == Counter(content_lines(OUT)))
print("源非空行:", len(src_lines), " 输出非空行:", len(out_lines),
      " (注: 差值为节末 '---' 归一化, verify 不要求)")
print("源条目键:", len(itemkeys(SRC)), " 输出条目键:", len(itemkeys(OUT)), " 一致:", faith_keys)
print("内容行(去 ---) 多重集一致:", faith_content)
moved = [(it['key'], it['cur'], proposed[it['key']]) for it in items if proposed[it['key']] != it['cur']]
print("移动条目数:", len(moved))
for k, c, t in moved[:60]:
    print("   %s : %s -> %s" % (k, c, t))
if len(moved) > 60: print("   ... 共 %d 条" % len(moved))

if not faith_keys or not faith_content:
    print("!! 保真校验失败（条目键或内容行多重集不一致，疑似内容丢失）—— 未写回，请排查解析 bug。")
elif APPLY:
    bak = SRC + ".bak_restruct_%s" % chkey
    shutil.copy2(SRC, bak)
    open(SRC, 'w', encoding='utf-8').write(result)
    print("已写回 %s (备份 %s)" % (SRC, bak))
else:
    print("未写回；输出在", OUT)
