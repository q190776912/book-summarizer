"""check_structure_completeness.py — 源侧重完整性校验 + 回填（校验层 verify/script 公用能力，由 extract/structure 步骤在写书前调用）

目的
----
`build_structure` 产出 `ch<N>_structure.json`（契约，SSOT）。但抽取器（`extract_items` 等）
的源侧捡漏只覆盖三级书且诊断被丢弃（见 `flows/extract/structure/script/build_structure.py`
对 `recover_missing_items` 返回的 `warnings/blocking` 的静默丢弃），非三级书在 structure 阶段
**没有任何源侧查漏**，structure.json 会安静地缺章节/缺定义定理例。

本脚本在「写书之前」把**公共校验子流程的源侧能力**接到 structure 步骤：
  * 章节完整性 -> 复用公共子流程 `verify/layers/section_continuity`（语义名 section-continuity，
    `check_d_layer`）的 raw 重扫能力（直接扫 `page_*.json`，独立于 extract_items）。
  * 条目完整性 -> 本脚本的「标题锚定」源侧扫描（覆盖全方案 three_level/two_level/en/fraleigh
    /gm/roman、全类型 定义/定理/引理/推论/命题/例/练习），作为对抽取器的**独立交叉校验**
    （抽取器是行内扫描，本扫描是块首锚定，二者互补，抓出被漏检的标题行条目）。
  * 比对书中真值集 vs `structure.json` 契约 -> 得到「遗漏章节 / 遗漏定义定理例」清单。
  * 混合回填（用户 2026-08-12 选定）：
      - 可读遗漏项（编号/标签/页码/标题均能从 OCR 干净取出）-> 脚本直接插回 structure.json；
      - 乱码 / 标题被吞等无法干净还原的项 -> 写入 `needs_agent` 报告，交 agent 凭知识/读图回填
        （沿用 `config/manual_overrides_chN` + `（OCR无法识别）` 既定机制，见 verify/missing_label_policy.md）。

用法
----
    python check_structure_completeness.py <extract_dir> [ch ...] [--backfill] [--report-dir DIR]
    # 不传 <ch> 即扫全部章；--backfill 才写回 structure.json，否则只产出报告（dry-run）。
    # 默认报告写到 <extract_dir>/completeness_reports/。

注意：本脚本只消费 raw `page_*.json` + `structure.json` + 配置，**不依赖已写的 .md**，
因此可在写书前独立运行，把查漏从「写完 MD 才发现」提前到「抽完即查、源侧兜底」。
"""
import os
import sys
import re
import json
import tempfile
from pathlib import Path

# ---- boot（与技能内其他脚本一致：定位 SKILL.md 根 + 注入 lib 与 **/script）----
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
from section_continuity import check_d_layer  # 公共子流程：section-continuity（D 层）源侧重扫
from verify_config import (
    BookConfig, ConfigLoader, ORDINAL_THREE_LEVEL, ORDINAL_TWO_LEVEL,
    ORDINAL_EN, ORDINAL_FRALEIGH, ORDINAL_GM, ORDINAL_ROMAN,
)

# === 源侧条目扫描：标题锚定，覆盖全方案 / 全类型 ============================
OCR_DIGIT = {'O': 0, 'o': 0, 'Q': 0, 'D': 0, '0': 0,
             'I': 1, 'l': 1, 'i': 1, '1': 1,
             'Z': 2, 'z': 2, '2': 2,
             'A': 4, 'a': 4, '4': 4,
             'S': 5, 's': 5, '5': 5,
             'G': 6, 'g': 6, '6': 6,
             'T': 7, 't': 7, '7': 7,
             'B': 8, 'b': 8, '8': 8,
             'g': 9, '9': 9}

CN_LABELS = ['定义', '定理', '引理', '推论', '命题', '例', '练习', '习题', '评注', '注', '公理', '准则']
EN_LABELS = ['Definition', 'Theorem', 'Lemma', 'Corollary', 'Proposition',
             'Example', 'Exercise', 'Remark', 'Axiom', 'Assertion', 'Conjecture',
             'Algorithm', 'Assumption']

