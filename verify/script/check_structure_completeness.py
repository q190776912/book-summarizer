"""check_structure_completeness.py — 源侧重完整性校验 + 回填（校验层 verify/script 公用能力，由 extract/structure 步骤在写书前调用）

目的
----
`build_structure` 产出分章契约（`book_structure/ch{N}.json`，经 `BookStructure.load` 聚合为书对象）。抽取器源侧捡漏覆盖不全，非三级书在 structure 阶段没有源侧查漏，契约文件会安静地缺章节 / 缺定义定理例。

步骤与状态分流的权威叙述（四步流程、readable / reference / needs_agent 分流、完整 + 连续闸门）见 `flows/write-source/structure/structure.md` 的「步骤（第 2–4 步）/ 源侧完整性校验与回填」一节；本文件仅承载该脚本的实现与调用方式。本脚本在「写书之前」把 `verify/section_continuity`（D 层）与 `verify/item_numbering_integrity`（B 层）两个公共校验层接到 structure 步骤做兜底，回填后由「完整 + 连续」闸门复核。

用法
----
    python check_structure_completeness.py <extract_dir> [ch ...] [--backfill] [--report-dir DIR]
    # 不传 <ch> 即扫全部章；--backfill 才写回分章契约（book_structure/ch{N}.json），否则只产出报告（dry-run）。
    # 默认报告写到 <extract_dir>/completeness_reports/。

注意：本脚本只消费 raw `page_*.json` + 分章契约 + 配置，**不依赖已写的 .md**，
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
from audit_ignore import run_audit             # ignore 条目审核（防误用隐藏真实缺项）
from verify_config import (
    BookConfig, ConfigLoader, ORDINAL_THREE_LEVEL, ORDINAL_TWO_LEVEL,
    ORDINAL_EN, ORDINAL_EN3, ORDINAL_GM, ORDINAL_ROMAN, ORDINAL_SINGLE,
    ORDINAL_CN3LAB, ORDINAL_ROSS,
    _canon_label, _load_ignore_file,
)

# manual_overrides_chN：手写恢复条目（OCR 完全吃掉标题时，agent 凭书补写并登记）。
# 校验层检测到 B 层序列缺口、但 scan_raw_items 因 OCR 丢号而看不到该条目时，
# 由本步从此文件取回并回填进契约 —— 这是「校验出来，然后填进去」的设计回收路径，
# 取代用 ignore 隐藏真实缺口的错误做法。
try:
    import manual_overrides_chN as _mo_mod
except Exception:
    _mo_mod = None

# === 源侧条目扫描：标题锚定，覆盖全方案 / 全类型 ============================
# 作为「源条目集」喂给 B 层（ctx.items）并做 set-difference 差集回填；它是独立于
# 抽取器的稳健交叉校验，专门抓抽取器漏检的标题行条目。
OCR_DIGIT = {'O': 0, 'o': 0, 'Q': 0, 'D': 0, '0': 0,
             'I': 1, 'l': 1, 'i': 1, '1': 1,
             'Z': 2, 'z': 2, '2': 2,
             'A': 4, 'a': 4, '4': 4,
             'S': 5, 's': 5, '5': 5,
             'G': 6, '6': 6,
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
    '公理': 'uncat', 'Axiom': 'axiom', '准则': 'uncat',
    '性质': 'property', 'Property': 'property',
    'uncat': 'uncat',
}

SEP = r'[.\-·，．]'
_CH = r'([0-9A-Za-z]+)'   # OCR 容错的「数字串」捕获（支持多位数章节号，如 10 / 11）
# 末段粘连字母守卫（Leinster 2014 实测）：OCR 把条目号后首词首字母
# 粘到编号上（"Definition 1.3.17A functor" / "Definition 1.2.1Let"）。编号
# 在任何体例中都不以字母结尾；尾部 [A-Za-z] 必是散文粘连。
# _S 用 lookahead 门：token 必须以数字结尾且后随分隔符/空白/行尾。
# lookahead 先行完整匹配后，外层捕获不能回溯缩短（否则 '17A'
# 会退化成 '1' 产生新幻影号）——实现：lookahead 内吹嘴匹配
# ([0-9A-Za-z]*[0-9]) 后紧跟 (?=[\s.‑·，．]|$)，失败则整体失败，
# 不会退回到更短的数字（对已完成书零回徒）。
_S = r'(?=[0-9A-Za-z]*[0-9][\s.\-·，．]|$)([0-9A-Za-z]*[0-9])'
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


def scan_raw_items(ext, ch, start, end, primary_type=None, chapter_first: bool = True, language=None, groups=None):
    """标题锚定源侧扫描：返回书中真值条目候选列表（跨校验源集）。
    每项: {key, label, page, snippet, scheme, canon, has_label}
    key 与 build_structure 产出的分章契约格式一致
    （三级 = "C.S-N"；两级中文 = "标签C.S"；两级英文 = "标签 C.S"），
    以便回填后能被 write-source / verify 原样消费。

    EN3 书（ORDINAL_EN3，标签在前三段式 `Label C.S.N`）特别处理：条目标号
    恒带显式标签词，而图号/公式号（`FIGURE 1.1.1` / `(1.1.1)` / 图版面
    `1.1.1b`）是「无标签的三段数字」。因此禁用数字前置的三段裸号方案
    `en3_nf` / `cn3_nf`（它们会误吞图版面 `1.1.1b` 为 `1.1-18` 伪项），
    仅保留标签前置方案。这与 extract_items_en3 的「要求标签词」一致。

    （2026-08-19 root-cause fix）`primary_type == ORDINAL_THREE_LEVEL` 但
    `language == "en"` 的「英文三级标签前置」书（Strogatz《Nonlinear Dynamics
    and Chaos》、Lasota & Mackey 等）走的是与 ORDINAL_EN3 **完全相同**的编号体例
    （条目恒带 `Example/Definition/...` 标签词，图号/公式号是无标签裸 `C.S.N`），
    只是 config 里 ordinal 写成了默认三级 `3` 而非 `9`。`build_structure` 已对
    此情形路由 `extract_items_en3`（标签前置），但本函数原先只在
    `primary_type == ORDINAL_EN3` 时禁用 `en3_nf`/`cn3_nf`，导致此类书被数字前置
    裸号方案 `en3_nf` 误吞 59+ 个图号/公式号/习题号为伪「缺项」，闸门永 FAIL。
    故此处一并把 `THREE_LEVEL + language=="en"` 纳入「禁用数字前置三段裸号」范围，
    与 build_structure 的分派对齐（单一真相源）。

    （2026-08-23 规则5增量扩展）CN 单级编号书（ORDINAL_SINGLE + language=="cn"，
    如李庆扬《数值分析》第5版：定理1/定义3/例12）：通用数字扫描会把三级小节
    标题（`1.1.1数学科学与数值分析`）误读为三段裸号伪项，故直接委托
    extract_items_cn_single（与 build_structure 同一抽取真源），不再走 _PATTERNS。
    """
    if primary_type == ORDINAL_SINGLE and language == "cn":
        from extract_items_cn_single import extract_items_cn_single
        out = []
        for it in extract_items_cn_single(ext, start, end, groups=groups):
            m = re.search(r"(\d+)$", it["key"])
            if not m:
                continue
            out.append({
                "key": it["key"], "label": it.get("label") or "uncat",
                "page": it["page"],
                "snippet": (it.get("text") or "")[:120].replace("\n", " "),
                "scheme": "cn_single", "canon": (int(m.group(1)),),
                "has_label": True,
            })
        return out
    if primary_type == ORDINAL_SINGLE and language == "en":
        # （2026-08-25 规则5增量扩展）EN 单级编号书（ORDINAL_SINGLE +
        # language=="en"，如 Evans《Partial Differential Equations》2ed：
        # THEOREM 1..N 按节重排、LEMMA/EXAMPLE 独立计数）：通用数字扫描会把
        # 三级小节标题（`2.2.1. Fundamental solution.`）误读为三段裸号伪项
        # （"2.2-1"），与 CN 单级书同型。故直接委托 extract_items_en(single=True)
        # （与 build_structure 同一抽取真源），不再走 _PATTERNS。
        # 键与 build_structure 的 EN 分支同构：`_canon_label(label)+num`
        # （"THEOREM 1" → "定理1"），保证契约/源侧两侧可比较。
        from extract_items_en import extract_items_en
        from verify_config import _canon_label as _canon_lab
        out = []
        for it in extract_items_en(ext, start, end, want_examples=True,
                                   section_scoped=False, single=True):
            m = re.search(r"(\d+)$", it["key"])
            if not m:
                continue
            lab, _, num = it["key"].partition(" ")
            out.append({
                "key": f"{_canon_lab(lab)}{num}",
                "label": it.get("label") or "uncat",
                "page": it["page"],
                "snippet": (it.get("text") or "")[:120].replace("\n", " "),
                "scheme": "en_single", "canon": (int(m.group(1)),),
                "has_label": True,
            })
        return out
    if primary_type == ORDINAL_ROSS:
        # （规则5增量扩展）Ross 体例（S. Ross《A First Course in Probability》）：
        # 标签在前 + 节内作用域编号（Example 2a / Proposition 4.1 / Axiom 1）。
        # 通用 _PATTERNS 会把三级小节标题/图号误读为伪项，直接委托
        # extract_items_ross（与 build_structure 同一抽取真源）。canon 与
        # _canon_key(ORDINAL_ROSS, key) 逐字段一致：字母位 a..z → 1..26。
        from extract_items_ross import extract_items_ross
        out = []
        for it in extract_items_ross(ext, start, end):
            c = _canon_key(ORDINAL_ROSS, it["key"])
            if c is None:
                continue
            lab = (it.get("label") or "uncat")
            out.append({
                "key": it["key"], "label": lab,
                "page": it["page"],
                "snippet": (it.get("text") or "")[:120].replace("\n", " "),
                "scheme": "ross", "canon": c, "has_label": True,
            })
        return out
    if primary_type == ORDINAL_CN3LAB:
        # （规则5增量扩展）CN 三级标签前缀书（如孙文祥《遍历论》：定理1.1.1 /
        # 定义2.3.4，每类标签独立计数、每节重置）。委托 extract_items_cn3lab
        # （与 build_structure 同一抽取真源），禁用 _PATTERNS——数字前置的
        # cn3_nf 会把三级小节标题（`2.3.1 标题`）误读为伪项，cn3_lf 的裸键
        # `C.S-N` 也与本书「标签内嵌键」形不一致。
        from extract_items_cn3lab import extract_items_cn3lab
        out = []
        for it in extract_items_cn3lab(ext, ch, start, end, groups=groups):
            nums = re.findall(r"\d+", it["key"])
            if len(nums) < 3:
                continue
            out.append({
                "key": it["key"], "label": it.get("label") or "uncat",
                "page": it["page"],
                "snippet": (it.get("text") or "")[:120].replace("\n", " "),
                "scheme": "cn3lab",
                "canon": tuple(int(x) for x in nums[:3]),
                "has_label": True,
            })
        return out
    patterns = _PATTERNS
    if primary_type == ORDINAL_EN3 or (primary_type == ORDINAL_THREE_LEVEL and language == "en"):
        # EN3 书条目恒带显式标签词（`Label C.S.N`），且编号按类型独立成序
        # （Definition 2.1.1 与 Remark 2.1.1 并存）。禁用「数字前置三段裸号」方案
        # en3_nf / cn3_nf（会误吞图版面 `1.1.1b`→`1.1-18` 伪项），仅保留标签前置
        # 三段方案 en3_lf / cn3_lf（要求标签词，天然排除图号/公式号）。其余两级
        # 方案也禁用——本书严格三级，避免把语篇里的 `Definition 2.1` 误判为两级项。
        patterns = [(rgx, sch) for (rgx, sch) in _PATTERNS
                    if sch in ('en3_lf', 'cn3_lf')]
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
            for rgx, scheme in patterns:
                m = rgx.match(txt)
                if not m:
                    continue
                label, raw_nums = _split(scheme, m.groups())
                nums = [_ocr_int(x) for x in raw_nums]
                if any(n is None for n in nums):
                    continue
                first = nums[0]
                # Section-scoped EN books (chapter_first == False): the first
                # numeric component is the SECTION, not the chapter, so a value
                # != ch is a legitimate in-chapter item, NOT a cross-chapter
                # forward reference. Only filter when chapter_first is True.
                if chapter_first and first != ch:
                    continue
                if len(nums) < 2:
                    continue
                if any(n > 200 for n in nums[1:]):
                    continue
                has_label = label is not None
                # 两级数字前置且无标签 -> 视为章节号噪声，丢弃
                if scheme in ('cn2_nf', 'en2_nf') and not has_label:
                    break
                # No-label numeric sequences (figure/equation labels like "1.1.1")
                # are always pure digits in print.  If OCR mapped a letter into a
                # token (e.g. "i.i.0" -> "1.1.0"), it is a variable/formula
                # fragment, not a label — drop it so it cannot surface as a
                # phantom missing item (e.g. ch2's "1.1-0" from "i.i.0<iti<").
                if not has_label and any(not t.isdigit() for t in raw_nums):
                    continue
                if _is_three(scheme):
                    if len(nums) < 3:
                        continue
                    # 两级书（ORDINAL_TWO_LEVEL / ORDINAL_EN）下的三段号是
                    # 三级/四级小节标题（"2.2.1 Preliminaries"、"13.3.2 Algorithm"
                    # —— 尾词恰为节题、会伪装成标签），不是编号条目——丢弃，
                    # 否则回填出幻影项污染契约（Koopman 书实测）。
                    if primary_type in (ORDINAL_TWO_LEVEL, ORDINAL_EN):
                        break
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


# === 契约（分章契约 book_structure/ch{N}.json，经 BookStructure.load 聚合）读取 =====
_LABEL_RE = re.compile(r'^(定义|定理|引理|推论|命题|例|练习|习题|评注|注'
                       r'|Definition|Theorem|Lemma|Corollary|Proposition|Example|Exercise|Remark|Axiom)')


def _canon_key(primary_type, key):
    """把契约/源侧 key 规范化为可比较的 int 元组（按方案）。"""
    if primary_type == ORDINAL_ROSS:
        # Ross 体例：字母位键 "Example 2a" → (节号, 字母位 a=1..z=26)；
        # 点分键 "Proposition 4.1" → (节号, 节内序号)；单数字键 "Axiom 1" → (序号,)。
        # 字母必须进 canon（否则 2a..2u 全折叠成 (2,)，契约缺例时假绿）。
        m = re.match(r'^([A-Za-z]+)\s+(\d{1,2})(?:\.(\d{1,3}))?(?:([A-Za-z]))?$',
                     str(key).strip())
        if not m:
            return None
        n1 = int(m.group(2))
        if m.group(3):
            return (n1, int(m.group(3)))
        if m.group(4):
            return (n1, ord(m.group(4).lower()) - 96)
        return (n1,)
    if primary_type == ORDINAL_THREE_LEVEL:
        m = re.match(r'^(\d+)[.\-·，．]+(\d+)[.\-·，．]+(\d+)$', key)
        return tuple(int(x) for x in m.groups()) if m else None
    if primary_type in (ORDINAL_TWO_LEVEL,):
        s = _LABEL_RE.sub('', key).strip()
        m = re.match(r'^(\d+)[.\-·，．]+(\d+)$', s)
        return (int(m.group(1)), int(m.group(2))) if m else None
    s = _LABEL_RE.sub('', key).strip()
    nums = re.findall(r'\d+', s)
    return tuple(int(x) for x in nums) if nums else None


def _composite_key(primary_type, label, canon):
    """把契约/源侧条目表示为可比较的键。

    对「标签内含」方案（含显式类型词、且编号按类型独立成序的书：CN 三级 / 二级、
    EN 二级 / 三级 EN3 等），同一 ``(C,S,N)`` 会跨类型出现（如 Definition 2.1.1 与
    Remark 2.1.1 并存），若只按数字 canon 比对会把两者折叠成同一键，导致契约丢失
    条目、集合差把真实漏项静默吞掉（假绿）。故此类方案用 ``(label_lower, canon)``
    复合键，label 区分类型；无标签方案（纯数字三级等）仍用 canon 本身。

    label 一律先经 ``_canon_label`` 规范化（Theorem/定理 → 定理）：契约侧
    `_TYPE_TO_LABEL` 产英文标签、源侧抽取器产中文标签，不规范化则复合键永不
    相交、整章被误报缺失（2026-08-23 CN 单级书实测）。
    """
    if primary_type in (ORDINAL_THREE_LEVEL, ORDINAL_TWO_LEVEL,
                        ORDINAL_GM, ORDINAL_EN, ORDINAL_EN3, ORDINAL_SINGLE,
                        ORDINAL_CN3LAB, ORDINAL_ROSS):
        return (_canon_label(str(label)).lower(), canon)
    return canon


def load_contract(tree):
    """从结构树（StructureNode）提取 (tree, items: {canon: node}, sections: set(str 'C.S'))。

    tree 为某章节点（StructureNode）；调用方通过 BookStructure.load 聚合读取分章文件并
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
            label = _TYPE_TO_LABEL.get(n.type, "uncat")
            if label == "uncat":
                # uncat 节点（Assumption/Algorithm/Conjecture 等回填项）从 key
                # 前缀恢复标签词，与源侧扫描的 (label, canon) 复合键对齐——
                # 否则回填项在契约侧恒为 ('uncat', canon)，源侧为 ('假设', canon)，
                # 永不相交 → readable 残留、闸门死锁（Koopman 书实测）。
                # 前缀无需先规范化：_composite_key 内部会过 _canon_label。
                m = re.match(r'^([A-Za-z\u4e00-\u9fff]+)', str(n.key).strip())
                if m:
                    label = m.group(1)
            items[_composite_key(_PRIMARY, label, canon)] = n
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
        # 按 canon 顺序插入，保证合成 md / write-source 输出的条目序列连续有序
        # （否则回填项会被 append 到末尾，导致 2.1-4 排在 2.1-8 之后）。
        idx = len(sn.sub_sec)
        for i, child in enumerate(sn.sub_sec):
            cc = _canon_key(_PRIMARY, str(child.key) if isinstance(child.key, str) else str(child.key))
            if cc is not None and canon is not None and cc > canon:
                idx = i
                break
        sn.sub_sec.insert(idx, node)
        _fix_pages(tree)
        return True, sec_key or "(page-proximity)"
    tree.sub_sec.append(node)
    _fix_pages(tree)
    return True, "(chapter-bucket)"


