"""check_structure_completeness.py — 源侧重完整性校验 + 回填（校验层 verify/script 公用能力，由 extract/structure 步骤在写书前调用）

目的
----
`build_structure` 产出 `book_structure.json`（书对象契约）。抽取器源侧捡漏覆盖不全，非三级书在 structure 阶段没有源侧查漏，book_structure.json 会安静地缺章节 / 缺定义定理例。

步骤与状态分流的权威叙述（四步流程、readable / reference / needs_agent 分流、完整 + 连续闸门）见 `flows/extract/structure/structure.md` 的「步骤（第 2–4 步）/ 源侧完整性校验与回填」一节；本文件仅承载该脚本的实现与调用方式。本脚本在「写书之前」把 `verify/section_continuity`（D 层）与 `verify/item_numbering_integrity`（B 层）两个公共校验层接到 structure 步骤做兜底，回填后由「完整 + 连续」闸门复核。

用法
----
    python check_structure_completeness.py <extract_dir> [ch ...] [--backfill] [--report-dir DIR]
    # 不传 <ch> 即扫全部章；--backfill 才写回 book_structure.json，否则只产出报告（dry-run）。
    # 默认报告写到 <extract_dir>/completeness_reports/。

注意：本脚本只消费 raw `page_*.json` + `book_structure.json` + 配置，**不依赖已写的 .md**，
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

from data.book_structure.book_structure import BookStructure, StructureNode

import page_json
# 公共校验层（verify/*/script 由 boot 注入 sys.path，可直接裸 import）：
from section_continuity import check_d_layer          # D 层：section-continuity（章节连续性）
from item_numbering_integrity import ItemNumberingIntegrityLayer  # B 层：item-numbering-integrity（条目编号完整性）
from verify.script.base import VerifyContext   # B 层 run() 所需的精简运行时载体
from verify_config import (
    BookConfig, ConfigLoader, ORDINAL_THREE_LEVEL, ORDINAL_TWO_LEVEL,
    ORDINAL_EN, ORDINAL_FRALEIGH, ORDINAL_GM, ORDINAL_ROMAN,
)

# === 源侧条目扫描：标题锚定，覆盖全方案 / 全类型 ============================
# 作为「源条目集」喂给 B 层（ctx.items）并做 set-difference 差集回填；它是独立于
# 抽取器的稳健交叉校验，专门抓抽取器漏检的标题行条目。
OCR_DIGIT = {'O': 0, 'o': 0, 'Q': 0, 'D': 0, '0': 0,
             'I': 1, 'l': 1, 'i': 1, '1': 1,
             'Z': 2, 'z': 2, '2': 2,
             'A': 4, 'a': 4, '4': 4,
             'S': 5, 's': 5, '5': 5,
             'G': 6, 'g': 6, '6': 6,
             'T': 7, 't': 7, '7': 7,
             'B': 8, 'b': 8, '8': 8,
             'g': 9, '9': 9}

# 第 3 步只关心「定义 / 定理 / 引理 / 推论 / 命题 / 例」等重要概念；练习由 EXER 单独处理。
_EXER_LABELS_RAW = {'练习', '习题', 'Exercise'}

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
# 数字前置模式的标签为「可选」：有标签视为可信条目；无标签的三级匹配先作候选，
# 后续 step3 再判——仅当命中 _REF_RE（前向引用提及，如 "see 1.5-3"）才标 reference
# 交人工复核，否则按真实条头计（readable 自动回填）；无标签的两级匹配（大概率是
# 章节号，如 "10.2"）直接丢弃，避免把章节当条目录入。
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
    """标题锚定源侧扫描：返回书中真值条目候选列表（跨校验源集）。
    每项: {key, label, page, snippet, scheme, canon, has_label}
    key 与 build_structure 产出的 book_structure.json 契约格式一致
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


# === 契约（book_structure.json）读取 =============================================
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


def load_contract(tree):
    """从结构树（StructureNode）提取 (tree, items: {canon: node}, sections: set(str 'C.S'))。

    tree 为某章节点（StructureNode）；调用方通过 BookStructure.load 读取单文件并
    用 ``bs.find_chapter(ch)`` 取得。
    """
    items = {}
    sections = set()

    def walk(n):
        t = n.type
        if t == "section":
            sections.add(n.key)
        if t in ("chapter", "section"):
            for k in n.sub_sec:
                walk(k)
            return
        if t == "exercise":
            return
        canon = _canon_key(_PRIMARY, n.key if isinstance(n.key, str) else str(n.key))
        if canon is not None:
            items[canon] = n
    walk(tree)
    return tree, items, sections


