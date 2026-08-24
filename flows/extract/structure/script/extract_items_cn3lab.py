"""extract_items_cn3lab.py — CN 三级「标签前缀」编号项抽取（ORDINAL_CN3LAB，type 10）。

规则5（config_setting）增量扩展：孙文祥《遍历论》（第2版）等中文三级标签前缀书，
条目形如 `定理1.1.1` / `定义2.3.4` / `例2.1.6`（三段 C.S.N，标签紧贴编号前），
且**每类标签各自独立计数、每节重置**——`定义1.1.1` 与 `定理1.1.1` 并存于同一节
（全书实测 108 处跨标签同号冲突）。既有抽取器均不覆盖：

  * extract_items（type 3，CN 三级裸键 `C.S-N`）假定定理族共享一条节内计数器，
    本书的并行计数器在其键空间内必然撞键（定义1.1.1 / 定理1.1.1 → 同键 `1.1-1`）；
    且其「无标签裸号」通路会把三级小节标题（`2.3.1 Birkhoff遍历定理的陈述`——
    数字在前、标题含类型词）误收为条目并借标题子串误判 label。
  * extract_items_en3（type 9）键形同构（`评注1.1.1`），但其标签词表为英文、
    且要求编号后随句点/括注（Lasota 体例），本书条目头是 `定理1.1.1设X是…`
    （无句点直陈），句点守卫会整条拒真。

本抽取器与 extract_items_cn_single 同型：按 BookConfig.ordinal 各组 name
（经 _canon_label 规范化）取标签词表，只收「块首 标签+C.S.N」标题形态：

  * 块首锚定：全书实测 216 处块首命中皆为真条头，144 处块中命中皆为交叉引用
    （由定理X.X.X / 参见例X.X.X / 定理X.X.X说明…），锚定即完备。
  * 键形 `定理1.1.1`（规范中文标签 + 点分三段），与 keys_in_md 的
    ORDINAL_CN3LAB 分支（复用 ENTRY_RE_EN3_C，COMBINED_LABEL_KINDS 含中文）
    输出的 md 侧键 1:1 对齐；label 字段供 group_for_label 分组。
  * 守卫：编号后随 `的/说明/可知/知/中/见/即`（引用/证明头，如 `定理4.2.1的证明`）
    或 `）`（括注引用残块）→ 拒；`N≥10 且紧贴字母数字`（OCR 粘连，如
    `例1.1.12x={A⊂X}` 实为例1.1.1 + 幂 `2^X`）→ 拆末位回正文。
"""
import os
import re
import sys
from pathlib import Path

for _c in [Path(__file__).resolve(), *Path(__file__).resolve().parents]:
    if (_c / "SKILL.md").exists():
        _ROOT = str(_c)
        break
else:
    _ROOT = str(Path(__file__).resolve().parents[4])
for _p in (_ROOT, os.path.join(_ROOT, "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)
import lib.boot as _boot
_boot.setup()

from page_json import PageJson
from verify_config import _canon_label
from item_dedup import dedup_items

# 从 ordinal 组收集要抽取的标签词（规范化后），排除练习族与图族（与
# extract_items_cn_single._labels_from_groups 同型）。
_SKIP_LABELS = {"练习", "习题", "图", "Figure", "Fig", "Table", "表"}


def _labels_from_groups(groups):
    labels, seen = [], set()
    for g in groups or []:
        for nm in g.name or []:
            c = _canon_label(nm)
            if not c or c in _SKIP_LABELS or c in seen:
                continue
            seen.add(c)
            labels.append(c)
    # 长标签优先，避免「例」抢在「例题」前匹配（本书无例题，防御性保留）
    labels.sort(key=lambda x: -len(x))
    return labels


# 块首装饰字符（OCR 页眉残留 / 项目符号），不剥离会被块首判定整条漏抽
_DECOR = "*·•→'”\"“\u3000 \t"
# 编号后随「引用/证明头」标志：真条头后是陈述（设/若/对/令/则/…或公式），
# 绝不会以下列字样开头（实测：定理4.2.1的证明 / 定理1.1.5说明 / 定理2.2.2中的 / 定义7.2.1））
_REF_AFTER = re.compile(r"^(的|说明|可知|知|中|见|即|[)）])")
# OCR 粘连拆分：N≥10 且紧贴字母/数字（例1.1.12x → 例1.1.1 + "2x=…"）
_GLUE_NEXT = re.compile(r"[A-Za-z0-9]")


def extract_items_cn3lab(extract_dir, chapter, start, end, groups=None):
    """抽取一章的 CN 三级标签前缀条目，返回 [{key,label,page,text}]。

    `chapter` 过滤首段章号；键形 `定理1.1.1`（无空格点分三段）。
    """
    labels = _labels_from_groups(groups)
    if not labels:
        # 无组标签时回退到本书通用主类标签（不含练习/图族）
        labels = ["定理", "定义", "引理", "推论", "命题", "性质", "例"]
    lab_alt = "|".join(re.escape(x) for x in labels)
    head_re = re.compile(
        r"(" + lab_alt + r")\s*"
        r"(\d{1,2})[\.．](\d{1,2})[\.．](\d{1,2})")

    items = []
    for p in range(int(start), int(end) + 1):
        fp = os.path.join(extract_dir, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        data = PageJson.load(fp).data
        for t in data.get("text", []) or []:
            txt = (t.get("text", "") if isinstance(t, dict) else str(t)).strip()
            if not txt:
                continue
            m = head_re.match(txt.lstrip(_DECOR))
            if not m:
                continue
            # 块首锚定后仍要求命中点位于剥离装饰后的起点（head_re.match 已保证）
            label_raw, cs, sn, nn = m.group(1), m.group(2), m.group(3), m.group(4)
            c, s, n = int(cs), int(sn), int(nn)
            if c != chapter:
                continue
            if s > 20 or n > 60:
                continue
            rest = txt.lstrip(_DECOR)[m.end():]
            # OCR 粘连：N≥10 且紧贴字母/数字 → 末位实为正文起点（例1.1.12x → n=1）
            if n >= 10 and rest and _GLUE_NEXT.match(rest[0]):
                n = int(str(n)[0])
                rest = str(nn)[1:] + rest
            # 引用/证明头/括注残块守卫
            if rest and _REF_AFTER.match(rest):
                continue
            label = _canon_label(label_raw) or label_raw
            snippet = txt[max(0, m.start() - 5):m.end() + 90].replace("\n", " ")
            items.append({"key": f"{label}{c}.{s}.{n}", "label": label,
                          "page": p, "text": snippet})
    out = dedup_items(items)
    return out


if __name__ == "__main__":
    import argparse
    import io
    import sys
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description="Extract CN three-level label-first items.")
    ap.add_argument("pos", nargs=4, help="<ch> <start> <end> <extract_dir>")
    ns = ap.parse_args()
    ch, start, end, ext = int(ns.pos[0]), int(ns.pos[1]), int(ns.pos[2]), ns.pos[3]
    items = extract_items_cn3lab(ext, ch, start, end)
    print(f"=== Ch{ch} CN3LAB ITEMS ({len(items)}) ===")
    for it in items:
        print(f"{it['key']:16s} p{it['page']:3d}  {it['text'][:80]}")