def insert_section(tree, sec_key, page):
    if _section_node(tree, sec_key) is not None:
        return False
    node = _node(sec_key, "section", sec_key, page or 0)
    # 嵌套感知（2026-08-29）：多段数字键的子节（如 1.2.1）插到其数字父节
    # （1.2）的 sub_sec 内、按页码排序；父节不存在（编号洞）才回落章级平铺。
    parts = re.findall(r"\d+", str(sec_key))
    parent = None
    if len(parts) >= 2:
        parent_key = ".".join(parts[:-1])
        parent = _section_node(tree, parent_key)
    if parent is not None:
        idx = len(parent.sub_sec)
        for i, child in enumerate(parent.sub_sec):
            if (page or 0) < child.page_start:
                idx = i
                break
        parent.sub_sec.insert(idx, node)
        _fix_pages(tree)
        return True
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
    "algorithm": "Algorithm", "property": "Property",
    # Ross 体例（ORDINAL_ROSS）：Axiom 条目独立 type，标签 Axiom（_canon_label
    # 归一为 公理，与源侧 extract_items_ross 的 label 对齐）。
    "axiom": "Axiom",
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

    # 单级键（"性质4"/"例3"，标签+纯数字）→ (label, n)；其余 None。
    _SINGLE_KEY = re.compile(r'^([^\d]+)(\d+)$')

    def walk(n):
        if n.type in ("chapter", "section"):
            # Emit `## §C.S` anchors so prefix-less entries (single-level
            # labels like do Carmo "Example 4") get their true per-section
            # counter window in the B layer (item_numbering_integrity windows
            # prefix-less items by the current § heading when one is active).
            if n.type == "section":
                lines.append("## §%s" % n.key)
                # 🔴 节内计数器重起分窗（谷超豪《数学物理方程》ch6 §4 实测：
                # 一节内两套 性质1–4 计数器，印刷小节头各一套）。同一 ## § 窗内
                # 单级编号回落会被 B 层判「顺序错乱」假 BLOCKING；此处按阅读序
                # 检测单级键编号回落，在重起点就地输出 "### §k" 分窗锚（B 层数字
                # 深层 token 锚 = 父节-k），与 write-source 在印刷小节头的分窗
                # 约定一致。
                _last = {}
                _k = 1
                for c in n.sub_sec:
                    _t = getattr(c, "type", "")
                    if _t == "exercise":
                        continue
                    if _t in ("section", "chapter"):
                        walk(c)
                        continue
                    m = _SINGLE_KEY.match(str(getattr(c, "key", "")))
                    if m and '.' not in m.group(2):
                        lab, num = m.group(1), int(m.group(2))
                        if lab in _last and num < _last[lab]:
                            _k += 1
                            lines.append("### §%d" % _k)
                        _last[lab] = max(_last.get(lab, 0), num)
                    walk(c)
                return
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
_ITEM_TYPES = {"definition", "theorem", "lemma", "corollary",
               "proposition", "example", "remark"}