# 与 build_structure._LABEL_TO_TYPE 保持一致（SSOT）：决定回填节点的 type 字段。
LABEL_TO_TYPE = {
    '定义': 'definition', 'Definition': 'definition',
    '定理': 'theorem', 'Theorem': 'theorem',
    '引理': 'lemma', 'Lemma': 'lemma',
    '推论': 'corollary', 'Corollary': 'corollary',
    '命题': 'proposition', 'Proposition': 'proposition',
    '例': 'example', 'Example': 'example',
    '练习': 'exercise', 'Exercise': 'exercise', '习题': 'exercise',
    '评注': 'remark', 'Remark': 'remark', '注': 'remark',
    '断言': 'proposition', 'Assertion': 'proposition',
    '猜想': 'uncat', 'Conjecture': 'uncat',
    '算法': 'uncat', 'Algorithm': 'uncat',
    '假设': 'uncat', 'Assumption': 'uncat',
    '公理': 'uncat', 'Axiom': 'uncat', '准则': 'uncat',
    'uncat': 'uncat',
}

SEP = r'[.\-·，．]'
_CH = r'([0-9A-Za-z]+)'   # OCR 容错的「数字串」捕获（支持多位数章节号，如 10 / 11）
_S = r'([0-9A-Za-z]+)'
# 块首锚定的「标签 + 编号」候选正则（独立于抽取器的行内扫描）。
# 标签后加负向预查 (?![A-Za-z一-龥])，避免把章节标题（"Examples"/"Exercises"）或
# 语篇词（"例如"）误当成条目标签——它们是纯噪声，必须排除。
_NA = r'(?![A-Za-z一-龥])'
_LBL_CN = r'(定义|定理|引理|推论|命题|例|练习|习题|评注|注|公理|准则)'
_LBL_EN = (r'(Definition|Theorem|Lemma|Corollary|Proposition|Example|Exercise|'
           r'Remark|Axiom|Assertion|Conjecture|Algorithm|Assumption)')

# 八种方案（标签前置 / 数字前置 × 三级 / 两级 × 中 / 英）。
# 数字前置模式的标签为「可选」：有标签才视为可信条目；无标签的三级匹配标 reference
# 交人工复核，无标签的两级匹配（大概率是章节号，如 "10.2"）直接丢弃，避免把章节当条目录入。
# 顺序：英文在前，中文在后——英文数字前置模式能捕获尾部标签（"3.5-1 Example"），
# 必须优先于中文三级数字前置（否则会把带尾标签的英文项误判为无标签）。
_PATTERNS = [
    (re.compile(r'^\s*' + _LBL_EN + r'\b' + _NA + r'\s*' + _CH + SEP + _S + SEP + _S), 'en3_lf'),
    (re.compile(r'^\s*' + _CH + SEP + _S + SEP + _S + r'(?:\s*' + _LBL_EN + r'\b' + _NA + r')?'), 'en3_nf'),
    (re.compile(r'^\s*' + _LBL_EN + r'\b' + _NA + r'\s*' + _CH + SEP + _S), 'en2_lf'),
    (re.compile(r'^\s*' + _CH + SEP + _S + r'(?:\s*' + _LBL_EN + r'\b' + _NA + r')?'), 'en2_nf'),
    (re.compile(r'^\s*' + _LBL_CN + r'\s*' + _CH + SEP + _S + SEP + _S), 'cn3_lf'),
    (re.compile(r'^\s*' + _CH + SEP + _S + SEP + _S), 'cn3_nf'),
    (re.compile(r'^\s*' + _LBL_CN + r'\s*' + _CH + SEP + _S), 'cn2_lf'),
    (re.compile(r'^\s*' + _CH + SEP + _S), 'cn2_nf'),
]

