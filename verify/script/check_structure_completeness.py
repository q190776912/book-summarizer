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

from data.book_structure.book_structure import (BookStructure, StructureNode,
                                                chapter_label)
# 类型词 OCR 形近补救的单一真源（抽取器 extract_items_en 与本校验共用）
from lib import label_typo as _label_typo_lib

import page_json
# 公共校验层（verify/*/script 由 boot 注入 sys.path，可直接裸 import）：
from section_continuity import check_d_layer          # D 层：section-continuity（章节连续性）
from item_numbering_integrity import ItemNumberingIntegrityLayer  # B 层：item-numbering-integrity（条目编号完整性）
from verify.script.base import VerifyContext   # B 层 run() 所需的精简运行时载体
from audit_ignore import run_audit             # ignore 条目审核（防误用隐藏真实缺项）
from verify_config import (
    BookConfig, ConfigLoader, ORDINAL_THREE_LEVEL, ORDINAL_TWO_LEVEL,
    ORDINAL_SINGLE, ORDINAL_APP, ORDINAL_APP2, ORDINAL_VAKIL,
    LABEL_TO_TYPE, LABEL_TO_TYPE_LC, TYPE_TO_LABEL_EN,
    _LABEL_CANON, _canon_label, _load_ignore_file,
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
# Problem（Lee《Introduction to Smooth Manifolds》2e 实测：章末短横编号 `Problem 1-5`、
# 独立计数器）与 Exercise 同属练习族，走 EXER 节点通道。
_EXER_LABELS_RAW = {'练习', '习题', 'Exercise', 'Problem'}
_EXER_LABELS_RAW_LC = {s.lower() for s in _EXER_LABELS_RAW}

CN_LABELS = ['定义', '定理', '引理', '推论', '命题', '例', '练习', '习题', '评注', '注', '公理', '准则']
EN_LABELS = ['Definition', 'Theorem', 'Lemma', 'Corollary', 'Proposition',
             'Example', 'Exercise', 'Problem', 'Remark', 'Axiom', 'Assertion', 'Conjecture',
             'Algorithm', 'Assumption']

# 回填节点 type 字段（insert_item/_type_of 消费）：单源导入 config/verify_config
# 的派生表 LABEL_TO_TYPE（_LABEL_CANON × TYPE_TO_LABEL_CN，新增标签只改
# config）。练习/问题族（exercise/problem 类型）在本通道的机制：B 层豁免、
# DONE-only 门控、load_contract 排除；build_structure 侧走 _EXERCISE_LABELS+
# 3a 标记路由、不经其 _LABEL_TO_TYPE。
# 与 build_structure._LABEL_TO_TYPE 的差异仅 Table/Figure 两个图表注记类型
# （build_structure 本地扩展；checker 的回填不含图表项）。

SEP = r'[.\-·，．,]'
_CH = r'([0-9A-Za-z]+)'   # OCR 容错的「数字串」捕获（支持多位数章节号，如 10 / 11）
# 末段粘连字母守卫（Leinster 2014 实测）：OCR 把条目号后首词首字母
# 粘到编号上（"Definition 1.3.17A functor" / "Definition 1.2.1Let"）。编号
# 在任何体例中都不以字母结尾；尾部 [A-Za-z] 必是散文粘连。
# _S 用 lookahead 门：token 必须以数字结尾且后随分隔符/空白/行尾。
# lookahead 先行完整匹配后，外层捕获不能回溯缩短（否则 '17A'
# 会退化成 '1' 产生新幻影号）——实现：lookahead 内吹嘴匹配
# ([0-9A-Za-z]*[0-9]) 后紧跟 (?=[\s.‑·，．]|$)，失败则整体失败，
# 不会退回到更短的数字（对已完成书零回徒）。
# 🔴 后继类含冒号（半/全角，Strogatz 3e 实测）：条头印成 "Example 2.2.1:"（标题
# 在下一块），旧类无 ':' → en3_lf 整书失配 → 源侧真值集为空 → 闸门对「条目全漏」
# 失明（契约 items=0 仍 gate.passed=true 假绿）。
_S = r'(?=[0-9A-Za-z]*[0-9](?:[\s.\-·，．:：\u4e00-\u9fff（(]|$))([0-9A-Za-z]*[0-9])'
# 块首锚定的「标签 + 编号」候选正则（独立于抽取器的行内扫描）。
# 标签后加负向预查 (?![A-Za-z一-龥])，避免把章节标题（"Examples"/"Exercises"）或
# 语篇词（"例如"）误当成条目标签——它们是纯噪声，必须排除。
_NA = r'(?![A-Za-z一-龥])'
# 🔴 茆书 ch3 实测 2026-09-29：本书大量使用「性质N.M.K」条目体例，_LBL_CN
# 原缺 性质 → 源侧扫描看不见 性质 条目 → 与契约（已按 property 落账）错位、
# readable 假缺项。性质 → property 已在 TYPE_TO_LABEL_CN/_LABEL_CANON 在案。
_LBL_CN = r'(定义|定理|引理|推论|命题|性质|例|练习|习题|评注|注|公理|准则)'
_LBL_EN = (r'(Definition|Theorem|Lemma|Corollary|Proposition|Example|Exercise|Problem|'
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


def _edit_dist_1(a, b):
    """兼容旧名：判据已移至公用件 `lib/label_typo.py`（抽取器与本校验共用）。"""
    return _label_typo_lib.edit_dist_1(a, b)


def _label_typo_normalize(txt):
    """兼容旧名：调用公用件 `lib/label_typo.label_typo_normalize`（词表 = EN_LABELS）。

    根因（Apostol《Introduction to Analytic Number Theory》ch2 实测 2026-09-28）：
    印刷「Theorem 2.7 …」被 OCR 读成「Theorerm 2.7 …」，抽取器与本校验的类型词
    正则全部失配 → 该条既不入契约、也不在源侧候选集，闸门只剩 B 层「序列 1..27
    缺号 7」死锁（差集为空，回填无从下手）。四重判据（块首 ≥5 字母纯字母词、
    非正字亦非正字复数形、与词表**恰好一个**类型词编辑距离恰为 1、其后紧跟点分
    序标）与完整说明见 `lib/label_typo.py`。
    """
    return _label_typo_lib.label_typo_normalize(txt, EN_LABELS)


def scan_raw_items(ext, ch, start, end, primary_type=None, chapter_first: bool = True, language=None, groups=None):
    """标题锚定源侧扫描：返回书中真值条目候选列表（跨校验源集）。
    每项: {key, label, page, snippet, scheme, canon, has_label}
    key 与 build_structure 产出的分章契约格式一致
    （三级 = "C.S-N"；两级中文 = "标签C.S"；两级英文 = "标签 C.S"），
    以便回填后能被 write-source / verify 原样消费。

    英文三级「标签前置」书（`primary_type == ORDINAL_THREE_LEVEL` 且
    `language == "en"`，如 Strogatz《Nonlinear Dynamics and Chaos》、Lasota &
    Mackey；历史上曾是独立码 ORDINAL_EN3=9，现已并入三级 3）特别处理：条目标号
    恒带显式标签词（`Label C.S.N`），而图号/公式号（`FIGURE 1.1.1` / `(1.1.1)` /
    图版面 `1.1.1b`）是「无标签的三段数字」。因此禁用数字前置的三段裸号方案
    `en3_nf` / `cn3_nf`（它们会把图版面 `1.1.1b` 误吞为 `1.1-18` 伪「缺项」，闸门
    永 FAIL），仅保留标签前置方案 `en3_lf` / `cn3_lf`。这与 `extract_items_en3`
    的「要求标签词」及 build_structure 的路由一致（单一真相源）。

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
    if primary_type in (ORDINAL_APP, ORDINAL_APP2):
        # （附录字母章位，type 13 三级 / type 14 两段）条目形如
        # `Definition A.1.1` / 裸 `A.1.5`（13，Weibel）或 `Theorem B.2` /
        # 裸 `B.4`（14，Lee ISM），委托 extract_items_en3 的附录正则
        # （EN3_APP_RE / EN3_APP_BARE_*，与 build_structure 同一抽取真源）；
        # canon = (字母, 节[, 条]) 或 (字母, 条)，与
        # _canon_key(ORDINAL_APP[2], key) 逐字段一致。键存 normkey 形 "A.1-1"。
        from extract_items_en3 import extract_items_en3
        out = []
        for it in extract_items_en3(ext, ch, start, end, want_examples=True):
            # EN3 的键形为 "Definition A.1.1"（标签 + 空格 + 字母号）：先剥标签
            # 再做字母号 canon（标签单独经 _canon_label 进复合键）。
            lab = (it.get("label") or "uncat")
            _num = it["key"].partition(" ")[2] if " " in it["key"] else it["key"]
            c = _canon_key(primary_type, _num)
            if c is None:
                continue
            out.append({
                "key": _num, "label": lab,
                "page": it["page"],
                "snippet": (it.get("text") or "")[:120].replace("\n", " "),
                "scheme": "app", "canon": c, "has_label": True,
            })
        return out
    patterns = _PATTERNS
    if primary_type == ORDINAL_THREE_LEVEL and language == "en":
        # EN3 书条目恒带显式标签词（`Label C.S.N`），且编号按类型独立成序
        # （Definition 2.1.1 与 Remark 2.1.1 并存）。禁用「数字前置三段裸号」方案
        # en3_nf / cn3_nf（会误吞图版面 `1.1.1b`→`1.1-18` 伪项），仅保留标签前置
        # 三段方案 en3_lf / cn3_lf（要求标签词，天然排除图号/公式号）。其余两级
        # 方案也禁用——本书严格三级，避免把语篇里的 `Definition 2.1` 误判为两级项。
        patterns = [(rgx, sch) for (rgx, sch) in _PATTERNS
                    if sch in ('en3_lf', 'cn3_lf')]
    elif primary_type == ORDINAL_THREE_LEVEL and language == "cn":
        # 🔴 CN 三级标签前置书（如常庚哲《数学分析教程》：定义1.10.1 / 定理1.10.1
        # 恒带标签词，与 build_structure 的 extract_items 同一抽取真源——后者只
        # 抓带标签条目）：禁用「数字前置三段裸号」方案 cn3_nf。它把逗号分隔的散文
        # 枚举（"1,2.3…n…" / "1,0,2,0,3…"）误读为裸三段号伪「缺项」，又把无标签的
        # 交叉引用残句（"1.5.1,以下两个极限存在"）当成独立条目——而真实条目已由带
        # 标签方案 cn3_lf 抓到。仅保留标签前置方案，与 EN3 分支同理（单一真相源）。
        patterns = [(rgx, sch) for (rgx, sch) in _PATTERNS
                    if sch == 'cn3_lf']
    out = []
    for p in range(start, end + 1):
        fp = os.path.join(ext, f"page_{p:03d}.json")
        if not os.path.exists(fp):
            continue
        try:
            data = page_json.PageJson.load(fp).data
        except Exception:
            continue
        def _match_scheme(text, page_no):
            """对一个块文本跑一遍方案匹配；命中并产出候选返回 True。
            原「break」语义（命中即止 / 判为噪声弃块）都终止本轮匹配。"""
            for rgx, scheme in patterns:
                m = rgx.match(text)
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
                    return False
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
                    # 两级书（ORDINAL_TWO_LEVEL，含原 EN 两级折叠而来的英文两级
                    # 书）下的三段号是三级/四级小节标题（"2.2.1 Preliminaries"、
                    # "13.3.2 Algorithm"—— 尾词恰为节题、会伪装成标签），不是编号
                    # 条目——丢弃，否则回填出幻影项污染契约（Koopman 书实测）。
                    if primary_type == ORDINAL_TWO_LEVEL:
                        return False
                    # 🔴 OCR 粘连幻影守卫（茆书 ch1 p51 实测 2026-09-29）：
                    # 真条头「例1.3.13」与下一行行首数字 6 粘连成「例1.3.136」，
                    # 末段 136 远超单节真实条目数（本书每节条目 ≤ 20 余），若放行
                    # 会回填幻影 例1.3-136 并把 B 层序列空间撑到 136。抽取器
                    # _add_match 本就有 `num > 50` 上限过滤，源侧扫描同口径补齐：
                    # 末段 > 50 的 cn3_lf 命中一律丢弃（其他书条目 >50/节 的见
                    # 冯琦注记——那条放宽只针对两级 lab_items 路径，三级书单节
                    # 50+ 条目极罕见，真有再显式放宽此处）。
                    if scheme == 'cn3_lf' and nums[2] > 50:
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
                    "key": key, "label": label or "uncat", "page": page_no,
                    "snippet": text[:120].replace("\n", " "), "scheme": scheme,
                    "canon": canon, "has_label": has_label,
                })
                return True
            return False

        for blk in data.get("text", []):
            txt = blk.get("text", "").strip()
            if not txt:
                continue
            if _match_scheme(txt, p):
                continue
            # 🔴 类型词形近补救（见 _label_typo_normalize）：正字匹配一无所获时，
            # 才用归一后的文本重试一遍——绝不影响已正常命中的块。
            fixed = _label_typo_normalize(txt)
            if fixed and _match_scheme(fixed, p):
                continue
    # 🔴 section-scoped 英文两级书（type 2 + language=="en" + chapter_first=False，
    # 如 Hilton & Stammbach）：编号首段即节号，一章内同 (label, canon) 的真条目头
    # 只出现一次。行尾换行恰好落在 "Theorem 2.4." 的引用残行会被本扫描当成第二个
    # 条目头；若保留，回填会把幻影项写回契约。与 extract_items_en 的 unique_keys
    # 去重同语义：保留首个。
    if primary_type == ORDINAL_TWO_LEVEL and language == "en" and not chapter_first:
        seen = set()
        uniq = []
        for it in out:
            ck = (_canon_label(str(it.get("label") or "uncat")).lower(), it.get("canon"))
            if ck in seen:
                continue
            seen.add(ck)
            uniq.append(it)
        out = uniq
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
# 🔴 词表由 _LABEL_CANON 派生（Iwaniec-Kowalski 2026-09-28 实测）：旧硬编码缺
# 猜想/问题/断言/假设/条件/Conjecture… → `_canon_key('猜想7.32')` 返回 None →
# insert_item 定位循环把该节点整个跳过 → 回填条目插到它之后（B 层「顺序错乱」），
# 且契约侧存在性比对同样丢标签。长词在前保证交替匹配取最长。
_LABEL_RE = re.compile(
    r'^(?:' + '|'.join(sorted(
        (l for l in _LABEL_CANON if re.fullmatch(r'[A-Za-z\u4e00-\u9fff]+', l)),
        key=len, reverse=True)) + r')')


def _canon_key(primary_type, key):
    """把契约/源侧 key 规范化为可比较的 int 元组（按方案）。"""
    if primary_type in (ORDINAL_APP, ORDINAL_APP2):
        # 附录字母章位（type 13 三级 / type 14 两段）：契约键 "A.1-1"（normkey
        # 形）/ 源侧键 "A.1.1"，两级 "A.1"（type 14 的 Lee 体例 / Leinster 体
        # 例）也可；**允许中文/英文标签前缀**（Lee 契约键实测为 `例A.4` /
        # `定理B.2` 形——build_structure 落盘时标签内嵌进 key）。canon =
        # (字母, 节号[, 条目号]) 或 (字母, 条目号)，字母保留原样（str 元组与
        # int 元组互比安全：仅同方案内部比较）。
        m = re.match(r'^(?:[A-Za-z\u4e00-\u9fff]+)?([A-Za-z])[.\-·，．]+(\d+)'
                     r'(?:[.\-·，．]+(\d+))?$',
                     str(key).strip())
        if not m:
            return None
        c = (m.group(1).upper(), int(m.group(2)))
        if m.group(3):
            c = c + (int(m.group(3)),)
        return c
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
                        ORDINAL_SINGLE, ORDINAL_APP, ORDINAL_APP2):
        # ORDINAL_APP/APP2：Weibel 附录 Definition A.1.1 与 Exercise A.1.1
        # 同号并存（Lee 附录 Theorem B.2 与 Exercise B.2 同理），无标签复合键
        # 会把两类折叠、假绿。
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
        if t in ("exercise", "problem"):
            # 🔴 练习类节点仍登记「存在性」：源侧 scan_raw_items 全方案扫描会把
            # "12.1.3. Problem." 这类练习类条扫成候选，契约侧若不登记，差集会把它
            # 当缺失重要概念自动回填，造出同号重复节点、B 层随即报顺序错乱
            # （Rising Sea ch12 实测）。items 只作成员判定；回填目标另有
            # 「排除练习类」规则，登记练习类不会导致练习被回填。
            canon = _canon_key(_PRIMARY, n.key if isinstance(n.key, str) else str(n.key))
            if canon is not None:
                items[_composite_key(_PRIMARY, _TYPE_TO_LABEL.get(t, "uncat"), canon)] = n
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
            if label == "uncat":
                # 🔴 数字前置三级键（Kreyszig 实测 2026-09-26）：键为裸号
                # "C.S-N" 无前缀可恢复，而正文印刷条头可能整行丢失类型词
                # （p226 "4.1-5 Positive integers."——「Example (」被 OCR 吞），
                # 契约成 ('uncat',(4,1,5))、源侧真身候选却带标签（练习题
                # "In Example 4.1-5…" p227 → ('example',…)），两键永不相交 →
                # 假 readable-missing、闸门死锁，盲目 --backfill 还会从引用句
                # 造出重复条目。同 canon 的 uncat 节点即该条目的存在性证据
                # （B 层按裸号分组、跨类型同号并存书不受影响：那些书键自带
                # 前缀，走上方恢复分支）。登记 ('uncat', canon) 影子键，
                # 仅补「存在性」，不改节点类型。
                items.setdefault(("uncat", canon), n)
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
    # 大小写不敏感：OCR 标签大小写随印刷/识别波动（与 build_structure._type_of
    # 的 _LABEL_TO_TYPE_LC 同口径），避免 "ASSERTION" 这类变体掉进 uncat。
    return LABEL_TO_TYPE_LC.get((label or "").strip().lower(), "uncat")


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


_CN_LABEL_RE = re.compile(r'^[一-鿿]+')


def _match_contract_key_style(tree, key, label):
    """🔴 回填键式须与**契约自身**的键式同构（Shafarevich ch3 实测）。

    HOM 系抽取器（`extract_items_hom`）把印刷标签归一为**中文标签**键（`命题3.1`），
    而源侧 `scan_raw_items` 给出的是印刷标签（`Proposition 3.1`）。直接拿后者
    `insert_item` 会在契约里造出一个「非本章序标形态」的节点：门控 ㉓（单元标签
    须在契约登记）与 P 层都认不出它，B 层还把同号两条当「双现」。

    判据不看书名、不看词表：取树内**同类型**条目节点键的首字符形态（汉字 / 拉丁）
    多数决；中文式则把新键渲染为 `_canon_label(label) + 数字尾`（与 scan_raw_items
    的 en_single 分支同一渲染式，见其注释「键与 build_structure 同构」）。树内无同类
    条目（首个回填）或键式已一致 → 原样返回，零回归。
    """
    if not key:
        return key
    k = str(key)
    cn = en = 0
    g_cn = g_en = 0
    stack = [tree]
    while stack:
        n = stack.pop()
        for c in getattr(n, 'sub_sec', None) or []:
            stack.append(c)
            _ct = getattr(c, 'type', None)
            ck = str(getattr(c, 'key', '') or '')
            if _ct == _type_of(label):
                if _CN_LABEL_RE.match(ck):
                    cn += 1
                elif re.match(r'^[A-Za-z]', ck):
                    en += 1
            # 🔴 全局多数（Iwaniec-Kowalski 实测）：回填该章**首个**某类型条目
            # （如 ch3 无既有 proposition 节点）时同类证据为 0，旧判据原样返回
            # 印刷键 `3.7`，在中文标签键契约里造出裸键异类节点——合成 md 按
            # _BARE_THREE 只认三级裸键，两级裸键被 B 层当节号丢弃 → 假缺号照旧。
            # 同类无证据时退而看全部条目类节点键式的首字符多数。
            elif _ct in _ITEM_TYPES:
                if _CN_LABEL_RE.match(ck):
                    g_cn += 1
                elif re.match(r'^[A-Za-z]', ck):
                    g_en += 1
    if not cn and cn <= en and (g_cn and g_cn > g_en):
        cn = 1  # 同类无证据、全局压倒性中文键式 → 按全局键式渲染
    if not cn or cn <= en:
        return k
    if _CN_LABEL_RE.match(k):
        return k
    num = re.search(r'([0-9][0-9.．\-–]*)\s*$', k)
    if not num:
        return k
    return "%s%s" % (_canon_label(str(label or '')), num.group(1).replace('．', '.').replace('-', '.').replace('–', '.'))


def _anchor_problem_count(tree):
    """契约前序页码单调性违例条数（判据与 ``lib.unit_order.check_contract_anchors`` 同源）。

    回填候选位置的**事后否决**用：邻近锚定（canon-adjacency）只看条目号相邻，不看
    页码，条目号与节号同一编号空间的「章内共享计数器」书里会把晚页条目插到早页节
    内容之前（Iwaniec-Kowalski ch3 命题3.7 / ch5 命题5.25 / ch20 命题20.7 实测：
    合并 md 阅读顺序倒退，门控 ⑪ 事后必拦）。判据本身异常 → 返回 -1（不否决，
    保守维持旧行为；第 4 步闸门仍会阻断）。
    """
    from lib.unit_order import check_contract_anchors
    try:
        return len(check_contract_anchors(tree.to_dict()))
    except Exception:
        return -1


def insert_item(tree, key, label, page, canon, snippet=""):
    """把遗漏条目插回结构树（StructureNode）。three_level 优先归到 C.S 节；否则按页码归最近节。
    节点字段（key/type/name/page）与 build_structure 完全一致，回填后 write-source / verify 可直接消费。
    """
    itype = _type_of(label)
    key = _match_contract_key_style(tree, key, label)
    title = _clean_title(snippet, key)
    name = (f"{key} {title}".strip()) if title else key
    node = _node(key, itype, name, page)
    sec_key = None
    if _PRIMARY in (ORDINAL_THREE_LEVEL, ORDINAL_APP) and len(canon) >= 2:
        sec_key = f"{canon[0]}.{canon[1]}"
    sn = _section_node(tree, sec_key) if sec_key else None
    # 🔴 邻近锚定回填（Iwaniec-Kowalski ch13 实测 2026-09-28）：无 sec_key 的
    # 章内共享计数器书里，页码归节在同页多节起始时必错判（§13.4/§13.5 同起
    # p344，条目 13.4 被挂进 §13.5 → 与 §13.4 里的 13.5 形成阅读序逆序 → B 层
    # 「顺序错乱」）。条目号与节号无蕴含关系，但 B 层窗口按**条目自身前缀**分窗、
    # 要求 canon 单调——故直接落在 canon 前驱条目之后（其父节点的子列表内），
    # 窗口内阅读序恒单调；前驱/后继都找不到才回落页码就近。
    if sn is None and canon is not None:
        items_doc = []   # (pos, canon, parent_node, index_in_parent)
        def _collect(n):
            for i, c in enumerate(n.sub_sec):
                if c.type in _ITEM_TYPES:
                    cc = _canon_key(_PRIMARY, str(c.key))
                    if cc is not None and len(cc) == len(canon):
                        items_doc.append((cc, n, i))
                _collect(c)
        _collect(tree)
        prevs = [t for t in items_doc if t[0] < canon]
        nexts = [t for t in items_doc if t[0] > canon]
        # 🔴 事后否决（Iwaniec-Kowalski ch3/ch5/ch20 实测 2026-09-28）：条目号相邻
        # ≠ 阅读位置相邻。章内共享计数器的书里 canon 前驱可能跨了好几节（前驱 p61、
        # 本条目 p65），照抄「插在前驱之后」就把晚页条目挂到了早页节内容之前 → 契约
        # 锚点自相矛盾。插入后锚点违例变多即撤销，改试 canon 后继位、再回落页码就近。
        # 比较前后**都不跑** `_fix_pages`：它会把节锚点改写成子节点最小页（节引言
        # 散文不是带类型子节点时锚点被抬高），先跑一次反而污染回落判据的输入。
        _base_anchor = _anchor_problem_count(tree)
        _cands = []
        if prevs:
            _cands.append((max(prevs, key=lambda t: t[0]), True))
        if nexts:
            _cands.append((min(nexts, key=lambda t: t[0]), False))
        for _cand, _at_end in _cands:
            _, _par, _i = _cand
            _pos = _i + 1 if _at_end else _i
            _par.sub_sec.insert(_pos, node)
            if _base_anchor < 0 or _anchor_problem_count(tree) <= _base_anchor:
                _fix_pages(tree)
                return True, "(canon-adjacency)"
            _par.sub_sec.remove(node)
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
            # 仅与「条目类」子节点比较位置：description（键如 D19，canon=(19,)）
            # 等非条目节点的元组与条目 canon 长度不同，元组比较会恒真把回填项
            # 拽到节首（2026-09-15《高等代数学》实测）；再以长度守卫兜底。
            _ct = child.get("type") if isinstance(child, dict) else getattr(child, "type", None)
            if _ct not in _ITEM_TYPES:
                continue
            cc = _canon_key(_PRIMARY, str(child.key) if isinstance(child.key, str) else str(child.key))
            if cc is None or canon is None or len(cc) != len(canon):
                continue
            # 阅读序感知比较（2026-09-15《高等代数学》实测）：子节点按 (page, y)
            # 排序，canon 序与阅读序在跨页交错时并不一致（如例9.5.2 排在其 canon
            # 更小的定理之后页）；纯 canon 比较会把回填项插错位。改用
            # ``(page_start, canon)`` 字典序定位：先过完所有「页更早或同页更小」
            # 的条目，停在第一个「页更晚或同页更大」的条目之前。
            _cp = int(getattr(child, "page_start", 0) or 0)
            if (_cp, cc) > (int(page or 0), canon):
                idx = i
                break
        sn.sub_sec.insert(idx, node)
        _fix_pages(tree)
        return True, sec_key or "(page-proximity)"
    # chapter-bucket（书无 section 节点）：按 canon 序插入而非 append——否则
    # 回填条目永远挂在章尾，B 层必报「顺序错乱」（Lee 2e 实测：Prop 11.25 被
    # append 到 11.51 之后）。canon 未知（None）才回落 append。
    idx = len(tree.sub_sec)
    if canon is not None:
        for i, child in enumerate(tree.sub_sec):
            _ct = child.get("type") if isinstance(child, dict) else getattr(child, "type", None)
            if _ct not in _ITEM_TYPES:
                continue
            cc = _canon_key(_PRIMARY, str(child.key))
            if cc is None or len(cc) != len(canon):
                continue
            _cp = int(getattr(child, "page_start", 0) or 0)
            if (_cp, cc) > (int(page or 0), canon):
                idx = i
                break
    tree.sub_sec.insert(idx, node)
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


# 类型 -> 代表性英文标签（单源导入 TYPE_TO_LABEL_EN）：供合成 md 重建可被
# B 层解析的条目头、以及 load_contract 复合键的标签恢复。
_TYPE_TO_LABEL = TYPE_TO_LABEL_EN
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
                    if _t in ("exercise", "problem"):
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
        if n.type == "problem":
            # 🔴 问题节点进 B 层（2026-09-12 拍板）：头 = 正名「问题」+ 裸短横键
            # （'问题11-1'——键经 3a 剥离无标签前缀，此处补正名）。B 层按 Problem
            # 组独立查连续性 / 顺序；源侧（raw scan 对裸短横头不可见）Problem 组
            # 为空，tail 比对方向为「md 比源少」→ 空源组不误报。
            key = str(n.key)
            label = _canon_label(_TYPE_TO_LABEL.get("problem", "Problem"))
            lines.append("**%s%s**" % (label, key))
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
# 🔴 Iwaniec-Kowalski 2026-09-28 实测：本集合漏 conjecture/assertion 时，
# insert_item 的定位循环 `if _ct not in _ITEM_TYPES: continue` 会跳过猜想节点，
# 回填条目越过在位的邻近大号、插错阅读序（定理7.31 落到 猜想7.32 之后 →
# B 层「顺序错乱」假象）。凡 TYPE_TO_LABEL_CN 里的条目类型都须在列。
_ITEM_TYPES = {"definition", "theorem", "lemma", "corollary",
               "proposition", "example", "remark", "conjecture",
               "assertion", "assumption", "condition", "axiom", "property"}


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


def _foreign_sections(bs, ch):
    """跨章引用节号集合（节级编号英文两级书专用，如 Tu《流形导论》/ Hilton-Stammbach）。

    全局节编号书（`chapter_first=False` + `ORDINAL_TWO_LEVEL`）的条号首段即**节号**，
    而节唯一归属某一章。`build_structure` / `scan_raw_items` 按**页码区间**扫某章，
    区间内常混排**指向他章的交叉引用**（如 ch4 页上 "Theorem 11.15" —— §11 属 ch3）。
    因 `chapter_first=False`，扫描侧不能用「首段 != 章号」过滤（首段是节号不是章号），
    于是这些引用被当成「本章缺项」。

    本函数返回**归属于其他章**的节号整数集合：调用方据此把首段落在此集合的扫描项判为
    交叉引用（reference），既不回填、也不阻断闸门。附录节号为字母（非纯数字）自然排除，
    不会与数字章节号混淆。
    """
    foreign = set()
    root = getattr(bs, "root", None) if bs is not None else None
    if root is None:
        return foreign
    target = str(ch).strip()
    for chap in getattr(root, "sub_sec", []) or []:
        if getattr(chap, "type", None) != "chapter":
            continue
        ck = str(getattr(chap, "key", "")).strip()
        if ck == target:
            continue  # 本章自己的节号不算「跨章」
        for node in getattr(chap, "sub_sec", []) or []:
            if getattr(node, "type", None) != "section":
                continue
            k = str(getattr(node, "key", "")).strip()
            if re.fullmatch(r"\d+", k):
                foreign.add(int(k))
    return foreign


def step2_sections(ch, start, end, ext, cfg, tree):
    """第 2 步：用 section_continuity（D 层）校验遗漏章节并回填 book_structure。

    喂 book_structure 派生的合成 md → D 层比对「源真值章节集」（直接重扫
    page_*.json，独立于抽取器）与 book_structure 契约，返回遗漏章节：
      * continuity_sections：书内章节序列的内部洞（节序断裂）；
      * missing_sections：落在 book_structure 最后一个已写节之后的整节缺失。
    二者合并即「源有而 book_structure 无」的遗漏章节集合。
    """
    if not str(ch)[:1].isdigit():
        # 附录字母章：D 层数字节号解析域之外，源侧节查漏跳过（不做无意义扫描，
        # 也避免回填路径 int("A") 崩溃）。
        return [], {"continuity": [], "tail": [], "skipped": "appendix-letter-chapter"}
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
_OCR_SUFFIX_DIGIT = {"b": "8", "o": "0", "i": "1", "l": "1", "s": "5",
                     "z": "2", "g": "9", "e": "6"}


def _contract_item_keys(tree):
    """契约树中全部条目节点（非 chapter/section/description/proof）的**原始键**小写集。

    供「字母后缀形近」豁免使用：`_canon_key` 不接受尾字母（`定理1b` 无 int 尾号），
    这类真身在 contract_items 里必然缺席，只能用裸键集合做存在性证据。"""
    ks = set()

    def walk(n):
        if getattr(n, "type", None) not in ("chapter", "section",
                                            "description", "proof"):
            k = str(getattr(n, "key", "") or "").strip().lower()
            if k:
                ks.add(k)
        for c in getattr(n, "sub_sec", None) or []:
            walk(c)
    walk(tree)
    return ks


def _norm_alnum(s):
    """只留小写字母与数字，并剥去**开头的数字串**（节序标本身）。

    OCR 文本与契约节题比对时忽略空格/标点/大小写；剥开头数字是因为两形态都要
    可比——契约 ``name`` 有的带序标（``"5.1 Definition and …"``，Apostol 实测）、
    有的只带裸标题，而候选 snippet 恒带序标。
    """
    return re.sub(r"^\d+", "", re.sub(r"[^a-z0-9]", "", str(s or "").lower()))


def _section_title_map(tree):
    """``{节序标元组: 归一节题文本}``——契约里每个小节节点的印刷标题。

    供「节题伪装」判据使用（见 :func:`step3_items`）：数字前置方案会把
    「5.1 Definition and basic properties of …」这类**小节标题行**读成条目
    ``Definition 5.1``，而该行正是契约里 §5.1 的标题本身。"""
    out = {}

    def walk(n):
        if getattr(n, "type", None) == "section":
            parts = [p for p in re.split(r"[.\-·，．]+", str(getattr(n, "key", "") or "").strip()) if p]
            if parts and all(p.isdigit() for p in parts):
                title = _norm_alnum(getattr(n, "name", "") or "")
                if title:
                    out.setdefault(tuple(int(p) for p in parts), title)
        for c in getattr(n, "sub_sec", None) or []:
            walk(c)
    walk(tree)
    return out


def step3_items(ch, start, end, ext, cfg, tree, contract_items, bs=None):
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

    # 🔴 跨章引用节号集（节级编号英文两级书，如 Tu/Hilton-Stammbach）：某章页区间内
    # 混排「指向他章」的交叉引用（如 ch4 页 "Theorem 11.15" 属 ch3 §11），因
    # chapter_first=False 扫描侧不能按「首段!=章号」过滤，会被当成缺项。守卫条件与
    # 下方去重逻辑一致，其他类型书 foreign_secs 恒空、行为不变。
    _foreign_secs = set()
    if (bs is not None and not getattr(cfg, "chapter_first", True)
            and cfg.primary_type == ORDINAL_TWO_LEVEL and cfg.language == "en"):
        _foreign_secs = _foreign_sections(bs, ch)

    raw_items = [it for it in scan_raw_items(ext, ch, start, end, cfg.primary_type, cfg.chapter_first, cfg.language,
                                             groups=getattr(cfg, "ordinal", None))
                 if str(it["label"]).strip().lower() not in _EXER_LABELS_RAW_LC]

    # 0) agent 已核实「非条目」的键（ignore_ch{N}.json，须附理由）：从源侧缺失集
    #    剔除，不得回填进契约。适用形态：OCR 把公式/编号散文误读成条目号
    #    （谷超豪《数学物理方程》ch10 实测：连乘积 1·3·5·…·(2n−1)! 被读成
    #    三级号 1.3-5）。ignore 审计（run_audit）仍会在报告中展示该条目供复核。
    try:
        from key_parse import normkey as _normkey
        _ign = _load_ignore_file(os.path.join(ext, f'ignore_{chapter_label(ch)}.json'))
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

    # 🔴 共享计数器豁免（Han-Lin《Elliptic PDEs》实测）：配置把多个标签并进**同一个
    # ordinal group**（= 它们共享一个升序计数器）时，同一编号全书只会出现一次。
    # 若该编号已以**另一标签**落在契约里（契约有 评注4.2），源侧又扫到
    # "Corollary 4.2 implies u ∈ C^{δ0}…"（章末 Notes 里的交叉引用/折行续句），
    # 那不是遗漏条目——回填会造出重复编号、B 层随即报顺序错乱。故判为
    # shared_counter：闸门不拦、不回填，但仍在报告里留痕供复核。
    def _shared_groups():
        out = []
        for g in getattr(cfg, "ordinal", None) or []:
            names = getattr(g, "name", None) or []
            if len(names) > 1:
                out.append({str(x).lower() for x in names}
                           | {str(_canon_label(str(x))).lower() for x in names})
        return out

    _shared = _shared_groups()
    if _shared:
        canon_labels = {}
        for _ck in contract_items:
            if (isinstance(_ck, tuple) and len(_ck) == 2
                    and isinstance(_ck[1], tuple)):
                _canon, _lab = _ck[1], str(_ck[0]).lower()
            else:
                _canon, _lab = tuple(_ck) if isinstance(_ck, tuple) else _ck, ''
            canon_labels.setdefault(_canon, set()).add(_lab)

    missing_items = []
    _contract_keys = _contract_item_keys(tree)
    _sec_titles = _section_title_map(tree)
    _phantom_sec_ck = set()   # 节题伪装候选（同样不得喂 B 层）
    _exempt_ck = set()   # suffix_confusion 豁免候选的复合键（B 层同样不得喂入）
    for ck, it in best.items():
        if ck in contract_items:
            continue
        c = tuple(it["canon"]) if isinstance(it["canon"], list) else it["canon"]
        # 🔴 uncat 影子匹配（Kreyszig 4.1-5 实测 2026-09-26）：契约侧该 canon
        # 以无类型 uncat 节点存在（印刷类型词被 OCR 吞），源侧带标签候选来自
        # 交叉引用句。条目本体在契约中，不缺、不可回填（会重复）——记
        # type_shadow 留痕，不进 readable/reference、不拦闸。
        # （load_contract 对无标签前缀可恢复的裸号 uncat 节点登记 ("uncat", canon)。）
        if ("uncat", c) in contract_items:
            missing_items.append({
                "key": it["key"], "label": it["label"], "page": it["page"],
                "snippet": it["snippet"], "canon": list(c),
                "has_label": it.get("has_label", False),
                "status": "type_shadow",
                "note": "contract holds this canon as type=uncat",
            })
            continue
        # 🔴 节题伪装（Apostol ch5 实测 2026-09-28）：数字前置方案（*_nf）会把小节
        # 标题「5.1 Definition and basic properties of …」整行扫成条头「Definition 5.1」
        # ——label 是从标题词里抓来的，不是印刷类型词。契约里同一序标**已是 section
        # 节点**，回填只会在契约里凭空造出「定义5.1」幽灵条目并带乱 B 层序列。
        # 判据（两重，防真条目恰与节同号）：候选来自 *_nf 方案且带 label；其 snippet
        # 归一文本与契约里**同序标小节**的标题互为前缀。命中记 section_title：
        # 不回填、不拦闸，且不得喂给 B 层。
        if str(it.get("scheme", "")).endswith("_nf") and it.get("has_label"):
            st = _sec_titles.get(tuple(c))
            sn = _norm_alnum(it.get("snippet", ""))
            if st and len(sn) >= 8 and (st.startswith(sn) or sn.startswith(st)):
                _phantom_sec_ck.add(ck)
                missing_items.append({
                    "key": it["key"], "label": it["label"], "page": it["page"],
                    "snippet": it["snippet"], "canon": list(c),
                    "has_label": True,
                    "status": "section_title",
                    "note": "contract holds section %s with this title; the "
                            "'label' is a title word, not an item head" % (
                                ".".join(str(x) for x in c)),
                })
                continue
        # 🔴 字母后缀序标 OCR 形近豁免（do Carmo ch5 实测 2026-09-26）：印刷
        # 「THEOREM 1a / 1b」的尾字母被抽取器按形近折成数字（b→8 → 伪候选
        # canon=(18,) 键「定理18」），而契约真身「定理1b」因尾字母无 int canon
        # 必然缺席 contract_items → 假 readable 缺项、闸门死锁；盲目回填会在契约
        # 里造出幽灵「定理18」。判据（两重，防真 18 与 1b 并存的书被误豁免）：
        # ① 候选 snippet 本身印着「标签 + 数字 + 单字母」形态；② 候选 canon 末段
        # 恰等于把该字母按形近表折回数字后的编号；③ 契约裸键里有同号同尾字母项。
        m_sf = re.match(r"^\s*([A-Za-z][A-Za-z .]*?)\s*(\d+)\s*([A-Za-z])\b",
                        it.get("snippet", ""))
        if (m_sf and c and isinstance(c[-1], int)
                and m_sf.group(3).lower() in _OCR_SUFFIX_DIGIT):
            _mangled = int(m_sf.group(2) + _OCR_SUFFIX_DIGIT[m_sf.group(3).lower()])
            _lab_sf = _canon_label(m_sf.group(1).strip().rstrip(". :"))
            if _mangled == c[-1] and \
                    f"{_lab_sf}{m_sf.group(2)}{m_sf.group(3)}".lower() \
                    in _contract_keys:
                _exempt_ck.add(ck)
                missing_items.append({
                    "key": it["key"], "label": it["label"], "page": it["page"],
                    "snippet": it["snippet"], "canon": list(c),
                    "has_label": it.get("has_label", False),
                    "status": "suffix_confusion",
                    "note": "printed ordinal '%s%s' OCR-mangled to %d; contract "
                            "holds the suffixed sibling" % (
                                m_sf.group(2), m_sf.group(3), _mangled),
                })
                continue
        # 🔴 跨章引用降级（节级编号英文两级书，Tu 实测）：该扫描项的首段（节号）归属
        # 其他章 → 是「指向他章」的交叉引用，非本章缺项。判 reference：不回填、不阻断，
        # 仅在报告留痕供复核（其真实条目已由归属章契约承载）。
        if _foreign_secs and isinstance(c, tuple) and len(c) >= 2 and c[0] in _foreign_secs:
            missing_items.append({
                "key": it["key"], "label": it["label"], "page": it["page"],
                "snippet": it["snippet"], "canon": list(c),
                "has_label": it.get("has_label", False),
                "status": "reference",
                "note": "cross-chapter reference (section %d owned by another chapter)" % c[0],
            })
            continue
        if _shared and c in canon_labels:
            _cand = {str(it["label"]).lower(),
                     str(_canon_label(str(it["label"]))).lower()}
            if any(_cand & grp and (canon_labels[c] & grp) for grp in _shared):
                missing_items.append({
                    "key": it["key"], "label": it["label"], "page": it["page"],
                    "snippet": it["snippet"], "canon": list(c),
                    "has_label": it.get("has_label", False),
                    "status": "shared_counter",
                })
                continue
        garbled = not (len(c) >= 1 and all(isinstance(x, int) for x in c)
                       and (len(c) < 2 or c[1] <= 60) and (len(c) < 3 or c[2] <= 200))
        is_ref = bool(_REF_RE.search(it.get("snippet", "")))
        if cfg.primary_type == ORDINAL_VAKIL and not garbled and \
                (len(c) == 2 or (len(c) >= 3 and c[-1] == 0)):
            # Vakil 体例结构不可能形态 → 幻影，不回填、不拦闸（Rising Sea 实测）：
            #  * 两段（"Proposition 10.1" ← 断号交叉引用 "Proposition 10.1.13)"、
            #    "Definition 2.2" ← 节标题 "2.2 Definition of sheaf…"——条目键恒为
            #    三段 C.S-N 或字母 C.S.A，两段只可能是引用/节号）；
            #  * 末段 0（练习字母 O 的 OCR 数字替身：5.5.O → 5.5-0；条目计数器
            #    从 1 起，C.S.0 在本体例中不存在）。
            missing_items.append({
                "key": it["key"], "label": it["label"], "page": it["page"],
                "snippet": it["snippet"], "canon": list(c),
                "has_label": it.get("has_label", False),
                "status": "reference",
            })
            continue
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
    # 🔴 suffix_confusion 豁免候选（印刷 1b 折成 18 一类）同样**不得喂给 B 层**：
    # 它们是同一真身的形近替身，留在源集里 B 会报「源最大 18 远大于 md 最大 3」
    # TAIL BLOCKING 幻影（do Carmo ch5 回归实测），闸门依旧死锁。
    b_raw = raw_items
    if _exempt_ck or _phantom_sec_ck:
        b_raw = []
        for it in raw_items:
            cc = tuple(it["canon"]) if isinstance(it["canon"], list) else it["canon"]
            if cc is None:
                b_raw.append(it)
                continue
            _ck2 = _composite_key(cfg.primary_type, it.get("label", "uncat"), cc)
            if _ck2 in _exempt_ck or _ck2 in _phantom_sec_ck:
                continue
            b_raw.append(it)
    bmeta = _run_b_layer(ch, start, end, ext, cfg, tree, b_raw)

    return missing_items, bmeta


def _run_b_layer(ch, start, end, ext, cfg, tree, source_items):
    """把 book_structure 派生 md + 源条目集喂给 item_numbering_integrity（B 层），
    返回其 metadata：{blocking, b_gap_warnings, b_tail_warnings, ignored_hit}。"""
    md = synthetic_item_md(tree)
    # 按章合并 ignore_ch{N}.json（与正式 verify 流程 ConfigLoader.ignore_for_chapter
    # 同语义）：否则预检管线里登记的稀疏号豁免对 B 层不可见，闸门永 FAIL。
    try:
        from dataclasses import replace as _dc_replace
        extra = _load_ignore_file(os.path.join(ext, f'ignore_{chapter_label(ch)}.json'))
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
def _node_f(n, k, default=None):
    return n.get(k, default) if isinstance(n, dict) else getattr(n, k, default)


def _sec_key_nums(key):
    """`2.1.3` → (2, 1, 3)；含非数字段（字母附录位、裸标题）返回 None。"""
    parts = re.split(r"[.\-]", str(key or "").strip())
    try:
        return tuple(int(p) for p in parts if p != "")
    except ValueError:
        return None


def subsection_order_problems(node):
    """🔒 同父小节键序闸（步骤3 blocking 项）。

    同一父节点下的 `section` 子节点，其**数字键**必须随契约列表顺序严格递增。
    成因（Rosen 8e ch2 实测）：章扉页只印 §N.M 级目录，`build_structure`
    的「目录页免疫回扫」把 §2.1.1 的通用词标题（`Introduction`）撞上**别的小节**
    （§2.6.1）的裸标题块 → §2.1.1 锚到 p211，契约里 §2.1 的子节序变成
    `2.1.2 … 2.1.8, 2.1.1`，§2.1 窗口被拖成 144–211，p211 的内容同时挂进
    §2.1.1 与 §2.6.1 两个节点（最终 md 里整段重复）。

    为什么必须由本闸兜住：D 层（section_continuity）只比对到 §N.M 一级——契约里
    没有 subsection 容器节点，level 3 的断裂/逆序它结构性失明；B/Q 层也不看节序。
    此处在**拆分单元之前**阻断，返工成本最低。

    判据只取「逆序」不取「缺号」：小节从 `.2` 起（首节无印刷序号）是合法形态，
    不算异常。字母附录位等非数字键一律跳过（不参与比较）。
    """
    out = []

    def rec(n, path):
        kids = _node_f(n, "sub_sec") or []
        seq = [(_node_f(c, "key"), _node_f(c, "page_start"),
                _node_f(c, "type")) for c in kids]
        prev = None
        for key, pg, typ in seq:
            if typ != "section":
                continue
            nums = _sec_key_nums(key)
            if nums is None:
                continue
            if prev is not None and nums < prev[0]:
                out.append(
                    "节序逆序：§%s（锚点页 %s）排在 §%s（锚点页 %s）之后"
                    "——小节锚点页与印刷节号自相矛盾（多半是章目录回扫把该节"
                    "锚到了别的小节的页面），须回 build_structure 修锚点后重跑本闸"
                    % (key, pg, prev[0] and ".".join(str(x) for x in prev[0]),
                       prev[1]))
            prev = (nums, pg)
        for c in kids:
            rec(c, path + "/%s" % _node_f(c, "key"))

    rec(node, "")
    return out


def ordinal_occupancy_sets(ch_node, miss_it2):
    """契约「序标占用表」：(条目 canon 集合, 节号字符串集合, 可读遗漏 canon 集合)。

    见 `step4_gate` 的 🔴 序标被他节点占用豁免注释。判据测试
    `verify/script/tests/test_ordinal_occupancy_gap.py`。
    """
    occ_items, occ_secs = set(), set()

    def walk(n):
        ck = _canon_key(_PRIMARY, str(n.key)) if n.key is not None else None
        if ck:
            if n.type == "section":
                occ_secs.add(".".join(str(x) for x in ck))
            else:
                occ_items.add(tuple(ck))
        for k in n.sub_sec:
            walk(k)

    walk(ch_node)
    gap_left = {tuple(m.get("canon") or ()) for m in (miss_it2 or [])
                if m.get("status") == "readable"}
    return occ_items, occ_secs, gap_left


_GAP_ORDINAL_RE = re.compile(r"(\d+(?:\.\d+)*)\s*缺号\s*(\d+)")
# 🔴 B 层缺号消息的锚是**窗口号** `gk = "<组号>:<窗口>"`（verify/item_numbering_integrity
# 的窗口路由：scope==3 组按 `## §` 标题分窗）。窗口有两种形态：
#   · 数字/点分节号（"4:14"、"0:1.2"）——上方 `_GAP_ORDINAL_RE` 把它与缺号拼成完整
#     序标 canon，交「契约占用表 / 源侧 readable 差集」判定；
#   · **字母小节**（附录按字母块分窗：Arnold《经典力学的数学方法》附录B 实测
#     "1:F 缺号 1（序列 7..10 不连续…"）。附录 B 全篇只有**一条** 定理 计数器
#     （定理1..6 印在字母块 D 的 p271-272、定理7..10 印在块 F 的 p273，其后
#     11..12 在 H、13 在 J、14..15 在 K），B 层按块开窗就把「前一节用掉的号」报成
#     本块缺号——数字锚形态的占用表对此**永不**命中（"1:F" 里 缺号 之前是字母），
#     于是成为假阻断。
# 判据（机械可验、不外溢）：窗口标识是字母 + 缺号 < 本窗已印序列的下界 + 该号在
# 本章契约里**同名标签**下的别的窗口确有其条 + 源侧差集在该号上没报 readable 遗漏。
# 四条同时成立才豁免，且一律登记进 `gate.b_gap_ordinal_occupancy` 供人工复核。
_GAP_LETTER_WINDOW_RE = re.compile(
    r"(?:^|[^\w])(\d{1,3}):([A-Za-z][A-Za-z0-9.]*)\s*缺号\s*(\d+)"
    r"(?:（序列\s*(\d+)\.\.(\d+))?")
_ITEM_KEY_LABEL_RE = re.compile(r"^([^\d.]+?)\s*(\d{1,3})$")


def letter_window_occupancy(ch_node):
    """契约条目占用表 ``{(所属节, 规范标签词): {号, ...}}``（仅服务字母窗口分支）。

    条目键形如 "定理7"（CN 单级）→ 标签 "定理" + 号 7。节 / 章 / 练习节点不计
    （练习/问题族 B 层豁免，与本表同纪律——它们不会报出缺号，也就无需抵账）。

    🔴 键必须带**所属节**（Arnold 实测 2026-09-28，本书附录B 的字母窗口
    `1:F 缺号 1（序列 7..10 …` 是该分支唯一真实来路）：本书条目计数器只在**所属节
    内**连续，同号 定理9 可以在 §36 确有其条、在别处真缺。旧实现按整章汇总
    `{标签: {号}}`，于是任一节的在账条目能把**另一节**的真漏抽洗白（闸门 PASS 而
    契约少一条）。父级取章下**第一层** section 键：字母块（附录把字母块升级成
    `## §`，键以字母起头）归一为 `""`，与 `shared_counter_letter_gap` 里「窗口令牌
    无点 = 裸字母」同源，使同一附录内跨字母块的共享计数器照旧互相抵账。
    """
    occ = {}

    def walk(n, sec):
        key = str(n.key or "")
        cur = sec
        if n.type == "section" and sec is None:
            cur = "" if not re.match(r"^\d", key) else key.split(".")[0]
        if n.type not in ("section", "chapter", "exercise", "problem"):
            m = _ITEM_KEY_LABEL_RE.match(key)
            if m:
                occ.setdefault((cur or "", _canon_label(m.group(1))),
                               set()).add(int(m.group(2)))
        for c in n.sub_sec:
            walk(c, cur)

    walk(ch_node, None)
    return occ


def shared_counter_letter_gap(message, group_labels, occ_label_nums, readable_nums):
    """字母窗口 + 跨块共享计数器 → ``"shared-counter-window"``；否则 None。

    ``group_labels``: ``{组号: {规范标签词}}``（cfg.ordinal 下标）；
    ``occ_label_nums``: `letter_window_occupancy` 的产物（按所属节分键）；
    ``readable_nums``: 源侧差集里 status=='readable' 的 ``{标签: {号}}``（安全网）。
    """
    w = _GAP_LETTER_WINDOW_RE.search(message)
    if not w:
        return None
    gi, win, missing = w.group(1), w.group(2), int(w.group(3))
    if win.isdigit():
        return None          # 数字窗口归 `_GAP_ORDINAL_RE` 的序标形态管
    lo = int(w.group(4)) if w.group(4) else None
    if lo is not None and missing >= lo:
        return None          # 序列内部的洞不是「前一节占用」
    labels = (group_labels or {}).get(int(gi)) or set()
    if not labels:
        return None
    for lab in labels:
        if missing in (readable_nums.get(lab) or ()):
            return None      # 源侧确有该条头却未进契约：真漏抽，不豁免
    # 窗口令牌 → 所属节：`35.G` 归 §35；裸字母 `F`（附录字母块即窗口）归 ""。
    parent = win.split(".")[0] if "." in win else ""
    if not re.match(r"^\d", parent):
        parent = ""
    for lab in labels:
        if missing in (occ_label_nums.get((parent, lab)) or ()):
            return "shared-counter-window"
    return None


def occupied_ordinal(message, occ_items, occ_secs, gap_left, letter_ctx=None):
    """B 层「缺号」消息 → 占用形态（``"item"`` / ``"section"`` /
    ``"shared-counter-window"``）；真缺号返回 None。

    安全网：该序标在源侧差集里被报成 `readable` 遗漏时**一律不豁免**——真漏抽的
    条头必先被 `scan_raw_items` 抓到，所以本判据只可能放过「书中本无此条」的
    印刷体例（共享计数器 / 序标被节标题占用），不会掩盖数据缺陷。

    ``letter_ctx``: ``(group_labels, occ_label_nums, readable_nums)``。数字窗口
    形态的消息不传时行为与旧版逐字一致；**字母窗口**形态的消息不传则直接抛
    `AssertionError`（判据未接线 = 调用点 bug，不得静默退化成假阻断）。
    """
    if not isinstance(message, str):
        return None
    m = _GAP_ORDINAL_RE.search(message)
    if m:
        try:
            canon = tuple(int(x) for x in m.group(1).split(".")) + (int(m.group(2)),)
        except ValueError:
            return None
        if canon in gap_left:
            return None
        if canon in occ_items:
            return "item"
        if ".".join(str(x) for x in canon) in occ_secs:
            return "section"
        return None
    if _GAP_LETTER_WINDOW_RE.search(message) and letter_ctx is None:
        # 🔴 判据未接线的**响铃**（fail-loud）：字母窗口形态的缺号消息到达本函数，
        # 而调用方没建占用表 → 旧行为是静默不豁免，整章被假阻断（Arnold 附录B
        # 实测：`_letter_ctx` 在 `step4_gate` 里算好了却漏传，6 条假缺号一路 FAIL，
        # 且因该分支无打印而毫无线索）。宁可炸出调用点，也不要让「忘接线」
        # 伪装成「数据有问题」。
        raise AssertionError(
            "字母窗口缺号消息未接 letter_ctx（判据未接线）：%s" % message.strip())
    if letter_ctx:
        return shared_counter_letter_gap(message, *letter_ctx)
    return None


def step4_gate(ext, ch, start, end, cfg, bs, ch_node_after, bmeta_before):
    """第 4 步：回填后重跑第 2 / 第 3 步，断言遗漏章节 / 可读遗漏项 / B 层 blocking 全部归零，
    保证 book_structure 既完整（无遗漏）又连续（章节序列 / 条目编号无洞）。"""
    tree2, items2, _secs2 = load_contract(ch_node_after)
    miss_sec2, _ = step2_sections(ch, start, end, ext, cfg, tree2)
    miss_it2, bmeta2 = step3_items(ch, start, end, ext, cfg, tree2, items2, bs)

    readable_left = [m for m in miss_it2 if m["status"] == "readable"]
    b_blocking = bmeta2.get("blocking", [])
    sec_left = list(miss_sec2)
    # B-layer blocking: numbering errors (out-of-order / gaps) are now blocking,
    # not just diagnostic — they propagate to unit content and final output.
    # Only exercise-block ordering issues are exempt (some books have genuine
    # non-sequential exercise numbering). B 层 blocking 条目现为字符串消息
    # （"  WARN (BLOCKING): ..."）；保留旧 dict 格式的豁免判断，非 dict 视为真 blocking。
    #
    # 🔴 练习号豁免（共享计数器书）：正文各标签共享节内计数器、练习另持**独立**
    # 节内计数器（Weibel 实测：Definition 10.3.1 与 Exercise 10.3.1 同节并存）。
    # 合并视图的合成 md 只含非练习条目，练习号在该视图下必然呈现为「缺号」，
    # 但契约**确实含有**该号（exercise 节点）——不是遗漏。凡缺号命中契约练习
    # 键 → 豁免；真正的缺号（契约全无该号）仍阻断，交 agent 回填/登记 ignore。
    ex_keys = set()

    def _collect_ex(n):
        if n.type in ("exercise", "problem"):
            ex_keys.add(str(n.key))
            # 🔴 带标签的练习/问题键（回填键式渲染出的 `问题7.19`）须同时登记
            # 裸号变体，否则 _is_exercise_gap 按 `7-19`/`7.19` 查不到、
            # 合成 md（不含练习）必然呈现的练习缺号无法豁免
            # （Iwaniec-Kowalski ch7 PROBLEM 7.19/7.25/7.29 实测）。
            ck = _canon_key(_PRIMARY, str(n.key))
            if ck:
                _cs = '.'.join(str(x) for x in ck[:-1])
                _tail = str(ck[-1])
                _bare = (_cs + '-' + _tail) if _cs else _tail
                ex_keys.add(_bare)
                ex_keys.add(_bare.replace('-', '.'))
        for k in n.sub_sec:
            _collect_ex(k)

    _collect_ex(ch_node_after)
    _ex_gap_re = re.compile(r"(\d+(?:\.\d+)*)\s*缺号\s*(\d+)")

    def _is_exercise_gap(b):
        if not isinstance(b, str):
            return False
        m = _ex_gap_re.search(b)
        if not m:
            return False
        sec, num = m.group(1), m.group(2)
        return f"{sec}-{num}" in ex_keys or f"{sec}.{num}" in ex_keys

    # 🔴 序标被他节点占用豁免（共享计数器 / 稀疏编号的**机械可验**形态；
    # Apostol《Introduction to Analytic Number Theory》ch7 / ch12 实测 2026-09-28）。
    # 两种印刷体例都会让「按标签分桶」的 B 层报出假缺号：
    #   ① 同章多个标签**共用一条计数器**——ch7 印 定理7.1/7.2/7.3、引理7.4…7.8、
    #      定理7.9/7.10，Theorem 桶看似的「缺号 4..8」其实由 Lemma 在账（Lemma 桶
    #      的「缺号 1..3」同理）；
    #   ② 序标被**节标题**占用——ch12 印 §12.11「Evaluation of …」，条目序列
    #      12.10 → 12.12 是真实印刷（源侧全方案扫描在该页找不到任何 12.11 条头）。
    # 判据：该序标在契约里**确有**另一节点（异标签条目 / section）**且**源侧差集
    # 在该序标**没有**报出可读遗漏——后者是关键安全网：真漏抽的条头一定先被
    # `scan_raw_items` 抓到并置 `readable`（→ `readable_left` 非空 → 闸门照拦），
    # 所以本豁免只可能放过「书中本无此条」的印刷体例，不会掩盖数据缺陷。
    # 放过的项目**不静默**：全部登记进 gate.b_gap_ordinal_occupancy 供人工复核
    # （替代 `ignore_chN` 手工账——ignore 是「人说了算」，本判据是「账说了算」）。
    _occ_items, _occ_secs, _gap_left_canon = ordinal_occupancy_sets(
        ch_node_after, miss_it2)
    # 字母窗口形态（附录按字母块分窗 + 计数器跨块延续，见
    # `_GAP_LETTER_WINDOW_RE` 注释）：另建「组号 → 标签词」「标签词 → 契约号集」
    # 「标签词 → 源侧 readable 号集」三张表，交给 occupied_ordinal 的 letter_ctx。
    _group_labels = {}
    for _i, _g in enumerate(getattr(cfg, "ordinal", None) or []):
        _group_labels[_i] = {_canon_label(str(x))
                             for x in (getattr(_g, "name", None) or [])}
    _occ_label_nums = letter_window_occupancy(ch_node_after)
    _readable_nums = {}
    for _m in (miss_it2 or []):
        if _m.get("status") != "readable":
            continue
        _c = _m.get("canon") or []
        if len(_c) == 1 and isinstance(_c[0], int):
            _readable_nums.setdefault(
                _canon_label(str(_m.get("label") or "")), set()).add(_c[0])
    _letter_ctx = (_group_labels, _occ_label_nums, _readable_nums)

    b_gap_occupancy = []
    real_b_blocking = []
    for b in b_blocking:
        if isinstance(b, dict) and b.get("exercise_block_only", False):
            continue
        if _is_exercise_gap(b):
            continue
        occ = occupied_ordinal(b, _occ_items, _occ_secs, _gap_left_canon,
                               letter_ctx=_letter_ctx)
        if occ:
            b_gap_occupancy.append({"message": str(b).strip(), "occupied_by": occ})
            continue
        real_b_blocking.append(b)
    # 🔴 同父小节键序闸（见 subsection_order_problems 注释）：D 层对 level 3
    # 结构性失明，锚点回扫扫歪时整节内容会重复挂两个节点，必须在拆单元前阻断。
    order_problems = subsection_order_problems(ch_node_after)
    # 🔴 契约锚点自洽闸（回填位缺口补齐）：``build_structure`` 已在写契约前跑过
    # ``check_contract_anchors``，但**回填路径**（``insert_item`` / 人工
    # ``manual_overrides``）在它之后落盘，锚点倒退的条目就此漏网——门控 ⑪（写源期）
    # 才报「单元跨节/跨页错位」，那时 27 章已拆完、返工面是整章。此处补拦 = 在
    # 拆单元之前阻断（Iwaniec-Kowalski ch3/ch5/ch20 实测 2026-09-28）。
    from lib.unit_order import check_contract_anchors
    try:
        anchor_problems = check_contract_anchors(ch_node_after.to_dict())
    except Exception as e:
        anchor_problems = ["契约锚点自查执行失败（fail-closed）：%r" % (e,)]
    passed = (not sec_left) and (not readable_left) and (not real_b_blocking) \
        and (not order_problems) and (not anchor_problems)
    return {
        "passed": passed,
        "residual_sections": sec_left,
        "residual_readable_items": [m["key"] for m in readable_left],
        "residual_b_blocking": real_b_blocking,
        "b_gap_ordinal_occupancy": b_gap_occupancy,
        "residual_section_order": order_problems,
        "residual_anchor_order": anchor_problems,
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
    missing_items, bmeta = step3_items(ch, start, end, ext, cfg, tree, contract_items, bs)

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
            mo_path = os.path.join(ext, f"manual_overrides_{chapter_label(ch)}.json")
            mo_list = _mo_mod.load_manual_overrides(mo_path)
            if mo_list:
                # 🔴 练习/问题通道去重集：load_contract 排除 exercise 与 problem
                # 节点（见上文 `if t in ("exercise", "problem"): return`），
                # contract_items 永远不含这两类键，下面的 composite-key 守卫对
                # 练习/问题类 overrides **恒不命中**——重跑 --backfill 会把整批
                # overrides 重复插入契约（Lee 2e 实测：ch1 BACKFILLED=13 全为
                # 已存在节点的重复；B 层合成 md 与闸门豁免对本通道双盲，重复
                # 静默）。故改查树内 exercise/problem 节点键（点/短横两形态都
                # 查），插入成功后回填集合保持幂等。
                _ex_keys = set()

                def _collect_ex_keys(n):
                    if n.type in ("exercise", "problem"):
                        _ex_keys.add(str(n.key))
                    for k in n.sub_sec:
                        _collect_ex_keys(k)

                _collect_ex_keys(tree)
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
                    if str(_mo_label).strip().lower() in _EXER_LABELS_RAW_LC:
                        _mk_variants = {str(mk), str(mk).replace("-", "."),
                                        str(mk).replace(".", "-")}
                        if _mk_variants & _ex_keys:
                            continue  # 树内已有同号 exercise 节点（避免重复插入）
                    elif _composite_key(_PRIMARY, _mo_label, c) in contract_items:
                        continue  # 已在校验起点契约中，跳过（避免重复插入）
                    ok, where = insert_item(tree, mk, _mo_label,
                                            mo.get("page", 0), c, mo.get("text", ""))
                    if ok:
                        if str(_mo_label).strip().lower() in _EXER_LABELS_RAW_LC:
                            _ex_keys.add(str(mk))
                        backfilled_items.append({"key": mk, "where": where,
                                                 "page": mo.get("page"), "source": "manual_override"})
        if backfilled_items or backfilled_sections:
            # 回填后写回分章契约：ch{N}.json 是"骨架+内容"
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
    with open(os.path.join(report_dir, f"{chapter_label(ch)}_completeness_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    n_read = sum(1 for m in missing_items if m["status"] == "readable")
    n_agent = sum(1 for m in missing_items if m["status"] == "needs_agent")
    n_ref = sum(1 for m in missing_items if m["status"] == "reference")
    print(f"{chapter_label(ch)}: contract(items={len(contract_items)}, sections={len(contract_sections)}) | "
          f"missing(sections={len(missing_sections)}[{len(sec_detail.get('continuity', []))}cont/{len(sec_detail.get('tail', []))}tail], "
          f"items={len(missing_items)}[{n_read}r/{n_ref}ref/{n_agent}a])"
          + (f" | BACKFILLED(items={len(backfilled_items)}, sections={len(backfilled_sections)})" if backfill else "")
          + f" | GATE={'PASS' if gate['passed'] else 'FAIL'}"
          + (f" | IGNORE-AUDIT(suspect={report['ignore_audit']['suspect_count']})" if report['ignore_audit']['suspect_count'] else "")
          + (f" | SUBSEC-ORDER({len(gate.get('residual_section_order', []))})"
             if gate.get('residual_section_order') else ""))
    for p in gate.get('residual_section_order') or []:
        print("  BLOCKING(节序): " + p)
    for p in gate.get('residual_anchor_order') or []:
        print("  BLOCKING(锚点): " + p)
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
    # 🔴 灌注 kind 注册表（Chapter/Appendix/Supplement 三分依赖 chapter_map 的显式 kind）
    try:
        from book_structure import prime_chapter_kinds
        prime_chapter_kinds(ext)
    except Exception:
        pass
    want = []
    for x in args[1:]:
        try:
            want.append(int(x))
        except ValueError:
            want.append(x.strip())  # 字母章号（附录 A/B…）
    if report_dir is None:
        report_dir = os.path.join(ext, "completeness_reports")

    cfg_path = os.path.join(ext, "verify_config.json")
    loader_obj = None
    try:
        loader = ConfigLoader(ext, os.path.dirname(ext.rstrip("/")) or ext)
        loader.require_complete()
        book = loader.book
        loader_obj = loader
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
            print(f"{chapter_label(ch)} SKIP (not in chapter_map)")
            continue
        s, e = rng[ch]
        # 附录章路由：字母章号（或章名含 Appendix/附录）切到 appendix 配置
        # （type 13 字母章位），与 build_structure / verify 的 per-chapter 路由
        # 同一机制；正文章零变化。
        cfg_ch = loader_obj.config_for_chapter(ch) if loader_obj is not None else book
        check_chapter(ext, ch, s, e, cfg_ch, backfill, report_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