def _contract_item_num_tuples(tree):
    """契约内所有编号项的全数字元组集合（如 ``定理2.25`` -> ``(2, 25)``）。

    用于剔除 D 层把「编号项号」误读成的『缺失节』（章内计数器书里
    ``Theorem 2.25`` 的形态与 ``§2.25`` 完全同构，OCR 把定理号误排到行首时
    会被 section 扫描当成节头）。同一 (章,号) 已作为条目落地进契约，则它
    绝不可能是缺失节——真实缺节不会同时是一个已捕获条目，故剔除属纠错而非掩盖。
    """
    out = set()

    def _walk(n):
        t = getattr(n, "type", None) if not isinstance(n, dict) else n.get("type")
        key = getattr(n, "key", None) if not isinstance(n, dict) else n.get("key")
        if t in _ITEM_TYPES and key:
            ds = re.findall(r"\d+", str(key))
            if ds:
                out.add(tuple(int(x) for x in ds))
        kids = getattr(n, "sub_sec", None) if not isinstance(n, dict) else n.get("sub_sec")
        if kids:
            for k in kids:
                _walk(k)
    _walk(tree)
    return out


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
    # 契约只建模 chapter → section → 条目（**没有 subsection 容器
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
    # 🔒 合法性过滤：D 层把「编号项号」（如 Theorem 2.25）误读为节号而报
    # 「缺失节」。若同一 (章,号) 已作为编号项捕获进契约，则它绝不是缺失节
    # （真实缺节不会同时是一个已落地条目），须剔除，否则为假绿/假红源头。
    item_num_tuples = _contract_item_num_tuples(tree)
    filtered = []
    for r in missing:
        nums = tuple(int(x) for x in r.split("."))
        if nums in item_num_tuples:
            continue
        filtered.append(r)
    missing = filtered
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

    raw_items = [it for it in scan_raw_items(ext, ch, start, end, cfg.primary_type, cfg.chapter_first, cfg.language,
                                             groups=getattr(cfg, "ordinal", None))
                 if it["label"] not in _EXER_LABELS_RAW]

    # 0) agent 已核实「非条目」的键（ignore_ch{N}.json，须附理由）：从源侧缺失集
    #    剔除，不得回填进契约。适用形态：OCR 把公式/编号散文误读成条目号
    #    （谷超豪《数学物理方程》ch10 实测：连乘积 1·3·5·…·(2n−1)! 被读成
    #    三级号 1.3-5）。ignore 审计（run_audit）仍会在报告中展示该条目供复核。
    try:
        from key_parse import normkey as _normkey
        _ign = _load_ignore_file(os.path.join(ext, f'ignore_ch{ch}.json'))
    except Exception:
        _ign = {}
    if _ign:
        try:
            _ignk = {_normkey(str(k)) for k in _ign}
            raw_items = [it for it in raw_items
                         if _normkey(str(it.get('key', ''))) not in _ignk]
        except Exception:
            pass

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
        # 复合键（标签内含方案下含类型词）：同一 (C,S,N) 跨类型并存时，
        # 去重集合与「契约命中」判断均按 (label, canon) 区分，避免把
        # Definition 2.1.1 / Remark 2.1.1 折叠、静默吞掉真实漏项。
        ck = _composite_key(cfg.primary_type, it["label"], c)
        is_ref = bool(_REF_RE.search(it.get("snippet", "")))
        prev = best.get(ck)
        if prev is None:
            best[ck] = it
            continue
        prev_ref = bool(_REF_RE.search(prev.get("snippet", "")))
        if (not is_ref) and prev_ref:
            best[ck] = it
        elif (not is_ref) == (not prev_ref) and it["page"] < prev["page"]:
            best[ck] = it

    missing_items = []
    for ck, it in best.items():
        if ck in contract_items:
            continue
        c = tuple(it["canon"]) if isinstance(it["canon"], list) else it["canon"]
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
    # 按章合并 ignore_ch{N}.json（与正式 verify 流程 ConfigLoader.ignore_for_chapter
    # 同语义）：否则预检管线里登记的稀疏号豁免对 B 层不可见，闸门永 FAIL。
    try:
        from dataclasses import replace as _dc_replace
        extra = _load_ignore_file(os.path.join(ext, f'ignore_ch{ch}.json'))
        if extra:
            cfg = _dc_replace(cfg, ignore=sorted(set(cfg.ignore) | set(extra)))
    except Exception:
        pass
    with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
        f.write(md)
        md_path = f.name
    try:
        ctx = VerifyContext(ch=ch, start=start, end=end, md_file=md_path,
                            ext_dir=ext, config=cfg)
        ctx.items = source_items            # 源条目集（供尾部校验：源 max vs md max）
        # 修复接线：正常 verify 流程由 verify.script.structure_io.md_keys_for_chapter 填充
        # ctx.entry_keys / ctx.all_keys（按章过滤）；之前漏调导致 B 层看到空
        # all_keys → 全部源条目被判缺失（假阳性 blocking）。
        from verify.script.structure_io import md_keys_for_chapter
        ctx.entry_keys, ctx.all_keys = md_keys_for_chapter(ctx.md_file, cfg, ctx.ch)
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
    # B-layer blocking: numbering errors (out-of-order / gaps) are now blocking,
    # not just diagnostic — they propagate to unit content and final output.
    # Only exercise-block ordering issues are exempt (some books have genuine
    # non-sequential exercise numbering).
    real_b_blocking = [b for b in b_blocking if not b.get("exercise_block_only", False)]
    passed = (not sec_left) and (not readable_left) and (not real_b_blocking)
    return {
        "passed": passed,
        "residual_sections": sec_left,
        "residual_readable_items": [m["key"] for m in readable_left],
        "residual_b_blocking": real_b_blocking,
    }