# 交叉引用启发式：块内匹配键之后若出现这些「强引用」标记，说明是「提及/引用」而非
# 「定义」，不自动回填（避免插出幽灵项），标为 reference 交 agent/人工复核。
# 注意：只用强标记（see / in the next / cf. / refer to / the following …），
# 不用 of/by/from/as 等高频日常词，否则会把真定义（如 "series of"）误判为引用。
_REF_RE = re.compile(
    r'\b(see|in the next|we refer|refer to|cf\.?|namely|i\.e\.|e\.g\.|'
    r'the above|the following|as shown|as mentioned|quoted in|shown in)\b',
    re.I)


def _ocr_int(tok):
    """把 OCR 容错数字串规范化成 int（字母按 OCR_DIGIT 映射：A→4, B→8, ...）。"""
    s = ''.join(str(OCR_DIGIT.get(c, c)) for c in tok)
    return int(s) if s.isdigit() else None


def _split(scheme, groups):
    """按方案拆解正则分组 -> (label_or_None, [num_tokens])。"""
    if scheme == 'cn3_lf':
        return groups[0], list(groups[1:4])
    if scheme == 'cn3_nf':
        return None, list(groups[0:3])
    if scheme == 'cn2_lf':
        return groups[0], list(groups[1:3])
    if scheme == 'cn2_nf':
        return None, list(groups[0:2])
    if scheme == 'en3_lf':
        return groups[0], list(groups[1:4])
    if scheme == 'en3_nf':
        return (groups[3] if groups[3] is not None else None), list(groups[0:3])
    if scheme == 'en2_lf':
        return groups[0], list(groups[1:3])
    if scheme == 'en2_nf':
        return (groups[2] if groups[2] is not None else None), list(groups[0:2])
    return None, []


def _is_three(scheme):
    return scheme in ('cn3_lf', 'cn3_nf', 'en3_lf', 'en3_nf')


