# -*- coding: utf-8 -*-
"""extract_items_cn_single.py — CN 单级编号项抽取（ORDINAL_SINGLE + language=cn）。

规则5（config_setting）增量扩展：李庆扬《数值分析》第5版等中文单级编号书，
条目为「标签+单一数字」且无章/节分量（定理1 / 定义3 / 例12 / 算法2 / 性质4），
既有抽取器均不覆盖：
  * extract_items(_two_level/_three_level) 只认 N.S-N / N.S.K 多级号；
  * extract_items_en(single=True) 的 EN_LABELS 无中文标签词。
本抽取器按 BookConfig.ordinal 各组的 name（经 _canon_label 规范化）取标签词表，
只收「块首 标签+数字」标题形态（与 extract_items_en 的 heading-vs-prose 守卫
同型），块中引用（如「由定理5可知」「利用算法2的结果」）天然被起点锚排除。

key 形态：f"{规范中文标签}{n}"（如 "定理1"），与 keys_in_md 的 ORDINAL_SINGLE
分支（ENTRY_RE_EN_SINGLE_C，COMBINED_LABEL_KINDS 含中文）输出的 md 侧键
1:1 对齐；label 字段携带原始标签供 group_for_label 分组。
"""
import os
import re

from lib.boot import setup

setup()

from page_json import PageJson
from verify_config import _canon_label


def _labels_from_groups(groups):
    """从 ordinal 组收集要抽取的标签词（规范化后），排除练习族与图族。"""
    skip = {"练习", "习题", "图", "Figure", "Fig", "Table", "表"}
    labels = []
    seen = set()
    for g in groups or []:
        for nm in g.name or []:
            c = _canon_label(nm)
            if not c or c in skip or c in seen:
                continue
            seen.add(c)
            labels.append(c)
    # 长标签优先（避免"注"抢在"注记"前匹配）
    labels.sort(key=len, reverse=True)
    return labels


def extract_items_cn_single(extract_dir, start, end, groups=None, manual_overrides=None):
    """从 page_*.json 抽取中文单级编号项（块首「标签+数字」形态）。

    返回 [{'key': '定理1', 'label': '定理', 'page': p, 'text': snippet}, ...]。
    """
    labels = _labels_from_groups(groups)
    if not labels:
        return []
    # 仅拒绝「助词/连词」紧随数字的行首形态（如"定理1的证明""例2和例3"）。
    # 动词/介词开头（对于/给定/在线性方程组中/说明…）可能是真标题陈述句，
    # 不拒绝——行首真引用大多带前导词（由/见/利用/注意），被起点锚排除；
    # 漏网的行首引用由下方「按 key 保留最早页」兜底，不影响契约正确性。
    # 句点不拒：本书排版存在「定义5.若…」（号后带点再接正文）的标题形态，
    # 两级号仍由 (?!\d) 拦截。
    ref_next = '的之中即与和或及时前后都均也是'
    lab_re = re.compile(
        r'^[\s>]*(' + '|'.join(re.escape(l) for l in labels) + r')\s*'
        r'(\d{1,3})(?!\d)(?![' + ref_next + r'])')
    items = []
    for p in range(int(start), int(end) + 1):
        fp = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        data = PageJson.load(fp).data
        for t in data.get("text", []) or []:
            txt = (t.get("text") or "").strip()
            if not txt:
                continue
            m = lab_re.match(txt)
            if not m:
                continue
            label = m.group(1)
            n = int(m.group(2))
            if n <= 0:
                continue
            key = f"{_canon_label(label)}{n}"
            snippet = txt[:100]
            items.append({"key": key, "label": _canon_label(label),
                          "page": p, "text": snippet})
    # 按 key 收敛到最早页出现（真标题在前，行首引用/证明复述在后）。
    # 本书的同号再现均为引用或证明回指（如 p20「定理1 说明…」、
    # 「定理N 的证明」），不存在 Lasota-Mackey 式同号异条排版，
    # 故不做 dedup_items 的跨页异名保留。
    first = {}
    for it in sorted(items, key=lambda x: (x["page"], x["key"])):
        first.setdefault(it["key"], it)
    out = sorted(first.values(), key=lambda x: (x["page"], x["key"]))
    # manual_overrides_ch{N}.json：恢复 OCR 错字/漏识的真实条目
    # （如「个圆寇理5(（格什戈林圆盘定理）」→ 定理5），语义与 extract_items 一致：
    # 已有同 key 条目则原位替换，否则追加，最后按 (page, key) 稳定排序。
    if manual_overrides:
        existing = {it['key']: idx for idx, it in enumerate(out)}
        for mo in manual_overrides:
            entry = {'key': mo['key'], 'page': mo['page'],
                     'label': mo.get('label') or mo['key'].rstrip('0123456789'),
                     'text': mo.get('text') or '', 'agent_recovered': True}
            if mo['key'] in existing:
                out[existing[mo['key']]] = entry
            else:
                out.append(entry)
        out.sort(key=lambda x: (x['page'], x['key']))
    return out


if __name__ == "__main__":
    import sys
    import json
    if len(sys.argv) < 3:
        print(__doc__)
        raise SystemExit(2)
    ext, s, e = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
    rows = extract_items_cn_single(ext, s, e)
    for r in rows:
        print(f"p{r['page']:03d} {r['key']}: {r['text'][:60]}")
    print(f"[total] {len(rows)} items")