# === 主流程 ================================================================
_PRIMARY = ORDINAL_THREE_LEVEL


def check_chapter(ext, ch, start, end, cfg, backfill, report_dir):
    global _PRIMARY
    _PRIMARY = cfg.primary_type
    # 分章契约：经 BookStructure.load 聚合读取，定位指定章节点。
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
        # ---- 手写恢复条目回填（manual_overrides_chN.json）----
        # 覆盖「B 层检测到序列缺口，但 scan_raw_items 因 OCR 丢号而完全看不到该条目」
        # 的情形：从 manual_overrides 取回 agent 凭书补写的条目，回填进契约。
        # 这样校验逻辑既能「检测」缺口、又能「填回」，无需借助 ignore 隐藏真实缺项。
        if _mo_mod is not None:
            mo_path = os.path.join(ext, f"manual_overrides_ch{ch}.json")
            mo_list = _mo_mod.load_manual_overrides(mo_path)
            if mo_list:
                for mo in mo_list:
                    mk = mo.get("key")
                    if not mk:
                        continue
                    c = _canon_key(_PRIMARY, mk)
                    if c is None:
                        continue
                    # contract_items 以复合键 (label_lower, canon) 为键（见
                    # load_contract / _composite_key）——裸 canon 永远查不中，
                    # 重跑 --backfill 会把同一手写条目重复插入书结构。
                    _mo_label = mo.get("label", "uncat")
                    if _composite_key(_PRIMARY, _mo_label, c) in contract_items:
                        continue  # 已在校验起点契约中，跳过（避免重复插入）
                    ok, where = insert_item(tree, mk, _mo_label,
                                            mo.get("page", 0), c, mo.get("text", ""))
                    if ok:
                        backfilled_items.append({"key": mk, "where": where,
                                                 "page": mo.get("page"), "source": "manual_override"})
        if backfilled_items or backfilled_sections:
            # 回填后写回分章契约（2026-08-29 重构）：ch{N}.json 是"骨架+内容"
            # 完整契约——先丢 raw 保真视图（树已被原地修改），重建该章内容
            # （build_chapter_contract 幂等重挂，新回填条目也获得 text/formula
            # 内容块），再写回单章文件。不走 bs.save()（会把全书按内存树
            # 重写；此处只改了一章，避免无谓重写其他章）。
            from attach_content import build_chapter_contract as _bcc
            from data.book_structure.book_structure import chapter_json_path as _ch_path
            tree.clear_raw_recursive()
            full_ch, _stats = _bcc(ext, tree.to_dict())
            with open(_ch_path(ext, str(ch)), "w", encoding="utf-8") as f:
                json.dump(full_ch, f, ensure_ascii=False, indent=2)
            bs.root.replace_chapter(StructureNode.from_dict(full_ch))

    # ---- 第 4 步：完整性与连续性闸门（回填后重跑断言）----
    # 回填已写入 bs（内存同对象），用最新章节点重算契约再校验。
    ch_node_after = bs.find_chapter(ch)
    gate = step4_gate(ext, ch, start, end, cfg, bs, ch_node_after, bmeta)

    report = {
        "chapter": ch,
        "contract_items": len(contract_items),
        "contract_sections": sorted(contract_sections),
        "ignore_audit": run_audit(ext, ch),  # ignore 条目审核：SUSPECT 提示 agent 复核
        "raw_items_scanned": _count_raw_items(ext, ch, start, end, cfg.chapter_first),
        "raw_sections_present": sorted(set(sec_detail.get("continuity", []) + sec_detail.get("tail", []))),
        "missing_sections": missing_sections,
        "missing_items": missing_items,
        "backfilled_items": backfilled_items,
        "backfilled_sections": backfilled_sections,
        "manual_override_backfills": [b for b in backfilled_items if b.get("source") == "manual_override"],
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
          + f" | GATE={'PASS' if gate['passed'] else 'FAIL'}"
          + (f" | IGNORE-AUDIT(suspect={report['ignore_audit']['suspect_count']})" if report['ignore_audit']['suspect_count'] else ""))
    return report