def scan_raw_items(ext, ch, start, end):
    """标题锚定源侧扫描：返回书中真值条目候选列表。
    每项: {key, label, page, snippet, scheme, canon, has_label}
    key 与 build_structure 产出的 structure.json 契约格式一致
    （三级 = "C.S-N"；两级中文 = "标签C.S"；两级英文 = "标签 C.S"），
    以便回填后能被 write-source / verify 原样消费。
    """
    out = []
    for p in range(start, end + 1):
        fp = os.path.join(ext, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        try:
            data = page_json.PageJson.load(fp).data
        except Exception:
            continue
        for blk in data.get("text", []):
            txt = blk.get("text", "").strip()
            if not txt:
                continue
            for rgx, scheme in _PATTERNS:
                m = rgx.match(txt)
                if not m:
                    continue
                label, raw_nums = _split(scheme, m.groups())
                nums = [_ocr_int(x) for x in raw_nums]
                if any(n is None for n in nums):
                    continue
                first = nums[0]
                if first != ch:
                    continue
                if len(nums) < 2:
                    continue
                if any(n > 200 for n in nums[1:]):
                    continue
                has_label = label is not None
                # 两级数字前置且无标签 -> 视为章节号噪声，丢弃
                if scheme in ('cn2_nf', 'en2_nf') and not has_label:
                    break
                if _is_three(scheme):
                    if len(nums) < 3:
                        continue
                    key = f"{nums[0]}.{nums[1]}-{nums[2]}"
                    canon = (nums[0], nums[1], nums[2])
                else:
                    if scheme.startswith('en'):
                        key = (label + " " if label else "") + f"{nums[0]}.{nums[1]}"
                    else:
                        key = (label or "") + f"{nums[0]}.{nums[1]}"
                    canon = (nums[0], nums[1])
                out.append({
                    "key": key, "label": label or "uncat", "page": p,
                    "snippet": txt[:120].replace("\n", " "), "scheme": scheme,
                    "canon": canon, "has_label": has_label,
                })
                break
    return out


def _find_section_page(ext, ch, sec_tuple):
    """为缺失章节找一个真实页码（扫 raw 的 C.S / C.S 标题行）。"""
    target = ".".join(str(x) for x in sec_tuple)
    head_a = re.compile(r'^(?:§|8)\s*' + re.escape(target) + r'\b')
    head_b = re.compile(r'^\s*' + re.escape(target) + r'\s+\S')
    for p in range(0, 9999):
        fp = os.path.join(ext, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        try:
            data = page_json.PageJson.load(fp).data
        except Exception:
            continue
        for blk in data.get("text", []):
            t = blk.get("text", "").strip()
            if head_a.match(t) or head_b.match(t):
                return p
    return None


# === 契约（structure.json）读取 =============================================
_LABEL_RE = re.compile(r'^(定义|定理|引理|推论|命题|例|练习|习题|评注|注'
                       r'|Definition|Theorem|Lemma|Corollary|Proposition|Example|Exercise|Remark|Axiom)')


def _canon_key(primary_type, key):
    """把契约/源侧 key 规范化为可比较的 int 元组（按方案）。"""
    if primary_type == ORDINAL_THREE_LEVEL:
        m = re.match(r'^(\d+)[.\-·，．]+(\d+)[.\-·，．]+(\d+)$', key)
        return tuple(int(x) for x in m.groups()) if m else None
    if primary_type in (ORDINAL_TWO_LEVEL, ORDINAL_FRALEIGH):
        s = _LABEL_RE.sub('', key).strip()
        m = re.match(r'^(\d+)[.\-·，．]+(\d+)$', s)
        return (int(m.group(1)), int(m.group(2))) if m else None
    s = _LABEL_RE.sub('', key).strip()
    nums = re.findall(r'\d+', s)
    return tuple(int(x) for x in nums) if nums else None


def load_contract(path):
    """读 structure.json，返回 (tree, items: {canon: node}, sections: set(str 'C.S'))。"""
    tree = json.load(open(path, encoding="utf-8"))
    items = {}
    sections = set()

    def walk(n):
        t = n.get("type")
        if t == "section":
            sections.add(n.get("key"))
        if t in ("chapter", "section"):
            for k in n.get("sub_sec", []):
                walk(k)
            return
        if t == "exercise":
            return
        canon = _canon_key(_PRIMARY, n.get("key", ""))
        if canon is not None:
            items[canon] = n
    walk(tree)
    return tree, items, sections


# === 树操作（回填） =========================================================
def _fix_pages(node):
    kids = node.get("sub_sec")
    if not kids:
        return node["page_end"]
    cs = [k["page_start"] for k in kids]
    ce = [_fix_pages(k) for k in kids]
    node["page_start"] = min(cs)
    node["page_end"] = max(ce)
    return node["page_end"]


def _section_node(tree, sec_key):
    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "section" and n.get("key") == sec_key:
                return n
            for k in n.get("sub_sec", []):
                r = walk(k)
                if r:
                    return r
        return None
    return walk(tree)


def _iter_sections(tree):
    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "section":
                yield n
            for k in n.get("sub_sec", []):
                yield from walk(k)
    yield from walk(tree)


# ---- 与 build_structure 契约一致的 name / type 构造（回填节点须原样可被消费）----
_STRIP_LABEL = re.compile(
    r'^(定义|定理|引理|推论|命题|例|评注|注|算法|假设|断言|猜想|'
    r'Definition|Theorem|Lemma|Corollary|Proposition|Example|Remark|'
    r'Assertion|Conjecture|Algorithm|Assumption)\b\s*', re.IGNORECASE)
_STRIP_LABEL_CN = re.compile(r'^(定义|定理|引理|推论|命题|例|评注|注)')


def _type_of(label):
    return LABEL_TO_TYPE.get((label or "").strip(), "uncat")


def _clean_title(text, key):
    """从条目 OCR 文本抽取印刷标题（去掉 key / label 前缀，截断）——镜像 build_structure。"""
    if not text:
        return ""
    t = text.replace(key, "", 1).strip()
    t = _STRIP_LABEL.sub("", t)
    t = _STRIP_LABEL_CN.sub("", t)
    t = t.strip(" .:：．，,()（）\u00a0")
    if not t:
        return ""
    if len(t) > 90:
        cut = t[:90]
        sp = cut.rfind(" ")
        if sp > 40:
            cut = cut[:sp]
        t = cut.rstrip(" .:：．，,") + "\u2026"
    return t


def _node(key, ntype, name, page):
    return {"key": key, "type": ntype, "name": name,
            "page_start": page, "page_end": page}


def insert_item(tree, key, label, page, canon, snippet=""):
    """把遗漏条目插回 structure.json 树。three_level 优先归到 C.S 节；否则按页码归最近节。
    节点字段（key/type/name/page）与 build_structure 完全一致，回填后 write-source / verify 可直接消费。
    """
    itype = _type_of(label)
    title = _clean_title(snippet, key)
    name = (f"{key} {title}".strip()) if title else key
    node = _node(key, itype, name, page)
    sec_key = None
    if _PRIMARY == ORDINAL_THREE_LEVEL and len(canon) >= 2:
        sec_key = f"{canon[0]}.{canon[1]}"
    sn = _section_node(tree, sec_key) if sec_key else None
    if sn is None:
        secs = list(_iter_sections(tree))
        cand = None
        for s in secs:
            if s["page_start"] <= page:
                cand = s
        if cand is not None:
            sn = cand
    if sn is not None:
        sn.setdefault("sub_sec", []).append(node)
        _fix_pages(tree)
        return True, sec_key or "(page-proximity)"
    tree.setdefault("sub_sec", []).append(node)
    _fix_pages(tree)
    return True, "(chapter-bucket)"


def insert_section(tree, sec_key, page):
    if _section_node(tree, sec_key) is not None:
        return False
    node = {"key": sec_key, "type": "section", "name": sec_key,
            "page_start": page or 0, "page_end": page or 0, "sub_sec": []}
    secs = list(_iter_sections(tree))
    inserted = False
    for s in secs:
        if (page or 0) < s["page_start"]:
            idx = tree["sub_sec"].index(s) if s in tree["sub_sec"] else len(tree["sub_sec"])
            tree["sub_sec"].insert(idx, node)
            inserted = True
            break
    if not inserted:
        tree.setdefault("sub_sec", []).append(node)
    _fix_pages(tree)
    return True


# === 主流程 ================================================================
_PRIMARY = ORDINAL_THREE_LEVEL


def raw_present_sections(ch, start, end, ext, cfg):
    """复用公共子流程 section-continuity 的源侧重扫：喂空 md -> 返回书中真值章节集。"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write("")
        md_path = f.name
    try:
        d = check_d_layer(ch, start, end, md_path, ext, cfg=cfg)
    finally:
        try:
            os.unlink(md_path)
        except OSError:
            pass
    rel = d.get("missing_sections", []) + d.get("continuity_sections", [])
    full = set()
    for r in rel:
        if not r:
            continue
        parts = r.split(".")
        full.add(".".join([str(ch)] + parts))
    return full


def check_chapter(ext, ch, start, end, cfg, backfill, report_dir):
    global _PRIMARY
    _PRIMARY = cfg.primary_type
    sp = os.path.join(ext, f"ch{ch}_structure.json")
    if not os.path.exists(sp):
        return None
    tree, contract_items, contract_sections = load_contract(sp)

    raw_secs = raw_present_sections(ch, start, end, ext, cfg)
    missing_sections = sorted(s for s in raw_secs
                              if s not in contract_sections and len(s.split(".")) == 2)

    raw_items = scan_raw_items(ext, ch, start, end)
    missing_items = []
    seen_canon = set(contract_items.keys())
    for it in raw_items:
        c = it["canon"]
        if c is None or c in seen_canon:
            continue
        seen_canon.add(c)
        garbled = not (len(c) >= 1 and all(isinstance(x, int) for x in c)
                       and (len(c) < 2 or c[1] <= 60) and (len(c) < 3 or c[2] <= 200))
        if garbled:
            status = "needs_agent"
        elif not it.get("has_label"):
            # 数字前置三级但无显式标签：可能是真实漏项，也可能是前向引用；
            # 不自动回填，标 reference 交人工/agent 复核。
            status = "reference"
        elif _REF_RE.search(it["snippet"]):
            status = "reference"
        else:
            status = "readable"
        missing_items.append({
            "key": it["key"], "label": it["label"], "page": it["page"],
            "snippet": it["snippet"], "canon": list(c),
            "has_label": it.get("has_label", False), "status": status,
        })

    backfilled_items = []
    backfilled_sections = []
    if backfill:
        for ms in missing_sections:
            parts = [int(x) for x in ms.split(".")]
            pg = _find_section_page(ext, ch, parts)
            if insert_section(tree, ms, pg):
                backfilled_sections.append({"sec": ms, "page": pg})
        for mi in missing_items:
            if mi["status"] != "readable":
                continue
            c = tuple(mi["canon"])
            ok, where = insert_item(tree, mi["key"], mi["label"], mi["page"], c, mi["snippet"])
            if ok:
                backfilled_items.append({"key": mi["key"], "where": where, "page": mi["page"]})
        if backfilled_items or backfilled_sections:
            with open(sp, "w", encoding="utf-8") as f:
                json.dump(tree, f, ensure_ascii=False, indent=2)

    report = {
        "chapter": ch,
        "contract_items": len(contract_items),
        "contract_sections": sorted(contract_sections),
        "raw_items_scanned": len(raw_items),
        "raw_sections_present": sorted(raw_secs),
        "missing_sections": missing_sections,
        "missing_items": missing_items,
        "backfilled_items": backfilled_items,
        "backfilled_sections": backfilled_sections,
    }
    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(report_dir, f"ch{ch}_completeness_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    n_read = sum(1 for m in missing_items if m["status"] == "readable")
    n_agent = sum(1 for m in missing_items if m["status"] == "needs_agent")
    n_ref = sum(1 for m in missing_items if m["status"] == "reference")
    print(f"ch{ch}: contract(items={len(contract_items)}, sections={len(contract_sections)}) | "
          f"raw(items={len(raw_items)}, sections={len(raw_secs)}) | "
          f"missing(items={len(missing_items)}[{n_read}r/{n_ref}ref/{n_agent}a], sections={len(missing_sections)})"
          + (f" | BACKFILLED(items={len(backfilled_items)}, sections={len(backfilled_sections)})" if backfill else ""))
    return report


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = [a for a in sys.argv[1:] if a.startswith("--")]
    backfill = "--backfill" in flags
    report_dir = None
    for fl in flags:
        if fl.startswith("--report-dir"):
            report_dir = fl.split("=", 1)[1]
    if not args:
        print(__doc__)
        return 2
    ext = args[0]
    want = [int(x) for x in args[1:]]
    if report_dir is None:
        report_dir = os.path.join(ext, "completeness_reports")

    cfg_path = os.path.join(ext, "verify_config.json")
    try:
        loader = ConfigLoader(ext, os.path.dirname(ext.rstrip("/")) or ext)
        loader.require_complete()
        book = loader.book
    except Exception:
        if not os.path.exists(cfg_path):
            print("verify_config.json not found")
            return 2
        with open(cfg_path, encoding="utf-8-sig") as fh:
            book = BookConfig.from_dict(json.load(fh))

    cm_path = os.path.join(ext, "chapter_map.json")
    cm = json.load(open(cm_path, encoding="utf-8")) if os.path.exists(cm_path) else {"chapters": []}
    rng = {}
    for c in cm.get("chapters", []):
        n = c.get("chapter", c.get("num"))
        rng[n] = (c.get("start"), c.get("end"))

    for ch in (want or sorted(rng)):
        if ch not in rng:
            print(f"ch{ch} SKIP (not in chapter_map)")
            continue
        s, e = rng[ch]
        check_chapter(ext, ch, s, e, book, backfill, report_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