# === 树操作（回填，操作 StructureNode 模型，不再裸操作 dict）================
def _fix_pages(node):
    kids = node.sub_sec
    if not kids:
        return node.page_end
    cs = [k.page_start for k in kids]
    ce = [_fix_pages(k) for k in kids]
    node.page_start = min(cs)
    node.page_end = max(ce)
    return node.page_end


def _section_node(tree, sec_key):
    def walk(n):
        if n.type == "section" and str(n.key) == str(sec_key):
            return n
        for k in n.sub_sec:
            r = walk(k)
            if r is not None:
                return r
        return None
    return walk(tree)


def _iter_sections(tree):
    def walk(n):
        if n.type == "section":
            yield n
        for k in n.sub_sec:
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
    return StructureNode(key=key, type=ntype, name=name,
                         page_start=page, page_end=page, sub_sec=[])


def insert_item(tree, key, label, page, canon, snippet=""):
    """把遗漏条目插回结构树（StructureNode）。three_level 优先归到 C.S 节；否则按页码归最近节。
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
            if s.page_start <= page:
                cand = s
        if cand is not None:
            sn = cand
    if sn is not None:
        sn.sub_sec.append(node)
        _fix_pages(tree)
        return True, sec_key or "(page-proximity)"
    tree.sub_sec.append(node)
    _fix_pages(tree)
    return True, "(chapter-bucket)"


def insert_section(tree, sec_key, page):
    if _section_node(tree, sec_key) is not None:
        return False
    node = _node(sec_key, "section", sec_key, page or 0)
    secs = list(_iter_sections(tree))
    inserted = False
    for s in secs:
        if (page or 0) < s.page_start:
            idx = tree.sub_sec.index(s) if s in tree.sub_sec else len(tree.sub_sec)
            tree.sub_sec.insert(idx, node)
            inserted = True
            break
    if not inserted:
        tree.sub_sec.append(node)
    _fix_pages(tree)
    return True


# === 合成 md（book_structure → .md，喂给 verify 层）=========================
def synthetic_section_md(tree):
    """把 book_structure 的 section 节点写成 ``## §C.S`` 标题，供 D 层
    （section_continuity）解析比对（D 层读 md 的 § 标题行，独立于 page_*.json）。"""
    lines = []

    def walk(n):
        if n.type == "section":
            lines.append("## §%s" % n.key)
        if n.type in ("chapter", "section"):
            for k in n.sub_sec:
                walk(k)
    walk(tree)
    return "\n".join(lines) + "\n"


# 类型 -> 规范标签（反向映射 LABEL_TO_TYPE），供合成 md 重建可被 B 层解析的条目头。
_TYPE_TO_LABEL = {
    "definition": "Definition", "theorem": "Theorem", "lemma": "Lemma",
    "corollary": "Corollary", "proposition": "Proposition", "example": "Example",
    "remark": "Remark", "exercise": "Exercise", "uncat": "uncat",
}
# 三级裸键（"C.S-K" / "C.S.K"，无内置标签）——这类键需补一个类型标签，B 层
# num-first 解析才认得出是真实条目（否则尾串无标签 -> 被当 reference 丢弃）。
_BARE_THREE = re.compile(r'^\d+[.\-·，．]\d+[.\-·，．]\d+$')


def synthetic_item_md(tree):
    """把 book_structure 的非练习条目节点写成 ``**...**`` 粗体头，供 B 层
    （item_numbering_integrity）解析其编号分组 / 连续性（B 层读 md 粗体条目头）。

    **关键**：``build_structure`` 产出的 name 经 ``_clean_title`` 已**剥掉类型词**
    （如 ``"1.1-1 Metric space."``，标签留在 ``type`` 字段而非 name）。若直接把 name
    喂给 B 层，B 层 ``_parse_entry`` 对「数字前置 + 无尾标签/描述性尾串」会判定为
    reference 而**丢弃**，导致 B 层对三级书的 book_structure 永远查不出缺号（假绿）。
    故此处按 ``type`` 反推标签，为裸三级键重建 ``**key Label**`` 形式（两级书的 key
    已自带标签，如 ``"Definition 1.1"``，无需补；uncat 裸键 B 层自然丢弃，由
    set-difference 兜底，不影响连续性闸门）。"""
    lines = []

    def walk(n):
        if n.type in ("chapter", "section"):
            for k in n.sub_sec:
                walk(k)
            return
        if n.type == "exercise":
            return
        key = str(n.key)
        label = _TYPE_TO_LABEL.get(n.type, "uncat")
        if _BARE_THREE.match(key) and label != "uncat":
            entry = "%s %s" % (key, label)
        else:
            entry = key        # 两级键自带标签；uncat 裸键 -> B 层丢弃（可接受）
        lines.append("**%s**" % entry)
    walk(tree)
    return "\n".join(lines) + "\n"


# === 第 2 步：section_continuity 校验遗漏章节 ===============================
def step2_sections(ch, start, end, ext, cfg, tree):
    """第 2 步：用 section_continuity（D 层）校验遗漏章节并回填 book_structure。

    喂 book_structure 派生的合成 md → D 层比对「源真值章节集」（直接重扫
    page_*.json，独立于抽取器）与 book_structure 契约，返回遗漏章节：
      * continuity_sections：书内章节序列的内部洞（节序断裂）；
      * missing_sections：落在 book_structure 最后一个已写节之后的整节缺失。
    二者合并即「源有而 book_structure 无」的遗漏章节集合。
    """
    md = synthetic_section_md(tree)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(md)
        md_path = f.name
    try:
        d = check_d_layer(ch, start, end, md_path, ext, cfg=cfg)
    finally:
        try:
            os.unlink(md_path)
        except OSError:
            pass
    # book_structure.json 只建模 chapter → section → 条目（**没有 subsection 容器
    # 节点**），所以 D 层只需比对「章节级（level 2 = C.S）」；level 3（subsection）
    # 在契约里无对应节点，若纳入会把每个 C.S-K 条目误报成「缺失 subsection」。
    # 故只取 levels[2] 的 continuity / missing（level 1 = 章前缀，level 2 = 节）。
    levels = d.get("levels", {}) or {}
    sec = levels.get(2, {}) or {}
    continuity = list(sec.get("continuity", []))
    tail = list(sec.get("missing", []))
    missing = []
    for r in continuity + tail:
        if not r:
            continue
        parts = r.split(".")
        missing.append(".".join([str(ch)] + parts))
    return sorted(set(missing)), {"continuity": continuity, "tail": tail}


# === 第 3 步：item_numbering_integrity 校验遗漏重要概念 ======================
def step3_items(ch, start, end, ext, cfg, tree, contract_items):
    """第 3 步：用 item_numbering_integrity（B 层）校验遗漏定义/定理/例等重要概念并回填。

    做法（避免在写书前依赖「已写 .md」，与 verify 端 B 层解耦）：
      1) 用 scan_raw_items 得到源侧条目集（稳健跨校验，抓抽取器漏检）；
         仅保留「重要概念」（排除练习类），与契约对比做 set-difference → 结构化缺失（驱动回填）。
      2) 把 book_structure 派生出「合成 md」（非练习条目 → ``**key name**`` 粗体头），
         并把源条目集作为 ``ctx.items`` 喂给 B 层，让其分组 / 编号 / ignore 逻辑校验
         book_structure 的条目完整性；B 层输出（blocking / b_gap_warnings /
         b_tail_warnings）作为「编号连续性」诊断一并上报。
    """
    global _PRIMARY
    _PRIMARY = cfg.primary_type

    raw_items = [it for it in scan_raw_items(ext, ch, start, end)
                 if it["label"] not in _EXER_LABELS_RAW]

    # 1) set-difference：源有而契约无 → 结构化缺失（驱动回填）。
    #    按 canon 取「最佳代表」去重：前向引用提及(_REF_RE 命中，如 page45
    #    "Example 1.5-3 in the next section") 绝不能污染去重集合、掩盖同 canon
    #    的真实条头(page49 "1.5-3 Completeness of c")——否则真实漏项被静默吞掉
    #    （旧逻辑用平铺 seen_canon，引用提及先入集即把真实条头 continue 掉）。
    #    真实条头（非引用提及）优先；同类则保留较早页（条头通常先于提及出现）。
    best = {}
    for it in raw_items:
        c = tuple(it["canon"]) if isinstance(it["canon"], list) else it["canon"]
        if c is None:
            continue
        is_ref = bool(_REF_RE.search(it.get("snippet", "")))
        prev = best.get(c)
        if prev is None:
            best[c] = it
            continue
        prev_ref = bool(_REF_RE.search(prev.get("snippet", "")))
        if (not is_ref) and prev_ref:
            best[c] = it
        elif (not is_ref) == (not prev_ref) and it["page"] < prev["page"]:
            best[c] = it

    missing_items = []
    for c, it in best.items():
        if c in contract_items:
            continue
        garbled = not (len(c) >= 1 and all(isinstance(x, int) for x in c)
                       and (len(c) < 2 or c[1] <= 60) and (len(c) < 3 or c[2] <= 200))
        is_ref = bool(_REF_RE.search(it.get("snippet", "")))
        if garbled:
            # OCR 字母↔数字无法干净还原 → 交 agent 凭读图/知识回填。
            status = "needs_agent"
        elif is_ref:
            # 前向引用提及（see/refer to/cf./in the next…），非定义条头，
            # 不自动回填，交人工/agent 复核。
            status = "reference"
        else:
            # 真实条头（含三级数字前置无显式标签项，Kreyszig 等书此类即真实条目）
            # → 可读、自动回填，不再误判为 reference 漏网。
            status = "readable"
        missing_items.append({
            "key": it["key"], "label": it["label"], "page": it["page"],
            "snippet": it["snippet"], "canon": list(c),
            "has_label": it.get("has_label", False), "status": status,
        })

    # 2) item_numbering_integrity（B 层）：喂合成 md + ctx.items=源条目集
    bmeta = _run_b_layer(ch, start, end, ext, cfg, tree, raw_items)

    return missing_items, bmeta


def _run_b_layer(ch, start, end, ext, cfg, tree, source_items):
    """把 book_structure 派生 md + 源条目集喂给 item_numbering_integrity（B 层），
    返回其 metadata：{blocking, b_gap_warnings, b_tail_warnings, ignored_hit}。"""
    md = synthetic_item_md(tree)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(md)
        md_path = f.name
    try:
        ctx = VerifyContext(ch=ch, start=start, end=end, md_file=md_path,
                            ext_dir=ext, config=cfg)
        ctx.items = source_items            # 源条目集（供尾部校验：源 max vs md max）
        # 修复接线：正常 verify 流程由 data_provider.keys_in_md 填充
        # ctx.entry_keys / ctx.all_keys（按章过滤）；之前漏调导致 B 层看到空
        # all_keys → 全部源条目被判缺失（假阳性 blocking）。
        from data_provider import keys_in_md, _first_num
        _ek, _ak = keys_in_md(ctx.md_file, groups=cfg.ordinal)
        ctx.entry_keys = {k for k in _ek if _first_num(k) == ctx.ch}
        ctx.all_keys = {k for k in _ak if _first_num(k) == ctx.ch}
        ctx.extraction_blocking = []        # structure 阶段无 EXTRACT 层；源侧缺失由 set-difference 直接算
        ctx.ignored_hit = []
        res = ItemNumberingIntegrityLayer().run(ctx)
    finally:
        try:
            os.unlink(md_path)
        except OSError:
            pass
    return res.metadata


# === 第 4 步：完整性与连续性闸门 =============================================
def step4_gate(ext, ch, start, end, cfg, bs, ch_node_after, bmeta_before):
    """第 4 步：回填后重跑第 2 / 第 3 步，断言遗漏章节 / 可读遗漏项 / B 层 blocking 全部归零，
    保证 book_structure 既完整（无遗漏）又连续（章节序列 / 条目编号无洞）。"""
    tree2, items2, _secs2 = load_contract(ch_node_after)
    miss_sec2, _ = step2_sections(ch, start, end, ext, cfg, tree2)
    miss_it2, bmeta2 = step3_items(ch, start, end, ext, cfg, tree2, items2)

    readable_left = [m for m in miss_it2 if m["status"] == "readable"]
    b_blocking = bmeta2.get("blocking", [])
    sec_left = list(miss_sec2)
    passed = (not sec_left) and (not readable_left) and (not b_blocking)
    return {
        "passed": passed,
        "residual_sections": sec_left,
        "residual_readable_items": [m["key"] for m in readable_left],
        "residual_b_blocking": b_blocking,
    }


# === 主流程 ================================================================
_PRIMARY = ORDINAL_THREE_LEVEL


def check_chapter(ext, ch, start, end, cfg, backfill, report_dir):
    global _PRIMARY
    _PRIMARY = cfg.primary_type
    # 单文件书对象：经 BookStructure 读取，定位指定章节点。
    bs = BookStructure.load(ext)
    if bs is None:
        return None
    ch_node = bs.find_chapter(ch)
    if ch_node is None:
        return None
    tree, contract_items, contract_sections = load_contract(ch_node)

    # ---- 第 2 步：section_continuity 校验遗漏章节 ----
    missing_sections, sec_detail = step2_sections(ch, start, end, ext, cfg, tree)

    # ---- 第 3 步：item_numbering_integrity 校验遗漏重要概念 ----
    missing_items, bmeta = step3_items(ch, start, end, ext, cfg, tree, contract_items)

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
            # 回填后整体写回单文件书对象：用 ch_node 替换本书根下同 key 章节，再 save。
            bs.root.replace_chapter(tree)
            bs.save(ext)

    # ---- 第 4 步：完整性与连续性闸门（回填后重跑断言）----
    # 回填已写入 bs（内存同对象），用最新章节点重算契约再校验。
    ch_node_after = bs.find_chapter(ch)
    gate = step4_gate(ext, ch, start, end, cfg, bs, ch_node_after, bmeta)

    report = {
        "chapter": ch,
        "contract_items": len(contract_items),
        "contract_sections": sorted(contract_sections),
        "raw_items_scanned": _count_raw_items(ext, ch, start, end),
        "raw_sections_present": sorted(set(sec_detail.get("continuity", []) + sec_detail.get("tail", []))),
        "missing_sections": missing_sections,
        "missing_items": missing_items,
        "backfilled_items": backfilled_items,
        "backfilled_sections": backfilled_sections,
        "section_detail": sec_detail,
        "b_layer": {
            "blocking": bmeta.get("blocking", []),
            "b_gap_warnings": bmeta.get("b_gap_warnings", []),
            "b_tail_warnings": bmeta.get("b_tail_warnings", []),
        },
        "gate": gate,
    }

    os.makedirs(report_dir, exist_ok=True)
    with open(os.path.join(report_dir, f"ch{ch}_completeness_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    n_read = sum(1 for m in missing_items if m["status"] == "readable")
    n_agent = sum(1 for m in missing_items if m["status"] == "needs_agent")
    n_ref = sum(1 for m in missing_items if m["status"] == "reference")
    print(f"ch{ch}: contract(items={len(contract_items)}, sections={len(contract_sections)}) | "
          f"missing(sections={len(missing_sections)}[{len(sec_detail.get('continuity', []))}cont/{len(sec_detail.get('tail', []))}tail], "
          f"items={len(missing_items)}[{n_read}r/{n_ref}ref/{n_agent}a])"
          + (f" | BACKFILLED(items={len(backfilled_items)}, sections={len(backfilled_sections)})" if backfill else "")
          + f" | GATE={'PASS' if gate['passed'] else 'FAIL'}")
    return report


def _count_raw_items(ext, ch, start, end):
    """轻量统计源侧（含练习过滤前）扫描到的原始条目数，仅用于报告，不影响回填。"""
    return len(scan_raw_items(ext, ch, start, end))


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
    # 兼容两种 chapter_map 格式：{"chapters":[{num,start,end}]} 与扁平 {"1":{start,end}}
    # （与 build_structure._build_rng 一致，避免格式不一致导致 rng 为空、静默无报告）
    if isinstance(cm, dict) and "chapters" in cm:
        for c in cm["chapters"]:
            n = c.get("num", c.get("chapter", c.get("ch")))
            if n is None:
                continue
            rng[int(n)] = (c.get("start"), c.get("end"))
    elif isinstance(cm, dict):
        for kk, cc in cm.items():
            s = cc.get("start", cc.get("start_page"))
            e = cc.get("end", cc.get("end_page"))
            if s is None or e is None:
                continue
            rng[int(kk)] = (int(s), int(e))

    for ch in (want or sorted(rng)):
        if ch not in rng:
            print(f"ch{ch} SKIP (not in chapter_map)")
            continue
        s, e = rng[ch]
        check_chapter(ext, ch, s, e, book, backfill, report_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