def _count_raw_items(ext, ch, start, end, chapter_first: bool = True):
    """轻量统计源侧（含练习过滤前）扫描到的原始条目数，仅用于报告，不影响回填。"""
    return len(scan_raw_items(ext, ch, start, end, None, chapter_first))


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
    want = []
    for x in args[1:]:
        try:
            want.append(int(x))
        except ValueError:
            want.append(x.strip())  # 字母章号（附录 A/B…）
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
            try:
                key = int(n)
            except (TypeError, ValueError):
                key = str(n).strip()  # 字母章号（附录 A/B…）
            rng[key] = (c.get("start", c.get("start_page")), c.get("end", c.get("end_page")))
    elif isinstance(cm, dict):
        for kk, cc in cm.items():
            s = cc.get("start", cc.get("start_page"))
            e = cc.get("end", cc.get("end_page"))
            if s is None or e is None:
                continue
            rng[int(kk)] = (int(s), int(e))

    def _rng_sort_key(k):
        try:
            return (0, int(str(k)), "")
        except (TypeError, ValueError):
            return (1, 0, str(k))

    for ch in (want or sorted(rng, key=_rng_sort_key)):
        if ch not in rng:
            print(f"ch{ch} SKIP (not in chapter_map)")
            continue
        s, e = rng[ch]
        check_chapter(ext, ch, s, e, book, backfill, report_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
